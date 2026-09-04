/*!
 * TRION Waves Blockchain Behavioral Indexer — Rust
 * =================================================
 * Polls public Waves node REST API for blocks and transactions.
 * Produces 128-dim vectors AND per-tx canonical BH (L0.1 ledger).
 *
 * Waves behavioral dimensions (9 Shannon entropy features):
 *   f1 — Transaction type entropy   H(transfer/massTransfer/lease/invokeScript/...)
 *   f2 — Sender entropy             H(sender frequency)
 *   f3 — Recipient entropy          H(recipient frequency)
 *   f4 — Amount entropy             H(amount bins, WAVES)
 *   f5 — Fee entropy                H(fee bins)
 *   f6 — Asset diversity            H(assetId frequency)
 *   f7 — Lease ratio entropy        H(lease vs transfer)
 *   f8 — Script invocation entropy  H(dApp function calls)
 *   f9 — Version diversity          H(tx version distribution)
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

const CHAIN_ID:  u64  = 30000;
const CHAIN_LBL: &str = "WAVES";
const VM_TYPE:   &str = "WAVES";

const WAVES_URLS: &[&str] = &[
    "https://nodes.wavesnodes.com",
    "https://wavesnode.com",
];

/// 1 WAVES = 1e8 wavy (satoshis)
const WAVES_DECIMALS: f64 = 1e8;

async fn waves_get(client: &reqwest::Client, base: &str, path: &str) -> Result<Value> {
    let url = format!("{}{}", base.trim_end_matches('/'), path);
    let resp = client.get(&url).header("Accept", "application/json").send().await?;
    if !resp.status().is_success() { anyhow::bail!("Waves HTTP {} on {}", resp.status(), path); }
    Ok(resp.json().await?)
}

async fn get_height(client: &reqwest::Client, base: &str) -> Result<u64> {
    let v = waves_get(client, base, "/blocks/height").await?;
    Ok(v.get("height").and_then(|h| h.as_u64()).unwrap_or(0))
}

async fn get_block(client: &reqwest::Client, base: &str, height: u64) -> Result<Value> {
    waves_get(client, base, &format!("/blocks/at/{}", height)).await
}

/// Canonical event-type classification for Waves transaction types.
fn classify_waves(tx: &Value) -> u8 {
    let ttype = tx.get("type").and_then(|v| v.as_u64()).unwrap_or(0);
    match ttype {
        4  => 0,   // Transfer
        11 => 0,   // MassTransfer
        8  => 3,   // Lease (locking funds) → STAKE
        9  => 4,   // LeaseCancel → UNSTAKE
        12 => 19,  // DataTransaction → CLAIM (state claim)
        13 => 6,   // SetAssetScript → GOVERNANCE
        14 => 12,  // SponsorFee → UPGRADE
        15 => 13,  // Alias → MINT (identity creation)
        16 => 12,  // Burn → UPGRADE-ish; use BURN=14
        _ => {
            // 16 is Burn in modern numbering; check explicit
            if tx.get("burnedTokens").is_some() { 14 }
            else if ttype == 16 { 14 } // Burn
            else if ttype == 17 { 0 }  // Reissue
            else if ttype == 3 { 13 }  // Issue → MINT
            else if ttype == 6 { 2 }   // Alias (legacy) → LIQUIDITY placeholder
            else if ttype == 18 || ttype == 103 || ttype == 104 { 1 } // Exchange / scripts → SWAP
            else if ttype == 22 { 2 }  // UpdateAssetInfo
            else { 0 }                 // TRANSFER fallback
        }
    }
}

fn tx_type_name(tx: &Value) -> String {
    match tx.get("type").and_then(|v| v.as_u64()).unwrap_or(0) {
        1  => "Genesis",
        2  => "Payment",
        3  => "Issue",
        4  => "Transfer",
        5  => "Reissue",
        6  => "Alias",
        7  => "MassTransferLegacy",
        8  => "Lease",
        9  => "LeaseCancel",
        10 => "CreateAlias",
        11 => "MassTransfer",
        12 => "DataTransaction",
        13 => "SetScript",
        14 => "SponsorFee",
        15 => "SetAssetScript",
        16 => "Burn",
        17 => "Exchange",
        18 => "TransferWithData",
        22 => "UpdateAssetInfo",
        100 => "InvokeScript",
        101 => "IssueSmartAsset",
        102 => "ReissueSmartAsset",
        103 => "BurnSmartAsset",
        104 => "SponsorFeeSmartAsset",
        105 => "CreateAliasSmart",
        _   => "Unknown",
    }.to_string()
}

fn tx_amount_wavy(tx: &Value) -> u64 {
    // amount in wavy (1e8)
    if let Some(a) = tx.get("amount").and_then(|v| v.as_u64()) { return a; }
    if let Some(a) = tx.get("amount").and_then(|v| v.as_i64()) { return a.max(0) as u64; }
    if let Some(transfers) = tx.get("transfers").and_then(|v| v.as_array()) {
        return transfers.iter()
            .filter_map(|t| t.get("amount").and_then(|v| v.as_u64()))
            .sum();
    }
    if let Some(total) = tx.get("totalAmount").and_then(|v| v.as_u64()) { return total; }
    0
}

fn extract_features(txs: &[Value]) -> [f64; 9] {
    if txs.is_empty() { return [0.5f64; 9]; }

    let mut ttypes:   Vec<String> = Vec::new();
    let mut senders:  Vec<String> = Vec::new();
    let mut recipients: Vec<String> = Vec::new();
    let mut amounts:  Vec<f64>    = Vec::new();
    let mut fees:     Vec<f64>    = Vec::new();
    let mut assets:   Vec<String> = Vec::new();
    let (mut leases, mut non_leases) = (0u64, 0u64);
    let mut invokes:  Vec<String> = Vec::new();
    let mut versions: Vec<String> = Vec::new();

    for tx in txs {
        let ttype = tx.get("type").and_then(|v| v.as_u64()).unwrap_or(0);
        ttypes.push(tx_type_name(tx));
        senders.push(tx.get("sender").and_then(|v| v.as_str()).unwrap_or("").to_string());
        recipients.push(tx.get("recipient").and_then(|v| v.as_str()).unwrap_or("").to_string());

        let amt = tx_amount_wavy(tx) as f64 / WAVES_DECIMALS;
        if amt > 0.0 { amounts.push(amt); }

        let fee = tx.get("fee").and_then(|v| v.as_u64()).unwrap_or(0) as f64 / WAVES_DECIMALS;
        fees.push(fee);

        let asset = tx.get("assetId").and_then(|v| v.as_str())
            .or_else(|| tx.get("asset").and_then(|v| v.as_str()))
            .unwrap_or("WAVES");
        assets.push(asset.to_string());

        if ttype == 8 || ttype == 9 { leases += 1; } else { non_leases += 1; }

        if ttype == 16 || ttype == 100 {
            let func = tx.pointer("/call/function").and_then(|v| v.as_str()).unwrap_or("default");
            invokes.push(func.to_string());
        }

        versions.push(format!("v{}", tx.get("version").and_then(|v| v.as_u64()).unwrap_or(1)));
    }

    [
        freq_entropy(&ttypes),
        freq_entropy(&senders),
        freq_entropy(&recipients),
        histogram_entropy(&amounts, 8),
        histogram_entropy(&fees, 8),
        freq_entropy(&assets),
        ratio_entropy(leases, leases + non_leases),
        freq_entropy(&invokes),
        freq_entropy(&versions),
    ]
}

// ── Per-tx Behavioral Hash pipeline ──────────────────────────────────────────

/// CANONICAL_BH.md §4 — deterministic magnitude normalization:
///   human = raw / 10^8 (WAVES wavy); M = min(1, log10(human + 1) / log10(1001))
/// The rolling session-max tracker was removed: it made the BH of a fixed
/// transaction depend on what else the process had observed (canonical
/// violation — the same tx must always produce the same BH).
fn waves_magnitude(wavy: u64) -> f64 {
    let human = wavy as f64 / 1e8;
    if human <= 0.0 { return 0.0; }
    ((human + 1.0).log10() / (1001.0_f64).log10()).min(1.0)
}

fn waves_bh_batch(txs: &[Value], height: u64, block_hash: &str, ts: u64) -> TxBhBatch {
    let mut entries: Vec<TxBhEntry> = Vec::new();

    for tx in txs {
        let id = tx.get("id").and_then(|v| v.as_str()).unwrap_or("").to_string();
        if id.is_empty() { continue; }

        let sender = tx.get("sender").and_then(|v| v.as_str()).unwrap_or("unknown").to_string();
        let dest   = tx.get("recipient").and_then(|v| v.as_str()).unwrap_or("").to_string();
        let et     = classify_waves(tx);
        let wavy   = tx_amount_wavy(tx);
        let mag    = waves_magnitude(wavy);
        let eid    = bh_id(&sender);
        let (sense_hex, antisense_hex) = canonical_bh(&eid, et, mag, 0, ts, CHAIN_ID, block_hash);

        entries.push(TxBhEntry {
            tx_hash: id,
            from_addr: sender,
            to_addr: dest,
            event_type: et,
            event_type_name: event_type_name(et).to_string(),
            entity_id: eid,
            magnitude_norm: mag,
            value_wei: wavy.to_string(),
            selector: tx_type_name(tx),
            timestamp: ts,
            chain_id: CHAIN_ID,
            chain_label: CHAIN_LBL.to_string(),
            block_num: height,
            block_hash: block_hash.to_string(),
            sense_hex,
            antisense_hex,
        });
    }

    TxBhBatch {
        chain_id: CHAIN_ID,
        chain_label: CHAIN_LBL.to_string(),
        block_num: height,
        block_hash: block_hash.to_string(),
        timestamp: ts,
        entries,
    }
}

#[tokio::main]
async fn main() -> Result<()> {
    tracing_subscriber::fmt().with_env_filter("info").init();

    let faiss_url = std::env::var("FAISS_SERVICE_URL").unwrap_or_else(|_| "http://127.0.0.1:8000".into());
    let poll_ms   = std::env::var("POLL_MS").ok().and_then(|s| s.parse().ok()).unwrap_or(15_000u64);
    let mut base      = std::env::var("WAVES_RPC_URL").unwrap_or_else(|_| WAVES_URLS[0].into());
    let mut rpc_idx = 0usize;  // RPC failover rotation index
    let faiss     = FaissClient::new(&faiss_url)?;
    let state = IndexerState::new("waves");
    let client    = reqwest::Client::builder().timeout(Duration::from_secs(15)).build()?;

    info!("TRION Waves Rust Indexer — chain={} poll={}ms node={}", CHAIN_ID, poll_ms, base);

    loop {
        if !faiss.is_healthy().await { sleep(Duration::from_secs(5)).await; continue; }

        let latest = match get_height(&client, &base).await {
            Ok(n) => n,
            Err(e) => { warn!("Waves height error: {} — rotating RPC", e); { rpc_idx += 1; base = WAVES_URLS[rpc_idx % WAVES_URLS.len()].into(); } sleep(Duration::from_millis(poll_ms)).await; continue; }
        };
        let last = state.last_block();
        let from = if last == 0 { latest.saturating_sub(1) } else { last + 1 };

        for height in from..=latest {
            let block = match get_block(&client, &base, height).await {
                Ok(v) => v,
                Err(e) => { warn!("[{}] block {} error: {}", CHAIN_LBL, height, e); continue; }
            };

            let txs: Vec<Value> = block.get("transactions").and_then(|v| v.as_array()).cloned().unwrap_or_default();
            let signature = block.get("signature").and_then(|v| v.as_str()).unwrap_or("");
            // CANONICAL_BH.md §5 — Waves block timestamp (ms → s); 0 = unknown, never wall-clock.
            let ts = block.get("timestamp").and_then(|v| v.as_u64()).map(|t| t / 1000).unwrap_or(0);

            if txs.is_empty() { state.save(height).ok(); continue; }

            let features = extract_features(&txs);
            let phi      = features.iter().sum::<f64>() / 9.0;
            let eid      = block_entity_id(CHAIN_LBL, height);
            let bh       = bh_id(&eid);
            let vector   = build_vector(&features, &format!("{}:{}", CHAIN_LBL, height));
            let block_hash_hex = if signature.is_empty() {
                bh_id(&format!("waves_block:{}:{}", CHAIN_LBL, height))
            } else {
                bh_id(signature)
            };

            let payload = BatchPayload {
                vectors: vec![VectorEntry {
                    entity_id: eid,
                    vector,
                    magnitude: phi,
                    entropy: phi,
                    timestamp: ts as f64,
                    bh_id: bh,
                    block_num: height,
                    chain_id: CHAIN_ID,
                    chain_label: CHAIN_LBL.into(),
                    vm_type: VM_TYPE.into(),
                    funding_source: None,
                    block_hash_hex: Some(block_hash_hex.clone()),
                    event_type: Some(classify_waves(&txs[0])),
                    sense_hex: None,
                    antisense_hex: None,
                }],
                block_num: height,
                block_features: features.to_vec(),
                block_phi: phi,
                chain_id: CHAIN_ID,
                chain_label: CHAIN_LBL.into(),
                vm_type: VM_TYPE.into(),
            };

            match faiss.add_batch(&payload).await {
                Ok(added) => {
                    let tx_batch = waves_bh_batch(&txs, height, &block_hash_hex, ts);
                    let bh_stored = faiss.add_tx_bh_batch(&tx_batch).await.unwrap_or(0);
                    info!("[{}] height={} txs={} φ={:.4} added={} bh_stored={}",
                          CHAIN_LBL, height, txs.len(), phi, added, bh_stored);
                }
                Err(e) => warn!("[{}] FAISS failed: {}", CHAIN_LBL, e),
            }
            state.save(height).ok();
        }
        sleep(Duration::from_millis(poll_ms)).await;
    }
}
