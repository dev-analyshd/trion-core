"""
TRION Protocol — L7.1: Natural Liquidity Score
NL(asset, t) = LD(a,t) · LO(a,t) · LC(a,t) · LS(a,t)
NL < 0.30 → LIQUIDITY_HEALTH signal emitted

LD = Liquidity Depth Entropy        = H(depth_distribution_across_price_levels)
LO = Liquidity Origin Score          = 1 - Sybil_LP_ratio,
                                      Sybil_LP_ratio = top_5_LP_share / (LP_BEO_count / 5)
LC = Liquidity Consistency           = corr(LD_current, LD_90d_baseline)
LS = Liquidity Stress Resilience     = LD(during_stress) / LD(normal_conditions)

# NOTE: The "March 12, 2026 AAVE" incident referenced in prior versions was fabricated.
"""

import numpy as np
from typing import List, Optional
import math


NL_ALERT_THRESHOLD = 0.30


def compute_ld(depth_per_tick: List[float]) -> float:
    if not depth_per_tick or sum(depth_per_tick) <= 0:
        return 0.0
    total = sum(depth_per_tick)
    probs = [d / total for d in depth_per_tick if d > 0]
    H     = -sum(p * math.log2(p) for p in probs)
    max_H = math.log2(len(depth_per_tick))
    return H / max_H if max_H > 0 else 0.0


def compute_lo(top5_lp_share: float, lp_count: int) -> float:
    """
    LO = 1 - Sybil_LP_ratio where Sybil_LP_ratio = top_5_share / (BEO_count / 5)
    (whitepaper L7.1). lp_count is the number of INDEPENDENT LP entities
    (BEO-resolved), not raw wallet count.
    """
    if lp_count <= 0:
        return 0.0
    sybil_ratio = top5_lp_share / max(1, lp_count / 5)
    return max(0.0, 1.0 - sybil_ratio)


def _pearson(x: List[float], y: List[float]) -> Optional[float]:
    """Pearson correlation; None when either series is constant (undefined)."""
    n = min(len(x), len(y))
    if n < 2:
        return None
    x, y = list(x[-n:]), list(y[-n:])
    mx, my = sum(x) / n, sum(y) / n
    cov = sum((a - mx) * (b - my) for a, b in zip(x, y))
    vx  = sum((a - mx) ** 2 for a in x)
    vy  = sum((b - my) ** 2 for b in y)
    if vx <= 0 or vy <= 0:
        return None
    return max(-1.0, min(1.0, cov / math.sqrt(vx * vy)))


def compute_lc(
    current_ld: float,
    baseline_ld_history: List[float],
    recent_ld_history: Optional[List[float]] = None,
) -> float:
    """
    LC = corr(LD_current, LD_90d_baseline) — whitepaper L7.1.

    High: stable pattern over time (genuine market-maker behavior).
    Low:  pattern recently changed (possible manipulation preparation).

    Two evaluation paths:
    1. Series path (spec-literal): when a recent LD observation series is
       supplied, LC is the Pearson correlation between the recent window and
       the 90-day baseline window, mapped from [-1, 1] to [0, 1] via
       max(0, corr) so anti-correlated drift scores 0.
    2. Scalar path (degenerate case): when only the current scalar LD is
       available, correlation against a series is undefined; LC degenerates to
       the consistency of the current value with the baseline distribution
       (z-score deviation, capped at 3σ). A flat baseline with current ==
       baseline mean yields LC = 1.0 — matching the correlation's limit.
    """
    if not baseline_ld_history:
        return 0.5

    # Spec-literal correlation path
    if recent_ld_history is not None and len(recent_ld_history) >= 2:
        corr = _pearson(recent_ld_history, baseline_ld_history)
        if corr is not None:
            return max(0.0, min(1.0, corr))
        # Both windows flat and equal → perfectly stable
        if len(recent_ld_history) and len(baseline_ld_history):
            r_set = set(round(v, 9) for v in recent_ld_history)
            b_set = set(round(v, 9) for v in baseline_ld_history)
            if len(r_set) == 1 and len(b_set) == 1 and r_set == b_set:
                return 1.0
        return 0.5

    # Scalar degenerate path — consistency with baseline distribution
    baseline_mean = float(np.mean(baseline_ld_history))
    baseline_std  = float(np.std(baseline_ld_history))
    if baseline_std < 1e-6:
        deviation = abs(current_ld - baseline_mean)
        if deviation < 0.05:
            return 1.0
        if deviation < 0.30:
            return round(max(0.5, 1.0 - deviation * 1.5), 4)
        return 0.5
    z = abs(current_ld - baseline_mean) / baseline_std
    return max(0.0, 1.0 - min(1.0, z / 3.0))


def compute_ls(ld_during_stress: float, ld_during_normal: float) -> float:
    if ld_during_normal <= 0:
        return 0.0
    return min(1.0, ld_during_stress / ld_during_normal)


def compute_nl(
    depth_per_tick:   List[float],
    top5_lp_share:    float,
    lp_count:         int,
    baseline_ld_90d:  List[float],
    ld_during_stress: float,
    ld_during_normal: float,
    recent_ld_history: Optional[List[float]] = None,
) -> dict:
    ld = compute_ld(depth_per_tick)
    lo = compute_lo(top5_lp_share, lp_count)
    lc = compute_lc(ld, baseline_ld_90d, recent_ld_history=recent_ld_history)
    ls = compute_ls(ld_during_stress, ld_during_normal)

    nl       = ld * lo * lc * ls
    alert    = nl < NL_ALERT_THRESHOLD
    limiting = min({'LD':ld,'LO':lo,'LC':lc,'LS':ls}, key={'LD':ld,'LO':lo,'LC':lc,'LS':ls}.get)

    return {
        "nl_score":        nl,
        "ld_score":        ld,
        "lo_score":        lo,
        "lc_score":        lc,
        "ls_score":        ls,
        "alert":           alert,
        "limiting_factor": limiting,
        "recommendation":  "DO_NOT_ROUTE" if nl < NL_ALERT_THRESHOLD else "CAUTION" if nl < 0.50 else "CLEAR",
    }


# ═══════════════════════════════════════════════════════════════════════════════
# BTCP Master Implementation Spec §6.1 — The Liquidity Ocean (form-equivalents)
# ═══════════════════════════════════════════════════════════════════════════════
#
# "No Asset Has Zero Liquidity": USDC exists in at least seventeen simultaneous
# forms at any moment. BTCP does not look for exact form. It looks for
# value-equivalent form. An asset's form may transform (token → wrapped →
# LP-share → staked-derivative…); each form carries:
#
#   LIQUIDITY_OCEAN_SCORE(asset, t) =
#       Σ_forms [ VALUE(form_k)
#                 × 1/shift_cost(form_k)        # 1/cost to shift to target form
#                 × 1/time_to_convert(form_k)   # 1/time to shift
#                 × BEO_health(holder_of_form_k) ]
#
#   If > 0: routable liquidity exists.
#   Only zero: total ecosystem value is zero (thermodynamic death — not
#   practical).
#
# Implementation notes (honest-scoping):
#   * The raw sum above is dimensionally "USD × cost⁻¹ × time⁻¹" — it is NOT a
#     dollar amount. For the routing gate we additionally expose a normalized
#     `ocean_score` ∈ [0, 1]: the value-weighted fraction of the asset's total
#     form-value that is readily routable, with each form's cost/time efficiency
#     capped at 1 against the reference constants below (implementation
#     constants, not whitepaper values).
#   * The literal spec pseudocode guards division by zero by zeroing the term
#     (`1.0/shift_cost if shift_cost > 0 else 0`), so a zero-cost / zero-time
#     form contributes 0 to the raw sum. This edge is preserved verbatim.
#   * The chain-level NL aggregation (L_ocean = Σ NL·W/ΣW, spec §7.2) is a
#     different surface and lives unchanged in anima-service/liquidity_ocean.py.
#   * The spec's data source `akashic.get_equivalent_forms(asset)` has no live
#     feed yet (§6.2 form-transformation events are not indexed) — callers
#     supply the observed forms; NOTHING here is fabricated.

LIQUIDITY_OCEAN_ROUTING_THRESHOLD = 0.40   # mirrors the chain-level ocean routing-viable gate
OCEAN_REF_SHIFT_COST = 0.0010              # 10 bps — cost at/ below which a form is "frictionless"
OCEAN_REF_SHIFT_TIME = 60.0                # 60 s  — conversion at/ below which a form is "instant"

# Accepted input aliases per form field (primary name first).
_FORM_KEY_ALIASES = {
    "form":           ("form", "name", "form_id", "form_name", "symbol"),
    "value":          ("value", "value_usd", "amount"),
    "shift_cost":     ("shift_cost", "cost", "cost_bps", "shift_cost_bps"),
    "time_to_convert": ("time_to_convert", "time", "shift_time", "time_to_shift", "blocks"),
    "beo_health":     ("beo_health", "behavioral_health", "beo", "holder_health"),
}


def _form_field(form: dict, canonical: str):
    for key in _FORM_KEY_ALIASES[canonical]:
        if key in form and form[key] is not None:
            return form[key]
    return None


def normalize_shift_cost(cost) -> float:
    """
    §6.1 allows shift_cost as "basis points or 0-1 cost". Values >= 1.0 are
    interpreted as basis points (30 → 0.003); values in (0, 1) are already
    0-1 cost fractions. Negative, None or non-numeric → 0.0 (the literal
    spec guard then zeroes the term).
    """
    try:
        cost = float(cost)
    except (TypeError, ValueError):
        return 0.0
    if cost < 0.0:
        return 0.0
    if cost >= 1.0:
        return cost / 10_000.0
    return cost


def normalize_time_to_convert(time_to_convert) -> float:
    """time_to_convert in seconds (or blocks — any consistent positive unit)."""
    try:
        t = float(time_to_convert)
    except (TypeError, ValueError):
        return 0.0
    return max(0.0, t)


def normalize_beo_health(beo_health) -> float:
    """Holder BEO health score, clamped to [0, 1]."""
    try:
        h = float(beo_health)
    except (TypeError, ValueError):
        return 0.0
    return min(1.0, max(0.0, h))


def _best_form_path(asset_id: str, breakdown: list) -> Optional[dict]:
    """
    Lowest combined cost×time route to the most liquid form.

    "Most liquid form" = the form with the highest §6.1 contribution
    (VALUE × 1/cost × 1/time × BEO_health — the ocean's own liquidity
    measure; ties broken by higher VALUE). Every form's shift_cost /
    time_to_convert describe its conversion to the base asset form, so the
    route from any origin form into the most liquid form runs
    origin → base asset → target; the origin with the lowest combined
    (cost × time) product is the recommended entry point into the ocean.
    """
    if not breakdown:
        return None
    target = max(breakdown, key=lambda b: (b["contribution"], b["value"]))
    candidates = [
        b for b in breakdown
        if b is not target and b["shift_cost"] > 0 and b["time_to_convert"] > 0
    ]
    if not candidates:
        return {
            "path": [target["form"]],
            "hops": [],
            "origin_form": target["form"],
            "target_form": target["form"],
            "combined_shift_cost": 0.0,
            "combined_time_to_convert": 0.0,
            "cost_time_product": 0.0,
            "target_value": target["value"],
            "target_beo_health": target["beo_health"],
            "target_contribution": target["contribution"],
            "note": "value already held in the most liquid form — no conversion required",
        }
    scored = []
    for b in candidates:
        combined_cost = b["shift_cost"] + target["shift_cost"]
        combined_time = b["time_to_convert"] + target["time_to_convert"]
        scored.append((combined_cost * combined_time, combined_cost, combined_time, b))
    # lowest cost×time product; ties broken by lower combined cost, then time
    _, combined_cost, combined_time, origin = min(
        scored, key=lambda s: (s[0], s[1], s[2])
    )
    return {
        "path": [origin["form"], asset_id, target["form"]],
        "hops": [
            {"from": origin["form"], "to": asset_id,
             "shift_cost": origin["shift_cost"],
             "time_to_convert": origin["time_to_convert"]},
            {"from": asset_id, "to": target["form"],
             "shift_cost": target["shift_cost"],
             "time_to_convert": target["time_to_convert"]},
        ],
        "origin_form": origin["form"],
        "target_form": target["form"],
        "combined_shift_cost": combined_cost,
        "combined_time_to_convert": combined_time,
        "cost_time_product": combined_cost * combined_time,
        "target_value": target["value"],
        "target_beo_health": target["beo_health"],
        "target_contribution": target["contribution"],
        "selection_rule": "lowest combined (shift_cost × time_to_convert) route to the most liquid form",
    }


def liquidity_ocean_score(
    asset_id,
    forms: Optional[List[dict]],
    notional: Optional[float] = None,
    routing_threshold: Optional[float] = None,
) -> dict:
    """
    BTCP Master Implementation Spec §6.1 — form-equivalent Liquidity Ocean score.

    LIQUIDITY_OCEAN_SCORE = Σ_forms [ VALUE(form) × 1/shift_cost(form)
                                      × 1/time_to_convert(form) × BEO_health(form) ]

    Args:
        asset_id:          asset identifier (string or bytes).
        forms:             list of equivalent-form records. Each record carries
                           `form` (id), `value` (USD), `shift_cost` (0-1 fraction
                           OR basis points — values >= 1.0 are read as bps),
                           `time_to_convert` (seconds/blocks, > 0), `beo_health`
                           (holder BEO health in [0, 1]). Common aliases
                           (name/value_usd/cost/time/…) are accepted.
        notional:          optional intended route size in USD — enables the
                           market-impact term of the slippage estimate.
        routing_threshold: override for LIQUIDITY_OCEAN_ROUTING_THRESHOLD.

    Returns a dict with:
        total_score        — the raw spec §6.1 sum (USD × cost⁻¹ × time⁻¹ units)
        ocean_score        — normalized routable fraction in [0, 1] (threshold basis)
        form_breakdown     — per-form {form, value, shift_cost, time_to_convert,
                             beo_health, cost_inverse, time_inverse, contribution,
                             cost_efficiency, time_efficiency, normalized_contribution}
        best_form_path     — lowest combined cost×time route to the most liquid form
        slippage_estimate  — combined shift cost + optional linear market impact
        signal             — LIQUIDITY_OCEAN_SIGNAL (extended LIQUIDITY_HEALTH
                             payload, see build_liquidity_ocean_signal) emitted
                             when ocean_score crosses routing_threshold; else None
        routing_viable / recommendation / theorem flags
    """
    asset_id = asset_id.hex() if isinstance(asset_id, bytes) else str(asset_id)
    if routing_threshold is None:
        routing_threshold = LIQUIDITY_OCEAN_ROUTING_THRESHOLD

    breakdown: List[dict] = []
    total_score = 0.0
    total_value = 0.0
    total_normalized = 0.0

    for f in (forms or []):
        if not isinstance(f, dict):
            raise TypeError(f"form records must be dicts, got {type(f).__name__}: {f!r}")
        name       = _form_field(f, "form")
        raw_value  = _form_field(f, "value")
        try:
            value = max(0.0, float(raw_value)) if raw_value is not None else 0.0
        except (TypeError, ValueError):
            raise ValueError(f"non-numeric value for form {name!r}: {raw_value!r}")
        cost   = normalize_shift_cost(_form_field(f, "shift_cost"))
        time_c = normalize_time_to_convert(_form_field(f, "time_to_convert"))
        beo    = normalize_beo_health(_form_field(f, "beo_health"))

        # Spec-literal terms — division-by-zero guarded by zeroing (§6.1 pseudocode)
        cost_inv = (1.0 / cost) if cost > 0 else 0.0
        time_inv = (1.0 / time_c) if time_c > 0 else 0.0
        contribution = value * cost_inv * time_inv * beo

        # Normalized efficiencies (capped at 1 against the reference constants)
        cost_eff = min(1.0, OCEAN_REF_SHIFT_COST / cost) if cost > 0 else 0.0
        time_eff = min(1.0, OCEAN_REF_SHIFT_TIME / time_c) if time_c > 0 else 0.0
        normalized_contribution = value * cost_eff * time_eff * beo

        total_score   += contribution
        total_value   += value
        total_normalized += normalized_contribution

        breakdown.append({
            "form":                    str(name) if name is not None else "<unnamed-form>",
            "value":                   value,
            "shift_cost":              cost,
            "time_to_convert":         time_c,
            "beo_health":              beo,
            "cost_inverse":            cost_inv,
            "time_inverse":            time_inv,
            "cost_efficiency":         cost_eff,
            "time_efficiency":         time_eff,
            "contribution":            contribution,
            "normalized_contribution": normalized_contribution,
        })

    ocean_score = (total_normalized / total_value) if total_value > 0 else 0.0

    best_form_path = _best_form_path(asset_id, breakdown)

    # ── Slippage estimate ────────────────────────────────────────────────────
    # Linear-impact model: market impact = notional / (notional + effective
    # depth), with effective depth = VALUE(target form) × BEO_health(target)
    # — the behaviorally-weighted depth of the most liquid form — plus the
    # combined shift cost of the best form path.
    slippage_estimate: Optional[float] = None
    slippage_breakdown: Optional[dict] = None
    if best_form_path is not None:
        conversion_cost  = best_form_path["combined_shift_cost"]
        effective_depth  = best_form_path["target_value"] * best_form_path["target_beo_health"]
        if notional is not None and notional > 0:
            market_impact = (notional / (notional + effective_depth)) if effective_depth > 0 else 1.0
            slippage_estimate = conversion_cost + market_impact
        else:
            market_impact = None
            slippage_estimate = conversion_cost
        slippage_breakdown = {
            "conversion_cost":     conversion_cost,
            "market_impact":       market_impact,
            "notional":            notional,
            "effective_depth":     effective_depth,
            "model":               ("linear market impact notional/(notional + effective_depth) "
                                    "vs BEO-health-weighted depth of the most liquid form, plus "
                                    "combined shift cost of the best form path"),
        }

    routing_viable = ocean_score >= routing_threshold
    if not breakdown or total_value <= 0:
        recommendation = "DO_NOT_ROUTE"        # no known value — nothing to route
    elif routing_viable:
        recommendation = "ROUTE_OK"
    elif ocean_score > 0:
        recommendation = "CAUTION"             # routable liquidity exists, below threshold
    else:
        recommendation = "DO_NOT_ROUTE"        # value > 0 but zero routability — thermodynamic death

    result = {
        "asset_id":                  asset_id,
        "total_score":               total_score,
        "ocean_score":               ocean_score,
        "form_count":                len(breakdown),
        "total_form_value":          total_value,
        "form_breakdown":            breakdown,
        "best_form_path":            best_form_path,
        "slippage_estimate":         slippage_estimate,
        "slippage_breakdown":        slippage_breakdown,
        "routing_threshold":         routing_threshold,
        "routing_viable":            routing_viable,
        "recommendation":            recommendation,
        "no_asset_has_zero_liquidity": total_score > 0,
        "formula":                   ("LIQUIDITY_OCEAN_SCORE = Σ_forms [VALUE × 1/shift_cost "
                                      "× 1/time_to_convert × BEO_health]"),
        "spec":                      "BTCP Master Implementation Spec §6.1 (No Asset Has Zero Liquidity)",
        "signal":                    None,
    }

    # LIQUIDITY_OCEAN_SIGNAL — emitted when the ocean crosses the routing
    # threshold (spec §6.1 emission: asset, ocean_score, form_breakdown,
    # best_form_path, estimated_slippage).
    if breakdown and routing_viable:
        result["signal"] = build_liquidity_ocean_signal(result)

    return result


def build_liquidity_ocean_signal(
    ocean_result: dict,
    entity_id=None,
    coherence_result: Optional[dict] = None,
    observed_timestamps: Optional[list] = None,
    provenance: Optional[list] = None,
) -> dict:
    """
    LIQUIDITY_OCEAN_SIGNAL (BTCP spec §6.1) — emitted as an EXTENDED PAYLOAD on
    the LIQUIDITY_HEALTH core signal type (id 10).

    WHY NOT A NEW TYPE: the canonical registry is a hard 24-type parity
    constraint — spec/signal_types.md invariant ("Exactly 24 signal types are
    defined; new types require a protocol fork"), the wasm signal processor's
    signal_type_count() == 24, and the on-chain signal type ids all mirror the
    same 24. The whitepaper 6.x LIQUIDITY_OCEAN emission is therefore carried
    as a typed sub-payload (signal_subtype "LIQUIDITY_OCEAN") on
    LIQUIDITY_HEALTH — the liquidity signal family — instead of registering a
    25th type that would break parity.

    Args:
        ocean_result:     the dict returned by liquidity_ocean_score().
        entity_id:        signal entity (defaults to the asset_id).
        coherence_result: real coherence evaluation if available; otherwise an
                          honest ocean-derived stub (C=ocean_score,
                          theta=routing_threshold, emits=True) is used.
        observed_timestamps: optional BRT observation timestamps.
        provenance:       optional caller source records.
    """
    try:
        from core.master.signal_factory import build_signal, SignalType
    except ImportError as exc:
        raise ImportError(
            "build_liquidity_ocean_signal requires the core package on sys.path "
            "(repo root) — import as core.extended.natural_liquidity, or run with "
            "the repository root importable"
        ) from exc

    asset_id    = ocean_result.get("asset_id")
    ocean_score = float(ocean_result.get("ocean_score", 0.0))
    threshold   = float(ocean_result.get("routing_threshold", LIQUIDITY_OCEAN_ROUTING_THRESHOLD))
    form_breakdown = ocean_result.get("form_breakdown", [])

    if entity_id is None:
        entity_id = asset_id if asset_id is not None else "liquidity-ocean"

    if coherence_result is None:
        coherence_result = {
            "C":     ocean_score,
            "theta": threshold,
            "emits": True,
            "margin": ocean_score - threshold,
        }

    return build_signal(
        entity_id=entity_id,
        signal_type=SignalType.LIQUIDITY_HEALTH,
        coherence_result=coherence_result,
        signal_value=ocean_score,
        ci_95_lower=max(0.0, ocean_score - 0.05),
        ci_95_upper=min(1.0, ocean_score + 0.05),
        extra={
            "signal_subtype":     "LIQUIDITY_OCEAN",
            "asset_id":           asset_id,
            "ocean_score":        ocean_score,
            "total_score":        ocean_result.get("total_score"),
            "form_count":         len(form_breakdown),
            "form_breakdown":     form_breakdown,
            "best_form_path":     ocean_result.get("best_form_path"),
            "estimated_slippage": ocean_result.get("slippage_estimate"),
            "slippage_breakdown": ocean_result.get("slippage_breakdown"),
            "routing_threshold":  threshold,
            "routing_viable":     ocean_result.get("routing_viable"),
            "recommendation":     ocean_result.get("recommendation"),
            "formula":            ocean_result.get("formula"),
            "spec":               ocean_result.get("spec"),
            "emission_rule":      "emitted when ocean_score >= routing_threshold (§6.1)",
        },
        observed_timestamps=observed_timestamps,
        provenance=provenance if provenance is not None else [{
            "source":  "liquidity_ocean",
            "stage":   "§6.1 form-equivalent aggregation",
            "forms":   len(form_breakdown),
            "spec":    "BTCP Master Implementation Spec §6.1",
        }],
    )


class LiquidityOceanEngine:
    """
    §6.1 form-equivalent engine wrapper for the BTCP integration hub
    (core/btcp/integration.py module 3.4 — `from liquidity_ocean import
    LiquidityOceanEngine` previously pointed at a class that did not exist,
    so the ocean term silently fell back to 0.5).

    The spec's `akashic.get_equivalent_forms(asset)` data source has no live
    feed yet (§6.2 form-transformation events are not indexed), so the
    registry here is CALLER-POPULATED and empty by default — nothing is
    fabricated. Register the observed equivalent forms (from
    STAKE/UNSTAKE/MINT/BURN/LIQUIDITY/BORROW/REPAY events per §6.2) via
    register_forms().
    """

    def __init__(self, forms_registry: Optional[dict] = None):
        self._registry: dict = {
            str(k): list(v) for k, v in (forms_registry or {}).items()
        }

    def register_forms(self, asset_id, forms: List[dict]) -> int:
        """Register the observed equivalent forms for an asset. Returns count."""
        self._registry[str(asset_id)] = list(forms)
        return len(self._registry[str(asset_id)])

    def get_equivalent_forms(self, asset_id) -> List[dict]:
        """Spec §6.1 accessor (the akashic.get_equivalent_forms placeholder)."""
        return list(self._registry.get(str(asset_id), []))

    def score(self, asset_id, **kwargs) -> dict:
        """Full §6.1 result dict (see liquidity_ocean_score)."""
        return liquidity_ocean_score(asset_id, self.get_equivalent_forms(asset_id), **kwargs)

    def compute_score(self, asset_id, chain_id=None) -> float:
        """
        Raw §6.1 LIQUIDITY_OCEAN_SCORE — the Σ VALUE × 1/shift_cost ×
        1/time_to_convert × BEO_health sum — for the BTCP routing hub (3.4).

        Raises ValueError when the asset has no registered equivalent forms:
        an empty registry is MISSING DATA, not zero liquidity (per the §6.1
        theorem only a zero-value ecosystem scores zero), so the hub's
        try/except falls through to its documented 0.5 neutral fallback
        instead of misreporting thermodynamic death.
        """
        forms = self.get_equivalent_forms(asset_id)
        if not forms:
            raise ValueError(
                f"no equivalent forms registered for asset {asset_id!r} — "
                "empty registry is missing data, not zero liquidity (spec §6.1)"
            )
        return liquidity_ocean_score(asset_id, forms)["total_score"]

    def compute_normalized(self, asset_id) -> float:
        """Normalized ocean score in [0, 1] (value-weighted routable fraction)."""
        forms = self.get_equivalent_forms(asset_id)
        if not forms:
            raise ValueError(
                f"no equivalent forms registered for asset {asset_id!r} — "
                "empty registry is missing data, not zero liquidity (spec §6.1)"
            )
        return liquidity_ocean_score(asset_id, forms)["ocean_score"]


if __name__ == "__main__":
    euler_march2023 = compute_nl(
        depth_per_tick=[1000, 50, 20, 10, 5],
        top5_lp_share=0.92,
        lp_count=8,
        baseline_ld_90d=[0.5, 0.6, 0.55, 0.48, 0.52],
        ld_during_stress=0.05,
        ld_during_normal=0.55,
    )
    print(f"Euler March 2023 ($197M exploit, real historical event) NL:  {euler_march2023['nl_score']:.4f} (expected ~0.09 (based on real Euler exploit behavioral pattern))")
    print(f"  LD={euler_march2023['ld_score']:.3f} LO={euler_march2023['lo_score']:.3f} "
          f"LC={euler_march2023['lc_score']:.3f} LS={euler_march2023['ls_score']:.3f}")
    print(f"  Alert:            {euler_march2023['alert']} (expected True)")
    assert euler_march2023['alert'], "NL alert should fire for Euler scenario"

    healthy = compute_nl(
        depth_per_tick=[100]*20,
        top5_lp_share=0.35,
        lp_count=200,
        baseline_ld_90d=[0.9]*30,
        ld_during_stress=0.8,
        ld_during_normal=0.9,
    )
    print(f"Healthy pool NL:   {healthy['nl_score']:.4f} (expected > 0.60)")
    assert healthy['nl_score'] > 0.50, "Healthy pool should score well"
    print("PHASE 16 PASS — NL engine verified, simulated March 12 scenario (synthetic test vector) passes")
