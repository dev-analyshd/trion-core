"""
TRION Protocol — BTCP Module 2.19: Dispute Resolution (Conscious Layer)
Gap I: Behavioral Evidence Standard — 3-of-5 + stake-and-slash.
"""
from __future__ import annotations
import hashlib, sys, time
from dataclasses import dataclass, field
from enum import Enum
from typing import Dict, List, Optional

# Persistence (S7): annotators and cases survive restarts via the shared
# SQLite state store. The plain-name fallback covers direct script
# execution (``python core/btcp/dispute_resolution.py``) — the script's own
# directory is already on sys.path in that mode.
try:
    from .state_store import BtcpStateStore
except ImportError:  # pragma: no cover - direct script execution
    from state_store import BtcpStateStore


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

    def is_expired(self, now: Optional[float] = None) -> bool:
        """True if the 72h dispute window has elapsed since the case was opened.

        Per BTCP Master Spec §11 Gap I, a dispute MUST be resolved within
        DISPUTE_WINDOW_SECONDS (72h = 259 200 s) of being filed. Once the
        window elapses, the case auto-resolves IN FAVOR OF THE ROUTE — i.e.
        NOT_GUILTY — because the claimant failed to produce a 3-of-5
        majority in time. Closed cases never expire.
        """
        if self.status != DisputeStatus.OPEN:
            return False
        ts = now if now is not None else time.time()
        return (ts - self.opened_at) > DISPUTE_WINDOW_SECONDS

    def remaining_seconds(self, now: Optional[float] = None) -> float:
        """Seconds left in the dispute window; 0.0 if expired or closed."""
        if self.status != DisputeStatus.OPEN:
            return 0.0
        ts = now if now is not None else time.time()
        return max(0.0, DISPUTE_WINDOW_SECONDS - (ts - self.opened_at))


# ── Persistence (S7) ─────────────────────────────────────────────────────────
# Explicit row serialization: nested DisputeVoteRecord dataclasses and Enum
# values are not directly JSON-serializable, so conversion is written by hand.

ANNOTATOR_ROW_TYPE = "annotator_v1"
CASE_ROW_TYPE = "dispute_case_v1"


def _annotator_to_row(a: Annotator) -> Dict[str, object]:
    """Annotator → JSON-safe row dict for BtcpStateStore."""
    return {
        "annotator_id": a.annotator_id,
        "stake": a.stake,
        "jurisdiction": a.jurisdiction,
        "active": a.active,
    }


def _annotator_from_row(row: Dict[str, object]) -> Annotator:
    """Row dict → Annotator (inverse of _annotator_to_row)."""
    return Annotator(
        annotator_id=row["annotator_id"],
        stake=float(row["stake"]),
        jurisdiction=row.get("jurisdiction", "UNKNOWN"),
        active=bool(row.get("active", True)),
    )


def _case_to_row(c: DisputeCase) -> Dict[str, object]:
    """DisputeCase → JSON-safe row dict for BtcpStateStore."""
    return {
        "case_id":             c.case_id,
        "route_id":            c.route_id,
        "claimant":            c.claimant,
        "respondent":          c.respondent,
        "claim":               c.claim,
        "evidence_hashes":     list(c.evidence_hashes),
        "challenged_value":    c.challenged_value,
        "challenge_bond":      c.challenge_bond,
        "selected_annotators": list(c.selected_annotators),
        "votes": {
            aid: {
                "annotator_id": v.annotator_id,
                "vote": v.vote.value,
                "rationale_hash": v.rationale_hash,
                "timestamp": v.timestamp,
            }
            for aid, v in c.votes.items()
        },
        "status":          c.status.value,
        "opened_at":       c.opened_at,
        "resolved_at":     c.resolved_at,
        "resolution_note": c.resolution_note,
    }


def _case_from_row(row: Dict[str, object]) -> DisputeCase:
    """Row dict → DisputeCase (inverse of _case_to_row)."""
    votes = {
        aid: DisputeVoteRecord(
            annotator_id=v["annotator_id"],
            vote=Vote(v["vote"]),
            rationale_hash=v["rationale_hash"],
            timestamp=float(v["timestamp"]),
        )
        for aid, v in (row.get("votes") or {}).items()
    }
    return DisputeCase(
        case_id=row["case_id"],
        route_id=row["route_id"],
        claimant=row["claimant"],
        respondent=row["respondent"],
        claim=row["claim"],
        evidence_hashes=list(row.get("evidence_hashes") or []),
        challenged_value=float(row.get("challenged_value", 0.0)),
        challenge_bond=float(row.get("challenge_bond", 0.0)),
        selected_annotators=list(row.get("selected_annotators") or []),
        votes=votes,
        status=DisputeStatus(row.get("status", DisputeStatus.OPEN.value)),
        opened_at=float(row.get("opened_at", 0.0)),
        resolved_at=row.get("resolved_at"),
        resolution_note=row.get("resolution_note", ""),
    )


class DisputeResolver:
    """Conscious Layer 3-of-5 dispute resolution engine.

    Mutable state (annotators, cases) is write-through persisted to SQLite
    (S7): a restart reloads open/resolved cases instead of wiping them.

    ``state_db``: optional SQLite path (default: env TRION_STATE_DB, then
    ``db/btcp_state.db``; test-context constructions get an isolated temp
    store — see core/btcp/state_store.py).
    """

    def __init__(self, state_db: Optional[str] = None) -> None:
        self._store = BtcpStateStore(state_db)
        self._annotators: Dict[str, Annotator] = {}
        self._cases: Dict[str, DisputeCase] = {}
        self._load()

    # ── Persistence (S7) ────────────────────────────────────────────────

    def _load(self) -> None:
        """Load persisted annotators/cases into memory (bad rows skipped)."""
        for annotator_id, (type_tag, row) in self._store.get_annotators().items():
            if type_tag != ANNOTATOR_ROW_TYPE:
                continue
            try:
                self._annotators[annotator_id] = _annotator_from_row(row)
            except (KeyError, ValueError, TypeError):
                print(f"[btcp.dispute] skipping malformed persisted annotator "
                      f"{annotator_id!r}", file=sys.stderr)
        for case_id, (type_tag, row) in self._store.get_cases().items():
            if type_tag != CASE_ROW_TYPE:
                continue
            try:
                self._cases[case_id] = _case_from_row(row)
            except (KeyError, ValueError, TypeError):
                print(f"[btcp.dispute] skipping malformed persisted case "
                      f"{case_id!r}", file=sys.stderr)

    def _persist_annotator(self, annotator_id: str) -> None:
        a = self._annotators.get(annotator_id)
        if a is not None:
            self._store.save_annotator(annotator_id, _annotator_to_row(a), ANNOTATOR_ROW_TYPE)

    def _persist_case(self, case_id: str) -> None:
        c = self._cases.get(case_id)
        if c is not None:
            self._store.save_case(case_id, _case_to_row(c), CASE_ROW_TYPE)

    def reload(self) -> None:
        """Re-read persisted annotators/cases from SQLite, replacing memory."""
        self._annotators = {}
        self._cases = {}
        self._load()

    def register_annotator(self, annotator_id: str, stake: float, jurisdiction: str = "UNKNOWN") -> bool:
        if annotator_id in self._annotators:
            return False
        self._annotators[annotator_id] = Annotator(annotator_id, max(0.0, stake), jurisdiction)
        self._persist_annotator(annotator_id)
        return True

    def _select_annotators(self, exclude: set) -> List[str]:
        candidates = [a for a in self._annotators.values()
                      if a.active and a.annotator_id not in exclude]
        candidates.sort(key=lambda a: (-a.stake, a.annotator_id))
        return [a.annotator_id for a in candidates[:ANNOTATORS_PER_DISPUTE]]

    def open_case(self, route_id, claimant, respondent, claim,
                  evidence_hashes=None, challenged_value=0.0,
                  filed_at: Optional[float] = None) -> DisputeCase:
        """Open a new dispute case.

        ``filed_at`` (Gap D6 fix): the timestamp at which the dispute was
        filed. Defaults to ``time.time()`` (now) when not supplied. The 72h
        window (DISPUTE_WINDOW_SECONDS) is measured from this instant — see
        ``DisputeCase.is_expired`` / ``remaining_seconds``.
        """
        filed_ts = float(filed_at) if filed_at is not None else time.time()
        case_id = "DISPUTE-" + hashlib.sha3_256(
            f"{route_id}:{claimant}:{respondent}:{filed_ts}:{time.time_ns()}".encode()).hexdigest()[:16]
        case = DisputeCase(
            case_id=case_id, route_id=route_id, claimant=claimant, respondent=respondent,
            claim=claim, evidence_hashes=list(evidence_hashes or []),
            challenged_value=max(0.0, challenged_value),
            challenge_bond=(max(0.0, challenged_value) * CHALLENGE_BOND_BPS) / 10_000,
            selected_annotators=self._select_annotators({claimant, respondent}),
            opened_at=filed_ts)
        self._cases[case_id] = case
        self._persist_case(case_id)
        return case

    def _auto_resolve_expired(self, case: DisputeCase, now: Optional[float] = None) -> bool:
        """Gap D6 enforcement: if the 72h window elapsed, resolve the case
        IN FAVOR OF THE ROUTE (NOT_GUILTY) per spec §11 Gap I.

        Returns True if the case was auto-resolved, False otherwise.
        Idempotent: a closed case never re-resolves.
        """
        if case.status != DisputeStatus.OPEN:
            return False
        if not case.is_expired(now=now):
            return False
        case.status = DisputeStatus.RESOLVED_NOT_GUILTY
        case.resolved_at = time.time()
        case.resolution_note = (
            "72-hour dispute window (259200 seconds) elapsed without a "
            "3-of-5 majority — auto-resolved in favor of the route per "
            "spec \u00a711 Gap I (Gap D6 runtime enforcement)."
        )
        return True

    def resolve_expired_cases(self, now: Optional[float] = None) -> List[str]:
        """Scan all OPEN cases and auto-resolve any whose 72h window has
        elapsed. Returns the list of case_ids that were auto-resolved.
        Useful as a periodic sweep (e.g. on every dispute-resolution tick).
        """
        ts = now if now is not None else time.time()
        resolved: List[str] = []
        for case_id, case in list(self._cases.items()):
            if self._auto_resolve_expired(case, now=ts):
                self._persist_case(case_id)
                resolved.append(case_id)
        return resolved

    def cast_vote(self, case_id: str, annotator_id: str, vote: Vote, rationale: str) -> bool:
        case = self._cases.get(case_id)
        if case is None or case.status != DisputeStatus.OPEN:
            return False
        # Gap D6 runtime enforcement: refuse votes filed after the 72h window
        # has elapsed. The case is auto-resolved in favor of the route
        # (NOT_GUILTY) and the vote is rejected.
        if case.is_expired():
            self._auto_resolve_expired(case)
            self._persist_case(case_id)
            return False
        if annotator_id not in case.selected_annotators or annotator_id in case.votes:
            return False
        case.votes[annotator_id] = DisputeVoteRecord(
            annotator_id, vote, hashlib.sha3_256(rationale.encode()).hexdigest(), time.time())
        # Resolution triggers: (a) full 5-vote panel, (b) 3-of-5 majority,
        # or (c) panel EXHAUSTION — when fewer than 5 annotators were
        # selectable, the case must resolve once every panel member voted;
        # a short panel splitting 2-2 resolves DISMISSED instead of hanging
        # OPEN forever (previously DISMISSED was unreachable and short
        # panels deadlocked — INV-015, docs/security/CANONICAL_INVARIANTS.md).
        if (len(case.votes) >= ANNOTATORS_PER_DISPUTE
                or len(case.votes) >= len(case.selected_annotators)):
            self._resolve(case)
        elif case.guilty_votes >= MAJORITY_REQUIRED or case.not_guilty_votes >= MAJORITY_REQUIRED:
            self._resolve(case)
        self._persist_case(case_id)
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
    # Hermetic self-test DB (S7): persistence is exercised without touching
    # the shared production store.
    import os as _os
    import tempfile as _tempfile
    _db = _os.path.join(_tempfile.mkdtemp(prefix="btcp_dispute_selftest_"), "btcp_state.db")

    r = DisputeResolver(state_db=_db)
    for aid, s, j in [("a1",100,"EU"),("a2",80,"US"),("a3",60,"AS"),("a4",50,"AF"),("a5",40,"SA"),("a6",30,"OC")]:
        assert r.register_annotator(aid, s, j)
    c = r.open_case("route1", "0xC", "0xR", "stale anchor", challenged_value=10_000)
    assert c.challenge_bond == 500.0
    for a, v in zip(c.selected_annotators, [Vote.NOT_GUILTY]*2 + [Vote.GUILTY]*3):
        assert r.cast_vote(c.case_id, a, v, "reviewed")
    assert r.get_case(c.case_id).status == DisputeStatus.RESOLVED_GUILTY

    # Persistence (S7): a second resolver on the same DB sees the annotators
    # and the resolved case; reload() re-reads from SQLite.
    r2 = DisputeResolver(state_db=_db)
    assert len(r2._annotators) == 6
    assert r2.get_case(c.case_id).status == DisputeStatus.RESOLVED_GUILTY
    assert r2.get_case(c.case_id).guilty_votes == 3
    c2 = r2.open_case("route2", "0xC2", "0xR2", "wash trade")
    r.reload()
    assert r.get_case(c2.case_id) is not None  # reload picked up r2's write
    print("BTCP Module 2.19 — ALL TESTS PASS (incl. persistence)")

    # ── Gap D6: 72h dispute window runtime enforcement ──────────────────
    # Spec §11 Gap I: a dispute MUST be resolved within 72h (259 200 s) of
    # being filed. If the window elapses without a 3-of-5 majority, the
    # case auto-resolves IN FAVOR OF THE ROUTE (NOT_GUILTY).
    import time as _t
    now_ts = _t.time()
    # 1) File a dispute "73 hours ago" (just past the 72h window).
    expired_filed_at = now_ts - (73 * 3600)
    c_exp = r.open_case("route_expired", "0xC", "0xR",
                        "stale anchor", challenged_value=10_000,
                        filed_at=expired_filed_at)
    # The case is OPEN immediately after filing, but is_expired() is True.
    assert c_exp.status == DisputeStatus.OPEN
    assert c_exp.is_expired() is True, "case filed 73h ago must be expired"
    assert c_exp.remaining_seconds() == 0.0
    # The filing timestamp is persisted on the case row.
    assert c_exp.opened_at == expired_filed_at
    # 2) cast_vote on an expired case must be refused AND trigger
    #    auto-resolution in favor of the route.
    first_annotator = c_exp.selected_annotators[0]
    accepted = r.cast_vote(c_exp.case_id, first_annotator, Vote.GUILTY, "late vote")
    assert accepted is False, "vote after 72h window must be rejected"
    assert r.get_case(c_exp.case_id).status == DisputeStatus.RESOLVED_NOT_GUILTY, \
        "expired dispute must auto-resolve in favor of the route (NOT_GUILTY)"
    assert "72-hour dispute window" in r.get_case(c_exp.case_id).resolution_note
    print("✓ Gap D6: expired case auto-resolves NOT_GUILTY (vote refused)")

    # 3) A fresh case is NOT expired and accepts votes normally.
    c_fresh = r.open_case("route_fresh", "0xC", "0xR", "stale anchor", challenged_value=1_000)
    assert c_fresh.is_expired() is False
    assert c_fresh.remaining_seconds() > 0.0
    # 4) Bulk sweep: resolve_expired_cases finds expired OPEN cases.
    resolved_ids = r.resolve_expired_cases()
    assert c_exp.case_id in resolved_ids or \
           r.get_case(c_exp.case_id).status == DisputeStatus.RESOLVED_NOT_GUILTY
    # The fresh case must NOT be swept (still OPEN).
    assert r.get_case(c_fresh.case_id).status == DisputeStatus.OPEN
    print("✓ Gap D6: fresh case stays OPEN; sweep correctly distinguishes")
    print("BTCP Module 2.19 + Gap D6 — ALL TESTS PASS (72h runtime enforcement)")
