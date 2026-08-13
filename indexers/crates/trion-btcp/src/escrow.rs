//! Module 2.2: Escrow Monitor — State machine with cascade revert
//!
//! States: IDLE → HOLDING → PENDING_AKASHIC → RELEASED / REVERTED / EMERGENCY_REVERTED
//! Gap 8: Emergency Escape (7 days), Gap 9: Cascade Revert, E1: 24h Akashic, G1: Two-Phase

use std::collections::HashMap;
use std::time::{SystemTime, UNIX_EPOCH};

const EMERGENCY_ESCAPE_SECONDS: u64 = 7 * 24 * 3600;
const AKASHIC_RECOVERY_SECONDS: u64 = 24 * 3600;

#[derive(Debug, Clone, Copy, PartialEq, Eq)]
pub enum EscrowState {
    Idle,
    Holding,
    PendingAkashic,
    Released,
    Reverted,
    EmergencyReverted,
}

#[derive(Debug, Clone, Copy, PartialEq, Eq)]
pub enum RevertReason {
    Timeout,
    CoherenceFailure,
    RouteInvalid,
    Manual,
    AkashicOutage24h,
    CascadeRevert,
    EmergencyEscape,
}

#[derive(Debug, Clone)]
pub struct Escrow {
    pub escrow_id: String,
    pub route_id: String,
    pub entity_id: [u8; 32],
    pub amount: f64,
    pub lock_block: u64,
    pub lock_timestamp: f64,
    pub timeout_blocks: u64,
    pub state: EscrowState,
    pub revert_reason: RevertReason,
    pub settled_at: Option<f64>,
    pub reverted_at: Option<f64>,
    pub parent_escrow_id: Option<String>,
    pub settlement_verified: bool,
}

fn now() -> f64 {
    SystemTime::now().duration_since(UNIX_EPOCH).unwrap().as_secs_f64()
}

pub struct EscrowMonitor {
    escrows: HashMap<String, Escrow>,
}

impl EscrowMonitor {
    pub fn new() -> Self {
        Self { escrows: HashMap::new() }
    }

    pub fn lock_escrow(&mut self, id: &str, route: &str, entity: [u8; 32], amount: f64,
                       timeout: u64, parent: Option<&str>, block: u64) -> bool {
        if self.escrows.contains_key(id) { return false; }
        self.escrows.insert(id.into(), Escrow {
            escrow_id: id.into(), route_id: route.into(), entity_id: entity,
            amount, lock_block: block, lock_timestamp: now(), timeout_blocks: timeout,
            state: EscrowState::Holding, revert_reason: RevertReason::Timeout,
            settled_at: None, reverted_at: None,
            parent_escrow_id: parent.map(|s| s.into()), settlement_verified: false,
        });
        true
    }

    pub fn verify_settlement(&mut self, id: &str) -> bool {
        if let Some(e) = self.escrows.get_mut(id) {
            if e.state == EscrowState::Holding { e.settlement_verified = true; return true; }
        }
        false
    }

    pub fn release_escrow(&mut self, id: &str, coherence: f64, min_coherence: f64, block: u64) -> bool {
        if let Some(e) = self.escrows.get_mut(id) {
            if e.state != EscrowState::Holding || !e.settlement_verified { return false; }
            if coherence < min_coherence { return false; }
            if block > e.lock_block + e.timeout_blocks { return false; }
            e.state = EscrowState::Released;
            e.settled_at = Some(now());
            return true;
        }
        false
    }

    pub fn enter_pending_akashic(&mut self, id: &str) -> bool {
        if let Some(e) = self.escrows.get_mut(id) {
            if e.state == EscrowState::Holding { e.state = EscrowState::PendingAkashic; return true; }
        }
        false
    }

    pub fn revert_escrow(&mut self, id: &str, reason: RevertReason, block: u64) -> bool {
        let parent = match self.escrows.get(id) {
            Some(e) if e.state == EscrowState::Holding || e.state == EscrowState::PendingAkashic => e.parent_escrow_id.clone(),
            _ => return false,
        };
        if let Some(e) = self.escrows.get_mut(id) {
            e.state = EscrowState::Reverted;
            e.revert_reason = reason;
            e.reverted_at = Some(now());
        }
        if let Some(parent_id) = parent {
            self.cascade_revert(&parent_id);
        }
        true
    }

    pub fn revert_emergency(&mut self, id: &str) -> bool {
        let parent = match self.escrows.get(id) {
            Some(e) if e.state == EscrowState::Holding || e.state == EscrowState::PendingAkashic => {
                if now() < e.lock_timestamp + EMERGENCY_ESCAPE_SECONDS as f64 { return false; }
                e.parent_escrow_id.clone()
            }
            _ => return false,
        };
        if let Some(e) = self.escrows.get_mut(id) {
            e.state = EscrowState::EmergencyReverted;
            e.revert_reason = RevertReason::EmergencyEscape;
            e.reverted_at = Some(now());
        }
        if let Some(parent_id) = parent {
            self.cascade_revert(&parent_id);
        }
        true
    }

    fn cascade_revert(&mut self, parent_id: &str) {
        let grandparent = match self.escrows.get(parent_id) {
            Some(e) if e.state == EscrowState::Holding || e.state == EscrowState::PendingAkashic => {
                e.parent_escrow_id.clone()
            }
            _ => return,
        };
        if let Some(e) = self.escrows.get_mut(parent_id) {
            e.state = EscrowState::Reverted;
            e.revert_reason = RevertReason::CascadeRevert;
            e.reverted_at = Some(now());
        }
        if let Some(gp) = grandparent {
            self.cascade_revert(&gp);
        }
    }

    pub fn get_escrow(&self, id: &str) -> Option<&Escrow> { self.escrows.get(id) }
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn test_lock_and_release() {
        let mut mon = EscrowMonitor::new();
        mon.lock_escrow("e1", "r1", [1; 32], 1000.0, 1000, None, 100);
        assert!(mon.verify_settlement("e1"));
        assert!(mon.release_escrow("e1", 0.80, 0.55, 200));
        assert_eq!(mon.get_escrow("e1").unwrap().state, EscrowState::Released);
    }

    #[test]
    fn test_timeout_revert() {
        let mut mon = EscrowMonitor::new();
        mon.lock_escrow("e2", "r2", [2; 32], 500.0, 100, None, 100);
        assert!(mon.revert_escrow("e2", RevertReason::Timeout, 300));
        assert_eq!(mon.get_escrow("e2").unwrap().state, EscrowState::Reverted);
    }

    #[test]
    fn test_cascade_revert() {
        let mut mon = EscrowMonitor::new();
        mon.lock_escrow("parent", "rp", [3; 32], 2000.0, 1000, None, 100);
        mon.lock_escrow("child", "rc", [3; 32], 1500.0, 500, Some("parent"), 100);
        mon.revert_escrow("child", RevertReason::Timeout, 700);
        assert_eq!(mon.get_escrow("child").unwrap().state, EscrowState::Reverted);
        assert_eq!(mon.get_escrow("parent").unwrap().state, EscrowState::Reverted);
        assert_eq!(mon.get_escrow("parent").unwrap().revert_reason, RevertReason::CascadeRevert);
    }

    #[test]
    fn test_release_requires_settlement() {
        let mut mon = EscrowMonitor::new();
        mon.lock_escrow("e3", "r3", [4; 32], 1000.0, 1000, None, 100);
        // No verify_settlement call → release should fail
        assert!(!mon.release_escrow("e3", 0.80, 0.55, 200));
    }
}
