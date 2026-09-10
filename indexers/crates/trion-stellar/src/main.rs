/*!
 * TRION Stellar (Soroban VM) Behavioral Indexer — Rust
 * Polls Stellar ledgers via Horizon API, pushes 128-dim vectors + per-tx BH.
 */

use anyhow::Result;
use serde_json::Value;
use tokio::time::{sleep, Duration};
use tracing::{info, warn};
use trion_common::{
    bh_id, block_entity_id, build_vector, canonical_bh,
    freq_entropy, histogram_entropy,
    BatchPayload, FaissClient, IndexerState, VectorEntry,
};

const VM_TYPE: &str = "STELLAR";

struct StellarConfig { chain_id: u64, label: &'static str, api: &'static str }

fn config() -> StellarConfig {
    let is_testnet = std::env::var("STELLAR_NETWORK").unwrap_or_default() == "testnet";
    if is_testnet {
        StellarConfig { chain_id: 27001, label: "STELLAR_TESTNET", api: "https://horizon-testnet.stellar.org" }
    } else {
        StellarConfig { chain_id: 27000, label: "STELLAR_MAINNET", api: "https://horizon.stellar.org" }
    }
}

async fn horizon_get(client: &reqwest::Client, api: &str, path: &str) -> Result<Value> {
    let url = format!("{}{}", api, path);
    let resp = client.get(&url).send().await?;
    let json: Value = resp.json().await?;
    Ok(json)
}

fn extract_features(txs: &[Value]) -> [f64; 9] {
    let mut op_types: Vec<String> = Vec::new();
    let mut sources: Vec<String> = Vec::new();
    let mut fees: Vec<f64> = Vec::new();
    let mut memo_types: Vec<String> = Vec::new();

    for tx in txs {
        if let Some(ops) = tx.get("operations").and_then(|v| v.as_array()) {
            for op in ops {
                if let Some(t) = op.get("type").and_then(|v| v.as_str()) { op_types.push(t.to_string()); }
            }
        }
        if let Some(s) = tx.get("source_account").and_then(|v| v.as_str()) { sources.push(s.to_string()); }
        if let Some(f) = tx.get("fee_paid").and_then(|v| v.as_u64()) { fees.push(f as f64); }
        if let Some(m) = tx.get("memo_type").and_then(|v| v.as_str()) { memo_types.push(m.to_string()); }
    }
    [freq_entropy(&op_types), freq_entropy(&sources), 0.0, 0.0,
     histogram_entropy(&[txs.len() as f64], 5), 0.0, 0.0, freq_entropy(&memo_types), histogram_entropy(&fees, 10)]
}

#[tokio::main]
async fn main() -> Result<()> {
    tracing_subscriber::fmt().with_env_filter("info,trion_stellar=debug").init();
    let cfg = config();
    info!("TRION Stellar indexer starting — {} (chain_id={}, api={})", cfg.label, cfg.chain_id, cfg.api);

    let client = reqwest::Client::builder().timeout(Duration::from_secs(30)).build()?;
    let faiss_url = std::env::var("FAISS_SERVICE_URL").unwrap_or_else(|_| "http://127.0.0.1:8000".to_string());
    let faiss = FaissClient::new(&faiss_url)?;
    let mut state = IndexerState::new(&format!("/tmp/trion-stellar-{}.state", cfg.chain_id));
    let mut current_ledger = state.last_block();

    loop {
        let tip = match horizon_get(&client, cfg.api, "/ledgers?order=desc&limit=1").await {
            Ok(d) => d.get("_embedded").and_then(|e| e.get("records")).and_then(|r| r.as_array())
                .and_then(|a| a.first()).and_then(|l| l.get("sequence").and_then(|v| v.as_u64())).unwrap_or(0),
            Err(e) => { warn!("Horizon API error: {}, retrying", e); sleep(Duration::from_secs(10)).await; continue; }
        };
        if current_ledger == 0 { current_ledger = tip.saturating_sub(10); }
        if current_ledger >= tip.saturating_sub(3) { sleep(Duration::from_secs(5)).await; continue; }

        let target = current_ledger + 1;
        let path = format!("/ledgers/{}/transactions?limit=50", target);
        let txs_resp = match horizon_get(&client, cfg.api, &path).await {
            Ok(d) => d, Err(e) => { warn!("Ledger {} fetch error: {}", target, e); sleep(Duration::from_secs(5)).await; continue; }
        };
        let txs: Vec<Value> = txs_resp.get("_embedded").and_then(|e| e.get("records")).and_then(|r| r.as_array()).cloned().unwrap_or_default();
        let features = extract_features(&txs);
        let vector = build_vector(&features, &format!("{}:{}", cfg.label, target));
        let block_entity = block_entity_id(cfg.label, target);
        let (bh, _bh_id_str) = canonical_bh(&block_entity, 0u8, (txs.len() as f64) / 100.0, 0u64, 0u64, cfg.chain_id, "");

        let entry = VectorEntry {
            entity_id: block_entity.clone(),
            vector: vector.clone(),
            magnitude: txs.len() as f64,
            entropy: features[0],
            timestamp: 0.0,
            bh_id: bh_id(&format!("{}_{}", cfg.label, target)),
            block_num: target,
            chain_id: cfg.chain_id,
            chain_label: cfg.label.to_string(),
            vm_type: VM_TYPE.to_string(),
            funding_source: None,
            block_hash_hex: None,
            event_type: Some(0u8),
            sense_hex: Some(bh.clone()),
            antisense_hex: Some(bh.clone()),
        };

        let payload = BatchPayload {
            vectors: vec![entry],
            block_num: target,
            block_features: features.to_vec(),
            block_phi: features[0],
            chain_id: cfg.chain_id,
            chain_label: cfg.label.to_string(),
            vm_type: VM_TYPE.to_string(),
        };

        match faiss.add_batch(&payload).await {
            Ok(_) => info!("Ledger {} indexed — {} txs", target, txs.len()),
            Err(e) => warn!("FAISS push failed: {}", e),
        }
        state.save(target)?;
        current_ledger = target;
    }
}
