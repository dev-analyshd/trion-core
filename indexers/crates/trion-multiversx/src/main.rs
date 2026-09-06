/*!
 * TRION MultiversX Behavioral Indexer — Rust
 * ===========================================
 * Polls public MultiversX API (proxy + indexer gateway) for blocks/rounds
 * and transactions across shards.
 * Produces 128-dim vectors AND per-tx canonical BH (L0.1 ledger).
 *
 * MultiversX behavioral dimensions (9 Shannon entropy features):
 *   f1 — Shard distribution entropy   H(shard 0/1/2/metachain)
 *   f2 — Sender entropy               H(sender bech32 frequency)
 *   f3 — Receiver entropy             H(receiver frequency)
 *   f4 — Value entropy                H(value bins, eGLD)
 *   f5 — Gas-limit entropy            H(gasLimit bins)
 *   f6 — Gas-price entropy            H(gasPrice bins)
 *   f7 — Data presence entropy        H(data empty vs populated)
 *   f8 — Status ratio entropy         H(success vs failed)
 *   f9 — Function diversity           H(sc function signatures)
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

const CHAIN_ID:  u64  = 32000;
const CHAIN_LBL: &str = "MULTIVERSX";
const VM_TYPE:   &str = "MULTIVERSX";

const MX_URLS: &[&str] = &[
    "https://api.multiversx.com",
    "https://gateway.multiversx.com",
    "https://api.multiversx.eu",
];

/// 1 eGLD = 1e18 wei-denominated
const EGLD_DECIMALS: f64 = 1e18;

async fn mx_get(client: &reqwest::Client, base: &str, path: &str) -> Result<Value> {
    let url = format!("{}{}", base.trim_end_matches('/'), path);
    let resp = client.get(&url).header("Accept", "application/json").send().await?;
    if !resp.status().is_success() { anyhow::bail!("MX HTTP {} on {}", resp.status(), path); }
    Ok(resp.json().await?)
}

/// Query txs by shard (kept for per-shard backfill — hyperblock covers live indexing).
#[allow(dead_code)]
async fn get_shard_txs(client: &reqwest::Client, base: &str, nonce: u64, shard: u64) -> Result<Vec<Value>> {
    // /blocks/:shard/:nonce/transactions (gateway route; falls back to by-nonce)
    let path = if shard == 4294967295 {
        format!("/blocks/metachain/{}/transactions", nonce)
    } else {
        format!("/blocks/{}/{}/transactions", shard, nonce)
    };
    let v = match mx_get(client, base, &path).await {
        Ok(v) => v,
        Err(_) => {
            // fallback: query by-nonce endpoint
            let alt = format!("/transactions?afterNonce={}&size=50", nonce);
            mx_get(client, base, &alt).await?
        }
    };
    Ok(v.as_array().cloned().unwrap_or_default())
}

async fn get_hyperblock(client: &reqwest::Client, base: &str, nonce: u64) -> Result<Value> {
    mx_get(client, base, &format!("/hyperblock/by-nonce/{}", nonce)).await
}

/// Canonical event-type classification for MultiversX tx data signatures.
fn classify_mx(tx: &Value) -> u8 {
    let data_hex = tx.get("data").and_then(|v| v.as_str()).unwrap_or("");
    let receiver = tx.get("receiver").and_then(|v| v.as_str()).unwrap_or("");

    // data is hex-encoded function call (esdtTransfer/execute, etc.)
    if !data_hex.is_empty() {
        let decoded = hex_decode_ascii(data_hex);
        let lower = decoded.to_lowercase();
        if lower.contains("swap")              { return 1; }  // SWAP
        if lower.contains("addliquidity")      { return 2; }  // LIQUIDITY
        if lower.contains("removeliquidity")   { return 2; }
        if lower.contains("stake")             { return 3; }  // STAKE
        if lower.contains("unstake") || lower.contains("unbond") { return 4; } // UNSTAKE
        if lower.contains("vote") || lower.contains("proposal")  { return 6; } // GOVERNANCE/PROPOSAL
        if lower.contains("borrow")            { return 7; }  // BORROW
        if lower.contains("repay")             { return 8; }  // REPAY
        if lower.contains("liquidat")          { return 9; }  // LIQUIDATE
        if lower.contains("bridge") || lower.contains("transfer") {
            if lower.contains("bridge")        { return 10; } // BRIDGE
        }
        if lower.contains("deploy")            { return 11; } // DEPLOY
        if lower.contains("upgrade")           { return 12; } // UPGRADE
        if lower.contains("mint")              { return 13; } // MINT
        if lower.contains("burn")              { return 14; } // BURN
        if lower.contains("claim") || lower.contains("harvest") { return 19; } // CLAIM
        if lower.contains("esdttransfer")      { return 0; }  // TRANSFER (token)
        if lower.contains("multiesdt")         { return 0; }
    }

    // System/staking receivers
    if receiver.starts_with("erd1qqqqqq") { return 6; }     // governance-ish system SC
    if receiver.is_empty()                { return 11; }    // deploy (no receiver)

    0 // TRANSFER fallback (native eGLD move)
}

fn hex_decode_ascii(hex: &str) -> String {
    let s = hex.trim_start_matches("0x");
    let mut out = String::new();
    let bytes: Vec<char> = s.chars().collect();
    let mut i = 0;
    while i + 1 < bytes.len() {
        let byte = u8::from_str_radix(&format!("{}{}", bytes[i], bytes[i+1]), 16).unwrap_or(0);
        if byte >= 32 && byte < 127 { out.push(byte as char); }
        i += 2;
    }
    out
}

fn tx_value_wei(tx: &Value) -> u128 {
    tx.get("value").and_then(|v| v.as_str())
        .and_then(|s| s.parse::<u128>().ok())
        .or_else(|| tx.get("value").and_then(|v| v.as_u64()).map(|v| v as u128))
        .unwrap_or(0)
}

fn extract_features(txs: &[Value]) -> [f64; 9] {
    if txs.is_empty() { return [0.5f64; 9]; }

    let mut shards:    Vec<String> = Vec::new();
    let mut senders:   Vec<String> = Vec::new();
    let mut receivers: Vec<String> = Vec::new();
    let mut values:    Vec<f64>    = Vec::new();
    let mut gas_limits: Vec<f64>  = Vec::new();
    let mut gas_prices: Vec<f64>  = Vec::new();
    let mut data_pres: Vec<String> = Vec::new();
    let (mut success, mut failed) = (0u64, 0u64);
    let mut funcs:     Vec<String> = Vec::new();

    for tx in txs {
        let shard = tx.get("shard").map(|s| match s {
            Value::Number(n) => n.to_string(),
            Value::String(s) => s.clone(),
            _ => "0".into(),
        }).unwrap_or_else(|| "0".into());
        shards.push(shard);

        senders.push(tx.get("sender").and_then(|v| v.as_str()).unwrap_or("").to_string());
        receivers.push(tx.get("receiver").and_then(|v| v.as_str()).unwrap_or("").to_string());

        let v = tx_value_wei(tx);
        if v > 0 { values.push(v as f64 / EGLD_DECIMALS); }

        gas_limits.push(tx.get("gasLimit").and_then(|v| v.as_u64()).unwrap_or(0) as f64);
        gas_prices.push(tx.get("gasPrice").and_then(|v| v.as_u64()).unwrap_or(0) as f64);

        let has_data = tx.get("data").and_then(|d| d.as_str()).map(|d| !d.is_empty()).unwrap_or(false);
        data_pres.push(if has_data { "data".into() } else { "empty".into() });

        let status = tx.get("status").and_then(|v| v.as_str()).unwrap_or("success");
        if status == "success" || status == "executed" { success += 1; } else if status == "fail" || status == "invalid" { failed += 1; }

        if has_data {
            let decoded = hex_decode_ascii(tx.get("data").and_then(|v| v.as_str()).unwrap_or(""));
            let first_word = decoded.split('@').next().unwrap_or("").to_string();
            if !first_word.is_empty() { funcs.push(first_word); }
        }
    }

    [
        freq_entropy(&shards),
        freq_entropy(&senders),
        freq_entropy(&receivers),
        histogram_entropy(&values, 8),
        histogram_entropy(&gas_limits, 8),
        histogram_entropy(&gas_prices, 8),
        freq_entropy(&data_pres),
        ratio_entropy(success, success + failed),
        freq_entropy(&funcs),
    ]
}

// ── Per-tx Behavioral Hash pipeline ──────────────────────────────────────────

/// CANONICAL_BH.md §4 — deterministic magnitude normalization:
///   human = raw / 10^18 (eGLD wei); M = min(1, log10(human + 1) / log10(1001))
/// The rolling session-max tracker was removed: it made the BH of a fixed
/// transaction depend on what else the process had observed (canonical
/// violation — the same tx must always produce the same BH).
fn mx_magnitude(wei: u128) -> f64 {
    let w = (wei as u64).min(u64::MAX / 2);
    let human = w as f64 / 1e18;
    if human <= 0.0 { return 0.0; }
    ((human + 1.0).log10() / (1001.0_f64).log10()).min(1.0)
}

fn mx_bh_batch(txs: &[Value], nonce: u64, hyper_hash: &str, ts: u64) -> TxBhBatch {
    let mut entries: Vec<TxBhEntry> = Vec::new();

    for tx in txs {
        let hash = tx.get("txHash").and_then(|v| v.as_str())
            .or_else(|| tx.get("hash").and_then(|v| v.as_str()))
            .unwrap_or("").to_string();
        if hash.is_empty() { continue; }

        let sender = tx.get("sender").and_then(|v| v.as_str()).unwrap_or("unknown").to_string();
        let dest   = tx.get("receiver").and_then(|v| v.as_str()).unwrap_or("").to_string();
        let et     = classify_mx(tx);
        let wei    = tx_value_wei(tx);
        let mag    = mx_magnitude(wei);
        let eid    = bh_id(&sender);
        let (sense_hex, antisense_hex) = canonical_bh(&eid, et, mag, 0, ts, CHAIN_ID, hyper_hash);

        let selector = tx.get("data").and_then(|v| v.as_str()).map(|d| {
            hex_decode_ascii(d).split('@').next().unwrap_or("").to_string()
        }).unwrap_or_default();

        entries.push(TxBhEntry {
            tx_hash: hash,
            from_addr: sender,
            to_addr: dest,
            event_type: et,
            event_type_name: event_type_name(et).to_string(),
            entity_id: eid,
            magnitude_norm: mag,
            value_wei: wei.to_string(),
            selector,
            timestamp: ts,
            chain_id: CHAIN_ID,
            chain_label: CHAIN_LBL.to_string(),
            block_num: nonce,
            block_hash: hyper_hash.to_string(),
            sense_hex,
            antisense_hex,
        });
    }

    TxBhBatch {
        chain_id: CHAIN_ID,
        chain_label: CHAIN_LBL.to_string(),
        block_num: nonce,
        block_hash: hyper_hash.to_string(),
        timestamp: ts,
        entries,
    }
}

#[tokio::main]
async fn main() -> Result<()> {
    tracing_subscriber::fmt().with_env_filter("info").init();

    let faiss_url = std::env::var("FAISS_SERVICE_URL").unwrap_or_else(|_| "http://127.0.0.1:8000".into());
    let poll_ms   = std::env::var("POLL_MS").ok().and_then(|s| s.parse().ok()).unwrap_or(6_000u64);
    let mut base      = std::env::var("MULTIVERSX_API_URL").unwrap_or_else(|_| MX_URLS[0].into());
    let mut rpc_idx = 0usize;  // RPC failover rotation index
    let faiss     = FaissClient::new(&faiss_url)?;
    let state = IndexerState::new("multiversx");
    let client    = reqwest::Client::builder().timeout(Duration::from_secs(15)).build()?;

    info!("TRION MultiversX Rust Indexer — chain={} poll={}ms api={}", CHAIN_ID, poll_ms, base);

    // Network status → shard count
    let shard_count = mx_get(&client, &base, "/network/status/0")
        .await
        .ok()
        .and_then(|v| {
            v.pointer("/data/status/shard_count")
                .and_then(|s| s.as_u64())
        })
        .unwrap_or(3);

    info!("MultiversX shard_count={}", shard_count);

    loop {
        if !faiss.is_healthy().await { sleep(Duration::from_secs(5)).await; continue; }

        // hyperblock nonce = metachain round
        let latest = match mx_get(&client, &base, "/network/status/4294967295").await {
            Ok(v) => v.pointer("/data/status/nonce").and_then(|n| n.as_u64()).unwrap_or(0),
            Err(_) => {
                // fallback to shard 0
                mx_get(&client, &base, "/network/status/0").await
                    .ok()
                    .and_then(|v| v.pointer("/data/status/nonce").and_then(|n| n.as_u64()))
                    .unwrap_or(0)
            }
        };
        if latest == 0 {
            // Both status endpoints failed — rotate to the next RPC
            rpc_idx += 1;
            base = MX_URLS[rpc_idx % MX_URLS.len()].into();
            sleep(Duration::from_millis(poll_ms)).await;
            continue;
        }

        let last = state.last_block();
        let from = if last == 0 { latest.saturating_sub(1) } else { last + 1 };

        for nonce in from..=latest {
            let hyper = match get_hyperblock(&client, &base, nonce).await {
                Ok(v) => v.pointer("/data/hyperblock").cloned().unwrap_or(Value::Null),
                Err(_) => Value::Null,
            };
            let hyper_hash = hyper.get("hash").and_then(|v| v.as_str()).unwrap_or("").to_string();
            // CANONICAL_BH.md §5 — hyperblock timestamp; 0 = unknown, never wall-clock.
            let ts = hyper.get("timestamp").and_then(|v| v.as_u64()).unwrap_or(0);

            // Gather txs from hyperblock if present (includes all shards)
            let txs: Vec<Value> = hyper.get("transactions").and_then(|v| v.as_array()).cloned().unwrap_or_default();
            if txs.is_empty() { state.save(nonce).ok(); continue; }

            let features = extract_features(&txs);
            let phi      = features.iter().sum::<f64>() / 9.0;
            let eid      = block_entity_id(CHAIN_LBL, nonce);
            let bh       = bh_id(&eid);
            let vector   = build_vector(&features, &format!("{}:{}", CHAIN_LBL, nonce));
            let block_hash_hex = if hyper_hash.is_empty() {
                // SEC-05 — genuinely-missing → honest zero (§9), never a
                // fabricated synthetic id.
                warn!("[{}] nonce {}: no hyperblock hash — zero block hash", CHAIN_LBL, nonce);
                "0x0".to_string()
            } else {
                // SEC-05 — REAL hyperblock hash verbatim: bh_id() here was a
                // silent SHA3 substitution (hash-of-hash) that canonical BH §9
                // explicitly forbids.
                hyper_hash.clone()
            };

            let payload = BatchPayload {
                vectors: vec![VectorEntry {
                    entity_id: eid,
                    vector,
                    magnitude: phi,
                    entropy: phi,
                    timestamp: ts as f64,
                    bh_id: bh,
                    block_num: nonce,
                    chain_id: CHAIN_ID,
                    chain_label: CHAIN_LBL.into(),
                    vm_type: VM_TYPE.into(),
                    funding_source: None,
                    block_hash_hex: Some(block_hash_hex.clone()),
                    event_type: Some(classify_mx(&txs[0])),
                    sense_hex: None,
                    antisense_hex: None,
                }],
                block_num: nonce,
                block_features: features.to_vec(),
                block_phi: phi,
                chain_id: CHAIN_ID,
                chain_label: CHAIN_LBL.into(),
                vm_type: VM_TYPE.into(),
            };

            match faiss.add_batch(&payload).await {
                Ok(added) => {
                    let tx_batch = mx_bh_batch(&txs, nonce, &block_hash_hex, ts);
                    let bh_stored = faiss.add_tx_bh_batch(&tx_batch).await.unwrap_or(0);
                    info!("[{}] nonce={} txs={} φ={:.4} added={} bh_stored={}",
                          CHAIN_LBL, nonce, txs.len(), phi, added, bh_stored);
                }
                Err(e) => warn!("[{}] FAISS failed: {}", CHAIN_LBL, e),
            }
            state.save(nonce).ok();
        }
        sleep(Duration::from_millis(poll_ms)).await;
    }
}
