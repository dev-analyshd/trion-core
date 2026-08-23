/*!
 * TRION Algorand Behavioral Indexer — Rust
 * Polls AlgoNode public REST. 9 entropy features + per-tx canonical BH.
 * Event mapping: pay/axfer→TRANSFER, keyreg→STAKE, acfg→MINT, afrz→UNSTAKE,
 * appl→SWAP/DEPLOY, close-amount→BURN.
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

const CHAIN_ID:  u64  = 8200;
const CHAIN_LBL: &str = "ALGORAND";
const VM_TYPE:   &str = "ALGORAND";
const ALGOD_URLS: &[&str] = &[
    "https://mainnet-api.algonode.cloud",
    "https://algoexplorerapi.purestake.io/ps2",
];

async fn algo_get(client: &reqwest::Client, base: &str, path: &str) -> Result<Value> {
    let url = format!("{}{}", base.trim_end_matches('/'), path);
    let resp = client.get(&url).header("Accept", "application/json").send().await?;
    if !resp.status().is_success() { anyhow::bail!("Algod HTTP {}", resp.status()); }
    Ok(resp.json().await?)
}

fn classify_algorand(tx: &Value) -> u8 {
    let ttype = tx.get("tx-type").and_then(|v| v.as_str())
        .or_else(|| tx.get("type").and_then(|v| v.as_str())).unwrap_or("pay");
    let has_close = tx.get("asset-transfer-transaction")
        .and_then(|a| a.get("close-amount")).is_some();
    match ttype {
        "pay"   => 0,
        "axfer" if has_close => 14,
        "axfer" => 0,
        "afrz"  => 4,
        "acfg"  => 13,
        "keyreg" => 3,
        "appl"  => {
            match tx.get("on-completion").and_then(|v| v.as_str()).unwrap_or("noop") {
                "optin" | "create" => 11,
                "closeout" | "clear" => 4,
                _ => if tx.get("application-id").and_then(|v| v.as_u64()).unwrap_or(0) > 0 { 1 } else { 6 },
            }
        }
        _ => 0,
    }
}

fn tx_amount_micro(tx: &Value) -> u64 {
    if let Some(p) = tx.get("payment-transaction") {
        return p.get("amount").and_then(|a| a.as_u64()).unwrap_or(0);
    }
    if let Some(a) = tx.get("asset-transfer-transaction") {
        return a.get("amount").and_then(|x| x.as_u64()).unwrap_or(0);
    }
    0
}

fn extract_features(txs: &[Value]) -> [f64; 9] {
    if txs.is_empty() { return [0.5f64; 9]; }
    let mut ttypes = Vec::new(); let mut senders = Vec::new();
    let mut receivers = Vec::new(); let mut amounts = Vec::new();
    let mut fees = Vec::new(); let mut assets = Vec::new(); let mut apps = Vec::new();
    let (mut close_rem, mut plain) = (0u64, 0u64);
    let (mut grouped, mut single) = (0u64, 0u64);

    for tx in txs {
        ttypes.push(tx.get("tx-type").and_then(|v| v.as_str()).unwrap_or("pay").to_string());
        senders.push(tx.get("sender").and_then(|v| v.as_str()).unwrap_or("").to_string());
        let recv = tx.get("payment-transaction").and_then(|p| p.get("receiver").and_then(|r| r.as_str()))
            .or_else(|| tx.get("asset-transfer-transaction").and_then(|a| a.get("receiver").and_then(|r| r.as_str())))
            .or_else(|| tx.get("receiver").and_then(|r| r.as_str())).unwrap_or("");
        receivers.push(recv.to_string());
        let amt = tx_amount_micro(tx) as f64 / 1e6;
        if amt > 0.0 { amounts.push(amt); }
        fees.push(tx.get("fee").and_then(|f| f.as_u64()).unwrap_or(0) as f64 / 1e6);
        let asset = tx.get("asset-transfer-transaction").and_then(|a| a.get("asset-id"))
            .map(|id| id.to_string())
            .or_else(|| tx.get("xfer-asset").map(|id| id.to_string()))
            .unwrap_or_else(|| "algo".into());
        assets.push(asset);
        if let Some(app_id) = tx.get("application-id").and_then(|v| v.as_u64()) { apps.push(app_id.to_string()); }
        let has_close = tx.get("payment-transaction").and_then(|p| p.get("close-remainder-amount")).is_some()
            || tx.get("asset-transfer-transaction").and_then(|a| a.get("close-amount")).is_some();
        if has_close { close_rem += 1; } else { plain += 1; }
        if tx.get("group").is_some() { grouped += 1; } else { single += 1; }
    }
    [
        freq_entropy(&ttypes), freq_entropy(&senders), freq_entropy(&receivers),
        histogram_entropy(&amounts, 8), histogram_entropy(&fees, 8),
        freq_entropy(&assets), freq_entropy(&apps),
        ratio_entropy(close_rem, close_rem + plain),
        ratio_entropy(grouped, grouped + single),
    ]
}

static MAX_MICRO: AtomicU64 = AtomicU64::new(1_000_000_000);

fn algo_magnitude(micro: u64) -> f64 {
    let old = MAX_MICRO.load(Ordering::Relaxed);
    if micro > old { MAX_MICRO.store(micro, Ordering::Relaxed); }
    let max = MAX_MICRO.load(Ordering::Relaxed).max(1) as f64;
    ((micro as f64 + 1.0).log10() / (max + 1.0).log10()).clamp(0.0, 1.0)
}

fn algo_bh_batch(txs: &[Value], round: u64, block_hash: &str, ts: u64) -> TxBhBatch {
    let mut entries = Vec::new();
    for tx in txs {
        let hash = tx.get("id").and_then(|v| v.as_str()).unwrap_or("").to_string();
        if hash.is_empty() { continue; }
        let sender = tx.get("sender").and_then(|v| v.as_str()).unwrap_or("unknown").to_string();
        let recv = tx.get("payment-transaction").and_then(|p| p.get("receiver").and_then(|r| r.as_str()))
            .or_else(|| tx.get("asset-transfer-transaction").and_then(|a| a.get("receiver").and_then(|r| r.as_str())))
            .or_else(|| tx.get("receiver").and_then(|r| r.as_str())).unwrap_or("").to_string();
        let et = classify_algorand(tx);
        let micro = tx_amount_micro(tx);
        let mag = algo_magnitude(micro);
        let eid = bh_id(&sender);
        let (sense_hex, antisense_hex) = canonical_bh(&eid, et, mag, 0, ts, CHAIN_ID, block_hash);
        entries.push(TxBhEntry {
            tx_hash: hash, from_addr: sender, to_addr: recv,
            event_type: et, event_type_name: event_type_name(et).to_string(),
            entity_id: eid, magnitude_norm: mag, value_wei: micro.to_string(),
            selector: tx.get("tx-type").and_then(|v| v.as_str()).unwrap_or("").to_string(),
            timestamp: ts, chain_id: CHAIN_ID, chain_label: CHAIN_LBL.to_string(),
            block_num: round, block_hash: block_hash.to_string(),
            sense_hex, antisense_hex,
        });
    }
    TxBhBatch { chain_id: CHAIN_ID, chain_label: CHAIN_LBL.to_string(),
                block_num: round, block_hash: block_hash.to_string(),
                timestamp: ts, entries }
}

#[tokio::main]
async fn main() -> Result<()> {
    tracing_subscriber::fmt().with_env_filter("info").init();
    let faiss_url = std::env::var("FAISS_SERVICE_URL").unwrap_or_else(|_| "http://127.0.0.1:8000".into());
    let poll_ms = std::env::var("POLL_MS").ok().and_then(|s| s.parse().ok()).unwrap_or(4_000u64);
    let mut base = std::env::var("ALGORAND_RPC_URL").unwrap_or_else(|_| ALGOD_URLS[0].into());
    let mut rpc_idx = 0usize;  // RPC failover rotation index
    let faiss = FaissClient::new(&faiss_url)?;
    let state = IndexerState::new("algorand");
    let client = reqwest::Client::builder().timeout(Duration::from_secs(15)).build()?;
    info!("TRION Algorand Indexer — chain={} poll={}ms", CHAIN_ID, poll_ms);

    loop {
        if !faiss.is_healthy().await { sleep(Duration::from_secs(5)).await; continue; }
        let latest = match algo_get(&client, &base, "/v2/status").await {
            Ok(v) => v.get("last-round").and_then(|r| r.as_u64()).unwrap_or(0),
            Err(e) => { warn!("Algorand status error: {} — rotating RPC", e); { rpc_idx += 1; base = ALGOD_URLS[rpc_idx % ALGOD_URLS.len()].into(); } sleep(Duration::from_millis(poll_ms)).await; continue; }
        };
        if latest == 0 { sleep(Duration::from_millis(poll_ms)).await; continue; }
        let last = state.last_block();
        let from = if last == 0 { latest.saturating_sub(1) } else { last + 1 };

        for round in from..=latest {
            let block = match algo_get(&client, &base, &format!("/v2/blocks/{}", round)).await {
                Ok(v) => v, Err(e) => { warn!("[{}] round {} error: {}", CHAIN_LBL, round, e); continue; }
            };
            let txs: Vec<Value> = block.pointer("/block/txns").and_then(|v| v.as_array())
                .cloned().unwrap_or_default();
            let block_hash = block.pointer("/cert/proposal/ophash").and_then(|v| v.as_str())
                .or_else(|| block.get("hash").and_then(|v| v.as_str())).unwrap_or("").to_string();
            let ts = block.pointer("/block/ts").and_then(|v| v.as_u64())
                .unwrap_or_else(|| SystemTime::now().duration_since(UNIX_EPOCH).unwrap_or_default().as_secs());
            if txs.is_empty() { state.save(round).ok(); continue; }

            let features = extract_features(&txs);
            let phi = features.iter().sum::<f64>() / 9.0;
            let eid = block_entity_id(CHAIN_LBL, round);
            let bh = bh_id(&eid);
            let vector = build_vector(&features, &format!("{}:{}", CHAIN_LBL, round));
            let block_hash_hex = if block_hash.is_empty() {
                bh_id(&format!("algorand_round:{}:{}", CHAIN_LBL, round))
            } else { bh_id(&block_hash) };

            let payload = BatchPayload {
                vectors: vec![VectorEntry {
                    entity_id: eid, vector, magnitude: phi, entropy: phi,
                    timestamp: ts as f64, bh_id: bh, block_num: round,
                    chain_id: CHAIN_ID, chain_label: CHAIN_LBL.into(), vm_type: VM_TYPE.into(),
                    funding_source: None, block_hash_hex: Some(block_hash_hex.clone()),
                    event_type: Some(classify_algorand(&txs[0])),
                    sense_hex: None, antisense_hex: None,
                }],
                block_num: round, block_features: features.to_vec(), block_phi: phi,
                chain_id: CHAIN_ID, chain_label: CHAIN_LBL.into(), vm_type: VM_TYPE.into(),
            };
            match faiss.add_batch(&payload).await {
                Ok(added) => {
                    let tx_batch = algo_bh_batch(&txs, round, &block_hash_hex, ts);
                    let bh_stored = faiss.add_tx_bh_batch(&tx_batch).await.unwrap_or(0);
                    info!("[{}] round={} txs={} φ={:.4} added={} bh={}", CHAIN_LBL, round, txs.len(), phi, added, bh_stored);
                }
                Err(e) => warn!("[{}] FAISS failed: {}", CHAIN_LBL, e),
            }
            state.save(round).ok();
        }
        sleep(Duration::from_millis(poll_ms)).await;
    }
}
