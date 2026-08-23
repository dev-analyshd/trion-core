"""
TRION Protocol — BTCP Module 2.19: Dispute Resolution (Conscious Layer)
Gap I: Behavioral Evidence Standard — 3-of-5 + stake-and-slash.
"""
from __future__ import annotations
import hashlib, time
from dataclasses import dataclass, field
from enum import Enum
from typing import Dict, List, Optional


class Vote(Enum):
    GUILTY = "GUILTY"
    NOT_GUILTY = "NOT_GUILTY"


class DisputeStatus(str, Enum):
    OPEN = "OPEN"
    RESOLVED_GUILTY = "RESOLVED_GUILTY"
    RESOLVED_NOT_GUILTY = "RESOLVED_NOT_GUILTY"
    DISMISSED = "DISMISSED"


ANNOTATORS_PER_DISPUTE = 5
MAJORITY_REQUIRED = 3
DISPUTE_WINDOW_SECONDS = 72 * 3600
CHALLENGE_BOND_BPS = 500


@dataclass
class Annotator:
    annotator_id: str
    stake: float
    jurisdiction: str = "UNKNOWN"
    active: bool = True


@dataclass
class DisputeVoteRecord:
    annotator_id: str
    vote: Vote
    rationale_hash: str
    timestamp: float


@dataclass
class DisputeCase:
    case_id: str
    route_id: str
    claimant: str
    respondent: str
    claim: str
    evidence_hashes: List[str] = field(default_factory=list)
    challenged_value: float = 0.0
    challenge_bond: float = 0.0
    selected_annotators: List[str] = field(default_factory=list)
    votes: Dict[str, DisputeVoteRecord] = field(default_factory=dict)
    status: DisputeStatus = DisputeStatus.OPEN
    opened_at: float = field(default_factory=time.time)
    resolved_at: Optional[float] = None
    resolution_note: str = ""

    @property
    def guilty_votes(self) -> int:
        return sum(1 for v in self.votes.values() if v.vote == Vote.GUILTY)

    @property
    def not_guilty_votes(self) -> int:
        return sum(1 for v in self.votes.values() if v.vote == Vote.NOT_GUILTY)


class DisputeResolver:
    """Conscious Layer 3-of-5 dispute resolution engine."""

    def __init__(self) -> None:
        self._annotators: Dict[str, Annotator] = {}
        self._cases: Dict[str, DisputeCase] = {}

    def register_annotator(self, annotator_id: str, stake: float, jurisdiction: str = "UNKNOWN") -> bool:
        if annotator_id in self._annotators:
            return False
        self._annotators[annotator_id] = Annotator(annotator_id, max(0.0, stake), jurisdiction)
        return True

    def _select_annotators(self, exclude: set) -> List[str]:
        candidates = [a for a in self._annotators.values()
                      if a.active and a.annotator_id not in exclude]
        candidates.sort(key=lambda a: (-a.stake, a.annotator_id))
        return [a.annotator_id for a in candidates[:ANNOTATORS_PER_DISPUTE]]

    def open_case(self, route_id, claimant, respondent, claim,
                  evidence_hashes=None, challenged_value=0.0) -> DisputeCase:
        case_id = "DISPUTE-" + hashlib.sha3_256(
            f"{route_id}:{claimant}:{respondent}:{time.time_ns()}".encode()).hexdigest()[:16]
        case = DisputeCase(
            case_id=case_id, route_id=route_id, claimant=claimant, respondent=respondent,
            claim=claim, evidence_hashes=list(evidence_hashes or []),
            challenged_value=max(0.0, challenged_value),
            challenge_bond=(max(0.0, challenged_value) * CHALLENGE_BOND_BPS) / 10_000,
            selected_annotators=self._select_annotators({claimant, respondent}))
        self._cases[case_id] = case
        return case

    def cast_vote(self, case_id: str, annotator_id: str, vote: Vote, rationale: str) -> bool:
        case = self._cases.get(case_id)
        if case is None or case.status != DisputeStatus.OPEN:
            return False
        if annotator_id not in case.selected_annotators or annotator_id in case.votes:
            return False
        case.votes[annotator_id] = DisputeVoteRecord(
            annotator_id, vote, hashlib.sha3_256(rationale.encode()).hexdigest(), time.time())
        if len(case.votes) >= ANNOTATORS_PER_DISPUTE:
            self._resolve(case)
        elif case.guilty_votes >= MAJORITY_REQUIRED or case.not_guilty_votes >= MAJORITY_REQUIRED:
            self._resolve(case)
        return True

    def _resolve(self, case: DisputeCase) -> None:
        case.resolved_at = time.time()
        if case.guilty_votes >= MAJORITY_REQUIRED:
            case.status = DisputeStatus.RESOLVED_GUILTY
            case.resolution_note = f"3-of-5 majority GUILTY ({case.guilty_votes}/5)."
        elif case.not_guilty_votes >= MAJORITY_REQUIRED:
            case.status = DisputeStatus.RESOLVED_NOT_GUILTY
            case.resolution_note = f"3-of-5 majority NOT_GUILTY ({case.not_guilty_votes}/5)."
        else:
            case.status = DisputeStatus.DISMISSED
            case.resolution_note = "Insufficient majority — dismissed."

    def get_case(self, case_id): return self._cases.get(case_id)
    def summary(self):
        by_status = {}
        for c in self._cases.values():
            by_status[c.status.value] = by_status.get(c.status.value, 0) + 1
        return {"annotators": len(self._annotators), "total_cases": len(self._cases),
                "by_status": by_status, "panel": ANNOTATORS_PER_DISPUTE,
                "majority": MAJORITY_REQUIRED}


_resolver = None
def get_dispute_resolver():
    global _resolver
    if _resolver is None:
        _resolver = DisputeResolver()
    return _resolver


if __name__ == "__main__":
    r = DisputeResolver()
    for aid, s, j in [("a1",100,"EU"),("a2",80,"US"),("a3",60,"AS"),("a4",50,"AF"),("a5",40,"SA"),("a6",30,"OC")]:
        assert r.register_annotator(aid, s, j)
    c = r.open_case("route1", "0xC", "0xR", "stale anchor", challenged_value=10_000)
    assert c.challenge_bond == 500.0
    for a, v in zip(c.selected_annotators, [Vote.NOT_GUILTY]*2 + [Vote.GUILTY]*3):
        assert r.cast_vote(c.case_id, a, v, "reviewed")
    assert r.get_case(c.case_id).status == DisputeStatus.RESOLVED_GUILTY
    print("BTCP Module 2.19 — ALL TESTS PASS")
