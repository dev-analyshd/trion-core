/*!
 * TRION Solana (SVM) Behavioral Indexer — Rust
 * =============================================
 * Polls Solana slots via JSON-RPC (getBlock) and pushes 128-dim vectors
 * AND per-transaction canonical BH (L0.1 ledger).
 *
 * SVM behavioral dimensions (9 Shannon entropy features):
 *   f1 — Instruction diversity    H(program_id distribution)
 *   f2 — Account access entropy   H(account_key_frequency)
 *   f3 — Compute unit entropy     H(CU bins)
 *   f4 — Lamport transfer entropy H(lamport_value bins)
 *   f5 — Signer diversity         H(num_signers distribution)
 *   f6 — Program invocation depth H(CPI count per tx bins)
 *   f7 — Fee payer diversity      H(fee_payer frequency)
 *   f8 — Slot timing entropy      H(slot gap bins)
 *   f9 — Write/read ratio entropy H(writable_fraction bins)
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

const CHAIN_ID:  u64  = 900;
const VM_TYPE:   &str = "SVM";

// Known high-volume Solana programs → event type classification
const STAKE_PROG:      &str = "Stake11111111111111111111111111111111111111";
const VOTE_PROG:       &str = "Vote111111111111111111111111111111111111111p";
const SYSTEM_PROG:     &str = "11111111111111111111111111111111";
const TOKEN_PROG:      &str = "TokenkegQfeZyiNwAJbNbGKPFXCWuBvf9Ss623VQ5DA";
const TOKEN22_PROG:    &str = "TokenzQdBNbLqP5VEhdkAS6EPFLC1PHnBqCXEpPxuEb";
// Common Solana DEX program IDs (first 8 chars for fast match)
const RAYDIUM_AMM:     &str = "675kPX9"; // Raydium V4 AMM
const ORCA_WHIRL:      &str = "whirLbMi"; // Orca Whirlpool
const SERUM_DEX:       &str = "9xQeWvG8"; // Serum v3

fn chain_label() -> String {
    std::env::var("SOLANA_LABEL").unwrap_or_else(|_| "SOLANA_MAINNET".into())
}

fn rpc_url() -> String {
    std::env::var("SOLANA_RPC_URL").unwrap_or_else(|_| "https://api.mainnet-beta.solana.com".into())
}

async fn sol_rpc(client: &reqwest::Client, method: &str, params: Value) -> Result<Value> {
    let url = rpc_url();
    let body = serde_json::json!({ "jsonrpc": "2.0", "id": 1, "method": method, "params": params });
    let resp = client.post(&url).json(&body).send().await?;
    let json: Value = resp.json().await?;
    if let Some(e) = json.get("error") { anyhow::bail!("Solana RPC: {}", e); }
    Ok(json["result"].clone())
}

fn extract_features(block: &Value, prev_slot: u64, cur_slot: u64) -> [f64; 9] {
    let txs = match block["transactions"].as_array() {
        Some(a) => a, None => return [0.5f64; 9],
    };
    if txs.is_empty() { return [0.5f64; 9]; }

    let mut program_ids:    Vec<String> = Vec::new();
    let mut account_keys:   Vec<String> = Vec::new();
    let mut compute_units:  Vec<f64>    = Vec::new();
    let mut lamports:       Vec<f64>    = Vec::new();
    let mut signer_counts:  Vec<f64>    = Vec::new();
    let mut cpi_depths:     Vec<f64>    = Vec::new();
    let mut fee_payers:     Vec<String> = Vec::new();
    let mut writable_fracs: Vec<f64>    = Vec::new();

    for tx in txs {
        let msg  = &tx["transaction"]["message"];
        let meta = &tx["meta"];
        if let Some(keys) = msg["accountKeys"].as_array() {
            for k in keys { account_keys.push(k.as_str().unwrap_or("").to_string()); }
            if let Some(fp) = keys.first() { fee_payers.push(fp.as_str().unwrap_or("").to_string()); }
            let sigs      = msg["header"]["numRequiredSignatures"].as_u64().unwrap_or(0);
            let ro_signed = msg["header"]["numReadonlySignedAccounts"].as_u64().unwrap_or(0);
            signer_counts.push(sigs as f64);
            let total = keys.len().max(1) as f64;
            writable_fracs.push((total - ro_signed as f64) / total);
        }
        if let Some(insts) = msg["instructions"].as_array() {
            cpi_depths.push(insts.len() as f64);
            for inst in insts {
                if let Some(pi) = inst["programIdIndex"].as_u64() {
                    program_ids.push(format!("prog_{}", pi));
                }
            }
        }
        if let Some(cu) = meta["computeUnitsConsumed"].as_u64() { compute_units.push(cu as f64); }
        if let (Some(pre), Some(post)) = (meta["preBalances"].as_array(), meta["postBalances"].as_array()) {
            let diff: f64 = pre.iter().zip(post.iter())
                .map(|(a, b)| (b.as_f64().unwrap_or(0.0) - a.as_f64().unwrap_or(0.0)).abs())
                .sum();
            lamports.push(diff);
        }
    }
    let slot_gap = (cur_slot.saturating_sub(prev_slot)) as f64;
    [
        freq_entropy(&program_ids),
        freq_entropy(&account_keys),
        histogram_entropy(&compute_units, 8),
        histogram_entropy(&lamports, 8),
        histogram_entropy(&signer_counts, 4),
        histogram_entropy(&cpi_depths, 8),
        freq_entropy(&fee_payers),
        histogram_entropy(&[slot_gap], 4),
        histogram_entropy(&writable_fracs, 8),
    ]
}

// ── Per-tx Behavioral Hash pipeline ──────────────────────────────────────────

static MAX_LAMPORTS: AtomicU64 = AtomicU64::new(1_000_000_000); // 1 SOL in lamports

fn sol_magnitude(lamports: u64) -> f64 {
    let old = MAX_LAMPORTS.load(Ordering::Relaxed);
    if lamports > old { MAX_LAMPORTS.store(lamports, Ordering::Relaxed); }
    let max = MAX_LAMPORTS.load(Ordering::Relaxed).max(1) as f64;
    let v   = lamports as f64;
    ((v + 1.0).log10() / (max + 1.0).log10()).clamp(0.0, 1.0)
}

fn classify_sol_event(tx: &Value, account_keys: &[String]) -> u8 {
    let meta = &tx["meta"];
    // Canonical whitepaper event types (L0.1 §2):
    // 0 TRANSFER, 1 SWAP, 2 LIQUIDITY, 3 STAKE, 4 UNSTAKE, 5 GOVERNANCE,
    // 6 PROPOSAL, 7 BORROW, 8 REPAY, 9 LIQUIDATE, 10 BRIDGE, 11 DEPLOY,
    // 12 UPGRADE, 13 MINT, 14 BURN, 15 ORACLE_UPDATE, 16 MEV_CAPTURE,
    // 17 FLASH_LOAN, 18 AIRDROP, 19 CLAIM
    if account_keys.iter().any(|k| k == STAKE_PROG) { return 3; } // STAKE
    if account_keys.iter().any(|k| k == VOTE_PROG)  { return 5; } // GOVERNANCE
    // Check for known DEX programs (partial match)
    for k in account_keys {
        let k8 = if k.len() >= 8 { &k[..8] } else { k.as_str() };
        if k8 == RAYDIUM_AMM || k8 == ORCA_WHIRL || k8 == SERUM_DEX { return 1; } // SWAP
    }
    // High compute → likely DEX interaction
    let cu = meta["computeUnitsConsumed"].as_u64().unwrap_or(0);
    if cu > 200_000 { return 1; } // SWAP
    // Token program = token transfer
    if account_keys.iter().any(|k| k == TOKEN_PROG || k == TOKEN22_PROG) { return 0; } // TRANSFER
    // System program → SOL transfer
    if account_keys.iter().any(|k| k == SYSTEM_PROG) { return 0; } // TRANSFER
    0 // TRANSFER default
}

fn sol_bh_batch(block: &Value, slot: u64, chain_id: u64, label: &str, blockhash: &str, ts: u64) -> TxBhBatch {
    let txs = match block["transactions"].as_array() {
        Some(a) => a, None => return TxBhBatch { chain_id, chain_label: label.to_string(), block_num: slot, block_hash: blockhash.to_string(), timestamp: ts, entries: vec![] },
    };
    let mut entries: Vec<TxBhEntry> = Vec::with_capacity(txs.len());

    for tx in txs {
        // Solana tx signature as the "hash"
        let sigs = tx["transaction"]["signatures"].as_array();
        let tx_hash = sigs.and_then(|s| s.first()).and_then(|s| s.as_str()).unwrap_or("").to_string();
        if tx_hash.is_empty() { continue; }

        let msg  = &tx["transaction"]["message"];
        let meta = &tx["meta"];

        // Collect account keys
        let account_keys: Vec<String> = msg["accountKeys"].as_array()
            .map(|ks| ks.iter().map(|k| k.as_str().unwrap_or("").to_string()).collect())
            .unwrap_or_default();

        let sender = account_keys.first().cloned().unwrap_or_default();
        let et = classify_sol_event(tx, &account_keys);

        // Lamport balance diff as magnitude proxy
        let lamports = if let (Some(pre), Some(post)) = (meta["preBalances"].as_array(), meta["postBalances"].as_array()) {
            pre.iter().zip(post.iter())
                .map(|(a, b)| (b.as_i64().unwrap_or(0) - a.as_i64().unwrap_or(0)).unsigned_abs())
                .max().unwrap_or(0)
        } else { 0u64 };

        let mag = sol_magnitude(lamports);
        let eid = bh_id(&sender);
        let (sense_hex, antisense_hex) = canonical_bh(&eid, et, mag, 0, ts, chain_id, blockhash);

        entries.push(TxBhEntry {
            tx_hash, from_addr: sender, to_addr: String::new(),
            event_type: et, event_type_name: event_type_name(et).to_string(),
            entity_id: eid, magnitude_norm: mag, value_wei: lamports.to_string(),
            selector: String::new(), timestamp: ts, chain_id,
            chain_label: label.to_string(), block_num: slot,
            block_hash: blockhash.to_string(), sense_hex, antisense_hex,
        });
    }
    TxBhBatch { chain_id, chain_label: label.to_string(), block_num: slot, block_hash: blockhash.to_string(), timestamp: ts, entries }
}

#[tokio::main]
async fn main() -> Result<()> {
    tracing_subscriber::fmt().with_env_filter("info").init();

    let faiss_url = std::env::var("FAISS_SERVICE_URL").unwrap_or_else(|_| "http://127.0.0.1:8000".into());
    let poll_ms   = std::env::var("POLL_SLEEP_MS").ok().and_then(|s| s.parse().ok()).unwrap_or(1_500u64);
    let label     = chain_label();
    let faiss     = FaissClient::new(&faiss_url)?;
    let state = IndexerState::new(&format!("svm_{}", label.to_lowercase()));
    let client    = reqwest::Client::builder().timeout(Duration::from_secs(15)).build()?;
    let mut prev_slot = 0u64;

    info!("TRION SVM Rust Indexer — chain={} label={} poll={}ms faiss={}", CHAIN_ID, label, poll_ms, faiss_url);

    loop {
        if !faiss.is_healthy().await { warn!("FAISS not reachable — waiting 5s"); sleep(Duration::from_secs(5)).await; continue; }

        let slot = match sol_rpc(&client, "getSlot", serde_json::json!([])).await {
            Ok(v)  => v.as_u64().unwrap_or(0),
            Err(e) => { warn!("getSlot error: {}", e); sleep(Duration::from_millis(poll_ms)).await; continue; }
        };

        let last = state.last_block();
        let from = if last == 0 { slot.saturating_sub(1) } else { last + 1 };

        for cur_slot in from..=slot {
            let block = match sol_rpc(&client, "getBlock",
                serde_json::json!([cur_slot, { "encoding": "json", "maxSupportedTransactionVersion": 0, "transactionDetails": "full", "rewards": false }])
            ).await {
                Ok(b)  => b,
                Err(e) => { warn!("[{}] slot {} fetch error: {}", label, cur_slot, e); continue; }
            };
            if block.is_null() { continue; }

            let features = extract_features(&block, prev_slot, cur_slot);
            let phi      = features.iter().sum::<f64>() / 9.0;
            let eid      = block_entity_id(&label, cur_slot);
            let bh       = bh_id(&eid);
            let vector   = build_vector(&features, &format!("{}:{}", label, cur_slot));
            let ts       = SystemTime::now().duration_since(UNIX_EPOCH).unwrap_or_default().as_secs_f64();
            let ts_u64   = ts as u64;
            let blockhash = block["blockhash"].as_str()
                .map(|h| h.to_string())
                .unwrap_or_else(|| bh_id(&format!("sol_slot:{}:{}", label, cur_slot)));

            let payload = BatchPayload {
                vectors: vec![VectorEntry {
                    entity_id: eid, vector, magnitude: phi, entropy: phi, timestamp: ts,
                    bh_id: bh, block_num: cur_slot,
                    chain_id: CHAIN_ID, chain_label: label.clone(), vm_type: VM_TYPE.into(),
                    funding_source: None, block_hash_hex: None, event_type: None, sense_hex: None, antisense_hex: None,
                }],
                block_num: cur_slot, block_features: features.to_vec(), block_phi: phi,
                chain_id: CHAIN_ID, chain_label: label.clone(), vm_type: VM_TYPE.into(),
            };

            match faiss.add_batch(&payload).await {
                Ok(added) => {
                    let tx_batch = sol_bh_batch(&block, cur_slot, CHAIN_ID, &label, &blockhash, ts_u64);
                    let bh_stored = faiss.add_tx_bh_batch(&tx_batch).await.unwrap_or(0);
                    info!("[{}] slot={} φ={:.4} added={} bh_stored={}", label, cur_slot, phi, added, bh_stored);
                }
                Err(e) => warn!("[{}] FAISS failed slot {}: {}", label, cur_slot, e),
            }
            state.save(cur_slot).ok();
            prev_slot = cur_slot;
        }
        sleep(Duration::from_millis(poll_ms)).await;
    }
}
