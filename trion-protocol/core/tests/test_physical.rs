use trion_core::physical::phi::{compute_phi, temporal_coherence};
use trion_core::physical::features::PhysicalFeatures;
use trion_core::physical::manipulation::{ManipulationInput, ManipulationType};

fn healthy_input() -> ManipulationInput {
    ManipulationInput {
        cyclic_flow_ratio:           0.05,
        counterparty_count:          500,
        sync_buy_ratio:              0.10,
        coordinated_beo_count:       1,
        ref_price_deviation_pct:     0.5,
        large_swap_within_10_blocks: false,
        top5_lp_share:               0.30,
        funding_source_count:        100,
        vote_hhi:                    800.0,
        proposal_age_hours:          72.0,
        mev_rate_pct:                0.05,
        mev_days_sustained:          0,
        volume_entropy:              0.75,
        volume_spike_multiplier:     1.5,
    }
}

fn healthy_features() -> PhysicalFeatures {
    PhysicalFeatures::with_equal_weights(
        0.75, 0.82, 0.68, 0.71, 0.65, 0.70, 0.78, 0.60, 0.90
    )
}

#[test]
fn test_healthy_phi_above_threshold() {
    let result = compute_phi(&healthy_features(), &healthy_input());
    assert!(result.phi_raw > 0.60, "Healthy phi_raw must be > 0.60, got {}", result.phi_raw);
    assert!(result.phi_adj > 0.60, "Healthy phi_adj must be > 0.60, got {}", result.phi_adj);
    assert!(result.manipulation.mf_score < 0.10, "Healthy MF must be < 0.10");
}

#[test]
fn test_wash_trading_reduces_phi_adj() {
    let features = healthy_features();
    let manip = ManipulationInput {
        cyclic_flow_ratio: 0.85,
        counterparty_count: 3,
        ..healthy_input()
    };
    let result = compute_phi(&features, &manip);
    assert!(result.phi_adj < result.phi_raw, "phi_adj must be < phi_raw when wash trading");
    assert!(result.manipulation.active_types.contains(&ManipulationType::WashTrading));
}

#[test]
fn test_oracle_attack_collapses_phi_adj() {
    let features = healthy_features();
    let manip = ManipulationInput {
        ref_price_deviation_pct:     20.0,
        large_swap_within_10_blocks: true,
        ..healthy_input()
    };
    let result = compute_phi(&features, &manip);
    assert!((result.manipulation.mf_score - 1.0).abs() < 1e-6,
        "Oracle attack must set MF_score = 1.0");
    assert!(result.phi_adj < 1e-6, "phi_adj must be 0.0 on oracle attack");
}

#[test]
fn test_governance_capture_detected() {
    let manip = ManipulationInput {
        vote_hhi:           5500.0,
        proposal_age_hours: 12.0,
        ..healthy_input()
    };
    let result = compute_phi(&healthy_features(), &manip);
    assert!(result.manipulation.active_types.contains(&ManipulationType::GovernanceCapture));
}

#[test]
fn test_mf_score_capped_at_one() {
    let manip = ManipulationInput {
        cyclic_flow_ratio:     0.90,
        counterparty_count:    2,
        sync_buy_ratio:        0.95,
        coordinated_beo_count: 5,
        ..healthy_input()
    };
    let result = compute_phi(&healthy_features(), &manip);
    assert!(result.manipulation.mf_score <= 1.0, "MF_score must never exceed 1.0");
    assert!(result.manipulation.active_types.len() >= 2);
}

#[test]
fn test_temporal_coherence_fresh() {
    let reference = 1_000_000i64;
    let ttl_min   = 30_000i64;
    let tc_min    = 0.50;
    let fresh = vec![999_500, 1_000_100, 999_800];
    let (tc, valid) = temporal_coherence(&fresh, reference, ttl_min, tc_min);
    assert!(valid, "Fresh timestamps must be valid, TC={:.3}", tc);
}

#[test]
fn test_temporal_coherence_stale() {
    let reference = 1_000_000i64;
    let ttl_min   = 30_000i64;
    let tc_min    = 0.50;
    let stale = vec![900_000, 1_000_100, 999_800];
    let (tc, valid) = temporal_coherence(&stale, reference, ttl_min, tc_min);
    assert!(!valid, "Stale timestamp must fail TC, TC={:.3}", tc);
}
