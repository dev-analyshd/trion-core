/*!
 * TRION VeChain Behavioral Indexer — Rust
 * ========================================
 * Polls public VeChain Thor REST API for blocks and transactions.
 * Produces 128-dim vectors AND per-tx canonical BH (L0.1 ledger).
 *
 * VeChain behavioral dimensions (9 Shannon entropy features):
 *   f1 — Clause count entropy     H(clauses-per-tx bins)
 *   f2 — Origin entropy           H(origin address frequency)
 *   f3 — Clause target entropy    H(clause `to` frequency)
 *   f4 — Value entropy            H(clause value bins, VET)
 *   f5 — Gas entropy              H(gas / gasUsed bins)
 *   f6 — Data presence entropy    H(clause data empty vs populated)
 *   f7 — Delegate ratio entropy   H(delegated vs paid by origin)
 *   f8 — DependsOn entropy        H(dependent-tx patterns)
 *   f9 — Result ratio entropy     H(success vs reverted)
 */

use anyhow::Result;
use serde_json::Value;
use std::sync::atomic::{AtomicU64, Ordering};
use std::time::{SystemTime, UNIX_EPOCH};
use tokio::time::{sleep, Duration};
use tracing::{info, warn};
use trion_common::{
    bh_id, block_entity_id, build_vector, canonical_bh, classify_event_type, event_type_name,
    freq_entropy, histogram_entropy,
    entropy::ratio_entropy, BatchPayload, FaissClient, IndexerState, TxBhBatch, TxBhEntry, VectorEntry,
};

const CHAIN_ID:  u64  = 8400;
const CHAIN_LBL: &str = "VECHAIN";
const VM_TYPE:   &str = "EVM"; // VeChainThor is EVM-compatible

const THOR_URLS: &[&str] = &[
    "https://mainnet.vechain.org",
    "https://vethor-node.vechain.com",
    "https://synthetixsync.com",
];

async fn thor_get(client: &reqwest::Client, base: &str, path: &str) -> Result<Value> {
    let url = format!("{}{}", base.trim_end_matches('/'), path);
    let resp = client.get(&url).header("Accept", "application/json").send().await?;
    if !resp.status().is_success() { anyhow::bail!("Thor HTTP {} on {}", resp.status(), path); }
    Ok(resp.json().await?)
}

async fn get_best_block(client: &reqwest::Client, base: &str) -> Result<Value> {
    // /blocks/best — expanded: true returns txs with clauses
    thor_get(client, base, "/blocks/best?expanded=true").await
}

async fn get_block(client: &reqwest::Client, base: &str, num: u64) -> Result<Value> {
    thor_get(client, base, &format!("/blocks/{}?expanded=true", num)).await
}
fn tx_gas_used(tx: &Value) -> f64 {
    tx.get("gasUsed").and_then(|v| v.as_u64()).unwrap_or(0) as f64
}

fn extract_features(txs: &[Value]) -> [f64; 9] {
    if txs.is_empty() { return [0.5f64; 9]; }

    let mut clause_counts: Vec<f64> = Vec::new();
    let mut origins:  Vec<String> = Vec::new();
    let mut targets:  Vec<String> = Vec::new();
    let mut values:   Vec<f64>    = Vec::new();
    let mut gas:      Vec<f64>    = Vec::new();
    let mut data_pres: Vec<String> = Vec::new();
    let (mut delegated, mut not_delegated) = (0u64, 0u64);
    let mut depends:  Vec<String> = Vec::new();
    let (mut success, mut reverted) = (0u64, 0u64);

    for tx in txs {
        let clauses = tx.get("clauses").and_then(|v| v.as_array()).cloned().unwrap_or_default();
        clause_counts.push(clauses.len() as f64);
        origins.push(tx.get("origin").and_then(|v| v.as_str()).unwrap_or("").to_string());

        for c in &clauses {
            targets.push(c.get("to").and_then(|v| v.as_str()).unwrap_or("").to_string());
            let v = c.get("value").and_then(|x| x.as_str()).unwrap_or("0x0");
            if let Ok(f) = u128::from_str_radix(v.trim_start_matches("0x"), 16) {
                if f > 0 { values.push(f as f64 / 1e18); }
            }
            let has_data = c.get("data").and_then(|d| d.as_str()).map(|d| d.len() > 4).unwrap_or(false);
            data_pres.push(if has_data { "data".into() } else { "empty".into() });
        }

        gas.push(tx_gas_used(tx));

        if tx.get("delegated").and_then(|v| v.as_bool()).unwrap_or(false) {
            delegated += 1;
        } else {
            not_delegated += 1;
        }

        let dep = tx.get("dependsOn").and_then(|v| v.as_str()).unwrap_or("");
        depends.push(if dep.is_empty() { "independent".into() } else { "dependent".into() });

        // success detection: gasUsed < gas OR explicit receipt in expanded tx
        let gas_paid = tx.get("gas").and_then(|v| v.as_u64()).unwrap_or(0);
        let used = tx.get("gasUsed").and_then(|v| v.as_u64()).unwrap_or(0);
        if gas_paid == 0 || used <= gas_paid { success += 1; } else { reverted += 1; }
    }

    [
        histogram_entropy(&clause_counts, 5),
        freq_entropy(&origins),
        freq_entropy(&targets),
        histogram_entropy(&values, 8),
        histogram_entropy(&gas, 8),
        freq_entropy(&data_pres),
        ratio_entropy(delegated, delegated + not_delegated),
        freq_entropy(&depends),
        ratio_entropy(success, success + reverted),
    ]
}

/// Selector from first clause data (first 8 hex chars after 0x).
fn clause_selector(tx: &Value) -> String {
    let clause = tx.get("clauses").and_then(|v| v.as_array()).and_then(|a| a.first());
    clause
        .and_then(|c| c.get("data").and_then(|d| d.as_str()))
        .map(|d| {
            let s = d.trim_start_matches("0x");
            s.chars().take(8).collect()
        })
        .unwrap_or_default()
}

/// Clause `to` of first clause — the interaction target.
fn first_clause_to(tx: &Value) -> String {
    let clause = tx.get("clauses").and_then(|v| v.as_array()).and_then(|a| a.first());
    clause
        .and_then(|c| c.get("to").and_then(|t| t.as_str()))
        .unwrap_or("")
        .to_string()
}

// ── Per-tx Behavioral Hash pipeline ──────────────────────────────────────────

static MAX_WEI: AtomicU64 = AtomicU64::new(1_000_000_000_000_000_000); // 1 VET ref (wei)

fn vechain_magnitude(wei: u128) -> f64 {
    let w = (wei as u64).min(u64::MAX / 2); // saturate safely
    let old = MAX_WEI.load(Ordering::Relaxed);
    if w > old { MAX_WEI.store(w, Ordering::Relaxed); }
    let max = MAX_WEI.load(Ordering::Relaxed).max(1) as f64;
    ((w as f64 + 1.0).log10() / (max + 1.0).log10()).clamp(0.0, 1.0)
}

fn vechain_bh_batch(txs: &[Value], block_num: u64, block_hash: &str, ts: u64) -> TxBhBatch {
    let mut entries: Vec<TxBhEntry> = Vec::new();

    for tx in txs {
        let hash = tx.get("id").and_then(|v| v.as_str()).unwrap_or("").to_string();
        if hash.is_empty() { continue; }

        let sender = tx.get("origin").and_then(|v| v.as_str()).unwrap_or("unknown").to_string();
        let dest   = first_clause_to(tx);
        let sel    = clause_selector(tx);
        let et     = if sel.is_empty() { 0 } else { classify_event_type(&sel) };

        let mut total_wei: u128 = 0;
        if let Some(clauses) = tx.get("clauses").and_then(|v| v.as_array()) {
            for c in clauses {
                let v = c.get("value").and_then(|x| x.as_str()).unwrap_or("0x0");
                if let Ok(f) = u128::from_str_radix(v.trim_start_matches("0x"), 16) {
                    total_wei += f;
                }
            }
        }

        let mag = vechain_magnitude(total_wei);
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
            value_wei: total_wei.to_string(),
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
    let poll_ms   = std::env::var("POLL_MS").ok().and_then(|s| s.parse().ok()).unwrap_or(10_000u64);
    let base      = std::env::var("VECHAIN_RPC_URL").unwrap_or_else(|_| THOR_URLS[0].into());
    let faiss     = FaissClient::new(&faiss_url)?;
    let state = IndexerState::new("vechain");
    let client    = reqwest::Client::builder().timeout(Duration::from_secs(15)).build()?;

    info!("TRION VeChain Rust Indexer — chain={} poll={}ms thor={}", CHAIN_ID, poll_ms, base);

    loop {
        if !faiss.is_healthy().await { sleep(Duration::from_secs(5)).await; continue; }

        let best = match get_best_block(&client, &base).await {
            Ok(v) => v,
            Err(e) => { warn!("VeChain best block error: {}", e); sleep(Duration::from_millis(poll_ms)).await; continue; }
        };
        let latest = best.get("number").and_then(|v| v.as_u64()).unwrap_or(0);
        if latest == 0 { sleep(Duration::from_millis(poll_ms)).await; continue; }

        let last = state.last_block();
        let from = if last == 0 { latest.saturating_sub(1) } else { last + 1 };

        for num in from..=latest {
            let block = if num == latest { best.clone() } else {
                match get_block(&client, &base, num).await {
                    Ok(v) => v,
                    Err(e) => { warn!("[{}] block {} error: {}", CHAIN_LBL, num, e); continue; }
                }
            };

            let block_hash = block.get("id").and_then(|v| v.as_str()).unwrap_or("").to_string();
            let ts = block.get("timestamp").and_then(|v| v.as_u64()).unwrap_or_else(|| {
                SystemTime::now().duration_since(UNIX_EPOCH).unwrap_or_default().as_secs()
            });

            let txs: Vec<Value> = block.get("transactions").and_then(|v| v.as_array()).cloned().unwrap_or_default();
            if txs.is_empty() { state.save(num).ok(); continue; }

            let features = extract_features(&txs);
            let phi      = features.iter().sum::<f64>() / 9.0;
            let eid      = block_entity_id(CHAIN_LBL, num);
            let bh       = bh_id(&eid);
            let vector   = build_vector(&features, &format!("{}:{}", CHAIN_LBL, num));
            let block_hash_hex = if block_hash.is_empty() {
                bh_id(&format!("vechain_block:{}:{}", CHAIN_LBL, num))
            } else {
                bh_id(&block_hash)
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
                    let tx_batch = vechain_bh_batch(&txs, num, &block_hash_hex, ts);
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
