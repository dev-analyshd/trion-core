"""
distribution_coherence.py — Protocol-level Mental plane substitute.

The standard Mental plane (M) measures intent consistency of a single identity
over time.  For protocol contracts this is meaningless because thousands of
diverse callers produce inherently chaotic intent signals.

This module replaces M with a distribution-stability score:

  DC(t) = 1 - JSD(P_current || P_baseline)

Where:
  P_current  = event-type distribution in the current observation window
  P_baseline = rolling 30-day event-type distribution (expected behaviour)
  JSD        = Jensen-Shannon divergence (symmetric, bounded [0, 1])

DC(t) = 1.0  → current activity perfectly matches baseline (stable)
DC(t) = 0.0  → current activity is completely unlike baseline (anomaly)

Attack detection: a flash-loan exploit typically shifts P_current to
>80% FLASH_LOAN / LIQUIDATE from a baseline of ~5-10%, driving DC toward 0.

References: whitepaper §4.2 (Mental Plane), §6.3 (Protocol Coherence Extension)
"""

from __future__ import annotations

import math
import time
import logging
from collections import defaultdict

log = logging.getLogger(__name__)

ALL_EVENT_TYPES = [
    "SWAP", "LIQUIDITY", "BORROW", "LIQUIDATE", "GOVERNANCE",
    "PROPOSAL", "STAKE", "UNSTAKE", "BRIDGE", "DEPLOY",
    "MINT", "BURN", "FLASH_LOAN", "MEV_CAPTURE", "AIRDROP", "CLAIM",
]


def _normalise(dist: dict) -> dict:
    total = sum(dist.values())
    if total == 0:
        uniform = 1.0 / len(ALL_EVENT_TYPES)
        return {k: uniform for k in ALL_EVENT_TYPES}
    base = {k: dist.get(k, 0) / total for k in ALL_EVENT_TYPES}
    return base


def _smooth(dist: dict, epsilon: float = 1e-9) -> dict:
    return {k: max(v, epsilon) for k, v in dist.items()}


def _entropy(p: dict) -> float:
    return -sum(v * math.log2(v) for v in p.values() if v > 0)


def jensen_shannon_divergence(p: dict, q: dict) -> float:
    """
    Compute JSD(P || Q) in [0, 1].
    JSD = 0 → identical distributions.
    JSD = 1 → maximally different distributions.
    """
    p_norm = _smooth(_normalise(p))
    q_norm = _smooth(_normalise(q))

    m = {k: (p_norm[k] + q_norm[k]) / 2.0 for k in ALL_EVENT_TYPES}

    kl_pm = sum(p_norm[k] * math.log2(p_norm[k] / m[k]) for k in ALL_EVENT_TYPES if p_norm[k] > 0)
    kl_qm = sum(q_norm[k] * math.log2(q_norm[k] / m[k]) for k in ALL_EVENT_TYPES if q_norm[k] > 0)

    jsd = (kl_pm + kl_qm) / 2.0
    return min(max(jsd, 0.0), 1.0)


def distribution_coherence_score(current: dict, baseline: dict) -> float:
    """
    DC(t) = 1 - JSD(current || baseline)
    Returns float in [0, 1]. Higher = more coherent (stable).
    """
    if not current or not baseline:
        return 0.5
    jsd = jensen_shannon_divergence(current, baseline)
    return round(1.0 - jsd, 6)


class DistributionCoherenceEngine:
    """
    Maintains a rolling baseline for a protocol contract and computes DC(t).

    Usage:
        engine = DistributionCoherenceEngine()
        engine.update_baseline("0xUniswap", activity_30d)
        score = engine.compute("0xUniswap", current_activity)
    """

    def __init__(self, baseline_window_days: int = 30):
        self._baselines: dict[str, dict] = {}
        self._history: dict[str, list] = defaultdict(list)
        self._window_days = baseline_window_days

    def update_baseline(self, protocol: str, distribution: dict) -> None:
        snapshot = {"ts": time.time(), "dist": distribution}
        self._history[protocol].append(snapshot)
        cutoff = time.time() - self._baseline_window_sec
        self._history[protocol] = [
            s for s in self._history[protocol] if s["ts"] >= cutoff
        ]
        merged: dict = defaultdict(float)
        for snap in self._history[protocol]:
            for k, v in snap["dist"].items():
                merged[k] += v
        total = sum(merged.values())
        if total > 0:
            self._baselines[protocol] = {k: v / total for k, v in merged.items()}
        else:
            self._baselines[protocol] = {}

    @property
    def _baseline_window_sec(self) -> float:
        return self._window_days * 86400

    def compute(
        self,
        protocol: str,
        current_distribution: dict,
        window_label: str = "1h",
    ) -> dict:
        baseline = self._baselines.get(protocol, {})
        if not baseline:
            baseline = current_distribution

        dc = distribution_coherence_score(current_distribution, baseline)
        jsd = jensen_shannon_divergence(current_distribution, baseline)

        anomaly_events = self._find_anomalous_events(
            current_distribution, baseline
        )

        attack_probability = self._estimate_attack_probability(
            current_distribution, jsd
        )

        return {
            "distribution_coherence": dc,
            "jsd": round(jsd, 6),
            "window": window_label,
            "baseline_available": bool(baseline),
            "anomalous_events": anomaly_events,
            "attack_probability": attack_probability,
            "current_distribution": {k: round(v, 6) for k, v in _normalise(current_distribution).items() if v > 0.001},
            "baseline_distribution": {k: round(v, 6) for k, v in _normalise(baseline).items() if v > 0.001},
            "interpretation": self._interpret(dc),
        }

    def _find_anomalous_events(
        self, current: dict, baseline: dict, threshold: float = 3.0
    ) -> list:
        cur_norm = _normalise(current)
        base_norm = _normalise(baseline)
        anomalies = []
        for evt in ALL_EVENT_TYPES:
            cur_v = cur_norm.get(evt, 0)
            base_v = base_norm.get(evt, 1e-9)
            ratio = cur_v / max(base_v, 1e-9)
            if ratio >= threshold and cur_v > 0.02:
                anomalies.append({
                    "event": evt,
                    "current_ratio": round(cur_v, 4),
                    "baseline_ratio": round(base_v, 4),
                    "spike_factor": round(ratio, 2),
                })
        return sorted(anomalies, key=lambda x: -x["spike_factor"])

    def _estimate_attack_probability(self, current: dict, jsd: float) -> float:
        cur_norm = _normalise(current)
        flash = cur_norm.get("FLASH_LOAN", 0)
        liq = cur_norm.get("LIQUIDATE", 0)
        mev = cur_norm.get("MEV_CAPTURE", 0)
        attack_signal = flash * 0.45 + liq * 0.30 + mev * 0.25
        divergence_signal = jsd * 0.4
        p = min(attack_signal + divergence_signal, 1.0)
        return round(p, 4)

    @staticmethod
    def _interpret(dc: float) -> str:
        if dc >= 0.85:
            return "STABLE — behaviour matches baseline; normal protocol activity"
        if dc >= 0.65:
            return "DRIFTING — moderate divergence; elevated monitoring recommended"
        if dc >= 0.40:
            return "ANOMALOUS — significant divergence; potential stress or manipulation"
        return "CRITICAL — extreme divergence; possible active exploit or governance attack"
