/*!
 * TRION Common — shared types, entropy math, FAISS client, and vector builder.
 *
 * Every chain-specific crate links this and only implements the
 * `ChainIndexer` trait.  Common handles:
 *   - Shannon entropy + histogram helpers (whitepaper L1.1)
 *   - 128-dim vector construction (9 entropy features + deterministic padding)
 *   - HashDNA BH-ID generation (L0.1)
 *   - FAISS /index/add_batch HTTP client
 *   - State persistence (last-indexed block/slot/checkpoint to /tmp)
 *   - Exponential back-off retry wrapper
 */

pub mod entropy;
pub mod faiss;
pub mod vector;
pub mod hash_dna;
pub mod living_security;
pub mod state;
pub mod retry;

use anyhow::Result;
use async_trait::async_trait;

// Re-export the most commonly used items at the crate root.
pub use entropy::{shannon_entropy, histogram_entropy, freq_entropy};
pub use faiss::{FaissClient, BatchPayload, VectorEntry, TxBhEntry, TxBhBatch};
pub use vector::build_vector;
pub use hash_dna::{bh_id, block_entity_id, canonical_bh, classify_event_type, event_type_name, hex_to_32bytes, iso8601_to_epoch};
pub use state::IndexerState;
pub use retry::with_retry;

/// Every chain indexer implements this trait.
#[async_trait]
pub trait ChainIndexer: Send + Sync {
    /// Human label shown in logs (e.g. "SUI_MAINNET").
    fn label(&self) -> &str;
    /// TRION internal chain_id.
    fn chain_id(&self) -> u64;
    /// VM family string sent to FAISS (e.g. "SUI", "SVM", "EVM").
    fn vm_type(&self) -> &str;
    /// Poll one unit of work (block / slot / checkpoint).
    /// Returns the block number that was processed (or None on skip).
    async fn poll_once(&mut self, client: &FaissClient) -> Result<Option<u64>>;
}
