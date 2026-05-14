/*!
 * TRION TRON Behavioral Indexer — Rust
 * =====================================
 * Polls TRON blocks via TronGrid REST API.
 *
 * TRON behavioral dimensions (9 Shannon entropy features):
 *   f1 — Contract type entropy       H(TransferContract/TriggerSmartContract/...)
 *   f2 — Sender entropy              H(owner_address frequency)
 *   f3 — Energy consumption entropy  H(energy_used bins)
 *   f4 — TRX transfer entropy        H(trx_amount bins)
 *   f5 — TRC-20 token diversity      H(contract_address frequency)
 *   f6 — Bandwidth entropy           H(bandwidth_used bins)
 *   f7 — DApp interaction entropy    H(dapp_contract frequency)
 *   f8 — Resource delegation entropy H(delegate_resource type)
 *   f9 — Vote/witness entropy        H(vote_address frequency)
 */

use anyhow::Result;
use serde_json::Value;
use std::time::{SystemTime, UNIX_EPOCH};
use tokio::time::{sleep, Duration};
use tracing::{info, warn};
use trion_common::{
    bh_id, block_entity_id, build_vector, freq_entropy, histogram_entropy,
    BatchPayload, FaissClient, IndexerState, VectorEntry,
};

const CHAIN_ID:  u64  = 3001;
const CHAIN_LBL: &str = "TRON_MAINNET";
const VM_TYPE:   &str = "TVM_TRON";

fn api_base() -> String {
    std::env::var("TRON_API_URL").unwrap_or_else(|_| "https://api.trongrid.io".into())
}

async fn tron_get(client: &reqwest::Client, path: &str) -> Result<Value> {
    let base    = api_base();
    let api_key = std::env::var("TRON_API_KEY").unwrap_or_default();
    let url     = format!("{}{}", base.trim_end_matches('/'), path);
    let mut req = client.get(&url).header("Accept", "application/json");
    if !api_key.is_empty() { req = req.header("TRON-PRO-API-KEY", &api_key); }
    let resp = req.send().await?;
    if !resp.status().is_success() { anyhow::bail!("TronGrid HTTP {}", resp.status()); }
    Ok(resp.json().await?)
}

async fn get_latest_block_num(client: &reqwest::Client) -> Result<u64> {
    let data = tron_get(client, "/wallet/getnowblock").await?;
    Ok(data["block_header"]["raw_data"]["number"].as_u64().unwrap_or(0))
}

async fn get_block(client: &reqwest::Client, num: u64) -> Result<Value> {
    let path = format!("/wallet/getblockbynum?num={}", num);
    tron_get(client, &path).await
}

fn extract_features(block: &Value) -> [f64; 9] {
    let txs = match block["transactions"].as_array() {
        Some(a) => a, None => return [0.5f64; 9],
    };
    if txs.is_empty() { return [0.5f64; 9]; }

    let mut contract_types: Vec<String> = Vec::new();
    let mut senders:        Vec<String> = Vec::new();
    let mut energies:       Vec<f64>    = Vec::new();
    let mut trx_amounts:    Vec<f64>    = Vec::new();
    let mut trc20_addrs:    Vec<String> = Vec::new();
    let mut bandwidths:     Vec<f64>    = Vec::new();
    let mut dapp_addrs:     Vec<String> = Vec::new();
    let mut delegation_types:Vec<String>= Vec::new();
    let mut vote_addrs:     Vec<String> = Vec::new();

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
                        let amt = param["amount"].as_u64().unwrap_or(0) as f64;
                        trx_amounts.push(amt);
                    }
                    "TriggerSmartContract" => {
                        let addr = param["contract_address"].as_str().unwrap_or("").to_string();
                        if !addr.is_empty() {
                            trc20_addrs.push(addr.clone());
                            dapp_addrs.push(addr);
                        }
                    }
                    "DelegateResourceContract" | "UnDelegateResourceContract" => {
                        let rtype = param["resource"].as_str().unwrap_or("ENERGY").to_string();
                        delegation_types.push(rtype);
                    }
                    "VoteWitnessContract" => {
                        if let Some(votes) = param["votes"].as_array() {
                            for v in votes {
                                let addr = v["vote_address"].as_str().unwrap_or("").to_string();
                                vote_addrs.push(addr);
                            }
                        }
                    }
                    _ => {}
                }
            }
        }

        // Energy and bandwidth from receipt
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

#[tokio::main]
async fn main() -> Result<()> {
    tracing_subscriber::fmt().with_env_filter("info").init();

    let faiss_url = std::env::var("FAISS_SERVICE_URL").unwrap_or_else(|_| "http://127.0.0.1:8000".into());
    let poll_ms   = std::env::var("POLL_MS").ok().and_then(|s| s.parse().ok()).unwrap_or(3_000u64);
    let faiss     = FaissClient::new(&faiss_url)?;
    let mut state = IndexerState::new("tron_mainnet");
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
            let features = extract_features(&block);
            let phi      = features.iter().sum::<f64>() / 9.0;
            let eid      = block_entity_id(CHAIN_LBL, block_num);
            let bh       = bh_id(&eid);
            let vector   = build_vector(&features, &format!("{}:{}", CHAIN_LBL, block_num));
            let ts       = SystemTime::now().duration_since(UNIX_EPOCH).unwrap_or_default().as_secs_f64();

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
                Ok(added) => info!("[{}] block={} φ={:.4} added={}", CHAIN_LBL, block_num, phi, added),
                Err(e)    => warn!("[{}] FAISS failed: {}", CHAIN_LBL, e),
            }
            state.save(block_num).ok();
        }
        sleep(Duration::from_millis(poll_ms)).await;
    }
}
