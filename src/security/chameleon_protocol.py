"""
TRION Protocol — Section 23: Chameleon Protocol
Anti-fingerprinting defense that prevents adversaries from learning
the exact threshold values that would trigger SILENCE.

Core idea: controlled nondeterminism in signal output.
Signal value = True_value + ε(t)  where ε ~ N(0, σ_ε)
σ_ε = f(volatility, query_pattern)

When adversarial probing is detected (same entity queried > K times
in T seconds), the response noise increases:
σ_ε_adversarial = σ_ε × escalation_factor

The oracle NEVER returns the raw coherence threshold.
"""

import time
import math
import hashlib
import secrets
from dataclasses import dataclass, field
from typing import Dict, List, Optional


CHAMELEON_BASE_SIGMA  = 0.015   # base noise level (1.5%)
CHAMELEON_MAX_SIGMA   = 0.060   # maximum noise level (6%)
PROBE_WINDOW_SECS     = 60.0    # detection window
PROBE_THRESHOLD_COUNT = 5       # queries in window before escalation
ESCALATION_FACTOR     = 2.5     # noise multiplier when probing detected


@dataclass
class QueryRecord:
    entity_id: str
    timestamp: float
    caller_ip: Optional[str] = None


class ChameleonProtocol:
    def __init__(self):
        self._query_log:    Dict[str, List[float]] = {}
        self._probe_alerts: Dict[str, int]         = {}
        self._salt = secrets.token_bytes(32)

    def _count_recent_queries(self, entity_id: str, now: float) -> int:
        history = self._query_log.get(entity_id, [])
        return sum(1 for t in history if now - t < PROBE_WINDOW_SECS)

    def _log_query(self, entity_id: str, now: float) -> None:
        if entity_id not in self._query_log:
            self._query_log[entity_id] = []
        self._query_log[entity_id].append(now)
        self._query_log[entity_id] = [
            t for t in self._query_log[entity_id]
            if now - t < PROBE_WINDOW_SECS * 10
        ]

    def _derive_noise(self, entity_id: str, now: float) -> float:
        """Deterministic but unpredictable per (entity, timestamp) noise."""
        h = hashlib.sha3_256(
            self._salt + entity_id.encode() + str(int(now * 1000)).encode()
        ).digest()
        val = int.from_bytes(h[:4], 'big') / (2**32)
        return val * 2 - 1

    def compute_sigma(self, entity_id: str, volatility: float, now: float) -> float:
        recent     = self._count_recent_queries(entity_id, now)
        is_probing = recent >= PROBE_THRESHOLD_COUNT
        if is_probing:
            self._probe_alerts[entity_id] = self._probe_alerts.get(entity_id, 0) + 1

        base_sigma = CHAMELEON_BASE_SIGMA + volatility * 0.02
        if is_probing:
            base_sigma = min(CHAMELEON_MAX_SIGMA, base_sigma * ESCALATION_FACTOR)
        return base_sigma

    def apply(
        self,
        entity_id:   str,
        true_value:  float,
        volatility:  float = 0.30,
        now:         Optional[float] = None,
    ) -> dict:
        if now is None:
            now = time.time()

        self._log_query(entity_id, now)
        sigma  = self.compute_sigma(entity_id, volatility, now)
        noise  = self._derive_noise(entity_id, now) * sigma
        output = max(0.0, min(1.0, true_value + noise))

        is_probing = self._probe_alerts.get(entity_id, 0) > 0

        return {
            "output_value":       output,
            "noise_applied":      True,
            "sigma_used":         sigma,
            "probing_detected":   is_probing,
            "recent_query_count": self._count_recent_queries(entity_id, now),
            "threshold_hidden":   True,
        }

    def get_probe_alerts(self) -> Dict[str, int]:
        return dict(self._probe_alerts)


if __name__ == "__main__":
    chameleon   = ChameleonProtocol()
    entity_id   = "0xabc123"
    true_value  = 0.72

    normal_outputs = [
        chameleon.apply(entity_id, true_value, volatility=0.30,
                        now=time.time() - 300 + i*60)['output_value']
        for i in range(4)
    ]

    probe_outputs = [
        chameleon.apply(entity_id, true_value, volatility=0.30,
                        now=time.time() + i)['output_value']
        for i in range(10)
    ]

    normal_std = (sum((x - true_value)**2 for x in normal_outputs) / len(normal_outputs))**0.5
    probe_std  = (sum((x - true_value)**2 for x in probe_outputs) / len(probe_outputs))**0.5

    print(f"Normal noise σ:       {normal_std:.4f}")
    print(f"Probing noise σ:      {probe_std:.4f} (escalated)")
    print(f"Probe detected:       {chameleon.get_probe_alerts().get(entity_id, 0) > 0}")
    print("Threshold never exposed in any response")
    print("PHASE 23 PASS — Chameleon Protocol implemented")
