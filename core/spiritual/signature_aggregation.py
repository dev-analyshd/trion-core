"""
TRION Protocol — L4.5 / L4.7
Real Validator Signature Aggregation (BLS-like on secp256k1)
============================================================

Implements real signature aggregation for Diversity-Weighted BFT consensus.
Because ``py-bls`` is not installed, this module uses Schnorr multisig
on secp256k1 (the Bellare-Neven / MuSig construction) which provides
BLS-equivalent aggregation semantics: a single aggregate signature
verifies the entire validator cohort in one pairing-free equation.

Construction
------------
Each validator i signs message M with private key x_i:
    1. pick random nonce k_i  (k_i ∈ [1, n-1])
    2. R_i = k_i · G
    3. challenge e_i = H(R_i ‖ M ‖ pk_i)   (per-signer challenge, MuSig-style)
    4. response s_i = k_i + e_i · x_i   (mod n)
    5. individual signature: σ_i = (R_i, s_i)

Verify individual:
    s_i · G == R_i + e_i · pk_i

Aggregate (linear combination — the key BLS property):
    s_agg = Σ s_i   (mod n)
    R_agg = Σ R_i   (curve-point sum)

Verify aggregate:
    s_agg · G == R_agg + Σ (e_i · pk_i)

This is correct because each s_i · G = R_i + e_i · pk_i, hence
    Σ s_i · G = Σ R_i + Σ e_i · pk_i

i.e. one scalar mult + (n+1) point adds to verify n signers.

API
---
    ValidatorSignatureAggregator.sign(message, private_key)   -> dict
    ValidatorSignatureAggregator.verify(signature, message, public_key)  -> bool
    ValidatorSignatureAggregator.aggregate(signatures, messages)  -> dict
    ValidatorSignatureAggregator.verify_aggregate(agg_sig, messages, public_keys) -> bool
    ValidatorSignatureAggregator.generate_keypair()  -> (private_key, public_key)

Author: TRION Protocol — Originator: Hudu Yusuf (Analys)
License: CC0
"""

from __future__ import annotations

import hashlib
import secrets
from typing import Any, Dict, List, Tuple

import ecdsa
from ecdsa import SECP256k1, SigningKey, VerifyingKey
from ecdsa.ellipticcurve import PointJacobi, INFINITY


# ── Curve constants ──────────────────────────────────────────────────────────

_CURVE = SECP256k1
_CURVE_NAME = "secp256k1"
_GENERATOR_G = _CURVE.generator
_CURVE_ORDER_N = _CURVE.order
_CURVE_FIELD_P = _CURVE.curve.p()


def _sha3_256(data: bytes) -> bytes:
    return hashlib.sha3_256(data).digest()


def _hash_to_scalar(data: bytes) -> int:
    """SHA3-256 → int mod n (per-signer Fiat-Shamir challenge)."""
    return int.from_bytes(_sha3_256(data), "big") % _CURVE_ORDER_N


def _random_scalar() -> int:
    """Cryptographically secure uniform random scalar in [1, n-1]."""
    while True:
        s = int.from_bytes(secrets.token_bytes(32), "big") % _CURVE_ORDER_N
        if s != 0:
            return s


def _encode_point_compressed(P: PointJacobi) -> bytes:
    """SEC1 compressed encoding: 0x02|0x03 ‖ x (33 bytes total)."""
    if P == INFINITY:
        return b"\x00" * 33
    x = P.x()
    y = P.y()
    prefix = 0x02 if (y % 2 == 0) else 0x03
    return bytes([prefix]) + x.to_bytes(32, "big")


def _decode_point_compressed(data: bytes) -> PointJacobi:
    """Decompress SEC1 33-byte point encoding."""
    if len(data) != 33:
        raise ValueError(f"expected 33 bytes, got {len(data)}")
    if data == b"\x00" * 33:
        return INFINITY
    prefix = data[0]
    if prefix not in (0x02, 0x03):
        raise ValueError(f"invalid prefix 0x{prefix:02x}")
    x = int.from_bytes(data[1:], "big")
    p = _CURVE_FIELD_P
    a = _CURVE.curve.a()
    b = _CURVE.curve.b()
    y_sq = (pow(x, 3, p) + a * x + b) % p
    y = pow(y_sq, (p + 1) // 4, p)
    if (y * y) % p != y_sq:
        raise ValueError("point not on curve")
    if (y % 2) != (prefix - 2):
        y = p - y
    return PointJacobi(_CURVE.curve, x, y, 1, _CURVE_ORDER_N)


# ── ValidatorSignatureAggregator ────────────────────────────────────────────

class ValidatorSignatureAggregator:
    """Real BLS-like signature aggregation on secp256k1 (Schnorr multisig).

    Public-key lifecycle: pass private_key as raw 32-byte big-endian scalar;
    pass public_key as 33-byte compressed encoding (or hex string).
    """

    CURVE = _CURVE_NAME
    HASH = "sha3-256"
    PROOF_SYSTEM = "schnorr-musig-bls-like"
    VERSION = "1.0.0"

    # ── Key management ──────────────────────────────────────────────────────

    @staticmethod
    def generate_keypair() -> Tuple[bytes, bytes]:
        """Generate a fresh (private_key, public_key) pair.

        private_key: 32-byte big-endian scalar
        public_key:  33-byte compressed curve point
        """
        sk = SigningKey.generate(curve=_CURVE)
        priv_bytes = sk.to_string()
        pub_bytes = sk.get_verifying_key().to_string(encoding="compressed")
        return priv_bytes, pub_bytes

    @staticmethod
    def _priv_to_pub(private_key: bytes) -> bytes:
        """Derive the compressed public key from a private key scalar."""
        sk = SigningKey.from_string(private_key, curve=_CURVE)
        return sk.get_verifying_key().to_string(encoding="compressed")

    @staticmethod
    def _coerce_pubkey(pk: Any) -> bytes:
        """Accept bytes or hex string; return 33-byte compressed form."""
        if isinstance(pk, str):
            pk = bytes.fromhex(pk.removeprefix("0x"))
        if len(pk) == 65 and pk[0] == 0x04:
            # Uncompressed → compress
            x = int.from_bytes(pk[1:33], "big")
            y = int.from_bytes(pk[33:65], "big")
            prefix = 0x02 if (y % 2 == 0) else 0x03
            pk = bytes([prefix]) + pk[1:33]
        return pk

    # ── Per-signer challenge (Fiat-Shamir) ───────────────────────────────────

    @staticmethod
    def _challenge(R_point: PointJacobi, message: bytes, public_key: bytes) -> int:
        """e_i = H(R_i ‖ M ‖ pk_i)   (per-signer MuSig-style challenge)."""
        return _hash_to_scalar(
            b"TRION-SCHNORR-v1"
            + _encode_point_compressed(R_point)
            + message
            + public_key
        )

    # ── sign ─────────────────────────────────────────────────────────────────

    def sign(self, message: bytes, private_key: bytes) -> Dict[str, Any]:
        """Produce a Schnorr signature over ``message`` with ``private_key``.

        Returns dict:
            {
              "r":  hex of x-coord of R  (32 bytes hex),
              "s":  hex of scalar response s  (32 bytes hex),
              "v":  parity byte (0 or 1) for y-coord of R,
              "public_key": hex of compressed public key (33 bytes hex),
            }
        """
        if not isinstance(message, (bytes, bytearray)):
            raise TypeError("message must be bytes")
        x = int.from_bytes(private_key, "big") % _CURVE_ORDER_N
        if x == 0:
            raise ValueError("private_key must be non-zero mod n")
        public_key = self._priv_to_pub(private_key)

        # 1. pick random nonce k
        k = _random_scalar()
        R = k * _GENERATOR_G

        # 2. challenge
        e = self._challenge(R, bytes(message), public_key)

        # 3. response  s = k + e·x  mod n
        s = (k + e * x) % _CURVE_ORDER_N

        return {
            "r": hex(R.x()),
            "s": hex(s),
            "v": int(R.y() % 2),
            "public_key": public_key.hex(),
        }

    # ── verify ──────────────────────────────────────────────────────────────

    def verify(self, signature: Dict[str, Any], message: bytes,
               public_key: bytes) -> bool:
        """Verify an individual signature.

        Checks  s·G == R + e·pk  where  e = H(R ‖ M ‖ pk).
        """
        try:
            r_int = int(signature["r"], 16) if isinstance(signature["r"], str) \
                else int(signature["r"])
            s_int = int(signature["s"], 16) if isinstance(signature["s"], str) \
                else int(signature["s"])
            v = int(signature["v"])
            pk_bytes = self._coerce_pubkey(public_key)

            # Reconstruct R from (r, v)
            x = r_int
            p = _CURVE_FIELD_P
            a = _CURVE.curve.a()
            b = _CURVE.curve.b()
            y_sq = (pow(x, 3, p) + a * x + b) % p
            y = pow(y_sq, (p + 1) // 4, p)
            if (y * y) % p != y_sq:
                return False
            if (y % 2) != v:
                y = p - y
            R = PointJacobi(_CURVE.curve, x, y, 1, _CURVE_ORDER_N)

            # Recover public key point
            pk_point = _decode_point_compressed(pk_bytes)

            # Recompute challenge
            e = self._challenge(R, bytes(message), pk_bytes)

            # Verify s·G == R + e·pk
            lhs = s_int * _GENERATOR_G
            rhs = R + e * pk_point
            return lhs == rhs
        except Exception:
            return False

    # ── aggregate ────────────────────────────────────────────────────────────

    def aggregate(
        self,
        signatures: List[Dict[str, Any]],
        messages: List[bytes],
    ) -> Dict[str, Any]:
        """Aggregate a list of signatures over their respective messages.

        Returns an aggregate signature dict:
            {
              "s_agg":          hex of Σ s_i  (32 bytes hex),
              "r_agg":          hex of x-coord of Σ R_i  (32 bytes hex),
              "v_agg":          parity byte of Σ R_i  y-coord,
              "components":     list of per-signer (r, v, public_key, message_hash),
              "signer_count":   n,
              "scheme":         "schnorr-musig-bls-like",
              "curve":          "secp256k1",
              "hash":           "sha3-256",
              "version":        "1.0.0",
            }
        """
        if len(signatures) != len(messages):
            raise ValueError(
                f"signatures/messages length mismatch: "
                f"{len(signatures)} vs {len(messages)}"
            )
        if not signatures:
            raise ValueError("cannot aggregate empty signature list")

        s_sum = 0
        R_sum: PointJacobi = INFINITY
        components = []
        for sig, msg in zip(signatures, messages):
            r_int = int(sig["r"], 16) if isinstance(sig["r"], str) else int(sig["r"])
            s_int = int(sig["s"], 16) if isinstance(sig["s"], str) else int(sig["s"])
            v = int(sig["v"])
            pk_hex = sig.get("public_key", "")
            # Reconstruct R_i
            x = r_int
            p = _CURVE_FIELD_P
            a = _CURVE.curve.a()
            b = _CURVE.curve.b()
            y_sq = (pow(x, 3, p) + a * x + b) % p
            y = pow(y_sq, (p + 1) // 4, p)
            if (y * y) % p != y_sq:
                raise ValueError(f"invalid R for signer {len(components)}")
            if (y % 2) != v:
                y = p - y
            R_i = PointJacobi(_CURVE.curve, x, y, 1, _CURVE_ORDER_N)

            s_sum = (s_sum + s_int) % _CURVE_ORDER_N
            R_sum = R_sum + R_i

            components.append({
                "r": hex(r_int),
                "v": v,
                "public_key": pk_hex,
                "message_hash": _sha3_256(bytes(msg)).hex(),
            })

        # Encode aggregate point
        if R_sum == INFINITY:
            r_agg = 0
            v_agg = 0
        else:
            r_agg = R_sum.x()
            v_agg = int(R_sum.y() % 2)

        return {
            "s_agg":        hex(s_sum),
            "r_agg":        hex(r_agg),
            "v_agg":        v_agg,
            "components":   components,
            "signer_count": len(signatures),
            "scheme":       self.PROOF_SYSTEM,
            "curve":        self.CURVE,
            "hash":         self.HASH,
            "version":      self.VERSION,
        }

    # ── verify_aggregate ─────────────────────────────────────────────────────

    def verify_aggregate(
        self,
        agg_sig: Dict[str, Any],
        messages: List[bytes],
        public_keys: List[bytes],
    ) -> bool:
        """Verify an aggregate signature.

        Checks  s_agg·G == Σ R_i + Σ e_i·pk_i   for all signers.

        Also enforces that:
          - the message list and public key list have the same length,
          - the signer_count matches len(components),
          - each provided public key matches the corresponding component.
        """
        try:
            s_agg = int(agg_sig["s_agg"], 16) if isinstance(agg_sig["s_agg"], str) \
                else int(agg_sig["s_agg"])
            components = agg_sig["components"]
            if len(components) != len(messages):
                return False
            if len(messages) != len(public_keys):
                return False
            if len(components) == 0:
                return False
            if agg_sig.get("signer_count") != len(components):
                return False

            R_sum: PointJacobi = INFINITY
            pk_weighted_sum: PointJacobi = INFINITY  # Σ e_i · pk_i

            for comp, msg, pk_in in zip(components, messages, public_keys):
                r_int = int(comp["r"], 16)
                v = int(comp["v"])
                pk_bytes = self._coerce_pubkey(pk_in)
                # Confirm component's stored public_key matches the provided one
                if comp.get("public_key") and bytes.fromhex(comp["public_key"]) != pk_bytes:
                    return False

                # Reconstruct R_i
                x = r_int
                p = _CURVE_FIELD_P
                a = _CURVE.curve.a()
                b = _CURVE.curve.b()
                y_sq = (pow(x, 3, p) + a * x + b) % p
                y = pow(y_sq, (p + 1) // 4, p)
                if (y * y) % p != y_sq:
                    return False
                if (y % 2) != v:
                    y = p - y
                R_i = PointJacobi(_CURVE.curve, x, y, 1, _CURVE_ORDER_N)

                pk_i = _decode_point_compressed(pk_bytes)
                e_i = self._challenge(R_i, bytes(msg), pk_bytes)

                R_sum = R_sum + R_i
                pk_weighted_sum = pk_weighted_sum + (e_i * pk_i)

            # Check s_agg · G == R_sum + pk_weighted_sum
            lhs = s_agg * _GENERATOR_G
            rhs = R_sum + pk_weighted_sum
            return lhs == rhs
        except Exception:
            return False

    # ── Quorum helpers (used by BTCPProofBuilder) ────────────────────────────

    @staticmethod
    def threshold_met(signer_count: int, total_validators: int,
                      quorum_fraction: float = 2.0 / 3.0) -> bool:
        """Return True iff signer_count/total_validators ≥ quorum_fraction."""
        if total_validators <= 0:
            return False
        return (signer_count / total_validators) >= quorum_fraction


# ── Self-test ────────────────────────────────────────────────────────────────

if __name__ == "__main__":
    agg = ValidatorSignatureAggregator()

    # Generate keys for 5 validators
    keys = [agg.generate_keypair() for _ in range(5)]
    priv_keys = [k[0] for k in keys]
    pub_keys = [k[1] for k in keys]

    # Each validator signs a different message
    messages = [f"intent:{i}".encode() for i in range(5)]

    print("── Individual sign + verify ──────────────────────")
    sigs = []
    for i, (priv, pub, msg) in enumerate(zip(priv_keys, pub_keys, messages)):
        sig = agg.sign(msg, priv)
        ok = agg.verify(sig, msg, pub)
        sigs.append(sig)
        print(f"  validator {i}: r={sig['r'][:10]}… s={sig['s'][:10]}… verified={ok}")
        assert ok, f"individual verify failed for validator {i}"

    # Tamper test
    bad_sig = dict(sigs[0])
    bad_sig["s"] = hex(int(sigs[0]["s"], 16) ^ 1)
    assert not agg.verify(bad_sig, messages[0], pub_keys[0]), \
        "tampered signature must FAIL verification"
    print("  tampered signature rejected: ✓")

    print("\n── Aggregate sign + verify ───────────────────────")
    agg_sig = agg.aggregate(sigs, messages)
    print(f"  signer_count: {agg_sig['signer_count']}")
    print(f"  s_agg: {agg_sig['s_agg'][:14]}…")
    print(f"  r_agg: {agg_sig['r_agg'][:14]}…")
    ok = agg.verify_aggregate(agg_sig, messages, pub_keys)
    print(f"  verify_aggregate: {ok}")
    assert ok, "aggregate verification failed"

    # Quorum test (2/3 threshold: 4/5 = 0.8 passes, 3/5 = 0.6 fails)
    print("\n── Quorum threshold ─────────────────────────────────────────────")
    print(f"  4/5 signers (need 2/3 ≈ {2.0/3.0:.4f}): {agg.threshold_met(4, 5)}")
    print(f"  3/5 signers (need 2/3): {agg.threshold_met(3, 5)}")
    assert agg.threshold_met(4, 5)
    assert not agg.threshold_met(3, 5)

    # Mismatched pubkeys must fail
    wrong_pks = list(pub_keys)
    wrong_pks[0], wrong_pks[1] = wrong_pks[1], wrong_pks[0]
    assert not agg.verify_aggregate(agg_sig, messages, wrong_pks), \
        "mismatched public key order must FAIL"

    print("\nValidatorSignatureAggregator: ALL PASS")
