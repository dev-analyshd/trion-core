"""
role_classifier.py — DeFi role detection from event_type patterns.

Maps the per-transaction event_type distribution of a SubEntity to one of
7 canonical DeFi roles. Each role has a characteristic fingerprint (dominant
event type + supporting context) that allows meaningful FAISS archetype
distance scoring for protocol participants.

Roles
-----
LIQUIDITY_PROVIDER  — LIQUIDITY dominates, steady magnitude, low SWAP ratio
BORROWER            — BORROW + STAKE cycles, moderate LIQUIDATE exposure
LIQUIDATOR          — LIQUIDATE spikes, FLASH_LOAN bursts, high magnitude
MEV_BOT             — MEV_CAPTURE dominant, ultra-high tx density, rapid timing
ARBITRAGEUR         — SWAP + BRIDGE, medium frequency, consistent magnitude
GOVERNANCE_ACTOR    — GOVERNANCE + PROPOSAL dominant, low tx count
TRADER              — SWAP dominant, moderate frequency, varied magnitude
UNKNOWN             — insufficient signal
"""

from __future__ import annotations
from enum import Enum
from dataclasses import dataclass

EVENT_SWAP       = "SWAP"
EVENT_LIQUIDITY  = "LIQUIDITY"
EVENT_BORROW     = "BORROW"
EVENT_LIQUIDATE  = "LIQUIDATE"
EVENT_GOVERNANCE = "GOVERNANCE"
EVENT_PROPOSAL   = "PROPOSAL"
EVENT_STAKE      = "STAKE"
EVENT_UNSTAKE    = "UNSTAKE"
EVENT_BRIDGE     = "BRIDGE"
EVENT_DEPLOY     = "DEPLOY"
EVENT_MINT       = "MINT"
EVENT_BURN       = "BURN"
EVENT_FLASH_LOAN = "FLASH_LOAN"
EVENT_MEV        = "MEV_CAPTURE"
EVENT_CLAIM      = "CLAIM"


class DeFiRole(str, Enum):
    LIQUIDITY_PROVIDER = "LIQUIDITY_PROVIDER"
    BORROWER           = "BORROWER"
    LIQUIDATOR         = "LIQUIDATOR"
    MEV_BOT            = "MEV_BOT"
    ARBITRAGEUR        = "ARBITRAGEUR"
    GOVERNANCE_ACTOR   = "GOVERNANCE_ACTOR"
    TRADER             = "TRADER"
    UNKNOWN            = "UNKNOWN"

    @property
    def archetype(self) -> str:
        return _ROLE_TO_ARCHETYPE[self]

    @property
    def risk_level(self) -> str:
        return _ROLE_RISK[self]

    @property
    def description(self) -> str:
        return _ROLE_DESC[self]


_ROLE_TO_ARCHETYPE: dict[DeFiRole, str] = {
    DeFiRole.LIQUIDITY_PROVIDER: "Innocent",
    DeFiRole.BORROWER:           "Sage",
    DeFiRole.LIQUIDATOR:         "Outlaw",
    DeFiRole.MEV_BOT:            "Jester",
    DeFiRole.ARBITRAGEUR:        "Hero",
    DeFiRole.GOVERNANCE_ACTOR:   "Lover",
    DeFiRole.TRADER:             "Regular",
    DeFiRole.UNKNOWN:            "Regular",
}

_ROLE_RISK: dict[DeFiRole, str] = {
    DeFiRole.LIQUIDITY_PROVIDER: "LOW",
    DeFiRole.BORROWER:           "MEDIUM",
    DeFiRole.LIQUIDATOR:         "MEDIUM",
    DeFiRole.MEV_BOT:            "HIGH",
    DeFiRole.ARBITRAGEUR:        "MEDIUM",
    DeFiRole.GOVERNANCE_ACTOR:   "LOW",
    DeFiRole.TRADER:             "LOW",
    DeFiRole.UNKNOWN:            "UNKNOWN",
}

_ROLE_DESC: dict[DeFiRole, str] = {
    DeFiRole.LIQUIDITY_PROVIDER: "Consistently provides liquidity; deposit/withdraw symmetry; stable magnitude",
    DeFiRole.BORROWER:           "Regular borrow/repay cycles with stable collateral behaviour",
    DeFiRole.LIQUIDATOR:         "Targets under-collateralised positions; flash loan bursts under market stress",
    DeFiRole.MEV_BOT:            "Extracts MEV via sandwich attacks, arbitrage, or front-running",
    DeFiRole.ARBITRAGEUR:        "Cross-venue price arbitrage; SWAP + BRIDGE pattern; consistent magnitude",
    DeFiRole.GOVERNANCE_ACTOR:   "Participates in governance via proposals and voting; rare, high-impact txs",
    DeFiRole.TRADER:             "Regular token swapper; moderate frequency; varied magnitude",
    DeFiRole.UNKNOWN:            "Insufficient transaction history for confident role assignment",
}


@dataclass
class RoleResult:
    role: DeFiRole
    confidence: float
    archetype: str
    risk_level: str
    description: str
    evidence: dict


class RoleClassifier:
    """
    Classifies a wallet's DeFi role from its event_type_counts dict.

    Usage:
        clf = RoleClassifier()
        result = clf.classify(event_type_counts, tx_count, magnitude_stats)
    """

    MIN_TX = 2

    def classify(
        self,
        event_type_counts: dict,
        tx_count: int = 0,
        magnitude_stats: dict | None = None,
        timing_density: float = 0.0,
    ) -> RoleResult:
        if tx_count < self.MIN_TX or not event_type_counts:
            return self._unknown(event_type_counts)

        total = sum(event_type_counts.values())
        freq = {k: v / total for k, v in event_type_counts.items()}
        mag = magnitude_stats or {}

        scores: dict[DeFiRole, float] = {role: 0.0 for role in DeFiRole}

        mev_ratio     = freq.get(EVENT_MEV, 0)
        flash_ratio   = freq.get(EVENT_FLASH_LOAN, 0)
        liq_ratio     = freq.get(EVENT_LIQUIDATE, 0)
        liquidity_rat = freq.get(EVENT_LIQUIDITY, 0)
        borrow_ratio  = freq.get(EVENT_BORROW, 0)
        swap_ratio    = freq.get(EVENT_SWAP, 0)
        bridge_ratio  = freq.get(EVENT_BRIDGE, 0)
        gov_ratio     = freq.get(EVENT_GOVERNANCE, 0) + freq.get(EVENT_PROPOSAL, 0)

        scores[DeFiRole.MEV_BOT] = (
            mev_ratio * 0.7
            + flash_ratio * 0.15
            + min(timing_density / 10.0, 0.15)
        )

        scores[DeFiRole.LIQUIDATOR] = (
            liq_ratio * 0.6
            + flash_ratio * 0.25
            + min(mag.get("p95", 0) * 0.15, 0.15)
        )

        scores[DeFiRole.LIQUIDITY_PROVIDER] = (
            liquidity_rat * 0.75
            + (1 - mag.get("std", 0.5)) * 0.10
            + min(1 - swap_ratio, 0.15)
        )

        scores[DeFiRole.BORROWER] = (
            borrow_ratio * 0.65
            + freq.get(EVENT_STAKE, 0) * 0.15
            + freq.get(EVENT_UNSTAKE, 0) * 0.10
            + (1 - liq_ratio) * 0.10
        )

        scores[DeFiRole.ARBITRAGEUR] = (
            swap_ratio * 0.40
            + bridge_ratio * 0.45
            + min(tx_count / 500.0, 0.15)
        ) * (1 - mev_ratio)

        scores[DeFiRole.GOVERNANCE_ACTOR] = (
            gov_ratio * 0.85
            + freq.get(EVENT_CLAIM, 0) * 0.15
        )

        scores[DeFiRole.TRADER] = (
            swap_ratio * 0.7
            + (1 - mev_ratio) * 0.15
            + (1 - liq_ratio) * 0.15
        ) * (1 - gov_ratio) * max(0.0, 1 - bridge_ratio * 0.8)

        scores[DeFiRole.UNKNOWN] = 0.0

        best_role = max(
            (r for r in scores if r != DeFiRole.UNKNOWN),
            key=lambda r: scores[r],
        )
        best_score = scores[best_role]

        if best_score < 0.15:
            best_role = DeFiRole.UNKNOWN
            best_score = 0.0

        confidence = min(best_score, 1.0)

        return RoleResult(
            role=best_role,
            confidence=round(confidence, 4),
            archetype=best_role.archetype,
            risk_level=best_role.risk_level,
            description=best_role.description,
            evidence={
                "dominant_event_ratio": round(freq.get(best_role.value.replace("_", ""), 0), 4),
                "tx_count": tx_count,
                "all_scores": {r.value: round(v, 4) for r, v in scores.items()},
                "event_frequencies": {k: round(v, 4) for k, v in freq.items()},
            },
        )

    def _unknown(self, counts: dict) -> RoleResult:
        return RoleResult(
            role=DeFiRole.UNKNOWN,
            confidence=0.0,
            archetype="Regular",
            risk_level="UNKNOWN",
            description=DeFiRole.UNKNOWN.description,
            evidence={"tx_count": sum(counts.values()) if counts else 0},
        )

    def classify_batch(
        self, sub_entities: list
    ) -> list:
        results = []
        for se in sub_entities:
            result = self.classify(
                se.event_type_counts,
                se.tx_count,
                se.magnitude_stats,
            )
            se.role = result.role.value
            results.append((se, result))
        return results
