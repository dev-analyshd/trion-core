"""tests/unit/test_conservation_audit.py — R-EC-06 lunar-cycle audit (W3-D).

CANONICAL_SPEC_MATRIX R-EC-06 / top-10 remediation #6:
    I_TRION(t) = BH_generated + A_absorbed − S_emitted − E_lost
    dI/dt ≥ 0 (append-only law, MD L0.4/L9.2); the spec's lunar cadence
    (L6.2 lunar period 2,551,442 s) requires an AUTOMATED audit that emits
    SYSTEMIC_RISK when |ΔI_ledger − ΔI_expected| > τ_audit.

run_conservation_audit (core/primitives/thermodynamics.py, Wave 3 D) is
that automation. These tests pin:
  * a coherent ledger audits clean (no directive);
  * a tampered balance (leak/injection) trips the deviation beyond τ;
  * a net-negative ΔI (information destroyed) trips the append-only
    violation factor;
  * the audit window filters states (lunar trailing window);
  * insufficient history audits clean with a note (never fabricates a
    verdict from one state);
  * the canonical constants (lunar period, τ_audit).
"""

import pytest

from core.primitives.thermodynamics import (
    LUNAR_CYCLE_SECONDS,
    TAU_AUDIT_DEFAULT,
    AkashicConservationLedger,
    run_conservation_audit,
)


def _ledger(rows):
    """Build a ledger from (ts, bh, a, s, e) tuples via the real API."""
    led = AkashicConservationLedger()
    for ts, bh, a, s, e in rows:
        led.record_state(timestamp=ts, bh_generated=bh, a_absorbed=a,
                         s_emitted=s, e_lost=e)
    return led


T0 = 1_700_000_000.0
ROWS = [
    (T0,             100.0, 50.0, 30.0, 1.0),
    (T0 + 3_600,     80.0,  20.0, 10.0, 0.5),
    (T0 + 2 * 86_400, 60.0, 40.0, 25.0, 0.2),
]


class TestConstants:
    def test_lunar_cycle_is_l6_2(self):
        assert LUNAR_CYCLE_SECONDS == 2_551_442   # 29.5 days (MD L6.2)

    def test_tau_audit_default(self):
        assert TAU_AUDIT_DEFAULT == 1e-6


class TestCleanLedger:
    def test_conserved_ledger_audits_clean(self):
        led = _ledger(ROWS)
        report = run_conservation_audit(led, now=T0 + 3 * 86_400)
        assert report["conserved"] is True
        assert report["systemic_risk"] is False
        assert report["emission_directive"] is None
        assert report["states_audited"] == 3
        assert report["risk_factors"] == []

    def test_expected_matches_realized_on_real_api(self):
        """States recorded via record_state balance exactly by construction."""
        led = _ledger(ROWS)
        report = run_conservation_audit(led, now=T0 + 3 * 86_400)
        assert report["deviation"] == pytest.approx(0.0, abs=TAU_AUDIT_DEFAULT)
        assert report["delta_realized"] == pytest.approx(report["delta_expected"])
        assert report["i_end"] == led.total_information

    def test_delta_expected_is_flow_sum(self):
        led = _ledger(ROWS)
        report = run_conservation_audit(led, now=T0 + 3 * 86_400)
        manual = sum(bh + a - s - e for _, bh, a, s, e in ROWS)
        assert report["delta_expected"] == pytest.approx(manual)

    def test_insufficient_history_is_not_a_verdict(self):
        led = _ledger([ROWS[0]])
        report = run_conservation_audit(led, now=T0 + 60)
        assert report["conserved"] is True
        assert report["states_audited"] == 1
        assert report["emission_directive"] is None
        assert "insufficient_history" in report["risk_factors"]
        assert "nothing to audit" in report["note"]

    def test_empty_ledger_never_fabricates(self):
        report = run_conservation_audit(AkashicConservationLedger(), now=T0)
        assert report["conserved"] is True
        assert report["systemic_risk"] is False


class TamperedLedger(AkashicConservationLedger):
    """Ledger whose recorded balance was externally corrupted (leak class)."""


class TestLeakDetection:
    def _tampered(self, delta):
        led = _ledger(ROWS)
        led.states[-1].i_total += delta     # corrupt the end balance
        return led

    def test_leak_trips_systemic_risk(self):
        led = self._tampered(-25.0)         # 25 nats vanished
        report = run_conservation_audit(led, now=T0 + 3 * 86_400)
        assert report["deviation"] == pytest.approx(25.0)
        assert report["conserved"] is False
        assert report["systemic_risk"] is True
        assert any("leak" in f or "accounting" in f
                   for f in report["risk_factors"])

    def test_injection_trips_systemic_risk(self):
        led = self._tampered(+10.0)         # 10 nats appeared from nowhere
        report = run_conservation_audit(led, now=T0 + 3 * 86_400)
        assert report["conserved"] is False
        assert report["systemic_risk"] is True

    def test_directive_is_systemic_risk_signal(self):
        led = self._tampered(-25.0)
        report = run_conservation_audit(led, now=T0 + 3 * 86_400)
        directive = report["emission_directive"]
        assert directive["signal_type"] == "SYSTEMIC_RISK"
        assert directive["reason"] == "information_conservation_audit_failure"
        assert directive["risk_factors"]
        assert directive["window_seconds"] > 0

    def test_small_deviation_within_tau_passes(self):
        led = self._tampered(TAU_AUDIT_DEFAULT / 10)
        report = run_conservation_audit(led, now=T0 + 3 * 86_400)
        assert report["conserved"] is True


class TestInformationDestroyed:
    def test_negative_di_violates_append_only_law(self):
        """dI/dt < 0 — information destroyed (MD L0.4/L9.2 violation).

        The ledger API clamps i_total at 0 (conservation floor), so a
        NEGATIVE balance can only appear in a foreign/corrupted ledger
        projection — constructed here directly to exercise the audit's
        append-only-law tripwire.
        """
        from core.primitives.thermodynamics import InformationState
        led = AkashicConservationLedger()
        led.states = [
            InformationState(timestamp=T0, bh_generated=100.0, a_absorbed=0.0,
                             s_emitted=0.0, e_lost=0.0, i_total=100.0),
            InformationState(timestamp=T0 + 3_600, bh_generated=0.0, a_absorbed=0.0,
                             s_emitted=500.0, e_lost=0.0, i_total=-400.0),
        ]
        report = run_conservation_audit(led, now=T0 + 7_200)
        assert report["delta_realized"] == pytest.approx(-400.0)
        assert report["conserved"] is False
        assert report["systemic_risk"] is True
        assert any("dI/dt" in f and "< 0" in f for f in report["risk_factors"])
        assert any("append-only" in f for f in report["risk_factors"])

    def test_overemission_trips_via_deviation(self):
        """Emitting more than the ledger holds: the API's 0-floor absorbs
        the negative balance, so the audit catches it as a conservation
        DEVIATION (expected −400 vs realized 0) — still fail-closed."""
        led = _ledger([
            (T0,         100.0, 0.0,   0.0, 0.0),
            (T0 + 3_600,   0.0, 0.0, 500.0, 0.0),
        ])
        report = run_conservation_audit(led, now=T0 + 7_200)
        assert report["systemic_risk"] is True
        assert report["deviation"] == pytest.approx(400.0)
        assert report["emission_directive"]["signal_type"] == "SYSTEMIC_RISK"

    def test_negative_di_directive_fires(self):
        from core.primitives.thermodynamics import InformationState
        led = AkashicConservationLedger()
        led.states = [
            InformationState(timestamp=T0, bh_generated=10.0, a_absorbed=0.0,
                             s_emitted=0.0, e_lost=0.0, i_total=10.0),
            InformationState(timestamp=T0 + 120, bh_generated=0.0, a_absorbed=0.0,
                             s_emitted=30.0, e_lost=0.0, i_total=-20.0),
        ]
        report = run_conservation_audit(led, now=T0 + 180)
        assert report["delta_realized"] == pytest.approx(-20.0)
        assert report["emission_directive"] is not None
        assert report["emission_directive"]["signal_type"] == "SYSTEMIC_RISK"


class TestAuditWindow:
    def test_window_filters_old_states(self):
        """Only states inside the trailing lunar window are audited."""
        led = _ledger([
            (T0,                   100.0, 0.0, 0.0, 0.0),
            (T0 + 10 * 86_400,      50.0, 0.0, 0.0, 0.0),   # inside window
            (T0 + 20 * 86_400,      25.0, 0.0, 0.0, 0.0),   # inside window
        ])
        now = T0 + 20 * 86_400 + 1
        report = run_conservation_audit(led, window_seconds=15 * 86_400, now=now)
        assert report["states_audited"] == 2
        assert report["delta_expected"] == pytest.approx(75.0)
        # i_start is the first IN-WINDOW state's balance (the pre-window
        # state's +100 is outside the audited flow set)
        assert report["i_start"] == 150.0
        assert report["i_end"] == 175.0
        assert report["conserved"] is True

    def test_lunar_window_is_the_default(self):
        led = _ledger(ROWS)
        report = run_conservation_audit(led, now=T0 + 3 * 86_400)
        assert report["window_seconds"] == LUNAR_CYCLE_SECONDS

    def test_no_states_in_window_falls_back_to_all(self):
        """Honest fallback: an empty window audits the full ledger rather
        than returning a fabricated clean verdict from no data."""
        led = _ledger(ROWS)
        report = run_conservation_audit(
            led, window_seconds=1.0, now=T0 + 10 * LUNAR_CYCLE_SECONDS)
        assert report["states_audited"] == 3

    def test_tau_is_configurable(self):
        led = _ledger(ROWS)
        led.states[-1].i_total += 0.5
        strict = run_conservation_audit(led, tau_audit=1e-9, now=T0 + 3 * 86_400)
        loose = run_conservation_audit(led, tau_audit=1.0, now=T0 + 3 * 86_400)
        assert strict["conserved"] is False
        assert loose["conserved"] is True
