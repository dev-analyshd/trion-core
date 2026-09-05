"""
TRIONOracleV3.submitCertificateAttestation — the canonical certificate path
on a real EVM (Wave 2, Agent G — H-01, H-03, H-04, M-04 oracle leg).

Positive + adversarial pairs, §6 sequence of docs/protocol/
CANONICAL_CERTIFICATE.md:

1. POSITIVE: a well-formed certificate with a weight-quorum of current-epoch
   validators is accepted, recorded and emitted; the unbound oracle fails
   closed first.
2. H-01 epoch binding: retired epoch (beyond grace) rejected; future epoch
   rejected; signers from the WRONG epoch set rejected even when the
   certificate claims the current epoch.
3. H-04 weight quorum: the count attack — 4 of 5 signers pass the COUNT
   quorum (⌈2·5/3⌉ = 4) but hold only 300k/1.0e6 power → rejected; the heavy
   quorum passes.
4. H-03 threshold provenance: the certificate's threshold must equal the
   registry's registered Θ(t) — a caller-lowered threshold is rejected even
   with a full valid signature quorum over it.
5. Registry conformance: validator_count / total_effective_power lies
   rejected (the certificate may not self-attest its set).
6. Freshness: expired and future-dated certificates rejected.
7. M-04 replay: idempotent resubmission of the same certificate is a no-op;
   same (epoch, escrow, nonce) with a different payload → the conflicting
   certificate is NOT recorded, the equivocation evidence IS recorded
   (state flag + event — persists because the call does not revert); a lower
   nonce is stale.
8. Structural fail-closed battery: kind, HHI, AWA, isSafe, ttl, dest chain,
   version, min signers, envelope shape, corrupted signature, forged weight
   claims (§6 step 5c).
9. Init takeover: non-owner cannot bind the registry.

Run: python3 tests/contracts/test_certificate_oracle_sol.py
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
EvmHarness, make_cert, make_validators, sign_cert_with_weights, sort_numeric, event_names = (  # noqa: E402
    _sh.EvmHarness, _sh.make_cert, _sh.make_validators,
    _sh.sign_cert_with_weights, _sh.sort_numeric, _sh.event_names
)


PASSED = []
FAILED = []


def check(name, cond, detail=""):
    (PASSED if cond else FAILED).append(name)
    print(f"  {'OK' if cond else 'FAIL'} {name}" + (f" — {detail}" if detail and not cond else ""))


def env(stakes, divs):
    """Interleave [s_j, d_j] pairs — the contract's envelope weight layout."""
    out = []
    for s, d in zip(stakes, divs):
        out.extend((s, d))
    return out


def submit(h, oracle, cert, sigs, stakes, divs, sender=None, expect_fail=False):
    fn = oracle.functions.submitCertificateAttestation(
        cert.encode_payload(), env(stakes, divs), b"".join(sigs))
    if expect_fail:
        return h.must_revert(fn, sender=sender)
    return h.tx(fn, sender=sender)


def batch(h, ep, epoch, signers, **cert_kw):
    cert = make_cert(
        validator_epoch=epoch,
        validator_count=ep["count"],
        total_effective_power=ep["power"],
        threshold=ep["theta"],
        issued_at=h.now(),
        **cert_kw,
    )
    sigs, stakes, divs, _ = sign_cert_with_weights(h, cert, signers, ep["stakes_by_addr"], ep["divs_by_addr"])
    return cert, sigs, stakes, divs


def epoch_set(seed, divs, theta, count=None):
    """Build an epoch-set fixture: validators numerically ordered, weight
    arrays index-aligned to the validator list, plus by-addr lookups for the
    signing helper."""
    vals = make_validators(len(divs), seed_start=seed)
    addrs = [v["addr"] for v in vals]
    order = sorted(range(len(addrs)), key=lambda i: int(addrs[i], 16))
    vals = [vals[i] for i in order]
    divs_sorted = [divs[i] for i in order]
    stakes = [1_000_000] * len(vals)
    power = sum((s * d) // 1_000_000 for s, d in zip(stakes, divs_sorted))
    d_cons = sum(divs_sorted) // len(divs_sorted)
    return {
        "vals": vals, "addrs": [v["addr"] for v in vals],
        "stakes": stakes, "divs": divs_sorted,
        "stakes_by_addr": {v["addr"]: s for v, s in zip(vals, stakes)},
        "divs_by_addr": {v["addr"]: d for v, d in zip(vals, divs_sorted)},
        "count": count or len(vals), "power": power, "theta": theta, "d_cons": d_cons,
    }


def main():
    h = EvmHarness()
    oracle = h.deploy(*h.compile(
        [h.path("TRIONOracleV3.sol")], names=["TRIONOracleV3"])["TRIONOracleV3"])
    reg = h.deploy(*h.compile([h.path("TrionEpochRegistry.sol")])["TrionEpochRegistry"])

    # epoch set A (tier 3): w = [700k, 100k, 100k, 50k, 50k], total 1.0e6, Θ=550k
    ep_a = epoch_set(0xCE57_0AAA_0000_0000_0000_0000_0000_0001,
                     [700_000, 100_000, 100_000, 50_000, 50_000], 550_000)
    # epoch set B (tier 1, DIFFERENT keys): d=0.8 ×5, total 4.0e6, Θ=600k
    ep_b = epoch_set(0xFEED_0000_0000_0000_0000_0000_0000_0001,
                     [800_000] * 5, 600_000)

    def register_epoch(ep, epx):
        h.tx(reg.functions.registerEpoch(ep, epx["addrs"], epx["stakes"], epx["divs"],
                                         epx["d_cons"], epx["theta"], 1_200))

    register_epoch(1, ep_a)

    print("\n1) POSITIVE — weight-quorum certificate accepted (after fail-closed)")
    esc = h.w3.keccak(text="escrow-oracle-1")
    check("unbound oracle fails closed",
          submit(h, oracle, *batch(h, ep_a, 1, ep_a["vals"], escrow_id=esc), expect_fail=True))
    h.tx(oracle.functions.setEpochRegistry(reg.address))
    check("registry bound", oracle.functions.epochRegistry().call() == reg.address)

    rcpt = submit(h, oracle, *batch(h, ep_a, 1, ep_a["vals"], escrow_id=esc, certificate_nonce=1))
    evs = event_names(oracle, rcpt)
    check("CertificateAttested emitted", "CertificateAttested" in evs, str(evs))
    rec = oracle.functions.canonicalBinding(esc).call()
    check("verdict recorded (nonce/epoch)",
          rec[0] is True and rec[6] == 1 and rec[7] == 1)
    check("canonicalHighestNonce[1][esc] == 1",
          oracle.functions.canonicalHighestNonce(1, esc).call() == 1)

    print("\n2) H-01 — epoch binding")
    check("same-epoch higher nonce accepted",
          submit(h, oracle, *batch(h, ep_a, 1, ep_a["vals"], escrow_id=esc, certificate_nonce=2)) is not None)
    check("future epoch (99) rejected",
          submit(h, oracle, *batch(h, ep_a, 99, ep_a["vals"], escrow_id=esc), expect_fail=True))
    check("unregistered epoch (0) rejected",
          submit(h, oracle, *batch(h, ep_a, 0, ep_a["vals"], escrow_id=esc), expect_fail=True))
    # rotate away: epochs 2-4 with set B → epoch 1 falls out of grace (4-1=3 > 2)
    register_epoch(2, ep_b)
    register_epoch(3, ep_b)
    register_epoch(4, ep_b)
    check("retired epoch (1, beyond grace) rejected",
          submit(h, oracle, *batch(h, ep_a, 1, ep_a["vals"], escrow_id=esc, certificate_nonce=3), expect_fail=True))
    check("set-A signers rejected when claiming the CURRENT epoch",
          submit(h, oracle, *batch(h, ep_a, 4, ep_a["vals"], escrow_id=esc, certificate_nonce=3), expect_fail=True))
    esc2 = h.w3.keccak(text="escrow-oracle-2")
    check("current epoch (4) with set-B quorum accepted",
          submit(h, oracle, *batch(h, ep_b, 4, ep_b["vals"], escrow_id=esc2)) is not None)

    print("\n3) H-04 — weight quorum (count attack)")
    register_epoch(5, ep_a)   # bring set A back as the current epoch
    esc3 = h.w3.keccak(text="escrow-oracle-3")
    heavy_idx = ep_a["divs"].index(700_000)
    low_signers = [v for i, v in enumerate(ep_a["vals"]) if i != heavy_idx]
    check("count-attack: 4 low-weight signers (300k < 850k) rejected",
          submit(h, oracle, *batch(h, ep_a, 5, low_signers, escrow_id=esc3), expect_fail=True))
    heavy_and_3 = [ep_a["vals"][heavy_idx]] + low_signers[:3]
    check("heavy + 3 (950k ≥ 850k) accepted",
          submit(h, oracle, *batch(h, ep_a, 5, heavy_and_3, escrow_id=esc3, certificate_nonce=2)) is not None)

    print("\n4) H-03 — threshold provenance")
    esc4 = h.w3.keccak(text="escrow-oracle-4")
    c, s, st, dv = batch(h, ep_a, 5, ep_a["vals"], escrow_id=esc4, certificate_nonce=1)
    c.threshold = 100_000   # caller-lowered bar — coherence 900k trivially "safe"
    check("caller-lowered threshold rejected (must equal registry Θ(t))",
          submit(h, oracle, c, s, st, dv, expect_fail=True))
    c.threshold = 550_001
    check("off-by-one threshold rejected", submit(h, oracle, c, s, st, dv, expect_fail=True))

    print("\n5) registry conformance — the certificate may not lie about the set")
    c, s, st, dv = batch(h, ep_a, 5, ep_a["vals"], escrow_id=esc4, certificate_nonce=1)
    c.total_effective_power = ep_a["power"] + 1
    check("inflated total_effective_power rejected", submit(h, oracle, c, s, st, dv, expect_fail=True))
    c.total_effective_power = ep_a["power"]
    c.validator_count = ep_a["count"] + 1
    check("wrong validator_count rejected", submit(h, oracle, c, s, st, dv, expect_fail=True))

    print("\n6) freshness")
    c, s, st, dv = batch(h, ep_a, 5, ep_a["vals"], escrow_id=esc4, certificate_nonce=1)
    c.issued_at = h.now() - 3_601
    check("expired certificate rejected", submit(h, oracle, c, s, st, dv, expect_fail=True))
    c.issued_at = h.now() + 120
    check("future-dated beyond drift rejected", submit(h, oracle, c, s, st, dv, expect_fail=True))

    print("\n7) M-04 — replay, idempotence, conflict evidence")
    esc5 = h.w3.keccak(text="escrow-oracle-5")
    c, s, st, dv = batch(h, ep_a, 5, ep_a["vals"], escrow_id=esc5, certificate_nonce=10)
    submit(h, oracle, c, s, st, dv)
    rcpt2 = submit(h, oracle, c, s, st, dv)  # idempotent resubmission
    check("idempotent resubmission emits no new event",
          rcpt2 is not None and "CertificateAttested" not in event_names(oracle, rcpt2))
    check("highest nonce unchanged after idempotent resubmission",
          oracle.functions.canonicalHighestNonce(5, esc5).call() == 10)
    # same (epoch, escrow, nonce), DIFFERENT payload → conflict evidence
    c_conf = make_cert(
        validator_epoch=5, validator_count=ep_a["count"],
        total_effective_power=ep_a["power"], threshold=ep_a["theta"],
        issued_at=h.now(), escrow_id=esc5, certificate_nonce=10, amount=999)
    sigs_c, st_c, dv_c, _ = sign_cert_with_weights(h, c_conf, ep_a["vals"],
                                                   ep_a["stakes_by_addr"], ep_a["divs_by_addr"])
    rcpt_c = submit(h, oracle, c_conf, sigs_c, st_c, dv_c)
    evs = event_names(oracle, rcpt_c)
    check("conflicting certificate rejected (verdict NOT overwritten)",
          oracle.functions.canonicalBinding(esc5).call()[7] == 10)
    check("CertificateEquivocation evidence event emitted", "CertificateEquivocation" in evs, str(evs))
    conflict = oracle.functions.certificateConflict(5, esc5).call()
    check("conflict evidence recorded in state (two digests)",
          conflict[0] is True and conflict[1] != bytes(32) and conflict[2] != bytes(32))
    # lower nonce is stale
    c_stale = make_cert(
        validator_epoch=5, validator_count=ep_a["count"],
        total_effective_power=ep_a["power"], threshold=ep_a["theta"],
        issued_at=h.now(), escrow_id=esc5, certificate_nonce=9)
    sigs_s, st_s, dv_s, _ = sign_cert_with_weights(h, c_stale, ep_a["vals"],
                                                   ep_a["stakes_by_addr"], ep_a["divs_by_addr"])
    check("lower nonce is stale and rejected",
          submit(h, oracle, c_stale, sigs_s, st_s, dv_s, expect_fail=True))
    # higher nonce advances
    c_new = make_cert(
        validator_epoch=5, validator_count=ep_a["count"],
        total_effective_power=ep_a["power"], threshold=ep_a["theta"],
        issued_at=h.now(), escrow_id=esc5, certificate_nonce=11)
    sigs_n, st_n, dv_n, _ = sign_cert_with_weights(h, c_new, ep_a["vals"],
                                                   ep_a["stakes_by_addr"], ep_a["divs_by_addr"])
    check("higher nonce advances the ordering",
          submit(h, oracle, c_new, sigs_n, st_n, dv_n) is not None and
          oracle.functions.canonicalHighestNonce(5, esc5).call() == 11)

    print("\n8) structural fail-closed battery")
    cases = [
        ("unknown kind", dict(certificate_kind=2)),
        ("hhi critical", dict(hhi_at_emission=4001)),
        ("awa not enforced", dict(awa_enforced=False)),
        ("coherence below threshold", dict(coherence=500_000)),
        ("zero ttl", dict(ttl=0)),
        ("unbound dest chain", dict(dest_chain=0)),
        ("version too new", dict(protocol_version=66052)),
    ]
    for name, kw in cases:
        c, s, st, dv = batch(h, ep_a, 5, ep_a["vals"], escrow_id=esc5, certificate_nonce=12, **kw)
        check(name + " rejected", submit(h, oracle, c, s, st, dv, expect_fail=True))
    c, s, st, dv = batch(h, ep_a, 5, ep_a["vals"], escrow_id=esc5, certificate_nonce=12)
    check("envelope shape mismatch rejected",
          h.must_revert(oracle.functions.submitCertificateAttestation(c.encode_payload(), env(st, dv), b"".join(s[:3]))))
    check("below min signers rejected",
          h.must_revert(oracle.functions.submitCertificateAttestation(c.encode_payload(), env(st[:2], dv[:2]), b"".join(s[:2]))))
    bad = bytearray(s[0]); bad[10] ^= 0xFF
    check("one corrupted signature fails the batch",
          h.must_revert(oracle.functions.submitCertificateAttestation(
              c.encode_payload(), env(st, dv), bytes(bad) + b"".join(s[1:]))))
    st_forged = list(st); st_forged[0] += 1
    check("forged stake claim rejected (§6 step 5c)",
          h.must_revert(oracle.functions.submitCertificateAttestation(c.encode_payload(), env(st_forged, dv), b"".join(s))))
    dv_forged = list(dv); dv_forged[1] += 1
    check("forged diversity claim rejected",
          h.must_revert(oracle.functions.submitCertificateAttestation(c.encode_payload(), env(st, dv_forged), b"".join(s))))

    print("\n9) init takeover on the oracle")
    check("non-owner cannot bind the registry",
          h.must_revert(oracle.functions.setEpochRegistry(reg.address), sender=h.other))
    check("zero registry rejected",
          h.must_revert(oracle.functions.setEpochRegistry("0x" + "00" * 20)))

    print(f"\n═══ RESULT: {len(PASSED)} passed, {len(FAILED)} failed ═══")
    if FAILED:
        print("FAILED:", FAILED)
        sys.exit(1)
    print("TRIONOracleV3 canonical attestation path verified on real EVM.")


def test_full_battery_runs_clean():
    """pytest entry point (battery-integrity fix, follow-on-2 loop): the
    script battery must run clean whenever the pytest contracts battery
    runs — main() exits non-zero on any check() failure. Script-mode
    ("python3 tests/contracts/<file>.py") keeps working unchanged."""
    main()


if __name__ == "__main__":
    main()
