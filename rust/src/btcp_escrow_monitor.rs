//! btcp_escrow_monitor.rs — Watch BTCP_ESCROW state, trigger release/revert
//! Per BTCP Master Implementation Spec §Phase 2
//!
//! Watches escrow contracts on both chains. On proof verification,
//! triggers atomic release. On timeout, triggers revert.

use crate::types::*;
use std::collections::HashMap;
use std::time::{SystemTime, UNIX_EPOCH};

/// Escrow state
#[derive(Debug, Clone, Copy, PartialEq, Eq)]
pub enum EscrowState {
    Holding,
    Released,
    Reverted,
    Disputed,
}

/// Revert reason
#[derive(Debug, Clone, Copy, PartialEq, Eq)]
pub enum RevertReason {
    Timeout,
    ProofInvalid,
    DisputeLost,
    ChainOutage,
    EntityCancel,
}

/// Escrow record
#[derive(Debug, Clone)]
pub struct Escrow {
    pub escrow_id: H256,
    pub entity_id: BEOId,
    pub amount: u128,
    pub chain_id: ChainId,
    pub counterparty: Option<BEOId>,
    pub timeout_blocks: u64,
    pub created_block: u64,
    pub state: EscrowState,
    pub created_at: u64,
    pub akashic_recovery_seconds: u64,
    pub emergency_escape_seconds: u64,
}

/// Escrow Monitor — tracks dual-chain escrow states
#[derive(Debug, Default)]
pub struct EscrowMonitor {
    escrows: HashMap<H256, Escrow>,
    route_to_escrows: HashMap<H256, (H256, H256)>, // route_id -> (escrow_a, escrow_b)
}

/// Default constants per spec
pub const AKASHIC_RECOVERY_SECONDS: u64 = 86400; // 24 hours
pub const EMERGENCY_ESCAPE_SECONDS: u64 = 604800; // 7 days

impl EscrowMonitor {
    pub fn new() -> Self {
        EscrowMonitor {
            escrows: HashMap::new(),
            route_to_escrows: HashMap::new(),
        }
    }

    /// Create a new escrow record.
    ///
    /// `created_block` MUST be the chain height at which the escrow was
    /// locked (observed from the chain, not a default). The previous
    /// version hardcoded 0, which made every escrow instantly "timed out"
    /// at real chain heights (millions) — a P0 correctness bug.
    pub fn create_escrow(
        &mut self,
        escrow_id: H256,
        entity_id: BEOId,
        amount: u128,
        chain_id: ChainId,
        timeout_blocks: u64,
        created_block: u64,
    ) -> Escrow {
        let now = current_timestamp();
        let escrow = Escrow {
            escrow_id,
            entity_id,
            amount,
            chain_id,
            counterparty: None,
            timeout_blocks,
            created_block,
            state: EscrowState::Holding,
            created_at: now,
            akashic_recovery_seconds: AKASHIC_RECOVERY_SECONDS,
            emergency_escape_seconds: EMERGENCY_ESCAPE_SECONDS,
        };
        self.escrows.insert(escrow_id, escrow.clone());
        escrow
    }

    /// Link two escrows to a route
    pub fn link_escrows_to_route(
        &mut self,
        route_id: H256,
        escrow_a: H256,
        escrow_b: H256,
    ) {
        self.route_to_escrows.insert(route_id, (escrow_a, escrow_b));
    }

    /// Release escrow (on valid BTCP proof)
    pub fn release_escrow(&mut self, escrow_id: &H256) -> EscrowState {
        if let Some(escrow) = self.escrows.get_mut(escrow_id) {
            if escrow.state == EscrowState::Holding {
                escrow.state = EscrowState::Released;
            }
            return escrow.state;
        }
        EscrowState::Reverted
    }

    /// Revert escrow (on timeout, invalid proof, or dispute)
    pub fn revert_escrow(
        &mut self,
        escrow_id: &H256,
        reason: RevertReason,
    ) -> EscrowState {
        if let Some(escrow) = self.escrows.get_mut(escrow_id) {
            if escrow.state == EscrowState::Holding
                || escrow.state == EscrowState::Disputed
            {
                escrow.state = EscrowState::Reverted;
            }
            return escrow.state;
        }
        EscrowState::Reverted
    }

    /// Check if escrow has timed out
    pub fn is_timed_out(&self, escrow_id: &H256, current_block: u64) -> bool {
        self.escrows
            .get(escrow_id)
            .map(|e| {
                current_block > e.created_block + e.timeout_blocks
                    && e.state == EscrowState::Holding
            })
            .unwrap_or(false)
    }

    /// Get escrow by ID
    pub fn get_escrow(&self, escrow_id: &H256) -> Option<&Escrow> {
        self.escrows.get(escrow_id)
    }

    /// Get escrows for a route
    pub fn get_route_escrows(&self, route_id: &H256) -> Option<(&Escrow, &Escrow)> {
        self.route_to_escrows.get(route_id).and_then(|(a, b)| {
            let escrow_a = self.escrows.get(a)?;
            let escrow_b = self.escrows.get(b)?;
            Some((escrow_a, escrow_b))
        })
    }

    /// Process timeouts for all escrows
    pub fn process_timeouts(&mut self, current_block: u64) -> Vec<H256> {
        let mut reverted = Vec::new();
        let ids: Vec<H256> = self.escrows.keys().cloned().collect();

        for id in ids {
            if self.is_timed_out(&id, current_block) {
                self.revert_escrow(&id, RevertReason::Timeout);
                reverted.push(id);
            }
        }
        reverted
    }

    /// Dual-chain atomic release — releases both escrows or neither
    pub fn atomic_release(&mut self, route_id: &H256) -> bool {
        // Clone IDs first to avoid borrow checker conflict
        let ids = self.route_to_escrows.get(route_id).cloned();
        if let Some((escrow_a_id, escrow_b_id)) = ids {
            // Verify both are in Holding state before releasing either
            let a_ready = self
                .escrows
                .get(&escrow_a_id)
                .map(|e| e.state == EscrowState::Holding)
                .unwrap_or(false);
            let b_ready = self
                .escrows
                .get(&escrow_b_id)
                .map(|e| e.state == EscrowState::Holding)
                .unwrap_or(false);

            if a_ready && b_ready {
                self.release_escrow(&escrow_a_id);
                self.release_escrow(&escrow_b_id);
                return true;
            }
        }
        false
    }

    /// Get all escrows
    pub fn all_escrows(&self) -> Vec<&Escrow> {
        self.escrows.values().collect()
    }

    /// Get escrows by state
    pub fn escrows_by_state(&self, state: EscrowState) -> Vec<&Escrow> {
        self.escrows
            .values()
            .filter(|e| e.state == state)
            .collect()
    }
}

fn current_timestamp() -> u64 {
    SystemTime::now()
        .duration_since(UNIX_EPOCH)
        .map(|d| d.as_secs())
        .unwrap_or(0)
}

#[cfg(test)]
mod tests {
    use super::*;

    fn create_test_escrow(monitor: &mut EscrowMonitor, chain: ChainId) -> H256 {
        let id = H256::sha3(format!("escrow_{}", chain).as_bytes());
        monitor.create_escrow(
            id,
            H256::sha3(b"entity"),
            1_000_000_000_000_000_000u128,
            chain,
            100,
            0, // test chain height baseline (explicitly passed)
        );
        id
    }

    #[test]
    fn test_create_and_get_escrow() {
        let mut monitor = EscrowMonitor::new();
        let id = create_test_escrow(&mut monitor, 42161);

        let escrow = monitor.get_escrow(&id).unwrap();
        assert_eq!(escrow.chain_id, 42161);
        assert_eq!(escrow.state, EscrowState::Holding);
        assert_eq!(escrow.akashic_recovery_seconds, AKASHIC_RECOVERY_SECONDS);
    }

    #[test]
    fn test_release_escrow() {
        let mut monitor = EscrowMonitor::new();
        let id = create_test_escrow(&mut monitor, 42161);

        let state = monitor.release_escrow(&id);
        assert_eq!(state, EscrowState::Released);

        let escrow = monitor.get_escrow(&id).unwrap();
        assert_eq!(escrow.state, EscrowState::Released);
    }

    #[test]
    fn test_revert_escrow() {
        let mut monitor = EscrowMonitor::new();
        let id = create_test_escrow(&mut monitor, 42161);

        let state = monitor.revert_escrow(&id, RevertReason::Timeout);
        assert_eq!(state, EscrowState::Reverted);
    }

    #[test]
    fn test_timeout_detection() {
        let mut monitor = EscrowMonitor::new();
        let id = create_test_escrow(&mut monitor, 42161);

        // Not timed out yet
        assert!(!monitor.is_timed_out(&id, 50));

        // Timed out
        assert!(monitor.is_timed_out(&id, 150));
    }

    #[test]
    fn test_created_block_from_real_chain_height() {
        // Regression: created_block used to be hardcoded 0, so escrows
        // locked at real chain heights (e.g. Arbitrum ~200M) were instantly
        // "timed out". Timeout math must anchor to the observed height.
        let mut monitor = EscrowMonitor::new();
        let id = H256::sha3(b"escrow_real_height");
        monitor.create_escrow(
            id,
            H256::sha3(b"entity"),
            1_500_000_000_000_000_000u128,
            42161,
            100,       // 100-block timeout
            200_000_000, // locked at Arbitrum height 200M
        );

        // Just after locking — NOT timed out
        assert!(!monitor.is_timed_out(&id, 200_000_050));
        // After timeout window — timed out
        assert!(monitor.is_timed_out(&id, 200_000_101));
        // process_timeouts at the lock height must revert nothing
        assert!(monitor.process_timeouts(200_000_050).is_empty());
    }

    #[test]
    fn test_atomic_release() {
        let mut monitor = EscrowMonitor::new();
        let route_id = H256::sha3(b"route_1");
        let escrow_a = create_test_escrow(&mut monitor, 42161);
        let escrow_b = create_test_escrow(&mut monitor, 900);

        monitor.link_escrows_to_route(route_id, escrow_a, escrow_b);

        let success = monitor.atomic_release(&route_id);
        assert!(success);

        let (a, b) = monitor.get_route_escrows(&route_id).unwrap();
        assert_eq!(a.state, EscrowState::Released);
        assert_eq!(b.state, EscrowState::Released);
    }

    #[test]
    fn test_process_timeouts() {
        let mut monitor = EscrowMonitor::new();
        let id1 = create_test_escrow(&mut monitor, 42161);
        let id2 = create_test_escrow(&mut monitor, 900);

        let reverted = monitor.process_timeouts(150);
        assert_eq!(reverted.len(), 2);
        assert!(reverted.contains(&id1));
        assert!(reverted.contains(&id2));
    }

    #[test]
    fn test_escrows_by_state() {
        let mut monitor = EscrowMonitor::new();
        let id1 = create_test_escrow(&mut monitor, 42161);
        let id2 = create_test_escrow(&mut monitor, 900);

        assert_eq!(monitor.escrows_by_state(EscrowState::Holding).len(), 2);

        monitor.release_escrow(&id1);
        assert_eq!(monitor.escrows_by_state(EscrowState::Holding).len(), 1);
        assert_eq!(monitor.escrows_by_state(EscrowState::Released).len(), 1);
    }
}
