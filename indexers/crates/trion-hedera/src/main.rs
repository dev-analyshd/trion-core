/*!
 * TRION Hedera Behavioral Indexer — Rust
 * ========================================
 * Polls Hedera Hashio JSON-RPC (EVM-compatible) via eth_getBlockByNumber.
 * Produces 128-dim vectors AND per-tx canonical BH (L0.1 ledger).
 *
 * Hedera behavioral dimensions (9 Shannon entropy features):
 *   f1 — Value entropy        H(tx value bins, HBAR)
 *   f2 — Sender entropy       H(from frequency)
 *   f3 — Recipient entropy    H(to frequency)
 *   f4 — Gas price entropy    H(gasPrice bins)
 *   f5 — Gas usage entropy    H(gas bins)
 *   f6 — Input data entropy   H(input length bins)
 *   f7 — Contract ratio       H(contract-creation vs call)
 *   f8 — Selector diversity   H(4-byte selectors)
 *   f9 — Value-flow entropy   H(incoming vs outgoing value)
 */

use anyhow::Result;
use serde_json::Value;
use tokio::time::{sleep, Duration};
use tracing::{info, warn};
use trion_common::{
    bh_id, block_entity_id, build_vector, canonical_bh, classify_event_type, event_type_name,
    hex_to_32bytes, freq_entropy, histogram_entropy,
    entropy::ratio_entropy, BatchPayload, FaissClient, IndexerState, TxBhBatch, TxBhEntry, VectorEntry,
};

const CHAIN_ID:  u64  = 28000;
const CHAIN_LBL: &str = "HEDERA";
const VM_TYPE:   &str = "EVM"; // Hedera smart contracts are EVM-compatible

const HEDERA_RPCS: &[&str] = &[
    "https://mainnet.hashio.io/api",
    "https://hedera-mainnet.rpc.subquery.network/public",
    "https://hederamainnet.rpc.thirdweb.com",
];

/// 1 HBAR = 1e8 tinybar; JSON-RPC values are in 1e18 wei-equivalent
const WEI_DECIMALS: f64 = 1e18;

async fn rpc(client: &reqwest::Client, base: &str, method: &str, params: Value) -> Result<Value> {
    let url = base.trim_end_matches('/');
    let body = serde_json::json!({ "jsonrpc": "2.0", "id": 1, "method": method, "params": params });
    let resp = client.post(url).json(&body).send().await?;
    if !resp.status().is_success() { anyhow::bail!("Hedera RPC HTTP {}", resp.status()); }
    let v: Value = resp.json().await?;
    if let Some(err) = v.get("error") {
        anyhow::bail!("Hedera RPC error: {}", err);
    }
    Ok(v.get("result").cloned().unwrap_or(Value::Null))
}

async fn get_latest_block(client: &reqwest::Client, base: &str) -> Result<u64> {
    let r = rpc(client, base, "eth_blockNumber", Value::Array(vec![])).await?;
    let hex = r.as_str().unwrap_or("0x0");
    Ok(u64::from_str_radix(hex.trim_start_matches("0x"), 16).unwrap_or(0))
}

async fn get_block(client: &reqwest::Client, base: &str, num: u64) -> Result<Value> {
    rpc(client, base, "eth_getBlockByNumber", serde_json::json!([
        format!("0x{:x}", num), true
    ])).await
}

fn hex_to_u128(hex: &str) -> u128 {
    let s = hex.trim_start_matches("0x");
    u128::from_str_radix(s, 16).unwrap_or(0)
}

fn extract_features(txs: &[Value]) -> [f64; 9] {
    if txs.is_empty() { return [0.5f64; 9]; }

    let mut values:    Vec<f64>    = Vec::new();
    let mut senders:   Vec<String> = Vec::new();
    let mut recipients: Vec<String> = Vec::new();
    let mut gas_prices: Vec<f64>   = Vec::new();
    let mut gas:       Vec<f64>    = Vec::new();
    let mut input_lens: Vec<f64>   = Vec::new();
    let (mut creations, mut calls) = (0u64, 0u64);
    let mut selectors: Vec<String> = Vec::new();
    let (mut in_val, mut out_val) = (0f64, 0f64);

    for tx in txs {
        let val = hex_to_u128(tx.get("value").and_then(|v| v.as_str()).unwrap_or("0x0")) as f64 / WEI_DECIMALS;
        if val > 0.0 { values.push(val); }

        let from = tx.get("from").and_then(|v| v.as_str()).unwrap_or("").to_string();
        let to   = tx.get("to").and_then(|v| v.as_str()).map(|s| s.to_string());
        senders.push(from.clone());
        if let Some(t) = &to { recipients.push(t.clone()); }

        let gp = hex_to_u128(tx.get("gasPrice").and_then(|v| v.as_str()).unwrap_or("0x0")) as f64;
        gas_prices.push(gp / 1e9); // gwei-scale

        gas.push(hex_to_u128(tx.get("gas").and_then(|v| v.as_str()).unwrap_or("0x0")) as f64);

        let input = tx.get("input").and_then(|v| v.as_str()).unwrap_or("0x");
        input_lens.push((input.len() as f64 / 2.0).clamp(0.0, 100_000.0));

        if to.is_none() || to.as_deref() == Some("") {
            creations += 1;
        } else {
            calls += 1;
        }

        let selector: String = input.trim_start_matches("0x").chars().take(8).collect();
        if !selector.is_empty() { selectors.push(selector); }

        // crude value flow: from-address reuse tracks direction
        if senders.iter().filter(|s| *s == &from).count() > 1 { out_val += val.max(0.0); } else { in_val += val.max(0.0); }
    }

    [
        histogram_entropy(&values, 8),
        freq_entropy(&senders),
        freq_entropy(&recipients),
        histogram_entropy(&gas_prices, 8),
        histogram_entropy(&gas, 8),
        histogram_entropy(&input_lens, 8),
        ratio_entropy(creations, creations + calls),
        freq_entropy(&selectors),
        ratio_entropy(out_val as u64, (in_val + out_val) as u64),
    ]
}

// ── Per-tx Behavioral Hash pipeline ──────────────────────────────────────────

/// CANONICAL_BH.md §4 — deterministic magnitude normalization:
///   human = raw / 10^18 (EVM-style wei; HBAR tinybar differs — see CANONICAL_BH.md §4); M = min(1, log10(human + 1) / log10(1001))
/// The rolling session-max tracker was removed: it made the BH of a fixed
/// transaction depend on what else the process had observed (canonical
/// violation — the same tx must always produce the same BH).
fn hbar_magnitude(wei: u128) -> f64 {
    let w = (wei as u64).min(u64::MAX / 2);
    let human = w as f64 / 1e18;
    if human <= 0.0 { return 0.0; }
    ((human + 1.0).log10() / (1001.0_f64).log10()).min(1.0)
}

fn hedera_bh_batch(txs: &[Value], block_num: u64, block_hash: &str, ts: u64) -> TxBhBatch {
    let mut entries: Vec<TxBhEntry> = Vec::new();

    for tx in txs {
        let hash = tx.get("hash").and_then(|v| v.as_str()).unwrap_or("").to_string();
        if hash.is_empty() { continue; }

        let sender = tx.get("from").and_then(|v| v.as_str()).unwrap_or("unknown").to_string();
        let dest   = tx.get("to").and_then(|v| v.as_str()).unwrap_or("").to_string();
        let input  = tx.get("input").and_then(|v| v.as_str()).unwrap_or("0x");
        let sel: String = input.trim_start_matches("0x").chars().take(8).collect();
        let et = if dest.is_empty() { 11 } else if sel.is_empty() { 0 } else { classify_event_type(&sel) };
        let wei = hex_to_u128(tx.get("value").and_then(|v| v.as_str()).unwrap_or("0x0"));
        let mag = hbar_magnitude(wei);
        let eid = bh_id(&sender);
        let (sense_hex, antisense_hex) = canonical_bh(&eid, et, mag, 0, ts, CHAIN_ID, block_hash);

        entries.push(TxBhEntry {
            tx_hash: hash,
            from_addr: sender,
            to_addr: dest,
            event_type: et,
            event_type_name: event_type_name(et).to_string(),
            entity_id: eid,
            magnitude_norm: mag,
            value_wei: wei.to_string(),
            selector: sel,
            timestamp: ts,
            chain_id: CHAIN_ID,
            chain_label: CHAIN_LBL.to_string(),
            block_num: block_num,
            block_hash: block_hash.to_string(),
            sense_hex,
            antisense_hex,
        });
    }

    TxBhBatch {
        chain_id: CHAIN_ID,
        chain_label: CHAIN_LBL.to_string(),
        block_num: block_num,
        block_hash: block_hash.to_string(),
        timestamp: ts,
        entries,
    }
}

#[tokio::main]
async fn main() -> Result<()> {
    tracing_subscriber::fmt().with_env_filter("info").init();

    let faiss_url = std::env::var("FAISS_SERVICE_URL").unwrap_or_else(|_| "http://127.0.0.1:8000".into());
    let poll_ms   = std::env::var("POLL_MS").ok().and_then(|s| s.parse().ok()).unwrap_or(5_000u64);
    let mut base  = std::env::var("HEDERA_RPC_URL").unwrap_or_else(|_| HEDERA_RPCS[0].into());
    let mut rpc_idx = 0usize;  // RPC failover rotation index
    let faiss     = FaissClient::new(&faiss_url)?;
    let state = IndexerState::new("hedera");
    let client    = reqwest::Client::builder().timeout(Duration::from_secs(15)).build()?;

    info!("TRION Hedera Rust Indexer — chain={} poll={}ms rpc={}", CHAIN_ID, poll_ms, base);

    loop {
        if !faiss.is_healthy().await { sleep(Duration::from_secs(5)).await; continue; }

        let latest = match get_latest_block(&client, &base).await {
            Ok(n) => n,
            Err(e) => { warn!("Hedera latest block error: {} — rotating RPC", e); rpc_idx += 1; base = HEDERA_RPCS[rpc_idx % HEDERA_RPCS.len()].into(); sleep(Duration::from_millis(poll_ms)).await; continue; }
        };
        if latest == 0 { sleep(Duration::from_millis(poll_ms)).await; continue; }

        let last = state.last_block();
        let from = if last == 0 { latest.saturating_sub(1) } else { last + 1 };

        for num in from..=latest {
            let block = match get_block(&client, &base, num).await {
                Ok(v) if !v.is_null() => v,
                _ => { warn!("[{}] block {} unavailable", CHAIN_LBL, num); continue; }
            };

            let block_hash = block.get("hash").and_then(|v| v.as_str()).unwrap_or("").to_string();
            // CANONICAL_BH.md §5 — Hedera block timestamp (hex seconds);
            // 0 = unknown, never wall-clock.
            let ts = block.get("timestamp").and_then(|v| v.as_str())
                .and_then(|s| u64::from_str_radix(s.trim_start_matches("0x"), 16).ok())
                .unwrap_or(0);

            let txs: Vec<Value> = block.get("transactions").and_then(|v| v.as_array()).cloned().unwrap_or_default();
            if txs.is_empty() { state.save(num).ok(); continue; }

            let features = extract_features(&txs);
            let phi      = features.iter().sum::<f64>() / 9.0;
            let eid      = block_entity_id(CHAIN_LBL, num);
            let bh       = bh_id(&eid);
            let vector   = build_vector(&features, &format!("{}:{}", CHAIN_LBL, num));
            // CANONICAL_BH.md §9 — the payload's block_hash is the lenient
            // hex decode of the chain's real block hash (byte-identical to
            // the Python/TS pipelines). The old SHA3-substitution
            // (bh_id(block_hash)) was unreproducible cross-language and has
            // been removed. Missing hash → canonical "0x0" (32 zero bytes).
            let block_hash_hex = if block_hash.is_empty() {
                "0x0".to_string()
            } else {
                hex::encode(hex_to_32bytes(block_hash.trim_start_matches("0x")))
            };

            let payload = BatchPayload {
                vectors: vec![VectorEntry {
                    entity_id: eid,
                    vector,
                    magnitude: phi,
                    entropy: phi,
                    timestamp: ts as f64,
                    bh_id: bh,
                    block_num: num,
                    chain_id: CHAIN_ID,
                    chain_label: CHAIN_LBL.into(),
                    vm_type: VM_TYPE.into(),
                    funding_source: None,
                    block_hash_hex: Some(block_hash_hex.clone()),
                    event_type: Some(0),
                    sense_hex: None,
                    antisense_hex: None,
                }],
                block_num: num,
                block_features: features.to_vec(),
                block_phi: phi,
                chain_id: CHAIN_ID,
                chain_label: CHAIN_LBL.into(),
                vm_type: VM_TYPE.into(),
            };

            match faiss.add_batch(&payload).await {
                Ok(added) => {
                    let tx_batch = hedera_bh_batch(&txs, num, &block_hash_hex, ts);
                    let bh_stored = faiss.add_tx_bh_batch(&tx_batch).await.unwrap_or(0);
                    info!("[{}] block={} txs={} φ={:.4} added={} bh_stored={}",
                          CHAIN_LBL, num, txs.len(), phi, added, bh_stored);
                }
                Err(e) => warn!("[{}] FAISS failed: {}", CHAIN_LBL, e),
            }
            state.save(num).ok();
        }
        sleep(Duration::from_millis(poll_ms)).await;
    }
}
