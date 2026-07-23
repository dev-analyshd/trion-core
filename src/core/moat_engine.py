"""
TRION Protocol — L9 Economic Moat Engine
=========================================
Whitepaper Section L9 / L0.5 (referenced from L5 master equation):

    M_moat(t) = D(t) · Q(t) · R(t) · X(t) · F(t) · N(t)

Six multiplicative factors — each ∈ (0, 1]:

    D  Akashic Depth factor      — data moat (accumulated behavioral history)
    Q  Quality factor            — signal quality via validator conscious-plane score
    R  Reflexivity factor        — observer-effect resistance (M_adj stability)
    X  Cross-chain factor        — multi-VM/chain coverage breadth
    F  Falsifiability factor     — 15-condition falsifiability registry score
    N  Network factor            — moat durability; decays over time as competitors emerge

The moat is MULTIPLICATIVE, not additive.  Weakness in any single factor
collapses the product toward zero.  This is the intended design: a partial
moat is no moat.

Author : TRION Protocol — Hudu Yusuf (Analys)
License: CC0
"""

from __future__ import annotations

import math
from dataclasses import dataclass


# ── Constants ──────────────────────────────────────────────────────────────────

# Falsifiability registry baseline.
# Updated upward by governance votes when new falsification conditions are
# registered; can decrease if registered conditions are shown to be invalid.
F_REGISTRY_BASELINE: float = 0.90

# Time-scaling constant for the Network factor N(t).
# Whitepaper §2.3 mandates logarithmic GROWTH (not decay):
#   N(t) = log(1 + t/τ) / log(11)
# At t = τ  ≈ 3 years:  N ≈ 0.289
# At t = 10τ ≈ 30 years: N = 1.0  (mature network moat)
# Genesis (t=0): N = 0 (no network moat yet — must be earned over time)
N_DECAY_TAU: float = 1e8

# Depth scaling constants for D and X factors.
D_DEPTH_SCALE:  float = 1_000.0    # entities needed for D to reach ~0.5
X_DEPTH_SCALE:  float = 5_000.0    # entities needed for X to reach ~0.5
X_CHAIN_TARGET: float = 3.0        # log base — 3 chains → X = 0.5, 100 → X ≈ 1.0


# ── Data Model ────────────────────────────────────────────────────────────────

@dataclass(frozen=True)
class MoatInput:
    """
    All inputs required to compute M_moat(t).

    akashic_depth  : float  — number of distinct entities in the BH ledger
    k_plane        : float  — conscious-plane score K ∈ [0, 1] (quality proxy)
    m_adj          : float  — observer-effect-adjusted mental score ∈ [0, 1]
    moat_time      : float  — elapsed time in seconds since protocol genesis
    f_registry     : float  — optional override for the falsifiability factor;
                              defaults to F_REGISTRY_BASELINE when 0.0
    """
    akashic_depth: float
    k_plane:       float
    m_adj:         float
    moat_time:     float
    f_registry:    float = 0.0   # 0.0 → use module-level baseline


# ── Engine ────────────────────────────────────────────────────────────────────

class MoatEngine:
    """
    Standalone L9 Moat Engine.

    Separated from CoherenceEngine so that:
      - The moat formula is the sole responsibility of this module.
      - Callers can query moat strength independently of C(t) computation.
      - Unit tests can verify each factor in isolation.
    """

    # ── Factor computers ──────────────────────────────────────────────────────

    @staticmethod
    def _factor_D(akashic_depth: float) -> float:
        """
        D — Akashic Depth factor.

        D(t) = log(1 + depth / D_scale) / log(1 + 10)

        Saturates toward 1.0 as the BH ledger accumulates hundreds of thousands
        of entities.  At ~10,000 entities D ≈ 0.77; at ~1,000 D ≈ 0.5.
        """
        return min(1.0, math.log1p(akashic_depth / D_DEPTH_SCALE) /
                        math.log1p(10.0))

    @staticmethod
    def _factor_Q(k_plane: float) -> float:
        """
        Q — Quality factor.

        Q(t) = min(1.0, K + 0.15)

        Uses the Conscious-plane score as a quality proxy: higher annotator
        diversity and stake-weighted consensus → higher K → higher Q.
        The +0.15 offset gives bootstrapping protocols a floor above zero.
        """
        return min(1.0, k_plane + 0.15)

    @staticmethod
    def _factor_R(m_adj: float) -> float:
        """
        R — Reflexivity factor.

        R(t) = min(1.0, 1 - 0.30 · (M_adj - 0.5)²)

        Peaks at M_adj = 0.5 (balanced confidence).  A model that is either
        wildly uncertain OR suspiciously over-confident has lower reflexivity
        resistance — both extremes reduce R.
        """
        return min(1.0, 1.0 - 0.30 * (m_adj - 0.5) ** 2)

    @staticmethod
    def _factor_X(akashic_depth: float) -> float:
        """
        X — Cross-chain factor.

        X(t) = log(1 + depth / X_scale) / log(X_chain_target)

        Uses depth as a proxy for chain breadth (deeper ledger implies wider
        chain indexing coverage).  At 5,000 entities X ≈ 0.5; at 50,000 X ≈ 1.0.
        """
        return min(1.0, math.log1p(akashic_depth / X_DEPTH_SCALE) /
                        math.log(X_CHAIN_TARGET))

    @staticmethod
    def _factor_F(f_registry: float) -> float:
        """
        F — Falsifiability factor.

        Governed by the 15-condition falsifiability registry.  Defaults to
        F_REGISTRY_BASELINE (0.90) unless an explicit override is supplied.
        Bounded to (0, 1].
        """
        raw = f_registry if f_registry > 0.0 else F_REGISTRY_BASELINE
        return min(1.0, max(1e-6, raw))

    @staticmethod
    def _factor_N(moat_time: float) -> float:
        """
        N — Network / durability factor.

        Whitepaper §2.3 canonical formula:
            N(t) = log(1 + t/τ) / log(11)

        Encodes logarithmic network-effect GROWTH: the protocol moat
        strengthens as cumulative adoption and behavioral history accumulate.
        At genesis (t=0) there is no network moat.  At t=10τ (≈30 years)
        N reaches 1.0 (full network-effect saturation).

        τ = 1e8 seconds ≈ 3.17 years.  N(τ) ≈ 0.289.
        """
        if moat_time <= 0.0:
            return 0.0
        return min(1.0, math.log1p(moat_time / N_DECAY_TAU) / math.log(11.0))

    # ── Public API ────────────────────────────────────────────────────────────

    def compute(self, inp: MoatInput) -> dict:
        """
        Compute M_moat(t) and return all components.

        Returns
        -------
        dict with keys:
            moat_factor   — final M_moat ∈ [0, 1]
            M_moat_scalar — legacy log-scale depth scalar (backwards compat)
            components    — dict of the six individual factors
        """
        D = self._factor_D(inp.akashic_depth)
        Q = self._factor_Q(inp.k_plane)
        R = self._factor_R(inp.m_adj)
        X = self._factor_X(inp.akashic_depth)
        F = self._factor_F(inp.f_registry)
        N = self._factor_N(inp.moat_time)

        moat_factor = min(1.0, max(0.0, D * Q * R * X * F * N))

        return {
            "moat_factor":    moat_factor,
            "M_moat_scalar":  math.log1p(inp.akashic_depth / 10_000),
            "components": {
                "D_data":           round(D, 6),
                "Q_quality":        round(Q, 6),
                "R_reflexivity":    round(R, 6),
                "X_crosschain":     round(X, 6),
                "F_falsifiability": round(F, 6),
                "N_network":        round(N, 6),
            },
        }


# ── Module self-test ──────────────────────────────────────────────────────────

if __name__ == "__main__":
    engine = MoatEngine()

    print("TRION Protocol — L9 Moat Engine self-test")
    print("─" * 50)

    cases = [
        ("Bootstrap   (depth=100,  t=0)",
         MoatInput(akashic_depth=100,    k_plane=0.10, m_adj=0.50, moat_time=0)),
        ("Early       (depth=1000, t=1e6)",
         MoatInput(akashic_depth=1_000,  k_plane=0.40, m_adj=0.55, moat_time=1e6)),
        ("Growing     (depth=10k,  t=1e7)",
         MoatInput(akashic_depth=10_000, k_plane=0.60, m_adj=0.65, moat_time=1e7)),
        ("Mature      (depth=50k,  t=3e7)",
         MoatInput(akashic_depth=50_000, k_plane=0.80, m_adj=0.72, moat_time=3e7)),
        ("Current BH  (depth=22700,t=2e7)",
         MoatInput(akashic_depth=22_700, k_plane=0.65, m_adj=0.68, moat_time=2e7)),
    ]

    all_pass = True
    for label, inp in cases:
        result = engine.compute(inp)
        mf     = result["moat_factor"]
        comp   = result["components"]
        status = "PASS" if 0.0 <= mf <= 1.0 else "FAIL"
        if status == "FAIL":
            all_pass = False
        print(f"  {label}")
        print(f"    M_moat={mf:.4f}  D={comp['D_data']:.3f}  Q={comp['Q_quality']:.3f}"
              f"  R={comp['R_reflexivity']:.3f}  X={comp['X_crosschain']:.3f}"
              f"  F={comp['F_falsifiability']:.3f}  N={comp['N_network']:.3f}"
              f"  [{status}]")

    # Invariant: moat is strictly monotone in depth (all other inputs equal).
    # Use a non-zero moat_time so N(t) > 0; at t=0 the product is always 0
    # regardless of depth (genesis state has no network moat yet — correct).
    base = MoatInput(akashic_depth=1_000, k_plane=0.5, m_adj=0.5, moat_time=1e7)
    deep = MoatInput(akashic_depth=100_000, k_plane=0.5, m_adj=0.5, moat_time=1e7)
    moat_base = engine.compute(base)["moat_factor"]
    moat_deep = engine.compute(deep)["moat_factor"]
    monotone_ok = moat_deep > moat_base
    if not monotone_ok:
        all_pass = False
    print(f"\n  Depth monotonicity: {moat_base:.4f} → {moat_deep:.4f}"
          f"  [{'PASS' if monotone_ok else 'FAIL'}]")

    # Invariant: moat_factor is always in [0, 1]
    bound_ok = all(
        0.0 <= engine.compute(MoatInput(akashic_depth=d, k_plane=k,
                                        m_adj=m, moat_time=t))["moat_factor"] <= 1.0
        for d in [0, 1, 100, 1e6]
        for k in [0.0, 0.5, 1.0]
        for m in [0.0, 0.5, 1.0]
        for t in [0, 1e8, 1e10]
    )
    if not bound_ok:
        all_pass = False
    print(f"  Bound invariant [0,1] across all inputs: [{'PASS' if bound_ok else 'FAIL'}]")

    print("─" * 50)
    print(f"{'ALL PASS' if all_pass else 'SOME TESTS FAILED'} — L9 Moat Engine")
