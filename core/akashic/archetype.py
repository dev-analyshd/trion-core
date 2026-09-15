"""
TRION Akashic Index — Behavioral Archetypes
============================================
12 concrete behavioral archetypes, each with:
  - Full 9-dim Phi vector (physical plane)
  - 5-plane behavioral signature (Φ, M, Σ, K, A)
  - Life cycle compatibility
  - Epigenetic mutation rate
  - CRISPR repair template
  - Historical examples
  - Investment signal

These archetypes are the "DNA" of on-chain behavioral patterns.
The Akashic Index stores all observed entities as distances from these archetypes.
"""

from dataclasses import dataclass, field
from typing import List, Dict, Optional
import numpy as np

# ─── L2.2 Behavioral feature space dimension ───────────────────────────────
# Whitepaper spec (L2.2): "Cosine similarity in 128-dimensional behavioral
# feature space." This mirrors the BP_FINGERPRINT_DIM = 128 used in
# core/primitives/entity_resolution.py for BEO behavioral fingerprints.
ARCHETYPE_FEATURE_DIM: int = 128


def _embed_phi_to_128(
    phi_vector: List[float],
    mental: float,
    sigma: float,
    karma: float,
    anima: float,
) -> np.ndarray:
    """
    Embed the 9-dim Phi vector + 4 behavioral plane scores (M, Σ, K, A)
    into a 128-dimensional behavioral feature space per whitepaper L2.2 spec.

    Layout (128 dimensions):
      [  0 ..   8]  9 phi features (physical plane Φ)
      [  9 ..  12]  4 behavioral plane scores (M, Σ, K, A)
      [ 13 ..  48]  36 pairwise cross-products of phi features (i<j)
      [ 49 ..  84]  36 products of phi features × plane scores
      [ 85 ..  89]   5 statistical summaries (mean, std, min, max, median of phi)
      [ 90 .. 127]  38 reserved (zeros) — future behavioral features

    This is a deterministic, more sophisticated embedding than naive zero
    padding: it preserves the original 9-dim Phi signal while exposing
    non-linear cross-feature structure that the cosine similarity can exploit
    to discriminate archetypes that share many Phi coordinates but diverge
    in plane scores (e.g. Accumulation vs. Distribution).
    """
    vec = np.zeros(ARCHETYPE_FEATURE_DIM, dtype=np.float32)
    phi = np.asarray(phi_vector, dtype=np.float32)
    planes = np.array([mental, sigma, karma, anima], dtype=np.float32)

    # 9 phi features (physical plane)
    n_phi = min(9, len(phi))
    vec[0:n_phi] = phi[:n_phi]

    # 4 behavioral plane scores
    vec[9:13] = planes

    # 36 pairwise cross-products of phi features (i<j)
    idx = 13
    for i in range(9):
        for j in range(i + 1, 9):
            vec[idx] = phi[i] * phi[j]
            idx += 1

    # 36 products of phi features × plane scores
    for i in range(9):
        for p in range(4):
            vec[idx] = phi[i] * planes[p]
            idx += 1

    # 5 statistical summaries of phi
    if n_phi > 0:
        vec[idx] = float(phi[:n_phi].mean()); idx += 1
        vec[idx] = float(phi[:n_phi].std());  idx += 1
        vec[idx] = float(phi[:n_phi].min());  idx += 1
        vec[idx] = float(phi[:n_phi].max());  idx += 1
        vec[idx] = float(np.median(phi[:n_phi])); idx += 1

    # Remaining positions are zeros (reserved for future behavioral features).
    return vec


@dataclass
class BehavioralArchetype:
    id: str
    name: str
    description: str

    # 5-plane behavioral signature
    phi_vector: List[float]        # 9-dim physical plane
    mental_score: float            # M plane (observer effect)
    sigma_score: float             # Σ plane (network consensus)
    karma_score: float             # K plane (historical consistency)
    anima_score: float             # A plane (predictive)

    # Lifecycle
    typical_lifecycle: List[str]   # expected stage sequence
    avg_duration_days: int         # typical duration in this archetype
    mutation_rate: float           # how fast entities leave this archetype

    # Risk and signals
    risk_level: str                # SAFE | CAUTION | DANGER | CRITICAL
    investment_signal: str         # BUY | WATCH | AVOID | SHORT
    investment_confidence: float

    # Historical examples
    examples: List[str]
    known_transitions_to: List[str]  # archetypes this typically evolves into

    # CRISPR repair
    crispr_template: str           # how to nudge entity toward healthier archetype

    # 128-dim behavioral feature fingerprint — derived from phi_vector + plane
    # scores via _embed_phi_to_128() in __post_init__(). Stored (not computed
    # on every match) so that cosine similarity runs against a precomputed
    # matrix per whitepaper L2.2 spec ("store 128-dim vectors").
    behavioral_fingerprint: List[float] = field(default_factory=list)

    def __post_init__(self) -> None:
        if not self.behavioral_fingerprint:
            fp = _embed_phi_to_128(
                self.phi_vector,
                self.mental_score,
                self.sigma_score,
                self.karma_score,
                self.anima_score,
            )
            # Store as plain Python list (JSON-serializable, dataclass-friendly).
            self.behavioral_fingerprint = fp.tolist()


ARCHETYPES: List[BehavioralArchetype] = [

    BehavioralArchetype(
        id="ARCH_01",
        name="Organic Growth",
        description="Healthy, diverse, steady growth with broad participation and no manipulation signals.",
        phi_vector=[0.32, 0.28, 0.38, 0.30, 0.22, 0.18, 0.34, 0.29, 0.35],
        mental_score=0.70,
        sigma_score=0.75,
        karma_score=0.80,
        anima_score=0.72,
        typical_lifecycle=["BIRTH", "GROWTH", "MATURITY"],
        avg_duration_days=365,
        mutation_rate=0.15,
        risk_level="SAFE",
        investment_signal="BUY",
        investment_confidence=0.78,
        examples=["Uniswap (early)", "Aave (2021)", "Ethereum (2016-2017)"],
        known_transitions_to=["Maturity Protocol", "Distribution"],
        crispr_template="Maintain current trajectory. Encourage validator diversity.",
    ),

    BehavioralArchetype(
        id="ARCH_02",
        name="Accumulation",
        description="Smart money quietly building positions. Low entropy, coordinated buying, below-market awareness.",
        phi_vector=[0.45, 0.42, 0.55, 0.40, 0.62, 0.58, 0.44, 0.41, 0.54],
        mental_score=0.55,
        sigma_score=0.60,
        karma_score=0.65,
        anima_score=0.68,
        typical_lifecycle=["BIRTH", "GROWTH"],
        avg_duration_days=90,
        mutation_rate=0.35,
        risk_level="CAUTION",
        investment_signal="BUY",
        investment_confidence=0.65,
        examples=["BTC (pre-2020 halving)", "ETH (pre-merge)", "many DeFi protocols pre-TVL spike"],
        known_transitions_to=["Organic Growth", "Distribution", "Flash Exploit"],
        crispr_template="Increase transparency. Publish tokenomics. Encourage public participation.",
    ),

    BehavioralArchetype(
        id="ARCH_03",
        name="Distribution",
        description="Late-stage selling pressure. Whales reducing positions, volume high but price diverges.",
        phi_vector=[0.68, 0.64, 0.76, 0.60, 0.72, 0.68, 0.66, 0.62, 0.74],
        mental_score=0.40,
        sigma_score=0.35,
        karma_score=0.42,
        anima_score=0.38,
        typical_lifecycle=["MATURITY", "DECLINE"],
        avg_duration_days=60,
        mutation_rate=0.50,
        risk_level="DANGER",
        investment_signal="AVOID",
        investment_confidence=0.72,
        examples=["Most tokens at peak", "Terra/LUNA (weeks before collapse)", "FTX (late 2022)"],
        known_transitions_to=["Liquidity Drain", "Death Spiral", "Recovery"],
        crispr_template="Investigate whale wallet concentration. Audit team vesting schedules.",
    ),

    BehavioralArchetype(
        id="ARCH_04",
        name="Liquidity Drain",
        description="Active removal of protocol liquidity by insiders or coordinated actors.",
        phi_vector=[0.80, 0.75, 0.90, 0.70, 0.85, 0.80, 0.78, 0.73, 0.88],
        mental_score=0.20,
        sigma_score=0.18,
        karma_score=0.15,
        anima_score=0.12,
        typical_lifecycle=["DECLINE", "DEATH"],
        avg_duration_days=7,
        mutation_rate=0.85,
        risk_level="CRITICAL",
        investment_signal="SHORT",
        investment_confidence=0.90,
        examples=["Squid Game Token", "Thodex", "Bald (Base chain)"],
        known_transitions_to=["Death Spiral"],
        crispr_template="EMERGENCY: Pause withdrawals. Multi-sig emergency stop. Community governance takeover.",
    ),

    BehavioralArchetype(
        id="ARCH_05",
        name="Flash Exploit",
        description="Single-block or multi-block exploit execution. Extreme entropy spike, massive value drain.",
        phi_vector=[0.96, 0.92, 0.88, 0.94, 0.04, 0.03, 0.94, 0.90, 0.96],
        mental_score=0.05,
        sigma_score=0.03,
        karma_score=0.02,
        anima_score=0.01,
        typical_lifecycle=["DEATH"],
        avg_duration_days=1,
        mutation_rate=1.0,
        risk_level="CRITICAL",
        investment_signal="SHORT",
        investment_confidence=0.98,
        examples=["Euler ($197M)", "Beanstalk ($182M)", "Mango Markets ($114M)", "Ronin ($625M)"],
        known_transitions_to=["Death Spiral", "Recovery (post-exploit)"],
        crispr_template="IMMEDIATE: Pause all functions. Report to security teams. Engage whitehats.",
    ),

    BehavioralArchetype(
        id="ARCH_06",
        name="Wash Trading",
        description="Artificial volume via circular self-trades. High volume, near-zero net balance change.",
        phi_vector=[0.32, 0.28, 0.84, 0.24, 0.80, 0.76, 0.30, 0.26, 0.82],
        mental_score=0.30,
        sigma_score=0.25,
        karma_score=0.20,
        anima_score=0.22,
        typical_lifecycle=["GROWTH", "MATURITY"],
        avg_duration_days=180,
        mutation_rate=0.40,
        risk_level="DANGER",
        investment_signal="AVOID",
        investment_confidence=0.68,
        examples=["NFT wash trading (LooksRare early)", "Low-cap CEX token inflation"],
        known_transitions_to=["Distribution", "Death Spiral"],
        crispr_template="Implement net-flow authenticity score. Penalize circular transactions in rewards.",
    ),

    BehavioralArchetype(
        id="ARCH_07",
        name="Governance Attack",
        description="Malicious actor gaining control of governance to pass harmful proposals.",
        phi_vector=[0.62, 0.68, 0.45, 0.80, 0.60, 0.55, 0.60, 0.66, 0.62],
        mental_score=0.30,
        sigma_score=0.25,
        karma_score=0.28,
        anima_score=0.20,
        typical_lifecycle=["MATURITY", "DECLINE"],
        avg_duration_days=30,
        mutation_rate=0.65,
        risk_level="CRITICAL",
        investment_signal="AVOID",
        investment_confidence=0.82,
        examples=["Beanstalk ($182M)", "Build Finance takeover", "Compound governance manipulation"],
        known_transitions_to=["Liquidity Drain", "Recovery"],
        crispr_template="Add voting delay (48h), timelock (72h), quorum (10%), per-wallet cap (20%).",
    ),

    BehavioralArchetype(
        id="ARCH_08",
        name="Bot Swarm",
        description="Coordinated automated agents creating artificial market activity.",
        phi_vector=[0.22, 0.20, 0.92, 0.18, 0.88, 0.86, 0.20, 0.18, 0.90],
        mental_score=0.25,
        sigma_score=0.20,
        karma_score=0.18,
        anima_score=0.15,
        typical_lifecycle=["GROWTH", "MATURITY"],
        avg_duration_days=30,
        mutation_rate=0.55,
        risk_level="DANGER",
        investment_signal="WATCH",
        investment_confidence=0.60,
        examples=["NFT mint bot swarms", "Arbitrage bot MEV", "Sybil farming"],
        known_transitions_to=["Wash Trading", "Distribution"],
        crispr_template="Implement CAPTCHA-equivalent, randomized delays, behavioral diversity requirements.",
    ),

    BehavioralArchetype(
        id="ARCH_09",
        name="Healthy DeFi Protocol",
        description="Balanced, diverse, sustainable DeFi protocol with real users and utility.",
        phi_vector=[0.56, 0.52, 0.62, 0.50, 0.42, 0.38, 0.54, 0.50, 0.60],
        mental_score=0.72,
        sigma_score=0.78,
        karma_score=0.75,
        anima_score=0.70,
        typical_lifecycle=["GROWTH", "MATURITY"],
        avg_duration_days=730,
        mutation_rate=0.10,
        risk_level="SAFE",
        investment_signal="BUY",
        investment_confidence=0.72,
        examples=["Uniswap v3", "Aave v3", "Compound (mature phase)"],
        known_transitions_to=["Organic Growth", "Accumulation"],
        crispr_template="Continue current governance practices. Diversify validator set.",
    ),

    BehavioralArchetype(
        id="ARCH_10",
        name="Dormant Contract",
        description="Low or zero activity. Contract exists but is no longer used — potential resurrection candidate.",
        phi_vector=[0.10, 0.08, 0.14, 0.12, 0.06, 0.05, 0.09, 0.07, 0.12],
        mental_score=0.15,
        sigma_score=0.10,
        karma_score=0.30,
        anima_score=0.20,
        typical_lifecycle=["DECLINE", "DEATH"],
        avg_duration_days=365,
        mutation_rate=0.08,
        risk_level="CAUTION",
        investment_signal="WATCH",
        investment_confidence=0.40,
        examples=["Old DEX contracts", "Failed ICO tokens", "Deprecated protocol versions"],
        known_transitions_to=["Organic Growth (resurrection)", "Death Spiral"],
        crispr_template="Evaluate for resurrection: check if code is still valuable. Consider migration.",
    ),

    BehavioralArchetype(
        id="ARCH_11",
        name="Ponzi Structure",
        description="Reward system that requires continuous new capital. Unsustainable yield source.",
        phi_vector=[0.62, 0.58, 0.80, 0.52, 0.74, 0.70, 0.60, 0.56, 0.78],
        mental_score=0.28,
        sigma_score=0.22,
        karma_score=0.18,
        anima_score=0.15,
        typical_lifecycle=["GROWTH", "DECLINE", "DEATH"],
        avg_duration_days=180,
        mutation_rate=0.75,
        risk_level="CRITICAL",
        investment_signal="AVOID",
        investment_confidence=0.88,
        examples=["Bitconnect", "HEX (aspects)", "many high-APY farms (2021)"],
        known_transitions_to=["Death Spiral", "Liquidity Drain"],
        crispr_template="Model yield sustainability: source must cover emissions. Publish cash flow.",
    ),

    BehavioralArchetype(
        id="ARCH_12",
        name="Death Spiral",
        description="Reflexive collapse: selling pressure → price drop → more selling. Terminal state.",
        phi_vector=[0.88, 0.84, 0.92, 0.80, 0.90, 0.88, 0.86, 0.82, 0.91],
        mental_score=0.08,
        sigma_score=0.06,
        karma_score=0.05,
        anima_score=0.03,
        typical_lifecycle=["DEATH"],
        avg_duration_days=14,
        mutation_rate=0.95,
        risk_level="CRITICAL",
        investment_signal="SHORT",
        investment_confidence=0.95,
        examples=["Terra/LUNA collapse", "IRON Finance", "SafeMoon late stage"],
        known_transitions_to=["Dormant Contract"],
        crispr_template="TERMINAL: No internal fix possible. Emergency circuit breaker or graceful shutdown.",
    ),
]


ARCHETYPE_MAP: Dict[str, BehavioralArchetype] = {a.id: a for a in ARCHETYPES}
ARCHETYPE_NAME_MAP: Dict[str, BehavioralArchetype] = {a.name: a for a in ARCHETYPES}


def get_archetype_by_id(arch_id: str) -> Optional[BehavioralArchetype]:
    return ARCHETYPE_MAP.get(arch_id)


def get_archetype_matrix() -> np.ndarray:
    """Return the 9-dim Phi matrix (12, 9) for backwards-compatible callers.

    Retained for callers that consume the physical-plane Phi vectors directly
    (e.g. tests/invention_verification.py). New code should prefer
    get_archetype_feature_matrix() which returns the 128-dim behavioral
    feature vectors per whitepaper L2.2 spec.
    """
    return np.array([a.phi_vector for a in ARCHETYPES], dtype=np.float32)


def get_archetype_feature_matrix() -> np.ndarray:
    """
    Return the 128-dimensional behavioral feature matrix (12, 128) per
    whitepaper L2.2 spec: "Cosine similarity in 128-dimensional behavioral
    feature space."
    """
    return np.array([a.behavioral_fingerprint for a in ARCHETYPES], dtype=np.float32)


def embed_phi_vector(
    phi_vector: List[float],
    behavioral_scores: Optional[Dict[str, float]] = None,
) -> np.ndarray:
    """
    Public helper: embed a 9-dim Phi vector + optional plane scores into the
    128-dimensional behavioral feature space used by match_archetype().

    Args:
        phi_vector: 9-dim physical-plane Φ vector.
        behavioral_scores: optional dict with keys 'mental', 'sigma',
            'karma', 'anima' (each in [0, 1]). Defaults to neutral 0.5 for
            any missing key — callers that have observed plane scores should
            pass them explicitly for a more discriminative embedding.
    """
    bs = behavioral_scores or {}
    return _embed_phi_to_128(
        phi_vector,
        bs.get("mental", 0.5),
        bs.get("sigma", 0.5),
        bs.get("karma", 0.5),
        bs.get("anima", 0.5),
    )


def match_archetype(
    phi_vector: List[float],
    behavioral_scores: Optional[Dict[str, float]] = None,
) -> Dict:
    """
    Match a 9-dim Phi vector against the 12-archetype library using
    128-dimensional cosine similarity in behavioral feature space.

    Whitepaper L2.2 spec: "Cosine similarity in 128-dimensional behavioral
    feature space." The query Phi vector is embedded to 128 dimensions via
    _embed_phi_to_128() (9 phi features + 4 plane scores + cross-products
    + statistical summaries + reserved zeros) and compared via cosine
    similarity against each archetype's precomputed behavioral_fingerprint.

    Args:
        phi_vector: 9-dim physical-plane Φ vector of the entity to classify.
        behavioral_scores: optional dict with 'mental', 'sigma', 'karma',
            'anima' plane scores in [0, 1]. Defaults to neutral 0.5 for
            any missing key — pass observed plane scores when available
            for a more discriminative match.
    """
    query_fp = embed_phi_vector(phi_vector, behavioral_scores)
    n_q = float(np.linalg.norm(query_fp))
    best_sim = -1.0
    best_arch = ARCHETYPES[0]
    if n_q > 0:
        for arch in ARCHETYPES:
            ref = np.asarray(arch.behavioral_fingerprint, dtype=np.float32)
            n_ref = float(np.linalg.norm(ref))
            if n_ref <= 0:
                continue
            sim = float(np.dot(query_fp, ref) / (n_q * n_ref))
            if sim > best_sim:
                best_sim = sim
                best_arch = arch
    return {
        "archetype_id": best_arch.id,
        "archetype_name": best_arch.name,
        "similarity": round(best_sim, 4),
        "distance": round(1.0 - best_sim, 4),
        "risk_level": best_arch.risk_level,
        "investment_signal": best_arch.investment_signal,
        "investment_confidence": best_arch.investment_confidence,
        "description": best_arch.description,
        "typical_lifecycle": best_arch.typical_lifecycle,
        "known_transitions": best_arch.known_transitions_to,
        "crispr_template": best_arch.crispr_template,
    }


def get_all_archetypes_summary() -> List[Dict]:
    return [
        {
            "id": a.id,
            "name": a.name,
            "risk_level": a.risk_level,
            "investment_signal": a.investment_signal,
            "investment_confidence": a.investment_confidence,
            "phi_vector": a.phi_vector,
            "lifecycle": a.typical_lifecycle,
            "examples": a.examples[:2],
            "description": a.description,
        }
        for a in ARCHETYPES
    ]
