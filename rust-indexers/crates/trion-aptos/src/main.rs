/*!
 * TRION Aptos (Move VM) Behavioral Indexer — Rust
 * =================================================
 * Polls Aptos REST API and pushes 128-dim vectors.
 *
 * Aptos behavioral dimensions (9 Shannon entropy features):
 *   f1 — Function call entropy   H(function_id distribution)
 *   f2 — Sender entropy          H(sender_address frequency)
 *   f3 — Gas unit entropy        H(gas_unit_price bins)
 *   f4 — Resource change entropy H(resource_type changes)
 *   f5 — Event emission entropy  H(event_type diversity)
 *   f6 — Module diversity        H(module_address frequency)
 *   f7 — Success ratio entropy   H(success vs failure)
 *   f8 — Payload type entropy    H(entry_function/script/multisig)
 *   f9 — Sequence delta entropy  H(sequence_number gaps)
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

const CHAIN_ID:  u64  = 5001;
const CHAIN_LBL: &str = "APTOS_MAINNET";
const VM_TYPE:   &str = "MOVE";

const APTOS_RPCS: &[&str] = &[
    "https://fullnode.mainnet.aptoslabs.com/v1",
    "https://aptos-mainnet.public.blastapi.io/v1",
    "https://aptos-mainnet-rpc.publicnode.com/v1",
    "https://api.mainnet.aptoslabs.com/v1",
];

async fn aptos_get(client: &reqwest::Client, rpc: &str, path: &str) -> Result<Value> {
    let url = format!("{}{}", rpc.trim_end_matches('/'), path);
    let resp = client.get(&url).header("Accept", "application/json").send().await?;
    if !resp.status().is_success() { anyhow::bail!("Aptos HTTP {}", resp.status()); }
    Ok(resp.json().await?)
}

async fn get_latest_block_height(client: &reqwest::Client, rpc: &str) -> Result<u64> {
    let data = aptos_get(client, rpc, "/").await?;
    Ok(data["block_height"].as_str().and_then(|s| s.parse().ok()).unwrap_or(0))
}

async fn get_block_txs(client: &reqwest::Client, rpc: &str, height: u64) -> Result<Value> {
    aptos_get(client, rpc, &format!("/blocks/by_height/{}?with_transactions=true", height)).await
}

fn extract_features(block: &Value) -> [f64; 9] {
    let txs = match block["transactions"].as_array() {
        Some(a) => a, None => return [0.5f64; 9],
    };
    let user_txs: Vec<&Value> = txs.iter().filter(|t| t["type"].as_str() == Some("user_transaction")).collect();
    if user_txs.is_empty() { return [0.5f64; 9]; }

    let mut functions:    Vec<String> = Vec::new();
    let mut senders:      Vec<String> = Vec::new();
    let mut gas_prices:   Vec<f64>    = Vec::new();
    let mut resource_types:Vec<String>= Vec::new();
    let mut event_types:  Vec<String> = Vec::new();
    let mut modules:      Vec<String> = Vec::new();
    let (mut success, mut failed) = (0u64, 0u64);
    let mut payload_types:Vec<String> = Vec::new();
    let mut seq_nums:     Vec<f64>    = Vec::new();

    for tx in &user_txs {
        let sender = tx["sender"].as_str().unwrap_or("").to_string();
        senders.push(sender);

        let gas = tx["gas_unit_price"].as_str().and_then(|s| s.parse::<f64>().ok()).unwrap_or(0.0);
        gas_prices.push(gas);

        let seq = tx["sequence_number"].as_str().and_then(|s| s.parse::<f64>().ok()).unwrap_or(0.0);
        seq_nums.push(seq);

        let payload = &tx["payload"];
        let ptype = payload["type"].as_str().unwrap_or("unknown").to_string();
        payload_types.push(ptype.clone());

        if ptype == "entry_function_payload" {
            let func = payload["function"].as_str().unwrap_or("").to_string();
            functions.push(func.clone());
            // Module from function "0xaddr::module::func"
            if let Some(module) = func.splitn(3, "::").nth(1) {
                modules.push(module.to_string());
            }
        }

        if tx["success"].as_bool().unwrap_or(false) { success += 1; } else { failed += 1; }

        if let Some(changes) = tx["changes"].as_array() {
            for change in changes {
                let rtype = change["data"]["type"].as_str().unwrap_or("").to_string();
                if !rtype.is_empty() { resource_types.push(rtype); }
            }
        }

        if let Some(events) = tx["events"].as_array() {
            for evt in events {
                let etype = evt["type"].as_str().unwrap_or("").to_string();
                if !etype.is_empty() { event_types.push(etype); }
            }
        }
    }

    [
        freq_entropy(&functions),
        freq_entropy(&senders),
        histogram_entropy(&gas_prices, 8),
        freq_entropy(&resource_types),
        freq_entropy(&event_types),
        freq_entropy(&modules),
        ratio_entropy(success, success + failed),
        freq_entropy(&payload_types),
        histogram_entropy(&seq_nums, 8),
    ]
}

#[tokio::main]
async fn main() -> Result<()> {
    tracing_subscriber::fmt().with_env_filter("info").init();

    let faiss_url = std::env::var("FAISS_SERVICE_URL").unwrap_or_else(|_| "http://127.0.0.1:8000".into());
    let poll_ms   = std::env::var("POLL_MS").ok().and_then(|s| s.parse().ok()).unwrap_or(4_000u64);
    let faiss     = FaissClient::new(&faiss_url)?;
    let mut state = IndexerState::new("aptos_mainnet");
    let client    = reqwest::Client::builder().timeout(Duration::from_secs(12)).build()?;
    let mut rpc_idx = 0usize;

    info!("TRION Aptos Rust Indexer — chain={} poll={}ms", CHAIN_ID, poll_ms);

    loop {
        if !faiss.is_healthy().await { sleep(Duration::from_secs(5)).await; continue; }

        let rpc    = APTOS_RPCS[rpc_idx % APTOS_RPCS.len()];
        let latest = match get_latest_block_height(&client, rpc).await {
            Ok(n)  => n,
            Err(e) => { warn!("Aptos latest error: {} — rotating", e); rpc_idx += 1; sleep(Duration::from_millis(poll_ms)).await; continue; }
        };
        let last = state.last_block();
        let from = if last == 0 { latest.saturating_sub(1) } else { last + 1 };

        for height in from..=latest {
            let block = match get_block_txs(&client, rpc, height).await {
                Ok(b)  => b,
                Err(e) => { warn!("[{}] block {} error: {}", CHAIN_LBL, height, e); rpc_idx += 1; continue; }
            };
            let features = extract_features(&block);
            let phi      = features.iter().sum::<f64>() / 9.0;
            let eid      = block_entity_id(CHAIN_LBL, height);
            let bh       = bh_id(&eid);
            let vector   = build_vector(&features, &format!("{}:{}", CHAIN_LBL, height));
            let ts       = SystemTime::now().duration_since(UNIX_EPOCH).unwrap_or_default().as_secs_f64();

            let payload = BatchPayload {
                vectors: vec![VectorEntry {
                    entity_id: eid, vector, magnitude: phi, entropy: phi, timestamp: ts,
                    bh_id: bh, block_num: height, chain_id: CHAIN_ID, chain_label: CHAIN_LBL.into(), vm_type: VM_TYPE.into(),
                    funding_source: None, block_hash_hex: None, event_type: None, sense_hex: None, antisense_hex: None,
                }],
                block_num: height, block_features: features.to_vec(), block_phi: phi,
                chain_id: CHAIN_ID, chain_label: CHAIN_LBL.into(), vm_type: VM_TYPE.into(),
            };

            match faiss.add_batch(&payload).await {
                Ok(added) => info!("[{}] block={} φ={:.4} added={}", CHAIN_LBL, height, phi, added),
                Err(e)    => warn!("[{}] FAISS failed: {}", CHAIN_LBL, e),
            }
            state.save(height).ok();
        }
        sleep(Duration::from_millis(poll_ms)).await;
    }
}
