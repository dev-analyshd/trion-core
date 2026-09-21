//! shadow_observer.rs — Shadow Observation Protocol for hostile chains
//! Per BTCP Master Implementation Spec §Water Principle 2 extension
//!
//! When a chain goes hostile or breaks, TRION doesn't lose the data.
//! It reconstructs behavioral truth from integrated chains' references.
//! "Bone heals stronger at the break point."

use crate::types::*;
use std::collections::HashMap;

/// Placeholder confidence weight attached to SIMULATED shadow sources.
///
/// PLACEHOLDER: 0.7 is not a calibrated value — it stands in until real
/// shadow-observation confidence calibration (per-chain indexer-quality
/// weighting) is implemented. Only applied to sources fabricated by
/// `collect_shadow_sources` (flagged `simulated: true`).
pub const SIMULATED_SOURCE_CONFIDENCE: f64 = 0.7;

/// Minimum mean shadow-observation confidence required for a hostile
/// chain to pass the Phase-1 rejoin gate (shadow history must become a
/// usable Genesis baseline).
///
/// PLACEHOLDER: no spec constant exists for this gate — 0.5 is a
/// conservative default pending calibration against the rejoin test set.
pub const REJOIN_MIN_CONFIDENCE: f64 = 0.5;

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
    ///
    /// HONEST LIMITATION — SIMULATED DATA: this does NOT read from real
    /// indexers, oracles, DEXs or governance feeds. The event hashes are
    /// fabricated from (hostile_chain, source_chain, index, timestamp) —
    /// placeholder shape only. Every returned source is flagged
    /// `simulated: true` and carries the placeholder confidence
    /// `SIMULATED_SOURCE_CONFIDENCE`; real production data must be
    /// supplied by indexer integration (TODO).
    ///
    /// BTCP-FIX2-S59 (§8.1): the REAL production path lives in the Python
    /// `core/btcp/shadow_observer.py::collect_real_shadow_sources`
    /// which queries the TimescaleDB `akashic_bh` table for events TRION
    /// observed but did NOT emit as published signals (rows whose
    /// `context->>'source' IS NULL`).  Those rows are persisted with
    /// `simulated = false`.  This Rust stub remains the offline reference
    /// path for the unit tests; both paths share the same `compute_shadow_bh`
    /// construction below so the weighted-BH algorithm has parity.
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
                    confidence_weight: SIMULATED_SOURCE_CONFIDENCE,
                    diversity_factor: 1.0 / integrated_chains.len() as f64,
                    source_chain: *chain,
                    simulated: true, // fabricated placeholder data — see doc
                });
            }
        }

        sources
    }

    /// BTCP-FIX2-S59 (§8.1): accept pre-collected REAL shadow sources
    /// (read from a live indexer / akashic_bh feed by the caller) and
    /// wrap them in `ShadowSource` with `simulated = false`.  This lets
    /// downstream consumers (rejoin_hostile_chain, compute_shadow_bh)
    /// operate on real data without re-fabricating sources.
    ///
    /// The Python `core/btcp/shadow_observer.py::collect_real_shadow_sources`
    /// is the production implementation; this Rust entry point exists so
    /// the in-process Rust callers (when wired) can ingest the same feed.
    pub fn collect_shadow_sources_real<I>(&self, real_sources: I) -> Vec<ShadowSource>
    where
        I: IntoIterator<Item = (H256, f64, f64, ChainId)>,
    {
        real_sources
            .into_iter()
            .map(|(event_hash, confidence_weight, diversity_factor, source_chain)| ShadowSource {
                event_hash,
                confidence_weight,
                diversity_factor,
                source_chain,
                simulated: false, // REAL data — caller read from a live feed
            })
            .collect()
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
    /// Phase 1: Shadow history becomes Genesis baseline (gated on mean
    ///          shadow confidence ≥ REJOIN_MIN_CONFIDENCE — rejoin no
    ///          longer succeeds unconditionally)
    /// Phase 2: Native Channel 6 observation begins
    /// Phase 3: Full BTCP integration — N(N-1)/2 new bridge pairs eliminated
    pub fn rejoin_hostile_chain(
        &mut self,
        chain: ChainId,
        num_total_chains: u64,
    ) -> RejoinResult {
        let history = self.get_shadow_history(chain);

        // Mean confidence of recorded shadow observations — the Phase-1
        // gate: a chain whose behavioral truth could not be reconstructed
        // with sufficient confidence has no Genesis baseline to rejoin
        // with, so rejoin FAILS instead of silently succeeding.
        let mean_confidence = history
            .map(|h| {
                if h.is_empty() {
                    0.0
                } else {
                    h.iter().map(|(_, c)| *c).sum::<f64>() / h.len() as f64
                }
            })
            .unwrap_or(0.0);
        let success = mean_confidence >= REJOIN_MIN_CONFIDENCE;

        // Shadow history transferred as behavioral depth foundation.
        // PLACEHOLDER SCALE: depth = count × 100 is an invented unit —
        // real Akashic depth weighting is TODO.
        let shadow_depth = history.map(|h| h.len() as f64 * 100.0).unwrap_or(0.0);

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
            success,
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
                simulated: true,
            },
            ShadowSource {
                event_hash: H256::sha3(b"source_2"),
                confidence_weight: 0.8,
                diversity_factor: 0.5,
                source_chain: 42161,
                simulated: true,
            },
            ShadowSource {
                event_hash: H256::sha3(b"source_3"),
                confidence_weight: 0.6,
                diversity_factor: 0.5,
                source_chain: 10,
                simulated: true,
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
    fn test_collect_shadow_sources_flags_simulated() {
        // Every source fabricated by the placeholder collector must be
        // disclosed as `simulated: true` with the placeholder confidence.
        let observer = ShadowObserver::new();
        let sources = observer.collect_shadow_sources(99999, &[1, 10, 42161]);

        assert_eq!(sources.len(), 15); // 5 per integrated chain
        for source in &sources {
            assert!(source.simulated, "simulated sources must be flagged");
            assert_eq!(source.confidence_weight, SIMULATED_SOURCE_CONFIDENCE);
        }
    }

    #[test]
    fn test_collect_shadow_sources_real_marks_not_simulated() {
        // BTCP-FIX2-S59 (§8.1): real sources ingested via the new entry
        // point must be flagged `simulated: false`.  The Python path
        // (core/btcp/shadow_observer.py::collect_real_shadow_sources)
        // is the production collector; this exercises the Rust-side
        // wrapper that downstream Rust consumers use to ingest the same
        // real feed.
        let observer = ShadowObserver::new();
        let real_sources = vec![
            (H256::sha3(b"real_event_1"), 0.7, 0.5, 1u64),
            (H256::sha3(b"real_event_2"), 0.8, 0.5, 42161u64),
            (H256::sha3(b"real_event_3"), 0.6, 0.5, 10u64),
        ];
        let sources = observer.collect_shadow_sources_real(real_sources);

        assert_eq!(sources.len(), 3);
        for source in &sources {
            assert!(!source.simulated, "real sources must NOT be flagged");
        }
        // compute_shadow_bh works on real sources too — same algorithm.
        let (bh, conf) = observer.compute_shadow_bh(&sources);
        assert_ne!(bh, H256::zero());
        assert!(conf > 0.0);
    }

    #[test]
    fn test_rejoin_hostile_chain() {
        let mut observer = ShadowObserver::new();
        observer.record_shadow(99999, H256::sha3(b"shadow_1"), 0.6);
        observer.record_shadow(99999, H256::sha3(b"shadow_2"), 0.7);

        // Mean confidence (0.6+0.7)/2 = 0.65 ≥ REJOIN_MIN_CONFIDENCE → rejoin succeeds
        let result = observer.rejoin_hostile_chain(99999, 10);

        assert!(result.success);
        assert_eq!(result.chain_id, 99999);
        assert!(result.shadow_depth_transferred > 0.0);
        assert_eq!(result.new_bridge_pairs_eliminated, 45); // 10*9/2
    }

    #[test]
    fn test_rejoin_fails_without_shadow_history() {
        // No shadow history → no Genesis baseline → rejoin must FAIL
        // (previously rejoin always returned success: true).
        let mut observer = ShadowObserver::new();
        let result = observer.rejoin_hostile_chain(99999, 10);
        assert!(!result.success);
        assert_eq!(result.shadow_depth_transferred, 0.0);
    }

    #[test]
    fn test_rejoin_fails_low_confidence_history() {
        // Mean confidence below REJOIN_MIN_CONFIDENCE → rejoin fails
        let mut observer = ShadowObserver::new();
        observer.record_shadow(99999, H256::sha3(b"weak_1"), 0.2);
        observer.record_shadow(99999, H256::sha3(b"weak_2"), 0.3);

        let result = observer.rejoin_hostile_chain(99999, 10);
        assert!(!result.success, "low-confidence history must not rejoin");
    }
}
