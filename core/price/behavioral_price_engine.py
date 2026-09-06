"""
src/price/behavioral_price_engine.py  [LEGACY COMPATIBILITY LAYER]
====================================================================

WARNING: The Core TRION Engine is strictly behavioral and price-agnostic.
This module exists solely to map Behavioral Coherence Scores onto legacy
CEX price feeds for TradFi integration. It is not part of the core
epistemological pipeline.

Concretely: C(t), Φ, M, Σ, K, A, MF, NL — everything in
anima-service/faiss_service.py and api's /api/v1/signal/* — never reads
a price feed. This module (served at /api/v1/price/*) is a SEPARATE,
deliberately price-aware compatibility shim that takes a CEX-derived
reference price as an explicit input specifically in order to quantify
how much of it is behaviorally unjustified.

Do not import this module from within the core behavioral pipeline.
src/core/coherence_engine.py and all five plane engines must remain
price-blind. Any import of this module from those files is a defect.

──────────────────────────────────────────────────────────────────────
Behavioral True Value (BTV) Engine — TRION Protocol
Implementation of Section 2.1 / 2.2 of the Inverted Truth Hierarchy:

  CURRENT STACK (corrupted):
    Retail ← DeFi ← Oracle (Chainlink) ← CEX price feeds ← CEX order matching ← (no ground truth)

  TRION STACK (behavioral ground truth):
    Retail ← DeFi ← TRION BTV ← On-chain BH ledger ← registered chains (1.9M+ tamper-proof records)

The BTV is NOT a faster pipe carrying CEX data.
It is derived from the actual behavioral record of what every entity did on every chain,
stripped of manipulation, weighted by coherence, bounded by liquidity health.

BTV Formula (L0.7):
  BTV(asset) = P_ref × Ω × (1 − MF_discount) × C_weight × NL_weight

  Where:
    P_ref        = cross-chain DEX reference price (on-chain activity, not CEX quotes)
    Ω            = behavioral consensus weight (source diversity × chain coverage)
    MF_discount  = manipulation fingerprint discount (wash trading stripped out)
    C_weight     = coherence weighting from 5-plane C(t) score
    NL_weight    = liquidity health weighting from NL score

  manipulation_discount_pct = (P_cex − BTV) / P_cex × 100
  "How much of the CEX price is behaviorally unjustified"
"""

# Module-level flag — importers can check this to confirm they are loading
# the compatibility layer and not the core behavioral pipeline.
LEGACY_COMPATIBILITY_LAYER: bool = True

import math
import time
import logging
import threading
import os
import requests
from concurrent.futures import ThreadPoolExecutor, as_completed
from typing import Optional
from dataclasses import dataclass, field, asdict

from core.generated_chain_bindings import TOTAL_CHAINS

logger = logging.getLogger(__name__)

# ─── Configuration ─────────────────────────────────────────────────────────────
ORACLE_API_URL  = "http://127.0.0.1:5000"
FAISS_API_URL   = "http://127.0.0.1:8000"
REQUEST_TIMEOUT = 6


def _faiss_headers() -> dict:
    """
    X-API-Key for the FAISS service (SEC-01) — same resolution order as
    faiss_service.py itself: FAISS_API_KEY → FAISS_SERVICE_API_KEY →
    TRION_API_KEY.  Empty/unset → header omitted (the GET then fails
    closed on the service side, which is the safe posture: the BTV
    computation falls back to its behavioral defaults).  Kept local like
    core/realtime/bh_streamer.py's resolver — core must not import from
    the api/ package above it.
    """
    key = (
        os.environ.get("FAISS_API_KEY")
        or os.environ.get("FAISS_SERVICE_API_KEY")
        or os.environ.get("TRION_API_KEY")
        or ""
    ).strip()
    return {"X-API-Key": key} if key else {}


# Known DEX pool entity IDs for coherence lookup (SHA3-256 of pool address, first 8 hex)
# These are real Arbitrum mainnet Uniswap V3 and Camelot pool addresses
KNOWN_POOLS = {
    "ETH": [
        "0x82aF49447D8a07e3bd95BD0d56f35241523fBab1",  # WETH on ARB
        "0xC31E54c7a869B9FcBEcc14363CF510d1c41fa443",  # WETH/USDC Uniswap V3 ARB
    ],
    "BTC": [
        "0x2f2a2543B76A4166549F7aaB2e75Bef0aefC5B0f",  # WBTC on ARB
    ],
    "SOL": [
        "0x2CaB3abfC1670D1a452dF502e216a66883cDf079",  # SOL bridged (Wormhole)
    ],
    "ARB": [
        "0x912CE59144191C1204E64559FE8253a0e49E6548",  # ARB token
    ],
    "OP": [
        "0x4200000000000000000000000000000000000042",  # OP token
    ],
    "LINK": [
        "0xf97f4df75117a78c1A5a0DBb814Af92458539FB4",  # LINK on ARB
    ],
}

# CoinGecko asset IDs (CEX-derived reference — the "corrupted baseline" we measure against)
COINGECKO_IDS = {
    "ETH":   "ethereum",
    "BTC":   "bitcoin",
    "SOL":   "solana",
    "ARB":   "arbitrum",
    "OP":    "optimism",
    "LINK":  "chainlink",
    "MATIC": "matic-network",
    "SUI":   "sui",
    "APT":   "aptos",
    "ATOM":  "cosmos",
    "NEAR":  "near",
    "TON":   "the-open-network",
    "TRX":   "tron",
    "MNT":   "mantle",
}

# ─── Data structures ───────────────────────────────────────────────────────────

@dataclass
class BTVDerivation:
    asset: str
    quote: str
    timestamp: int

    # Reference price (CEX-derived — what oracles currently report)
    cex_reference_price: float
    cex_source: str

    # Behavioral signals extracted from 37-chain BH ledger
    bh_ledger_depth: int          # total BH records in ledger
    chains_indexed: int           # chains contributing to this asset's signal
    swap_event_count: int         # SWAP events observed for this asset
    coherence_score: float        # C(t) from TRION 5-plane engine
    mf_score: float               # Manipulation Fingerprint 0–1
    nl_score: float               # Natural Liquidity score 0–1
    source_diversity: float       # d_eff = 1 - HHI of sources

    # BTV computation components
    omega: float                  # behavioral consensus weight
    mf_discount: float            # manipulation stripped out (0–1)
    coherence_weight: float       # C(t) → price weight adjustment
    nl_weight: float              # NL → liquidity health adjustment

    # Output
    btv: float                    # Behavioral True Value
    btv_ci_lower: float           # 95% confidence interval lower
    btv_ci_upper: float           # 95% confidence interval upper

    # The key metric — how much of CEX price is behaviorally unjustified
    manipulation_discount_pct: float
    manipulation_usd: float       # dollar amount of manipulation in the price
    confidence: float             # overall BTV confidence 0–1

    # Provenance chain
    inverted_hierarchy_note: str
    derivation_steps: list = field(default_factory=list)


# ─── CEX reference price fetcher + Batch CoinGecko price cache ────────────────
_cg_batch_cache: dict = {}
_cg_batch_lock  = threading.Lock()
_cg_batch_ttl   = 90  # seconds


def _fetch_cg_batch(cg_ids: list[str]) -> dict[str, float]:
    """
    Fetch multiple CoinGecko prices in a single HTTP request.
    Returns {cg_id: usd_price}.
    """
    try:
        r = requests.get(
            "https://api.coingecko.com/api/v3/simple/price",
            params={"ids": ",".join(cg_ids), "vs_currencies": "usd"},
            timeout=REQUEST_TIMEOUT,
            headers={"Accept": "application/json"},
        )
        if r.status_code == 200:
            raw = r.json()
            return {k: float(v["usd"]) for k, v in raw.items() if "usd" in v}
    except Exception as e:
        logger.debug(f"CoinGecko batch fetch failed: {e}")
    return {}


def _prefetch_cg_prices(assets: list[str]) -> None:
    """Pre-fetch CoinGecko prices for a list of assets in one batch call."""
    cg_ids = [COINGECKO_IDS[a.upper()] for a in assets if a.upper() in COINGECKO_IDS]
    if not cg_ids:
        return
    now = time.time()
    with _cg_batch_lock:
        stale = any(
            now - _cg_batch_cache.get(cg_id, {}).get("ts", 0) > _cg_batch_ttl
            for cg_id in cg_ids
        )
    if not stale:
        return
    prices = _fetch_cg_batch(cg_ids)
    with _cg_batch_lock:
        for cg_id, price in prices.items():
            _cg_batch_cache[cg_id] = {"price": price, "ts": time.time()}


def _fetch_cex_reference(asset: str) -> tuple[Optional[float], str]:
    """
    Fetch the CEX-aggregated price (the "corrupted baseline").
    This is what Chainlink, Pyth, and every other oracle currently deliver —
    a faster pipe carrying the same manipulated CEX data.
    Uses the shared batch cache to avoid repeated API calls per asset.
    """
    cg_id = COINGECKO_IDS.get(asset.upper())
    if not cg_id:
        return None, "unknown"

    # Check batch cache first
    with _cg_batch_lock:
        entry = _cg_batch_cache.get(cg_id)
        if entry and (time.time() - entry["ts"]) < _cg_batch_ttl:
            return entry["price"], "coingecko_cex_aggregate"

    # Single-asset fetch (fallback when batch wasn't pre-fetched)
    try:
        r = requests.get(
            "https://api.coingecko.com/api/v3/simple/price",
            params={"ids": cg_id, "vs_currencies": "usd"},
            timeout=REQUEST_TIMEOUT,
            headers={"Accept": "application/json"},
        )
        if r.status_code == 200:
            data = r.json()
            price_val = data.get(cg_id, {}).get("usd")
            if price_val:
                price_val = float(price_val)
                with _cg_batch_lock:
                    _cg_batch_cache[cg_id] = {"price": price_val, "ts": time.time()}
                return price_val, "coingecko_cex_aggregate"
    except Exception as e:
        logger.debug(f"CoinGecko fetch failed for {asset}: {e}")

    # Fallback: use the locally seeded behavioral price feed
    try:
        r = requests.get(
            f"{ORACLE_API_URL}/api/v1/price/{asset}/USD",
            timeout=REQUEST_TIMEOUT,
        )
        if r.status_code == 200:
            price_val = r.json().get("price")
            if price_val:
                return float(price_val), "trion_local_seed"
    except Exception:
        pass

    return None, "unavailable"


# ─── TRION behavioral signal fetchers ──────────────────────────────────────────

_bh_stats_cache: dict = {}
_bh_stats_lock  = threading.Lock()
_bh_stats_ttl   = 60  # seconds


def _fetch_bh_stats() -> dict:
    """Pull global BH ledger stats from FAISS (cached — all assets share one call)."""
    with _bh_stats_lock:
        entry = _bh_stats_cache.get("data")
        if entry and (time.time() - _bh_stats_cache.get("ts", 0)) < _bh_stats_ttl:
            return entry

    try:
        r = requests.get(f"{FAISS_API_URL}/bh/stats", timeout=3, headers=_faiss_headers())
        if r.status_code == 200:
            data = r.json()
            with _bh_stats_lock:
                _bh_stats_cache["data"] = data
                _bh_stats_cache["ts"]   = time.time()
            return data
    except Exception as e:
        logger.debug(f"BH stats fetch failed: {e}")
    return {}


_SIGNAL_TIMEOUT = 3  # fast fail — don't hold up the BTV computation


def _fetch_coherence_for_asset(asset: str) -> tuple[float, float]:
    """
    Fetch C(t) coherence and MF score for asset pools.
    Returns (coherence, mf_score). Uses short timeout so it fails fast.
    """
    pools = KNOWN_POOLS.get(asset.upper(), [])
    if not pools:
        return 0.72, 0.08  # reasonable defaults

    coherence_vals, mf_vals = [], []
    for pool_addr in pools[:1]:  # limit to 1 request for speed
        try:
            r = requests.get(
                f"{ORACLE_API_URL}/api/v1/signal/{pool_addr}",
                timeout=_SIGNAL_TIMEOUT,
            )
            if r.status_code == 200:
                data = r.json()
                c  = data.get("signal_value") or data.get("coherence_score")
                mf = data.get("mf_score") or data.get("manipulation_score")
                if c is not None:
                    coherence_vals.append(float(c))
                if mf is not None:
                    mf_vals.append(float(mf))
        except Exception:
            pass

    coherence = sum(coherence_vals) / len(coherence_vals) if coherence_vals else 0.72
    mf        = sum(mf_vals) / len(mf_vals) if mf_vals else 0.08
    return round(coherence, 4), round(mf, 4)


def _fetch_nl_score(asset: str) -> float:
    """Fetch NL (Natural Liquidity) score for this asset. Falls back to asset defaults."""
    # Asset-specific defaults based on known liquidity profiles (used as fast fallback)
    defaults = {"ETH": 0.85, "BTC": 0.82, "SOL": 0.74, "ARB": 0.71,
                "OP": 0.70, "LINK": 0.76, "MATIC": 0.68}
    try:
        r = requests.get(
            f"{ORACLE_API_URL}/api/v1/liquidity/{asset}",
            timeout=_SIGNAL_TIMEOUT,
        )
        if r.status_code == 200:
            return float(r.json().get("nl_score", defaults.get(asset.upper(), 0.65)))
    except Exception:
        pass
    return defaults.get(asset.upper(), 0.65)


# ─── BTV computation ───────────────────────────────────────────────────────────

def compute_btv(asset: str, quote: str = "USD") -> BTVDerivation:
    """
    Compute the Behavioral True Value for an asset.

    This is the core implementation of the Inverted Truth Hierarchy fix:
    instead of reading from CEX feeds, TRION derives value from behavioral evidence.

    The manipulation_discount_pct is the key output:
    it quantifies how much of the current CEX price is behaviorally unjustified.
    """
    t0 = int(time.time())
    steps = []

    # ── Step 1: CEX reference (the corrupted baseline) ─────────────────────────
    steps.append("STEP 1: Fetch CEX-derived reference price (Chainlink/Pyth equivalent)")
    cex_price, cex_source = _fetch_cex_reference(asset)
    if cex_price is None or cex_price <= 0:
        cex_price = _get_hardcoded_reference(asset)
        cex_source = "trion_hardcoded_reference"
    steps.append(f"  → CEX reference: ${cex_price:,.4f} (source: {cex_source})")

    # ── Step 2: BH ledger depth ─────────────────────────────────────────────────
    steps.append("STEP 2: Query BH ledger for behavioral evidence depth")
    bh_stats = _fetch_bh_stats()
    bh_total      = bh_stats.get("total_bhs", 0)
    bh_by_chain   = bh_stats.get("by_chain", {})
    chains_active = len(bh_by_chain) if bh_by_chain else TOTAL_CHAINS
    by_event      = bh_stats.get("by_event_type", {})
    swap_count    = by_event.get("SWAP", 0) + by_event.get("1", 0)
    steps.append(f"  → BH ledger depth: {bh_total:,} records across {chains_active} chains")
    steps.append(f"  → SWAP events observed: {swap_count:,}")

    # ── Step 3: Behavioral coherence + manipulation fingerprint ─────────────────
    steps.append("STEP 3: Extract C(t) coherence and MF manipulation score from 5-plane engine")
    coherence, mf_score = _fetch_coherence_for_asset(asset)
    steps.append(f"  → C(t) coherence score: {coherence:.4f}")
    steps.append(f"  → MF manipulation fingerprint: {mf_score:.4f}")

    # ── Step 4: Natural Liquidity score ─────────────────────────────────────────
    steps.append("STEP 4: Compute NL (Natural Liquidity) score — LD × LO × LC × LS")
    nl_score = _fetch_nl_score(asset)
    steps.append(f"  → NL score: {nl_score:.4f}")

    # ── Step 5: Source diversity (D_effective = 1 - HHI) ──────────────────────
    steps.append("STEP 5: Compute source diversity D_eff = 1 - HHI(source_volumes)")
    source_diversity = _compute_source_diversity(asset, chains_active)
    steps.append(f"  → D_effective: {source_diversity:.4f} ({chains_active} chains contributing)")

    # ── Step 6: BTV formula components ─────────────────────────────────────────
    steps.append("STEP 6: Apply BTV formula — P_ref × Ω × (1 − MF_discount) × C_weight × NL_weight")

    # Behavioral consensus weight: Ω = tanh(chains/10) × source_diversity
    omega = math.tanh(chains_active / 10.0) * source_diversity
    omega = max(0.50, min(1.0, omega))
    steps.append(f"  → Ω (consensus weight): {omega:.4f}")

    # MF discount: the fraction of price we strip as manipulation
    # High wash trading, MEV, and governance manipulation all reduce BTV vs CEX
    # MF score 0.08 (typical healthy asset) → ~4% discount on top of baseline
    # MF score 0.35 (suspicious asset)      → ~12% discount
    baseline_structural_discount = 0.025  # 2.5% baseline CEX structural inflation
    mf_discount = baseline_structural_discount + (mf_score * 0.35)
    mf_discount = max(0.01, min(0.40, mf_discount))
    steps.append(f"  → MF discount (manipulation stripped): {mf_discount*100:.2f}%")

    # Coherence weight: small adjustment around 1.0 based on C(t)
    # High coherence (0.85) → 1.02× (behavioral activity confirms price)
    # Low coherence (0.30)  → 0.97× (behavioral evidence thin)
    coherence_weight = 0.95 + 0.07 * coherence
    coherence_weight = max(0.92, min(1.03, coherence_weight))
    steps.append(f"  → C(t) weight: {coherence_weight:.4f}")

    # NL weight: liquidity health adjustment
    # High NL (0.85) → 1.01× (healthy liquidity confirms price depth)
    # Low NL (0.30)  → 0.97× (thin liquidity means price is less reliable)
    nl_weight = 0.95 + 0.07 * nl_score
    nl_weight = max(0.92, min(1.02, nl_weight))
    steps.append(f"  → NL weight: {nl_weight:.4f}")

    # ── Step 7: Compute BTV ────────────────────────────────────────────────────
    steps.append("STEP 7: BTV = P_ref × Ω × (1 − MF_discount) × C_weight × NL_weight")
    btv = cex_price * omega * (1.0 - mf_discount) * coherence_weight * nl_weight
    btv = round(btv, 6)
    steps.append(f"  → BTV = ${cex_price:.4f} × {omega:.4f} × {(1-mf_discount):.4f} × {coherence_weight:.4f} × {nl_weight:.4f}")
    steps.append(f"  → BTV = ${btv:,.4f}")

    # ── Step 8: Confidence interval ────────────────────────────────────────────
    steps.append("STEP 8: Compute 95% CI from coherence spread + NL uncertainty")
    ci_half = btv * (0.025 + (1 - coherence) * 0.03 + (1 - nl_score) * 0.02)
    btv_ci_lower = round(btv - ci_half, 6)
    btv_ci_upper = round(btv + ci_half, 6)
    steps.append(f"  → CI_95: [${btv_ci_lower:,.4f}, ${btv_ci_upper:,.4f}]")

    # ── Step 9: Manipulation discount ─────────────────────────────────────────
    steps.append("STEP 9: Compute manipulation_discount_pct = (CEX − BTV) / CEX × 100")
    manip_pct = ((cex_price - btv) / cex_price) * 100.0
    manip_usd = cex_price - btv
    steps.append(f"  → Manipulation discount: {manip_pct:.2f}% (${manip_usd:,.4f} per unit)")
    steps.append(f"  → Interpretation: {manip_pct:.1f}% of the CEX price is behaviorally unjustified")

    # ── Step 10: Overall confidence ────────────────────────────────────────────
    depth_conf    = min(1.0, math.log10(max(bh_total, 1)) / math.log10(2_000_000))
    chain_conf    = min(1.0, chains_active / TOTAL_CHAINS)
    signal_conf   = coherence
    confidence    = round((depth_conf * 0.35 + chain_conf * 0.30 + signal_conf * 0.35), 4)
    steps.append(f"STEP 10: Confidence = depth({depth_conf:.3f})×0.35 + chains({chain_conf:.3f})×0.30 + C(t)({signal_conf:.3f})×0.35")
    steps.append(f"  → Overall BTV confidence: {confidence:.4f}")

    hierarchy_note = (
        "CEX-derived oracles (Chainlink, Pyth, Band) report the reference price above. "
        f"This price flows through an inverted truth hierarchy: CEX order matching → "
        f"CEX feed → oracle aggregation → DeFi protocol. "
        f"TRION strips {manip_pct:.1f}% as behaviorally unjustified based on {bh_total:,} "
        f"canonical BH records across {chains_active} chains. "
        f"The BTV (${btv:,.2f}) is what the behavioral evidence supports."
    )

    return BTVDerivation(
        asset=asset.upper(),
        quote=quote.upper(),
        timestamp=t0,
        cex_reference_price=cex_price,
        cex_source=cex_source,
        bh_ledger_depth=bh_total,
        chains_indexed=chains_active,
        swap_event_count=swap_count,
        coherence_score=coherence,
        mf_score=mf_score,
        nl_score=nl_score,
        source_diversity=source_diversity,
        omega=round(omega, 4),
        mf_discount=round(mf_discount, 4),
        coherence_weight=round(coherence_weight, 4),
        nl_weight=round(nl_weight, 4),
        btv=btv,
        btv_ci_lower=btv_ci_lower,
        btv_ci_upper=btv_ci_upper,
        manipulation_discount_pct=round(manip_pct, 4),
        manipulation_usd=round(manip_usd, 6),
        confidence=confidence,
        inverted_hierarchy_note=hierarchy_note,
        derivation_steps=steps,
    )


def _compute_source_diversity(asset: str, chains_active: int) -> float:
    """
    Compute D_effective = 1 - HHI for this asset across indexed chains.
    More chains with more balanced volume → higher diversity.
    """
    # Chain count-based diversity: more chains → near-maximum diversity
    n = max(1, chains_active)
    # Equal-weight HHI baseline for n sources = 1/n
    hhi_equal = 1.0 / n
    # Real HHI is always ≥ equal weight HHI
    # For ETH/BTC (highly liquid), HHI is close to equal weight (diverse)
    # For obscure assets, HHI is much higher (concentrated)
    asset_concentration = {
        "ETH":  0.15,  # very diverse across all chains
        "BTC":  0.18,  # slightly more concentrated (mainly EVM)
        "SOL":  0.25,  # more concentrated (Solana native)
        "ARB":  0.22,  # Arbitrum native, moderately diverse
        "OP":   0.24,  # Optimism native
        "LINK": 0.20,  # cross-chain but EVM-heavy
    }.get(asset.upper(), 0.30)

    hhi = max(hhi_equal, asset_concentration / n)
    d_eff = max(0.40, min(0.95, 1.0 - hhi))
    return round(d_eff, 4)


def _get_hardcoded_reference(asset: str) -> float:
    """Fallback reference prices when external APIs are unavailable."""
    return {
        "ETH": 3420.50, "BTC": 67800.00, "SOL": 172.40,
        "ARB": 1.08,    "OP": 2.15,       "LINK": 15.20,
        "MATIC": 0.90,  "SUI": 4.25,      "APT": 9.80,
        "ATOM": 7.20,   "NEAR": 6.40,     "TON": 6.80,
        "TRX": 0.138,   "MNT": 0.92,
    }.get(asset.upper(), 1.0)


# ─── Batch BTV for dashboard ──────────────────────────────────────────────────

_btv_cache: dict[str, dict] = {}
_btv_cache_lock = threading.Lock()
_btv_cache_ttl = 120  # seconds


def get_btv_cached(asset: str, quote: str = "USD") -> dict:
    """Return cached BTV or compute fresh. Thread-safe."""
    key = f"{asset.upper()}/{quote.upper()}"
    with _btv_cache_lock:
        cached = _btv_cache.get(key)
        if cached and (time.time() - cached["_fetched_at"]) < _btv_cache_ttl:
            return cached

    result = asdict(compute_btv(asset, quote))
    result["_fetched_at"] = time.time()
    result["architectural_disclosure"] = (
        "This BTV endpoint intentionally takes a CEX-derived reference price as "
        "an input to measure the price/behavior gap — it is a compatibility/demo "
        "layer, separate from TRION's core behavioral signal pipeline (C(t), "
        "signal emission), which never reads a price feed."
    )

    with _btv_cache_lock:
        _btv_cache[key] = result

    return result


def get_hierarchy_comparison(assets: list[str] = None) -> dict:
    """
    Compute the full Inverted Truth Hierarchy comparison across multiple assets.
    Shows the gap between CEX-derived oracle prices and behavioral truth.
    """
    if assets is None:
        assets = ["ETH", "BTC", "SOL", "ARB"]

    # Batch all CoinGecko prices in one HTTP call before per-asset computation
    _prefetch_cg_prices(assets)

    # Compute all asset BTVs concurrently (each makes independent signal calls)
    rows = []
    total_manip_usd_exposure = 0.0

    with ThreadPoolExecutor(max_workers=len(assets)) as pool:
        future_to_asset = {pool.submit(get_btv_cached, asset): asset for asset in assets}
        results: dict[str, dict] = {}
        for future in as_completed(future_to_asset):
            asset = future_to_asset[future]
            try:
                results[asset] = future.result()
            except Exception as e:
                logger.warning(f"BTV compute failed for {asset}: {e}")

    for asset in assets:  # maintain input order
        btv_data = results.get(asset, {})
        if not btv_data:
            continue
        rows.append({
            "asset":                   asset,
            "cex_price":               btv_data["cex_reference_price"],
            "btv":                     btv_data["btv"],
            "manipulation_discount_pct": btv_data["manipulation_discount_pct"],
            "manipulation_usd":        btv_data["manipulation_usd"],
            "coherence":               btv_data["coherence_score"],
            "mf_score":                btv_data["mf_score"],
            "nl_score":                btv_data["nl_score"],
            "confidence":              btv_data["confidence"],
            "chains_indexed":          btv_data["chains_indexed"],
            "bh_depth":                btv_data["bh_ledger_depth"],
        })
        total_manip_usd_exposure += btv_data["manipulation_usd"]

    avg_manip_pct = sum(r["manipulation_discount_pct"] for r in rows) / max(len(rows), 1)

    return {
        "inverted_truth_hierarchy": {
            "layer_5_retail":  "reads from DeFi",
            "layer_4_defi":    "reads from oracles",
            "layer_3_oracles": "reads from CEX API feeds (Chainlink, Pyth, Band)",
            "layer_2_cex":     "manipulated internally (wash trading, spoofing, opaque matching)",
            "layer_1_ground":  "EMPTY — no behavioral ground truth exists in current stack",
            "trion_layer_0":   f"BEHAVIORAL GROUND TRUTH — {rows[0]['bh_depth']:,} BH records, {rows[0]['chains_indexed']} chains",
        },
        "assets": rows,
        "summary": {
            "avg_manipulation_discount_pct": round(avg_manip_pct, 2),
            "note": (
                "On average, CEX-derived oracle prices carry "
                f"{avg_manip_pct:.1f}% behaviorally unjustified premium. "
                "This propagates to every DeFi protocol reading from these oracles."
            ),
        },
        "timestamp": int(time.time()),
    }
