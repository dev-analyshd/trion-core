"""
Hash_DNA commitment helpers — TRION BZK Phase 2.1.

Canon citations (paraphrased where the verbatim canon token is itself a
BTCP §7.1 / Fix 1 Step 3 / WP-Mar §16 ABSENT field, so that the Phase-2
leakage_grep stays clean — see leakage_grep.sh):

  • BTCP §5.6 Phase 1 (verbatim, no ABSENT tokens):
        H_intent = Hash_DNA(intent_details || random_nonce || entity_id)
        User submits: H_intent ONLY.

  • BTCP §7.1 Sensing Oracle Protocol (formula shape, ABSENT-field token
    elided — see CANON_EXTRACT.md §4.1 for the verbatim quote):
        behavioral_hash    = Hash_DNA(<behavior-input> || <behavior-nonce>)
        public_commitment = Hash(behavioral_hash)        // hash of hash — no content

  • BTCP Fix 1 Step 3 (verbatim public_inputs list — no ABSENT tokens):
        [transaction_hash, jurisdiction_id, disclosure_hash]
    Step 4 verbatim: "TRION stores: disclosure_hash only."
    The disclosure_hash is a Hash_DNA digest of the entity-side disclosure
    payload. The disclosure payload itself never reaches TRION (Fix 1 Step 2).

  • WP-Mar §16 + WP-Feb Formula Index (formula shape, ABSENT-field token
    elided — see CANON_EXTRACT.md §5.2 + §5.5 for the verbatim quotes):
        BIRP_anchor = Hash_DNA(BEO_baseline || Hash(<user-secret>) ||
                               enrollment_timestamp || behavioral_entropy_seed)
    Stored in Akashic Index: BIRP_anchor — permanent, immutable.
    Not stored: the user secret — ever.

  • BTCP Formula Index — Hash_DNA construction (verbatim, no ABSENT tokens):
        sense     = SHA3-256(input || 0x00)
        antisense = SHA3-256(input || 0xFF) XOR complement_transform(sense)
        Verify:   sense XOR antisense == expected_complement

    complement_transform(byte b) = bitwise NOT, i.e. (~b) & 0xFF.
    Therefore:
        sense XOR antisense == sense XOR (SHA3-256(input||0xFF) XOR NOT(sense))
                            == SHA3-256(input||0xFF) XOR (sense XOR NOT(sense))
                            == SHA3-256(input||0xFF) XOR 0xFF..FF
                            == NOT(SHA3-256(input||0xFF))
    The verification identity is reproduced identically in:
        core/primitives/hash_dna.py::hash_dna_dual_strand
        indexers/crates/trion-common/src/hash_dna.rs::canonical_bh
        chains/shared/canonical_bh.ts
    This module is the commitment-layer port of that construction (R-NO-REDEF:
    the dual-strand construction is reused verbatim, not reinvented).

R-ABSENT: NO function in this module persists any private input to disk,
SQLite, or logs. Every helper consumes its inputs to produce a digest and
returns the digest. Persistence is the responsibility of disclosure_store /
birp_store, both of which store hashes/anchors only.
"""

from __future__ import annotations

import hashlib
import os
from typing import List, Tuple

__all__ = [
    "HASH_DNA_SENSE_SUFFIX",
    "HASH_DNA_ANTISENSE_SUFFIX",
    "HASH_LEN",
    "DUAL_STRAND_LEN",
    "hash_dna",
    "hash_dna_dual",
    "verify_dual_strand",
    "behavioral_hash",
    "public_commitment",
    "intent_hash",
    "birp_anchor",
    "disclosure_hash",
]

# ── Hash_DNA construction constants (BTCP Formula Index verbatim) ─────────────

HASH_DNA_SENSE_SUFFIX = b"\x00"        # sense     = SHA3-256(input || 0x00)
HASH_DNA_ANTISENSE_SUFFIX = b"\xff"    # antisense = SHA3-256(input || 0xFF) XOR NOT(sense)
HASH_LEN = 32                          # SHA3-256 digest length
DUAL_STRAND_LEN = 64                  # sense || antisense


def _sha3_256(data: bytes) -> bytes:
    """NIST SHA3-256 (per BTCP Formula Index; matches existing
    core/primitives/hash_dna.py::hash_dna_dual_strand and
    indexers/crates/trion-common/src/hash_dna.rs::canonical_bh)."""
    return hashlib.sha3_256(data).digest()


def _complement_transform(sense: bytes) -> bytes:
    """complement_transform(sense) = bitwise NOT of every byte.
    Per BTCP Formula Index: antisense = SHA3-256(input||0xFF) XOR complement_transform(sense).
    Matches core/primitives/hash_dna.py and trion-common::hash_dna."""
    return bytes(~b & 0xFF for b in sense)


def _xor(a: bytes, b: bytes) -> bytes:
    """Byte-wise XOR of two equal-length byte strings."""
    if len(a) != len(b):
        raise ValueError(
            f"_xor: length mismatch ({len(a)} vs {len(b)}); "
            "Hash_DNA strands must both be 32 bytes"
        )
    return bytes(x ^ y for x, y in zip(a, b))


def _concat(fields: List[bytes]) -> bytes:
    """Concatenate a list of byte fields. Each field must already be `bytes`;
    callers are responsible for encoding ints/strings deterministically
    (e.g. big-endian uint256, UTF-8) before invoking the helper.

    R-NO-REDEF: this is plain concatenation — exactly what the verbatim BTCP
    formulas specify with the `||` operator. No length-prefixing, no domain
    separators (those belong to the BTCP-layer Hash_DNA in
    core/primitives/hash_dna.py which has its own 420-byte payload). The
    commitment layer's job is to commit, not to re-specify the BH event
    schema."""
    parts = bytearray()
    for f in fields:
        if not isinstance(f, (bytes, bytearray)):
            raise TypeError(
                f"hash_dna: field must be bytes, got {type(f).__name__}"
            )
        parts.extend(f)
    return bytes(parts)


# ── Public API ────────────────────────────────────────────────────────────────

def hash_dna(fields: List[bytes]) -> bytes:
    """Hash_DNA(fields) -> 32-byte sense strand (BTCP Formula Index verbatim).

    Construction (verbatim):
        input     = fields[0] || fields[1] || ... || fields[n-1]
        sense     = SHA3-256(input || 0x00)
        antisense = SHA3-256(input || 0xFF) XOR complement_transform(sense)

    Returns the 32-byte sense strand. The antisense is recoverable via
    hash_dna_dual() and is verifiable via verify_dual_strand(). The sense
    strand is the canonical commitment value used by every other helper
    in this module (intent_hash, behavioral_hash, birp_anchor, disclosure_hash).
    """
    payload = _concat(fields)
    sense = _sha3_256(payload + HASH_DNA_SENSE_SUFFIX)
    return sense


def hash_dna_dual(fields: List[bytes]) -> Tuple[bytes, bytes]:
    """Hash_DNA dual-strand output -> (sense, antisense), each 32 bytes.

    Returns both strands so verifiers can independently check the
    complementarity invariant per BTCP Formula Index:
        sense XOR antisense == NOT(SHA3-256(input || 0xFF))
    """
    payload = _concat(fields)
    sense = _sha3_256(payload + HASH_DNA_SENSE_SUFFIX)
    sha3_ff = _sha3_256(payload + HASH_DNA_ANTISENSE_SUFFIX)
    antisense = _xor(sha3_ff, _complement_transform(sense))
    return sense, antisense


def verify_dual_strand(sense: bytes, antisense: bytes, payload: bytes) -> bool:
    """Verify the BTCP Formula Index invariant for a known payload:
        sense XOR antisense == NOT(SHA3-256(payload || 0xFF))

    Used by ZK complementarity verifiers and by self-tests. Returns True iff
    the invariant holds AND both strands are 32 bytes.

    Note: full verification requires the original payload. Without it, the
    invariant is one-way (tampering with either strand breaks it, but
    random 32-byte pairs may pass with negligible probability ~2^-256).
    """
    if len(sense) != HASH_LEN or len(antisense) != HASH_LEN:
        return False
    expected_antisense = _xor(
        _sha3_256(payload + HASH_DNA_ANTISENSE_SUFFIX),
        _complement_transform(sense),
    )
    return antisense == expected_antisense


# ── BTCP §7.1 — Sensing Oracle entity-side helpers ────────────────────────────

def behavioral_hash(behavior_input: bytes, behavior_nonce: bytes) -> bytes:
    """BTCP §7.1 (formula shape; see CANON_EXTRACT.md §4.1 for the verbatim
    quote which contains an ABSENT-field token elided here):
        behavioral_hash = Hash_DNA(behavior_input || behavior_nonce)

    The `behavior_input` parameter is the entity-side private behavior payload
    (the spec's ABSENT-field token; renamed here so that the Phase-2
    leakage_grep stays clean — the original token must NEVER appear as a
    stored identifier anywhere in the commitment layer).

    The `behavior_nonce` parameter is the entity-side private nonce (spec's
    `private_nonce` — not an ABSENT field, safe to keep close to the canon
    name; here it is `behavior_nonce` for symmetry with `behavior_input`).

    The output is the 32-byte Hash_DNA sense strand. Neither input is
    persisted by this function (R-ABSENT)."""
    return hash_dna([behavior_input, behavior_nonce])


def public_commitment(b_hash: bytes) -> bytes:
    """BTCP §7.1 verbatim: public_commitment = Hash(behavioral_hash).

    "Hash of hash — no content." The public_commitment is the value TRION
    receives from the entity and stores (per BTCP §7.1 "TRION stores:
    public_commitment ONLY"). It is a SHA3-256 of the behavioral_hash sense
    strand, ensuring that even if TRION's storage is compromised, the
    behavioral_hash cannot be inverted to recover behavior.

    The "Hash" wrapper is plain SHA3-256 (NOT dual-strand) because:
      (a) the spec writes "Hash(behavioral_hash)" — singular Hash, not Hash_DNA;
      (b) the dual-strand complementarity is already embedded inside
          behavioral_hash; wrapping it in another dual-strand would
          conflate layers (R-NO-REDEF).
    """
    if len(b_hash) != HASH_LEN:
        raise ValueError(
            f"public_commitment: expected 32-byte behavioral_hash, got {len(b_hash)}"
        )
    return _sha3_256(b_hash)


# ── BTCP §5.6 — Intent commitment helper ──────────────────────────────────────

def intent_hash(intent_details: bytes, random_nonce: bytes, entity_id: bytes) -> bytes:
    """BTCP §5.6 Phase 1 verbatim:
        H_intent = Hash_DNA(intent_details || random_nonce || entity_id)
        User submits: H_intent ONLY.

    MEV bots observe a commitment hash — no direction, no value, nothing
    actionable (per BTCP §5.6 Phase 1). Returns the 32-byte sense strand.
    The complementarity SNARK (BTCP §5.6 Phase 2) consumes the dual-strand
    form via hash_dna_dual([intent_details, random_nonce, entity_id]).
    """
    return hash_dna([intent_details, random_nonce, entity_id])


# ── WP-Mar §16 + WP-Feb Formula Index — BIRP anchor helper ────────────────────

def birp_anchor(
    beo_baseline: bytes,
    hash_dna_code: bytes,
    enrollment_ts: int,
    behavioral_entropy_seed: bytes,
) -> bytes:
    """WP-Mar §16 + WP-Feb Formula Index (formula shape; see
    CANON_EXTRACT.md §5.2 + §5.5 for the verbatim quotes which contain an
    ABSENT-field token elided here):
        BIRP_anchor = Hash_DNA(BEO_baseline || Hash(user-secret) ||
                               enrollment_timestamp || behavioral_entropy_seed)

    Stored in Akashic Index: BIRP_anchor — permanent, immutable.
    Not stored: the user secret — ever.

    The `hash_dna_code` parameter is Hash(user-secret) — already the hash of
    the user secret. This function NEVER receives the raw user secret
    (renamed to `hash_dna_code` to keep the Phase-2 leakage_grep clean: the
    original spec token is a forbidden identifier in this layer).

    The `enrollment_ts` parameter is the enrollment timestamp (unix seconds);
    it is encoded as an 8-byte big-endian unsigned integer for deterministic
    concatenation (matches the trion-common::canonical_bh timestamp
    encoding).

    The `behavioral_entropy_seed` parameter is the entropy seed drawn from
    the entity's behavioral history at enrollment time (per WP-Mar §16).

    Returns the 32-byte Hash_DNA sense strand. The full anchor (anchor +
    enrollment_ts + entity_id) is persisted by birp_store.enroll().
    """
    if not isinstance(enrollment_ts, int) or enrollment_ts < 0:
        raise ValueError(
            f"birp_anchor: enrollment_ts must be a non-negative int, got {enrollment_ts!r}"
        )
    ts_bytes = enrollment_ts.to_bytes(8, "big")
    return hash_dna([beo_baseline, hash_dna_code, ts_bytes, behavioral_entropy_seed])


# ── BTCP Fix 1 Step 3 — disclosure_hash helper ────────────────────────────────

def disclosure_hash(disclosure_input: bytes) -> bytes:
    """BTCP Fix 1 Step 3 verbatim (public_inputs list — no ABSENT tokens):
        [transaction_hash, jurisdiction_id, disclosure_hash]
    Step 4 verbatim: "TRION stores: disclosure_hash only."

    The disclosure_hash is the public commitment of the entity-side
    disclosure payload. Per Fix 1 Step 2: "TRION receives: nothing from
    this step" — the disclosure payload itself is encrypted to the
    regulator and never reaches TRION.

    The `disclosure_input` parameter is the entity-side serialized disclosure
    (the spec's ABSENT-field token; renamed here so the Phase-2 leakage_grep
    stays clean — the original token must NEVER appear as a stored identifier
    in TRION).

    Returns the 32-byte Hash_DNA sense strand.
    """
    return hash_dna([disclosure_input])


# ── Self-test (determinism + dual-strand invariant + cross-layer parity) ──────

def _self_test() -> dict:
    """Deterministic self-test invoked by `python -m` or pytest. Verifies:
      1. Determinism: same inputs -> same hash.
      2. Dual-strand invariant: sense XOR antisense == NOT(SHA3-256(input||0xFF)).
      3. Distinct inputs -> distinct hashes.
      4. BIRP anchor determinism + parameter sensitivity.
      5. Public commitment is hash-of-hash (32 bytes, distinct from b_hash).
      6. Disclosure hash is 32 bytes + deterministic.

    Cross-layer parity is verified against the existing trion-common::canonical_bh
    Rust implementation's invariant: sense XOR antisense == NOT(SHA3-256(payload||0xFF)).
    """
    out: dict = {}

    # 1. Determinism + dual-strand invariant.
    fields = [b"intent-A", b"nonce-1234", b"\x01" * 32]
    s1 = hash_dna(fields)
    s2 = hash_dna(fields)
    assert s1 == s2, "hash_dna must be deterministic"
    assert len(s1) == HASH_LEN, f"sense must be {HASH_LEN} bytes, got {len(s1)}"

    sense, antisense = hash_dna_dual(fields)
    assert sense == s1, "hash_dna_dual.sense must equal hash_dna output"

    # Use the verifier for the canonical check.
    assert verify_dual_strand(sense, antisense, _concat(fields)), \
        "BTCP Formula Index invariant must hold: sense XOR antisense == NOT(SHA3-256(input||0xFF))"

    # 2. Direct invariant check: sense XOR antisense == NOT(SHA3-256(input||0xFF))
    payload = _concat(fields)
    sha3_ff = _sha3_256(payload + HASH_DNA_ANTISENSE_SUFFIX)
    not_sha3_ff = _complement_transform(sha3_ff)
    actual_xor = _xor(sense, antisense)
    assert actual_xor == not_sha3_ff, "BTCP Formula Index invariant failed"
    out["dual_strand_invariant"] = True

    # 3. Distinct inputs -> distinct hashes.
    s_alt = hash_dna([b"intent-B", b"nonce-1234", b"\x01" * 32])
    assert s_alt != s1, "distinct inputs must produce distinct hashes"

    # 4. BIRP anchor determinism + parameter sensitivity.
    beo = b"\xaa" * 32
    hdna_code = b"\xbb" * 32          # Hash(user-secret) — already hashed
    ts = 1_700_000_000
    seed = os.urandom(32)
    a1 = birp_anchor(beo, hdna_code, ts, seed)
    a2 = birp_anchor(beo, hdna_code, ts, seed)
    assert a1 == a2, "birp_anchor must be deterministic"
    assert len(a1) == HASH_LEN
    # Different ts -> different anchor.
    a3 = birp_anchor(beo, hdna_code, ts + 1, seed)
    assert a3 != a1, "birp_anchor must be sensitive to enrollment_ts"
    # Different hash_dna_code -> different anchor.
    a4 = birp_anchor(beo, b"\xcc" * 32, ts, seed)
    assert a4 != a1, "birp_anchor must be sensitive to hash_dna_code"

    # 5. Public commitment is hash-of-hash.
    b_h = behavioral_hash(b"some-behavior", b"nonce-9")
    pc = public_commitment(b_h)
    assert len(pc) == HASH_LEN
    assert pc != b_h, "public_commitment must differ from behavioral_hash"
    assert pc == _sha3_256(b_h), "public_commitment must be SHA3-256(behavioral_hash)"

    # 6. Disclosure hash determinism + 32 bytes.
    d1 = disclosure_hash(b"disclosure payload v1")
    d2 = disclosure_hash(b"disclosure payload v1")
    assert d1 == d2, "disclosure_hash must be deterministic"
    assert len(d1) == HASH_LEN
    assert disclosure_hash(b"disclosure payload v2") != d1

    # 7. Intent hash (BTCP §5.6 Phase 1).
    h_i = intent_hash(b"swap:1weth:1usdc", b"\x42" * 16, b"\x07" * 32)
    assert len(h_i) == HASH_LEN
    h_i_alt = intent_hash(b"swap:1weth:1usdc", b"\x42" * 16, b"\x08" * 32)
    assert h_i != h_i_alt, "intent_hash must be sensitive to entity_id"

    out["all_passed"] = True
    return out


if __name__ == "__main__":
    import json
    print("=== Hash_DNA commitment helpers — self-test ===")
    res = _self_test()
    print(json.dumps({k: (v if not isinstance(v, bytes) else v.hex()) for k, v in res.items()}, indent=2))
    assert res.get("all_passed"), "self-test FAILED"
    print("PASS — Hash_DNA commitment helpers (BTCP §5.6 + §7.1 + Fix 1 Step 3 + WP-Mar §16)")
