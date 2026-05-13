"""
Source Credibility (CRED) — TRION L3
CRED(s, t) = Accuracy(s, t-90d) · Timeliness(s) · Independence(s)
cross_source_agreement = credibility-weighted standard deviation
"""
import math
from dataclasses import dataclass, field
from typing import Dict, List, Optional
from collections import deque


CRED_DECAY_LAMBDA    = 0.01   # per-day decay
INDEPENDENCE_PENALTY = 0.20   # if source is financially incentivized


@dataclass
class CredibilityEvent:
    source_id:  str
    predicted:  float
    actual:     float
    timestamp:  float    # unix seconds
    timeliness: float    # 0-1: 1 = on-time, 0 = late


class CredibilityRegistry:
    """Tracks per-source accuracy and computes cross-source agreement."""

    def __init__(self):
        self._scores: Dict[str, float] = {}
        self._history: Dict[str, deque] = {}

    def register(self, source_id: str, initial_cred: float = 0.70):
        self._scores[source_id]  = initial_cred
        self._history[source_id] = deque(maxlen=90)

    def update(self, event: CredibilityEvent):
        if event.source_id not in self._scores:
            self.register(event.source_id)

        error = abs(event.predicted - event.actual)
        accuracy = max(0.0, 1.0 - error)
        self._history[event.source_id].append((accuracy, event.timeliness))

        if len(self._history[event.source_id]) >= 5:
            accs    = [a for a, _ in self._history[event.source_id]]
            times   = [t for _, t in self._history[event.source_id]]
            avg_acc = sum(accs)  / len(accs)
            avg_tim = sum(times) / len(times)
            self._scores[event.source_id] = round(avg_acc * avg_tim, 6)

    def get_cred(self, source_id: str) -> float:
        return self._scores.get(source_id, 0.50)

    def cross_source_agreement(self, source_values: Dict[str, float]) -> float:
        """
        CA = 1 - (credibility-weighted std dev / max possible std dev)
        High agreement (low std) → high CA.
        """
        if len(source_values) < 2:
            return 1.0

        weighted_vals  = []
        weighted_creds = []

        for src, val in source_values.items():
            cred = self.get_cred(src)
            weighted_vals.append(val * cred)
            weighted_creds.append(cred)

        total_cred = sum(weighted_creds)
        if total_cred == 0:
            return 0.0

        w_mean = sum(weighted_vals) / total_cred
        w_var  = sum(
            c * (v - w_mean)**2
            for c, v in zip(weighted_creds, source_values.values())
        ) / total_cred

        w_std = math.sqrt(w_var)
        max_std = 0.5  # maximum possible std for [0,1] values

        return round(max(0.0, 1.0 - w_std / max_std), 6)
