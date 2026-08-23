/*!
 * TRION Cosmos SDK Behavioral Indexer — Rust
 * ===========================================
 * Indexes 6 Cosmos SDK chains simultaneously via public LCD REST APIs.
 * Produces 128-dim vectors AND per-tx canonical BH (L0.1 ledger).
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
use std::sync::atomic::{AtomicU64, Ordering};
use std::time::{SystemTime, UNIX_EPOCH};
use tokio::time::{sleep, Duration};
use tracing::{info, warn};
use trion_common::{
    bh_id, block_entity_id, build_vector, canonical_bh, event_type_name,
    freq_entropy, histogram_entropy,
    entropy::ratio_entropy, BatchPayload, FaissClient, IndexerState, TxBhBatch, TxBhEntry, VectorEntry,
};

#[derive(Clone)]
struct CosmosChain {
    label:    &'static str,
    chain_id: u64,
    lcds:     &'static [&'static str],
    #[allow(dead_code)]
    denom:    &'static str,
}

const CHAINS: &[CosmosChain] = &[
    CosmosChain { label: "COSMOS_HUB", chain_id: 10000, denom: "uatom",
        lcds: &["https://cosmos-api.polkachu.com", "https://cosmos.api.kjnodes.com",
                "https://cosmos-rest.publicnode.com", "https://rest.cosmos.directory/cosmoshub"] },
    CosmosChain { label: "KAVA",       chain_id: 10014, denom: "ukava",
        lcds: &["https://kava-api.polkachu.com", "https://kava.api.kjnodes.com",
                "https://kava-api.publicnode.com", "https://rest.cosmos.directory/kava"] },
    CosmosChain { label: "INJECTIVE",  chain_id: 10004, denom: "inj",
        lcds: &["https://injective-api.polkachu.com", "https://injective.api.kjnodes.com",
                "https://injective-rest.publicnode.com", "https://rest.cosmos.directory/injective"] },
    CosmosChain { label: "SEI",        chain_id: 10005, denom: "usei",
        lcds: &["https://sei-api.polkachu.com", "https://sei.api.kjnodes.com",
                "https://rest.cosmos.directory/sei"] },
    CosmosChain { label: "DYDX",       chain_id: 10006, denom: "adydx",
        lcds: &["https://dydx-api.polkachu.com", "https://dydx.api.kjnodes.com",
                "https://dydx-rest.publicnode.com", "https://rest.cosmos.directory/dydx"] },
    CosmosChain { label: "INITIA",     chain_id: 10015, denom: "uinit",
        lcds: &["https://initia-api.polkachu.com", "https://initia.api.kjnodes.com",
                "https://rest.initia.xyz"] },
];

async fn lcd_get(client: &reqwest::Client, lcd: &str, path: &str) -> Result<Value> {
    let url = format!("{}{}", lcd.trim_end_matches('/'), path);
    let resp = client.get(&url).send().await?;
    if !resp.status().is_success() { anyhow::bail!("LCD HTTP {} for {}", resp.status(), path); }
    Ok(resp.json().await?)
}

async fn get_latest_height(client: &reqwest::Client, lcd: &str) -> Result<u64> {
    let data = lcd_get(client, lcd, "/cosmos/base/tendermint/v1beta1/blocks/latest").await?;
    let h = data["block"]["header"]["height"].as_str()
        .and_then(|s| s.parse::<u64>().ok()).unwrap_or(0);
    Ok(h)
}

async fn get_block_txs(client: &reqwest::Client, lcd: &str, height: u64) -> Result<Value> {
    // Try plain = first (most nodes); fall back to %3D encoding
    let path1 = format!("/cosmos/tx/v1beta1/txs?events=tx.height={}&pagination.limit=50", height);
    match lcd_get(client, lcd, &path1).await {
        Ok(v) => Ok(v),
        Err(_) => lcd_get(client, lcd, &format!("/cosmos/tx/v1beta1/txs?events=tx.height%3D{}&pagination.limit=50", height)).await,
    }
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
        if let Some(gu) = tx_resp["gas_used"].as_str().and_then(|s| s.parse::<f64>().ok()) { gas_used.push(gu); }
        let tx = &tx_resp["tx"];
        if let Some(msgs) = tx["body"]["messages"].as_array() {
            for msg in msgs {
                let type_url = msg["@type"].as_str().unwrap_or("/unknown").to_string();
                msg_types.push(type_url.clone());
                let sender = msg["from_address"].as_str()
                    .or_else(|| msg["delegator_address"].as_str())
                    .or_else(|| msg["sender"].as_str())
                    .unwrap_or("").to_string();
                if !sender.is_empty() { senders.push(sender); }
                if let Some(amt) = msg["amount"].as_array().and_then(|a| a.first()) {
                    let v = amt["amount"].as_str().and_then(|s| s.parse::<f64>().ok()).unwrap_or(0.0);
                    amounts.push(v);
                }
                if type_url.contains("ibc") {
                    ibc_channels.push(msg["source_channel"].as_str().unwrap_or("unknown").to_string());
                }
                if type_url.contains("Delegate") || type_url.contains("Undelegate") || type_url.contains("Redelegate") {
                    staking_types.push(type_url.clone());
                }
                if type_url.contains("MsgExecuteContract") {
                    contracts.push(msg["contract"].as_str().unwrap_or("").to_string());
                }
            }
        }
    }

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

// ── Per-tx Behavioral Hash pipeline ──────────────────────────────────────────

static MAX_UATOM: AtomicU64 = AtomicU64::new(1_000_000_000); // 1000 ATOM in uatom

fn cosmos_magnitude(uatom: u64) -> f64 {
    let old = MAX_UATOM.load(Ordering::Relaxed);
    if uatom > old { MAX_UATOM.store(uatom, Ordering::Relaxed); }
    let max = MAX_UATOM.load(Ordering::Relaxed).max(1) as f64;
    let v   = uatom as f64;
    ((v + 1.0).log10() / (max + 1.0).log10()).clamp(0.0, 1.0)
}

fn classify_cosmos_msg(type_url: &str) -> u8 {
    // Canonical whitepaper event types (L0.1 §2):
    // 0 TRANSFER, 1 SWAP, 2 LIQUIDITY, 3 STAKE, 4 UNSTAKE, 5 GOVERNANCE,
    // 6 PROPOSAL, 7 BORROW, 8 REPAY, 9 LIQUIDATE, 10 BRIDGE, 11 DEPLOY,
    // 12 UPGRADE, 13 MINT, 14 BURN, 15 ORACLE_UPDATE, 16 MEV_CAPTURE,
    // 17 FLASH_LOAN, 18 AIRDROP, 19 CLAIM
    match true {
        _ if type_url.contains("MsgSend") || type_url.contains("MultiSend")             => 0,  // TRANSFER
        _ if type_url.contains("MsgTransfer") && type_url.contains("ibc")               => 10, // BRIDGE (IBC)
        _ if type_url.contains("MsgDelegate") || type_url.contains("MsgCreateValidator")=> 3,  // STAKE
        _ if type_url.contains("MsgUndelegate") || type_url.contains("MsgBeginRedelegate")=>4, // UNSTAKE
        _ if type_url.contains("MsgVote")                                               => 5,  // GOVERNANCE (vote)
        _ if type_url.contains("MsgSubmitProposal")                                     => 6,  // PROPOSAL
        _ if type_url.contains("MsgDeposit") && type_url.contains("gov")                => 5,  // GOVERNANCE
        _ if type_url.contains("MsgExecuteContract")                                     => 1,  // SWAP (CosmWasm DeFi)
        _ if type_url.contains("MsgInstantiateContract")                                 => 11, // DEPLOY
        _ if type_url.contains("MsgCreateDenom") || type_url.contains("MsgMint")        => 13, // MINT
        _ if type_url.contains("MsgBurn")                                                => 14, // BURN
        _ if type_url.contains("MsgWithdrawDelegator") || type_url.contains("MsgClaim") => 19, // CLAIM
        _ => 0, // TRANSFER
    }
}

fn cosmos_bh_batch(txs_resp: &Value, chain: &CosmosChain, height: u64, block_hash: &str, ts: u64) -> TxBhBatch {
    let txs = match txs_resp["tx_responses"].as_array() {
        Some(a) => a,
        None    => return TxBhBatch { chain_id: chain.chain_id, chain_label: chain.label.to_string(), block_num: height, block_hash: block_hash.to_string(), timestamp: ts, entries: vec![] },
    };

    let mut entries: Vec<TxBhEntry> = Vec::with_capacity(txs.len());

    for tx_resp in txs {
        let txhash = tx_resp["txhash"].as_str().unwrap_or("").to_string();
        if txhash.is_empty() { continue; }
        let code = tx_resp["code"].as_u64().unwrap_or(0);
        if code != 0 { continue; } // skip failed txs

        let tx = &tx_resp["tx"];
        let msgs = match tx["body"]["messages"].as_array() {
            Some(m) if !m.is_empty() => m,
            _ => continue,
        };

        // Use first message for event classification
        let first_msg  = &msgs[0];
        let type_url   = first_msg["@type"].as_str().unwrap_or("/unknown");
        let et         = classify_cosmos_msg(type_url);

        let sender = first_msg["from_address"].as_str()
            .or_else(|| first_msg["delegator_address"].as_str())
            .or_else(|| first_msg["sender"].as_str())
            .unwrap_or("unknown").to_string();

        // Extract amount from first message
        let uatom = first_msg["amount"].as_array()
            .and_then(|a| a.first())
            .and_then(|a| a["amount"].as_str())
            .and_then(|s| s.parse::<u64>().ok())
            .unwrap_or(0);

        let mag = cosmos_magnitude(uatom);
        let eid = bh_id(&sender);
        let (sense_hex, antisense_hex) = canonical_bh(&eid, et, mag, 0, ts, chain.chain_id, block_hash);

        entries.push(TxBhEntry {
            tx_hash: txhash, from_addr: sender, to_addr: String::new(),
            event_type: et, event_type_name: event_type_name(et).to_string(),
            entity_id: eid, magnitude_norm: mag, value_wei: uatom.to_string(),
            selector: String::new(), timestamp: ts, chain_id: chain.chain_id,
            chain_label: chain.label.to_string(), block_num: height,
            block_hash: block_hash.to_string(), sense_hex, antisense_hex,
        });
    }

    TxBhBatch { chain_id: chain.chain_id, chain_label: chain.label.to_string(), block_num: height, block_hash: block_hash.to_string(), timestamp: ts, entries }
}

async fn index_one_chain(chain: &CosmosChain, faiss: &FaissClient, state: &mut IndexerState, client: &reqwest::Client) -> Result<()> {
    let mut lcd_idx = 0usize;
    let lcd     = chain.lcds[lcd_idx % chain.lcds.len()];
    let latest  = match get_latest_height(client, lcd).await {
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

        let features  = extract_features(&block, &txs_resp);
        let phi       = features.iter().sum::<f64>() / 9.0;
        let eid       = block_entity_id(chain.label, height);
        let bh        = bh_id(&eid);
        let vector    = build_vector(&features, &format!("{}:{}", chain.label, height));
        let ts        = SystemTime::now().duration_since(UNIX_EPOCH).unwrap_or_default().as_secs_f64();
        let ts_u64    = ts as u64;
        let block_hash = block["block_id"]["hash"].as_str()
            .map(|h| h.to_string())
            .unwrap_or_else(|| bh_id(&format!("cosmos_block:{}:{}", chain.label, height)));

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
            Ok(added) => {
                let mut tx_batch = cosmos_bh_batch(&txs_resp, chain, height, &block_hash, ts_u64);
                // Fallback: when txs endpoint fails (500/400), emit one block-level BH from proposer
                if tx_batch.entries.is_empty() {
                    let fallback_id = format!("{}:{}", chain.label, height);
                    let proposer = block["block"]["header"]["proposer_address"].as_str().unwrap_or(&fallback_id);
                    let eid = bh_id(proposer);
                    let (sense_hex, antisense_hex) = canonical_bh(&eid, 6u8, 0.5, 0, ts_u64, chain.chain_id, &block_hash);
                    tx_batch.entries.push(TxBhEntry {
                        tx_hash: block_hash.clone(), from_addr: proposer.to_string(), to_addr: String::new(),
                        event_type: 6, event_type_name: "GOVERNANCE".into(),
                        entity_id: eid, magnitude_norm: 0.5, value_wei: "0".into(),
                        selector: "block_proposer".into(), timestamp: ts_u64,
                        chain_id: chain.chain_id, chain_label: chain.label.to_string(),
                        block_num: height, block_hash: block_hash.clone(), sense_hex, antisense_hex,
                    });
                }
                let bh_stored = faiss.add_tx_bh_batch(&tx_batch).await.unwrap_or(0);
                info!("[{}] height={} φ={:.4} added={} bh_stored={}", chain.label, height, phi, added, bh_stored);
            }
            Err(e) => warn!("[{}] FAISS failed: {}", chain.label, e),
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
            sleep(Duration::from_millis(500)).await;
        }
        sleep(Duration::from_millis(poll_ms)).await;
    }
}
