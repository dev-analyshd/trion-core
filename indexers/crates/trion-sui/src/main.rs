/*!
 * TRION Sui Behavioral Indexer
 * ============================
 * Polls Sui checkpoints via JSON-RPC and pushes 128-dim vectors
 * AND per-tx canonical BH (L0.1 ledger).
 *
 * FIX: Replaced fake feature extraction (truncated tx digests) with real
 * sui_getTransactionBlock calls that fetch actual sender, MoveCall, gas,
 * events, and mutated object data per transaction.
 *
 * Sui behavioral dimensions (9 Shannon entropy features):
 *   f1 — Command type entropy     H(MoveCall/Transfer/Publish/Upgrade/Split/Merge)
 *   f2 — Sender entropy           H(sender_address frequency)
 *   f3 — Gas cost entropy         H(computationCost bins)
 *   f4 — Object mutation entropy  H(mutated_objects_count bins)
 *   f5 — Move call diversity      H(package::module::function)
 *   f6 — Transfer entropy         H(transfer_count bins)
 *   f7 — Shared object entropy    H(shared vs owned ratio)
 *   f8 — Event count entropy      H(events_per_tx bins)
 *   f9 — Epoch entropy            H(epoch_id distribution)
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

const CHAIN_ID:  u64 = 20100;
const CHAIN_LBL: &str = "SUI_MAINNET";
const VM_TYPE:   &str = "SUI";

const RPCS: &[&str] = &[
    "https://fullnode.mainnet.sui.io:443",
    "https://sui-mainnet.public.blastapi.io",
    "https://sui-mainnet-rpc.allthatnode.com",
];

/// Cap per-checkpoint tx fetches to avoid RPC amplification.
/// For checkpoints with many txs, we sample the first 25.
const MAX_TX_FETCH: usize = 25;

async fn sui_rpc(client: &reqwest::Client, rpc: &str, method: &str, params: Value) -> Result<Value> {
    let body = serde_json::json!({ "jsonrpc": "2.0", "id": 1, "method": method, "params": params });
    let resp = client.post(rpc).json(&body).send().await?;
    let json: Value = resp.json().await?;
    if let Some(e) = json.get("error") { anyhow::bail!("Sui RPC error: {}", e); }
    Ok(json["result"].clone())
}

async fn get_latest_checkpoint(client: &reqwest::Client, rpc: &str) -> Result<u64> {
    let r = sui_rpc(client, rpc, "sui_getLatestCheckpointSequenceNumber", serde_json::json!([])).await?;
    Ok(r.as_str().unwrap_or("0").parse::<u64>().unwrap_or(0))
}

async fn get_checkpoint(client: &reqwest::Client, rpc: &str, seq: u64) -> Result<Value> {
    sui_rpc(client, rpc, "sui_getCheckpoint", serde_json::json!([seq.to_string()])).await
}

/// Fetch full transaction data for a single tx digest.
async fn get_tx_block(client: &reqwest::Client, rpc: &str, digest: &str) -> Result<Value> {
    sui_rpc(client, rpc, "sui_getTransactionBlock", serde_json::json!([
        digest,
        { "showInput": true, "showEffects": true, "showEvents": true }
    ])).await
}

/// Extract real per-tx features by fetching each transaction block.
async fn extract_features(
    cp: &Value,
    client: &reqwest::Client,
    rpc: &str,
) -> [f64; 9] {
    let txs = match cp["transactions"].as_array() {
        Some(a) => a, None => return [0.5f64; 9],
    };
    if txs.is_empty() { return [0.5f64; 9]; }

    let tx_digests: Vec<String> = txs.iter()
        .filter_map(|t| t.as_str().map(|s| s.to_string()))
        .take(MAX_TX_FETCH)
        .collect();

    let mut command_types: Vec<String> = Vec::new();
    let mut senders: Vec<String> = Vec::new();
    let mut gas_costs: Vec<f64> = Vec::new();
    let mut mutated_counts: Vec<f64> = Vec::new();
    let mut move_calls: Vec<String> = Vec::new();
    let mut transfer_counts: Vec<f64> = Vec::new();
    let mut shared_ratios: Vec<f64> = Vec::new();
    let mut event_counts: Vec<f64> = Vec::new();
    let mut epochs: Vec<String> = Vec::new();

    if let Some(ep) = cp["epoch"].as_str() {
        epochs.push(ep.to_string());
    } else if let Some(ep) = cp["epoch"].as_u64() {
        epochs.push(ep.to_string());
    }

    for digest in &tx_digests {
        match get_tx_block(client, rpc, digest).await {
            Ok(tx_block) => {
                // Real sender
                let sender = tx_block["transaction"]["data"]["sender"]
                    .as_str().unwrap_or("").to_string();
                senders.push(sender);

                // Real gas cost
                let gas = tx_block["effects"]["gasUsed"]["computationCost"]
                    .as_str()
                    .and_then(|s| s.parse::<f64>().ok())
                    .or_else(|| tx_block["effects"]["gasUsed"]["computationCost"]
                        .as_u64().map(|v| v as f64))
                    .unwrap_or(0.0);
                gas_costs.push(gas);

                // Command types from transaction.data.transactions
                if let Some(cmds) = tx_block["transaction"]["data"]["transactions"].as_array() {
                    for cmd in cmds {
                        let cmd_type = if cmd.get("MoveCall").is_some() {
                            "MoveCall".to_string()
                        } else if cmd.get("TransferObjects").is_some() {
                            "TransferObjects".to_string()
                        } else if cmd.get("Publish").is_some() {
                            "Publish".to_string()
                        } else if cmd.get("Upgrade").is_some() {
                            "Upgrade".to_string()
                        } else if cmd.get("SplitCoins").is_some() {
                            "SplitCoins".to_string()
                        } else if cmd.get("MergeCoins").is_some() {
                            "MergeCoins".to_string()
                        } else {
                            "Other".to_string()
                        };
                        command_types.push(cmd_type);

                        if let Some(mc) = cmd.get("MoveCall") {
                            let pkg = mc["package"].as_str().unwrap_or("");
                            let mod_ = mc["module"].as_str().unwrap_or("");
                            let func = mc["function"].as_str().unwrap_or("");
                            move_calls.push(format!("{}::{}::{}", pkg, mod_, func));
                        }
                    }
                }

                // Mutated objects
                let mutated = tx_block["effects"]["mutated"].as_array()
                    .map(|a| a.len() as f64)
                    .unwrap_or(0.0);
                mutated_counts.push(mutated);

                // Transfer count
                let transfers = tx_block["transaction"]["data"]["transactions"].as_array()
                    .map(|cmds| cmds.iter()
                        .filter(|c| c.get("TransferObjects").is_some()).count() as f64)
                    .unwrap_or(0.0);
                transfer_counts.push(transfers);

                // Shared object ratio
                let shared = tx_block["effects"]["sharedObjects"].as_array()
                    .map(|a| a.len() as f64)
                    .unwrap_or(0.0);
                shared_ratios.push(shared / mutated.max(1.0));

                // Event count
                let events = tx_block["events"].as_array()
                    .map(|a| a.len() as f64)
                    .unwrap_or(0.0);
                event_counts.push(events);
            }
            Err(e) => {
                warn!("[{}] tx fetch failed for {}: {}", CHAIN_LBL, digest, e);
                let per_tx = cp["epochRollingGasCostSummary"]["computationCost"]
                    .as_str().and_then(|s| s.parse::<f64>().ok()).unwrap_or(0.0)
                    / txs.len().max(1) as f64;
                gas_costs.push(per_tx);
                senders.push(format!("sui:{}", &digest[..digest.len().min(16)]));
            }
        }
    }

    [
        freq_entropy(&command_types),
        freq_entropy(&senders),
        histogram_entropy(&gas_costs, 8),
        histogram_entropy(&mutated_counts, 8),
        freq_entropy(&move_calls),
        histogram_entropy(&transfer_counts, 8),
        histogram_entropy(&shared_ratios, 4),
        histogram_entropy(&event_counts, 8),
        freq_entropy(&epochs),
    ]
}

// ── Per-tx Behavioral Hash pipeline ──────────────────────────────────────────

fn sui_magnitude(mist: u64) -> f64 {
    let human = mist as f64 / 1e9;
    if human <= 0.0 { return 0.0; }
    ((human + 1.0).log10() / (1001.0_f64).log10()).min(1.0)
}

/// Classify Sui tx based on real MoveCall data.
fn classify_sui_tx(tx_block: &Value) -> u8 {
    if let Some(cmds) = tx_block["transaction"]["data"]["transactions"].as_array() {
        for cmd in cmds {
            if let Some(mc) = cmd.get("MoveCall") {
                let func = mc["function"].as_str().unwrap_or("");
                let mod_ = mc["module"].as_str().unwrap_or("");
                if func.contains("swap") || mod_.contains("pool") || mod_.contains("dex") || mod_.contains("amm") {
                    return 1; // SWAP
                }
                if func.contains("stake") || func.contains("delegate") { return 3; }
                if func.contains("unstake") || func.contains("withdraw_stake") { return 4; }
                if func.contains("borrow") { return 7; }
                if func.contains("repay") { return 8; }
                if func.contains("add_liquidity") || func.contains("deposit") { return 2; }
                if func.contains("remove_liquidity") || func.contains("withdraw") { return 2; }
                return 1;
            }
            if cmd.get("Publish").is_some() { return 11; }
        }
    }
    0
}

/// Build per-tx BH batch with real tx data.
async fn sui_bh_batch(
    cp: &Value, seq: u64, chain_id: u64, label: &str,
    cp_hash: &str, ts: u64, client: &reqwest::Client, rpc: &str,
) -> TxBhBatch {
    let txs = match cp["transactions"].as_array() {
        Some(a) => a,
        None => return TxBhBatch {
            chain_id, chain_label: label.to_string(), block_num: seq,
            block_hash: cp_hash.to_string(), timestamp: ts, entries: vec![],
        },
    };

    let total_gas: u64 = cp["epochRollingGasCostSummary"]["computationCost"]
        .as_str().and_then(|s| s.parse().ok()).unwrap_or(0);
    let per_tx_gas_fallback = if txs.is_empty() { 0 } else { total_gas / txs.len().max(1) as u64 };

    let mut entries: Vec<TxBhEntry> = Vec::new();

    for tx in txs {
        let digest = tx.as_str().unwrap_or("").to_string();
        if digest.is_empty() { continue; }

        let (et, mag, sender, gas_str) = match get_tx_block(client, rpc, &digest).await {
            Ok(tx_block) => {
                let et = classify_sui_tx(&tx_block);
                let gas = tx_block["effects"]["gasUsed"]["computationCost"]
                    .as_str().and_then(|s| s.parse::<u64>().ok())
                    .or_else(|| tx_block["effects"]["gasUsed"]["computationCost"].as_u64())
                    .unwrap_or(per_tx_gas_fallback);
                let mag = sui_magnitude(gas);
                let sender = tx_block["transaction"]["data"]["sender"]
                    .as_str().unwrap_or("").to_string();
                (et, mag, sender, gas.to_string())
            }
            Err(e) => {
                warn!("[{}] tx fetch failed for BH {}: {}", CHAIN_LBL, digest, e);
                let et = if per_tx_gas_fallback > 5_000_000 { 1 } else { 0 };
                (et, sui_magnitude(per_tx_gas_fallback),
                 format!("sui:{}", digest), per_tx_gas_fallback.to_string())
            }
        };

        let eid = bh_id(&sender);
        let (sense_hex, antisense_hex) = canonical_bh(&eid, et, mag, 0, ts, chain_id, cp_hash);

        entries.push(TxBhEntry {
            tx_hash: digest.clone(), from_addr: sender,
            to_addr: String::new(),
            event_type: et, event_type_name: event_type_name(et).to_string(),
            entity_id: eid, magnitude_norm: mag, value_wei: gas_str,
            selector: String::new(), timestamp: ts, chain_id,
            chain_label: label.to_string(), block_num: seq,
            block_hash: cp_hash.to_string(), sense_hex, antisense_hex,
        });
    }

    TxBhBatch {
        chain_id, chain_label: label.to_string(), block_num: seq,
        block_hash: cp_hash.to_string(), timestamp: ts, entries,
    }
}

#[tokio::main]
async fn main() -> Result<()> {
    tracing_subscriber::fmt().with_env_filter("info").init();

    let faiss_url = std::env::var("FAISS_SERVICE_URL")
        .unwrap_or_else(|_| "http://127.0.0.1:8000".into());
    let poll_ms = std::env::var("POLL_MS").ok()
        .and_then(|s| s.parse().ok()).unwrap_or(5_000u64);

    let faiss = FaissClient::new(&faiss_url)?;
    let state = IndexerState::new("sui");
    let mut rpc_idx = 0usize;
    let client = reqwest::Client::builder()
        .timeout(Duration::from_secs(12)).build()?;

    info!("TRION Sui Rust Indexer — chain={} poll={}ms faiss={}", CHAIN_ID, poll_ms, faiss_url);

    loop {
        if !faiss.is_healthy().await {
            warn!("FAISS not reachable — waiting 5s");
            sleep(Duration::from_secs(5)).await;
            continue;
        }

        let rpc = RPCS[rpc_idx % RPCS.len()];
        let latest = match get_latest_checkpoint(&client, rpc).await {
            Ok(n) => n,
            Err(e) => {
                warn!("Sui RPC error ({}): {} — rotating", rpc, e);
                rpc_idx += 1;
                sleep(Duration::from_millis(poll_ms)).await;
                continue;
            }
        };

        let last = state.last_block();
        let from = if last == 0 { latest.saturating_sub(1) } else { last + 1 };

        for seq in from..=latest {
            let cp = match get_checkpoint(&client, rpc, seq).await {
                Ok(c) => c,
                Err(e) => {
                    warn!("[{}] checkpoint {} error: {}", CHAIN_LBL, seq, e);
                    rpc_idx += 1;
                    continue;
                }
            };

            let features = extract_features(&cp, &client, rpc).await;
            let phi = features.iter().sum::<f64>() / 9.0;
            let entity_id = block_entity_id(CHAIN_LBL, seq);
            let bh = bh_id(&entity_id);
            let vector = build_vector(&features, &format!("{}:{}", CHAIN_LBL, seq));
            let ts_u64 = cp["timestamp_ms"].as_u64().unwrap_or(0) / 1000;
            let ts = ts_u64 as f64;
            let cp_hash = match cp["digest"].as_str() {
                Some(h) if !h.is_empty() => h.to_string(),
                _ => {
                    warn!("[{}] checkpoint {}: no digest — zero block hash", CHAIN_LBL, seq);
                    "0x0".to_string()
                }
            };

            let payload = BatchPayload {
                vectors: vec![VectorEntry {
                    entity_id: entity_id.clone(), vector,
                    magnitude: phi, entropy: phi,
                    timestamp: ts, bh_id: bh, block_num: seq,
                    chain_id: CHAIN_ID, chain_label: CHAIN_LBL.into(),
                    vm_type: VM_TYPE.into(),
                    funding_source: None, block_hash_hex: None,
                    event_type: None, sense_hex: None, antisense_hex: None,
                }],
                block_num: seq, block_features: features.to_vec(),
                block_phi: phi, chain_id: CHAIN_ID,
                chain_label: CHAIN_LBL.into(), vm_type: VM_TYPE.into(),
            };

            match faiss.add_batch(&payload).await {
                Ok(added) => {
                    let tx_batch = sui_bh_batch(
                        &cp, seq, CHAIN_ID, CHAIN_LBL, &cp_hash, ts_u64,
                        &client, rpc,
                    ).await;
                    let bh_stored = faiss.add_tx_bh_batch(&tx_batch).await.unwrap_or(0);
                    info!("[{}] checkpoint={} phi={:.4} added={} bh_stored={}",
                        CHAIN_LBL, seq, phi, added, bh_stored);
                }
                Err(e) => warn!("[{}] FAISS ingest failed seq {}: {}", CHAIN_LBL, seq, e),
            }
            state.save(seq).ok();
        }
        sleep(Duration::from_millis(poll_ms)).await;
    }
}
