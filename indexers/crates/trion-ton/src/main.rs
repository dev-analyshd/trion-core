/*!
 * TRION TON Behavioral Indexer — Rust
 * =====================================
 * Polls TON masterchain blocks via HTTP API and pushes 128-dim vectors
 * AND per-tx canonical BH (L0.1 ledger).
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
use tokio::time::{sleep, Duration};
use tracing::{info, warn};
use trion_common::{
    bh_id, block_entity_id, build_vector, canonical_bh, event_type_name,
    freq_entropy, histogram_entropy,
    entropy::ratio_entropy, BatchPayload, FaissClient, IndexerState, TxBhBatch, TxBhEntry, VectorEntry,
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
    if testnet { (22001, "TON_TESTNET") } else { (22000, "TON_MAINNET") }
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

    let mut op_codes:      Vec<String> = Vec::new();
    let mut sources:       Vec<String> = Vec::new();
    let mut values:        Vec<f64>    = Vec::new();
    let mut dests:         Vec<String> = Vec::new();
    let mut msg_counts:    Vec<f64>    = Vec::new();
    let mut fees:          Vec<f64>    = Vec::new();
    let (mut bounce, mut no_bounce) = (0u64, 0u64);
    let (mut success, mut failure)  = (0u64, 0u64);
    let mut workchains:    Vec<String> = Vec::new();

    for tx in txs {
        let in_msg  = &tx["in_msg"];
        let out_msgs = tx["out_msgs"].as_array().cloned().unwrap_or_default();
        if let Some(src) = in_msg["source"].as_str()      { sources.push(src.to_string()); }
        if let Some(dst) = in_msg["destination"].as_str() { dests.push(dst.to_string()); }
        let val = in_msg["value"].as_str().and_then(|s| s.parse::<f64>().ok()).unwrap_or(0.0);
        values.push(val);
        let op = in_msg["op_code"].as_str().unwrap_or("0x0").to_string();
        op_codes.push(op);
        if in_msg["bounce"].as_bool().unwrap_or(false) { bounce += 1; } else { no_bounce += 1; }
        // Track transaction outcome: Toncenter returns `transaction_id` or
        // `success`/`aborted` flags. Default to success if no flag present.
        let aborted = tx["aborted"].as_bool().unwrap_or(false)
            || tx["description"]["aborted"].as_bool().unwrap_or(false);
        if aborted { failure += 1; } else { success += 1; }
        msg_counts.push(out_msgs.len() as f64 + 1.0);
        let fee = tx["total_fees"].as_str().and_then(|s| s.parse::<f64>().ok()).unwrap_or(0.0);
        fees.push(fee);
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
        freq_entropy(&workchains),            // f8 — workchain diversity (was duplicate of f7)
        ratio_entropy(success, success + failure), // f9 — transaction success ratio
    ]
}

// ── Per-tx Behavioral Hash pipeline ──────────────────────────────────────────

/// CANONICAL_BH.md §4 — deterministic magnitude normalization:
///   human = raw / 10^9 (TON nano); M = min(1, log10(human + 1) / log10(1001))
/// The rolling session-max tracker was removed: it made the BH of a fixed
/// transaction depend on what else the process had observed (canonical
/// violation — the same tx must always produce the same BH).
fn ton_magnitude(nano: u64) -> f64 {
    let human = nano as f64 / 1e9;
    if human <= 0.0 { return 0.0; }
    ((human + 1.0).log10() / (1001.0_f64).log10()).min(1.0)
}

/// Classify TON event from op_code and message properties.
/// TON uses op codes in the first 32 bits of message body.
fn classify_ton_event(in_msg: &Value) -> u8 {
    let op = in_msg["op_code"].as_str().unwrap_or("0x0");
    // Well-known TON DeFi op codes
    match op {
        "0x7362d09c" | "0xf8a7ea5"  => 0,   // token transfer / transfer notification
        "0x595f07bc" | "0xad3029e3" => 1,   // DEX swap (TON jetton AMM ops)
        "0x47d54391" | "0x7bdd97de" => 2,   // add/remove liquidity
        // Canonical STAKE=3 (was 8 — fixed to match whitepaper L0.1 §2)
        // Note: 0x47d54391 also matched staking in old code; removed duplicate.
        "0xa7fb58f8"                 => 4,   // unstake (was 9 — canonical UNSTAKE=4)
        "0xb5de5f9e" | "0x42a0fb43" => 5,   // governance / voting (canonical GOVERNANCE=5)
        "0x00000000"                 => {
            // op_code 0 = simple transfer
            let val = in_msg["value"].as_str().and_then(|s| s.parse::<u64>().ok()).unwrap_or(0);
            if val > 0 { 0 } else { 0 } // TRANSFER
        }
        _                            => {
            // Any op_code present → likely smart contract call
            let val = in_msg["value"].as_str().and_then(|s| s.parse::<u64>().ok()).unwrap_or(0);
            if op != "0x0" && op != "0x00000000" { 1 } // SWAP (generic contract call)
            else if val > 0 { 0 } // TRANSFER
            else { 0 }
        }
    }
}

fn ton_bh_batch(txs: &[Value], chain_id: u64, label: &str, seqno: u64, block_hash: &str, ts: u64) -> TxBhBatch {
    let mut entries: Vec<TxBhEntry> = Vec::new();

    for tx in txs {
        let tx_hash = tx["transaction_id"]["hash"].as_str()
            .or_else(|| tx["hash"].as_str())
            .unwrap_or("").to_string();
        if tx_hash.is_empty() { continue; }

        let in_msg  = &tx["in_msg"];
        let sender  = in_msg["source"].as_str().unwrap_or("unknown").to_string();
        let dest    = in_msg["destination"].as_str().unwrap_or("").to_string();
        let nano    = in_msg["value"].as_str().and_then(|s| s.parse::<u64>().ok()).unwrap_or(0);
        let et      = classify_ton_event(in_msg);
        let mag     = ton_magnitude(nano);
        let eid     = bh_id(&sender);
        let (sense_hex, antisense_hex) = canonical_bh(&eid, et, mag, 0, ts, chain_id, block_hash);

        entries.push(TxBhEntry {
            tx_hash, from_addr: sender, to_addr: dest,
            event_type: et, event_type_name: event_type_name(et).to_string(),
            entity_id: eid, magnitude_norm: mag, value_wei: nano.to_string(),
            selector: in_msg["op_code"].as_str().unwrap_or("0x0").to_string(),
            timestamp: ts, chain_id, chain_label: label.to_string(), block_num: seqno,
            block_hash: block_hash.to_string(), sense_hex, antisense_hex,
        });
    }

    TxBhBatch { chain_id, chain_label: label.to_string(), block_num: seqno, block_hash: block_hash.to_string(), timestamp: ts, entries }
}

#[tokio::main]
async fn main() -> Result<()> {
    tracing_subscriber::fmt().with_env_filter("info").init();

    let faiss_url = std::env::var("FAISS_SERVICE_URL").unwrap_or_else(|_| "http://127.0.0.1:8000".into());
    let poll_ms   = std::env::var("POLL_MS").ok().and_then(|s| s.parse().ok()).unwrap_or(5_000u64);
    let (chain_id, label) = chain_info();
    let faiss     = FaissClient::new(&faiss_url)?;
    let state = IndexerState::new(&format!("ton_{}", label.to_lowercase()));
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
                let addr = tid["account"].as_str().unwrap_or("");
                let lt   = tid["lt"].as_str().unwrap_or("0");
                let hash = tid["hash"].as_str().unwrap_or("");
                if let Ok(tx) = ton_get(&client, "getTransactions",
                    &[("address", addr.into()), ("limit", "1".into()), ("lt", lt.into()), ("hash", hash.into())]
                ).await {
                    if let Some(arr) = tx.as_array() { txs.extend(arr.clone()); }
                }
            }

            let features  = extract_features(&txs);
            let phi       = features.iter().sum::<f64>() / 9.0;
            let eid       = block_entity_id(label, seqno);
            let bh        = bh_id(&eid);
            let vector    = build_vector(&features, &format!("{}:{}", label, seqno));
            // CANONICAL_BH.md §5 — block time from the first tx's utime
            // (toncenter); 0 = unknown. Never wall-clock.
            let ts_u64    = txs.first().and_then(|t| t["utime"].as_u64()).unwrap_or(0);
            let ts        = ts_u64 as f64;
            let block_hash = bh_id(&format!("ton_block:{}:{}", label, seqno));

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
                Ok(added) => {
                    let tx_batch = ton_bh_batch(&txs, chain_id, label, seqno, &block_hash, ts_u64);
                    let bh_stored = faiss.add_tx_bh_batch(&tx_batch).await.unwrap_or(0);
                    info!("[{}] seqno={} φ={:.4} added={} bh_stored={}", label, seqno, phi, added, bh_stored);
                }
                Err(e) => warn!("[{}] FAISS failed: {}", label, e),
            }
            state.save(seqno).ok();
        }
        sleep(Duration::from_millis(poll_ms)).await;
    }
}
