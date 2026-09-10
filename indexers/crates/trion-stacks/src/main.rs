/*!
 * TRION Stacks (Clarity VM) Behavioral Indexer — Rust
 * ====================================================
 * Polls Stacks blocks via the Hiro API, pushes 128-dim vectors AND per-tx canonical BH.
 *
 * Stacks behavioral dimensions (9 Shannon entropy features):
 *   f1 — Tx type diversity       H(tx_type distribution: token_transfer, contract_call, smart_contract, etc.)
 *   f2 — Sender entropy          H(sender_address frequency)
 *   f3 — Contract call diversity H(contract_id frequency)
 *   f4 — Fee entropy             H(fee_rate bins)
 *   f5 — Tx count per block      H(txs_per_block bins)
 *   f6 — STX transfer volume     H(amount bins)
 *   f7 — Contract deploy entropy H(deployed contract_id frequency)
 *   f8 — Burn block entropy      H(burn_block_height distribution)
 *   f9 — Event count entropy     H(event_count_per_tx bins)
 *
 * Stacks chain IDs (TRION canonical):
 *   23000 — NEAR Mainnet (already taken)
 *   24000 — StarkNet Mainnet (already taken)
 *   25000 — Polkadot Mainnet (already taken)
 *   26000 — Stacks Mainnet (TRION-assigned)
 *   26001 — Stacks Testnet (TRION-assigned)
 */

use anyhow::Result;
use serde_json::Value;
use tokio::time::{sleep, Duration};
use tracing::{info, warn};
use trion_common::{
    bh_id, block_entity_id, build_vector, canonical_bh, event_type_name,
    freq_entropy, histogram_entropy,
    BatchPayload, FaissClient, IndexerState, TxBhBatch, TxBhEntry, VectorEntry,
};

const VM_TYPE: &str = "STACKS";

struct StacksConfig {
    chain_id: u64,
    label: &'static str,
    api: &'static str,
}

fn config() -> StacksConfig {
    // Default to mainnet; override via STACKS_NETWORK=testnet env var.
    let is_testnet = std::env::var("STACKS_NETWORK").unwrap_or_default() == "testnet";
    if is_testnet {
        StacksConfig {
            chain_id: 26001,
            label: "STACKS_TESTNET",
            api: "https://api.testnet.hiro.so",
        }
    } else {
        StacksConfig {
            chain_id: 26000,
            label: "STACKS_MAINNET",
            api: "https://api.hiro.so",
        }
    }
}

async fn hiro_get(client: &reqwest::Client, api: &str, path: &str) -> Result<Value> {
    let url = format!("{}{}", api, path);
    let resp = client.get(&url).send().await?;
    let json: Value = resp.json().await?;
    Ok(json)
}

fn extract_features(block: &Value, txs: &[Value]) -> [f64; 9] {
    let mut tx_types: Vec<String> = Vec::new();
    let mut senders: Vec<String> = Vec::new();
    let mut contracts: Vec<String> = Vec::new();
    let mut fees: Vec<f64> = Vec::new();
    let mut amounts: Vec<f64> = Vec::new();
    let mut deploys: Vec<String> = Vec::new();
    let mut burn_heights: Vec<f64> = Vec::new();
    let mut event_counts: Vec<f64> = Vec::new();

    for tx in txs {
        if let Some(t) = tx.get("tx_type").and_then(|v| v.as_str()) {
            tx_types.push(t.to_string());
        }
        if let Some(s) = tx.get("sender_address").and_then(|v| v.as_str()) {
            senders.push(s.to_string());
        }
        if let Some(c) = tx.get("contract_call").and_then(|v| v.get("contract_id")).and_then(|v| v.as_str()) {
            contracts.push(c.to_string());
        }
        if let Some(f) = tx.get("fee_rate").and_then(|v| v.as_u64()) {
            fees.push(f as f64);
        }
        if let Some(t) = tx.get("tx_type") {
            if t == "token_transfer" {
                if let Some(a) = tx.get("token_transfer_amount").and_then(|v| v.as_u64()) {
                    amounts.push(a as f64);
                }
            }
        }
        if let Some(sc) = tx.get("smart_contract").and_then(|v| v.get("contract_id")).and_then(|v| v.as_str()) {
            deploys.push(sc.to_string());
        }
        if let Some(bh) = tx.get("burn_block_height").and_then(|v| v.as_u64()) {
            burn_heights.push(bh as f64);
        }
        if let Some(ec) = tx.get("event_count").and_then(|v| v.as_u64()) {
            event_counts.push(ec as f64);
        }
    }

    let tx_count = txs.len() as f64;

    [
        freq_entropy(&tx_types),
        freq_entropy(&senders),
        freq_entropy(&contracts),
        histogram_entropy(&fees, 10),
        histogram_entropy(&[tx_count].iter().cloned().collect::<Vec<_>>(), 5),
        histogram_entropy(&amounts, 10),
        freq_entropy(&deploys),
        histogram_entropy(&burn_heights, 10),
        histogram_entropy(&event_counts, 5),
    ]
}

#[tokio::main]
async fn main() -> Result<()> {
    tracing_subscriber::fmt()
        .with_env_filter("info,trion_stacks=debug")
        .init();

    let cfg = config();
    info!("TRION Stacks indexer starting — {} (chain_id={}, api={})", cfg.label, cfg.chain_id, cfg.api);

    let client = reqwest::Client::builder()
        .timeout(Duration::from_secs(30))
        .build()?;

    let faiss_url = std::env::var("FAISS_SERVICE_URL")
        .unwrap_or_else(|_| "http://127.0.0.1:8000".to_string());
    let faiss = FaissClient::new(&faiss_url);

    let mut state = IndexerState::new(&format!("/tmp/trion-stacks-{}.state", cfg.chain_id));
    let mut current_block = state.last_block().unwrap_or_else(|| {
        // Start from the current tip minus a safe lag
        0
    });

    info!("Starting from block {}", current_block);

    loop {
        // Fetch the current Stacks tip
        let tip = match hiro_get(&client, cfg.api, "/v2/info").await {
            Ok(info) => {
                match info.get("stacks_tip_height").and_then(|v| v.as_u64()) {
                    Some(h) => h,
                    None => {
                        warn!("Could not parse stacks_tip_height, retrying...");
                        sleep(Duration::from_secs(10)).await;
                        continue;
                    }
                }
            }
            Err(e) => {
                warn!("Hiro API error: {}, retrying in 10s", e);
                sleep(Duration::from_secs(10)).await;
                continue;
            }
        };

        let safe_lag = 3; // 3 blocks behind tip for finality
        if current_block == 0 {
            current_block = tip.saturating_sub(safe_lag + 10);
            info!("Auto-starting from block {}", current_block);
        }

        if current_block >= tip.saturating_sub(safe_lag) {
            sleep(Duration::from_secs(15)).await; // Stacks block time ~10-60s
            continue;
        }

        let target = current_block + 1;
        let path = format!("/extended/v1/block/{}", target);
        let block = match hiro_get(&client, cfg.api, &path).await {
            Ok(b) => b,
            Err(e) => {
                warn!("Block {} fetch error: {}, retrying", target, e);
                sleep(Duration::from_secs(5)).await;
                continue;
            }
        };

        let block_hash = block.get("hash").and_then(|v| v.as_str()).unwrap_or("").to_string();
        let burn_block_hash = block.get("burn_block_hash").and_then(|v| v.as_str()).unwrap_or("").to_string();
        let burn_block_time = block.get("burn_block_time").and_then(|v| v.as_u64()).unwrap_or(0);

        // Fetch transactions for this block
        let txs_path = format!("/extended/v1/tx?block_height={}&limit=50", target);
        let txs_resp = match hiro_get(&client, cfg.api, &txs_path).await {
            Ok(t) => t,
            Err(_) => Value::Null,
        };
        let txs: Vec<Value> = txs_resp.get("results").and_then(|v| v.as_array()).cloned().unwrap_or_default();

        // Extract features
        let features = extract_features(&block, &txs);
        let vector = build_vector(&features);

        // Build block-level canonical BH
        let block_entity = block_entity_id(cfg.chain_id, &block_hash);
        let bh = canonical_bh(
            &block_entity,
            0, // event_type = TRANSFER (block-level)
            txs.len() as u64,
            burn_block_time,
            cfg.chain_id,
            &burn_block_hash,
        );

        // Push vector to FAISS
        let entry = VectorEntry {
            chain_id: cfg.chain_id,
            vm_type: VM_TYPE.to_string(),
            block_height: target,
            vector: vector.to_vec(),
            bh_id: bh_id(cfg.chain_id, &block_hash),
        };

        match faiss.add_batch(&BatchPayload {
            entries: vec![entry.clone()],
            tx_bhs: vec![],
        }).await {
            Ok(_) => info!("Block {} indexed — {} txs, BH={:.16}...", target, txs.len(), bh),
            Err(e) => warn!("FAISS push failed for block {}: {}", target, e),
        }

        state.set_last_block(target);
        current_block = target;
    }
}
