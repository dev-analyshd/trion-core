"""
BTCP Master Spec §4.1 — adapters BTCPIntent field set (final gap #8 leg)
=========================================================================
The spec's Intent object (spec/BTCP_SPEC.txt lines 272-292) defines 15
fields across the top level and the constraints block. Task 21-b aligned
``core/btcp/modules.py`` ``BITPIntent`` and ``rust/src/types.rs``
``Intent``/``IntentConstraints``; this suite pins the last two
representations:

1. the orchestrator/crossvm ``BTCPIntent`` (adapters/__init__.py) carries
   the full §4.1 field set with the spec defaults,
2. legacy positional (12 transport fields) and keyword construction still
   work (backwards compatibility — every construction site in the repo is
   keyword-based, all fields defaulted),
3. ``to_dict()`` round-trips through ``BTCPIntent(**row)`` — the
   orchestrator persistence path (core/btcp/orchestrator.py:212) rebuilds
   intents exactly this way,
4. ``BTCPIntent.hash()`` is a deterministic 32-byte SHA3-256 that covers
   every §4.1 field (append-only policy, mirroring BITPIntent.hash() in
   core/btcp/modules.py and Intent::hash() in rust/src/types.rs),
5. the Rust clipboard entry ``BITPIntentData`` (rust/src/bitp_matcher.rs,
   the §17 CUT/MATCH/PASTE object) statically covers the same §4.1 list
   (no cargo in this sandbox — structural source check).
"""
import dataclasses
import re
from pathlib import Path

from adapters import BTCPIntent
from core.btcp.modules import BITPIntent

REPO_ROOT = Path(__file__).resolve().parents[2]


# spec §4.1 field names, lowercased for cross-language comparison
# (rust uses snake_case min_nl_score; the spec writes min_NL_score)
SPEC_FIELDS = {
    "entity_id", "action", "value", "asset_in", "asset_out",
    "deadline", "max_total_gas", "min_finality", "min_nl_score",
    "chain_pref", "privacy", "btcp_version", "nonce",
}

# The adapters intent is the orchestrator/crossvm TRANSPORT object: it
# identifies the intent by source/dest ADDRESS + intent_id, not by the
# BEO entity/asset triple (that is the modules BITPIntent / rust Intent
# representation). The §4.1 fields meaningful on this representation are
# everything except the BEO identity triple:
SPEC_FIELDS_ON_ADAPTERS = SPEC_FIELDS - {"entity_id", "asset_in", "asset_out"}

# legacy transport fields, positional order frozen
LEGACY_TRANSPORT_FIELDS = [
    "intent_id", "source_chain", "dest_chain", "source_address",
    "dest_address", "amount", "asset", "intent_type",
    "deadline", "nonce", "metadata", "timestamp",
]

# legacy positional args (orchestrator/adversarial-style intent)
LEGACY_ARGS = (
    "intent_x", 1, 137, "0x" + "ab" * 20, "0x" + "cd" * 20,
    10 ** 18, "ETH", "SWAP", 999, 5,
)


def _adapter_fields():
    return {f.name.lower() for f in dataclasses.fields(BTCPIntent)}


class TestSpecFieldPresence:
    def test_adapters_intent_covers_full_spec_41_field_set(self):
        fields = _adapter_fields()
        missing = SPEC_FIELDS_ON_ADAPTERS - fields
        assert not missing, f"adapters BTCPIntent missing spec §4.1 fields: {sorted(missing)}"

    def test_adapter_identity_is_the_transport_triple(self):
        # the BEO-identity §4.1 fields (entity_id, asset_in, asset_out) are
        # intentionally NOT on this representation — the transport intent
        # carries source/dest address + intent_id instead (orchestrator
        # and VM adapters route by address); documented in the class
        # docstring. This pins the honest difference.
        fields = _adapter_fields()
        assert not ({"entity_id", "asset_in", "asset_out"} & fields)
        assert {"source_address", "dest_address", "intent_id"} <= fields

    def test_legacy_transport_fields_survive_in_order(self):
        names = [f.name for f in dataclasses.fields(BTCPIntent)]
        assert names[:12] == LEGACY_TRANSPORT_FIELDS

    def test_spec_fields_appended_after_legacy_block(self):
        # the §4.1 fields must come after the legacy transport block so
        # positional construction semantics are frozen
        names = [f.name for f in dataclasses.fields(BTCPIntent)]
        assert names[12:] == [
            "action", "value", "max_total_gas", "min_finality",
            "min_nl_score", "chain_pref", "privacy", "btcp_version",
        ]

    def test_field_count_is_legacy_plus_spec(self):
        # 12 legacy transport fields + 8 new §4.1 fields (deadline and
        # nonce were already legacy fields here — not re-added)
        assert len(dataclasses.fields(BTCPIntent)) == 20


class TestSpecDefaults:
    def test_defaults_per_spec_41(self):
        intent = BTCPIntent()
        assert intent.action == "SWAP"
        assert intent.value is None            # unset → legacy amount carries it
        assert intent.max_total_gas is None    # unset → unbounded
        assert intent.min_finality == "STANDARD"
        assert intent.min_nl_score == 300      # ×1000 → 0.30 default
        assert intent.chain_pref == "OPTIMAL"
        assert intent.privacy == "PUBLIC"
        assert intent.btcp_version == "1.0.0"
        assert intent.nonce == 0               # already a legacy field, spec default
        assert intent.deadline == 0

    def test_legacy_defaults_unchanged(self):
        intent = BTCPIntent()
        assert intent.intent_id == ""
        assert intent.intent_type == "TRANSFER"
        assert intent.amount == 0
        assert intent.metadata == {}


class TestLegacyConstruction:
    def test_positional_twelve_args_still_works(self):
        a = BTCPIntent(*LEGACY_ARGS)
        assert a.intent_id == "intent_x"
        assert a.source_chain == 1 and a.dest_chain == 137
        assert a.amount == 10 ** 18
        assert a.intent_type == "SWAP"
        assert a.deadline == 999 and a.nonce == 5

    def test_keyword_orchestrator_construction(self):
        # core/btcp/orchestrator.py:869 style
        intent = BTCPIntent(
            intent_id="btcp_deadbeef",
            source_chain=1,
            dest_chain=42161,
            source_address="0x1F98431c8aD98523631AE4a59f267346ea31F984",
            dest_address="0x87870Bca3F3fD6335C3F4ce8392D69350B4fA4E2",
            amount=int(1.5 * 10 ** 18),
            asset="ETH",
            intent_type="SWAP",
            deadline=3600,
            nonce=42,
        )
        assert intent.action == "SWAP"  # spec default alongside legacy type
        assert intent.btcp_version == "1.0.0"

    def test_dataclass_equality_unchanged(self):
        # timestamp is default_factory=time.time — fresh constructions are
        # never equal (pre-existing semantics, unchanged by the §4.1
        # extension). With a fixed timestamp the §4.1 fields participate.
        a = dataclasses.replace(BTCPIntent(*LEGACY_ARGS), timestamp=1.0)
        b = dataclasses.replace(BTCPIntent(*LEGACY_ARGS), timestamp=1.0)
        assert a == b
        assert a != dataclasses.replace(b, nonce=6)


class TestDictRoundTrip:
    def test_to_dict_contains_spec_41_fields(self):
        d = BTCPIntent(*LEGACY_ARGS).to_dict()
        for name in ("action", "value", "max_total_gas", "min_finality",
                     "min_nl_score", "chain_pref", "privacy", "btcp_version"):
            assert name in d, f"to_dict missing §4.1 field {name}"

    def test_intent_row_round_trips_through_constructor(self):
        # core/btcp/orchestrator.py:212 rebuilds persisted intents as
        # BTCPIntent(**intent_row) — the dict from to_dict() must be a
        # valid constructor payload (old rows without §4.1 keys rely on
        # the defaults and keep working)
        intent = BTCPIntent(
            *LEGACY_ARGS,
            action="TRANSFER",
            value=10 ** 18,
            max_total_gas=50,
            min_finality="FAST",
            min_nl_score=450,
            chain_pref=[1, 137],
            privacy="ZK_CREDENTIAL",
            btcp_version="1.2.3",
        )
        rebuilt = BTCPIntent(**intent.to_dict())
        assert rebuilt == intent

    def test_legacy_row_without_spec_keys_still_rebuilds(self):
        # rows persisted before the §4.1 extension carry only the legacy
        # keys — defaults must fill the rest
        legacy_row = BTCPIntent(*LEGACY_ARGS).to_dict()
        legacy_row.pop("timestamp")  # not part of the persisted shape check
        row = {k: v for k, v in legacy_row.items() if k in LEGACY_TRANSPORT_FIELDS}
        rebuilt = BTCPIntent(**row)
        assert rebuilt.action == "SWAP"
        assert rebuilt.min_nl_score == 300


class TestSpecFieldRoundTrip:
    def test_full_41_construction_round_trips(self):
        # nonce is a legacy positional field here — set it through the
        # legacy slot, not a §4.1 keyword
        intent = BTCPIntent(
            *LEGACY_ARGS[:9],           # through deadline
            7,                          # nonce (legacy slot 10)
            action="LIQUIDITY",
            value=2 ** 256 - 1,
            max_total_gas=2 ** 128 - 1,
            min_finality="SECURE",
            min_nl_score=450,
            chain_pref="SINGLE_CHAIN",
            privacy="INVISIBLE",
            btcp_version="1.2.3",
        )
        assert intent.action == "LIQUIDITY"
        assert intent.value == 2 ** 256 - 1
        assert intent.max_total_gas == 2 ** 128 - 1
        assert intent.min_finality == "SECURE"
        assert intent.min_nl_score == 450
        assert intent.chain_pref == "SINGLE_CHAIN"
        assert intent.privacy == "INVISIBLE"
        assert intent.btcp_version == "1.2.3"
        assert intent.nonce == 7

    def test_chain_pref_accepts_all_spec_forms(self):
        assert BTCPIntent(*LEGACY_ARGS, chain_pref="OPTIMAL").chain_pref == "OPTIMAL"
        assert BTCPIntent(*LEGACY_ARGS, chain_pref="SINGLE_CHAIN").chain_pref == "SINGLE_CHAIN"
        assert BTCPIntent(*LEGACY_ARGS, chain_pref=[1, 137, 900]).chain_pref == [1, 137, 900]


class TestIntentHash:
    def test_hash_is_32_byte_sha3_256(self):
        digest = BTCPIntent(*LEGACY_ARGS).hash()
        assert isinstance(digest, bytes) and len(digest) == 32

    def test_hash_deterministic(self):
        assert BTCPIntent(*LEGACY_ARGS).hash() == BTCPIntent(*LEGACY_ARGS).hash()

    def test_hash_covers_every_spec_41_field(self):
        base = BTCPIntent(*LEGACY_ARGS)
        mutations = {
            "action": "STAKE",
            "value": 10 ** 18,
            "max_total_gas": 50,
            "min_finality": "SECURE",
            "min_nl_score": 450,
            "chain_pref": [1, 137],
            "privacy": "INVISIBLE",
            "btcp_version": "1.2.3",
            "nonce": 6,           # legacy field, also spec §4.1
            "intent_type": "TRANSFER",
            "amount": 42,
        }
        for field_name, new_value in mutations.items():
            mutated = dataclasses.replace(base, **{field_name: new_value})
            assert mutated.hash() != base.hash(), (
                f"hash insensitive to field {field_name}"
            )

    def test_hash_policy_mirrors_modules_bitp_intent(self):
        # append-only policy: legacy field text first, §4.1 fields appended
        # — both python representations define the extended format fresh
        # (no vectors were pinned before), and both are 32-byte sha3-256
        modules_intent = BITPIntent(b"\x01" * 32, b"\xAA" * 32, b"\xBB" * 32, 1000.0, 1, 1000)
        assert len(modules_intent.hash()) == 32 == len(BTCPIntent(*LEGACY_ARGS).hash())


class TestRustClipboardParity:
    """Static cross-language parity: the Rust clipboard entry
    BITPIntentData (rust/src/bitp_matcher.rs — the §17 CUT/MATCH/PASTE
    object that adds behavioral_proof_root to the intent data) must cover
    the same §4.1 list. Rust is not compiled in this sandbox (no cargo),
    so this is a structural source check, not a runtime one."""

    @staticmethod
    def _clipboard_struct_fields() -> set:
        source = (REPO_ROOT / "rust" / "src" / "bitp_matcher.rs").read_text()
        match = re.search(
            r"pub struct BITPIntentData\s*\{(.*?)\n\}", source, re.DOTALL
        )
        assert match, "pub struct BITPIntentData not found in rust/src/bitp_matcher.rs"
        return {
            m.group(1).lower()
            for m in re.finditer(r"pub\s+([A-Za-z_][A-Za-z0-9_]*)\s*:", match.group(1))
        }

    def test_rust_clipboard_entry_covers_spec_41(self):
        fields = self._clipboard_struct_fields()
        # action/value are carried directly; magnitude/chain_id are the
        # legacy magnitude/chain carriers (same roles as the python twins)
        required = SPEC_FIELDS | {"magnitude", "chain_id", "behavioral_proof_root"}
        missing = required - fields
        assert not missing, f"rust BITPIntentData missing: {sorted(missing)}"

    def test_rust_clipboard_keeps_17_proof_binding(self):
        fields = self._clipboard_struct_fields()
        assert {"behavioral_proof_root", "nonce"} <= fields

    def test_cut_commitment_binds_the_spec_fields(self):
        # the §17 commitment must hash the §4.1 field set too (append-only
        # extension) — the spec_fields_canonical encoder must be called
        # from execute_cut
        source = (REPO_ROOT / "rust" / "src" / "bitp_matcher.rs").read_text()
        cut = re.search(
            r"pub fn execute_cut.*?\n    \}", source, re.DOTALL
        )
        assert cut, "execute_cut not found"
        assert "spec_fields_canonical" in cut.group(0), (
            "execute_cut no longer binds the §4.1 field set into the commitment"
        )


class TestCrossRepresentationParity:
    def test_modules_and_adapters_intents_cover_the_same_spec_set(self):
        # modules BITPIntent carries the BEO identity triple; adapters
        # BTCPIntent is the address-based transport intent — each must
        # cover the §4.1 fields meaningful to its representation
        modules_fields = {f.name.lower() for f in dataclasses.fields(BITPIntent)}
        adapters_fields = _adapter_fields()
        missing_modules = SPEC_FIELDS - modules_fields
        missing_adapters = SPEC_FIELDS_ON_ADAPTERS - adapters_fields
        assert not missing_modules, f"modules BITPIntent missing: {sorted(missing_modules)}"
        assert not missing_adapters, f"adapters BTCPIntent missing: {sorted(missing_adapters)}"

    def test_default_values_match_across_representations(self):
        # the py twins (modules BITPIntent / adapters BTCPIntent) carry
        # identical §4.1 defaults so the orchestrator, matcher and router
        # agree on what an unspecified intent means (nonce: modules default
        # 0; adapters legacy default is also 0 — compare against the
        # no-arg construction, LEGACY_ARGS sets it to 5)
        m = BITPIntent(b"\x01" * 32, b"\xAA" * 32, b"\xBB" * 32, 1000.0, 1, 1000)
        a = BTCPIntent()
        assert (m.action, m.min_finality, m.min_nl_score,
                m.chain_pref, m.privacy, m.btcp_version, m.nonce) == (
               a.action, a.min_finality, a.min_nl_score,
               a.chain_pref, a.privacy, a.btcp_version, a.nonce)
        assert m.value is None and a.value is None
        assert m.max_total_gas is None and a.max_total_gas is None
