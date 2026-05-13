/*!
 * TRION NEAR Behavioral Indexer — Rust
 * =====================================
 * Polls NEAR blocks via JSON-RPC and pushes 128-dim vectors.
 *
 * NEAR behavioral dimensions (9 Shannon entropy features):
 *   f1 — Action type diversity   H(action_kind distribution)
 *   f2 — Signer entropy          H(signer_id frequency)
 *   f3 — Receiver entropy        H(receiver_id frequency)
 *   f4 — Gas burnt entropy       H(gas_burnt_per_receipt bins)
 *   f5 — Token transfer entropy  H(deposit value bins)
 *   f6 — Receipt action count    H(actions_per_receipt bins)
 *   f7 — Contract call diversity H(method_name frequency)
 *   f8 — Shard entropy           H(shard_id distribution)
 *   f9 — Tx count entropy        H(txs_per_chunk bins)
 */

use anyhow::Result;
use serde_json::Value;
use std::time::{SystemTime, UNIX_EPOCH};
use tokio::time::{sleep, Duration};
use tracing::{info, warn};
use trion_common::{
    bh_id, block_entity_id, build_vector, freq_entropy, histogram_entropy,
    BatchPayload, FaissClient, IndexerState, VectorEntry,
};

const VM_TYPE: &str = "NEAR";

struct NearConfig {
    chain_id: u64, label: &'static str, rpcs: Vec<&'static str>,
}

fn config() -> NearConfig {
    let mainnet = std::env::var("NEAR_MAINNET").as_deref() == Ok("true");
    if mainnet {
        NearConfig {
            chain_id: 1200, label: "NEAR_MAINNET",
            rpcs: vec!["https://rpc.mainnet.near.org", "https://rpc.fastnear.com"],
        }
    } else {
        NearConfig {
            chain_id: 1201, label: "NEAR_TESTNET",
            rpcs: vec!["https://rpc.testnet.fastnear.com", "https://test.rpc.fastnear.com", "https://archival-rpc.testnet.near.org"],
        }
    }
}

async fn near_rpc(client: &reqwest::Client, rpc: &str, method: &str, params: Value) -> Result<Value> {
    let body = serde_json::json!({ "jsonrpc": "2.0", "id": "trion", "method": method, "params": params });
    let resp = client.post(rpc).json(&body).send().await?;
    let json: Value = resp.json().await?;
    if let Some(e) = json.get("error") { anyhow::bail!("NEAR RPC: {}", e); }
    Ok(json["result"].clone())
}

fn extract_features(block: &Value, chunks: &[Value]) -> [f64; 9] {
    let mut action_kinds: Vec<String> = Vec::new();
    let mut signers:      Vec<String> = Vec::new();
    let mut receivers:    Vec<String> = Vec::new();
    let mut gas_burts:    Vec<f64>    = Vec::new();
    let mut deposits:     Vec<f64>    = Vec::new();
    let mut action_counts:Vec<f64>    = Vec::new();
    let mut method_names: Vec<String> = Vec::new();
    let mut shard_ids:    Vec<String> = Vec::new();
    let mut tx_counts:    Vec<f64>    = Vec::new();

    for chunk in chunks {
        if let Some(sid) = chunk["shard_id"].as_u64() {
            shard_ids.push(sid.to_string());
        }
        if let Some(txs) = chunk["transactions"].as_array() {
            tx_counts.push(txs.len() as f64);
            for tx in txs {
                let signer = tx["signer_id"].as_str().unwrap_or("").to_string();
                let receiver = tx["receiver_id"].as_str().unwrap_or("").to_string();
                signers.push(signer);
                receivers.push(receiver);
                if let Some(actions) = tx["actions"].as_array() {
                    action_counts.push(actions.len() as f64);
                    for action in actions {
                        let kind = if action.is_string() {
                            action.as_str().unwrap_or("Unknown").to_string()
                        } else {
                            action.as_object().and_then(|o| o.keys().next().cloned()).unwrap_or_default()
                        };
                        action_kinds.push(kind.clone());
                        if kind == "FunctionCall" {
                            let name = action["FunctionCall"]["method_name"].as_str().unwrap_or("").to_string();
                            method_names.push(name);
                            let deposit = action["FunctionCall"]["deposit"].as_str()
                                .and_then(|s| s.parse::<f64>().ok()).unwrap_or(0.0);
                            deposits.push(deposit);
                        }
                    }
                }
            }
        }
        if let Some(gb) = chunk["gas_used"].as_u64() { gas_burts.push(gb as f64); }
    }

    [
        freq_entropy(&action_kinds),
        freq_entropy(&signers),
        freq_entropy(&receivers),
        histogram_entropy(&gas_burts, 8),
        histogram_entropy(&deposits, 8),
        histogram_entropy(&action_counts, 8),
        freq_entropy(&method_names),
        freq_entropy(&shard_ids),
        histogram_entropy(&tx_counts, 8),
    ]
}

#[tokio::main]
async fn main() -> Result<()> {
    tracing_subscriber::fmt().with_env_filter("info").init();

    let faiss_url = std::env::var("FAISS_SERVICE_URL").unwrap_or_else(|_| "http://127.0.0.1:8000".into());
    let poll_ms   = std::env::var("POLL_MS").ok().and_then(|s| s.parse().ok()).unwrap_or(10_000u64);
    let cfg       = config();
    let faiss     = FaissClient::new(&faiss_url)?;
    let mut state = IndexerState::new(&format!("near_{}", cfg.label.to_lowercase()));
    let client    = reqwest::Client::builder().timeout(Duration::from_secs(12)).build()?;
    let mut rpc_idx = 0usize;

    info!("TRION NEAR Rust Indexer — chain={} label={} poll={}ms", cfg.chain_id, cfg.label, poll_ms);

    loop {
        if !faiss.is_healthy().await { sleep(Duration::from_secs(5)).await; continue; }

        let rpc = cfg.rpcs[rpc_idx % cfg.rpcs.len()];
        let status = match near_rpc(&client, rpc, "status", serde_json::json!([])).await {
            Ok(v)  => v,
            Err(e) => { warn!("NEAR status error: {} — rotating RPC", e); rpc_idx += 1; sleep(Duration::from_millis(poll_ms)).await; continue; }
        };
        let latest = status["sync_info"]["latest_block_height"].as_u64().unwrap_or(0);
        let last   = state.last_block();
        let from   = if last == 0 { latest.saturating_sub(1) } else { last + 1 };

        for block_num in from..=latest {
            let block = match near_rpc(&client, rpc, "block", serde_json::json!({ "block_id": block_num })).await {
                Ok(b)  => b,
                Err(e) => { warn!("[{}] block {} error: {}", cfg.label, block_num, e); continue; }
            };
            let chunks: Vec<Value> = block["chunks"].as_array().cloned().unwrap_or_default();
            let features  = extract_features(&block, &chunks);
            let phi       = features.iter().sum::<f64>() / 9.0;
            let eid       = block_entity_id(cfg.label, block_num);
            let bh        = bh_id(&eid);
            let vector    = build_vector(&features, &format!("{}:{}", cfg.label, block_num));
            let ts        = SystemTime::now().duration_since(UNIX_EPOCH).unwrap_or_default().as_secs_f64();

            let payload = BatchPayload {
                vectors: vec![VectorEntry {
                    entity_id: eid, vector, magnitude: phi, entropy: phi, timestamp: ts,
                    bh_id: bh, block_num,
                    chain_id: cfg.chain_id, chain_label: cfg.label.into(), vm_type: VM_TYPE.into(),
                    funding_source: None, block_hash_hex: None, event_type: None, sense_hex: None, antisense_hex: None,
                }],
                block_num, block_features: features.to_vec(), block_phi: phi,
                chain_id: cfg.chain_id, chain_label: cfg.label.into(), vm_type: VM_TYPE.into(),
            };

            match faiss.add_batch(&payload).await {
                Ok(added) => info!("[{}] block={} φ={:.4} added={}", cfg.label, block_num, phi, added),
                Err(e)    => warn!("[{}] FAISS failed: {}", cfg.label, e),
            }
            state.save(block_num).ok();
        }
        sleep(Duration::from_millis(poll_ms)).await;
    }
}
