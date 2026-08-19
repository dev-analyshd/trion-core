//! shadow_observer.rs — Shadow Observation Protocol for hostile chains
//! Per BTCP Master Implementation Spec §Water Principle 2 extension
//!
//! When a chain goes hostile or breaks, TRION doesn't lose the data.
//! It reconstructs behavioral truth from integrated chains' references.
//! "Bone heals stronger at the break point."

use crate::types::*;
use std::collections::HashMap;

/// Shadow Observer — reconstructs behavioral truth about hostile chains
/// from cross-chain references on integrated chains
#[derive(Debug, Default)]
pub struct ShadowObserver {
    shadow_history: HashMap<ChainId, Vec<(H256, f64)>>, // chain -> [(bh, confidence)]
}

impl ShadowObserver {
    pub fn new() -> Self {
        ShadowObserver {
            shadow_history: HashMap::new(),
        }
    }

    /// Collect shadow sources for a hostile chain
    /// Gathers events referencing hostile_chain from all integrated chains:
    /// - Cross-chain transfers
    /// - Oracle updates citing the chain
    /// - Bridge events
    /// - DEX trades of native token
    /// - Governance references
    pub fn collect_shadow_sources(
        &self,
        hostile_chain: ChainId,
        integrated_chains: &[ChainId],
    ) -> Vec<ShadowSource> {
        let mut sources = Vec::new();

        for chain in integrated_chains {
            // Simulate collecting cross-chain references
            // In production: read from indexers, oracles, DEXs, governance
            for i in 0..5 {
                let event_data = format!(
                    "{}:{}:{}:{}",
                    hostile_chain, chain, i, current_timestamp()
                );
                sources.push(ShadowSource {
                    event_hash: H256::sha3(event_data.as_bytes()),
                    confidence_weight: 0.7,
                    diversity_factor: 1.0 / integrated_chains.len() as f64,
                    source_chain: *chain,
                });
            }
        }

        sources
    }

    /// Compute shadow BH from weighted sources
    /// shadow_hash = Hash_DNA::from_weighted_sources(sources)
    pub fn compute_shadow_bh(&self, sources: &[ShadowSource]) -> (H256, f64) {
        if sources.is_empty() {
            return (H256::zero(), 0.0);
        }

        // Weighted XOR-like combination: hash each source with its weight
        let mut combined = Vec::new();
        let mut total_confidence = 0.0;

        for source in sources {
            let weighted = format!(
                "{}:{:.4}:{:.4}",
                source.event_hash.to_hex(),
                source.confidence_weight,
                source.diversity_factor
            );
            combined.push(weighted);
            total_confidence += source.confidence_weight;
        }

        let combined_hash = H256::sha3(combined.join("|").as_bytes());
        let avg_confidence = total_confidence / sources.len() as f64;

        (combined_hash, avg_confidence)
    }

    /// Reconstruct shadow BH from shadow sources (convenience method)
    pub fn reconstruct_shadow_bh(&self, sources: &[ShadowSource]) -> (H256, f64) {
        self.compute_shadow_bh(sources)
    }

    /// Record shadow observation for a chain
    pub fn record_shadow(&mut self, chain_id: ChainId, bh: H256, confidence: f64) {
        self.shadow_history
            .entry(chain_id)
            .or_default()
            .push((bh, confidence));
    }

    /// Get shadow history for a chain
    pub fn get_shadow_history(&self, chain_id: ChainId) -> Option<&Vec<(H256, f64)>> {
        self.shadow_history.get(&chain_id)
    }

    /// Rejoin sequence when hostile chain requests integration
    /// Phase 1: Shadow history becomes Genesis baseline
    /// Phase 2: Native Channel 6 observation begins
    /// Phase 3: Full BTCP integration — N(N-1)/2 new bridge pairs eliminated
    pub fn rejoin_hostile_chain(
        &mut self,
        chain: ChainId,
        num_total_chains: u64,
    ) -> RejoinResult {
        // Shadow history transferred as behavioral depth foundation
        let shadow_depth = self
            .get_shadow_history(chain)
            .map(|h| h.len() as f64 * 100.0)
            .unwrap_or(0.0);

        // N(N-1)/2 bridge pairs eliminated
        let new_pairs_eliminated = if num_total_chains > 1 {
            num_total_chains * (num_total_chains - 1) / 2
        } else {
            0
        };

        RejoinResult {
            chain_id: chain,
            shadow_depth_transferred: shadow_depth,
            new_bridge_pairs_eliminated: new_pairs_eliminated,
            success: true,
        }
    }
}

fn current_timestamp() -> u64 {
    use std::time::{SystemTime, UNIX_EPOCH};
    SystemTime::now()
        .duration_since(UNIX_EPOCH)
        .map(|d| d.as_secs())
        .unwrap_or(0)
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn test_compute_shadow_bh() {
        let observer = ShadowObserver::new();

        let sources = vec![
            ShadowSource {
                event_hash: H256::sha3(b"source_1"),
                confidence_weight: 0.7,
                diversity_factor: 0.5,
                source_chain: 1,
            },
            ShadowSource {
                event_hash: H256::sha3(b"source_2"),
                confidence_weight: 0.8,
                diversity_factor: 0.5,
                source_chain: 42161,
            },
            ShadowSource {
                event_hash: H256::sha3(b"source_3"),
                confidence_weight: 0.6,
                diversity_factor: 0.5,
                source_chain: 10,
            },
        ];

        let (shadow_hash, confidence) = observer.compute_shadow_bh(&sources);
        assert_ne!(shadow_hash, H256::zero());
        assert!(confidence > 0.0);
        assert!(confidence <= 1.0);
        println!("Shadow BH: {} (conf: {:.2})", shadow_hash, confidence);
    }

    #[test]
    fn test_empty_sources() {
        let observer = ShadowObserver::new();
        let (hash, conf) = observer.compute_shadow_bh(&[]);
        assert_eq!(hash, H256::zero());
        assert_eq!(conf, 0.0);
    }

    #[test]
    fn test_record_and_get_history() {
        let mut observer = ShadowObserver::new();
        let bh = H256::sha3(b"test_shadow");
        observer.record_shadow(99999, bh, 0.65);

        let history = observer.get_shadow_history(99999).unwrap();
        assert_eq!(history.len(), 1);
        assert_eq!(history[0].0, bh);
        assert_eq!(history[0].1, 0.65);
    }

    #[test]
    fn test_rejoin_hostile_chain() {
        let mut observer = ShadowObserver::new();
        observer.record_shadow(99999, H256::sha3(b"shadow_1"), 0.6);
        observer.record_shadow(99999, H256::sha3(b"shadow_2"), 0.7);

        let result = observer.rejoin_hostile_chain(99999, 10);

        assert!(result.success);
        assert_eq!(result.chain_id, 99999);
        assert!(result.shadow_depth_transferred > 0.0);
        assert_eq!(result.new_bridge_pairs_eliminated, 45); // 10*9/2
    }
}
