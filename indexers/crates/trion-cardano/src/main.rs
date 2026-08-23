/*!
 * TRION Cardano Behavioral Indexer — Rust
 * =========================================
 * Polls Koios public REST (api.koios.rest) for blocks and transactions.
 * Produces 128-dim vectors AND per-tx canonical BH (L0.1 ledger).
 *
 * Cardano behavioral dimensions (9 Shannon entropy features):
 *   f1 — Tx type entropy           H(tx_type frequency: Conway/Plutus/Shelley/Allegra/Mary)
 *   f2 — Input address entropy     H(input address frequency)
 *   f3 — Output address entropy    H(output address frequency)
 *   f4 — ADA amount entropy        H(amount bins, lovelace)
 *   f5 — Fee entropy               H(fee bins)
 *   f6 — Asset diversity           H(asset policy frequency)
 *   f7 — Script/Plutus ratio       H(Plutus script execution)
 *   f8 — Input count entropy       H(inputs-per-tx bins)
 *   f9 — Output count entropy      H(outputs-per-tx bins)
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

const CHAIN_ID:  u64  = 9400;
const CHAIN_LBL: &str = "CARDANO";
const VM_TYPE:   &str = "CARDANO"; // eUTXO with Plutus scripts

const KOIOS_URLS: &[&str] = &[
    "https://api.koios.rest/api/v1",
    "https://guild.koios.rest/api/v1",
];

/// 1 ADA = 1e6 lovelace
const LOVELACE: f64 = 1e6;

async fn koios_get(client: &reqwest::Client, base: &str, path: &str) -> Result<Value> {
    let url = format!("{}{}", base.trim_end_matches('/'), path);
    let resp = client.get(&url)
        .header("Accept", "application/json")
        .header("User-Agent", "trion-indexer/1.0")
        .send().await?;
    if !resp.status().is_success() {
        anyhow::bail!("Koios HTTP {} on {}", resp.status(), path);
    }
    Ok(resp.json().await?)
}

async fn koios_post(client: &reqwest::Client, base: &str, path: &str, body: &str) -> Result<Value> {
    let url = format!("{}{}", base.trim_end_matches('/'), path);
    let resp = client.post(&url)
        .header("Content-Type", "application/json")
        .header("Accept", "application/json")
        .header("User-Agent", "trion-indexer/1.0")
        .body(body.to_string())
        .send().await?;
    if !resp.status().is_success() {
        anyhow::bail!("Koios POST HTTP {} on {}", resp.status(), path);
    }
    Ok(resp.json().await?)
}

async fn get_tip(client: &reqwest::Client, base: &str) -> Result<u64> {
    let v = koios_get(client, base, "/tip").await?;
    Ok(v.as_array()
        .and_then(|a| a.first())
        .and_then(|tip| tip.get("block_no"))
        .and_then(|b| b.as_u64())
        .unwrap_or(0))
}

async fn get_block_txs(client: &reqwest::Client, base: &str, height: u64) -> Result<Vec<Value>> {
    // POST /tx_info with {_block_heights: [height]}
    let body = format!("{{\"_block_heights\":[{}]}}", height);
    let v = koios_post(client, base, "/tx_info", &body).await?;
    Ok(v.as_array().cloned().unwrap_or_default())
}

/// Canonical event-type classification for Cardano transactions.
fn classify_cardano(tx: &Value) -> u8 {
    let ttype = tx.get("type").and_then(|v| v.as_str()).unwrap_or("");
    let has_plutus = tx.get("plutus_scripts").is_some()
        || tx.get("script_size").is_some()
        || tx.get("plutus_size").is_some();
    let has_assets = tx.get("asset_list")
        .and_then(|a| a.as_array())
        .map(|a| !a.is_empty())
        .unwrap_or(false);
    let mint = tx.get("mint")
        .and_then(|m| m.as_array())
        .map(|a| !a.is_empty())
        .unwrap_or(false);

    if mint { return 13; }           // MINT
    if has_plutus {
        // Plutus script execution — DEX swap or DeFi interaction
        return 1;                     // SWAP
    }
    if has_assets { return 0; }      // TRANSFER (token transfer)
    if ttype.contains("cert") || tx.get("stake_cert").is_some() {
        return 3;                     // STAKE (stake registration/delegation)
    }
    0                                 // TRANSFER (ADA)
}

fn tx_lovelace(tx: &Value) -> u64 {
    // Total output lovelace
    tx.get("outputs")
        .and_then(|o| o.as_array())
        .map(|outputs| {
            outputs.iter()
                .filter_map(|out| out.get("value")
                    .and_then(|v| v.as_u64()))
                .sum()
        })
        .unwrap_or(0)
}

fn tx_input_addrs(tx: &Value) -> Vec<String> {
    tx.get("inputs")
        .and_then(|i| i.as_array())
        .map(|inputs| {
            inputs.iter()
                .filter_map(|inp| inp.get("payment_addr").and_then(|a| a.as_str()))
                .map(|s| s.to_string())
                .collect()
        })
        .unwrap_or_default()
}

fn tx_output_addrs(tx: &Value) -> Vec<String> {
    tx.get("outputs")
        .and_then(|o| o.as_array())
        .map(|outputs| {
            outputs.iter()
                .filter_map(|out| out.get("payment_addr").and_then(|a| a.as_str()))
                .map(|s| s.to_string())
                .collect()
        })
        .unwrap_or_default()
}

fn extract_features(txs: &[Value]) -> [f64; 9] {
    if txs.is_empty() { return [0.5f64; 9]; }

    let mut ttypes:  Vec<String> = Vec::new();
    let mut inputs:  Vec<String> = Vec::new();
    let mut outputs: Vec<String> = Vec::new();
    let mut amounts: Vec<f64>    = Vec::new();
    let mut fees:    Vec<f64>    = Vec::new();
    let mut assets:  Vec<String> = Vec::new();
    let (mut plutus, mut plain) = (0u64, 0u64);
    let mut input_counts:  Vec<f64> = Vec::new();
    let mut output_counts: Vec<f64> = Vec::new();

    for tx in txs {
        ttypes.push(tx.get("type").and_then(|v| v.as_str()).unwrap_or("unknown").to_string());

        let in_addrs = tx_input_addrs(tx);
        let out_addrs = tx_output_addrs(tx);
        inputs.extend(in_addrs.clone());
        outputs.extend(out_addrs.clone());

        let lovelace = tx_lovelace(tx);
        if lovelace > 0 { amounts.push(lovelace as f64 / LOVELACE); }

        let fee = tx.get("fee").and_then(|f| f.as_u64()).unwrap_or(0) as f64 / LOVELACE;
        fees.push(fee);

        if let Some(asset_list) = tx.get("asset_list").and_then(|a| a.as_array()) {
            for asset in asset_list {
                let policy = asset.get("policy_id").and_then(|p| p.as_str()).unwrap_or("native");
                assets.push(policy.to_string());
            }
        }

        if tx.get("plutus_scripts").is_some() || tx.get("script_size").is_some() {
            plutus += 1;
        } else {
            plain += 1;
        }

        input_counts.push(in_addrs.len() as f64);
        output_counts.push(out_addrs.len() as f64);
    }

    [
        freq_entropy(&ttypes),
        freq_entropy(&inputs),
        freq_entropy(&outputs),
        histogram_entropy(&amounts, 8),
        histogram_entropy(&fees, 8),
        freq_entropy(&assets),
        ratio_entropy(plutus, plutus + plain),
        histogram_entropy(&input_counts, 5),
        histogram_entropy(&output_counts, 5),
    ]
}

// ── Per-tx Behavioral Hash pipeline ──────────────────────────────────────────

static MAX_LOVELACE: AtomicU64 = AtomicU64::new(1_000_000_000_000); // 1M ADA reference

fn ada_magnitude(lovelace: u64) -> f64 {
    let old = MAX_LOVELACE.load(Ordering::Relaxed);
    if lovelace > old { MAX_LOVELACE.store(lovelace, Ordering::Relaxed); }
    let max = MAX_LOVELACE.load(Ordering::Relaxed).max(1) as f64;
    ((lovelace as f64 + 1.0).log10() / (max + 1.0).log10()).clamp(0.0, 1.0)
}

fn cardano_bh_batch(txs: &[Value], height: u64, block_hash: &str, ts: u64) -> TxBhBatch {
    let mut entries: Vec<TxBhEntry> = Vec::new();

    for tx in txs {
        let hash = tx.get("tx_hash").and_then(|v| v.as_str()).unwrap_or("").to_string();
        if hash.is_empty() { continue; }

        let sender = tx_input_addrs(tx).first().cloned().unwrap_or_else(|| "unknown".to_string());
        let dest = tx_output_addrs(tx).first().cloned().unwrap_or_default();

        let et = classify_cardano(tx);
        let lovelace = tx_lovelace(tx);
        let mag = ada_magnitude(lovelace);
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
            value_wei: lovelace.to_string(),
            selector: tx.get("type").and_then(|v| v.as_str()).unwrap_or("").to_string(),
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
    let poll_ms   = std::env::var("POLL_MS").ok().and_then(|s| s.parse().ok()).unwrap_or(20_000u64);
    let base      = std::env::var("CARDANO_KOIOS_URL").unwrap_or_else(|_| KOIOS_URLS[0].into());
    let faiss     = FaissClient::new(&faiss_url)?;
    let state     = IndexerState::new("cardano");
    let client    = reqwest::Client::builder().timeout(Duration::from_secs(20)).build()?;

    info!("TRION Cardano Rust Indexer — chain={} poll={}ms koios={}", CHAIN_ID, poll_ms, base);

    loop {
        if !faiss.is_healthy().await { sleep(Duration::from_secs(5)).await; continue; }

        let latest = match get_tip(&client, &base).await {
            Ok(n) => n,
            Err(e) => { warn!("Cardano tip error: {}", e); sleep(Duration::from_millis(poll_ms)).await; continue; }
        };
        if latest == 0 { sleep(Duration::from_millis(poll_ms)).await; continue; }

        let last = state.last_block();
        let from = if last == 0 { latest.saturating_sub(1) } else { last + 1 };

        // Cardano blocks are 20s — process at most 2 per cycle to stay polite
        for height in from..=latest.min(from + 1) {
            let txs = match get_block_txs(&client, &base, height).await {
                Ok(v) => v,
                Err(e) => { warn!("[{}] block {} error: {}", CHAIN_LBL, height, e); continue; }
            };

            let ts = SystemTime::now().duration_since(UNIX_EPOCH)
                .unwrap_or_default().as_secs();
            let block_hash = txs.first()
                .and_then(|t| t.get("block_hash").and_then(|h| h.as_str()))
                .unwrap_or("");

            if txs.is_empty() { state.save(height).ok(); continue; }

            let features = extract_features(&txs);
            let phi      = features.iter().sum::<f64>() / 9.0;
            let eid      = block_entity_id(CHAIN_LBL, height);
            let bh       = bh_id(&eid);
            let vector   = build_vector(&features, &format!("{}:{}", CHAIN_LBL, height));
            let block_hash_hex = if block_hash.is_empty() {
                bh_id(&format!("cardano_block:{}:{}", CHAIN_LBL, height))
            } else {
                bh_id(block_hash)
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
                    event_type: Some(classify_cardano(&txs[0])),
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
                    let tx_batch = cardano_bh_batch(&txs, height, &block_hash_hex, ts);
                    let bh_stored = faiss.add_tx_bh_batch(&tx_batch).await.unwrap_or(0);
                    info!("[{}] block={} txs={} φ={:.4} added={} bh_stored={}",
                          CHAIN_LBL, height, txs.len(), phi, added, bh_stored);
                }
                Err(e) => warn!("[{}] FAISS failed: {}", CHAIN_LBL, e),
            }
            state.save(height).ok();
        }
        sleep(Duration::from_millis(poll_ms)).await;
    }
}
