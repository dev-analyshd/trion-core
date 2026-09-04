/*!
 * TRION BOT Chain Behavioral Indexer — L0.1 Per-Transaction BH + Block-Level Vectors
 * ==============================================================================
 * Chain: BOT Chain (EVM-compatible)
 *   Network Name:    BOT Chain
 *   Default RPC URL: https://rpc.botchain.ai
 *   Chain ID:        677
 *   Currency Symbol: BOT
 *   Block Explorer:  https://scan.botchain.ai
 *
 * This is the 14th indexer crate in the TRION Rust workspace. It mirrors the
 * canonical EVM indexer pattern (trion-evm) but is dedicated to BOT Chain so
 * that the dedicated relayer and supervisor can run it independently.
 *
 * Two outputs per block:
 *   1. Block-level 128-dim vector (φ) → POST /index/add_batch   (FAISS indexing)
 *   2. Per-transaction canonical BH   → POST /index/add_tx_bh_batch (L0.1 ledger)
 *
 * Block-level behavioral dimensions (9 Shannon entropy features):
 *   f1 — Transaction volume entropy    H(value_in_wei bins)
 *   f2 — Counterparty entropy          H(to_address frequency)
 *   f3 — Gas price entropy             H(gas_price bins)
 *   f4 — Contract interaction entropy  H(input_data_length bins)
 *   f5 — Value flow entropy            H(value > 0 ratio)
 *   f6 — Sender entropy                H(from_address frequency)
 *   f7 — ERC-20/DeFi interaction       H(method_selector frequency)
 *   f8 — Gas usage entropy             H(gas_used bins)
 *   f9 — MEV pattern entropy           H(miner_tip / base_fee ratio bins)
 *
 * Per-transaction BH uses canonical 93-byte payload (whitepaper L0.1 §3.1):
 *   entity_id(32) || event_type(1) || magnitude_nano(8) || context(8) ||
 *   timestamp(8)  || chain_id(4)   || block_hash(32)
 */

use anyhow::Result;
use serde_json::Value;
use std::time::{SystemTime, UNIX_EPOCH};
use tokio::time::{sleep, Duration};
use tracing::{error, info, warn};
use trion_common::{
    bh_id, block_entity_id, build_vector, canonical_bh, classify_event_type, event_type_name,
    freq_entropy, histogram_entropy,
    BatchPayload, FaissClient, IndexerState, TxBhBatch, TxBhEntry, VectorEntry, with_retry,
};

/// BOT Chain configuration.
const BOT_CHAIN_LABEL:    &str   = "BOT_CHAIN";
const BOT_CHAIN_ID:       u64    = 677;
const BOT_CHAIN_SYMBOL:   &str   = "BOT";
const BOT_CHAIN_VM_TYPE:  &str   = "EVM";
const BOT_CHAIN_EXPLORER: &str   = "https://scan.botchain.ai";

/// RPC endpoints for BOT Chain (rotated on failure).
const BOT_CHAIN_RPCS: &[&str] = &[
    "https://rpc.botchain.ai",
    // Public fallbacks (added as community endpoints come online)
];

#[derive(Clone, Copy)]
struct BotChain {
    label:    &'static str,
    chain_id: u64,
    rpcs:     &'static [&'static str],
}

const BOT_CHAIN: BotChain = BotChain {
    label:    BOT_CHAIN_LABEL,
    chain_id: BOT_CHAIN_ID,
    rpcs:     BOT_CHAIN_RPCS,
};

// ── RPC helpers ───────────────────────────────────────────────────────────────

async fn eth_rpc(client: &reqwest::Client, rpc: &str, method: &str, params: Value) -> Result<Value> {
    let body = serde_json::json!({
        "jsonrpc": "2.0", "id": 1, "method": method, "params": params
    });
    let resp = client.post(rpc).json(&body).send().await?;
    let json: Value = resp.json().await?;
    if let Some(err) = json.get("error") {
        anyhow::bail!("RPC error: {}", err);
    }
    Ok(json["result"].clone())
}

fn hex_to_u64(s: &str) -> u64 {
    let s = s.trim_start_matches("0x");
    u64::from_str_radix(s, 16).unwrap_or(0)
}

// ── Block-level feature extraction (9 Shannon entropy dimensions) ─────────────

fn extract_features(block: &Value) -> [f64; 9] {
    let txs = match block["transactions"].as_array() {
        Some(a) => a.clone(),
        None    => return [0.5f64; 9],
    };
    if txs.is_empty() {
        return [0.5f64; 9];
    }

    let values:     Vec<f64> = txs.iter().map(|t| hex_to_u64(t["value"].as_str().unwrap_or("0x0")) as f64).collect();
    let gas_prices: Vec<f64> = txs.iter().map(|t| hex_to_u64(t["gasPrice"].as_str().unwrap_or("0x0")) as f64).collect();
    let input_lens: Vec<f64> = txs.iter().map(|t| t["input"].as_str().unwrap_or("0x").len() as f64).collect();
    let gas_limits: Vec<f64> = txs.iter().map(|t| hex_to_u64(t["gas"].as_str().unwrap_or("0x0")) as f64).collect();
    let froms:      Vec<String> = txs.iter().map(|t| t["from"].as_str().unwrap_or("").to_string()).collect();
    let tos:        Vec<String> = txs.iter().map(|t| t["to"].as_str().unwrap_or("0x0").to_string()).collect();
    let selectors:  Vec<String> = txs.iter()
        .map(|t| { let i = t["input"].as_str().unwrap_or("0x"); if i.len() >= 10 { i[..10].to_string() } else { "0x".into() } })
        .collect();
    let max_prio:   Vec<f64> = txs.iter().map(|t| hex_to_u64(t["maxPriorityFeePerGas"].as_str().unwrap_or("0x0")) as f64).collect();
    let base_fee = hex_to_u64(block["baseFeePerGas"].as_str().unwrap_or("0x1")) as f64;
    let mev_ratios: Vec<f64> = max_prio.iter().map(|&p| (p / base_fee.max(1.0)).min(100.0) / 100.0).collect();

    let f1 = histogram_entropy(&values, 16);
    let f2 = freq_entropy(&tos);
    let f3 = histogram_entropy(&gas_prices, 16);
    let f4 = histogram_entropy(&input_lens, 8);
    let nonzero_ratio = values.iter().filter(|&&v| v > 0.0).count() as f64 / txs.len() as f64;
    let f5 = trion_common::entropy::ratio_entropy((nonzero_ratio * txs.len() as f64) as u64, txs.len() as u64);
    let f6 = freq_entropy(&froms);
    let f7 = freq_entropy(&selectors);
    let f8 = histogram_entropy(&gas_limits, 8);
    let f9 = histogram_entropy(&mev_ratios, 8);

    [f1, f2, f3, f4, f5, f6, f7, f8, f9]
}

// ── Per-transaction BH generation (whitepaper L0.1 §3.1) ─────────────────────

/// CANONICAL_BH.md §4 — deterministic magnitude normalization:
///   human = raw / 10^18 (BOT, same as ETH); M = min(1, log10(human + 1) / log10(1001))
/// The rolling "90-day max" tracker was removed: it made the BH of a fixed
/// transaction depend on what else the process had seen (session state) — a
/// canonical violation. The same tx must always produce the same BH.
fn magnitude_norm(value_wei: u64) -> f64 {
    let bot = value_wei as f64 / 1e18;
    if bot <= 0.0 { return 0.0; }
    ((bot + 1.0).log10() / (1001.0_f64).log10()).min(1.0)
}

/// Build per-transaction BH entries for every transaction in a block.
fn build_tx_bh_batch(
    block:      &Value,
    chain:      &BotChain,
    timestamp:  u64,
    block_num:  u64,
    block_hash: &str,
) -> TxBhBatch {
    let txs = match block["transactions"].as_array() {
        Some(a) => a,
        None    => return TxBhBatch {
            chain_id: chain.chain_id, chain_label: chain.label.to_string(),
            block_num, block_hash: block_hash.to_string(), timestamp, entries: vec![],
        },
    };

    let mut entries: Vec<TxBhEntry> = Vec::with_capacity(txs.len());

    for tx in txs {
        let from_addr = tx["from"].as_str().unwrap_or("0x0000000000000000000000000000000000000000");
        let to_addr   = tx["to"].as_str().unwrap_or("0x0000000000000000000000000000000000000000");
        let tx_hash   = tx["hash"].as_str().unwrap_or("0x0000000000000000000000000000000000000000000000000000000000000000");
        let value_wei = hex_to_u64(tx["value"].as_str().unwrap_or("0x0"));
        let input     = tx["input"].as_str().unwrap_or("0x");

        // Extract 4-byte method selector
        let selector = if input.len() >= 10 {
            input[2..10].to_string()
        } else {
            String::new()
        };

        // Classify event type
        let et_byte = if input == "0x" || input.is_empty() {
            0u8 // TRANSFER
        } else if input != "0x" && selector.is_empty() {
            11u8 // DEPLOY
        } else {
            classify_event_type(&selector)
        };

        // Detect MEV: high miner tip relative to base fee
        let max_prio = hex_to_u64(tx["maxPriorityFeePerGas"].as_str().unwrap_or("0x0"));
        let base_fee = hex_to_u64(block["baseFeePerGas"].as_str().unwrap_or("0x1"));
        let mev_ratio = max_prio as f64 / base_fee.max(1) as f64;
        let et_byte = if mev_ratio > 5.0 && (et_byte == 1 || et_byte == 0) {
            17u8 // MEV_CAPTURE
        } else {
            et_byte
        };

        let mag = magnitude_norm(value_wei);
        let entity_id_hex = bh_id(from_addr);

        let (sense_hex, antisense_hex) = canonical_bh(
            &entity_id_hex,
            et_byte,
            mag,
            0u64,
            timestamp,
            chain.chain_id,
            block_hash,
        );

        entries.push(TxBhEntry {
            tx_hash:         tx_hash.to_string(),
            from_addr:       from_addr.to_string(),
            to_addr:         to_addr.to_string(),
            event_type:      et_byte,
            event_type_name: event_type_name(et_byte).to_string(),
            entity_id:       entity_id_hex,
            magnitude_norm:  mag,
            value_wei:       value_wei.to_string(),
            selector,
            timestamp,
            chain_id:        chain.chain_id,
            chain_label:     chain.label.to_string(),
            block_num,
            block_hash:      block_hash.to_string(),
            sense_hex,
            antisense_hex,
        });
    }

    TxBhBatch {
        chain_id:    chain.chain_id,
        chain_label: chain.label.to_string(),
        block_num,
        block_hash:  block_hash.to_string(),
        timestamp,
        entries,
    }
}

// ── Block indexing loop ───────────────────────────────────────────────────────

async fn index_chain(chain: &BotChain, faiss: &FaissClient, state: &mut IndexerState) -> Result<()> {
    let client = reqwest::Client::builder()
        .timeout(Duration::from_secs(12))
        .build()?;

    let mut rpc_idx = 0usize;

    // ── Try each RPC in rotation for eth_blockNumber ──────────────────────────
    let mut latest_opt: Option<u64> = None;
    for (i, rpc) in chain.rpcs.iter().enumerate() {
        let rpc_str = rpc.to_string();
        let res = with_retry(chain.label, 2, 800, || {
            let c = client.clone(); let r = rpc_str.clone();
            async move {
                let v = eth_rpc(&c, &r, "eth_blockNumber", serde_json::json!([])).await?;
                Ok(v.as_str().unwrap_or("0x0").to_string())
            }
        }).await;
        if let Ok(hex) = res {
            let n = hex_to_u64(&hex);
            if n > 0 {
                latest_opt = Some(n);
                rpc_idx = i;
                break;
            }
        }
    }
    let latest = match latest_opt {
        Some(l) => l,
        None => return Err(anyhow::anyhow!("[{}] all RPCs failed for eth_blockNumber", chain.label)),
    };

    let last = state.last_block();
    let from = if last == 0 { latest.saturating_sub(1) } else { last + 1 };
    if from > latest { return Ok(()); }

    for block_num in from..=latest {
        let rpc_str = chain.rpcs[rpc_idx % chain.rpcs.len()].to_string();
        let block = match with_retry(chain.label, 3, 2000, || {
            let c = client.clone(); let r = rpc_str.clone();
            let n = block_num;
            async move {
                eth_rpc(&c, &r, "eth_getBlockByNumber",
                    serde_json::json!([format!("0x{:x}", n), true])).await
            }
        }).await {
            Ok(b) => b,
            Err(e) => { warn!("[{}] block {} fetch failed: {}", chain.label, block_num, e); rpc_idx += 1; continue; }
        };

        let block_hash = block["hash"].as_str().unwrap_or("0x0000000000000000000000000000000000000000000000000000000000000000");
        let timestamp  = hex_to_u64(block["timestamp"].as_str().unwrap_or("0x0"));

        // ── 1. Block-level 128-dim vector (φ computation) ─────────────────────
        let features  = extract_features(&block);
        let phi       = features.iter().sum::<f64>() / 9.0;
        let entity_id = block_entity_id(chain.label, block_num);
        let block_bh  = bh_id(&entity_id);

        let dominant_et = {
            let txs = block["transactions"].as_array();
            let mut counts = [0u32; 20];
            if let Some(txs) = txs {
                for tx in txs {
                    let input = tx["input"].as_str().unwrap_or("0x");
                    let sel   = if input.len() >= 10 { &input[2..10] } else { "" };
                    let et    = classify_event_type(sel) as usize;
                    if et < 20 { counts[et] += 1; }
                }
            }
            counts.iter().enumerate().max_by_key(|&(_, &c)| c).map(|(i, _)| i as u8).unwrap_or(0)
        };

        let (block_sense, block_antisense) = canonical_bh(
            &block_bh,
            dominant_et,
            phi,
            0u64,
            timestamp,
            chain.chain_id,
            block_hash,
        );

        let vector  = build_vector(&features, &format!("{}:{}", chain.label, block_num));

        let payload = BatchPayload {
            vectors: vec![VectorEntry {
                entity_id:      entity_id.clone(),
                vector,
                magnitude:      phi,
                entropy:        phi,
                timestamp:      SystemTime::now().duration_since(UNIX_EPOCH).unwrap_or_default().as_secs_f64(),
                bh_id:          block_sense.clone(),
                block_num,
                chain_id:       chain.chain_id,
                chain_label:    chain.label.to_string(),
                vm_type:        BOT_CHAIN_VM_TYPE.to_string(),
                funding_source: None,
                block_hash_hex: Some(block_hash.to_string()),
                event_type:     Some(dominant_et),
                sense_hex:      Some(block_sense),
                antisense_hex:  Some(block_antisense),
            }],
            block_num,
            block_features: features.to_vec(),
            block_phi:      phi,
            chain_id:       chain.chain_id,
            chain_label:    chain.label.to_string(),
            vm_type:        BOT_CHAIN_VM_TYPE.to_string(),
        };

        match faiss.add_batch(&payload).await {
            Ok(added) => info!("[{}] block={} phi={:.4} added={} (BOT Chain)", chain.label, block_num, phi, added),
            Err(e)    => warn!("[{}] FAISS ingest failed for block {}: {}", chain.label, block_num, e),
        }

        // ── 2. Per-transaction canonical BH (whitepaper L0.1 §3.1) ──────────
        let tx_batch = build_tx_bh_batch(&block, chain, timestamp, block_num, block_hash);
        let tx_count = tx_batch.entries.len();
        if tx_count > 0 {
            match faiss.add_tx_bh_batch(&tx_batch).await {
                Ok(stored) => info!("[{}] block={} per-tx BHs: {}/{} stored (BOT Chain)", chain.label, block_num, stored, tx_count),
                Err(e)     => warn!("[{}] tx BH batch failed for block {}: {}", chain.label, block_num, e),
            }
        }

        state.save(block_num).ok();
    }
    Ok(())
}

// ── Main ──────────────────────────────────────────────────────────────────────

#[tokio::main]
async fn main() -> Result<()> {
    tracing_subscriber::fmt().with_env_filter("info").init();

    let faiss_url = std::env::var("FAISS_SERVICE_URL").unwrap_or_else(|_| "http://127.0.0.1:8000".into());
    let poll_ms   = std::env::var("POLL_INTERVAL_MS").ok().and_then(|s| s.parse().ok()).unwrap_or(15_000u64);

    info!("══════════════════════════════════════════════════════════════════════════");
    info!("TRION BOT Chain Behavioral Indexer — L0.1 per-transaction BH pipeline");
    info!("  Chain:       {} (ID {})", BOT_CHAIN_LABEL, BOT_CHAIN_ID);
    info!("  Symbol:      {}", BOT_CHAIN_SYMBOL);
    info!("  RPC:         {:?}", BOT_CHAIN_RPCS);
    info!("  Explorer:    {}", BOT_CHAIN_EXPLORER);
    info!("  VM Type:     {}", BOT_CHAIN_VM_TYPE);
    info!("  Poll:        {} ms", poll_ms);
    info!("  FAISS URL:   {}", faiss_url);
    info!("  L0.1 BH:     ENABLED (canonical 93-byte payload + dual-strand SHA3)");
    info!("══════════════════════════════════════════════════════════════════════════");

    let faiss = FaissClient::new(&faiss_url)?;
    let mut state = IndexerState::new("botchain_mainnet");

    loop {
        if !faiss.is_healthy().await {
            warn!("[{}] FAISS not reachable — waiting 5s", BOT_CHAIN.label);
            sleep(Duration::from_secs(5)).await;
            continue;
        }
        if let Err(e) = index_chain(&BOT_CHAIN, &faiss, &mut state).await {
            error!("[{}] indexer error: {}", BOT_CHAIN.label, e);
        }
        sleep(Duration::from_millis(poll_ms)).await;
    }
}
