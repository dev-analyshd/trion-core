/*!
 * TRION Solana (SVM) Behavioral Indexer — Rust
 * =============================================
 * Polls Solana slots via JSON-RPC (getBlock) and pushes 128-dim vectors.
 *
 * SVM behavioral dimensions (9 Shannon entropy features):
 *   f1 — Instruction diversity    H(program_id distribution)
 *   f2 — Account access entropy   H(account_key_frequency)
 *   f3 — Compute unit entropy     H(CU bins)
 *   f4 — Lamport transfer entropy H(lamport_value bins)
 *   f5 — Signer diversity         H(num_signers distribution)
 *   f6 — Program invocation depth H(CPI count per tx bins)
 *   f7 — Fee payer diversity      H(fee_payer frequency)
 *   f8 — Slot timing entropy      H(slot gap bins)
 *   f9 — Write/read ratio entropy H(writable_fraction bins)
 */

use anyhow::Result;
use serde_json::Value;
use std::time::{SystemTime, UNIX_EPOCH};
use tokio::time::{sleep, Duration};
use tracing::{error, info, warn};
use trion_common::{
    bh_id, block_entity_id, build_vector, freq_entropy, histogram_entropy,
    BatchPayload, FaissClient, IndexerState, VectorEntry, with_retry,
};

const CHAIN_ID:  u64  = 103;
const VM_TYPE:   &str = "SVM";

fn chain_label() -> String {
    std::env::var("SOLANA_LABEL").unwrap_or_else(|_| "SOLANA_DEVNET".into())
}

fn rpc_url() -> String {
    std::env::var("SOLANA_RPC_URL").unwrap_or_else(|_| "https://api.devnet.solana.com".into())
}

async fn sol_rpc(client: &reqwest::Client, method: &str, params: Value) -> Result<Value> {
    let url = rpc_url();
    let body = serde_json::json!({ "jsonrpc": "2.0", "id": 1, "method": method, "params": params });
    let resp = client.post(&url).json(&body).send().await?;
    let json: Value = resp.json().await?;
    if let Some(e) = json.get("error") {
        anyhow::bail!("Solana RPC: {}", e);
    }
    Ok(json["result"].clone())
}

fn extract_features(block: &Value, prev_slot: u64, cur_slot: u64) -> [f64; 9] {
    let txs = match block["transactions"].as_array() {
        Some(a) => a, None => return [0.5f64; 9],
    };
    if txs.is_empty() { return [0.5f64; 9]; }

    let mut program_ids:      Vec<String> = Vec::new();
    let mut account_keys:     Vec<String> = Vec::new();
    let mut compute_units:    Vec<f64>    = Vec::new();
    let mut lamports:         Vec<f64>    = Vec::new();
    let mut signer_counts:    Vec<f64>    = Vec::new();
    let mut cpi_depths:       Vec<f64>    = Vec::new();
    let mut fee_payers:       Vec<String> = Vec::new();
    let mut writable_fracs:   Vec<f64>    = Vec::new();

    for tx in txs {
        let msg = &tx["transaction"]["message"];
        let meta = &tx["meta"];

        // Account keys
        if let Some(keys) = msg["accountKeys"].as_array() {
            for k in keys {
                account_keys.push(k.as_str().unwrap_or("").to_string());
            }
            if let Some(fee_payer) = keys.first() {
                fee_payers.push(fee_payer.as_str().unwrap_or("").to_string());
            }
            // Writable: header says how many are writable
            let num_required_sigs = msg["header"]["numRequiredSignatures"].as_u64().unwrap_or(0);
            signer_counts.push(num_required_sigs as f64);
            let num_writable = msg["header"]["numReadonlySignedAccounts"].as_u64().unwrap_or(0);
            let total = keys.len().max(1) as f64;
            writable_fracs.push((total - num_writable as f64) / total);
        }

        // Instructions → program diversity
        if let Some(insts) = msg["instructions"].as_array() {
            cpi_depths.push(insts.len() as f64);
            for inst in insts {
                if let Some(pi) = inst["programIdIndex"].as_u64() {
                    program_ids.push(format!("prog_{}", pi));
                }
            }
        }

        // Compute units from meta
        if let Some(cu) = meta["computeUnitsConsumed"].as_u64() {
            compute_units.push(cu as f64);
        }

        // Pre/post balance diff as lamport proxy
        if let (Some(pre), Some(post)) = (meta["preBalances"].as_array(), meta["postBalances"].as_array()) {
            let diff: f64 = pre.iter().zip(post.iter())
                .map(|(a, b)| (b.as_f64().unwrap_or(0.0) - a.as_f64().unwrap_or(0.0)).abs())
                .sum();
            lamports.push(diff);
        }
    }

    let slot_gap = (cur_slot.saturating_sub(prev_slot)) as f64;

    let f1 = freq_entropy(&program_ids);
    let f2 = freq_entropy(&account_keys);
    let f3 = histogram_entropy(&compute_units, 8);
    let f4 = histogram_entropy(&lamports, 8);
    let f5 = histogram_entropy(&signer_counts, 4);
    let f6 = histogram_entropy(&cpi_depths, 8);
    let f7 = freq_entropy(&fee_payers);
    let f8 = histogram_entropy(&[slot_gap], 4);
    let f9 = histogram_entropy(&writable_fracs, 8);

    [f1, f2, f3, f4, f5, f6, f7, f8, f9]
}

#[tokio::main]
async fn main() -> Result<()> {
    tracing_subscriber::fmt().with_env_filter("info").init();

    let faiss_url = std::env::var("FAISS_SERVICE_URL").unwrap_or_else(|_| "http://127.0.0.1:8000".into());
    let poll_ms   = std::env::var("POLL_SLEEP_MS").ok().and_then(|s| s.parse().ok()).unwrap_or(1_500u64);
    let label     = chain_label();

    let faiss  = FaissClient::new(&faiss_url)?;
    let mut state = IndexerState::new(&format!("svm_{}", label.to_lowercase()));
    let client = reqwest::Client::builder().timeout(Duration::from_secs(15)).build()?;

    info!("TRION SVM Rust Indexer — chain={} label={} poll={}ms faiss={}", CHAIN_ID, label, poll_ms, faiss_url);

    let mut prev_slot = 0u64;

    loop {
        if !faiss.is_healthy().await {
            warn!("FAISS not reachable — waiting 5s");
            sleep(Duration::from_secs(5)).await;
            continue;
        }

        let slot = match sol_rpc(&client, "getSlot", serde_json::json!([])).await {
            Ok(v)  => v.as_u64().unwrap_or(0),
            Err(e) => { warn!("getSlot error: {}", e); sleep(Duration::from_millis(poll_ms)).await; continue; }
        };

        let last = state.last_block();
        let from = if last == 0 { slot.saturating_sub(1) } else { last + 1 };

        for cur_slot in from..=slot {
            let block = match sol_rpc(&client, "getBlock",
                serde_json::json!([cur_slot, { "encoding": "json", "maxSupportedTransactionVersion": 0, "transactionDetails": "full", "rewards": false }])
            ).await {
                Ok(b)  => b,
                Err(e) => { warn!("[{}] slot {} fetch error: {}", label, cur_slot, e); continue; }
            };
            if block.is_null() { continue; }

            let features  = extract_features(&block, prev_slot, cur_slot);
            let phi       = features.iter().sum::<f64>() / 9.0;
            let eid       = block_entity_id(&label, cur_slot);
            let bh        = bh_id(&eid);
            let vector    = build_vector(&features, &format!("{}:{}", label, cur_slot));
            let ts        = SystemTime::now().duration_since(UNIX_EPOCH).unwrap_or_default().as_secs_f64();

            let payload = BatchPayload {
                vectors: vec![VectorEntry {
                    entity_id: eid, vector, magnitude: phi, entropy: phi, timestamp: ts,
                    bh_id: bh, block_num: cur_slot,
                    chain_id: CHAIN_ID, chain_label: label.clone(), vm_type: VM_TYPE.into(),
                    funding_source: None, block_hash_hex: None, event_type: None, sense_hex: None, antisense_hex: None,
                }],
                block_num: cur_slot, block_features: features.to_vec(), block_phi: phi,
                chain_id: CHAIN_ID, chain_label: label.clone(), vm_type: VM_TYPE.into(),
            };

            match faiss.add_batch(&payload).await {
                Ok(added) => info!("[{}] slot={} φ={:.4} added={}", label, cur_slot, phi, added),
                Err(e)    => warn!("[{}] FAISS failed slot {}: {}", label, cur_slot, e),
            }
            state.save(cur_slot).ok();
            prev_slot = cur_slot;
        }
        sleep(Duration::from_millis(poll_ms)).await;
    }
}
