"""
TRION Protocol — L4.9: Slashing Engine + 7-Step Dispute Resolution
Whitepaper Chapter 14: Governance Architecture — Validator Accountability

Five Slashing Conditions:
  S1. Double-signing:           slash 50% of stake, permanent ban
  S2. Prolonged offline (>72h): slash 5% of stake, temp suspension
  S3. False signal submission:  slash 20% of stake, probation 30d
  S4. Manipulation collusion:   slash 100% of stake, permanent ban
  S5. Geographic constraint violation: slash 10% of stake, 7-day suspension

Seven-Step Dispute Resolution Flow:
  Step 1: Accusation filed (any validator or protocol)
  Step 2: Evidence window (48h for accused to submit counter-evidence)
  Step 3: Quorum check (≥2/3 of non-accused validator stake must vote)
  Step 4: Vote (binary: GUILTY/INNOCENT)
  Step 5: HHI check (vote HHI must be < 4000 — no governance capture)
  Step 6: Slashing execution (if GUILTY + HHI_ok)
  Step 7: Appeal window (7 days, requires new evidence, one appeal per case)

Slashing is irreversible once Step 6 executes (semi-immutability principle).
Appeal can only reduce slash amount by up to 50%, not reverse guilt finding.

Author: TRION Protocol — Originator: Hudu Yusuf (Analys)
License: CC0
"""

from __future__ import annotations

import hashlib
import time
from dataclasses import dataclass, field
from enum import Enum
from typing import Dict, List, Optional


# ── Slashing Conditions ───────────────────────────────────────────────────────

class SlashingCondition(str, Enum):
    DOUBLE_SIGNING             = "S1_DOUBLE_SIGNING"
    PROLONGED_OFFLINE          = "S2_PROLONGED_OFFLINE"
    FALSE_SIGNAL_SUBMISSION    = "S3_FALSE_SIGNAL_SUBMISSION"
    MANIPULATION_COLLUSION     = "S4_MANIPULATION_COLLUSION"
    GEO_CONSTRAINT_VIOLATION   = "S5_GEO_CONSTRAINT_VIOLATION"


SLASH_PARAMETERS: Dict[SlashingCondition, dict] = {
    SlashingCondition.DOUBLE_SIGNING: {
        "stake_fraction":   0.50,
        "permanent_ban":    True,
        "suspension_days":  None,
        "probation_days":   None,
        "description":      "Validator signed two conflicting blocks at the same height.",
        "severity":         "CRITICAL",
    },
    SlashingCondition.PROLONGED_OFFLINE: {
        "stake_fraction":   0.05,
        "permanent_ban":    False,
        "suspension_days":  7,
        "probation_days":   None,
        "description":      "Validator offline > 72h without authorized maintenance window.",
        "severity":         "LOW",
    },
    SlashingCondition.FALSE_SIGNAL_SUBMISSION: {
        "stake_fraction":   0.20,
        "permanent_ban":    False,
        "suspension_days":  None,
        "probation_days":   30,
        "description":      "Validator submitted signal that was later falsified with evidence.",
        "severity":         "HIGH",
    },
    SlashingCondition.MANIPULATION_COLLUSION: {
        "stake_fraction":   1.00,
        "permanent_ban":    True,
        "suspension_days":  None,
        "probation_days":   None,
        "description":      "Validator participated in coordinated manipulation of TRION outputs.",
        "severity":         "CRITICAL",
    },
    SlashingCondition.GEO_CONSTRAINT_VIOLATION: {
        "stake_fraction":   0.10,
        "permanent_ban":    False,
        "suspension_days":  7,
        "probation_days":   None,
        "description":      "Validator violated L4.8 geographic distribution constraints.",
        "severity":         "MEDIUM",
    },
}


# ── Dispute Resolution States ─────────────────────────────────────────────────

class DisputeState(str, Enum):
    STEP_1_ACCUSATION   = "STEP_1_ACCUSATION"
    STEP_2_EVIDENCE     = "STEP_2_EVIDENCE"
    STEP_3_QUORUM_CHECK = "STEP_3_QUORUM_CHECK"
    STEP_4_VOTING       = "STEP_4_VOTING"
    STEP_5_HHI_CHECK    = "STEP_5_HHI_CHECK"
    STEP_6_EXECUTION    = "STEP_6_EXECUTION"
    STEP_7_APPEAL       = "STEP_7_APPEAL"
    RESOLVED_GUILTY     = "RESOLVED_GUILTY"
    RESOLVED_INNOCENT   = "RESOLVED_INNOCENT"
    APPEAL_GRANTED      = "APPEAL_GRANTED"


@dataclass
class SlashingEvent:
    """A completed slashing execution."""
    case_id:            str
    validator_id:       str
    condition:          SlashingCondition
    stake_slashed:      float       # Absolute amount slashed
    stake_remaining:    float       # Remaining stake after slash
    slash_fraction:     float       # Fraction of stake slashed
    permanent_ban:      bool
    suspension_until:   Optional[float]   # Unix timestamp
    probation_until:    Optional[float]   # Unix timestamp
    executed_at:        float
    evidence_hash:      str         # SHA3-256 of evidence submitted
    appeal_eligible:    bool
    appeal_deadline:    float       # 7 days after execution


@dataclass
class DisputeCase:
    """A dispute case tracking all 7 steps."""
    case_id:            str
    accused_id:         str
    accuser_id:         str
    condition:          SlashingCondition
    state:              DisputeState
    created_at:         float
    evidence_deadline:  float       # 48h after creation
    evidence_submitted: List[str]   # Evidence hash list
    votes_guilty:       float       # Total stake-weight voting GUILTY
    votes_innocent:     float       # Total stake-weight voting INNOCENT
    vote_hhi:           float       # HHI of voting stake (must be < 4000)
    total_eligible_stake: float
    quorum_reached:     bool
    hhi_ok:             bool
    slashing_event:     Optional[SlashingEvent] = None
    appeal_evidence:    Optional[str] = None
    resolution_notes:   str = ""
    has_been_appealed:  bool = False


# ── Dispute Resolution Engine ─────────────────────────────────────────────────

class SlashingEngine:
    """
    TRION L4.9 Slashing Engine.

    Implements the full 7-step dispute resolution flow.
    Slashing is irreversible once Step 6 executes.
    """

    EVIDENCE_WINDOW_HOURS = 48.0
    APPEAL_WINDOW_DAYS    = 7.0
    QUORUM_THRESHOLD      = 2.0 / 3.0     # ≥2/3 of non-accused validator stake
    HHI_THRESHOLD         = 4000.0        # Vote HHI must be < 4000 (L4.8)
    APPEAL_MAX_REDUCTION  = 0.50          # Appeal can reduce slash by up to 50%

    def __init__(self):
        self._cases:  Dict[str, DisputeCase] = {}
        self._events: List[SlashingEvent]    = []
        self._banned: set                    = set()     # Permanently banned validator IDs
        self._suspended: Dict[str, float]    = {}        # validator_id → until timestamp

    def _case_id(self, accused: str, condition: SlashingCondition) -> str:
        payload = f"{accused}:{condition.value}:{time.time()}".encode()
        return "CASE-" + hashlib.sha3_256(payload).hexdigest()[:16].upper()

    # ── Step 1: File accusation ───────────────────────────────────────────────

    def file_accusation(
        self,
        accused_id:   str,
        accuser_id:   str,
        condition:    SlashingCondition,
        total_eligible_stake: float = 1000.0,
    ) -> DisputeCase:
        """
        Step 1: Accusation filed.
        Opens 48h evidence window (Step 2).
        """
        if accused_id in self._banned:
            raise ValueError(f"Validator {accused_id} is permanently banned — no new cases needed.")

        now      = time.time()
        case_id  = self._case_id(accused_id, condition)

        case = DisputeCase(
            case_id              = case_id,
            accused_id           = accused_id,
            accuser_id           = accuser_id,
            condition            = condition,
            state                = DisputeState.STEP_2_EVIDENCE,
            created_at           = now,
            evidence_deadline    = now + self.EVIDENCE_WINDOW_HOURS * 3600,
            evidence_submitted   = [],
            votes_guilty         = 0.0,
            votes_innocent       = 0.0,
            vote_hhi             = 0.0,
            total_eligible_stake = total_eligible_stake,
            quorum_reached       = False,
            hhi_ok               = True,
        )
        self._cases[case_id] = case
        return case

    # ── Step 2: Submit evidence ───────────────────────────────────────────────

    def submit_evidence(
        self,
        case_id:   str,
        submitter: str,
        evidence:  bytes,
    ) -> bool:
        """Step 2: Accused (or anyone) submits counter-evidence within 48h window."""
        case = self._cases.get(case_id)
        if not case or case.state != DisputeState.STEP_2_EVIDENCE:
            return False
        if time.time() > case.evidence_deadline:
            case.state = DisputeState.STEP_3_QUORUM_CHECK
            return False
        evidence_hash = hashlib.sha3_256(evidence).hexdigest()
        case.evidence_submitted.append(evidence_hash)
        return True

    # ── Step 3+4: Vote ────────────────────────────────────────────────────────

    def cast_vote(
        self,
        case_id:      str,
        voter_id:     str,
        guilty:       bool,
        stake_weight: float,
    ) -> bool:
        """
        Steps 3+4: Quorum check + voting.
        Excluded: accused validator's own stake.
        """
        case = self._cases.get(case_id)
        if not case:
            return False
        if case.state not in (DisputeState.STEP_2_EVIDENCE, DisputeState.STEP_3_QUORUM_CHECK,
                              DisputeState.STEP_4_VOTING):
            return False
        if voter_id == case.accused_id:
            return False

        case.state = DisputeState.STEP_4_VOTING
        if guilty:
            case.votes_guilty   += stake_weight
        else:
            case.votes_innocent += stake_weight

        total_votes = case.votes_guilty + case.votes_innocent
        case.quorum_reached = total_votes >= case.total_eligible_stake * self.QUORUM_THRESHOLD

        if case.quorum_reached:
            case.state = DisputeState.STEP_5_HHI_CHECK

        return True

    # ── Step 5: HHI check ────────────────────────────────────────────────────

    def run_hhi_check(
        self,
        case_id: str,
        voter_stakes: List[float],
    ) -> bool:
        """
        Step 5: Verify vote HHI < 4000 (no governance capture of the vote itself).
        If HHI ≥ 4000: dispute is escalated (no slashing — governance capture detected).
        """
        case = self._cases.get(case_id)
        if not case or case.state != DisputeState.STEP_5_HHI_CHECK:
            return False

        total = sum(voter_stakes) or 1.0
        shares = [s / total for s in voter_stakes]
        hhi = sum(s ** 2 for s in shares) * 10000
        case.vote_hhi = hhi
        case.hhi_ok   = hhi < self.HHI_THRESHOLD

        if case.hhi_ok:
            case.state = DisputeState.STEP_6_EXECUTION
        else:
            case.resolution_notes = (
                f"GOVERNANCE CAPTURE of dispute: vote HHI={hhi:.0f} ≥ {self.HHI_THRESHOLD}. "
                "Slashing blocked — quorum is itself captured. "
                "Case escalated to emergency AWA review."
            )
            case.state = DisputeState.RESOLVED_INNOCENT

        return case.hhi_ok

    # ── Step 6: Execute slashing ──────────────────────────────────────────────

    def execute_slashing(
        self,
        case_id:         str,
        validator_stake: float,
    ) -> Optional[SlashingEvent]:
        """
        Step 6: Execute slashing if GUILTY + quorum + HHI_ok.
        This is irreversible per the semi-immutability principle.
        """
        case = self._cases.get(case_id)
        if not case or case.state != DisputeState.STEP_6_EXECUTION:
            return None

        guilty_fraction = (
            case.votes_guilty / (case.votes_guilty + case.votes_innocent)
            if (case.votes_guilty + case.votes_innocent) > 0 else 0.0
        )
        guilty = guilty_fraction > 0.50

        if not guilty:
            case.state = DisputeState.RESOLVED_INNOCENT
            case.resolution_notes = f"INNOCENT: {guilty_fraction:.2%} guilty votes (need >50%)"
            return None

        params      = SLASH_PARAMETERS[case.condition]
        slash_frac  = params["stake_fraction"]
        stake_slash = min(validator_stake, validator_stake * slash_frac)
        remaining   = max(0.0, validator_stake - stake_slash)

        now   = time.time()
        event = SlashingEvent(
            case_id          = case_id,
            validator_id     = case.accused_id,
            condition        = case.condition,
            stake_slashed    = stake_slash,
            stake_remaining  = remaining,
            slash_fraction   = slash_frac,
            permanent_ban    = params["permanent_ban"],
            suspension_until = (now + params["suspension_days"] * 86400
                                if params.get("suspension_days") else None),
            probation_until  = (now + params["probation_days"] * 86400
                                if params.get("probation_days") else None),
            executed_at      = now,
            evidence_hash    = "|".join(case.evidence_submitted) or "none",
            appeal_eligible  = True,
            appeal_deadline  = now + self.APPEAL_WINDOW_DAYS * 86400,
        )

        if params["permanent_ban"]:
            self._banned.add(case.accused_id)
        if event.suspension_until:
            self._suspended[case.accused_id] = event.suspension_until

        case.slashing_event = event
        case.state          = DisputeState.STEP_7_APPEAL
        self._events.append(event)
        return event

    # ── Step 7: Appeal ───────────────────────────────────────────────────────

    def file_appeal(
        self,
        case_id:         str,
        new_evidence:    bytes,
        validator_stake: float,
    ) -> dict:
        """
        Step 7: Appeal window (7 days).
        One appeal per case. Can reduce slash by up to 50% with new evidence.
        Cannot reverse guilt finding.
        Cannot re-open a permanently banned case.
        """
        case = self._cases.get(case_id)
        if not case or case.state != DisputeState.STEP_7_APPEAL:
            return {"success": False, "reason": "Case not in appeal window"}
        if case.has_been_appealed:
            return {"success": False, "reason": "One appeal per case — already appealed"}
        if not case.slashing_event:
            return {"success": False, "reason": "No slashing event to appeal"}
        if time.time() > case.slashing_event.appeal_deadline:
            case.state = DisputeState.RESOLVED_GUILTY
            return {"success": False, "reason": "Appeal deadline passed"}
        if case.slashing_event.permanent_ban:
            return {"success": False, "reason": "Permanent ban cases are non-appealable"}

        new_evidence_hash   = hashlib.sha3_256(new_evidence).hexdigest()
        case.appeal_evidence = new_evidence_hash
        case.has_been_appealed = True

        original_slash = case.slashing_event.stake_slashed
        reduced_slash  = original_slash * (1.0 - self.APPEAL_MAX_REDUCTION)
        original_remaining = case.slashing_event.stake_remaining
        restored = original_slash - reduced_slash
        new_remaining = original_remaining + restored

        case.slashing_event = SlashingEvent(
            case_id          = case_id,
            validator_id     = case.slashing_event.validator_id,
            condition        = case.slashing_event.condition,
            stake_slashed    = reduced_slash,
            stake_remaining  = new_remaining,
            slash_fraction   = case.slashing_event.slash_fraction * (1.0 - self.APPEAL_MAX_REDUCTION),
            permanent_ban    = False,
            suspension_until = case.slashing_event.suspension_until,
            probation_until  = case.slashing_event.probation_until,
            executed_at      = case.slashing_event.executed_at,
            evidence_hash    = case.slashing_event.evidence_hash + "|APPEAL:" + new_evidence_hash,
            appeal_eligible  = False,
            appeal_deadline  = case.slashing_event.appeal_deadline,
        )
        case.state = DisputeState.APPEAL_GRANTED

        return {
            "success":         True,
            "original_slash":  original_slash,
            "reduced_slash":   reduced_slash,
            "stake_restored":  restored,
            "new_remaining":   new_remaining,
            "evidence_hash":   new_evidence_hash,
            "note":            "Guilt finding stands. Slash reduced by up to 50% (new evidence accepted).",
        }

    # ── Query helpers ─────────────────────────────────────────────────────────

    def is_banned(self, validator_id: str) -> bool:
        return validator_id in self._banned

    def is_suspended(self, validator_id: str) -> bool:
        until = self._suspended.get(validator_id)
        return until is not None and time.time() < until

    def get_case(self, case_id: str) -> Optional[dict]:
        case = self._cases.get(case_id)
        if not case:
            return None
        return {
            "case_id":            case.case_id,
            "accused_id":         case.accused_id,
            "accuser_id":         case.accuser_id,
            "condition":          case.condition.value,
            "state":              case.state.value,
            "quorum_reached":     case.quorum_reached,
            "votes_guilty":       case.votes_guilty,
            "votes_innocent":     case.votes_innocent,
            "vote_hhi":           case.vote_hhi,
            "hhi_ok":             case.hhi_ok,
            "has_been_appealed":  case.has_been_appealed,
            "resolution_notes":   case.resolution_notes,
            "slashing_event":     {
                "stake_slashed":  case.slashing_event.stake_slashed,
                "slash_fraction": case.slashing_event.slash_fraction,
                "permanent_ban":  case.slashing_event.permanent_ban,
                "executed_at":    case.slashing_event.executed_at,
            } if case.slashing_event else None,
        }

    def summary(self) -> dict:
        return {
            "total_cases":       len(self._cases),
            "total_slashings":   len(self._events),
            "permanently_banned": len(self._banned),
            "currently_suspended": len([v for v, t in self._suspended.items() if time.time() < t]),
            "banned_validators": list(self._banned),
        }


# ── Module-level singleton ─────────────────────────────────────────────────────

_engine = SlashingEngine()

def get_slashing_engine() -> SlashingEngine:
    return _engine


# ── Self-test ─────────────────────────────────────────────────────────────────

if __name__ == "__main__":
    engine = SlashingEngine()

    # ── Test S1: Double-signing (permanent ban) ───────────────────────────────
    case = engine.file_accusation("validator_X", "validator_Y",
                                   SlashingCondition.DOUBLE_SIGNING, total_eligible_stake=3000)
    assert case.state == DisputeState.STEP_2_EVIDENCE

    engine.submit_evidence(case.case_id, "validator_X", b"I did not double sign")
    engine.cast_vote(case.case_id, "v_A", True,  1200)
    engine.cast_vote(case.case_id, "v_B", True,  1000)
    engine.cast_vote(case.case_id, "v_C", False, 400)
    assert case.quorum_reached, "Quorum should be reached (2200/3000 = 73.3% > 66.7%)"
    assert case.state == DisputeState.STEP_5_HHI_CHECK

    engine.run_hhi_check(case.case_id, [1200, 1000, 400])
    assert case.hhi_ok, f"HHI should be OK: {case.vote_hhi:.0f}"

    event = engine.execute_slashing(case.case_id, validator_stake=10000)
    assert event is not None
    assert event.slash_fraction == 0.50
    assert event.permanent_ban
    assert event.stake_slashed == 5000
    assert engine.is_banned("validator_X")
    print(f"S1 Double-signing: slashed {event.stake_slashed:.0f} of 10000, permanent_ban={event.permanent_ban}")

    # ── Test appeal rejected for permanent ban ────────────────────────────────
    appeal_result = engine.file_appeal(case.case_id, b"new evidence", validator_stake=5000)
    assert not appeal_result["success"]
    print(f"Appeal rejected: {appeal_result['reason']}")

    # ── Test S3: False signal (probation, appealable) ─────────────────────────
    engine2 = SlashingEngine()
    case3 = engine2.file_accusation("validator_Z", "protocol_monitor",
                                     SlashingCondition.FALSE_SIGNAL_SUBMISSION, total_eligible_stake=2000)
    engine2.cast_vote(case3.case_id, "vA", True,  700)
    engine2.cast_vote(case3.case_id, "vB", True,  700)
    engine2.cast_vote(case3.case_id, "vC", False, 400)
    assert case3.quorum_reached
    engine2.run_hhi_check(case3.case_id, [700, 700, 400])
    event3 = engine2.execute_slashing(case3.case_id, validator_stake=5000)
    assert event3 and event3.slash_fraction == 0.20
    print(f"S3 False signal: slashed {event3.stake_slashed:.0f}, probation={event3.probation_until is not None}")

    appeal3 = engine2.file_appeal(case3.case_id, b"corrected calibration data", validator_stake=4000)
    assert appeal3["success"]
    print(f"Appeal granted: restored {appeal3['stake_restored']:.0f}, new_slash={appeal3['reduced_slash']:.0f}")

    print("\nL4.9 Slashing + 7-Step Dispute Resolution: ALL PASS")
