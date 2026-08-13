"""
TRION Protocol — L0.3 Resonance Communication
Channel 17: P2P Resonance Communication

Resonance Communication principle:
    Comm(A, B) iff ∃f : RF(A, f) > 0 AND RF(B, f) > 0

Two entities communicate only if they share a resonant frequency.
This governs: validator ↔ validator, chain ↔ chain, entity ↔ entity.

The 20 VM-Agnostic Event Types:
TRION maps all blockchain events to these 20 universal types regardless
of chain, VM, or protocol. Universal entity resolution across EVM, SVM,
CosmWasm, MoveVM, Substrate, UTXO, etc.

Author: TRION Protocol — Originator: Hudu Yusuf (Analys)
License: CC0
"""

from __future__ import annotations
from dataclasses import dataclass
from enum import IntEnum
from typing import Dict, List, Tuple


# ── 20 VM-Agnostic Event Types ────────────────────────────────────────────────
# These are the universal event abstractions that TRION maps all blockchain
# events onto, regardless of underlying VM. This enables cross-chain
# behavioral comparison.

class UniversalEventType(IntEnum):
    """Canonical 20 event types — aligned with L0.1 EventType in behavioral_hash.py."""
    TRANSFER              = 0
    SWAP                  = 1
    LIQUIDITY             = 2
    STAKE                 = 3
    UNSTAKE               = 4
    GOVERNANCE            = 5
    PROPOSAL              = 6
    BORROW                = 7
    REPAY                 = 8
    LIQUIDATE             = 9
    BRIDGE                = 10
    DEPLOY                = 11
    UPGRADE               = 12
    MINT                  = 13
    BURN                  = 14
    ORACLE_UPDATE         = 15
    MEV_CAPTURE           = 16
    FLASH_LOAN            = 17
    AIRDROP               = 18
    CLAIM                 = 19
    # Backward-compatible aliases
    LIQUIDITY_ADD         = 2
    LIQUIDITY_REMOVE      = 2
    GOVERNANCE_VOTE       = 5
    GOVERNANCE_PROPOSE    = 6
    CONTRACT_DEPLOY       = 11
    CONTRACT_UPGRADE      = 12
    BRIDGE_DEPOSIT        = 10
    BRIDGE_WITHDRAW       = 10
    MEV_EXTRACTION        = 16
    REWARD_CLAIM          = 19
    NFT_MINT              = 13
    NFT_TRANSFER          = 0
    SYSTEM_INTERNAL       = 19


# Behavioral weights per event type (sum normalized per entity over time)
# Higher weight = more behaviorally informative
EVENT_WEIGHTS: Dict[UniversalEventType, float] = {
    UniversalEventType.TRANSFER:           1.00,
    UniversalEventType.SWAP:               1.10,
    UniversalEventType.LIQUIDITY:          1.30,
    UniversalEventType.STAKE:              1.20,
    UniversalEventType.UNSTAKE:            1.20,
    UniversalEventType.GOVERNANCE:         1.50,
    UniversalEventType.PROPOSAL:           1.70,
    UniversalEventType.BORROW:             1.40,
    UniversalEventType.REPAY:              1.40,
    UniversalEventType.LIQUIDATE:          1.60,
    UniversalEventType.BRIDGE:             1.10,
    UniversalEventType.DEPLOY:             2.00,
    UniversalEventType.UPGRADE:            2.00,
    UniversalEventType.MINT:               1.10,
    UniversalEventType.BURN:               1.10,
    UniversalEventType.ORACLE_UPDATE:      1.50,
    UniversalEventType.MEV_CAPTURE:        1.80,
    UniversalEventType.FLASH_LOAN:         1.80,
    UniversalEventType.AIRDROP:            1.20,
    UniversalEventType.CLAIM:              0.90,
}


@dataclass
class ResonanceFrequency:
    """
    RF(entity, f) = normalized behavioral activity at frequency f.
    Frequency is measured in events per unit time at a specific event type.
    """
    entity_id:     str
    event_type:    UniversalEventType
    frequency:     float  # Events per day
    amplitude:     float  # Normalized [0, 1] — relative activity level
    phase:         float  # Phase alignment with circadian BRT [0, 2π]


@dataclass
class ResonanceResult:
    """
    Comm(A, B) iff ∃f : RF(A, f) > 0 AND RF(B, f) > 0
    """
    entity_a:              str
    entity_b:              str
    shared_frequencies:    List[UniversalEventType]
    resonance_score:       float     # [0, 1] — strength of shared resonance
    communicates:          bool      # True iff resonance_score > 0
    dominant_channel:      UniversalEventType
    phase_alignment:       float     # How closely phase-aligned the entities are


def compute_resonance_frequencies(
    entity_id: str,
    event_counts: Dict[UniversalEventType, int],
    observation_days: float = 90.0,
) -> List[ResonanceFrequency]:
    """
    Compute resonance frequency spectrum for an entity from its event history.

    event_counts: { event_type → count over observation_days }
    Returns list of ResonanceFrequency — one per event type with activity > 0.
    """
    if observation_days <= 0:
        return []

    total_events = sum(event_counts.values())
    if total_events == 0:
        return []

    frequencies = []
    for etype, count in event_counts.items():
        if count <= 0:
            continue
        freq = count / observation_days  # Events per day
        amplitude = count / total_events  # Normalized share of total activity
        # Phase: derived from event timing relative to circadian cycle
        # Simplified: uniform phase unless timing data available
        phase = 0.0
        frequencies.append(ResonanceFrequency(
            entity_id  = entity_id,
            event_type = etype,
            frequency  = freq,
            amplitude  = amplitude,
            phase      = phase,
        ))

    return sorted(frequencies, key=lambda r: r.amplitude, reverse=True)


def compute_channel_resonance(
    rf_a: List[ResonanceFrequency],
    rf_b: List[ResonanceFrequency],
) -> ResonanceResult:
    """
    Comm(A, B) iff ∃f : RF(A, f) > 0 AND RF(B, f) > 0

    Resonance score = cosine similarity of behavioral frequency vectors,
    weighted by event importance weights.
    """
    if not rf_a or not rf_b:
        entity_a = rf_a[0].entity_id if rf_a else "unknown_a"
        entity_b = rf_b[0].entity_id if rf_b else "unknown_b"
        return ResonanceResult(
            entity_a           = entity_a,
            entity_b           = entity_b,
            shared_frequencies = [],
            resonance_score    = 0.0,
            communicates       = False,
            dominant_channel   = UniversalEventType.SYSTEM_INTERNAL,
            phase_alignment    = 0.0,
        )

    entity_a = rf_a[0].entity_id
    entity_b = rf_b[0].entity_id

    # Build frequency vectors
    freq_map_a: Dict[UniversalEventType, ResonanceFrequency] = {r.event_type: r for r in rf_a}
    freq_map_b: Dict[UniversalEventType, ResonanceFrequency] = {r.event_type: r for r in rf_b}

    shared = [et for et in freq_map_a if et in freq_map_b]

    if not shared:
        return ResonanceResult(
            entity_a           = entity_a,
            entity_b           = entity_b,
            shared_frequencies = [],
            resonance_score    = 0.0,
            communicates       = False,
            dominant_channel   = UniversalEventType.SYSTEM_INTERNAL,
            phase_alignment    = 0.0,
        )

    # Weighted cosine similarity
    dot, mag_a, mag_b = 0.0, 0.0, 0.0
    phase_sum = 0.0
    dominant_channel = shared[0]
    max_resonance = 0.0

    all_types = list(UniversalEventType)
    vec_a = [freq_map_a.get(et, None) for et in all_types]
    vec_b = [freq_map_b.get(et, None) for et in all_types]

    for i, et in enumerate(all_types):
        w = EVENT_WEIGHTS[et]
        amp_a = vec_a[i].amplitude * w if vec_a[i] else 0.0
        amp_b = vec_b[i].amplitude * w if vec_b[i] else 0.0
        dot   += amp_a * amp_b
        mag_a += amp_a ** 2
        mag_b += amp_b ** 2

        if vec_a[i] and vec_b[i]:
            reson = amp_a * amp_b
            if reson > max_resonance:
                max_resonance = reson
                dominant_channel = et
            phase_sum += abs(vec_a[i].phase - vec_b[i].phase)

    denom = (mag_a ** 0.5) * (mag_b ** 0.5)
    resonance_score = dot / denom if denom > 0 else 0.0
    phase_alignment = 1.0 - (phase_sum / (len(shared) * 2 * 3.14159)) if shared else 0.0
    phase_alignment = max(0.0, min(1.0, phase_alignment))

    return ResonanceResult(
        entity_a           = entity_a,
        entity_b           = entity_b,
        shared_frequencies = shared,
        resonance_score    = min(1.0, resonance_score),
        communicates       = resonance_score > 0,
        dominant_channel   = dominant_channel,
        phase_alignment    = phase_alignment,
    )


def can_communicate(rf_a: List[ResonanceFrequency], rf_b: List[ResonanceFrequency]) -> bool:
    """
    Simple predicate: Comm(A, B) iff ∃f : RF(A, f) > 0 AND RF(B, f) > 0
    """
    types_a = {r.event_type for r in rf_a if r.frequency > 0}
    types_b = {r.event_type for r in rf_b if r.frequency > 0}
    return bool(types_a & types_b)


if __name__ == "__main__":
    # Self-test
    events_a = {
        UniversalEventType.SWAP:            500,
        UniversalEventType.LIQUIDITY_ADD:   120,
        UniversalEventType.GOVERNANCE_VOTE: 15,
    }
    events_b = {
        UniversalEventType.SWAP:            300,
        UniversalEventType.BORROW:          80,
        UniversalEventType.GOVERNANCE_VOTE: 8,
    }
    rf_a = compute_resonance_frequencies("entity_A", events_a)
    rf_b = compute_resonance_frequencies("entity_B", events_b)

    result = compute_channel_resonance(rf_a, rf_b)
    print(f"Resonance score: {result.resonance_score:.4f}")
    print(f"Communicates:    {result.communicates}")
    print(f"Shared channels: {[e.name for e in result.shared_frequencies]}")
    print(f"Dominant:        {result.dominant_channel.name}")
    print("L0.3 PASS")
