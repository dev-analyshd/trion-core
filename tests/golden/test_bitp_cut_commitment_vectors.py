"""
TRION — Canonical §17 BITP CUT commitment corpus (follow-on-1 ruling)
=====================================================================

Verifies tests/golden/bitp_cut_commitment_vectors.json two ways:

  (a) PYTHON — a doc-exact rebuild of the canonical byte-format ruling
      (every segment via the canonical encoder policy: bytes → lowercase
      hex with no 0x prefix, None → "none", floats → repr, ints decimal,
      lists → bracketed comma-join) must reproduce the pinned preimage
      TEXT byte-for-byte, and ``AkashicClipboard._commitment`` must
      produce the pinned sha3-256 digest. Pinning the text (not just the
      digest) catches any encoding drift at the segment level — a
      different None form, 0x prefix, zero padding or float rendering
      changes the text before it changes the hash.
  (b) RUST — static source pins over rust/src/bitp_matcher.rs
      ``execute_cut`` / ``spec_fields_canonical`` / ``py_repr_f64``: the
      encoding calls that make the Rust text byte-identical with the
      Python one (hex::encode on entity_id/proof root — no to_hex 0x
      forms inside the commitment, py_repr_f64 for the magnitude, the
      bracketed allow-list). No cargo toolchain in this environment —
      the Rust verification is static; cargo build/test remains the
      documented unverified boundary (same pattern as
      tests/unit/test_adapters_intent_spec_fields.py).

Ruling source: docs/audit/canonical-sweep/FINAL_RELEASE_VERDICT.md
follow-on 1 (CUT commitment py↔rust byte-format divergence), closed here.
"""
import json
import re
from pathlib import Path

from core.btcp.modules import BITPIntent, AkashicClipboard, _canonical_intent_field

REPO = Path(__file__).resolve().parents[2]
VECTORS_PATH = REPO / "tests" / "golden" / "bitp_cut_commitment_vectors.json"
RUST_MATCHER = REPO / "rust" / "src" / "bitp_matcher.rs"

CORPUS = json.loads(VECTORS_PATH.read_text())
VECTORS = CORPUS["vectors"]


def _doc_exact_text(intent: BITPIntent) -> str:
    """Independent rebuild of the ruling's preimage layout.

    Field order (frozen): entity_id, asset_in, asset_out, magnitude,
    deadline, behavioral_proof_root (None → "0"*64), nonce, then the
    eight §4.1 fields as ONE colon-joined segment.
    """
    spec_block = ":".join([
        _canonical_intent_field(intent.action),
        _canonical_intent_field(intent.value),
        _canonical_intent_field(intent.max_total_gas),
        _canonical_intent_field(intent.min_finality),
        _canonical_intent_field(intent.min_nl_score),
        _canonical_intent_field(intent.chain_pref),
        _canonical_intent_field(intent.privacy),
        _canonical_intent_field(intent.btcp_version),
    ])
    return ":".join([
        _canonical_intent_field(intent.entity_id),
        _canonical_intent_field(intent.asset_in),
        _canonical_intent_field(intent.asset_out),
        _canonical_intent_field(intent.magnitude),
        _canonical_intent_field(intent.deadline),
        (_canonical_intent_field(intent.behavioral_proof_root)
         if intent.behavioral_proof_root is not None else "0" * 64),
        _canonical_intent_field(intent.nonce),
        spec_block,
    ])


def _intent_from_vector(vec) -> BITPIntent:
    kw = dict(vec["input"])
    for key in ("entity_id", "asset_in", "asset_out", "behavioral_proof_root"):
        if kw.get(key) is not None:
            kw[key] = bytes.fromhex(kw[key])
    return BITPIntent(**kw)


# ─── (a) Python: doc-exact text pin + digest pin ─────────────────────────────


def test_corpus_shape():
    assert len(VECTORS) >= 6, "the follow-on-1 corpus must keep its 6 coverage vectors"
    for vec in VECTORS:
        assert set(vec) >= {"id", "description", "input", "canonical_text",
                            "expected_sha3_256"}
        assert len(vec["expected_sha3_256"]) == 64


def test_doc_exact_text_and_digest():
    clipboard = AkashicClipboard()
    for vec in VECTORS:
        intent = _intent_from_vector(vec)
        text = _doc_exact_text(intent)
        assert text == vec["canonical_text"], (
            f"{vec['id']}: preimage text drifted from the canonical ruling"
        )
        assert clipboard._commitment(intent).hex() == vec["expected_sha3_256"], (
            f"{vec['id']}: commitment digest drifted from the pinned corpus"
        )


def test_none_forms_and_prefix_rules_are_canonical():
    """The four named divergences stay closed: no 0x prefixes, no "None"
    (capital) forms, no zero padding of short ids, allow-lists bracketed."""
    v1 = next(v for v in VECTORS if v["id"] == "cut_v1_defaults_32byte")
    # None value/max_total_gas → "none" (lowercase), not "None"
    assert ":none:none:" in v1["canonical_text"]
    assert ":None:" not in v1["canonical_text"]
    # no 0x prefix anywhere in the hex segments
    assert "0x" not in v1["canonical_text"]
    # short ids keep their variable-length hex (no zero padding)
    v6 = next(v for v in VECTORS if v["id"] == "cut_v6_short_ids_fractional")
    assert v6["canonical_text"].startswith("0101010101010101:cdcdcdcdcdcdcdcd:")
    # allow-list is bracketed
    v4 = next(v for v in VECTORS if v["id"] == "cut_v4_chain_pref_allowed")
    assert v4["canonical_text"].endswith(":SWAP:none:none:STANDARD:300:[1,137]:"
                                         "PUBLIC:1.0.0")
    # integral magnitude keeps the python-repr ".0"
    assert ":100.0:" in v1["canonical_text"]


def test_proof_root_and_nonce_change_the_commitment():
    """§17 binding: a different proof root or nonce is a different
    commitment (the uniqueness property the corpus must keep exercising)."""
    base = dict(entity_id=b"\xab" * 32, asset_in=b"\xaa" * 20,
                asset_out=b"\xbb" * 20, magnitude=100.0, chain_id=1,
                deadline=2000)
    clipboard = AkashicClipboard()
    c_base = clipboard._commitment(BITPIntent(**base))
    c_root = clipboard._commitment(BITPIntent(
        **base, behavioral_proof_root=b"\x11" * 32))
    c_nonce = clipboard._commitment(BITPIntent(**base, nonce=7))
    assert len({c_base, c_root, c_nonce}) == 3


# ─── (b) Rust: static source pins (cargo-blocked, honestly labeled) ──────────


def _cut_body() -> str:
    source = RUST_MATCHER.read_text()
    match = re.search(r"pub fn execute_cut.*?\n    \}", source, re.DOTALL)
    assert match, "execute_cut not found in rust/src/bitp_matcher.rs"
    return match.group(0)


def test_rust_cut_uses_prefix_free_hex():
    """entity_id / behavioral_proof_root go through hex::encode (no 0x
    prefix, zero root == "0"*64 matching the python None fallback) — the
    H256::to_hex() 0x-forms must not appear inside the commitment."""
    body = _cut_body()
    assert "hex::encode(intent.entity_id.0)" in body
    assert "hex::encode(intent.behavioral_proof_root.0)" in body
    assert ".to_hex()" not in body, (
        "execute_cut regressed to a 0x-prefixed hex form"
    )


def test_rust_cut_uses_py_repr_float():
    body = _cut_body()
    assert "py_repr_f64(intent.magnitude)" in body, (
        "execute_cut must render the magnitude with the python-repr rule "
        "(integral floats keep the .0)"
    )


def test_rust_cut_binds_spec_fields():
    body = _cut_body()
    assert "spec_fields_canonical()" in body


def test_rust_spec_fields_canonical_rules():
    source = RUST_MATCHER.read_text()
    match = re.search(
        r"fn spec_fields_canonical.*?\n    \}", source, re.DOTALL)
    assert match, "spec_fields_canonical not found"
    body = match.group(0)
    # None → "none" (both arms)
    assert body.count('"none"') >= 2
    # allow-list → bracketed "[...]" (no ALLOWED prefix — python list rule)
    assert '"[{}]"' in body
    assert "ALLOWED[" not in body


def test_rust_py_repr_f64_helper_exists_with_dot_zero_arm():
    source = RUST_MATCHER.read_text()
    match = re.search(
        r"fn py_repr_f64.*?\n\}", source, re.DOTALL)
    assert match, "py_repr_f64 helper not found in bitp_matcher.rs"
    body = match.group(0)
    assert "{:.1}" in body, (
        "py_repr_f64 must append the .0 for finite integral values"
    )
    assert "1e16" in body, "the documented float-domain boundary guard"
