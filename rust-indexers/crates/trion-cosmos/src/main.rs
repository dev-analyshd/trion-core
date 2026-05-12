/*!
 * TRION Cosmos SDK Behavioral Indexer — Rust
 * ===========================================
 * Indexes 6 Cosmos SDK chains simultaneously via public LCD REST APIs.
 *
 * Cosmos behavioral dimensions (9 Shannon entropy features):
 *   f1 — Message type diversity  H(msg_type distribution)
 *   f2 — Sender entropy          H(sender_address frequency)
 *   f3 — Gas fee entropy         H(gas_used bins)
 *   f4 — Amount entropy          H(token_amount bins)
 *   f5 — Validator entropy       H(proposer_address)
 *   f6 — IBC transfer entropy    H(channel_id distribution)
 *   f7 — Staking action entropy  H(delegate/undelegate/redelegate)
 *   f8 — Contract call entropy   H(contract_address frequency)
 *   f9 — Success ratio entropy   H(success vs failure)
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

#[derive(Clone)]
struct CosmosChain {
    label:    &'static str,
    chain_id: u64,
    lcds:     &'static [&'static str],
    denom:    &'static str,
}

const CHAINS: &[CosmosChain] = &[
    CosmosChain { label: "COSMOS_HUB",  chain_id: 4001, denom: "uatom",
        lcds: &["https://cosmos-rest.publicnode.com", "https://rest.cosmos.directory/cosmoshub"] },
    CosmosChain { label: "KAVA",        chain_id: 4002, denom: "ukava",
        lcds: &["https://kava-api.publicnode.com", "https://rest.cosmos.directory/kava"] },
    CosmosChain { label: "INJECTIVE",   chain_id: 4003, denom: "inj",
        lcds: &["https://injective-rest.publicnode.com", "https://rest.cosmos.directory/injective"] },
    CosmosChain { label: "SEI",         chain_id: 4004, denom: "usei",
        lcds: &["https://sei-api.polkachu.com", "https://rest.cosmos.directory/sei"] },
    CosmosChain { label: "DYDX",        chain_id: 4005, denom: "adydx",
        lcds: &["https://dydx-rest.publicnode.com", "https://rest.cosmos.directory/dydx"] },
    CosmosChain { label: "INITIA",      chain_id: 4006, denom: "uinit",
        lcds: &["https://rest.initia.xyz", "https://initia-api.polkachu.com"] },
];

async fn lcd_get(client: &reqwest::Client, lcd: &str, path: &str) -> Result<Value> {
    let url = format!("{}{}", lcd.trim_end_matches('/'), path);
    let resp = client.get(&url).send().await?;
    if !resp.status().is_success() {
        anyhow::bail!("LCD HTTP {} for {}", resp.status(), path);
    }
    Ok(resp.json().await?)
}

async fn get_latest_height(client: &reqwest::Client, lcd: &str) -> Result<u64> {
    let data = lcd_get(client, lcd, "/cosmos/base/tendermint/v1beta1/blocks/latest").await?;
    let h = data["block"]["header"]["height"].as_str()
        .and_then(|s| s.parse::<u64>().ok())
        .unwrap_or(0);
    Ok(h)
}

async fn get_block_txs(client: &reqwest::Client, lcd: &str, height: u64) -> Result<Value> {
    lcd_get(client, lcd, &format!("/cosmos/tx/v1beta1/txs?events=tx.height%3D{}&pagination.limit=50", height)).await
}

async fn get_block(client: &reqwest::Client, lcd: &str, height: u64) -> Result<Value> {
    lcd_get(client, lcd, &format!("/cosmos/base/tendermint/v1beta1/blocks/{}", height)).await
}

fn extract_features(block: &Value, txs_resp: &Value) -> [f64; 9] {
    let txs = match txs_resp["tx_responses"].as_array() {
        Some(a) => a, None => return [0.5f64; 9],
    };
    if txs.is_empty() { return [0.5f64; 9]; }

    let mut msg_types:     Vec<String> = Vec::new();
    let mut senders:       Vec<String> = Vec::new();
    let mut gas_used:      Vec<f64>    = Vec::new();
    let mut amounts:       Vec<f64>    = Vec::new();
    let mut ibc_channels:  Vec<String> = Vec::new();
    let mut staking_types: Vec<String> = Vec::new();
    let mut contracts:     Vec<String> = Vec::new();
    let (mut success, mut failed) = (0u64, 0u64);

    for tx_resp in txs {
        let code = tx_resp["code"].as_u64().unwrap_or(0);
        if code == 0 { success += 1; } else { failed += 1; }

        if let Some(gu) = tx_resp["gas_used"].as_str().and_then(|s| s.parse::<f64>().ok()) {
            gas_used.push(gu);
        }

        let tx = &tx_resp["tx"];
        if let Some(msgs) = tx["body"]["messages"].as_array() {
            for msg in msgs {
                let type_url = msg["@type"].as_str().unwrap_or("/unknown").to_string();
                msg_types.push(type_url.clone());

                // Sender
                let sender = msg["from_address"].as_str()
                    .or_else(|| msg["delegator_address"].as_str())
                    .or_else(|| msg["sender"].as_str())
                    .unwrap_or("").to_string();
                if !sender.is_empty() { senders.push(sender); }

                // Amount
                if let Some(amt) = msg["amount"].as_array().and_then(|a| a.first()) {
                    let v = amt["amount"].as_str().and_then(|s| s.parse::<f64>().ok()).unwrap_or(0.0);
                    amounts.push(v);
                }

                // IBC
                if type_url.contains("ibc") {
                    let ch = msg["source_channel"].as_str().unwrap_or("unknown").to_string();
                    ibc_channels.push(ch);
                }

                // Staking
                if type_url.contains("Delegate") || type_url.contains("Undelegate") || type_url.contains("Redelegate") {
                    staking_types.push(type_url.clone());
                }

                // Contract
                if type_url.contains("MsgExecuteContract") {
                    let addr = msg["contract"].as_str().unwrap_or("").to_string();
                    contracts.push(addr);
                }
            }
        }
    }

    // Proposer from block header
    let proposer = block["block"]["header"]["proposer_address"].as_str().unwrap_or("").to_string();
    let proposers = if proposer.is_empty() { vec![] } else { vec![proposer] };

    [
        freq_entropy(&msg_types),
        freq_entropy(&senders),
        histogram_entropy(&gas_used, 8),
        histogram_entropy(&amounts, 8),
        freq_entropy(&proposers),
        freq_entropy(&ibc_channels),
        freq_entropy(&staking_types),
        freq_entropy(&contracts),
        ratio_entropy(success, success + failed),
    ]
}

async fn index_one_chain(chain: &CosmosChain, faiss: &FaissClient, state: &mut IndexerState, client: &reqwest::Client) -> Result<()> {
    let mut lcd_idx = 0usize;
    let lcd = chain.lcds[lcd_idx % chain.lcds.len()];

    let latest = match get_latest_height(client, lcd).await {
        Ok(h)  => h,
        Err(e) => { warn!("[{}] latest height error: {}", chain.label, e); return Ok(()); }
    };
    let last = state.last_block();
    let from = if last == 0 { latest.saturating_sub(1) } else { last + 1 };

    for height in from..=latest {
        let lcd = chain.lcds[lcd_idx % chain.lcds.len()];
        let block = match get_block(client, lcd, height).await {
            Ok(b)  => b,
            Err(e) => { warn!("[{}] block {} error: {} — rotating LCD", chain.label, height, e); lcd_idx += 1; continue; }
        };
        let txs_resp = match get_block_txs(client, lcd, height).await {
            Ok(t)  => t,
            Err(e) => { warn!("[{}] txs {} error: {}", chain.label, height, e); serde_json::json!({}) }
        };

        let features = extract_features(&block, &txs_resp);
        let phi      = features.iter().sum::<f64>() / 9.0;
        let eid      = block_entity_id(chain.label, height);
        let bh       = bh_id(&eid);
        let vector   = build_vector(&features, &format!("{}:{}", chain.label, height));
        let ts       = SystemTime::now().duration_since(UNIX_EPOCH).unwrap_or_default().as_secs_f64();

        let payload = BatchPayload {
            vectors: vec![VectorEntry {
                entity_id: eid, vector, magnitude: phi, entropy: phi, timestamp: ts,
                bh_id: bh, block_num: height, chain_id: chain.chain_id,
                chain_label: chain.label.into(), vm_type: "COSMOS".into(),
                funding_source: None, block_hash_hex: None, event_type: None, sense_hex: None, antisense_hex: None,
            }],
            block_num: height, block_features: features.to_vec(), block_phi: phi,
            chain_id: chain.chain_id, chain_label: chain.label.into(), vm_type: "COSMOS".into(),
        };

        match faiss.add_batch(&payload).await {
            Ok(added) => info!("[{}] height={} φ={:.4} added={}", chain.label, height, phi, added),
            Err(e)    => warn!("[{}] FAISS failed: {}", chain.label, e),
        }
        state.save(height).ok();
    }
    Ok(())
}

#[tokio::main]
async fn main() -> Result<()> {
    tracing_subscriber::fmt().with_env_filter("info").init();

    let faiss_url = std::env::var("FAISS_SERVICE_URL").unwrap_or_else(|_| "http://127.0.0.1:8000".into());
    let poll_ms   = std::env::var("POLL_MS").ok().and_then(|s| s.parse().ok()).unwrap_or(8_000u64);
    let faiss     = FaissClient::new(&faiss_url)?;
    let client    = reqwest::Client::builder().timeout(Duration::from_secs(15)).build()?;

    let mut states: Vec<IndexerState> = CHAINS.iter()
        .map(|c| IndexerState::new(&format!("cosmos_{}", c.label.to_lowercase())))
        .collect();

    info!("TRION Cosmos Rust Indexer — {} chains, poll={}ms", CHAINS.len(), poll_ms);

    loop {
        if !faiss.is_healthy().await { sleep(Duration::from_secs(5)).await; continue; }

        for (chain, state) in CHAINS.iter().zip(states.iter_mut()) {
            if let Err(e) = index_one_chain(chain, &faiss, state, &client).await {
                warn!("[{}] error: {}", chain.label, e);
            }
            sleep(Duration::from_millis(500)).await; // rate-limit between chains
        }
        sleep(Duration::from_millis(poll_ms)).await;
    }
}
