/*!
 * TRION Cardano Behavioral Indexer — Rust
 * Polls Koios public REST. 9 entropy features + per-tx canonical BH.
 * Event mapping: mint→MINT, Plutus scripts→SWAP, assets→TRANSFER, certs→STAKE.
 */

use anyhow::Result;
use serde_json::Value;
use tokio::time::{sleep, Duration};
use tracing::{info, warn};
use trion_common::{
    bh_id, block_entity_id, build_vector, canonical_bh, event_type_name,
    freq_entropy, histogram_entropy,
    entropy::ratio_entropy, BatchPayload, FaissClient, IndexerState, TxBhBatch, TxBhEntry, VectorEntry,
};

const CHAIN_ID:  u64  = 9400;
const CHAIN_LBL: &str = "CARDANO";
const VM_TYPE:   &str = "CARDANO";
const KOIOS_URLS: &[&str] = &[
    "https://api.koios.rest/api/v1",
    "https://guild.koios.rest/api/v1",
];

async fn koios_get(client: &reqwest::Client, base: &str, path: &str) -> Result<Value> {
    let url = format!("{}{}", base.trim_end_matches('/'), path);
    let resp = client.get(&url).header("Accept", "application/json")
        .header("User-Agent", "trion-indexer/1.0").send().await?;
    if !resp.status().is_success() { anyhow::bail!("Koios HTTP {} on {}", resp.status(), path); }
    Ok(resp.json().await?)
}

async fn koios_post(client: &reqwest::Client, base: &str, path: &str, body: &str) -> Result<Value> {
    let url = format!("{}{}", base.trim_end_matches('/'), path);
    let resp = client.post(&url).header("Content-Type", "application/json")
        .header("Accept", "application/json").header("User-Agent", "trion-indexer/1.0")
        .body(body.to_string()).send().await?;
    if !resp.status().is_success() { anyhow::bail!("Koios POST HTTP {} on {}", resp.status(), path); }
    Ok(resp.json().await?)
}

fn classify_cardano(tx: &Value) -> u8 {
    let mint = tx.get("mint").and_then(|m| m.as_array()).map(|a| !a.is_empty()).unwrap_or(false);
    if mint { return 13; }
    let has_plutus = tx.get("plutus_scripts").is_some() || tx.get("script_size").is_some();
    if has_plutus { return 1; }
    let has_assets = tx.get("asset_list").and_then(|a| a.as_array())
        .map(|a| !a.is_empty()).unwrap_or(false);
    if has_assets { return 0; }
    if tx.get("stake_cert").is_some() { return 3; }
    0
}

fn tx_lovelace(tx: &Value) -> u64 {
    tx.get("outputs").and_then(|o| o.as_array())
        .map(|outputs| outputs.iter().filter_map(|out| out.get("value").and_then(|v| v.as_u64())).sum())
        .unwrap_or(0)
}

fn tx_input_addrs(tx: &Value) -> Vec<String> {
    tx.get("inputs").and_then(|i| i.as_array())
        .map(|inputs| inputs.iter().filter_map(|inp| inp.get("payment_addr").and_then(|a| a.as_str()))
            .map(|s| s.to_string()).collect())
        .unwrap_or_default()
}

fn tx_output_addrs(tx: &Value) -> Vec<String> {
    tx.get("outputs").and_then(|o| o.as_array())
        .map(|outputs| outputs.iter().filter_map(|out| out.get("payment_addr").and_then(|a| a.as_str()))
            .map(|s| s.to_string()).collect())
        .unwrap_or_default()
}

fn extract_features(txs: &[Value]) -> [f64; 9] {
    if txs.is_empty() { return [0.5f64; 9]; }
    let mut ttypes = Vec::new(); let mut inputs = Vec::new(); let mut outputs = Vec::new();
    let mut amounts = Vec::new(); let mut fees = Vec::new(); let mut assets = Vec::new();
    let (mut plutus, mut plain) = (0u64, 0u64);
    let mut input_counts = Vec::new(); let mut output_counts = Vec::new();

    for tx in txs {
        ttypes.push(tx.get("type").and_then(|v| v.as_str()).unwrap_or("unknown").to_string());
        let in_addrs = tx_input_addrs(tx);
        let out_addrs = tx_output_addrs(tx);
        inputs.extend(in_addrs.clone());
        outputs.extend(out_addrs.clone());
        let lovelace = tx_lovelace(tx);
        if lovelace > 0 { amounts.push(lovelace as f64 / 1e6); }
        fees.push(tx.get("fee").and_then(|f| f.as_u64()).unwrap_or(0) as f64 / 1e6);
        if let Some(asset_list) = tx.get("asset_list").and_then(|a| a.as_array()) {
            for asset in asset_list {
                assets.push(asset.get("policy_id").and_then(|p| p.as_str()).unwrap_or("native").to_string());
            }
        }
        if tx.get("plutus_scripts").is_some() || tx.get("script_size").is_some() { plutus += 1; } else { plain += 1; }
        input_counts.push(in_addrs.len() as f64);
        output_counts.push(out_addrs.len() as f64);
    }
    [
        freq_entropy(&ttypes), freq_entropy(&inputs), freq_entropy(&outputs),
        histogram_entropy(&amounts, 8), histogram_entropy(&fees, 8),
        freq_entropy(&assets), ratio_entropy(plutus, plutus + plain),
        histogram_entropy(&input_counts, 5), histogram_entropy(&output_counts, 5),
    ]
}

/// CANONICAL_BH.md §4 — deterministic magnitude normalization:
///   human = raw / 10^6 (ADA lovelace); M = min(1, log10(human + 1) / log10(1001))
/// The rolling session-max tracker was removed: it made the BH of a fixed
/// transaction depend on what else the process had observed (canonical
/// violation — the same tx must always produce the same BH).
fn ada_magnitude(lovelace: u64) -> f64 {
    let human = lovelace as f64 / 1e6;
    if human <= 0.0 { return 0.0; }
    ((human + 1.0).log10() / (1001.0_f64).log10()).min(1.0)
}

fn cardano_bh_batch(txs: &[Value], height: u64, block_hash: &str, ts: u64) -> TxBhBatch {
    let mut entries = Vec::new();
    for tx in txs {
        let hash = tx.get("tx_hash").and_then(|v| v.as_str()).unwrap_or("").to_string();
        if hash.is_empty() { continue; }
        let sender = tx_input_addrs(tx).first().cloned().unwrap_or_else(|| "unknown".to_string());
        let dest = tx_output_addrs(tx).first().cloned().unwrap_or_default();
        let et = classify_cardano(tx);
        let lovelace = tx_lovelace(tx);
        let mag = ada_magnitude(lovelace);
        let eid = bh_id(&sender);
        let (sense_hex, antisense_hex) = canonical_bh(&eid, et, mag, 0, ts, CHAIN_ID, block_hash);
        entries.push(TxBhEntry {
            tx_hash: hash, from_addr: sender, to_addr: dest,
            event_type: et, event_type_name: event_type_name(et).to_string(),
            entity_id: eid, magnitude_norm: mag, value_wei: lovelace.to_string(),
            selector: tx.get("type").and_then(|v| v.as_str()).unwrap_or("").to_string(),
            timestamp: ts, chain_id: CHAIN_ID, chain_label: CHAIN_LBL.to_string(),
            block_num: height, block_hash: block_hash.to_string(),
            sense_hex, antisense_hex,
        });
    }
    TxBhBatch { chain_id: CHAIN_ID, chain_label: CHAIN_LBL.to_string(),
                block_num: height, block_hash: block_hash.to_string(),
                timestamp: ts, entries }
}

#[tokio::main]
async fn main() -> Result<()> {
    tracing_subscriber::fmt().with_env_filter("info").init();
    let faiss_url = std::env::var("FAISS_SERVICE_URL").unwrap_or_else(|_| "http://127.0.0.1:8000".into());
    let poll_ms = std::env::var("POLL_MS").ok().and_then(|s| s.parse().ok()).unwrap_or(20_000u64);
    let mut base = std::env::var("CARDANO_KOIOS_URL").unwrap_or_else(|_| KOIOS_URLS[0].into());
    let mut rpc_idx = 0usize;  // RPC failover rotation index
    let faiss = FaissClient::new(&faiss_url)?;
    let state = IndexerState::new("cardano");
    let client = reqwest::Client::builder().timeout(Duration::from_secs(20)).build()?;
    info!("TRION Cardano Indexer — chain={} poll={}ms", CHAIN_ID, poll_ms);

    loop {
        if !faiss.is_healthy().await { sleep(Duration::from_secs(5)).await; continue; }
        let latest = match koios_get(&client, &base, "/tip").await {
            Ok(v) => v.as_array().and_then(|a| a.first())
                .and_then(|tip| tip.get("block_no")).and_then(|b| b.as_u64()).unwrap_or(0),
            Err(e) => { warn!("Cardano tip error: {} — rotating RPC", e); { rpc_idx += 1; base = KOIOS_URLS[rpc_idx % KOIOS_URLS.len()].into(); } sleep(Duration::from_millis(poll_ms)).await; continue; }
        };
        if latest == 0 { sleep(Duration::from_millis(poll_ms)).await; continue; }
        let last = state.last_block();
        let from = if last == 0 { latest.saturating_sub(1) } else { last + 1 };

        for height in from..=latest.min(from + 1) {
            let body = format!("{{\"_block_heights\":[{}]}}", height);
            let txs = match koios_post(&client, &base, "/tx_info", &body).await {
                Ok(v) => v.as_array().cloned().unwrap_or_default(),
                Err(e) => { warn!("[{}] block {} error: {}", CHAIN_LBL, height, e); continue; }
            };
            // CANONICAL_BH.md §5 — Koios block_time (ISO 8601) of the
            // block's first tx; 0 = unknown. Never wall-clock.
            let ts = txs.first()
                .and_then(|t| t.get("block_time"))
                .and_then(|v| v.as_str())
                .map(trion_common::iso8601_to_epoch)
                .unwrap_or(0);
            let block_hash = txs.first().and_then(|t| t.get("block_hash").and_then(|h| h.as_str())).unwrap_or("");
            if txs.is_empty() { state.save(height).ok(); continue; }

            let features = extract_features(&txs);
            let phi = features.iter().sum::<f64>() / 9.0;
            let eid = block_entity_id(CHAIN_LBL, height);
            let bh = bh_id(&eid);
            let vector = build_vector(&features, &format!("{}:{}", CHAIN_LBL, height));
            // SEC-05 / SWEEP-B D1 — pass the REAL Koios block hash VERBATIM
            // (tx_info's `block_hash` — the same hash the Python streamer's
            // CARDANO fetcher reads from /blocks as blk["hash"]);
            // the lenient decoder inside canonical_bh owns the §9 hex decode,
            // so pre-normalising here — the old SHA3 substitution
            // (bh_id(block_hash)) or the interim 0ef64fd decode-and-re-encode
            // that dropped the chain's own "0x…" string — is exactly what §9
            // forbids ("never a silent substitution"). Genuinely-missing →
            // warn + honest "0x0" (32 zero bytes), never a fabricated
            // synthetic id.
            let block_hash_hex = if block_hash.is_empty() {
                warn!("[{}] block {}: no block hash from Koios — zero block hash", CHAIN_LBL, height);
                "0x0".to_string()
            } else {
                block_hash.to_string()
            };

            let payload = BatchPayload {
                vectors: vec![VectorEntry {
                    entity_id: eid, vector, magnitude: phi, entropy: phi,
                    timestamp: ts as f64, bh_id: bh, block_num: height,
                    chain_id: CHAIN_ID, chain_label: CHAIN_LBL.into(), vm_type: VM_TYPE.into(),
                    funding_source: None, block_hash_hex: Some(block_hash_hex.clone()),
                    event_type: Some(classify_cardano(&txs[0])),
                    sense_hex: None, antisense_hex: None,
                }],
                block_num: height, block_features: features.to_vec(), block_phi: phi,
                chain_id: CHAIN_ID, chain_label: CHAIN_LBL.into(), vm_type: VM_TYPE.into(),
            };
            match faiss.add_batch(&payload).await {
                Ok(added) => {
                    let tx_batch = cardano_bh_batch(&txs, height, &block_hash_hex, ts);
                    let bh_stored = faiss.add_tx_bh_batch(&tx_batch).await.unwrap_or(0);
                    info!("[{}] block={} txs={} φ={:.4} added={} bh={}", CHAIN_LBL, height, txs.len(), phi, added, bh_stored);
                }
                Err(e) => warn!("[{}] FAISS failed: {}", CHAIN_LBL, e),
            }
            state.save(height).ok();
        }
        sleep(Duration::from_millis(poll_ms)).await;
    }
}
