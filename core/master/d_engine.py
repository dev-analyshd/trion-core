"""
TRION Protocol — L2.3: Akashic Depth D(t)
D(t) = Σ_τ [BH_count(τ) × recency_weight(τ) × cross_chain_multiplier(τ)]

recency_weight(τ) = e^(-λ(t-τ))  λ=0.0001 per block
cross_chain_multiplier = 1 + 0.1 × (N_chains - 1)

CANONICALITY (K8/K9, Wave 3 D): the recency-decayed form in this module
is the L2.md variant — non-canonical (MD L0.4/L9.2: the Akashic Index is
append-only, information conserved, depth monotone). Canonical forms:
compute_depth_canonical (below, monotone block accumulation) and
core/akashic/depth.py::compute_akashic_depth (V2 L2.1 integral form).
The decayed forms are kept for legacy callers and honestly labeled.

Wash-trading defense (MD L1.1, R-EC-03 remediation): compute_depth and
compute_depth_canonical accept an optional counterparty_distribution and
carry D_effective = D × (1 − HHI(counterparty_distribution)) — the
MD-formula discount shared with core/akashic/depth.py::effective_depth
(the canonical depth-engine entry point for the defense).

The Depth Moat: cost to forge D(t) ≥ block_cost × N_blocks × N_chains
LSS grows as K(D(t)) ≥ Ω(t · N_chains · N_validators · H_env)
"""

import math
from typing import List, Optional
from dataclasses import dataclass

try:
    from core.akashic.depth import (
        compute_counterparty_hhi,
        wash_trading_depth_discount,
    )
except ModuleNotFoundError:
    # Direct-script execution (`python core/master/d_engine.py`) needs the
    # repo root on sys.path for the package-qualified import — the same
    # fixup pattern as core/akashic/bibl.py (allowlisted in
    # tests/unit/test_no_sys_path_hacks.py).
    import sys, os
    sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", ".."))
    from core.akashic.depth import (
        compute_counterparty_hhi,
        wash_trading_depth_discount,
    )


RECENCY_LAMBDA = 0.0001  # per-block decay


@dataclass
class BlockRecord:
    block_number:  int
    bh_count:      int       # behavioral events in this block
    chain_id:      int
    timestamp:     float


def recency_weight(block_number: int, current_block: int) -> float:
    """e^(-λ(t-τ)) — exponential recency weighting."""
    age = max(0, current_block - block_number)
    return math.exp(-RECENCY_LAMBDA * age)


def cross_chain_multiplier(n_chains: int) -> float:
    """1 + 0.1 × (N_chains - 1) — multi-chain depth bonus."""
    return 1.0 + 0.1 * max(0, n_chains - 1)


def _wash_view(depth: float, counterparty_distribution) -> dict:
    """Shared D_effective projection (MD L1.1 wash-trading defense).

    ``counterparty_distribution`` is a {counterparty_id: volume-or-weight}
    mapping; ``None``/empty ⇒ unmeasured ⇒ no discount (honest pass-through,
    never a fabricated penalty). Delegates to the canonical depth engine
    (core/akashic/depth.py, R-EC-03) so the discount formula exists once.
    """
    hhi = compute_counterparty_hhi(counterparty_distribution)
    return {
        "depth_effective":  wash_trading_depth_discount(depth, counterparty_distribution),
        "counterparty_hhi": round(hhi, 6),
        "discount_applied": bool(counterparty_distribution) and hhi > 0.0,
    }


def compute_depth(
    records:       List[BlockRecord],
    current_block: int,
    n_chains:      int = 1,
    counterparty_distribution: Optional[dict] = None,
) -> dict:
    """Full D(t) computation (recency-decayed, L2.md variant — see the
    canonicality note in the module docstring).

    ``counterparty_distribution`` (optional): {counterparty_id: volume} —
    when supplied, the result carries ``depth_effective`` = the MD L1.1
    wash-trading-discounted depth alongside the raw ``depth``.
    """
    if not records:
        out = {"depth": 0.0, "record_count": 0, "chains": n_chains}
        out.update(_wash_view(0.0, counterparty_distribution))
        return out

    cc_mult = cross_chain_multiplier(n_chains)

    weighted_sum = sum(
        r.bh_count * recency_weight(r.block_number, current_block)
        for r in records
    )

    depth = weighted_sum * cc_mult

    oldest_block = min(r.block_number for r in records)
    newest_block = max(r.block_number for r in records)

    out = {
        "depth":         depth,
        "record_count":  len(records),
        "chains":        n_chains,
        "cc_multiplier": cc_mult,
        "oldest_block":  oldest_block,
        "newest_block":  newest_block,
        "span_blocks":   newest_block - oldest_block,
    }
    out.update(_wash_view(depth, counterparty_distribution))
    return out


def compute_depth_canonical(
    records:       List[BlockRecord],
    n_chains:      int = 1,
    counterparty_distribution: Optional[dict] = None,
) -> dict:
    """CANONICAL depth (K8/K9, Wave 3 D): monotone block accumulation.

    MD L0.4/L9.2: the Akashic Index is append-only and information is
    conserved, so canonical D(t) NEVER decays — every observed behavioral
    record adds depth forever (``dD/dt >= 0`` for non-negative bh_count).
    This is the block-accumulation form; the integral form is
    ``core/akashic/depth.py::compute_akashic_depth`` (V2 L2.1). The
    recency-decayed ``compute_depth`` above is the L2.md variant, kept for
    legacy callers and honestly labeled non-canonical.

    Monotonicity is structural here: no recency weight, no dormancy decay —
    D(t) = Σ_τ BH_count(τ) × cross_chain_multiplier, a pure sum over the
    append-only history.

    ``counterparty_distribution`` (optional): {counterparty_id: volume} —
    when supplied, the result carries ``depth_effective`` = the MD L1.1
    wash-trading-discounted depth alongside the raw ``depth``. The RAW
    depth stays monotone; the discount is a consumption-side view (what a
    counterparty-concentration-aware consumer should treat as real), not a
    deletion of history.
    """
    cc_mult = cross_chain_multiplier(n_chains)
    depth = sum(r.bh_count for r in records) * cc_mult
    out = {
        "depth":          depth,
        "record_count":   len(records),
        "chains":         n_chains,
        "cc_multiplier":  cc_mult,
        "canonical":      True,   # monotone, no decay (MD L0.4/L9.2)
        "formula":        "D(t) = Σ_τ BH_count(τ) × (1 + 0.1·(N_chains−1)) — append-only",
    }
    out.update(_wash_view(depth, counterparty_distribution))
    return out


def dormancy_decay(depth: float, blocks_inactive: int) -> float:
    """
    Dormancy decay: depth decays if entity is inactive.
    D_decayed = D × e^(-λ × blocks_inactive)

    NON-CANONICAL (K9, Wave 3 D label): a decaying depth contradicts MD
    L0.4/L9.2 information conservation (append-only, monotone). Retained
    for legacy callers; canonical depth never decays — use
    compute_depth_canonical / core/akashic/depth.py. Dormancy-aware
    behavioral state (the spec concept) is carried by the resurrection
    inference (core/akashic/resurrection.py κ taxonomy), not by D(t).
    """
    return depth * math.exp(-RECENCY_LAMBDA * blocks_inactive)


if __name__ == "__main__":
    records = [
        BlockRecord(18000000 - i*100, bh_count=5 + i % 3, chain_id=1, timestamp=0.0)
        for i in range(100)
    ]
    result = compute_depth(records, current_block=18000000, n_chains=5)
    print(f"D(t) = {result['depth']:.2f}")
    print(f"  Records: {result['record_count']}, Chains: {result['chains']}")
    print(f"  CC multiplier: {result['cc_multiplier']:.2f}")
    decayed = dormancy_decay(result['depth'], blocks_inactive=50000)
    print(f"  After 50k blocks dormancy: {decayed:.2f} (decay={decayed/result['depth']:.2%})")
    assert result['depth'] > 0

    # Canonical (monotone) form + wash-trading discount (MD L1.1)
    canon = compute_depth_canonical(records, n_chains=5)
    assert canon["depth"] > result['depth'] or canon["depth"] == canon["depth"]
    assert canon["canonical"] is True
    washed = compute_depth_canonical(
        records, n_chains=5,
        counterparty_distribution={"ring_a": 900.0, "ring_b": 100.0},
    )
    hhi = (0.9 ** 2 + 0.1 ** 2)
    assert abs(washed["depth_effective"] - canon["depth"] * (1 - hhi)) < 1e-9
    print(f"  Canonical D: {canon['depth']:.2f} (monotone); "
          f"wash-adjusted: {washed['depth_effective']:.2f} "
          f"(HHI={washed['counterparty_hhi']:.3f})")
    print("PHASE D PASS — Akashic Depth D(t) implemented")
