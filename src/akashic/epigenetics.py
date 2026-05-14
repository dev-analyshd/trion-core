"""
TRION Epigenetic Behavioral Layer
===================================
Tracks HOW entity behavior changes in response to environmental pressures:
  - Market volatility events
  - Protocol upgrades / forks
  - Regulatory pressure
  - Token price shocks
  - Governance changes
  - Exploit events

Like biological epigenetics: the underlying "DNA" (code) doesn't change,
but expression patterns (behavioral vectors) do — and these changes persist.

Key outputs:
  - Epigenetic drift score: how far current behavior is from baseline
  - Environmental pressure classification
  - Methylation pattern: which behavioral features are suppressed/amplified
  - Heritable signal: will this behavioral change persist?
"""

import time
import math
import json
import os
import sys
from typing import Dict, List, Optional, Tuple
from dataclasses import dataclass, field, asdict
import numpy as np

sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', '..'))

logger = __import__('logging').getLogger(__name__)

EPIGENETIC_STORE_PATH = "/tmp/trion_epigenetic_state.json"


@dataclass
class EpigeneticState:
    entity_id: str
    baseline_phi: List[float]          # original behavioral vector
    current_phi: List[float]           # current behavioral vector
    methylation_mask: List[float]      # 0=suppressed, 1=amplified per feature
    drift_history: List[float]         # drift over time
    environmental_events: List[Dict]   # recorded pressures
    last_updated: int
    heritable_changes: List[Dict]      # persistent behavioral changes
    epigenetic_age: float              # how much the entity has "aged" behaviorally


@dataclass
class EnvironmentalPressure:
    pressure_type: str     # MARKET_CRASH | EXPLOIT | UPGRADE | REGULATORY | FORK | LIQUIDITY_SHOCK
    magnitude: float       # 0-1 intensity
    duration_blocks: int
    timestamp: int
    affected_features: List[int]  # which phi features are affected


class EpigeneticEngine:
    """
    Tracks behavioral evolution of entities under environmental pressure.
    
    Methylation analogy:
      - Features can be "methylated" (suppressed) or "amplified" under pressure
      - Some changes are temporary (stress response)
      - Some changes are heritable (permanent behavioral shift)
    """

    DRIFT_THRESHOLD_SOFT = 0.15   # soft warning
    DRIFT_THRESHOLD_HARD = 0.35   # hard warning — significant shift
    DRIFT_THRESHOLD_CRITICAL = 0.60  # critical — possible exploit or governance change

    PRESSURE_PROFILES = {
        "MARKET_CRASH": {
            "affected_features": [0, 1, 6, 7],  # volume, complexity, length, timestamp
            "methylation_mod": [-0.3, -0.2, 0.0, 0.0, 0.0, 0.0, -0.25, -0.15, 0.0],
            "heritable_probability": 0.20,
        },
        "EXPLOIT": {
            "affected_features": [0, 1, 2, 3, 4, 5, 6, 7, 8],
            "methylation_mod": [0.5, 0.4, 0.3, 0.4, 0.6, 0.8, 0.5, 0.4, 0.5],
            "heritable_probability": 0.90,
        },
        "UPGRADE": {
            "affected_features": [2, 3, 4, 6],
            "methylation_mod": [0.0, 0.0, 0.2, 0.15, 0.3, 0.0, 0.2, 0.0, 0.25],
            "heritable_probability": 0.85,
        },
        "REGULATORY": {
            "affected_features": [0, 1, 7],
            "methylation_mod": [-0.2, -0.15, 0.0, 0.0, 0.0, 0.0, 0.0, -0.1, 0.0],
            "heritable_probability": 0.60,
        },
        "FORK": {
            "affected_features": [0, 2, 6],
            "methylation_mod": [0.3, 0.0, 0.4, 0.0, 0.0, 0.0, 0.35, 0.0, 0.0],
            "heritable_probability": 0.75,
        },
        "LIQUIDITY_SHOCK": {
            "affected_features": [0, 1, 4, 5],
            "methylation_mod": [0.4, 0.3, 0.0, 0.0, 0.5, 0.6, 0.0, 0.0, 0.0],
            "heritable_probability": 0.45,
        },
    }

    def __init__(self):
        self._store: Dict[str, EpigeneticState] = {}
        self._load_store()

    def _load_store(self):
        try:
            if os.path.exists(EPIGENETIC_STORE_PATH):
                with open(EPIGENETIC_STORE_PATH) as f:
                    raw = json.load(f)
                for eid, data in raw.items():
                    self._store[eid] = EpigeneticState(**data)
        except Exception:
            pass

    def _save_store(self):
        try:
            out = {eid: asdict(s) for eid, s in self._store.items()}
            with open(EPIGENETIC_STORE_PATH, "w") as f:
                json.dump(out, f)
        except Exception:
            pass

    def _get_or_create(self, entity_id: str, phi: List[float]) -> EpigeneticState:
        if entity_id not in self._store:
            self._store[entity_id] = EpigeneticState(
                entity_id=entity_id,
                baseline_phi=list(phi),
                current_phi=list(phi),
                methylation_mask=[1.0] * len(phi),
                drift_history=[0.0],
                environmental_events=[],
                last_updated=int(time.time()),
                heritable_changes=[],
                epigenetic_age=0.0,
            )
        return self._store[entity_id]

    def record_observation(self, entity_id: str, phi: List[float]) -> Dict:
        state = self._get_or_create(entity_id, phi)
        baseline = np.array(state.baseline_phi, dtype=np.float32)
        current = np.array(phi, dtype=np.float32)

        drift = float(np.linalg.norm(current - baseline))
        state.current_phi = list(phi)
        state.drift_history.append(round(drift, 4))
        if len(state.drift_history) > 1000:
            state.drift_history = state.drift_history[-1000:]

        # Update methylation mask based on feature-wise change
        for i in range(min(len(phi), len(state.methylation_mask))):
            delta = abs(phi[i] - state.baseline_phi[i])
            if delta > 0.3:
                state.methylation_mask[i] = round(min(2.0, state.methylation_mask[i] + 0.1), 3)
            elif delta < 0.05 and state.methylation_mask[i] > 1.0:
                state.methylation_mask[i] = round(max(1.0, state.methylation_mask[i] - 0.05), 3)

        state.epigenetic_age = round(state.epigenetic_age + drift * 0.01, 4)
        state.last_updated = int(time.time())
        self._save_store()

        if drift >= self.DRIFT_THRESHOLD_CRITICAL:
            drift_label = "CRITICAL"
        elif drift >= self.DRIFT_THRESHOLD_HARD:
            drift_label = "SIGNIFICANT"
        elif drift >= self.DRIFT_THRESHOLD_SOFT:
            drift_label = "MODERATE"
        else:
            drift_label = "STABLE"

        return {
            "entity_id": entity_id,
            "drift": round(drift, 4),
            "drift_label": drift_label,
            "methylation_mask": state.methylation_mask,
            "epigenetic_age": state.epigenetic_age,
            "heritable_changes": len(state.heritable_changes),
        }

    def apply_pressure(self, entity_id: str, phi: List[float],
                       pressure: EnvironmentalPressure) -> Dict:
        state = self._get_or_create(entity_id, phi)
        profile = self.PRESSURE_PROFILES.get(pressure.pressure_type, {})

        mods = profile.get("methylation_mod", [0.0] * len(phi))
        modified_phi = list(phi)
        for i, mod in enumerate(mods):
            if i < len(modified_phi):
                modified_phi[i] = round(max(0.0, min(1.0,
                    modified_phi[i] + mod * pressure.magnitude)), 4)

        heritable_prob = profile.get("heritable_probability", 0.3)
        is_heritable = (pressure.magnitude >= 0.7 and heritable_prob > 0.5)

        if is_heritable:
            state.heritable_changes.append({
                "pressure_type": pressure.pressure_type,
                "magnitude": pressure.magnitude,
                "phi_delta": [round(modified_phi[i] - phi[i], 4) for i in range(len(phi))],
                "timestamp": pressure.timestamp,
                "description": f"{pressure.pressure_type} caused permanent behavioral shift"
            })
            state.baseline_phi = [
                round((state.baseline_phi[i] * 0.9 + modified_phi[i] * 0.1), 4)
                if i < len(modified_phi) else state.baseline_phi[i]
                for i in range(len(state.baseline_phi))
            ]

        state.environmental_events.append({
            "type": pressure.pressure_type,
            "magnitude": round(pressure.magnitude, 3),
            "timestamp": pressure.timestamp,
            "heritable": is_heritable,
        })
        if len(state.environmental_events) > 200:
            state.environmental_events = state.environmental_events[-200:]

        state.current_phi = modified_phi
        state.last_updated = int(time.time())
        self._save_store()

        return {
            "entity_id": entity_id,
            "pressure_type": pressure.pressure_type,
            "magnitude": pressure.magnitude,
            "modified_phi": modified_phi,
            "is_heritable": is_heritable,
            "total_heritable_changes": len(state.heritable_changes),
            "description": (
                f"{'Permanent' if is_heritable else 'Temporary'} behavioral shift "
                f"from {pressure.pressure_type} (magnitude={pressure.magnitude:.2f})"
            ),
        }

    def get_epigenetic_report(self, entity_id: str) -> Dict:
        if entity_id not in self._store:
            return {"entity_id": entity_id, "status": "no_data"}
        state = self._store[entity_id]
        drift_history = state.drift_history
        recent_drift = drift_history[-1] if drift_history else 0.0
        max_drift = max(drift_history) if drift_history else 0.0
        avg_drift = sum(drift_history) / max(len(drift_history), 1)
        return {
            "entity_id": entity_id,
            "epigenetic_age": state.epigenetic_age,
            "recent_drift": round(recent_drift, 4),
            "max_drift_observed": round(max_drift, 4),
            "avg_drift": round(avg_drift, 4),
            "drift_trend": "increasing" if len(drift_history) > 2 and drift_history[-1] > drift_history[-2] else "stable",
            "heritable_changes": len(state.heritable_changes),
            "environmental_events": len(state.environmental_events),
            "methylation_pattern": {
                f"feature_{i}": round(v, 3)
                for i, v in enumerate(state.methylation_mask)
            },
            "baseline_stability": round(1.0 - avg_drift, 4),
            "last_updated": state.last_updated,
        }


_engine_instance: Optional[EpigeneticEngine] = None


def get_epigenetic_engine() -> EpigeneticEngine:
    global _engine_instance
    if _engine_instance is None:
        _engine_instance = EpigeneticEngine()
    return _engine_instance
