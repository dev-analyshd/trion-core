/*!
 * TRION Movement Labs (Move VM) Behavioral Indexer — Rust L0
 * ===========================================================
 * Polls Movement Labs REST API and pushes 128-dim behavioral vectors
 * AND per-tx canonical BH (L0.1 ledger).
 *
 * Movement behavioral dimensions (9 Shannon entropy features):
 *   f1 — Function call entropy   H(function_id distribution)
 *   f2 — Sender entropy          H(sender_address frequency)
 *   f3 — Gas unit entropy        H(gas_unit_price bins)
 *   f4 — Resource change entropy H(resource_type changes)
 *   f5 — Event emission entropy  H(event_type diversity)
 *   f6 — Module diversity        H(module_address frequency)
 *   f7 — Success ratio entropy   H(success vs failure)
 *   f8 — Payload type entropy    H(entry_function/script/multisig)
 *   f9 — Sequence delta entropy  H(sequence_number gaps)
 *
 * Chain ID: 5002 (MOVEMENT_MAINNET)
 */

use anyhow::Result;
use serde_json::Value;
use std::sync::atomic::{AtomicU64, Ordering};
use std::time::{SystemTime, UNIX_EPOCH};
use tokio::time::{sleep, Duration};
use tracing::{info, warn};
use trion_common::{
    bh_id, block_entity_id, build_vector, canonical_bh, event_type_name,
    freq_entropy, histogram_entropy,
    entropy::ratio_entropy, BatchPayload, FaissClient, IndexerState, TxBhBatch, TxBhEntry, VectorEntry,
};

const CHAIN_ID:  u64  = 5002;
const CHAIN_LBL: &str = "MOVEMENT_MAINNET";
const VM_TYPE:   &str = "MOVE";

const MOVEMENT_RPCS: &[&str] = &[
    "https://mainnet.movementnetwork.xyz/v1",
    "https://seed-node2.movementlabs.xyz/v1",
    "https://movement-mainnet.rpc.thirdweb.com",
    // Removed testnet endpoint — was leaking stale testnet data into mainnet indexer.
];

async fn movement_get(client: &reqwest::Client, rpc: &str, path: &str) -> Result<Value> {
    let url = format!("{}{}", rpc.trim_end_matches('/'), path);
    let resp = client.get(&url).header("Accept", "application/json").send().await?;
    if !resp.status().is_success() { anyhow::bail!("Movement HTTP {}", resp.status()); }
    Ok(resp.json().await?)
}

async fn get_latest_block_height(client: &reqwest::Client, rpc: &str) -> Result<u64> {
    let data = movement_get(client, rpc, "/").await?;
    Ok(data["block_height"].as_str().and_then(|s| s.parse().ok()).unwrap_or(0))
}

async fn get_block_txs(client: &reqwest::Client, rpc: &str, height: u64) -> Result<Value> {
    movement_get(client, rpc, &format!("/blocks/by_height/{}?with_transactions=true", height)).await
}

fn extract_features(block: &Value) -> [f64; 9] {
    let txs = match block["transactions"].as_array() {
        Some(a) => a, None => return [0.5f64; 9],
    };
    let user_txs: Vec<&Value> = txs.iter().filter(|t| t["type"].as_str() == Some("user_transaction")).collect();
    if user_txs.is_empty() { return [0.5f64; 9]; }

    let mut functions:      Vec<String> = Vec::new();
    let mut senders:        Vec<String> = Vec::new();
    let mut gas_prices:     Vec<f64>    = Vec::new();
    let mut resource_types: Vec<String> = Vec::new();
    let mut event_types:    Vec<String> = Vec::new();
    let mut modules:        Vec<String> = Vec::new();
    let (mut success, mut failed) = (0u64, 0u64);
    let mut payload_types:  Vec<String> = Vec::new();
    let mut seq_nums:       Vec<f64>    = Vec::new();

    for tx in &user_txs {
        senders.push(tx["sender"].as_str().unwrap_or("").to_string());
        gas_prices.push(tx["gas_unit_price"].as_str().and_then(|s| s.parse::<f64>().ok()).unwrap_or(0.0));
        seq_nums.push(tx["sequence_number"].as_str().and_then(|s| s.parse::<f64>().ok()).unwrap_or(0.0));
        let payload = &tx["payload"];
        let ptype   = payload["type"].as_str().unwrap_or("unknown").to_string();
        payload_types.push(ptype.clone());
        if ptype == "entry_function_payload" {
            let func = payload["function"].as_str().unwrap_or("").to_string();
            functions.push(func.clone());
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

// ── Per-tx Behavioral Hash pipeline ──────────────────────────────────────────

static MAX_OCTA: AtomicU64 = AtomicU64::new(100_000_000); // 1 MOVE in octas

fn move_magnitude(octas: u64) -> f64 {
    let old = MAX_OCTA.load(Ordering::Relaxed);
    if octas > old { MAX_OCTA.store(octas, Ordering::Relaxed); }
    let max = MAX_OCTA.load(Ordering::Relaxed).max(1) as f64;
    let v   = octas as f64;
    ((v + 1.0).log10() / (max + 1.0).log10()).clamp(0.0, 1.0)
}

fn classify_move_function(func: &str) -> u8 {
    let f = func.to_lowercase();
    let module = func.splitn(3, "::").nth(1).unwrap_or("").to_lowercase();
    match true {
        _ if f.contains("swap") || f.contains("exchange") || module.contains("swap") || module.contains("dex") => 1,  // SWAP
        _ if f.contains("add_liquidity") || f.contains("add_pool") || module.contains("liquidity")              => 2,  // LIQUIDITY
        _ if (f.contains("stake") || module.contains("staking")) && !f.contains("unstake")                      => 8,  // STAKE
        _ if f.contains("unstake") || f.contains("unlock")                                                       => 9,  // UNSTAKE
        _ if f.contains("borrow")                                                                                 => 3,  // BORROW
        _ if f.contains("repay")                                                                                  => 4,  // REPAY
        _ if f.contains("vote") || f.contains("proposal") || module.contains("governance")                      => 6,  // GOVERNANCE
        _ if f.contains("flash")                                                                                   => 15, // FLASH_LOAN
        _ if f.contains("oracle") || f.contains("price")                                                          => 16, // ORACLE_UPDATE
        _ if f.contains("mint") && !f.contains("comment")                                                         => 13, // MINT
        _ if f.contains("burn")                                                                                    => 14, // BURN
        _ if f.contains("claim") || f.contains("harvest")                                                         => 19, // CLAIM
        _ if f.contains("airdrop")                                                                                 => 18, // AIRDROP
        _ => 0, // TRANSFER
    }
}

fn move_bh_batch(block: &Value, chain_id: u64, label: &str, height: u64, block_hash: &str, ts: u64) -> TxBhBatch {
    let txs = match block["transactions"].as_array() {
        Some(a) => a,
        None    => return TxBhBatch { chain_id, chain_label: label.to_string(), block_num: height, block_hash: block_hash.to_string(), timestamp: ts, entries: vec![] },
    };
    let mut entries: Vec<TxBhEntry> = Vec::new();

    for tx in txs {
        if tx["type"].as_str() != Some("user_transaction") { continue; }
        let tx_hash = tx["hash"].as_str().unwrap_or("").to_string();
        if tx_hash.is_empty() { continue; }

        let sender  = tx["sender"].as_str().unwrap_or("unknown").to_string();
        let payload = &tx["payload"];
        let func    = payload["function"].as_str().unwrap_or("0x1::coin::transfer");
        let et      = classify_move_function(func);

        let octas = payload["arguments"].as_array()
            .and_then(|args| args.iter().rev()
                .find_map(|a| a.as_str().and_then(|s| s.parse::<u64>().ok())
                    .or_else(|| a.as_u64())))
            .unwrap_or(0);

        let mag = move_magnitude(octas);
        let eid = bh_id(&sender);
        let (sense_hex, antisense_hex) = canonical_bh(&eid, et, mag, 0, ts, chain_id, block_hash);

        entries.push(TxBhEntry {
            tx_hash, from_addr: sender, to_addr: String::new(),
            event_type: et, event_type_name: event_type_name(et).to_string(),
            entity_id: eid, magnitude_norm: mag, value_wei: octas.to_string(),
            selector: func[..func.len().min(32)].to_string(),
            timestamp: ts, chain_id, chain_label: label.to_string(), block_num: height,
            block_hash: block_hash.to_string(), sense_hex, antisense_hex,
        });
    }
    TxBhBatch { chain_id, chain_label: label.to_string(), block_num: height, block_hash: block_hash.to_string(), timestamp: ts, entries }
}

#[tokio::main]
async fn main() -> Result<()> {
    tracing_subscriber::fmt().with_env_filter("info").init();

    let faiss_url = std::env::var("FAISS_SERVICE_URL").unwrap_or_else(|_| "http://127.0.0.1:8000".into());
    let poll_ms   = std::env::var("POLL_MS").ok().and_then(|s| s.parse().ok()).unwrap_or(4_000u64);
    let faiss     = FaissClient::new(&faiss_url)?;
    let mut state = IndexerState::new("movement_mainnet");
    let client    = reqwest::Client::builder().timeout(Duration::from_secs(12)).build()?;
    let mut rpc_idx = 0usize;

    info!("TRION Movement Rust Indexer — chain={} label={} poll={}ms", CHAIN_ID, CHAIN_LBL, poll_ms);

    loop {
        if !faiss.is_healthy().await { sleep(Duration::from_secs(5)).await; continue; }

        let rpc    = MOVEMENT_RPCS[rpc_idx % MOVEMENT_RPCS.len()];
        let latest = match get_latest_block_height(&client, rpc).await {
            Ok(n)  => n,
            Err(e) => { warn!("Movement latest error: {} — rotating", e); rpc_idx += 1; sleep(Duration::from_millis(poll_ms)).await; continue; }
        };
        let last = state.last_block();
        let from = if last == 0 { latest.saturating_sub(1) } else { last + 1 };

        for height in from..=latest {
            let block = match get_block_txs(&client, rpc, height).await {
                Ok(b)  => b,
                Err(e) => { warn!("[{}] block {} error: {}", CHAIN_LBL, height, e); rpc_idx += 1; continue; }
            };
            let features  = extract_features(&block);
            let phi       = features.iter().sum::<f64>() / 9.0;
            let eid       = block_entity_id(CHAIN_LBL, height);
            let bh        = bh_id(&eid);
            let vector    = build_vector(&features, &format!("{}:{}", CHAIN_LBL, height));
            let ts        = SystemTime::now().duration_since(UNIX_EPOCH).unwrap_or_default().as_secs_f64();
            let ts_u64    = ts as u64;
            let block_hash = block["block_hash"].as_str()
                .map(|h| h.to_string())
                .unwrap_or_else(|| bh_id(&format!("move_block:{}:{}", CHAIN_LBL, height)));

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
                Ok(added) => {
                    let tx_batch = move_bh_batch(&block, CHAIN_ID, CHAIN_LBL, height, &block_hash, ts_u64);
                    let bh_stored = faiss.add_tx_bh_batch(&tx_batch).await.unwrap_or(0);
                    info!("[{}] block={} φ={:.4} added={} bh_stored={}", CHAIN_LBL, height, phi, added, bh_stored);
                }
                Err(e) => warn!("[{}] FAISS failed: {}", CHAIN_LBL, e),
            }
            state.save(height).ok();
        }
        sleep(Duration::from_millis(poll_ms)).await;
    }
}
