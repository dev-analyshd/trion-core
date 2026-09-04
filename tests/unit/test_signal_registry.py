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
"""

import pytest

from core.master.signal_factory import (
    BTCP_DOMAIN_SIGNALS,
    CANONICAL_19_TYPES,
    V2_EXTENDED_5_TYPES,
    SignalType,
    build_btcp_domain_signal,
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
