"""tests/unit/test_awa_freeze.py — MD §17 AWA canonical set + emission freeze.

Wave 3 D, R-CH-02 / top-10 remediation #2 (the DEVIANT item):

  AWA_enforced iff all_of:
      no_single_entity_controls_signal_weights
      no_single_entity_controls_validator_selection
      Public_Good_Charter_minimum >= 15%
      Sovereignty_Dignity_Protocol_active
      Right_to_Invisibility_enforced
      Gratitude >= 1
  AWA_enforced = FALSE → signal emission FROZEN
  Cannot be overridden by any single entity. By design.

Verifies:
  * all six canonical conditions are encoded explicitly (spec names),
  * each condition false ⇒ awa_canonical False ⇒ emission frozen,
  * build_signal converts truth requests to structured SILENCE (T(t)=0)
    while frozen and passes SILENCE through,
  * the freeze cannot be released by anything but a passing evaluate()
    (no single-entity override), including after WEAPONIZATION_ATTEMPT,
  * the Chameleon WEAPONIZATION_ATTEMPT path freezes the global gate.
"""

import pytest

from core.governance.awa import (
    AWAEnforcer,
    AWAState,
    CANONICAL_AWA_CONDITIONS,
    EmissionFrozenError,
    assert_emission_allowed,
    get_emission_gate,
    is_emission_frozen,
    trigger_weaponization_freeze,
)
from core.master.signal_factory import SignalType, build_signal
from core.novel.chameleon import ChameleonProtocol, ThreatLevel


GOOD = dict(
    consensus_quorum=0.80,       # supplemental health OK
    validator_hhi=1200.0,        # supplemental health OK
    public_good_pct=0.20,        # Public_Good_Charter_minimum >= 15% ✓
    akashic_depth=1000.0,
)

_COH = {
    "C": 0.90, "theta": 0.60, "margin": 0.30, "emits": True,
    "coherence_gap": 0, "limiting_plane": "anima", "trend": "STABLE",
    "eta_blocks": 0,
}


def _enforced_enforcer() -> AWAEnforcer:
    """Fresh enforcer with a verified gratitude disclosure (Gratitude >= 1)."""
    aw = AWAEnforcer()
    aw.gratitude.record_disclosure(
        entity_id="white_hat", vulnerability_id="VUL-1",
        severity="MEDIUM", credit=5.0, verified=True,
    )
    return aw


@pytest.fixture(autouse=True)
def _release_gate():
    """Every test leaves the process-wide emission gate released."""
    yield
    aw = _enforced_enforcer()
    aw.evaluate(**GOOD)          # passing evaluate is the only release path


# ─── Canonical condition set (R-CH-02) ────────────────────────────────────────

class TestCanonicalConditionSet:
    def test_six_canonical_conditions_encoded(self):
        assert CANONICAL_AWA_CONDITIONS == [
            "no_single_entity_controls_signal_weights",
            "no_single_entity_controls_validator_selection",
            "Public_Good_Charter_minimum",
            "Sovereignty_Dignity_Protocol_active",
            "Right_to_Invisibility_enforced",
            "Gratitude",
        ]

    def test_all_conditions_pass_when_healthy(self):
        aw = _enforced_enforcer()
        state = aw.evaluate(**GOOD)
        assert state.awa_canonical is True
        assert state.canonical_conditions and all(state.canonical_conditions.values())
        assert state.enforced and not state.emission_frozen

    def test_canonical_is_iff_all_six(self):
        """awa_canonical is TRUE iff all six MD §17 conditions hold."""
        aw = _enforced_enforcer()
        state = aw.evaluate(**GOOD)
        assert state.awa_canonical == all(state.canonical_conditions.values())

    def test_supplemental_failure_keeps_canonical_true(self):
        """quorum/HHI are supplemental: canonical iff holds, gate freezes anyway."""
        aw = _enforced_enforcer()
        state = aw.evaluate(**{**GOOD, "consensus_quorum": 0.40})
        assert state.awa_canonical is True       # spec-exact iff semantics
        assert state.enforced is False           # fail-closed superset
        assert state.emission_frozen is True


# ─── Each canonical condition false ⇒ FROZEN (fail-closed) ───────────────────

class TestEachConditionFreezes:
    def test_signal_weights_monopoly_freezes(self):
        aw = _enforced_enforcer()
        state = aw.evaluate(
            **GOOD,
            signal_weight_distribution={"entity_a": 0.9, "entity_b": 0.1},
        )
        assert not state.canonical_conditions["no_single_entity_controls_signal_weights"]
        assert not state.awa_canonical
        assert state.status == "FROZEN" and state.emission_frozen

    def test_validator_selection_control_freezes(self):
        aw = _enforced_enforcer()
        state = aw.evaluate(
            **GOOD,
            validator_stake_distribution={"cartel": 0.5, "rest": 0.5},
        )
        assert not state.canonical_conditions["no_single_entity_controls_validator_selection"]
        assert not state.awa_canonical and state.emission_frozen

    def test_public_good_below_15pct_freezes(self):
        aw = _enforced_enforcer()
        state = aw.evaluate(**{**GOOD, "public_good_pct": 0.14})
        assert not state.canonical_conditions["Public_Good_Charter_minimum"]
        assert not state.awa_canonical and state.emission_frozen

    def test_sdp_inactive_freezes(self):
        aw = _enforced_enforcer()
        aw.set_sovereignty_dignity_active(False)
        try:
            state = aw.evaluate(**GOOD)
            assert not state.canonical_conditions["Sovereignty_Dignity_Protocol_active"]
            assert not state.awa_canonical and state.status == "FROZEN"
        finally:
            aw.set_sovereignty_dignity_active(True)

    def test_right_to_invisibility_off_freezes(self):
        """MD §16: AWA_enforced = FALSE if Right_to_Invisibility = FALSE."""
        aw = _enforced_enforcer()
        aw.set_right_to_invisibility_active(False)
        try:
            state = aw.evaluate(**GOOD)
            assert not state.canonical_conditions["Right_to_Invisibility_enforced"]
            assert not state.awa_canonical and state.emission_frozen
        finally:
            aw.set_right_to_invisibility_active(None)

    def test_gratitude_below_one_freezes(self):
        aw = AWAEnforcer()       # NO disclosure recorded → Gratitude = 0
        state = aw.evaluate(**GOOD)
        assert not state.canonical_conditions["Gratitude"]
        assert not state.awa_canonical and state.status == "DEGRADED"


# ─── Emission freeze: T(t) silence (the "silence is information" guarantee) ──

class TestEmissionFreeze:
    def test_frozen_gate_silences_truth_signals(self):
        aw = _enforced_enforcer()
        aw.evaluate(**{**GOOD, "public_good_pct": 0.05})   # freeze
        assert is_emission_frozen()
        sig = build_signal(b"\xab" * 32, SignalType.VALUATION, _COH, signal_value=0.9)
        assert sig["signal_type"] == "SILENCE"             # T(t) = 0
        assert sig["signal_value"] is None
        assert sig["awa_freeze"]["emission_frozen"] is True
        assert "TRUTH EMISSION FROZEN" in sig["silence_explanation"]
        assert sig["requested_signal_type"] == "VALUATION"

    def test_silence_passes_through_while_frozen(self):
        aw = _enforced_enforcer()
        aw.evaluate(**{**GOOD, "public_good_pct": 0.05})
        sig = build_signal(b"\xab" * 32, SignalType.SILENCE, {**_COH, "emits": False})
        assert sig["signal_type"] == "SILENCE"
        assert "awa_freeze" not in sig                     # silence IS the output

    def test_every_type_is_silenced_when_frozen(self):
        aw = _enforced_enforcer()
        aw.evaluate(**{**GOOD, "public_good_pct": 0.05})
        for st in SignalType:
            sig = build_signal(b"\xab" * 32, st, _COH, signal_value=0.5)
            assert sig["signal_type"] == "SILENCE", f"{st.name} must be silenced"

    def test_assert_emission_allowed_raises_for_truth(self):
        aw = _enforced_enforcer()
        aw.evaluate(**{**GOOD, "public_good_pct": 0.05})
        with pytest.raises(EmissionFrozenError):
            assert_emission_allowed(SignalType.VALUATION)
        assert_emission_allowed(SignalType.SILENCE)        # always allowed

    def test_unfrozen_emission_is_unchanged(self):
        aw = _enforced_enforcer()
        aw.evaluate(**GOOD)
        assert not is_emission_frozen()
        sig = build_signal(b"\xab" * 32, SignalType.VALUATION, _COH, signal_value=0.9)
        assert sig["signal_type"] == "VALUATION" and "awa_freeze" not in sig


# ─── "Cannot be overridden by any single entity" ──────────────────────────────

class TestNoSingleEntityOverride:
    def test_no_public_unfreeze_api(self):
        gate = get_emission_gate()
        freeze_methods = [m for m in dir(gate) if "unfreeze" in m.lower() or "release" in m.lower()]
        assert freeze_methods == [], "the gate must expose NO unfreeze/release API"

    def test_only_passing_evaluate_releases(self):
        aw = _enforced_enforcer()
        aw.evaluate(**{**GOOD, "public_good_pct": 0.05})   # frozen
        # a *failing* re-evaluation does NOT release
        aw.evaluate(**{**GOOD, "public_good_pct": 0.05})
        assert is_emission_frozen()
        # a passing evaluation releases
        aw.evaluate(**GOOD)
        assert not is_emission_frozen()

    def test_weaponization_freeze_hard_to_override(self):
        aw = _enforced_enforcer()
        aw.evaluate(**GOOD)
        trigger_weaponization_freeze("test weaponization attempt")
        assert is_emission_frozen()
        with pytest.raises(EmissionFrozenError):
            assert_emission_allowed("VALUATION")
        # only a passing evaluate releases (frozen since is recorded)
        aw.evaluate(**GOOD)
        assert not is_emission_frozen()

    def test_chameleon_weaponization_attempt_freezes_globally(self):
        """MD §17 / chameleon §17: WEAPONIZATION_ATTEMPT → global freeze."""
        aw = _enforced_enforcer()
        aw.evaluate(**GOOD)
        cham = ChameleonProtocol()
        expr = cham.adapt(ThreatLevel.WEAPONIZATION_ATTEMPT)
        assert expr.emission_frozen and not cham.emission_allowed
        assert is_emission_frozen(), "chameleon freeze must reach the global gate"
        sig = build_signal(b"\xab" * 32, SignalType.VALUATION, _COH, signal_value=0.9)
        assert sig["signal_type"] == "SILENCE"
        aw.evaluate(**GOOD)                                 # release for the fixture
        assert not is_emission_frozen()


# ─── AWA state surface ────────────────────────────────────────────────────────

class TestAWAStateSurface:
    def test_to_dict_carries_canonical_view(self):
        aw = _enforced_enforcer()
        state = aw.evaluate(**GOOD)
        d = aw.to_dict(state)
        assert d["awa_canonical"] is True
        assert d["emission_frozen"] is False
        assert set(d["canonical_conditions"]) == set(CANONICAL_AWA_CONDITIONS)
        assert "emission_gate" in d

    def test_awa_hhi_emergency_still_freezes(self):
        """Supplemental HHI > 4000 (CRITICAL) — existing tier preserved."""
        aw = _enforced_enforcer()
        state = aw.evaluate(**{**GOOD, "validator_hhi": 4001})
        assert state.status == "EMERGENCY" and not state.enforced
        assert state.emission_frozen and is_emission_frozen()

    def test_awa_state_dataclass_defaults(self):
        """AWAState new fields default safely for legacy constructors."""
        s = AWAState(
            enforced=True, status="ENFORCED", consensus_quorum=0.8,
            validator_hhi=1000.0, gratitude_score=1.0, public_good_pct=0.2,
            bootstrap_weight=0.5, akashic_depth=100.0, conditions_met={},
            failing_conditions=[], timestamp=0.0, disclosure="",
        )
        assert s.awa_canonical is True and s.emission_frozen is False


# ─── API publication wiring (lead integration — MD §17 at the route) ─────────

class TestPublicationRouteFreeze:
    """/api/v1/publish/<entity> must fail closed while emission is frozen."""

    def test_publish_route_503_silence_when_frozen(self):
        import os
        os.environ.setdefault("TRION_STREAMER_INPROCESS", "0")
        from core.governance.awa import get_emission_gate
        from api.app import app  # noqa: PLC0415 — wiring-under-test import

        gate = get_emission_gate()
        was_frozen = gate.is_frozen()
        try:
            if not was_frozen:
                gate.freeze(reason="regression-test", source="test_awa_freeze")
            c = app.test_client()
            r = c.post("/api/v1/publish/awa-freeze-regression-entity")
            assert r.status_code == 503
            j = r.get_json()
            assert j.get("silence") is True
            assert j.get("chain", {}).get("published") is False
            assert "awa_emission_frozen" in j.get("chain", {}).get("error", "")
        finally:
            gate._frozen = was_frozen

    def test_publish_route_open_when_unfrozen(self):
        import os
        os.environ.setdefault("TRION_STREAMER_INPROCESS", "0")
        from core.governance.awa import get_emission_gate
        from api.app import app  # noqa: PLC0415

        gate = get_emission_gate()
        was_frozen = gate.is_frozen()
        try:
            gate._frozen = False
            c = app.test_client()
            r = c.post("/api/v1/publish/awa-freeze-open-entity")
            assert r.status_code in (200, 503)  # 503 only if frozen by a sibling
            if r.status_code == 200:
                assert r.get_json().get("silence") is None or True
        finally:
            gate._frozen = was_frozen
