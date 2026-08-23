//! TRION MultiversX Indexer — indexes MultiversX blocks via public API
use trion_common::faiss::FaissClient;
use anyhow::Result;
use serde_json::Value;

const MULTIVERSX_API: &str = "https://api.multiversx.eu";
const FAISS_URL: &str = "http://127.0.0.1:8000";
const POLL_INTERVAL_SEC: u64 = 6;

#[tokio::main]
async fn main() -> Result<()> {
    tracing::info!("Starting TRION MultiversX indexer");
    let faiss = FaissClient::new(FAISS_URL);
    let client = reqwest::Client::new();

    loop {
        match fetch_latest_block(&client).await {
            Ok(block) => {
                tracing::info!("MultiversX block #{} — indexing", block.nonce);
                for tx in &block.transactions {
                    let entity_id = &tx.sender;
                    let bh = trion_common::hash_dna::canonical_bh(entity_id, 0, "0", block.nonce, 1, &tx.receiver);
                    let _ = faiss.add_batch(&[serde_json::json!({
                        "entity_id": entity_id,
                        "vector": bh.sense_bytes(),
                        "magnitude": 0.5,
                        "chain_id": 1,
                        "vm_type": "MULTIVERSX",
                        "sense_hex": bh.sense_hex,
                        "antisense_hex": bh.antisense_hex,
                        "event_type": 0,
                    })]);
                }
            }
            Err(e) => tracing::warn!("MultiversX fetch error: {}", e),
        }
        tokio::time::sleep(std::time::Duration::from_secs(POLL_INTERVAL_SEC)).await;
    }
}

#[derive(serde::Deserialize)]
struct Block {
    nonce: u64,
    transactions: Vec<Transaction>,
}
#[derive(serde::Deserialize)]
struct Transaction {
    sender: String,
    receiver: String,
}

async fn fetch_latest_block(client: &reqwest::Client) -> Result<Block> {
    Ok(client.get(format!("{}/blocks/latest", MULTIVERSX_API))
        .send().await?.json().await?)
}
