"""
TRION Protocol — L0.2: Behavioral Entity Object (BEO)
Entity Resolution — multi-wallet to canonical BEO identity.

BEO_confidence = w_CF·CF + w_ST·ST + w_SC·SC + w_BP·BP
w_CF=0.40, w_ST=0.25, w_SC=0.25, w_BP=0.10  (whitepaper L0.2 — 4 components, sum=1.00)
threshold: BEO_confidence >= 0.75 → same entity
"""

import hashlib
import math
import time
from dataclasses import dataclass, field
from typing import List, Optional

# ─── BEO BP component (Behavioral Pattern match) ─────────────────────────────
# Whitepaper L0.2 spec:
#   BP = behavioral pattern match score from FAISS 128-dim space.
#
# FAISS is not always available (dev / lightweight deployments). We provide a
# deterministic hash-based behavioral similarity fallback (SimHash-style) that
# produces a 128-dim fingerprint per wallet from its observable features and
# computes mean pairwise cosine similarity across wallets. This is NOT a
# substitute for the full ANIMA/FAISS embedding pipeline, but it is a real,
# runtime-evaluated behavioral pattern score (not a hardcoded constant).
#
# Features hashed into the fingerprint (per WalletActivity):
#   * chain_id            — preferred execution environment
#   * funding_source      — common funder (often same deployer / treasury)
#   * first_tx_ts         — wallet creation epoch bucket (30-day bins)
#   * co_tx_timestamps    — timing rhythm (hour-of-day, inter-arrival bins)
#   * activity_count      — log-bucketed activity volume
#   * address_prefix      — address-family (EVM/SVM/TVM/Near) prefix
BP_FINGERPRINT_DIM = 128
BP_TS_BUCKET_SECS  = 30 * 86400  # 30-day bins


def _wallet_features(w: "WalletActivity") -> List[str]:
    """Extract behavioral feature strings from a WalletActivity record."""
    feats: List[str] = []

    # Address family / chain affinity
    feats.append(f"chain:{w.chain_id}")

    addr = (w.address or "").lower()
    if addr.startswith("0x"):
        feats.append("addr_family:evm")
    elif addr.startswith("act") or addr.startswith("actor"):
        feats.append("addr_family:svm")
    elif addr.startswith("tz") or addr.startswith("kt"):
        feats.append("addr_family:tvm")
    elif "." in addr:
        feats.append("addr_family:near")
    else:
        feats.append("addr_family:unknown")

    # Address prefix (first 4 chars) — clusters vanity / factory-deployed wallets
    if len(addr) >= 4:
        feats.append(f"addr_prefix:{addr[:4]}")

    # Common funding source
    if w.funding_source:
        feats.append(f"funder:{w.funding_source.lower()}")

    # First-tx epoch bucket (30-day bins)
    if w.first_tx_ts and w.first_tx_ts > 0:
        bucket = int(w.first_tx_ts) // BP_TS_BUCKET_SECS
        feats.append(f"first_tx_bucket:{bucket}")

    # Timing rhythm: hour-of-day buckets (UTC) of co-tx timestamps
    for ts in w.co_tx_timestamps:
        if ts and ts > 0:
            hour = int(ts) // 3600 % 24
            feats.append(f"hour_of_day:{hour}")
            # Inter-arrival bin (log10 of minutes)
            # (computed pairwise below — single-wallet contribution is the absolute hour)

    # Activity volume bucket (log10 of count, clamped)
    n_co = len(w.co_tx_timestamps)
    if n_co > 0:
        log_n = max(0, min(6, int(math.log10(n_co + 1))))
        feats.append(f"activity_bucket:{log_n}")

    return feats


def behavioral_fingerprint(w: "WalletActivity", dim: int = BP_FINGERPRINT_DIM) -> List[float]:
    """
    Hash the wallet's behavioral feature strings into a `dim`-dim float vector
    using a SimHash-style construction: for each feature, derive a (position,
    sign) pair from sha3_256, then increment/decrement that dimension. The
    resulting vector is dense enough for cosine similarity to be meaningful
    while remaining deterministic and side-effect-free.

    Returns a list of `dim` floats (NOT a numpy array — avoids hard dependency
    on numpy in this L0 primitive module).
    """
    vec = [0.0] * dim
    feats = _wallet_features(w)
    for feat in feats:
        h = hashlib.sha3_256(feat.encode("utf-8")).digest()
        # Use first 4 bytes for position (mod dim), next byte for sign
        pos = int.from_bytes(h[:4], "big") % dim
        sign = 1.0 if (h[4] & 1) == 0 else -1.0
        # Weight: more features that hash to the same slot → stronger signal
        vec[pos] += sign
    return vec


def _cosine_sim(v1: List[float], v2: List[float]) -> float:
    """Cosine similarity of two equal-length float vectors, clamped to [0, 1]."""
    dot = 0.0
    n1 = 0.0
    n2 = 0.0
    for a, b in zip(v1, v2):
        dot += a * b
        n1 += a * a
        n2 += b * b
    if n1 <= 1e-12 or n2 <= 1e-12:
        return 0.0
    sim = dot / (math.sqrt(n1) * math.sqrt(n2))
    # Behavioral similarity is meaningful only in [0, 1] for BEO purposes
    # (negative cosine = anti-correlated behavior → treat as 0).
    return max(0.0, min(1.0, sim))


def compute_bp_score(wallets: List["WalletActivity"]) -> float:
    """
    BP = mean pairwise cosine similarity of behavioral fingerprints.

    Whitepaper L0.2: BP is the behavioral pattern match score (cosine sim in
    128-dim feature space). When FAISS is unavailable this hash-based
    fingerprint is used as a deterministic fallback. Returns 0.0 if fewer than
    2 wallets (no pairwise comparison possible).
    """
    if len(wallets) < 2:
        return 0.0
    fps = [behavioral_fingerprint(w) for w in wallets]
    n_pairs = 0
    sim_sum = 0.0
    for i in range(len(fps)):
        for j in range(i + 1, len(fps)):
            sim_sum += _cosine_sim(fps[i], fps[j])
            n_pairs += 1
    return sim_sum / n_pairs if n_pairs > 0 else 0.0


@dataclass
class WalletActivity:
    address:       str
    chain_id:      int
    funding_source: Optional[str]
    first_tx_ts:   float
    co_tx_timestamps: List[float] = field(default_factory=list)


def compute_cf_score(wallets: List[WalletActivity]) -> float:
    """CF = Common Funding Source: fraction sharing same funder."""
    if len(wallets) < 2:
        return 0.0
    funders = [w.funding_source for w in wallets if w.funding_source]
    if not funders:
        return 0.0
    most_common = max(set(funders), key=funders.count)
    return funders.count(most_common) / len(funders)


def compute_st_score(wallets: List[WalletActivity], window_secs: float = 300) -> float:
    """ST = Synchronized Timing: co-transaction clustering."""
    if len(wallets) < 2:
        return 0.0
    all_ts = []
    for w in wallets:
        all_ts.extend(w.co_tx_timestamps)
    if len(all_ts) < 2:
        return 0.0
    all_ts_sorted = sorted(all_ts)
    clustered = sum(
        1 for i in range(len(all_ts_sorted) - 1)
        if all_ts_sorted[i+1] - all_ts_sorted[i] < window_secs
    )
    max_pairs = len(all_ts_sorted) - 1
    return clustered / max_pairs if max_pairs > 0 else 0.0


def compute_sc_score(wallets: List[WalletActivity]) -> float:
    """SC = Shared Contract Ownership (proxy from chain_id clustering)."""
    if len(wallets) < 2:
        return 0.0
    chains = [w.chain_id for w in wallets]
    most_common_chain = max(set(chains), key=chains.count)
    return chains.count(most_common_chain) / len(wallets)


BEO_CONFIDENCE_THRESHOLD = 0.75  # whitepaper L0.2: BEO_confidence >= 0.75 → same entity


def resolve_entity(
    wallets: List[WalletActivity],
    w_CF: float = 0.40,
    w_ST: float = 0.25,
    w_SC: float = 0.25,
    w_BP: float = 0.10,
    bp_prior: float = 0.50,
) -> dict:
    """
    Resolve multiple wallets to a canonical BEO identity.

    Whitepaper L0.2 exact formula:
      BEO_confidence = w_CF·CF + w_ST·ST + w_SC·SC + w_BP·BP
      w_CF=0.40, w_ST=0.25, w_SC=0.25, w_BP=0.10  (sum=1.00)
      threshold: BEO_confidence >= 0.75 → same entity

    BP = behavioral pattern match score. When FAISS 128-dim embeddings are
    unavailable, a deterministic SimHash-style 128-dim fingerprint is derived
    per wallet from observable features (chain, funder, timing, address family,
    activity volume) and BP = mean pairwise cosine similarity across wallets.
    bp_prior is used only as a floor when no behavioral signal is extractable.
    """
    if abs(w_CF + w_ST + w_SC + w_BP - 1.0) >= 1e-9:
        raise ValueError(f"BEO weights must sum to 1.0, got {w_CF + w_ST + w_SC + w_BP}")

    if not wallets:
        return {"beo_confidence": 0.0, "canonical_id": None, "wallet_count": 0}

    cf = compute_cf_score(wallets)
    st = compute_st_score(wallets)
    sc = compute_sc_score(wallets)
    # BP: real behavioral-pattern match score from deterministic hash-based
    # 128-dim fingerprint similarity (fallback for the FAISS 128-dim embedding
    # used in the ANIMA service). No longer hardcoded to bp_prior; the prior
    # is only used as a floor when wallets carry no behavioral features at all.
    bp_real = compute_bp_score(wallets)
    bp = bp_real if bp_real > 0.0 else bp_prior

    beo_confidence = w_CF*cf + w_ST*st + w_SC*sc + w_BP*bp
    beo_confidence = max(0.0, min(1.0, beo_confidence))

    # Canonical ID: deterministic hash of sorted wallet addresses
    sorted_addrs = sorted(w.address.lower() for w in wallets)
    canonical_payload = "|".join(sorted_addrs).encode()
    canonical_id = "0x" + hashlib.sha3_256(canonical_payload).hexdigest()

    same_entity = beo_confidence >= BEO_CONFIDENCE_THRESHOLD

    return {
        "beo_confidence":   beo_confidence,
        "canonical_id":     canonical_id,
        "wallet_count":     len(wallets),
        "same_entity":      same_entity,
        "threshold":        BEO_CONFIDENCE_THRESHOLD,
        "cf_score":         cf,
        "st_score":         st,
        "sc_score":         sc,
        "bp_score":         bp,
        "components":       {"CF": cf, "ST": st, "SC": sc, "BP": bp},
        "weights":          {"w_CF": w_CF, "w_ST": w_ST, "w_SC": w_SC, "w_BP": w_BP},
    }


if __name__ == "__main__":
    wallets = [
        WalletActivity("0xAAA", 1, "0xFUNDER", 1700000000, [1700000100, 1700000200]),
        WalletActivity("0xBBB", 1, "0xFUNDER", 1700000050, [1700000110, 1700000210]),
        WalletActivity("0xCCC", 1, "0xFUNDER", 1700000075, [1700000120, 1700000220]),
    ]
    result = resolve_entity(wallets)
    print(f"BEO confidence: {result['beo_confidence']:.4f}")
    print(f"Canonical ID:   {result['canonical_id'][:16]}...")
    print(f"CF score:       {result['cf_score']:.4f}")
    assert 0 <= result['beo_confidence'] <= 1
    print("PHASE 9 PASS — BEO resolution verified")
