"""tests/unit/test_signal_registry.py — signal-type registry completion.

Wave 3 D, R-SG-03 / top-10 remediation #8 (K4 resolution):

  * The canonical registry is EXACTLY 24 types = MD §11's 19 + V2 Part 5's
    5 extended (cross-language parity: wasm signal_type_count()==24, rust
    SIGNAL_TYPE_COUNT==24, on-chain ids 0–23, signal_types.md S1–S24).
  * BTCP §14.2's ten additions: three already exist in the 24
    (BTCP_ROUTE, CONSENSUS_ADAPTATION, RESURRECTION); the other seven
    (BEHAVIORAL_TRUTH, SHADOW_CHAIN, LIQUIDITY_OCEAN, CHAIN_RELIABILITY,
    BTCP_ESCROW_EVENT, BTCP_TIMEOUT, GENESIS_COMMITMENT) are registered as
    an EXPLICIT BTCP-domain extension carried as typed sub-payloads —
    closing the "missing CHAIN_RELIABILITY/BTCP_TIMEOUT weaken
    route-failure signaling" gap without breaking the 24-type parity.
  * Every one of the 31 names is classifiable at emission (fail-closed on
    unknown names — signal_types.md: "A signal without a valid
    emitter_layer MUST be rejected").

M-073 owner ruling (Wave 5): the canonical taxonomy is 29 types = the 19
  base (D1 §11) + the BTCP-family 10 (spec §2 + §14.2). BTCP_ROUTE and
  CONSENSUS_ADAPTATION sit in both families, so the closed set holds 27
  distinct names while the count is 29. Pinned below, together with the
  spec-faithful per-type builders and their D3 payload contracts.
"""

import pytest

from core.master.signal_factory import (
    BTCP_DOMAIN_SIGNALS,
    BTCP_ESCROW_STATES,
    BTCP_FAMILY_10_TYPES,
    CANONICAL_19_TYPES,
    CANONICAL_29_TOTAL,
    DUAL_FAMILY_TYPES,
    NL_COLLAPSE_THRESHOLD,
    RULING_BASE_19_TYPES,
    RULING_CLOSED_SET_27,
    RULING_NAME_ALIASES,
    SENSING_PLANE_COUNT,
    SignalType,
    ULTRA_LIGHT_NODE_BYTES_PER_BLOCK,
    V2_EXTENDED_5_TYPES,
    build_btcp_domain_signal,
    build_btcp_escrow_event,
    build_btcp_timeout,
    build_behavioral_truth,
    build_chain_reliability,
    build_genesis_commitment,
    build_liquidity_ocean,
    build_shadow_chain,
    classify_signal,
    signal_registry,
)


# MD §11 "THE 19 SIGNAL TYPES" — exact table rows.
MD_SECTION_11_TYPES = {
    "VALUATION", "SILENCE", "LIQUIDITY_HEALTH", "MANIPULATION_ALERT",
    "TRAJECTORY", "SYSTEMIC_RISK", "GOVERNANCE_SIGNAL",
    "CROSS_CHAIN_COHERENCE", "STABLECOIN_HEALTH", "PHASE_TRANSITION",
    "FORK_DIVERGENCE", "GENESIS", "REGULATORY_BEHAVIORAL",
    "SOVEREIGN_BEHAVIORAL", "MEV_BEHAVIORAL", "ENERGY_PARTICIPATION",
    "BIOLOGICAL_CAPITAL", "BTCP_ROUTE", "CONSENSUS_ADAPTATION",
}

# V2 Part 5's 5 extended types (authoritative where MD is silent).
V2_PART5_EXTRA = {
    "RESURRECTION", "NEGATIVE_SPACE", "INSTITUTIONAL_BHV",
    "ECOSYSTEM_HEALTH", "BOOTSTRAP",
}

# Registry-name aliases the enum uses for two MD rows (MEV_BEHAVIORAL →
# MEV_EXPOSURE; REGULATORY_BEHAVIORAL → REGULATORY_BHV).
MD_ALIASES = {
    "MEV_EXPOSURE": "MEV_BEHAVIORAL",
    "REGULATORY_BHV": "REGULATORY_BEHAVIORAL",
}

# BTCP Master Implementation Spec §14.2 "New Signal Types to Add" — the
# ten listed names (three already in the canonical 24).
BTCP_14_2_TYPES = {
    "BTCP_ROUTE", "BEHAVIORAL_TRUTH", "SHADOW_CHAIN", "LIQUIDITY_OCEAN",
    "CONSENSUS_ADAPTATION", "CHAIN_RELIABILITY", "BTCP_ESCROW_EVENT",
    "BTCP_TIMEOUT", "GENESIS_COMMITMENT", "RESURRECTION",
}


class TestCanonical24:
    def test_exactly_24_types(self):
        assert len(SignalType) == 24

    def test_ids_0_to_23_dense(self):
        assert sorted(int(t) for t in SignalType) == list(range(24))

    def test_md_11_all_19_present(self):
        names = {MD_ALIASES.get(t.name, t.name) for t in SignalType}
        missing = MD_SECTION_11_TYPES - names
        assert not missing, f"MD §11 types missing from enum: {missing}"

    def test_v2_extended_5_present(self):
        names = {t.name for t in SignalType}
        assert V2_PART5_EXTRA <= names

    def test_k4_resolution_19_plus_5(self):
        """K4: MD's 19 + V2's 5 extended = the implemented 24."""
        names = {t.name for t in SignalType}
        md_names = {MD_ALIASES.get(n, n) for n in names}
        assert MD_SECTION_11_TYPES <= md_names
        assert V2_PART5_EXTRA <= names
        assert len(MD_SECTION_11_TYPES) == 19
        assert len(V2_PART5_EXTRA) == 5
        assert len(SignalType) == 19 + 5

    def test_canonical_lists_are_disjoint_and_complete(self):
        assert not set(CANONICAL_19_TYPES) & set(V2_EXTENDED_5_TYPES)
        assert set(CANONICAL_19_TYPES) | set(V2_EXTENDED_5_TYPES) == {
            t.name for t in SignalType
        }

    def test_registry_view(self):
        reg = signal_registry()
        assert reg["total_classifiable"] == 31
        assert len(reg["canonical_24"]) == 24
        assert len(reg["canonical_19"]) == 19
        assert len(reg["v2_extended_5"]) == 5
        assert len(reg["btcp_domain_7"]) == 7


class TestM073RulingTaxonomy:
    """M-073 owner ruling: the canonical taxonomy is 29 signal types."""

    def test_exactly_29_types(self):
        """29 = 19 base (D1 §11) + 10 BTCP family (spec §2 + §14.2)."""
        assert CANONICAL_29_TOTAL == 29
        assert len(RULING_BASE_19_TYPES) == 19
        assert len(BTCP_FAMILY_10_TYPES) == 10
        assert len(RULING_BASE_19_TYPES) + len(BTCP_FAMILY_10_TYPES) == 29

    def test_closed_set_matches_ruling_list(self):
        """The closed set is exactly the ruling's 27 distinct names."""
        assert set(RULING_CLOSED_SET_27) == set(RULING_BASE_19_TYPES) | set(BTCP_FAMILY_10_TYPES)
        assert len(RULING_CLOSED_SET_27) == 27
        assert len(set(RULING_CLOSED_SET_27)) == 27   # no duplicates

    def test_dual_family_names_are_shared(self):
        """BTCP_ROUTE + CONSENSUS_ADAPTATION sit in both families (the
        ruling's own note) — counted once per family in the 29."""
        assert set(DUAL_FAMILY_TYPES) == set(RULING_BASE_19_TYPES) & set(BTCP_FAMILY_10_TYPES)
        assert sorted(DUAL_FAMILY_TYPES) == ["BTCP_ROUTE", "CONSENSUS_ADAPTATION"]

    def test_registry_view_reports_the_ruling(self):
        reg = signal_registry()
        assert reg["canonical_total"] == 29
        assert reg["ruling_base_19"] == RULING_BASE_19_TYPES
        assert reg["btcp_family_10"] == BTCP_FAMILY_10_TYPES
        assert reg["dual_family_2"] == ["BTCP_ROUTE", "CONSENSUS_ADAPTATION"]
        assert reg["closed_set_27"] == RULING_CLOSED_SET_27

    def test_every_closed_set_name_classifiable(self):
        """Each of the 27 names (ruling spelling) constructs a signal with
        the required schema fields and classifies fail-closed-adjacent."""
        for name in RULING_CLOSED_SET_27:
            cls = classify_signal(name)
            assert cls["ruling_name"] == name
            assert cls["btcp_family"] == (name in BTCP_FAMILY_10_TYPES)
            assert cls["severity"] in ("info", "warning", "critical")
            assert cls["emitter_layer"].startswith("L")

    def test_whitepaper_spellings_resolve(self):
        """The two drifted names classify in their ruling spelling too."""
        for ruling_name, internal in RULING_NAME_ALIASES.items():
            cls = classify_signal(ruling_name)
            assert cls["type_name"] == internal
            assert cls["ruling_name"] == ruling_name
            assert cls["domain"] == "canonical_19"


class TestSpecFaithfulBuilders:
    """Per-type payload contracts from the BTCP master spec (D3)."""

    _COH = {
        "C": 0.90, "theta": 0.60, "margin": 0.30, "emits": True,
        "coherence_gap": 0, "limiting_plane": "anima", "trend": "STABLE",
        "eta_blocks": 0,
    }
    _E = b"\xab" * 32

    _SCHEMA_FIELDS = (
        "signal_id", "signal_type", "signal_type_id", "entity_id",
        "signal_value", "ci_95", "coherence", "threshold", "margin",
        "plane_breakdown", "limiting_plane", "silence", "silence_gap",
        "coherence_trend", "eta_blocks", "akashic_depth", "bootstrap_phase",
        "conf_genesis", "timestamp", "ttl_seconds", "biological_time",
        "genomic_signature", "immune_clearance", "security_generation",
        "validator_count", "validator_hhi", "reflexivity_flag",
        "temporal_coherence", "provenance",
    )

    def _assert_schema(self, sig, subtype, carrier: SignalType):
        for field in self._SCHEMA_FIELDS:
            assert field in sig, f"{subtype} missing schema field {field}"
        assert sig["signal_subtype"] == subtype
        assert sig["btcp_domain"] is True
        assert sig["signal_type_id"] == int(carrier)
        assert sig["signal_type_id"] < 24, "must ride a canonical-24 carrier"
        assert isinstance(sig["provenance"], list) and sig["provenance"]
        assert isinstance(sig["ci_95"], list) and len(sig["ci_95"]) == 2

    def test_behavioral_truth_payload(self):
        """D3-150: 4 present fields, 5 absent fields, 7-plane results."""
        sig = build_behavioral_truth(
            self._E, self._COH, 0.84, "0xcommit", [True] * 7,
        )
        self._assert_schema(sig, "BEHAVIORAL_TRUTH", SignalType.VALUATION)
        assert sig["public_commitment"] == "0xcommit"
        assert sig["coherence_score"] == 0.84
        assert sig["plane_results"] == [True] * 7
        assert sig["planes_checked"] == SENSING_PLANE_COUNT == 7
        assert sig["coherent_7_plane"] is True
        for absent in ("behavior_content", "amount", "counterparty", "protocol", "chain"):
            assert absent not in sig, f"{absent} must be ABSENT (D3-150)"

    def test_behavioral_truth_fail_closed(self):
        with pytest.raises(ValueError):
            build_behavioral_truth(self._E, self._COH, 1.5, "0xcommit", [True] * 7)
        with pytest.raises(ValueError):
            build_behavioral_truth(self._E, self._COH, 0.8, "0xcommit", [True] * 5)
        with pytest.raises(ValueError):
            build_behavioral_truth(self._E, self._COH, 0.8, "0xcommit", [1, 1, 1, 1, 1, 1, 1])

    def test_shadow_chain_payload(self):
        """D3-152..156: sources, 80-byte ultra-light node, rejoin phases."""
        sig = build_shadow_chain(
            self._E, self._COH, 0.68, "hostile-x",
            ["CROSS_CHAIN_TRANSFER", "BRIDGE_EVENT"], 2,
            rejoin_phase="CHANNEL6_OBSERVATION",
        )
        self._assert_schema(sig, "SHADOW_CHAIN", SignalType.SYSTEMIC_RISK)
        assert sig["hostile_chain"] == "hostile-x"
        assert sig["shadow_confidence"] == 0.68
        assert sig["source_count"] == 2
        assert sig["ultra_light_node_bytes_per_block"] == ULTRA_LIGHT_NODE_BYTES_PER_BLOCK == 80
        assert sig["rejoin_phase"] == "CHANNEL6_OBSERVATION"
        assert "rejoin_note" in sig
        assert sig["dead_zone"] is False
        dead = build_shadow_chain(
            self._E, self._COH, 0.0, "isolated-x", [], 0, dead_zone=True,
        )
        assert dead["dead_zone"] is True and "dead_zone_note" in dead
        with pytest.raises(ValueError):
            build_shadow_chain(self._E, self._COH, 0.5, "x", [], 0, rejoin_phase="NOT_A_PHASE")

    def test_liquidity_ocean_payload(self):
        """D3-145: asset, ocean_score, form_breakdown, best_form_path,
        estimated_slippage + routable flag (D3-144)."""
        sig = build_liquidity_ocean(
            self._E, self._COH, 1_250_000.0, "USDC",
            {"aUSDC": 500_000.0, "cUSDC": 300_000.0}, "USDC→aUSDC", 0.004,
        )
        self._assert_schema(sig, "LIQUIDITY_OCEAN", SignalType.LIQUIDITY_HEALTH)
        assert sig["asset"] == "USDC"
        assert sig["ocean_score"] == 1_250_000.0
        assert sig["form_breakdown"] == {"aUSDC": 500_000.0, "cUSDC": 300_000.0}
        assert sig["best_form_path"] == "USDC→aUSDC"
        assert sig["estimated_slippage"] == 0.004
        assert sig["routable_liquidity"] is True
        zero = build_liquidity_ocean(self._E, self._COH, 0.0, "DEAD", {}, "-", 0.0)
        assert zero["routable_liquidity"] is False
        with pytest.raises(ValueError):
            build_liquidity_ocean(self._E, self._COH, -1.0, "X", {}, "-", 0.0)

    def test_chain_reliability_payload(self):
        """D3-179: EXTERNAL/ENTITY cause, BEO impact, NL collapse 0.10."""
        sig = build_chain_reliability(
            self._E, self._COH, 0.93, 42161, 0.07, "EXTERNAL_CAUSE",
            ["beo_1", "beo_2"], nl_at_failure=0.08,
        )
        self._assert_schema(sig, "CHAIN_RELIABILITY", SignalType.CROSS_CHAIN_COHERENCE)
        assert sig["chain_id"] == 42161
        assert sig["failure_rate"] == 0.07
        assert sig["cause_classification"] == "EXTERNAL_CAUSE"
        assert sig["beo_impact"] == ["beo_1", "beo_2"]
        assert sig["nl_collapse"] is True          # 0.08 < 0.10 (D3-179)
        assert NL_COLLAPSE_THRESHOLD == 0.10
        ok = build_chain_reliability(
            self._E, self._COH, 0.95, 1, 0.02, "ENTITY_CAUSE", [], nl_at_failure=0.50,
        )
        assert ok["nl_collapse"] is False
        no_nl = build_chain_reliability(self._E, self._COH, 0.95, 1, 0.02, "ENTITY_CAUSE", [])
        assert "nl_collapse" not in no_nl          # never fabricated without the figure
        with pytest.raises(ValueError):
            build_chain_reliability(self._E, self._COH, 0.9, 1, 0.1, "MYSTERY_CAUSE", [])

    def test_btcp_escrow_event_payload(self):
        """§14.2: escrow states HOLDING | RELEASED | REVERTED (fail-closed)."""
        for state in BTCP_ESCROW_STATES:
            sig = build_btcp_escrow_event(
                self._E, self._COH, "0xescrow_1", state, 12_500.0, "route_7",
            )
            self._assert_schema(sig, "BTCP_ESCROW_EVENT", SignalType.BTCP_ROUTE)
            assert sig["escrow_state"] == state
            assert sig["escrow_id"] == "0xescrow_1"
            assert sig["amount"] == 12_500.0
            assert sig["route_id"] == "route_7"
            assert "state_note" in sig
        with pytest.raises(ValueError):
            build_btcp_escrow_event(self._E, self._COH, "0xescrow_1", "PENDING", 1.0)

    def test_btcp_timeout_payload(self):
        """revert_on_timeout assert: current > lock + timeout (D3)."""
        sig = build_btcp_timeout(
            self._E, self._COH, "0xescrow_1", 1_800_000, 7200, 1_800_001, "intent_9a3f",
        )
        self._assert_schema(sig, "BTCP_TIMEOUT", SignalType.BTCP_ROUTE)
        assert sig["timeout_reached"] is False      # 1_800_001 ≤ 1_807_200
        assert sig["blocks_elapsed"] == 1
        assert sig["intent_preserved"] is True
        assert sig["intent"] == "intent_9a3f"
        fired = build_btcp_timeout(
            self._E, self._COH, "0xescrow_1", 1_800_000, 7200, 1_807_201, "intent_9a3f",
        )
        assert fired["timeout_reached"] is True     # 1_807_201 > 1_807_200
        with pytest.raises(ValueError):
            build_btcp_timeout(self._E, self._COH, "0xescrow_1", 100, 0, 200, "i")

    def test_genesis_commitment_payload(self):
        """D3-157..160: pathway, null state, sponsored genesis, ocean entry."""
        sig = build_genesis_commitment(
            self._E, self._COH, 0.80, "SPONSORED_GENESIS", "0xcommit_abc",
            null_state="BEHAVIORAL_NULL_STATE",
            sponsor="beo_sponsor_1", sponsor_bond=1_000.0,
        )
        self._assert_schema(sig, "GENESIS_COMMITMENT", SignalType.GENESIS)
        assert sig["genesis_pathway"] == "SPONSORED_GENESIS"
        assert sig["commitment_hash"] == "0xcommit_abc"
        assert sig["commitment_score"] == 0.80
        assert sig["null_state"] == "BEHAVIORAL_NULL_STATE"
        assert sig["sponsor"] == "beo_sponsor_1"
        assert sig["sponsor_bond"] == 1_000.0
        assert "null_state_note" in sig and "sponsored_note" in sig
        asset = build_genesis_commitment(
            self._E, self._COH, 0.7, "PROTOCOL_ISSUANCE", "0xc2", null_state="LIQUIDITY_NULL_STATE",
        )
        assert "liquidity_ocean_entry" in asset      # D3-158
        with pytest.raises(ValueError):
            build_genesis_commitment(self._E, self._COH, 0.7, "MAGIC_PATHWAY", "0xc")
        with pytest.raises(ValueError):
            build_genesis_commitment(self._E, self._COH, 0.7, "SOCIAL_PROOF", "0xc", null_state="WRONG")

    def test_every_new_type_constructs_full_schema(self):
        """All 7 spec-faithful builders construct a schema-complete signal."""
        built = 0
        for name in BTCP_DOMAIN_SIGNALS:
            cls = classify_signal(name)
            assert cls["domain"] == "btcp_14_2" and cls["btcp_family"] is True
            built += 1
        assert built == 7


class TestBTCPDomainRegistry:
    def test_btcp_14_2_all_ten_classifiable(self):
        """Every BTCP §14.2 name resolves (3 in the 24 + 7 domain entries)."""
        for name in BTCP_14_2_TYPES:
            meta = classify_signal(name)
            assert meta["type_name"] == name
            assert meta["domain"] in ("canonical_19", "v2_extended_5", "btcp_14_2")
            assert meta["severity"] and meta["emitter_layer"]

    def test_the_missing_seven_are_registered(self):
        """Top-10 #8: the seven absent names now exist and are classifiable."""
        missing_7 = {
            "BEHAVIORAL_TRUTH", "SHADOW_CHAIN", "LIQUIDITY_OCEAN",
            "CHAIN_RELIABILITY", "BTCP_ESCROW_EVENT", "BTCP_TIMEOUT",
            "GENESIS_COMMITMENT",
        }
        assert missing_7 == set(BTCP_DOMAIN_SIGNALS)

    def test_domain_types_ride_canonical_carriers(self):
        for name, meta in BTCP_DOMAIN_SIGNALS.items():
            assert meta["carrier"] in {t.name for t in SignalType}
            cls = classify_signal(name)
            assert cls["signal_subtype"] == name
            assert cls["signal_type_id"] < 24
            assert cls["domain"] == "btcp_14_2"

    def test_route_failure_types_classifiable(self):
        for name in ("CHAIN_RELIABILITY", "BTCP_TIMEOUT"):
            cls = classify_signal(name)
            assert cls["severity"] == "warning"
            assert cls["emitter_layer"] == "L9"


class TestEmission:
    _COH = {
        "C": 0.90, "theta": 0.60, "margin": 0.30, "emits": True,
        "coherence_gap": 0, "limiting_plane": "anima", "trend": "STABLE",
        "eta_blocks": 0,
    }

    def test_build_btcp_domain_signal_emits_typed_payload(self):
        sig = build_btcp_domain_signal("BTCP_TIMEOUT", b"\xab" * 32, self._COH, 0.8)
        assert sig["signal_type_id"] == int(SignalType.BTCP_ROUTE)
        assert sig["signal_subtype"] == "BTCP_TIMEOUT"
        assert sig["btcp_domain"] is True
        assert sig["severity"] == "warning"
        assert "ci_95" in sig and sig["provenance"]

    def test_build_all_seven_domain_types(self):
        for name in BTCP_DOMAIN_SIGNALS:
            sig = build_btcp_domain_signal(name, b"\xab" * 32, self._COH, 0.7)
            assert sig["signal_subtype"] == name

    def test_unknown_type_fails_closed(self):
        with pytest.raises(KeyError):
            classify_signal("NOT_A_TYPE")
        with pytest.raises(KeyError):
            build_btcp_domain_signal("NOT_A_TYPE", b"\xab" * 32, self._COH, 0.7)

    def test_classify_accepts_enum_members(self):
        cls = classify_signal(SignalType.VALUATION)
        assert cls["domain"] == "canonical_19"
        cls = classify_signal(SignalType.BOOTSTRAP)
        assert cls["domain"] == "v2_extended_5"

    def test_classification_of_all_31(self):
        for t in SignalType:
            assert classify_signal(t)["domain"] in ("canonical_19", "v2_extended_5")
        for name in BTCP_DOMAIN_SIGNALS:
            assert classify_signal(name)["domain"] == "btcp_14_2"
