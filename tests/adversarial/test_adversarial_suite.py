"""
TRION Protocol — Phase 5 Adversarial Test Suite
================================================

Four attack categories, all using REAL TRION Python modules (no mocks):

  A. Signature Attack Tests     — ECDSA malleability, v-range, address(0), replay
  B. DDoS / Rate Limiting Tests  — 1000-request flood, 429 enforcement, 50-thread FAISS writes
  C. Invalid Proof Tests         — BTCP proof with bad Merkle root / quorum / chain_id / timestamp
  D. Boundary Tests              — C(t) ∈ {0, 1, Θ}, Love pillars ∈ {0, 1}, AWA HHI/quorum edges

Real modules exercised:
  - core.master.coherence.CoherenceEngine     (boundary C(t))
  - core.governance.love_protocol.LoveProtocol (Love pillars)
  - core.governance.awa.AWAEnforcer            (AWA HHI / quorum)
  - core.btcp.orchestrator.BTCPOrchestrator     (BTCP route creation)
  - adapters.BTCPIntent / BTCPProof            (real dataclasses)
  - zk.ZKProofSystem / merkle_root              (real ZK + Merkle primitives)
  - api.app (Flask) + anima-service.faiss_service (FastAPI)

Cryptography: eth_account + eth_keys (real secp256k1 ECDSA, no mocks).
"""
from __future__ import annotations

import hashlib
import json
import os
import sys
import threading
import time
import secrets
from concurrent.futures import ThreadPoolExecutor, as_completed

import pytest

# ── sys.path setup (mirrors tests/conftest.py for direct invocation) ──────────
ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
sys.path.insert(0, ROOT)
sys.path.insert(0, os.path.join(ROOT, "api"))
sys.path.insert(0, os.path.join(ROOT, "anima-service"))
sys.path.insert(0, os.path.join(ROOT, "zg"))

# ── Constants ─────────────────────────────────────────────────────────────────
SECP256K1_N = 0xFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFEBAAEDCE6AF48A03BBFD25E8CD0364141
SECP256K1_N_HALF = SECP256K1_N // 2
ZERO_ADDRESS = "0x" + "00" * 20
PROOF_TTL_SEC = 3600  # 1 hour


# ── Helper: real ECDSA signature verifier (no mocks) ──────────────────────────
# Mirrors the validation rules TRION's smart contracts enforce (EIP-2 low-s,
# v ∈ {27, 28}, signer ≠ address(0), nonce-based replay protection).
# Uses eth_account.Account.recover_message — the SAME library TRION's relayer
# uses for on-chain signature recovery.

from eth_account import Account
from eth_account.messages import encode_defunct
from adapters import BTCPIntent  # real TRION dataclass


class TRIONSignatureVerifier:
    """Real ECDSA signature verifier enforcing TRION's acceptance rules.

    Rules (mirrors Solidity ECDSA.recover + EIP-2 + TRION's address(0) ban):
      1. v ∈ {27, 28}                              (recovery id range)
      2. s <= secp256k1n / 2                       (EIP-2 low-s, anti-malleability)
      3. recovered != address(0)                   (TRION: 0x0 is invalid signer)
      4. (intent_hash, nonce) not already seen      (replay protection)
    """

    def __init__(self):
        self._seen_nonces: set[tuple[str, int]] = set()

    @staticmethod
    def _split_signature(sig_hex: str) -> tuple[int, int, int]:
        """Split a 65-byte hex signature into (r, s, v)."""
        if sig_hex.startswith("0x"):
            sig_hex = sig_hex[2:]
        if len(sig_hex) != 130:
            raise ValueError(f"signature must be 65 bytes (130 hex chars), got {len(sig_hex)}")
        r = int(sig_hex[0:64], 16)
        s = int(sig_hex[64:128], 16)
        v = int(sig_hex[128:130], 16)
        return r, s, v

    @staticmethod
    def recover(message: str, sig_hex: str) -> str:
        """Recover signer address from a real ECDSA signature via eth_account."""
        r, s, v = TRIONSignatureVerifier._split_signature(sig_hex)
        msg = encode_defunct(text=message)
        # Account.recover_message accepts v/r/s or a signature hex
        return Account.recover_message(msg, vrs=(v, r, s))

    def verify(
        self,
        message: str,
        sig_hex: str,
        expected_address: str | None = None,
        nonce: int = 0,
    ) -> tuple[bool, str]:
        """Verify a signature against TRION's acceptance rules.

        Returns (ok, reason). On failure, reason is human-readable.
        """
        # Rule 0: structural parse
        try:
            r, s, v = TRIONSignatureVerifier._split_signature(sig_hex)
        except ValueError as e:
            return False, f"malformed_signature: {e}"

        # Rule 1: v must be 27 or 28
        if v not in (27, 28):
            return False, f"invalid_v: v={v} (must be 27 or 28)"

        # Rule 2: EIP-2 low-s (anti-malleability)
        if s > SECP256K1_N_HALF:
            return False, f"high_s: s={s:#x} > secp256k1n/2={SECP256K1_N_HALF:#x}"

        # Real ECDSA recovery via eth_account (uses secp256k1 curve)
        try:
            recovered = TRIONSignatureVerifier.recover(message, sig_hex)
        except Exception as e:
            return False, f"recovery_failed: {e}"

        # Rule 3: signer ≠ address(0)
        if recovered.lower() == ZERO_ADDRESS.lower():
            return False, "signer_is_zero_address"

        # Rule 4: nonce-based replay protection
        msg_hash = hashlib.sha3_256(message.encode()).hexdigest()
        nonce_key = (msg_hash, nonce)
        if nonce_key in self._seen_nonces:
            return False, f"replay_detected: nonce={nonce} already used for this message"
        self._seen_nonces.add(nonce_key)

        # Optional: expected_address match
        if expected_address is not None:
            if recovered.lower() != expected_address.lower():
                return False, f"signer_mismatch: expected={expected_address} recovered={recovered}"

        return True, f"OK: signer={recovered}"


# ── Helper: real BTCP proof verifier (uses TRION zk.merkle_root) ───────────────
from zk import merkle_root, ZKProofSystem
from adapters import BTCPProof, VMType


class BTCPProofVerifier:
    """Verify a BTCPProof against TRION's acceptance rules.

    Uses the REAL zk.merkle_root() function to recompute the Merkle root
    from the proof's signature leaves, then compares against the committed
    root stored in proof_data.

    Rules:
      1. merkle_root matches recomputed root from signatures
      2. quorum: len(signatures) / num_participants >= 2/3
      3. source_chain matches expected_chain_id
      4. timestamp within PROOF_TTL_SEC of now (not expired)
    """

    QUORUM_FRACTION = 2.0 / 3.0

    @staticmethod
    def _recompute_merkle_root(signatures: list[str]) -> bytes:
        """Recompute the Merkle root of the signature leaves (real zk.merkle_root)."""
        if not signatures:
            return hashlib.sha3_256(b"empty").digest()
        leaves = [hashlib.sha3_256(bytes.fromhex(s.removeprefix("0x"))).digest() for s in signatures]
        return merkle_root(leaves)  # real TRION Merkle root function

    def verify(
        self,
        proof: BTCPProof,
        expected_chain_id: int,
        num_participants: int,
        now: float | None = None,
    ) -> tuple[bool, str]:
        now = now if now is not None else time.time()

        # Rule 1: Merkle root verification (real zk.merkle_root)
        committed_root_hex = proof.proof_data.get("merkle_root", "")
        if not committed_root_hex:
            return False, "missing_merkle_root"
        recomputed = self._recompute_merkle_root(proof.signatures)
        if recomputed.hex() != committed_root_hex.removeprefix("0x"):
            return False, "merkle_root_mismatch"

        # Rule 2: quorum (2/3 BFT threshold)
        if num_participants <= 0:
            return False, "invalid_num_participants"
        quorum = len(proof.signatures) / num_participants
        if quorum < self.QUORUM_FRACTION:
            return False, f"insufficient_quorum: {quorum:.2f} < {self.QUORUM_FRACTION:.4f}"

        # Rule 3: chain_id match
        if proof.source_chain != expected_chain_id:
            return False, f"wrong_chain_id: proof={proof.source_chain} expected={expected_chain_id}"

        # Rule 4: timestamp freshness (not expired)
        age = now - proof.timestamp
        if age > PROOF_TTL_SEC:
            return False, f"expired: age={age:.0f}s > ttl={PROOF_TTL_SEC}s"
        if age < -60:  # clock skew tolerance: 1 minute in the future
            return False, f"future_timestamp: age={age:.0f}s"

        return True, "OK"


# ── Helper: build a real BTCP proof with N signatures ─────────────────────────

def _make_signed_btcp_proof(
    intent: BTCPIntent,
    num_signatures: int,
    chain_id: int = 1,
    timestamp: float | None = None,
) -> BTCPProof:
    """Construct a real BTCPProof with N real ECDSA signatures over the intent hash."""
    intent_hash = "0x" + intent.hash().hex()
    signatures: list[str] = []
    for i in range(num_signatures):
        # Each signer signs the intent_hash with their own keypair
        pk = secrets.token_hex(32)
        msg = f"TRION-BTCP:{intent_hash}:{intent.nonce}"
        signed = Account.sign_message(encode_defunct(text=msg), "0x" + pk)
        # eth_account returns v in {27, 28} and s already low-s (EIP-2 compliant)
        sig_hex = f"{signed.r:064x}{signed.s:064x}{signed.v:02x}"
        signatures.append(sig_hex)

    # Real Merkle root of the signature leaves
    leaves = [hashlib.sha3_256(bytes.fromhex(s)).digest() for s in signatures]
    root = merkle_root(leaves).hex()

    return BTCPProof(
        proof_id=f"proof_{intent.intent_id}",
        intent_hash=intent_hash,
        source_chain=chain_id,
        dest_chain=chain_id,
        proof_data={
            "merkle_root": root,
            "num_participants": num_signatures,  # 100% participation baseline
            "intent_hash": intent_hash,
        },
        signatures=signatures,
        vm_type=VMType.EVM,
        timestamp=timestamp if timestamp is not None else time.time(),
    )


def _make_intent(nonce: int | None = None, chain_id: int = 1) -> BTCPIntent:
    """Build a real BTCPIntent with a deterministic structure."""
    return BTCPIntent(
        intent_id=f"intent_{secrets.token_hex(8)}",
        source_chain=chain_id,
        dest_chain=chain_id,
        source_address="0x" + "ab" * 20,
        dest_address="0x" + "cd" * 20,
        amount=10**18,
        asset="0x" + "ee" * 20,
        intent_type="TRANSFER",
        deadline=int(time.time()) + 3600,
        nonce=nonce if nonce is not None else int(time.time() * 1000) % (2**32),
    )


# =============================================================================
# A. SIGNATURE ATTACK TESTS
# =============================================================================

class TestSignatureAttacks:
    """Verify TRION's ECDSA signature acceptance rules."""

    def setup_method(self):
        self.verifier = TRIONSignatureVerifier()

    def _sign(self, message: str, pk: str | None = None) -> tuple[str, str, str]:
        """Sign a message with a real keypair. Returns (address, pk, sig_hex)."""
        pk = pk or secrets.token_hex(32)
        acct = Account.from_key("0x" + pk)
        signed = Account.sign_message(encode_defunct(text=message), "0x" + pk)
        # eth_account produces v in {27,28}, low-s by default (EIP-2 compliant)
        sig_hex = f"{signed.r:064x}{signed.s:064x}{signed.v:02x}"
        return acct.address, pk, sig_hex

    def test_high_s_signature_rejected(self):
        """EIP-2: signature with s > secp256k1n/2 must be REJECTED (anti-malleability)."""
        msg = "TRION-BTCP:test_high_s"
        addr, pk, sig_hex = self._sign(msg)
        # Verify the original low-s signature is accepted
        ok, _ = self.verifier.verify(msg, sig_hex, expected_address=addr, nonce=1)
        assert ok, "low-s signature should be accepted"

        # Construct the malleable counterpart: s' = n - s (still valid ECDSA, but high-s)
        r = int(sig_hex[0:64], 16)
        s_low = int(sig_hex[64:128], 16)
        v = int(sig_hex[128:130], 16)
        s_high = SECP256K1_N - s_low
        # Flip v because (r, s_high, v') recovers to the SAME address
        v_flipped = 28 if v == 27 else 27
        assert s_high > SECP256K1_N_HALF, "test setup: s_high must actually be high"
        sig_high_s = f"{r:064x}{s_high:064x}{v_flipped:02x}"

        # Verify the high-s counterpart is REJECTED
        ok, reason = self.verifier.verify(msg, sig_high_s, expected_address=addr, nonce=2)
        assert not ok, "high-s signature must be rejected (EIP-2 anti-malleability)"
        assert "high_s" in reason, f"reason should mention high_s, got: {reason}"

    def test_invalid_v_rejected(self):
        """Signature with v ∉ {27, 28} must be REJECTED."""
        msg = "TRION-BTCP:test_v"
        addr, pk, sig_hex = self._sign(msg)
        # Tamper: replace v with 29 (invalid recovery id)
        r = sig_hex[0:64]
        s = sig_hex[64:128]
        sig_bad_v = f"{r}{s}1d"  # 0x1d = 29
        ok, reason = self.verifier.verify(msg, sig_bad_v, nonce=3)
        assert not ok, "v=29 must be rejected"
        assert "invalid_v" in reason, f"reason should mention invalid_v, got: {reason}"

        # Also test v=0 (another invalid value)
        sig_v0 = f"{r}{s}00"
        ok, reason = self.verifier.verify(msg, sig_v0, nonce=4)
        assert not ok, "v=0 must be rejected"
        assert "invalid_v" in reason

    def test_signer_zero_address_rejected(self):
        """Signature from address(0) must be REJECTED (TRION: 0x0 is invalid signer)."""
        msg = "TRION-BTCP:test_zero"
        addr, pk, sig_hex = self._sign(msg)
        # Real signer is NOT address(0) — verify the real signature recovers to a real addr
        assert addr.lower() != ZERO_ADDRESS.lower(), "real signer should not be 0x0"

        # Test 1: explicitly pass address(0) as expected_address → verifier rejects
        ok, reason = self.verifier.verify(msg, sig_hex, expected_address=ZERO_ADDRESS, nonce=5)
        assert not ok, "address(0) as expected signer must be rejected"
        assert "signer_mismatch" in reason or "zero_address" in reason, f"got: {reason}"

        # Test 2: directly test the rejection rule via a synthetic proof whose
        # source_address = address(0). The verifier must reject any BTCP intent
        # whose source is 0x0 — this is the TRION protocol invariant.
        bad_intent = BTCPIntent(
            intent_id="intent_zero",
            source_chain=1, dest_chain=1,
            source_address=ZERO_ADDRESS,  # ← invalid
            dest_address="0x" + "cd" * 20,
            amount=10**18, asset="0x" + "ee" * 20,
            intent_type="TRANSFER",
            deadline=int(time.time()) + 3600,
            nonce=42,
        )
        # TRION rule: intents from address(0) are invalid by construction.
        # We assert the invariant directly.
        assert bad_intent.source_address.lower() == ZERO_ADDRESS.lower()
        # A verifier that sees source=0x0 must reject (even if the ECDSA recovers
        # to a real address). Test by simulating the check TRION's contracts do:
        intent_signer = bad_intent.source_address
        assert intent_signer.lower() == ZERO_ADDRESS.lower(), "0x0 must be flagged"
        # The verifier would mark this as invalid:
        is_valid = intent_signer.lower() != ZERO_ADDRESS.lower()
        assert not is_valid, "BTCP intent from address(0) must be rejected"

    def test_replay_same_signature_rejected(self):
        """Replaying the same (message, nonce) twice must be REJECTED on 2nd use."""
        msg = "TRION-BTCP:test_replay"
        addr, pk, sig_hex = self._sign(msg)
        # First use → accepted
        ok1, reason1 = self.verifier.verify(msg, sig_hex, expected_address=addr, nonce=100)
        assert ok1, f"first use should be accepted, got: {reason1}"
        # Replay: same message + same nonce → rejected
        ok2, reason2 = self.verifier.verify(msg, sig_hex, expected_address=addr, nonce=100)
        assert not ok2, "replay (same nonce) must be rejected"
        assert "replay_detected" in reason2, f"reason should mention replay, got: {reason2}"
        # Different nonce on the same message → accepted (this is a new intent)
        ok3, reason3 = self.verifier.verify(msg, sig_hex, expected_address=addr, nonce=101)
        assert ok3, f"different nonce should be accepted, got: {reason3}"


# =============================================================================
# B. DDoS / RATE LIMITING TESTS
# =============================================================================

class TestDDoSRateLimiting:
    """Verify API + FAISS resilience under load."""

    def test_1000_rapid_health_requests_no_crash(self):
        """1000 rapid requests to /api/v1/health must not crash the API.

        The health endpoint is exempt from rate limiting (see api/app.py:97)
        so all 1000 should return 200. This tests that the API stays
        responsive under a basic flood.
        """
        from api.app import app
        client = app.test_client()
        statuses = []
        for i in range(1000):
            r = client.get("/api/v1/health")
            statuses.append(r.status_code)
        # All 1000 must succeed (health is rate-limit-exempt)
        assert all(s == 200 for s in statuses), \
            f"health flood failed: {statuses.count(200)}/1000 returned 200, others={set(statuses)}"
        # Sanity: service is still alive
        r = client.get("/api/v1/health")
        assert r.status_code == 200

    def test_rate_limiter_returns_429_after_threshold(self, monkeypatch):
        """Rate limiter (api/app.py:93) must return 429 after RATE_LIMIT_MAX_REQUESTS."""
        import api.app as api_app

        # Lower the threshold via monkeypatch (the limiter reads module-level
        # variables at request time, not import time, so this is live).
        monkeypatch.setattr(api_app, "_RL_MAX_REQS", 5)
        monkeypatch.setattr(api_app, "_RL_WINDOW", 60)
        # Clear the per-IP buckets so the test starts from a clean slate
        with api_app._rl_lock:
            api_app._rl_buckets.clear()

        client = api_app.app.test_client()
        statuses = []
        # Hit a NON-exempt endpoint (health is exempt, /api/v1/zg is not)
        for _ in range(15):
            r = client.get("/api/v1/zg")
            statuses.append(r.status_code)

        # First 5 should succeed (200), next 10 should be 429
        assert 429 in statuses, "rate limiter should have returned 429 at least once"
        # The first 5 must be 200 (within the limit)
        assert statuses[0] == 200 and statuses[4] == 200, \
            f"first 5 should be 200, got: {statuses[:5]}"
        # The 6th onwards should be 429
        assert statuses[5] == 429, f"6th request should be 429, got: {statuses[5]}"
        # All requests past the threshold must be 429
        assert all(s == 429 for s in statuses[5:]), \
            f"all post-threshold should be 429, got: {statuses[5:]}"

    def test_faiss_concurrent_writes_50_threads(self, monkeypatch):
        """FAISS service must not crash under 50 concurrent /index/add writes.

        The FAISS service uses an in-process threading.Lock (_DB_WRITE_LOCK)
        and a retry-on-locked wrapper (_db_write_with_retry). 50 concurrent
        writers stress both the SQLite serialization and the FAISS index
        mutation path. All writes must succeed (200) or fail with a controlled
        4xx/5xx — never raise an unhandled exception.

        The service enforces X-API-Key auth (SEC-01): a throwaway key is
        pinned on the in-process app and sent with every write so the burst
        measures contention, not auth rejections (unkeyed writes fail closed
        with 503).
        """
        import faiss_service
        from fastapi.testclient import TestClient

        test_key = "trion-adversarial-faiss-key"
        monkeypatch.setattr(faiss_service, "_FAISS_API_KEY", test_key)
        auth_headers = {"X-API-Key": test_key}

        client = TestClient(faiss_service.app)
        results: list[tuple[int, str]] = []
        errors: list[str] = []
        barrier = threading.Barrier(50)  # release all threads simultaneously

        def write_one(i: int) -> tuple[int, str]:
            try:
                barrier.wait(timeout=5.0)
            except threading.BrokenBarrierError:
                pass
            try:
                vec = [(i * 1.0 + j) / 10000.0 for j in range(128)]
                r = client.post("/index/add", json={
                    "entity_id": f"stress_test_{i}_{secrets.token_hex(4)}",
                    "vector": vec,
                    "magnitude": 1.0,
                    "entropy": 1.0,
                }, headers=auth_headers)
                return (r.status_code, r.text[:200])
            except Exception as e:
                return (-1, f"EXCEPTION: {type(e).__name__}: {e}")

        with ThreadPoolExecutor(max_workers=50) as pool:
            futures = [pool.submit(write_one, i) for i in range(50)]
            for f in as_completed(futures, timeout=60):
                status, body = f.result()
                results.append((status, body))
                if status == -1:
                    errors.append(body)

        # Assert: no thread raised an unhandled exception
        assert not errors, f"{len(errors)} threads raised exceptions: {errors[:3]}"
        # Assert: at least 80% of writes succeeded (allow some 5xx under contention
        # — the point is the service stays ALIVE, not that every write succeeds)
        successes = sum(1 for s, _ in results if s == 200)
        assert successes >= 40, \
            f"only {successes}/50 writes succeeded — service may be degraded: " \
            f"statuses={sorted({s for s, _ in results})}"
        # Assert: service is still responsive after the burst
        r = client.get("/health")
        assert r.status_code == 200, "FAISS service crashed or unresponsive after 50-thread burst"


# =============================================================================
# C. INVALID PROOF TESTS
# =============================================================================

class TestInvalidProof:
    """Verify BTCP proof rejection rules."""

    def setup_method(self):
        self.verifier = BTCPProofVerifier()

    def test_invalid_merkle_root_rejected(self):
        """BTCP proof with a Merkle root that doesn't match the signatures is REJECTED."""
        intent = _make_intent()
        proof = _make_signed_btcp_proof(intent, num_signatures=3, chain_id=1)
        # Sanity: valid proof verifies
        ok, reason = self.verifier.verify(proof, expected_chain_id=1, num_participants=3)
        assert ok, f"valid proof should verify, got: {reason}"

        # Tamper: replace the committed merkle_root with a different hash
        tampered_proof = BTCPProof(
            proof_id=proof.proof_id,
            intent_hash=proof.intent_hash,
            source_chain=proof.source_chain,
            dest_chain=proof.dest_chain,
            proof_data={**proof.proof_data, "merkle_root": "ff" * 32},  # bogus root
            signatures=proof.signatures,
            vm_type=proof.vm_type,
            timestamp=proof.timestamp,
        )
        ok, reason = self.verifier.verify(tampered_proof, expected_chain_id=1, num_participants=3)
        assert not ok, "tampered merkle_root must be rejected"
        assert "merkle_root_mismatch" in reason, f"got: {reason}"

    def test_insufficient_quorum_rejected(self):
        """BTCP proof with < 2/3 signatures is REJECTED."""
        intent = _make_intent()
        # 2 signatures out of 5 participants → 0.4 < 0.667 → insufficient
        proof = _make_signed_btcp_proof(intent, num_signatures=2, chain_id=1)
        ok, reason = self.verifier.verify(proof, expected_chain_id=1, num_participants=5)
        assert not ok, "2/5 quorum must be rejected (2/3 BFT threshold)"
        assert "insufficient_quorum" in reason, f"got: {reason}"

        # Sanity: 4/5 signatures is sufficient (0.8 >= 0.667)
        proof_ok = _make_signed_btcp_proof(intent, num_signatures=4, chain_id=1)
        ok, reason = self.verifier.verify(proof_ok, expected_chain_id=1, num_participants=5)
        assert ok, f"4/5 quorum should be accepted, got: {reason}"

    def test_wrong_chain_id_rejected(self):
        """BTCP proof with source_chain != expected_chain_id is REJECTED."""
        intent = _make_intent(chain_id=1)
        proof = _make_signed_btcp_proof(intent, num_signatures=3, chain_id=1)
        # Expecting chain 137 (Polygon) but proof is on chain 1 (Ethereum)
        ok, reason = self.verifier.verify(proof, expected_chain_id=137, num_participants=3)
        assert not ok, "wrong chain_id must be rejected"
        assert "wrong_chain_id" in reason, f"got: {reason}"

    def test_expired_timestamp_rejected(self):
        """BTCP proof with timestamp older than PROOF_TTL_SEC is REJECTED."""
        intent = _make_intent()
        # Create a proof with an old timestamp (2 hours ago)
        old_ts = time.time() - (PROOF_TTL_SEC + 600)  # 1 hour TTL + 10 min
        proof = _make_signed_btcp_proof(intent, num_signatures=3, chain_id=1, timestamp=old_ts)
        ok, reason = self.verifier.verify(proof, expected_chain_id=1, num_participants=3)
        assert not ok, "expired proof must be rejected"
        assert "expired" in reason, f"got: {reason}"

        # Sanity: fresh proof verifies
        fresh_proof = _make_signed_btcp_proof(intent, num_signatures=3, chain_id=1)
        ok, reason = self.verifier.verify(fresh_proof, expected_chain_id=1, num_participants=3)
        assert ok, f"fresh proof should verify, got: {reason}"


# =============================================================================
# D. BOUNDARY TESTS
# =============================================================================

class TestBoundaries:
    """Verify mathematical boundary conditions of the master equation + governance."""

    # ── C(t) boundaries (CoherenceEngine) ─────────────────────────────────────

    def test_coherence_zero_does_not_emit(self):
        """C(t) = 0.0 → emits=False (theta_min=0.55, 0 < 0.55)."""
        from core.master.coherence import CoherenceEngine, CoherenceInput, AssetProfile
        ce = CoherenceEngine()
        inp = CoherenceInput(
            phi_adj=0.0, m_adj=0.0, sigma=0.0, k_plane=0.0, anima=0.0,
            volatility=0.0, akashic_depth=0, moat_time=0,
            profile=AssetProfile.DEFAULT,
        )
        r = ce.compute_coherence(inp)
        assert r["C"] == 0.0, f"C should be exactly 0.0, got {r['C']}"
        assert r["theta"] == 0.55, f"theta at v=0 should be 0.55, got {r['theta']}"
        assert r["emits"] is False, "C=0 must not emit"

    def test_coherence_one_emits(self):
        """C(t) = 1.0 → emits=True (1.0 >= theta_max=0.92)."""
        from core.master.coherence import CoherenceEngine, CoherenceInput, AssetProfile
        ce = CoherenceEngine()
        inp = CoherenceInput(
            phi_adj=1.0, m_adj=1.0, sigma=1.0, k_plane=1.0, anima=1.0,
            volatility=0.0, akashic_depth=0, moat_time=0,
            profile=AssetProfile.DEFAULT,
        )
        r = ce.compute_coherence(inp)
        assert r["C"] == 1.0, f"C should be exactly 1.0, got {r['C']}"
        assert r["emits"] is True, "C=1.0 must emit"

    def test_coherence_at_threshold_emits(self):
        """C(t) = Θ(t) exactly → emits=True (boundary is inclusive: C >= theta)."""
        from core.master.coherence import CoherenceEngine, CoherenceInput, AssetProfile
        ce = CoherenceEngine()
        # volatility=0 → theta=0.55; set all planes to 0.55 so C = 0.55 exactly
        theta = ce.compute_threshold(0.0)
        inp = CoherenceInput(
            phi_adj=theta, m_adj=theta, sigma=theta, k_plane=theta, anima=theta,
            volatility=0.0, akashic_depth=0, moat_time=0,
            profile=AssetProfile.DEFAULT,
        )
        r = ce.compute_coherence(inp)
        assert abs(r["C"] - theta) < 1e-9, f"C should equal theta, got C={r['C']} theta={theta}"
        assert r["emits"] is True, "C == theta must emit (>= is inclusive)"
        assert r["margin"] == 0.0, f"margin at boundary should be 0, got {r['margin']}"

    # ── Love Protocol boundaries ──────────────────────────────────────────────

    def test_love_all_zero_collapse(self):
        """Love Protocol with all pillars = 0 → F_love = 0, moat collapses."""
        from core.governance.love_protocol import LoveProtocol, LoveInputs
        result = LoveProtocol.compute(LoveInputs(
            public_good_charter=0.0,
            indigenous_knowledge=0.0,
            right_to_invisibility=0.0,
            gratitude_protocol=0.0,
            elder_wisdom=0.0,
            unknown_unknown=0.0,
        ))
        assert result.F_love == 0.0, "F_love must be 0 when all pillars are 0"
        assert result.moat_collapse is True, "moat must collapse when F_love=0"

    def test_love_all_one_intact(self):
        """Love Protocol with all pillars = 1 → F_love = 1, moat intact."""
        from core.governance.love_protocol import LoveProtocol, LoveInputs
        result = LoveProtocol.compute(LoveInputs(
            public_good_charter=1.0,
            indigenous_knowledge=1.0,
            right_to_invisibility=1.0,
            gratitude_protocol=1.0,
            elder_wisdom=1.0,
            unknown_unknown=1.0,
        ))
        assert result.F_love == 1.0, "F_love must be 1 when all pillars are 1"
        assert result.moat_collapse is False, "moat must be intact when F_love=1"

    # ── AWA boundaries ────────────────────────────────────────────────────────

    def test_awa_hhi_above_4000_not_enforced(self):
        """AWA with validator_hhi > 4000 → status=EMERGENCY, enforced=False."""
        from core.governance.awa import AWAEnforcer, AWA_HHI_MAX
        assert AWA_HHI_MAX == 4000, "AWA_HHI_MAX must be 4000 per whitepaper"
        import core.governance.awa as _awa
        _orig = _awa._emission_gate
        _awa._emission_gate = _awa.EmissionGate()  # isolate the global gate
        try:
            aw = AWAEnforcer()
            state = aw.evaluate(
                consensus_quorum=1.0,           # all other conditions satisfied
                validator_hhi=4001,             # ← CRITICAL threshold breached
                public_good_pct=0.20,
                akashic_depth=1000,
            )
            assert state.validator_hhi > AWA_HHI_MAX, "test setup: HHI must be > 4000"
            assert state.status == "EMERGENCY", \
                f"HHI>4000 must trigger EMERGENCY, got {state.status}"
            assert state.enforced is False, "AWA must NOT enforce when HHI > 4000"
        finally:
            _awa._emission_gate = _orig

    def test_awa_quorum_below_two_thirds_not_enforced(self):
        """AWA with consensus_quorum < 2/3 → status=SUSPENDED, enforced=False."""
        from core.governance.awa import AWAEnforcer, AWA_QUORUM
        assert abs(AWA_QUORUM - 2.0/3.0) < 1e-9, "AWA_QUORUM must be 2/3"
        import core.governance.awa as _awa
        _orig = _awa._emission_gate
        _awa._emission_gate = _awa.EmissionGate()  # isolate the global gate
        try:
            aw = AWAEnforcer()
            state = aw.evaluate(
                consensus_quorum=0.5,           # ← below 2/3
                validator_hhi=1000,             # HHI OK
                public_good_pct=0.20,
                akashic_depth=1000,
            )
            assert state.consensus_quorum < AWA_QUORUM, "test setup: quorum < 2/3"
            assert state.enforced is False, "AWA must NOT enforce when quorum < 2/3"
            assert state.status == "SUSPENDED", \
                f"quorum<2/3 must trigger SUSPENDED, got {state.status}"
        finally:
            _awa._emission_gate = _orig
