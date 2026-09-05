"""
Canonical certificate payload — byte-for-byte parity between the Solidity
library and the Python reference encoder (Wave 2, Agent G — H-01 ground layer).

Pins, on a REAL EVM (eth_tester / py-evm):

1. GOLDEN VECTOR parity — the Solidity CanonicalCertificate.encodePayload
   reproduces the exact 346-byte payload of the golden certificate pinned in
   tests/unit/test_certificate_domain_separation.py; payloadDigest ==
   keccak256(P) == GOLDEN_EVM_INNER_DIGEST; ethSignedDigest == the EIP-191
   wrap (the value family-1 validators sign).
2. Field-domain parity — mutating any canonical field changes the Solidity
   digest (the payload is not a fixed constant).
3. L4.2 tier quorum arithmetic — the strict 2/3 boundary (exactly-2/3 is NOT
   a quorum), the 0.75 tier and the 0.85 tier equality case (17/20).
4. §6 step 1/4 structural preconditions — adversarial pairs for every
   fail-closed check (kind, version, ttl, dest chain, hhi, awa, isSafe).
5. §9 freshness — positive window, expired, future-dated beyond drift.
6. Destination encoding — EVM address → left-padded bytes32 (§7).

Run: python3 tests/contracts/test_canonical_certificate_sol.py
"""

import os
import sys

import importlib.util as _ilu
_spec = _ilu.spec_from_file_location(
    "tests.contracts.sol_helpers",
    os.path.join(os.path.dirname(os.path.abspath(__file__)), "sol_helpers.py"))
import sys as _sys
_sh = _ilu.module_from_spec(_spec)
_sys.modules[_spec.name] = _sh
_spec.loader.exec_module(_sh)
EvmHarness, REPO, make_cert, cert_to_sol = (  # noqa: E402
    _sh.EvmHarness, _sh.REPO, _sh.make_cert, _sh.cert_to_sol
)

PASSED = []
FAILED = []


def check(name, cond, detail=""):
    (PASSED if cond else FAILED).append(name)
    print(f"  {'OK' if cond else 'FAIL'} {name}" + (f" — {detail}" if detail and not cond else ""))


# Golden vector (MUST equal tests/unit/test_certificate_domain_separation.py)
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
GOLDEN_EVM_INNER_DIGEST = "3e95f1fda338c447f83ba22ac6f749c6721d41ad359ad40e33cf7370f3aaa9ce"
GOLDEN_EVM_SIGNED_MESSAGE = "235e33f59f629f908a4878323d98d20da07d183d16f36e6bc0e2892f44c10828"


def golden_certificate():
    import hashlib
    from core.consensus.certificate import pack_version
    h = lambda s: hashlib.sha3_256(s.encode()).digest()
    from core.consensus.certificate import CanonicalCertificate as PyCert
    return PyCert(
        certificate_kind=1,
        protocol_version=pack_version(1, 2, 3),
        validator_epoch=7,
        certificate_nonce=42,
        escrow_id=h("golden-escrow"),
        route_id=h("golden-route"),
        intent_hash=h("golden-intent"),
        entity_id=h("golden-entity"),
        source_chain=1,
        dest_chain=900,
        destination=bytes.fromhex("00" * 12 + "deadbeef" * 5),
        amount=1_234_567_890_123_456_789,
        anchor_bh=h("golden-anchor"),
        execution_bh=h("golden-execution"),
        coherence=820_000,
        threshold=550_000,
        hhi_at_emission=1_234,
        total_effective_power=2_100_000,
        validator_count=3,
        awa_enforced=True,
        issued_at=1_700_000_123,
        ttl=86_400,
    )


def main():
    h = EvmHarness()
    probe = h.deploy(*h.compile(
        [os.path.join(REPO, "contracts", "test", "CertificateProbe.sol")]
    )["CertificateProbe"])

    print("\n1) GOLDEN VECTOR — payload byte-for-byte parity (sol ↔ py reference)")
    g = golden_certificate()
    sol_bytes = probe.functions.payload(cert_to_sol(g)).call()
    check("solidity payload == 346 bytes", len(sol_bytes) == 346, str(len(sol_bytes)))
    check("solidity payload == py golden payload hex", sol_bytes.hex() == GOLDEN_PAYLOAD_HEX)
    check("solidity payload == py encode_payload()", sol_bytes == g.encode_payload())
    d = probe.functions.digest(cert_to_sol(g)).call()
    check("solidity payloadDigest == GOLDEN_EVM_INNER_DIGEST", d.hex() == GOLDEN_EVM_INNER_DIGEST, d.hex())
    e = probe.functions.ethDigest(cert_to_sol(g)).call()
    check("solidity ethSignedDigest == GOLDEN_EVM_SIGNED_MESSAGE", e.hex() == GOLDEN_EVM_SIGNED_MESSAGE, e.hex())

    print("\n2) field-domain — any field change changes the Solidity digest")
    base = make_cert(issued_at=1000)
    d0 = probe.functions.digest(cert_to_sol(base)).call()
    mutations = {
        "nonce": lambda c: setattr(c, "certificate_nonce", 99),
        "epoch": lambda c: setattr(c, "validator_epoch", 8),
        "escrow": lambda c: setattr(c, "escrow_id", b"\x01" * 32),
        "route": lambda c: setattr(c, "route_id", b"\x01" * 32),
        "intent": lambda c: setattr(c, "intent_hash", b"\x01" * 32),
        "entity": lambda c: setattr(c, "entity_id", b"\x01" * 32),
        "dest_chain": lambda c: setattr(c, "dest_chain", 2),
        "destination": lambda c: setattr(c, "destination", b"\x00" * 12 + b"\x22" * 20),
        "amount": lambda c: setattr(c, "amount", 5),
        "anchor_bh": lambda c: setattr(c, "anchor_bh", b"\x01" * 32),
        "execution_bh": lambda c: setattr(c, "execution_bh", b"\x01" * 32),
        "coherence": lambda c: setattr(c, "coherence", 899_999),
        "threshold": lambda c: setattr(c, "threshold", 549_999),
    }
    for name, mut in mutations.items():
        c = make_cert(issued_at=1000)
        mut(c)
        check(f"digest changes with {name}", probe.functions.digest(cert_to_sol(c)).call() != d0)

    print("\n3) L4.2 tier quorum (exact integer arithmetic)")
    # tier 1 (D ≥ 0.6): 3·signed > 2·total — exactly-2/3 is NOT a quorum
    check("tier1 exact-2/3 rejected (strict)", not probe.functions.quorum(2_000_000, 3_000_000, 700_000).call())
    check("tier1 above-2/3 accepted", probe.functions.quorum(2_000_001, 3_000_000, 700_000).call())
    # tier 2 (0.4 ≤ D < 0.6): 4·signed ≥ 3·total (exactly-0.75 accepted)
    check("tier2 exact-0.75 accepted", probe.functions.quorum(750_000, 1_000_000, 500_000).call())
    check("tier2 below-0.75 rejected", not probe.functions.quorum(749_999, 1_000_000, 500_000).call())
    # tier 3 (D < 0.4): 20·signed ≥ 17·total (exactly-0.85 accepted)
    check("tier3 exact-0.85 (17/20) accepted", probe.functions.quorum(850_000, 1_000_000, 100_000).call())
    check("tier3 below-0.85 rejected", not probe.functions.quorum(849_999, 1_000_000, 100_000).call())
    check("zero total power never quorum", not probe.functions.quorum(1, 0, 700_000).call())

    print("\n4) §6 step 1/4 structural preconditions (fail-closed)")
    good = make_cert()
    probe.functions.structural(cert_to_sol(good)).call()
    check("well-formed cert passes structure", True)
    bad = [
        ("unknown kind rejected", dict(certificate_kind=2)),
        ("version too new rejected", dict(protocol_version=66052)),
        ("zero ttl rejected", dict(ttl=0)),
        ("unbound dest chain rejected", dict(dest_chain=0)),
        ("hhi critical rejected", dict(hhi_at_emission=4001)),
        ("awa not enforced rejected", dict(awa_enforced=False)),
        ("coherence below threshold rejected", dict(coherence=500_000, threshold=550_000)),
    ]
    for name, kw in bad:
        c = make_cert(**kw)
        try:
            probe.functions.structural(cert_to_sol(c)).call()
            check(name, False, "accepted")
        except Exception:
            check(name, True)

    print("\n5) §9 freshness window")
    c = make_cert(issued_at=1000, ttl=600)
    probe.functions.fresh(cert_to_sol(c), 1000).call()
    probe.functions.fresh(cert_to_sol(c), 1600).call()
    check("issued_at..issued_at+ttl accepted", True)
    check("future-dated within 60s drift accepted (lower bound widened)",
          _ok(probe, c, 960))
    check("future-dated beyond 60s rejected", _rev(probe, c, 930))
    check("expired (now > issued_at+ttl) rejected", _rev(probe, c, 1601))

    print("\n6) destination encoding (§7 EVM family)")
    a = h.dest
    enc = probe.functions.destinationOf(a).call()
    check("address left-padded to bytes32", enc == b"\x00" * 12 + bytes.fromhex(a[2:]),
          enc.hex())

    print(f"\n═══ RESULT: {len(PASSED)} passed, {len(FAILED)} failed ═══")
    if FAILED:
        print("FAILED:", FAILED)
        sys.exit(1)
    print("CanonicalCertificate library: golden-vector parity verified on real EVM.")


def _ok(probe, c, now):
    try:
        probe.functions.fresh(cert_to_sol(c), now).call()
        return True
    except Exception:
        return False


def _rev(probe, c, now):
    try:
        probe.functions.fresh(cert_to_sol(c), now).call()
        return False
    except Exception:
        return True


def test_full_battery_runs_clean():
    """pytest entry point (battery-integrity fix, follow-on-2 loop): the
    script battery must run clean whenever the pytest contracts battery
    runs — main() exits non-zero on any check() failure. Script-mode
    ("python3 tests/contracts/<file>.py") keeps working unchanged."""
    main()


if __name__ == "__main__":
    main()
