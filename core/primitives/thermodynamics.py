"""
TRION Protocol — L9.2 Information Conservation Law

I_total(t) = I_total(t-1) + ΔI_consumed(t) - ΔI_transformed(t)

I_TRION(t) = BH_generated + A_absorbed - S_emitted - E_lost

Conservation principle:
    Information is neither created nor destroyed in the Akashic Index.
    It is only transformed from one form to another.
    Every BH generated = information absorbed from the environment.
    Every signal emitted = information transformed to a consumer form.
    Information "lost" to entropy is tracked, not ignored.

Signal Selection Principle (L0.5):
    Selected iff dI_gained / dS_entropy_cost > θ_selection

This is the thermodynamic basis for TRION's signal selectivity.
Not every observed pattern becomes a signal — only those where
the information gain exceeds the entropy cost of emission.

The Information Conservation Law ensures TRION cannot "create" information
from nothing — it can only transform what exists in behavioral history.
This is the formal bound on TRION's predictive capability.

Author: TRION Protocol — Originator: Hudu Yusuf (Analys)
License: CC0
"""

from __future__ import annotations
import math
from dataclasses import dataclass
from typing import List, Optional


THETA_SELECTION_DEFAULT = 1.0    # Signal selection threshold (dimensionless ratio)


@dataclass
class InformationState:
    """
    I_TRION(t) tracking.
    All components in natural information units (nats or bits — consistent within session).
    """
    timestamp:          float
    bh_generated:       float   # Information from behavioral hashes generated
    a_absorbed:         float   # Information absorbed from environment (ANIMA, sensors)
    s_emitted:          float   # Information emitted as signals to consumers
    e_lost:             float   # Information lost to entropy (non-recoverable)
    i_total:            float   # I_total(t) = I_total(t-1) + ΔI_consumed - ΔI_transformed


@dataclass
class ConservationCheckResult:
    """
    Verify information conservation holds: I_total(t) - I_total(t-1) = ΔI_net
    """
    timestamp:          float
    i_current:          float
    i_previous:         float
    delta_consumed:     float   # BH_generated + A_absorbed
    delta_transformed:  float   # S_emitted + E_lost
    delta_net:          float   # delta_consumed - delta_transformed
    expected_current:   float   # i_previous + delta_net
    conserved:          bool    # |i_current - expected_current| < tolerance
    tolerance:          float
    deviation:          float


@dataclass
class SignalSelectionResult:
    """
    L0.5: Signal selection based on information gain vs entropy cost.
    Signal selected iff dI_gained / dS_entropy_cost > θ_selection
    """
    signal_id:          str
    i_gained:           float   # Information gained from this signal
    s_entropy_cost:     float   # Entropy cost of emitting this signal
    ratio:              float   # dI_gained / dS_entropy_cost
    theta:              float   # Selection threshold
    selected:           bool    # True iff ratio > theta
    reason:             str


def compute_information_state(
    previous:      Optional[InformationState],
    bh_generated:  float,
    a_absorbed:    float,
    s_emitted:     float,
    e_lost:        float,
    timestamp:     float,
) -> InformationState:
    """
    I_TRION(t) = BH_generated + A_absorbed - S_emitted - E_lost
    I_total(t) = I_total(t-1) + ΔI_consumed(t) - ΔI_transformed(t)

    ΔI_consumed    = BH_generated + A_absorbed  (information taken in)
    ΔI_transformed = S_emitted + E_lost         (information put out)
    """
    delta_consumed    = bh_generated + a_absorbed
    delta_transformed = s_emitted + e_lost

    i_previous = previous.i_total if previous else 0.0
    i_total    = i_previous + delta_consumed - delta_transformed

    return InformationState(
        timestamp      = timestamp,
        bh_generated   = bh_generated,
        a_absorbed     = a_absorbed,
        s_emitted      = s_emitted,
        e_lost         = e_lost,
        i_total        = max(0.0, i_total),  # Cannot go below 0 — conservation floor
    )


def verify_conservation(
    current:    InformationState,
    previous:   InformationState,
    tolerance:  float = 1e-6,
) -> ConservationCheckResult:
    """
    Verify conservation law holds between two consecutive states.
    Deviation beyond tolerance indicates a conservation violation
    (data loss, hash collision, or implementation error).
    """
    delta_consumed    = current.bh_generated + current.a_absorbed
    delta_transformed = current.s_emitted    + current.e_lost
    delta_net         = delta_consumed - delta_transformed

    expected_current  = previous.i_total + delta_net
    deviation         = abs(current.i_total - expected_current)
    conserved         = deviation <= tolerance

    return ConservationCheckResult(
        timestamp        = current.timestamp,
        i_current        = current.i_total,
        i_previous       = previous.i_total,
        delta_consumed   = delta_consumed,
        delta_transformed = delta_transformed,
        delta_net        = delta_net,
        expected_current = expected_current,
        conserved        = conserved,
        tolerance        = tolerance,
        deviation        = deviation,
    )


def apply_signal_selection(
    signal_id:         str,
    i_gained:          float,
    s_entropy_cost:    float,
    theta:             float = THETA_SELECTION_DEFAULT,
) -> SignalSelectionResult:
    """
    Signal selected iff dI_gained / dS_entropy_cost > θ_selection

    i_gained      = Shannon information gained by emitting this signal
                    (measured by reduction in consumer uncertainty)
    s_entropy_cost = Entropy cost of signal emission
                    (bits transmitted, storage cost, observer effect risk)
    theta         = Selection threshold (default 1.0 — must gain more than it costs)

    When ratio ≤ θ: signal SUPPRESSED (not worth the entropy cost)
    When ratio > θ: signal EMITTED
    """
    if s_entropy_cost <= 0:
        # Zero entropy cost → always select (pure information gain)
        ratio = float('inf')
        selected = i_gained > 0
        reason = "zero_cost_signal"
    else:
        ratio = i_gained / s_entropy_cost
        selected = ratio > theta
        if selected:
            reason = f"ratio={ratio:.4f} > theta={theta:.4f} → EMITTED"
        else:
            reason = f"ratio={ratio:.4f} <= theta={theta:.4f} → SUPPRESSED"

    return SignalSelectionResult(
        signal_id       = signal_id,
        i_gained        = i_gained,
        s_entropy_cost  = s_entropy_cost,
        ratio           = ratio,
        theta           = theta,
        selected        = selected,
        reason          = reason,
    )


def compute_information_gain(
    p_prior:    List[float],   # Prior probability distribution over outcomes
    p_posterior: List[float],  # Posterior after receiving signal
) -> float:
    """
    Information gained by a signal = KL(posterior || prior)
    = Σ P_post(i) · log(P_post(i) / P_prior(i))

    This measures how much the signal reduces uncertainty.
    High information gain = signal is valuable.
    Low information gain = signal adds nothing new.
    """
    n = min(len(p_prior), len(p_posterior))
    if n == 0:
        return 0.0

    eps = 1e-10
    sum_prior = sum(p_prior[:n]) or 1.0
    sum_post  = sum(p_posterior[:n]) or 1.0

    kl = 0.0
    for i in range(n):
        prior = max(eps, p_prior[i] / sum_prior)
        post  = max(eps, p_posterior[i] / sum_post)
        kl += post * math.log(post / prior)

    return max(0.0, kl)


def compute_entropy_cost(
    signal_bits:       float,   # Size of signal in bits
    observer_effect:   float,   # OE_factor [0, 1] — observer effect risk
    broadcast_factor:  float,   # How widely signal is broadcast [0, 1]
) -> float:
    """
    S_entropy_cost = signal_bits × (1 + observer_effect × broadcast_factor)

    Observer effect multiplies cost: broadcasting a prediction creates
    behavioral changes that consume additional entropy budget.
    """
    return signal_bits * (1.0 + observer_effect * broadcast_factor)


class AkashicConservationLedger:
    """
    Running ledger of information conservation for the Akashic Index.
    Every append to the Akashic Index must be recorded here.
    """

    def __init__(self):
        self.states: List[InformationState] = []
        self.violations: List[ConservationCheckResult] = []

    def record_state(
        self,
        timestamp:     float,
        bh_generated:  float,
        a_absorbed:    float,
        s_emitted:     float,
        e_lost:        float,
    ) -> ConservationCheckResult:
        """Record a new information state and verify conservation."""
        previous = self.states[-1] if self.states else None
        new_state = compute_information_state(
            previous, bh_generated, a_absorbed, s_emitted, e_lost, timestamp
        )
        self.states.append(new_state)

        if previous:
            result = verify_conservation(new_state, previous)
            if not result.conserved:
                self.violations.append(result)
            return result

        return ConservationCheckResult(
            timestamp=timestamp, i_current=new_state.i_total, i_previous=0.0,
            delta_consumed=bh_generated + a_absorbed,
            delta_transformed=s_emitted + e_lost,
            delta_net=(bh_generated + a_absorbed) - (s_emitted + e_lost),
            expected_current=new_state.i_total,
            conserved=True, tolerance=1e-6, deviation=0.0,
        )

    @property
    def total_information(self) -> float:
        return self.states[-1].i_total if self.states else 0.0

    @property
    def has_violations(self) -> bool:
        return len(self.violations) > 0


if __name__ == "__main__":
    import time

    # Conservation ledger test
    ledger = AkashicConservationLedger()
    now = time.time()

    # Block 1: ingest 100 BH + 50 ANIMA, emit 30 signals + 5 lost
    r1 = ledger.record_state(now, bh_generated=100, a_absorbed=50, s_emitted=30, e_lost=5)
    print(f"Block 1: I_total={ledger.total_information:.2f} conserved={r1.conserved}")
    assert r1.conserved

    # Block 2: ingest 80 BH + 40 ANIMA, emit 60 signals + 3 lost
    r2 = ledger.record_state(now + 12, bh_generated=80, a_absorbed=40, s_emitted=60, e_lost=3)
    print(f"Block 2: I_total={ledger.total_information:.2f} conserved={r2.conserved}")
    assert r2.conserved
    assert not ledger.has_violations

    # Signal selection test
    sel_good = apply_signal_selection("manipulation_alert_001", i_gained=2.5, s_entropy_cost=1.0)
    sel_bad  = apply_signal_selection("noise_signal_001",       i_gained=0.3, s_entropy_cost=1.0)
    print(f"Good signal: selected={sel_good.selected} ratio={sel_good.ratio:.4f}")
    print(f"Noise signal: selected={sel_bad.selected} ratio={sel_bad.ratio:.4f}")
    assert sel_good.selected
    assert not sel_bad.selected

    # Information gain test
    prior     = [0.25, 0.25, 0.25, 0.25]
    posterior = [0.70, 0.15, 0.10, 0.05]
    ig = compute_information_gain(prior, posterior)
    print(f"Information gain from signal: {ig:.4f} nats")
    assert ig > 0

    print("L9.2 Information Conservation Law: PASS")
