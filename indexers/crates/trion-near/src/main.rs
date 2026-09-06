/*!
 * TRION NEAR Behavioral Indexer — Rust
 * =====================================
 * Polls NEAR blocks via JSON-RPC, pushes 128-dim vectors AND per-tx canonical BH.
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
use tokio::time::{sleep, Duration};
use tracing::{info, warn};
use trion_common::{
    bh_id, block_entity_id, build_vector, canonical_bh, event_type_name,
    freq_entropy, histogram_entropy,
    BatchPayload, FaissClient, IndexerState, TxBhBatch, TxBhEntry, VectorEntry,
};

const VM_TYPE: &str = "NEAR";

struct NearConfig {
    chain_id: u64, label: &'static str, rpcs: Vec<&'static str>,
}

fn config() -> NearConfig {
    NearConfig {
        chain_id: 23000, label: "NEAR_MAINNET",
        rpcs: vec![
            "https://rpc.mainnet.near.org",
            "https://rpc.fastnear.com",
            "https://near.lava.build",
        ],
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
                signers.push(tx["signer_id"].as_str().unwrap_or("").to_string());
                receivers.push(tx["receiver_id"].as_str().unwrap_or("").to_string());
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
    let _ = block;
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

// ── Per-tx Behavioral Hash pipeline ──────────────────────────────────────────

/// CANONICAL_BH.md §4 — deterministic magnitude normalization:
///   human = raw / 10^24 (NEAR yocto); M = min(1, log10(human + 1) / log10(1001))
/// The rolling session-max tracker was removed: it made the BH of a fixed
/// transaction depend on what else the process had observed (canonical
/// violation — the same tx must always produce the same BH).
fn near_magnitude(yocto: u64) -> f64 {
    let human = yocto as f64 / 1e24;
    if human <= 0.0 { return 0.0; }
    ((human + 1.0).log10() / (1001.0_f64).log10()).min(1.0)
}

fn classify_near_event(actions: &[Value]) -> u8 {
    for action in actions {
        let kind = if action.is_string() {
            action.as_str().unwrap_or("").to_string()
        } else {
            action.as_object().and_then(|o| o.keys().next().cloned()).unwrap_or_default()
        };
        match kind.as_str() {
            "Transfer"       => return 0,   // TRANSFER
            "DeployContract" => return 11,  // DEPLOY
            // Canonical event types per whitepaper L0.1 §2:
            //   3=STAKE, 4=UNSTAKE, 7=BORROW, 8=REPAY, 9=LIQUIDATE
            "Stake"          => return 3,   // STAKE
            "FunctionCall"   => {
                let m = action["FunctionCall"]["method_name"]
                    .as_str().unwrap_or("").to_lowercase();
                if m.contains("swap") || m.contains("exchange")           { return 1;  } // SWAP
                if m.contains("add_liquidity") || m.contains("add_pool")  { return 2;  } // LIQUIDITY
                if m.contains("stake") && !m.contains("unstake")          { return 3;  } // STAKE
                if m.contains("unstake") || m.contains("withdraw")        { return 4;  } // UNSTAKE
                if m.contains("borrow")                                    { return 7;  } // BORROW
                if m.contains("repay") || m.contains("return_loan")       { return 8;  } // REPAY
                if m.contains("vote") || m.contains("proposal") || m.contains("governance") { return 6; } // GOVERNANCE
                if m.contains("oracle") || m.contains("price_update")     { return 15; } // ORACLE_UPDATE
                if m.contains("flash")                                     { return 17; } // FLASH_LOAN
                if m.contains("mint")                                      { return 13; } // MINT
                if m.contains("burn")                                      { return 14; } // BURN
                if m.contains("claim")                                     { return 19; } // CLAIM
                if m.contains("airdrop")                                   { return 18; } // AIRDROP
                return 0; // TRANSFER
            }
            _ => {}
        }
    }
    0
}

// NEAR block RPC returns chunk HEADERS only. Transactions require a separate `chunk` RPC call.
async fn near_bh_batch(client: &reqwest::Client, rpc: &str, chunk_headers: &[Value], chain_id: u64, label: &str, block_num: u64, block_hash: &str, ts: u64) -> TxBhBatch {
    let mut entries: Vec<TxBhEntry> = Vec::new();
    for chunk_hdr in chunk_headers {
        let chunk_hash = match chunk_hdr["chunk_hash"].as_str() {
            Some(h) => h,
            None    => continue,
        };
        // Fetch full chunk to get transactions list
        let chunk_data = match near_rpc(client, rpc, "chunk", serde_json::json!({ "chunk_id": chunk_hash })).await {
            Ok(v)  => v,
            Err(_) => continue,
        };
        let txs = match chunk_data["transactions"].as_array() {
            Some(t) => t,
            None    => continue,
        };
        for tx in txs {
            let tx_hash  = tx["hash"].as_str().unwrap_or("").to_string();
            if tx_hash.is_empty() { continue; }
            let sender   = tx["signer_id"].as_str().unwrap_or("unknown");
            let receiver = tx["receiver_id"].as_str().unwrap_or("").to_string();
            let actions: Vec<Value> = tx["actions"].as_array().cloned().unwrap_or_default();
            let et = classify_near_event(&actions);
            let yocto = actions.iter()
                .flat_map(|a| [
                    a["FunctionCall"]["deposit"].as_str().and_then(|s| s.parse::<u64>().ok()),
                    a["Transfer"]["deposit"].as_str().and_then(|s| s.parse::<u64>().ok()),
                ])
                .flatten()
                .max()
                .unwrap_or(0);
            let mag = near_magnitude(yocto);
            let eid = bh_id(sender);
            let (sense_hex, antisense_hex) = canonical_bh(&eid, et, mag, 0, ts, chain_id, block_hash);
            entries.push(TxBhEntry {
                tx_hash, from_addr: sender.to_string(), to_addr: receiver,
                event_type: et, event_type_name: event_type_name(et).to_string(),
                entity_id: eid, magnitude_norm: mag, value_wei: yocto.to_string(),
                selector: String::new(), timestamp: ts, chain_id,
                chain_label: label.to_string(), block_num,
                block_hash: block_hash.to_string(), sense_hex, antisense_hex,
            });
        }
    }
    TxBhBatch { chain_id, chain_label: label.to_string(), block_num, block_hash: block_hash.to_string(), timestamp: ts, entries }
}

#[tokio::main]
async fn main() -> Result<()> {
    tracing_subscriber::fmt().with_env_filter("info").init();

    let faiss_url = std::env::var("FAISS_SERVICE_URL").unwrap_or_else(|_| "http://127.0.0.1:8000".into());
    let poll_ms   = std::env::var("POLL_MS").ok().and_then(|s| s.parse().ok()).unwrap_or(10_000u64);
    let cfg       = config();
    let faiss     = FaissClient::new(&faiss_url)?;
    let state = IndexerState::new(&format!("near_{}", cfg.label.to_lowercase()));
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
            // CANONICAL_BH.md §5 — NEAR header.timestamp is nanoseconds;
            // 0 = unknown. Never wall-clock.
            let ts_u64    = block["header"]["timestamp"].as_u64().unwrap_or(0) / 1_000_000_000;
            let ts        = ts_u64 as f64;
            // SEC-05 / SWEEP-B D3 — pass the REAL NEAR block hash VERBATIM
            // (`header.hash` from the block RPC — the same field the Python
            // streamer's NEAR fetcher reads). Genuinely-missing → warn +
            // honest "0x0" (32 zero bytes), never the old synthetic
            // bh_id("near_block:…") substitution.
            let block_hash_hex = match block["header"]["hash"].as_str() {
                Some(h) if !h.is_empty() => h.to_string(),
                _ => {
                    warn!("[{}] block {}: no block hash from NEAR RPC — zero block hash", cfg.label, block_num);
                    "0x0".to_string()
                }
            };

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
                Ok(added) => {
                    let tx_batch = near_bh_batch(&client, rpc, &chunks, cfg.chain_id, cfg.label, block_num, &block_hash_hex, ts_u64).await;
                    let bh_stored = faiss.add_tx_bh_batch(&tx_batch).await.unwrap_or(0);
                    info!("[{}] block={} φ={:.4} added={} bh_stored={}", cfg.label, block_num, phi, added, bh_stored);
                }
                Err(e) => warn!("[{}] FAISS failed: {}", cfg.label, e),
            }
            state.save(block_num).ok();
        }
        sleep(Duration::from_millis(poll_ms)).await;
    }
}
