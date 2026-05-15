/*!
 * TRION EVM Behavioral Indexer — L0.1 Per-Transaction BH + Block-Level Vectors
 * =============================================================================
 * Covers: ETH Mainnet, ARB Mainnet, BASE Mainnet, OP Mainnet, BNB Mainnet,
 *         HashKey Mainnet, Mantle Mainnet, Linea Mainnet, Scroll Mainnet,
 *         Polygon Mainnet, 0G Mainnet, 0G Newton Mainnet
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

#[derive(Clone, Copy)]
struct EvmChain {
    label:    &'static str,
    chain_id: u64,
    rpcs:     &'static [&'static str],
}

const CHAINS: &[EvmChain] = &[
    // ── Ethereum ecosystem mainnets ───────────────────────────────────────────
    EvmChain {
        label: "ETH_MAINNET", chain_id: 1,
        rpcs: &[
            "https://ethereum.publicnode.com",
            "https://cloudflare-eth.com",
            "https://rpc.ankr.com/eth",
            "https://eth.llamarpc.com",
        ],
    },
    EvmChain {
        label: "ARB_MAINNET", chain_id: 42161,
        rpcs: &[
            "https://arb1.arbitrum.io/rpc",
            "https://arbitrum-mainnet.public.blastapi.io",
            "https://rpc.ankr.com/arbitrum",
        ],
    },
    EvmChain {
        label: "BASE_MAINNET", chain_id: 8453,
        rpcs: &[
            "https://mainnet.base.org",
            "https://base-mainnet.public.blastapi.io",
            "https://rpc.ankr.com/base",
        ],
    },
    EvmChain {
        label: "OP_MAINNET", chain_id: 10,
        rpcs: &[
            "https://mainnet.optimism.io",
            "https://optimism-mainnet.public.blastapi.io",
            "https://rpc.ankr.com/optimism",
        ],
    },
    EvmChain {
        label: "POLYGON", chain_id: 137,
        rpcs: &[
            "https://polygon.llamarpc.com",
            "https://polygon-bor-rpc.publicnode.com",
            "https://1rpc.io/matic",
            "https://polygon-rpc.com",
            "https://rpc.ankr.com/polygon",
        ],
    },
    EvmChain {
        label: "BNB_MAINNET", chain_id: 56,
        rpcs: &[
            "https://bsc-dataseed.binance.org",
            "https://bsc-dataseed1.defibit.io",
            "https://bsc-dataseed1.ninicoin.io",
            "https://bsc-mainnet.public.blastapi.io",
        ],
    },
    EvmChain {
        label: "MANTLE", chain_id: 5000,
        rpcs: &["https://rpc.mantle.xyz", "https://mantle-mainnet.public.blastapi.io"],
    },
    EvmChain {
        label: "LINEA", chain_id: 59144,
        rpcs: &["https://rpc.linea.build", "https://linea-mainnet.public.blastapi.io"],
    },
    EvmChain {
        label: "SCROLL", chain_id: 534352,
        rpcs: &["https://rpc.scroll.io", "https://scroll-mainnet.public.blastapi.io"],
    },
    EvmChain {
        label: "HASHKEY", chain_id: 177,
        rpcs: &["https://mainnet.hsk.xyz", "https://hashkey-mainnet-rpc.publicnode.com"],
    },
    // ── 0G Networks ───────────────────────────────────────────────────────────
    EvmChain {
        label: "ZG_MAINNET", chain_id: 16661,
        rpcs: &[
            "https://evmrpc.0g.ai",
            "https://rpc.0g.ai",
        ],
    },
    EvmChain {
        label: "ZG_NEWTON", chain_id: 16600,
        rpcs: &[
            "https://evmrpc-mainnet.0g.ai",
            "https://0g-mainnet.g.alchemy.com/v2/demo",
            "https://0g.rpc.thirdweb.com",
        ],
    },
];

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

/// Global 90-day max value tracker for magnitude normalisation.
/// Thread-local per-process (not persisted — resets on restart, which is fine).
static MAX_90D_WEI: std::sync::atomic::AtomicU64 = std::sync::atomic::AtomicU64::new(1);

fn magnitude_norm(value_wei: u64) -> f64 {
    // L0.1: magnitude_norm = log10(ETH_value + 1) / log10(max_90d + 1)
    // ETH_value = value_wei / 1e18 (avoid f64 precision loss by working in gwei)
    let eth = value_wei as f64 / 1e18;
    // Update running max (approximate 90-day max with session max)
    let current_max_raw = MAX_90D_WEI.load(std::sync::atomic::Ordering::Relaxed);
    if value_wei > current_max_raw {
        MAX_90D_WEI.store(value_wei, std::sync::atomic::Ordering::Relaxed);
    }
    let max_eth = MAX_90D_WEI.load(std::sync::atomic::Ordering::Relaxed) as f64 / 1e18;
    let denom = (max_eth + 1.0).log10();
    if denom < 1e-10 { return 0.0; }
    ((eth + 1.0).log10() / denom).clamp(0.0, 1.0)
}

/// Build per-transaction BH entries for every transaction in a block.
/// Returns a TxBhBatch ready to POST to /index/add_tx_bh_batch.
fn build_tx_bh_batch(
    block:      &Value,
    chain:      &EvmChain,
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

        // Extract 4-byte method selector (first 8 hex chars after "0x")
        let selector = if input.len() >= 10 {
            input[2..10].to_string() // skip "0x"
        } else {
            String::new()
        };

        // Classify event type
        let et_byte = if input == "0x" || input.is_empty() {
            // Pure ETH transfer — no contract call
            0u8 // TRANSFER
        } else if input != "0x" && selector.is_empty() {
            11u8 // DEPLOY (contract creation — no to address)
        } else {
            classify_event_type(&selector)
        };

        // Detect MEV: high miner tip relative to base fee
        let max_prio = hex_to_u64(tx["maxPriorityFeePerGas"].as_str().unwrap_or("0x0"));
        let base_fee = hex_to_u64(block["baseFeePerGas"].as_str().unwrap_or("0x1"));
        let mev_ratio = max_prio as f64 / base_fee.max(1) as f64;
        // If MEV ratio > 5× and it's a swap-adjacent call, flag as MEV_CAPTURE
        let et_byte = if mev_ratio > 5.0 && (et_byte == 1 || et_byte == 0) {
            17u8 // MEV_CAPTURE
        } else {
            et_byte
        };

        // magnitude_norm using log10 formula
        let mag = magnitude_norm(value_wei);

        // entity_id = SHA3-256(normalised from_addr) — 32-byte entity routing key
        let entity_id_hex = bh_id(from_addr);

        // Compute canonical 93-byte BH
        let (sense_hex, antisense_hex) = canonical_bh(
            &entity_id_hex,
            et_byte,
            mag,
            0u64,       // context flags (venue/layer — reserved, 0 for now)
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

async fn index_chain(chain: &EvmChain, faiss: &FaissClient, state: &mut IndexerState) -> Result<()> {
    let client = reqwest::Client::builder()
        .timeout(Duration::from_secs(12))
        .build()?;

    let mut rpc_idx = 0usize;

    let rpc0 = chain.rpcs[rpc_idx % chain.rpcs.len()].to_string();
    let latest_hex = with_retry(chain.label, 3, 1000, || {
        let c = client.clone(); let r = rpc0.clone();
        async move {
            let v = eth_rpc(&c, &r, "eth_blockNumber", serde_json::json!([])).await?;
            Ok(v.as_str().unwrap_or("0x0").to_string())
        }
    }).await?;
    let latest = hex_to_u64(&latest_hex);

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

        // Extract block hash and timestamp
        let block_hash = block["hash"].as_str().unwrap_or("0x0000000000000000000000000000000000000000000000000000000000000000");
        let timestamp  = hex_to_u64(block["timestamp"].as_str().unwrap_or("0x0"));

        // ── 1. Block-level 128-dim vector (φ computation) ─────────────────────
        let features  = extract_features(&block);
        let phi       = features.iter().sum::<f64>() / 9.0;
        let entity_id = block_entity_id(chain.label, block_num);
        let block_bh  = bh_id(&entity_id);

        // Dominant event type across this block (for block-level BH metadata)
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

        // Block-level canonical BH using block entity_id and dominant event type
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
                bh_id:          block_sense.clone(),  // use canonical sense as block BH-ID
                block_num,
                chain_id:       chain.chain_id,
                chain_label:    chain.label.to_string(),
                vm_type:        "EVM".to_string(),
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
            vm_type:        "EVM".to_string(),
        };

        match faiss.add_batch(&payload).await {
            Ok(added) => info!("[{}] block={} φ={:.4} added={}", chain.label, block_num, phi, added),
            Err(e)    => warn!("[{}] FAISS ingest failed for block {}: {}", chain.label, block_num, e),
        }

        // ── 2. Per-transaction canonical BH (whitepaper L0.1 §3.1) ──────────
        let tx_batch = build_tx_bh_batch(&block, chain, timestamp, block_num, block_hash);
        let tx_count = tx_batch.entries.len();
        if tx_count > 0 {
            match faiss.add_tx_bh_batch(&tx_batch).await {
                Ok(stored) => info!("[{}] block={} per-tx BHs: {}/{} stored", chain.label, block_num, stored, tx_count),
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

    info!("TRION EVM Rust Indexer — {} chains (parallel), poll={}ms, faiss={}", CHAINS.len(), poll_ms, faiss_url);
    info!("L0.1 per-transaction BH: ENABLED — canonical 93-byte payload + dual-strand SHA3");

    // ── Spawn one independent tokio task per chain ────────────────────────────
    // Each chain runs its own poll loop concurrently — no chain starves another.
    let mut handles = Vec::new();
    for chain in CHAINS {
        let faiss = FaissClient::new(&faiss_url)?;
        let mut state = IndexerState::new(&format!("evm_{}", chain.label.to_lowercase()));
        let chain = *chain;
        let handle = tokio::spawn(async move {
            loop {
                if !faiss.is_healthy().await {
                    warn!("[{}] FAISS not reachable — waiting 5s", chain.label);
                    sleep(Duration::from_secs(5)).await;
                    continue;
                }
                if let Err(e) = index_chain(&chain, &faiss, &mut state).await {
                    error!("[{}] indexer error: {}", chain.label, e);
                }
                sleep(Duration::from_millis(poll_ms)).await;
            }
        });
        handles.push(handle);
    }

    // Wait for all tasks (they loop forever — this blocks until process exits)
    for h in handles {
        let _ = h.await;
    }
    Ok(())
}
