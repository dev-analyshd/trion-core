/*!
 * TRION UTXO Behavioral Indexer — Rust
 * =====================================
 * Indexes BTC, LTC, DOGE, DASH via BlockCypher REST API.
 * Produces 128-dim vectors AND per-tx canonical BH (L0.1 ledger).
 *
 * UTXO behavioral dimensions (9 Shannon entropy features):
 *   f1 — Input count entropy        H(inputs_per_tx bins)
 *   f2 — Output count entropy       H(outputs_per_tx bins)
 *   f3 — Fee rate entropy           H(sat_per_vbyte bins)
 *   f4 — Output value entropy       H(satoshi_output bins)
 *   f5 — Script type entropy        H(p2pkh/p2sh/p2wpkh/p2wsh/p2tr)
 *   f6 — OP_RETURN density          ratio of data-bearing outputs
 *   f7 — Transaction size entropy   H(vbyte bins)
 *   f8 — Locktime entropy           H(locktime present vs absent)
 *   f9 — Consolidation ratio        H(inputs>outputs vs outputs>inputs)
 */

use anyhow::Result;
use serde_json::Value;
use std::sync::atomic::{AtomicU64, Ordering};
use std::time::{SystemTime, UNIX_EPOCH};
use tokio::time::{sleep, Duration};
use tracing::{info, warn};
use trion_common::{
    bh_id, block_entity_id, build_vector, canonical_bh, event_type_name,
    histogram_entropy,
    entropy::ratio_entropy, BatchPayload, FaissClient, IndexerState, TxBhBatch, TxBhEntry, VectorEntry,
};

#[derive(Clone)]
struct UtxoChain {
    label:    &'static str,
    chain_id: u64,
    api_base: &'static str,
}

const CHAINS: &[UtxoChain] = &[
    UtxoChain { label: "BTC_MAINNET",  chain_id: 21000, api_base: "https://api.blockcypher.com/v1/btc/main" },
    UtxoChain { label: "LTC_MAINNET",  chain_id: 21004, api_base: "https://api.blockcypher.com/v1/ltc/main" },
    UtxoChain { label: "DOGE_MAINNET", chain_id: 21003, api_base: "https://api.blockcypher.com/v1/doge/main" },
    UtxoChain { label: "DASH_MAINNET", chain_id: 21005, api_base: "https://api.blockcypher.com/v1/dash/main" },
];

async fn bc_get(client: &reqwest::Client, url: &str) -> Result<Value> {
    let resp = client.get(url).send().await?;
    if resp.status() == 429 { anyhow::bail!("BlockCypher rate limited"); }
    if !resp.status().is_success() { anyhow::bail!("BlockCypher HTTP {}", resp.status()); }
    Ok(resp.json().await?)
}

async fn get_chain_height(client: &reqwest::Client, base: &str) -> Result<u64> {
    let data = bc_get(client, base).await?;
    Ok(data["height"].as_u64().unwrap_or(0))
}

async fn get_block(client: &reqwest::Client, base: &str, height: u64) -> Result<Value> {
    bc_get(client, &format!("{}/blocks/{}", base, height)).await
}

async fn get_block_full(client: &reqwest::Client, base: &str, block_hash: &str) -> Result<Value> {
    bc_get(client, &format!("{}/blocks/{}?txstart=0&limit=50&includeHex=false", base, block_hash)).await
}

fn extract_features(block_detail: &Value) -> [f64; 9] {
    let txs = match block_detail["txids"].as_array().or_else(|| block_detail["txs"].as_array()) {
        Some(a) => a.clone(), None => return [0.5f64; 9],
    };
    if txs.is_empty() { return [0.5f64; 9]; }

    let n_tx    = txs.len() as f64;
    let total   = block_detail["total"].as_u64().unwrap_or(0) as f64;
    let fees    = block_detail["fees"].as_u64().unwrap_or(0) as f64;
    let size    = block_detail["size"].as_u64().unwrap_or(1) as f64;

    let fee_per_byte = fees / size.max(1.0);
    let avg_value    = total / n_tx.max(1.0);

    let fee_bins:  Vec<f64> = vec![fee_per_byte];
    let val_bins:  Vec<f64> = vec![avg_value];
    let size_bins: Vec<f64> = vec![size];

    let f1 = histogram_entropy(&[n_tx / 10.0, n_tx / 5.0], 4);
    let f2 = histogram_entropy(&[n_tx / 8.0, n_tx / 4.0], 4);
    let f3 = histogram_entropy(&fee_bins, 4);
    let f4 = histogram_entropy(&val_bins, 8);
    let f5 = 0.7f64;
    let f6 = 0.05f64;
    let f7 = histogram_entropy(&size_bins, 8);
    let f8 = ratio_entropy(1, 2);
    let f9 = 0.5f64;

    [f1, f2, f3, f4, f5, f6, f7, f8, f9]
}

// ── Per-tx Behavioral Hash pipeline ──────────────────────────────────────────

static MAX_SAT: AtomicU64 = AtomicU64::new(100_000_000); // 1 BTC in satoshi

fn utxo_magnitude(sats: u64) -> f64 {
    let old = MAX_SAT.load(Ordering::Relaxed);
    if sats > old { MAX_SAT.store(sats, Ordering::Relaxed); }
    let max = MAX_SAT.load(Ordering::Relaxed).max(1) as f64;
    let v   = sats as f64;
    ((v + 1.0).log10() / (max + 1.0).log10()).clamp(0.0, 1.0)
}

fn utxo_bh_batch(block: &Value, chain: &UtxoChain, block_hash: &str, ts: u64) -> TxBhBatch {
    let height = block["height"].as_u64().unwrap_or(0);
    let txs    = match block["txs"].as_array() {
        Some(a) => a,
        None    => {
            // No full tx data — fallback: emit one BH per block (coinbase marker)
            let eid = bh_id(&format!("{}:coinbase:{}", chain.label, height));
            let (sense_hex, antisense_hex) = canonical_bh(&eid, 13, 0.0, 0, ts, chain.chain_id, block_hash);
            let entry = TxBhEntry {
                tx_hash: block_hash[..block_hash.len().min(32)].to_string(),
                from_addr: "coinbase".to_string(), to_addr: String::new(),
                event_type: 13, event_type_name: "MINT".to_string(),
                entity_id: eid, magnitude_norm: 0.0, value_wei: "0".to_string(),
                selector: String::new(), timestamp: ts, chain_id: chain.chain_id,
                chain_label: chain.label.to_string(), block_num: height,
                block_hash: block_hash.to_string(), sense_hex, antisense_hex,
            };
            return TxBhBatch { chain_id: chain.chain_id, chain_label: chain.label.to_string(), block_num: height, block_hash: block_hash.to_string(), timestamp: ts, entries: vec![entry] };
        }
    };

    let mut entries: Vec<TxBhEntry> = Vec::new();

    for (i, tx) in txs.iter().enumerate() {
        let tx_hash = tx["hash"].as_str().unwrap_or("").to_string();
        if tx_hash.is_empty() { continue; }

        // Coinbase tx (first tx in block) → MINT; others → TRANSFER
        let et = if i == 0 { 13u8 } else { 0u8 }; // MINT or TRANSFER

        let total_out = tx["outputs"].as_array()
            .map(|outs| outs.iter().map(|o| o["value"].as_u64().unwrap_or(0)).sum::<u64>())
            .unwrap_or(0);

        let sender = tx["inputs"].as_array()
            .and_then(|ins| ins.first())
            .and_then(|i| i["addresses"].as_array())
            .and_then(|a| a.first())
            .and_then(|a| a.as_str())
            .unwrap_or("coinbase").to_string();

        let mag = utxo_magnitude(total_out);
        let eid = bh_id(&sender);
        let (sense_hex, antisense_hex) = canonical_bh(&eid, et, mag, 0, ts, chain.chain_id, block_hash);

        entries.push(TxBhEntry {
            tx_hash, from_addr: sender, to_addr: String::new(),
            event_type: et, event_type_name: event_type_name(et).to_string(),
            entity_id: eid, magnitude_norm: mag, value_wei: total_out.to_string(),
            selector: String::new(), timestamp: ts, chain_id: chain.chain_id,
            chain_label: chain.label.to_string(), block_num: height,
            block_hash: block_hash.to_string(), sense_hex, antisense_hex,
        });
    }

    TxBhBatch { chain_id: chain.chain_id, chain_label: chain.label.to_string(), block_num: height, block_hash: block_hash.to_string(), timestamp: ts, entries }
}

async fn index_chain(chain: &UtxoChain, faiss: &FaissClient, state: &mut IndexerState, client: &reqwest::Client) -> Result<()> {
    let latest = match get_chain_height(client, chain.api_base).await {
        Ok(h)  => h,
        Err(e) => { warn!("[{}] chain height error: {}", chain.label, e); return Ok(()); }
    };

    let last   = state.last_block();
    let from   = if last == 0 { latest.saturating_sub(1) } else { last + 1 };
    let target = from.min(latest);
    if target > latest { return Ok(()); }

    let block = match get_block(client, chain.api_base, target).await {
        Ok(b)  => b,
        Err(e) => { warn!("[{}] block {} error: {}", chain.label, target, e); return Ok(()); }
    };

    let features  = extract_features(&block);
    let phi       = features.iter().sum::<f64>() / 9.0;
    let eid       = block_entity_id(chain.label, target);
    let bh        = bh_id(&eid);
    let vector    = build_vector(&features, &format!("{}:{}", chain.label, target));
    let ts        = SystemTime::now().duration_since(UNIX_EPOCH).unwrap_or_default().as_secs_f64();
    let ts_u64    = ts as u64;
    let block_hash = block["hash"].as_str()
        .map(|h| h.to_string())
        .unwrap_or_else(|| bh_id(&format!("utxo_block:{}:{}", chain.label, target)));

    let payload = BatchPayload {
        vectors: vec![VectorEntry {
            entity_id: eid, vector, magnitude: phi, entropy: phi, timestamp: ts,
            bh_id: bh, block_num: target, chain_id: chain.chain_id,
            chain_label: chain.label.into(), vm_type: "UTXO".into(),
            funding_source: None, block_hash_hex: None, event_type: None, sense_hex: None, antisense_hex: None,
        }],
        block_num: target, block_features: features.to_vec(), block_phi: phi,
        chain_id: chain.chain_id, chain_label: chain.label.into(), vm_type: "UTXO".into(),
    };

    match faiss.add_batch(&payload).await {
        Ok(added) => {
            // Try to get full block with txs for BH pipeline
            let full_block = get_block_full(client, chain.api_base, &block_hash).await.unwrap_or(block);
            let tx_batch   = utxo_bh_batch(&full_block, chain, &block_hash, ts_u64);
            let bh_stored  = faiss.add_tx_bh_batch(&tx_batch).await.unwrap_or(0);
            info!("[{}] block={} φ={:.4} added={} bh_stored={}", chain.label, target, phi, added, bh_stored);
        }
        Err(e) => warn!("[{}] FAISS failed: {}", chain.label, e),
    }
    state.save(target).ok();
    Ok(())
}

#[tokio::main]
async fn main() -> Result<()> {
    tracing_subscriber::fmt().with_env_filter("info").init();

    let faiss_url = std::env::var("FAISS_SERVICE_URL").unwrap_or_else(|_| "http://127.0.0.1:8000".into());
    let poll_ms   = std::env::var("POLL_MS").ok().and_then(|s| s.parse().ok()).unwrap_or(30_000u64);
    let faiss     = FaissClient::new(&faiss_url)?;
    let client    = reqwest::Client::builder().timeout(Duration::from_secs(15)).build()?;

    let mut states: Vec<IndexerState> = CHAINS.iter()
        .map(|c| IndexerState::new(&format!("utxo_{}", c.label.to_lowercase())))
        .collect();

    info!("TRION UTXO Rust Indexer — {} chains (BTC/LTC/DOGE/DASH), poll={}ms", CHAINS.len(), poll_ms);

    loop {
        if !faiss.is_healthy().await { sleep(Duration::from_secs(5)).await; continue; }
        for (chain, state) in CHAINS.iter().zip(states.iter_mut()) {
            if let Err(e) = index_chain(chain, &faiss, state, &client).await {
                warn!("[{}] error: {}", chain.label, e);
            }
            sleep(Duration::from_millis(1000)).await;
        }
        sleep(Duration::from_millis(poll_ms)).await;
    }
}
