//! TRION Vechain Indexer — indexes Vechain blocks via public RPC
use trion_common::faiss::FaissClient;
use trion_common::hash_dna::canonical_bh;
use anyhow::Result;
use serde_json::Value;

const VECHAIN_RPC: &str = "https://mainnet.vechain.org";
const FAISS_URL: &str = "http://127.0.0.1:8000";
const POLL_INTERVAL_SEC: u64 = 10;

#[tokio::main]
async fn main() -> Result<()> {
    tracing::info!("Starting TRION Vechain indexer");
    let faiss = FaissClient::new(FAISS_URL);
    let client = reqwest::Client::new();

    loop {
        match fetch_latest_block(&client).await {
            Ok(block) => {
                tracing::info!("Vechain block #{} — indexing", block.id);
                for tx in &block.transactions {
                    let entity_id = &tx.origin;
                    let bh = canonical_bh(entity_id, 0, "0", block.id, 39, &tx.clauses.get(0).map(|c| c.to.clone()).unwrap_or_default());
                    let _ = faiss.add_batch(&[serde_json::json!({
                        "entity_id": entity_id,
                        "vector": bh.sense_bytes(),
                        "magnitude": 0.5,
                        "chain_id": 39,
                        "vm_type": "EVM",
                        "sense_hex": bh.sense_hex,
                        "antisense_hex": bh.antisense_hex,
                        "event_type": 0,
                    })]);
                }
            }
            Err(e) => tracing::warn!("Vechain fetch error: {}", e),
        }
        tokio::time::sleep(std::time::Duration::from_secs(POLL_INTERVAL_SEC)).await;
    }
}

#[derive(serde::Deserialize)]
struct Block { id: u64, transactions: Vec<Transaction> }
#[derive(serde::Deserialize)]
struct Transaction { origin: String, clauses: Vec<Clause> }
#[derive(serde::Deserialize)]
struct Clause { to: String }

async fn fetch_latest_block(client: &reqwest::Client) -> Result<Block> {
    Ok(client.get(format!("{}/blocks/best", VECHAIN_RPC))
        .send().await?.json().await?)
}
