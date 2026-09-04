//! blo_scheduler.rs — BRT intent scheduling, optimal window calculation
//! Per BTCP Master Implementation Spec §Water Principle 5
//!
//! Water finding cracks in time: non-urgent intents wait for biological
//! rhythm optima. Finds intersection of:
//! circadian_low_window ∩ NL_peak_window ∩ MEV_valley_window

use crate::types::*;

/// BLO Scheduler — Behavioral Limit Order scheduling
/// Uses Biological Rhythm Timer (BRT) to find optimal execution windows
#[derive(Debug, Default)]
pub struct BLOScheduler;

impl BLOScheduler {
    pub fn new() -> Self {
        BLOScheduler
    }

    /// Find optimal execution window using BRT
    /// Returns the optimal block offset from now
    pub fn find_optimal_window(
        &self,
        circadian_low_hours: &[u32],
        nl_peak_hours: &[u32],
        mev_valley_hours: &[u32],
    ) -> Vec<u32> {
        // Find intersection of all three windows
        let mut optimal = Vec::new();

        for &hour in circadian_low_hours {
            if nl_peak_hours.contains(&hour) && mev_valley_hours.contains(&hour) {
                optimal.push(hour);
            }
        }

        if optimal.is_empty() {
            // Fallback: just circadian low
            optimal = circadian_low_hours.to_vec();
        }

        optimal
    }

    /// Compute optimal delay in blocks based on BRT phase
    /// Circadian phase 0.0-1.0 indicates position in daily cycle
    pub fn compute_optimal_delay(
        &self,
        circadian_phase: f64,
        current_gas_gwei: f64,
    ) -> u64 {
        // If circadian phase is near low point (~0.3-0.5 for many entities),
        // and gas is reasonable, execute now
        let in_optimal_phase = circadian_phase >= 0.25 && circadian_phase <= 0.55;

        if in_optimal_phase && current_gas_gwei < 50.0 {
            return 0; // Execute now
        }

        // Otherwise delay to next optimal window
        // Rough estimate: 12 seconds per block, delay to next circadian low
        let blocks_per_hour = 300; // ~12s blocks
        let hours_to_low = if circadian_phase < 0.3 {
            (0.3 - circadian_phase) * 24.0
        } else {
            (1.0 - circadian_phase + 0.3) * 24.0
        };

        (hours_to_low * blocks_per_hour as f64) as u64
    }

    /// Create a Behavioral Limit Order
    pub fn create_blo(
        &self,
        entity_id: BEOId,
        intent: Intent,
        expiry_block: u64,
    ) -> BehavioralLimitOrder {
        let commitment = H256::sha3(
            format!(
                "{}:{}:{}:{}",
                entity_id.to_hex(),
                intent.hash().to_hex(),
                expiry_block,
                intent.nonce
            )
            .as_bytes(),
        );

        BehavioralLimitOrder {
            commitment,
            entity_id,
            intent,
            expiry_block,
            status: BLOStatus::Open,
            filled_amount: 0,
        }
    }

    /// Check if BLO has expired
    pub fn is_expired(&self, blo: &BehavioralLimitOrder, current_block: u64) -> bool {
        current_block > blo.expiry_block && blo.status == BLOStatus::Open
    }

    /// Record partial fill on BLO
    pub fn record_partial_fill(
        &self,
        blo: &mut BehavioralLimitOrder,
        fill_amount: u128,
    ) {
        blo.filled_amount += fill_amount;
        if blo.filled_amount >= blo.intent.amount_in {
            blo.status = BLOStatus::Filled;
        } else {
            blo.status = BLOStatus::PartiallyFilled;
        }
    }
}

#[cfg(test)]
mod tests {
    use super::*;

    fn create_test_intent() -> Intent {
        Intent {
            intent_id: H256::zero(),
            entity_id: H256::sha3(b"entity"),
            source_address: "0x1234".to_string(),
            dest_address: "0x5678".to_string(),
            source_chain: 42161,
            dest_chain: 900,
            asset_in: "ETH".to_string(),
            asset_out: "SOL".to_string(),
            amount_in: 1_000_000_000_000_000_000u128,
            intent_type: "SWAP".to_string(),
            deadline: 1787141851,
            nonce: 42,
            constraints: IntentConstraints::default(),
            btcp_version: SemVer::new(1, 0, 0),
        }
    }

    #[test]
    fn test_find_optimal_window() {
        let scheduler = BLOScheduler::new();

        // Perfect alignment: hour 3 is in all three windows
        let optimal = scheduler.find_optimal_window(&[3, 4], &[2, 3], &[3, 4, 5]);
        assert_eq!(optimal, vec![3]);

        // No intersection → fallback to circadian low
        let optimal2 = scheduler.find_optimal_window(&[3, 4], &[6, 7], &[9, 10]);
        assert_eq!(optimal2, vec![3, 4]);
    }

    #[test]
    fn test_compute_optimal_delay_execute_now() {
        let scheduler = BLOScheduler::new();
        let delay = scheduler.compute_optimal_delay(0.35, 30.0); // Good phase, low gas
        assert_eq!(delay, 0);
    }

    #[test]
    fn test_compute_optimal_delay_wait() {
        let scheduler = BLOScheduler::new();
        let delay = scheduler.compute_optimal_delay(0.8, 100.0); // Bad phase, high gas
        assert!(delay > 0);
        println!("Optimal delay: {} blocks", delay);
    }

    #[test]
    fn test_create_blo() {
        let scheduler = BLOScheduler::new();
        let entity = H256::sha3(b"entity");
        let intent = create_test_intent();

        let blo = scheduler.create_blo(entity, intent, 18001000);

        assert_ne!(blo.commitment, H256::zero());
        assert_eq!(blo.status, BLOStatus::Open);
        assert_eq!(blo.filled_amount, 0);
        assert_eq!(blo.expiry_block, 18001000);
    }

    #[test]
    fn test_partial_fill() {
        let scheduler = BLOScheduler::new();
        let entity = H256::sha3(b"entity");
        let intent = create_test_intent();
        let mut blo = scheduler.create_blo(entity, intent, 18001000);

        scheduler.record_partial_fill(&mut blo, 500_000_000_000_000_000u128);
        assert_eq!(blo.status, BLOStatus::PartiallyFilled);
        assert_eq!(blo.filled_amount, 500_000_000_000_000_000u128);

        // Fill the rest
        scheduler.record_partial_fill(&mut blo, 500_000_000_000_000_000u128);
        assert_eq!(blo.status, BLOStatus::Filled);
    }

    #[test]
    fn test_blo_expiry() {
        let scheduler = BLOScheduler::new();
        let entity = H256::sha3(b"entity");
        let intent = create_test_intent();
        let blo = scheduler.create_blo(entity, intent, 18001000);

        assert!(!scheduler.is_expired(&blo, 18000000)); // Before expiry
        assert!(scheduler.is_expired(&blo, 18002000)); // After expiry
    }
}
