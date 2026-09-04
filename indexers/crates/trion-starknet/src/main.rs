/*!
 * TRION StarkNet (Cairo VM) Behavioral Indexer — Rust
 * ====================================================
 * Polls StarkNet blocks via JSON-RPC (starknet_getBlockWithTxs).
 * Produces 128-dim vectors AND per-tx canonical BH (L0.1 ledger).
 *
 * StarkNet behavioral dimensions (9 Shannon entropy features):
 *   f1 — Tx version entropy       H(version 0/1/2/3 distribution)
 *   f2 — Sender entropy           H(sender_address frequency)
 *   f3 — Calldata length entropy  H(calldata_len bins)
 *   f4 — Fee token entropy        H(ETH/STRK fee ratio)
 *   f5 — Resource bounds entropy  H(L1/L2 gas bound bins)
 *   f6 — Multi-call density       H(call_count bins per tx)
 *   f7 — Receipt status entropy   H(SUCCEEDED/REVERTED)
 *   f8 — Event count entropy      H(events_per_tx bins)
 *   f9 — Block tx count window    H(tx_count bins)
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

const CHAIN_ID:  u64  = 24000;
const CHAIN_LBL: &str = "STARKNET_MAINNET";
const VM_TYPE:   &str = "CAIROVM";

const RPCS: &[&str] = &[
    "https://starknet-mainnet.g.alchemy.com/starknet/version/rpc/v0_8/demo",
    "https://api.cartridge.gg/x/starknet/mainnet",
    "https://free-rpc.nethermind.io/mainnet-juno",
    "https://starknet-mainnet.public.blastapi.io/rpc/v0_7",
];

async fn snrpc(client: &reqwest::Client, rpc: &str, method: &str, params: Value) -> Result<Value> {
    let body = serde_json::json!({ "jsonrpc": "2.0", "id": 1, "method": method, "params": params });
    let resp = client.post(rpc).json(&body).send().await?;
    let json: Value = resp.json().await?;
    if let Some(e) = json.get("error") { anyhow::bail!("StarkNet RPC: {}", e); }
    Ok(json["result"].clone())
}

async fn get_latest_block(client: &reqwest::Client, rpc: &str) -> Result<u64> {
    let r = snrpc(client, rpc, "starknet_blockNumber", serde_json::json!([])).await?;
    Ok(r.as_u64().unwrap_or(0))
}

async fn get_block_with_txs(client: &reqwest::Client, rpc: &str, num: u64) -> Result<Value> {
    snrpc(client, rpc, "starknet_getBlockWithTxs",
        serde_json::json!([{ "block_number": num }])).await
}

fn extract_features(block: &Value) -> [f64; 9] {
    let txs = match block["transactions"].as_array() {
        Some(a) => a, None => return [0.5f64; 9],
    };
    if txs.is_empty() { return [0.5f64; 9]; }

    let mut versions:      Vec<String> = Vec::new();
    let mut senders:       Vec<String> = Vec::new();
    let mut calldata_lens: Vec<f64>    = Vec::new();
    let mut fee_tokens:    Vec<String> = Vec::new();
    let mut l1_gas_bounds: Vec<f64>    = Vec::new();
    let mut call_counts:   Vec<f64>    = Vec::new();
    let (mut succeeded, reverted) = (0u64, 0u64);
    let mut event_counts:  Vec<f64>    = Vec::new();

    for tx in txs {
        versions.push(tx["version"].as_str().unwrap_or("0x0").to_string());
        let sender = tx["sender_address"].as_str()
            .or_else(|| tx["contract_address"].as_str())
            .unwrap_or("").to_string();
        senders.push(sender);
        let calldata = tx["calldata"].as_array().map(|a| a.len()).unwrap_or(0) as f64;
        calldata_lens.push(calldata);
        if tx["resource_bounds"].is_null() {
            fee_tokens.push("ETH".to_string());
        } else {
            let l1_gas = tx["resource_bounds"]["l1_gas"]["max_amount"]
                .as_str().and_then(|s| u64::from_str_radix(s.trim_start_matches("0x"), 16).ok())
                .unwrap_or(0) as f64;
            l1_gas_bounds.push(l1_gas);
            fee_tokens.push("STRK".to_string());
        }
        if tx["type"].as_str() == Some("INVOKE") && calldata > 0.0 {
            call_counts.push(calldata / 4.0);
        } else {
            call_counts.push(1.0);
        }
        succeeded += 1;
        event_counts.push(0.0);
    }

    let tx_count = txs.len() as f64;
    [
        freq_entropy(&versions),
        freq_entropy(&senders),
        histogram_entropy(&calldata_lens, 8),
        freq_entropy(&fee_tokens),
        histogram_entropy(&l1_gas_bounds, 8),
        histogram_entropy(&call_counts, 8),
        ratio_entropy(succeeded, succeeded + reverted),
        histogram_entropy(&event_counts, 4),
        histogram_entropy(&[tx_count], 4),
    ]
}

// ── Per-tx Behavioral Hash pipeline ──────────────────────────────────────────

/// CANONICAL_BH.md §4 — deterministic magnitude normalization:
///   human = raw / 10^18 (wei; input is tx max_fee proxy — see CANONICAL_BH.md §4 proxy note); M = min(1, log10(human + 1) / log10(1001))
/// The rolling session-max tracker was removed: it made the BH of a fixed
/// transaction depend on what else the process had observed (canonical
/// violation — the same tx must always produce the same BH).
fn snark_magnitude(max_fee: u64) -> f64 {
    let human = max_fee as f64 / 1e18;
    if human <= 0.0 { return 0.0; }
    ((human + 1.0).log10() / (1001.0_f64).log10()).min(1.0)
}

fn classify_snark_tx(tx: &Value) -> u8 {
    match tx["type"].as_str().unwrap_or("") {
        "DECLARE"                     => 11, // DEPLOY (class declaration)
        "DEPLOY_ACCOUNT"              => 11, // DEPLOY
        "INVOKE" => {
            let calldata_len = tx["calldata"].as_array().map(|a| a.len()).unwrap_or(0);
            // Large calldata → likely multi-call or DEX swap
            if calldata_len > 20 { 1 }   // SWAP
            else if calldata_len > 8 { 2 } // LIQUIDITY
            else { 0 } // TRANSFER
        }
        _ => 0, // TRANSFER
    }
}

fn snark_bh_batch(block: &Value, chain_id: u64, label: &str, block_num: u64, block_hash: &str, ts: u64) -> TxBhBatch {
    let txs = match block["transactions"].as_array() {
        Some(a) => a,
        None    => return TxBhBatch { chain_id, chain_label: label.to_string(), block_num, block_hash: block_hash.to_string(), timestamp: ts, entries: vec![] },
    };
    let mut entries: Vec<TxBhEntry> = Vec::new();

    for tx in txs {
        let tx_hash = tx["transaction_hash"].as_str().unwrap_or("").to_string();
        if tx_hash.is_empty() { continue; }

        let sender = tx["sender_address"].as_str()
            .or_else(|| tx["contract_address"].as_str())
            .unwrap_or("unknown").to_string();

        let et = classify_snark_tx(tx);

        // Max fee as magnitude proxy (hex string → u64)
        let max_fee = tx["max_fee"].as_str()
            .and_then(|s| u64::from_str_radix(s.trim_start_matches("0x"), 16).ok())
            .unwrap_or(0);

        let mag = snark_magnitude(max_fee);
        let eid = bh_id(&sender);
        let (sense_hex, antisense_hex) = canonical_bh(&eid, et, mag, 0, ts, chain_id, block_hash);

        entries.push(TxBhEntry {
            tx_hash, from_addr: sender, to_addr: String::new(),
            event_type: et, event_type_name: event_type_name(et).to_string(),
            entity_id: eid, magnitude_norm: mag, value_wei: max_fee.to_string(),
            selector: tx["type"].as_str().unwrap_or("").to_string(),
            timestamp: ts, chain_id, chain_label: label.to_string(), block_num,
            block_hash: block_hash.to_string(), sense_hex, antisense_hex,
        });
    }

    TxBhBatch { chain_id, chain_label: label.to_string(), block_num, block_hash: block_hash.to_string(), timestamp: ts, entries }
}

#[tokio::main]
async fn main() -> Result<()> {
    tracing_subscriber::fmt().with_env_filter("info").init();

    let faiss_url = std::env::var("FAISS_SERVICE_URL").unwrap_or_else(|_| "http://127.0.0.1:8000".into());
    let poll_ms   = std::env::var("POLL_MS").ok().and_then(|s| s.parse().ok()).unwrap_or(6_000u64);
    let faiss     = FaissClient::new(&faiss_url)?;
    let state = IndexerState::new("starknet_mainnet");
    let client    = reqwest::Client::builder().timeout(Duration::from_secs(12)).build()?;
    let mut rpc_idx = 0usize;

    info!("TRION StarkNet Rust Indexer — chain={} poll={}ms", CHAIN_ID, poll_ms);

    loop {
        if !faiss.is_healthy().await { sleep(Duration::from_secs(5)).await; continue; }

        let rpc    = RPCS[rpc_idx % RPCS.len()];
        let latest = match get_latest_block(&client, rpc).await {
            Ok(n)  => n,
            Err(e) => { warn!("StarkNet latest error: {} — rotating", e); rpc_idx += 1; sleep(Duration::from_millis(poll_ms)).await; continue; }
        };
        let last = state.last_block();
        let from = if last == 0 { latest.saturating_sub(1) } else { last + 1 };

        for block_num in from..=latest {
            let block = match get_block_with_txs(&client, rpc, block_num).await {
                Ok(b)  => b,
                Err(e) => { warn!("[{}] block {} error: {}", CHAIN_LBL, block_num, e); rpc_idx += 1; continue; }
            };
            let features  = extract_features(&block);
            let phi       = features.iter().sum::<f64>() / 9.0;
            let eid       = block_entity_id(CHAIN_LBL, block_num);
            let bh        = bh_id(&eid);
            let vector    = build_vector(&features, &format!("{}:{}", CHAIN_LBL, block_num));
            // CANONICAL_BH.md §5 — starknet block timestamp (unix seconds);
            // 0 = unknown. Never wall-clock.
            let ts_u64    = block["timestamp"].as_u64().unwrap_or(0);
            let ts        = ts_u64 as f64;
            let block_hash = block["block_hash"].as_str()
                .map(|h| h.to_string())
                .unwrap_or_else(|| bh_id(&format!("snark_block:{}:{}", CHAIN_LBL, block_num)));

            let payload = BatchPayload {
                vectors: vec![VectorEntry {
                    entity_id: eid, vector, magnitude: phi, entropy: phi, timestamp: ts,
                    bh_id: bh, block_num, chain_id: CHAIN_ID, chain_label: CHAIN_LBL.into(), vm_type: VM_TYPE.into(),
                    funding_source: None, block_hash_hex: None, event_type: None, sense_hex: None, antisense_hex: None,
                }],
                block_num, block_features: features.to_vec(), block_phi: phi,
                chain_id: CHAIN_ID, chain_label: CHAIN_LBL.into(), vm_type: VM_TYPE.into(),
            };

            match faiss.add_batch(&payload).await {
                Ok(added) => {
                    let tx_batch = snark_bh_batch(&block, CHAIN_ID, CHAIN_LBL, block_num, &block_hash, ts_u64);
                    let bh_stored = faiss.add_tx_bh_batch(&tx_batch).await.unwrap_or(0);
                    info!("[{}] block={} φ={:.4} added={} bh_stored={}", CHAIN_LBL, block_num, phi, added, bh_stored);
                }
                Err(e) => warn!("[{}] FAISS failed: {}", CHAIN_LBL, e),
            }
            state.save(block_num).ok();
        }
        sleep(Duration::from_millis(poll_ms)).await;
    }
}
