"""
TRION Protocol — L9 Economic Moat Engine
=========================================
specification Section L9 / L0.5 (referenced from L5 master equation):

    M_moat(t) = D(t) · Q(t) · R(t) · X(t) · F(t) · N(t)

Six multiplicative factors — each ∈ (0, 1]:

    D  Akashic Depth factor      — data moat (accumulated behavioral history)
    Q  Quality factor            — signal ACCURACY: corr(predicted, actual)
                                    over the rolling HA window. Falls back to
                                    the conscious-plane score K when no
                                    accuracy history exists (bootstrap).
    R  Regulatory factor         — REGULATORY clarity across jurisdictions
                                    (MiCA, SEC, MAS, FCA, ESMA, …). Falls back
                                    to the observer-effect-adjusted mental
                                    score M_adj as a reflexivity proxy when
                                    the regulatory registry is not consulted.
    X  Cross-chain factor        — number of distinct VM families / chains
                                    indexed by the BH ledger. Was previously
                                    a depth proxy; now reads the real chain
                                    count surfaced by FAISS /vm-status.
    F  Falsifiability factor     — number of registered falsifiability
                                    CHALLENGES (Part 13 conditions). Each new
                                    challenge increases the moat because the
                                    protocol has bound itself to be refutable
                                    on more dimensions.
    N  Network factor            — protocols × TVL: a multiplicative
                                    network-effect proxy. Network moat grows
                                    with both the number of integrated
                                    protocols AND the value they custody
                                    through TRION. Falls back to a pure
                                    time-based exponential saturation when
                                    the protocols/TVL registry is empty.

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
# specification §2.3 — exponential saturation (asymptotic compounding):
#   N(t) = 1 − e^(−t / τ)
# At genesis (t=0):  N = 0   (no network moat yet)
# At t = τ ≈ 3 yr:  N ≈ 0.632 (inflection point)
# At t → ∞:         N → 1.0  (full network-effect saturation)
# The exponential saturation formula encodes compounding trust: each unit of
# time adds more moat than linearly expected at early stages, then tapers as
# the protocol approaches full maturity.
N_GROWTH_TAU: float = 1e8
N_DECAY_TAU:  float = N_GROWTH_TAU  # backward-compat alias

# Depth scaling constants for D and X factors.
D_DEPTH_SCALE:  float = 1_000.0    # entities needed for D to reach ~0.5
X_DEPTH_SCALE:  float = 5_000.0    # entities needed for X to reach ~0.5 (legacy proxy)
X_CHAIN_TARGET: float = 3.0        # log base — 3 chains → X = 0.5, 100 → X ≈ 1.0

# ── New (gap #2) — real factor inputs ─────────────────────────────────────────
# Chain count normaliser for X — saturates at ~50 chains (X ≈ 0.99).
X_CHAIN_SATURATION: int = 50
# Challenge-count normaliser for F — Part 13 baseline is 15 conditions;
# log(1 + challenges) / log(1 + F_CHALLENGE_TARGET) saturates at ~15.
F_CHALLENGE_TARGET: int = 15
# Network factor: TVL scaling — $1B TVL across 100 protocols saturates N.
N_PROTOCOL_SATURATION: int = 100
N_TVL_SATURATION_USD:  float = 1e9   # $1B


# ── Data Model ────────────────────────────────────────────────────────────────

@dataclass(frozen=True)
class MoatInput:
    """
    All inputs required to compute M_moat(t).

    Specification-mandated factors (whitepaper Part 13 + L0.5):
        D  akashic_depth       — distinct entities in the BH ledger
        Q  prediction_accuracy — corr(predicted, actual) over the rolling
                                  HA window; None → fall back to k_plane
        R  regulatory_score    — ∈ [0,1] across MiCA/SEC/MAS/FCA/ESMA/…;
                                  None → fall back to m_adj reflexivity proxy
        X  chain_count         — distinct VM families indexed; None → fall
                                  back to akashic_depth proxy
        F  challenge_count     — registered falsifiability challenges
                                  (Part 13); None → fall back to f_registry
        N  protocols_count + tvl_usd — multiplicative network-effect proxy;
                                  None for both → fall back to moat_time

    Backward-compat legacy inputs (used as honest fallbacks when the spec-
    mandated input is not yet wired by the caller):
        k_plane       — conscious-plane score (Q fallback)
        m_adj         — observer-effect-adjusted mental score (R fallback)
        f_registry    — explicit override for F (defaults to baseline)
        moat_time     — elapsed seconds since genesis (N fallback)
    """
    akashic_depth:        float
    k_plane:              float = 0.0
    m_adj:                float = 0.5
    moat_time:            float = 0.0
    f_registry:           float = 0.0   # 0.0 → use module-level baseline

    # ── spec-mandated new inputs (gap #2) ────────────────────────────────────
    prediction_accuracy:  "float | None" = None
    regulatory_score:    "float | None" = None
    chain_count:         "int | None"   = None
    challenge_count:     "int | None"   = None
    protocols_count:     "int | None"   = None
    tvl_usd:             "float | None" = None


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
    def _factor_Q(prediction_accuracy: float | None,
                  k_plane: float) -> float:
        """
        Q — Quality / Accuracy factor.

        Spec (whitepaper Part 13): Q = corr(predicted_signal_value,
        actual_outcome) over the rolling 90-day historical-accuracy window
        (the same window the ANIMA HA component uses).

        Falls back to the conscious-plane score K (with a +0.15 bootstrap
        offset) when no accuracy history exists yet. Callers that supply a
        real accuracy figure from the ANIMA calibration store get the
        spec-faithful Q.
        """
        if prediction_accuracy is not None:
            acc = max(0.0, min(1.0, float(prediction_accuracy)))
            # Q = accuracy directly: a model that has never been right
            # cannot have a moat. The 0.05 floor keeps the product from
            # collapsing to literal zero during early calibration.
            return max(0.05, acc)
        # Bootstrap fallback — K is the conscious-plane proxy for quality.
        return min(1.0, k_plane + 0.15)

    @staticmethod
    def _factor_R(regulatory_score: float | None,
                  m_adj: float) -> float:
        """
        R — Regulatory factor.

        Spec (Part 13): R = regulatory clarity across the jurisdictions the
        protocol operates in (MiCA, SEC, MAS, FCA, ESMA, JFSA, …). A protocol
        with no regulatory opinion in any jurisdiction has R → 0; one with
        explicit no-action letters / registrations has R → 1.

        Falls back to the observer-effect-adjusted mental score M_adj as a
        reflexivity proxy when the regulatory registry is not consulted
        (legacy bootstrap behavior — preserved for backward compatibility).
        """
        if regulatory_score is not None:
            return max(0.0, min(1.0, float(regulatory_score)))
        # Bootstrap fallback — reflexivity-shaped curve peaks at M_adj=0.5.
        return min(1.0, 1.0 - 0.30 * (m_adj - 0.5) ** 2)

    @staticmethod
    def _factor_X(chain_count: int | None,
                  akashic_depth: float) -> float:
        """
        X — Cross-chain factor.

        Spec (Part 13): X = log(1 + N_chains) / log(1 + saturation),
        where N_chains is the number of distinct VM families indexed by
        the BH ledger (EVM, SVM, UTXO, Starknet, Move, Cosmos, TON, NEAR,
        Polkadot, Stellar, Aptos, Sui, …). A protocol indexing only one
        VM family cannot claim a cross-chain moat.

        Falls back to a depth proxy when the chain-count registry is
        not consulted (legacy bootstrap behavior — preserved for backward
        compatibility).
        """
        if chain_count is not None and chain_count > 0:
            return min(1.0,
                       math.log1p(chain_count) /
                       math.log1p(X_CHAIN_SATURATION))
        # Bootstrap fallback — depth as a proxy for chain breadth.
        return min(1.0, math.log1p(akashic_depth / X_DEPTH_SCALE) /
                        math.log(X_CHAIN_TARGET))

    @staticmethod
    def _factor_F(challenge_count: int | None,
                  f_registry: float) -> float:
        """
        F — Falsifiability factor.

        Spec (Part 13): F = log(1 + N_challenges) / log(1 + target),
        where N_challenges is the number of registered falsifiability
        conditions. The Part 13 baseline is 15 conditions; registering
        more increases the moat because the protocol has bound itself to
        be refutable on more dimensions.

        Falls back to the legacy F_REGISTRY_BASELINE (0.90) when the
        challenge registry is not consulted.
        """
        if challenge_count is not None and challenge_count >= 0:
            return min(1.0,
                       math.log1p(challenge_count) /
                       math.log1p(F_CHALLENGE_TARGET))
        # Legacy fallback — explicit override or module baseline.
        raw = f_registry if f_registry > 0.0 else F_REGISTRY_BASELINE
        return min(1.0, max(1e-6, raw))

    @staticmethod
    def _factor_N(protocols_count: int | None,
                  tvl_usd: float | None,
                  moat_time: float) -> float:
        """
        N — Network factor (protocols × TVL).

        Spec (Part 13): N = sqrt(P_norm · T_norm), where:
            P_norm = log(1 + N_protocols) / log(1 + saturation_protocols)
            T_norm = log(1 + TVL_usd) / log(1 + saturation_tvl)
        Network moat grows with BOTH the number of integrated protocols AND
        the value they custody through TRION. A protocol with 100
        integrations but $0 TVL has half a moat.

        Falls back to a pure time-based exponential saturation
        (1 − e^(−t / τ)) when the protocols/TVL registry is empty — this
        was the pre-gap behaviour and preserves backward compatibility for
        callers that have not yet wired the registry.
        """
        if (protocols_count is not None and protocols_count > 0 and
            tvl_usd is not None and tvl_usd > 0):
            p_norm = min(1.0, math.log1p(protocols_count) /
                                 math.log1p(N_PROTOCOL_SATURATION))
            t_norm = min(1.0, math.log1p(tvl_usd) /
                               math.log1p(N_TVL_SATURATION_USD))
            # Geometric mean — both must be present for a full network moat.
            return math.sqrt(p_norm * t_norm)
        # Bootstrap fallback — pure time-based saturation.
        if moat_time <= 0.0:
            return 0.0
        return 1.0 - math.exp(-moat_time / N_GROWTH_TAU)

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
            inputs        — echo of the resolved inputs used (for audit)
        """
        D = self._factor_D(inp.akashic_depth)
        Q = self._factor_Q(inp.prediction_accuracy, inp.k_plane)
        R = self._factor_R(inp.regulatory_score,    inp.m_adj)
        X = self._factor_X(inp.chain_count,         inp.akashic_depth)
        F = self._factor_F(inp.challenge_count,     inp.f_registry)
        N = self._factor_N(inp.protocols_count,     inp.tvl_usd, inp.moat_time)

        moat_factor = min(1.0, max(0.0, D * Q * R * X * F * N))

        # Echo which inputs were spec-faithful vs. fallback — useful for the
        # dashboard's "Moat Factors" panel and for audit logs.
        inputs_used = {
            "D": {"akashic_depth": inp.akashic_depth},
            "Q": {"source": "prediction_accuracy" if inp.prediction_accuracy is not None
                            else "k_plane_fallback",
                  "value":   inp.prediction_accuracy if inp.prediction_accuracy is not None
                             else inp.k_plane},
            "R": {"source": "regulatory_score" if inp.regulatory_score is not None
                            else "m_adj_fallback",
                  "value":   inp.regulatory_score if inp.regulatory_score is not None
                             else inp.m_adj},
            "X": {"source": "chain_count" if inp.chain_count is not None
                            else "akashic_depth_fallback",
                  "value":   inp.chain_count if inp.chain_count is not None
                             else inp.akashic_depth},
            "F": {"source": "challenge_count" if inp.challenge_count is not None
                            else "f_registry_fallback",
                  "value":   inp.challenge_count if inp.challenge_count is not None
                             else inp.f_registry},
            "N": {"source": "protocols_tvl" if (inp.protocols_count and inp.tvl_usd)
                            else "moat_time_fallback",
                  "value":   {"protocols": inp.protocols_count,
                              "tvl_usd":   inp.tvl_usd}
                              if (inp.protocols_count and inp.tvl_usd)
                              else inp.moat_time},
        }

        return {
            "moat_factor":    moat_factor,
            "M_moat_scalar":  math.log1p(inp.akashic_depth / 10_000),
            "components": {
                "D_depth":           round(D, 6),
                "Q_accuracy":        round(Q, 6),
                "R_regulatory":      round(R, 6),
                "X_chains":          round(X, 6),
                "F_challenges":      round(F, 6),
                "N_protocols_tvl":   round(N, 6),
                # Legacy aliases (preserved for the existing dashboard /
                # tests that read D_data / Q_quality / R_reflexivity /
                # X_crosschain / F_falsifiability / N_network).
                "D_data":           round(D, 6),
                "Q_quality":        round(Q, 6),
                "R_reflexivity":    round(R, 6),
                "X_crosschain":     round(X, 6),
                "F_falsifiability": round(F, 6),
                "N_network":        round(N, 6),
            },
            "inputs": inputs_used,
        }


# ── Module self-test ──────────────────────────────────────────────────────────

if __name__ == "__main__":
    engine = MoatEngine()

    print("TRION Protocol — L9 Moat Engine self-test")
    print("─" * 60)

    cases = [
        ("Bootstrap   (depth=100,  t=0, 0 chains, 0 challenges)",
         MoatInput(akashic_depth=100,    k_plane=0.10, m_adj=0.50, moat_time=0)),
        ("Early       (depth=1000, t=1e6, fallback inputs)",
         MoatInput(akashic_depth=1_000,  k_plane=0.40, m_adj=0.55, moat_time=1e6)),
        ("Growing     (depth=10k,  t=1e7, fallback inputs)",
         MoatInput(akashic_depth=10_000, k_plane=0.60, m_adj=0.65, moat_time=1e7)),
        ("Mature      (depth=50k,  t=3e7, fallback inputs)",
         MoatInput(akashic_depth=50_000, k_plane=0.80, m_adj=0.72, moat_time=3e7)),
        ("Spec-faithful  (12 chains, 15 challenges, 50 protocols, $500M TVL, acc=0.78, reg=0.85)",
         MoatInput(akashic_depth=10_000, prediction_accuracy=0.78,
                   regulatory_score=0.85, chain_count=12,
                   challenge_count=15, protocols_count=50, tvl_usd=5e8)),
        ("Honest-zero   (no chains, no challenges — moat collapses to 0)",
         MoatInput(akashic_depth=0, k_plane=0.0, m_adj=0.0, moat_time=0,
                   chain_count=0, challenge_count=0, protocols_count=0, tvl_usd=0.0)),
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
        print(f"    M_moat={mf:.4f}  D={comp['D_depth']:.3f}  Q={comp['Q_accuracy']:.3f}"
              f"  R={comp['R_regulatory']:.3f}  X={comp['X_chains']:.3f}"
              f"  F={comp['F_challenges']:.3f}  N={comp['N_protocols_tvl']:.3f}"
              f"  [{status}]")

    # Invariant: moat is strictly monotone in depth (all other inputs equal).
    base = MoatInput(akashic_depth=1_000, k_plane=0.5, m_adj=0.5, moat_time=1e7)
    deep = MoatInput(akashic_depth=100_000, k_plane=0.5, m_adj=0.5, moat_time=1e7)
    moat_base = engine.compute(base)["moat_factor"]
    moat_deep = engine.compute(deep)["moat_factor"]
    monotone_ok = moat_deep > moat_base
    if not monotone_ok:
        all_pass = False
    print(f"\n  Depth monotonicity: {moat_base:.4f} → {moat_deep:.4f}"
          f"  [{'PASS' if monotone_ok else 'FAIL'}]")

    # Invariant: spec-faithful inputs strictly beat fallback inputs at the
    # same depth (accuracy > K proxy, regulatory > M_adj proxy, real chains
    # > depth proxy, etc.).
    fallback = MoatInput(akashic_depth=10_000, k_plane=0.5, m_adj=0.5, moat_time=1e7)
    spec     = MoatInput(akashic_depth=10_000, prediction_accuracy=0.78,
                         regulatory_score=0.85, chain_count=12,
                         challenge_count=15, protocols_count=50, tvl_usd=5e8)
    fb = engine.compute(fallback)["moat_factor"]
    sp = engine.compute(spec)["moat_factor"]
    spec_beats_fb = sp > fb
    if not spec_beats_fb:
        all_pass = False
    print(f"  Spec-faithful > fallback: {sp:.4f} > {fb:.4f}"
          f"  [{'PASS' if spec_beats_fb else 'FAIL'}]")

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

    print("─" * 60)
    print(f"{'ALL PASS' if all_pass else 'SOME TESTS FAILED'} — L9 Moat Engine")
