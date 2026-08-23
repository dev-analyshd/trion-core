/*!
 * TRION TRON Behavioral Indexer — Rust
 * =====================================
 * Indexes TRON mainnet via TronGrid REST API.
 * Produces 128-dim vectors AND per-tx canonical BH (L0.1 ledger).
 *
 * TRON behavioral dimensions (9 Shannon entropy features):
 *   f1 — Contract type entropy   H(TransferContract/TriggerSmartContract/etc)
 *   f2 — Sender entropy          H(owner_address frequency)
 *   f3 — Energy entropy          H(energy_usage_total bins)
 *   f4 — TRX amount entropy      H(trx_amount bins)
 *   f5 — TRC20 contract entropy  H(contract_address frequency)
 *   f6 — Bandwidth entropy       H(bandwidth_usage bins)
 *   f7 — DApp entropy            H(dapp_address frequency)
 *   f8 — Delegation type entropy H(ENERGY/BANDWIDTH resource)
 *   f9 — Vote entropy            H(vote_address distribution)
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
    BatchPayload, FaissClient, IndexerState, TxBhBatch, TxBhEntry, VectorEntry,
};

const CHAIN_ID:  u64  = 7001;
const CHAIN_LBL: &str = "TRON_MAINNET";
const VM_TYPE:   &str = "TVM";

const TRON_APIS: &[&str] = &[
    "https://api.trongrid.io",
    "https://api.shasta.trongrid.io",
];

#[allow(dead_code)]
async fn tron_get(client: &reqwest::Client, base: &str, path: &str) -> Result<Value> {
    let url  = format!("{}{}", base.trim_end_matches('/'), path);
    let resp = client.get(&url).header("TRON-PRO-API-KEY", "").send().await?;
    if !resp.status().is_success() { anyhow::bail!("TRON HTTP {}", resp.status()); }
    Ok(resp.json().await?)
}

async fn get_latest_block_num(client: &reqwest::Client) -> Result<u64> {
    let url  = format!("{}/wallet/getnowblock", TRON_APIS[0]);
    let resp = client.post(&url).json(&serde_json::json!({})).send().await?;
    let data: Value = resp.json().await?;
    Ok(data["block_header"]["raw_data"]["number"].as_u64().unwrap_or(0))
}

async fn get_block(client: &reqwest::Client, block_num: u64) -> Result<Value> {
    let url  = format!("{}/wallet/getblockbynum", TRON_APIS[0]);
    let resp = client.post(&url).json(&serde_json::json!({ "num": block_num })).send().await?;
    let data: Value = resp.json().await?;
    Ok(data)
}

fn extract_features(block: &Value) -> [f64; 9] {
    let txs = match block["transactions"].as_array() {
        Some(a) => a, None => return [0.5f64; 9],
    };
    if txs.is_empty() { return [0.5f64; 9]; }

    let mut contract_types:  Vec<String> = Vec::new();
    let mut senders:         Vec<String> = Vec::new();
    let mut energies:        Vec<f64>    = Vec::new();
    let mut trx_amounts:     Vec<f64>    = Vec::new();
    let mut trc20_addrs:     Vec<String> = Vec::new();
    let mut bandwidths:      Vec<f64>    = Vec::new();
    let mut dapp_addrs:      Vec<String> = Vec::new();
    let mut delegation_types:Vec<String> = Vec::new();
    let mut vote_addrs:      Vec<String> = Vec::new();

    for tx in txs {
        let raw = &tx["raw_data"];
        if let Some(contracts) = raw["contract"].as_array() {
            for contract in contracts {
                let ctype = contract["type"].as_str().unwrap_or("Unknown").to_string();
                contract_types.push(ctype.clone());
                let param = &contract["parameter"]["value"];
                let owner = param["owner_address"].as_str().unwrap_or("").to_string();
                if !owner.is_empty() { senders.push(owner); }
                match ctype.as_str() {
                    "TransferContract" => {
                        trx_amounts.push(param["amount"].as_u64().unwrap_or(0) as f64);
                    }
                    "TriggerSmartContract" => {
                        let addr = param["contract_address"].as_str().unwrap_or("").to_string();
                        if !addr.is_empty() { trc20_addrs.push(addr.clone()); dapp_addrs.push(addr); }
                    }
                    "DelegateResourceContract" | "UnDelegateResourceContract" => {
                        delegation_types.push(param["resource"].as_str().unwrap_or("ENERGY").to_string());
                    }
                    "VoteWitnessContract" => {
                        if let Some(votes) = param["votes"].as_array() {
                            for v in votes { vote_addrs.push(v["vote_address"].as_str().unwrap_or("").to_string()); }
                        }
                    }
                    _ => {}
                }
            }
        }
        let receipt = &tx["ret"];
        if let Some(r) = receipt.as_array().and_then(|a| a.first()) {
            let energy = r["energy_usage_total"].as_u64().unwrap_or(0) as f64;
            if energy > 0.0 { energies.push(energy); }
        }
        bandwidths.push(raw["data"].as_str().map(|s| s.len()).unwrap_or(0) as f64);
    }

    [
        freq_entropy(&contract_types),
        freq_entropy(&senders),
        histogram_entropy(&energies, 8),
        histogram_entropy(&trx_amounts, 8),
        freq_entropy(&trc20_addrs),
        histogram_entropy(&bandwidths, 8),
        freq_entropy(&dapp_addrs),
        freq_entropy(&delegation_types),
        freq_entropy(&vote_addrs),
    ]
}

// ── Per-tx Behavioral Hash pipeline ──────────────────────────────────────────

static MAX_SUN: AtomicU64 = AtomicU64::new(1_000_000); // 1 TRX in sun

fn tron_magnitude(sun: u64) -> f64 {
    let old = MAX_SUN.load(Ordering::Relaxed);
    if sun > old { MAX_SUN.store(sun, Ordering::Relaxed); }
    let max = MAX_SUN.load(Ordering::Relaxed).max(1) as f64;
    let v   = sun as f64;
    ((v + 1.0).log10() / (max + 1.0).log10()).clamp(0.0, 1.0)
}

fn classify_tron_contract(ctype: &str, param: &Value) -> u8 {
    match ctype {
        "TransferContract" | "TransferAssetContract" => 0, // TRANSFER
        "FreezeBalanceContract" | "FreezeBalanceV2Contract"
            | "DelegateResourceContract"         => 3,  // STAKE
        "UnfreezeBalanceContract" | "UnfreezeBalanceV2Contract"
            | "UnDelegateResourceContract"       => 4,  // UNSTAKE
        "VoteWitnessContract"                    => 5,  // GOVERNANCE
        "TriggerSmartContract"                   => {
            // Heuristic: large data field → likely DEX swap
            let data = param["data"].as_str().unwrap_or("");
            if data.len() > 200 { 1 } else { 0 } // SWAP or TRANSFER
        }
        "CreateSmartContract"                    => 11, // DEPLOY
        "ExchangeCreateContract" | "ExchangeInjectContract"
            | "ExchangeWithdrawContract"         => 2,  // LIQUIDITY
        "WithdrawBalanceContract" | "WithdrawExpireUnfreezeContract" => 19, // CLAIM
        _                                        => 0,  // TRANSFER
    }
}

fn tron_bh_batch(block: &Value, chain_id: u64, label: &str, block_num: u64, block_hash: &str, ts: u64) -> TxBhBatch {
    let txs = match block["transactions"].as_array() {
        Some(a) => a,
        None    => return TxBhBatch { chain_id, chain_label: label.to_string(), block_num, block_hash: block_hash.to_string(), timestamp: ts, entries: vec![] },
    };
    let mut entries: Vec<TxBhEntry> = Vec::new();

    for tx in txs {
        let tx_hash = tx["txID"].as_str().unwrap_or("").to_string();
        if tx_hash.is_empty() { continue; }

        let raw = &tx["raw_data"];
        let contracts = match raw["contract"].as_array() {
            Some(c) if !c.is_empty() => c,
            _ => continue,
        };

        let contract = &contracts[0];
        let ctype    = contract["type"].as_str().unwrap_or("Unknown");
        let param    = &contract["parameter"]["value"];
        let et       = classify_tron_contract(ctype, param);

        let sender = param["owner_address"].as_str().unwrap_or("unknown").to_string();
        let sun    = param["amount"].as_u64().unwrap_or(0);
        let mag    = tron_magnitude(sun);
        let eid    = bh_id(&sender);
        let (sense_hex, antisense_hex) = canonical_bh(&eid, et, mag, 0, ts, chain_id, block_hash);

        entries.push(TxBhEntry {
            tx_hash, from_addr: sender, to_addr: param["to_address"].as_str().unwrap_or("").to_string(),
            event_type: et, event_type_name: event_type_name(et).to_string(),
            entity_id: eid, magnitude_norm: mag, value_wei: sun.to_string(),
            selector: ctype[..ctype.len().min(16)].to_string(),
            timestamp: ts, chain_id, chain_label: label.to_string(), block_num,
            block_hash: block_hash.to_string(), sense_hex, antisense_hex,
        });
    }

    TxBhBatch { chain_id, chain_label: label.to_string(), block_num, block_hash: block_hash.to_string(), timestamp: ts, entries }
}

#[tokio::main]
async fn main() -> Result<()> {
    tracing_subscriber::fmt().with_env_filter("info").init();

    let faiss_url = std::env::var("FAISS_SERVICE_URL").unwrap_or_else(|_| "http://127.0.0.1:8000".into());
    let poll_ms   = std::env::var("POLL_MS").ok().and_then(|s| s.parse().ok()).unwrap_or(3_000u64);
    let faiss     = FaissClient::new(&faiss_url)?;
    let state = IndexerState::new("tron_mainnet");
    let client    = reqwest::Client::builder().timeout(Duration::from_secs(12)).build()?;

    info!("TRION TRON Rust Indexer — chain={} poll={}ms", CHAIN_ID, poll_ms);

    loop {
        if !faiss.is_healthy().await { sleep(Duration::from_secs(5)).await; continue; }

        let latest = match get_latest_block_num(&client).await {
            Ok(n)  => n,
            Err(e) => { warn!("TRON latest block error: {}", e); sleep(Duration::from_millis(poll_ms)).await; continue; }
        };
        let last = state.last_block();
        let from = if last == 0 { latest.saturating_sub(1) } else { last + 1 };

        for block_num in from..=latest {
            let block = match get_block(&client, block_num).await {
                Ok(b)  => b,
                Err(e) => { warn!("[{}] block {} error: {}", CHAIN_LBL, block_num, e); continue; }
            };
            let features  = extract_features(&block);
            let phi       = features.iter().sum::<f64>() / 9.0;
            let eid       = block_entity_id(CHAIN_LBL, block_num);
            let bh        = bh_id(&eid);
            let vector    = build_vector(&features, &format!("{}:{}", CHAIN_LBL, block_num));
            let ts        = SystemTime::now().duration_since(UNIX_EPOCH).unwrap_or_default().as_secs_f64();
            let ts_u64    = ts as u64;
            // Derive block hash from blockID field
            let block_hash = block["blockID"].as_str()
                .map(|h| h.to_string())
                .unwrap_or_else(|| bh_id(&format!("tron_block:{}:{}", CHAIN_LBL, block_num)));

            let payload = BatchPayload {
                vectors: vec![VectorEntry {
                    entity_id: eid, vector, magnitude: phi, entropy: phi, timestamp: ts,
                    bh_id: bh, block_num, chain_id: CHAIN_ID, chain_label: CHAIN_LBL.into(), vm_type: VM_TYPE.into(),
                    funding_source: None, block_hash_hex: None, event_type: None, sense_hex: None, antisense_hex: None,
                }],
                block_num, block_features: features.to_vec(), block_phi: phi,
                chain_id: CHAIN_ID, chain_label: CHAIN_LBL.into(), vm_type: VM_TYPE.into(),
            };

            match faiss.add_batch(&payload).await {
                Ok(added) => {
                    let tx_batch = tron_bh_batch(&block, CHAIN_ID, CHAIN_LBL, block_num, &block_hash, ts_u64);
                    let bh_stored = faiss.add_tx_bh_batch(&tx_batch).await.unwrap_or(0);
                    info!("[{}] block={} φ={:.4} added={} bh_stored={}", CHAIN_LBL, block_num, phi, added, bh_stored);
                }
                Err(e) => warn!("[{}] FAISS failed: {}", CHAIN_LBL, e),
            }
            state.save(block_num).ok();
        }
        sleep(Duration::from_millis(poll_ms)).await;
    }
}
