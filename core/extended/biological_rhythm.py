"""
L6.2 — Biological Rhythm Timer (BRT)

Natural rhythm correlations tracked in Akashic Index:
  - Circadian anomaly: signal pattern deviates from 24h baseline
  - Lunar anomaly: liquidity pattern shifts correlating with lunar phase
  - Seasonal anomaly: behavioral rhythm shifts at quarter boundaries

BRT is included in every TRIONSignal object as biological_time field.
Enables ANIMA to detect when human behavioral patterns shift relative to
natural rhythms — a known precursor to market regime changes.

Clock source: GPS primary, NTP redundant, phase-locked loops maintained.
"""

import time
import math
from dataclasses import dataclass
from typing import Dict, Optional


# ── Constants (whitepaper L6.2) ────────────────────────────────────────────
CIRCADIAN_SECONDS = 86400      # 24 hours
ULTRADIAN_SECONDS = 5400       # 90 minutes
LUNAR_SECONDS = 2551442        # 29.53059 days ≈ synodic month
SEASONAL_SECONDS = 31557600    # 365.25 days ≈ tropical year


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


def get_brt_dict(timestamp: Optional[float] = None) -> Dict[str, float]:
    """Convenience: return BRT as dict for direct signal inclusion."""
    return compute_brt(timestamp).to_dict()


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
    "BRT",
    "CIRCADIAN_SECONDS",
    "ULTRADIAN_SECONDS",
    "LUNAR_SECONDS",
    "SEASONAL_SECONDS",
]
