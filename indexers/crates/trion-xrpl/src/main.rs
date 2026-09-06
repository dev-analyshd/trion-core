/*!
 * TRION XRPL (XRP Ledger) Behavioral Indexer — Rust
 * =================================================
 * Polls public rippled JSON-RPC for ledger transactions.
 * Produces 128-dim vectors AND per-tx canonical BH (L0.1 ledger).
 *
 * XRPL behavioral dimensions (9 Shannon entropy features):
 *   f1 — Transaction type entropy   H(Payment/TrustSet/OfferCreate/...)
 *   f2 — Account entropy            H(Account frequency)
 *   f3 — Destination entropy        H(Destination frequency)
 *   f4 — Amount entropy             H(amount bins, drops)
 *   f5 — Fee entropy                H(Fee bins, drops)
 *   f6 — Flags/quality entropy      H(SetFlag/ClearFlag distribution)
 *   f7 — Issuer diversity           H(issuer frequency)
 *   f8 — Offer side ratio           H(buy taker_gets XFLM vs sell)
 *   f9 — Result ratio entropy       H(tesSUCCESS vs failure)
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

const CHAIN_ID:  u64  = 31000;
const CHAIN_LBL: &str = "XRPL";
const VM_TYPE:   &str = "XRPL";

const RIPPLED_URLS: &[&str] = &[
    "https://s1.ripple.com:51234",
    "https://s2.ripple.com:51234",
    "https://xrplcluster.com",
];

/// drops: 1 XRP = 1,000,000 drops
const DROPS_PER_XRP: f64 = 1_000_000.0;

async fn rpc(client: &reqwest::Client, base: &str, method: &str, params: Value) -> Result<Value> {
    let url = format!("{}/", base.trim_end_matches('/'));
    let body = serde_json::json!({ "method": method, "params": [params] });
    let resp = client.post(&url).json(&body).send().await?;
    if !resp.status().is_success() {
        anyhow::bail!("rippled HTTP {}", resp.status());
    }
    let v: Value = resp.json().await?;
    let result = v.get("result").cloned().unwrap_or(Value::Null);
    let status = result.get("status").and_then(|s| s.as_str()).unwrap_or("");
    if status == "error" {
        let err = result.get("error").and_then(|e| e.as_str()).unwrap_or("unknown");
        anyhow::bail!("rippled error: {}", err);
    }
    Ok(result)
}

async fn get_latest_ledger(client: &reqwest::Client, base: &str) -> Result<u64> {
    let r = rpc(client, base, "ledger_current", serde_json::json!({})).await?;
    Ok(r.get("ledger_current_index").and_then(|v| v.as_u64()).unwrap_or(0))
}

async fn get_ledger(client: &reqwest::Client, base: &str, index: u64) -> Result<Value> {
    let r = rpc(client, base, "ledger", serde_json::json!({
        "ledger_index": index.to_string(),
        "transactions": true,
        "expand": true,
        "binary": false,
    })).await?;
    Ok(r.get("ledger").cloned().unwrap_or(Value::Null))
}

/// Canonical event-type classification for XRPL transaction types.
fn classify_xrpl(tx: &Value) -> u8 {
    let ttype = tx.get("TransactionType").and_then(|v| v.as_str()).unwrap_or("");
    match ttype {
        "Payment"                 => 0,  // TRANSFER
        "OfferCreate"             => 1,  // SWAP (DEX order)
        "OfferCancel"             => 1,  // SWAP (order cancel)
        "TrustSet"                => 19, // CLAIM (trustline)
        "AccountSet"              => 6,  // GOVERNANCE (account options)
        "SetRegularKey"           => 12, // UPGRADE (key rotation)
        "SignerListSet"           => 6,  // GOVERNANCE (multisig)
        "PaymentChannelCreate"    => 10, // BRIDGE (channel)
        "PaymentChannelFund"      => 10, // BRIDGE
        "PaymentChannelClaim"     => 19, // CLAIM
        "EscrowCreate"            => 3,  // STAKE (lock)
        "EscrowFinish"            => 4,  // UNSTAKE (release)
        "EscrowCancel"            => 4,  // UNSTAKE
        "NFTokenMint"             => 13, // MINT
        "NFTokenBurn"             => 14, // BURN
        "NFTokenAcceptOffer"      => 1,  // SWAP
        "NFTokenCreateOffer"      => 1,  // SWAP
        "CheckCreate"             => 7,  // BORROW (deferred)
        "CheckCash"               => 8,  // REPAY
        "CheckCancel"             => 4,  // UNSTAKE
        "DepositPreauth"          => 6,  // GOVERNANCE
        "AMMBid" | "AMMVote"      => 2,  // LIQUIDITY (AMM)
        "AMMCreate"               => 2,  // LIQUIDITY
        "AMMDeposit"              => 2,  // LIQUIDITY
        "AMMWithdraw"             => 2,  // LIQUIDITY
        "EnableAmendment"         => 6,  // GOVERNANCE
        "TicketCreate"            => 11, // DEPLOY
        "AccountDelete"           => 14, // BURN
        _                         => 0,  // TRANSFER fallback
    }
}

fn tx_amount_drops(tx: &Value) -> u64 {
    // Payment: Amount may be a string (XRP drops) or object (token)
    match tx.get("Amount") {
        Some(Value::String(s)) => s.parse::<u64>().unwrap_or(0),
        Some(Value::Object(o)) => {
            // token amount — convert value string to raw units
            o.get("value").and_then(|v| v.as_str())
                .and_then(|s| s.parse::<f64>().ok())
                .map(|f| (f * DROPS_PER_XRP) as u64)
                .unwrap_or(0)
        }
        _ => 0,
    }
}

fn extract_features(txs: &[Value]) -> [f64; 9] {
    if txs.is_empty() { return [0.5f64; 9]; }

    let mut ttypes:  Vec<String> = Vec::new();
    let mut accounts: Vec<String> = Vec::new();
    let mut dests:   Vec<String> = Vec::new();
    let mut amounts: Vec<f64>    = Vec::new();
    let mut fees:    Vec<f64>    = Vec::new();
    let mut flags:   Vec<String> = Vec::new();
    let mut issuers: Vec<String> = Vec::new();
    let (mut buy_offers, mut sell_offers) = (0u64, 0u64);
    let (mut success, mut failure) = (0u64, 0u64);

    for tx in txs {
        let ttype = tx.get("TransactionType").and_then(|v| v.as_str()).unwrap_or("Unknown").to_string();
        ttypes.push(ttype.clone());
        accounts.push(tx.get("Account").and_then(|v| v.as_str()).unwrap_or("").to_string());
        dests.push(tx.get("Destination").and_then(|v| v.as_str()).unwrap_or("").to_string());

        let amt = tx_amount_drops(tx) as f64 / DROPS_PER_XRP;
        if amt > 0.0 { amounts.push(amt); }

        let fee = tx.get("Fee").and_then(|v| v.as_str()).and_then(|s| s.parse::<f64>().ok()).unwrap_or(0.0);
        fees.push(fee / DROPS_PER_XRP);

        // flags bucket
        let has_set = tx.get("SetFlag").is_some();
        let has_clear = tx.get("ClearFlag").is_some();
        flags.push(if has_set { "set".into() } else if has_clear { "clear".into() } else { "none".into() });

        // issuer diversity from token paths / trustset
        if let Some(Value::Object(o)) = tx.get("Amount") {
            if let Some(iss) = o.get("issuer").and_then(|v| v.as_str()) {
                issuers.push(iss.to_string());
            }
        }
        if let Some(iss) = tx.get("Issuer").and_then(|v| v.as_str()) {
            issuers.push(iss.to_string());
        }

        // offer side: TakerGets=XRP → sell offer; TakerPays=XRP → buy offer
        if ttype == "OfferCreate" {
            let gets_xrp = matches!(tx.get("TakerGets"), Some(Value::String(_)));
            if gets_xrp { sell_offers += 1; } else { buy_offers += 1; }
        }

        // result (present when ledger expanded with metadata)
        match tx.get("meta").and_then(|m| m.get("TransactionResult")).and_then(|r| r.as_str()) {
            Some("tesSUCCESS") | Some("terSUCCESS") => success += 1,
            Some(_) => failure += 1,
            None => success += 1, // assume success when no metadata
        }
    }

    [
        freq_entropy(&ttypes),
        freq_entropy(&accounts),
        freq_entropy(&dests),
        histogram_entropy(&amounts, 8),
        histogram_entropy(&fees, 8),
        freq_entropy(&flags),
        freq_entropy(&issuers),
        ratio_entropy(buy_offers, buy_offers + sell_offers),
        ratio_entropy(success, success + failure),
    ]
}

// ── Per-tx Behavioral Hash pipeline ──────────────────────────────────────────

/// CANONICAL_BH.md §4 — deterministic magnitude normalization:
///   human = raw / 10^6 (XRP drops); M = min(1, log10(human + 1) / log10(1001))
/// The rolling session-max tracker was removed: it made the BH of a fixed
/// transaction depend on what else the process had observed (canonical
/// violation — the same tx must always produce the same BH).
fn xrpl_magnitude(drops: u64) -> f64 {
    let human = drops as f64 / 1e6;
    if human <= 0.0 { return 0.0; }
    ((human + 1.0).log10() / (1001.0_f64).log10()).min(1.0)
}

fn xrpl_bh_batch(txs: &[Value], ledger: u64, ledger_hash: &str, ts: u64) -> TxBhBatch {
    let mut entries: Vec<TxBhEntry> = Vec::new();

    for tx in txs {
        let hash = tx.get("hash").and_then(|v| v.as_str()).unwrap_or("").to_string();
        if hash.is_empty() { continue; }

        let sender = tx.get("Account").and_then(|v| v.as_str()).unwrap_or("unknown").to_string();
        let dest   = tx.get("Destination").and_then(|v| v.as_str()).unwrap_or("").to_string();
        let et     = classify_xrpl(tx);
        let drops  = tx_amount_drops(tx);
        let mag    = xrpl_magnitude(drops);
        let eid    = bh_id(&sender);
        let (sense_hex, antisense_hex) = canonical_bh(&eid, et, mag, 0, ts, CHAIN_ID, ledger_hash);

        entries.push(TxBhEntry {
            tx_hash: hash,
            from_addr: sender,
            to_addr: dest,
            event_type: et,
            event_type_name: event_type_name(et).to_string(),
            entity_id: eid,
            magnitude_norm: mag,
            value_wei: drops.to_string(),
            selector: tx.get("TransactionType").and_then(|v| v.as_str()).unwrap_or("").to_string(),
            timestamp: ts,
            chain_id: CHAIN_ID,
            chain_label: CHAIN_LBL.to_string(),
            block_num: ledger,
            block_hash: ledger_hash.to_string(),
            sense_hex,
            antisense_hex,
        });
    }

    TxBhBatch {
        chain_id: CHAIN_ID,
        chain_label: CHAIN_LBL.to_string(),
        block_num: ledger,
        block_hash: ledger_hash.to_string(),
        timestamp: ts,
        entries,
    }
}

#[tokio::main]
async fn main() -> Result<()> {
    tracing_subscriber::fmt().with_env_filter("info").init();

    let faiss_url = std::env::var("FAISS_SERVICE_URL").unwrap_or_else(|_| "http://127.0.0.1:8000".into());
    let poll_ms   = std::env::var("POLL_MS").ok().and_then(|s| s.parse().ok()).unwrap_or(6_000u64);
    let mut rippled   = std::env::var("XRPL_RPC_URL").unwrap_or_else(|_| RIPPLED_URLS[0].into());
    let mut rpc_idx = 0usize;  // RPC failover rotation index
    let faiss     = FaissClient::new(&faiss_url)?;
    let state = IndexerState::new("xrpl");
    let client    = reqwest::Client::builder()
        .timeout(Duration::from_secs(15))
        .danger_accept_invalid_certs(false)
        .build()?;

    info!("TRION XRPL Rust Indexer — chain={} poll={}ms rippled={}", CHAIN_ID, poll_ms, rippled);

    loop {
        if !faiss.is_healthy().await { sleep(Duration::from_secs(5)).await; continue; }

        let latest = match get_latest_ledger(&client, &rippled).await {
            Ok(n) => n,
            Err(e) => { warn!("XRPL latest ledger error: {} — rotating RPC", e); { rpc_idx += 1; rippled = RIPPLED_URLS[rpc_idx % RIPPLED_URLS.len()].into(); } sleep(Duration::from_millis(poll_ms)).await; continue; }
        };
        let last = state.last_block();
        let from = if last == 0 { latest.saturating_sub(1) } else { last + 1 };

        for ledger_num in from..=latest {
            let ledger = match get_ledger(&client, &rippled, ledger_num).await {
                Ok(v) if !v.is_null() => v,
                Ok(_) => { warn!("[{}] ledger {} not found", CHAIN_LBL, ledger_num); continue; }
                Err(e) => { warn!("[{}] ledger {} error: {}", CHAIN_LBL, ledger_num, e); continue; }
            };

            // rippled exposes the ledger hash both at result.ledger_hash and
            // as ledger.hash (the field the Python fetcher reads) — accept either.
            let ledger_hash = ledger.get("hash")
                .or_else(|| ledger.get("ledger_hash"))
                .and_then(|v| v.as_str())
                .unwrap_or("")
                .to_string();
            let close_time  = ledger.get("close_time").and_then(|v| v.as_u64()).unwrap_or(0);
            // CANONICAL_BH.md §5 — XRPL ledger close_time (+946684800 epoch shift);
            // 0 = unknown, never wall-clock.
            let ts = if close_time > 0 { close_time + 946684800 } else { 0 };

            let txs: Vec<Value> = ledger.get("transactions")
                .and_then(|v| v.as_array())
                .cloned()
                .unwrap_or_default();
            if txs.is_empty() {
                state.save(ledger_num).ok();
                continue;
            }

            let features = extract_features(&txs);
            let phi      = features.iter().sum::<f64>() / 9.0;
            let eid      = block_entity_id(CHAIN_LBL, ledger_num);
            let bh       = bh_id(&eid);
            let vector   = build_vector(&features, &format!("{}:{}", CHAIN_LBL, ledger_num));
            let ts_f     = ts as f64;
            // SEC-05 — pass the REAL ledger hash verbatim: bh_id() here was a
            // silent SHA3 substitution (hash-of-hash) that canonical BH §9
            // explicitly forbids. Genuinely-missing → honest zero, never a
            // fabricated synthetic id.
            let block_hash_hex = if ledger_hash.is_empty() {
                warn!("[{}] ledger {}: no ledger hash from rippled — zero block hash", CHAIN_LBL, ledger_num);
                "0x0".to_string()
            } else {
                ledger_hash.clone()
            };

            let payload = BatchPayload {
                vectors: vec![VectorEntry {
                    entity_id: eid,
                    vector,
                    magnitude: phi,
                    entropy: phi,
                    timestamp: ts_f,
                    bh_id: bh,
                    block_num: ledger_num,
                    chain_id: CHAIN_ID,
                    chain_label: CHAIN_LBL.into(),
                    vm_type: VM_TYPE.into(),
                    funding_source: None,
                    block_hash_hex: Some(block_hash_hex.clone()),
                    event_type: Some(classify_xrpl(&txs[0])),
                    sense_hex: None,
                    antisense_hex: None,
                }],
                block_num: ledger_num,
                block_features: features.to_vec(),
                block_phi: phi,
                chain_id: CHAIN_ID,
                chain_label: CHAIN_LBL.into(),
                vm_type: VM_TYPE.into(),
            };

            match faiss.add_batch(&payload).await {
                Ok(added) => {
                    let tx_batch = xrpl_bh_batch(&txs, ledger_num, &block_hash_hex, ts);
                    let bh_stored = faiss.add_tx_bh_batch(&tx_batch).await.unwrap_or(0);
                    info!("[{}] ledger={} txs={} φ={:.4} added={} bh_stored={}",
                          CHAIN_LBL, ledger_num, txs.len(), phi, added, bh_stored);
                }
                Err(e) => warn!("[{}] FAISS failed: {}", CHAIN_LBL, e),
            }
            state.save(ledger_num).ok();
        }
        sleep(Duration::from_millis(poll_ms)).await;
    }
}
