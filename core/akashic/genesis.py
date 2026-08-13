"""
TRION Protocol — L2.2: Genesis Inference
For assets with no behavioral history — priced from archetype similarity.

Whitepaper Section 6 — Genesis Inference: Valuing the Unvalued from Block Zero

Genesis Fingerprint: 6-dimensional snapshot at t=0
  1. Liquidity seeding structure (amount, concentration, LP wallet history)
  2. Initial token distribution (holder count, wallet type, concentration index)
  3. Deployer wallet behavioral history from Akashic Index
  4. Contract architecture (upgrade patterns, ownership, permission topology)
  5. First-block interaction data (volume, wallet diversity, price impact)
  6. Cross-chain context (similar contemporaneous launches, market environment)

Archetype Matching:
  sim(G, A_k) = (G · A_k) / (‖G‖ · ‖A_k‖)  cosine similarity in 128-dim space

Genesis Valuation:
  V₀ = Σₖ sim(G, Aₖ) · Vₖ(stage=0) / Σₖ sim(G, Aₖ)

Confidence Convergence (variable λ per whitepaper §6.4):
  conf(t) = 1 − e^(−λ · A(t))
  λ = Σₖ sim(G, Aₖ) · λₖ / Σₖ sim(G, Aₖ)   (archetype-matched convergence rate)

  Fast-moving assets (high early activity) → larger λ → converge quickly
  Slow-moving assets → smaller λ → wider confidence intervals longer
"""

import os
import logging
import numpy as np
import math
from typing import List, Optional
from dataclasses import dataclass, field

logger = logging.getLogger(__name__)

GENESIS_DIM            = 128
GENESIS_LAMBDA_DEFAULT = 0.001   # fallback when no archetypes available

# ── FAISS Service client (L2.2 archetype matching) ───────────────────────────
# Base URL follows the same convention as akashic/genesis_backfill*.py:
#   FAISS_SERVICE_URL env var, defaulting to http://127.0.0.1:8000
FAISS_SERVICE_URL = os.environ.get("FAISS_SERVICE_URL", "http://127.0.0.1:8000")
_ARCHETYPE_MATCH_ENDPOINT = f"{FAISS_SERVICE_URL}/archetypes/match_vector"

# Lazy-import requests so the module stays importable without it installed.
def _get_requests():
    try:
        import requests as _requests
        return _requests
    except ImportError:
        return None


def query_faiss_archetype_similarities(
    feature_vector: np.ndarray,
    timeout: float = 2.0,
) -> Optional[List[dict]]:
    """
    POST feature_vector to the live FAISS service and return a list of dicts:
      [{"archetype_id": int, "cosine_similarity": float, "centroid": list}, ...]

    Returns None if the FAISS service is unreachable or returns an error,
    so callers can fall back to local np.linalg.norm computation.
    """
    requests = _get_requests()
    if requests is None:
        logger.warning(
            "[genesis_inference] 'requests' library not available — "
            "falling back to local cosine similarity computation."
        )
        return None
    try:
        resp = requests.post(
            _ARCHETYPE_MATCH_ENDPOINT,
            json={"vector": feature_vector.tolist()},
            timeout=timeout,
        )
        resp.raise_for_status()
        data = resp.json()
        if data.get("status") not in ("ok",):
            logger.warning(
                "[genesis_inference] FAISS /archetypes/match_vector returned "
                "status=%r (n_archetypes=%d) — falling back to local computation.",
                data.get("status"),
                data.get("n_archetypes", 0),
            )
            return None
        return data["archetypes"]   # list of {archetype_id, cosine_similarity, centroid}
    except Exception as exc:
        logger.warning(
            "[genesis_inference] FAISS service unreachable at %s — "
            "falling back to local np.linalg.norm cosine computation. (%s: %s)",
            _ARCHETYPE_MATCH_ENDPOINT,
            type(exc).__name__,
            exc,
        )
        return None


# ── Genesis Fingerprint ───────────────────────────────────────────────────────

@dataclass
class GenesisFingerprint:
    """
    Whitepaper §6.2 — Full 6-dimension Genesis Fingerprint captured at t=0.
    Each dimension maps directly to a whitepaper-specified input.
    """
    # Dimension 1: Liquidity seeding structure
    liquidity_seed_amount_usd:      float = 0.0       # USD value seeded at launch
    liquidity_concentration:        float = 1.0       # HHI of LP wallet concentration [0,1]
    lp_wallet_akashic_depth:        float = 0.0       # Avg Akashic depth of LP wallets

    # Dimension 2: Initial token distribution
    initial_holder_count:           int   = 1
    initial_distribution_entropy:   float = 0.0       # Shannon entropy of holder distribution
    initial_concentration_index:    float = 1.0       # Gini coefficient of token distribution

    # Dimension 3: Deployer wallet behavioral history (from Akashic Index)
    deployer_akashic_depth:         float = 0.0       # Deployer's total behavioral history depth
    deployer_clean_history_ratio:   float = 1.0       # Fraction of non-manipulation BH records
    deployer_prior_protocol_count:  int   = 0         # # of protocols previously deployed
    deployer_prior_success_rate:    float = 0.5       # Historical success rate of deployer protocols

    # Dimension 4: Contract architecture
    has_upgrade_proxy:              bool  = False      # Upgradeable proxy pattern detected
    ownership_centralized:          bool  = True       # Single owner vs multisig/DAO
    permission_topology_score:      float = 0.5       # 0=centralized, 1=fully decentralized
    contract_complexity_score:      float = 0.5       # Normalized function selector count
    has_timelock:                   bool  = False      # Timelock on privileged operations

    # Dimension 5: First-block interaction data
    first_block_trade_volume_usd:   float = 0.0       # Volume in genesis block
    first_block_wallet_diversity:   float = 0.0       # Unique wallets / total txs in block 1
    first_block_price_impact:       float = 1.0       # Price impact of first trades [0,1]; lower=better

    # Dimension 6: Cross-chain context
    cross_chain_context_score:      float = 0.5       # Behavioral environment at launch [0,1]
    contemporaneous_similar_count:  int   = 0         # Similar assets launching in same 7d window
    market_coherence_at_launch:     float = 0.5       # C(t) system-wide at launch moment

    def to_feature_vector(self) -> np.ndarray:
        """Convert 6-dimension fingerprint to 128-dim behavioral feature vector."""
        raw = np.array([
            # Liquidity seeding
            min(math.log10(self.liquidity_seed_amount_usd + 1) / 8.0, 1.0),
            1.0 - self.liquidity_concentration,
            min(self.lp_wallet_akashic_depth / 50000.0, 1.0),
            # Token distribution
            min(self.initial_holder_count / 10000.0, 1.0),
            self.initial_distribution_entropy,
            1.0 - self.initial_concentration_index,
            # Deployer history
            min(self.deployer_akashic_depth / 100000.0, 1.0),
            self.deployer_clean_history_ratio,
            min(self.deployer_prior_protocol_count / 20.0, 1.0),
            self.deployer_prior_success_rate,
            # Contract architecture
            0.0 if self.has_upgrade_proxy else 0.5,
            0.0 if self.ownership_centralized else 1.0,
            self.permission_topology_score,
            self.contract_complexity_score,
            1.0 if self.has_timelock else 0.0,
            # First-block interactions
            min(math.log10(self.first_block_trade_volume_usd + 1) / 7.0, 1.0),
            self.first_block_wallet_diversity,
            1.0 - self.first_block_price_impact,
            # Cross-chain context
            self.cross_chain_context_score,
            min(self.contemporaneous_similar_count / 50.0, 1.0),
            self.market_coherence_at_launch,
        ], dtype=np.float32)

        # Tile raw features to fill 128-dim space (repeating pattern with harmonic dampening)
        feature_vec = np.zeros(GENESIS_DIM, dtype=np.float32)
        n_raw = len(raw)
        for i in range(GENESIS_DIM):
            base_idx = i % n_raw
            harmonic  = 1.0 / (1.0 + (i // n_raw))
            feature_vec[i] = raw[base_idx] * harmonic
        # Normalize to unit sphere
        norm = np.linalg.norm(feature_vec)
        if norm > 0:
            feature_vec /= norm
        return feature_vec

    def risk_score(self) -> float:
        """
        Composite genesis risk score [0,1]; 0=minimal risk, 1=maximum risk.
        Weighted combination of the highest-signal risk dimensions.
        """
        risks = [
            0.30 * self.liquidity_concentration,
            0.20 * self.initial_concentration_index,
            0.20 * (1.0 - self.deployer_clean_history_ratio),
            0.15 * (0.0 if self.has_timelock else 1.0),
            0.10 * (1.0 if self.ownership_centralized else 0.0),
            0.05 * self.first_block_price_impact,
        ]
        return round(sum(risks), 4)

    def summary(self) -> dict:
        return {
            "dimension_1_liquidity": {
                "seed_usd":       self.liquidity_seed_amount_usd,
                "concentration":  self.liquidity_concentration,
                "lp_depth":       self.lp_wallet_akashic_depth,
            },
            "dimension_2_distribution": {
                "holder_count":   self.initial_holder_count,
                "entropy":        self.initial_distribution_entropy,
                "gini":           self.initial_concentration_index,
            },
            "dimension_3_deployer_history": {
                "akashic_depth":      self.deployer_akashic_depth,
                "clean_ratio":        self.deployer_clean_history_ratio,
                "prior_protocols":    self.deployer_prior_protocol_count,
                "prior_success_rate": self.deployer_prior_success_rate,
            },
            "dimension_4_contract_architecture": {
                "upgrade_proxy":       self.has_upgrade_proxy,
                "ownership_centralized": self.ownership_centralized,
                "permission_score":    self.permission_topology_score,
                "complexity":          self.contract_complexity_score,
                "has_timelock":        self.has_timelock,
            },
            "dimension_5_first_block": {
                "volume_usd":         self.first_block_trade_volume_usd,
                "wallet_diversity":   self.first_block_wallet_diversity,
                "price_impact":       self.first_block_price_impact,
            },
            "dimension_6_cross_chain_context": {
                "context_score":           self.cross_chain_context_score,
                "similar_contemporaneous": self.contemporaneous_similar_count,
                "market_coherence":        self.market_coherence_at_launch,
            },
        }


# ── Legacy GenesisVector (backward compat) ────────────────────────────────────

@dataclass
class GenesisVector:
    asset_id:                     str
    feature_vector:               np.ndarray
    deployer_signature:           Optional[np.ndarray] = None
    token_economic_structure:     float = 0.5
    initial_distribution_entropy: float = 0.5
    protocol_category:            int   = 0
    smart_contract_complexity:    float = 0.5


# ── Archetype ─────────────────────────────────────────────────────────────────

@dataclass
class Archetype:
    archetype_id:       str
    name:               str
    category:           str
    feature_vector:     np.ndarray
    base_value:         float
    convergence_rate:   float = 0.001   # λₖ — asset-class specific convergence rate
    genesis_stage_value: float = 0.0    # Vₖ(stage=0) per whitepaper §6.3


# ── Core Functions ────────────────────────────────────────────────────────────

def cosine_similarity(v1: np.ndarray, v2: np.ndarray) -> float:
    n1, n2 = np.linalg.norm(v1), np.linalg.norm(v2)
    if n1 == 0 or n2 == 0:
        return 0.0
    return float(np.dot(v1, v2) / (n1 * n2))


def archetype_matched_lambda(
    sims:       List[float],
    archetypes: List[Archetype],
) -> float:
    """
    Whitepaper §6.4 — Variable λ estimated from matched archetypes' convergence rates.
    λ = Σₖ sim(G, Aₖ) · λₖ / Σₖ sim(G, Aₖ)

    Fast-moving asset classes (e.g. memecoins with high early activity) have
    higher λₖ and converge quickly. Slow-moving classes (e.g. governance tokens)
    have lower λₖ and carry wider confidence intervals longer.
    """
    total_sim = sum(sims)
    if total_sim <= 0:
        return GENESIS_LAMBDA_DEFAULT
    return sum(s * a.convergence_rate for s, a in zip(sims, archetypes)) / total_sim


def genesis_confidence(D_asset: float, lam: float = GENESIS_LAMBDA_DEFAULT) -> float:
    """conf(t) = 1 − e^(−λ · A(t))  with variable λ per whitepaper §6.4."""
    return 1.0 - math.exp(-lam * D_asset)


def infer_genesis_value(
    genesis:    GenesisVector,
    archetypes: List[Archetype],
    D_asset:    float = 0.0,
    _use_v2:    bool = True,   # attempt transformer path if available
) -> dict:
    """
    Full Genesis Inference per whitepaper §6.3–6.4.

    V₀ = Σₖ sim(G, Aₖ) · Vₖ(stage=0) / Σₖ sim(G, Aₖ)
    λ  = archetype-matched convergence rate (variable, not fixed)
    conf(t) = 1 − e^(−λ · A(t))

    When _use_v2=True (default) and PyTorch is available + model is fitted,
    delegates to mental_transformer.infer_genesis_value_v2() which uses a real
    self-attention transformer encoder over behavioral sequences.
    Falls back to the original harmonic-cosine path transparently.
    """
    if _use_v2:
        try:
            from src.core.mental_transformer import (
                infer_genesis_value_v2, _TORCH_AVAILABLE, _fitted,
            )
            if _TORCH_AVAILABLE and _fitted:
                return infer_genesis_value_v2(genesis, archetypes, D_asset)
        except Exception as _exc:
            logger.debug("[genesis_inference] v2 dispatch failed (%s), using harmonic path", _exc)
    # ── Original harmonic-cosine path (always preserved as fallback) ────────
    if not archetypes:
        return {
            "genesis_value": 0.50,
            "conf_genesis":  0.0,
            "archetype":     None,
            "lambda":        GENESIS_LAMBDA_DEFAULT,
            "method":        "no_archetypes",
        }

    # ── Step 1: cosine similarities via FAISS service or local fallback ───────
    # Try the live FAISS service first (real 127k+ indexed vectors / K-means centroids).
    # Fall back to local np.linalg.norm only if the service is unreachable.
    faiss_results = query_faiss_archetype_similarities(genesis.feature_vector)
    similarity_source = "faiss_service"

    if faiss_results is not None and len(faiss_results) > 0:
        # FAISS returned centroid similarities.  Map them onto the caller-supplied
        # Archetype list so the whitepaper formulas (V₀, λ) still use the
        # per-class metadata (base_value, convergence_rate, genesis_stage_value).
        # Strategy: for each local Archetype find the FAISS centroid whose vector
        # is most cosine-similar, then weight by that centroid's FAISS score.
        faiss_centroids = np.array(
            [r["centroid"] for r in faiss_results], dtype=np.float32
        )  # shape [n_faiss, 128]
        local_vecs = np.array(
            [a.feature_vector for a in archetypes], dtype=np.float32
        )  # shape [n_local, 128]

        lv_norms = np.linalg.norm(local_vecs, axis=1, keepdims=True)
        fc_norms = np.linalg.norm(faiss_centroids, axis=1, keepdims=True)
        lv_norms = np.where(lv_norms < 1e-10, 1e-10, lv_norms)
        fc_norms = np.where(fc_norms < 1e-10, 1e-10, fc_norms)
        # similarity matrix: [n_local × n_faiss]
        sim_matrix = (local_vecs / lv_norms) @ (faiss_centroids / fc_norms).T

        faiss_scores = np.array(
            [r["cosine_similarity"] for r in faiss_results], dtype=np.float64
        )  # shape [n_faiss]
        # For each local archetype, find the best-matching FAISS centroid
        best_faiss_idx = np.argmax(sim_matrix, axis=1)          # [n_local]
        alignment = np.clip(
            sim_matrix[np.arange(len(archetypes)), best_faiss_idx], 0.0, 1.0
        )
        sims = list(alignment * faiss_scores[best_faiss_idx])
    else:
        # FAISS service unreachable — fall back to local np.linalg.norm computation.
        sims = [cosine_similarity(genesis.feature_vector, a.feature_vector) for a in archetypes]
        similarity_source = "local_cosine_fallback"

    total_sim  = sum(sims)

    # ── Step 2: archetype-matched λ (variable per whitepaper §6.4) ───────────
    lam = archetype_matched_lambda(sims, archetypes)

    if total_sim <= 0:
        archetype_value      = 0.50
        genesis_stage_value  = 0.50
        best_archetype       = archetypes[0].name
    else:
        # V₀ = Σₖ sim(G, Aₖ) · Vₖ(stage=0) / Σₖ sim(G, Aₖ)
        genesis_stage_value = sum(
            s * a.genesis_stage_value / total_sim
            for s, a in zip(sims, archetypes)
        )
        # Fallback to base_value for archetype_value (used when D>0)
        archetype_value = sum(
            s * a.base_value / total_sim
            for s, a in zip(sims, archetypes)
        )
        best_idx       = int(np.argmax(sims))
        best_archetype = archetypes[best_idx].name

    conf = genesis_confidence(D_asset, lam)

    # Blend: at D=0 use V₀ (genesis stage); as conf grows use direct behavioral value
    direct_value = 0.50
    total_value  = conf * direct_value + (1 - conf) * genesis_stage_value

    return {
        "genesis_value":        total_value,
        "genesis_stage_value":  genesis_stage_value,
        "archetype_value":      archetype_value,
        "direct_value":         direct_value,
        "conf_genesis":         conf,
        "lambda":               round(lam, 6),
        "lambda_source":        "archetype_matched" if total_sim > 0 else "default",
        "best_archetype":       best_archetype,
        "similarities":         dict(zip([a.name for a in archetypes], [round(s, 4) for s in sims])),
        "similarity_source":    similarity_source,
        "method":               "genesis_inference",
        "disclosure": (
            f"Genesis inference: conf={conf:.3f}, λ={lam:.6f} (archetype-matched). "
            f"Archetype: {best_archetype}. Similarity source: {similarity_source}. "
            f"Confidence grows as behavioral history accumulates: conf(t)=1-e^(-{lam:.6f}·D)."
        ),
    }


if __name__ == "__main__":
    np.random.seed(42)

    archetypes = [
        Archetype("A1", "DeFi_Blue_Chip",  "MATURE_PROTOCOL",
                  np.random.normal(0.7, 0.1, 128), base_value=0.80,
                  convergence_rate=0.0005, genesis_stage_value=0.60),
        Archetype("A2", "New_Memecoin",    "NEW_TOKEN",
                  np.random.normal(0.3, 0.2, 128), base_value=0.20,
                  convergence_rate=0.005,  genesis_stage_value=0.10),
        Archetype("A3", "Stablecoin",      "STABLECOIN",
                  np.random.normal(0.5, 0.05, 128), base_value=0.60,
                  convergence_rate=0.002,  genesis_stage_value=0.55),
    ]

    # Test full GenesisFingerprint pipeline
    fp = GenesisFingerprint(
        liquidity_seed_amount_usd=500_000,
        liquidity_concentration=0.35,
        lp_wallet_akashic_depth=12000,
        initial_holder_count=850,
        initial_distribution_entropy=0.72,
        initial_concentration_index=0.28,
        deployer_akashic_depth=45000,
        deployer_clean_history_ratio=0.97,
        deployer_prior_protocol_count=3,
        deployer_prior_success_rate=0.82,
        has_upgrade_proxy=True,
        ownership_centralized=False,
        permission_topology_score=0.75,
        contract_complexity_score=0.55,
        has_timelock=True,
        first_block_trade_volume_usd=280_000,
        first_block_wallet_diversity=0.68,
        first_block_price_impact=0.03,
        cross_chain_context_score=0.61,
        contemporaneous_similar_count=4,
        market_coherence_at_launch=0.58,
    )
    genesis_vec = GenesisVector(
        asset_id="0xNEW",
        feature_vector=fp.to_feature_vector(),
    )

    r0     = infer_genesis_value(genesis_vec, archetypes, D_asset=0)
    r1000  = infer_genesis_value(genesis_vec, archetypes, D_asset=1000)
    r50000 = infer_genesis_value(genesis_vec, archetypes, D_asset=50000)

    print(f"Genesis (D=0):     value={r0['genesis_value']:.3f}  conf={r0['conf_genesis']:.4f}  λ={r0['lambda']}")
    print(f"Genesis (D=1000):  value={r1000['genesis_value']:.3f}  conf={r1000['conf_genesis']:.4f}")
    print(f"Genesis (D=50000): value={r50000['genesis_value']:.3f}  conf={r50000['conf_genesis']:.4f}")
    print(f"Best archetype:    {r0['best_archetype']}")
    print(f"Risk score:        {fp.risk_score()}")
    print(f"λ source:          {r0['lambda_source']}")
    assert r50000['conf_genesis'] > r0['conf_genesis'], "Confidence must grow with D"
    assert r0['lambda_source'] == "archetype_matched", "λ must be archetype-matched"
    print("GENESIS INFERENCE PASS — Variable λ, V₀, full 6-dim fingerprint")
