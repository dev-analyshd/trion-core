/*!
 * Lightweight indexer state — persists the last-processed block number
 * to a file in /tmp so restarts resume from where they left off.
 */

use anyhow::Result;
use std::path::PathBuf;

pub struct IndexerState {
    path: PathBuf,
}

impl IndexerState {
    /// Create state handle backed by `/tmp/trion_<label>.json`.
    pub fn new(label: &str) -> Self {
        let path = PathBuf::from(format!("/tmp/trion_{}.json", label.to_lowercase()));
        Self { path }
    }

    /// Read the last processed block number (returns 0 if no state file).
    pub fn last_block(&self) -> u64 {
        std::fs::read_to_string(&self.path)
            .ok()
            .and_then(|s| serde_json::from_str::<serde_json::Value>(&s).ok())
            .and_then(|v| v["last_block"].as_u64())
            .unwrap_or(0)
    }

    /// Persist the last processed block number.
    pub fn save(&self, block: u64) -> Result<()> {
        let json = serde_json::json!({ "last_block": block });
        std::fs::write(&self.path, serde_json::to_string(&json)?)?;
        Ok(())
    }
}
