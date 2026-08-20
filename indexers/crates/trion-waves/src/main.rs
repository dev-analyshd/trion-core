//! TRION Waves Indexer — indexes Waves blocks via public node API
use trion_common::faiss::FaissClient;
use trion_common::hash_dna::canonical_bh;
use anyhow::Result;
use serde_json::Value;

const WAVES_API: &str = "https://nodes.wavesnodes.com";
const FAISS_URL: &str = "http://127.0.0.1:8000";
const POLL_INTERVAL_SEC: u64 = 15;

#[tokio::main]
async fn main() -> Result<()> {
    tracing::info!("Starting TRION Waves indexer");
    let faiss = FaissClient::new(FAISS_URL);
    let client = reqwest::Client::new();

    loop {
        match fetch_block_height(&client).await {
            Ok(height) => {
                tracing::info!("Waves height #{} — indexing", height);
                if let Ok(block) = fetch_block(&client, height).await {
                    if let Some(txs) = block.get("transactions").and_then(|v| v.as_array()) {
                        for tx in txs {
                            let sender = tx.get("sender").and_then(|v| v.as_str()).unwrap_or("");
                            let bh = canonical_bh(sender, 0, "0", height, 57, sender);
                            let _ = faiss.add_batch(&[serde_json::json!({
                                "entity_id": sender,
                                "vector": bh.sense_bytes(),
                                "magnitude": 0.5,
                                "chain_id": 57,
                                "vm_type": "WAVES",
                                "sense_hex": bh.sense_hex,
                                "antisense_hex": bh.antisense_hex,
                                "event_type": 0,
                            })]);
                        }
                    }
                }
            }
            Err(e) => tracing::warn!("Waves fetch error: {}", e),
        }
        tokio::time::sleep(std::time::Duration::from_secs(POLL_INTERVAL_SEC)).await;
    }
}

async fn fetch_block_height(client: &reqwest::Client) -> Result<u64> {
    let resp: Value = client.get(format!("{}/blocks/height", WAVES_API)).send().await?.json().await?;
    Ok(resp.get("height").and_then(|v| v.as_u64()).unwrap_or(0))
}

async fn fetch_block(client: &reqwest::Client, height: u64) -> Result<Value> {
    Ok(client.get(format!("{}/blocks/at/{}", WAVES_API, height)).send().await?.json().await?)
}
