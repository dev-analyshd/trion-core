"""
TRION Protocol — Section 17: Chameleon Protocol
Regulatory adaptation through behavioral form change without architectural change.

The biological basis: A chameleon does not become a different animal under threat.
Its DNA is unchanged. What changes is expression — automatically, continuously,
in direct response to environmental signal. Core preserved. Surface adapts.

Adaptation Sequence (WP2 §17):
  LOW:                increase privacy defaults, ZK credential options surfaced
  MEDIUM:             ZK proofs become default output, Right_to_Invisibility auto-enforced
  HIGH:               validator weight in hostile jurisdiction de-emphasized
  CRITICAL:           signal disaggregation across neutral jurisdictions
  WEAPONIZATION:      AWA_enforced → FALSE → emission FROZEN

Author: TRION Protocol — Originator: Hudu Yusuf (Analys)
License: CC0
"""

import time
import hashlib
import secrets
from dataclasses import dataclass
from enum import Enum
from typing import Dict, List, Optional


class ThreatLevel(Enum):
    LOW = "LOW"
    MEDIUM = "MEDIUM"
    HIGH = "HIGH"
    CRITICAL = "CRITICAL"
    WEAPONIZATION_ATTEMPT = "WEAPONIZATION_ATTEMPT"


class ExpressionMode(Enum):
    STANDARD = "STANDARD"
    PRIVACY_ENHANCED = "PRIVACY_ENHANCED"
    ZK_DEFAULT = "ZK_DEFAULT"
    JURISDICTION_REBALANCED = "JURISDICTION_REBALANCED"
    DISAGGREGATED = "DISAGGREGATED"
    FROZEN = "FROZEN"


@dataclass
class AWAState:
    no_single_entity_controls_signal_weights: bool = True
    no_single_entity_controls_validator_selection: bool = True
    public_good_charter_minimum: float = 0.15
    sovereignty_dignity_protocol_active: bool = True
    right_to_invisibility_enforced: bool = True
    gratitude: float = 1.0

    @property
    def enforced(self) -> bool:
        return all([
            self.no_single_entity_controls_signal_weights,
            self.no_single_entity_controls_validator_selection,
            self.public_good_charter_minimum >= 0.15,
            self.sovereignty_dignity_protocol_active,
            self.right_to_invisibility_enforced,
            self.gratitude >= 1.0,
        ])


@dataclass
class ChameleonExpression:
    mode: ExpressionMode
    threat_level: ThreatLevel
    zk_default: bool
    right_to_invisibility: bool
    jurisdiction_weights: Dict[str, float]
    signal_disaggregation: bool
    emission_frozen: bool
    timestamp: float


CHAMELEON_BASE_SIGMA = 0.015
CHAMELEON_MAX_SIGMA = 0.060
PROBE_WINDOW_SECS = 60.0
PROBE_THRESHOLD_COUNT = 5
ESCALATION_FACTOR = 2.5


class ChameleonProtocol:
    """TRION Chameleon Protocol — Regulatory Adaptation (WP2 §17).

    Core preserved. Surface adapts. Architecture unchanged. Only expression changes.

    Two layers:
    1. Threat-adaptive: 5-level state machine (LOW → MEDIUM → HIGH → CRITICAL → FROZEN)
    2. Anti-probing noise: prevents adversaries from learning exact thresholds
    """

    def __init__(self):
        self._awa = AWAState()
        self._current_threat = ThreatLevel.LOW
        self._expression_mode = ExpressionMode.STANDARD
        self._jurisdiction_weights: Dict[str, float] = {}
        self._frozen = False
        self._query_log: Dict[str, List[float]] = {}
        self._noise_seed = secrets.token_hex(32)

    @property
    def awa(self) -> AWAState:
        return self._awa

    def assess_threat(self, regulatory_signals: dict) -> ThreatLevel:
        """Assess regulatory threat level from REGULATORY_BEHAVIORAL signals."""
        threat_score = 0.0
        if regulatory_signals.get("sba_divergence", 0) > 0.5:
            threat_score += 0.3
        if regulatory_signals.get("capital_entropy_shift", 0) > 0.7:
            threat_score += 0.2
        if regulatory_signals.get("legislative_threat", False):
            threat_score += 0.3
        if regulatory_signals.get("gov_wallet_change", 0) > 0.6:
            threat_score += 0.2
        if regulatory_signals.get("weaponization_detected", False):
            return ThreatLevel.WEAPONIZATION_ATTEMPT
        if threat_score > 0.8:
            return ThreatLevel.CRITICAL
        elif threat_score > 0.6:
            return ThreatLevel.HIGH
        elif threat_score > 0.3:
            return ThreatLevel.MEDIUM
        return ThreatLevel.LOW

    def adapt(self, threat_level: ThreatLevel) -> ChameleonExpression:
        """Adapt expression based on threat level per WP2 §17."""
        self._current_threat = threat_level
        if threat_level == ThreatLevel.WEAPONIZATION_ATTEMPT:
            self._awa.no_single_entity_controls_signal_weights = False
            self._frozen = True
            self._expression_mode = ExpressionMode.FROZEN
            # MD §17 wiring (Wave 3 D): a WEAPONIZATION_ATTEMPT must freeze
            # TRUTH emission globally (T(t) silence) — not only this
            # protocol's own emission_allowed flag. The governance emission
            # gate can be released ONLY by a subsequent passing AWA
            # evaluate() — no single-entity override.
            try:
                from core.governance.awa import trigger_weaponization_freeze
                trigger_weaponization_freeze(
                    "chameleon WEAPONIZATION_ATTEMPT (regulatory_signals "
                    "weaponization_detected)"
                )
            except Exception:
                # Keep the Chameleon self-contained if the governance layer
                # is unavailable (e.g. minimal runtimes); local freeze above
                # still applies.
                pass
        elif threat_level == ThreatLevel.CRITICAL:
            self._expression_mode = ExpressionMode.DISAGGREGATED
            self._frozen = False
        elif threat_level == ThreatLevel.HIGH:
            self._expression_mode = ExpressionMode.JURISDICTION_REBALANCED
            self._frozen = False
        elif threat_level == ThreatLevel.MEDIUM:
            self._expression_mode = ExpressionMode.ZK_DEFAULT
            self._frozen = False
        else:
            self._expression_mode = ExpressionMode.PRIVACY_ENHANCED
            self._frozen = False
        return ChameleonExpression(
            mode=self._expression_mode, threat_level=threat_level,
            zk_default=self._expression_mode in (ExpressionMode.ZK_DEFAULT, ExpressionMode.JURISDICTION_REBALANCED, ExpressionMode.DISAGGREGATED),
            right_to_invisibility=self._awa.right_to_invisibility_enforced,
            jurisdiction_weights=self._jurisdiction_weights.copy(),
            signal_disaggregation=self._expression_mode == ExpressionMode.DISAGGREGATED,
            emission_frozen=self._frozen, timestamp=time.time(),
        )

    @property
    def emission_allowed(self) -> bool:
        return self._awa.enforced and not self._frozen

    def _derive_noise(self, entity_id: str, timestamp: float) -> float:
        payload = f"{entity_id}:{timestamp:.0f}:{self._noise_seed}".encode()
        h = hashlib.sha3_256(payload).digest()
        val = int.from_bytes(h[:8], 'big') / (2**64)
        return (val * 2 - 1)

    def apply_noise(self, entity_id: str, true_value: float, volatility: float, now: Optional[float] = None) -> dict:
        """Apply anti-probing noise to signal output."""
        now = now or time.time()
        if entity_id in self._query_log:
            self._query_log[entity_id] = [t for t in self._query_log[entity_id] if now - t < PROBE_WINDOW_SECS]
        queries = self._query_log.get(entity_id, [])
        probing_detected = len(queries) >= PROBE_THRESHOLD_COUNT
        sigma = CHAMELEON_BASE_SIGMA + volatility * 0.01
        if probing_detected:
            sigma *= ESCALATION_FACTOR
        sigma = min(sigma, CHAMELEON_MAX_SIGMA)
        noise = self._derive_noise(entity_id, now) * sigma
        output_value = true_value + noise
        if entity_id not in self._query_log:
            self._query_log[entity_id] = []
        self._query_log[entity_id].append(now)
        return {"output_value": output_value, "sigma_used": sigma, "probing_detected": probing_detected, "threshold_hidden": True}


if __name__ == "__main__":
    chameleon = ChameleonProtocol()
    expr = chameleon.adapt(ThreatLevel.LOW)
    print(f"LOW → {expr.mode.value}, frozen={expr.emission_frozen}")
    assert chameleon.emission_allowed == True
    expr = chameleon.adapt(ThreatLevel.MEDIUM)
    print(f"MEDIUM → {expr.mode.value}, zk_default={expr.zk_default}")
    expr = chameleon.adapt(ThreatLevel.HIGH)
    print(f"HIGH → {expr.mode.value}")
    expr = chameleon.adapt(ThreatLevel.CRITICAL)
    print(f"CRITICAL → {expr.mode.value}, disaggregated={expr.signal_disaggregation}")
    expr = chameleon.adapt(ThreatLevel.WEAPONIZATION_ATTEMPT)
    print(f"WEAPONIZATION → {expr.mode.value}, frozen={expr.emission_frozen}")
    assert chameleon.emission_allowed == False
    result = chameleon.apply_noise("entity_1", 0.75, 0.3)
    print(f"Noise: output={result['output_value']:.4f}, sigma={result['sigma_used']:.4f}")
    print("CHAMELEON PROTOCOL: PASS")
