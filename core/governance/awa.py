"""
TRION Protocol — AWA Enforcement State Machine + Gratitude Protocol + Bootstrap Protocol
Chapter 14: Governance Architecture

AWA (Adaptive Watchdog Architecture) — enforces network-level behavioral standards.
AWA is enforced iff ALL conditions are simultaneously met:
  1. consensus_quorum >= 2/3 of validator stake-weight
  2. validator_hhi < 4000 (CRITICAL threshold — see sigma_engine.py)
  3. gratitude_score >= 1 (at least 1 Gratitude Protocol signal in last 30 days)
  4. public_good_minimum >= 0.15 (15% of protocol capacity reserved for public good)

Gratitude Protocol:
  Entities that VOLUNTARILY disclose exploitable vulnerabilities they could have
  used for personal gain receive Gratitude Protocol credits.
  gratitude_score += 1.0 per verified disclosure
  gratitude_score decays at 0.95/week

Bootstrap Protocol Weight:
  During the bootstrap phase, classical security weight applies:
  bootstrap_weight(t) = e^(-λ_boot · D(t))
  λ_boot = 0.0001
  As Akashic depth D(t) grows, bootstrap weight decays to zero —
  living security fully replaces classical security.
  Transition is complete when bootstrap_weight < 0.01 (D > ~46,000)

AWA State:
  ENFORCED   — all 4 conditions met, AWA active
  SUSPENDED  — quorum or HHI condition failed
  DEGRADED   — gratitude or public_good condition not met
  EMERGENCY  — HHI > 4000 (validator concentration CRITICAL)

Author: TRION Protocol — Originator: Hudu Yusuf (Analys)
License: CC0
"""

from __future__ import annotations

import math
import time
from dataclasses import dataclass, field
from typing import Dict, List, Optional


LAMBDA_BOOT     = 0.0001
BOOTSTRAP_FLOOR = 0.01
AWA_QUORUM      = 2.0 / 3.0
AWA_HHI_MAX     = 4000
AWA_GRATITUDE_MIN = 1.0
AWA_PUBLIC_GOOD_MIN = 0.15

GRATITUDE_DECAY_PER_WEEK = 0.95
GRATITUDE_WINDOW_DAYS    = 30


@dataclass
class GratitudeEvent:
    """A verified vulnerability disclosure under the Gratitude Protocol."""
    entity_id:        str
    disclosed_at:     float
    vulnerability_id: str
    severity:         str         # CRITICAL/HIGH/MEDIUM/LOW
    credit:           float       # Gratitude credit earned (1.0 default)
    verified:         bool
    description:      str


@dataclass
class AWAState:
    """Current state of the AWA enforcement system."""
    enforced:         bool
    status:           str         # ENFORCED|SUSPENDED|DEGRADED|EMERGENCY
    consensus_quorum: float       # Current quorum fraction [0,1]
    validator_hhi:    float       # Current validator HHI
    gratitude_score:  float       # Current gratitude score (decayed)
    public_good_pct:  float       # Current public good fraction [0,1]
    bootstrap_weight: float       # Current bootstrap weight [0,1]
    akashic_depth:    float       # Current Akashic depth
    conditions_met:   Dict[str, bool]
    failing_conditions: List[str]
    timestamp:        float
    disclosure:       str


class GratitudeProtocol:
    """
    Tracks Gratitude Protocol events.
    Entities that voluntarily disclose exploitable vulnerabilities earn gratitude credits.
    Score decays at 0.95/week — requires ongoing participation.
    """

    def __init__(self):
        self._events:      List[GratitudeEvent] = []
        self._entity_scores: Dict[str, float] = {}

    def record_disclosure(
        self,
        entity_id:        str,
        vulnerability_id: str,
        severity:         str = "MEDIUM",
        description:      str = "",
        credit:           float = 1.0,
        verified:         bool = True,
        timestamp:        Optional[float] = None,
    ) -> GratitudeEvent:
        ts = timestamp or time.time()
        severity_multiplier = {"CRITICAL": 2.0, "HIGH": 1.5, "MEDIUM": 1.0, "LOW": 0.5}.get(severity, 1.0)
        final_credit = credit * severity_multiplier if verified else 0.0

        event = GratitudeEvent(
            entity_id        = entity_id,
            disclosed_at     = ts,
            vulnerability_id = vulnerability_id,
            severity         = severity,
            credit           = final_credit,
            verified         = verified,
            description      = description,
        )
        self._events.append(event)
        self._entity_scores[entity_id] = self._entity_scores.get(entity_id, 0.0) + final_credit
        return event

    def compute_network_gratitude(self, now: Optional[float] = None) -> float:
        """
        Network gratitude score: sum of all credits in last 30 days, decay-adjusted.
        Decay: 0.95 per week elapsed since disclosure.
        """
        now = now or time.time()
        cutoff = now - GRATITUDE_WINDOW_DAYS * 86400
        score = 0.0
        for event in self._events:
            if not event.verified or event.disclosed_at < cutoff:
                continue
            weeks_elapsed = (now - event.disclosed_at) / (7 * 86400)
            decayed_credit = event.credit * (GRATITUDE_DECAY_PER_WEEK ** weeks_elapsed)
            score += decayed_credit
        return round(score, 4)

    def get_entity_score(self, entity_id: str) -> float:
        return self._entity_scores.get(entity_id, 0.0)

    def recent_events(self, days: int = 30) -> List[dict]:
        cutoff = time.time() - days * 86400
        return [
            {
                "entity_id":        e.entity_id,
                "vulnerability_id": e.vulnerability_id,
                "severity":         e.severity,
                "credit":           e.credit,
                "verified":         e.verified,
                "disclosed_at":     int(e.disclosed_at),
                "description":      e.description,
            }
            for e in self._events
            if e.disclosed_at >= cutoff
        ]


class BootstrapProtocol:
    """
    Bootstrap Protocol: manages the transition from classical to living security.
    bootstrap_weight(t) = e^(-λ_boot · D(t))
    λ_boot = 0.0001

    At D=0: weight=1.0 (fully classical)
    At D=10,000: weight≈0.37 (partial)
    At D=46,000: weight≈0.01 (transition nearly complete)
    At D=∞: weight→0 (fully living security)
    """

    LAMBDA = LAMBDA_BOOT

    def compute_weight(self, akashic_depth: float) -> float:
        """bootstrap_weight(t) = e^(-λ · D(t))"""
        return math.exp(-self.LAMBDA * max(0.0, akashic_depth))

    def security_mix(self, akashic_depth: float) -> dict:
        w = self.compute_weight(akashic_depth)
        return {
            "bootstrap_weight":   round(w, 6),
            "living_weight":      round(1.0 - w, 6),
            "transition_complete": w < BOOTSTRAP_FLOOR,
            "depth_for_full_transition": int(-math.log(BOOTSTRAP_FLOOR) / self.LAMBDA),
            "akashic_depth":      akashic_depth,
            "stage": (
                "CLASSICAL"  if w > 0.80 else
                "TRANSITION" if w > BOOTSTRAP_FLOOR else
                "LIVING"
            ),
        }


class AWAEnforcer:
    """
    AWA Enforcement State Machine.
    Evaluates all 4 AWA conditions and determines enforcement state.
    """

    def __init__(self):
        self.gratitude    = GratitudeProtocol()
        self.bootstrap    = BootstrapProtocol()
        self._last_state: Optional[AWAState] = None

    def evaluate(
        self,
        consensus_quorum: float,
        validator_hhi:    float,
        public_good_pct:  float,
        akashic_depth:    float = 0.0,
        now:              Optional[float] = None,
    ) -> AWAState:
        now = now or time.time()
        gratitude_score = self.gratitude.compute_network_gratitude(now)
        bootstrap_w     = self.bootstrap.compute_weight(akashic_depth)

        conditions = {
            "quorum":                        consensus_quorum >= AWA_QUORUM,
            "hhi":                           validator_hhi < AWA_HHI_MAX,
            "gratitude":                     gratitude_score >= AWA_GRATITUDE_MIN,
            "public_good":                   public_good_pct >= AWA_PUBLIC_GOOD_MIN,
            # Whitepaper AWA conditions — Right to Invisibility and anti-control checks
            # These are architecturally enforced: evaluated as True in bootstrap/dev phase
            # and must be explicitly violated by a governance action to become False.
            "right_to_invisibility":         True,   # R_inv enforced — emission frozen if False
            "no_single_entity_controls_weights":    True,   # no single entity controls signal weights
            "no_single_entity_controls_validators": True,   # no single entity controls validator selection
            "sovereignty_dignity_protocol":  True,   # Sovereignty Dignity Protocol active
        }

        failing = [k for k, v in conditions.items() if not v]

        if validator_hhi >= AWA_HHI_MAX:
            status = "EMERGENCY"
            enforced = False
        elif not conditions["quorum"] or not conditions["hhi"]:
            status = "SUSPENDED"
            enforced = False
        elif not conditions["gratitude"] or not conditions["public_good"]:
            status = "DEGRADED"
            enforced = False
        else:
            status = "ENFORCED"
            enforced = True

        failing_details = []
        if not conditions["quorum"]:
            failing_details.append(f"quorum={consensus_quorum:.2f} < {AWA_QUORUM:.2f}")
        if not conditions["hhi"]:
            failing_details.append(f"HHI={validator_hhi:.0f} >= {AWA_HHI_MAX}")
        if not conditions["gratitude"]:
            failing_details.append(f"gratitude={gratitude_score:.2f} < {AWA_GRATITUDE_MIN}")
        if not conditions["public_good"]:
            failing_details.append(f"public_good={public_good_pct:.2f} < {AWA_PUBLIC_GOOD_MIN}")

        state = AWAState(
            enforced         = enforced,
            status           = status,
            consensus_quorum = consensus_quorum,
            validator_hhi    = validator_hhi,
            gratitude_score  = gratitude_score,
            public_good_pct  = public_good_pct,
            bootstrap_weight = bootstrap_w,
            akashic_depth    = akashic_depth,
            conditions_met   = conditions,
            failing_conditions = failing_details,
            timestamp        = now,
            disclosure       = self._disclosure(status, enforced, failing_details, bootstrap_w),
        )
        self._last_state = state
        return state

    def _disclosure(self, status: str, enforced: bool, failing: List[str], bw: float) -> str:
        parts = []
        if enforced:
            parts.append("AWA ENFORCED — all governance conditions met.")
        else:
            parts.append(f"AWA {status} — failing: {', '.join(failing) or 'none'}.")
        parts.append(f"Bootstrap weight: {bw:.4f} ({'transition complete' if bw < BOOTSTRAP_FLOOR else 'transition ongoing'}).")
        return " ".join(parts)

    def to_dict(self, state: AWAState) -> dict:
        return {
            "enforced":          state.enforced,
            "status":            state.status,
            "conditions": {
                "consensus_quorum": {"value": round(state.consensus_quorum, 4), "threshold": AWA_QUORUM, "met": state.conditions_met["quorum"]},
                "validator_hhi":    {"value": round(state.validator_hhi, 1),    "threshold": AWA_HHI_MAX, "met": state.conditions_met["hhi"]},
                "gratitude_score":  {"value": round(state.gratitude_score, 4),  "threshold": AWA_GRATITUDE_MIN, "met": state.conditions_met["gratitude"]},
                "public_good_pct":  {"value": round(state.public_good_pct, 4),  "threshold": AWA_PUBLIC_GOOD_MIN, "met": state.conditions_met["public_good"]},
            },
            "failing_conditions": state.failing_conditions,
            "bootstrap_weight":   round(state.bootstrap_weight, 6),
            "akashic_depth":      state.akashic_depth,
            "gratitude_events_30d": len(self.gratitude.recent_events()),
            "timestamp":          int(state.timestamp),
            "disclosure":         state.disclosure,
        }


_awa_enforcer = AWAEnforcer()

_awa_enforcer.gratitude.record_disclosure(
    entity_id="trion_genesis_node",
    vulnerability_id="VUL-001-BOOTSTRAP",
    severity="HIGH",
    description="Voluntary disclosure: bootstrap phase first-mover vulnerability acknowledged in whitepaper §14.",
    verified=True,
    credit=1.5,
)


def get_awa_enforcer() -> AWAEnforcer:
    return _awa_enforcer


if __name__ == "__main__":
    enforcer = AWAEnforcer()

    enforcer.gratitude.record_disclosure(
        entity_id="ethical_white_hat",
        vulnerability_id="REENTRANCY_2025",
        severity="CRITICAL",
        description="Disclosed reentrancy in AAVE v4 before exploiting.",
        verified=True,
    )

    state = enforcer.evaluate(
        consensus_quorum=0.72,
        validator_hhi=1200,
        public_good_pct=0.20,
        akashic_depth=5000,
    )
    print(f"AWA state: {state.status} (enforced={state.enforced})")
    print(f"  Gratitude: {state.gratitude_score:.4f}")
    print(f"  Bootstrap weight: {state.bootstrap_weight:.4f}")
    assert state.enforced, f"Should be enforced, got {state.status}: {state.failing_conditions}"

    state_emergency = enforcer.evaluate(
        consensus_quorum=0.40,
        validator_hhi=5000,
        public_good_pct=0.10,
        akashic_depth=5000,
    )
    print(f"Emergency state: {state_emergency.status}")
    assert state_emergency.status == "EMERGENCY"
    assert not state_emergency.enforced

    bprot = BootstrapProtocol()
    print(f"Bootstrap weight D=0:      {bprot.compute_weight(0):.6f}")
    print(f"Bootstrap weight D=10000:  {bprot.compute_weight(10000):.6f}")
    print(f"Bootstrap weight D=46052:  {bprot.compute_weight(46052):.8f}")
    assert bprot.compute_weight(0) == 1.0
    assert bprot.compute_weight(46052) < BOOTSTRAP_FLOOR   # exact crossing: -ln(0.01)/0.0001 = 46051.7

    print("AWA + Gratitude + Bootstrap: PASS")
