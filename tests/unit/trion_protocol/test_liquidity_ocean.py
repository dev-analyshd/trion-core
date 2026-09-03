"""
BTCP Master Implementation Spec §6.1 — form-equivalent Liquidity Ocean tests.

LIQUIDITY_OCEAN_SCORE = Σ_forms [ VALUE(form) × 1/shift_cost(form)
                                  × 1/time_to_convert(form) × BEO_health(form) ]

Covers:
  * the literal spec sum on a multi-form asset (ETH / WETH / stETH-LP)
  * "No Asset Has Zero Liquidity" — a form with near-zero direct liquidity
    still contributes through cheap conversion; only a zero-value ecosystem
    totals zero
  * basis-points vs 0-1 fraction cost inputs
  * the literal spec pseudocode div-by-zero guard (cost=0 / time=0 → 0)
  * best_form_path (lowest combined cost×time route to the most liquid form)
  * slippage estimate (combined shift cost + linear market impact)
  * threshold emission of LIQUIDITY_OCEAN_SIGNAL as an extended payload on
    LIQUIDITY_HEALTH (id 10) — the 24-type registry parity constraint forbids
    registering a 25th signal type
  * LiquidityOceanEngine (BTCP integration hub 3.4 wrapper)
  * import parity: the canonical core.extended.natural_liquidity path and the
    spec-named anima-service liquidity_ocean path resolve to the same objects
"""
import pytest

from core.extended.natural_liquidity import (
    liquidity_ocean_score,
    build_liquidity_ocean_signal,
    LiquidityOceanEngine,
    LIQUIDITY_OCEAN_ROUTING_THRESHOLD,
    OCEAN_REF_SHIFT_COST,
    OCEAN_REF_SHIFT_TIME,
)

# Multi-form asset per the task: ETH / WETH / stETH-LP.
ETH_FORMS = [
    {"form": "ETH",      "value": 12_000_000.0, "shift_cost": 0.0005, "time_to_convert": 12.0,  "beo_health": 0.92},
    {"form": "WETH",     "value": 45_000_000.0, "shift_cost": 0.0003, "time_to_convert": 15.0,  "beo_health": 0.88},
    {"form": "stETH-LP", "value":  8_500_000.0, "shift_cost": 0.0012, "time_to_convert": 600.0, "beo_health": 0.75},
]

# Everything slow, expensive and behaviorally weak → ocean far below threshold.
ILLIQUID_FORMS = [
    {"form": "ETH", "value": 100_000.0, "shift_cost": 0.02, "time_to_convert": 86_400.0, "beo_health": 0.30},
]


def _spec_contribution(form: dict) -> float:
    """Independent recomputation of the §6.1 term (spec-literal pseudocode)."""
    value = form["value"]
    cost = form["shift_cost"]
    time_c = form["time_to_convert"]
    return (value
            * (1.0 / cost if cost > 0 else 0)
            * (1.0 / time_c if time_c > 0 else 0)
            * form["beo_health"])


# ─── spec formula: the sum ───────────────────────────────────────────────────

class TestSpecFormula:
    def test_total_score_is_the_spec_sum(self):
        result = liquidity_ocean_score("ETH", ETH_FORMS)
        expected = sum(_spec_contribution(f) for f in ETH_FORMS)
        assert result["total_score"] == pytest.approx(expected, rel=1e-12)

    def test_per_form_breakdown_contributions(self):
        result = liquidity_ocean_score("ETH", ETH_FORMS)
        assert result["form_count"] == 3
        by_name = {b["form"]: b for b in result["form_breakdown"]}
        assert set(by_name) == {"ETH", "WETH", "stETH-LP"}
        for f in ETH_FORMS:
            b = by_name[f["form"]]
            # breakdown mirrors the task's required per-form fields
            for key in ("form", "value", "shift_cost", "time_to_convert",
                        "beo_health", "contribution"):
                assert key in b
            assert b["value"] == f["value"]
            assert b["shift_cost"] == f["shift_cost"]
            assert b["time_to_convert"] == f["time_to_convert"]
            assert b["beo_health"] == f["beo_health"]
            assert b["contribution"] == pytest.approx(_spec_contribution(f), rel=1e-12)
        # the sum of the breakdown equals the total
        assert sum(b["contribution"] for b in result["form_breakdown"]) == \
            pytest.approx(result["total_score"], rel=1e-12)

    def test_formula_documented_in_result(self):
        result = liquidity_ocean_score("ETH", ETH_FORMS)
        assert "LIQUIDITY_OCEAN_SCORE" in result["formula"]
        assert "§6.1" in result["spec"]

    def test_ocean_score_is_value_weighted_routable_fraction(self):
        result = liquidity_ocean_score("ETH", ETH_FORMS)
        # ETH and WETH are both cheaper than the 10 bps / 60 s references →
        # efficiency 1; stETH-LP is capped below.
        eth, weth, steth = (b for b in result["form_breakdown"])
        assert eth["cost_efficiency"] == 1.0 and eth["time_efficiency"] == 1.0
        assert weth["cost_efficiency"] == 1.0 and weth["time_efficiency"] == 1.0
        assert steth["cost_efficiency"] == pytest.approx(OCEAN_REF_SHIFT_COST / 0.0012)
        assert steth["time_efficiency"] == pytest.approx(OCEAN_REF_SHIFT_TIME / 600.0)
        total_value = sum(f["value"] for f in ETH_FORMS)
        expected = sum(b["normalized_contribution"] for b in result["form_breakdown"]) / total_value
        assert result["ocean_score"] == pytest.approx(expected, rel=1e-12)
        assert 0.0 <= result["ocean_score"] <= 1.0


# ─── "No Asset Has Zero Liquidity" (§6.1 theorem) ────────────────────────────

class TestNoAssetHasZeroLiquidity:
    def test_near_zero_direct_liquidity_still_contributes(self):
        """stETH-LP has near-zero DIRECT liquidity (no liquid market for the
        LP token itself) — but a cheap, fast conversion to WETH means the
        asset still contributes to the ocean."""
        result = liquidity_ocean_score("ETH", ETH_FORMS)
        steth = next(b for b in result["form_breakdown"] if b["form"] == "stETH-LP")
        assert steth["contribution"] > 0
        assert result["total_score"] > 0
        assert result["no_asset_has_zero_liquidity"] is True

    def test_only_convertible_illiquid_form_still_routable(self):
        """Even when the ONLY form has no direct market, a cheap conversion
        keeps the ocean > 0 — the theorem's core claim."""
        forms = [{
            "form": "stETH-LP",            # near-zero direct liquidity…
            "value": 5_000_000.0,
            "shift_cost": 0.0006,          # …but cheap (6 bps) conversion
            "time_to_convert": 120.0,
            "beo_health": 0.8,
        }]
        result = liquidity_ocean_score("ETH", forms)
        assert result["total_score"] == pytest.approx(_spec_contribution(forms[0]))
        assert result["total_score"] > 0
        assert result["ocean_score"] > 0
        assert result["recommendation"] != "DO_NOT_ROUTE"

    def test_zero_total_value_is_the_only_zero_ocean(self):
        """Only a zero-value ecosystem totals zero (thermodynamic death)."""
        zero_value = [{"form": "ETH", "value": 0.0, "shift_cost": 0.0005,
                       "time_to_convert": 12.0, "beo_health": 0.9}]
        result = liquidity_ocean_score("ETH", zero_value)
        assert result["total_score"] == 0.0
        assert result["no_asset_has_zero_liquidity"] is False

    def test_empty_forms(self):
        result = liquidity_ocean_score("ETH", [])
        assert result["total_score"] == 0.0
        assert result["ocean_score"] == 0.0
        assert result["routing_viable"] is False
        assert result["signal"] is None
        assert result["best_form_path"] is None
        assert result["slippage_estimate"] is None
        assert result["recommendation"] == "DO_NOT_ROUTE"

    def test_empty_forms_none_argument(self):
        result = liquidity_ocean_score("ETH", None)
        assert result["total_score"] == 0.0


# ─── cost input conventions ──────────────────────────────────────────────────

class TestCostConventions:
    def test_basis_points_equal_fraction(self):
        bps = [{"form": "X", "value": 1_000_000.0, "shift_cost": 12,  # 12 bps
                "time_to_convert": 60.0, "beo_health": 0.9}]
        fraction = [{"form": "X", "value": 1_000_000.0, "shift_cost": 0.0012,
                     "time_to_convert": 60.0, "beo_health": 0.9}]
        assert liquidity_ocean_score("X", bps)["total_score"] == \
            pytest.approx(liquidity_ocean_score("X", fraction)["total_score"], rel=1e-12)

    def test_zero_cost_literal_spec_guard(self):
        """The spec pseudocode zeroes the term rather than dividing by zero:
        `1.0/shift_cost if shift_cost > 0 else 0` — a zero-cost (or zero-time)
        form contributes exactly 0 to the raw sum."""
        result = liquidity_ocean_score("X", [
            {"form": "FREE", "value": 1_000_000.0, "shift_cost": 0,
             "time_to_convert": 10.0, "beo_health": 1.0},
        ])
        assert result["form_breakdown"][0]["contribution"] == 0.0
        assert result["total_score"] == 0.0

    def test_zero_time_literal_spec_guard(self):
        result = liquidity_ocean_score("X", [
            {"form": "INSTANT", "value": 1_000_000.0, "shift_cost": 0.001,
             "time_to_convert": 0, "beo_health": 1.0},
        ])
        assert result["total_score"] == 0.0

    def test_alias_keys_accepted(self):
        aliased = [{"name": "WETH", "value_usd": 45_000_000.0, "cost": 0.0003,
                    "time": 15.0, "beo": 0.88}]
        result = liquidity_ocean_score("ETH", aliased)
        canonical = liquidity_ocean_score("ETH", ETH_FORMS[1:2])
        assert result["total_score"] == pytest.approx(canonical["total_score"], rel=1e-12)

    def test_bytes_asset_id_hex_encoded(self):
        result = liquidity_ocean_score(b"\xab\xcd", ETH_FORMS)
        assert result["asset_id"] == "abcd"

    def test_non_dict_form_raises(self):
        with pytest.raises(TypeError):
            liquidity_ocean_score("ETH", ["WETH"])


# ─── best_form_path ──────────────────────────────────────────────────────────

class TestBestFormPath:
    def test_lowest_cost_time_route_to_most_liquid_form(self):
        # WETH has the highest §6.1 contribution → target.
        # From stETH-LP the route stETH-LP → ETH → WETH costs
        # (0.0012 + 0.0003) × (600 + 15) — the only candidate with two forms.
        forms = [ETH_FORMS[1], ETH_FORMS[2]]  # WETH + stETH-LP
        result = liquidity_ocean_score("ETH", forms)
        path = result["best_form_path"]
        assert path["target_form"] == "WETH"
        assert path["origin_form"] == "stETH-LP"
        assert path["path"] == ["stETH-LP", "ETH", "WETH"]
        assert path["combined_shift_cost"] == pytest.approx(0.0012 + 0.0003)
        assert path["combined_time_to_convert"] == pytest.approx(600.0 + 15.0)
        assert path["cost_time_product"] == pytest.approx(0.0015 * 615.0)
        assert len(path["hops"]) == 2
        assert path["hops"][0] == {"from": "stETH-LP", "to": "ETH",
                                   "shift_cost": 0.0012, "time_to_convert": 600.0}
        assert path["hops"][1] == {"from": "ETH", "to": "WETH",
                                   "shift_cost": 0.0003, "time_to_convert": 15.0}

    def test_cheapest_origin_chosen(self):
        # Among ETH and stETH-LP, routing ETH → WETH has the far lower
        # combined cost×time product (0.0008 × 27 vs 0.0015 × 615).
        result = liquidity_ocean_score("ETH", ETH_FORMS)
        path = result["best_form_path"]
        assert path["origin_form"] == "ETH"
        assert path["target_form"] == "WETH"
        assert path["cost_time_product"] == pytest.approx(0.0008 * 27.0)

    def test_single_form_needs_no_conversion(self):
        result = liquidity_ocean_score("ETH", ETH_FORMS[1:2])
        path = result["best_form_path"]
        assert path["path"] == ["WETH"]
        assert path["hops"] == []
        assert path["combined_shift_cost"] == 0.0

    def test_no_forms_no_path(self):
        assert liquidity_ocean_score("ETH", [])["best_form_path"] is None


# ─── slippage estimate ───────────────────────────────────────────────────────

class TestSlippageEstimate:
    def test_conversion_cost_plus_linear_market_impact(self):
        result = liquidity_ocean_score("ETH", ETH_FORMS, notional=1_000_000.0)
        # target = WETH: effective depth = 45M × 0.88 = 39.6M
        conversion_cost = 0.0005 + 0.0003          # ETH → ETH(base) → WETH
        market_impact = 1_000_000.0 / (1_000_000.0 + 45_000_000.0 * 0.88)
        assert result["slippage_estimate"] == \
            pytest.approx(conversion_cost + market_impact, rel=1e-12)
        bd = result["slippage_breakdown"]
        assert bd["conversion_cost"] == pytest.approx(conversion_cost)
        assert bd["market_impact"] == pytest.approx(market_impact, rel=1e-12)
        assert bd["effective_depth"] == pytest.approx(45_000_000.0 * 0.88)
        assert result["slippage_estimate"] < 1.0

    def test_no_notional_conversion_cost_only(self):
        result = liquidity_ocean_score("ETH", ETH_FORMS)
        assert result["slippage_estimate"] == pytest.approx(0.0005 + 0.0003)
        assert result["slippage_breakdown"]["market_impact"] is None


# ─── threshold emission: LIQUIDITY_OCEAN_SIGNAL ──────────────────────────────

class TestThresholdEmission:
    def test_signal_emitted_above_threshold(self):
        result = liquidity_ocean_score("ETH", ETH_FORMS)
        assert result["ocean_score"] >= LIQUIDITY_OCEAN_ROUTING_THRESHOLD
        assert result["routing_viable"] is True
        assert result["signal"] is not None

    def test_signal_not_emitted_below_threshold(self):
        result = liquidity_ocean_score("ETH", ILLIQUID_FORMS)
        assert result["ocean_score"] < LIQUIDITY_OCEAN_ROUTING_THRESHOLD
        assert result["routing_viable"] is False
        assert result["signal"] is None
        assert result["recommendation"] == "CAUTION"  # routable but shallow

    def test_custom_threshold_controls_emission(self):
        deep = liquidity_ocean_score("ETH", ETH_FORMS, routing_threshold=0.99)
        assert deep["signal"] is None
        shallow = liquidity_ocean_score("ETH", ILLIQUID_FORMS, routing_threshold=0.0)
        assert shallow["signal"] is not None  # threshold 0 → always crosses

    def test_signal_is_extended_payload_on_liquidity_health(self):
        """The 24-type registry parity (wasm signal_type_count() == 24,
        spec/signal_types.md invariant) forbids a 25th type — the §6.1
        LIQUIDITY_OCEAN emission rides LIQUIDITY_HEALTH (id 10) as a typed
        sub-payload."""
        result = liquidity_ocean_score("ETH", ETH_FORMS)
        signal = result["signal"]
        assert signal["signal_type"] == "LIQUIDITY_HEALTH"
        assert signal["signal_type_id"] == 10
        assert signal["signal_subtype"] == "LIQUIDITY_OCEAN"

    def test_signal_carries_spec_6_1_fields(self):
        """Spec §6.1: LIQUIDITY_OCEAN_SIGNAL emits asset, ocean_score,
        form_breakdown, best_form_path, estimated_slippage."""
        result = liquidity_ocean_score("ETH", ETH_FORMS, notional=500_000.0)
        signal = result["signal"]
        assert signal["asset_id"] == "ETH"
        assert signal["ocean_score"] == pytest.approx(result["ocean_score"])
        assert signal["total_score"] == pytest.approx(result["total_score"])
        assert signal["form_breakdown"] == result["form_breakdown"]
        assert signal["best_form_path"] == result["best_form_path"]
        assert signal["estimated_slippage"] == result["slippage_estimate"]

    def test_signal_mandatory_envelope(self):
        """Mirrors the core/master/signal_factory.py pattern: CI_95 always,
        biological_time, genomic_signature, non-empty provenance chain."""
        result = liquidity_ocean_score("ETH", ETH_FORMS)
        signal = result["signal"]
        assert isinstance(signal["signal_id"], str)
        lo, hi = signal["ci_95"]
        assert lo <= signal["signal_value"] <= hi
        assert "biological_time" in signal
        assert "genomic_signature" in signal and signal["genomic_signature"]
        assert isinstance(signal["provenance"], list) and signal["provenance"]
        assert signal["provenance"][0]["source"] == "liquidity_ocean"
        assert signal["recommendation"] == "ROUTE_OK"

    def test_direct_signal_builder_with_real_coherence(self):
        result = liquidity_ocean_score("ETH", ETH_FORMS)
        signal = build_liquidity_ocean_signal(
            result,
            coherence_result={"C": 0.9, "theta": 0.55, "emits": True},
        )
        assert signal["coherence"] == 0.9
        assert signal["signal_subtype"] == "LIQUIDITY_OCEAN"


# ─── LiquidityOceanEngine (BTCP integration hub 3.4 wrapper) ─────────────────

class TestLiquidityOceanEngine:
    def test_registry_roundtrip_and_raw_score(self):
        engine = LiquidityOceanEngine()
        with pytest.raises(ValueError):
            engine.compute_score("ETH")          # empty registry = missing data
        engine.register_forms("ETH", ETH_FORMS)
        assert engine.get_equivalent_forms("ETH") == ETH_FORMS
        raw = engine.compute_score("ETH", 42161)
        assert raw == pytest.approx(sum(_spec_contribution(f) for f in ETH_FORMS))
        assert engine.compute_normalized("ETH") == pytest.approx(
            liquidity_ocean_score("ETH", ETH_FORMS)["ocean_score"]
        )

    def test_score_returns_full_dict(self):
        engine = LiquidityOceanEngine({"ETH": ETH_FORMS})
        result = engine.score("ETH", notional=1_000_000.0)
        assert result["form_count"] == 3
        assert result["signal"] is not None


# ─── import parity: core path == spec-named anima-service path ───────────────

class TestImportParity:
    def test_anima_service_module_reexports_same_objects(self):
        # tests/conftest.py puts anima-service on sys.path
        import liquidity_ocean as anima_ocean
        from core.extended import natural_liquidity as core_nl
        assert anima_ocean.liquidity_ocean_score is core_nl.liquidity_ocean_score
        assert anima_ocean.build_liquidity_ocean_signal is core_nl.build_liquidity_ocean_signal
        assert anima_ocean.LiquidityOceanEngine is core_nl.LiquidityOceanEngine
        assert anima_ocean.LIQUIDITY_OCEAN_ROUTING_THRESHOLD == \
            core_nl.LIQUIDITY_OCEAN_ROUTING_THRESHOLD
        # the chain-level §7.2 aggregator is still importable from the same module
        assert hasattr(anima_ocean, "LiquidityOcean")
        assert hasattr(anima_ocean, "compute_ocean_coherence")

    def test_btcp_hub_module_34_import_resolves(self):
        """core/btcp/integration.py module 3.4 imports
        `from liquidity_ocean import LiquidityOceanEngine` — previously a
        nonexistent class (silent 0.5 fallback); it must now resolve."""
        import liquidity_ocean as anima_ocean
        assert anima_ocean.LiquidityOceanEngine is LiquidityOceanEngine
