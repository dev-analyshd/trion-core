"""
Canonical certificate — domain separation + golden vectors (Wave 1, Agent E)
==============================================================================

Pins docs/protocol/CANONICAL_CERTIFICATE.md against the Python reference
encoder (core/consensus/certificate.py):

1. GOLDEN VECTOR — the exact 346-byte payload, the SHA3-256 certificate hash
   and the EVM-family signed message for a fixed certificate. Every Wave 2 VM
   implementation (EVM, Vyper, Solana, Move, TON, Cairo, NEAR, PVM) and the
   Go/Rust cores must reproduce these bytes exactly. If this test changes,
   the certificate format version must bump.
2. Width/offset table — the payload slices decode back to the fields via the
   OFFSETS table (the doc §2 table is the same dict).
3. Determinism + round-trip.
4. DOMAIN SEPARATION — mutating ANY canonical field changes the certificate
   hash (parametrized over all 23 fields + the awa flag + the kind + the
   version + the domain tag), so a signature over one certificate can never
   verify for another escrow / route / intent / chain / epoch / nonce /
   version / statement.
5. Fail-closed structural verification (§6 steps 1-2, 4): wrong width, bad
   domain tag, unknown kind, < 3 signers, HHI > 4000, AWA false, not isSafe,
   ttl 0, unbound dest_chain, epoch outside the grace window.
6. Quorum tiers (L4.2) in exact integer arithmetic, including the
   exactly-2/3-is-NOT-a-quorum boundary and the 0.85 equality case (17/20).
7. STARK-family felt chunking is injective (chunks rebuild the payload).
8. The canonical payload is NOT the legacy py signing message
   (intent_hash || pubkey — audit finding H-02) and not any Behavioral-Hash
   or intent commitment (disjoint domain).

Run: /home/z/.venv/bin/python3 -m pytest tests/unit/test_certificate_domain_separation.py -q
"""

from __future__ import annotations

import hashlib
import dataclasses
import pytest

from core.consensus.certificate import (
    CanonicalCertificate,
    CertificateEnvelope,
    EpochSet,
    EpochSetEntry,
    SignatureFamily,
    WeightedSignatureEntry,
    OFFSETS,
    PAYLOAD_WIDTH,
    DOMAIN_TAG,
    MIN_SIGNERS,
    HHI_MAX_ACCEPTABLE,
    EPOCH_GRACE_DEFAULT,
    pack_version,
    unpack_version,
    ttl_for_value_usd,
    verify_structure,
    check_epoch_set_conformance,
    _HAVE_KECCAK,
)

# ═════════════════════════════════════════════════════════════════════════════
# Golden fixture
# ═════════════════════════════════════════════════════════════════════════════

_h = lambda s: hashlib.sha3_256(s.encode()).digest()


def golden_certificate() -> CanonicalCertificate:
    """The fixed certificate whose bytes every VM implementation must match."""
    return CanonicalCertificate(
        certificate_kind=1,
        protocol_version=pack_version(1, 2, 3),
        validator_epoch=7,
        certificate_nonce=42,
        escrow_id=_h("golden-escrow"),
        route_id=_h("golden-route"),
        intent_hash=_h("golden-intent"),
        entity_id=_h("golden-entity"),
        source_chain=1,                      # Ethereum (canonical registry)
        dest_chain=900,                      # Solana (canonical registry)
        destination=bytes.fromhex("00" * 12 + "deadbeef" * 5),
        amount=1_234_567_890_123_456_789,
        anchor_bh=_h("golden-anchor"),
        execution_bh=_h("golden-execution"),
        coherence=820_000,                   # ×1e6 → 0.82
        threshold=550_000,                   # ×1e6 → 0.55
        hhi_at_emission=1_234,               # ×1e4 → 12.34 on the 0-10000 scale
        total_effective_power=2_100_000,     # ×1e6 — matches golden epoch set
        validator_count=3,
        awa_enforced=True,
        issued_at=1_700_000_123,
        ttl=86_400,                          # 24 h ($5k value tier)
    )


# GOLDEN VECTOR — DO NOT EDIT (format version must bump if these change).
GOLDEN_PAYLOAD_HEX = (
    "5452494f4e2d434552542d56310101020300000007000000000000002a92ddb37e180f22e5c6bf"
    "8a5a0193e6667f9e5033e0f7e211f872b228c0d5ab4844382abe7384edc55fee90e34e8ad5125d"
    "1424cda169ac66c49bab352edcb1c7f5b924aa164638afc1ecf06bfd2497cb0d2b69db1957bd34"
    "c9c07b92027b9491b77eff14723f36d91c2c3c980e7ccb5f7d2a4e5000559e4cdd74f0476ab415"
    "d40000000100000384000000000000000000000000deadbeefdeadbeefdeadbeefdeadbeefdead"
    "beef000000000000000000000000000000000000000000000000112210f47de981159f79fd8be8"
    "87f26ada731d90a3a7530c8c28f90e89b154a36330e62e37f401994d7ec804d5d44a79c9147769"
    "1041d8c90cdead3735f764c000e2f842a5c5b07100000000000c83200000000000086470000000"
    "00000004d20000000000200b200000000301000000006553f17b0000000000015180"
)
GOLDEN_CERT_HASH = (
    "2638da1937fcd389a15fe8280b402f28243a2f6fd2395976f3bbb10d7ce3c6d6"
)
GOLDEN_EVM_SIGNED_MESSAGE = (
    "235e33f59f629f908a4878323d98d20da07d183d16f36e6bc0e2892f44c10828"
)
GOLDEN_EVM_INNER_DIGEST = (
    "3e95f1fda338c447f83ba22ac6f749c6721d41ad359ad40e33cf7370f3aaa9ce"
)


def golden_epoch_set() -> EpochSet:
    """3 validators × (s=1.0, d=0.7) → total power 2.1e6, D=0.7 → tier 1."""
    return EpochSet(7, [
        EpochSetEntry(_h("golden-validator-a"), 1_000_000, 700_000),
        EpochSetEntry(_h("golden-validator-b"), 1_000_000, 700_000),
        EpochSetEntry(_h("golden-validator-c"), 1_000_000, 700_000),
    ])


def golden_envelope(family: int = int(SignatureFamily.ED25519)) -> CertificateEnvelope:
    es = golden_epoch_set()
    return CertificateEnvelope(
        family=family,
        signatures=[
            WeightedSignatureEntry(
                e.validator_id, e.stake_weight, e.diversity_weight,
                bytes(SignatureFamily(family).signature_length),
            )
            for e in es.entries
        ],
    )


# ═════════════════════════════════════════════════════════════════════════════
# 1. Golden vector + width/offsets
# ═════════════════════════════════════════════════════════════════════════════

class TestGoldenVector:
    def test_payload_width(self):
        p = golden_certificate().encode_payload()
        assert len(p) == PAYLOAD_WIDTH == 346

    def test_golden_payload_bytes(self):
        assert golden_certificate().encode_payload().hex() == GOLDEN_PAYLOAD_HEX

    def test_golden_certificate_hash(self):
        # SHA3-256 (FIPS 202) of the payload — the cross-VM certificate id
        assert golden_certificate().certificate_hash().hex() == GOLDEN_CERT_HASH
        assert golden_certificate().certificate_hash() == hashlib.sha3_256(
            golden_certificate().encode_payload()
        ).digest()

    def test_golden_evm_signed_message(self):
        if not _HAVE_KECCAK:
            pytest.skip("pycryptodome not installed — keccak digest unavailable")
        cert = golden_certificate()
        assert cert.evm_signed_message().hex() == GOLDEN_EVM_SIGNED_MESSAGE
        # Independent re-derivation: EIP-191 wrap of the keccak inner digest
        from core.consensus.certificate import keccak256
        inner = keccak256(cert.encode_payload())
        assert inner.hex() == GOLDEN_EVM_INNER_DIGEST
        assert cert.evm_signed_message() == keccak256(
            b"\x19Ethereum Signed Message:\n32" + inner
        )

    def test_offsets_table_decodes_every_field(self):
        cert = golden_certificate()
        p = cert.encode_payload()
        u = lambda name, width: int.from_bytes(
            p[OFFSETS[name][0]: OFFSETS[name][0] + width], "big"
        )
        assert p[OFFSETS["domain_tag"][0]:OFFSETS["domain_tag"][1]] == DOMAIN_TAG
        assert u("certificate_kind", 1) == cert.certificate_kind
        assert u("protocol_version", 3) == cert.protocol_version
        assert u("validator_epoch", 4) == cert.validator_epoch
        assert u("certificate_nonce", 8) == cert.certificate_nonce
        for name in ("escrow_id", "route_id", "intent_hash", "entity_id",
                     "destination", "anchor_bh", "execution_bh"):
            assert p[OFFSETS[name][0]:OFFSETS[name][1]] == getattr(cert, name)
        assert u("source_chain", 4) == cert.source_chain
        assert u("dest_chain", 4) == cert.dest_chain
        assert p[OFFSETS["amount"][0]:OFFSETS["amount"][1]] == cert.amount.to_bytes(32, "big")
        assert u("coherence", 8) == cert.coherence
        assert u("threshold", 8) == cert.threshold
        assert u("hhi_at_emission", 8) == cert.hhi_at_emission
        assert u("total_effective_power", 8) == cert.total_effective_power
        assert u("validator_count", 4) == cert.validator_count
        assert u("awa_enforced", 1) == 1
        assert u("issued_at", 8) == cert.issued_at
        assert u("ttl", 8) == cert.ttl
        # offsets are contiguous and end exactly at the payload width
        end = 0
        for name, (start, stop) in OFFSETS.items():
            assert start == end, f"{name} starts at {start}, expected {end}"
            end = stop
        assert end == PAYLOAD_WIDTH

    def test_round_trip(self):
        cert = golden_certificate()
        rt = CanonicalCertificate.from_payload(cert.encode_payload())
        assert rt == cert
        assert rt.encode_payload() == cert.encode_payload()

    def test_determinism(self):
        a, b = golden_certificate(), golden_certificate()
        assert a.encode_payload() == b.encode_payload()
        assert a.certificate_hash() == b.certificate_hash()

    def test_stark_felt_chunks_rebuild_payload(self):
        # FAMILY 3 chunking is injective: 12 chunks (11 × 31 bytes + one
        # 5-byte tail), rebuilt with the FIXED per-chunk widths (the Cairo
        # side knows the chunking convention — the last felt carries
        # PAYLOAD_WIDTH - 11*31 bytes)
        cert = golden_certificate()
        chunks = cert.stark_felt_chunks()
        assert len(chunks) == 12
        tail_width = PAYLOAD_WIDTH - 11 * 31          # 346 - 341 = 5
        rebuilt = b"".join(
            c.to_bytes(31 if i < 11 else tail_width, "big")
            for i, c in enumerate(chunks)
        )
        assert rebuilt == cert.encode_payload()
        assert all(c < 2**252 for c in chunks)
        # domain felt is the short-string encoding of the tag (one felt)
        assert cert.stark_domain_felt == int.from_bytes(DOMAIN_TAG, "big")


# ═════════════════════════════════════════════════════════════════════════════
# 2. Domain separation — every field is bound
# ═════════════════════════════════════════════════════════════════════════════

# (field name, replacement value)
_FIELD_MUTATIONS = [
    ("certificate_kind",      2),                         # BOOTSTRAP_MULTISIG
    ("protocol_version",      pack_version(2, 0, 0)),
    ("validator_epoch",       8),
    ("certificate_nonce",     43),
    ("escrow_id",             _h("other-escrow")),
    ("route_id",              _h("other-route")),
    ("intent_hash",           _h("other-intent")),
    ("entity_id",             _h("other-entity")),
    ("source_chain",          900),
    ("dest_chain",            23000),
    ("destination",           bytes(32)),
    ("amount",                1),
    ("anchor_bh",             _h("other-anchor")),
    ("execution_bh",          _h("other-execution")),
    ("coherence",             820_001),
    ("threshold",             550_001),
    ("hhi_at_emission",       1_235),
    ("total_effective_power", 2_100_001),
    ("validator_count",       4),
    ("issued_at",             1_700_000_124),
    ("ttl",                   86_401),
]


class TestDomainSeparation:
    @pytest.mark.parametrize("field,new_value", _FIELD_MUTATIONS,
                             ids=[f for f, _ in _FIELD_MUTATIONS])
    def test_every_field_is_bound(self, field, new_value):
        base = golden_certificate()
        baseline = base.certificate_hash()
        mutated = dataclasses.replace(base, **{field: new_value})
        assert mutated.certificate_hash() != baseline, (
            f"mutating {field} did not change the certificate hash — "
            "the field is NOT bound in the signing payload"
        )

    def test_awa_flag_is_bound(self):
        base = golden_certificate()
        mutated = dataclasses.replace(base, awa_enforced=False)
        assert mutated.certificate_hash() != base.certificate_hash()

    def test_domain_tag_prefix(self):
        p = golden_certificate().encode_payload()
        assert p[:13] == b"TRION-CERT-V1"
        # no other protocol message shares the tag (BH tag differs)
        assert b"TRION-BEHAVIORAL_HASH_V1" not in p
        assert p[:13] != b"TRION-VOTE-V1"

    def test_legacy_py_signing_message_is_not_the_payload(self):
        # audit H-02: the old py path signed intent_hash || pubkey — the
        # canonical payload is a different, wider, domain-tagged object
        cert = golden_certificate()
        legacy_msg = cert.intent_hash + bytes(33)
        assert legacy_msg != cert.encode_payload()
        assert len(legacy_msg) != PAYLOAD_WIDTH
        assert cert.certificate_hash() != hashlib.sha3_256(legacy_msg).digest()

    def test_replay_firewalls(self):
        base = golden_certificate()
        h = base.certificate_hash()
        # another chain (Ethereum 1 → NEAR 23000)
        other_chain = dataclasses.replace(base, dest_chain=23000)
        # another escrow
        other_escrow = dataclasses.replace(base, escrow_id=_h("escrow-2"))
        # another epoch
        other_epoch = dataclasses.replace(base, validator_epoch=8)
        # another nonce (re-attestation)
        other_nonce = dataclasses.replace(base, certificate_nonce=43)
        # another statement kind (bootstrap multisig ≠ DW-BFT release)
        with pytest.raises(ValueError):
            CanonicalCertificate(certificate_kind=99)
        other_kind = dataclasses.replace(base, certificate_kind=2)
        assert other_kind.certificate_hash() != h
        for mutant in (other_chain, other_escrow, other_epoch, other_nonce):
            assert mutant.certificate_hash() != h
            # the mutated certificate also decodes to different bytes
            assert CanonicalCertificate.from_payload(
                mutant.encode_payload()
            ).encode_payload() != base.encode_payload()


# ═════════════════════════════════════════════════════════════════════════════
# 3. Fail-closed structural verification
# ═════════════════════════════════════════════════════════════════════════════

class TestFailClosed:
    def test_valid_structure_passes(self):
        ok, reasons = verify_structure(golden_certificate(), golden_envelope())
        assert ok and reasons == []

    def test_wrong_width_rejected(self):
        p = golden_certificate().encode_payload()
        with pytest.raises(ValueError):
            CanonicalCertificate.from_payload(p[:-1])
        with pytest.raises(ValueError):
            CanonicalCertificate.from_payload(p + b"\x00")

    def test_bad_domain_tag_rejected(self):
        p = bytearray(golden_certificate().encode_payload())
        p[0] = ord("X")
        with pytest.raises(ValueError):
            CanonicalCertificate.from_payload(bytes(p))

    def test_unknown_kind_rejected(self):
        with pytest.raises(ValueError):
            CanonicalCertificate(certificate_kind=99)

    def test_insufficient_signers(self):
        env = golden_envelope()
        env2 = CertificateEnvelope(
            family=env.family, signatures=env.signatures[:MIN_SIGNERS - 1]
        )
        ok, reasons = verify_structure(golden_certificate(), env2)
        assert not ok and any("insufficient signers" in r for r in reasons)

    def test_duplicate_signers_rejected_at_envelope(self):
        sigs = golden_envelope().signatures
        with pytest.raises(ValueError):
            CertificateEnvelope(family=int(SignatureFamily.ED25519),
                                signatures=[sigs[0], sigs[0], sigs[1]])

    def test_hhi_above_critical_rejected(self):
        cert = dataclasses.replace(golden_certificate(), hhi_at_emission=HHI_MAX_ACCEPTABLE + 1)
        ok, reasons = verify_structure(cert, golden_envelope())
        assert not ok and any("hhi" in r for r in reasons)

    def test_awa_false_rejected(self):
        cert = dataclasses.replace(golden_certificate(), awa_enforced=False)
        ok, reasons = verify_structure(cert, golden_envelope())
        assert not ok and any("awa" in r for r in reasons)

    def test_not_is_safe_rejected(self):
        cert = dataclasses.replace(golden_certificate(), threshold=820_001)
        ok, reasons = verify_structure(cert, golden_envelope())
        assert not ok and any("isSafe" in r for r in reasons)

    def test_zero_ttl_rejected(self):
        cert = dataclasses.replace(golden_certificate(), ttl=0)
        ok, reasons = verify_structure(cert, golden_envelope())
        assert not ok and any("ttl" in r for r in reasons)

    def test_zero_dest_chain_rejected(self):
        cert = dataclasses.replace(golden_certificate(), dest_chain=0)
        ok, reasons = verify_structure(cert, golden_envelope())
        assert not ok and any("dest_chain" in r for r in reasons)

    def test_epoch_outside_grace_rejected(self):
        # certificate from an epoch 3 older than the latest registered (grace 2)
        ok, reasons = verify_structure(
            golden_certificate(), golden_envelope(), latest_registered_epoch=7 + EPOCH_GRACE_DEFAULT + 1
        )
        assert not ok and any("grace" in r for r in reasons)

    def test_epoch_within_grace_accepted(self):
        ok, reasons = verify_structure(
            golden_certificate(), golden_envelope(), latest_registered_epoch=7 + EPOCH_GRACE_DEFAULT
        )
        assert ok and reasons == []

    def test_future_epoch_rejected(self):
        ok, reasons = verify_structure(
            golden_certificate(), golden_envelope(), latest_registered_epoch=6
        )
        assert not ok and any("future epoch" in r for r in reasons)

    def test_bad_field_widths_rejected(self):
        with pytest.raises(ValueError):
            CanonicalCertificate(escrow_id=b"\x00" * 31)
        with pytest.raises(ValueError):
            CanonicalCertificate(amount=1 << 256)
        with pytest.raises(ValueError):
            CanonicalCertificate(coherence=1_000_001)   # ×1e6 scale overflow
        with pytest.raises(ValueError):
            CanonicalCertificate(hhi_at_emission=10_001)  # ×1e4 scale overflow

    def test_epoch_set_conformance(self):
        cert = golden_certificate()
        ok, reasons = check_epoch_set_conformance(cert, golden_epoch_set())
        assert ok and reasons == []
        # certificate lies about the set
        liar = dataclasses.replace(cert, total_effective_power=2_100_001)
        ok, reasons = check_epoch_set_conformance(liar, golden_epoch_set())
        assert not ok and any("lied" in r for r in reasons)
        liar2 = dataclasses.replace(cert, validator_count=4)
        ok, reasons = check_epoch_set_conformance(liar2, golden_epoch_set())
        assert not ok and any("validator_count" in r for r in reasons)


# ═════════════════════════════════════════════════════════════════════════════
# 4. Quorum tiers (L4.2) — exact integer arithmetic
# ═════════════════════════════════════════════════════════════════════════════

def _uniform_set(epoch: int, n: int, d: int = 700_000) -> EpochSet:
    return EpochSet(epoch, [
        EpochSetEntry(_h(f"v-{epoch}-{i}"), 1_000_000, d) for i in range(n)
    ])


class TestQuorumTiers:
    def test_effective_power_is_stake_times_diversity(self):
        # w_j = s_j · d_j carried ×1e6: (1e6 × 0.7e6)/1e6 = 0.7e6
        assert EpochSetEntry(_h("x"), 1_000_000, 700_000).effective_power() == 700_000
        assert EpochSetEntry(_h("x"), 2_000_000, 500_000).effective_power() == 1_000_000

    def test_d_consensus_and_tier_boundaries(self):
        assert _uniform_set(1, 3, d=600_000).quorum_tier() == 1     # D ≥ 0.60
        assert _uniform_set(1, 3, d=599_999).quorum_tier() == 2     # 0.40 ≤ D < 0.60
        assert _uniform_set(1, 3, d=400_000).quorum_tier() == 2
        assert _uniform_set(1, 3, d=399_999).quorum_tier() == 3     # D < 0.40

    def test_tier1_exactly_two_thirds_is_not_a_quorum(self):
        # 3 equal validators, 2 sign: 2/3 exactly → STRICT > fails
        es = _uniform_set(7, 3, d=700_000)
        ids = [e.validator_id for e in es.entries]
        met, signed, total, tier = es.quorum_met(ids[:2])
        assert tier == 1
        assert (signed, total) == (1_400_000, 2_100_000)
        assert not met, "exactly 2/3 must NOT be a quorum (Go engine discipline)"

    def test_tier1_above_two_thirds_passes(self):
        es = _uniform_set(7, 3, d=700_000)
        ids = [e.validator_id for e in es.entries]
        met, _, _, _ = es.quorum_met(ids)
        assert met

    def test_tier2_quorum_is_three_quarters(self):
        # D = 0.50 → tier 2 → 0.75: 2 of 3 (0.667) fails, 3 of 3 passes
        es = _uniform_set(7, 3, d=500_000)
        ids = [e.validator_id for e in es.entries]
        assert es.quorum_tier() == 2
        assert not es.quorum_met(ids[:2])[0]
        assert es.quorum_met(ids)[0]
        # 3 of 4 = 0.75 exactly → ≥ holds
        es4 = _uniform_set(7, 4, d=500_000)
        ids4 = [e.validator_id for e in es4.entries]
        assert es4.quorum_met(ids4[:3])[0]
        assert not es4.quorum_met(ids4[:2])[0]

    def test_tier3_quorum_is_85_percent(self):
        # D = 0.30 → tier 3 → 0.85: 17 of 20 exactly → ≥ holds
        es = _uniform_set(7, 20, d=300_000)
        ids = [e.validator_id for e in es.entries]
        assert es.quorum_tier() == 3
        met, signed, total, _ = es.quorum_met(ids[:17])
        assert met and signed * 20 == 17 * total   # exact equality passes
        assert not es.quorum_met(ids[:16])[0]

    def test_unknown_signers_contribute_no_power(self):
        es = golden_epoch_set()
        met, signed, _, _ = es.quorum_met([_h("ghost"), _h("ghost-2"), _h("ghost-3")])
        assert signed == 0 and not met

    def test_hhi_uniform_three_validators(self):
        # uniform 3 validators → HHI ≈ 3333 (×1e4 scale), below CRITICAL 4000
        assert 3_300 <= _uniform_set(7, 3).hhi() <= 3_400

    def test_golden_certificate_quorum_with_full_set(self):
        es = golden_epoch_set()
        ids = [e.validator_id for e in es.entries]
        met, signed, total, tier = es.quorum_met(ids)
        assert met and tier == 1
        assert (signed, total) == (2_100_000, 2_100_000)
        # the golden certificate's bound total matches the registered total
        assert golden_certificate().total_effective_power == total


# ═════════════════════════════════════════════════════════════════════════════
# 5. Freshness / TTL tiers (§9)
# ═════════════════════════════════════════════════════════════════════════════

class TestFreshness:
    def test_ttl_value_tiers(self):
        assert ttl_for_value_usd(500.0) == 3_600
        assert ttl_for_value_usd(1_000.0) == 86_400
        assert ttl_for_value_usd(99_999.0) == 86_400
        assert ttl_for_value_usd(100_000.0) == 259_200
        assert ttl_for_value_usd(9_999_999.0) == 259_200
        assert ttl_for_value_usd(10_000_000.0) == 604_800
        assert ttl_for_value_usd(10**12) == 604_800

    def test_freshness_window(self):
        cert = golden_certificate()   # issued 1_700_000_123, ttl 86_400
        assert cert.fresh_at(1_700_000_123)
        assert cert.fresh_at(1_700_000_123 + 86_400)
        assert not cert.fresh_at(1_700_000_123 + 86_401)   # expired — never widened
        # lower bound widened by drift tolerance only
        assert cert.fresh_at(1_700_000_123 - 60)
        assert not cert.fresh_at(1_700_000_123 - 61)

    def test_expires_at(self):
        cert = golden_certificate()
        assert cert.expires_at() == cert.issued_at + cert.ttl


# ═════════════════════════════════════════════════════════════════════════════
# 6. Version packing + envelope families
# ═════════════════════════════════════════════════════════════════════════════

class TestMisc:
    def test_version_pack_unpack(self):
        assert pack_version(1, 2, 3) == (1 << 16) | (2 << 8) | 3
        assert unpack_version(pack_version(255, 255, 255)) == (255, 255, 255)
        with pytest.raises(ValueError):
            pack_version(256, 0, 0)

    @pytest.mark.parametrize("family,expected_len", [
        (SignatureFamily.SECP256K1_EVM, 65),
        (SignatureFamily.ED25519, 64),
        (SignatureFamily.STARK_FELT, 64),
    ])
    def test_signature_family_lengths(self, family, expected_len):
        assert family.signature_length == expected_len

    def test_envelope_rejects_wrong_family_signature_length(self):
        with pytest.raises(ValueError):
            CertificateEnvelope(
                family=int(SignatureFamily.SECP256K1_EVM),
                signatures=[WeightedSignatureEntry(_h("v"), 1, 1, bytes(64))],
            )

    def test_envelope_rejects_unknown_family(self):
        with pytest.raises(ValueError):
            CertificateEnvelope(family=9)

    def test_epoch_set_rejects_duplicates_and_empty(self):
        with pytest.raises(ValueError):
            EpochSet(1, [])
        e = EpochSetEntry(_h("dup"), 1, 1)
        with pytest.raises(ValueError):
            EpochSet(1, [e, e])
