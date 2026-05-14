"""
TRION Protocol — L1.3 Temporal Coherence
Channel 1: Physical Cosmological Communication (GPS/NTP)

TC(t) = 1 - max_i(|t_plane_i - t_reference|) / TTL_min

Ensures all five planes are synchronized to within TTL_min of each other.
If any plane's data is more than TTL_min stale, TC degrades toward 0.

TC = 1.0: all planes perfectly synchronized
TC = 0.0: at least one plane is >= TTL_min behind reference
TC < 0:   truncated to 0 — plane is critically stale

TI (Transduction Integrity):
TI(sensor, t) = Calibration(s,t) · Drift_correction(s,t) · Cross_verification(s,t)
TI = 0: uncalibrated sensor — excluded from Φ computation entirely

Author: TRION Protocol — Originator: Hudu Yusuf (Analys)
License: CC0
"""

from __future__ import annotations
from dataclasses import dataclass
from typing import Dict, Optional


# Default TTL_min = 300 seconds (5 minutes) — all planes must be within this
TTL_MIN_DEFAULT: float = 300.0

PLANE_NAMES = ("physical", "mental", "spiritual", "conscious", "akashic")


@dataclass
class PlaneTimestamp:
    """Timestamp metadata for one coherence plane."""
    plane:      str
    timestamp:  float   # Unix timestamp of latest data
    ttl:        float   # TTL of this plane's data (seconds)
    source:     str     # data source identifier


@dataclass
class TemporalCoherenceResult:
    """
    TC(t) = 1 - max_i(|t_plane_i - t_reference|) / TTL_min
    """
    tc:                 float   # [0, 1]
    max_lag_seconds:    float
    ttl_min:            float
    lagging_plane:      str     # The plane with the maximum lag
    t_reference:        float   # Reference timestamp (latest plane)
    plane_lags:         Dict[str, float]
    valid:              bool
    warning:            Optional[str]


def compute_temporal_coherence(
    plane_timestamps: Dict[str, PlaneTimestamp],
    ttl_min:          float = TTL_MIN_DEFAULT,
) -> TemporalCoherenceResult:
    """
    TC(t) = 1 - max_i(|t_plane_i - t_reference|) / TTL_min

    t_reference = the most recent plane timestamp
    max_i = the plane farthest behind reference

    If TC < 0: truncated to 0. Any plane > TTL_min stale → TC = 0.
    """
    if not plane_timestamps:
        return TemporalCoherenceResult(
            tc=0.0, max_lag_seconds=float("inf"), ttl_min=ttl_min,
            lagging_plane="none", t_reference=0.0, plane_lags={},
            valid=False, warning="No plane timestamps provided",
        )

    # Reference = most recent timestamp
    t_ref = max(pt.timestamp for pt in plane_timestamps.values())

    plane_lags: Dict[str, float] = {}
    max_lag = 0.0
    lagging_plane = ""

    for name, pt in plane_timestamps.items():
        lag = abs(t_ref - pt.timestamp)
        plane_lags[name] = lag
        if lag > max_lag:
            max_lag = lag
            lagging_plane = name

    tc = max(0.0, 1.0 - max_lag / ttl_min)

    warning = None
    if tc < 0.50:
        warning = f"TC={tc:.3f} critical — {lagging_plane} plane lag={max_lag:.0f}s > {ttl_min/2:.0f}s"
    elif tc < 0.80:
        warning = f"TC={tc:.3f} degraded — {lagging_plane} plane lag={max_lag:.0f}s"

    return TemporalCoherenceResult(
        tc              = tc,
        max_lag_seconds = max_lag,
        ttl_min         = ttl_min,
        lagging_plane   = lagging_plane,
        t_reference     = t_ref,
        plane_lags      = plane_lags,
        valid           = True,
        warning         = warning,
    )


@dataclass
class SensorCalibration:
    """Calibration state for a physical sensor."""
    sensor_id:           str
    calibration_score:   float   # [0, 1] — decays with time since calibration
    drift_correction:    float   # [0, 1] — 1 = no drift, 0 = fully drifted
    cross_verification:  float   # [0, 1] — agreement with peer sensors


@dataclass
class TransductionIntegrityResult:
    """
    TI(sensor, t) = Calibration(s,t) · Drift_correction(s,t) · Cross_verification(s,t)
    """
    sensor_id:    str
    ti:           float   # [0, 1]
    calibration:  float
    drift:        float
    cross:        float
    excluded:     bool    # TI = 0 → sensor excluded from Φ computation
    reason:       Optional[str]


def compute_transduction_integrity(
    sensor: SensorCalibration,
) -> TransductionIntegrityResult:
    """
    TI(sensor, t) = Calibration · Drift_correction · Cross_verification

    TI = 0 conditions:
    - Calibration = 0: sensor not calibrated within tolerance
    - Drift = 0: sensor has drifted beyond acceptable range
    - Cross-verification = 0: sensor disagrees with all peers

    Any zero component → TI = 0 → sensor excluded from Φ.
    """
    cal  = max(0.0, min(1.0, sensor.calibration_score))
    dri  = max(0.0, min(1.0, sensor.drift_correction))
    cro  = max(0.0, min(1.0, sensor.cross_verification))

    ti = cal * dri * cro
    excluded = ti == 0.0

    reason = None
    if cal == 0.0:
        reason = "Sensor not calibrated — excluded from Φ"
    elif dri == 0.0:
        reason = "Sensor drift exceeds tolerance — excluded from Φ"
    elif cro == 0.0:
        reason = "Sensor cross-verification failed — excluded from Φ"

    return TransductionIntegrityResult(
        sensor_id   = sensor.sensor_id,
        ti          = ti,
        calibration = cal,
        drift       = dri,
        cross       = cro,
        excluded    = excluded,
        reason      = reason,
    )


def adjust_phi_for_ti(phi_raw: float, ti_scores: list[float]) -> float:
    """
    Φ_adj(t) = Φ(t) · mean(TI_scores)
    Sensors with TI = 0 are excluded before this step (not averaged in).
    """
    valid_ti = [ti for ti in ti_scores if ti > 0]
    if not valid_ti:
        return 0.0
    mean_ti = sum(valid_ti) / len(valid_ti)
    return phi_raw * mean_ti


if __name__ == "__main__":
    import time
    now = time.time()

    planes = {
        "physical":  PlaneTimestamp("physical",  now - 10,   300, "evm_indexer"),
        "mental":    PlaneTimestamp("mental",    now - 45,   300, "anima_crawler"),
        "spiritual": PlaneTimestamp("spiritual", now - 5,    300, "validator_mesh"),
        "conscious": PlaneTimestamp("conscious", now - 120,  300, "annotation_api"),
        "akashic":   PlaneTimestamp("akashic",   now - 8,    300, "timescaledb"),
    }

    tc_result = compute_temporal_coherence(planes)
    print(f"TC={tc_result.tc:.4f} max_lag={tc_result.max_lag_seconds:.0f}s "
          f"lagging={tc_result.lagging_plane}")
    assert 0 < tc_result.tc <= 1.0

    # Sensor TI test
    sensor = SensorCalibration("hsm_0", calibration_score=0.95, drift_correction=0.98, cross_verification=0.92)
    ti = compute_transduction_integrity(sensor)
    print(f"TI={ti.ti:.4f} excluded={ti.excluded}")
    assert not ti.excluded

    dead_sensor = SensorCalibration("dead", calibration_score=0.0, drift_correction=0.9, cross_verification=0.9)
    ti_dead = compute_transduction_integrity(dead_sensor)
    assert ti_dead.ti == 0.0
    assert ti_dead.excluded

    print("L1.3 Temporal Coherence + L1.4 Transduction Integrity: PASS")
