"""
Biological Capital Index (BC) — TRION L7
BC(ecosystem, t) = Flow(e,t) * Resilience(e,t) * Uniqueness(e,t) * Interdependence(e,t)
"""
from dataclasses import dataclass

BC_WARNING_THRESHOLD = -0.15


@dataclass
class EcosystemMetrics:
    ecosystem_id:   str
    flow:           float
    resilience:     float
    uniqueness:     float
    interdependence: float
    iucn_calibrated: bool = False


def compute_bc(metrics: EcosystemMetrics) -> dict:
    bc = (metrics.flow * metrics.resilience *
          metrics.uniqueness * metrics.interdependence)
    return {
        "bc_score":      round(bc, 6),
        "flow":          metrics.flow,
        "resilience":    metrics.resilience,
        "uniqueness":    metrics.uniqueness,
        "interdependence": metrics.interdependence,
        "iucn_calibrated": metrics.iucn_calibrated,
        "source_id":     f"bc_{metrics.ecosystem_id}",
        "warning":       not metrics.iucn_calibrated,
    }


@dataclass
class BiologicalRhythmTimer:
    CIRCADIAN_HOURS  = 24.0
    ULTRADIAN_HOURS  = 1.5
    LUNAR_DAYS       = 29.5
    SEASONAL_DAYS    = 365.25

    def current_phase(self, unix_timestamp: float) -> dict:
        hours = unix_timestamp / 3600.0
        days  = unix_timestamp / 86400.0
        return {
            "circadian_phase":  (hours % self.CIRCADIAN_HOURS) / self.CIRCADIAN_HOURS,
            "ultradian_phase":  (hours % self.ULTRADIAN_HOURS) / self.ULTRADIAN_HOURS,
            "lunar_phase":      (days  % self.LUNAR_DAYS)      / self.LUNAR_DAYS,
            "seasonal_phase":   (days  % self.SEASONAL_DAYS)   / self.SEASONAL_DAYS,
        }
