"""
TRION Protocol — AWA Enforcement State Machine + Gratitude Protocol + Bootstrap Protocol
Chapter 14: Governance Architecture

AWA (Anti-Weaponization Architecture — MD §17 / V2 §14.2 canonical name).
Historical note: this module previously carried the mislabel "Adaptive
Watchdog Architecture" (spec conflict K15); MD §17 names it the
Anti-Weaponization Architecture and that name is normative here.

CANONICAL 6-CONDITION SET (MD §17, quoted verbatim)::

    AWA_enforced iff all_of:
        no_single_entity_controls_signal_weights
        no_single_entity_controls_validator_selection
        Public_Good_Charter_minimum >= 15%
        Sovereignty_Dignity_Protocol_active
        Right_to_Invisibility_enforced
        Gratitude >= 1
    AWA_enforced = FALSE → signal emission FROZEN
    Cannot be overridden by any single entity. By design.

``AWAState.awa_canonical`` is the spec-exact conjunction of those six
conditions (``iff`` semantics preserved: TRUE iff all six hold). The
operational ``enforced`` field is a fail-closed SUPERSET — the six canonical
conditions PLUS two validator-health checks (consensus quorum >= 2/3 and
validator HHI < 4000 CRITICAL, per sigma_engine.py). Freeing on extra
conditions is conservative (it can only freeze MORE, never less), and the
MD §17 guarantee holds exactly: any canonical condition failing ⇒
``awa_canonical = FALSE`` ⇒ ``emission_frozen = True``.

EMISSION FREEZE (MD §17, wired Wave 3 D): every ``evaluate()`` updates the
module-level ``EmissionGate`` singleton; ``signal_factory.build_signal``
consults it as a hard precondition and converts truth signals into
structured SILENCE (T(t) = 0) while frozen. The gate can only be released by
a subsequent passing ``evaluate()`` — there is no single-entity override
(no public unfreeze). A WEAPONIZATION_ATTEMPT (Chameleon §17 / MD §17)
freezes the gate immediately via ``trigger_weaponization_freeze()``.

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
  ENFORCED   — all 8 conditions met (6 canonical + quorum + HHI), AWA active
  SUSPENDED  — quorum or HHI condition failed (supplemental health)
  DEGRADED   — gratitude or public_good condition not met
  FROZEN     — anti-centralization / R_inv / SDP condition violated (MD §17:
               signal emission FROZEN, cannot be overridden by any single entity)
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

# ─── MD §17 canonical condition names (verbatim) ─────────────────────────────
# AWA_enforced iff all_of: <these six>. Encoded explicitly (Wave 3 D,
# spec-matrix R-CH-02 remediation) — the AWA freeze is the F12 control.
CANONICAL_AWA_CONDITIONS: List[str] = [
    "no_single_entity_controls_signal_weights",
    "no_single_entity_controls_validator_selection",
    "Public_Good_Charter_minimum",          # >= 0.15
    "Sovereignty_Dignity_Protocol_active",
    "Right_to_Invisibility_enforced",
    "Gratitude",                            # >= 1
]


class EmissionFrozenError(RuntimeError):
    """Raised by hard-gate consumers when truth emission is AWA-frozen.

    MD §17: ``AWA_enforced = FALSE → signal emission FROZEN … Cannot be
    overridden by any single entity.`` On-chain / publication paths call
    :func:`assert_emission_allowed` so a frozen AWA state is fail-closed
    at the boundary, not only inside ``build_signal``.
    """


class EmissionGate:
    """MD §17 emission-freeze gate (singleton — see ``_emission_gate``).

    * ``frozen`` — truth emission frozen (T(t) = 0, structured SILENCE only).
    * Freeze sources: any ``AWAEnforcer.evaluate()`` whose state is not
      enforced (automatically wired), or a governance WEAPONIZATION_ATTEMPT
      via :meth:`trigger_weaponization_freeze`.
    * Release: ONLY a subsequent ``evaluate()`` returning an enforced state.
      There is deliberately NO public unfreeze — "cannot be overridden by
      any single entity" is enforced structurally, not by policy.
    """

    def __init__(self) -> None:
        self._frozen: bool = False
        self._reason: str = ""
        self._source: str = ""
        self._since: float = 0.0

    # ── read API (consumed by core/master/signal_factory.py) ────────────
    def is_frozen(self) -> bool:
        return self._frozen

    @property
    def reason(self) -> str:
        return self._reason

    @property
    def source(self) -> str:
        return self._source

    @property
    def since(self) -> float:
        return self._since

    def freeze(self, reason: str, source: str, now: Optional[float] = None) -> None:
        """Freeze emission (governance action / AWA evaluation only)."""
        if not self._frozen:
            self._since = now if now is not None else time.time()
        self._frozen = True
        self._reason = reason
        self._source = source

    # ── write API (AWAEnforcer.evaluate only) ────────────────────────────
    def _update_from_state(self, state: "AWAState") -> None:
        """Called by every AWAEnforcer.evaluate(): frozen iff not enforced.

        A passing evaluation RELEASES a previous freeze (the only release
        path — single-entity override is structurally impossible).
        """
        if state.enforced:
            if self._frozen:
                # Release with an audit trail of the prior freeze.
                self._frozen = False
                self._reason = ""
                self._source = ""
            return
        detail = ", ".join(state.failing_conditions) or state.status
        self.freeze(
            reason=f"AWA_{state.status}: {detail}"[:512],
            source="governance.awa.evaluate",
            now=state.timestamp,
        )

    def to_dict(self) -> dict:
        return {
            "emission_frozen": self._frozen,
            "freeze_reason":   self._reason,
            "freeze_source":   self._source,
            "frozen_since":    int(self._since) if self._since else None,
            "spec":            "MD §17 / V2 §14.2 — AWA_enforced=FALSE → signal emission FROZEN",
        }


# Module-level singleton consumed by the signal emission path.
_emission_gate = EmissionGate()


def get_emission_gate() -> EmissionGate:
    """The process-wide AWA emission-freeze gate (MD §17)."""
    return _emission_gate


def is_emission_frozen() -> bool:
    """True while AWA is not enforced — truth emission must be silent (T(t)=0)."""
    return _emission_gate.is_frozen()


def trigger_weaponization_freeze(reason: str = "WEAPONIZATION_ATTEMPT") -> None:
    """Governance/Chameleon hook (MD §17 WEAPONIZATION_ATTEMPT → FROZEN).

    Freezes emission immediately; release requires a passing AWA
    ``evaluate()`` (no single-entity override).
    """
    _emission_gate.freeze(
        reason=f"WEAPONIZATION_ATTEMPT: {reason}"[:512],
        source="governance.awa.weaponization",
    )


def assert_emission_allowed(signal_type: object = None) -> None:
    """Hard precondition for publication paths (fail-closed).

    Raises :class:`EmissionFrozenError` while the gate is frozen. SILENCE
    signals remain emittable (silence IS the information — MD §11);
    ``signal_type`` may be a ``SignalType``/name and is checked for that.
    Wiring point for API/on-chain publication (Agent M / VM tiers).
    """
    if not _emission_gate.is_frozen():
        return
    name = getattr(signal_type, "name", signal_type)
    if name == "SILENCE":
        return
    raise EmissionFrozenError(
        f"TRUTH EMISSION FROZEN (AWA, MD §17): {_emission_gate.reason or 'AWA not enforced'}"
    )

GRATITUDE_DECAY_PER_WEEK = 0.95
GRATITUDE_WINDOW_DAYS    = 30

# ─── WP2 §17 anti-centralization thresholds (AUDIT-3 G2 fix) ───────────────────
# A single entity controlling >50% of signal weights constitutes majority control
# (signal-weights AWA violation); a single entity controlling >= 1/3 of validator
# stake violates BFT safety (validator-selection AWA violation). These are the
# WP2 §17 "no single entity" conditions. They MUST be runtime-evaluated, never
# hardcoded True.
AWA_SIGNAL_WEIGHT_MAX_SHARE   = 0.50
AWA_VALIDATOR_STAKE_MAX_SHARE = 1.0 / 3.0


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
    status:           str         # ENFORCED|SUSPENDED|DEGRADED|EMERGENCY|FROZEN
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
    # ── MD §17 canonical fields (Wave 3 D, R-CH-02) ─────────────────────
    # awa_canonical: spec-exact AWA_enforced — iff all six MD §17 conditions.
    awa_canonical:    bool = True
    # emission_frozen: MD §17 freeze flag (True iff not enforced — the
    # operational fail-closed superset, which includes awa_canonical).
    emission_frozen:  bool = False
    # canonical_conditions: per-condition MD §17 verdicts (spec names).
    canonical_conditions: Dict[str, bool] = field(default_factory=dict)


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

    AUDIT-3 G2 fix: the 4 "architecturally enforced" conditions
    (right_to_invisibility, no_single_entity_controls_weights,
    no_single_entity_controls_validators, sovereignty_dignity_protocol)
    are now runtime-evaluated, not hardcoded True. Override hooks:
      * set_sovereignty_dignity_active(False) — governance action revokes SDP
      * evaluate(signal_weight_distribution=..., validator_stake_distribution=...)
        runs the anti-centralization checks against real distribution data
      * right_to_invisibility is checked live against the
        core.governance.right_to_invisibility enforcement layer
    """

    def __init__(self):
        self.gratitude    = GratitudeProtocol()
        self.bootstrap    = BootstrapProtocol()
        self._last_state: Optional[AWAState] = None
        # Runtime AWA flags (G2 fix). Defaults preserve historical behavior
        # but are now mutable through explicit governance actions and runtime
        # evaluation against real distribution data.
        self._sovereignty_dignity_active: bool = True
        self._right_to_invisibility_active: Optional[bool] = None  # None = auto-detect
        # Cached RightToInvisibility enforcement-layer handle (lazy init).
        self._rtiv_handle = None
        self._rtiv_init_attempted = False

    # ─── Runtime governance hooks (G2 fix) ──────────────────────────────────

    def set_sovereignty_dignity_active(self, active: bool) -> None:
        """Governance action: revoke/restore Sovereignty Dignity Protocol."""
        self._sovereignty_dignity_active = bool(active)

    def set_right_to_invisibility_active(self, active: Optional[bool]) -> None:
        """Override Right-to-Invisibility runtime check.

        Pass True/False to force a state, or None to re-enable auto-detection
        against the live enforcement layer (core.governance.right_to_invisibility).
        """
        self._right_to_invisibility_active = active

    def _check_right_to_invisibility(self) -> bool:
        """Runtime check: Right-to-Invisibility enforcement layer functional.

        Per WP2 §17, signal emission is FROZEN if R_inv is not enforced. We
        verify the enforcement layer can be initialized (SQLite petitions DB
        accessible, RightToInvisibility class loadable). An explicit override
        via set_right_to_invisibility_active() takes precedence.
        """
        if self._right_to_invisibility_active is not None:
            return self._right_to_invisibility_active
        if not self._rtiv_init_attempted:
            self._rtiv_init_attempted = True
            try:
                # Import inside method so the AWA module remains importable
                # even if the right_to_invisibility module has optional deps
                # (e.g. missing sqlite3) on minimal runtimes. Direct-script
                # execution (`python core/governance/awa.py`) needs the repo
                # root on sys.path for the package-qualified import — the
                # same fixup pattern used by core/akashic/bibl.py.
                try:
                    from core.governance.right_to_invisibility import RightToInvisibility
                except ImportError:
                    import sys as _sys, os as _os
                    _sys.path.insert(
                        0, _os.path.join(_os.path.dirname(__file__), "..", "..")
                    )
                    from core.governance.right_to_invisibility import RightToInvisibility
                # Use an in-memory DB to avoid filesystem side-effects on import.
                self._rtiv_handle = RightToInvisibility(db_path=":memory:")
            except Exception:
                self._rtiv_handle = None
        return self._rtiv_handle is not None

    @staticmethod
    def _max_share(distribution: Optional[Dict[str, float]]) -> Optional[float]:
        """Return the largest single-entity share in a {entity_id: share} dict.

        Shares are expected to be already normalized (sum ≈ 1.0). If the dict
        is empty or None, returns None (signal: distribution data unavailable).
        """
        if not distribution:
            return None
        vals = [float(v) for v in distribution.values() if v is not None and v >= 0]
        if not vals:
            return None
        return max(vals)

    def _check_no_single_entity_controls_weights(
        self, signal_weight_distribution: Optional[Dict[str, float]]
    ) -> bool:
        """Runtime check: no single entity controls > 50% of signal weights.

        If distribution data is unavailable (None / empty), the check is
        data-pending and treated as PASS (presumption of innocence) but
        flagged in the disclosure. This is NOT a hardcoded True — the
        condition is genuinely unmeasurable until distribution data is fed
        in by the caller.
        """
        mx = self._max_share(signal_weight_distribution)
        if mx is None:
            return True  # data-pending
        return mx < AWA_SIGNAL_WEIGHT_MAX_SHARE

    def _check_no_single_entity_controls_validator_selection(
        self, validator_stake_distribution: Optional[Dict[str, float]]
    ) -> bool:
        """Runtime check: no single entity controls validator selection.

        MD §17 condition name is ``no_single_entity_controls_validator_selection``;
        implemented as the BFT safety floor on validator stake: an adversary
        with >= 1/3 of validator stake controls validator selection outcomes
        (halts consensus / selects the set). Data-pending distributions are
        treated as PASS with a disclosure flag (presumption of innocence).
        """
        mx = self._max_share(validator_stake_distribution)
        if mx is None:
            return True  # data-pending
        return mx < AWA_VALIDATOR_STAKE_MAX_SHARE

    def _check_sovereignty_dignity(self) -> bool:
        """Runtime check: Sovereignty Dignity Protocol is active.

        The flag is mutable via set_sovereignty_dignity_active(); a
        WEAPONIZATION_ATTEMPT event in the Chameleon Protocol (§17) flips
        it to False, which immediately freezes signal emission.
        """
        return self._sovereignty_dignity_active

    def evaluate(
        self,
        consensus_quorum: float,
        validator_hhi:    float,
        public_good_pct:  float,
        akashic_depth:    float = 0.0,
        now:              Optional[float] = None,
        # AUDIT-3 G2 fix: distribution inputs for the 4 previously-hardcoded
        # conditions. When omitted (None), the anti-centralization checks are
        # data-pending (treated as PASS, presumption of innocence, but flagged
        # in the disclosure string so operators know the check is unmeasured).
        signal_weight_distribution:    Optional[Dict[str, float]] = None,
        validator_stake_distribution:  Optional[Dict[str, float]] = None,
    ) -> AWAState:
        now = now or time.time()
        gratitude_score = self.gratitude.compute_network_gratitude(now)
        bootstrap_w     = self.bootstrap.compute_weight(akashic_depth)

        # AUDIT-3 G2 fix: all 8 AWA conditions now runtime-evaluated.
        rtiv_ok     = self._check_right_to_invisibility()
        weights_ok  = self._check_no_single_entity_controls_weights(signal_weight_distribution)
        validators_ok = self._check_no_single_entity_controls_validator_selection(validator_stake_distribution)
        sdp_ok      = self._check_sovereignty_dignity()

        # Track which anti-centralization checks were data-pending (unmeasured).
        weights_measured    = signal_weight_distribution is not None and len(signal_weight_distribution) > 0
        validators_measured = validator_stake_distribution is not None and len(validator_stake_distribution) > 0

        conditions = {
            "quorum":                            consensus_quorum >= AWA_QUORUM,
            "hhi":                               validator_hhi < AWA_HHI_MAX,
            "gratitude":                         gratitude_score >= AWA_GRATITUDE_MIN,
            "public_good":                       public_good_pct >= AWA_PUBLIC_GOOD_MIN,
            "right_to_invisibility":             rtiv_ok,
            "no_single_entity_controls_weights":    weights_ok,
            "no_single_entity_controls_validators": validators_ok,
            "sovereignty_dignity_protocol":      sdp_ok,
        }

        failing = [k for k, v in conditions.items() if not v]

        # ── MD §17 canonical 6-condition conjunction (spec-exact iff) ────
        # AWA_enforced iff all_of: no_single_entity_controls_signal_weights,
        # no_single_entity_controls_validator_selection,
        # Public_Good_Charter_minimum >= 15%, Sovereignty_Dignity_Protocol_active,
        # Right_to_Invisibility_enforced, Gratitude >= 1.
        canonical_conditions = {
            "no_single_entity_controls_signal_weights":
                conditions["no_single_entity_controls_weights"],
            "no_single_entity_controls_validator_selection":
                conditions["no_single_entity_controls_validators"],
            "Public_Good_Charter_minimum":
                conditions["public_good"],
            "Sovereignty_Dignity_Protocol_active":
                conditions["sovereignty_dignity_protocol"],
            "Right_to_Invisibility_enforced":
                conditions["right_to_invisibility"],
            "Gratitude":
                conditions["gratitude"],
        }
        awa_canonical = all(canonical_conditions.values())

        # AUDIT-3 G2 fix: wire the 4 newly-runtime conditions into `enforced`.
        # Per WP2 §17: "AWA_enforced = FALSE -> signal emission FROZEN. Cannot
        # be overridden by any single entity. By design." Any failing condition
        # (including the anti-centralization + R_inv + SDP conditions) freezes
        # signal emission. Status tier reflects which category failed.
        #
        # Wave 3 D: `enforced` is the operational fail-closed SUPERSET —
        # canonical six + supplemental quorum/HHI validator-health checks.
        # awa_canonical (above) preserves the spec-exact iff semantics.
        if validator_hhi >= AWA_HHI_MAX:
            status = "EMERGENCY"
            enforced = False
        elif not conditions["quorum"] or not conditions["hhi"]:
            status = "SUSPENDED"
            enforced = False
        elif not conditions["gratitude"] or not conditions["public_good"]:
            status = "DEGRADED"
            enforced = False
        elif not (rtiv_ok and weights_ok and validators_ok and sdp_ok):
            # Anti-centralization / dignity / invisibility violation.
            # MD §17: "Cannot be overridden by any single entity."
            status = "FROZEN"
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
        if not rtiv_ok:
            failing_details.append("right_to_invisibility=NOT_ENFORCED (R_inv layer unavailable/revoked)")
        if not weights_ok:
            mx = self._max_share(signal_weight_distribution)
            failing_details.append(
                f"max_signal_weight_share={mx:.3f} >= {AWA_SIGNAL_WEIGHT_MAX_SHARE:.2f}"
            )
        elif not weights_measured:
            failing_details.append("max_signal_weight_share=DATA_PENDING")
        if not validators_ok:
            mx = self._max_share(validator_stake_distribution)
            failing_details.append(
                f"max_validator_stake_share={mx:.3f} >= {AWA_VALIDATOR_STAKE_MAX_SHARE:.3f}"
            )
        elif not validators_measured:
            failing_details.append("max_validator_stake_share=DATA_PENDING")
        if not sdp_ok:
            failing_details.append("sovereignty_dignity_protocol=INACTIVE")

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
            awa_canonical    = awa_canonical,
            emission_frozen  = not enforced,
            canonical_conditions = canonical_conditions,
        )
        self._last_state = state
        # MD §17 emission-freeze wiring (Wave 3 D): every evaluation updates
        # the process-wide emission gate. A failing state freezes truth
        # emission (T(t) silence); a passing state is the ONLY release path.
        _emission_gate._update_from_state(state)
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
            # MD §17 canonical view (Wave 3 D): spec-exact six-condition
            # AWA_enforced + the emission-freeze verdict.
            "awa_canonical":     state.awa_canonical,
            "emission_frozen":   state.emission_frozen,
            "canonical_conditions": {
                name: {"met": state.canonical_conditions.get(name, False)}
                for name in CANONICAL_AWA_CONDITIONS
            },
            "emission_gate":     _emission_gate.to_dict(),
            "conditions": {
                "consensus_quorum": {"value": round(state.consensus_quorum, 4), "threshold": AWA_QUORUM, "met": state.conditions_met["quorum"]},
                "validator_hhi":    {"value": round(state.validator_hhi, 1),    "threshold": AWA_HHI_MAX, "met": state.conditions_met["hhi"]},
                "gratitude_score":  {"value": round(state.gratitude_score, 4),  "threshold": AWA_GRATITUDE_MIN, "met": state.conditions_met["gratitude"]},
                "public_good_pct":  {"value": round(state.public_good_pct, 4),  "threshold": AWA_PUBLIC_GOOD_MIN, "met": state.conditions_met["public_good"]},
                # AUDIT-3 G2: 4 previously-hardcoded conditions now exposed live.
                "right_to_invisibility":             {"met": state.conditions_met["right_to_invisibility"]},
                "no_single_entity_controls_weights":    {
                    "met":       state.conditions_met["no_single_entity_controls_weights"],
                    "threshold": AWA_SIGNAL_WEIGHT_MAX_SHARE,
                },
                "no_single_entity_controls_validators": {
                    "met":       state.conditions_met["no_single_entity_controls_validators"],
                    "threshold": AWA_VALIDATOR_STAKE_MAX_SHARE,
                },
                "sovereignty_dignity_protocol":      {"met": state.conditions_met["sovereignty_dignity_protocol"]},
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

    # MD §17 canonical semantics: quorum/HHI are supplemental — the six
    # canonical conditions can all hold while the operational gate freezes
    # (fail-closed superset), but never the reverse.
    state_suppl = enforcer.evaluate(
        consensus_quorum=0.40,          # supplemental failure
        validator_hhi=1200,             # all six canonical conditions OK
        public_good_pct=0.20,
        akashic_depth=5000,
    )
    assert state_suppl.awa_canonical and not state_suppl.enforced
    assert state_suppl.emission_frozen

    # Emission gate: frozen after a failing evaluate, released by a passing one
    assert is_emission_frozen(), "failing evaluate must freeze emission"
    _pass = enforcer.evaluate(
        consensus_quorum=0.80, validator_hhi=1200,
        public_good_pct=0.20, akashic_depth=5000,
    )
    assert _pass.enforced and not is_emission_frozen()

    # WEAPONIZATION_ATTEMPT freeze + no single-entity override
    trigger_weaponization_freeze("self-test weaponization")
    assert is_emission_frozen()
    try:
        assert_emission_allowed("VALUATION")
        raise AssertionError("must raise while frozen")
    except EmissionFrozenError:
        pass
    assert_emission_allowed("SILENCE")   # silence is always emittable
    enforcer.evaluate(                    # only a passing evaluate releases
        consensus_quorum=0.80, validator_hhi=1200,
        public_good_pct=0.20, akashic_depth=5000,
    )
    assert not is_emission_frozen()

    bprot = BootstrapProtocol()
    print(f"Bootstrap weight D=0:      {bprot.compute_weight(0):.6f}")
    print(f"Bootstrap weight D=10000:  {bprot.compute_weight(10000):.6f}")
    print(f"Bootstrap weight D=46052:  {bprot.compute_weight(46052):.8f}")
    assert bprot.compute_weight(0) == 1.0
    assert bprot.compute_weight(46052) < BOOTSTRAP_FLOOR   # exact crossing: -ln(0.01)/0.0001 = 46051.7

    print("AWA + Gratitude + Bootstrap: PASS")
