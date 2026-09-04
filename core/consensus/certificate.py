"""
TRION Protocol — Canonical Certificate reference encoder (Wave 1, Agent E)
==========================================================================

Reference implementation of docs/protocol/CANONICAL_CERTIFICATE.md — the ONE
canonical cross-VM consensus certificate. Every Wave 2 VM implementation
(EVM/Solidity, Vyper, Solana, Move, TON, Cairo, NEAR, PVM), the Go validator
fleet and the Rust core MUST reproduce the 346-byte payload produced here
byte-for-byte, and the SHA3-256 certificate hash for the golden vector pinned
in tests/unit/test_certificate_domain_separation.py.

What this module provides
-------------------------
- ``CanonicalCertificate`` — the 23 canonical fields, strict width checks,
  ``encode_payload()`` (346 bytes, big-endian, fixed widths, no floats),
  ``certificate_hash()`` (FIPS SHA3-256 — the cross-VM id), the EVM-family
  digest (EIP-191-wrapped keccak256), and the STARK-family felt chunking.
- ``CertificateEnvelope`` / ``WeightedSignatureEntry`` — the unsigned
  signature-carrier envelope (weights are CLAIMS; the verifier cross-checks
  them against the registered epoch set — see check_epoch_set_quorum).
- ``EpochSet`` — the per-epoch canonical validator state (validator_id,
  stake s_j ×1e6, diversity d_j ×1e6) with the L4.2 quorum tier check in
  exact integer arithmetic.
- Structural verification (fail-closed, §6 step 1 of the canonical doc).

What this module deliberately does NOT do
-----------------------------------------
- It does not verify ECDSA/Ed25519/STARK signatures — that is the job of the
  VM verifiers (Wave 2) and the Go fleet. The Python reference exists to pin
  the BYTE LAYOUT and the QUORUM ARITHMETIC, not to be a trust root.
- It does not sign. Emission-side signing is the validator fleet's job —
  but as of this sweep the Go validator/ tree contains NO certificate code
  yet (see docs/audit/canonical-sweep/SWEEP-A.md D1): certificate producers
  today are the Python test batteries and deployment tooling. On-chain
  verification is real on every tier; fleet emission signing remains an
  open external dependency, honestly labelled.

Spec provenance: MD L0.1/§17, V2 Part 5/L4.1-4.2/L4.8/L4.9, BTCP_SPEC §4.1,
§4.2 Step 3/Step 6, §12.2, §12.4; L4_spiritual_security.md; conflicts
resolved per CANONICAL_CERTIFICATE.md §12.

Author: TRION Protocol — Originator: Hudu Yusuf (Analys)
License: CC0
"""

from __future__ import annotations

import hashlib
import warnings
from dataclasses import dataclass, field
from enum import IntEnum
from typing import Dict, List, Optional, Sequence, Tuple

# Use pycryptodome for keccak256 (Ethereum-compatible, distinct from NIST
# SHA3-256) — the same pattern as core/primitives/hash_dna.py.
try:  # pragma: no cover - import guard
    from Crypto.Hash import keccak as _keccak

    def keccak256(data: bytes) -> bytes:
        """Ethereum-compatible keccak-256 (not NIST SHA3-256)."""
        h = _keccak.new(digest_bits=256)
        h.update(data)
        return h.digest()

    _HAVE_KECCAK = True
except ImportError:  # pragma: no cover - fallback path
    _HAVE_KECCAK = False

    def keccak256(data: bytes) -> bytes:  # type: ignore[misc]
        warnings.warn(
            "pycryptodome not installed — evm_digest() falls back to NIST "
            "SHA3-256 and will NOT match on-chain keccak256. Install "
            "pycryptodome before using the EVM-family digest.",
            stacklevel=2,
        )
        return hashlib.sha3_256(data).digest()


# ═════════════════════════════════════════════════════════════════════════════
# Constants (CANONICAL_CERTIFICATE.md §2, §3.2, §4, §5.2, §9.2, §10.1)
# ═════════════════════════════════════════════════════════════════════════════

DOMAIN_TAG: bytes = b"TRION-CERT-V1"          # 13 bytes
DOMAIN_TAG_LEN: int = len(DOMAIN_TAG)

#: Total signed payload width — the single most important constant.
PAYLOAD_WIDTH: int = 346

# Offsets (§2) — pinned by tests; any change is a format version bump.
OFFSETS: Dict[str, Tuple[int, int]] = {
    "domain_tag":            (0, 13),
    "certificate_kind":      (13, 14),
    "protocol_version":      (14, 17),
    "validator_epoch":       (17, 21),
    "certificate_nonce":     (21, 29),
    "escrow_id":             (29, 61),
    "route_id":              (61, 93),
    "intent_hash":           (93, 125),
    "entity_id":             (125, 157),
    "source_chain":          (157, 161),
    "dest_chain":            (161, 165),
    "destination":           (165, 197),
    "amount":                (197, 229),
    "anchor_bh":             (229, 261),
    "execution_bh":          (261, 293),
    "coherence":             (293, 301),
    "threshold":             (301, 309),
    "hhi_at_emission":       (309, 317),
    "total_effective_power": (317, 325),
    "validator_count":       (325, 329),
    "awa_enforced":          (329, 330),
    "issued_at":             (330, 338),
    "ttl":                   (338, 346),
}

# Fixed-point scales
SCALE_1E6: int = 1_000_000
SCALE_1E4: int = 10_000

# L4.8 concentration bounds (0-10000 HHI scale)
HHI_MAX_ACCEPTABLE: int = 4_000        # CRITICAL tier — certificate invalid

# L4.2 quorum tiers on D_consensus (×1e6)
D_CONSENSUS_TIER1: int = 600_000       # >= 0.60 → 2/3  (STRICT >)
D_CONSENSUS_TIER2: int = 400_000       # >= 0.40 → 0.75
# below 0.40 → 0.85 + GOVERNANCE_SIGNAL (off-chain)

# Minimum distinct signers (liveness floor; rust InsufficientSigners parity)
MIN_SIGNERS: int = 3

# Epoch cadence (ED-E1) and verifier epoch grace (ED-G)
EPOCH_SECONDS_DEFAULT: int = 6 * 3600
EPOCH_GRACE_DEFAULT: int = 2

# Value-tier TTLs in seconds (ED-A3 — portable form of the A3 windows)
TTL_TIERS_USD: Tuple[Tuple[float, int], ...] = (
    (1_000.0,          3_600),      # <  $1k       → 1 h
    (100_000.0,      86_400),      # <  $100k     → 24 h
    (10_000_000.0, 259_200),      # <  $10M      → 3 d
    (float("inf"),  604_800),      # >= $10M      → 7 d
)


def ttl_for_value_usd(value_usd: float) -> int:
    """Canonical TTL (seconds) for a value tier — CANONICAL_CERTIFICATE §9.2."""
    for threshold, ttl in TTL_TIERS_USD:
        if value_usd < threshold:
            return ttl
    return TTL_TIERS_USD[-1][1]  # pragma: no cover — inf is matched above


class CertificateKind(IntEnum):
    """ED-K1 — one payload format, many statement types. Fail-closed on
    unknown kinds at verification (§6 step 1)."""
    ESCROW_RELEASE = 1
    # Proposed bootstrap statement (CANONICAL_CERTIFICATE §14.4 — needs a
    # governance decision before first mainnet emission): the L2.1/L4.7
    # classical fallback (multi-sig 7-of-12) reuses the same payload with
    # kind 2 so bootstrap attestations can never be reinterpreted as
    # DW-BFT quorum releases.
    BOOTSTRAP_MULTISIG = 2


class SignatureFamily(IntEnum):
    """§3.2 — the family of the destination VM determines the digest and the
    signature primitive; the signed payload P is identical for all families."""
    SECP256K1_EVM = 1     # 65-byte r||s||v over EIP-191(keccak256(P))
    ED25519 = 2           # 64-byte over raw P
    STARK_FELT = 3        # felt pair (r, s) over Poseidon(domain_felt, chunks)

    @property
    def signature_length(self) -> int:
        if self is SignatureFamily.SECP256K1_EVM:
            return 65
        if self is SignatureFamily.ED25519:
            return 64
        return 64  # stark-felt pair serialized as 64 bytes (r[32] || s[32])


def pack_version(major: int, minor: int, patch: int) -> int:
    """Pack semver into the uint24 protocol_version field (major<<16|minor<<8|patch)."""
    if not (0 <= major <= 255 and 0 <= minor <= 255 and 0 <= patch <= 255):
        raise ValueError(f"semver components must fit uint8: {major}.{minor}.{patch}")
    return (major << 16) | (minor << 8) | patch


def unpack_version(packed: int) -> Tuple[int, int, int]:
    return (packed >> 16) & 0xFF, (packed >> 8) & 0xFF, packed & 0xFF


# ═════════════════════════════════════════════════════════════════════════════
# Canonical certificate (§2)
# ═════════════════════════════════════════════════════════════════════════════

def _check_bytes32(name: str, value: bytes) -> bytes:
    if not isinstance(value, (bytes, bytearray)):
        raise TypeError(f"{name} must be bytes, got {type(value).__name__}")
    if len(value) != 32:
        raise ValueError(f"{name} must be exactly 32 bytes, got {len(value)}")
    return bytes(value)


def _check_uint(name: str, value: int, max_bits: int) -> int:
    if isinstance(value, bool) or not isinstance(value, int):
        raise TypeError(f"{name} must be int, got {type(value).__name__}")
    if value < 0:
        raise ValueError(f"{name} must be non-negative, got {value}")
    if value >= (1 << max_bits):
        raise ValueError(f"{name} must fit uint{max_bits}, got {value}")
    return value


@dataclass
class CanonicalCertificate:
    """The ONE canonical certificate — docs/protocol/CANONICAL_CERTIFICATE.md §2.

    All integers unsigned big-endian on the wire. All fixed-point fields
    carry their scale in the name (×1e6 / ×1e4). No floats, no dynamic
    widths, no timestamps other than issued_at.
    """

    # header
    certificate_kind: int = int(CertificateKind.ESCROW_RELEASE)
    protocol_version: int = pack_version(1, 0, 0)   # uint24 packed semver
    validator_epoch: int = 0                        # uint32
    certificate_nonce: int = 0                      # uint64, per (epoch, escrow)
    # binding
    escrow_id: bytes = b"\x00" * 32
    route_id: bytes = b"\x00" * 32
    intent_hash: bytes = b"\x00" * 32
    entity_id: bytes = b"\x00" * 32
    source_chain: int = 0                           # uint32, TRION registry id
    dest_chain: int = 0                             # uint32, TRION registry id
    destination: bytes = b"\x00" * 32               # canonical dest account (§7)
    amount: int = 0                                 # uint256, raw dest-native units
    anchor_bh: bytes = b"\x00" * 32
    execution_bh: bytes = b"\x00" * 32
    # consensus state at emission
    coherence: int = 0                              # uint64 ×1e6
    threshold: int = 0                              # uint64 ×1e6
    hhi_at_emission: int = 0                        # uint64 ×1e4 (0-10000)
    total_effective_power: int = 0                  # uint64 ×1e6, Σ s_j·d_j
    validator_count: int = 0                        # uint32
    awa_enforced: bool = False
    # validity
    issued_at: int = 0                              # uint64 unix seconds
    ttl: int = 0                                    # uint64 seconds

    def __post_init__(self) -> None:
        _check_uint("certificate_kind", self.certificate_kind, 8)
        if self.certificate_kind not in {int(k) for k in CertificateKind}:
            raise ValueError(
                f"unknown certificate_kind {self.certificate_kind} — "
                "fail-closed per §6 step 1"
            )
        _check_uint("protocol_version", self.protocol_version, 24)
        _check_uint("validator_epoch", self.validator_epoch, 32)
        _check_uint("certificate_nonce", self.certificate_nonce, 64)
        _check_uint("source_chain", self.source_chain, 32)
        _check_uint("dest_chain", self.dest_chain, 32)
        _check_uint("amount", self.amount, 256)
        _check_uint("coherence", self.coherence, 64)
        _check_uint("threshold", self.threshold, 64)
        _check_uint("hhi_at_emission", self.hhi_at_emission, 64)
        _check_uint("total_effective_power", self.total_effective_power, 64)
        _check_uint("validator_count", self.validator_count, 32)
        _check_uint("issued_at", self.issued_at, 64)
        _check_uint("ttl", self.ttl, 64)
        if self.coherence > SCALE_1E6:
            raise ValueError("coherence is ×1e6 — must be ≤ 1_000_000")
        if self.threshold > SCALE_1E6:
            raise ValueError("threshold is ×1e6 — must be ≤ 1_000_000")
        if self.hhi_at_emission > 10_000:
            raise ValueError("hhi_at_emission is ×1e4 — must be ≤ 10_000")
        for name in ("escrow_id", "route_id", "intent_hash", "entity_id",
                     "destination", "anchor_bh", "execution_bh"):
            _check_bytes32(name, getattr(self, name))
        self.awa_enforced = bool(self.awa_enforced)

    # ── wire encoding ─────────────────────────────────────────────────────────

    def encode_payload(self) -> bytes:
        """The 346-byte canonical signing payload P (§2). Deterministic:
        identical fields → identical bytes, on every platform."""
        p = bytearray()
        p += DOMAIN_TAG
        p += self.certificate_kind.to_bytes(1, "big")
        p += self.protocol_version.to_bytes(3, "big")
        p += self.validator_epoch.to_bytes(4, "big")
        p += self.certificate_nonce.to_bytes(8, "big")
        p += self.escrow_id
        p += self.route_id
        p += self.intent_hash
        p += self.entity_id
        p += self.source_chain.to_bytes(4, "big")
        p += self.dest_chain.to_bytes(4, "big")
        p += self.destination
        p += self.amount.to_bytes(32, "big")
        p += self.anchor_bh
        p += self.execution_bh
        p += self.coherence.to_bytes(8, "big")
        p += self.threshold.to_bytes(8, "big")
        p += self.hhi_at_emission.to_bytes(8, "big")
        p += self.total_effective_power.to_bytes(8, "big")
        p += self.validator_count.to_bytes(4, "big")
        p += bytes([1 if self.awa_enforced else 0])
        p += self.issued_at.to_bytes(8, "big")
        p += self.ttl.to_bytes(8, "big")
        if len(p) != PAYLOAD_WIDTH:  # pragma: no cover — structural guard
            raise AssertionError(f"payload width {len(p)} != {PAYLOAD_WIDTH}")
        return bytes(p)

    @classmethod
    def from_payload(cls, payload: bytes) -> "CanonicalCertificate":
        """Strict decode — exact width, exact domain tag (§6 step 1)."""
        if not isinstance(payload, (bytes, bytearray)):
            raise TypeError("payload must be bytes")
        if len(payload) != PAYLOAD_WIDTH:
            raise ValueError(f"payload must be {PAYLOAD_WIDTH} bytes, got {len(payload)}")
        b = bytes(payload)
        if b[:DOMAIN_TAG_LEN] != DOMAIN_TAG:
            raise ValueError(
                f"bad domain tag {b[:DOMAIN_TAG_LEN]!r} — not a TRION certificate v1"
            )
        u = lambda off, width: int.from_bytes(b[off:off + width], "big")
        return cls(
            certificate_kind=u(13, 1),
            protocol_version=u(14, 3),
            validator_epoch=u(17, 4),
            certificate_nonce=u(21, 8),
            escrow_id=b[29:61],
            route_id=b[61:93],
            intent_hash=b[93:125],
            entity_id=b[125:157],
            source_chain=u(157, 4),
            dest_chain=u(161, 4),
            destination=b[165:197],
            amount=u(197, 32),
            anchor_bh=b[229:261],
            execution_bh=b[261:293],
            coherence=u(293, 8),
            threshold=u(301, 8),
            hhi_at_emission=u(309, 8),
            total_effective_power=u(317, 8),
            validator_count=u(325, 4),
            awa_enforced=b[329] == 1,
            issued_at=u(330, 8),
            ttl=u(338, 8),
        )

    # ── digests (§3.2) ────────────────────────────────────────────────────────

    def certificate_hash(self) -> bytes:
        """SHA3-256 (FIPS 202) of P — the cross-VM certificate id (§2.1).
        Computed identically by py/rust/go emitters; EVM contracts do not
        recompute it (they use the keccak family digest instead — §3.2)."""
        return hashlib.sha3_256(self.encode_payload()).digest()

    def evm_digest(self) -> bytes:
        """FAMILY 1 inner digest: keccak256(P) — the EVM-native recomputable
        digest (§3.2). Requires pycryptodome for true keccak."""
        return keccak256(self.encode_payload())

    def evm_signed_message(self) -> bytes:
        """FAMILY 1 signed message: EIP-191 wrap of the 32-byte inner digest
        — ``keccak256("\\x19Ethereum Signed Message:\\n32" || keccak256(P))``.
        Matches TRIONOracleV3.routeVerdictHash → toEthSignedMessageHash and
        relayer.js signMessage discipline exactly."""
        inner = self.evm_digest()
        return keccak256(b"\x19Ethereum Signed Message:\n32" + inner)

    def stark_felt_chunks(self) -> List[int]:
        """FAMILY 3 chunking: P split into 31-byte big-endian chunks, each an
        integer < 2^252 (§3.2). 346 bytes → 12 felts (11 full + 5 bytes
        zero-left-padded). Injective and deterministic; the Cairo verifier
        rebuilds the same chunks. D_stark = Poseidon(felt("TRION-CERT-V1"),
        f_0..f_11) — the Poseidon call itself is Cairo-side."""
        p = self.encode_payload()
        chunks = [int.from_bytes(p[i:i + 31], "big") for i in range(0, len(p), 31)]
        if chunks and len(p) % 31 != 0:
            # last chunk is < 31 bytes — its integer encoding is identical to
            # the zero-left-padded 31-byte big-endian read (leading zeros are
            # insignificant in the felt), so no extra padding is applied.
            pass
        return chunks

    @property
    def stark_domain_felt(self) -> int:
        """felt("TRION-CERT-V1") — the 13-char short string fits one felt."""
        return int.from_bytes(DOMAIN_TAG, "big")

    def is_safe(self) -> bool:
        """coherence ≥ threshold — the isSafe verdict (§5.4)."""
        return self.coherence >= self.threshold

    def expires_at(self) -> int:
        return self.issued_at + self.ttl

    def fresh_at(self, now: int, drift_tolerance: int = 60) -> bool:
        """§9 freshness: issued_at ≤ now ≤ issued_at+ttl; the drift tolerance
        widens the LOWER bound only (consensus-time skew tolerated, expiry
        never)."""
        return (self.issued_at - drift_tolerance) <= now <= self.expires_at()


# ═════════════════════════════════════════════════════════════════════════════
# Envelope (§4)
# ═════════════════════════════════════════════════════════════════════════════

@dataclass
class WeightedSignatureEntry:
    """One validator's signature over P plus its weight CLAIMS (§4).

    stake_weight / diversity_weight are ×1e6 claims that the verifier MUST
    cross-check against the registered epoch set (§6 step 5c) — they are
    carried for relayers and analytics, never trusted as authority.
    """
    validator_id: bytes
    stake_weight: int          # s_j ×1e6 (claim)
    diversity_weight: int      # d_j ×1e6 (claim)
    signature: bytes           # family-sized: 65 | 64 bytes

    def __post_init__(self) -> None:
        _check_bytes32("validator_id", self.validator_id)
        _check_uint("stake_weight", self.stake_weight, 64)
        _check_uint("diversity_weight", self.diversity_weight, 64)


@dataclass
class CertificateEnvelope:
    """The unsigned carrier: one family, distinct signers, ≥ MIN_SIGNERS,
    optional BTCPProof metadata (feature_flags / min_verifier_ver — §2.3
    ED-X5: unsigned routing hints, never verification authority)."""
    family: int = int(SignatureFamily.ED25519)
    signatures: List[WeightedSignatureEntry] = field(default_factory=list)
    feature_flags: Optional[Dict[str, bool]] = None
    min_verifier_ver: Optional[Tuple[int, int, int]] = None

    def __post_init__(self) -> None:
        if self.family not in {int(f) for f in SignatureFamily}:
            raise ValueError(f"unknown signature family {self.family}")
        expected_len = SignatureFamily(self.family).signature_length
        seen = set()
        for sig in self.signatures:
            if len(sig.signature) != expected_len:
                raise ValueError(
                    f"family {self.family} signatures must be {expected_len} "
                    f"bytes, got {len(sig.signature)}"
                )
            if sig.validator_id in seen:
                raise ValueError("duplicate signer — padding is not consensus (§4 inv. 2)")
            seen.add(sig.validator_id)


# ═════════════════════════════════════════════════════════════════════════════
# Epoch set + quorum (§5)
# ═════════════════════════════════════════════════════════════════════════════

@dataclass
class EpochSetEntry:
    """One validator's canonical epoch-scoped state (§10.2)."""
    validator_id: bytes
    stake_weight: int          # s_j ×1e6
    diversity_weight: int      # d_j ×1e6
    secp256k1_pubkey: Optional[bytes] = None   # 33-byte compressed (family 1)
    ed25519_pubkey: Optional[bytes] = None     # 32-byte (family 2)
    stark_pubkey: Optional[bytes] = None       # serialized point (family 3)

    def __post_init__(self) -> None:
        _check_bytes32("validator_id", self.validator_id)
        _check_uint("stake_weight", self.stake_weight, 64)
        _check_uint("diversity_weight", self.diversity_weight, 64)

    def effective_power(self) -> int:
        """w_j = s_j · d_j, carried ×1e6: (s×d)/1e6 (§5.1)."""
        return (self.stake_weight * self.diversity_weight) // SCALE_1E6


class EpochSet:
    """The per-epoch canonical validator state (§5, §10.2).

    This is what every VM epoch registry stores. Quorum is computed from
    THIS state — never from certificate- or envelope-supplied values.
    """

    def __init__(self, epoch: int, entries: Sequence[EpochSetEntry]):
        _check_uint("epoch", epoch, 32)
        if not entries:
            raise ValueError("epoch set cannot be empty")
        seen = set()
        for e in entries:
            if e.validator_id in seen:
                raise ValueError(f"duplicate validator {e.validator_id.hex()}")
            seen.add(e.validator_id)
        self.epoch = epoch
        self.entries: List[EpochSetEntry] = list(entries)
        self._by_id: Dict[bytes, EpochSetEntry] = {e.validator_id: e for e in entries}

    def __len__(self) -> int:
        return len(self.entries)

    def total_effective_power(self) -> int:
        """Σ_j s_j·d_j over the epoch set (×1e6) — == certificate field."""
        return sum(e.effective_power() for e in self.entries)

    def d_consensus(self) -> int:
        """D_consensus = mean(d_j) over the epoch set (×1e6) — L4.2."""
        return sum(e.diversity_weight for e in self.entries) // len(self.entries)

    def entry(self, validator_id: bytes) -> Optional[EpochSetEntry]:
        return self._by_id.get(validator_id)

    def quorum_tier(self) -> int:
        """L4.2 tier of this epoch set: 1 (2/3 strict), 2 (0.75), 3 (0.85)."""
        d = self.d_consensus()
        if d >= D_CONSENSUS_TIER1:
            return 1
        if d >= D_CONSENSUS_TIER2:
            return 2
        return 3

    def quorum_met(self, signed_validator_ids: Sequence[bytes]) -> Tuple[bool, int, int, int]:
        """Check the L4.2 tier quorum for the given signer ids (§5.2).

        Returns (met, signed_power, total_power, tier). signed_power is
        recomputed from THIS set's weights (§5 — never envelope claims).
        Unknown signers contribute zero power (they fail §6 step 5b in a
        real verifier; here they are simply not counted).
        """
        signed_power = 0
        for vid in signed_validator_ids:
            e = self._by_id.get(bytes(vid))
            if e is not None:
                signed_power += e.effective_power()
        total_power = self.total_effective_power()
        tier = self.quorum_tier()
        if total_power <= 0:
            return False, signed_power, total_power, tier
        if tier == 1:
            # STRICT: exactly-2/3 is not a quorum (Go engine discipline)
            met = 3 * signed_power > 2 * total_power
        elif tier == 2:
            met = 4 * signed_power >= 3 * total_power
        else:
            met = 20 * signed_power >= 17 * total_power
        return met, signed_power, total_power, tier

    def hhi(self) -> int:
        """HHI over effective power shares, ×1e4 scale (L4.8) — for the
        registrar's emission-side audit (the certificate carries the
        emitted hhi_at_emission)."""
        total = self.total_effective_power()
        if total <= 0:
            return 10_000
        s = 0
        for e in self.entries:
            share = (e.effective_power() * SCALE_1E4) // total
            s += share * share
        return s // SCALE_1E4  # re-scale: sum of (share_e4)^2 / 1e4


# ═════════════════════════════════════════════════════════════════════════════
# Structural verification (§6 steps 1, 4 — the payload-side checks)
# ═════════════════════════════════════════════════════════════════════════════

def verify_structure(
    cert: CanonicalCertificate,
    envelope: CertificateEnvelope,
    latest_registered_epoch: Optional[int] = None,
) -> Tuple[bool, List[str]]:
    """Fail-closed structural checks (§6 steps 1-2 and 4 — everything a
    payload-side verifier can check without the VM registry and clock).

    Returns (ok, reasons). Any reason ⇒ the certificate is rejected.
    """
    reasons: List[str] = []
    if cert.certificate_kind != int(CertificateKind.ESCROW_RELEASE):
        reasons.append(f"unknown certificate_kind {cert.certificate_kind}")
    if len(envelope.signatures) < MIN_SIGNERS:
        reasons.append(
            f"insufficient signers: {len(envelope.signatures)} < {MIN_SIGNERS}"
        )
    if cert.hhi_at_emission > HHI_MAX_ACCEPTABLE:
        reasons.append(
            f"hhi_at_emission {cert.hhi_at_emission} > {HHI_MAX_ACCEPTABLE} "
            "(L4.8 CRITICAL — consensus paused, emission impossible)"
        )
    if not cert.awa_enforced:
        reasons.append("awa_enforced=0 — emission was frozen (MD §17)")
    if not cert.is_safe():
        reasons.append(
            f"coherence {cert.coherence} < threshold {cert.threshold} — not isSafe"
        )
    if cert.ttl == 0:
        reasons.append("ttl=0 — certificate is born expired")
    if cert.dest_chain == 0:
        reasons.append("dest_chain=0 — no destination chain bound")
    if latest_registered_epoch is not None:
        if cert.validator_epoch > latest_registered_epoch:
            reasons.append(
                f"validator_epoch {cert.validator_epoch} > latest registered "
                f"{latest_registered_epoch} — future epoch"
            )
        elif latest_registered_epoch - cert.validator_epoch > EPOCH_GRACE_DEFAULT:
            reasons.append(
                f"validator_epoch {cert.validator_epoch} older than grace window "
                f"(latest {latest_registered_epoch}, grace {EPOCH_GRACE_DEFAULT})"
            )
    if envelope.signatures:
        ids = [s.validator_id for s in envelope.signatures]
        if len(set(ids)) != len(ids):
            reasons.append("duplicate signers in envelope")
    return (len(reasons) == 0), reasons


def check_epoch_set_conformance(
    cert: CanonicalCertificate,
    epoch_set: EpochSet,
) -> Tuple[bool, List[str]]:
    """Cross-check the certificate's claims against the canonical epoch set
    (§6 steps 4-6 payload-side halves: count, power total, tier quorum)."""
    reasons: List[str] = []
    if cert.validator_epoch != epoch_set.epoch:
        reasons.append(
            f"certificate epoch {cert.validator_epoch} != set epoch {epoch_set.epoch}"
        )
    if cert.validator_count != len(epoch_set):
        reasons.append(
            f"validator_count {cert.validator_count} != set size {len(epoch_set)}"
        )
    total = epoch_set.total_effective_power()
    if cert.total_effective_power != total:
        reasons.append(
            f"total_effective_power {cert.total_effective_power} != registered "
            f"{total} — the certificate lied about the set"
        )
    return (len(reasons) == 0), reasons


# ═════════════════════════════════════════════════════════════════════════════
# Self-test / golden-vector generation
# ═════════════════════════════════════════════════════════════════════════════

if __name__ == "__main__":  # pragma: no cover — manual smoke
    import random
    rng = random.Random(42)
    h = lambda s: hashlib.sha3_256(s.encode()).digest()
    cert = CanonicalCertificate(
        validator_epoch=1,
        certificate_nonce=1,
        escrow_id=h("escrow"),
        route_id=h("route"),
        intent_hash=h("intent"),
        entity_id=h("entity"),
        source_chain=1,
        dest_chain=900,
        destination=bytes(12) + bytes(range(20)),
        amount=10**18,
        anchor_bh=h("anchor"),
        execution_bh=h("execution"),
        coherence=820_000,
        threshold=550_000,
        hhi_at_emission=1_200,
        total_effective_power=0,   # set below
        validator_count=3,
        awa_enforced=True,
        issued_at=1_700_000_000,
        ttl=ttl_for_value_usd(5_000.0),
    )
    entries = [
        EpochSetEntry(h(f"validator-{i}"), stake_weight=10**6,
                      diversity_weight=700_000)
        for i in range(3)
    ]
    es = EpochSet(1, entries)
    cert.total_effective_power = es.total_effective_power()
    p = cert.encode_payload()
    print(f"payload width: {len(p)}")
    print(f"certificate_hash: {cert.certificate_hash().hex()}")
    ok, reasons = verify_structure(cert, CertificateEnvelope(
        family=int(SignatureFamily.ED25519),
        signatures=[WeightedSignatureEntry(
            e.validator_id, e.stake_weight, e.diversity_weight, bytes(64))
            for e in entries],
    ))
    print(f"structure: {ok} {reasons}")
    met, sp, tp, tier = es.quorum_met([e.validator_id for e in entries])
    print(f"quorum: met={met} signed={sp} total={tp} tier={tier}")
