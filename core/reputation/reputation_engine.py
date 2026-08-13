"""
TRION Reputation & Credit Eligibility Engine
=============================================
On-chain behavioral reputation scoring via long-term coherence tracking.
Builds a reputation score for any address/entity based on:
  - Historical C(t) consistency
  - Manipulation fingerprint track record
  - Cross-chain behavioral consistency
  - Lifecycle stage trajectory
  - Governance participation quality
  - Credit eligibility (behavioral creditworthiness)

This is the foundation of the TRION Truth Financial Layer:
trustworthy, manipulation-resistant, behavior-based credit and reputation.
"""

import time
import math
import json
import os
from typing import Dict, List, Optional, Tuple
from dataclasses import dataclass, field, asdict
import numpy as np

_DATA_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "..", "data")
os.makedirs(_DATA_DIR, exist_ok=True)
REPUTATION_STORE_PATH = os.path.join(_DATA_DIR, "trion_reputation_state.json")


@dataclass
class ReputationRecord:
    entity_id: str
    created_at: int
    last_updated: int
    # Core scores
    reputation_score: float        # 0-1, overall behavioral reputation
    credit_score: float            # 0-1, creditworthiness
    trust_tier: str                # UNTRUSTED | PROBATION | TRUSTED | VERIFIED | EXEMPLARY
    # History
    coherence_history: List[float]
    manipulation_events: int       # number of detected MF events
    governance_votes: int          # quality governance participation
    cross_chain_consistency: float # how consistent behavior is across chains
    # Financial credit
    max_credit_usd: float          # estimated max trustworthy credit in USD
    repayment_score: float         # track record of "repaying" (e.g., returning borrowed funds)
    # Behavioral signals
    total_tx_count: int
    active_days: int
    avg_coherence: float
    peak_coherence: float
    min_coherence: float
    volatility: float              # std deviation of coherence
    # Consensus
    validator_endorsements: int    # how many validators have endorsed this entity
    dispute_count: int             # number of behavioral disputes raised


TRUST_TIERS = {
    "UNTRUSTED": {"min_score": 0.0, "max_credit_usd": 0, "color": "#e74c3c"},
    "PROBATION": {"min_score": 0.2, "max_credit_usd": 1_000, "color": "#e67e22"},
    "TRUSTED":   {"min_score": 0.5, "max_credit_usd": 50_000, "color": "#f1c40f"},
    "VERIFIED":  {"min_score": 0.70, "max_credit_usd": 500_000, "color": "#2ecc71"},
    "EXEMPLARY": {"min_score": 0.88, "max_credit_usd": 10_000_000, "color": "#3498db"},
}


class ReputationEngine:

    def __init__(self):
        self._store: Dict[str, ReputationRecord] = {}
        self._load_store()

    def _load_store(self):
        try:
            if os.path.exists(REPUTATION_STORE_PATH):
                with open(REPUTATION_STORE_PATH) as f:
                    raw = json.load(f)
                for eid, data in raw.items():
                    self._store[eid] = ReputationRecord(**data)
        except Exception:
            pass

    def _save_store(self):
        try:
            out = {eid: asdict(r) for eid, r in self._store.items()}
            with open(REPUTATION_STORE_PATH, "w") as f:
                json.dump(out, f)
        except Exception:
            pass

    def _classify_trust_tier(self, score: float, active_days: int) -> str:
        if score >= 0.88 and active_days >= 365:
            return "EXEMPLARY"
        elif score >= 0.70 and active_days >= 90:
            return "VERIFIED"
        elif score >= 0.50 and active_days >= 30:
            return "TRUSTED"
        elif score >= 0.20:
            return "PROBATION"
        return "UNTRUSTED"

    def _compute_credit_score(self, record: ReputationRecord) -> float:
        if record.active_days < 7:
            return 0.05

        # Weighted components (like FICO but behavioral)
        components = [
            record.avg_coherence * 0.35,                         # payment history analog
            record.cross_chain_consistency * 0.20,               # consistency
            min(1.0, record.active_days / 365.0) * 0.15,        # account age
            (1.0 - record.volatility) * 0.15,                    # stability
            min(1.0, record.validator_endorsements / 10.0) * 0.10, # community validation
            max(0.0, 1.0 - record.manipulation_events * 0.1) * 0.05,  # clean history
        ]

        credit = sum(components)

        # Dispute penalty
        if record.dispute_count > 0:
            credit *= max(0.5, 1.0 - record.dispute_count * 0.15)

        return round(min(1.0, max(0.0, credit)), 4)

    def _compute_max_credit(self, credit_score: float, total_tx: int,
                             active_days: int) -> float:
        if credit_score < 0.2:
            return 0.0
        # Base credit from score
        base = 10 ** (credit_score * 7)  # $10 to $10M range
        # Activity multiplier
        activity_mult = min(3.0, math.log1p(total_tx) / math.log1p(10000))
        age_mult = min(2.0, active_days / 180.0)
        return round(min(10_000_000, base * activity_mult * age_mult), 2)

    def record_observation(
        self,
        entity_id: str,
        coherence: float,
        manipulation_score: float = 0.0,
        chain_ids: Optional[List[int]] = None,
        governance_voted: bool = False,
        tx_count: int = 0,
    ) -> Dict:
        now = int(time.time())

        if entity_id not in self._store:
            self._store[entity_id] = ReputationRecord(
                entity_id=entity_id,
                created_at=now,
                last_updated=now,
                reputation_score=0.5,
                credit_score=0.1,
                trust_tier="PROBATION",
                coherence_history=[],
                manipulation_events=0,
                governance_votes=0,
                cross_chain_consistency=0.5,
                max_credit_usd=0.0,
                repayment_score=0.5,
                total_tx_count=0,
                active_days=0,
                avg_coherence=coherence,
                peak_coherence=coherence,
                min_coherence=coherence,
                volatility=0.0,
                validator_endorsements=0,
                dispute_count=0,
            )

        r = self._store[entity_id]

        # Update coherence history
        r.coherence_history.append(round(coherence, 4))
        if len(r.coherence_history) > 1000:
            r.coherence_history = r.coherence_history[-1000:]

        # Update stats
        hist = r.coherence_history
        r.avg_coherence = round(sum(hist) / len(hist), 4)
        r.peak_coherence = round(max(hist), 4)
        r.min_coherence = round(min(hist), 4)
        r.volatility = round(float(np.std(hist)), 4) if len(hist) > 1 else 0.0

        # Manipulation penalty
        if manipulation_score > 0.5:
            r.manipulation_events += 1

        # Governance participation
        if governance_voted:
            r.governance_votes += 1

        # Transaction count
        r.total_tx_count += tx_count

        # Active days
        days_since_creation = (now - r.created_at) / 86400.0
        r.active_days = round(days_since_creation, 1)

        # Cross-chain consistency (multi-chain presence is positive)
        if chain_ids and len(chain_ids) > 1:
            r.cross_chain_consistency = min(1.0, r.cross_chain_consistency + 0.02)

        # Reputation score: weighted average of key factors
        r.reputation_score = round(
            r.avg_coherence * 0.50 +
            (1.0 - r.volatility) * 0.20 +
            r.cross_chain_consistency * 0.15 +
            min(1.0, r.active_days / 365) * 0.15, 4
        )
        if r.manipulation_events > 0:
            r.reputation_score *= max(0.3, 1.0 - r.manipulation_events * 0.05)
        if r.dispute_count > 0:
            r.reputation_score *= max(0.5, 1.0 - r.dispute_count * 0.10)
        r.reputation_score = round(r.reputation_score, 4)

        # Credit score
        r.credit_score = self._compute_credit_score(r)
        r.max_credit_usd = self._compute_max_credit(r.credit_score, r.total_tx_count, r.active_days)
        r.trust_tier = self._classify_trust_tier(r.reputation_score, r.active_days)
        r.last_updated = now

        self._save_store()

        return {
            "entity_id": entity_id,
            "reputation_score": r.reputation_score,
            "credit_score": r.credit_score,
            "trust_tier": r.trust_tier,
            "max_credit_usd": r.max_credit_usd,
            "avg_coherence": r.avg_coherence,
            "observations": len(r.coherence_history),
        }

    def get_reputation(self, entity_id: str) -> Optional[Dict]:
        if entity_id not in self._store:
            return None
        r = self._store[entity_id]
        return {
            "entity_id": entity_id,
            "reputation_score": r.reputation_score,
            "credit_score": r.credit_score,
            "trust_tier": r.trust_tier,
            "tier_color": TRUST_TIERS.get(r.trust_tier, {}).get("color", "#666"),
            "max_credit_usd": r.max_credit_usd,
            "avg_coherence": r.avg_coherence,
            "peak_coherence": r.peak_coherence,
            "min_coherence": r.min_coherence,
            "volatility": r.volatility,
            "active_days": r.active_days,
            "total_tx_count": r.total_tx_count,
            "manipulation_events": r.manipulation_events,
            "governance_votes": r.governance_votes,
            "cross_chain_consistency": r.cross_chain_consistency,
            "validator_endorsements": r.validator_endorsements,
            "dispute_count": r.dispute_count,
            "observations": len(r.coherence_history),
            "last_updated": r.last_updated,
            "interpretation": self._interpret(r),
        }

    def _interpret(self, r: ReputationRecord) -> str:
        parts = [f"Trust tier: {r.trust_tier}."]
        parts.append(f"Reputation: {r.reputation_score:.3f}. Credit: {r.credit_score:.3f}.")
        if r.max_credit_usd > 0:
            parts.append(f"Max behavioral credit: ${r.max_credit_usd:,.0f}.")
        if r.manipulation_events > 0:
            parts.append(f"WARNING: {r.manipulation_events} manipulation event(s) on record.")
        if r.trust_tier in ("VERIFIED", "EXEMPLARY"):
            parts.append("This entity has demonstrated sustained behavioral integrity.")
        return " ".join(parts)

    def endorse(self, entity_id: str, endorser_id: str) -> Dict:
        r = self._store.get(entity_id)
        if not r:
            return {"error": "entity not found"}
        r.validator_endorsements += 1
        r.reputation_score = min(1.0, r.reputation_score + 0.005)
        self._save_store()
        return {"entity_id": entity_id, "endorsements": r.validator_endorsements}

    def dispute(self, entity_id: str, disputer_id: str, evidence: str) -> Dict:
        r = self._store.get(entity_id)
        if not r:
            return {"error": "entity not found"}
        r.dispute_count += 1
        r.reputation_score = max(0.0, r.reputation_score - 0.02)
        r.credit_score = max(0.0, r.credit_score - 0.03)
        self._save_store()
        return {"entity_id": entity_id, "disputes": r.dispute_count,
                "new_reputation": r.reputation_score}

    def leaderboard(self, top_n: int = 20) -> List[Dict]:
        ranked = sorted(
            self._store.values(),
            key=lambda r: r.reputation_score,
            reverse=True
        )[:top_n]
        return [
            {
                "rank": i + 1,
                "entity_id": r.entity_id,
                "reputation_score": r.reputation_score,
                "trust_tier": r.trust_tier,
                "avg_coherence": r.avg_coherence,
            }
            for i, r in enumerate(ranked)
        ]


_rep_engine: Optional[ReputationEngine] = None


def get_reputation_engine() -> ReputationEngine:
    global _rep_engine
    if _rep_engine is None:
        _rep_engine = ReputationEngine()
    return _rep_engine
