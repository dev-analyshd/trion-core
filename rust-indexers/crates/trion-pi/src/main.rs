/*!
 * TRION Pi Network / Stellar (MVM) Behavioral Indexer — Rust
 * ===========================================================
 * Polls Horizon REST API for ledger transactions.
 * Produces 128-dim vectors AND per-tx canonical BH (L0.1 ledger).
 *
 * Pi/Stellar behavioral dimensions (9 Shannon entropy features):
 *   f1 — Operation type entropy   H(payment/create_account/manage_offer/...)
 *   f2 — Account entropy          H(source_account frequency)
 *   f3 — Fee entropy              H(fee_charged bins)
 *   f4 — Amount entropy           H(amount bins)
 *   f5 — Asset diversity          H(asset_type/code distribution)
 *   f6 — Memo type entropy        H(none/text/hash/return/id)
 *   f7 — Path payment entropy     H(path_length bins)
 *   f8 — Trustline entropy        H(change_trust operations)
 *   f9 — Offer density            H(manage_offer operations)
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

const CHAIN_ID:  u64  = 8001;
const CHAIN_LBL: &str = "PI_MVM";
const VM_TYPE:   &str = "MVM";

const HORIZON_URLS: &[&str] = &[
    "https://horizon.stellar.org",
    "https://horizon.stellar.lobstr.co",
];

async fn horizon_get(client: &reqwest::Client, base: &str, path: &str) -> Result<Value> {
    let url = format!("{}{}", base.trim_end_matches('/'), path);
    let resp = client.get(&url).header("Accept", "application/json").send().await?;
    if !resp.status().is_success() { anyhow::bail!("Horizon HTTP {}", resp.status()); }
    Ok(resp.json().await?)
}

async fn get_latest_ledger(client: &reqwest::Client, base: &str) -> Result<u64> {
    let data = horizon_get(client, base, "/ledgers?order=desc&limit=1").await?;
    let seq  = data["_embedded"]["records"][0]["sequence"].as_u64().unwrap_or(0);
    Ok(seq)
}

async fn get_ledger_txs(client: &reqwest::Client, base: &str, ledger: u64) -> Result<Value> {
    horizon_get(client, base, &format!("/ledgers/{}/transactions?limit=50&include_failed=true", ledger)).await
}

async fn get_tx_ops(client: &reqwest::Client, base: &str, tx_hash: &str) -> Result<Value> {
    horizon_get(client, base, &format!("/transactions/{}/operations?limit=50", tx_hash)).await
}

fn extract_features(txs: &[Value], ops_per_tx: &[Vec<Value>]) -> [f64; 9] {
    if txs.is_empty() { return [0.5f64; 9]; }

    let mut op_types:   Vec<String> = Vec::new();
    let mut sources:    Vec<String> = Vec::new();
    let mut fees:       Vec<f64>    = Vec::new();
    let mut amounts:    Vec<f64>    = Vec::new();
    let mut assets:     Vec<String> = Vec::new();
    let mut memo_types: Vec<String> = Vec::new();
    let mut path_lens:  Vec<f64>    = Vec::new();
    let (mut trustlines, mut non_trustlines) = (0u64, 0u64);
    let (mut offers, mut non_offers) = (0u64, 0u64);

    for (tx, ops) in txs.iter().zip(ops_per_tx.iter()) {
        sources.push(tx["source_account"].as_str().unwrap_or("").to_string());
        let fee = tx["fee_charged"].as_str().and_then(|s| s.parse::<f64>().ok()).unwrap_or(0.0);
        fees.push(fee);
        memo_types.push(tx["memo_type"].as_str().unwrap_or("none").to_string());
        for op in ops {
            let otype = op["type"].as_str().unwrap_or("unknown").to_string();
            op_types.push(otype.clone());
            let amt = op["amount"].as_str().and_then(|s| s.parse::<f64>().ok()).unwrap_or(0.0);
            if amt > 0.0 { amounts.push(amt); }
            let asset_code = op["asset_code"].as_str().unwrap_or(
                op["asset_type"].as_str().unwrap_or("native")).to_string();
            assets.push(asset_code);
            if otype.contains("path") {
                path_lens.push(op["path"].as_array().map(|p| p.len()).unwrap_or(0) as f64);
            }
            if otype == "change_trust" { trustlines += 1; } else { non_trustlines += 1; }
            if otype.contains("offer") || otype.contains("liquidity") { offers += 1; } else { non_offers += 1; }
        }
    }

    [
        freq_entropy(&op_types),
        freq_entropy(&sources),
        histogram_entropy(&fees, 8),
        histogram_entropy(&amounts, 8),
        freq_entropy(&assets),
        freq_entropy(&memo_types),
        histogram_entropy(&path_lens, 4),
        ratio_entropy(trustlines, trustlines + non_trustlines),
        ratio_entropy(offers, offers + non_offers),
    ]
}

// ── Per-tx Behavioral Hash pipeline ──────────────────────────────────────────

static MAX_STROOPS: AtomicU64 = AtomicU64::new(10_000_000); // 1 XLM in stroops

fn pi_magnitude(stroops: u64) -> f64 {
    let old = MAX_STROOPS.load(Ordering::Relaxed);
    if stroops > old { MAX_STROOPS.store(stroops, Ordering::Relaxed); }
    let max = MAX_STROOPS.load(Ordering::Relaxed).max(1) as f64;
    let v   = stroops as f64;
    ((v + 1.0).log10() / (max + 1.0).log10()).clamp(0.0, 1.0)
}

fn classify_stellar_op(ops: &[Value]) -> u8 {
    for op in ops {
        match op["type"].as_str().unwrap_or("") {
            "payment" | "create_account"     => return 0,   // TRANSFER
            "manage_sell_offer"
            | "manage_buy_offer"
            | "create_passive_sell_offer"    => return 1,   // SWAP (DEX)
            "path_payment_strict_send"
            | "path_payment_strict_receive"  => return 1,   // SWAP (path payment)
            "liquidity_pool_deposit"         => return 2,   // LIQUIDITY
            "liquidity_pool_withdraw"        => return 2,   // LIQUIDITY
            "change_trust"                   => return 19,  // CLAIM (trustline)
            "set_options"                    => return 6,   // GOVERNANCE
            "claim_claimable_balance"        => return 19,  // CLAIM
            "inflation"                      => return 13,  // MINT
            _ => {}
        }
    }
    0 // TRANSFER
}

fn pi_bh_batch(txs: &[Value], ops_per_tx: &[Vec<Value>], chain_id: u64, label: &str, ledger: u64, block_hash: &str, ts: u64) -> TxBhBatch {
    let mut entries: Vec<TxBhEntry> = Vec::new();

    for (tx, ops) in txs.iter().zip(ops_per_tx.iter()) {
        let tx_hash = tx["hash"].as_str().unwrap_or("").to_string();
        if tx_hash.is_empty() { continue; }

        let sender = tx["source_account"].as_str().unwrap_or("unknown").to_string();
        let et     = classify_stellar_op(ops);

        // fee_charged is in stroops (1 XLM = 10,000,000 stroops)
        let stroops = tx["fee_charged"].as_str().and_then(|s| s.parse::<u64>().ok()).unwrap_or(0);
        // Also check first op amount as magnitude
        let amount_stroops = ops.first()
            .and_then(|o| o["amount"].as_str())
            .and_then(|s| {
                let f: f64 = s.parse().ok()?;
                Some((f * 10_000_000.0) as u64)
            }).unwrap_or(0);
        let best_value = amount_stroops.max(stroops);
        let mag = pi_magnitude(best_value);
        let eid = bh_id(&sender);
        let (sense_hex, antisense_hex) = canonical_bh(&eid, et, mag, 0, ts, chain_id, block_hash);

        entries.push(TxBhEntry {
            tx_hash, from_addr: sender, to_addr: String::new(),
            event_type: et, event_type_name: event_type_name(et).to_string(),
            entity_id: eid, magnitude_norm: mag, value_wei: best_value.to_string(),
            selector: ops.first().and_then(|o| o["type"].as_str()).unwrap_or("").to_string(),
            timestamp: ts, chain_id, chain_label: label.to_string(), block_num: ledger,
            block_hash: block_hash.to_string(), sense_hex, antisense_hex,
        });
    }

    TxBhBatch { chain_id, chain_label: label.to_string(), block_num: ledger, block_hash: block_hash.to_string(), timestamp: ts, entries }
}

#[tokio::main]
async fn main() -> Result<()> {
    tracing_subscriber::fmt().with_env_filter("info").init();

    let faiss_url = std::env::var("FAISS_SERVICE_URL").unwrap_or_else(|_| "http://127.0.0.1:8000".into());
    let poll_ms   = std::env::var("POLL_MS").ok().and_then(|s| s.parse().ok()).unwrap_or(6_000u64);
    let horizon   = std::env::var("PI_HORIZON_URL").unwrap_or_else(|_| HORIZON_URLS[0].into());
    let faiss     = FaissClient::new(&faiss_url)?;
    let mut state = IndexerState::new("pi_mvm");
    let client    = reqwest::Client::builder().timeout(Duration::from_secs(15)).build()?;

    info!("TRION Pi/Stellar Rust Indexer — chain={} poll={}ms horizon={}", CHAIN_ID, poll_ms, horizon);

    loop {
        if !faiss.is_healthy().await { sleep(Duration::from_secs(5)).await; continue; }

        let latest = match get_latest_ledger(&client, &horizon).await {
            Ok(n)  => n,
            Err(e) => { warn!("Pi/Stellar latest ledger error: {}", e); sleep(Duration::from_millis(poll_ms)).await; continue; }
        };
        let last = state.last_block();
        let from = if last == 0 { latest.saturating_sub(1) } else { last + 1 };

        for ledger_num in from..=latest {
            let txs_resp = match get_ledger_txs(&client, &horizon, ledger_num).await {
                Ok(v)  => v,
                Err(e) => { warn!("[{}] ledger {} txs error: {}", CHAIN_LBL, ledger_num, e); continue; }
            };
            let txs: Vec<Value> = txs_resp["_embedded"]["records"].as_array().cloned().unwrap_or_default();

            // Fetch ops for up to 10 txs
            let mut ops_per_tx: Vec<Vec<Value>> = Vec::new();
            for tx in txs.iter().take(10) {
                let hash = tx["hash"].as_str().unwrap_or("");
                let ops  = get_tx_ops(&client, &horizon, hash).await
                    .ok()
                    .and_then(|v| v["_embedded"]["records"].as_array().cloned())
                    .unwrap_or_default();
                ops_per_tx.push(ops);
            }
            while ops_per_tx.len() < txs.len() { ops_per_tx.push(vec![]); }

            let features  = extract_features(&txs, &ops_per_tx);
            let phi       = features.iter().sum::<f64>() / 9.0;
            let eid       = block_entity_id(CHAIN_LBL, ledger_num);
            let bh        = bh_id(&eid);
            let vector    = build_vector(&features, &format!("{}:{}", CHAIN_LBL, ledger_num));
            let ts        = SystemTime::now().duration_since(UNIX_EPOCH).unwrap_or_default().as_secs_f64();
            let ts_u64    = ts as u64;
            let block_hash = bh_id(&format!("pi_ledger:{}:{}", CHAIN_LBL, ledger_num));

            let payload = BatchPayload {
                vectors: vec![VectorEntry {
                    entity_id: eid, vector, magnitude: phi, entropy: phi, timestamp: ts,
                    bh_id: bh, block_num: ledger_num, chain_id: CHAIN_ID,
                    chain_label: CHAIN_LBL.into(), vm_type: VM_TYPE.into(),
                    funding_source: None, block_hash_hex: None, event_type: None, sense_hex: None, antisense_hex: None,
                }],
                block_num: ledger_num, block_features: features.to_vec(), block_phi: phi,
                chain_id: CHAIN_ID, chain_label: CHAIN_LBL.into(), vm_type: VM_TYPE.into(),
            };

            match faiss.add_batch(&payload).await {
                Ok(added) => {
                    let tx_batch = pi_bh_batch(&txs, &ops_per_tx, CHAIN_ID, CHAIN_LBL, ledger_num, &block_hash, ts_u64);
                    let bh_stored = faiss.add_tx_bh_batch(&tx_batch).await.unwrap_or(0);
                    info!("[{}] ledger={} φ={:.4} added={} bh_stored={}", CHAIN_LBL, ledger_num, phi, added, bh_stored);
                }
                Err(e) => warn!("[{}] FAISS failed: {}", CHAIN_LBL, e),
            }
            state.save(ledger_num).ok();
        }
        sleep(Duration::from_millis(poll_ms)).await;
    }
}
