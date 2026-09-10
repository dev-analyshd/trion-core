"""
BTCP Master Spec §4.1 — Intent object field set (gap #8 closure)
================================================================
The spec's Intent object (spec/BTCP_SPEC.txt lines 272-292) defines 15
fields across the top level and the constraints block. This suite pins:

1. the Python ``BITPIntent`` (core/btcp/modules.py) carries the full
   §4.1 field set with the spec defaults,
2. legacy 6-argument positional construction still works (backwards
   compatibility — the matcher/netting/aggregator callers rely on it),
3. the BITP matcher, netting engine and intent aggregator operate on
   fully-defaulted intents,
4. the §4.1 fields round-trip through construction untouched,
5. ``BITPIntent.hash()`` is a deterministic 32-byte SHA3-256 that covers
   every §4.1 field (append-only policy, mirroring rust Intent::hash),
6. the Rust ``Intent``/``IntentConstraints`` (rust/src/types.rs) field
   set statically covers the same §4.1 list (cross-language parity).
"""
import dataclasses
import re
from pathlib import Path

from core.btcp.modules import (
    BITPIntent,
    BITPMatcher,
    NettingEngine,
    IntentAggregator,
    INTENT_ACTIONS,
    MIN_FINALITY_LEVELS,
    PRIVACY_LEVELS,
    CHAIN_PREF_MODES,
)

REPO_ROOT = Path(__file__).resolve().parents[2]

# spec §4.1 field names, lowercased for cross-language comparison
# (rust uses snake_case min_nl_score; the spec writes min_NL_score)
SPEC_FIELDS = {
    "entity_id", "action", "value", "asset_in", "asset_out",
    "deadline", "max_total_gas", "min_finality", "min_nl_score",
    "chain_pref", "privacy", "btcp_version", "nonce",
}

LEGACY_ARGS = (b"\x01" * 32, b"\xAA" * 32, b"\xBB" * 32, 1000.0, 1, 1000)


def _py_intent_fields():
    return {f.name.lower() for f in dataclasses.fields(BITPIntent)}


class TestSpecFieldPresence:
    def test_python_covers_full_spec_41_field_set(self):
        fields = _py_intent_fields()
        missing = SPEC_FIELDS - fields
        assert not missing, f"BITPIntent missing spec §4.1 fields: {sorted(missing)}"

    def test_legacy_bitp_fields_survive(self):
        # the 6 legacy positional fields must keep their order
        names = [f.name for f in dataclasses.fields(BITPIntent)]
        assert names[:6] == [
            "entity_id", "asset_in", "asset_out",
            "magnitude", "chain_id", "deadline",
        ]

    def test_spec_enumerations_complete(self):
        assert INTENT_ACTIONS == {"SWAP", "TRANSFER", "LIQUIDITY", "STAKE", "BORROW"}
        assert MIN_FINALITY_LEVELS == {"FAST", "STANDARD", "SECURE"}
        assert PRIVACY_LEVELS == {"PUBLIC", "ZK_CREDENTIAL", "INVISIBLE"}
        assert CHAIN_PREF_MODES == {"OPTIMAL", "SINGLE_CHAIN"}


class TestSpecDefaults:
    def test_defaults_per_spec_41(self):
        intent = BITPIntent(*LEGACY_ARGS)
        assert intent.action == "SWAP"
        assert intent.value is None            # unset → legacy magnitude carries it
        assert intent.max_total_gas is None    # unset → unbounded
        assert intent.min_finality == "STANDARD"
        assert intent.min_nl_score == 300      # ×1000 → 0.30 default
        assert intent.chain_pref == "OPTIMAL"
        assert intent.privacy == "PUBLIC"
        assert intent.btcp_version == "1.0.0"
        assert intent.nonce == 0

    def test_min_nl_score_scaling(self):
        # uint16 scaled ×1000: 0.30 → 300, 0.45 → 450
        assert BITPIntent(*LEGACY_ARGS, min_nl_score=450).min_nl_score == 450


class TestLegacyConstruction:
    def test_positional_six_args_still_works(self):
        a = BITPIntent(*LEGACY_ARGS)
        assert (a.entity_id, a.asset_in, a.asset_out,
                a.magnitude, a.chain_id, a.deadline) == LEGACY_ARGS

    def test_keyword_legacy_construction(self):
        # invention_verification.py style (str assets, keyword args)
        intent = BITPIntent(
            entity_id=b"A", asset_in="X", asset_out="Y",
            magnitude=100, chain_id=1, deadline=999,
        )
        assert intent.entity_id == b"A"
        assert intent.asset_in == "X"
        assert intent.nonce == 0

    def test_dataclass_equality_unchanged(self):
        assert BITPIntent(*LEGACY_ARGS) == BITPIntent(*LEGACY_ARGS)
        assert BITPIntent(*LEGACY_ARGS) != BITPIntent(*LEGACY_ARGS, nonce=1)


class TestMatcherWithDefaultedIntents:
    def test_find_complement(self):
        a = BITPIntent(*LEGACY_ARGS)
        b = BITPIntent(b"\x02" * 32, b"\xBB" * 32, b"\xAA" * 32, 1000.0, 137, 1000)
        assert BITPMatcher().find_complement(a, [b]) is b

    def test_find_complement_same_chain_is_not_a_complement(self):
        a = BITPIntent(*LEGACY_ARGS)
        b = BITPIntent(b"\x02" * 32, b"\xBB" * 32, b"\xAA" * 32, 1000.0, 1, 1000)
        assert BITPMatcher().find_complement(a, [b]) is None

    def test_execute_paste(self):
        a = BITPIntent(*LEGACY_ARGS)
        b = BITPIntent(b"\x02" * 32, b"\xBB" * 32, b"\xAA" * 32, 1000.0, 137, 1000)
        paste = BITPMatcher().execute_paste(a, b)
        assert paste["cross_chain_movement"] == 0
        assert paste["bridge"] == "NONE"

    def test_netting_engine(self):
        a = BITPIntent(*LEGACY_ARGS)
        c = BITPIntent(b"\x03" * 32, b"\xBB" * 32, b"\xAA" * 32, 1000.0, 1, 1000)
        assert NettingEngine().find_netting_pair(a, [c]) is c

    def test_intent_aggregator_pool(self):
        intents = [
            BITPIntent(b"\x01" * 32, b"\xAA" * 32, b"\xBB" * 32, 100.0, 1, 1000),
            BITPIntent(b"\x02" * 32, b"\xAA" * 32, b"\xBB" * 32, 200.0, 1, 1000),
            BITPIntent(b"\x03" * 32, b"\xAA" * 32, b"\xBB" * 32, 150.0, 1, 1000),
        ]
        pool = IntentAggregator().find_aggregation_pool(intents)
        assert len(pool) == 3


class TestSpecFieldRoundTrip:
    def test_full_41_construction_round_trips(self):
        intent = BITPIntent(
            *LEGACY_ARGS,
            action="TRANSFER",
            value=10 ** 18,
            max_total_gas=50,
            min_finality="FAST",
            min_nl_score=450,
            chain_pref=[1, 137],
            privacy="ZK_CREDENTIAL",
            btcp_version="1.2.3",
            nonce=7,
        )
        assert intent.action == "TRANSFER"
        assert intent.value == 10 ** 18
        assert intent.max_total_gas == 50
        assert intent.min_finality == "FAST"
        assert intent.min_nl_score == 450
        assert intent.chain_pref == [1, 137]
        assert intent.privacy == "ZK_CREDENTIAL"
        assert intent.btcp_version == "1.2.3"
        assert intent.nonce == 7

    def test_chain_pref_accepts_all_spec_forms(self):
        assert BITPIntent(*LEGACY_ARGS, chain_pref="OPTIMAL").chain_pref == "OPTIMAL"
        assert BITPIntent(*LEGACY_ARGS, chain_pref="SINGLE_CHAIN").chain_pref == "SINGLE_CHAIN"
        assert BITPIntent(*LEGACY_ARGS, chain_pref=[1, 137, 900]).chain_pref == [1, 137, 900]

    def test_uint256_and_uint128_sized_values_round_trip(self):
        intent = BITPIntent(*LEGACY_ARGS, value=2 ** 256 - 1, max_total_gas=2 ** 128 - 1)
        assert intent.value == 2 ** 256 - 1
        assert intent.max_total_gas == 2 ** 128 - 1


class TestIntentHash:
    def test_hash_is_32_byte_sha3_256(self):
        digest = BITPIntent(*LEGACY_ARGS).hash()
        assert isinstance(digest, bytes) and len(digest) == 32

    def test_hash_deterministic(self):
        assert BITPIntent(*LEGACY_ARGS).hash() == BITPIntent(*LEGACY_ARGS).hash()

    def test_hash_covers_every_spec_41_field(self):
        base = BITPIntent(*LEGACY_ARGS)
        mutations = {
            "action": "STAKE",
            "value": 10 ** 18,
            "max_total_gas": 50,
            "min_finality": "SECURE",
            "min_nl_score": 450,
            "chain_pref": [1, 137],
            "privacy": "INVISIBLE",
            "btcp_version": "1.2.3",
            "nonce": 1,
        }
        for field_name, new_value in mutations.items():
            mutated = dataclasses.replace(base, **{field_name: new_value})
            assert mutated.hash() != base.hash(), (
                f"hash insensitive to §4.1 field {field_name}"
            )

    def test_hash_stable_for_str_and_bytes_asset_ids(self):
        # invention_verification.py passes str assets — hash must not crash
        intent = BITPIntent(entity_id=b"A", asset_in="X", asset_out="Y",
                            magnitude=100, chain_id=1, deadline=999)
        assert len(intent.hash()) == 32
        assert intent.hash() == BITPIntent(
            entity_id=b"A", asset_in="X", asset_out="Y",
            magnitude=100, chain_id=1, deadline=999).hash()


class TestRustParity:
    """Static cross-language parity: the Rust Intent / IntentConstraints
    field set (rust/src/types.rs) must cover the same §4.1 list. Rust is
    not compiled in this sandbox (no cargo), so this is a structural
    source check, not a runtime one."""

    @staticmethod
    def _rust_struct_block(source: str, struct_name: str) -> str:
        match = re.search(
            rf"pub struct {struct_name}\s*\{{(.*?)\n\}}", source, re.DOTALL
        )
        assert match, f"pub struct {struct_name} not found in rust/src/types.rs"
        return match.group(1)

    @classmethod
    def _rust_fields(cls, struct_name: str) -> set:
        source = (REPO_ROOT / "rust" / "src" / "types.rs").read_text()
        block = cls._rust_struct_block(source, struct_name)
        return {
            m.group(1).lower()
            for m in re.finditer(r"pub\s+([A-Za-z_][A-Za-z0-9_]*)\s*:", block)
        }

    def test_rust_intent_covers_spec_41_top_level(self):
        fields = self._rust_fields("Intent")
        # action → intent_type, value → amount_in (legacy names, same role)
        required = {"entity_id", "asset_in", "asset_out", "deadline",
                    "nonce", "btcp_version", "intent_type", "amount_in"}
        missing = required - fields
        assert not missing, f"rust Intent missing: {sorted(missing)}"

    def test_rust_constraints_cover_spec_41_constraints(self):
        fields = self._rust_fields("IntentConstraints")
        required = {"deadline", "max_total_gas", "min_finality",
                    "min_nl_score", "chain_pref", "privacy"}
        missing = required - fields
        assert not missing, f"rust IntentConstraints missing: {sorted(missing)}"

    def test_rust_keeps_legacy_constraint_fields(self):
        fields = self._rust_fields("IntentConstraints")
        assert {"max_slippage", "privacy_level",
                "allow_partial_fill", "allow_deferred"} <= fields

    def test_both_languages_cover_spec_41(self):
        rust = (self._rust_fields("Intent")
                | self._rust_fields("IntentConstraints"))
        # rust legacy aliases for the spec names
        rust |= {"action", "value"}
        py = _py_intent_fields() | {"magnitude", "chain_id"}
        py |= {"action", "value"}
        missing_py = SPEC_FIELDS - py
        missing_rust = SPEC_FIELDS - rust
        assert not missing_py, f"python side missing: {sorted(missing_py)}"
        assert not missing_rust, f"rust side missing: {sorted(missing_rust)}"
