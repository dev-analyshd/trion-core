//! TRION Hedera Indexer — indexes Hedera blocks via Hashio JSON-RPC
//! Hedera is EVM-compatible (uses standard eth_getBlockByNumber)
use trion_common::faiss::FaissClient;
use trion_common::hash_dna::canonical_bh;
use trion_common::entropy::EntropyFeatures;
use anyhow::Result;
use serde_json::Value;

const HEDERA_RPC: &str = "https://mainnet.hashio.io/api";
const FAISS_URL: &str = "http://127.0.0.1:8000";
const POLL_INTERVAL_SEC: u64 = 5;

#[tokio::main]
async fn main() -> Result<()> {
    tracing::info!("Starting TRION Hedera indexer");
    let faiss = FaissClient::new(FAISS_URL);
    let client = reqwest::Client::new();
    let mut last_block: u64 = 0;

    loop {
        match fetch_latest_block(&client).await {
            Ok(block_num) if block_num > last_block => {
                tracing::info!("Hedera block #{} — indexing", block_num);
                if let Ok(txs) = fetch_block_txs(&client, block_num).await {
                    for tx in txs {
                        let entity_id = tx.get("from").and_then(|v| v.as_str()).unwrap_or("0x0");
                        let to_addr = tx.get("to").and_then(|v| v.as_str()).unwrap_or("0x0");
                        let value = tx.get("value").and_then(|v| v.as_str()).unwrap_or("0x0");
                        let bh = canonical_bh(entity_id, 0, value, block_num, 295, to_addr);
                        let _ = faiss.add_batch(&[serde_json::json!({
                            "entity_id": entity_id,
                            "vector": bh.sense_bytes(),
                            "magnitude": 0.5,
                            "chain_id": 295,
                            "vm_type": "EVM",
                            "sense_hex": bh.sense_hex,
                            "antisense_hex": bh.antisense_hex,
                            "event_type": 0,
                        })]);
                    }
                    tracing::info!("Indexed {} txs from Hedera block {}", txs.len(), block_num);
                }
                last_block = block_num;
            }
            Ok(_) => {}
            Err(e) => tracing::warn!("Hedera fetch error: {}", e),
        }
        tokio::time::sleep(std::time::Duration::from_secs(POLL_INTERVAL_SEC)).await;
    }
}

async fn fetch_latest_block(client: &reqwest::Client) -> Result<u64> {
    let resp: Value = client.post(HEDERA_RPC)
        .json(&serde_json::json!({"jsonrpc":"2.0","method":"eth_blockNumber","params":[],"id":1}))
        .send().await?.json().await?;
    Ok(u64::from_str_radix(
        resp.get("result").and_then(|v| v.as_str()).unwrap_or("0x0").trim_start_matches("0x"), 16
    )?)
}

async fn fetch_block_txs(client: &reqwest::Client, block: u64) -> Result<Vec<Value>> {
    let block_hex = format!("0x{:x}", block);
    let resp: Value = client.post(HEDERA_RPC)
        .json(&serde_json::json!({"jsonrpc":"2.0","method":"eth_getBlockByNumber","params":[block_hex, true],"id":1}))
        .send().await?.json().await?;
    Ok(resp.get("result").and_then(|v| v.get("transactions")).and_then(|v| v.as_array()).cloned().unwrap_or_default())
}
