"""
liquidity_ocean.py — Liquidity Ocean: cross-chain NL signal aggregation
Aggregates NL scores across all integrated chains into a coherent ocean signal.
L_ocean(t) = Σ (NL_k × W_k × availability_k) / Σ W_k
Spec: BTCP Master Implementation Spec §7.2

ALSO re-exported from this module (the spec §6.1 pseudocode names this file):
the per-asset, form-equivalent LIQUIDITY_OCEAN_SCORE engine —
    LIQUIDITY_OCEAN_SCORE = Σ_forms [VALUE × 1/shift_cost
                                      × 1/time_to_convert × BEO_health]
("No Asset Has Zero Liquidity"). Canonical implementation:
core/extended/natural_liquidity.py (importable package path, next to the
L7.1 NL engine); re-exported here so BOTH import paths work:
    from liquidity_ocean import liquidity_ocean_score, LiquidityOceanEngine, ...
    from core.extended.natural_liquidity import liquidity_ocean_score, ...
and so the BTCP integration hub import (`from liquidity_ocean import
LiquidityOceanEngine`, core/btcp/integration.py module 3.4) resolves.
"""

import math
from typing import Optional
from nl_score_engine import compute_nl_score, apply_oe_correction

# ─── §6.1 form-equivalent Liquidity Ocean (re-export) ──────────────────────
# The repo-root import-path bootstrap is performed by the nl_score_engine
# import above (allowlisted P3-CONSOLIDATE path fixup) — this file itself
# introduces NO new path bootstrap (tests/unit/test_no_sys_path_hacks.py
# guard stays green).
from core.extended.natural_liquidity import (  # noqa: E402,F401  (re-export)
    liquidity_ocean_score,
    build_liquidity_ocean_signal,
    LiquidityOceanEngine,
    LIQUIDITY_OCEAN_ROUTING_THRESHOLD,
    OCEAN_REF_SHIFT_COST,
    OCEAN_REF_SHIFT_TIME,
)

# ─── Chain weight configuration ───────────────────────────────────────────────
CHAIN_WEIGHTS = {
    42161:  0.25,   # Arbitrum One — primary BTCP chain
    8453:   0.18,   # Base
    10:     0.15,   # Optimism
    137:    0.12,   # Polygon
    1:      0.20,   # Ethereum mainnet (higher weight, lower BTCP score due to gas)
    56:     0.05,   # BNB Chain
    43114:  0.05,   # Avalanche
    421614: 0.01,   # Arbitrum Sepolia (testnet)
}

OOA_CHAIN_PENALTY = 0.70   # Θ_OOA penalty applied to OOA chain weights

# ─── Ocean coherence (C(t)) ───────────────────────────────────────────────────
def compute_ocean_coherence(
    nl_scores:    dict[int, float],   # chain_id → NL score
    chain_weights: dict[int, float] = None,
) -> dict:
    """
    C(t): Cross-chain NL coherence.
    Measures agreement between chain NL signals.
    High C(t) = consistent behavioral environment across chains.
    Low C(t) = fragmented liquidity → BTCP routes to most coherent subset.
    """
    if chain_weights is None:
        chain_weights = CHAIN_WEIGHTS

    active_chains = {cid: nl for cid, nl in nl_scores.items() if nl > 0}
    if not active_chains:
        return {"coherence": 0.0, "l_ocean": 0.0, "active_chains": 0}

    # Weighted mean NL
    total_weight = sum(chain_weights.get(cid, 0.01) for cid in active_chains)
    l_ocean = sum(
        nl * chain_weights.get(cid, 0.01)
        for cid, nl in active_chains.items()
    ) / total_weight if total_weight > 0 else 0.0

    # Coherence: 1 - normalized variance
    mean_nl = sum(active_chains.values()) / len(active_chains)
    if mean_nl == 0:
        coherence = 0.0
    else:
        variance = sum((nl - mean_nl) ** 2 for nl in active_chains.values()) / len(active_chains)
        cv = math.sqrt(variance) / mean_nl
        coherence = 1.0 - math.tanh(2.0 * cv)

    return {
        "coherence":     round(coherence, 6),
        "l_ocean":       round(l_ocean, 6),
        "active_chains": len(active_chains),
        "total_weight":  round(total_weight, 4),
    }


# ─── HHI for liquidity concentration (market-level) ──────────────────────────
def compute_liquidity_hhi(nl_scores: dict[int, float]) -> float:
    """
    Liquidity HHI across chains.
    High HHI = liquidity concentrated on few chains → fragile routing.
    Low HHI = distributed → BTCP can always find a path.
    """
    total = sum(nl_scores.values())
    if total == 0:
        return 1.0
    return sum((nl / total) ** 2 for nl in nl_scores.values())


# ─── Liquidity Ocean aggregator ───────────────────────────────────────────────
class LiquidityOcean:
    """
    Central NL signal aggregator.
    Maintains per-chain NL scores and computes ocean-level metrics.
    """

    def __init__(self, oe_factor: float = 0.0):
        self.chain_nl: dict[int, float] = {}
        self.oe_factor = oe_factor
        self.coherence_history: list[float] = []

    def update_chain(
        self,
        chain_id:      int,
        pool_depths:   list[float],
        pool_corrs:    Optional[list[float]] = None,
        depth_history: Optional[list[float]] = None,
        price_history: Optional[list[float]] = None,
        is_ooa:        bool = False,
    ) -> dict:
        """
        Update NL signal for a single chain. OOA chains get penalty factor.
        """
        result = compute_nl_score(pool_depths, pool_corrs, depth_history, price_history)
        nl = result["nl_score"]

        # Observer effect correction
        nl = apply_oe_correction(nl, self.oe_factor)

        # OOA chains: score × OOA_penalty
        if is_ooa:
            nl = nl * OOA_CHAIN_PENALTY

        self.chain_nl[chain_id] = nl
        return result

    def get_ocean_signal(self) -> dict:
        ocean = compute_ocean_coherence(self.chain_nl)

        # Track coherence history for dynamic threshold adjustment
        self.coherence_history.append(ocean["coherence"])
        if len(self.coherence_history) > 1000:
            self.coherence_history.pop(0)

        hhi = compute_liquidity_hhi(self.chain_nl)

        return {
            **ocean,
            "hhi":             round(hhi, 6),
            "chain_nl":        {str(k): round(v, 6) for k, v in self.chain_nl.items()},
            "oe_factor":       round(self.oe_factor, 6),
            "best_chain":      self._best_chain(),
            "routing_viable":  ocean["coherence"] > 0.40,
        }

    def _best_chain(self) -> Optional[int]:
        if not self.chain_nl:
            return None
        return max(self.chain_nl, key=lambda cid: self.chain_nl[cid])

    def get_nl(self, chain_id: int) -> float:
        return self.chain_nl.get(chain_id, 0.0)

    def update_oe_factor(self, oe_factor: float) -> None:
        self.oe_factor = max(0.0, min(1.0, oe_factor))

    def dynamic_routing_threshold(self) -> float:
        """
        Θ(t): adjusts dynamically based on recent coherence history.
        During high-coherence periods, threshold rises.
        During fragmentation, threshold lowers to maintain routing viability.
        """
        if len(self.coherence_history) < 10:
            return 0.40  # default
        recent = self.coherence_history[-50:]
        mean_c = sum(recent) / len(recent)
        std_c  = math.sqrt(sum((c - mean_c) ** 2 for c in recent) / len(recent))
        return max(0.30, min(0.70, mean_c - std_c))


if __name__ == "__main__":
    import json

    ocean = LiquidityOcean(oe_factor=0.05)

    # §6.1 form-equivalent demo (spec formula, synthetic example values)
    forms = [
        {"form": "USDC",    "value": 250_000_000.0, "shift_cost": 0.0002, "time_to_convert": 5.0,   "beo_health": 0.95},
        {"form": "aUSDC",   "value": 120_000_000.0, "shift_cost": 0.0009, "time_to_convert": 900.0, "beo_health": 0.80},
        {"form": "cUSDC",   "value":  40_000_000.0, "shift_cost": 0.0006, "time_to_convert": 120.0, "beo_health": 0.85},
    ]
    ocean6 = liquidity_ocean_score("USDC", forms)
    print("§6.1 LIQUIDITY_OCEAN_SCORE (USDC, 3 equivalent forms):")
    print(json.dumps({k: v for k, v in ocean6.items() if k != "signal"}, indent=2, default=str))
    print()

    # Simulate updates for a few chains
    for chain_id, scale in [(42161, 1.0), (8453, 0.8), (10, 0.75), (1, 1.2)]:
        ocean.update_chain(
            chain_id,
            pool_depths   = [d * scale for d in [10_000_000, 5_000_000, 2_000_000]],
            pool_corrs    = [0.2, 0.4, 0.15],
            depth_history = [d * scale for d in [9_500_000, 10_200_000, 10_000_000]],
            price_history = [2000.0, 2020.0, 1990.0, 2010.0],
        )

    print(json.dumps(ocean.get_ocean_signal(), indent=2))
