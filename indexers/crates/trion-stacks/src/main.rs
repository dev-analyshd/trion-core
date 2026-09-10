/*!
 * TRION Stacks (Clarity VM) Behavioral Indexer — Rust
 * Polls Stacks blocks via the Hiro API, pushes 128-dim vectors AND per-tx canonical BH.
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

const VM_TYPE: &str = "STACKS";

struct StacksConfig { chain_id: u64, label: &'static str, api: &'static str }

fn config() -> StacksConfig {
    let is_testnet = std::env::var("STACKS_NETWORK").unwrap_or_default() == "testnet";
    if is_testnet {
        StacksConfig { chain_id: 26001, label: "STACKS_TESTNET", api: "https://api.testnet.hiro.so" }
    } else {
        StacksConfig { chain_id: 26000, label: "STACKS_MAINNET", api: "https://api.hiro.so" }
    }
}

async fn hiro_get(client: &reqwest::Client, api: &str, path: &str) -> Result<Value> {
    let url = format!("{}{}", api, path);
    let resp = client.get(&url).send().await?;
    let json: Value = resp.json().await?;
    Ok(json)
}

fn extract_features(txs: &[Value]) -> [f64; 9] {
    let mut tx_types: Vec<String> = Vec::new();
    let mut senders: Vec<String> = Vec::new();
    let mut fees: Vec<f64> = Vec::new();
    let mut amounts: Vec<f64> = Vec::new();

    for tx in txs {
        if let Some(t) = tx.get("tx_type").and_then(|v| v.as_str()) { tx_types.push(t.to_string()); }
        if let Some(s) = tx.get("sender_address").and_then(|v| v.as_str()) { senders.push(s.to_string()); }
        if let Some(f) = tx.get("fee_rate").and_then(|v| v.as_u64()) { fees.push(f as f64); }
        if let Some(t) = tx.get("tx_type") {
            if t == "token_transfer" {
                if let Some(a) = tx.get("token_transfer_amount").and_then(|v| v.as_u64()) { amounts.push(a as f64); }
            }
        }
    }
    [freq_entropy(&tx_types), freq_entropy(&senders), 0.0, histogram_entropy(&fees, 10),
     histogram_entropy(&[txs.len() as f64], 5), histogram_entropy(&amounts, 10), 0.0, 0.0, 0.0]
}

#[tokio::main]
async fn main() -> Result<()> {
    tracing_subscriber::fmt().with_env_filter("info,trion_stacks=debug").init();
    let cfg = config();
    info!("TRION Stacks indexer starting — {} (chain_id={}, api={})", cfg.label, cfg.chain_id, cfg.api);

    let client = reqwest::Client::builder().timeout(Duration::from_secs(30)).build()?;
    let faiss_url = std::env::var("FAISS_SERVICE_URL").unwrap_or_else(|_| "http://127.0.0.1:8000".to_string());
    let faiss = FaissClient::new(&faiss_url)?;
    let mut state = IndexerState::new(&format!("/tmp/trion-stacks-{}.state", cfg.chain_id));
    let mut current_block = state.last_block();

    loop {
        let tip = match hiro_get(&client, cfg.api, "/v2/info").await {
            Ok(info) => info.get("stacks_tip_height").and_then(|v| v.as_u64()).unwrap_or(0),
            Err(e) => { warn!("Hiro API error: {}, retrying", e); sleep(Duration::from_secs(10)).await; continue; }
        };
        if current_block == 0 { current_block = tip.saturating_sub(13); }
        if current_block >= tip.saturating_sub(3) { sleep(Duration::from_secs(15)).await; continue; }

        let target = current_block + 1;
        let path = format!("/extended/v1/block?limit=1");
        let block = match hiro_get(&client, cfg.api, &path).await {
            Ok(b) => b, Err(e) => { warn!("Block fetch error: {}", e); sleep(Duration::from_secs(5)).await; continue; }
        };
        let _block_hash = block.get("results").and_then(|r| r.get(0)).and_then(|b| b.get("hash")).and_then(|v| v.as_str()).unwrap_or("").to_string();

        let txs_path = format!("/extended/v1/tx?block_height={}&limit=50", target);
        let txs_resp = match hiro_get(&client, cfg.api, &txs_path).await {
            Ok(t) => t, Err(_) => Value::Null,
        };
        let txs: Vec<Value> = txs_resp.get("results").and_then(|v| v.as_array()).cloned().unwrap_or_default();

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
            Ok(_) => info!("Block {} indexed — {} txs", target, txs.len()),
            Err(e) => warn!("FAISS push failed: {}", e),
        }
        state.save(target)?;
        current_block = target;
    }
}
