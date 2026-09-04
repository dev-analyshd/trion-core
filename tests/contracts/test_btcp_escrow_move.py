"""
btcp_escrow.move — canonical certificate verification mirror + attack matrix
(Wave 2, Agent I — closure of audit finding C-02).

There is no Move toolchain in this environment (external-toolchain policy).
This file is therefore TWO things:

  1. A byte-faithful PYTHON MIRROR of the Move program's validation logic
     (trion::canonical_cert + trion::epoch_registry + trion::btcp_escrow):
     the same §6 verification order, the same error codes, the same
     integer arithmetic (u64/u128, floor division), the same state
     machine. Certificates are built with the REAL reference encoder
     (core/consensus/certificate.py) and signed with REAL Ed25519 keys
     (cryptography.hazmat — RFC 8032 PureEdDSA, the exact primitive
     aptos_std::ed25519::signature_verify_strict verifies on-chain).

  2. STATIC SOURCE ASSERTIONS over contracts/move/sources/*.move — the
     checks the .move code must textually contain (native ed25519 call,
     registered-key lookup, tier quorum math, u128, grace, derived
     escrow_id binding, @trion init) and the C-02 regression surface
     that must textally NOT exist (coherence_verified, verify_coherence,
     any dev-mode release path).

Attack matrix (every row must fail closed with the exact Move error):
  structure (width/tag/kind/version/scales/hhi/awa/isSafe/ttl),
  envelope (<3 signers, dup signer, wrong sig width),
  epoch (unknown / future / stale-beyond-grace),
  freshness (expired / future beyond 60 s drift),
  weight claims (lied s_j or d_j),
  signatures (unregistered signer, bad signature bytes),
  quorum (below tier bar, EXACTLY-2/3 at tier 1 — strict),
  binding (escrow_id / route / intent / entity / source chain /
  dest chain / destination / amount / amount-too-large / anchor /
  execution BH),
  escrow-local gate (cert coherence below escrow min_coherence),
  nonce/replay (older nonce, different-hash resubmission on terminal),
  pause bypass, double release, release on REVERTED,
  lock-time INV-003 (sub-floor min_coherence rejected at lock).

Run:  python3 -m pytest tests/contracts/test_btcp_escrow_move.py -q
  or:  python3 -m tests.contracts.test_btcp_escrow_move   (from repo root)
"""

import hashlib
import importlib.util
import os
import sys
import traceback

from cryptography.hazmat.primitives.asymmetric.ed25519 import (
    Ed25519PrivateKey,
    Ed25519PublicKey,
)
from cryptography.hazmat.primitives.serialization import (
    Encoding,
    PublicFormat,
)

from core.consensus.certificate import (
    CanonicalCertificate,
    CertificateEnvelope,
    CertificateKind,
    EpochSet,
    EpochSetEntry,
    SignatureFamily,
    WeightedSignatureEntry,
    pack_version,
    ttl_for_value_usd,
    verify_structure as py_verify_structure,
    check_epoch_set_conformance,
)

REPO = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
MOVE_SOURCES = os.path.join(REPO, "contracts", "move", "sources")

PASSED = []
FAILED = []


def check(name, cond, detail=""):
    (PASSED if cond else FAILED).append(name)
    print(f"  {'OK' if cond else 'FAIL'} {name}" + (f" — {detail}" if detail and not cond else ""))


_h = lambda s: hashlib.sha3_256(s.encode()).digest()


# ═══════════════════════════════════════════════════════════════════════
# Error-code twins (exact mirrors of the .move constants)
# ═══════════════════════════════════════════════════════════════════════

class CertErr:
    """trion::canonical_cert error codes."""
    E_PAYLOAD_WIDTH = 1
    E_DOMAIN_TAG = 2
    E_UNKNOWN_KIND = 3
    E_VERSION = 4
    E_TTL_ZERO = 5
    E_TTL_TOO_LONG = 6
    E_NO_DEST_CHAIN = 7
    E_AWA_NOT_ENFORCED = 8
    E_HHI_CRITICAL = 9
    E_COHERENCE_SCALE = 10
    E_THRESHOLD_SCALE = 11
    E_NOT_SAFE = 12
    E_RANGE = 13


class RegErr:
    """trion::epoch_registry error codes."""
    E_NOT_MODULE_ACCOUNT = 1
    E_ALREADY_INITIALIZED = 2
    E_REGISTRY_NOT_INITIALIZED = 3
    E_NO_ADMIN_CAP = 4
    E_EPOCH_ORDER = 5
    E_TOO_FEW_VALIDATORS = 6
    E_ENTRY_WIDTH = 7
    E_PARALLEL_WIDTHS = 8
    E_DUPLICATE_VALIDATOR = 9
    E_WEIGHT_SCALE = 10
    E_EPOCH_UNKNOWN = 11
    E_EPOCH_FUTURE = 12
    E_EPOCH_STALE = 13
    E_INSUFFICIENT_SIGNERS = 14
    E_SIG_WIDTH = 15
    E_DUPLICATE_SIGNER = 16
    E_VALIDATOR_NOT_REGISTERED = 17
    E_WEIGHT_CLAIM_MISMATCH = 18
    E_BAD_SIGNATURE = 19
    E_QUORUM_NOT_MET = 20
    E_COUNT_LIE = 21
    E_POWER_LIE = 22
    E_NOT_FRESH = 23


class EscErr:
    """trion::btcp_escrow error codes."""
    E_NOT_FOUND = 1
    E_INVALID_STATE = 2
    E_ZERO_AMOUNT = 3
    E_EMERGENCY_NOT_YET = 4
    E_NOT_RELAYER = 5
    E_PAUSED = 6
    E_NOT_INITIALIZED = 7
    E_NOT_MODULE_ACCOUNT = 8
    E_ALREADY_INITIALIZED = 9
    E_NO_ADMIN_CAP = 10
    E_FIELD_WIDTH = 11
    E_TIMEOUT_BOUNDS = 12
    E_COHERENCE_FLOOR = 13
    E_COHERENCE_CAP = 14
    E_ESCROW_ID_MISMATCH = 15
    E_ROUTE_MISMATCH = 16
    E_INTENT_MISMATCH = 17
    E_ENTITY_MISMATCH = 18
    E_SOURCE_CHAIN_MISMATCH = 19
    E_DEST_CHAIN_MISMATCH = 20
    E_DESTINATION_MISMATCH = 21
    E_AMOUNT_MISMATCH = 22
    E_AMOUNT_TOO_LARGE = 23
    E_ANCHOR_MISMATCH = 24
    E_EXECUTION_BH_MISMATCH = 25
    E_MIN_COHERENCE_NOT_MET = 26
    E_STALE_NONCE = 27
    E_SIG_ARRAY_WIDTH = 28
    E_COIN_MISMATCH = 29


class MoveAbort(Exception):
    """The Python twin of a Move `abort` — carries the module error code."""

    def __init__(self, code: int, name: str):
        super().__init__(f"abort code {code} ({name})")
        self.code = code
        self.name = name


# ═══════════════════════════════════════════════════════════════════════
# Mirror of trion::canonical_cert (payload codec, §6 steps 1/4, §9)
# ═══════════════════════════════════════════════════════════════════════

MOVE_CERT = type("M", (), {})()  # namespace
MOVE_CERT.PAYLOAD_WIDTH = 346
MOVE_CERT.DOMAIN_TAG = b"TRION-CERT-V1"
MOVE_CERT.TTL_MAX = 604_800
MOVE_CERT.DRIFT = 60
MOVE_CERT.HHI_MAX = 4000
MOVE_CERT.SCALE_1E6 = 1_000_000
MOVE_CERT.U64_MAX = (1 << 64) - 1


def _u(payload: bytes, off: int, width: int) -> int:
    if off + width > len(payload):
        raise MoveAbort(CertErr.E_RANGE, "E_RANGE")
    return int.from_bytes(payload[off:off + width], "big")


def cert_readers(payload: bytes):
    """Field readers mirroring trion::canonical_cert (offsets = §2)."""
    return {
        "kind": _u(payload, 13, 1),
        "version": _u(payload, 14, 3),
        "epoch": _u(payload, 17, 4),
        "nonce": _u(payload, 21, 8),
        "escrow_id": payload[29:61],
        "route_id": payload[61:93],
        "intent_hash": payload[93:125],
        "entity_id": payload[125:157],
        "source_chain": _u(payload, 157, 4),
        "dest_chain": _u(payload, 161, 4),
        "destination": payload[165:197],
        "amount": _u(payload, 197, 32),
        "anchor_bh": payload[229:261],
        "execution_bh": payload[261:293],
        "coherence": _u(payload, 293, 8),
        "threshold": _u(payload, 301, 8),
        "hhi": _u(payload, 309, 8),
        "total_effective_power": _u(payload, 317, 8),
        "validator_count": _u(payload, 325, 4),
        "awa": payload[329] == 1,
        "issued_at": _u(payload, 330, 8),
        "ttl": _u(payload, 338, 8),
    }


def move_verify_structure(payload: bytes) -> None:
    """Mirror of canonical_cert::verify_structure (§6 steps 1 + 4)."""
    f = cert_readers(payload)
    if len(payload) != MOVE_CERT.PAYLOAD_WIDTH:
        raise MoveAbort(CertErr.E_PAYLOAD_WIDTH, "E_PAYLOAD_WIDTH")
    if payload[:13] != MOVE_CERT.DOMAIN_TAG:
        raise MoveAbort(CertErr.E_DOMAIN_TAG, "E_DOMAIN_TAG")
    if f["kind"] != 1:
        raise MoveAbort(CertErr.E_UNKNOWN_KIND, "E_UNKNOWN_KIND")
    if not (0x010000 <= f["version"] <= 0x01FFFF):
        raise MoveAbort(CertErr.E_VERSION, "E_VERSION")
    if f["ttl"] == 0:
        raise MoveAbort(CertErr.E_TTL_ZERO, "E_TTL_ZERO")
    if f["ttl"] > MOVE_CERT.TTL_MAX:
        raise MoveAbort(CertErr.E_TTL_TOO_LONG, "E_TTL_TOO_LONG")
    if f["dest_chain"] == 0:
        raise MoveAbort(CertErr.E_NO_DEST_CHAIN, "E_NO_DEST_CHAIN")
    if not f["awa"]:
        raise MoveAbort(CertErr.E_AWA_NOT_ENFORCED, "E_AWA_NOT_ENFORCED")
    if f["hhi"] > MOVE_CERT.HHI_MAX:
        raise MoveAbort(CertErr.E_HHI_CRITICAL, "E_HHI_CRITICAL")
    if f["coherence"] > MOVE_CERT.SCALE_1E6:
        raise MoveAbort(CertErr.E_COHERENCE_SCALE, "E_COHERENCE_SCALE")
    if f["threshold"] > MOVE_CERT.SCALE_1E6:
        raise MoveAbort(CertErr.E_THRESHOLD_SCALE, "E_THRESHOLD_SCALE")
    if f["coherence"] < f["threshold"]:
        raise MoveAbort(CertErr.E_NOT_SAFE, "E_NOT_SAFE")


def move_is_fresh_at(payload: bytes, now: int) -> bool:
    """Mirror of canonical_cert::is_fresh_at (§9, overflow-safe)."""
    f = cert_readers(payload)
    issued, t = f["issued_at"], f["ttl"]
    not_future = True if issued <= now else (issued - now) <= MOVE_CERT.DRIFT
    not_expired = True if issued > MOVE_CERT.U64_MAX - t else now <= issued + t
    return not_future and not_expired


def move_certificate_hash(payload: bytes) -> bytes:
    """Mirror of canonical_cert::certificate_hash (SHA3-256, FIPS 202)."""
    return hashlib.sha3_256(payload).digest()


# ═══════════════════════════════════════════════════════════════════════
# Mirror of trion::epoch_registry (registry + §6 steps 1-6)
# ═══════════════════════════════════════════════════════════════════════

class SigEntry:
    """Mirror of epoch_registry::CertificateSignature (§4 envelope entry)."""

    def __init__(self, validator_id: bytes, stake_weight: int,
                 diversity_weight: int, signature: bytes):
        self.validator_id = validator_id
        self.stake_weight = stake_weight
        self.diversity_weight = diversity_weight
        self.signature = signature


class EpochSetMirror:
    """Mirror of epoch_registry::EpochSetData + registration computation."""

    def __init__(self, entries):  # entries: list of (vid, pubkey, s, d)
        self.validators = {
            vid: {"pubkey": pk, "stake": s, "diversity": d}
            for (vid, pk, s, d) in entries
        }
        self.validator_count = len(entries)
        # exact floor-division arithmetic of the .move code
        self.total_effective_power = sum(
            (s * d) // MOVE_CERT.SCALE_1E6 for (_, _, s, d) in entries
        )
        self.d_consensus = sum(d for (_, _, _, d) in entries) // len(entries)


class MoveEpochRegistry:
    """Mirror of trion::epoch_registry storage + §6 verification."""

    EPOCH_GRACE = 2
    MIN_EPOCH_SET_SIZE = 3
    D_TIER1 = 600_000
    D_TIER2 = 400_000

    def __init__(self):
        self.current_epoch = 0
        self.epochs = {}          # epoch -> EpochSetMirror
        self.admin_caps = set()   # accounts holding EpochAdminCap
        self.initialized = False

    def initialize(self, admin: bytes):
        if admin != MODULE_ADDR:
            raise MoveAbort(RegErr.E_NOT_MODULE_ACCOUNT, "E_NOT_MODULE_ACCOUNT")
        if self.initialized:
            raise MoveAbort(RegErr.E_ALREADY_INITIALIZED, "E_ALREADY_INITIALIZED")
        self.initialized = True
        self.admin_caps.add(admin)

    def register_epoch(self, admin: bytes, epoch: int, entries):
        """entries: list of (validator_id, pubkey, stake, diversity)."""
        if not self.initialized:
            raise MoveAbort(RegErr.E_REGISTRY_NOT_INITIALIZED,
                            "E_REGISTRY_NOT_INITIALIZED")
        if admin not in self.admin_caps:
            raise MoveAbort(RegErr.E_NO_ADMIN_CAP, "E_NO_ADMIN_CAP")
        if len(entries) < self.MIN_EPOCH_SET_SIZE:
            raise MoveAbort(RegErr.E_TOO_FEW_VALIDATORS, "E_TOO_FEW_VALIDATORS")
        if self.current_epoch == 0:
            if epoch < 1:
                raise MoveAbort(RegErr.E_EPOCH_ORDER, "E_EPOCH_ORDER")
        elif epoch != self.current_epoch + 1:
            raise MoveAbort(RegErr.E_EPOCH_ORDER, "E_EPOCH_ORDER")
        if epoch in self.epochs:
            raise MoveAbort(RegErr.E_EPOCH_ORDER, "E_EPOCH_ORDER")
        for (vid, pk, s, d) in entries:
            if len(vid) != 32 or len(pk) != 32:
                raise MoveAbort(RegErr.E_ENTRY_WIDTH, "E_ENTRY_WIDTH")
            if s > MOVE_CERT.SCALE_1E6 or d > MOVE_CERT.SCALE_1E6:
                raise MoveAbort(RegErr.E_WEIGHT_SCALE, "E_WEIGHT_SCALE")
        ids = [e[0] for e in entries]
        if len(set(ids)) != len(ids):
            raise MoveAbort(RegErr.E_DUPLICATE_VALIDATOR, "E_DUPLICATE_VALIDATOR")
        self.epochs[epoch] = EpochSetMirror(entries)
        self.current_epoch = epoch

    def verify_certificate(self, payload: bytes, sigs, now: int):
        """§6 steps 1-6 in exact order; returns (signed_power, total, tier)."""
        move_verify_structure(payload)                       # step 1 (payload)
        if not self.initialized:
            raise MoveAbort(RegErr.E_REGISTRY_NOT_INITIALIZED,
                            "E_REGISTRY_NOT_INITIALIZED")
        # step 1 (envelope half)
        if len(sigs) < 3:
            raise MoveAbort(RegErr.E_INSUFFICIENT_SIGNERS, "E_INSUFFICIENT_SIGNERS")
        for s in sigs:
            if len(s.signature) != 64:
                raise MoveAbort(RegErr.E_SIG_WIDTH, "E_SIG_WIDTH")
            if len(s.validator_id) != 32:
                raise MoveAbort(RegErr.E_ENTRY_WIDTH, "E_ENTRY_WIDTH")
        ids = [s.validator_id for s in sigs]
        if len(set(ids)) != len(ids):
            raise MoveAbort(RegErr.E_DUPLICATE_SIGNER, "E_DUPLICATE_SIGNER")
        # step 2 — EPOCH
        f = cert_readers(payload)
        cert_epoch = f["epoch"]
        if cert_epoch not in self.epochs:
            raise MoveAbort(RegErr.E_EPOCH_UNKNOWN, "E_EPOCH_UNKNOWN")
        latest = self.current_epoch
        if cert_epoch > latest:
            raise MoveAbort(RegErr.E_EPOCH_FUTURE, "E_EPOCH_FUTURE")
        if latest - cert_epoch > self.EPOCH_GRACE:
            raise MoveAbort(RegErr.E_EPOCH_STALE, "E_EPOCH_STALE")
        es = self.epochs[cert_epoch]
        # step 3 — FRESHNESS
        if not move_is_fresh_at(payload, now):
            raise MoveAbort(RegErr.E_NOT_FRESH, "E_NOT_FRESH")
        # step 4 — registry preconditions (no lying about the set)
        if f["validator_count"] != es.validator_count:
            raise MoveAbort(RegErr.E_COUNT_LIE, "E_COUNT_LIE")
        if f["total_effective_power"] != es.total_effective_power:
            raise MoveAbort(RegErr.E_POWER_LIE, "E_POWER_LIE")
        # step 5 — SIGNATURES against REGISTERED keys, claims cross-checked
        signed_power = 0
        for s in sigs:
            if s.validator_id not in es.validators:
                raise MoveAbort(RegErr.E_VALIDATOR_NOT_REGISTERED,
                                "E_VALIDATOR_NOT_REGISTERED")
            entry = es.validators[s.validator_id]
            if s.stake_weight != entry["stake"] or \
                    s.diversity_weight != entry["diversity"]:
                raise MoveAbort(RegErr.E_WEIGHT_CLAIM_MISMATCH,
                                "E_WEIGHT_CLAIM_MISMATCH")
            # RFC 8032 Ed25519 over the RAW payload — the exact primitive
            # aptos_std::ed25519::signature_verify_strict verifies.
            try:
                Ed25519PublicKey.from_public_bytes(entry["pubkey"]).verify(
                    s.signature, payload)
            except Exception:
                raise MoveAbort(RegErr.E_BAD_SIGNATURE, "E_BAD_SIGNATURE")
            signed_power += (entry["stake"] * entry["diversity"]) \
                // MOVE_CERT.SCALE_1E6
        # step 6 — QUORUM (L4.2 tiers, u128 integer math)
        total_power = es.total_effective_power
        if es.d_consensus >= self.D_TIER1:
            tier = 1
            if not 3 * signed_power > 2 * total_power:
                raise MoveAbort(RegErr.E_QUORUM_NOT_MET, "E_QUORUM_NOT_MET")
        elif es.d_consensus >= self.D_TIER2:
            tier = 2
            if not 4 * signed_power >= 3 * total_power:
                raise MoveAbort(RegErr.E_QUORUM_NOT_MET, "E_QUORUM_NOT_MET")
        else:
            tier = 3
            if not 20 * signed_power >= 17 * total_power:
                raise MoveAbort(RegErr.E_QUORUM_NOT_MET, "E_QUORUM_NOT_MET")
        return signed_power, total_power, tier


# ═══════════════════════════════════════════════════════════════════════
# Mirror of trion::btcp_escrow (state machine + §6 steps 7-9)
# ═══════════════════════════════════════════════════════════════════════

MODULE_ADDR = _h("trion-module-account")  # @trion (32-byte Move address)

HOLDING, PENDING_AKASHIC, RELEASED, REVERTED, EMERGENCY_REVERTED = 0, 1, 2, 3, 4
EMERGENCY_ESCAPE_SECONDS = 7 * 24 * 60 * 60
AKASHIC_RECOVERY_SECONDS = 24 * 60 * 60
MIN_COHERENCE_FLOOR = 550_000
COHERENCE_CAP = 1_000_000
MAX_TIMEOUT_SECONDS = 7 * 24 * 60 * 60


class EscrowMirror:
    def __init__(self, **kw):
        self.__dict__.update(kw)
        self.state = HOLDING
        self.consumed_epoch = 0
        self.consumed_nonce = 0
        self.released_cert_hash = b""
        self.held = kw["amount"]


class MoveEscrow:
    """Mirror of trion::btcp_escrow storage + entry points."""

    def __init__(self, registry: MoveEpochRegistry):
        self.registry = registry
        self.escrows = {}                # addr(bytes32) -> EscrowMirror
        self.config = None               # {relayer, paused}
        self.admin_caps = set()
        self.clock = 0

    def initialize(self, admin: bytes):
        if admin != MODULE_ADDR:
            raise MoveAbort(EscErr.E_NOT_MODULE_ACCOUNT, "E_NOT_MODULE_ACCOUNT")
        if self.config is not None:
            raise MoveAbort(EscErr.E_ALREADY_INITIALIZED, "E_ALREADY_INITIALIZED")
        self.config = {"relayer": admin, "paused": False}
        self.admin_caps.add(admin)

    def pause(self, admin: bytes):
        if admin not in self.admin_caps:
            raise MoveAbort(EscErr.E_NO_ADMIN_CAP, "E_NO_ADMIN_CAP")
        self.config["paused"] = True

    def unpause(self, admin: bytes):
        if admin not in self.admin_caps:
            raise MoveAbort(EscErr.E_NO_ADMIN_CAP, "E_NO_ADMIN_CAP")
        self.config["paused"] = False

    def _assert_relayer(self, caller: bytes):
        if self.config is None:
            raise MoveAbort(EscErr.E_NOT_INITIALIZED, "E_NOT_INITIALIZED")
        if self.config["relayer"] != caller:
            raise MoveAbort(EscErr.E_NOT_RELAYER, "E_NOT_RELAYER")

    def lock_escrow(self, entity: bytes, route_id: bytes, intent_hash: bytes,
                    entity_id: bytes, anchor_bh: bytes, execution_bh: bytes,
                    source_chain: int, dest_chain: int, destination: bytes,
                    amount: int, min_coherence: int, timeout_seconds: int):
        if self.config is None:
            raise MoveAbort(EscErr.E_NOT_INITIALIZED, "E_NOT_INITIALIZED")
        if self.config["paused"]:
            raise MoveAbort(EscErr.E_PAUSED, "E_PAUSED")
        if entity in self.escrows:
            raise MoveAbort(EscErr.E_INVALID_STATE, "E_INVALID_STATE")
        if amount == 0:
            raise MoveAbort(EscErr.E_ZERO_AMOUNT, "E_ZERO_AMOUNT")
        for f in (route_id, intent_hash, entity_id, anchor_bh, execution_bh):
            if len(f) != 32:
                raise MoveAbort(EscErr.E_FIELD_WIDTH, "E_FIELD_WIDTH")
        if not (MIN_COHERENCE_FLOOR <= min_coherence <= COHERENCE_CAP):
            # the .move aborts E_COHERENCE_FLOOR for < floor and
            # E_COHERENCE_CAP for > cap — same family, distinguished here
            raise MoveAbort(
                EscErr.E_COHERENCE_FLOOR if min_coherence < MIN_COHERENCE_FLOOR
                else EscErr.E_COHERENCE_CAP,
                "E_COHERENCE_FLOOR/CAP")
        if not (0 < timeout_seconds <= MAX_TIMEOUT_SECONDS):
            raise MoveAbort(EscErr.E_TIMEOUT_BOUNDS, "E_TIMEOUT_BOUNDS")
        if dest_chain == 0:
            raise MoveAbort(EscErr.E_DEST_CHAIN_MISMATCH, "E_DEST_CHAIN_MISMATCH")
        self.escrows[entity] = EscrowMirror(
            route_id=route_id, intent_hash=intent_hash, entity_id=entity_id,
            anchor_bh=anchor_bh, execution_bh=execution_bh,
            source_chain=source_chain, dest_chain=dest_chain,
            destination=destination, amount=amount,
            min_coherence=min_coherence,
            lock_timestamp=self.clock, timeout_seconds=timeout_seconds,
            locked_by=entity, released_balance=0, reverted_balance=0)

    def release_escrow(self, submitter: bytes, escrow_addr: bytes,
                       payload: bytes, sigs):
        """§6 in exact order — the ONLY release path (no relayer gate)."""
        if escrow_addr not in self.escrows:
            raise MoveAbort(EscErr.E_NOT_FOUND, "E_NOT_FOUND")
        cert_hash = move_certificate_hash(payload)
        esc = self.escrows[escrow_addr]
        # §8.2 idempotent same-hash resubmission on a RELEASED escrow.
        if esc.state == RELEASED:
            if esc.released_cert_hash != cert_hash:
                raise MoveAbort(EscErr.E_INVALID_STATE, "E_INVALID_STATE")
            return  # no-op success
        if esc.state not in (HOLDING, PENDING_AKASHIC):
            raise MoveAbort(EscErr.E_INVALID_STATE, "E_INVALID_STATE")
        # circuit breaker
        if self.config is None:
            raise MoveAbort(EscErr.E_NOT_INITIALIZED, "E_NOT_INITIALIZED")
        if self.config["paused"]:
            raise MoveAbort(EscErr.E_PAUSED, "E_PAUSED")
        # §6 steps 1-6 via the registry
        signed_power, total_power, tier = self.registry.verify_certificate(
            payload, sigs, self.clock)
        f = cert_readers(payload)
        # escrow-local INV-003 gate
        if f["coherence"] < esc.min_coherence:
            raise MoveAbort(EscErr.E_MIN_COHERENCE_NOT_MET,
                            "E_MIN_COHERENCE_NOT_MET")
        # §6 step 7 — BINDING (escrow_id is DERIVED: BCS of escrow_addr)
        if f["escrow_id"] != escrow_addr:
            raise MoveAbort(EscErr.E_ESCROW_ID_MISMATCH, "E_ESCROW_ID_MISMATCH")
        if f["route_id"] != esc.route_id:
            raise MoveAbort(EscErr.E_ROUTE_MISMATCH, "E_ROUTE_MISMATCH")
        if f["intent_hash"] != esc.intent_hash:
            raise MoveAbort(EscErr.E_INTENT_MISMATCH, "E_INTENT_MISMATCH")
        if f["entity_id"] != esc.entity_id:
            raise MoveAbort(EscErr.E_ENTITY_MISMATCH, "E_ENTITY_MISMATCH")
        if f["source_chain"] != esc.source_chain:
            raise MoveAbort(EscErr.E_SOURCE_CHAIN_MISMATCH,
                            "E_SOURCE_CHAIN_MISMATCH")
        if f["dest_chain"] != esc.dest_chain:
            raise MoveAbort(EscErr.E_DEST_CHAIN_MISMATCH, "E_DEST_CHAIN_MISMATCH")
        if f["destination"] != esc.destination:
            raise MoveAbort(EscErr.E_DESTINATION_MISMATCH,
                            "E_DESTINATION_MISMATCH")
        if f["amount"] >= (1 << 64):
            raise MoveAbort(EscErr.E_AMOUNT_TOO_LARGE, "E_AMOUNT_TOO_LARGE")
        if f["amount"] != esc.amount:
            raise MoveAbort(EscErr.E_AMOUNT_MISMATCH, "E_AMOUNT_MISMATCH")
        if f["anchor_bh"] != esc.anchor_bh:
            raise MoveAbort(EscErr.E_ANCHOR_MISMATCH, "E_ANCHOR_MISMATCH")
        if f["execution_bh"] != esc.execution_bh:
            raise MoveAbort(EscErr.E_EXECUTION_BH_MISMATCH,
                            "E_EXECUTION_BH_MISMATCH")
        # §6 step 8 — NONCE / CONSUMED
        if esc.consumed_epoch == 0:
            if f["epoch"] < 1:
                raise MoveAbort(EscErr.E_STALE_NONCE, "E_STALE_NONCE")
        elif f["epoch"] == esc.consumed_epoch:
            if not f["nonce"] > esc.consumed_nonce:
                raise MoveAbort(EscErr.E_STALE_NONCE, "E_STALE_NONCE")
        else:
            if not f["epoch"] > esc.consumed_epoch:
                raise MoveAbort(EscErr.E_STALE_NONCE, "E_STALE_NONCE")
        # §6 step 9 — EFFECTS (state first, then the transfer)
        esc.consumed_epoch = f["epoch"]
        esc.consumed_nonce = f["nonce"]
        esc.released_cert_hash = cert_hash
        esc.state = RELEASED
        esc.released_balance += esc.held
        esc.held = 0
        return signed_power, total_power, tier

    def revert_escrow(self, caller: bytes, escrow_addr: bytes, reason: int):
        if escrow_addr not in self.escrows:
            raise MoveAbort(EscErr.E_NOT_FOUND, "E_NOT_FOUND")
        esc = self.escrows[escrow_addr]
        if esc.state not in (HOLDING, PENDING_AKASHIC):
            raise MoveAbort(EscErr.E_INVALID_STATE, "E_INVALID_STATE")
        is_timeout = self.clock > esc.lock_timestamp + esc.timeout_seconds
        is_akashic_expired = (
            esc.state == PENDING_AKASHIC
            and self.clock > esc.lock_timestamp + AKASHIC_RECOVERY_SECONDS
        )
        if not is_timeout and not is_akashic_expired:
            self._assert_relayer(caller)
        esc.state = REVERTED
        esc.reverted_balance += esc.held
        esc.held = 0

    def emergency_revert(self, _caller: bytes, escrow_addr: bytes):
        if escrow_addr not in self.escrows:
            raise MoveAbort(EscErr.E_NOT_FOUND, "E_NOT_FOUND")
        esc = self.escrows[escrow_addr]
        if esc.state not in (HOLDING, PENDING_AKASHIC):
            raise MoveAbort(EscErr.E_INVALID_STATE, "E_INVALID_STATE")
        if self.clock < esc.lock_timestamp + EMERGENCY_ESCAPE_SECONDS:
            raise MoveAbort(EscErr.E_EMERGENCY_NOT_YET, "E_EMERGENCY_NOT_YET")
        esc.state = EMERGENCY_REVERTED
        esc.reverted_balance += esc.held
        esc.held = 0

    def enter_pending_akashic(self, relayer: bytes, escrow_addr: bytes):
        self._assert_relayer(relayer)
        if self.config is None:
            raise MoveAbort(EscErr.E_NOT_INITIALIZED, "E_NOT_INITIALIZED")
        if self.config["paused"]:
            raise MoveAbort(EscErr.E_PAUSED, "E_PAUSED")
        if escrow_addr not in self.escrows:
            raise MoveAbort(EscErr.E_NOT_FOUND, "E_NOT_FOUND")
        esc = self.escrows[escrow_addr]
        if esc.state != HOLDING:
            raise MoveAbort(EscErr.E_INVALID_STATE, "E_INVALID_STATE")
        esc.state = PENDING_AKASHIC


# ═══════════════════════════════════════════════════════════════════════
# Test fixtures — real keys, real certificates, real registry
# ═══════════════════════════════════════════════════════════════════════

NOW = 1_800_000_000


def gen_validator(seed: str):
    """A real Ed25519 key pair (RFC 8032) + its canonical validator id."""
    sk = Ed25519PrivateKey.from_private_bytes(_h(seed)[:32])
    pk = sk.public_key().public_bytes(Encoding.Raw, PublicFormat.Raw)
    vid = _h("validator-" + seed)
    return sk, pk, vid


def build_set(registry, epoch, n, diversity, admin=MODULE_ADDR):
    """Register an epoch with n validators (s=1e6, d=diversity)."""
    vals = [gen_validator(f"epoch{epoch}-v{i}") for i in range(n)]
    entries = [(vid, pk, 1_000_000, diversity) for (_, pk, vid) in vals]
    registry.register_epoch(admin, epoch, entries)
    return vals, entries


def make_certificate(escrow_addr, esc, epoch, nonce, **overrides):
    """Build a REAL canonical certificate bound to the escrow record.
    kwargs: coherence, threshold, hhi_at_emission, issued_at, ttl,
    awa_enforced, total_effective_power, validator_count + any field
    override (used by the binding-mutation attack cases)."""
    cert = CanonicalCertificate(
        certificate_kind=1,
        protocol_version=pack_version(1, 0, 0),
        validator_epoch=epoch,
        certificate_nonce=nonce,
        escrow_id=escrow_addr,
        route_id=esc.route_id,
        intent_hash=esc.intent_hash,
        entity_id=esc.entity_id,
        source_chain=esc.source_chain,
        dest_chain=esc.dest_chain,
        destination=esc.destination,
        amount=esc.amount,
        anchor_bh=esc.anchor_bh,
        execution_bh=esc.execution_bh,
        coherence=overrides.pop("coherence", 820_000),
        threshold=overrides.pop("threshold", 550_000),
        hhi_at_emission=overrides.pop("hhi_at_emission", 1_200),
        total_effective_power=overrides.pop("total_effective_power", 0),
        validator_count=overrides.pop("validator_count", 0),
        awa_enforced=overrides.pop("awa_enforced", True),
        issued_at=overrides.pop("issued_at", NOW),
        ttl=overrides.pop("ttl", 86_400),
    )
    for k, v in overrides.items():
        setattr(cert, k, v)
    return cert


def sign_all(cert, validators, entries=None):
    """Sign the 346-byte payload with each validator key (family 2).

    Envelope weight CLAIMS are taken from the registered entries (the
    honest relayer copies them from the epoch set); they are cross-checked
    against the registry by §6 step 5c either way. Defaults to the tier-1
    fixture weights (s=1.0, d=0.7)."""
    payload = cert.encode_payload()
    sigs = []
    for i, (sk, _pk, vid) in enumerate(validators):
        sig = sk.sign(payload)
        if entries is not None:
            s, d = entries[i][2], entries[i][3]
        else:
            s, d = 1_000_000, 700_000
        sigs.append(SigEntry(vid, s, d, sig))
    return payload, sigs


def expect_abort(code, fn, *args, **kwargs):
    try:
        fn(*args, **kwargs)
    except MoveAbort as ab:
        return ab.code == code, f"got {ab.code} ({ab.name}), want {code}"
    return False, "no abort (accepted!)"


# ═══════════════════════════════════════════════════════════════════════
# The matrix
# ═══════════════════════════════════════════════════════════════════════

def fresh_system():
    reg = MoveEpochRegistry()
    reg.initialize(MODULE_ADDR)
    esc = MoveEscrow(reg)
    esc.initialize(MODULE_ADDR)
    esc.clock = NOW
    return reg, esc


def locked_escrow(esc, **kw):
    # The Escrow resource lives under the LOCKING account (the .move code
    # does move_to(entity, Escrow{...})) — the escrow address IS the
    # locker's address, one escrow per account. The mirror must key the
    # same way or the §6 step-7 escrow_id binding (BCS of the escrow
    # account address) would bind to the wrong account.
    entity = kw.pop("entity", _h("escrow-" + str(len(esc.escrows))))
    addr = kw.pop("addr", entity)
    rec = dict(
        route_id=_h("route"), intent_hash=_h("intent"), entity_id=_h("entity"),
        anchor_bh=_h("anchor"), execution_bh=_h("execution"),
        source_chain=kw.pop("source_chain", 1),
        dest_chain=kw.pop("dest_chain", 900),
        destination=kw.pop("destination", _h("dest-account")),
        amount=kw.pop("amount", 10_000_000_000),
        min_coherence=kw.pop("min_coherence", 550_000),
        timeout_seconds=kw.pop("timeout_seconds", 3600),
    )
    esc.lock_escrow(entity, rec["route_id"],
                    rec["intent_hash"], rec["entity_id"], rec["anchor_bh"],
                    rec["execution_bh"], rec["source_chain"], rec["dest_chain"],
                    rec["destination"], rec["amount"], rec["min_coherence"],
                    rec["timeout_seconds"])
    return addr, esc.escrows[addr]


def tier1_system():
    """3 validators × (s=1.0, d=0.7) → total 2.1e6, D=0.7 → tier 1."""
    reg, esc = fresh_system()
    vals, entries = build_set(reg, epoch=1, n=3, diversity=700_000)
    return reg, esc, vals, entries


def cert_for(vals, entries, escrow_addr, esc, epoch=1, nonce=1, **kw):
    cert = make_certificate(escrow_addr, esc, epoch, nonce, **kw)
    cert.validator_count = len(entries)
    cert.total_effective_power = sum(
        (s * d) // 1_000_000 for (_, _, s, d) in entries)
    return cert


def run_matrix():
    print("\n── 1) golden-vector byte parity (Move offsets == py reference)")
    _spec = importlib.util.spec_from_file_location(
        "trion_golden_vector_module",
        os.path.join(REPO, "tests", "unit",
                     "test_certificate_domain_separation.py"))
    _gold = importlib.util.module_from_spec(_spec)
    _spec.loader.exec_module(_gold)
    GOLDEN_CERT_HASH = _gold.GOLDEN_CERT_HASH
    GOLDEN_PAYLOAD_HEX = _gold.GOLDEN_PAYLOAD_HEX
    golden_certificate = _gold.golden_certificate
    payload = bytes.fromhex(GOLDEN_PAYLOAD_HEX)
    f = cert_readers(payload)
    g = golden_certificate()
    check("golden payload decodes at the Move offsets",
          f["kind"] == 1 and f["epoch"] == 7 and f["nonce"] == 42
          and f["escrow_id"] == g.escrow_id and f["route_id"] == g.route_id
          and f["intent_hash"] == g.intent_hash
          and f["entity_id"] == g.entity_id
          and f["source_chain"] == 1 and f["dest_chain"] == 900
          and f["destination"] == g.destination and f["amount"] == g.amount
          and f["anchor_bh"] == g.anchor_bh
          and f["execution_bh"] == g.execution_bh
          and f["coherence"] == 820_000 and f["threshold"] == 550_000
          and f["hhi"] == 1_234
          and f["total_effective_power"] == 2_100_000
          and f["validator_count"] == 3 and f["awa"] is True
          and f["issued_at"] == 1_700_000_123 and f["ttl"] == 86_400)
    check("move certificate_hash == golden SHA3-256",
          move_certificate_hash(payload).hex() == GOLDEN_CERT_HASH)
    check("move structure check accepts the golden payload",
          move_verify_structure(payload) is None)
    check("move freshness at issued+1000 accepts",
          move_is_fresh_at(payload, 1_700_000_123 + 1000))
    check("move freshness at expiry+1 rejects",
          not move_is_fresh_at(payload, 1_700_000_123 + 86_400 + 1))
    check("move freshness tolerates 60s future, not 61",
          move_is_fresh_at(payload, 1_700_000_123 - 60)
          and not move_is_fresh_at(payload, 1_700_000_123 - 61))

    print("\n── 2) valid release (the only path that should pass)")
    reg, esc, vals, entries = tier1_system()
    addr, e = locked_escrow(esc)
    cert = cert_for(vals, entries, addr, e)
    payload, sigs = sign_all(cert, vals)
    anyone = _h("random-submitter")
    res = esc.release_escrow(anyone, addr, payload, sigs)
    check("permissionless release succeeds (no relayer involved)",
          e.state == RELEASED and e.released_balance == e.amount
          and res == (2_100_000, 2_100_000, 1))
    check("consumed epoch/nonce recorded", e.consumed_epoch == 1
          and e.consumed_nonce == 1)
    check("released_cert_hash == SHA3-256(P)",
          e.released_cert_hash == move_certificate_hash(payload))

    print("\n── 3) C-02 regression: the relayer-flag attack is dead")
    # Pre-Wave-2, `verify_coherence(relayer, escrow)` flipped a boolean
    # and release only needed the relayer + that boolean. The equivalent
    # attack today: submit NO signatures at all.
    reg, esc, vals, entries = tier1_system()
    addr, e = locked_escrow(esc)
    cert = cert_for(vals, entries, addr, e)
    payload, _ = sign_all(cert, vals)
    ok, det = expect_abort(RegErr.E_INSUFFICIENT_SIGNERS,
                           esc.release_escrow, anyone, addr, payload, [])
    check("release with ZERO signatures aborts (old flag carried nothing)",
          ok, det)
    # A relayer calling release without a valid certificate fares no better.
    ok, det = expect_abort(RegErr.E_INSUFFICIENT_SIGNERS,
                           esc.release_escrow, MODULE_ADDR, addr, payload, [])
    check("the RELAYER itself cannot release without a quorum",
          ok, det)
    # DEV-MODE-ON-MAINNET assertion: the module has NO dev-mode resource,
    # NO admin release bypass, and NO flag any privileged call can flip —
    # so a dev-mode release path is unreachable by construction (there
    # is nothing on mainnet genesis to create). The EscrowAdminCap holder
    # (the strongest principal on the contract) can pause, unpause and
    # set the relayer — and STILL cannot release one unit without the
    # certificate quorum.
    ok, det = expect_abort(RegErr.E_INSUFFICIENT_SIGNERS,
                           esc.release_escrow, MODULE_ADDR, addr, payload, [])
    check("the ADMIN (EscrowAdminCap holder) cannot release either — "
          "no dev-mode exists to reach on ANY network", ok, det)
    esc.pause(MODULE_ADDR)
    ok, det = expect_abort(EscErr.E_PAUSED,
                           esc.release_escrow, MODULE_ADDR, addr, payload, [])
    check("admin's only release-relevant power is the pause breaker "
          "(which blocks, never authorizes)", ok, det)

    print("\n── 4) envelope + signature attacks")
    reg, esc, vals, entries = tier1_system()
    addr, e = locked_escrow(esc)
    cert = cert_for(vals, entries, addr, e)
    payload, sigs = sign_all(cert, vals)
    two = sigs[:2]
    ok, det = expect_abort(RegErr.E_INSUFFICIENT_SIGNERS,
                           esc.release_escrow, anyone, addr, payload, two)
    check("< 3 signers rejected", ok, det)
    dup = [sigs[0], sigs[0], sigs[1]]
    ok, det = expect_abort(RegErr.E_DUPLICATE_SIGNER,
                           esc.release_escrow, anyone, addr, payload, dup)
    check("duplicate-signer padding rejected", ok, det)
    badlen = SigEntry(sigs[0].validator_id, 1_000_000, 700_000, b"\x01" * 63)
    ok, det = expect_abort(RegErr.E_SIG_WIDTH,
                           esc.release_escrow, anyone, addr, payload,
                           [badlen, sigs[1], sigs[2]])
    check("63-byte signature rejected (family-2 width)", ok, det)
    liar = SigEntry(sigs[0].validator_id, 999_999, 700_000, sigs[0].signature)
    ok, det = expect_abort(RegErr.E_WEIGHT_CLAIM_MISMATCH,
                           esc.release_escrow, anyone, addr, payload,
                           [liar, sigs[1], sigs[2]])
    check("lied stake-weight claim rejected (§6 5c)", ok, det)
    liar2 = SigEntry(sigs[0].validator_id, 1_000_000, 700_001, sigs[0].signature)
    ok, det = expect_abort(RegErr.E_WEIGHT_CLAIM_MISMATCH,
                           esc.release_escrow, anyone, addr, payload,
                           [liar2, sigs[1], sigs[2]])
    check("lied diversity-weight claim rejected", ok, det)
    # signature over a DIFFERENT payload (route proof for another escrow)
    other_addr, other_e = locked_escrow(esc)
    other_cert = cert_for(vals, entries, other_addr, other_e)
    _, forged_sigs = sign_all(other_cert, vals)
    ok, det = expect_abort(RegErr.E_BAD_SIGNATURE,
                           esc.release_escrow, anyone, addr, payload,
                           forged_sigs)
    check("signatures for a different payload rejected "
          "(batch fail-closed)", ok, det)
    unregistered = gen_validator("not-in-set")
    ok, det = expect_abort(RegErr.E_VALIDATOR_NOT_REGISTERED,
                           esc.release_escrow, anyone, addr, payload,
                           [SigEntry(unregistered[2], 1_000_000, 700_000,
                                     unregistered[0].sign(payload)),
                            sigs[1], sigs[2]])
    check("unregistered signer rejected (verified keys are registry keys)",
          ok, det)

    print("\n── 5) quorum tier arithmetic (L4.2, exact integer math)")
    # Tier 1: 6 validators, 4 sign = EXACTLY 2/3 of weight → STRICT
    # failure (the envelope check has already passed: 4 ≥ 3 signers —
    # this isolates the quorum boundary from the liveness floor).
    reg, esc = fresh_system()
    vals, entries = build_set(reg, epoch=1, n=6, diversity=700_000)
    addr, e = locked_escrow(esc)
    cert = cert_for(vals, entries, addr, e)
    payload, sigs = sign_all(cert, vals, entries)
    ok, det = expect_abort(RegErr.E_QUORUM_NOT_MET,
                           esc.release_escrow, anyone, addr, payload, sigs[:4])
    check("tier 1: EXACTLY 2/3 is NOT a quorum (strict >)", ok, det)
    # …and 5 of 6 (> 2/3 strictly) passes.
    reg, esc = fresh_system()
    vals, entries = build_set(reg, epoch=1, n=6, diversity=700_000)
    addr, e = locked_escrow(esc)
    cert = cert_for(vals, entries, addr, e)
    payload, sigs = sign_all(cert, vals, entries)
    res = esc.release_escrow(anyone, addr, payload, sigs[:5])
    check("tier 1: 5/6 > 2/3 passes (strict >)", res[2] == 1
          and e.state == RELEASED)
    # parity with the py reference quorum implementation (both must
    # agree at every signer count — the mirror IS the .move arithmetic)
    py_set = EpochSet(1, [EpochSetEntry(v[2], 1_000_000, 700_000)
                          for v in vals])
    mirror_es = EpochSetMirror([(v[2], v[1], 1_000_000, 700_000)
                                for v in vals])
    for n_sig in (0, 1, 2, 3, 4, 5, 6):
        signed = sum((mirror_es.validators[v[2]]["stake"]
                      * mirror_es.validators[v[2]]["diversity"]) // 1_000_000
                     for v in vals[:n_sig])
        met_py, sp, tp, tier = py_set.quorum_met([v[2] for v in vals[:n_sig]])
        met_move = 3 * signed > 2 * mirror_es.total_effective_power
        check(f"mirror tier-1 quorum(n={n_sig}) == py reference",
              met_py == met_move)
    # Tier 2: 4 validators d=0.5 → 0.75 bar; 3 of 4 = exactly 0.75 passes.
    reg, esc = fresh_system()
    vals, entries = build_set(reg, epoch=1, n=4, diversity=500_000)
    addr, e = locked_escrow(esc)
    cert = cert_for(vals, entries, addr, e)
    payload, sigs = sign_all(cert, vals, entries)
    res = esc.release_escrow(anyone, addr, payload, sigs[:3])
    check("tier 2: exactly 0.75 passes (>=)", res[2] == 2
          and e.state == RELEASED)
    # Tier 2 negative: 8 validators d=0.5; 3 signers (≥ liveness floor)
    # carry 3/8 = 0.375 weight < 0.75 bar → quorum failure (not the
    # min-signers failure — the envelope check passes first).
    reg, esc = fresh_system()
    vals, entries = build_set(reg, epoch=1, n=8, diversity=500_000)
    addr, e = locked_escrow(esc)
    cert = cert_for(vals, entries, addr, e)
    payload, sigs = sign_all(cert, vals, entries)
    ok, det = expect_abort(RegErr.E_QUORUM_NOT_MET,
                           esc.release_escrow, anyone, addr, payload, sigs[:3])
    check("tier 2: 0.375 weight fails the 0.75 bar (≥3 signers)", ok, det)
    # Tier 3: 20 validators d=0.3 → 0.85 bar; 17 of 20 = exactly 0.85 passes.
    reg, esc = fresh_system()
    vals, entries = build_set(reg, epoch=1, n=20, diversity=300_000)
    addr, e = locked_escrow(esc)
    cert = cert_for(vals, entries, addr, e)
    payload, sigs = sign_all(cert, vals, entries)
    res = esc.release_escrow(anyone, addr, payload, sigs[:17])
    check("tier 3: exactly 0.85 passes (>=)", res[2] == 3
          and e.state == RELEASED)
    reg, esc = fresh_system()
    vals, entries = build_set(reg, epoch=1, n=20, diversity=300_000)
    addr, e = locked_escrow(esc)
    cert = cert_for(vals, entries, addr, e)
    payload, sigs = sign_all(cert, vals, entries)
    ok, det = expect_abort(RegErr.E_QUORUM_NOT_MET,
                           esc.release_escrow, anyone, addr, payload, sigs[:16])
    check("tier 3: 0.8 weight fails the 0.85 bar", ok, det)

    print("\n── 6) epoch + freshness attacks")
    reg, esc, vals, entries = tier1_system()
    # unregistered epoch
    addr, e = locked_escrow(esc)
    cert = cert_for(vals, entries, addr, e, epoch=9)
    cert.validator_count = 3
    cert.total_effective_power = 2_100_000
    payload, sigs = sign_all(cert, vals, entries)
    ok, det = expect_abort(RegErr.E_EPOCH_UNKNOWN,
                           esc.release_escrow, anyone, addr, payload, sigs)
    check("unregistered epoch rejected (no historical-set acceptance)",
          ok, det)
    # stale epoch: register 2..5 (strict +1 order), cert for epoch 1
    # (grace 2 exceeded) — keep the epoch-4 keys for the next case.
    vals4, entries4 = None, None
    for ep in (2, 3, 4, 5):
        v4, e4 = build_set(reg, epoch=ep, n=3, diversity=700_000)
        if ep == 4:
            vals4, entries4 = v4, e4
    addr, e = locked_escrow(esc)
    cert = cert_for(vals, entries, addr, e, epoch=1)
    payload, sigs = sign_all(cert, vals, entries)
    ok, det = expect_abort(RegErr.E_EPOCH_STALE,
                           esc.release_escrow, anyone, addr, payload, sigs)
    check("epoch 1 stale at current 5 (grace=2) rejected", ok, det)
    # within grace: epoch 4 at current 5 is accepted (epoch-4 keys)
    addr, e = locked_escrow(esc)
    cert = cert_for(vals4, entries4, addr, e, epoch=4)
    payload, sigs = sign_all(cert, vals4, entries4)
    res = esc.release_escrow(anyone, addr, payload, sigs)
    check("epoch 4 (within grace) accepted", e.state == RELEASED)
    # expired certificate
    reg, esc, vals, entries = tier1_system()
    addr, e = locked_escrow(esc)
    cert = cert_for(vals, entries, addr, e, issued_at=NOW - 86_400 - 1)
    payload, sigs = sign_all(cert, vals)
    ok, det = expect_abort(RegErr.E_NOT_FRESH,
                           esc.release_escrow, anyone, addr, payload, sigs)
    check("expired certificate rejected (issued_at + ttl < now)", ok, det)
    # future certificate beyond the 60 s drift tolerance
    cert = cert_for(vals, entries, addr, e, issued_at=NOW + 61)
    payload, sigs = sign_all(cert, vals)
    ok, det = expect_abort(RegErr.E_NOT_FRESH,
                           esc.release_escrow, anyone, addr, payload, sigs)
    check("future certificate beyond 60 s drift rejected", ok, det)
    # future within drift is tolerated
    cert = cert_for(vals, entries, addr, e, issued_at=NOW + 30)
    payload, sigs = sign_all(cert, vals)
    res = esc.release_escrow(anyone, addr, payload, sigs)
    check("30 s consensus-clock skew tolerated (lower bound only)",
          e.state == RELEASED)
    # ttl beyond the one-week clamp (fresh escrow — the drift case above
    # already released this one, and terminal states fail-closed first)
    reg, esc, vals, entries = tier1_system()
    addr, e = locked_escrow(esc)
    cert = cert_for(vals, entries, addr, e, ttl=604_801)
    payload, _ = sign_all(cert, vals, entries)
    ok, det = expect_abort(CertErr.E_TTL_TOO_LONG,
                           esc.release_escrow, anyone, addr, payload, [])
    check("ttl > 1 week rejected (§9.2 clamp)", ok, det)

    print("\n── 7) consensus-state attacks (payload preconditions)")
    for field, value, code, name in [
        ("awa_enforced", False, CertErr.E_AWA_NOT_ENFORCED, "awa=0"),
        ("hhi_at_emission", 4_001, CertErr.E_HHI_CRITICAL, "hhi>4000"),
        ("coherence", 500_000, CertErr.E_NOT_SAFE, "coherence<threshold"),
        ("certificate_kind", 2, CertErr.E_UNKNOWN_KIND, "unknown kind"),
        ("coherence", 1_000_001, CertErr.E_COHERENCE_SCALE,
         "coherence scale"),
    ]:
        reg, esc, vals, entries = tier1_system()
        addr, e = locked_escrow(esc)
        cert = cert_for(vals, entries, addr, e)
        if field == "certificate_kind":
            cert.certificate_kind = value
        elif field == "awa_enforced":
            cert.awa_enforced = value
        else:
            setattr(cert, field, value)
        payload, sigs = sign_all(cert, vals)
        ok, det = expect_abort(code, esc.release_escrow, anyone, addr,
                               payload, sigs)
        check(f"payload precondition: {name} rejected", ok, det)
    # tampered domain tag
    reg, esc, vals, entries = tier1_system()
    addr, e = locked_escrow(esc)
    cert = cert_for(vals, entries, addr, e)
    payload, sigs = sign_all(cert, vals)
    tampered = bytearray(payload)
    tampered[0] = ord("X")
    ok, det = expect_abort(CertErr.E_DOMAIN_TAG,
                           esc.release_escrow, anyone, addr,
                           bytes(tampered), sigs)
    check("wrong domain tag rejected", ok, det)
    # cert lies about the set
    reg, esc, vals, entries = tier1_system()
    addr, e = locked_escrow(esc)
    cert = cert_for(vals, entries, addr, e)
    cert.validator_count = 99
    payload, sigs = sign_all(cert, vals)
    ok, det = expect_abort(RegErr.E_COUNT_LIE,
                           esc.release_escrow, anyone, addr, payload, sigs)
    check("certificate lying about validator_count rejected", ok, det)
    reg, esc, vals, entries = tier1_system()
    addr, e = locked_escrow(esc)
    cert = cert_for(vals, entries, addr, e)
    cert.total_effective_power = 2_100_001
    payload, sigs = sign_all(cert, vals)
    ok, det = expect_abort(RegErr.E_POWER_LIE,
                           esc.release_escrow, anyone, addr, payload, sigs)
    check("certificate lying about total_effective_power rejected", ok, det)

    print("\n── 8) escrow binding attacks (§6 step 7 — full tuple)")
    binding_cases = [
        ("escrow_id", lambda c: setattr(c, "escrow_id", _h("other-escrow")),
         EscErr.E_ESCROW_ID_MISMATCH),
        ("route_id", lambda c: setattr(c, "route_id", _h("other-route")),
         EscErr.E_ROUTE_MISMATCH),
        ("intent_hash", lambda c: setattr(c, "intent_hash", _h("other-intent")),
         EscErr.E_INTENT_MISMATCH),
        ("entity_id", lambda c: setattr(c, "entity_id", _h("other-entity")),
         EscErr.E_ENTITY_MISMATCH),
        ("source_chain", lambda c: setattr(c, "source_chain", 2),
         EscErr.E_SOURCE_CHAIN_MISMATCH),
        ("dest_chain", lambda c: setattr(c, "dest_chain", 901),
         EscErr.E_DEST_CHAIN_MISMATCH),
        ("destination", lambda c: setattr(c, "destination", _h("thief")),
         EscErr.E_DESTINATION_MISMATCH),
        ("amount", lambda c: setattr(c, "amount", 1),
         EscErr.E_AMOUNT_MISMATCH),
        ("amount>u64", lambda c: setattr(c, "amount", 1 << 70),
         EscErr.E_AMOUNT_TOO_LARGE),
        ("anchor_bh", lambda c: setattr(c, "anchor_bh", _h("other-anchor")),
         EscErr.E_ANCHOR_MISMATCH),
        ("execution_bh", lambda c: setattr(c, "execution_bh",
                                           _h("other-execution")),
         EscErr.E_EXECUTION_BH_MISMATCH),
    ]
    for name, mutate, code in binding_cases:
        reg, esc, vals, entries = tier1_system()
        addr, e = locked_escrow(esc)
        cert = cert_for(vals, entries, addr, e)
        mutate(cert)
        payload, sigs = sign_all(cert, vals)
        ok, det = expect_abort(code, esc.release_escrow, anyone, addr,
                               payload, sigs)
        check(f"binding: {name} mismatch rejected", ok, det)
    # escrow-min_coherence gate (INV-003, escrow-local tightening)
    reg, esc, vals, entries = tier1_system()
    addr, e = locked_escrow(esc, min_coherence=900_000)
    cert = cert_for(vals, entries, addr, e)
    payload, sigs = sign_all(cert, vals)
    ok, det = expect_abort(EscErr.E_MIN_COHERENCE_NOT_MET,
                           esc.release_escrow, anyone, addr, payload, sigs)
    check("cert coherence below escrow floor rejected", ok, det)

    print("\n── 9) replay / double-release / terminal states")
    reg, esc, vals, entries = tier1_system()
    addr, e = locked_escrow(esc)
    cert = cert_for(vals, entries, addr, e, nonce=5)
    payload, sigs = sign_all(cert, vals)
    esc.release_escrow(anyone, addr, payload, sigs)
    balance = e.released_balance
    esc.release_escrow(anyone, addr, payload, sigs)  # idempotent resubmit
    check("same-hash resubmission is an idempotent no-op",
          e.state == RELEASED and e.released_balance == balance)
    # a DIFFERENT certificate (different nonce) on the terminal escrow
    cert2 = cert_for(vals, entries, addr, e, nonce=6)
    payload2, sigs2 = sign_all(cert2, vals)
    ok, det = expect_abort(EscErr.E_INVALID_STATE,
                           esc.release_escrow, anyone, addr, payload2, sigs2)
    check("different certificate on RELEASED escrow rejected "
          "(terminal freeze)", ok, det)
    # release on a REVERTED escrow
    reg, esc, vals, entries = tier1_system()
    addr, e = locked_escrow(esc, timeout_seconds=1)
    esc.clock = NOW + 2
    esc.revert_escrow(anyone, addr, 0)
    cert = cert_for(vals, entries, addr, e)
    payload, sigs = sign_all(cert, vals)
    ok, det = expect_abort(EscErr.E_INVALID_STATE,
                           esc.release_escrow, anyone, addr, payload, sigs)
    check("release on REVERTED escrow rejected", ok, det)
    # nonce guard (white-box: the guard is defense-in-depth — on Move a
    # successful release flips the state atomically, so consumed_* is
    # non-zero only on terminal escrows; we simulate a hypothetical
    # future partial-consumption path to prove the guard's semantics).
    reg, esc, vals, entries = tier1_system()
    addr, e = locked_escrow(esc)
    e.consumed_epoch, e.consumed_nonce = 1, 5
    cert_old = cert_for(vals, entries, addr, e, nonce=5)
    p_old, s_old = sign_all(cert_old, vals)
    ok, det = expect_abort(EscErr.E_STALE_NONCE,
                           esc.release_escrow, anyone, addr, p_old, s_old)
    check("same-epoch nonce ≤ consumed rejected (§8 monotonic)", ok, det)
    cert_new = cert_for(vals, entries, addr, e, nonce=6)
    p_new, s_new = sign_all(cert_new, vals)
    esc.release_escrow(anyone, addr, p_new, s_new)
    check("same-epoch nonce > consumed accepted",
          e.state == RELEASED and e.consumed_nonce == 6)
    # release from PENDING_AKASHIC also works (E4)
    reg, esc, vals, entries = tier1_system()
    addr, e = locked_escrow(esc)
    cert_hi = cert_for(vals, entries, addr, e, nonce=9)
    p_hi, s_hi = sign_all(cert_hi, vals)
    esc.enter_pending_akashic(esc.config["relayer"], addr)
    esc.release_escrow(anyone, addr, p_hi, s_hi)
    check("release from PENDING_AKASHIC works (E4)", e.state == RELEASED)

    print("\n── 10) pause circuit breaker (and its bypass attempts)")
    reg, esc, vals, entries = tier1_system()
    addr, e = locked_escrow(esc)
    # Lock the egress-hatch escrows BEFORE pausing (pause blocks ingress).
    addr2, e2 = locked_escrow(esc, timeout_seconds=1, entity=_h("l2"))
    addr3, e3 = locked_escrow(esc, timeout_seconds=3600, entity=_h("l3"))
    cert = cert_for(vals, entries, addr, e)
    payload, sigs = sign_all(cert, vals, entries)
    esc.pause(MODULE_ADDR)
    ok, det = expect_abort(EscErr.E_PAUSED,
                           esc.release_escrow, anyone, addr, payload, sigs)
    check("paused release rejected — even with a perfect certificate",
          ok, det)
    ok, det = expect_abort(EscErr.E_PAUSED, esc.lock_escrow, _h("l4"),
                           _h("r"), _h("i"), _h("e"), _h("a"), _h("x"),
                           1, 900, _h("d"), 1, 550_000, 60)
    check("paused lock rejected (ingress blocked)", ok, det)
    # egress stays open under pause (funds never frozen)
    esc.clock = NOW + 2
    esc.revert_escrow(anyone, addr2, 0)
    check("timeout revert STILL WORKS while paused",
          e2.state == REVERTED and e2.reverted_balance == e2.amount)
    esc.clock = NOW + EMERGENCY_ESCAPE_SECONDS + 1
    esc.emergency_revert(anyone, addr3)
    check("7-day emergency revert STILL WORKS while paused",
          e3.state == EMERGENCY_REVERTED)
    # a non-cap-holder cannot pause/unpause
    reg, esc, vals, entries = tier1_system()
    ok, det = expect_abort(EscErr.E_NO_ADMIN_CAP, esc.pause, _h("attacker"))
    check("pause requires EscrowAdminCap", ok, det)

    print("\n── 11) lock-time discipline (INV-003 + widths + timeouts)")
    reg, esc, vals, entries = tier1_system()
    ok, det = expect_abort(EscErr.E_COHERENCE_FLOOR, esc.lock_escrow,
                           _h("l"), _h("r"), _h("i"), _h("e"), _h("a"),
                           _h("x"), 1, 900, _h("d"), 1, 549_999, 60)
    check("lock with min_coherence below 0.55 floor rejected", ok, det)
    ok, det = expect_abort(EscErr.E_COHERENCE_CAP, esc.lock_escrow,
                           _h("l"), _h("r"), _h("i"), _h("e"), _h("a"),
                           _h("x"), 1, 900, _h("d"), 1, 1_000_001, 60)
    check("lock with min_coherence above 1.0 rejected", ok, det)
    ok, det = expect_abort(EscErr.E_TIMEOUT_BOUNDS, esc.lock_escrow,
                           _h("l"), _h("r"), _h("i"), _h("e"), _h("a"),
                           _h("x"), 1, 900, _h("d"), 1, 550_000, 0)
    check("zero timeout rejected", ok, det)
    ok, det = expect_abort(EscErr.E_TIMEOUT_BOUNDS, esc.lock_escrow,
                           _h("l"), _h("r"), _h("i"), _h("e"), _h("a"),
                           _h("x"), 1, 900, _h("d"), 1, 550_000,
                           MAX_TIMEOUT_SECONDS + 1)
    check("timeout above the 7-day horizon rejected "
          "(overflow-free arithmetic)", ok, det)
    ok, det = expect_abort(EscErr.E_FIELD_WIDTH, esc.lock_escrow,
                           _h("l"), b"short-route", _h("i"), _h("e"),
                           _h("a"), _h("x"), 1, 900, _h("d"), 1, 550_000, 60)
    check("non-32-byte route_id rejected", ok, det)
    ok, det = expect_abort(EscErr.E_ZERO_AMOUNT, esc.lock_escrow,
                           _h("l"), _h("r"), _h("i"), _h("e"), _h("a"),
                           _h("x"), 1, 900, _h("d"), 0, 550_000, 60)
    check("zero amount rejected", ok, det)

    print("\n── 12) registry authority (registrar discipline)")
    reg, esc = fresh_system()
    ok, det = expect_abort(RegErr.E_NO_ADMIN_CAP, reg.register_epoch,
                           _h("not-registrar"), 1,
                           [(v[2], v[1], 1_000_000, 700_000)
                            for v in [gen_validator("a")]] * 3)
    check("register_epoch without EpochAdminCap rejected", ok, det)
    reg, esc = fresh_system()
    vals, entries = build_set(reg, epoch=1, n=3, diversity=700_000)
    ok, det = expect_abort(RegErr.E_EPOCH_ORDER, reg.register_epoch,
                           MODULE_ADDR, 3, entries)
    check("epoch must be current+1 (no gaps, no rewrites)", ok, det)
    ok, det = expect_abort(RegErr.E_EPOCH_ORDER, reg.register_epoch,
                           MODULE_ADDR, 1, entries)
    check("epoch re-registration rejected", ok, det)
    ok, det = expect_abort(RegErr.E_TOO_FEW_VALIDATORS, reg.register_epoch,
                           MODULE_ADDR, 2, entries[:2])
    check("epoch set smaller than 3 rejected", ok, det)
    dupe = [(entries[0][0], entries[0][1], 1_000_000, 700_000)] * 3
    ok, det = expect_abort(RegErr.E_DUPLICATE_VALIDATOR, reg.register_epoch,
                           MODULE_ADDR, 2, dupe)
    check("duplicate validator ids rejected at registration", ok, det)

    print("\n── 13) revert / emergency authority matrix")
    reg, esc, vals, entries = tier1_system()
    addr, e = locked_escrow(esc, timeout_seconds=3600)
    ok, det = expect_abort(EscErr.E_NOT_RELAYER, esc.revert_escrow,
                           _h("attacker"), addr, 3)
    check("non-timeout revert by a non-relayer rejected", ok, det)
    esc.revert_escrow(esc.config["relayer"], addr, 1)
    check("relayer CAN revert (safe direction: funds → locker)",
          e.state == REVERTED and e.reverted_balance == e.amount)
    reg, esc, vals, entries = tier1_system()
    addr, e = locked_escrow(esc, timeout_seconds=3600)
    ok, det = expect_abort(EscErr.E_EMERGENCY_NOT_YET, esc.emergency_revert,
                           anyone, addr)
    check("emergency revert before 7 days rejected", ok, det)
    esc.clock = NOW + EMERGENCY_ESCAPE_SECONDS
    esc.emergency_revert(anyone, addr)
    check("emergency revert by ANYONE at day 7 refunds the locker",
          e.state == EMERGENCY_REVERTED and e.reverted_balance == e.amount)
    ok, det = expect_abort(EscErr.E_INVALID_STATE, esc.emergency_revert,
                           anyone, addr)
    check("terminal state has no outgoing edges", ok, det)

    print("\n── 14) reference-encoder parity (py twin == py reference)")
    reg, esc, vals, entries = tier1_system()
    addr, e = locked_escrow(esc)
    cert = cert_for(vals, entries, addr, e)
    payload = cert.encode_payload()
    env = CertificateEnvelope(
        family=int(SignatureFamily.ED25519),
        signatures=[WeightedSignatureEntry(v[2], 1_000_000, 700_000,
                                            v[0].sign(payload))
                    for v in vals])
    ok, reasons = py_verify_structure(cert, env)
    check("py reference verify_structure accepts the same certificate",
          ok, str(reasons))
    py_set = EpochSet(1, [EpochSetEntry(v[2], 1_000_000, 700_000)
                          for v in vals])
    ok, reasons = check_epoch_set_conformance(cert, py_set)
    check("py reference epoch-set conformance agrees "
          "(count + power + tier)", ok, str(reasons))
    met, sp, tp, tier = py_set.quorum_met([v[2] for v in vals])
    check("py reference quorum met for the full signer set",
          met and tier == 1 and sp == 2_100_000 and tp == 2_100_000)


# ═══════════════════════════════════════════════════════════════════════
# Static source assertions (the .move files must textually contain /
# not contain these) — the C-02 closure evidence at source level
# ═══════════════════════════════════════════════════════════════════════

def _strip_move_comments(src: str) -> str:
    """Remove Move comments (/// doc, // line, /* block */) so the C-02
    static regression greps the CODE, not the closure documentation —
    the module headers legitimately narrate the removed flag."""
    import re as _re
    out = _re.sub(r"/\*.*?\*/", " ", src, flags=_re.S)
    out = _re.sub(r"//[^\n]*", " ", out)
    return out


def run_static():
    esc_src = open(os.path.join(MOVE_SOURCES, "btcp_escrow.move")).read()
    reg_src = open(os.path.join(MOVE_SOURCES, "trion_epoch_registry.move")).read()
    cert_src = open(os.path.join(MOVE_SOURCES, "canonical_cert.move")).read()
    toml_src = open(os.path.join(REPO, "contracts", "move", "Move.toml")).read()
    # CODE-ONLY view (comments stripped) for the regression greps.
    esc_code = _strip_move_comments(esc_src)
    reg_code = _strip_move_comments(reg_src)
    cert_code = _strip_move_comments(cert_src)

    print("\n── S1) C-02 closure: the relayer coherence flag is GONE")
    check("no `coherence_verified` in any move CODE (comments stripped)",
          "coherence_verified" not in esc_code + reg_code + cert_code)
    check("no `verify_coherence` entry point in CODE",
          "verify_coherence" not in esc_code + reg_code + cert_code)
    check("no dev-mode / dev flag resource or entry in CODE",
          "dev_mode" not in (esc_code + reg_code + cert_code).lower()
          and "DevMode" not in esc_code + reg_code + cert_code)
    release_block = esc_src[esc_src.index("public entry fun release_escrow"):]
    release_block = release_block[:release_block.index("public entry fun revert_escrow")]
    check("the release path contains NO relayer authority check",
          "assert_relayer" not in release_block)
    check("release is permissionless (submitter carries no authority)",
          "_submitter: &signer" in release_block
          or "submitter: &signer" in release_block)
    # ENTRY-POINT INVENTORY (the strong dev-mode-on-mainnet statement):
    # the module exposes exactly these public entry points and NOTHING
    # else — there is no hidden flag-flipper, no dev-mode constructor, no
    # upgrade path an admin could use to mint release authority. Found
    # by regex over the CODE (comments stripped), so a comment cannot
    # hide a function and a function cannot hide in a comment.
    import re as _re
    found = set(_re.findall(r"public entry fun (\w+)", esc_code))
    expected = {
        "initialize", "transfer_admin", "set_relayer", "pause", "unpause",
        "lock_escrow", "release_escrow", "release_escrow_with_sigs",
        "revert_escrow", "emergency_revert", "enter_pending_akashic",
    }
    check("btcp_escrow entry-point inventory is exactly the audited set "
          "(no hidden dev-mode path on mainnet or anywhere)",
          found == expected,
          f"unexpected: {sorted(found - expected)}, "
          f"missing: {sorted(expected - found)}")
    reg_found = set(_re.findall(r"public entry fun (\w+)", reg_code))
    reg_expected = {"initialize", "transfer_admin", "register_epoch"}
    check("epoch_registry entry-point inventory is exactly the audited set",
          reg_found == reg_expected,
          f"unexpected: {sorted(reg_found - reg_expected)}, "
          f"missing: {sorted(reg_expected - reg_found)}")

    print("\n── S2) canonical verification is really in the Move source")
    check("native Ed25519 strict verification is called",
          "signature_verify_strict" in reg_src)
    check("envelope entries assembled via the registry's public "
          "constructor (Move struct literals are module-private — a "
          "cross-module literal would not compile)",
          "epoch_registry::new_signature(" in esc_src)
    check("verification uses the REGISTERED pubkey (not caller-supplied)",
          "entry.ed25519_pubkey" in reg_src)
    check("domain tag TRION-CERT-V1 pinned",
          'b"TRION-CERT-V1"' in cert_src)
    check("346-byte payload width pinned", "PAYLOAD_WIDTH: u64 = 346"
          in cert_src)
    check("SHA3-256 (FIPS) canonical hash on-chain",
          "hash::sha3_256" in cert_src)
    check("L4.2 tier-1 STRICT quorum in u128",
          "3 * signed_power > 2 * total_power" in reg_src
          and "as u128" in reg_src)
    check("tier-2 0.75 quorum", "4 * signed_power >= 3 * total_power"
          in reg_src)
    check("tier-3 0.85 quorum", "20 * signed_power >= 17 * total_power"
          in reg_src)
    check("epoch grace window", "EPOCH_GRACE: u64 = 2" in reg_src)
    check("clock = timestamp::now_seconds()",
          "timestamp::now_seconds()" in esc_src)
    check("freshness: drift widens the lower bound only",
          "CLOCK_DRIFT_TOLERANCE_SECONDS" in cert_src)
    check("weight claims cross-checked against the registry (§6 5c)",
          "E_WEIGHT_CLAIM_MISMATCH" in reg_src)
    check("batch fail-closed signatures (§6 5a)",
          "E_BAD_SIGNATURE" in reg_src)
    check("escrow_id binding is DERIVED from the escrow address",
          "bcs::to_bytes<address>(&escrow_addr)" in esc_src)
    check("destination binding is DERIVED too",
          "bcs::to_bytes<address>(&esc.destination)" in esc_src)
    check("replay record: consumed epoch + nonce + cert hash",
          "consumed_epoch" in esc_src and "consumed_nonce" in esc_src
          and "released_cert_hash" in esc_src)
    check("INV-003 coherence floor (0.55) enforced at lock",
          "MIN_COHERENCE_FLOOR: u64 = 550_000" in esc_src)
    check("HHI CRITICAL bound enforced", "HHI_MAX_ACCEPTABLE: u64 = 4000"
          in cert_src)
    check("AWA bit enforced", "E_AWA_NOT_ENFORCED" in cert_src)
    check("min signers = 3", "MIN_SIGNERS: u64 = 3" in cert_src)

    print("\n── S3) §6 verification order is textual (registry)")
    p_env = reg_src.index("§6 step 1 (envelope half)")
    p_epoch = reg_src.index("§6 step 2 — EPOCH")
    p_fresh = reg_src.index("§6 step 3 — FRESHNESS")
    p_pre = reg_src.index("§6 step 4 (registry half)")
    p_sigs = reg_src.index("§6 step 5 — SIGNATURES")
    p_quorum = reg_src.index("§6 step 6 — QUORUM")
    check("order: structure → envelope → epoch → freshness → "
          "preconditions → signatures → quorum",
          p_env < p_epoch < p_fresh < p_pre < p_sigs < p_quorum)

    print("\n── S4) capability + init discipline")
    check("registry init once, @trion only",
          "E_NOT_MODULE_ACCOUNT" in reg_src
          and "E_ALREADY_INITIALIZED" in reg_src)
    check("escrow init once, @trion only",
          "E_NOT_MODULE_ACCOUNT" in esc_src
          and "E_ALREADY_INITIALIZED" in esc_src)
    check("EpochAdminCap is has key (no copy/drop)",
          "struct EpochAdminCap has key {}" in reg_src)
    check("EscrowAdminCap is has key (no copy/drop)",
          "struct EscrowAdminCap has key {}" in esc_src)
    check("escrow resource is has key (held coin cannot be extracted)",
          "struct Escrow has key {" in esc_src)
    check("strict epoch ordering (current+1)",
          "E_EPOCH_ORDER" in reg_src)
    check("AptosStdlib dependency declared (native ed25519)",
          "AptosStdlib" in toml_src)

    print("\n── S5) timeout/overflow discipline")
    check("timeout capped at the 7-day emergency horizon",
          "MAX_TIMEOUT_SECONDS" in esc_src
          and "timeout_seconds <= MAX_TIMEOUT_SECONDS" in esc_src)
    check("quorum math widened to u128 (no u64 overflow bypass)",
          "(set.total_effective_power as u128)" in reg_src)
    check("u128→u64 narrowing guarded by asserts (Move `as` casts "
          "truncate silently — no bypass via type casting)",
          "E_AGGREGATE_OVERFLOW" in reg_src
          and "assert!(total_power <= MAX_U64" in reg_src)
    check("overflow-safe freshness (issued + ttl)",
          "MAX_U64" in cert_src)


def main():
    try:
        run_matrix()
        run_static()
    except Exception:
        traceback.print_exc()
        FAILED.append("unexpected exception")
    print(f"\n═══ RESULT: {len(PASSED)} passed, {len(FAILED)} failed ═══")
    if FAILED:
        print("FAILED:", FAILED)
        sys.exit(1)
    print("Move btcp_escrow: canonical certificate verification "
          "(C-02 closure) verified — mirror + static source audit.")
    print("UNVERIFIED BOUNDARY: `aptos move test` / prover require the "
          "Move toolchain (absent in this environment).")


def test_btcp_escrow_move_matrix():
    """pytest entry: the full matrix must pass with zero failures."""
    main()


if __name__ == "__main__":
    main()
