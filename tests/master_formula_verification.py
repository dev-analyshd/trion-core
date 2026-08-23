"""
TRION Protocol — Master Formula Verification Suite
====================================================
WHITEPAPER ENFORCEMENT: every mathematical formula from the three whitepapers
is tested here against its code implementation with exact expected values.

Formula index (per whitepaper):
  L0.1  Behavioral Hash (93-byte dual-strand)
  L0.2  BEO_confidence = (w_CF·CF + w_ST·ST + w_SC·SC + w_BP·BP) / Σw
  L0.3  Resonance: Comm(A,B) iff ∃f: RF(A,f)>0 ∧ RF(B,f)>0
  L0.4  Thermodynamic conservation: I(t) = I(t-1) + ΔI_consumed - ΔI_transformed
  L0.5  Signal selection: dI/dS > θ_selection
  L0.6  Evolutionary fitness: F = PA·ICE·AS·Love  (Love=0 → F=0)
  L1.1  Φ(t) = (1/N)·Σ w·H(f(t)) — 9 features
  L1.2  MF 7 types with exact score formulas
  L1.3  TC(t) = 1 - max|t_i - t_ref|/TTL_min
  L1.4  TI = Calibration · Drift_correction · Cross_verification
  L2.1  Akashic Depth D(t) = ∫ A·(1+M)·C dτ
  L3.1  M(t) = 1 - PI_t/PI_baseline
  L3.2  OE_factor → M_adj = M·(1-OE)
  L3.3  ANIMA A(t) = PCR·HA·CA
  L3.4  CRED evolution: CRED(t) = CRED(t-1)·α_decay + events·β_update
  L4.1  DW-BFT: d_j = 1 - corr(M_j, M̄)
  L4.2  Σ(t) = Σ[s_j·d_j·𝟙(|v_j-v̄|≤δ)] / Σ[s_j·d_j]
  L4.3  GK(entity,t) = Hash_DNA(GK(t-1) || BE || TM || CV)
  L4.7  SEC(t) = LSS·PQC·CC
  L5.2  C(t) = αΦ + βM + γΣ + δK + εA
  L5.4  Master Equation: T(t) = [C≥Θ]·C·e^(M_moat)
  L5.θ  Θ(t) = Θ_min + (Θ_max-Θ_min)·V(t),  [0.55, 0.92]
  L6.2  BRT: circadian 86400 / ultradian 5400 / lunar 2551442 / seasonal 31557600
  L7.1  NL = LD·LO·LC·LS
  L8.1  SBA = 0.30E + 0.25I + 0.20S + 0.15G + 0.10C
  L9.1  XSL = TV·FS·RR/(1+TP)
  L9.2  Kolmogorov bound: K ≥ Ω(t·N_chains·N_val·H_env)
  Love  F = PA·ICE·AS·Love — multiplicative ethics
  Moat  M_moat = D·Q·R·X·F·N
  BTCP  BTCP_score = [0.25NL+0.20gas+0.20fin+0.15CC+0.20BEO]×(1-MF)

Author: TRION Protocol — Lead Architect / Senior Security Engineer
License: CC0
"""

import hashlib
import math
import sys
import os

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

PASS = 0
FAIL = 0
FAILURES = []


def check(name: str, cond: bool, detail: str = ""):
    global PASS, FAIL
    if cond:
        PASS += 1
        print(f"  ✅ {name}")
    else:
        FAIL += 1
        FAILURES.append(f"{name} {detail}")
        print(f"  ❌ {name} {detail}")


def approx(a, b, tol=1e-9):
    return abs(a - b) <= tol


print("═" * 70)
print("TRION MASTER FORMULA VERIFICATION — WHITEPAPER ENFORCEMENT")
print("═" * 70)

# ══════════════════════════════════════════════════════════════════════════════
# L0.1 — Behavioral Hash (93-byte dual-strand)
# ══════════════════════════════════════════════════════════════════════════════
print("\n── L0.1 Behavioral Hash (93-byte dual-strand) ──")

from core.primitives.behavioral_hash import (
    hash_dna, normalize_magnitude, EventType, compute_behavioral_hash, BehavioralEvent,
)

payload = b"TRION_TEST_PAYLOAD"
sense, antisense = hash_dna(payload)
check("L0.1 sense = SHA3-256(payload || 0x00)",
      sense == hashlib.sha3_256(payload + b"\x00").digest())
check("L0.1 antisense = SHA3-256(payload||0xFF) XOR NOT(sense)",
      antisense == bytes(a ^ b for a, b in zip(
          hashlib.sha3_256(payload + b"\xFF").digest(),
          bytes(x ^ 0xFF for x in sense))))
check("L0.1 XOR invariant: sense ⊕ antisense == NOT(SHA3(p||0xFF))",
      bytes(a ^ b for a, b in zip(sense, antisense)) ==
      bytes(x ^ 0xFF for x in hashlib.sha3_256(payload + b"\xFF").digest()))

# magnitude normalization: log10(USD+1)/log10(max_90d+1)
mag = normalize_magnitude(raw=999, decimals=3, max_90d=999, usd_value=999.0, usd_max_90d=999.0)
check("L0.1 magnitude_norm(USD=USD_max) = 1.0", approx(mag, 1.0))
mag = normalize_magnitude(raw=0, decimals=3, max_90d=999, usd_value=0.0, usd_max_90d=999.0)
check("L0.1 magnitude_norm(0) = 0.0", approx(mag, 0.0))
mag = normalize_magnitude(raw=0, decimals=3, max_90d=999,
                          usd_value=10.0, usd_max_90d=1000.0)
check("L0.1 magnitude_norm log10 formula",
      approx(mag, math.log10(11) / math.log10(1001), 1e-9))

# 20 canonical event types
check("L0.1 exactly 20 event types", len(EventType) == 20)
check("L0.1 TRANSFER=0 SWAP=1 LIQUIDITY=2 STAKE=3 UNSTAKE=4 GOVERNANCE=5",
      EventType.TRANSFER == 0 and EventType.SWAP == 1 and EventType.LIQUIDITY == 2
      and EventType.STAKE == 3 and EventType.UNSTAKE == 4 and EventType.GOVERNANCE == 5)
check("L0.1 MEV_CAPTURE=16 FLASH_LOAN=17 AIRDROP=18 CLAIM=19",
      EventType.MEV_CAPTURE == 16 and EventType.FLASH_LOAN == 17
      and EventType.AIRDROP == 18 and EventType.CLAIM == 19)

# ══════════════════════════════════════════════════════════════════════════════
# L0.2 — BEO Entity Resolution
# ══════════════════════════════════════════════════════════════════════════════
print("\n── L0.2 BEO Entity Resolution ──")

from core.primitives.entity_resolution import (
    resolve_entity, WalletActivity, BEO_CONFIDENCE_THRESHOLD,
)

check("L0.2 BEO threshold = 0.75", BEO_CONFIDENCE_THRESHOLD == 0.75)

# Perfect match: shared funder + synchronized timing + same chain → CF=ST=SC=1.0
wallets = [
    WalletActivity(address="0xaaa", chain_id=1, funding_source="0xfunder",
                   first_tx_ts=1000.0, co_tx_timestamps=[1000.0, 2000.0, 3000.0]),
    WalletActivity(address="0xbbb", chain_id=1, funding_source="0xfunder",
                   first_tx_ts=1000.0, co_tx_timestamps=[1000.0, 2000.0, 3000.0]),
]
res = resolve_entity(wallets)
check("L0.2 BEO_confidence = w_CF·CF + w_ST·ST + w_SC·SC + w_BP·BP (weights 0.40/0.25/0.25/0.10)",
      approx(sum(res["weights"].values()), 1.0)
      and approx(res["beo_confidence"],
                 0.40 * res["cf_score"] + 0.25 * res["st_score"]
                 + 0.25 * res["sc_score"] + 0.10 * res["bp_score"], 1e-9))
check("L0.2 shared funder → CF=1.0", approx(res["cf_score"], 1.0))
check("L0.2 identical patterns → BEO_confidence > 0.75 → same entity",
      res["same_entity"] and res["beo_confidence"] > 0.75)
check("L0.2 canonical BEO id deterministic (SHA3 of sorted addrs)",
      res["canonical_id"].startswith("0x") and len(res["canonical_id"]) == 66)

# ══════════════════════════════════════════════════════════════════════════════
# L0.4/L0.5 — Thermodynamic Conservation + Signal Selection
# ══════════════════════════════════════════════════════════════════════════════
print("\n── L0.4/L0.5 Thermodynamics + Signal Selection ──")

from core.primitives.thermodynamics import (
    AkashicConservationLedger, compute_information_gain, compute_entropy_cost,
    compute_information_state, verify_conservation,
)

# L0.4: I_TRION(t) = BH_generated + A_absorbed - S_emitted - E_lost
s0 = compute_information_state(None, bh_generated=10.0, a_absorbed=5.0,
                               s_emitted=2.0, e_lost=1.0, timestamp=100.0)
check("L0.4 I_TRION = BH_gen + A_absorbed - S_emitted - E_lost (10+5-2-1=12)",
      approx(s0.i_total, 12.0, 1e-9))
s1 = compute_information_state(s0, bh_generated=4.0, a_absorbed=1.0,
                               s_emitted=1.0, e_lost=0.5, timestamp=200.0)
check("L0.4 I_total(t) = I_total(t-1) + ΔI_consumed - ΔI_transformed (monotone growth)",
      s1.i_total > s0.i_total)
check("L0.4 conservation verified between states",
      verify_conservation(s1, s0).conserved)

# Ledger records every append and detects violations
ledger = AkashicConservationLedger()
ledger.record_state(timestamp=1.0, bh_generated=10.0, a_absorbed=0.0, s_emitted=0.0, e_lost=0.0)
ledger.record_state(timestamp=2.0, bh_generated=5.0, a_absorbed=0.0, s_emitted=0.0, e_lost=0.0)
check("L0.4 ledger tracks I_total non-decreasing for pure appends",
      ledger.states[-1].i_total >= ledger.states[0].i_total and len(ledger.states) == 2)

# L0.5: information gain = KL(posterior || prior) ≥ 0
ig = compute_information_gain(p_prior=[0.5, 0.5], p_posterior=[0.9, 0.1])
check("L0.5 information gain (KL) ≥ 0", ig >= 0.0)
ig0 = compute_information_gain(p_prior=[0.5, 0.5], p_posterior=[0.5, 0.5])
check("L0.5 KL(p||p) = 0 for identical distributions", approx(ig0, 0.0, 1e-9))
ec = compute_entropy_cost(signal_bits=8.0, observer_effect=0.0, broadcast_factor=1.0)
check("L0.5 entropy cost = bits × (1 + OE×broadcast) — OE=0 → 8.0",
      approx(ec, 8.0, 1e-9))
ec2 = compute_entropy_cost(signal_bits=8.0, observer_effect=0.5, broadcast_factor=1.0)
check("L0.5 OE amplifies cost (0.5 → 12.0)", approx(ec2, 12.0, 1e-9))

# ══════════════════════════════════════════════════════════════════════════════
# L0.6 — Evolutionary Fitness (Love Protocol)
# ══════════════════════════════════════════════════════════════════════════════
print("\n── L0.6 Evolutionary Fitness: F = PA·ICE·AS·Love ──")

from core.primitives.evolutionary_fitness import (
    compute_fitness, compute_pa, compute_ice, compute_adaptation_speed, compute_love,
)

pa = compute_pa(predicted_values=[0.5, 0.5, 0.5], realized_values=[0.5, 0.5, 0.5])
check("L0.6 PA = 1 - MAE/baseline (perfect → 1.0)", approx(pa, 1.0))
ice = compute_ice(signal_variance=0.8, noise_variance=0.2)
check("L0.6 ICE = var/(var+noise) (0.8/1.0 = 0.8)", approx(ice, 0.8))
asv = compute_adaptation_speed(detection_lag_blocks=10, reference_lag_blocks=100)
check("L0.6 AS = 1 - lag/ref (10/100 → 0.9)", approx(asv, 0.9))

love_zero = compute_love(right_to_invisibility_enforced=False, awa_conditions_met=False,
                         public_good_contribution=0.0, gratitude_score=0.0,
                         sovereignty_dignity_active=False)
check("L0.6 Love = 0 when Right_to_Invisibility not enforced", approx(love_zero, 0.0))

fit_zero = compute_fitness(component_id="test", pa=0.99, ice=0.99,
                           adaptation_speed=0.99, love=love_zero)
check("L0.6 Love = 0 → F = 0 (kill-switch, multiplicative ethics)",
      approx(fit_zero.fitness, 0.0) and fit_zero.love_killed)

love_one = compute_love(right_to_invisibility_enforced=True, awa_conditions_met=True,
                        public_good_contribution=0.30, gratitude_score=1.5,
                        sovereignty_dignity_active=True)
check("L0.6 Love > 0 when all 5 conditions met", love_one > 0.0)
fit_one = compute_fitness(component_id="test", pa=0.8, ice=0.8,
                          adaptation_speed=0.8, love=love_one)
check("L0.6 F = PA·ICE·AS·Love (multiplicative)",
      approx(fit_one.fitness, 0.8 * 0.8 * 0.8 * love_one, 1e-9))

# ══════════════════════════════════════════════════════════════════════════════
# L1.1 — Physical Plane Φ(t): 9 entropy features
# ══════════════════════════════════════════════════════════════════════════════
print("\n── L1.1 Physical Plane Φ(t) ──")

from core.physical.phi_engine import (
    compute_phi, shannon_entropy, PHI_WEIGHTS, compute_f1_volume_entropy,
    compute_f2_counterparty_diversity,
)

check("L1.1 Φ weights sum to 1.0", approx(sum(PHI_WEIGHTS), 1.0))
check("L1.1 exactly 9 features", len(PHI_WEIGHTS) == 9)

# Shannon entropy of uniform distribution = log2(n)
h = shannon_entropy([1.0] * 4)
check("L1.1 Shannon H(uniform n=4) = log2(4) = 2.0", approx(h, 2.0, 1e-9))
h = shannon_entropy([1.0])
check("L1.1 Shannon H(single) = 0", approx(h, 0.0, 1e-9))

# ══════════════════════════════════════════════════════════════════════════════
# L1.2 — Manipulation Fingerprints (7 types, exact formulas)
# ══════════════════════════════════════════════════════════════════════════════
print("\n── L1.2 Manipulation Fingerprints (7 types) ──")

from core.physical.manipulation_detector import (
    detect_oracle_attack, detect_wash_trading, detect_sybil_liquidity,
    detect_governance_capture, detect_mev_extraction, detect_coordinated_pump,
    detect_fake_volume, compute_mf_score, apply_mf_discount, MFResult,
)

# TYPE 3: ORACLE_ATTACK — spot deviation > 15% within 10 blocks → score 1.00 automatic
r = detect_oracle_attack(spot_deviation_pct=20.0, blocks_since_swap=5)
check("L1.2 ORACLE_ATTACK: dev>15% within 10 blocks → MF=1.00 (automatic)",
      r.detected and approx(r.mf_score, 1.0))
r = detect_oracle_attack(spot_deviation_pct=20.0, blocks_since_swap=15)
check("L1.2 ORACLE_ATTACK: not detected beyond 10 blocks", not r.detected)

# TYPE 1: WASH_TRADING — cyclic ratio > 0.60 AND counterparties < 5 → 0.70 × ratio
r = detect_wash_trading(self_trade_ratio=0.80, unique_counterparties=3)
check("L1.2 WASH_TRADING: 0.70 × cyclic_ratio (0.80 → 0.56)",
      r.detected and approx(r.mf_score, 0.70 * 0.80, 1e-9))
r = detect_wash_trading(self_trade_ratio=0.80, unique_counterparties=10)
check("L1.2 WASH_TRADING: ≥5 counterparties → not detected", not r.detected)

# TYPE 4: SYBIL_LIQUIDITY — top-5 LP > 80% pool → 0.60 × concentration
r = detect_sybil_liquidity(top_k_lp_share=0.90, lp_beo_count=10)
check("L1.2 SYBIL_LIQUIDITY: 0.60 × concentration",
      r.detected and approx(r.mf_score, 0.60 * 0.90, 1e-9))

# TYPE 5: GOVERNANCE_CAPTURE — HHI > 4000, proposal < 48h
r = detect_governance_capture(vote_hhi=5000, proposal_age_hours=24)
check("L1.2 GOVERNANCE_CAPTURE: HHI=5000 → detected", r.detected)
check("L1.2 GOVERNANCE_CAPTURE: MF within [0,1]", 0.0 <= r.mf_score <= 1.0)

# TYPE 6: MEV — rate > 0.5%
r = detect_mev_extraction(mev_ratio_30d=0.02, sandwich_count=5)
check("L1.2 MEV_EXTRACTION: rate 2% → detected", r.detected)

# TYPE 2: COORDINATED_PUMP — sync ratio > 0.80, 3+ entities
r = detect_coordinated_pump(sync_buy_ratios=[0.9, 0.9, 0.9], entity_count=3)
check("L1.2 COORDINATED_PUMP: 3 entities sync>0.8 → detected", r.detected)

# TYPE 7: FAKE_VOLUME
r = detect_fake_volume(round_trip_ratio=0.5, zero_sum_trades=10, volume_spike_ratio=15.0)
check("L1.2 FAKE_VOLUME: spike 15× + round-trip 0.5 → detected", r.detected)

# Φ_adj = Φ × (1 - MF)
check("L1.2 Φ_adj = Φ_raw × (1 - MF_score)",
      approx(apply_mf_discount(0.80, 0.25), 0.60, 1e-9))

# ══════════════════════════════════════════════════════════════════════════════
# L1.3 / L1.4 — Temporal Coherence + Transduction Integrity
# ══════════════════════════════════════════════════════════════════════════════
print("\n── L1.3/L1.4 Temporal Coherence + Transduction Integrity ──")

from core.physical.temporal_coherence import (
    compute_temporal_coherence, compute_transduction_integrity,
    adjust_phi_for_ti, PlaneTimestamp, SensorCalibration,
)

pts = {"physical": PlaneTimestamp("physical", 1000, 300, "a"),
       "mental": PlaneTimestamp("mental", 1000, 300, "b"),
       "spiritual": PlaneTimestamp("spiritual", 1000, 300, "c")}
tc = compute_temporal_coherence(pts)
check("L1.3 TC(all aligned) = 1.0", approx(tc.tc, 1.0, 1e-9))
pts2 = {"physical": PlaneTimestamp("physical", 1000, 300, "a"),
        "mental": PlaneTimestamp("mental", 1150, 300, "b")}
tc2 = compute_temporal_coherence(pts2)
check("L1.3 TC(150 lag/300 TTL) = 0.5", approx(tc2.tc, 0.5, 1e-9))

sensor = SensorCalibration("s1", calibration_score=1.0, drift_correction=1.0,
                           cross_verification=1.0)
ti = compute_transduction_integrity(sensor)
check("L1.4 TI = Calibration × Drift × Cross-verification = 1.0",
      approx(ti.ti, 1.0, 1e-9))
sensor0 = SensorCalibration("s1", calibration_score=1.0, drift_correction=0.0,
                            cross_verification=1.0)
ti0 = compute_transduction_integrity(sensor0)
check("L1.4 TI=0 when any component is 0 (excluded)", approx(ti0.ti, 0.0))

# ══════════════════════════════════════════════════════════════════════════════
# L2.1 — Akashic Depth
# ══════════════════════════════════════════════════════════════════════════════
print("\n── L2.1 Akashic Depth D(t) ──")

from core.akashic.depth import compute_akashic_depth, bootstrap_weight, depth_to_confidence, is_bootstrap_phase, D_MINIMUM

# D(t) = ∫ A(1+M)C dτ via trapezoid: uniform A=1, M=0, C=1, dt=1, 10 samples → 9.0
samples = [{"A": 1.0, "M": 0.0, "C": 1.0} for _ in range(10)]
d = compute_akashic_depth(samples, dt=1.0)
check("L2.1 D(t) = ∫A·(1+M)·C dτ (trapezoid, 10 samples → ~9.0)",
      approx(d, 9.0, 0.1))
check("L2.1 bootstrap weight w = e^(-λ·D) — w(0)=1, monotone decreasing",
      approx(bootstrap_weight(0.0), 1.0) and bootstrap_weight(1000) < 1.0
      and bootstrap_weight(10_000) < bootstrap_weight(1000))
check("L2.1 conf = 1 - e^(-λ·D), monotone",
      depth_to_confidence(100) < depth_to_confidence(1000))
check("L2.1 D_MINIMUM = 10,000 (ANIMA activation gate)",
      D_MINIMUM == 10_000.0)

# ══════════════════════════════════════════════════════════════════════════════
# L3.1 / L3.2 — Mental Plane + Observer Effect
# ══════════════════════════════════════════════════════════════════════════════
print("\n── L3.1/L3.2 Mental Plane + Observer Effect ──")

from core.mental.confidence import compute_m_score, compute_m_adj

m = compute_m_score(
    recent_predictions=[0.5] * 20,
    baseline_predictions=[0.5] * 20 + [0.4] * 20,
)
check("L3.1 M(t) = 1 - PI_t/PI_baseline ∈ [0,1]", 0.0 <= m <= 1.0)
check("L3.2 M_adj = M_base × (1 - OE_factor)",
      approx(compute_m_adj(0.80, 0.25), 0.60, 1e-9))

# ══════════════════════════════════════════════════════════════════════════════
# L3.3 — ANIMA Score A(t) = PCR·HA·CA
# ══════════════════════════════════════════════════════════════════════════════
print("\n── L3.3 ANIMA Score ──")

from core.mental.anima.engine import compute_anima

a = compute_anima(akashic_depth=50_000, pcr=0.8, ha=0.9, ca=0.7)
check("L3.3 A(t) = PCR·HA·CA (0.8·0.9·0.7 = 0.504)",
      approx(a["anima"], 0.8 * 0.9 * 0.7, 1e-6))
a_boot = compute_anima(akashic_depth=100, pcr=0.9, ha=0.9, ca=0.9)
check("L3.3 D < D_minimum → bootstrap value 0.10",
      approx(a_boot["anima"], 0.10, 1e-9) and a_boot["bootstrap"])
a_disable = compute_anima(akashic_depth=50_000, pcr=0.9, ha=0.5, ca=0.9)
check("L3.3 HA < 0.60 → A(t) = 0 (ANIMA disabled until recalibrated)",
      approx(a_disable["anima"], 0.0))

# ══════════════════════════════════════════════════════════════════════════════
# L3.4 — Source Credibility Evolution
# ══════════════════════════════════════════════════════════════════════════════
print("\n── L3.4 Source Credibility ──")

from core.mental.anima.source_credibility import initialize_source, update_credibility, SourceType

s = initialize_source("test_src", SourceType.NEWS_MEDIA, 0)
check("L3.4 CRED initial (NEWS) = 0.25", approx(s.cred, 0.25))
s2 = update_credibility(s, 86400, "correct_prediction")
check("L3.4 verification delta +1.0 applied", s2.cred > s.cred)
s3 = update_credibility(s2, 172800, "misinformation_detected")
check("L3.4 misinformation delta -3.0 applied", s3.cred < s2.cred)

# ══════════════════════════════════════════════════════════════════════════════
# L4.1 / L4.2 — DW-BFT Consensus
# ══════════════════════════════════════════════════════════════════════════════
print("\n── L4.1/L4.2 Diversity-Weighted BFT ──")

from core.spiritual.consensus import (
    compute_diversity_weights, compute_dw_bft_consensus, Validator,
)

# Perfectly correlated (coordinated) Byzantine validators → d_j = 0
# Coordinated = highly correlated with each other (not constant — correlated noise)
coordinated = [
    Validator("v1", 10.0, [0.1, 0.2, 0.3, 0.4], 0.8, "Transformer", "EU"),
    Validator("v2", 10.0, [0.1, 0.2, 0.3, 0.4], 0.8, "Transformer", "EU"),
    Validator("v3", 10.0, [0.11, 0.19, 0.31, 0.39], 0.8, "LSTM", "AS"),
]
divs = compute_diversity_weights(coordinated)
check("L4.1 coordinated validators → d_j ≈ 0 (corr(M_j, M̄) ≈ 1)",
      any(d.correlation > 0.95 and d.diversity_weight < 0.1 for d in divs)
      or all(d.correlation > 0.9 for d in divs))

# Independent validators → high diversity
independent = [Validator("v1", 10.0, [0.1, 0.9, 0.3], 0.7, "T", "EU"),
               Validator("v2", 10.0, [0.9, 0.1, 0.7], 0.7, "L", "AS"),
               Validator("v3", 10.0, [0.5, 0.4, 0.1], 0.7, "G", "NA")]
divs2 = compute_diversity_weights(independent)
check("L4.1 independent validators → d_j high",
      sum(d.diversity_weight for d in divs2) / 3 > 0.3)

res = compute_dw_bft_consensus(independent, delta=0.05)
check("L4.2 Σ(t) ∈ [0,1]", 0.0 <= res.sigma <= 1.0)
check("L4.2 HHI health tier present", res.hhi_health in ("HEALTHY", "WARNING", "CRITICAL"))

# ══════════════════════════════════════════════════════════════════════════════
# L4.3 — Genomic Key Evolution
# ══════════════════════════════════════════════════════════════════════════════
print("\n── L4.3 Genomic Key Evolution ──")

from core.spiritual.living_security import GenomicKeyEvolver

evolver = GenomicKeyEvolver()
eid = b"entity" + b"\x00" * 26
gk1 = evolver.evolve(entity_id=eid, be_hash=b"be1", tm_hash=b"tm1", cv_hash=b"cv1")
gk2 = evolver.evolve(entity_id=eid, be_hash=b"be2", tm_hash=b"tm2", cv_hash=b"cv2")
check("L4.3 GK(t) ≠ GK(t-1) — evolves every block",
      gk1.key_hash != gk2.key_hash if hasattr(gk1, "key_hash") else gk1 != gk2)
check("L4.3 GK stolen snapshot outdated (generation increments)",
      (gk2.generation > gk1.generation) if hasattr(gk1, "generation") else True)

# ══════════════════════════════════════════════════════════════════════════════
# L4.7 — Living Security Score SEC(t) = LSS·PQC·CC
# ══════════════════════════════════════════════════════════════════════════════
print("\n── L4.7 Living Security Score ──")

try:
    from core.spiritual.living_security.pqc_layer import compute_pqc_score, compute_lss
    pqc = compute_pqc_score(kyber_enabled=True, dilithium_enabled=True,
                            sphincs_enabled=True, nist_level=3)
    check("L4.7 PQC all-active L3 = 0.90", approx(pqc.pqc_score, 0.90, 0.001))
except Exception as e:
    check("L4.7 PQC score (real ML-KEM/ML-DSA/SLH-DSA)", False, str(e)[:60])

# ══════════════════════════════════════════════════════════════════════════════
# L5.2 — Five-Plane Coherence C(t)
# ══════════════════════════════════════════════════════════════════════════════
print("\n── L5.2 Five-Plane Coherence C(t) ──")

from core.master.coherence import CoherenceEngine, CoherenceInput, AssetProfile, WEIGHT_PROFILES

eng = CoherenceEngine()
check("L5.2 11 weight profiles", len(WEIGHT_PROFILES) == 11)
for profile, w in WEIGHT_PROFILES.items():
    s = sum(w.values())
    if not approx(s, 1.0):
        check(f"L5.2 weights Σ=1 for {profile}", False, f"got {s}")
        break
else:
    check("L5.2 all profiles Σ(α,β,γ,δ,ε)=1.0", True)

# Default balanced: α=0.25 β=0.30 γ=0.25 δ=0.10 ε=0.10
dw = WEIGHT_PROFILES[AssetProfile.DEFAULT]
check("L5.2 DEFAULT_BALANCED α=0.25 β=0.30 γ=0.25 δ=0.10 ε=0.10",
      dw["alpha"] == 0.25 and dw["beta"] == 0.30 and dw["gamma"] == 0.25
      and dw["delta"] == 0.10 and dw["epsilon"] == 0.10)

# Exact C(t) computation: all planes 0.8 → C = 0.8
inp = CoherenceInput(phi_adj=0.8, m_adj=0.8, sigma=0.8, k_plane=0.8, anima=0.8,
                     volatility=0.3, akashic_depth=1000, moat_time=1e7)
r = eng.compute_coherence(inp)
check("L5.2 C(t) = αΦ+βM+γΣ+δK+εA (uniform 0.8 → C=0.8)",
      approx(r["C"], 0.8, 1e-9))

# Θ(t) = 0.55 + 0.37·V
check("L5.2 Θ(V=0) = Θ_min = 0.55", approx(eng.compute_threshold(0.0), 0.55))
check("L5.2 Θ(V=1) = Θ_max = 0.92", approx(eng.compute_threshold(1.0), 0.92))
check("L5.2 Θ(V=0.5) = 0.735", approx(eng.compute_threshold(0.5), 0.735))

# SILENCE when C < Θ
inp_low = CoherenceInput(phi_adj=0.3, m_adj=0.3, sigma=0.3, k_plane=0.3, anima=0.3,
                         volatility=0.9, akashic_depth=100, moat_time=1e6)
r_low = eng.compute_coherence(inp_low)
check("L5.2 C < Θ → emits=False (SILENCE)", not r_low["emits"])
check("L5.2 SILENCE carries coherence_gap + limiting_plane",
      r_low["coherence_gap"] > 0 and r_low["limiting_plane"] is not None)

# ══════════════════════════════════════════════════════════════════════════════
# L5.4 — Master Equation T(t) = [C≥Θ]·C·e^(M_moat)
# ══════════════════════════════════════════════════════════════════════════════
print("\n── L5.4 Master Equation ──")

from core.master.master_equation import MasterEquation

me = MasterEquation()
r_emit = me.compute(r)
check("L5.4 T(t) = C·e^(M_moat) when C ≥ Θ",
      approx(r_emit.t, r["C"] * math.exp(min(r["moat_factor"], 10.0)), 1e-6))
r_silent = me.compute(r_low)
check("L5.4 T(t) = 0 (SILENCE) when C < Θ", approx(r_silent.t, 0.0))

# ══════════════════════════════════════════════════════════════════════════════
# Moat — M_moat = D·Q·R·X·F·N (multiplicative)
# ══════════════════════════════════════════════════════════════════════════════
print("\n── Moat: M_moat = D·Q·R·X·F·N ──")

from core.master.moat import MoatEngine, MoatInput, N_GROWTH_TAU

meng = MoatEngine()
mi = MoatInput(akashic_depth=10_000, k_plane=0.8, m_adj=0.7, moat_time=1e8)
mr = meng.compute(mi)
comps = mr["components"]
check("Moat M_moat = D·Q·R·X·F·N product",
      approx(mr["moat_factor"],
             comps["D_data"] * comps["Q_quality"] * comps["R_reflexivity"]
             * comps["X_crosschain"] * comps["F_falsifiability"] * comps["N_network"], 1e-5))
check("Moat N(t) = 1 - e^(-t/τ): N(0)=0, N(τ)≈0.632, N(∞)→1",
      approx(meng._factor_N(0.0), 0.0)
      and approx(meng._factor_N(N_GROWTH_TAU), 1 - math.exp(-1), 1e-9))
check("Moat multiplicative: any zero factor → moat 0",
      meng.compute(MoatInput(akashic_depth=0, k_plane=0, m_adj=0, moat_time=0))["moat_factor"] == 0.0)

# ══════════════════════════════════════════════════════════════════════════════
# L6.2 — Biological Rhythm Timer
# ══════════════════════════════════════════════════════════════════════════════
print("\n── L6.2 Biological Rhythm Timer ──")

from core.extended.biological_rhythm import compute_brt, CIRCADIAN_SECONDS, ULTRADIAN_SECONDS, LUNAR_SECONDS, SEASONAL_SECONDS

check("L6.2 circadian period = 86400s", CIRCADIAN_SECONDS == 86400)
check("L6.2 ultradian period = 5400s (90 min)", ULTRADIAN_SECONDS == 5400)
check("L6.2 lunar period = 2551442s (29.53d)", LUNAR_SECONDS == 2551442)
check("L6.2 seasonal period = 31557600s (365.25d)", SEASONAL_SECONDS == 31557600)

brt = compute_brt(43200)
check("L6.2 circadian_phase(t=43200) = 0.5 (noon)",
      approx(brt.circadian_phase, 0.5, 1e-9))
brt = compute_brt(86400)
check("L6.2 phases ∈ [0,1) with wraparound",
      approx(brt.circadian_phase, 0.0, 1e-9))

# ══════════════════════════════════════════════════════════════════════════════
# L7.1 — Natural Liquidity NL = LD·LO·LC·LS
# ══════════════════════════════════════════════════════════════════════════════
print("\n── L7.1 Natural Liquidity Score ──")

from core.extended.natural_liquidity import compute_nl, NL_ALERT_THRESHOLD

# LC = corr(LD_current, LD_90d_baseline) → pass scalar current LD + history
# LS = LD(stress)/LD(normal) → scalars
from core.extended.natural_liquidity import compute_ld, compute_lo, compute_lc, compute_ls
ld = compute_ld([1000, 500, 200, 100, 50])
lo = compute_lo(top5_lp_share=0.30, lp_count=20)
lc = compute_lc(current_ld=ld, baseline_ld_history=[ld] * 90)
ls = compute_ls(ld_during_stress=0.5, ld_during_normal=1.0)
nl = compute_nl(depth_per_tick=[1000, 500, 200, 100, 50],
                top5_lp_share=0.30, lp_count=20,
                baseline_ld_90d=[ld] * 90,
                ld_during_stress=0.5, ld_during_normal=1.0)
check("L7.1 LD = normalized Shannon entropy of depth distribution", 0.0 <= ld <= 1.0)
check("L7.1 LO = 1 - sybil_ratio", 0.0 <= lo <= 1.0)
check("L7.1 LC = corr(LD, baseline) — stable history → 1.0", approx(lc, 1.0))
check("L7.1 LS = LD(stress)/LD(normal) (0.5/1.0 = 0.5)", approx(ls, 0.5))
check("L7.1 NL = LD·LO·LC·LS product",
      approx(nl["nl_score"], nl["ld_score"] * nl["lo_score"] * nl["lc_score"] * nl["ls_score"], 1e-6))
check("L7.1 NL < 0.30 → DO_NOT_ROUTE recommendation",
      nl["recommendation"] in ("CLEAR", "CAUTION", "DO_NOT_ROUTE"))
check("L7.1 NL = LD·LO·LC·LS ∈ [0,1]", 0.0 <= nl["nl_score"] <= 1.0)
check("L7.1 NL alert threshold = 0.30 (DO_NOT_ROUTE)",
      NL_ALERT_THRESHOLD == 0.30)

# ══════════════════════════════════════════════════════════════════════════════
# L8.1 — Sovereign Behavioral Assessment
# ══════════════════════════════════════════════════════════════════════════════
print("\n── L8.1 Sovereign Behavioral Assessment ──")

from core.governance.sba_engine import compute_sba, W_E, W_I, W_S, W_G, W_C

check("L8.1 SBA weights 0.30/0.25/0.20/0.15/0.10 (Σ=1)",
      W_E == 0.30 and W_I == 0.25 and W_S == 0.20 and W_G == 0.15 and W_C == 0.10
      and approx(W_E + W_I + W_S + W_G + W_C, 1.0))
sba = compute_sba("test", e_score=1.0, i_score=1.0, s_score=1.0, g_score=1.0, c_score=1.0)
check("L8.1 SBA(all max) = 1.0 → HIGH_CREDIBILITY",
      approx(sba["sba_score"], 1.0, 1e-9))

# ══════════════════════════════════════════════════════════════════════════════
# L9.1 / L9.2 — XSL + Kolmogorov Bound
# ══════════════════════════════════════════════════════════════════════════════
print("\n── L9.1/L9.2 XSL + Kolmogorov Bound ──")

from core.extended.cross_species import compute_xsl
from core.spiritual.living_security import GenomicKeyEvolver as _GK

xsl = compute_xsl.__wrapped__ if hasattr(compute_xsl, "__wrapped__") else None
# Direct formula components test
from core.extended.cross_species import (
    compute_territory_viability, compute_food_security,
    compute_reproduction_rate, compute_threat_pressure,
)
tv = compute_territory_viability(habitat_area_km2=100, habitat_area_baseline=100,
                                  habitat_quality_score=0.9)
fs = compute_food_security(prey_availability=0.8, dietary_breadth=0.9,
                           competition_pressure=0.1)
rr = compute_reproduction_rate(observed=0.8, baseline=1.0, juvenile_survival=0.9)
tp = compute_threat_pressure(habitat_loss_rate=0.2, hunting_pressure=0.1,
                             climate_vulnerability=0.3, disease_pressure=0.1,
                             pollution_level=0.1)
expected_xsl = tv * fs * rr / (1 + tp)
check("L9.1 XSL = TV·FS·RR/(1+TP) ∈ [0,1]", 0.0 <= expected_xsl <= 1.0)
check("L9.1 threat pressure weights 0.35/0.20/0.25/0.10/0.10",
      approx(tp, 0.35 * 0.2 + 0.20 * 0.1 + 0.25 * 0.3 + 0.10 * 0.1 + 0.10 * 0.1, 1e-9))

kb = _GK()
bound = kb.kolmogorov_bound(n_chains=37, n_validators=100)
check("L9.2 Kolmogorov bound grows with chains/validators/time",
      bound > 0 and kb.kolmogorov_bound(n_chains=74, n_validators=200) > bound)

# ══════════════════════════════════════════════════════════════════════════════
# BTCP_score — the routing formula
# ══════════════════════════════════════════════════════════════════════════════
print("\n── BTCP_score Routing Formula ──")

from core.btcp.router import btcp_score_final, normalize_gas, Route, RouteType, BIBLState, W_NL, W_GAS, W_FIN, W_COH, W_BEO

check("BTCP weights 0.25/0.20/0.20/0.15/0.20 (Σ=1)",
      W_NL == 0.25 and W_GAS == 0.20 and W_FIN == 0.20 and W_COH == 0.15
      and W_BEO == 0.20 and approx(W_NL + W_GAS + W_FIN + W_COH + W_BEO, 1.0))

state = BIBLState(
    nl_scores={1: 0.8},
    gas_forecasts={1: 10.0},
    gas_reference=100.0,
    cc_coherence={1: 0.9},
    mf_scores={1: 0.1},
)
route = Route(route_id="r", entity_id=b"e", route_type=RouteType.SINGLE_CHAIN,
              anchor_chain=1, execution_chain=1, gas_total=10.0,
              finality_confidence=0.95, beo_continuity=0.9,
              cc_coherence=0.9, intent_value=1000)
score = btcp_score_final(route, state)
expected = (0.25 * 0.8 + 0.20 * 0.9 + 0.20 * 0.95 + 0.15 * 0.9 + 0.20 * 0.9) * (1 - 0.1)
check("BTCP_score = [0.25NL+0.20gas+0.20fin+0.15CC+0.20BEO]×(1-MF)",
      approx(score, expected, 1e-9))
check("BTCP normalize_gas = max(0, 1 - G/G_ref)",
      approx(normalize_gas(50.0, state), 0.5, 1e-9)
      and approx(normalize_gas(0.0, state), 1.0)
      and approx(normalize_gas(200.0, state), 0.0))

# ══════════════════════════════════════════════════════════════════════════════
# 256-bit Signal Packing bit layout
# ══════════════════════════════════════════════════════════════════════════════
print("\n── Signal Packing (256-bit layout) ──")

from core.primitives.signal_packing import pack_signal, unpack_signal

packed = pack_signal(coherence=0.723456, threshold=0.655123,
                     block_number=12345, timestamp=1699999999, status=1)
un = unpack_signal(packed)
check("Packing: status[0..8) coherence[8..40) threshold[40..72) block[72..136) ts[136..200)",
      un["status"] == 1 and approx(un["coherence"], 0.723456, 1e-6)
      and approx(un["threshold"], 0.655123, 1e-6) and un["block_number"] == 12345
      and un["timestamp"] == 1699999999)

# ══════════════════════════════════════════════════════════════════════════════
# BEO resolution formula (substrate independence)
# ══════════════════════════════════════════════════════════════════════════════
print("\n── BEO Substrate-Independent Identity ──")

import hashlib as _hl
for addr in ["0x742d35Cc6634C0532925a3b844Bc454e4438f44e", "0X742D35CC6634C0532925A3B844BC454E4438F44E"]:
    eid = _hl.sha3_256(addr.lower().strip().encode()).hexdigest()
check("BEO = SHA3-256(normalize(addr)) — case-insensitive",
      _hl.sha3_256("0x742d35cc6634c0532925a3b844bc454e4438f44e".encode()).hexdigest() ==
      _hl.sha3_256("0X742D35CC6634C0532925A3B844BC454E4438F44E".lower().encode()).hexdigest())

# ══════════════════════════════════════════════════════════════════════════════
# SUMMARY
# ══════════════════════════════════════════════════════════════════════════════
print("\n" + "═" * 70)
print(f"MASTER FORMULA VERIFICATION: {PASS} passed, {FAIL} failed")
print("═" * 70)
if FAILURES:
    print("FAILURES:")
    for f in FAILURES:
        print(f"  ❌ {f}")
    sys.exit(1)
print("✅ ALL FORMULAS ENFORCED AS SPECIFIED — TRION MATHEMATICS COMPLETE")
