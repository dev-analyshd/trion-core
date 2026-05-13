//! Manipulation Fingerprint Detector — TRION L1
//! Whitepaper Section 3.2: 7 manipulation types
//! MF_score = min(1.0, max(all active contributions))
//! Phi_adj  = Phi_raw × (1 - MF_score)

use serde::{Deserialize, Serialize};

#[derive(Debug, Clone, PartialEq, Serialize, Deserialize)]
pub enum ManipulationType {
    WashTrading,
    CoordinatedPump,
    OracleAttackAttempt,
    SybilLiquidity,
    GovernanceCapture,
    MevExtractionSustained,
    FakeVolumeProtocol,
}

#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct ManipulationResult {
    pub mf_score:      f64,
    pub active_types:  Vec<ManipulationType>,
    pub dominant_type: Option<ManipulationType>,
}

#[derive(Debug, Clone)]
pub struct ManipulationInput {
    pub cyclic_flow_ratio:             f64,
    pub counterparty_count:            usize,
    pub sync_buy_ratio:                f64,
    pub coordinated_beo_count:         usize,
    pub ref_price_deviation_pct:       f64,
    pub large_swap_within_10_blocks:   bool,
    pub top5_lp_share:                 f64,
    pub funding_source_count:          usize,
    pub vote_hhi:                      f64,
    pub proposal_age_hours:            f64,
    pub mev_rate_pct:                  f64,
    pub mev_days_sustained:            u32,
    pub volume_entropy:                f64,
    pub volume_spike_multiplier:       f64,
}

pub fn detect_manipulation(inp: &ManipulationInput) -> ManipulationResult {
    let mut scores: Vec<(ManipulationType, f64)> = Vec::new();

    // TYPE 1: WASH_TRADING
    if inp.cyclic_flow_ratio > 0.60 && inp.counterparty_count < 5 {
        scores.push((ManipulationType::WashTrading, 0.70 * inp.cyclic_flow_ratio));
    }

    // TYPE 2: COORDINATED_PUMP
    if inp.sync_buy_ratio > 0.80 && inp.coordinated_beo_count >= 3 {
        scores.push((ManipulationType::CoordinatedPump, 0.85 * inp.sync_buy_ratio));
    }

    // TYPE 3: ORACLE_ATTACK — automatic 1.0
    if inp.ref_price_deviation_pct > 15.0 && inp.large_swap_within_10_blocks {
        scores.push((ManipulationType::OracleAttackAttempt, 1.0));
    }

    // TYPE 4: SYBIL_LIQUIDITY
    if inp.top5_lp_share > 0.80 && inp.funding_source_count < 3 {
        let concentration = 1.0 / inp.funding_source_count.max(1) as f64;
        scores.push((ManipulationType::SybilLiquidity, 0.60 * concentration));
    }

    // TYPE 5: GOVERNANCE_CAPTURE
    if inp.vote_hhi > 4000.0 && inp.proposal_age_hours < 48.0 {
        let hhi_norm = ((inp.vote_hhi - 4000.0) / 6000.0).clamp(0.0, 1.0);
        let recency  = 1.0 - (inp.proposal_age_hours / 48.0);
        scores.push((ManipulationType::GovernanceCapture,
                     (0.75 * hhi_norm * recency).clamp(0.0, 1.0)));
    }

    // TYPE 6: MEV_EXTRACTION_SUSTAINED
    if inp.mev_rate_pct > 0.5 && inp.mev_days_sustained > 7 {
        let rate_f = (inp.mev_rate_pct / 5.0).clamp(0.0, 1.0);
        let dur_f  = ((inp.mev_days_sustained - 7) as f64 / 30.0).clamp(0.0, 1.0);
        scores.push((ManipulationType::MevExtractionSustained,
                     (0.65 * rate_f * (1.0 + dur_f)).clamp(0.0, 1.0)));
    }

    // TYPE 7: FAKE_VOLUME_PROTOCOL
    if inp.volume_entropy < 0.30 && inp.volume_spike_multiplier > 10.0 {
        let spike = ((inp.volume_spike_multiplier - 10.0) / 90.0).clamp(0.0, 1.0);
        scores.push((ManipulationType::FakeVolumeProtocol,
                     (0.80 * (1.0 - inp.volume_entropy) * (1.0 + spike)).clamp(0.0, 1.0)));
    }

    if scores.is_empty() {
        return ManipulationResult { mf_score: 0.0, active_types: vec![], dominant_type: None };
    }

    let mf_score = scores.iter()
        .map(|(_, s)| *s)
        .fold(f64::NEG_INFINITY, f64::max)
        .min(1.0);

    let dominant = scores.iter()
        .max_by(|a, b| a.1.partial_cmp(&b.1).unwrap())
        .map(|(t, _)| t.clone());

    let active = scores.into_iter().map(|(t, _)| t).collect();
    ManipulationResult { mf_score, active_types: active, dominant_type: dominant }
}
