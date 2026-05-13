"""
TRION Protocol — ANIMA Data Stream Architecture
Part 8.2: Complete ANIMA Data Architecture (4 streams)

Stream 1: Onchain Behavioral
  Token flow patterns, wallet activation sequences, protocol interaction graphs,
  MEV activity patterns, governance participation sequences, liquidity migration,
  cross-protocol composability events.

Stream 2: Structured Offchain
  SEC EDGAR filings (Form 4, 8-K, 13F), patent applications, regulatory filings
  (MAS Singapore, FCA UK, ESMA EU, CFTC/SEC US), corporate hiring data, M&A
  filings, earnings transcripts.

Stream 3: Unstructured NLP (50+ languages)
  Developer repository activity (commit velocity, contributor growth, issue
  resolution rate), academic preprint servers, technical forums, news and media
  with source credibility weighting.

Stream 4: Biological + Ecological
  BC signals (L6.1), XSL signals (L9.1), BRT correlations (L6.2) — cross-domain
  signals invisible to finance-only oracles.

Author: TRION Protocol — Originator: Hudu Yusuf (Analys)
License: CC0
"""

from __future__ import annotations

import time
from dataclasses import dataclass, field
from typing import Dict, List, Optional


# ── Stream 1: Onchain Behavioral ──────────────────────────────────────────────

@dataclass
class OnchainBehavioralSnapshot:
    """
    Real-time onchain behavioral signal aggregation.
    Sourced from: TRION EVM/SVM/NVM indexers.
    """
    entity_id:                      str
    block_number:                   int
    timestamp:                      float

    # Token flow patterns
    inflow_volume_30d:              float   # USD
    outflow_volume_30d:             float   # USD
    net_flow_direction:             float   # [-1, 1] — negative = outflow dominated
    flow_entropy:                   float   # Shannon entropy of flow distribution

    # Wallet activation sequences
    wallet_cluster_score:           float   # [0, 1] — clustering density
    wallet_activation_velocity:     float   # New wallets/block
    beo_cluster_size:               int     # BEO-resolved entity cluster size

    # Protocol interaction graph
    protocol_diversity:             float   # H(protocol_interaction_types)
    cross_protocol_flow:            float   # [0, 1] — cross-protocol composability

    # MEV patterns
    mev_rate_30d:                   float   # Extracted value / total volume
    mev_bot_cluster_size:           int
    sandwich_frequency:             float   # [0, 1]

    # Governance
    governance_participation_rate:  float   # [0, 1]
    voter_concentration_hhi:        float   # HHI of governance participation
    proposal_velocity:              float   # Proposals per week

    # Liquidity migration
    lp_migration_rate:              float   # [0, 1] — fraction migrating/week
    lp_origin_diversity:            float   # [0, 1] — Sybil LP detection inverse

    # Composability
    cross_protocol_composability:   float   # [0, 1]

    def to_feature_dict(self) -> Dict[str, float]:
        return {
            "wallet_clustering":         self.wallet_cluster_score,
            "volume_trend":              max(0.0, self.net_flow_direction + 1) / 2,
            "mev_rate":                  self.mev_rate_30d,
            "holding_concentration":     1.0 - (self.lp_origin_diversity or 0.5),
            "governance_activity":       self.governance_participation_rate,
            "voter_concentration":       self.voter_concentration_hhi / 10000,
            "protocol_diversity":        self.protocol_diversity,
            "cross_protocol_flow":       self.cross_protocol_flow,
            "wallet_activation_velocity": min(1.0, self.wallet_activation_velocity / 100.0),
            "lp_migration_rate":         self.lp_migration_rate,
            "sandwich_frequency":        self.sandwich_frequency,
            "flow_entropy":              self.flow_entropy,
        }


# ── Stream 2: Structured Offchain ─────────────────────────────────────────────

@dataclass
class StructuredOffchainSignal:
    """
    Structured offchain data signal from regulatory/institutional sources.
    Credibility-weighted by source_credibility.py.
    """
    source_id:          str
    source_type:        str   # SEC_EDGAR, REGULATORY, PATENT, CORPORATE
    jurisdiction:       str
    timestamp:          float

    # Signal value: normalized strength of the signal [0, 1]
    signal_strength:    float

    # Type-specific fields
    filing_type:        Optional[str] = None    # 8-K, 13F, Form-4, etc.
    jurisdiction_code:  Optional[str] = None    # ISO 3166
    patent_domain:      Optional[str] = None
    corporate_sector:   Optional[str] = None

    # Credibility (set by source_credibility.py)
    source_cred:        float = 0.50

    def feature_contribution(self) -> Dict[str, float]:
        """Feature vector contribution for pattern matching."""
        features = {
            "institutional_defi_exposure": self.signal_strength * (self.source_cred ** 0.5),
            "regulatory_filing_count":     self.signal_strength if self.source_type == "REGULATORY" else 0.0,
            "patent_cluster_size":         self.signal_strength if self.source_type == "PATENT" else 0.0,
            "filing_frequency":            self.signal_strength * self.source_cred,
        }
        return features


# ── Stream 3: Unstructured NLP ────────────────────────────────────────────────

@dataclass
class NLPSignal:
    """
    NLP-derived signal from one language corpus and source type.
    50+ language coverage in full deployment.
    """
    language_code:      str    # ISO 639-1
    source_type:        str    # DEV_REPO, ACADEMIC, FORUM, NEWS, SOCIAL
    timestamp:          float

    # Sentiment and agreement
    sentiment_score:    float   # [0, 1] — positive behavioral sentiment
    confidence:         float   # [0, 1] — NLP model confidence
    source_count:       int     # Number of sources contributing

    # Source credibility (set by source_credibility.py)
    source_cred:        float = 0.40

    # Developer-specific (source_type == DEV_REPO)
    commit_velocity:    float = 0.0
    contributor_growth: float = 0.0
    issue_closure_rate: float = 0.0
    pr_merge_rate:      float = 0.0

    def feature_contribution(self) -> Dict[str, float]:
        features: Dict[str, float] = {
            f"{self.language_code}_sentiment": self.sentiment_score * self.source_cred,
        }
        if self.source_type == "DEV_REPO":
            features["commit_velocity"]        = self.commit_velocity
            features["contributor_growth"]     = self.contributor_growth
            features["issue_closure_rate"]     = self.issue_closure_rate
            features["pr_merge_rate"]          = self.pr_merge_rate
        return features


# ── Stream 4: Biological + Ecological ────────────────────────────────────────

@dataclass
class BiologicalEcologicalSignal:
    """
    Cross-domain signals from biological and ecological monitoring.
    Invisible to finance-only oracles — unique ANIMA advantage.
    """
    timestamp:  float

    # L6.2 BRT — Biological Rhythm Timer
    circadian_phase:            float   # [0, 1]
    ultradian_phase:            float   # [0, 1]
    lunar_phase:                float   # [0, 1]
    seasonal_phase:             float   # [0, 1]
    circadian_phase_deviation:  float   # Deviation from 24h baseline
    circadian_strength:         float   # Directional strength

    # L6.1 BC — Biological Capital
    bc_score:                   float   # [0, 1] ecosystem health
    bc_flow:                    float
    bc_resilience:              float
    bc_interdependence:         float

    # L9.1 XSL — Cross-Species Liquidity
    xsl_aggregate:              float   # [0, 1] ecosystem species aggregate
    xsl_keystone_score:         float   # Keystone species XSL
    xsl_decline_rate:           float   # Rate of XSL decline [0, 1]
    keystone_at_risk:           bool = False

    def feature_contribution(self) -> Dict[str, float]:
        return {
            "circadian_phase_deviation": self.circadian_phase_deviation,
            "circadian_strength":        self.circadian_strength,
            "ultradian_deviation":       abs(self.ultradian_phase - 0.5),
            "brt_anomaly_score":         max(self.circadian_phase_deviation, abs(self.ultradian_phase - 0.5)),
            "bc_score":                  self.bc_score,
            "bc_flow":                   self.bc_flow,
            "bc_resilience":             self.bc_resilience,
            "bc_interdependence":        self.bc_interdependence,
            "xsl_aggregate":             self.xsl_aggregate,
            "xsl_keystone_score":        self.xsl_keystone_score,
            "xsl_decline_rate":          self.xsl_decline_rate,
            "ecosystem_stress_index":    max(0.0, 1.0 - (self.bc_score + self.xsl_aggregate) / 2),
        }


# ── 4-Stream Aggregator ────────────────────────────────────────────────────────

@dataclass
class ANIMADataStreamBundle:
    """
    Complete 4-stream data bundle for one ANIMA computation cycle.
    All streams must be present. Missing streams degrade ANIMA quality.
    """
    entity_id:    str
    timestamp:    float
    block_number: int

    onchain:      Optional[OnchainBehavioralSnapshot]     = None
    offchain:     List[StructuredOffchainSignal]          = field(default_factory=list)
    nlp:          List[NLPSignal]                         = field(default_factory=list)
    biological:   Optional[BiologicalEcologicalSignal]   = None

    def streams_active(self) -> List[str]:
        active = []
        if self.onchain:      active.append("ONCHAIN")
        if self.offchain:     active.append("STRUCTURED_OFFCHAIN")
        if self.nlp:          active.append("NLP_UNSTRUCTURED")
        if self.biological:   active.append("BIOLOGICAL_ECOLOGICAL")
        return active

    def stream_completeness(self) -> float:
        """Fraction of 4 streams with data. Reduces ANIMA confidence when < 1.0."""
        return len(self.streams_active()) / 4.0

    def to_observation_dict(self) -> Dict[str, float]:
        """
        Merge all stream feature contributions into one observation dict.
        Used for pattern library coherence computation.
        """
        obs: Dict[str, float] = {}

        if self.onchain:
            obs.update(self.onchain.to_feature_dict())

        for sig in self.offchain:
            for k, v in sig.feature_contribution().items():
                obs[k] = max(obs.get(k, 0.0), v)

        for sig in self.nlp:
            for k, v in sig.feature_contribution().items():
                obs[k] = obs.get(k, 0.0) * 0.5 + v * 0.5  # blend

        if self.biological:
            obs.update(self.biological.feature_contribution())

        return obs

    def cross_source_agreement(self) -> float:
        """
        CA(t) = Σ_s CRED(s,t) · agreement(s,t) / Σ_s CRED(s,t)

        Computes cross-source agreement from all NLP signals using CRED weighting.
        Falls back to 0.5 if insufficient signals.
        """
        if len(self.nlp) < 2:
            return 0.5

        sentiments   = [s.sentiment_score for s in self.nlp]
        creds        = [s.source_cred for s in self.nlp]
        total_cred   = sum(creds)

        if total_cred <= 0:
            return 0.5

        weighted_mean = sum(s * c for s, c in zip(sentiments, creds)) / total_cred
        weighted_var  = sum(
            c * (s - weighted_mean) ** 2
            for s, c in zip(sentiments, creds)
        ) / total_cred

        import math
        weighted_std = math.sqrt(weighted_var)
        ca = max(0.0, 1.0 - weighted_std * 4.0)
        return min(1.0, ca)

    def historical_accuracy_score(
        self,
        prediction_history: List[float],
        outcome_history:    List[float],
        window_days:        int = 90,
    ) -> float:
        """
        HA = Historical Accuracy — rolling 90-day calibration score.
        HA < 0.70 → ANIMA output flagged.
        HA < 0.60 → A(t) = 0 (ANIMA disabled until recalibrated).
        """
        n = min(len(prediction_history), len(outcome_history))
        if n == 0:
            return 0.70  # Bootstrap assumption

        import math
        pairs = list(zip(prediction_history[-n:], outcome_history[-n:]))
        mae   = sum(abs(p - o) for p, o in pairs) / n
        # Normalize: MAE of 0 → HA=1.0, MAE of 0.5+ → HA=0.0
        ha = max(0.0, min(1.0, 1.0 - 2.0 * mae))
        return ha


# ── Self-test ─────────────────────────────────────────────────────────────────

if __name__ == "__main__":
    # Build a complete 4-stream bundle
    bundle = ANIMADataStreamBundle(
        entity_id="0xTEST",
        timestamp=time.time(),
        block_number=20_000_000,

        onchain=OnchainBehavioralSnapshot(
            entity_id="0xTEST", block_number=20_000_000, timestamp=time.time(),
            inflow_volume_30d=5_000_000, outflow_volume_30d=2_000_000,
            net_flow_direction=0.4, flow_entropy=0.75,
            wallet_cluster_score=0.80, wallet_activation_velocity=5.0, beo_cluster_size=12,
            protocol_diversity=0.70, cross_protocol_flow=0.55,
            mev_rate_30d=0.008, mev_bot_cluster_size=3, sandwich_frequency=0.05,
            governance_participation_rate=0.15, voter_concentration_hhi=1800.0, proposal_velocity=0.5,
            lp_migration_rate=0.12, lp_origin_diversity=0.72,
            cross_protocol_composability=0.60,
        ),

        offchain=[
            StructuredOffchainSignal(
                source_id="sec_edgar_001", source_type="SEC_EDGAR",
                jurisdiction="US", timestamp=time.time(),
                signal_strength=0.70, filing_type="13F",
                jurisdiction_code="US", source_cred=0.65,
            ),
        ],

        nlp=[
            NLPSignal("en", "DEV_REPO", time.time(), 0.72, 0.90, 500, source_cred=0.55,
                      commit_velocity=0.75, contributor_growth=0.60, issue_closure_rate=0.85, pr_merge_rate=0.78),
            NLPSignal("zh", "NEWS",     time.time(), 0.68, 0.80, 300, source_cred=0.40),
            NLPSignal("es", "FORUM",    time.time(), 0.75, 0.75, 200, source_cred=0.35),
            NLPSignal("ar", "NEWS",     time.time(), 0.65, 0.70, 100, source_cred=0.35),
            NLPSignal("ja", "NEWS",     time.time(), 0.70, 0.72, 150, source_cred=0.38),
        ],

        biological=BiologicalEcologicalSignal(
            timestamp=time.time(),
            circadian_phase=0.42, ultradian_phase=0.55, lunar_phase=0.30, seasonal_phase=0.75,
            circadian_phase_deviation=0.12, circadian_strength=0.65,
            bc_score=0.62, bc_flow=0.70, bc_resilience=0.55, bc_interdependence=0.65,
            xsl_aggregate=0.58, xsl_keystone_score=0.45, xsl_decline_rate=0.08,
            keystone_at_risk=False,
        ),
    )

    print(f"Active streams: {bundle.streams_active()}")
    print(f"Stream completeness: {bundle.stream_completeness():.2f}")

    obs = bundle.to_observation_dict()
    print(f"Feature dict: {len(obs)} features")

    ca = bundle.cross_source_agreement()
    print(f"Cross-source CA: {ca:.4f}")

    ha = bundle.historical_accuracy_score(
        prediction_history=[0.70, 0.72, 0.68, 0.74, 0.71],
        outcome_history   =[0.71, 0.70, 0.69, 0.72, 0.70],
    )
    print(f"Historical accuracy HA: {ha:.4f}")

    assert len(bundle.streams_active()) == 4
    assert bundle.stream_completeness() == 1.0
    assert len(obs) > 10

    print("ANIMA-DATA-STREAMS PASS — 4-stream architecture implemented")
