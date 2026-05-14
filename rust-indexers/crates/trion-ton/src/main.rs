/*!
 * TRION TON Behavioral Indexer — Rust
 * =====================================
 * Polls TON masterchain blocks via HTTP API and pushes 128-dim vectors.
 *
 * TON behavioral dimensions (9 Shannon entropy features):
 *   f1 — Op-code diversity     H(op_code distribution)
 *   f2 — Address entropy       H(source_address frequency)
 *   f3 — Value transfer entropy H(nanoTON value bins)
 *   f4 — Destination entropy   H(destination_address frequency)
 *   f5 — Message count entropy H(msg_count_per_tx bins)
 *   f6 — Gas fee entropy       H(total_fee bins)
 *   f7 — Bounce flag entropy   H(bounce/non-bounce ratio)
 *   f8 — Account status entropy H(account_state_changes)
 *   f9 — Workchain entropy     H(workchain_id distribution)
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

fn base_url() -> String {
    let testnet = std::env::var("TON_TESTNET").as_deref() == Ok("true");
    if testnet {
        std::env::var("TON_API_URL").unwrap_or_else(|_| "https://testnet.toncenter.com/api/v2".into())
    } else {
        std::env::var("TON_API_URL").unwrap_or_else(|_| "https://toncenter.com/api/v2".into())
    }
}

fn chain_info() -> (u64, &'static str) {
    let testnet = std::env::var("TON_TESTNET").as_deref() == Ok("true");
    if testnet { (1101, "TON_TESTNET") } else { (1100, "TON_MAINNET") }
}

async fn ton_get(client: &reqwest::Client, method: &str, params: &[(&str, String)]) -> Result<Value> {
    let api_key = std::env::var("TON_API_KEY").unwrap_or_default();
    let base    = base_url();
    let mut url = reqwest::Url::parse(&format!("{}/{}", base, method))?;
    for (k, v) in params { url.query_pairs_mut().append_pair(k, v); }
    let mut req = client.get(url);
    if !api_key.is_empty() { req = req.header("X-API-Key", &api_key); }
    let resp: Value = req.send().await?.json().await?;
    if resp["ok"].as_bool() != Some(true) {
        anyhow::bail!("TON API error: {}", resp["error"].as_str().unwrap_or("unknown"));
    }
    Ok(resp["result"].clone())
}

fn extract_features(txs: &[Value]) -> [f64; 9] {
    if txs.is_empty() { return [0.5f64; 9]; }

    let mut op_codes:     Vec<String> = Vec::new();
    let mut sources:      Vec<String> = Vec::new();
    let mut values:       Vec<f64>    = Vec::new();
    let mut dests:        Vec<String> = Vec::new();
    let mut msg_counts:   Vec<f64>    = Vec::new();
    let mut fees:         Vec<f64>    = Vec::new();
    let (mut bounce, mut no_bounce) = (0u64, 0u64);
    let mut workchains:   Vec<String> = Vec::new();

    for tx in txs {
        let in_msg = &tx["in_msg"];
        let out_msgs = tx["out_msgs"].as_array().cloned().unwrap_or_default();

        if let Some(src) = in_msg["source"].as_str() { sources.push(src.to_string()); }
        if let Some(dst) = in_msg["destination"].as_str() { dests.push(dst.to_string()); }

        let val = in_msg["value"].as_str().and_then(|s| s.parse::<f64>().ok()).unwrap_or(0.0);
        values.push(val);

        let op = in_msg["op_code"].as_str().unwrap_or("0x0").to_string();
        op_codes.push(op);

        if in_msg["bounce"].as_bool().unwrap_or(false) { bounce += 1; } else { no_bounce += 1; }

        msg_counts.push(out_msgs.len() as f64 + 1.0);

        let fee = tx["total_fees"].as_str().and_then(|s| s.parse::<f64>().ok()).unwrap_or(0.0);
        fees.push(fee);

        // workchain from address format
        let wc = if sources.last().map(|s| s.starts_with('-')).unwrap_or(false) { "-1" } else { "0" };
        workchains.push(wc.to_string());
    }

    [
        freq_entropy(&op_codes),
        freq_entropy(&sources),
        histogram_entropy(&values, 8),
        freq_entropy(&dests),
        histogram_entropy(&msg_counts, 8),
        histogram_entropy(&fees, 8),
        ratio_entropy(bounce, bounce + no_bounce),
        ratio_entropy(bounce, bounce + no_bounce), // proxy for account state entropy
        freq_entropy(&workchains),
    ]
}

#[tokio::main]
async fn main() -> Result<()> {
    tracing_subscriber::fmt().with_env_filter("info").init();

    let faiss_url = std::env::var("FAISS_SERVICE_URL").unwrap_or_else(|_| "http://127.0.0.1:8000".into());
    let poll_ms   = std::env::var("POLL_MS").ok().and_then(|s| s.parse().ok()).unwrap_or(5_000u64);
    let (chain_id, label) = chain_info();
    let faiss     = FaissClient::new(&faiss_url)?;
    let mut state = IndexerState::new(&format!("ton_{}", label.to_lowercase()));
    let client    = reqwest::Client::builder().timeout(Duration::from_secs(10)).build()?;

    info!("TRION TON Rust Indexer — chain={} label={} poll={}ms", chain_id, label, poll_ms);

    loop {
        if !faiss.is_healthy().await { sleep(Duration::from_secs(5)).await; continue; }

        let master = match ton_get(&client, "getMasterchainInfo", &[]).await {
            Ok(v)  => v,
            Err(e) => { warn!("TON getMasterchainInfo: {}", e); sleep(Duration::from_millis(poll_ms)).await; continue; }
        };
        let latest = master["last"]["seqno"].as_u64().unwrap_or(0);
        let last   = state.last_block();
        let from   = if last == 0 { latest.saturating_sub(1) } else { last + 1 };

        for seqno in from..=latest {
            let txs_resp = match ton_get(&client, "getBlockTransactions",
                &[("workchain", "-1".into()), ("shard", "8000000000000000".into()), ("seqno", seqno.to_string()), ("count", "100".into())]
            ).await {
                Ok(v)  => v,
                Err(e) => { warn!("[{}] seqno {} txs error: {}", label, seqno, e); continue; }
            };

            let tx_ids = txs_resp["transactions"].as_array().cloned().unwrap_or_default();
            let mut txs: Vec<Value> = Vec::new();
            for tid in &tx_ids[..tx_ids.len().min(20)] {
                let addr  = tid["account"].as_str().unwrap_or("");
                let lt    = tid["lt"].as_str().unwrap_or("0");
                let hash  = tid["hash"].as_str().unwrap_or("");
                if let Ok(tx) = ton_get(&client, "getTransactions",
                    &[("address", addr.into()), ("limit", "1".into()), ("lt", lt.into()), ("hash", hash.into())]
                ).await {
                    if let Some(arr) = tx.as_array() { txs.extend(arr.clone()); }
                }
            }

            let features = extract_features(&txs);
            let phi      = features.iter().sum::<f64>() / 9.0;
            let eid      = block_entity_id(label, seqno);
            let bh       = bh_id(&eid);
            let vector   = build_vector(&features, &format!("{}:{}", label, seqno));
            let ts       = SystemTime::now().duration_since(UNIX_EPOCH).unwrap_or_default().as_secs_f64();

            let payload = BatchPayload {
                vectors: vec![VectorEntry {
                    entity_id: eid, vector, magnitude: phi, entropy: phi, timestamp: ts,
                    bh_id: bh, block_num: seqno, chain_id, chain_label: label.into(), vm_type: "TON".into(),
                    funding_source: None, block_hash_hex: None, event_type: None, sense_hex: None, antisense_hex: None,
                }],
                block_num: seqno, block_features: features.to_vec(), block_phi: phi,
                chain_id, chain_label: label.into(), vm_type: "TON".into(),
            };

            match faiss.add_batch(&payload).await {
                Ok(added) => info!("[{}] seqno={} φ={:.4} added={}", label, seqno, phi, added),
                Err(e)    => warn!("[{}] FAISS failed: {}", label, e),
            }
            state.save(seqno).ok();
        }
        sleep(Duration::from_millis(poll_ms)).await;
    }
}
