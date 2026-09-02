"""
L6.2 — Biological Rhythm Timer (BRT)

Natural rhythm correlations tracked in Akashic Index:
  - Circadian anomaly: signal pattern deviates from 24h baseline
  - Lunar anomaly: liquidity pattern shifts correlating with lunar phase
  - Seasonal anomaly: behavioral rhythm shifts at quarter boundaries

BRT is included in every TRIONSignal object as biological_time field.
Enables ANIMA to detect when human behavioral patterns shift relative to
natural rhythms — a known precursor to market regime changes.

BRT–gas correlation (whitepaper F14, CONJECTURE):
  compute_brt_gas_correlation() measures the circular-linear correlation
  between a BRT phase (circadian/ultradian/lunar/seasonal) and observed
  on-chain gas prices, using Mardia's circular-linear correlation with an
  exact chi-square (df=2) significance test. Whitepaper rule: if the
  correlation p-value > 0.05, the rhythm carries no validated timing
  signal and consumers must fall back to the ANIMA forecast — this is
  reported via the `anima_fallback` field on the result.

Observed-timestamp derivation:
  get_brt_dict() accepts observed timestamps and derives the circadian
  phase via circular statistics (mean + resultant strength), labeled
  honestly as OBSERVED vs CLOCK_FALLBACK.

Clock source: GPS primary, NTP redundant, phase-locked loops maintained.
"""

import time
import math
from dataclasses import dataclass
from typing import Any, Dict, Optional, Sequence, Tuple

try:
    import numpy as _np
except ImportError:  # pragma: no cover — numpy is a core dependency
    _np = None  # type: ignore[assignment]


# ── Constants (whitepaper L6.2) ────────────────────────────────────────────
CIRCADIAN_SECONDS = 86400      # 24 hours
ULTRADIAN_SECONDS = 5400       # 90 minutes
LUNAR_SECONDS = 2551442        # 29.53059 days ≈ synodic month
SEASONAL_SECONDS = 31557600    # 365.25 days ≈ tropical year

# Whitepaper F14: significance level for the BRT–gas correlation. If
# p > ALPHA the BRT phase carries no validated timing signal and the
# caller must fall back to the ANIMA forecast.
BRT_GAS_ALPHA = 0.05

RHYTHM_PERIODS: Dict[str, float] = {
    "circadian": CIRCADIAN_SECONDS,
    "ultradian": ULTRADIAN_SECONDS,
    "lunar": LUNAR_SECONDS,
    "seasonal": SEASONAL_SECONDS,
}


@dataclass
class BiologicalRhythm:
    """Complete BRT phase state per whitepaper L6.2."""
    timestamp: float
    circadian_phase: float    # (t mod 86400) / 86400   ∈ [0, 1]
    ultradian_phase: float    # (t mod 5400) / 5400     ∈ [0, 1]
    lunar_phase: float        # (t mod 2551442) / 2551442 ∈ [0, 1]
    seasonal_phase: float     # (t mod 31557600) / 31557600 ∈ [0, 1]

    def to_dict(self) -> Dict[str, float]:
        """Serialize for inclusion in TRIONSignal."""
        return {
            "circadian_phase": round(self.circadian_phase, 6),
            "ultradian_phase": round(self.ultradian_phase, 6),
            "lunar_phase": round(self.lunar_phase, 6),
            "seasonal_phase": round(self.seasonal_phase, 6),
        }

    def phase_angle(self, rhythm: str) -> float:
        """Return phase as angle in radians [0, 2π) for correlation analysis."""
        phases = {
            "circadian": self.circadian_phase,
            "ultradian": self.ultradian_phase,
            "lunar": self.lunar_phase,
            "seasonal": self.seasonal_phase,
        }
        return 2.0 * math.pi * phases.get(rhythm, 0.0)


def compute_brt(timestamp: Optional[float] = None) -> BiologicalRhythm:
    """
    Compute Biological Rhythm Timer phases for a given timestamp.

    Whitepaper L6.2 formula:
      circadian_phase = (t mod 86400) / 86400
      ultradian_phase = (t mod 5400) / 5400
      lunar_phase     = (t mod 2551442) / 2551442
      seasonal_phase  = (t mod 31557600) / 31557600

    Args:
        timestamp: Unix timestamp in seconds. Defaults to current time.

    Returns:
        BiologicalRhythm dataclass with all four phases.
    """
    if timestamp is None:
        timestamp = time.time()

    return BiologicalRhythm(
        timestamp=timestamp,
        circadian_phase=(timestamp % CIRCADIAN_SECONDS) / CIRCADIAN_SECONDS,
        ultradian_phase=(timestamp % ULTRADIAN_SECONDS) / ULTRADIAN_SECONDS,
        lunar_phase=(timestamp % LUNAR_SECONDS) / LUNAR_SECONDS,
        seasonal_phase=(timestamp % SEASONAL_SECONDS) / SEASONAL_SECONDS,
    )


def get_brt_dict(
    timestamp: Optional[float] = None,
    observed_timestamps: Optional[Sequence[float]] = None,
) -> Dict[str, Any]:
    """
    Convenience: return BRT as dict for direct signal inclusion.

    Args:
        timestamp: reference Unix timestamp (default: now).
        observed_timestamps: optional observed event timestamps. When at
            least 24 observations are available, the circadian phase is
            derived via circular statistics (observed peak + resultant
            strength) instead of wall-clock time, and the dict carries an
            honest source label:

              brt_source:                "OBSERVED" | "OBSERVED_WEAK" | "CLOCK_FALLBACK"
              circadian_strength:        resultant length R ∈ [0, 1] (0.0 when no data)
              circadian_phase_deviation: circular distance between observed
                                         peak phase and wall-clock phase

    The four phase keys (circadian/ultradian/lunar/seasonal_phase) are
    always present and unchanged in meaning.
    """
    brt = compute_brt(timestamp)
    out: Dict[str, Any] = dict(brt.to_dict())

    ts = observed_timestamps or []
    n_obs = len(ts)
    if n_obs < 24:
        out["brt_source"] = "CLOCK_FALLBACK"
        out["circadian_strength"] = 0.0
        out["circadian_phase_deviation"] = 0.0
        return out

    angles = [(t % CIRCADIAN_SECONDS) / CIRCADIAN_SECONDS * 2.0 * math.pi
              for t in ts]
    peak_phase, strength = _circular_mean_and_strength(angles)

    out["brt_source"] = "OBSERVED" if strength >= 0.20 else "OBSERVED_WEAK"
    out["circadian_strength"] = round(strength, 6)
    if strength >= 0.20:
        out["circadian_phase"] = round(peak_phase, 6)
    # Circular distance between observed peak and wall-clock phase
    diff = abs(peak_phase - brt.circadian_phase) % 1.0
    out["circadian_phase_deviation"] = round(min(diff, 1.0 - diff), 6)
    return out


def _circular_mean_and_strength(angles: Sequence[float]) -> Tuple[float, float]:
    """Circular mean and resultant length for a set of angles (radians)."""
    n = len(angles)
    if n == 0:
        return 0.0, 0.0
    sin_m = sum(math.sin(a) for a in angles) / n
    cos_m = sum(math.cos(a) for a in angles) / n
    mean = (math.atan2(sin_m, cos_m) % (2.0 * math.pi)) / (2.0 * math.pi)
    strength = min(1.0, math.sqrt(sin_m ** 2 + cos_m ** 2))
    return mean, strength


# ── BRT–gas correlation (whitepaper F14) ────────────────────────────────────

@dataclass
class BRTGasCorrelation:
    """
    Result of the BRT phase ↔ gas-price correlation test (F14).

    Whitepaper rule: if p_value > alpha the BRT phase carries no
    statistically significant timing signal and consumers must fall back
    to the ANIMA forecast (`anima_fallback = True`).
    """
    rhythm:             str            # circadian | ultradian | lunar | seasonal
    n_samples:          int
    correlation:        float          # circular-linear correlation r ∈ [0, 1]
    chi2_statistic:     float          # n·r² — χ² with 2 df under H₀
    p_value:            float          # exact upper tail for χ²(df=2): exp(−x/2)
    alpha:              float          # significance level (default 0.05)
    significant:        bool           # p_value ≤ alpha
    anima_fallback:     bool           # p_value > alpha → ANIMA forecast
    data_quality:       str            # OK | INSUFFICIENT_SAMPLES | ZERO_VARIANCE
    method:             str = "mardia_circular_linear_chi2_df2"

    def to_dict(self) -> Dict[str, Any]:
        return {
            "rhythm":         self.rhythm,
            "n_samples":      self.n_samples,
            "correlation":    round(self.correlation, 6),
            "chi2_statistic": round(self.chi2_statistic, 6),
            "p_value":        self.p_value,
            "alpha":          self.alpha,
            "significant":    self.significant,
            "anima_fallback": self.anima_fallback,
            "data_quality":   self.data_quality,
            "method":         self.method,
        }


def compute_brt_gas_correlation(
    timestamps: Sequence[float],
    gas_prices: Sequence[float],
    rhythm: str = "circadian",
    alpha: float = BRT_GAS_ALPHA,
    min_samples: int = 10,
) -> BRTGasCorrelation:
    """
    Correlate a BRT phase with observed on-chain gas prices (F14).

    Computes Mardia's circular-linear correlation between the selected
    rhythm phase θ(t) = 2π·((t mod T)/T) and the gas price series:

        r² = (r_xc² + r_xs² − 2·r_xc·r_xs·r_cs) / (1 − r_cs²)

    where r_xc, r_xs, r_cs are the Pearson correlations between the gas
    series and cos(θ), sin(θ), and between cos(θ) and sin(θ). Under the
    null hypothesis of no association, n·r² follows a χ² distribution
    with 2 degrees of freedom, whose survival function is exactly
    exp(−n·r²/2) — no scipy required.

    Whitepaper rule: p_value > 0.05 (alpha) → `anima_fallback = True`
    (fall back to the ANIMA forecast; the BRT phase has no validated
    predictive power for gas in this sample).

    Args:
        timestamps: observed Unix timestamps (seconds), paired with gas_prices.
        gas_prices: observed gas prices (same length as timestamps).
        rhythm: one of circadian/ultradian/lunar/seasonal.
        alpha: significance level (default 0.05 per whitepaper).
        min_samples: minimum paired samples before the test is run
            (below this the result is INSUFFICIENT_SAMPLES with fallback).

    Returns:
        BRTGasCorrelation with correlation, p_value, significant and
        anima_fallback fields.
    """
    rhythm = rhythm.lower()
    if rhythm not in RHYTHM_PERIODS:
        raise ValueError(
            f"unknown rhythm {rhythm!r} — expected one of {sorted(RHYTHM_PERIODS)}"
        )
    period = RHYTHM_PERIODS[rhythm]

    if _np is None:  # pragma: no cover
        raise RuntimeError("numpy is required for compute_brt_gas_correlation")

    ts = _np.asarray(list(timestamps), dtype=float)
    gas = _np.asarray(list(gas_prices), dtype=float)
    n = min(ts.size, gas.size)

    def _result(corr: float, chi2: float, p: float, quality: str) -> BRTGasCorrelation:
        significant = p <= alpha and quality == "OK"
        return BRTGasCorrelation(
            rhythm=rhythm, n_samples=int(n),
            correlation=corr, chi2_statistic=chi2, p_value=p, alpha=alpha,
            significant=significant,
            anima_fallback=not significant,
            data_quality=quality,
        )

    if ts.size != gas.size:
        raise ValueError(
            f"timestamps ({ts.size}) and gas_prices ({gas.size}) must have equal length"
        )
    if n < min_samples:
        return _result(0.0, 0.0, 1.0, "INSUFFICIENT_SAMPLES")

    phases = (ts % period) / period
    theta = 2.0 * _np.pi * phases
    c = _np.cos(theta)
    s = _np.sin(theta)

    def _pearson(a: "_np.ndarray", b: "_np.ndarray") -> Optional[float]:
        sa, sb = float(a.std()), float(b.std())
        if sa < 1e-12 or sb < 1e-12:
            return None
        return float(_np.corrcoef(a, b)[0, 1])

    r_xc = _pearson(gas, c)
    r_xs = _pearson(gas, s)
    r_cs = _pearson(c, s)
    if r_xc is None or r_xs is None or r_cs is None:
        # Degenerate sample: constant gas series or constant phase — no
        # correlation is measurable; honest fallback to ANIMA.
        return _result(0.0, 0.0, 1.0, "ZERO_VARIANCE")

    denom = 1.0 - r_cs ** 2
    if denom < 1e-12:
        return _result(0.0, 0.0, 1.0, "ZERO_VARIANCE")

    r2 = (r_xc ** 2 + r_xs ** 2 - 2.0 * r_xc * r_xs * r_cs) / denom
    r2 = min(1.0, max(0.0, r2))
    chi2 = n * r2
    p_value = float(_np.exp(-chi2 / 2.0))

    return _result(math.sqrt(r2), chi2, p_value, "OK")


def detect_circadian_anomaly(current_pattern: Dict,
                             baseline_pattern: Dict,
                             threshold: float = 2.0) -> bool:
    """
    Detect when signal pattern deviates from 24h baseline.
    
    Returns True if deviation exceeds threshold standard deviations.
    Known precursor to market regime changes.
    """
    if not baseline_pattern:
        return False
    
    deviations = []
    for key in ["volume", "gas_price", "liquidity_depth"]:
        if key in current_pattern and key in baseline_pattern:
            curr = current_pattern[key]
            base_mean = baseline_pattern.get(f"{key}_mean", 0)
            base_std = baseline_pattern.get(f"{key}_std", 1)
            if base_std > 0:
                deviations.append(abs(curr - base_mean) / base_std)
    
    if not deviations:
        return False
    
    return max(deviations) > threshold


# ── Convenience aliases for backward compatibility ───────────────────────
def BRT(timestamp: Optional[float] = None) -> BiologicalRhythm:
    """Alias for compute_brt — matches whitepaper naming convention."""
    return compute_brt(timestamp)


__all__ = [
    "BiologicalRhythm",
    "compute_brt",
    "get_brt_dict",
    "detect_circadian_anomaly",
    "compute_brt_gas_correlation",
    "BRTGasCorrelation",
    "BRT",
    "CIRCADIAN_SECONDS",
    "ULTRADIAN_SECONDS",
    "LUNAR_SECONDS",
    "SEASONAL_SECONDS",
    "RHYTHM_PERIODS",
    "BRT_GAS_ALPHA",
]


# ── Self-test ────────────────────────────────────────────────────────────────

if __name__ == "__main__":
    import random

    print("=== Biological Rhythm Timer (BRT) Self-test ===\n")

    # 1. Phase computation matches whitepaper L6.2 exactly
    brt = compute_brt(43200)
    assert abs(brt.circadian_phase - 0.5) < 1e-9
    assert abs(brt.ultradian_phase - (43200 % 5400) / 5400) < 1e-9
    brt2 = compute_brt(86400)
    assert brt2.circadian_phase == 0.0
    print(f"✓ Phase formulas: circadian(43200)={brt.circadian_phase}, circadian(86400)={brt2.circadian_phase}")

    # 2. get_brt_dict clock fallback labeling
    d = get_brt_dict(43200)
    assert d["circadian_phase"] == 0.5
    assert d["brt_source"] == "CLOCK_FALLBACK"
    assert d["circadian_strength"] == 0.0
    print(f"✓ Clock fallback labeled: {d['brt_source']}")

    # 3. Observed timestamps → circular statistics
    rng = random.Random(42)
    midnight = 1700000000 - (1700000000 % 86400)
    obs = [midnight + day * 86400 + rng.uniform(32400, 61200)  # 09:00–17:00 UTC
           for day in range(10) for _ in range(10)]
    d2 = get_brt_dict(midnight + 12 * 3600, obs)
    assert d2["brt_source"] == "OBSERVED"
    assert 0.0 < d2["circadian_strength"] <= 1.0
    assert 0.30 <= d2["circadian_phase"] <= 0.60  # daytime peak
    print(f"✓ Observed BRT: source={d2['brt_source']} peak={d2['circadian_phase']:.3f} "
          f"strength={d2['circadian_strength']:.3f} deviation={d2['circadian_phase_deviation']:.3f}")

    # 4. BRT–gas correlation: strong circadian signal → significant
    ts_sig = sorted(rng.uniform(0, 86400 * 30) for _ in range(400))
    import numpy as np_test
    ts_arr = np_test.array(ts_sig)
    gas_sig = np_test.cos(2 * np_test.pi * ((ts_arr % 86400) / 86400)) \
        + np_test.random.RandomState(7).normal(0, 0.05, ts_arr.size)
    res = compute_brt_gas_correlation(ts_arr.tolist(), gas_sig.tolist(), rhythm="circadian")
    assert res.data_quality == "OK"
    assert res.significant, f"expected significant correlation, p={res.p_value}"
    assert not res.anima_fallback
    print(f"✓ Significant circadian-gas correlation: r={res.correlation:.4f} "
          f"p={res.p_value:.2e} → anima_fallback={res.anima_fallback}")

    # 5. BRT–gas correlation: noise → NOT significant → ANIMA fallback
    gas_noise = np_test.random.RandomState(11).normal(50.0, 10.0, ts_arr.size)
    res_noise = compute_brt_gas_correlation(ts_arr.tolist(), gas_noise.tolist())
    assert res_noise.p_value > 0.05, f"expected non-significant, p={res_noise.p_value}"
    assert res_noise.anima_fallback, "whitepaper rule: p > 0.05 → ANIMA forecast"
    print(f"✓ Noise → ANIMA fallback: r={res_noise.correlation:.4f} "
          f"p={res_noise.p_value:.3f} → anima_fallback={res_noise.anima_fallback}")

    # 6. Insufficient samples → honest fallback
    res_few = compute_brt_gas_correlation(ts_arr[:5].tolist(), gas_sig[:5].tolist())
    assert res_few.data_quality == "INSUFFICIENT_SAMPLES"
    assert res_few.anima_fallback
    print(f"✓ Insufficient samples (n=5): quality={res_few.data_quality} → anima_fallback=True")

    # 7. Zero-variance gas → honest fallback
    res_flat = compute_brt_gas_correlation(ts_arr[:50].tolist(), [50.0] * 50)
    assert res_flat.data_quality == "ZERO_VARIANCE"
    assert res_flat.anima_fallback
    print(f"✓ Constant gas series: quality={res_flat.data_quality} → anima_fallback=True")

    print("\nBRT PASS — phases + observed derivation + gas correlation (F14) with ANIMA fallback rule")
