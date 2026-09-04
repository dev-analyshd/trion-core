"""tests/unit/test_hhi_threshold.py — M-07 canonical HHI + AWA precondition.

VALIDATOR_SECURITY_AUDIT M-07: "py normalizes 0-10000 → 0-1 then rejects
> 0.5 (=5000, NOT the spec's 4000 CRITICAL)" and "AWA is never checked at
any verifier."

Canonical rules (CANONICAL_CERTIFICATE.md §5.4/§6 step 4):
    hhi_at_emission <= 4000 (×1e4 scale)
    awa_enforced == 1
    coherence >= threshold

Wave 3 D closes both legs in core/btcp/modules.py::verify_proof (py) and
statically in rust/src/btcp_proof_builder.rs (0.40 on the 0-1 scale).
"""

import pytest

from core.btcp.modules import (
    BTCPProof,
    BTCPProofBuilder,
    ConsensusProof,
    ValidatorSignature,
)


def _three_sigs():
    return [
        ValidatorSignature(b"\x03" * 32, b"\x04" * 65, 0.8),
        ValidatorSignature(b"\x13" * 32, b"\x14" * 65, 0.7),
        ValidatorSignature(b"\x23" * 32, b"\x24" * 65, 0.6),
    ]


def _proof(**overrides):
    builder = BTCPProofBuilder()
    good = dict(
        anchor_bh=b"\x01" * 32, intent_hash=b"\x02" * 32,
        route_type=1, certification_block=18_000_000, value_usd=5_000.0,
        validator_signatures=_three_sigs(),
        diversity_weights=[0.8, 0.7, 0.6], hhi=1500.0,
        coherence=0.85, threshold=0.55,
    )
    good.update(overrides)
    return builder.build_proof(**good)


BLOCK = 18_000_001


class TestHHIThreshold:
    def test_hhi_4000_accepted_4001_rejected_py_scale(self):
        """×1e4 scale: the spec boundary is 4000 (previously 5000)."""
        assert BTCPProofBuilder().verify_proof(_proof(hhi=4000.0), current_block=BLOCK)
        assert not BTCPProofBuilder().verify_proof(_proof(hhi=4001.0), current_block=BLOCK)

    def test_hhi_040_accepted_041_rejected_rust_scale(self):
        """0-1 scale (rust parity): boundary 0.40 = 4000/10_000."""
        assert BTCPProofBuilder().verify_proof(_proof(hhi=0.40), current_block=BLOCK)
        assert not BTCPProofBuilder().verify_proof(_proof(hhi=0.41), current_block=BLOCK)

    def test_old_5000_loophole_closed(self):
        """The exact M-07 deviation: 4000 < hhi <= 5000 must be REJECTED.

        Under the old code, hhi=4500 normalized to 0.45 <= 0.5 and PASSED —
        above the spec's CRITICAL 4000. This is the regression pin.
        """
        for hhi in (4100.0, 4500.0, 4999.0):
            assert not BTCPProofBuilder().verify_proof(
                _proof(hhi=hhi), current_block=BLOCK
            ), f"hhi={hhi} must be rejected (spec 4000 CRITICAL)"

    def test_healthy_hhi_still_accepted(self):
        for hhi in (0.15, 1500.0, 2500.0, 3999.0):
            assert BTCPProofBuilder().verify_proof(_proof(hhi=hhi), current_block=BLOCK)

    def test_constants_exposed(self):
        assert BTCPProofBuilder.HHI_CRITICAL_X1E4 == 4000
        assert abs(BTCPProofBuilder.HHI_CRITICAL_NORMALIZED - 0.40) < 1e-12


class TestAWAPrecondition:
    def test_consensus_proof_carries_awa_bit(self):
        proof = _proof()
        assert proof.consensus_proof.awa_enforced is True

    def test_awa_false_rejects_proof(self):
        """M-07/ED-A1: proofs emitted during an AWA freeze are rejected."""
        proof = _proof(awa_enforced=False)
        assert not BTCPProofBuilder().verify_proof(proof, current_block=BLOCK)

    def test_awa_true_accepted(self):
        assert BTCPProofBuilder().verify_proof(_proof(awa_enforced=True), current_block=BLOCK)

    def test_legacy_proof_dict_defaults_awa_true(self):
        """Proofs constructed before the field existed assert AWA held
        (getattr default) — the verification leg is present regardless."""
        proof = _proof()
        consensus = ConsensusProof(
            validator_signatures=_three_sigs(),
            diversity_certificate=[0.8, 0.7, 0.6],
            hhi_at_emission=1500.0, coherence_score=0.85,
            threshold_margin=0.30,
        )
        proof2 = BTCPProof(
            anchor_bh=proof.anchor_bh, consensus_proof=consensus,
            intent_hash=proof.intent_hash, route_type=proof.route_type,
            certification_block=proof.certification_block,
            certification_expiry=proof.certification_expiry,
            validator_key_version=proof.validator_key_version,
        )
        assert BTCPProofBuilder().verify_proof(proof2, current_block=BLOCK)


class TestTTLTableParity:
    """H-06: canonical §9.2 second-based TTL — mirrors certificate.py."""

    def test_ttl_tiers_match_canonical_certificate(self):
        from core.consensus.certificate import TTL_TIERS_USD, ttl_for_value_usd
        pb = BTCPProofBuilder()
        for value_usd in (100.0, 5_000.0, 500_000.0, 50_000_000.0):
            assert pb.compute_cert_ttl(value_usd) == ttl_for_value_usd(value_usd), \
                f"TTL mismatch at value={value_usd}"
        assert [t for t, _ in pb.CERT_TTL_SECONDS] == \
            [t for t, _ in TTL_TIERS_USD[:3]] + [float("inf")]

    def test_ttl_values(self):
        pb = BTCPProofBuilder()
        assert pb.compute_cert_ttl(999.99) == 3_600
        assert pb.compute_cert_ttl(1_000.0) == 86_400
        assert pb.compute_cert_ttl(99_999.0) == 86_400
        assert pb.compute_cert_ttl(100_000.0) == 259_200
        assert pb.compute_cert_ttl(10_000_000.0) == 604_800

    def test_block_windows_table_is_gone(self):
        assert not hasattr(BTCPProofBuilder, "CERT_WINDOWS"), \
            "H-06: the non-canonical block table must be deleted"

    def test_expiry_is_time_base_plus_ttl(self):
        proof = _proof(value_usd=5_000.0, certification_block=1_000_000)
        assert proof.certification_expiry == 1_000_000 + 86_400


class TestRustStaticParity:
    """Static source checks (cargo unavailable — external-toolchain policy).

    The rust verifier must reject hhi > 0.40 and carry the §9.2 seconds
    table, keeping py/rust conformance (audit H-06/M-07).
    """

    RUST_FILE = "rust/src/btcp_proof_builder.rs"

    def _src(self):
        import pathlib
        return pathlib.Path(self.RUST_FILE).read_text()

    def test_rust_hhi_bound_is_canonical_040(self):
        src = self._src()
        assert "diversity_cert.hhi > 0.40" in src
        assert "diversity_cert.hhi > 0.5" not in src.replace("0.5}", "")

    def test_rust_ttl_table_is_seconds(self):
        src = self._src()
        assert "CERT_TTL_SECONDS" in src
        assert "CERT_WINDOWS" not in src
        for seconds in ("3_600", "86_400", "259_200", "604_800"):
            assert seconds in src, f"§9.2 tier {seconds} missing from rust table"

    def test_rust_ttl_mirrors_py(self):
        pb = BTCPProofBuilder()
        src = self._src()
        for threshold, ttl in pb.CERT_TTL_SECONDS:
            assert str(ttl).replace(",", "") .replace("_", "") in \
                src.replace("_", ""), f"tier {ttl}s not in rust source"
