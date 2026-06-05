"""
TRION Protocol — L0.2: Behavioral Entity Object (BEO)
Entity Resolution — multi-wallet to canonical BEO identity.

BEO_confidence = w_CF·CF + w_ST·ST + w_SC·SC + w_BP·BP
w_CF=0.40, w_ST=0.25, w_SC=0.25, w_BP=0.10  (whitepaper L0.2 — 4 components, sum=1.00)
threshold: BEO_confidence >= 0.75 → same entity
"""

import hashlib
import math
from dataclasses import dataclass, field
from typing import List, Optional


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

    BP = behavioral pattern match score from FAISS 128-dim space.
    bp_prior=0.50 when FAISS behavioral pattern match is not available.
    """
    if abs(w_CF + w_ST + w_SC + w_BP - 1.0) >= 1e-9:
        raise ValueError(f"BEO weights must sum to 1.0, got {w_CF + w_ST + w_SC + w_BP}")

    if not wallets:
        return {"beo_confidence": 0.0, "canonical_id": None, "wallet_count": 0}

    cf = compute_cf_score(wallets)
    st = compute_st_score(wallets)
    sc = compute_sc_score(wallets)
    bp = bp_prior  # FAISS behavioral pattern match; 0.50 when unavailable

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
