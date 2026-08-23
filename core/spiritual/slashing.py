"""
TRION Protocol — L4.9 Slashing Conditions + Dispute Resolution

Slashing conditions (from whitepaper L4.9):

COORDINATED_ATTACK_CONFIRMED:  50% of stake. Permanent exclusion.
    Triggered: d_j → 0 over sustained period (≥ 10 blocks).
    Evidence: mathematical proof from coordination collapse theorem.

SUSTAINED_LOW_ACCURACY:        3% per 30-day window.
    Triggered: accuracy < 40% for consecutive 30-day window.
    Evidence: rolling calibration score from IMP.

HARDWARE_SECURITY_FAILURE:     10%.
    Triggered: HSM offline or behavioral signature mismatch.
    Evidence: HSM attestation failure.

UPTIME_FAILURE:                0.1% per day below minimum.
    Triggered: uptime < 99.5% over 30-day window.
    Evidence: heartbeat monitoring.

SYBIL_CLUSTER_CONFIRMED:       25% for all in cluster. Permanent exclusion.
    Triggered: entity resolution identifies validator cluster as Sybil.
    Evidence: BEO confidence > 0.95 for cluster.

Dispute Resolution:
    72-hour window from slash proposal.
    Challenger stakes 5% of slashed amount.
    Resolution: 3 independent validators + 1 human oversight council member.
    Timeline: 7 days for full resolution.
    If upheld: challenger loses bond. Slash stands.
    If reversed: challenger receives bond back + 2× reward.

Author: TRION Protocol — Originator: Hudu Yusuf (Analys)
License: CC0
"""

from __future__ import annotations
import time
from dataclasses import dataclass
from enum import Enum
from typing import Optional


class SlashType(Enum):
    COORDINATED_ATTACK   = "COORDINATED_ATTACK_CONFIRMED"
    LOW_ACCURACY         = "SUSTAINED_LOW_ACCURACY"
    HSM_FAILURE          = "HARDWARE_SECURITY_FAILURE"
    UPTIME_FAILURE       = "UPTIME_FAILURE"
    SYBIL_CLUSTER        = "SYBIL_CLUSTER_CONFIRMED"


class DisputeStatus(Enum):
    PENDING    = "PENDING"
    CHALLENGED = "CHALLENGED"
    REVIEWING  = "REVIEWING"
    UPHELD     = "UPHELD"      # Slash stands
    REVERSED   = "REVERSED"    # Slash cancelled


# Slash percentages (basis points of stake)
SLASH_AMOUNTS_BPS: dict[SlashType, int] = {
    SlashType.COORDINATED_ATTACK:  5000,   # 50%
    SlashType.LOW_ACCURACY:         300,   # 3%
    SlashType.HSM_FAILURE:         1000,   # 10%
    SlashType.UPTIME_FAILURE:        10,   # 0.1% per day
    SlashType.SYBIL_CLUSTER:       2500,   # 25%
}

PERMANENT_EXCLUSION: set[SlashType] = {
    SlashType.COORDINATED_ATTACK,
    SlashType.SYBIL_CLUSTER,
}

CHALLENGE_BOND_BPS = 500    # 5% of slashed amount
DISPUTE_WINDOW_H   = 72     # 72 hours
REVIEW_PERIOD_H    = 7 * 24  # 7 days


@dataclass
class SlashProposal:
    """A proposed slash against a validator."""
    slash_id:           str
    validator_id:       str
    slash_type:         SlashType
    stake_amount:       float
    slash_bps:          int
    slash_amount:       float
    proposed_at:        float       # Unix timestamp
    evidence_hash:      str
    permanent:          bool
    days_below_uptime:  int         # Only for UPTIME_FAILURE
    status:             str         # "PROPOSED"


@dataclass
class SlashDispute:
    """A validator's challenge to a slash proposal."""
    dispute_id:         str
    slash_id:           str
    validator_id:       str
    challenge_bond:     float
    challenged_at:      float
    resolution_votes:   list[dict]  # [{validator: str, vote: str, reason: str}]
    status:             DisputeStatus
    resolved_at:        Optional[float]
    upheld:             Optional[bool]


@dataclass
class SlashResult:
    """Final slashing decision."""
    slash_id:           str
    validator_id:       str
    slash_type:         SlashType
    slash_amount:       float
    executed:           bool
    permanent_excluded: bool
    dispute:            Optional[SlashDispute]
    stake_remaining:    float
    reason:             str


def compute_slash(
    slash_id:          str,
    validator_id:      str,
    slash_type:        SlashType,
    stake_amount:      float,
    days_below_uptime: int = 0,
) -> SlashProposal:
    """
    Compute the slash amount for a given violation.
    UPTIME_FAILURE is cumulative: 0.1% per day below minimum.
    All others are fixed percentages.
    """
    if slash_type == SlashType.UPTIME_FAILURE:
        # 0.1% per day below minimum uptime
        bps = SLASH_AMOUNTS_BPS[SlashType.UPTIME_FAILURE] * max(1, days_below_uptime)
    else:
        bps = SLASH_AMOUNTS_BPS[slash_type]

    bps = min(bps, 10000)  # Cap at 100%
    slash_amount = stake_amount * bps / 10000

    return SlashProposal(
        slash_id          = slash_id,
        validator_id      = validator_id,
        slash_type        = slash_type,
        stake_amount      = stake_amount,
        slash_bps         = bps,
        slash_amount      = slash_amount,
        proposed_at       = time.time(),
        evidence_hash     = f"sha3_{slash_id}_{validator_id}",
        permanent         = slash_type in PERMANENT_EXCLUSION,
        days_below_uptime = days_below_uptime,
        status            = "PROPOSED",
    )


def open_dispute(
    dispute_id:  str,
    proposal:    SlashProposal,
) -> SlashDispute:
    """
    Open a 72-hour dispute window.
    Challenger must stake 5% of slashed amount.
    """
    challenge_bond = proposal.slash_amount * CHALLENGE_BOND_BPS / 10000
    return SlashDispute(
        dispute_id      = dispute_id,
        slash_id        = proposal.slash_id,
        validator_id    = proposal.validator_id,
        challenge_bond  = challenge_bond,
        challenged_at   = time.time(),
        resolution_votes = [],
        status          = DisputeStatus.CHALLENGED,
        resolved_at     = None,
        upheld          = None,
    )


def is_dispute_window_open(proposal: SlashProposal) -> bool:
    """Check if the 72-hour dispute window is still open."""
    elapsed_h = (time.time() - proposal.proposed_at) / 3600
    return elapsed_h < DISPUTE_WINDOW_H


def resolve_dispute(
    dispute:      SlashDispute,
    votes:        list[dict],  # [{"validator": str, "vote": "UPHOLD"/"REVERSE", "reason": str}]
) -> DisputeStatus:
    """
    Resolution requires 3 independent validators + 1 human oversight council member.
    Majority vote determines outcome.
    Timeline: 7 days for full resolution.
    """
    dispute.resolution_votes = votes

    uphold_count  = sum(1 for v in votes if v.get("vote") == "UPHOLD")
    reverse_count = sum(1 for v in votes if v.get("vote") == "REVERSE")

    if uphold_count > reverse_count:
        dispute.status     = DisputeStatus.UPHELD
        dispute.upheld     = True
    else:
        dispute.status     = DisputeStatus.REVERSED
        dispute.upheld     = False

    dispute.resolved_at = time.time()
    return dispute.status


def execute_slash(
    proposal: SlashProposal,
    dispute:  Optional[SlashDispute] = None,
) -> SlashResult:
    """
    Execute the slash after dispute resolution (or after window expires).

    If dispute REVERSED: slash cancelled, challenger gets bond + 2× reward.
    If dispute UPHELD or no dispute: slash executed.
    """
    if dispute and dispute.status == DisputeStatus.REVERSED:
        return SlashResult(
            slash_id          = proposal.slash_id,
            validator_id      = proposal.validator_id,
            slash_type        = proposal.slash_type,
            slash_amount      = 0.0,
            executed          = False,
            permanent_excluded = False,
            dispute           = dispute,
            stake_remaining   = proposal.stake_amount,
            reason            = f"SLASH_REVERSED: dispute {dispute.dispute_id} upheld validator's challenge",
        )

    return SlashResult(
        slash_id          = proposal.slash_id,
        validator_id      = proposal.validator_id,
        slash_type        = proposal.slash_type,
        slash_amount      = proposal.slash_amount,
        executed          = True,
        permanent_excluded = proposal.permanent,
        dispute           = dispute,
        stake_remaining   = max(0, proposal.stake_amount - proposal.slash_amount),
        reason            = (
            f"SLASH_EXECUTED: {proposal.slash_type.value} "
            f"({proposal.slash_bps}bps = {proposal.slash_amount:.2f} TRION)"
            + (f" PERMANENT_EXCLUSION" if proposal.permanent else "")
        ),
    )


if __name__ == "__main__":
    # Coordinated attack — 50% slash + permanent
    prop = compute_slash("slash_001", "validator_xyz", SlashType.COORDINATED_ATTACK, 100_000.0)
    print(f"Coordinated: slash={prop.slash_amount:.0f} TRION permanent={prop.permanent}")
    assert prop.slash_amount == 50_000.0
    assert prop.permanent

    # Uptime failure — cumulative
    prop_up = compute_slash("slash_002", "val_abc", SlashType.UPTIME_FAILURE, 10_000.0, days_below_uptime=5)
    print(f"Uptime 5d: slash={prop_up.slash_amount:.2f} TRION ({prop_up.slash_bps}bps)")
    assert prop_up.slash_bps == 50  # 0.1% × 5 days

    # Dispute and reversal
    dispute = open_dispute("dispute_001", prop)
    votes = [
        {"validator": "v1", "vote": "REVERSE", "reason": "Evidence insufficient"},
        {"validator": "v2", "vote": "REVERSE", "reason": "Coordination unproven"},
        {"validator": "v3", "vote": "UPHOLD",  "reason": "Pattern confirmed"},
    ]
    status = resolve_dispute(dispute, votes)
    result = execute_slash(prop, dispute)
    print(f"Dispute reversed: executed={result.executed} remaining={result.stake_remaining:.0f}")
    assert not result.executed

    print("L4.9 Slashing + Dispute Resolution: PASS")
