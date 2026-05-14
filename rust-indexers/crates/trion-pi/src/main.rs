/*!
 * TRION Pi Network / Stellar (MVM) Behavioral Indexer — Rust
 * ===========================================================
 * Polls Horizon REST API for ledger transactions.
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
use std::time::{SystemTime, UNIX_EPOCH};
use tokio::time::{sleep, Duration};
use tracing::{info, warn};
use trion_common::{
    bh_id, block_entity_id, build_vector, freq_entropy, histogram_entropy,
    entropy::ratio_entropy, BatchPayload, FaissClient, IndexerState, VectorEntry,
};

const CHAIN_ID:  u64  = 7001;
const CHAIN_LBL: &str = "PI_MVM";
const VM_TYPE:   &str = "MVM";

const HORIZON_URLS: &[&str] = &[
    "https://horizon.stellar.org",
    "https://horizon-testnet.stellar.org",
];

async fn horizon_get(client: &reqwest::Client, base: &str, path: &str) -> Result<Value> {
    let url = format!("{}{}", base.trim_end_matches('/'), path);
    let resp = client.get(&url).header("Accept", "application/json").send().await?;
    if !resp.status().is_success() { anyhow::bail!("Horizon HTTP {}", resp.status()); }
    Ok(resp.json().await?)
}

async fn get_latest_ledger(client: &reqwest::Client, base: &str) -> Result<u64> {
    let data = horizon_get(client, base, "/ledgers?order=desc&limit=1").await?;
    let seq = data["_embedded"]["records"][0]["sequence"].as_u64().unwrap_or(0);
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

    let mut op_types:    Vec<String> = Vec::new();
    let mut sources:     Vec<String> = Vec::new();
    let mut fees:        Vec<f64>    = Vec::new();
    let mut amounts:     Vec<f64>    = Vec::new();
    let mut assets:      Vec<String> = Vec::new();
    let mut memo_types:  Vec<String> = Vec::new();
    let mut path_lens:   Vec<f64>    = Vec::new();
    let (mut trustlines, mut non_trustlines) = (0u64, 0u64);
    let (mut offers, mut non_offers) = (0u64, 0u64);

    for (tx, ops) in txs.iter().zip(ops_per_tx.iter()) {
        sources.push(tx["source_account"].as_str().unwrap_or("").to_string());
        let fee = tx["fee_charged"].as_str().and_then(|s| s.parse::<f64>().ok()).unwrap_or(0.0);
        fees.push(fee);
        let memo = tx["memo_type"].as_str().unwrap_or("none").to_string();
        memo_types.push(memo);

        for op in ops {
            let otype = op["type"].as_str().unwrap_or("unknown").to_string();
            op_types.push(otype.clone());

            // Amount
            let amt = op["amount"].as_str().and_then(|s| s.parse::<f64>().ok()).unwrap_or(0.0);
            if amt > 0.0 { amounts.push(amt); }

            // Asset
            let asset_code = op["asset_code"].as_str().unwrap_or(
                op["asset_type"].as_str().unwrap_or("native")
            ).to_string();
            assets.push(asset_code);

            // Path payment depth
            if otype.contains("path") {
                let path_len = op["path"].as_array().map(|p| p.len()).unwrap_or(0) as f64;
                path_lens.push(path_len);
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

#[tokio::main]
async fn main() -> Result<()> {
    tracing_subscriber::fmt().with_env_filter("info").init();

    let faiss_url  = std::env::var("FAISS_SERVICE_URL").unwrap_or_else(|_| "http://127.0.0.1:8000".into());
    let poll_ms    = std::env::var("POLL_MS").ok().and_then(|s| s.parse().ok()).unwrap_or(6_000u64);
    let horizon    = std::env::var("PI_HORIZON_URL").unwrap_or_else(|_| HORIZON_URLS[0].into());
    let faiss      = FaissClient::new(&faiss_url)?;
    let mut state  = IndexerState::new("pi_mvm");
    let client     = reqwest::Client::builder().timeout(Duration::from_secs(15)).build()?;

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
                let ops = get_tx_ops(&client, &horizon, hash).await
                    .ok()
                    .and_then(|v| v["_embedded"]["records"].as_array().cloned())
                    .unwrap_or_default();
                ops_per_tx.push(ops);
            }
            // Pad remaining with empty
            while ops_per_tx.len() < txs.len() { ops_per_tx.push(vec![]); }

            let features = extract_features(&txs, &ops_per_tx);
            let phi      = features.iter().sum::<f64>() / 9.0;
            let eid      = block_entity_id(CHAIN_LBL, ledger_num);
            let bh       = bh_id(&eid);
            let vector   = build_vector(&features, &format!("{}:{}", CHAIN_LBL, ledger_num));
            let ts       = SystemTime::now().duration_since(UNIX_EPOCH).unwrap_or_default().as_secs_f64();

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
                Ok(added) => info!("[{}] ledger={} φ={:.4} added={}", CHAIN_LBL, ledger_num, phi, added),
                Err(e)    => warn!("[{}] FAISS failed: {}", CHAIN_LBL, e),
            }
            state.save(ledger_num).ok();
        }
        sleep(Duration::from_millis(poll_ms)).await;
    }
}
