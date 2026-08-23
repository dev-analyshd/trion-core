"""
protocol_health.py — Aggregate protocol health score from user distribution.

Solves the core identity-aggregation problem: instead of one incoherent C(t)
for the contract address, compute a distribution-aware health score H(t) that
reflects the behavioural quality of the protocol's actual user base.

H(t) formula
------------
  H(t) = w1·DC(t) + w2·RoleCoherence(t) + w3·UserQuality(t) + w4·AttackSurface(t)

  DC(t)           — Distribution Coherence score (JSD-based Mental substitute)
  RoleCoherence   — Shannon entropy of role distribution (diverse but stable)
  UserQuality     — Mean C(t) of top-N users (proxy from magnitude + diversity)
  AttackSurface   — 1 - attack_probability from distribution coherence engine

Weights:  w1=0.35, w2=0.20, w3=0.30, w4=0.15

Output aligns with the existing C(t) scale [0, 1] so it can be compared
directly against Θ(t) and displayed on the same dashboard.
"""

from __future__ import annotations

import math
import time
import logging
from dataclasses import dataclass, field
from typing import Optional

from .segmentation import ProtocolSegmenter
from .role_classifier import RoleClassifier, DeFiRole
from .distribution_coherence import DistributionCoherenceEngine

log = logging.getLogger(__name__)

_W_DC           = 0.35
_W_ROLE_COH     = 0.20
_W_USER_QUALITY = 0.30
_W_ATTACK_SURF  = 0.15


@dataclass
class ProtocolHealthResult:
    address: str
    health_score: float
    grade: str
    components: dict
    role_distribution: dict
    top_users: list
    dc_result: dict
    sub_entity_count: int
    attacker_wallets: list
    recommendations: list
    computed_at: float = field(default_factory=time.time)


def _role_coherence(role_counts: dict) -> float:
    total = sum(role_counts.values())
    if total == 0:
        return 0.0
    probs = [v / total for v in role_counts.values() if v > 0]
    entropy = -sum(p * math.log2(p) for p in probs)
    max_entropy = math.log2(len(DeFiRole) - 1)
    normalised = entropy / max_entropy if max_entropy > 0 else 0
    stability_bonus = 1.0 - abs(normalised - 0.65)
    return round(min(max(stability_bonus, 0.0), 1.0), 6)


def _user_quality_proxy(sub_entities: list, classifier: RoleClassifier) -> float:
    if not sub_entities:
        return 0.5
    scores = []
    for se in sub_entities:
        role_res = classifier.classify(
            se.event_type_counts, se.tx_count, se.magnitude_stats
        )
        confidence = role_res.confidence
        risk_penalty = {"LOW": 0.0, "MEDIUM": 0.1, "HIGH": 0.25, "UNKNOWN": 0.15}.get(
            role_res.risk_level, 0.15
        )
        tx_bonus = min(math.log10(max(se.tx_count, 1)) / 3.0, 0.2)
        user_score = max(0.0, min(confidence * 0.7 + tx_bonus - risk_penalty, 1.0))
        scores.append(user_score)
    return round(sum(scores) / len(scores), 6)


def _grade(score: float) -> str:
    if score >= 0.80:
        return "A"
    if score >= 0.65:
        return "B"
    if score >= 0.50:
        return "C"
    if score >= 0.35:
        return "D"
    return "F"


def _recommendations(result: "ProtocolHealthResult") -> list:
    recs = []
    dc = result.dc_result.get("distribution_coherence", 1.0)
    attack_p = result.dc_result.get("attack_probability", 0.0)
    role_dist = result.role_distribution

    if dc < 0.5:
        recs.append("URGENT: Distribution coherence critical — investigate FLASH_LOAN and LIQUIDATE spikes")
    elif dc < 0.7:
        recs.append("Monitor: Event distribution drifting from baseline — elevated activity in unusual event types")

    if attack_p > 0.4:
        recs.append(f"ALERT: Attack probability {attack_p:.1%} — consider pausing protocol or raising collateral requirements")

    mev_share = role_dist.get(DeFiRole.MEV_BOT.value, 0)
    if mev_share > 0.25:
        recs.append(f"MEV bots represent {mev_share:.0%} of callers — consider MEV protection (private mempool, commit-reveal)")

    liq_share = role_dist.get(DeFiRole.LIQUIDATOR.value, 0)
    if liq_share > 0.30:
        recs.append("High liquidator concentration — protocol may be under collateral stress")

    if result.sub_entity_count < 5:
        recs.append("Insufficient user data in bh_ledger for this contract — try monitoring at individual wallet level")

    if result.health_score < 0.35:
        recs.append("Health score F — integrate commit-reveal stake attestations to boost Conscious-plane equivalent")

    if not recs:
        recs.append("Protocol health nominal — continue monitoring")

    return recs


class ProtocolHealthEngine:
    """
    Computes aggregate health score H(t) for a protocol contract.

    Usage:
        engine = ProtocolHealthEngine()
        result = engine.compute("0xUniswapV3Pool", top_n=50)
    """

    def __init__(self):
        self._segmenter = ProtocolSegmenter()
        self._classifier = RoleClassifier()
        self._dc_engine = DistributionCoherenceEngine()

    def compute(
        self,
        contract_address: str,
        top_n: int = 50,
        window_seconds: int = 3600,
    ) -> ProtocolHealthResult:
        sub_entities = self._segmenter.get_sub_entities(
            contract_address, limit=top_n
        )

        current_dist = self._segmenter.get_protocol_activity(
            contract_address, window_seconds=window_seconds
        )
        global_dist = self._segmenter.get_global_activity(
            window_seconds=window_seconds * 24
        )

        self._dc_engine.update_baseline(contract_address, global_dist or current_dist)
        dc_result = self._dc_engine.compute(contract_address, current_dist)

        classified = self._classifier.classify_batch(sub_entities)
        role_counts: dict = {}
        for se, role_res in classified:
            r = role_res.role.value
            role_counts[r] = role_counts.get(r, 0) + 1

        role_total = sum(role_counts.values())
        role_distribution = {
            k: round(v / role_total, 4) for k, v in role_counts.items()
        } if role_total > 0 else {}

        top_users = []
        for se, role_res in classified[:20]:
            top_users.append({
                "caller": se.caller,
                "role": role_res.role.value,
                "archetype": role_res.archetype,
                "risk_level": role_res.risk_level,
                "confidence": role_res.confidence,
                "tx_count": se.tx_count,
                "dominant_event": se.dominant_event,
                "chains": se.chains,
                "magnitude_mean": se.magnitude_stats.get("mean", 0),
                "last_seen": se.last_seen,
            })

        attacker_wallets = [
            u for u in top_users
            if u["role"] in ("MEV_BOT", "LIQUIDATOR") and u["confidence"] > 0.5
        ]

        dc_score = dc_result.get("distribution_coherence", 0.5)
        role_coh = _role_coherence(role_counts)
        user_qual = _user_quality_proxy(sub_entities, self._classifier)
        attack_surf = 1.0 - dc_result.get("attack_probability", 0.0)

        h_score = (
            _W_DC * dc_score
            + _W_ROLE_COH * role_coh
            + _W_USER_QUALITY * user_qual
            + _W_ATTACK_SURF * attack_surf
        )
        h_score = round(min(max(h_score, 0.0), 1.0), 6)

        preliminary = ProtocolHealthResult(
            address=contract_address,
            health_score=h_score,
            grade=_grade(h_score),
            components={
                "distribution_coherence": round(dc_score, 4),
                "role_coherence": round(role_coh, 4),
                "user_quality": round(user_qual, 4),
                "attack_surface": round(attack_surf, 4),
                "weights": {
                    "w_dc": _W_DC,
                    "w_role_coherence": _W_ROLE_COH,
                    "w_user_quality": _W_USER_QUALITY,
                    "w_attack_surface": _W_ATTACK_SURF,
                },
            },
            role_distribution=role_distribution,
            top_users=top_users,
            dc_result=dc_result,
            sub_entity_count=len(sub_entities),
            attacker_wallets=attacker_wallets,
            recommendations=[],
        )
        preliminary.recommendations = _recommendations(preliminary)
        return preliminary
