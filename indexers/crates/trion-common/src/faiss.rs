/*!
 * FAISS HTTP client — wraps POST /index/add_batch and POST /index/add_tx_bh_batch.
 *
 * Matches the BatchVectorPayload and TxBhBatchPayload schemas expected by
 * akashic/faiss_service.py.
 */

use anyhow::Result;
use reqwest::Client;
use serde::{Deserialize, Serialize};
use tracing::{debug, warn};

// ── Block-level vector batch ─────────────────────────────────────────────────

/// A single 128-dim vector entry inside a block-level batch payload.
/// One entry per block — aggregates all transactions via entropy features.
#[derive(Debug, Serialize, Deserialize)]
pub struct VectorEntry {
    pub entity_id:        String,
    pub vector:           Vec<f32>,
    pub magnitude:        f64,
    pub entropy:          f64,
    pub timestamp:        f64,
    pub bh_id:            String,
    pub block_num:        u64,
    pub chain_id:         u64,
    pub chain_label:      String,
    pub vm_type:          String,
    #[serde(skip_serializing_if = "Option::is_none")]
    pub funding_source:   Option<String>,
    /// Block hash (hex string) — used in canonical BH computation.
    #[serde(skip_serializing_if = "Option::is_none")]
    pub block_hash_hex:   Option<String>,
    /// Dominant event type for this block (0-19, whitepaper L0.1).
    #[serde(skip_serializing_if = "Option::is_none")]
    pub event_type:       Option<u8>,
    /// Canonical BH sense strand (64 hex chars) — L0.1 dual-strand.
    #[serde(skip_serializing_if = "Option::is_none")]
    pub sense_hex:        Option<String>,
    /// Canonical BH antisense strand (64 hex chars) — L0.1 dual-strand.
    #[serde(skip_serializing_if = "Option::is_none")]
    pub antisense_hex:    Option<String>,
}

/// The full batch payload sent to `/index/add_batch` (one per block).
#[derive(Debug, Serialize)]
pub struct BatchPayload {
    pub vectors:        Vec<VectorEntry>,
    pub block_num:      u64,
    pub block_features: Vec<f64>,
    pub block_phi:      f64,
    pub chain_id:       u64,
    pub chain_label:    String,
    pub vm_type:        String,
}

// ── Per-transaction BH batch ─────────────────────────────────────────────────

/// A single per-transaction BH entry (whitepaper L0.1 exact).
/// Computed for every transaction in a block.
#[derive(Debug, Serialize, Deserialize, Clone)]
pub struct TxBhEntry {
    /// EVM transaction hash (0x-prefixed, 66 chars).
    pub tx_hash:        String,
    /// Sender address (0x-prefixed).
    pub from_addr:      String,
    /// Receiver address or contract (0x-prefixed).
    pub to_addr:        String,
    /// Canonical whitepaper EventType byte (0-19).
    pub event_type:     u8,
    /// EventType name string (e.g. "SWAP").
    pub event_type_name: String,
    /// BH entity_id = bh_id(from_addr) — SHA3-256 of normalised sender.
    pub entity_id:      String,
    /// magnitude_norm = log10(wei_value/1e18 + 1) / log10(max_90d + 1) in [0,1].
    pub magnitude_norm: f64,
    /// Raw value in wei (as string to avoid u64 overflow).
    pub value_wei:      String,
    /// Method selector (first 4 bytes of input, 8 hex chars).
    pub selector:       String,
    /// Unix timestamp of the block.
    pub timestamp:      u64,
    /// Chain ID.
    pub chain_id:       u64,
    /// Chain label string.
    pub chain_label:    String,
    /// Block number.
    pub block_num:      u64,
    /// Block hash (0x-prefixed).
    pub block_hash:     String,
    /// Canonical BH sense strand (64 hex chars) — SHA3-256(93-byte payload || 0x00).
    pub sense_hex:      String,
    /// Canonical BH antisense strand (64 hex chars).
    pub antisense_hex:  String,
}

/// Batch of per-transaction BH entries — one per block, sent to
/// `POST /index/add_tx_bh_batch`.
#[derive(Debug, Serialize)]
pub struct TxBhBatch {
    pub chain_id:    u64,
    pub chain_label: String,
    pub block_num:   u64,
    pub block_hash:  String,
    pub timestamp:   u64,
    pub entries:     Vec<TxBhEntry>,
}

// ── Response types ───────────────────────────────────────────────────────────

/// Response from FAISS add_batch (partial — we only care about `added`).
#[derive(Debug, Deserialize)]
pub struct BatchResponse {
    pub added: Option<u64>,
    pub total: Option<u64>,
}

/// Response from FAISS add_tx_bh_batch.
#[derive(Debug, Deserialize)]
pub struct TxBhResponse {
    pub stored: Option<u64>,
}

// ── FaissClient ──────────────────────────────────────────────────────────────

/// Async FAISS HTTP client.  Cheap to clone.
#[derive(Clone)]
pub struct FaissClient {
    client:   Client,
    base_url: String,
    /// X-API-Key for the FAISS service (SEC-01).  Resolved once from the
    /// `FAISS_API_KEY` env var at construction; `None` (var unset/empty)
    /// sends no header — reads against a fail-closed service keep working,
    /// writes are refused there, which is the safe posture.
    api_key:  Option<String>,
}

impl FaissClient {
    pub fn new(base_url: &str) -> Result<Self> {
        let client = Client::builder()
            .timeout(std::time::Duration::from_secs(20))
            .build()?;
        let api_key = std::env::var("FAISS_API_KEY")
            .map(|k| k.trim().to_string())
            .ok()
            .filter(|k| !k.is_empty());
        Ok(Self {
            client,
            base_url: base_url.trim_end_matches('/').to_string(),
            api_key,
        })
    }

    /// POST a block-level vector batch to /index/add_batch.
    /// Returns number of vectors added.
    pub async fn add_batch(&self, payload: &BatchPayload) -> Result<u64> {
        let url = format!("{}/index/add_batch", self.base_url);
        let mut req = self.client.post(&url).json(payload);
        if let Some(ref key) = self.api_key {
            req = req.header("X-API-Key", key.as_str());
        }
        let resp = req.send().await?;

        if !resp.status().is_success() {
            let status = resp.status();
            let body = resp.text().await.unwrap_or_default();
            warn!("FAISS add_batch HTTP {} — {}", status, &body[..body.len().min(200)]);
            return Err(anyhow::anyhow!("FAISS HTTP {}", status));
        }

        let r: BatchResponse = resp.json().await?;
        let added = r.added.unwrap_or(0);
        let total = r.total.unwrap_or(0);
        debug!("FAISS add_batch → added={} total={}", added, total);
        Ok(added)
    }

    /// POST per-transaction canonical BH entries to /index/add_tx_bh_batch.
    /// Returns number of BH records stored.
    /// Non-fatal — errors are logged but do not abort block processing.
    pub async fn add_tx_bh_batch(&self, batch: &TxBhBatch) -> Result<u64> {
        if batch.entries.is_empty() {
            return Ok(0);
        }
        let url = format!("{}/index/add_tx_bh_batch", self.base_url);
        let mut req = self.client.post(&url).json(batch);
        if let Some(ref key) = self.api_key {
            req = req.header("X-API-Key", key.as_str());
        }
        let resp = req.send().await?;

        if !resp.status().is_success() {
            let status = resp.status();
            let body = resp.text().await.unwrap_or_default();
            warn!("FAISS add_tx_bh_batch HTTP {} — {}", status, &body[..body.len().min(200)]);
            return Err(anyhow::anyhow!("FAISS add_tx_bh HTTP {}", status));
        }

        let r: TxBhResponse = resp.json().await?;
        Ok(r.stored.unwrap_or(0))
    }

    /// Health check — returns true when FAISS is reachable.
    pub async fn is_healthy(&self) -> bool {
        let url = format!("{}/health", self.base_url);
        self.client.get(&url).send().await
            .map(|r| r.status().is_success())
            .unwrap_or(false)
    }
}
