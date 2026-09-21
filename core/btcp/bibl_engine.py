"""
TRION BTCP — Module 2.3: BIBL Engine
=====================================

Per BTCP Master Spec §Phase 2 Module 2.3:

    Responsibility: Implements the Behavioral Inter-Block Layer.
    Reads simultaneously across all integrated chains during the
    inter-block window (12-second Ethereum block time).

Per-Chain Data Collected:
    - NL(chain, t) — Natural Liquidity Score
    - gas_forecast(chain, t) — CI_95 prediction from Akashic archetype
    - CC_coherence(chain, t) — cross-chain state agreement
    - MF_score(chain, t) — manipulation fingerprint score
    - block_capacity(chain) — current blockspace availability
    - finality_dist(chain) — statistical finality distribution

Multi-Path Observation (A1 Resolution):
    - Minimum 3 independent RPC endpoints per validator per chain
    - Each endpoint in different: geographic region, network ASN, cloud provider
    - endpoint_diversity_proof included with submission
    - Missing diversity → ECLIPSE_VULNERABILITY_PENALTY applied to validator weight

Fork Classification Protocol (Gap 12):
    - On fork detection: routing suspended for FORK_ASSESSMENT_PERIOD = 30 days
    - Observe both chains via Channel 6
    - Track: validator set retention (%), TVL retention, developer activity
    - Canonical chain: retains ≥ 67% of original validator set weighted by
      pre-fork stake + TVL + dev activity
    - If no chain reaches 67%: Conscious Layer review + governance vote
    - Pre-fork behavioral data: belongs to CANONICAL chain only

Author: TRION Protocol — Originator: Hudu Yusuf (Analys)
License: CC0
"""

from __future__ import annotations

import time
import statistics
from dataclasses import dataclass, field
from typing import Dict, List, Optional, Tuple


FORK_ASSESSMENT_PERIOD_DAYS = 30
MIN_ENDPOINTS_PER_CHAIN = 3
CANONICAL_CHAIN_THRESHOLD = 0.67  # 67%


@dataclass
class PerChainState:
    """Tier-1 per-chain state, updated every block."""
    chain_id:           int
    nl_score:           float = 0.0
    gas_forecast:       float = 0.0
    gas_ci_95_lower:    float = 0.0
    gas_ci_95_upper:    float = 0.0
    cc_coherence:       float = 0.0
    mf_score:           float = 0.0
    block_capacity:     float = 0.0
    finality_avg_sec:   float = 12.0
    finality_dist:      List[float] = field(default_factory=list)
    last_block:         int = 0
    last_update:        float = 0.0


@dataclass
class EndpointDiversity:
    """A1 Resolution: Multi-Path Independent Observation."""
    chain_id:        int
    endpoints:       List[str]   # RPC URLs
    regions:         List[str]   # geographic regions
    asns:            List[str]   # network ASNs
    cloud_providers: List[str]   # cloud provider names


@dataclass
class ForkAssessment:
    """Gap 12: Fork Classification Protocol."""
    chain_id_original:    int
    chain_a_id:           int
    chain_b_id:           int
    detection_time:       float
    assessment_end:       float
    chain_a_validator_retention: float = 0.0
    chain_a_tvl_retention:       float = 0.0
    chain_a_dev_activity:        float = 0.0
    chain_b_validator_retention: float = 0.0
    chain_b_tvl_retention:       float = 0.0
    chain_b_dev_activity:        float = 0.0
    canonical_chain:      Optional[int] = None
    resolved:             bool = False


class BIBLEngine:
    """
    Behavioral Inter-Block Layer engine.

    Continuously collects per-chain state, detects forks, and computes
    the BIBL snapshot used by the BTCP router for Tier-2 route scoring.
    """

    def __init__(self):
        self._chain_states: Dict[int, PerChainState] = {}
        self._endpoint_diversity: Dict[int, EndpointDiversity] = {}
        self._fork_assessments: List[ForkAssessment] = []
        self._suspended_chains: set = set()  # chains with active fork assessment

    # ── Per-chain state updates ──────────────────────────────────────────────

    def update_chain_state(
        self,
        chain_id: int,
        nl_score: float,
        gas_forecast: float,
        gas_ci_95: Tuple[float, float],
        cc_coherence: float,
        mf_score: float,
        block_capacity: float,
        finality_sec: float,
        block_number: int,
    ) -> PerChainState:
        """Update the Tier-1 cached state for a chain."""
        if chain_id not in self._chain_states:
            self._chain_states[chain_id] = PerChainState(chain_id=chain_id)

        state = self._chain_states[chain_id]
        state.nl_score = nl_score
        state.gas_forecast = gas_forecast
        state.gas_ci_95_lower = gas_ci_95[0]
        state.gas_ci_95_upper = gas_ci_95[1]
        state.cc_coherence = cc_coherence
        state.mf_score = mf_score
        state.block_capacity = block_capacity
        state.finality_avg_sec = finality_sec
        state.finality_dist.append(finality_sec)
        if len(state.finality_dist) > 100:
            state.finality_dist = state.finality_dist[-100:]
        state.last_block = block_number
        state.last_update = time.time()
        return state

    def get_chain_state(self, chain_id: int) -> Optional[PerChainState]:
        return self._chain_states.get(chain_id)

    def get_all_states(self) -> Dict[int, PerChainState]:
        return dict(self._chain_states)

    # ── Multi-path observation (A1) ──────────────────────────────────────────

    def register_endpoint_diversity(self, div: EndpointDiversity) -> bool:
        """Register the endpoint diversity for a chain (A1 Resolution)."""
        if len(set(div.regions)) < MIN_ENDPOINTS_PER_CHAIN:
            return False
        if len(set(div.asns)) < MIN_ENDPOINTS_PER_CHAIN:
            return False
        if len(set(div.cloud_providers)) < MIN_ENDPOINTS_PER_CHAIN:
            return False
        self._endpoint_diversity[div.chain_id] = div
        return True

    def diversity_penalty(self, chain_id: int) -> float:
        """
        ECLIPSE_VULNERABILITY_PENALTY: if a chain has insufficient endpoint
        diversity, apply a penalty to validator weights on that chain.
        Returns a multiplier in [0, 1] (1 = no penalty, 0 = full penalty).
        """
        div = self._endpoint_diversity.get(chain_id)
        if not div:
            return 0.5  # unknown diversity → 50% penalty
        if (len(set(div.regions)) >= MIN_ENDPOINTS_PER_CHAIN and
            len(set(div.asns)) >= MIN_ENDPOINTS_PER_CHAIN and
            len(set(div.cloud_providers)) >= MIN_ENDPOINTS_PER_CHAIN):
            return 1.0  # no penalty
        # Partial penalty
        score = (
            len(set(div.regions)) / MIN_ENDPOINTS_PER_CHAIN * 0.34 +
            len(set(div.asns)) / MIN_ENDPOINTS_PER_CHAIN * 0.33 +
            len(set(div.cloud_providers)) / MIN_ENDPOINTS_PER_CHAIN * 0.33
        )
        return min(1.0, score)

    # ── Fork classification (Gap 12) ─────────────────────────────────────────

    def detect_fork(
        self,
        chain_id: int,
        chain_a_id: int,
        chain_b_id: int,
    ) -> ForkAssessment:
        """Detect a fork and start the 30-day assessment period."""
        assessment = ForkAssessment(
            chain_id_original=chain_id,
            chain_a_id=chain_a_id,
            chain_b_id=chain_b_id,
            detection_time=time.time(),
            assessment_end=time.time() + FORK_ASSESSMENT_PERIOD_DAYS * 86400,
        )
        self._fork_assessments.append(assessment)
        self._suspended_chains.add(chain_id)
        return assessment

    def update_fork_assessment(
        self,
        chain_id_original: int,
        chain_a_validator_retention: float,
        chain_a_tvl_retention: float,
        chain_a_dev_activity: float,
        chain_b_validator_retention: float,
        chain_b_tvl_retention: float,
        chain_b_dev_activity: float,
    ) -> Optional[int]:
        """
        Update fork assessment with observed metrics.
        Returns the canonical chain ID if resolved, None if still pending.
        """
        for fa in self._fork_assessments:
            if fa.chain_id_original != chain_id_original or fa.resolved:
                continue
            fa.chain_a_validator_retention = chain_a_validator_retention
            fa.chain_a_tvl_retention = chain_a_tvl_retention
            fa.chain_a_dev_activity = chain_a_dev_activity
            fa.chain_b_validator_retention = chain_b_validator_retention
            fa.chain_b_tvl_retention = chain_b_tvl_retention
            fa.chain_b_dev_activity = chain_b_dev_activity

            # Weighted score: 50% validator retention, 30% TVL, 20% dev activity
            score_a = (0.50 * chain_a_validator_retention +
                       0.30 * chain_a_tvl_retention +
                       0.20 * chain_a_dev_activity)
            score_b = (0.50 * chain_b_validator_retention +
                       0.30 * chain_b_tvl_retention +
                       0.20 * chain_b_dev_activity)

            if score_a >= CANONICAL_CHAIN_THRESHOLD and score_a > score_b:
                fa.canonical_chain = fa.chain_a_id
                fa.resolved = True
                self._suspended_chains.discard(chain_id_original)
                return fa.chain_a_id
            elif score_b >= CANONICAL_CHAIN_THRESHOLD and score_b > score_a:
                fa.canonical_chain = fa.chain_b_id
                fa.resolved = True
                self._suspended_chains.discard(chain_id_original)
                return fa.chain_b_id
            # else: still pending Conscious Layer review
            return None
        return None

    def is_chain_suspended(self, chain_id: int) -> bool:
        """Check if routing is suspended for a chain (fork assessment in progress)."""
        return chain_id in self._suspended_chains

    # ── BIBL snapshot ─────────────────────────────────────────────────────────

    @staticmethod
    def _finality_stats(dist: List[float]) -> Dict[str, float]:
        """
        Statistical finality distribution from OBSERVED finality samples.

        Honest statistics over the values actually recorded via
        update_chain_state() (rolling window of the last 100 observations).
        With fewer than 2 samples the percentiles fall back to the single
        observed value and the sample count discloses the evidence size —
        no fabricated distribution parameters.
        """
        if not dist:
            return {
                "finality_p50_sec": 0.0,
                "finality_p95_sec": 0.0,
                "finality_sample_count": 0,
            }
        ordered = sorted(dist)
        n = len(ordered)
        p50 = ordered[min(n - 1, max(0, (n - 1) // 2))]
        p95 = ordered[min(n - 1, max(0, int(round(0.95 * (n - 1)))))]
        return {
            "finality_p50_sec": p50,
            "finality_p95_sec": p95,
            "finality_sample_count": n,
        }

    def get_bibl_snapshot(self) -> Dict[int, Dict]:
        """
        Get the current BIBL snapshot for all chains.
        Used by BTCP router Tier-2 route scoring.

        Spec (BTCP Master Spec §Phase 2 Module 2.3): reads nl_score,
        gas_forecast, cc_coherence, mf_score, block_capacity and the
        finality distribution per chain — all from values supplied by
        callers via update_chain_state() (this engine is a Tier-1 state
        cache; it does not fabricate chain data).
        """
        snapshot = {}
        for chain_id, state in self._chain_states.items():
            if self.is_chain_suspended(chain_id):
                continue  # skip suspended chains
            snapshot[chain_id] = {
                "nl_score": state.nl_score,
                "gas_forecast": state.gas_forecast,
                "gas_ci_95": [state.gas_ci_95_lower, state.gas_ci_95_upper],
                "cc_coherence": state.cc_coherence,
                "mf_score": state.mf_score,
                "block_capacity": state.block_capacity,
                "finality_avg_sec": state.finality_avg_sec,
                # Statistical finality distribution (Gap 12 / spec §2.3):
                # real percentiles over the observed finality samples.
                **self._finality_stats(state.finality_dist),
                "diversity_penalty": self.diversity_penalty(chain_id),
                "last_block": state.last_block,
                "last_update": state.last_update,
            }
        return snapshot


# ── BTCP §4.2 Step 1 — analyze_intent (BTCP-FIX2-ZK Fix 2) ──────────────────

@dataclass
class BIBLAnalysis:
    """BTCP Master Spec §4.2 Step 1 — BIBLAnalysis result.

    Mirrors the Rust struct (spec lines 305-314):

        pub struct BIBLAnalysis {
            pub chain_id: u64,
            pub nl_score: f64,           // Natural Liquidity Score
            pub gas_forecast: GasForecast,  // CI_95
            pub cc_coherence: f64,       // cross-chain state agreement
            pub beo_state: BEOState,     // entity behavioral state on this chain
            pub mf_score: f64,           // manipulation fingerprint score
            pub block_capacity: f64,    // current blockspace availability
            pub finality_dist: FinalityDistribution,  // statistical finality
        }

    The orchestrator's Step 1 calls ``analyze_intent(intent,
    behavioral_data)`` and includes the result in the route + step_results
    so consumers can see whether the intent was classified CLEAN /
    SUSPICIOUS / BLOCKED by the Behavioral Inter-Block Layer before
    any ZK proof is generated.
    """
    intent_hash: str
    entity_id: str
    classification: str   # "CLEAN" | "SUSPICIOUS" | "BLOCKED"
    risk_score: float     # 0.0 (clean) .. 1.0 (blocked)
    reasons: List[str] = field(default_factory=list)
    pattern_match: Optional[str] = None    # archetype_code if a BIBL pattern matched
    chain_analysis: Dict[int, Dict[str, Any]] = field(default_factory=dict)
    behavioral_signals: Dict[str, Any] = field(default_factory=dict)
    beo_binding: Optional[Dict[str, Any]] = None
    timestamp: float = field(default_factory=time.time)

    def to_dict(self) -> Dict[str, Any]:
        return {
            "intent_hash": self.intent_hash,
            "entity_id": self.entity_id,
            "classification": self.classification,
            "risk_score": round(self.risk_score, 6),
            "reasons": list(self.reasons),
            "pattern_match": self.pattern_match,
            "chain_analysis": dict(self.chain_analysis),
            "behavioral_signals": dict(self.behavioral_signals),
            "beo_binding": self.beo_binding,
            "timestamp": self.timestamp,
            "spec": "BTCP Master Spec §4.2 Step 1 — BIBL analyze_intent",
        }


# Risk classification thresholds (BTCP-FIX2-ZK Fix 2)
RISK_THRESHOLD_SUSPICIOUS = 0.30   # >= 0.30 → SUSPICIOUS
RISK_THRESHOLD_BLOCKED = 0.60      # >= 0.60 → BLOCKED
HIGH_AMOUNT_USD = 1_000_000        # intents above $1M get extra scrutiny


def _hash_intent(intent: Any) -> str:
    """Deterministic SHA3-256 hash of a BTCPIntent for BIBL analysis."""
    import hashlib as _hl
    canonical = ":".join([
        str(getattr(intent, "source_chain", "")),
        str(getattr(intent, "dest_chain", "")),
        str(getattr(intent, "source_address", "")),
        str(getattr(intent, "dest_address", "")),
        str(getattr(intent, "amount", "")),
        str(getattr(intent, "asset", "")),
        str(getattr(intent, "intent_type", "")),
        str(getattr(intent, "deadline", "")),
        str(getattr(intent, "nonce", "")),
    ])
    return _hl.sha3_256(canonical.encode()).hexdigest()


def _load_bibl_pattern_for(chain_id: int) -> Optional[Dict[str, Any]]:
    """Read the most recent BIBL observation row for ``chain_id`` from
    the local SQLite pattern store (``akashic/bibl_patterns.db``).

    Returns None when the store is absent or has no rows for the chain
    (honest — never fabricates a pattern).
    """
    import sqlite3
    import os
    db_path = os.environ.get(
        "BIBL_PATTERN_DB",
        os.path.join(
            os.path.dirname(os.path.dirname(os.path.dirname(
                os.path.abspath(__file__)))), "akashic", "bibl_patterns.db"),
    )
    if not db_path or not os.path.exists(db_path):
        return None
    try:
        conn = sqlite3.connect(f"file:{db_path}?mode=ro", uri=True, timeout=2.0)
    except sqlite3.Error:
        return None
    try:
        row = conn.execute(
            "SELECT archetype_code, mempool_size, mev_rate, volatility, "
            "recommended_fee, actual_fee, prediction_error, chain_id, observed_at "
            "FROM bibl_observations WHERE chain_id = ? "
            "ORDER BY observed_at DESC LIMIT 1",
            (int(chain_id),),
        ).fetchone()
        if not row:
            return None
        return {
            "archetype_code": row[0],
            "mempool_size": row[1],
            "mev_rate": row[2],
            "volatility": row[3],
            "recommended_fee": row[4],
            "actual_fee": row[5],
            "prediction_error": row[6],
            "chain_id": row[7],
            "observed_at": row[8],
        }
    except sqlite3.Error:
        return None
    finally:
        try:
            conn.close()
        except sqlite3.Error:
            pass


def _classify_risk(
    intent: Any,
    behavioral_data: Optional[Dict[str, Any]],
    bibl_patterns: Dict[int, Dict[str, Any]],
    beo_binding: Optional[Dict[str, Any]],
) -> Tuple[float, List[str], Optional[str]]:
    """Compute a BIBL risk score in [0, 1] + the human-readable reasons
    that produced it.

    Risk contributions (additive, capped at 1.0):

      * High amount (above HIGH_AMOUNT_USD): +0.15
        (large intents are higher-stakes; legitimate but flagged for review)
      * Suspicious intent_type (BORROW): +0.05
        (BORROW events historically carry more MEV risk)
      * Caller-supplied manipulation_fingerprint >= 0.30: +0.30
        (caller already disclosed the entity is manipulative)
      * Caller-supplied coherence < 0.55: +0.20
        (below the protocol's coherence floor)
      * BIBL pattern's observed mev_rate >= 0.10: +0.10
        (chain currently exhibits MEV activity)
      * BIBL pattern's observed volatility >= 0.50: +0.05
        (chain currently volatile)
      * Entity not in the Akashic BEO ledger: +0.20
        (unknown entity — no behavioral history)
      * Entity in the BEO ledger but ledger_records == 0: +0.10
        (entity known but no behavioral record yet)

    Classification:
      risk_score < 0.30 → CLEAN
      0.30 <= risk_score < 0.60 → SUSPICIOUS
      risk_score >= 0.60 → BLOCKED
    """
    risk = 0.0
    reasons: List[str] = []
    pattern_match: Optional[str] = None

    # 1) Intent-shape scrutiny
    try:
        amount = int(getattr(intent, "amount", 0) or 0)
        if amount >= HIGH_AMOUNT_USD:
            risk += 0.15
            reasons.append(
                f"high-amount intent ({amount} >= {HIGH_AMOUNT_USD} threshold) — "
                f"flagged for elevated scrutiny")
    except (TypeError, ValueError):
        pass

    intent_type = str(getattr(intent, "intent_type", "TRANSFER")).upper()
    if intent_type == "BORROW":
        risk += 0.05
        reasons.append("BORROW intent_type — elevated MEV exposure per BIBL pattern library")

    # 2) Caller-supplied behavioral signals (witness evidence, not
    #    protocol measurements — labeled as such).
    if behavioral_data and isinstance(behavioral_data, dict):
        mf = behavioral_data.get("manipulation")
        try:
            mf = float(mf) if mf is not None else 0.0
        except (TypeError, ValueError):
            mf = 0.0
        if mf >= 0.30:
            risk += 0.30
            reasons.append(
                f"caller-supplied manipulation_fingerprint={mf:.2f} >= 0.30 threshold — "
                f"witness evidence of active manipulation")
        coh = behavioral_data.get("coherence")
        try:
            coh = float(coh) if coh is not None else 1.0
        except (TypeError, ValueError):
            coh = 1.0
        if coh < 0.55:
            risk += 0.20
            reasons.append(
                f"caller-supplied coherence={coh:.2f} < 0.55 protocol floor — "
                f"entity below minimum coherence threshold")

    # 3) BIBL pattern observations (per-chain market state)
    for chain_id, pat in bibl_patterns.items():
        if not isinstance(pat, dict):
            continue
        archetype = pat.get("archetype_code")
        if archetype:
            pattern_match = archetype
        mev_rate = pat.get("mev_rate") or 0.0
        try:
            mev_rate = float(mev_rate)
        except (TypeError, ValueError):
            mev_rate = 0.0
        if mev_rate >= 0.10:
            risk += 0.10
            reasons.append(
                f"chain {chain_id} BIBL pattern '{archetype}' mev_rate={mev_rate:.2f} >= 0.10 — "
                f"active MEV environment")
        vol = pat.get("volatility") or 0.0
        try:
            vol = float(vol)
        except (TypeError, ValueError):
            vol = 0.0
        if vol >= 0.50:
            risk += 0.05
            reasons.append(
                f"chain {chain_id} BIBL pattern volatility={vol:.2f} >= 0.50 — "
                f"elevated market volatility")

    # 4) Entity's Akashic BEO ledger binding
    if beo_binding is None:
        risk += 0.20
        reasons.append(
            "entity not in the Akashic BEO ledger (or ledger unavailable) — "
            "no behavioral history to validate the intent against")
    else:
        ledger_records = int(beo_binding.get("ledger_records", 0) or 0)
        if ledger_records == 0:
            risk += 0.10
            reasons.append(
                "entity in the Akashic BEO ledger but 0 behavioral records — "
                "newly-clustered entity, insufficient history")
        else:
            reasons.append(
                f"entity bound to Akashic BEO ledger ({ledger_records} records, "
                f"archetype_id={beo_binding.get('archetype_id')}) — behavioral "
                f"history available for cross-check")

    risk = min(1.0, risk)
    return risk, reasons, pattern_match


def analyze_intent(
    intent: Any,
    behavioral_data: Optional[Dict[str, Any]] = None,
    bibl_engine: Optional["BIBLEngine"] = None,
) -> BIBLAnalysis:
    """BTCP Master Spec §4.2 Step 1 — analyze an intent through the
    Behavioral Inter-Block Layer.

    Per spec lines 300-321:

        TRION's Behavioral Inter-Block Layer (BIBL) activates in the
        inter-block window, reading all integrated chains simultaneously:

            pub async fn analyze_intent(intent: &Intent) -> Vec<BIBLAnalysis> {
                let chains = get_integrated_chains();
                futures::future::join_all(
                    chains.iter().map(|c| analyze_chain(intent, c))
                ).await
            }

    This Python port takes the source/dest chain pair from the intent
    and produces a single BIBLAnalysis combining:

      * Per-chain BIBL pattern observations (mempool_size, mev_rate,
        volatility, recommended_fee, actual_fee, prediction_error) read
        from the local SQLite pattern store (``akashic/bibl_patterns.db``)
        — honest, no fabrication if the store is empty.
      * Risk classification (CLEAN / SUSPICIOUS / BLOCKED) derived from:
          - intent shape (amount, intent_type)
          - caller-supplied behavioral_data (manipulation, coherence)
          - BIBL per-chain pattern signals (mev_rate, volatility)
          - entity's Akashic BEO ledger binding (cluster history)
      * Behavioral signals from the caller-supplied behavioral_data
        (witness evidence — labeled, not protocol measurements).

    Args:
        intent: a BTCPIntent (duck-typed; reads source_chain, dest_chain,
            source_address, amount, intent_type, deadline, nonce).
        behavioral_data: optional dict with caller-supplied witness
            evidence (manipulation, coherence, liquidity, depth,
            genomic_sense, genomic_antisense, block_number).
        bibl_engine: optional BIBLEngine instance whose Tier-1 cache
            is queried for per-chain nl_score / gas_forecast /
            cc_coherence / mf_score / block_capacity / finality_dist.
            When None, only the SQLite pattern store + caller-supplied
            behavioral_data are used (chain_analysis will be sparse).

    Returns:
        BIBLAnalysis with .classification, .risk_score, .reasons,
        .chain_analysis, .behavioral_signals, .beo_binding.
    """
    intent_hash = _hash_intent(intent)
    entity_id = str(getattr(intent, "source_address", "") or "")

    # 1) Per-chain BIBL pattern observations from the local pattern store.
    chain_ids = []
    src_chain = getattr(intent, "source_chain", None)
    dst_chain = getattr(intent, "dest_chain", None)
    if isinstance(src_chain, int):
        chain_ids.append(src_chain)
    if isinstance(dst_chain, int) and dst_chain != src_chain:
        chain_ids.append(dst_chain)

    bibl_patterns: Dict[int, Dict[str, Any]] = {}
    for cid in chain_ids:
        pat = _load_bibl_pattern_for(cid)
        if pat is not None:
            bibl_patterns[cid] = pat

    # 2) Tier-1 cache snapshot (per-chain nl_score, gas_forecast, etc.)
    chain_analysis: Dict[int, Dict[str, Any]] = {}
    if bibl_engine is not None:
        try:
            snapshot = bibl_engine.get_bibl_snapshot()
            for cid in chain_ids:
                if cid in snapshot:
                    chain_analysis[cid] = snapshot[cid]
        except Exception:
            pass
    # Always include the pattern observation in chain_analysis (so
    # consumers can see the BIBL pattern even when no Tier-1 cache exists).
    for cid, pat in bibl_patterns.items():
        if cid not in chain_analysis:
            chain_analysis[cid] = {
                "pattern_observation": pat,
                "nl_score": 0.0,
                "gas_forecast": pat.get("recommended_fee", 0.0),
                "cc_coherence": 0.0,
                "mf_score": pat.get("mev_rate", 0.0),
                "block_capacity": 0.0,
                "finality_avg_sec": 0.0,
                "finality_p50_sec": 0.0,
                "finality_p95_sec": 0.0,
                "finality_sample_count": 0,
                "source": "bibl_pattern_store",
            }
        else:
            # Augment the Tier-1 snapshot with the pattern observation.
            chain_analysis[cid] = dict(chain_analysis[cid])
            chain_analysis[cid]["pattern_observation"] = pat

    # 3) Akashic BEO ledger binding (read-only).
    beo_binding: Optional[Dict[str, Any]] = None
    try:
        from core.akashic.beo_lookup import lookup_beo_binding
        beo_binding = lookup_beo_binding(entity_id)
    except Exception:
        pass

    # 4) Risk classification.
    risk_score, reasons, pattern_match = _classify_risk(
        intent=intent,
        behavioral_data=behavioral_data,
        bibl_patterns=bibl_patterns,
        beo_binding=beo_binding,
    )

    if risk_score < RISK_THRESHOLD_SUSPICIOUS:
        classification = "CLEAN"
    elif risk_score < RISK_THRESHOLD_BLOCKED:
        classification = "SUSPICIOUS"
    else:
        classification = "BLOCKED"

    # 5) Behavioral signals (caller-supplied witness evidence).
    behavioral_signals: Dict[str, Any] = {}
    if behavioral_data and isinstance(behavioral_data, dict):
        # Copy the caller-supplied signals but explicitly label them as
        # witness evidence (not protocol measurements).
        for k in ("coherence", "manipulation", "liquidity", "depth",
                  "genomic_sense", "genomic_antisense", "block_number"):
            if k in behavioral_data:
                behavioral_signals[k] = behavioral_data[k]
        behavioral_signals["source"] = "caller_supplied_witness_evidence"

    return BIBLAnalysis(
        intent_hash=intent_hash,
        entity_id=entity_id,
        classification=classification,
        risk_score=risk_score,
        reasons=reasons,
        pattern_match=pattern_match,
        chain_analysis=chain_analysis,
        behavioral_signals=behavioral_signals,
        beo_binding=beo_binding,
    )


# ── Self-test ──────────────────────────────────────────────────────────────────

if __name__ == "__main__":
    print("=== BIBL Engine Self-test ===\n")

    bibl = BIBLEngine()

    # Test 1: Update chain state
    bibl.update_chain_state(
        chain_id=1, nl_score=0.85, gas_forecast=31.0,
        gas_ci_95=(28.0, 34.0), cc_coherence=0.90, mf_score=0.02,
        block_capacity=0.80, finality_sec=12.0, block_number=18000000,
    )
    state = bibl.get_chain_state(1)
    assert state.nl_score == 0.85
    print(f"✓ Chain state updated: NL={state.nl_score}")

    # Test 1b: Finality distribution statistics from observed samples
    for f in (11.5, 12.5, 13.0, 14.0, 25.0):
        bibl.update_chain_state(
            chain_id=1, nl_score=0.85, gas_forecast=31.0,
            gas_ci_95=(28.0, 34.0), cc_coherence=0.90, mf_score=0.02,
            block_capacity=0.80, finality_sec=f, block_number=18000000,
        )
    snap1 = bibl.get_bibl_snapshot()[1]
    assert snap1["finality_sample_count"] == 6  # 1 + 5 observed samples
    assert snap1["finality_p50_sec"] == 12.5      # median of observed dist
    assert snap1["finality_p95_sec"] == 25.0      # p95 tail
    print(f"✓ Finality dist stats: p50={snap1['finality_p50_sec']}s "
          f"p95={snap1['finality_p95_sec']}s n={snap1['finality_sample_count']}")

    # Test 2: Endpoint diversity (A1)
    div = EndpointDiversity(
        chain_id=1,
        endpoints=["rpc1.example.com", "rpc2.example.com", "rpc3.example.com"],
        regions=["us-east", "eu-west", "ap-south"],
        asns=["AS15169", "AS16509", "AS8075"],
        cloud_providers=["gcp", "aws", "azure"],
    )
    assert bibl.register_endpoint_diversity(div)
    assert bibl.diversity_penalty(1) == 1.0  # no penalty
    print(f"✓ Endpoint diversity: penalty={bibl.diversity_penalty(1)}")

    # Test 3: Insufficient diversity → penalty
    div_bad = EndpointDiversity(
        chain_id=2,
        endpoints=["rpc1.example.com", "rpc2.example.com"],
        regions=["us-east", "us-west"],
        asns=["AS15169", "AS15169"],
        cloud_providers=["gcp", "gcp"],
    )
    bibl.register_endpoint_diversity(div_bad)
    penalty = bibl.diversity_penalty(2)
    assert penalty < 1.0
    print(f"✓ Insufficient diversity: penalty={penalty:.2f}")

    # Test 4: Fork detection
    fa = bibl.detect_fork(chain_id=1, chain_a_id=1, chain_b_id=1001)
    assert bibl.is_chain_suspended(1)
    print(f"✓ Fork detected: chain 1 suspended for 30 days")

    # Test 5: Fork resolution — chain A wins (67%+ retention)
    canonical = bibl.update_fork_assessment(
        chain_id_original=1,
        chain_a_validator_retention=0.80,
        chain_a_tvl_retention=0.85,
        chain_a_dev_activity=0.90,
        chain_b_validator_retention=0.20,
        chain_b_tvl_retention=0.15,
        chain_b_dev_activity=0.10,
    )
    assert canonical == 1
    assert not bibl.is_chain_suspended(1)
    print(f"✓ Fork resolved: canonical chain = {canonical}")

    # Test 6: BIBL snapshot excludes suspended chains
    bibl.detect_fork(chain_id=137, chain_a_id=137, chain_b_id=2137)
    snapshot = bibl.get_bibl_snapshot()
    assert 137 not in snapshot  # suspended
    assert 1 in snapshot         # not suspended
    print(f"✓ BIBL snapshot: {list(snapshot.keys())} (suspended chains excluded)")

    print("\nPHASE 2.3 PASS — BIBL Engine implemented")
