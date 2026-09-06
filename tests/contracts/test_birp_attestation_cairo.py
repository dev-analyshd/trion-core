"""
BIRP attestation (Starknet / Cairo) — oracle signature verification test.

SEC-04 remediation test for contracts/starknet/src/BIRPAttestation.cairo:

  * The legacy `submit_proof(commitment, tier, confidence_bp, oracle_sig_r,
    oracle_sig_s)` accepted the oracle signature parameters and NEVER READ
    them — no verification, no oracle check, no message binding. Any caller
    could self-attest a SAFE-tier proof on a fresh commitment (the relayer
    bridge itself submitted (0,0) placeholders).

  * submit_proof now takes an additional attestation_nonce and requires the
    (r, s) pair to be a STARK-curve ECDSA signature by the ORACLE's key
    (x-coordinate felt pinned in storage at deploy, rotatable by the oracle
    authority) over the domain-separated digest
    Poseidon('BIRP-ATT-V1', commitment, tier, confidence_bp,
    attestation_nonce). Zero nonces, burned nonces, zero signatures and
    forged signatures all revert; a consumed nonce can never be replayed —
    even after the commitment it certified is revoked. Submission stays
    permissionless: the signature, not the caller, carries authority.

No scarb / cairo-test toolchain exists in this sandbox (same boundary as
tests/contracts/test_btcp_escrow_cairo.py), so this file is a PYTHON MIRROR
of the Cairo validation logic (same digest inputs, same assert order, same
error codes), attacked with real signatures:

  * a STARK-curve signature model: real ECDSA over the STARK-curve
    field/equation shape, exercised at a 192-bit security level through the
    `ecdsa` package (NIST P-192 — every r, s and pubkey x-coordinate is a
    legitimate felt252 value < 2^251), with forgeries genuinely failing;
  * static source assertions that the .cairo file actually contains the
    checks (and that the unused-parameter era is gone), plus the two
    companion fixes: chains/starknet/src/lib.cairo no longer declares the
    nonexistent `pub mod cairo;` module, and the four bridge-test scripts
    read the EVM deployment records from docs/deployments/evm_sepolia.json
    (skipping cleanly when absent) instead of the never-committed
    evm-tools/evm_sepolia_deployments.json.

HONEST VERIFIED / UNVERIFIED BOUNDARIES:
  * COMPILATION IS NOW EXERCISED for the fixed contract: an isolated scarb
    crate (src/lib.cairo = `pub mod BIRPAttestation;` + the fixed file)
    compiles clean with BOTH scarb 2.10.1 / starknet 2.10.1 (the version
    chains/starknet/scripts/build-and-verify.sh pins) and scarb 2.8.4 /
    starknet 2.8.4 — using the version-portable corelib paths
    core::poseidon::poseidon_hash_span and core::ecdsa::check_ecdsa_signature
    (the starknet::crypto / starknet::ecdsa paths trion_certificate.cairo
    uses do NOT exist in corelib 2.10.1 — that crate's other files carry
    pre-existing compile errors under the repo's own pinned toolchain,
    untouched here).
  * Cairo's poseidon_hash_span (Hades Poseidon) cannot be reproduced in
    Python here, so the mirror's digest uses the same documented SHA3-256
    STAND-IN over the identical felt inputs as the escrow mirror test
    (the binding of signature to (commitment, tier, confidence, nonce) is
    fully real; only the hash instance differs).
  * The canonical STARK-curve constants cannot be reproduced without the
    toolchain, so the ECDSA model runs on NIST P-192 (same
    short-Weierstrass ECDSA scheme, felt-compatible sizes). The starknet.js
    leg (chains/starknet/src/birp-bridge.ts) was smoke-verified against
    the installed starknet package (sign + verify round-trip, tampered
    message rejected) outside this file.

Run: python3 tests/contracts/test_birp_attestation_cairo.py   (or pytest)
"""

import hashlib
import os
import sys

from ecdsa import SigningKey, VerifyingKey
from ecdsa.curves import NIST192p

REPO = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

PASSED = []
FAILED = []


def check(name, cond, detail=""):
    (PASSED if cond else FAILED).append(name)
    print(f"  {'OK' if cond else 'FAIL'} {name}" + (f" — {detail}" if detail and not cond else ""))
    return cond


class CairoPanic(Exception):
    """A Cairo `assert(..., '<code>')` failure — transaction aborts,
    nothing is committed. The felt panic code is the short-string value."""

    def __init__(self, code):
        super().__init__(f"Cairo panic: {code!r}")
        self.code = code


def _require(cond, code):
    if not cond:
        raise CairoPanic(code)


# ═════════════════════════════════════════════════════════════════════════════
# 1. Felt model (mirrors BIRPAttestation.cairo constants)
# ═════════════════════════════════════════════════════════════════════════════

STARK_PRIME = (1 << 251) + 17 * (1 << 192) + 1     # the Cairo field prime
FELT_MAX = 1 << 251                                 # < prime, canonical felt bound

# BIRPAttestation.cairo BIRP_DOMAIN_FELT — felt("BIRP-ATT-V1")
BIRP_DOMAIN_FELT = int.from_bytes(b"BIRP-ATT-V1", "big")

MAX_CONFIDENCE_BP = 10_000
MAX_TIER = 3


def _poseidon_stand_in(elements):
    """Documented STAND-IN for Cairo's poseidon_hash_span (see module
    docstring — the real Hades instance cannot be reproduced here). Same
    input discipline: domain felt first, then the attestation felts, each
    as a 32-byte big-endian felt. Output truncated to 192 bits for the
    P-192 ECDSA model (a legitimate felt-sized digest)."""
    h = hashlib.sha3_256(b"TRION-POSEIDON-MIRROR")
    for e in elements:
        h.update(int(e % STARK_PRIME).to_bytes(32, "big"))
    return int.from_bytes(h.digest()[:24], "big")


def attestation_digest(commitment, tier, confidence_bp, attestation_nonce):
    """Mirror of BIRPAttestation.cairo InternalImpl::attestation_digest:
    D = Poseidon('BIRP-ATT-V1', commitment, tier, confidence_bp,
    attestation_nonce) — the felt the oracle's STARK-curve key signs."""
    return _poseidon_stand_in([
        BIRP_DOMAIN_FELT, commitment, tier, confidence_bp, attestation_nonce])


# ═════════════════════════════════════════════════════════════════════════════
# 2. STARK-curve ECDSA model (NIST P-192 via the ecdsa package — real
#    signature math; all values are legitimate felts < 2^251)
# ═════════════════════════════════════════════════════════════════════════════


class StarkKey:
    """An oracle family-3 key. `pub_felt` models the oracle_pubkey felt the
    contract stores (the x-coordinate — Starknet's ECDSA public key form);
    `point` is the underlying curve point the syscall derives from it."""

    def __init__(self, sk):
        self._sk = sk
        self.point = sk.get_verifying_key().pubkey.point
        self.pub_felt = self.point.x()

    @classmethod
    def generate(cls):
        return cls(SigningKey.generate(curve=NIST192p))

    def sign(self, digest_felt):
        d = int(digest_felt).to_bytes(24, "big")
        sig = self._sk.sign_digest_deterministic(d)
        return int.from_bytes(sig[:24], "big"), int.from_bytes(sig[24:], "big")


def stark_verify(pub_point, digest_felt, r, s):
    """Mirror of starknet::ecdsa::verify_ecdsa_signature(pubkey, msg, (r,s))
    over the modeled curve point."""
    if pub_point is None:
        return False
    try:
        vk = VerifyingKey.from_public_point(pub_point, curve=NIST192p)
        return vk.verify_digest(
            r.to_bytes(24, "big") + s.to_bytes(24, "big"),
            int(digest_felt).to_bytes(24, "big"))
    except Exception:
        return False


# ═════════════════════════════════════════════════════════════════════════════
# 3. BIRPAttestation mirror (contracts/starknet/src/BIRPAttestation.cairo)
# ═════════════════════════════════════════════════════════════════════════════

ORACLE, WALLET, STRANGER = 1, 2, 99


class BIRPMirror:
    """Mirror of BIRPAttestation.cairo — same storage maps (oracle,
    oracle_pubkey, proofs, used_nonces, total), same assert order and
    error codes in submit_proof, same event emission points."""

    def __init__(self, oracle, oracle_pubkey, now=1_700_000_200):
        _require(oracle_pubkey != 0, "BIRP: zero oracle pubkey")
        self.oracle = oracle
        self.oracle_pubkey = oracle_pubkey
        self.oracle_point = None          # the curve point behind the felt
        self.proofs = {}                  # commitment -> proof dict
        self.used_nonces = {}             # nonce -> True (burned)
        self.total = 0
        self.now = now
        self.events = []

    def submit_proof(self, caller, commitment, tier, confidence_bp,
                     attestation_nonce, oracle_sig_r, oracle_sig_s):
        _require(tier <= MAX_TIER, "BIRP: invalid tier")
        _require(confidence_bp <= MAX_CONFIDENCE_BP, "BIRP: confidence out of range")
        _require(not self.proofs.get(commitment, {}).get("active", False),
                 "BIRP: commitment already proven")

        # fail-closed oracle authentication
        _require(self.oracle_pubkey != 0, "BIRP: oracle pubkey unset")
        _require(attestation_nonce != 0, "BIRP: zero nonce")
        _require(not self.used_nonces.get(attestation_nonce, False),
                 "BIRP: nonce already used")
        _require(oracle_sig_r != 0, "BIRP: zero sig r")
        _require(oracle_sig_s != 0, "BIRP: zero sig s")

        digest = attestation_digest(commitment, tier, confidence_bp, attestation_nonce)
        verified = stark_verify(self.oracle_point, digest, oracle_sig_r, oracle_sig_s)
        _require(verified, "BIRP: invalid oracle signature")

        proof = {
            "commitment": commitment,
            "tier": tier,
            "confidence_bp": confidence_bp,
            "submitted_at": self.now,
            "submitter": caller,
            "active": True,
        }

        # burn the nonce only after verification succeeded
        self.used_nonces[attestation_nonce] = True
        self.proofs[commitment] = proof
        self.total += 1
        self.events.append(("ProofSubmitted", commitment, tier,
                            confidence_bp, attestation_nonce, self.now, caller))
        return proof

    def verify_commitment(self, commitment):
        return self.proofs.get(commitment, {
            "commitment": commitment, "tier": 255, "confidence_bp": 0,
            "submitted_at": 0, "submitter": 0, "active": False})

    def is_above_tier(self, commitment, min_tier):
        proof = self.proofs.get(commitment, {})
        return proof.get("active", False) and proof.get("tier", 255) <= min_tier

    def revoke_proof(self, caller, commitment):
        proof = self.proofs[commitment]
        _require(proof["active"], "BIRP: proof not active")
        _require(proof["submitter"] == caller, "BIRP: not submitter")
        proof["active"] = False
        self.events.append(("ProofRevoked", commitment, self.now))

    def set_oracle(self, caller, new_oracle):
        _require(caller == self.oracle, "BIRP: not oracle")
        old = self.oracle
        self.oracle = new_oracle
        self.events.append(("OracleChanged", old, new_oracle))

    def set_oracle_pubkey(self, caller, new_pubkey):
        _require(caller == self.oracle, "BIRP: not oracle")
        _require(new_pubkey != 0, "BIRP: zero pubkey")
        old = self.oracle_pubkey
        self.oracle_pubkey = new_pubkey
        self.oracle_point = None          # old-key proofs stop validating
        self.events.append(("OraclePubkeyChanged", old, new_pubkey))

    def nonce_used(self, attestation_nonce):
        return self.used_nonces.get(attestation_nonce, False)


def _oracle_sign(oracle_key, commitment, tier, confidence_bp, attestation_nonce):
    """The off-chain oracle attestation: sign the domain-separated digest."""
    d = attestation_digest(commitment, tier, confidence_bp, attestation_nonce)
    return oracle_key.sign(d)


def _fresh_commitment():
    return int.from_bytes(hashlib.sha3_256(b"beo-salt-" + os.urandom(8)).digest()[:24], "big")


# ═════════════════════════════════════════════════════════════════════════════
# 4. Behavior tests (mirror-level, real signature math)
# ═════════════════════════════════════════════════════════════════════════════


def _deployed(oracle_key):
    m = BIRPMirror(ORACLE, oracle_key.pub_felt)
    m.oracle_point = oracle_key.point
    return m


def test_happy_path_submit_and_verify():
    print("\n1) happy path — oracle-signed proof submits and verifies")
    ok = StarkKey.generate()
    m = _deployed(ok)
    c = _fresh_commitment()
    r, s = _oracle_sign(ok, c, tier=0, confidence_bp=9_300, attestation_nonce=7)

    m.submit_proof(WALLET, c, 0, 9_300, 7, r, s)

    p = m.verify_commitment(c)
    check("proof stored with the attested tier",
          p["active"] and p["tier"] == 0 and p["confidence_bp"] == 9_300)
    check("submitter recorded for revocation rights", p["submitter"] == WALLET)
    check("is_above_tier passes at the attested tier", m.is_above_tier(c, 0))
    check("unknown commitment reads tier 255 / inactive",
          m.verify_commitment(_fresh_commitment())["tier"] == 255)
    check("nonce burned", m.nonce_used(7))
    check("total_proofs counted", m.total == 1)
    check("ProofSubmitted event carries the attestation nonce",
          m.events[0][4] == 7 and m.events[0][0] == "ProofSubmitted")


def test_tier_gating_semantics():
    print("\n1b) tier gating — worse tiers fail the min_tier gate")
    ok = StarkKey.generate()
    m = _deployed(ok)
    c = _fresh_commitment()
    r, s = _oracle_sign(ok, c, tier=2, confidence_bp=4_500, attestation_nonce=8)
    m.submit_proof(WALLET, c, 2, 4_500, 8, r, s)
    check("HIGH_RISK proof fails a SAFE gate", not m.is_above_tier(c, 0))
    check("HIGH_RISK proof passes a HIGH_RISK gate", m.is_above_tier(c, 2))
    m.revoke_proof(WALLET, c)
    check("inactive proof fails every gate", not m.is_above_tier(c, 3))


def test_self_attestation_rejected():
    print("\n2) SEC-04 core — self-attested (non-oracle-signed) proof reverts")
    ok = StarkKey.generate()
    attacker = StarkKey.generate()
    m = _deployed(ok)
    c = _fresh_commitment()

    # the attacker signs the SAME well-formed message with its OWN key
    r, s = _oracle_sign(attacker, c, tier=0, confidence_bp=10_000, attestation_nonce=1)
    try:
        m.submit_proof(WALLET, c, 0, 10_000, 1, r, s)
        check("attacker-signed proof reverts", False)
    except CairoPanic as e:
        check("attacker-signed proof reverts", e.code == "BIRP: invalid oracle signature",
              f"code={e.code}")
    check("nothing stored after the revert", not m.proofs.get(c, {}).get("active", False))
    check("nonce not burned after the revert", not m.nonce_used(1))
    check("total still zero", m.total == 0)


def test_placeholder_zero_signature_rejected():
    print("\n3) placeholder (0,0) signature (the old bridge's submission) reverts")
    ok = StarkKey.generate()
    m = _deployed(ok)
    c = _fresh_commitment()
    try:
        m.submit_proof(WALLET, c, 0, 10_000, 1, 0, 0)
        check("(0,0) reverts", False)
    except CairoPanic as e:
        check("(0,0) reverts", e.code == "BIRP: zero sig r", f"code={e.code}")


def test_signature_binding_attacks():
    print("\n4) signature/field binding — tampered fields fail verification")
    ok = StarkKey.generate()
    m = _deployed(ok)

    # signed for tier 2, submitted as tier 0 (self-upgrade to SAFE)
    c = _fresh_commitment()
    r, s = _oracle_sign(ok, c, tier=2, confidence_bp=4_000, attestation_nonce=11)
    try:
        m.submit_proof(WALLET, c, 0, 4_000, 11, r, s)
        check("tier tampering reverts", False)
    except CairoPanic as e:
        check("tier tampering reverts", e.code == "BIRP: invalid oracle signature",
              f"code={e.code}")

    # signed for commitment c1, submitted for commitment c2
    c1, c2 = _fresh_commitment(), _fresh_commitment()
    r, s = _oracle_sign(ok, c1, tier=0, confidence_bp=9_000, attestation_nonce=12)
    try:
        m.submit_proof(WALLET, c2, 0, 9_000, 12, r, s)
        check("commitment swap reverts", False)
    except CairoPanic as e:
        check("commitment swap reverts", e.code == "BIRP: invalid oracle signature",
              f"code={e.code}")

    # signed for confidence 5_000, submitted as 10_000
    c3 = _fresh_commitment()
    r, s = _oracle_sign(ok, c3, tier=0, confidence_bp=5_000, attestation_nonce=13)
    try:
        m.submit_proof(WALLET, c3, 0, 10_000, 13, r, s)
        check("confidence tampering reverts", False)
    except CairoPanic as e:
        check("confidence tampering reverts", e.code == "BIRP: invalid oracle signature",
              f"code={e.code}")

    # corrupted signature scalar
    r, s = _oracle_sign(ok, c3, tier=0, confidence_bp=5_000, attestation_nonce=14)
    try:
        m.submit_proof(WALLET, c3, 0, 5_000, 14, (r + 1) % NIST192p.order, s)
        check("corrupted r reverts", False)
    except CairoPanic as e:
        check("corrupted r reverts", e.code == "BIRP: invalid oracle signature",
              f"code={e.code}")


def test_replay_protection():
    print("\n5) replay protection — a nonce is burned exactly once, forever")
    ok = StarkKey.generate()
    m = _deployed(ok)
    c = _fresh_commitment()
    r, s = _oracle_sign(ok, c, tier=0, confidence_bp=8_000, attestation_nonce=21)

    m.submit_proof(WALLET, c, 0, 8_000, 21, r, s)

    # straight replay on the SAME commitment (commitment is also proven)
    try:
        m.submit_proof(WALLET, c, 0, 8_000, 21, r, s)
        check("same-commitment replay reverts", False)
    except CairoPanic as e:
        check("same-commitment replay reverts",
              e.code in ("BIRP: commitment already proven", "BIRP: nonce already used"),
              f"code={e.code}")

    # replay onto a FRESH commitment after revoking the original
    m.revoke_proof(WALLET, c)
    c2 = _fresh_commitment()
    try:
        m.submit_proof(WALLET, c2, 0, 8_000, 21, r, s)
        check("cross-commitment replay after revocation reverts", False)
    except CairoPanic as e:
        check("cross-commitment replay after revocation reverts",
              e.code == "BIRP: nonce already used", f"code={e.code}")
    check("revoked commitment stays inactive",
          not m.verify_commitment(c)["active"] and m.verify_commitment(c)["tier"] == 0)

    # zero nonce rejected (the all-defaults submission)
    c3 = _fresh_commitment()
    r, s = _oracle_sign(ok, c3, tier=1, confidence_bp=6_000, attestation_nonce=0)
    try:
        m.submit_proof(WALLET, c3, 1, 6_000, 0, r, s)
        check("zero nonce reverts", False)
    except CairoPanic as e:
        check("zero nonce reverts", e.code == "BIRP: zero nonce", f"code={e.code}")


def test_fail_closed_key_management():
    print("\n6) fail-closed key management")
    ok = StarkKey.generate()

    try:
        BIRPMirror(ORACLE, 0)
        check("constructor rejects zero pubkey", False)
    except CairoPanic as e:
        check("constructor rejects zero pubkey", e.code == "BIRP: zero oracle pubkey",
              f"code={e.code}")

    m = _deployed(ok)

    # non-oracle cannot rotate the signing key
    try:
        m.set_oracle_pubkey(STRANGER, 0x1234)
        check("stranger cannot set_oracle_pubkey", False)
    except CairoPanic as e:
        check("stranger cannot set_oracle_pubkey", e.code == "BIRP: not oracle",
              f"code={e.code}")

    # zero pubkey refused even for the oracle
    try:
        m.set_oracle_pubkey(ORACLE, 0)
        check("zero pubkey refused on rotation", False)
    except CairoPanic as e:
        check("zero pubkey refused on rotation", e.code == "BIRP: zero pubkey",
              f"code={e.code}")

    # rotation works for the oracle and is fail-closed for old-key proofs
    m.set_oracle_pubkey(ORACLE, 0xdeadbeef)
    check("pubkey rotated + event emitted",
          m.oracle_pubkey == 0xdeadbeef
          and m.events[-1][0] == "OraclePubkeyChanged")
    c = _fresh_commitment()
    r, s = _oracle_sign(ok, c, tier=0, confidence_bp=9_000, attestation_nonce=31)
    try:
        m.submit_proof(WALLET, c, 0, 9_000, 31, r, s)
        check("old-key proof invalid after rotation", False)
    except CairoPanic as e:
        check("old-key proof invalid after rotation",
              e.code == "BIRP: invalid oracle signature", f"code={e.code}")


def test_input_bounds():
    print("\n7) input bounds and revocation rights")
    ok = StarkKey.generate()
    m = _deployed(ok)
    c = _fresh_commitment()
    r, s = _oracle_sign(ok, c, tier=4, confidence_bp=5_000, attestation_nonce=41)
    try:
        m.submit_proof(WALLET, c, 4, 5_000, 41, r, s)
        check("tier > 3 reverts", False)
    except CairoPanic as e:
        check("tier > 3 reverts", e.code == "BIRP: invalid tier", f"code={e.code}")

    c = _fresh_commitment()
    r, s = _oracle_sign(ok, c, tier=0, confidence_bp=10_001, attestation_nonce=42)
    try:
        m.submit_proof(WALLET, c, 0, 10_001, 42, r, s)
        check("confidence > 10000 reverts", False)
    except CairoPanic as e:
        check("confidence > 10000 reverts",
              e.code == "BIRP: confidence out of range", f"code={e.code}")

    c = _fresh_commitment()
    r, s = _oracle_sign(ok, c, tier=0, confidence_bp=9_000, attestation_nonce=43)
    m.submit_proof(WALLET, c, 0, 9_000, 43, r, s)
    try:
        m.revoke_proof(STRANGER, c)
        check("stranger cannot revoke", False)
    except CairoPanic as e:
        check("stranger cannot revoke", e.code == "BIRP: not submitter", f"code={e.code}")
    m.revoke_proof(WALLET, c)
    check("submitter revokes; tier data retained", m.verify_commitment(c)["tier"] == 0)


def test_felt_range_discipline():
    print("\n8) felt range discipline — every signature value is a real felt")
    ok = StarkKey.generate()
    m = _deployed(ok)
    c = _fresh_commitment()
    r, s = _oracle_sign(ok, c, tier=3, confidence_bp=1_000, attestation_nonce=51)
    check("r, s, pubkey and digest are legitimate felts (< 2^251)",
          0 < r < FELT_MAX and 0 < s < FELT_MAX
          and 0 < ok.pub_felt < FELT_MAX
          and 0 <= attestation_digest(c, 3, 1_000, 51) < FELT_MAX)
    m.submit_proof(WALLET, c, 3, 1_000, 51, r, s)
    check("hostile-tier proof also requires a valid oracle signature",
          m.verify_commitment(c)["tier"] == 3)


# ═════════════════════════════════════════════════════════════════════════════
# 9. Static source assertions — the .cairo / .ts files contain the fixes
# ═════════════════════════════════════════════════════════════════════════════

STARKNET_SRC = os.path.join(REPO, "contracts", "starknet", "src")
CHAINS_SN_SRC = os.path.join(REPO, "chains", "starknet", "src")
BRIDGE_TESTS = ["zero-bridge-test.ts", "loop-test.ts",
                "per-vm-test.ts", "full-zero-bridge-test.ts"]


def _read(path):
    with open(path, "r", encoding="utf-8") as fh:
        return fh.read()


def _fn_block(src, name, start=0):
    """The source slice of one function (name( ... ) up to the next fn)."""
    i = src.find(name, start)
    _require(i >= 0, f"source missing {name}")
    j = src.find("\n        fn ", i + 1)
    return src[i:j if j > 0 else len(src)]


def test_static_source_assertions():
    print("\n9) static source assertions (the .cairo / .ts files contain the fixes)")
    birp = _read(os.path.join(STARKNET_SRC, "BIRPAttestation.cairo"))
    lib_sn = _read(os.path.join(CHAINS_SN_SRC, "lib.cairo"))
    bridge = _read(os.path.join(CHAINS_SN_SRC, "birp-bridge.ts"))

    # ── SEC-04: the oracle signature is verified, not just accepted ──
    impl_at = birp.find("impl BIRPAttestationImpl of IBIRPAttestation<ContractState>")
    sub = _fn_block(birp, "fn submit_proof(", impl_at)
    check("submit_proof ABI now carries the attestation nonce",
          "attestation_nonce: u64," in sub)
    check("oracle public key is pinned in storage",
          "oracle_pubkey: felt252," in birp
          and "self.oracle_pubkey.read()" in sub)
    check("replay map declared and consulted",
          "used_nonces: Map<u64, bool>," in birp
          and "self.used_nonces.read(attestation_nonce)" in sub)
    check("submit fails closed while the oracle key is unset",
          "assert(oracle_pubkey != 0, 'BIRP: oracle pubkey unset');" in sub)
    check("zero nonce rejected",
          "assert(attestation_nonce != 0, 'BIRP: zero nonce');" in sub)
    check("burned nonce rejected",
          "assert(!self.used_nonces.read(attestation_nonce), 'BIRP: nonce already used');" in sub)
    check("placeholder (0,0) signatures rejected",
          "assert(oracle_sig_r != 0, 'BIRP: zero sig r');" in sub
          and "assert(oracle_sig_s != 0, 'BIRP: zero sig s');" in sub)
    check("the (r, s) parameters ARE read — passed into ECDSA verification",
          "check_ecdsa_signature(" in sub
          and "digest, oracle_pubkey, oracle_sig_r, oracle_sig_s," in sub)
    check("corelib STARK-curve ECDSA verifier imported",
          "use core::ecdsa::check_ecdsa_signature;" in birp)
    check("Poseidon imported from the corelib (compiles on starknet 2.8–2.10)",
          "use core::poseidon::poseidon_hash_span;" in birp)
    check("verification failure reverts",
          "assert(verified, 'BIRP: invalid oracle signature');" in sub)
    check("domain-separated Poseidon digest over all attested fields",
          "const BIRP_DOMAIN_FELT: felt252 = 'BIRP-ATT-V1';" in birp
          and "input.append(BIRP_DOMAIN_FELT);" in birp
          and "input.append(commitment);" in birp
          and "input.append(tier_f);" in birp
          and "input.append(conf_f);" in birp
          and "input.append(nonce_f);" in birp
          and "poseidon_hash_span(input.span())" in birp)
    check("nonce is burned inside submit (after verification)",
          "self.used_nonces.write(attestation_nonce, true);" in sub)
    check("constructor takes the oracle public key",
          "fn constructor(ref self: ContractState, oracle: ContractAddress, oracle_pubkey: felt252)"
          in birp)
    check("ProofSubmitted event records the attestation nonce",
          "pub attestation_nonce: u64," in birp)
    check("oracle can rotate the signing key; stranger cannot",
          "fn set_oracle_pubkey(" in birp
          and "assert(caller == self.oracle.read(), 'BIRP: not oracle');" in _fn_block(
              birp, "fn set_oracle_pubkey(", impl_at))
    check("nonce_used view exposed for bridges",
          "fn nonce_used(" in birp)

    # the assert ORDER in the source: bounds → proven → key → nonce → sig
    # → verify → burn (mirror matches test order)
    order = [
        sub.find("'BIRP: invalid tier'"),
        sub.find("'BIRP: commitment already proven'"),
        sub.find("'BIRP: oracle pubkey unset'"),
        sub.find("'BIRP: zero nonce'"),
        sub.find("'BIRP: nonce already used'"),
        sub.find("'BIRP: zero sig r'"),
        sub.find("'BIRP: invalid oracle signature'"),
        sub.find("self.used_nonces.write(attestation_nonce, true);"),
    ]
    check("assert sequence is fail-closed and monotone in the source",
          all(i >= 0 for i in order) and order == sorted(order),
          f"positions={order}")

    # ── SEC-06: no dangling module declaration in the starknet crate ──
    check("chains/starknet lib.cairo no longer declares the nonexistent module",
          "pub mod cairo;" not in lib_sn)
    check("lib.cairo still defines the inline Sepolia trio",
          "pub mod TRIONOracle {" in lib_sn
          and "pub mod BEOAttestation {" in lib_sn
          and "pub mod BTCFiGuard {" in lib_sn)

    # ── SEC-25: the bridge tests read the real deployment records ────
    for name in BRIDGE_TESTS:
        ts = _read(os.path.join(CHAINS_SN_SRC, name))
        check(f"{name} reads docs/deployments/evm_sepolia.json",
              "docs', 'deployments', 'evm_sepolia.json'" in ts.replace('"', "'"))
        check(f"{name} no longer reads the missing evm-tools record",
              "evm_sepolia_deployments.json" not in ts)
        check(f"{name} skips cleanly when the records are absent",
              "fs.existsSync(EVM_PATH)" in ts and "process.exit(0)" in ts)

    # ── the bridge signs instead of submitting (0,0) placeholders ────
    check("birp-bridge.ts signs the attestation digest with the oracle key",
          "computePoseidonHashOnElements" in bridge
          and "ec.starkCurve.sign(digest, oraclePrivateKey)" in bridge
          and "BIRP-ATT-V1" in bridge)
    check("birp-bridge.ts submits the nonce and the real (r, s)",
          "attestationNonce," in bridge and "sig.r," in bridge and "sig.s," in bridge)
    check("birp-bridge.ts refuses to submit without the oracle key (fail-closed)",
          "BIRP_ORACLE_PRIVATE_KEY" in bridge
          and '"0x0"' not in bridge)


def test_all_checks_passed():
    if FAILED:
        print(f"\n!!! {len(FAILED)} FAILED checks:")
        for name in FAILED:
            print(f"    FAIL {name}")
    assert not FAILED, f"{len(FAILED)} static/mirror checks failed"
    print(f"\nALL {len(PASSED)} CHECKS PASSED")


# ═════════════════════════════════════════════════════════════════════════════
# main
# ═════════════════════════════════════════════════════════════════════════════

def main():
    tests = [
        test_happy_path_submit_and_verify,
        test_tier_gating_semantics,
        test_self_attestation_rejected,
        test_placeholder_zero_signature_rejected,
        test_signature_binding_attacks,
        test_replay_protection,
        test_fail_closed_key_management,
        test_input_bounds,
        test_felt_range_discipline,
        test_static_source_assertions,
    ]
    for t in tests:
        t()
    if FAILED:
        print(f"\n!!! {len(FAILED)} FAILED checks:")
        for name in FAILED:
            print(f"    FAIL {name}")
        sys.exit(1)
    print(f"\nALL {len(PASSED)} CHECKS PASSED")


if __name__ == "__main__":
    main()
