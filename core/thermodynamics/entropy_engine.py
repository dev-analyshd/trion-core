"""
TRION Protocol — L0.4 / L9.2: Behavioral Entropy Engine
=========================================================
Whitepaper L0.4 defines the Behavioral Entropy (BE) as a measure of
informational disorder in an entity's transaction sequence.  L9.2 integrates
entropy into the Economic Moat as the "thermodynamic floor" of the coherence
score: when entropy is pathologically low (artificially ordered behavior) or
pathologically high (random noise), the coherence score is penalized.

Key quantities:
  H(t)     — Shannon entropy of the event-type distribution (bits)
  H_norm   — normalized entropy H / H_max (0 = degenerate, 1 = fully random)
  ΔH(t)    — entropy velocity: rate of change over a rolling window
  S_thermo — thermodynamic entropy score ∈ [0, 1] (complement of disorder)
  Φ_ent    — entropy penalty factor applied to raw coherence score C(t)

Entropy in context:
  - Too LOW  (H_norm < 0.15): entity behavior is suspiciously uniform
              (e.g. wash trading, scripted bot) → Φ_ent < 1 (penalty)
  - Healthy  (0.15 ≤ H_norm ≤ 0.85): genuine behavioural diversity → Φ_ent = 1
  - Too HIGH (H_norm > 0.85): behavior is purely random, no identifiable pattern
              → Φ_ent < 1 (penalty — no meaningful signal can be extracted)

This module is referenced by:
  - L0.4 formal verification theorems (Haskell)
  - L9.2 moat engine thermodynamic floor
  - The FAISS ANIMA archetype clustering pipeline

Author: TRION Protocol — Hudu Yusuf (Analys)
License: CC0
"""

from __future__ import annotations

import math
import time
from collections import deque
from dataclasses import dataclass, field
from typing import Dict, List, Optional, Sequence, Tuple


# ── Constants ──────────────────────────────────────────────────────────────────

N_EVENT_TYPES: int   = 20          # canonical EventType count (L0.1)
H_MAX: float         = math.log2(N_EVENT_TYPES)   # ≈ 4.322 bits

# Healthy entropy band (normalized)
H_NORM_LOW:  float = 0.15          # below this: suspiciously uniform
H_NORM_HIGH: float = 0.85          # above this: suspiciously random

# Penalty steepness outside the healthy band (quadratic shape)
ENTROPY_PENALTY_K: float = 2.0

# Rolling window for entropy velocity ΔH(t)
ENTROPY_VELOCITY_WINDOW: int = 10  # number of snapshots


# ── Data Model ────────────────────────────────────────────────────────────────

@dataclass
class EntropySnapshot:
    """A single entropy measurement at one point in time."""
    timestamp:      float
    h_bits:         float     # raw Shannon entropy in bits
    h_norm:         float     # normalized 0–1
    event_counts:   Dict[int, int]   # event_type_id → count
    total_events:   int
    phi_entropy:    float     # penalty factor ∈ (0, 1]
    s_thermo:       float     # thermodynamic entropy score ∈ [0, 1]
    regime:         str       # "DEGENERATE" | "HEALTHY" | "RANDOM" | "EMPTY"


@dataclass
class EntropyState:
    """Accumulated entropy state for one entity."""
    entity_id:    str
    snapshots:    List[EntropySnapshot] = field(default_factory=list)
    event_counts: Dict[int, int]        = field(default_factory=dict)
    total_events: int                   = 0
    _velocity_q:  deque                 = field(default_factory=lambda: deque(maxlen=ENTROPY_VELOCITY_WINDOW))

    def add_event(self, event_type_id: int) -> None:
        self.event_counts[event_type_id] = self.event_counts.get(event_type_id, 0) + 1
        self.total_events += 1


# ── Core functions ────────────────────────────────────────────────────────────

def shannon_entropy(counts: Dict[int, int]) -> Tuple[float, float]:
    """
    Compute Shannon entropy H(X) = -Σ p_i log₂(p_i) from event type counts.

    Returns:
      h_bits — entropy in bits
      h_norm — entropy normalized to [0, 1] by H_max = log₂(N_EVENT_TYPES)
    """
    total = sum(counts.values())
    if total == 0:
        return 0.0, 0.0

    h_bits = 0.0
    for count in counts.values():
        if count > 0:
            p = count / total
            h_bits -= p * math.log2(p)

    h_norm = h_bits / H_MAX if H_MAX > 0 else 0.0
    return h_bits, min(1.0, h_norm)


def entropy_regime(h_norm: float, total_events: int = 0) -> str:
    """
    Classify entropy into behavioral regime.
    EMPTY      : no events recorded at all (not yet observed)
    DEGENERATE : h_norm < H_NORM_LOW — suspiciously uniform (bot-like, e.g. only SWAPs)
    HEALTHY    : H_NORM_LOW ≤ h_norm ≤ H_NORM_HIGH — genuine behavioral diversity
    RANDOM     : h_norm > H_NORM_HIGH — no discernible pattern

    Note: an entity that uses ONLY one event type has H=0 (not "empty" — it has events).
    We distinguish "no events" from "zero-entropy" by checking total_events.
    """
    if total_events == 0:
        return "EMPTY"
    if h_norm < H_NORM_LOW:
        return "DEGENERATE"
    if h_norm > H_NORM_HIGH:
        return "RANDOM"
    return "HEALTHY"


def entropy_penalty(h_norm: float, total_events: int = 0) -> float:
    """
    Φ_ent — entropy penalty factor ∈ (0, 1].

    HEALTHY range: Φ_ent = 1.0 (no penalty).
    Outside the healthy band, penalty grows quadratically:

      Below H_NORM_LOW:  Φ_ent = 1 - K · ((H_NORM_LOW - h_norm) / H_NORM_LOW)²
      Above H_NORM_HIGH: Φ_ent = 1 - K · ((h_norm - H_NORM_HIGH) / (1 - H_NORM_HIGH))²

    Clamped to (0.05, 1.0] — never fully zeroes coherence on entropy alone.
    Empty entity (no events at all): returns 0.10 floor (unobserved, not degenerate).
    """
    if total_events == 0:
        return 0.10   # no events yet — entity is unobserved; apply minimal floor

    if H_NORM_LOW <= h_norm <= H_NORM_HIGH:
        return 1.0

    if h_norm < H_NORM_LOW:
        deficit = (H_NORM_LOW - h_norm) / H_NORM_LOW
        return max(0.05, 1.0 - ENTROPY_PENALTY_K * deficit ** 2)

    # h_norm > H_NORM_HIGH
    excess  = (h_norm - H_NORM_HIGH) / max(1.0 - H_NORM_HIGH, 1e-9)
    return max(0.05, 1.0 - ENTROPY_PENALTY_K * excess ** 2)


def thermodynamic_entropy_score(h_norm: float) -> float:
    """
    S_thermo ∈ [0, 1] — thermodynamic entropy score for integration with the
    moat engine (L9.2).  Peaks at h_norm = 0.50 (maximum useful information):

      S_thermo = 1 - 4 · (h_norm - 0.5)²

    This is a concave parabola symmetric around h_norm = 0.5 that equals 1.0
    at the midpoint and 0.0 at the extremes 0 and 1.
    """
    return max(0.0, 1.0 - 4.0 * (h_norm - 0.5) ** 2)


def entropy_velocity(snapshots: Sequence[EntropySnapshot]) -> float:
    """
    ΔH(t) — rate of change of normalized entropy over recent snapshots.

    Positive: entropy is increasing (entity diversifying behavior).
    Negative: entropy is decreasing (entity concentrating into fewer event types).
    Zero:     stable.

    Returns the simple finite-difference slope (h_norm_last - h_norm_first) / n
    over the supplied window.  Returns 0.0 if fewer than 2 snapshots.
    """
    if len(snapshots) < 2:
        return 0.0
    h_values = [s.h_norm for s in snapshots]
    return (h_values[-1] - h_values[0]) / max(len(h_values) - 1, 1)


# ── Entity Entropy Engine ─────────────────────────────────────────────────────

class BehavioralEntropyEngine:
    """
    Per-entity behavioral entropy tracker.

    Tracks a rolling event-type distribution for each entity and computes
    entropy snapshots on demand.  Designed to integrate with:
      - CoherenceEngine: supplies Φ_ent to multiply against raw C(t)
      - MoatEngine L9.2: supplies S_thermo as thermodynamic floor
      - FAISS ANIMA: supplies entropy features for archetype clustering
    """

    def __init__(self):
        self._states: Dict[str, EntropyState] = {}

    def _get_or_create(self, entity_id: str) -> EntropyState:
        if entity_id not in self._states:
            self._states[entity_id] = EntropyState(entity_id=entity_id)
        return self._states[entity_id]

    def record_event(self, entity_id: str, event_type_id: int) -> None:
        """Record a single behavioral event for the entity."""
        state = self._get_or_create(entity_id)
        if not (0 <= event_type_id < N_EVENT_TYPES):
            raise ValueError(
                f"event_type_id {event_type_id} out of range [0, {N_EVENT_TYPES})"
            )
        state.add_event(event_type_id)

    def record_events_batch(self, entity_id: str,
                            event_type_ids: Sequence[int]) -> None:
        """Record a batch of behavioral events for the entity."""
        state = self._get_or_create(entity_id)
        for eid in event_type_ids:
            if not (0 <= eid < N_EVENT_TYPES):
                raise ValueError(f"event_type_id {eid} out of range")
            state.add_event(eid)

    def snapshot(self, entity_id: str) -> EntropySnapshot:
        """
        Compute and store an entropy snapshot for the entity at this moment.
        Returns the snapshot.
        """
        state = self._get_or_create(entity_id)
        counts = dict(state.event_counts)

        total_ev = sum(counts.values())
        h_bits, h_norm = shannon_entropy(counts)
        regime   = entropy_regime(h_norm, total_ev)
        phi_ent  = entropy_penalty(h_norm, total_ev)
        s_thermo = thermodynamic_entropy_score(h_norm)

        snap = EntropySnapshot(
            timestamp=time.time(),
            h_bits=round(h_bits, 6),
            h_norm=round(h_norm, 6),
            event_counts=counts,
            total_events=total_ev,
            phi_entropy=round(phi_ent, 6),
            s_thermo=round(s_thermo, 6),
            regime=regime,
        )
        state.snapshots.append(snap)
        state._velocity_q.append(snap)
        return snap

    def get_phi_entropy(self, entity_id: str) -> float:
        """
        Return the current Φ_ent for the entity.
        Returns 1.0 (no penalty) if no events have been recorded yet.
        """
        state = self._states.get(entity_id)
        if state is None or state.total_events == 0:
            return 1.0
        _, h_norm = shannon_entropy(state.event_counts)
        return entropy_penalty(h_norm, state.total_events)

    def get_s_thermo(self, entity_id: str) -> float:
        """Return the current S_thermo thermodynamic score for the entity."""
        state = self._states.get(entity_id)
        if state is None or state.total_events == 0:
            return 0.0  # unobserved entity has no thermodynamic score
        _, h_norm = shannon_entropy(state.event_counts)
        return thermodynamic_entropy_score(h_norm)

    def get_velocity(self, entity_id: str) -> float:
        """Return the ΔH(t) entropy velocity over the recent snapshot window."""
        state = self._states.get(entity_id)
        if state is None:
            return 0.0
        return entropy_velocity(list(state._velocity_q))

    def full_report(self, entity_id: str) -> dict:
        """
        Full entropy report for integration with CoherenceEngine and MoatEngine.
        Matches the field names expected by L9.2 moat_floor computation.
        """
        state = self._get_or_create(entity_id)
        snap  = self.snapshot(entity_id)

        return {
            "entity_id":       entity_id,
            "timestamp":       int(snap.timestamp),
            "h_bits":          snap.h_bits,
            "h_max_bits":      round(H_MAX, 6),
            "h_norm":          snap.h_norm,
            "phi_entropy":     snap.phi_entropy,
            "s_thermo":        snap.s_thermo,
            "regime":          snap.regime,
            "total_events":    snap.total_events,
            "event_counts":    snap.event_counts,
            "velocity":        round(self.get_velocity(entity_id), 6),
            "snapshot_count":  len(state.snapshots),
            # L0.4 / L9.2 integration fields
            "entropy_healthy": snap.regime == "HEALTHY",
            "moat_floor":      snap.s_thermo,   # L9.2 thermodynamic floor
            "coherence_mult":  snap.phi_entropy, # multiply against raw C(t)
            # Band parameters (for reference by formal verification)
            "h_norm_low":      H_NORM_LOW,
            "h_norm_high":     H_NORM_HIGH,
        }

    def entity_count(self) -> int:
        """Number of distinct entities tracked."""
        return len(self._states)

    def reset_entity(self, entity_id: str) -> None:
        """Clear the entropy state for an entity (e.g. after identity recovery)."""
        self._states.pop(entity_id, None)


# ── Module-level singleton ────────────────────────────────────────────────────

import threading as _threading

_ee_instance: Optional[BehavioralEntropyEngine] = None
_ee_lock = _threading.Lock()


def get_entropy_engine() -> BehavioralEntropyEngine:
    """Thread-safe singleton accessor for the global BehavioralEntropyEngine."""
    global _ee_instance
    if _ee_instance is None:
        with _ee_lock:
            if _ee_instance is None:
                _ee_instance = BehavioralEntropyEngine()
    return _ee_instance


# ── Self-test ─────────────────────────────────────────────────────────────────

if __name__ == "__main__":
    print("=== TRION L0.4/L9.2 Behavioral Entropy Engine — Self-test ===\n")

    ee = BehavioralEntropyEngine()

    # 1. Empty entity — no events
    snap0 = ee.snapshot("empty_entity")
    assert snap0.regime == "EMPTY"
    assert snap0.phi_entropy == 0.10  # near-zero floor for empty entity
    print(f"[PASS] Empty entity: regime={snap0.regime}, Φ_ent={snap0.phi_entropy}")

    # 2. Degenerate entity — only one event type (wash trading)
    for _ in range(100):
        ee.record_event("wash_trader", 1)  # only SWAP
    snap_deg = ee.snapshot("wash_trader")
    assert snap_deg.regime == "DEGENERATE", f"Expected DEGENERATE, got {snap_deg.regime}"
    assert snap_deg.phi_entropy < 1.0
    print(f"[PASS] Degenerate entity: H_norm={snap_deg.h_norm:.3f}, Φ_ent={snap_deg.phi_entropy:.3f}")

    # 3. Healthy entity — events spread across several types but NOT perfectly uniform.
    # Perfect uniformity gives H_norm = 1.0 (RANDOM — no identifiable pattern).
    # Realistic DeFi actors concentrate some activity (SWAP/TRANSFER dominate) but
    # have meaningful diversity — H_norm lands in the HEALTHY band [0.15, 0.85].
    counts_by_type = {0: 200, 1: 300, 2: 50, 3: 80, 4: 40,
                      5: 10,  6: 20,  7: 15, 8: 30, 9: 25}
    for et, n in counts_by_type.items():
        for _ in range(n):
            ee.record_event("healthy_entity", et)
    snap_h = ee.snapshot("healthy_entity")
    assert snap_h.regime == "HEALTHY", (
        f"Expected HEALTHY, got {snap_h.regime} (H_norm={snap_h.h_norm:.3f})"
    )
    assert snap_h.phi_entropy == 1.0
    print(f"[PASS] Healthy entity: H_norm={snap_h.h_norm:.3f}, Φ_ent={snap_h.phi_entropy:.3f}")

    # 4. Full report fields for L9.2 integration
    report = ee.full_report("healthy_entity")
    assert "moat_floor"   in report
    assert "coherence_mult" in report
    assert report["entropy_healthy"] is True
    print(f"[PASS] L9.2 integration fields present: moat_floor={report['moat_floor']:.3f}")

    # 5. Entropy velocity — increasing
    ve = BehavioralEntropyEngine()
    # Start with degenerate then diversify
    for _ in range(50):
        ve.record_event("vel_entity", 0)
    ve.snapshot("vel_entity")
    for et in range(20):
        for _ in range(20):
            ve.record_event("vel_entity", et)
    ve.snapshot("vel_entity")
    vel = ve.get_velocity("vel_entity")
    assert vel > 0, f"Entropy velocity should be positive after diversification, got {vel}"
    print(f"[PASS] Entropy velocity ΔH={vel:.4f} (positive = diversifying)")

    # 6. Shannon entropy formula invariants
    # Uniform over N types → H = log₂(N)
    uniform = {i: 100 for i in range(N_EVENT_TYPES)}
    h_bits, h_norm = shannon_entropy(uniform)
    assert abs(h_bits - H_MAX) < 1e-6, f"Uniform should give H_max={H_MAX:.4f}, got {h_bits:.4f}"
    assert abs(h_norm - 1.0) < 1e-6
    print(f"[PASS] Shannon entropy: uniform H={h_bits:.4f} bits = H_max")

    # Single type → H = 0
    single = {0: 100}
    h_zero, _ = shannon_entropy(single)
    assert h_zero == 0.0, f"Single type should give H=0, got {h_zero}"
    print(f"[PASS] Shannon entropy: single type H={h_zero:.4f} bits = 0")

    # 7. Thread-safe singleton
    eng = get_entropy_engine()
    assert eng is get_entropy_engine(), "Singleton must return same instance"
    print("[PASS] Thread-safe singleton")

    print("\n=== ALL L0.4/L9.2 ENTROPY ENGINE TESTS PASSED ===")
    print(f"H_max={H_MAX:.4f} bits, healthy band [{H_NORM_LOW}, {H_NORM_HIGH}]")
    print("Integration: Φ_ent → CoherenceEngine, S_thermo → MoatEngine L9.2")
