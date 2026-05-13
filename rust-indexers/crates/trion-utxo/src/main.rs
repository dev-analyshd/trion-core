/*!
 * TRION UTXO Behavioral Indexer — Rust
 * =====================================
 * Indexes BTC, LTC, DOGE, DASH via BlockCypher REST API.
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
use std::time::{SystemTime, UNIX_EPOCH};
use tokio::time::{sleep, Duration};
use tracing::{info, warn};
use trion_common::{
    bh_id, block_entity_id, build_vector, freq_entropy, histogram_entropy,
    entropy::ratio_entropy, BatchPayload, FaissClient, IndexerState, VectorEntry,
};

#[derive(Clone)]
struct UtxoChain {
    label:    &'static str,
    chain_id: u64,
    api_base: &'static str,
}

const CHAINS: &[UtxoChain] = &[
    UtxoChain { label: "BTC_MAINNET",  chain_id: 2000, api_base: "https://api.blockcypher.com/v1/btc/main" },
    UtxoChain { label: "LTC_MAINNET",  chain_id: 2010, api_base: "https://api.blockcypher.com/v1/ltc/main" },
    UtxoChain { label: "DOGE_MAINNET", chain_id: 2020, api_base: "https://api.blockcypher.com/v1/doge/main" },
    UtxoChain { label: "DASH_MAINNET", chain_id: 2030, api_base: "https://api.blockcypher.com/v1/dash/main" },
];

async fn bc_get(client: &reqwest::Client, url: &str) -> Result<Value> {
    let resp = client.get(url).send().await?;
    if resp.status() == 429 {
        anyhow::bail!("BlockCypher rate limited");
    }
    if !resp.status().is_success() {
        anyhow::bail!("BlockCypher HTTP {}", resp.status());
    }
    Ok(resp.json().await?)
}

async fn get_chain_height(client: &reqwest::Client, base: &str) -> Result<u64> {
    let data = bc_get(client, base).await?;
    Ok(data["height"].as_u64().unwrap_or(0))
}

async fn get_block(client: &reqwest::Client, base: &str, height: u64) -> Result<Value> {
    bc_get(client, &format!("{}/blocks/{}", base, height)).await
}

async fn get_block_txs(client: &reqwest::Client, base: &str, block_hash: &str) -> Result<Value> {
    bc_get(client, &format!("{}/blocks/{}?txstart=0&limit=100", base, block_hash)).await
}

fn extract_features(block_detail: &Value) -> [f64; 9] {
    let txs = match block_detail["txids"].as_array().or_else(|| block_detail["txs"].as_array()) {
        Some(a) => a.clone(), None => return [0.5f64; 9],
    };
    if txs.is_empty() { return [0.5f64; 9]; }

    // From block-level stats (BlockCypher block endpoint)
    let n_tx     = txs.len() as f64;
    let total    = block_detail["total"].as_u64().unwrap_or(0) as f64;
    let fees     = block_detail["fees"].as_u64().unwrap_or(0) as f64;
    let size     = block_detail["size"].as_u64().unwrap_or(1) as f64;

    // Derived UTXO entropy proxies
    let fee_per_byte = fees / size.max(1.0);
    let avg_value    = total / n_tx.max(1.0);

    let fee_bins:  Vec<f64> = vec![fee_per_byte];
    let val_bins:  Vec<f64> = vec![avg_value];
    let size_bins: Vec<f64> = vec![size];

    // Without full tx detail, use aggregate proxies
    let f1 = histogram_entropy(&[n_tx / 10.0, n_tx / 5.0], 4);  // input count proxy
    let f2 = histogram_entropy(&[n_tx / 8.0, n_tx / 4.0], 4);   // output count proxy
    let f3 = histogram_entropy(&fee_bins, 4);
    let f4 = histogram_entropy(&val_bins, 8);
    let f5 = 0.7f64; // script type — uniform approximation without full UTXO detail
    let f6 = 0.05f64; // OP_RETURN density — low by default
    let f7 = histogram_entropy(&size_bins, 8);
    let f8 = ratio_entropy(1, 2); // locktime entropy — assume 50/50
    let f9 = 0.5f64; // consolidation ratio

    [f1, f2, f3, f4, f5, f6, f7, f8, f9]
}

async fn index_chain(chain: &UtxoChain, faiss: &FaissClient, state: &mut IndexerState, client: &reqwest::Client) -> Result<()> {
    let latest = match get_chain_height(client, chain.api_base).await {
        Ok(h)  => h,
        Err(e) => { warn!("[{}] chain height error: {}", chain.label, e); return Ok(()); }
    };

    let last = state.last_block();
    let from = if last == 0 { latest.saturating_sub(1) } else { last + 1 };

    // UTXO chains are slow — only fetch 1 block per poll to respect rate limits
    let target = from.min(latest);
    if target > latest { return Ok(()); }

    let block = match get_block(client, chain.api_base, target).await {
        Ok(b)  => b,
        Err(e) => { warn!("[{}] block {} error: {}", chain.label, target, e); return Ok(()); }
    };

    let features = extract_features(&block);
    let phi      = features.iter().sum::<f64>() / 9.0;
    let eid      = block_entity_id(chain.label, target);
    let bh       = bh_id(&eid);
    let vector   = build_vector(&features, &format!("{}:{}", chain.label, target));
    let ts       = SystemTime::now().duration_since(UNIX_EPOCH).unwrap_or_default().as_secs_f64();

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
        Ok(added) => info!("[{}] block={} φ={:.4} added={}", chain.label, target, phi, added),
        Err(e)    => warn!("[{}] FAISS failed: {}", chain.label, e),
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
            // Respect BlockCypher rate limit: max 3 req/s for free tier
            sleep(Duration::from_millis(1000)).await;
        }
        sleep(Duration::from_millis(poll_ms)).await;
    }
}
