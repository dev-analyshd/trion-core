"""
TRION Entity Lifecycle Engine
================================
Models the full life/death cycle of on-chain entities:
  BIRTH → GROWTH → MATURITY → DECLINE → DEATH → (RESURRECTION?)

Inspired by biological life cycles: entropy accumulation, metabolic rate,
dormancy, and resurrection potential.

Key outputs:
  - Lifecycle stage (with confidence)
  - Vitality score (0=dead, 1=thriving)
  - Time-to-next-stage estimate
  - Resurrection potential (for dormant/dead entities)
  - Mortality risk curve
"""

import time
import math
import json
import os
from typing import Dict, List, Optional, Tuple
from dataclasses import dataclass, field, asdict
import numpy as np

LIFECYCLE_STORE_PATH = "/tmp/trion_lifecycle_state.json"


@dataclass
class LifecycleState:
    entity_id: str
    stage: str                     # BIRTH | GROWTH | MATURITY | DECLINE | DEATH
    vitality: float                # 0=dead, 1=thriving
    age_days: float                # estimated entity age in days
    stage_duration_days: float     # time in current stage
    last_activity: int             # last activity timestamp
    activity_history: List[float]  # recent activity counts (normalized)
    entropy_trend: List[float]     # entropy trajectory
    metabolic_rate: float          # how fast entity consumes "energy" (fees)
    resurrection_potential: float  # 0-1 probability of comeback
    mortality_risk: float          # probability of death in next 30 days
    stage_confidence: float        # confidence in current stage classification


LIFECYCLE_TRANSITIONS = {
    "BIRTH": {
        "to_GROWTH": {"min_activity": 0.3, "min_age_days": 1, "min_tx_count": 100},
        "to_DEATH": {"max_activity": 0.05, "min_age_days": 7},
    },
    "GROWTH": {
        "to_MATURITY": {"min_age_days": 90, "min_activity": 0.5, "entropy_stable": True},
        "to_DECLINE": {"max_activity_trend": -0.2},
        "to_DEATH": {"max_activity": 0.02},
    },
    "MATURITY": {
        "to_DECLINE": {"activity_trend": "decreasing", "entropy_increasing": True},
        "to_GROWTH": {"activity_spike": True},  # unlikely, rare
    },
    "DECLINE": {
        "to_DEATH": {"max_activity": 0.01, "entropy_high": True},
        "to_MATURITY": {"recovery_detected": True},
    },
    "DEATH": {
        "to_BIRTH": {"resurrection_signal": True},  # rare
    },
}


class EntityLifecycleEngine:

    VITALITY_DECAY_RATE = 0.02      # daily decay without activity
    RESURRECTION_THRESHOLD = 0.15   # min vitality for resurrection

    def __init__(self):
        self._store: Dict[str, LifecycleState] = {}
        self._load_store()

    def _load_store(self):
        try:
            if os.path.exists(LIFECYCLE_STORE_PATH):
                with open(LIFECYCLE_STORE_PATH) as f:
                    raw = json.load(f)
                for eid, data in raw.items():
                    self._store[eid] = LifecycleState(**data)
        except Exception:
            pass

    def _save_store(self):
        try:
            out = {eid: asdict(s) for eid, s in self._store.items()}
            with open(LIFECYCLE_STORE_PATH, "w") as f:
                json.dump(out, f)
        except Exception:
            pass

    def _classify_stage(self, activity_history: List[float],
                         age_days: float, entropy_trend: List[float],
                         vitality: float) -> Tuple[str, float]:
        if not activity_history:
            return "BIRTH", 0.6

        recent_activity = sum(activity_history[-5:]) / max(len(activity_history[-5:]), 1)
        avg_activity = sum(activity_history) / max(len(activity_history), 1)

        # Trend direction
        if len(activity_history) >= 3:
            trend = activity_history[-1] - activity_history[0]
        else:
            trend = 0.0

        # Entropy trend
        if len(entropy_trend) >= 2:
            entropy_delta = entropy_trend[-1] - entropy_trend[0]
        else:
            entropy_delta = 0.0

        # Classification logic
        if vitality < 0.05:
            return "DEATH", 0.95

        if recent_activity < 0.02 and age_days > 30:
            if vitality < 0.15:
                return "DEATH", 0.85
            return "DECLINE", 0.80

        if age_days < 7 and avg_activity < 0.3:
            return "BIRTH", 0.75

        if trend > 0.1 and recent_activity > 0.3:
            if age_days < 90:
                return "GROWTH", 0.80
            return "MATURITY", 0.70

        if trend < -0.15 or entropy_delta > 0.2:
            return "DECLINE", 0.75

        if avg_activity > 0.5 and abs(trend) < 0.1:
            return "MATURITY", 0.82

        if avg_activity > 0.2 and trend > 0:
            return "GROWTH", 0.70

        return "MATURITY", 0.60

    def _compute_vitality(self, activity_history: List[float],
                          last_activity: int) -> float:
        if not activity_history:
            return 0.5
        # Recency decay
        seconds_since = int(time.time()) - last_activity
        days_since = seconds_since / 86400.0
        recency_decay = math.exp(-self.VITALITY_DECAY_RATE * days_since)

        recent = sum(activity_history[-10:]) / max(len(activity_history[-10:]), 1)
        vitality = recent * recency_decay
        return round(min(1.0, max(0.0, vitality)), 4)

    def _compute_resurrection_potential(self, state: LifecycleState) -> float:
        if state.stage not in ("DECLINE", "DEATH"):
            return 0.0

        # Factors that enable resurrection
        factors = []

        # Historical vitality (was it ever healthy?)
        if state.activity_history:
            peak = max(state.activity_history)
            factors.append(peak * 0.4)

        # Age (older protocols may have brand/community value)
        age_factor = min(1.0, state.age_days / 365.0) * 0.2
        factors.append(age_factor)

        # Recent small signals
        recent = sum(state.activity_history[-3:]) / max(len(state.activity_history[-3:]), 1)
        factors.append(recent * 0.4)

        potential = sum(factors) / max(len(factors), 1)

        # Death has lower potential than decline
        if state.stage == "DEATH":
            potential *= 0.3

        return round(min(1.0, potential), 4)

    def _compute_mortality_risk(self, state: LifecycleState) -> float:
        if state.stage == "DEATH":
            return 1.0
        if state.stage in ("BIRTH", "GROWTH"):
            base = 0.05
        elif state.stage == "MATURITY":
            base = 0.08
        else:
            base = 0.45

        # Low vitality increases mortality
        vitality_mod = (1.0 - state.vitality) * 0.4

        # Entropy increase increases mortality
        if len(state.entropy_trend) >= 2:
            entropy_mod = max(0, state.entropy_trend[-1] - state.entropy_trend[-2]) * 0.3
        else:
            entropy_mod = 0.0

        return round(min(1.0, base + vitality_mod + entropy_mod), 4)

    def update(self, entity_id: str, tx_count: int, entropy: float,
               fee_usd: float = 0.0) -> Dict:
        now = int(time.time())

        if entity_id not in self._store:
            self._store[entity_id] = LifecycleState(
                entity_id=entity_id,
                stage="BIRTH",
                vitality=0.5,
                age_days=0.0,
                stage_duration_days=0.0,
                last_activity=now,
                activity_history=[],
                entropy_trend=[entropy],
                metabolic_rate=0.0,
                resurrection_potential=0.0,
                mortality_risk=0.1,
                stage_confidence=0.7,
            )

        state = self._store[entity_id]
        seconds_elapsed = now - state.last_activity
        days_elapsed = seconds_elapsed / 86400.0
        state.age_days = round(state.age_days + days_elapsed, 2)
        state.stage_duration_days = round(state.stage_duration_days + days_elapsed, 2)

        # Update activity history
        activity_norm = min(1.0, math.log1p(tx_count) / math.log1p(10000))
        state.activity_history.append(round(activity_norm, 4))
        if len(state.activity_history) > 500:
            state.activity_history = state.activity_history[-500:]

        # Update entropy trend
        state.entropy_trend.append(round(entropy, 4))
        if len(state.entropy_trend) > 200:
            state.entropy_trend = state.entropy_trend[-200:]

        # Metabolic rate
        state.metabolic_rate = round(min(1.0, fee_usd / 10000.0), 4)

        # Vitality
        state.vitality = self._compute_vitality(state.activity_history, now)

        # Lifecycle stage
        old_stage = state.stage
        new_stage, confidence = self._classify_stage(
            state.activity_history, state.age_days,
            state.entropy_trend, state.vitality
        )
        if new_stage != old_stage:
            state.stage_duration_days = 0.0
        state.stage = new_stage
        state.stage_confidence = round(confidence, 4)

        # Resurrection potential
        state.resurrection_potential = self._compute_resurrection_potential(state)

        # Mortality risk
        state.mortality_risk = self._compute_mortality_risk(state)

        state.last_activity = now
        self._save_store()

        return {
            "entity_id": entity_id,
            "stage": state.stage,
            "vitality": state.vitality,
            "age_days": state.age_days,
            "stage_duration_days": state.stage_duration_days,
            "stage_confidence": state.stage_confidence,
            "resurrection_potential": state.resurrection_potential,
            "mortality_risk": state.mortality_risk,
            "metabolic_rate": state.metabolic_rate,
            "transition": f"{old_stage} → {new_stage}" if old_stage != new_stage else None,
            "description": (
                f"Entity in {state.stage} stage. "
                f"Vitality: {state.vitality:.3f}. "
                f"Age: {state.age_days:.1f} days. "
                f"{'RESURRECTION POSSIBLE.' if state.resurrection_potential > 0.3 else ''}"
                f"{'HIGH MORTALITY RISK.' if state.mortality_risk > 0.6 else ''}"
            )
        }

    def get_lifecycle_state(self, entity_id: str) -> Optional[Dict]:
        if entity_id not in self._store:
            return None
        return asdict(self._store[entity_id])


_lifecycle_engine: Optional[EntityLifecycleEngine] = None


def get_lifecycle_engine() -> EntityLifecycleEngine:
    global _lifecycle_engine
    if _lifecycle_engine is None:
        _lifecycle_engine = EntityLifecycleEngine()
    return _lifecycle_engine
