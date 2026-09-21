"""
TRION Protocol — L1.4: Transduction Integrity (TI)
====================================================
Canonical source: core/physical/temporal_coherence.py::compute_transduction_integrity

  TI(sensor, t) = Calibration · Drift_correction · Cross_verification

  TI = 0 conditions:
    - Calibration = 0: sensor not calibrated within tolerance
    - Drift = 0: sensor has drifted beyond acceptable range
    - Cross-verification = 0: sensor disagrees with all peers

  Any zero component → TI = 0 → sensor excluded from Φ.

FIX-E (Gap 17b) — file rename + content relocation:
  Previously this file contained the TRION_PROTOCOL reflexive self-verification
  module (genomic key chaining, 5-plane coherence scoring, background monitor
  loop) — a misnaming that left TI consumers without a proper TI module and
  forced self-verification consumers to import from a confusingly-named file.
  That content has been moved to its correct location:
    core/physical/self_verification.py
  This file now re-exports the canonical TI implementation from
  core/physical/temporal_coherence.py so consumers can import the L1.4
  Transduction Integrity primitive from its spec-mandated module path
  (core/physical/transduction_integrity.py) without duplicating the formula.

The actual TI computation lives in temporal_coherence.py because TI is
tightly coupled with the Temporal Coherence (L1.3) pipeline — both consume
the same SensorCalibration input and both feed the Φ adjustment step.
Keeping them in the same module avoids circular imports and keeps the
spec L1.3/L1.4 implementation cohesive. This module is the canonical
public entry point for callers that only want TI.
"""

from __future__ import annotations

from typing import List, Optional

# ── Canonical TI primitive re-exports ──────────────────────────────────────────
# All four symbols are imported verbatim from temporal_coherence so that
# consumers of L1.4 Transduction Integrity can `from core.physical.
# transduction_integrity import compute_transduction_integrity` (the spec-
# mandated import path) without coupling to temporal_coherence.
from core.physical.temporal_coherence import (
    SensorCalibration,
    TransductionIntegrityResult,
    compute_transduction_integrity,
    adjust_phi_for_ti,
)

__all__ = [
    "SensorCalibration",
    "TransductionIntegrityResult",
    "compute_transduction_integrity",
    "adjust_phi_for_ti",
    "system_transduction_integrity",
]


def system_transduction_integrity(
    sensor_scores: List[SensorCalibration],
    *,
    exclude_zero: bool = True,
) -> dict:
    """
    Aggregate TI across a fleet of sensors.

    Returns the per-sensor TI results, the mean TI (excluding TI=0 sensors
    when `exclude_zero=True`), and the list of excluded sensor_ids (those
    whose Calibration/Drift/Cross-verification hit zero — see L1.4 spec).

    Parameters
    ----------
    sensor_scores : list of SensorCalibration inputs (one per sensor)
    exclude_zero  : if True (default — matches spec L1.4 "sensors with
                    TI=0 are excluded from Φ"), the mean is computed only
                    over sensors with TI > 0. If False, all sensors are
                    included in the mean.

    Returns
    -------
    {
        "per_sensor":   [TransductionIntegrityResult, ...],
        "mean_ti":      float,        # 0.0 if no sensors
        "excluded":     [sensor_id, ...],
        "sensor_count": int,
    }
    """
    per_sensor = [compute_transduction_integrity(s) for s in sensor_scores]
    excluded = [r.sensor_id for r in per_sensor if r.excluded]
    valid_tis = [r.ti for r in per_sensor if (r.ti > 0 or not exclude_zero)]
    mean_ti = (sum(valid_tis) / len(valid_tis)) if valid_tis else 0.0
    return {
        "per_sensor":   per_sensor,
        "mean_ti":      round(mean_ti, 6),
        "excluded":     excluded,
        "sensor_count": len(per_sensor),
    }


if __name__ == "__main__":
    # Smoke test — re-export parity + system_aggregate
    healthy = SensorCalibration(
        sensor_id="sol_mainnet_rpc",
        calibration_score=0.98,
        drift_correction=0.95,
        cross_verification=0.92,
    )
    drifted = SensorCalibration(
        sensor_id="eth_mainnet_archive",
        calibration_score=0.95,
        drift_correction=0.0,  # drifted beyond tolerance
        cross_verification=0.80,
    )
    r1 = compute_transduction_integrity(healthy)
    r2 = compute_transduction_integrity(drifted)
    assert r1.ti > 0.0, "Healthy sensor should have TI > 0"
    assert r2.ti == 0.0, "Drifted sensor should have TI = 0"
    assert r2.excluded, "Drifted sensor should be marked excluded"
    assert r2.reason == "Sensor drift exceeds tolerance — excluded from Φ"

    phi_adj = adjust_phi_for_ti(0.80, [r1.ti])
    expected_phi = 0.80 * r1.ti  # spec: Φ_adj = Φ_raw · mean(TI_scores)
    assert abs(phi_adj - expected_phi) < 1e-9, "Φ_adj with one healthy TI = Φ_raw · TI"

    sys_aggregate = system_transduction_integrity([healthy, drifted])
    assert sys_aggregate["sensor_count"] == 2
    assert sys_aggregate["excluded"] == ["eth_mainnet_archive"]
    assert sys_aggregate["mean_ti"] == round(r1.ti, 6)  # drifted excluded
    print(f"healthy TI: {r1.ti:.6f} (cal={r1.calibration} drift={r1.drift} cross={r1.cross})")
    print(f"drifted TI: {r2.ti:.6f} (excluded={r2.excluded}, reason={r2.reason})")
    print(f"system mean TI: {sys_aggregate['mean_ti']:.6f} (excluded: {sys_aggregate['excluded']})")
    print(f"Φ_adj after TI: {phi_adj:.6f}")
    print("L1.4 Transduction Integrity module — PASS (re-export from temporal_coherence verified)")
