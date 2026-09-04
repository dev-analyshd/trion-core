"""
TRION CONTINUUM — Phase 4: Five Continuum Engines
===================================================

Per BTCP Master Spec §Phase 4, CONTINUUM is the Behavioral Clearing
Network (L3) with 5 engines:

  4.1: BID — Behavioral Intent Detection
  4.2: CME — Complement Matching Engine
  4.3: PMO — Pre-Manifest Order System
  4.4: BDC — Behavioral Depth Credit
  4.5: Thermodynamic Settlement Triggers
  +    CCP — Complement Certainty Premium distribution

Author: TRION Protocol — Originator: Hudu Yusuf (Analys)
License: CC0
"""

from __future__ import annotations

import hashlib
import math
import time
from dataclasses import dataclass, field
from typing import Dict, List, Optional, Tuple, Any
from enum import IntEnum


# ═══════════════════════════════════════════════════════════════════════════════
# Engine 4.1: BID — Behavioral Intent Detection
# ═══════════════════════════════════════════════════════════════════════════════

@dataclass
class BIDResult:
    """Result of Behavioral Intent Detection."""
    confidence: float           # 0-1
    direction: str              # "BUY" or "SELL" or "NEUTRAL"
    feature_delta: List[float]  # 9-dim Shannon entropy delta
    pretrade_match: float       # cosine similarity to pretrade signature
    depth_factor: float         # min(1, D/D_min)
    detected: bool


class BIDEngine:
    """
    Engine 4.1: Behavioral Intent Detection.

    BID_confidence(entity, t) = cosine_similarity(feature_delta, pretrade_signature)
                                × min(1.0, D(t) / D_minimum)

    Where:
      - feature_delta = current_phi_features - baseline_phi_features (9-dim Shannon entropy)
      - pretrade_signature = learned from historical trade events in Akashic Index
      - Baseline = 90-day historical average per entity

    Direction Estimation:
      - Buyers: increased counterparty diversity, temporal acceleration, cross-protocol exploration
      - Sellers: decreased counterparty diversity, temporal deceleration, concentrated value flow

    Key Constraint: Nothing happens without entity confirmation. BID is detection,
    not commitment. Entity is offered PMO proposal and can accept or decline.
    """

    D_MINIMUM = 100.0  # minimum behavioral depth for full confidence

    def detect(
        self,
        current_features: List[float],     # 9-dim Shannon entropy
        baseline_features: List[float],    # 90-day average
        pretrade_signature: List[float],   # learned from historical trades
        depth_d: float,                    # D(t) — akashic depth
    ) -> BIDResult:
        """Detect behavioral intent from feature delta."""
        # Compute feature delta
        if len(current_features) != len(baseline_features):
            return BIDResult(0.0, "NEUTRAL", [], 0.0, 0.0, False)

        feature_delta = [c - b for c, b in zip(current_features, baseline_features)]

        # Cosine similarity to pretrade signature
        cos_sim = self._cosine_similarity(feature_delta, pretrade_signature)

        # Depth factor
        depth_factor = min(1.0, depth_d / self.D_MINIMUM)

        # Confidence
        confidence = cos_sim * depth_factor

        # Direction estimation
        if len(feature_delta) >= 3:
            # Buyers: features 0 (counterparty diversity) increases,
            #         features 1 (temporal) accelerates,
            #         features 2 (cross-protocol) explores
            buyer_signal = (feature_delta[0] > 0) and (feature_delta[1] > 0) and (feature_delta[2] > 0)
            seller_signal = (feature_delta[0] < 0) and (feature_delta[1] < 0) and (feature_delta[2] < 0)

            if buyer_signal and confidence > 0.5:
                direction = "BUY"
            elif seller_signal and confidence > 0.5:
                direction = "SELL"
            else:
                direction = "NEUTRAL"
        else:
            direction = "NEUTRAL"

        detected = confidence > 0.3 and direction != "NEUTRAL"

        return BIDResult(
            confidence=confidence,
            direction=direction,
            feature_delta=feature_delta,
            pretrade_match=cos_sim,
            depth_factor=depth_factor,
            detected=detected,
        )

    def _cosine_similarity(self, v1: List[float], v2: List[float]) -> float:
        n = min(len(v1), len(v2))
        if n < 2:
            return 0.0
        dot = sum(v1[i] * v2[i] for i in range(n))
        mag1 = math.sqrt(sum(x * x for x in v1[:n]))
        mag2 = math.sqrt(sum(x * x for x in v2[:n]))
        if mag1 == 0 or mag2 == 0:
            return 0.0
        return dot / (mag1 * mag2)


# ═══════════════════════════════════════════════════════════════════════════════
# Engine 4.2: CME — Complement Matching Engine
# ═══════════════════════════════════════════════════════════════════════════════

@dataclass
class CMEResult:
    """Result of complement matching."""
    complement_id: Optional[bytes]
    complement_score: float
    direction_complement: float
    temporal_alignment: float
    behavioral_health: float
    beo_independence: float
    liquidity_sufficiency: float
    matched: bool


class CMEEngine:
    """
    Engine 4.2: Complement Matching Engine.

    COMPLEMENT_score(A, B) = behavioral_direction_complement(A, B)
                           × temporal_alignment(A, B)
                           × behavioral_health(B)              # C(t) > Θ(t)
                           × beo_independence(A, B)            # not coordinated
                           × liquidity_sufficiency(B)

    Operates on FAISS behavioral vector similarity across 531,200+ BEO entities.
    Semantic matching — finds entities whose behavioral DNA complements the
    querying entity's trajectory. Not an order book. No price ladder.
    Price from TRION VALUATION signal.
    """

    def find_complement(
        self,
        entity_a_vector: List[float],     # 128-dim BEO vector
        entity_a_direction: str,           # "BUY" or "SELL"
        candidate_pool: List[Dict],        # [{entity_id, vector, direction, health, liquidity, ...}]
        temporal_window: Tuple[float, float] = (0, 3600),  # RELATIVE seconds vs. now — "intent expressed within the last hour"
        independence_threshold: float = 0.3,
    ) -> CMEResult:
        """Find the best complement for entity A.

        ``temporal_window`` is interpreted as a RELATIVE window in seconds
        measured against the current time (the moment of the match attempt):
        a candidate is temporally aligned when its intent ``timestamp`` is
        ``temporal_window[0]``–``temporal_window[1]`` seconds old. Candidate
        timestamps are epoch values (~1.7e9), so they must never be compared
        against the window bounds directly.
        """
        best_score = 0.0
        best_candidate = None
        best_components = {
            "direction": 0.0, "temporal": 0.0, "health": 0.0,
            "independence": 0.0, "liquidity": 0.0,
        }
        now = time.time()

        for candidate in candidate_pool:
            # Direction complement: A buys ↔ B sells
            dir_comp = 1.0 if (
                (entity_a_direction == "BUY" and candidate.get("direction") == "SELL") or
                (entity_a_direction == "SELL" and candidate.get("direction") == "BUY")
            ) else 0.0

            if dir_comp == 0.0:
                continue  # no complement possible

            # Temporal alignment — RELATIVE window: the candidate's intent
            # age (now - timestamp) must fall inside temporal_window. (The
            # old code compared the raw epoch timestamp against the (0, 3600)
            # bounds, which could never match, so every candidate silently
            # received the 0.5 fallback.)
            candidate_time = candidate.get("timestamp", now)
            intent_age = now - candidate_time
            temporal_align = 1.0 if temporal_window[0] <= intent_age <= temporal_window[1] else 0.5

            # Behavioral health: C(t) > Θ(t)
            health = candidate.get("behavioral_health", 0.5)
            if health < 0.55:  # below threshold
                continue

            # BEO independence: low cosine similarity = independent
            cos_sim = self._cosine_similarity(entity_a_vector, candidate.get("vector", []))
            independence = max(0.0, 1.0 - cos_sim)
            if independence < independence_threshold:
                continue  # too similar — likely coordinated

            # Liquidity sufficiency
            liquidity = candidate.get("liquidity", 0.5)

            # Combined score (multiplicative)
            score = dir_comp * temporal_align * health * independence * liquidity

            if score > best_score:
                best_score = score
                best_candidate = candidate
                best_components = {
                    "direction": dir_comp,
                    "temporal": temporal_align,
                    "health": health,
                    "independence": independence,
                    "liquidity": liquidity,
                }

        return CMEResult(
            complement_id=best_candidate.get("entity_id") if best_candidate else None,
            complement_score=best_score,
            direction_complement=best_components["direction"],
            temporal_alignment=best_components["temporal"],
            behavioral_health=best_components["health"],
            beo_independence=best_components["independence"],
            liquidity_sufficiency=best_components["liquidity"],
            matched=best_candidate is not None and best_score > 0.3,
        )

    def _cosine_similarity(self, v1: List[float], v2: List[float]) -> float:
        n = min(len(v1), len(v2))
        if n < 2:
            return 0.0
        dot = sum(v1[i] * v2[i] for i in range(n))
        mag1 = math.sqrt(sum(x * x for x in v1[:n]))
        mag2 = math.sqrt(sum(x * x for x in v2[:n]))
        if mag1 == 0 or mag2 == 0:
            return 0.0
        return dot / (mag1 * mag2)


# ═══════════════════════════════════════════════════════════════════════════════
# Engine 4.3: PMO — Pre-Manifest Order System
# ═══════════════════════════════════════════════════════════════════════════════

@dataclass
class PreManifestOrder:
    """PMO instrument."""
    entity_id:              bytes
    behavioral_commitment:  bytes   # Hash_DNA(intent || entity_BH || nonce)
    price_guarantee:        float   # TRION_VALUATION + CCP_premium
    complement_id:          bytes
    valid_blocks:           int = 100
    escrow_required:        bool = True
    privacy_mode:           int = 0  # ZK_COMMITMENT
    created_at:             float = field(default_factory=time.time)
    status:                 str = "ACTIVE"  # ACTIVE / FILLED / EXPIRED / CANCELLED


class PMOSystem:
    """
    Engine 4.3: Pre-Manifest Order System.

    In exchange for behavioral commitment BEFORE expressing intent to any market:
    1. ✅ Price guaranteed at TRION VALUATION + CCP bonus
    2. ✅ No slippage (counterparty already found)
    3. ✅ No MEV (commitment is hash, not direction)
    4. ✅ No bridge risk (BTCP settlement)
    5. ✅ Complement Certainty Premium earned

    Strictly better than any exchange for any entity who accepts it.
    Adoption is economically rational, not forced.
    """

    def __init__(self):
        self._pmos: Dict[bytes, PreManifestOrder] = {}

    def create_pmo(
        self,
        entity_id: bytes,
        intent_data: bytes,
        entity_bh: bytes,
        nonce: int,
        trion_valuation: float,
        ccp_premium: float,
        complement_id: bytes,
        valid_blocks: int = 100,
        privacy_mode: int = 0,
    ) -> PreManifestOrder:
        """Create a new PMO with behavioral commitment."""
        # Compute behavioral commitment: Hash_DNA(intent || entity_BH || nonce)
        commitment_input = intent_data + entity_bh + nonce.to_bytes(32, "big")
        behavioral_commitment = hashlib.sha3_256(commitment_input).digest()

        pmo = PreManifestOrder(
            entity_id=entity_id,
            behavioral_commitment=behavioral_commitment,
            price_guarantee=trion_valuation + ccp_premium,
            complement_id=complement_id,
            valid_blocks=valid_blocks,
            privacy_mode=privacy_mode,
        )
        self._pmos[behavioral_commitment] = pmo
        return pmo

    def fill_pmo(self, commitment: bytes) -> bool:
        """Fill a PMO — counterparty has accepted."""
        pmo = self._pmos.get(commitment)
        if not pmo or pmo.status != "ACTIVE":
            return False
        pmo.status = "FILLED"
        return True

    def expire_pmo(self, commitment: bytes) -> bool:
        """Expire a PMO after valid_blocks."""
        pmo = self._pmos.get(commitment)
        if not pmo:
            return False
        pmo.status = "EXPIRED"
        return True

    def get_pmo(self, commitment: bytes) -> Optional[PreManifestOrder]:
        return self._pmos.get(commitment)


# ═══════════════════════════════════════════════════════════════════════════════
# Engine 4.4: BDC — Behavioral Depth Credit
# ═══════════════════════════════════════════════════════════════════════════════

class BDCEngine:
    """
    Engine 4.4: Behavioral Depth Credit.

    BDC_credit_limit(entity) = D(t) × behavioral_consistency_ratio
                              × avg_trade_size_90d × confidence_multiplier

    behavioral_consistency_ratio = 1 - (std_dev(Φ(t)) / mean(Φ(t))) over 90 days
    confidence_multiplier = min(2.0, D(t) / D_minimum)

    Properties of D(t) as collateral:
    - ❌ Cannot be bought (only accumulated through time and honest behavior)
    - ❌ Cannot be transferred (belongs to BEO, not wallet key)
    - ❌ Cannot be lost (lives in Akashic Index, append-only forever)
    - ❌ Cannot be forged (Kolmogorov complexity bound grows without bound)
    - ✅ Compounds automatically (every honest trade increases it)

    Result: Entity with 2 years consistent history can participate at up to
    10× typical trade size backed by behavioral depth, not locked capital.
    """

    D_MINIMUM = 100.0

    def compute_credit_limit(
        self,
        depth_d: float,                    # D(t)
        phi_history_90d: List[float],      # Φ(t) values over 90 days
        avg_trade_size_90d: float,         # average trade size (USD)
    ) -> Dict:
        """Compute BDC credit limit."""
        if not phi_history_90d or len(phi_history_90d) < 2:
            return {
                "credit_limit": 0.0,
                "consistency_ratio": 0.0,
                "confidence_multiplier": 0.0,
                "reason": "insufficient_history",
            }

        mean_phi = sum(phi_history_90d) / len(phi_history_90d)
        variance = sum((x - mean_phi) ** 2 for x in phi_history_90d) / len(phi_history_90d)
        std_dev = math.sqrt(variance)

        # Consistency ratio: 1 - (std/mean)
        if mean_phi <= 0:
            consistency = 0.0
        else:
            consistency = max(0.0, 1.0 - (std_dev / mean_phi))

        # Confidence multiplier: min(2.0, D/D_min)
        confidence_mult = min(2.0, depth_d / self.D_MINIMUM)

        # Credit limit
        credit_limit = depth_d * consistency * avg_trade_size_90d * confidence_mult

        return {
            "credit_limit": credit_limit,
            "consistency_ratio": consistency,
            "confidence_multiplier": confidence_mult,
            "depth_d": depth_d,
            "avg_trade_size": avg_trade_size_90d,
            "std_dev_phi": std_dev,
            "mean_phi": mean_phi,
        }


# ═══════════════════════════════════════════════════════════════════════════════
# Engine 4.5: Thermodynamic Settlement Triggers
# ═══════════════════════════════════════════════════════════════════════════════

@dataclass
class SettlementTrigger:
    """Result of settlement trigger check."""
    triggered: bool
    conditions: Dict[str, bool]
    reason: str


class ThermodynamicSettlement:
    """
    Engine 4.5: Thermodynamic Settlement Triggers.

    SETTLEMENT_TRIGGER = C(entity_A, t) >= Θ(entity_A, t)
        AND C(entity_B, t) >= Θ(entity_B, t)
        AND BTCP_route_verified(route_id)
        AND temporal_alignment_valid(t)
        AND no_manipulation_fingerprint(A, B, t-window)

    When all conditions met: BTCP_ESCROW.release() on both chains simultaneously
    via TRION consensus.

    Key insight: An attacker trying to game settlement must maintain behavioral
    coherence while doing so — which means behaving honestly.
    Behavioral manipulation is self-defeating by construction.
    """

    def check_trigger(
        self,
        coherence_a: float, threshold_a: float,
        coherence_b: float, threshold_b: float,
        btcp_route_verified: bool,
        temporal_alignment_valid: bool,
        mf_detected: bool,
    ) -> SettlementTrigger:
        """Check if all 5 settlement conditions are met."""
        conditions = {
            "coherence_a_passes": coherence_a >= threshold_a,
            "coherence_b_passes": coherence_b >= threshold_b,
            "btcp_route_verified": btcp_route_verified,
            "temporal_alignment": temporal_alignment_valid,
            "no_mf": not mf_detected,
        }

        all_met = all(conditions.values())

        if all_met:
            reason = "ALL_CONDITIONS_MET — release both escrows"
        else:
            failed = [k for k, v in conditions.items() if not v]
            reason = f"FAILED: {', '.join(failed)}"

        return SettlementTrigger(
            triggered=all_met,
            conditions=conditions,
            reason=reason,
        )


# ═══════════════════════════════════════════════════════════════════════════════
# CCP — Complement Certainty Premium Distribution
# ═══════════════════════════════════════════════════════════════════════════════

class CCPDistribution:
    """
    Complement Certainty Premium distribution.

    The spread that market makers and MEV bots currently extract flows back
    to both traders.

    CCP_total = (best_exchange_spread - BTCP_routing_cost) × trade_value
    CCP_entity_A = CCP_total × 0.40
    CCP_entity_B = CCP_total × 0.40
    CCP_validators = CCP_total × 0.12
    CCP_protocol = CCP_total × 0.08
    """

    SPLIT_A = 0.40
    SPLIT_B = 0.40
    SPLIT_VALIDATORS = 0.12
    SPLIT_PROTOCOL = 0.08

    def compute_ccp(
        self,
        best_exchange_spread: float,   # e.g., 0.003 (30 bps)
        btcp_routing_cost: float,      # e.g., 0.0005 (5 bps)
        trade_value: float,            # USD
    ) -> Dict:
        """Compute CCP distribution."""
        spread_diff = best_exchange_spread - btcp_routing_cost
        if spread_diff <= 0:
            return {
                "ccp_total": 0.0,
                "ccp_a": 0.0, "ccp_b": 0.0,
                "ccp_validators": 0.0, "ccp_protocol": 0.0,
                "reason": "BTCP_cost_exceeds_exchange_spread",
            }

        ccp_total = spread_diff * trade_value
        return {
            "ccp_total": ccp_total,
            "ccp_a": ccp_total * self.SPLIT_A,
            "ccp_b": ccp_total * self.SPLIT_B,
            "ccp_validators": ccp_total * self.SPLIT_VALIDATORS,
            "ccp_protocol": ccp_total * self.SPLIT_PROTOCOL,
            "best_exchange_spread": best_exchange_spread,
            "btcp_routing_cost": btcp_routing_cost,
            "trade_value": trade_value,
        }


# ── Self-test ──────────────────────────────────────────────────────────────────

if __name__ == "__main__":
    print("=== Phase 4: CONTINUUM Engines Self-test ===\n")

    # 4.1: BID Engine
    bid = BIDEngine()
    result = bid.detect(
        current_features=[0.8, 0.7, 0.9, 0.6, 0.5, 0.4, 0.3, 0.2, 0.1],
        baseline_features=[0.7, 0.6, 0.8, 0.6, 0.5, 0.4, 0.3, 0.2, 0.1],
        pretrade_signature=[0.1, 0.1, 0.1, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0],
        depth_d=500.0,
    )
    print(f"4.1 BID: confidence={result.confidence:.4f}, direction={result.direction}, detected={result.detected}")
    assert result.confidence > 0
    assert result.depth_factor == 1.0  # 500 > 100

    # 4.2: CME Engine
    cme = CMEEngine()
    # Use orthogonal vectors so independence is high
    # entity_a: [1,0,0,...], candidate: [0,1,0,...] → cos_sim=0, independence=1.0
    vec_a = [1.0] + [0.0] * 127
    vec_b = [0.0, 1.0] + [0.0] * 126
    candidates = [
        {"entity_id": b"\x02"*32, "vector": vec_b, "direction": "SELL",
         "behavioral_health": 0.85, "liquidity": 0.9, "timestamp": time.time()},
    ]
    result = cme.find_complement(
        entity_a_vector=vec_a,
        entity_a_direction="BUY",
        candidate_pool=candidates,
    )
    print(f"4.2 CME: score={result.complement_score:.4f}, matched={result.matched}")
    assert result.matched

    # 4.3: PMO System
    pmo_sys = PMOSystem()
    pmo = pmo_sys.create_pmo(
        entity_id=b"\x01"*32,
        intent_data=b"swap 1000 USDC for ETH",
        entity_bh=b"\xAA"*32,
        nonce=42,
        trion_valuation=2000.0,
        ccp_premium=5.0,
        complement_id=b"\x02"*32,
    )
    print(f"4.3 PMO: price_guarantee=${pmo.price_guarantee:.2f}, status={pmo.status}")
    assert pmo.price_guarantee == 2005.0
    assert pmo_sys.fill_pmo(pmo.behavioral_commitment)
    assert pmo_sys.get_pmo(pmo.behavioral_commitment).status == "FILLED"

    # 4.4: BDC Engine
    bdc = BDCEngine()
    result = bdc.compute_credit_limit(
        depth_d=730.0,  # 2 years
        phi_history_90d=[0.8, 0.81, 0.79, 0.8, 0.82, 0.78, 0.8, 0.81, 0.79, 0.8],
        avg_trade_size_90d=1000.0,
    )
    print(f"4.4 BDC: credit_limit=${result['credit_limit']:.2f}, consistency={result['consistency_ratio']:.4f}")
    assert result["credit_limit"] > 0
    assert result["confidence_multiplier"] == 2.0  # min(2, 730/100)

    # 4.5: Thermodynamic Settlement
    ts = ThermodynamicSettlement()
    result = ts.check_trigger(
        coherence_a=0.85, threshold_a=0.55,
        coherence_b=0.80, threshold_b=0.55,
        btcp_route_verified=True,
        temporal_alignment_valid=True,
        mf_detected=False,
    )
    print(f"4.5 Settlement: triggered={result.triggered}, reason={result.reason}")
    assert result.triggered

    # Settlement with MF detected → no trigger
    result_mf = ts.check_trigger(
        coherence_a=0.85, threshold_a=0.55,
        coherence_b=0.80, threshold_b=0.55,
        btcp_route_verified=True,
        temporal_alignment_valid=True,
        mf_detected=True,
    )
    assert not result_mf.triggered

    # CCP Distribution
    ccp = CCPDistribution()
    result = ccp.compute_ccp(
        best_exchange_spread=0.003,  # 30 bps
        btcp_routing_cost=0.0005,    # 5 bps
        trade_value=10_000.0,
    )
    print(f"4.6 CCP: total=${result['ccp_total']:.2f}, A=${result['ccp_a']:.2f}, B=${result['ccp_b']:.2f}")
    assert result["ccp_total"] == 25.0  # (0.003 - 0.0005) × 10000
    assert result["ccp_a"] == 10.0       # 40% of 25
    assert result["ccp_b"] == 10.0       # 40% of 25
    assert result["ccp_validators"] == 3.0  # 12% of 25
    assert result["ccp_protocol"] == 2.0    # 8% of 25

    # Verify split sums to 1.0
    total_split = ccp.SPLIT_A + ccp.SPLIT_B + ccp.SPLIT_VALIDATORS + ccp.SPLIT_PROTOCOL
    assert abs(total_split - 1.0) < 1e-9

    print("\nPHASE 4 PASS — All 5 CONTINUUM engines implemented")
