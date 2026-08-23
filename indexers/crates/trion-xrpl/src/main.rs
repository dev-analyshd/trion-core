//! TRON XRPL Indexer — indexes XRPL (XRP Ledger) ledgers via public rippled API
use trion_common::faiss::FaissClient;
use trion_common::hash_dna::canonical_bh;
use anyhow::Result;
use serde_json::Value;

const XRPL_API: &str = "https://s1.ripple.com:51234";
const FAISS_URL: &str = "http://127.0.0.1:8000";
const POLL_INTERVAL_SEC: u64 = 4;

#[tokio::main]
async fn main() -> Result<()> {
    tracing::info!("Starting TRION XRPL indexer");
    let faiss = FaissClient::new(FAISS_URL);
    let client = reqwest::Client::new();

    loop {
        match fetch_ledger(&client).await {
            Ok(ledger_index) => {
                tracing::info!("XRPL ledger #{} — indexing", ledger_index);
                if let Ok(txs) = fetch_ledger_txs(&client, ledger_index).await {
                    for tx in txs {
                        let account = tx.get("Account").and_then(|v| v.as_str()).unwrap_or("");
                        let dest = tx.get("Destination").and_then(|v| v.as_str()).unwrap_or("");
                        let bh = canonical_bh(account, 0, "0", ledger_index, 0, dest);
                        let _ = faiss.add_batch(&[serde_json::json!({
                            "entity_id": account,
                            "vector": bh.sense_bytes(),
                            "magnitude": 0.5,
                            "chain_id": 0,
                            "vm_type": "XRPL",
                            "sense_hex": bh.sense_hex,
                            "antisense_hex": bh.antisense_hex,
                            "event_type": 0,
                        })]);
                    }
                }
            }
            Err(e) => tracing::warn!("XRPL fetch error: {}", e),
        }
        tokio::time::sleep(std::time::Duration::from_secs(POLL_INTERVAL_SEC)).await;
    }
}

async fn fetch_ledger(client: &reqwest::Client) -> Result<u64> {
    let resp: Value = client.post(XRPL_API)
        .json(&serde_json::json!({"method":"ledger_current","params":[{}]}))
        .send().await?.json().await?;
    Ok(resp.get("result").and_then(|v| v.get("ledger_current_index")).and_then(|v| v.as_u64()).unwrap_or(0))
}

async fn fetch_ledger_txs(client: &reqwest::Client, ledger: u64) -> Result<Vec<Value>> {
    let resp: Value = client.post(XRPL_API)
        .json(&serde_json::json!({"method":"ledger","params":[{"ledger_index": ledger.to_string(), "transactions": true, "expand": true}]}))
        .send().await?.json().await?;
    Ok(resp.get("result").and_then(|v| v.get("ledger")).and_then(|v| v.get("transactions")).and_then(|v| v.as_array()).cloned().unwrap_or_default())
}
