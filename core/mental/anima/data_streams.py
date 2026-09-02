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


# ── ANIMA Stream 3: Supported NLP Language Registry ───────────────────────────
# Whitepaper Section 8.2 / Channel 14: "1,000+ crawlers, 50+ languages"
# Full ISO 639-1 enumeration of all 54 supported languages.
# Crawlers are weighted by source credibility (CRED score per language corpus).

SUPPORTED_NLP_LANGUAGES: Dict[str, str] = {
    # ─── Tier 1: High-volume DeFi communities (CRED weight ≥ 0.80) ───────────
    "en": "English",          # 1.5B speakers — primary DeFi / dev corpus
    "zh": "Chinese",          # 1.1B speakers — Binance, Huobi, OKX ecosystem
    "es": "Spanish",          # 475M speakers — LatAm DeFi, Ethereum en español
    "ar": "Arabic",           # 370M speakers — MENA institutional DeFi
    "pt": "Portuguese",       # 260M speakers — Brazil crypto, Mercado Bitcoin
    "ru": "Russian",          # 255M speakers — TON, Telegram, CIS validators
    "ja": "Japanese",         # 125M speakers — Ethereum Japan, GMO, bitFlyer
    "ko": "Korean",           # 82M speakers  — Klaytn, KAIA, Kakao DeFi
    "fr": "French",           # 300M speakers — Société Générale DeFi, DFNS

    # ─── Tier 2: Emerging DeFi regions (CRED weight 0.60–0.79) ──────────────
    "de": "German",           # 100M speakers — EEA, Gnosis Chain, Unstoppable
    "tr": "Turkish",          # 84M speakers  — Avalanche community
    "vi": "Vietnamese",       # 98M speakers  — Axie Infinity, Ronin origins
    "id": "Indonesian",       # 270M speakers — Tokocrypto, Indodax ecosystem
    "hi": "Hindi",            # 600M speakers — India DeFi, WazirX community
    "th": "Thai",             # 60M speakers  — Kasikorn DeFi, Bitkub
    "pl": "Polish",           # 45M speakers  — Central EU crypto
    "uk": "Ukrainian",        # 45M speakers  — Polkadot/Kusama community
    "nl": "Dutch",            # 29M speakers  — ING blockchain, ABN DeFi
    "it": "Italian",          # 85M speakers  — Enel blockchain, TIM DeFi

    # ─── Tier 3: Active research and governance communities ──────────────────
    "sv": "Swedish",          # Klarna DeFi, Fingerprint Cards
    "da": "Danish",           # Chainalysis origins, Copenhagen FinTech
    "fi": "Finnish",          # Nokia blockchain
    "nb": "Norwegian",        # Aker BP DeFi, Equinor
    "cs": "Czech",            # Braiins (SlushPool), Czech blockchain hubs
    "sk": "Slovak",           # ESET security, Bratislava DeFi
    "hu": "Hungarian",        # Budapest DeFi scene
    "ro": "Romanian",         # Elrond/MultiversX origins
    "bg": "Bulgarian",        # Nexo Network origins
    "hr": "Croatian",         # Electrocoin, MyCryptoBank
    "sr": "Serbian",          # Bitcoin Balkan community
    "el": "Greek",            # IOTA, Hellenic blockchain
    "he": "Hebrew",           # Israeli blockchain unicorns, Fireblocks
    "fa": "Persian",          # Nobitex, IrCrypto
    "ur": "Urdu",             # Pakistan crypto community
    "bn": "Bengali",          # bKash blockchain, BD crypto

    # ─── Tier 4: High-growth and institutional expansion ─────────────────────
    "ms": "Malay",            # Malaysia DeFi, Luno ecosystem
    "tl": "Filipino",         # Coins.ph, Philippine DeFi
    "sw": "Swahili",          # M-Pesa blockchain, East Africa
    "am": "Amharic",          # Ethiopian CBDCs, telebirr DeFi
    "yo": "Yoruba",           # West African crypto communities
    "ha": "Hausa",            # Northern Nigeria DeFi
    "ig": "Igbo",             # Fintech Nigeria ecosystem
    "zu": "Zulu",             # South African crypto
    "af": "Afrikaans",        # SnapScan, Luno ZA
    "ta": "Tamil",            # India/Sri Lanka DeFi
    "te": "Telugu",           # Hyderabad blockchain hub
    "mr": "Marathi",          # Mumbai DeFi community
    "gu": "Gujarati",         # Ahmedabad blockchain, Indian exchange founders
    "ml": "Malayalam",        # Kerala blockchain mission

    # ─── Tier 5: Validator governance and academic research ──────────────────
    "ca": "Catalan",          # Barcelona DeFi labs
    "eu": "Basque",           # Bilbao blockchain center
    "cy": "Welsh",            # Cardiff University DLT research
    "ga": "Irish",            # Dublin blockchain cluster, Coinbase EU HQ
    "lt": "Lithuanian",       # Vilnius DeFi hub, FinTech Lithuania
    "lv": "Latvian",          # Riga DeFi scene
    "et": "Estonian",         # e-Estonia, Guardtime, Tagamets
    "sl": "Slovenian",        # Kraken EU HQ, Bitstamp origins
    "mk": "Macedonian",       # Balkans DeFi
    "sq": "Albanian",         # Eagle Coin, Balkans crypto
}

# Convenience list for iteration
SUPPORTED_LANGUAGE_CODES: List[str] = list(SUPPORTED_NLP_LANGUAGES.keys())

# Language tier weights — used by source_credibility.py CRED scoring
LANGUAGE_TIER_WEIGHTS: Dict[str, float] = {
    "en": 1.00, "zh": 0.95, "es": 0.88, "ar": 0.85, "pt": 0.83,
    "ru": 0.82, "ja": 0.90, "ko": 0.88, "fr": 0.80, "de": 0.78,
    "tr": 0.72, "vi": 0.70, "id": 0.68, "hi": 0.70, "th": 0.67,
    "pl": 0.65, "uk": 0.65, "nl": 0.72, "it": 0.70, "sv": 0.68,
    "da": 0.65, "fi": 0.65, "nb": 0.65, "cs": 0.62, "sk": 0.60,
    "hu": 0.60, "ro": 0.72, "bg": 0.65, "hr": 0.58, "sr": 0.58,
    "el": 0.62, "he": 0.75, "fa": 0.55, "ur": 0.55, "bn": 0.58,
    "ms": 0.62, "tl": 0.60, "sw": 0.55, "am": 0.50, "yo": 0.50,
    "ha": 0.48, "ig": 0.48, "zu": 0.50, "af": 0.55, "ta": 0.60,
    "te": 0.58, "mr": 0.55, "gu": 0.60, "ml": 0.55, "ca": 0.60,
    "eu": 0.55, "cy": 0.55, "ga": 0.58, "lt": 0.60, "lv": 0.58,
    "et": 0.62, "sl": 0.60, "mk": 0.52, "sq": 0.50,
}


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
    circadian_strength:         float   # Directional strength (0.0 = no observed evidence)

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
    # Honest BRT provenance: OBSERVED (circular stats from real timestamps)
    # vs CLOCK_FALLBACK (wall-clock — strength carries no evidence)
    brt_source:                 str = "CLOCK_FALLBACK"

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

        for nlp_sig in self.nlp:
            for k, v in nlp_sig.feature_contribution().items():
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



# ── ANIMA Data Aggregator ──────────────────────────────────────────────────────
# Wires the real external data source fetchers into a unified ANIMADataStreamBundle.
# Each fetcher lives in core/mental/anima/data_sources/*.py and is responsible
# for one external API (GitHub / arXiv / SEC EDGAR / news RSS / GBIF / IUCN).

@dataclass
class FetcherConfig:
    """
    Configuration for one ANIMA fetcher invocation.

    Maps the entity_id (typically an on-chain address or ticker) to the
    parameters each fetcher needs (e.g. CIK for SEC EDGAR, owner/repo for
    GitHub, region for GBIF).

    observed_timestamps: optional event timestamps for the entity (e.g.
        recent transaction times from the behavioral ledger). When supplied,
        the Stream-4 BRT circadian phase is derived from these observations
        via circular statistics (labeled OBSERVED) instead of wall-clock
        time (labeled CLOCK_FALLBACK).
    """
    entity_id:         str
    github_owner:      Optional[str] = None
    github_repo:       Optional[str] = None
    sec_cik:           Optional[str] = None
    sec_form_type:     Optional[str] = None
    ecological_region: str = "global"
    ecological_taxon_key: Optional[int] = None
    ecological_species:    Optional[List[str]] = None
    academic_max_results: int = 10
    observed_timestamps:   Optional[List[float]] = None
    news_ttl:          float = 300.0
    github_ttl:        float = 600.0
    arxiv_ttl:         float = 1800.0
    regulatory_ttl:    float = 900.0
    ecological_ttl:    float = 3600.0
    sec_edgar_ttl:     float = 600.0


class ANIMADataAggregator:
    """
    Orchestrates all ANIMA external data source fetchers and assembles the
    unified :class:`ANIMADataStreamBundle` for one entity / crawl cycle.

    Stream wiring:
      - Stream 1 (Onchain Behavioral): left to on-chain indexers (not wired here).
      - Stream 2 (Structured Offchain): SEC EDGAR adapter + Regulatory fetcher.
      - Stream 3 (Unstructured NLP): GitHub Activity + arXiv + News fetchers,
        with optional multilingual sentiment from anima-service/multilingual_sentiment.
      - Stream 4 (Biological + Ecological): GBIF + IUCN fetcher.

    Usage::

        agg = ANIMADataAggregator()
        cfg = FetcherConfig(
            entity_id="0xETH",
            github_owner="ethereum",
            github_repo="solidity",
            sec_cik="0000320193",
        )
        bundle = agg.build_bundle(cfg, block_number=18_000_000)

    Each fetcher is independent — a failure in one does not break the others.
    """

    def __init__(self, user_agent: Optional[str] = None):
        self._user_agent = user_agent
        # Lazy-load fetchers so the aggregator can be constructed even if
        # individual fetcher modules have import errors.
        self._gh = None
        self._arxiv = None
        self._reg = None
        self._eco = None
        self._sec = None
        self._news = None
        self._multilingual = None

    # ── Lazy fetcher accessors ───────────────────────────────────────────────

    def _github_fetcher(self):
        if self._gh is None:
            from core.mental.anima.data_sources import github_activity as _m
            self._gh = _m
        return self._gh

    def _arxiv_fetcher(self):
        if self._arxiv is None:
            from core.mental.anima.data_sources import academic as _m
            self._arxiv = _m
        return self._arxiv

    def _regulatory_fetcher(self):
        if self._reg is None:
            from core.mental.anima.data_sources import regulatory as _m
            self._reg = _m
        return self._reg

    def _ecological_fetcher(self):
        if self._eco is None:
            from core.mental.anima.data_sources import ecological as _m
            self._eco = _m
        return self._eco

    def _sec_edgar_fetcher(self):
        if self._sec is None:
            from core.mental.anima.data_sources import sec_edgar as _m
            self._sec = _m
        return self._sec

    def _news_fetcher(self):
        if self._news is None:
            from core.mental.anima.data_sources import news as _m
            self._news = _m
        return self._news

    def _multilingual_sentiment(self):
        if self._multilingual is None:
            try:
                # This module lives in anima-service; gracefully fall back if
                # anima-service is not on the import path.
                import sys
                import os
                svc_path = os.path.join(os.path.dirname(os.path.abspath(__file__)),
                                        "..", "..", "..", "anima-service")
                if svc_path not in sys.path:
                    sys.path.insert(0, svc_path)
                from multilingual_sentiment import score_text, detect_language
                self._multilingual = (score_text, detect_language)
            except Exception:
                self._multilingual = (None, None)
        return self._multilingual

    # ── Public API ──────────────────────────────────────────────────────────

    def build_bundle(
        self,
        cfg: FetcherConfig,
        block_number: int = 0,
        timestamp: Optional[float] = None,
    ) -> ANIMADataStreamBundle:
        """
        Build a complete ANIMADataStreamBundle from real external data.

        On-chain data (Stream 1) is left as None — it is filled in by the
        on-chain indexer layer (not the role of this aggregator).
        """
        ts = timestamp if timestamp is not None else time.time()
        entity_id = cfg.entity_id

        # ── Stream 2: Structured Offchain ──────────────────────────────────
        offchain_signals: List[StructuredOffchainSignal] = []
        offchain_signals.extend(self._fetch_sec_edgar(cfg, ts))
        offchain_signals.extend(self._fetch_regulatory(cfg, ts))

        # ── Stream 3: Unstructured NLP ─────────────────────────────────────
        nlp_signals: List[NLPSignal] = []
        nlp_signals.append(self._fetch_github(cfg, ts))
        nlp_signals.append(self._fetch_arxiv(cfg, ts))
        nlp_signals.append(self._fetch_news(cfg, ts))

        # ── Stream 4: Biological + Ecological ──────────────────────────────
        bio = self._fetch_ecological(cfg, ts)

        return ANIMADataStreamBundle(
            entity_id=entity_id,
            timestamp=ts,
            block_number=block_number,
            onchain=None,
            offchain=offchain_signals,
            nlp=nlp_signals,
            biological=bio,
        )

    # ── Per-stream builders ─────────────────────────────────────────────────

    def _fetch_sec_edgar(self, cfg: FetcherConfig, ts: float) -> List[StructuredOffchainSignal]:
        if not cfg.sec_cik:
            return []
        try:
            sig = self._sec_edgar_fetcher().compute_sec_edgar_signal(cik=cfg.sec_cik)
            count = int(sig.get("filing_count", 0) or 0)
            if count == 0:
                return []
            filings = sig.get("filings", []) or []
            form = filings[0].get("form_type", "10-K") if filings else "10-K"
            return [StructuredOffchainSignal(
                source_id=f"SEC_EDGAR_{cfg.sec_cik}", source_type="SEC_EDGAR",
                jurisdiction="US", timestamp=ts,
                signal_strength=min(1.0, 0.3 + 0.1 * count),
                filing_type=form, jurisdiction_code="US", source_cred=0.65)]
        except Exception:
            return []

    def _fetch_regulatory(self, cfg: FetcherConfig, ts: float) -> List[StructuredOffchainSignal]:
        try:
            sig = self._regulatory_fetcher().compute_regulatory_signal(
                query=cfg.entity_id or "blockchain cryptocurrency")
            filings = sig.get("filings", []) or []
            if not filings:
                return []
            count = int(sig.get("filing_count", len(filings)) or 0)
            return [StructuredOffchainSignal(
                source_id="REGULATORY_US", source_type="REGULATORY",
                jurisdiction="US", timestamp=ts,
                signal_strength=max(0.20, min(1.0, 0.3 + 0.07 * count)),
                filing_type="SEC_FTS", jurisdiction_code="US", source_cred=0.60)]
        except Exception:
            return []

    def _fetch_github(self, cfg: FetcherConfig, ts: float) -> NLPSignal:
        """Fetch GitHub repo activity → NLPSignal(source_type=DEV_REPO)."""
        if cfg.github_owner and cfg.github_repo:
            try:
                sig = self._github_fetcher().compute_github_signal(
                    owner=cfg.github_owner, repo=cfg.github_repo)
                n_events = int(sig.get("event_count", 0) or 0)
                event_types = sig.get("event_types", {}) or {}
                if n_events > 0:
                    pushes = event_types.get("PushEvent", 0)
                    pulls = event_types.get("PullRequestEvent", 0)
                    issues = event_types.get("IssuesEvent", 0) + event_types.get("IssueCommentEvent", 0)
                    activity = float(sig.get("activity_score", 0.0))
                    return NLPSignal(
                        language_code="en", source_type="DEV_REPO", timestamp=ts,
                        sentiment_score=min(1.0, 0.50 + 0.30 * activity),
                        confidence=min(1.0, n_events / 50.0),
                        source_count=n_events, source_cred=0.80,
                        commit_velocity=min(1.0, pushes / 20.0),
                        contributor_growth=float(sig.get("diversity_score", 0.0)),
                        issue_closure_rate=min(1.0, issues / 10.0),
                        pr_merge_rate=min(1.0, pulls / 10.0),
                    )
            except Exception:
                pass
        return NLPSignal(language_code="en", source_type="DEV_REPO", timestamp=ts,
                         sentiment_score=0.50, confidence=0.20, source_count=0, source_cred=0.40)

    def _fetch_arxiv(self, cfg: FetcherConfig, ts: float) -> NLPSignal:
        try:
            sig = self._arxiv_fetcher().compute_academic_signal(
                query=cfg.entity_id or "blockchain security")
            papers = int(sig.get("paper_count", 0) or 0)
            trend = float(sig.get("research_trend", 0.0) or 0.0)
            return NLPSignal(language_code="en", source_type="ACADEMIC", timestamp=ts,
                             sentiment_score=min(1.0, 0.50 + 0.25 * trend),
                             confidence=min(1.0, papers / 10.0),
                             source_count=papers, source_cred=0.45)
        except Exception:
            return NLPSignal(language_code="en", source_type="ACADEMIC", timestamp=ts,
                             sentiment_score=0.50, confidence=0.10, source_count=0, source_cred=0.30)

    def _fetch_news(self, cfg: FetcherConfig, ts: float) -> NLPSignal:
        try:
            sig = self._news_fetcher().compute_news_signal(query=cfg.entity_id or "")
            articles = int(sig.get("article_count", 0) or 0)
            avg = float(sig.get("avg_sentiment", 0.5) or 0.5)
            return NLPSignal(language_code="en", source_type="NEWS", timestamp=ts,
                             sentiment_score=avg,
                             confidence=min(1.0, articles / 50.0),
                             source_count=articles, source_cred=0.25)
        except Exception:
            return NLPSignal(language_code="en", source_type="NEWS", timestamp=ts,
                             sentiment_score=0.50, confidence=0.10, source_count=0, source_cred=0.25)

    def _fetch_ecological(self, cfg: FetcherConfig, ts: float) -> Optional[BiologicalEcologicalSignal]:
        try:
            query = cfg.ecological_species or cfg.ecological_region or "coral reef"
            sig = self._ecological_fetcher().compute_ecological_signal(species_query=query)
            # BRT phases: derived from the entity's observed event timestamps
            # when supplied (circular statistics, OBSERVED), otherwise
            # wall-clock (CLOCK_FALLBACK). Strength is honestly 0.0 without
            # observations — previously this call site silently fabricated a
            # default of 0.5 via dict.get().
            from core.extended.biological_rhythm import get_brt_dict
            brt = get_brt_dict(ts, observed_timestamps=cfg.observed_timestamps)
            bc_score = float(sig.get("bc_score", 0.0) or 0.0)
            diversity = float(sig.get("diversity_score", 0.0) or 0.0)
            threat = float(sig.get("threat_ratio", 0.0) or 0.0)
            return BiologicalEcologicalSignal(
                timestamp=ts,
                circadian_phase=brt["circadian_phase"],
                ultradian_phase=brt["ultradian_phase"],
                lunar_phase=brt["lunar_phase"],
                seasonal_phase=brt["seasonal_phase"],
                circadian_phase_deviation=brt.get("circadian_phase_deviation", 0.0),
                circadian_strength=brt.get("circadian_strength", 0.0),
                brt_source=str(brt.get("brt_source", "CLOCK_FALLBACK")),
                bc_score=bc_score, bc_flow=diversity,
                bc_resilience=1.0 - threat, bc_interdependence=diversity,
                xsl_aggregate=bc_score,
                xsl_keystone_score=1.0 if threat >= 0.6 else 0.5,
                xsl_decline_rate=threat, keystone_at_risk=threat >= 0.6)
        except Exception:
            return None

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
