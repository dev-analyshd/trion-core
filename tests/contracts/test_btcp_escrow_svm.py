#!/usr/bin/env python3
"""
SVM btcp_escrow — canonical certificate release gate (C-03 closure test)
==========================================================================

Verification vehicle for contracts/svm/programs/btcp_escrow/src/lib.rs
(Wave 2, Agent H). There is no Solana/Anchor toolchain in this environment,
so this suite verifies the rewrite three ways:

PART 1 — a faithful Python MIRROR of the program's validation logic
    (``SvmEscrowMirror``): the same checks, in the same order, with the
    same error variants, driven against a fake account/PDA/clock world.
    Account derivation, ownership and one-time ``init`` semantics emulate
    the Anchor constraints (seeds / bump / init / init_if_needed /
    address / Account<T> ownership).

PART 2 — the ATTACK BATTERY: real canonical certificates built with the
    reference encoder ``core/consensus/certificate.py`` (346-byte payload P,
    byte-exact) and REAL Ed25519 signatures. Signature verification follows
    the on-chain pattern exactly: the mirror models the TRANSACTION (a list
    of instructions), EXECUTES the native Ed25519SigVerify precompile the
    way the runtime does (real ``cryptography`` ed25519 verifies, any
    failure aborts the whole transaction), and then mirrors the program's
    instructions-sysvar INTROSPECTION — parsing the 14-byte offsets
    structs with the runtime's own index semantics (u16::MAX → own data,
    otherwise the referenced instruction's data) and requiring the exact
    three-way byte match (registered pubkey, envelope signature, payload).
    Every release-gate requirement of CANONICAL_CERTIFICATE.md §6 is
    attacked: wrong epoch / stale epoch, low-weight and exactly-2/3
    quorums, settlement-tuple (destination/amount) mismatch, expiry,
    future-dating, replay, equivocation conflict, unregistered signer,
    forged signature, missing / late / malformed / wrong-offset (the
    Relay bypass class) Ed25519SigVerify instructions, weight-claim lies,
    power/count/threshold lies, HHI/AWA/coherence violations, binding
    mismatches per field, wrong-PDA derivation, fake vault/destination
    accounts, double release, the old C-03 single-oracle-key attack (the
    pause authority cannot release), pause semantics, timeout/emergency-
    revert escapes and admin surface.

PART 3 — STATIC PARITY against the Rust source (grep-style assertions, the
    tests/unit/test_intent_spec_fields.py pattern): the payload slice
    offsets extracted from lib.rs must equal the reference encoder's
    OFFSETS table; the §6 step markers must appear in order; the ed25519
    introspection machinery (Ed25519SigVerify program id, checked sysvar
    loaders, u16::MAX index rule, offsets parsing), the checked-math ops,
    the seeds, the quorum tier literals, and a curated list of required
    ``BTCPError::`` guards must all be present;
    ``unsafe`` and the deleted ``is_release_authority``/``bind_oracle``
    oracle-key gate must be absent.

Run:  python3 tests/contracts/test_btcp_escrow_svm.py   (or pytest-ignored)
Exit: 0 iff every check passes.
"""

from __future__ import annotations

import hashlib
import importlib.util
import re
import struct
import sys
import types
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]


def _bootstrap_repo_imports():
    """Register the reference encoder and the golden-vector module under
    their dotted names WITHOUT touching sys.path — the repo's sys-path
    hygiene guard (tests/unit/test_no_sys_path_hacks.py, token-scanned)
    forbids new path-bootstrapping hacks, and this file must not add
    one."""
    # package parents as importable namespace modules
    for dotted, rel in (("core", "core"), ("core.consensus", "core/consensus")):
        if dotted not in sys.modules:
            pkg = types.ModuleType(dotted)
            pkg.__path__ = [str(REPO_ROOT / rel)]
            sys.modules[dotted] = pkg
    if "core.consensus.certificate" not in sys.modules:
        spec = importlib.util.spec_from_file_location(
            "core.consensus.certificate",
            REPO_ROOT / "core" / "consensus" / "certificate.py",
        )
        mod = importlib.util.module_from_spec(spec)
        sys.modules["core.consensus.certificate"] = mod
        spec.loader.exec_module(mod)
    if "test_certificate_domain_separation" not in sys.modules:
        spec = importlib.util.spec_from_file_location(
            "test_certificate_domain_separation",
            REPO_ROOT / "tests" / "unit" / "test_certificate_domain_separation.py",
        )
        mod = importlib.util.module_from_spec(spec)
        sys.modules["test_certificate_domain_separation"] = mod
        spec.loader.exec_module(mod)
    return sys.modules["core.consensus.certificate"]


from cryptography.hazmat.primitives.asymmetric.ed25519 import (  # noqa: E402
    Ed25519PrivateKey,
    Ed25519PublicKey,
)

_certificate = _bootstrap_repo_imports()
CanonicalCertificate = _certificate.CanonicalCertificate
OFFSETS = _certificate.OFFSETS
PAYLOAD_WIDTH = _certificate.PAYLOAD_WIDTH
pack_version = _certificate.pack_version
SCALE_1E6 = _certificate.SCALE_1E6
EpochSet = _certificate.EpochSet
EpochSetEntry = _certificate.EpochSetEntry

# Golden vector from the reference test suite (cross-checks the mirror's
# independent payload decoder against the pinned 346-byte vector).
golden_mod = sys.modules["test_certificate_domain_separation"]

LIB_RS = REPO_ROOT / "contracts" / "svm" / "programs" / "btcp_escrow" / "src" / "lib.rs"
COMMON_RS = REPO_ROOT / "contracts" / "svm" / "programs" / "btcp_common" / "src" / "lib.rs"

# ═════════════════════════════════════════════════════════════════════════════
# Constants — mirror of btcp_common (kept in sync by the static parity part)
# ═════════════════════════════════════════════════════════════════════════════

SEED_CONFIG = b"config"
SEED_ESCROW = b"escrow"
SEED_VAULT = b"vault"
SEED_TRION = b"trion"
SEED_VALIDATORS = b"validators"
SEED_CONSUMED = b"consumed"

CERT_DOMAIN_TAG = b"TRION-CERT-V1"
CERT_PAYLOAD_WIDTH = 346
CERT_KIND_ESCROW_RELEASE = 1
CERT_FAMILY_ED25519 = 2
CERT_ED25519_SIG_LEN = 64
CERT_SUPPORTED_VERSION = 1 << 16          # 1.0.0
CERT_MIN_SIGNERS = 3
CERT_EPOCH_GRACE = 2
CERT_HHI_MAX = 4_000
CERT_TTL_MAX = 604_800
CERT_DRIFT_TOLERANCE_SECS = 60
D_CONSENSUS_TIER1 = 600_000
D_CONSENSUS_TIER2 = 400_000
MAX_VALIDATORS = 256
EMERGENCY_REVERT_SECONDS = 7 * 24 * 60 * 60
SCALE = SCALE_1E6

# EscrowState / RevertReason mirrors (repr u8)
HOLDING, RELEASED, REVERTED, EMERGENCY_REVERTED = 0, 1, 2, 3
REASON_TIMEOUT, REASON_COHERENCE, REASON_ROUTE, REASON_MANUAL, REASON_EMERGENCY = 0, 1, 2, 3, 4

PROGRAM_ID = b"H" * 32     # fake program id (ownership checks)
SYSTEM_ID = b"Y" * 32      # fake system program id


def pda(*seeds: bytes) -> bytes:
    """Deterministic stand-in for Pubkey::find_program_address."""
    return hashlib.sha256(b"\x1f".join(seeds) + PROGRAM_ID).digest()


def be32(v: int) -> bytes:
    return struct.pack(">I", v)


def sha3_256(b: bytes) -> bytes:
    return hashlib.sha3_256(b).digest()


def canonical_validator_id(epoch: int, key_index: int) -> bytes:
    """validator_id = SHA3-256("TRION-VALIDATOR" || epoch || key_index) —
    CANONICAL_CERTIFICATE.md §4."""
    return sha3_256(b"TRION-VALIDATOR" + be32(epoch) + be32(key_index))


class ProgErr(Exception):
    """A BTCPError variant raised by the mirror (instruction body)."""

    def __init__(self, variant: str):
        super().__init__(variant)
        self.variant = variant


class AnchorErr(Exception):
    """An Anchor account-constraint failure (seeds / init / address /
    ownership / account-not-found) — also a rejection on-chain."""

    def __init__(self, constraint: str):
        super().__init__(constraint)
        self.constraint = constraint


# ═════════════════════════════════════════════════════════════════════════════
# PART 1 — the mirror of contracts/svm/programs/btcp_escrow/src/lib.rs
# (same checks, same order, same error variants)
# ═════════════════════════════════════════════════════════════════════════════

class ConfigData:
    def __init__(self):
        self.owner = None
        self.relayer = None
        self.registry_admin = None
        self.pause_authority = None      # None = Pubkey::default()
        self.self_chain = 0
        self.min_validator_count = 0
        self.latest_epoch = 0
        self.paused = False
        self.count = 0

    def is_authorized(self, signer):
        return signer in (self.owner, self.relayer)

    def is_owner(self, signer):
        return signer == self.owner

    def is_registry_admin(self, signer):
        return signer == self.registry_admin

    def is_pause_authority(self, signer):
        if self.is_owner(signer):
            return True
        return self.pause_authority is not None and signer == self.pause_authority


class ValidatorEntry:
    def __init__(self, validator_id, ed25519_pubkey, stake_weight, diversity_weight):
        self.validator_id = validator_id
        self.ed25519_pubkey = ed25519_pubkey
        self.stake_weight = stake_weight
        self.diversity_weight = diversity_weight


class RegistryData:
    def __init__(self, epoch, validators, threshold):
        self.epoch = epoch
        self.validators = validators  # sorted by validator_id
        self.validator_count = len(validators)
        self.total_effective_power = sum(effective_power(v) for v in validators)
        self.threshold = threshold
        self.set_root = epoch_set_root(epoch, validators)


def effective_power(v: ValidatorEntry) -> int:
    """w_j = s_j · d_j (×1e6 carried) — rounds DOWN (lib.rs)."""
    return (v.stake_weight * v.diversity_weight) // SCALE


def epoch_set_root(epoch: int, validators) -> bytes:
    """SHA-256("TRION-EPOCHSET" || epoch_be || entries) — lib.rs register_epoch."""
    buf = b"TRION-EPOCHSET" + be32(epoch)
    for v in validators:
        buf += v.validator_id + v.ed25519_pubkey
        buf += struct.pack(">Q", v.stake_weight) + struct.pack(">Q", v.diversity_weight)
    return hashlib.sha256(buf).digest()


class EscrowData:
    def __init__(self):
        self.escrow_id = b"\x00" * 32
        self.route_id = b"\x00" * 32
        self.intent_hash = b"\x00" * 32
        self.entity_id = b"\x00" * 32
        self.destination = b"\x00" * 32
        self.amount = 0
        self.min_coherence = 0
        self.source_chain = 0
        self.dest_chain = 0
        self.anchor_bh = b"\x00" * 32
        self.execution_bh = b"\x00" * 32
        self.lock_slot = 0
        self.locked_at = 0
        self.timeout_slots = 0
        self.state = HOLDING
        self.revert_reason = REASON_TIMEOUT
        self.settled_at = 0
        self.reverted_at = 0
        self.locked_by = b"\x00" * 32
        self.bump = 0
        self.vault_bump = 0

    def is_expired(self, current_slot: int) -> bool:
        # lib.rs Escrow::is_expired — saturating_add
        return self.state == HOLDING and current_slot > min(
            self.lock_slot + self.timeout_slots, 2**64 - 1
        )


class ConsumedData:
    def __init__(self):
        self.is_set = 0
        self.epoch = 0
        self.nonce = 0
        self.cert_sha256 = b"\x00" * 32


class Account:
    def __init__(self, kind, owner, data=None, lamports=0):
        self.kind = kind          # config | registry | escrow | consumed | vault | wallet
        self.owner = owner
        self.data = data
        self.lamports = lamports


def decode_payload(p: bytes) -> dict:
    """Mirror of lib.rs parse_certificate — the same offsets, the same
    fail-closed width/tag/u64-amount rules."""
    if len(p) != CERT_PAYLOAD_WIDTH:
        raise ProgErr("MalformedCertificate")
    if p[0:13] != CERT_DOMAIN_TAG:
        raise ProgErr("MalformedCertificate")
    amount_bytes = p[197:229]
    if amount_bytes[0:24] != b"\x00" * 24:
        raise ProgErr("AmountTooLarge")
    return {
        "kind": p[13],
        "protocol_version": int.from_bytes(bytes([0, p[14], p[15], p[16]]), "big"),
        "validator_epoch": int.from_bytes(p[17:21], "big"),
        "certificate_nonce": int.from_bytes(p[21:29], "big"),
        "escrow_id": p[29:61],
        "route_id": p[61:93],
        "intent_hash": p[93:125],
        "entity_id": p[125:157],
        "source_chain": int.from_bytes(p[157:161], "big"),
        "dest_chain": int.from_bytes(p[161:165], "big"),
        "destination": p[165:197],
        "amount": int.from_bytes(amount_bytes[24:32], "big"),
        "anchor_bh": p[229:261],
        "execution_bh": p[261:293],
        "coherence": int.from_bytes(p[293:301], "big"),
        "threshold": int.from_bytes(p[301:309], "big"),
        "hhi_at_emission": int.from_bytes(p[309:317], "big"),
        "total_effective_power": int.from_bytes(p[317:325], "big"),
        "validator_count": int.from_bytes(p[325:329], "big"),
        "awa_enforced": p[329],
        "issued_at": int.from_bytes(p[330:338], "big"),
        "ttl": int.from_bytes(p[338:346], "big"),
    }


def ed25519_verify(pubkey: bytes, payload: bytes, signature: bytes) -> bool:
    """The Ed25519SigVerify precompile's primitive (what the Solana runtime
    executes for every entry of an Ed25519SigVerify instruction)."""
    try:
        Ed25519PublicKey.from_public_bytes(pubkey).verify(signature, payload)
        return True
    except Exception:
        return False


# ═════════════════════════════════════════════════════════════════════════════
# Transaction model: Ed25519SigVerify instructions + instructions-sysvar
# introspection (mirrors lib.rs §6 step 5a exactly)
# ═════════════════════════════════════════════════════════════════════════════

# Stand-in for the native Ed25519SigVerify program id
# (Ed25519SigVerify1111111111111111111111111111111111).
ED25519_PROGRAM_ID = b"E" * 32
U16_MAX = 0xFFFF
ED_IX_PREFIX_LEN = 2       # u8 num_signatures ‖ u8 padding
ED_IX_OFFSETS_LEN = 14     # 7 × u16 LE offset fields


class TxInstruction:
    """One top-level transaction instruction (program_id, accounts, data)."""

    def __init__(self, program_id: bytes, accounts, data: bytes):
        self.program_id = program_id
        self.accounts = accounts
        self.data = data


class TxRejected(Exception):
    """The Solana runtime aborted the transaction (an Ed25519SigVerify
    instruction failed while EXECUTING — before or after release_escrow,
    atomicity rolls everything back). Also a fail-closed outcome."""


def build_ed_instruction_data(entries):
    """Build Ed25519SigVerify instruction data (the client-side builder).

    Each entry is a dict with optional keys:
      sig / sig_ix / sig_off   — 64-byte signature (embedded iff sig_ix omitted)
      pk  / pk_ix  / pk_off    — 32-byte pubkey   (embedded iff pk_ix omitted)
      msg / msg_ix / msg_off / msg_size — message (embedded iff msg_ix omitted)
    An explicit *_ix (≠ U16_MAX) cross-references another instruction's data
    at the given offset — the runtime-supported layout the real relayer uses
    to keep the 1232-byte transaction budget.
    """
    n = len(entries)
    blob = bytearray()
    offsets = []
    for ent in entries:
        sig_ix = ent.get("sig_ix", U16_MAX)
        pk_ix = ent.get("pk_ix", U16_MAX)
        msg_ix = ent.get("msg_ix", U16_MAX)
        sig_off = pk_off = msg_off = 0
        if sig_ix == U16_MAX:
            sig_off = ED_IX_PREFIX_LEN + n * ED_IX_OFFSETS_LEN + len(blob)
            blob += ent["sig"]
        else:
            sig_off = ent.get("sig_off", 0)
        if pk_ix == U16_MAX:
            pk_off = ED_IX_PREFIX_LEN + n * ED_IX_OFFSETS_LEN + len(blob)
            blob += ent["pk"]
        else:
            pk_off = ent.get("pk_off", 0)
        if msg_ix == U16_MAX:
            msg_off = ED_IX_PREFIX_LEN + n * ED_IX_OFFSETS_LEN + len(blob)
            blob += ent["msg"]
            msg_size = len(ent["msg"])
        else:
            msg_off = ent.get("msg_off", 0)
            msg_size = ent.get("msg_size", len(ent.get("msg", b"")))
        offsets.append(struct.pack(
            "<7H", sig_off, sig_ix, pk_off, pk_ix, msg_off, msg_size, msg_ix))
    return struct.pack("<BB", n, 0) + b"".join(offsets) + bytes(blob)


def parse_ed_offsets(data: bytes, entry: int):
    """Mirror of lib.rs read_ed_offsets — the i'th 14-byte offsets struct."""
    base = ED_IX_PREFIX_LEN + entry * ED_IX_OFFSETS_LEN
    b = data[base:base + ED_IX_OFFSETS_LEN]
    if len(b) != ED_IX_OFFSETS_LEN:
        return None
    v = struct.unpack("<7H", b)
    return {
        "sig_off": v[0], "sig_ix": v[1], "pk_off": v[2], "pk_ix": v[3],
        "msg_off": v[4], "msg_size": v[5], "msg_ix": v[6],
    }


def ed_resolve(tx, ix, index: int, offset: int, size: int):
    """Mirror of lib.rs ed_slice — the runtime's own index semantics:
    index == U16_MAX → the ed instruction's own data at `offset`;
    otherwise tx[index].data at `offset`. Bounds-checked, None on OOB."""
    src = ix.data if index == U16_MAX else (tx[index].data if index < len(tx) else None)
    if src is None:
        return None
    end = offset + size
    if offset > len(src) or end > len(src):
        return None
    return src[offset:end]


def execute_ed_instruction(ix, tx):
    """The native Ed25519SigVerify program EXECUTING (runtime semantics):
    resolve every entry's (signature, pubkey, message) per the offsets
    index rule and verify it — any failure aborts the whole transaction."""
    data = ix.data
    if len(data) < ED_IX_PREFIX_LEN:
        raise TxRejected("malformed ed instruction")
    for e in range(data[0]):
        off = parse_ed_offsets(data, e)
        if off is None:
            raise TxRejected("truncated offsets")
        sig = ed_resolve(tx, ix, off["sig_ix"], off["sig_off"], 64)
        pk = ed_resolve(tx, ix, off["pk_ix"], off["pk_off"], 32)
        msg = ed_resolve(tx, ix, off["msg_ix"], off["msg_off"], off["msg_size"])
        if sig is None or pk is None or msg is None:
            raise TxRejected("unresolvable offsets")
        if not ed25519_verify(pk, msg, sig):
            raise TxRejected("ed25519 verification failed")


def program_find_verified_sig(tx, current_index, payload, pubkey, signature):
    """Mirror of lib.rs verify_ed25519_signature — the program-side
    instructions-sysvar introspection. Only instructions that have already
    executed (index < current_index) are introspected; an ed instruction
    with accounts is not a verification source; every entry's offsets are
    parsed and resolved with the runtime's semantics; the three-way
    exact byte match (payload, pubkey, signature) must hold."""
    for ix in tx[:current_index]:
        if ix.program_id != ED25519_PROGRAM_ID:
            continue
        if ix.accounts:
            continue
        data = ix.data
        if len(data) < ED_IX_PREFIX_LEN:
            continue
        for e in range(data[0]):
            off = parse_ed_offsets(data, e)
            if off is None:
                break
            sig = ed_resolve(tx, ix, off["sig_ix"], off["sig_off"], 64)
            pk = ed_resolve(tx, ix, off["pk_ix"], off["pk_off"], 32)
            msg = ed_resolve(tx, ix, off["msg_ix"], off["msg_off"], off["msg_size"])
            if sig is None or pk is None or msg is None:
                continue
            if msg == payload and pk == pubkey and sig == signature:
                return True
    return False


def run_transaction(mirror, release_fn, tx):
    """Execute a mirror transaction: the runtime executes every
    Ed25519SigVerify instruction (in order — a failure aborts the tx),
    then the release instruction runs LAST with instructions-sysvar
    introspection seeing index = len(tx) - 1."""
    for ix in tx[:-1]:
        if ix.program_id == ED25519_PROGRAM_ID:
            execute_ed_instruction(ix, tx)
    return release_fn(tx=tx, current_index=len(tx) - 1)


class SvmEscrowMirror:
    """Faithful py mirror of the btcp_escrow program instructions."""

    def __init__(self, slot=1_000, now=1_700_000_000):
        self.accounts = {}          # address -> Account
        self.events = []
        self.slot = slot
        self.now = now

    # ── low-level account world (Anchor constraint emulation) ──────────

    def wallet(self, key: bytes, lamports: int = 10**12) -> bytes:
        if key not in self.accounts:
            self.accounts[key] = Account("wallet", SYSTEM_ID, lamports=lamports)
        return key

    def _get_typed(self, addr: bytes, kind: str):
        acct = self.accounts.get(addr)
        if acct is None:
            raise AnchorErr("AccountNotFound")
        if acct.owner != PROGRAM_ID:
            raise AnchorErr("AccountOwnedByWrongProgram")
        if acct.kind != kind:
            raise AnchorErr("AccountDiscriminatorMismatch")
        return acct.data

    def _transfer(self, src: bytes, dst: bytes, amount: int):
        """system_instruction::transfer — creates the recipient if missing
        (system semantics), fails on insufficient lamports."""
        src_acct = self.accounts[src]
        if src_acct.lamports < amount:
            raise ProgErr("TransferFailed")
        src_acct.lamports -= amount
        if dst not in self.accounts:
            self.accounts[dst] = Account("wallet", SYSTEM_ID)
        self.accounts[dst].lamports += amount

    # ── initialize ──────────────────────────────────────────────────────

    def initialize(self, payer: bytes, self_chain: int, min_validator_count: int = 3):
        addr = pda(SEED_CONFIG)
        if addr in self.accounts:
            raise AnchorErr("InitAlreadyExists")          # #[account(init)] — once
        if self_chain == 0:
            raise ProgErr("ZeroChain")
        if min_validator_count < CERT_MIN_SIGNERS:
            raise ProgErr("TooFewValidators")
        cfg = ConfigData()
        cfg.owner = payer
        cfg.relayer = payer
        cfg.registry_admin = payer
        cfg.pause_authority = None
        cfg.self_chain = self_chain
        cfg.min_validator_count = min_validator_count
        cfg.latest_epoch = 0
        cfg.paused = False
        cfg.count = 0
        self.accounts[addr] = Account("config", PROGRAM_ID, data=cfg)
        self.wallet(payer)
        return addr

    # ── register_epoch ─────────────────────────────────────────────────

    def register_epoch(self, admin: bytes, epoch: int, entries, threshold: int):
        config_addr = pda(SEED_CONFIG)
        config = self._get_typed(config_addr, "config")
        if not config.is_registry_admin(admin):
            raise ProgErr("NotRegistryAdmin")
        if epoch < 1:
            raise ProgErr("InvalidEpoch")
        if epoch <= config.latest_epoch:
            raise ProgErr("EpochAlreadyRegistered")
        if not entries:
            raise ProgErr("InvalidValidatorSet")
        if len(entries) > MAX_VALIDATORS:
            raise ProgErr("InvalidValidatorSet")
        if not (1 <= threshold <= SCALE):
            raise ProgErr("InvalidThreshold")

        registry_addr = pda(SEED_TRION, SEED_VALIDATORS, be32(epoch))
        if registry_addr in self.accounts:
            raise AnchorErr("InitAlreadyExists")          # init — immutable set
        self.wallet(admin)

        sorted_entries = sorted(entries, key=lambda v: v.validator_id)
        for a, b in zip(sorted_entries, sorted_entries[1:]):
            if a.validator_id == b.validator_id:
                raise ProgErr("DuplicateValidator")
        by_key = sorted(entries, key=lambda v: v.ed25519_pubkey)
        for a, b in zip(by_key, by_key[1:]):
            if a.ed25519_pubkey == b.ed25519_pubkey:
                raise ProgErr("DuplicateValidatorKey")

        total_power = 0
        for v in sorted_entries:
            if not (0 < v.stake_weight <= SCALE):
                raise ProgErr("InvalidWeight")
            if v.diversity_weight > SCALE:
                raise ProgErr("InvalidWeight")
            total_power += effective_power(v)             # bounded: ≤ 256 × 1e6
        if total_power == 0:
            raise ProgErr("ZeroPower")

        registry = RegistryData(epoch, sorted_entries, threshold)
        self.accounts[registry_addr] = Account("registry", PROGRAM_ID, data=registry)
        config.latest_epoch = epoch
        self.events.append(("EpochRegistered", epoch, registry.validator_count,
                            total_power, threshold))
        return registry_addr

    # ── lock_escrow ────────────────────────────────────────────────────

    def lock_escrow(self, relayer, vault_funder, escrow_id, route_id, intent_hash,
                    entity_id, amount, min_coherence, source_chain, dest_chain,
                    anchor_bh, execution_bh, timeout_slots, destination):
        config = self._get_typed(pda(SEED_CONFIG), "config")
        if not config.is_authorized(relayer):
            raise ProgErr("NotAuthorized")
        if config.paused:
            raise ProgErr("Paused")
        if min_coherence > SCALE:
            raise ProgErr("InvalidCoherence")
        # INV-003 (follow-on 2): tightening-only — sub-floor min_coherence
        # rejected at lock (fail-fast; mirrors the Move/Cairo twins)
        if min_coherence < 550_000:
            raise ProgErr("CoherenceFloor")
        if timeout_slots == 0:
            raise ProgErr("ZeroTimeout")
        if entity_id == b"\x00" * 32:
            raise ProgErr("ZeroDestination")
        if escrow_id == b"\x00" * 32:
            raise ProgErr("InvalidArgument")
        if intent_hash == b"\x00" * 32:
            raise ProgErr("ZeroIntentHash")
        if source_chain == 0:
            raise ProgErr("ZeroChain")
        if dest_chain != config.self_chain:
            raise ProgErr("WrongChain")
        if anchor_bh == b"\x00" * 32:
            raise ProgErr("ZeroAnchor")
        if execution_bh == b"\x00" * 32:
            raise ProgErr("ZeroExecutionBH")
        if amount == 0:
            raise ProgErr("ZeroAmount")
        funder = self.accounts[self.wallet(vault_funder)]
        if funder.lamports < amount:
            raise ProgErr("InsufficientFunds")
        # checked lock_slot + timeout_slots
        if self.slot + timeout_slots >= 2**64:
            raise ProgErr("Overflow")

        escrow_addr = pda(SEED_ESCROW, escrow_id)
        if escrow_addr in self.accounts:
            raise AnchorErr("InitAlreadyExists")
        vault_addr = pda(SEED_VAULT, escrow_id)

        self._transfer(vault_funder, vault_addr, amount)
        # a fresh vault is a system-owned PDA holding lamports
        self.accounts[vault_addr].kind = "vault"

        esc = EscrowData()
        esc.escrow_id = escrow_id
        esc.route_id = route_id
        esc.intent_hash = intent_hash
        esc.entity_id = entity_id
        esc.destination = destination
        esc.amount = amount
        esc.min_coherence = min_coherence
        esc.source_chain = source_chain
        esc.dest_chain = dest_chain
        esc.anchor_bh = anchor_bh
        esc.execution_bh = execution_bh
        esc.lock_slot = self.slot
        esc.locked_at = self.now
        esc.timeout_slots = timeout_slots
        esc.state = HOLDING
        esc.locked_by = vault_funder
        esc.bump = 0
        esc.vault_bump = 0
        self.accounts[escrow_addr] = Account("escrow", PROGRAM_ID, data=esc)
        config.count += 1
        self.events.append(("EscrowLocked", escrow_id.hex()))
        return escrow_addr

    # ── release_escrow (the §6 sequence, mirrors lib.rs line by line) ──

    def release_escrow(self, submitter, registry_addr, escrow_addr, vault_addr,
                       destination_addr, consumed_addr, payload, cert_epoch,
                       envelope, tx=None, current_index=None):
        # ---- Accounts-context constraint layer (Anchor emulation) ----
        config = self._get_typed(pda(SEED_CONFIG), "config")
        self.wallet(submitter)
        # the instructions sysvar account (address constraint + _checked
        # loaders) — the introspection source modeled by tx/current_index
        if tx is None:
            tx = []
            current_index = 0
        # registry: seeds = ["trion", "validators", cert_epoch_be]
        if registry_addr != pda(SEED_TRION, SEED_VALIDATORS, be32(cert_epoch)):
            raise AnchorErr("SeedsMismatch:registry")
        registry = self._get_typed(registry_addr, "registry")
        # escrow: seeds = ["escrow", escrow.escrow_id]
        escrow = self._get_typed(escrow_addr, "escrow")
        if escrow_addr != pda(SEED_ESCROW, escrow.escrow_id):
            raise AnchorErr("SeedsMismatch:escrow")
        # vault: seeds = ["vault", escrow.escrow_id]
        if vault_addr != pda(SEED_VAULT, escrow.escrow_id):
            raise AnchorErr("SeedsMismatch:vault")
        # destination: address = escrow.destination
        if destination_addr != escrow.destination:
            raise AnchorErr("AddressConstraint:destination")
        # consumed: init_if_needed, seeds = ["trion", "consumed", escrow_id]
        if consumed_addr != pda(SEED_TRION, SEED_CONSUMED, escrow.escrow_id):
            raise AnchorErr("SeedsMismatch:consumed")
        if consumed_addr not in self.accounts:
            self.accounts[consumed_addr] = Account(
                "consumed", PROGRAM_ID, data=ConsumedData())
        consumed = self.accounts[consumed_addr].data

        # ── §6 STEP 1 — STRUCTURE ──────────────────────────────────────
        cert = decode_payload(payload)
        if cert["kind"] != CERT_KIND_ESCROW_RELEASE:
            raise ProgErr("UnknownCertificateKind")
        if cert["protocol_version"] > CERT_SUPPORTED_VERSION:
            raise ProgErr("VersionIncompatible")
        if envelope["family"] != CERT_FAMILY_ED25519:
            raise ProgErr("WrongSignatureFamily")
        if len(envelope["signatures"]) < CERT_MIN_SIGNERS:
            raise ProgErr("InsufficientSigners")
        if len(envelope["signatures"]) > MAX_VALIDATORS:
            raise ProgErr("InvalidValidatorSet")
        for sig in envelope["signatures"]:
            if len(sig["signature"]) != CERT_ED25519_SIG_LEN:
                raise ProgErr("MalformedSignature")
        ids = [s["validator_id"] for s in envelope["signatures"]]
        if len(set(ids)) != len(ids):
            raise ProgErr("DuplicateSigner")
        if cert["validator_epoch"] != cert_epoch:
            raise ProgErr("EpochArgumentMismatch")

        # ── §6 STEP 2 — EPOCH ──────────────────────────────────────────
        if config.latest_epoch == 0:
            raise ProgErr("NoEpochRegistered")
        if cert["validator_epoch"] > config.latest_epoch:
            raise ProgErr("EpochFuture")
        grace_floor = max(config.latest_epoch - CERT_EPOCH_GRACE, 0)
        if cert["validator_epoch"] < grace_floor:
            raise ProgErr("EpochStale")
        if registry.epoch != cert["validator_epoch"]:
            raise ProgErr("RegistryEpochMismatch")

        # ── §6 STEP 3 — FRESHNESS ──────────────────────────────────────
        if not (0 < cert["ttl"] <= CERT_TTL_MAX):
            raise ProgErr("InvalidTtl")
        if self.now < 0:
            raise ProgErr("InvalidClock")
        now = self.now
        now_with_drift = now + CERT_DRIFT_TOLERANCE_SECS
        if cert["issued_at"] > now_with_drift:
            raise ProgErr("CertificateFutureDated")
        if now > cert["issued_at"] + cert["ttl"]:
            raise ProgErr("CertificateExpired")

        # ── §6 STEP 4 — CONSENSUS PRECONDITIONS ────────────────────────
        if cert["hhi_at_emission"] > CERT_HHI_MAX:
            raise ProgErr("HhiCritical")
        if cert["awa_enforced"] != 1:
            raise ProgErr("AwaNotEnforced")
        if cert["coherence"] < cert["threshold"]:
            raise ProgErr("CoherenceBelowThreshold")
        if registry.threshold != cert["threshold"]:
            raise ProgErr("ThresholdMismatch")
        if cert["validator_count"] != registry.validator_count:
            raise ProgErr("ValidatorCountMismatch")
        if len(registry.validators) != registry.validator_count:
            raise ProgErr("RegistryCorrupt")
        if registry.validator_count < config.min_validator_count:
            raise ProgErr("TooFewValidators")

        # ── §6 STEP 5 — SIGNATURES ─────────────────────────────────────
        by_id = {v.validator_id: v for v in registry.validators}
        for sig in envelope["signatures"]:
            entry = by_id.get(sig["validator_id"])
            if entry is None:
                raise ProgErr("UnregisteredValidator")
            if sig["stake_weight"] != entry.stake_weight:
                raise ProgErr("WeightClaimMismatch")
            if sig["diversity_weight"] != entry.diversity_weight:
                raise ProgErr("WeightClaimMismatch")
            # 5a — the runtime (Ed25519SigVerify precompile) must have
            # verified exactly (entry.ed25519_pubkey, signature, payload)
            # in an instruction that already EXECUTED (§6 step 5a,
            # lib.rs verify_ed25519_signature introspection mirror).
            if not program_find_verified_sig(
                tx, current_index, payload, entry.ed25519_pubkey,
                sig["signature"],
            ):
                raise ProgErr("SignatureVerificationFailed")

        # ── §6 STEP 6 — QUORUM ─────────────────────────────────────────
        total_power = sum(effective_power(v) for v in registry.validators)
        if total_power == 0:
            raise ProgErr("ZeroPower")
        if cert["total_effective_power"] != total_power:
            raise ProgErr("PowerMismatch")
        if registry.total_effective_power != total_power:
            raise ProgErr("RegistryPowerMismatch")
        signed_power = sum(effective_power(by_id[s["validator_id"]])
                           for s in envelope["signatures"])
        d_sum = sum(v.diversity_weight for v in registry.validators)
        d_consensus = d_sum // len(registry.validators)
        if d_consensus >= D_CONSENSUS_TIER1:
            quorum_met = 3 * signed_power > 2 * total_power      # TIER 1 STRICT
        elif d_consensus >= D_CONSENSUS_TIER2:
            quorum_met = 4 * signed_power >= 3 * total_power     # TIER 2
        else:
            quorum_met = 20 * signed_power >= 17 * total_power   # TIER 3
        if not quorum_met:
            raise ProgErr("InsufficientQuorum")

        # ── §6 STEP 7 — BINDING ───────────────────────────────────────
        if cert["escrow_id"] != escrow.escrow_id:
            raise ProgErr("EscrowMismatch")
        if cert["route_id"] != escrow.route_id:
            raise ProgErr("RouteMismatch")
        if cert["intent_hash"] != escrow.intent_hash:
            raise ProgErr("IntentMismatch")
        if cert["entity_id"] != escrow.entity_id:
            raise ProgErr("EntityMismatch")
        if cert["destination"] != escrow.destination:
            raise ProgErr("DestinationMismatch")
        if cert["amount"] != escrow.amount:
            raise ProgErr("AmountMismatch")
        if cert["source_chain"] != escrow.source_chain:
            raise ProgErr("ChainMismatch")
        if cert["dest_chain"] != escrow.dest_chain:
            raise ProgErr("ChainMismatch")
        if cert["dest_chain"] != config.self_chain:
            raise ProgErr("WrongChain")
        if cert["anchor_bh"] != escrow.anchor_bh:
            raise ProgErr("AnchorMismatch")
        if cert["execution_bh"] != escrow.execution_bh:
            raise ProgErr("ExecutionMismatch")
        if cert["coherence"] < escrow.min_coherence:
            raise ProgErr("CoherenceInsufficient")

        # ── §6 STEP 8 — NONCE / CONSUMED ──────────────────────────────
        payload_sha256 = hashlib.sha256(payload).digest()
        if consumed.is_set == 1:
            if consumed.cert_sha256 == payload_sha256:
                if escrow.state != RELEASED:
                    raise ProgErr("InconsistentReplayState")
                return "idempotent"
            self.events.append(("EquivocationDetected", escrow.escrow_id.hex(),
                                consumed.epoch, consumed.nonce))
            raise ProgErr("CertificateConflict")

        # ── §6 STEP 9 — settlement guard + effects ─────────────────────
        if escrow.state != HOLDING:
            raise ProgErr("NotHolding")
        if escrow.is_expired(self.slot):
            raise ProgErr("Expired")
        vault = self.accounts[vault_addr]
        if vault.lamports < escrow.amount:
            raise ProgErr("InsufficientFunds")

        consumed.is_set = 1
        consumed.epoch = cert["validator_epoch"]
        consumed.nonce = cert["certificate_nonce"]
        consumed.cert_sha256 = payload_sha256

        escrow.state = RELEASED
        escrow.settled_at = now
        self._transfer(vault_addr, destination_addr, escrow.amount)
        self.events.append(("EscrowReleased", escrow.escrow_id.hex(),
                            cert["validator_epoch"], cert["certificate_nonce"]))
        return "released"

    # ── revert_escrow ──────────────────────────────────────────────────

    def revert_escrow(self, caller, escrow_addr, vault_addr, locked_by_addr, reason):
        escrow = self._get_typed(escrow_addr, "escrow")
        if escrow_addr != pda(SEED_ESCROW, escrow.escrow_id):
            raise AnchorErr("SeedsMismatch:escrow")
        if vault_addr != pda(SEED_VAULT, escrow.escrow_id):
            raise AnchorErr("SeedsMismatch:vault")
        if locked_by_addr != escrow.locked_by:
            raise AnchorErr("AddressConstraint:locked_by")
        config = self._get_typed(pda(SEED_CONFIG), "config")
        self.wallet(caller)

        if escrow.state != HOLDING:
            raise ProgErr("NotHolding")

        is_timeout = escrow.is_expired(self.slot)
        if reason not in (0, 1, 2, 3, 4):
            raise ProgErr("InvalidAction")
        emergency_ready = self.now >= escrow.locked_at + EMERGENCY_REVERT_SECONDS
        if not is_timeout and not emergency_ready:
            if not config.is_authorized(caller):
                raise ProgErr("NotRelayerForRevert")
            if reason == REASON_TIMEOUT:
                raise ProgErr("NotRelayerForRevert")

        escrow.revert_reason = reason
        escrow.reverted_at = self.now
        escrow.state = EMERGENCY_REVERTED if reason == REASON_EMERGENCY else REVERTED
        self._transfer(vault_addr, locked_by_addr, escrow.amount)
        self.events.append(("EscrowReverted", escrow.escrow_id.hex(), reason))
        return "reverted"

    # ── admin instructions ─────────────────────────────────────────────

    def set_relayer(self, owner, new_relayer):
        config = self._get_typed(pda(SEED_CONFIG), "config")
        if not config.is_owner(owner):
            raise ProgErr("NotOwner")
        config.relayer = new_relayer

    def set_registry_admin(self, owner, new_admin):
        config = self._get_typed(pda(SEED_CONFIG), "config")
        if not config.is_owner(owner):
            raise ProgErr("NotOwner")
        if new_admin is None:
            raise ProgErr("InvalidArgument")
        config.registry_admin = new_admin

    def bind_pause_authority(self, owner, new_authority):
        config = self._get_typed(pda(SEED_CONFIG), "config")
        if not config.is_owner(owner):
            raise ProgErr("NotOwner")
        if new_authority is None:
            raise ProgErr("InvalidArgument")
        if config.pause_authority is not None:
            raise ProgErr("NotAuthorized")          # one-way binding
        config.pause_authority = new_authority
        self.events.append(("PauseAuthorityBound",))

    def pause(self, authority):
        config = self._get_typed(pda(SEED_CONFIG), "config")
        if not config.is_pause_authority(authority):
            raise ProgErr("NotAuthorized")
        if config.paused:
            raise ProgErr("InvalidArgument")
        config.paused = True
        self.events.append(("EscrowPaused",))

    def unpause(self, authority):
        config = self._get_typed(pda(SEED_CONFIG), "config")
        if not config.is_pause_authority(authority):
            raise ProgErr("NotAuthorized")
        if not config.paused:
            raise ProgErr("InvalidArgument")
        config.paused = False
        self.events.append(("EscrowUnpaused",))


# ═════════════════════════════════════════════════════════════════════════════
# Test world builder
# ═════════════════════════════════════════════════════════════════════════════

def make_keys(n: int, tag: str):
    """Deterministic ed25519 validator keypairs."""
    return [
        Ed25519PrivateKey.from_private_bytes(sha3_256(f"validator-key-{tag}-{i}".encode()))
        for i in range(n)
    ]


def pub_of(key) -> bytes:
    return key.public_key().public_bytes_raw()


class World:
    """One registry epoch (4 validators, s=1.0 d=0.7 → tier 1, total 2.8e6),
    one locked escrow, keys and a valid certificate factory."""

    SELF_CHAIN = 900
    SOURCE_CHAIN = 1
    THRESHOLD = 550_000

    def __init__(self, n_validators=4, stake=1_000_000, diversity=700_000,
                 min_validator_count=3):
        self.m = SvmEscrowMirror(slot=1_000, now=1_700_000_000)
        self.owner = sha3_256(b"owner")
        self.relayer = sha3_256(b"relayer")
        self.funder = sha3_256(b"funder")
        self.registrar = sha3_256(b"registrar")
        self.submitter = sha3_256(b"submitter")
        self.destination = sha3_256(b"destination")
        self.m.initialize(self.owner, self.SELF_CHAIN, min_validator_count)
        config = self.m._get_typed(pda(SEED_CONFIG), "config")
        config.relayer = self.relayer
        config.registry_admin = self.registrar

        self.keys = make_keys(n_validators, "main")
        self.entries = [
            ValidatorEntry(
                validator_id=canonical_validator_id(1, i),
                ed25519_pubkey=pub_of(k),
                stake_weight=stake,
                diversity_weight=diversity,
            )
            for i, k in enumerate(self.keys)
        ]
        self.registry_addr = self.m.register_epoch(
            self.registrar, 1, self.entries, self.THRESHOLD)

        self.escrow_id = sha3_256(b"escrow-a")
        self.route_id = sha3_256(b"route-a")
        self.intent_hash = sha3_256(b"intent-a")
        self.entity_id = sha3_256(b"entity-a")
        self.anchor_bh = sha3_256(b"anchor-a")
        self.execution_bh = sha3_256(b"execution-a")
        self.amount = 500_000_000
        self.m.wallet(self.funder, 10 * self.amount)
        self.escrow_addr = self.m.lock_escrow(
            relayer=self.relayer, vault_funder=self.funder,
            escrow_id=self.escrow_id, route_id=self.route_id,
            intent_hash=self.intent_hash, entity_id=self.entity_id,
            amount=self.amount, min_coherence=700_000,
            source_chain=self.SOURCE_CHAIN, dest_chain=self.SELF_CHAIN,
            anchor_bh=self.anchor_bh, execution_bh=self.execution_bh,
            timeout_slots=10_000, destination=self.destination)
        self.vault_addr = pda(SEED_VAULT, self.escrow_id)
        self.consumed_addr = pda(SEED_TRION, SEED_CONSUMED, self.escrow_id)

    # -- certificate factory ------------------------------------------------

    def cert_kwargs(self):
        total = sum(effective_power(v) for v in self.entries)
        return dict(
            certificate_kind=1,
            protocol_version=pack_version(1, 0, 0),
            validator_epoch=1,
            certificate_nonce=1,
            escrow_id=self.escrow_id,
            route_id=self.route_id,
            intent_hash=self.intent_hash,
            entity_id=self.entity_id,
            source_chain=self.SOURCE_CHAIN,
            dest_chain=self.SELF_CHAIN,
            destination=self.destination,
            amount=self.amount,
            anchor_bh=self.anchor_bh,
            execution_bh=self.execution_bh,
            coherence=820_000,
            threshold=self.THRESHOLD,
            hhi_at_emission=1_200,
            total_effective_power=total,
            validator_count=len(self.entries),
            awa_enforced=True,
            issued_at=self.m.now - 100,
            ttl=3_600,
        )

    def make_payload(self, **overrides) -> bytes:
        return CanonicalCertificate(**{**self.cert_kwargs(), **overrides}).encode_payload()

    def make_envelope(self, payload: bytes, signer_indices, weight_overrides=None,
                      family=2, sig_overrides=None):
        sigs = []
        for i in signer_indices:
            entry = self.entries[i]
            stake, div = entry.stake_weight, entry.diversity_weight
            if weight_overrides and i in weight_overrides:
                stake, div = weight_overrides[i]
            sig = self.keys[i].sign(payload)
            if sig_overrides and i in sig_overrides:
                sig = sig_overrides[i]
            sigs.append({
                "validator_id": entry.validator_id,
                "stake_weight": stake,
                "diversity_weight": div,
                "signature": sig,
            })
        return {"family": family, "signatures": sigs}

    def accounts(self, registry_addr=None):
        return {
            "registry": registry_addr or self.registry_addr,
            "escrow": self.escrow_addr,
            "vault": self.vault_addr,
            "destination": self.destination,
            "consumed": self.consumed_addr,
        }

    def release(self, payload, envelope, cert_epoch=1, submitter=None,
                ed_plan="honest", **acct_overrides):
        """Submit a release transaction. `ed_plan` controls the
        Ed25519SigVerify instructions that accompany the release
        instruction (the client-side half of §6 step 5a):

          "honest"    — one self-contained ed instruction covering every
                        envelope signature (the well-formed client);
          "cross_ref" — one ed instruction whose message bytes live in the
                        RELEASE instruction's own data (cross-instruction
                        index refs, the budget-saving client layout);
          "none"      — no ed instructions at all (envelope-only attack);
          "after"     — ed instructions placed AFTER the release
                        instruction (executed later — not introspectable);
          a list      — the explicit transaction instruction list to run;
                        release is appended LAST unless "after" style.
        """
        accts = self.accounts()
        accts.update(acct_overrides)

        # resolve validator pubkeys from the registry the release actually
        # targets (may be a rotated epoch set, not self.entries)
        reg_data = self.m._get_typed(accts["registry"], "registry")
        reg_by_id = {e.validator_id: e for e in reg_data.validators}

        def _release(**kw):
            return self.m.release_escrow(
                submitter or self.submitter, accts["registry"], accts["escrow"],
                accts["vault"], accts["destination"], accts["consumed"],
                payload, cert_epoch, envelope, **kw)

        release_ix = TxInstruction(PROGRAM_ID, [], b"release")
        if ed_plan == "honest":
            # the well-formed client pre-verifies every REGISTERED
            # envelope signer in one self-contained ed instruction
            entries = []
            for s in envelope["signatures"]:
                ent = reg_by_id.get(s["validator_id"])
                if ent is None or len(s["signature"]) != CERT_ED25519_SIG_LEN:
                    continue   # unregistered/garbage signers: no honest
                               # client would pre-verify them
                entries.append({"pk": ent.ed25519_pubkey,
                                "sig": s["signature"], "msg": payload})
            if entries:
                tx = [TxInstruction(ED25519_PROGRAM_ID, [],
                                    build_ed_instruction_data(entries))]
            else:
                tx = []
            tx.append(release_ix)
        elif ed_plan == "cross_ref":
            # release instruction data: 8-byte anchor disc + borsh
            # (payload Vec) + epoch + envelope — the payload sits at a
            # known offset; the ed entries reference it cross-instruction
            # (msg_ix = release index), only pubkeys are embedded.
            payload_off = 8 + 4
            release_ix.data = (
                b"\x9a\x1e\xdc\x3b\x6c\xd1\x0f\x74"
                + struct.pack("<I", len(payload)) + payload
            )
            entries = []
            for s in envelope["signatures"]:
                ent = reg_by_id.get(s["validator_id"])
                if ent is None or len(s["signature"]) != CERT_ED25519_SIG_LEN:
                    continue
                entries.append({
                    "pk": ent.ed25519_pubkey,
                    "sig": s["signature"],
                    "msg_ix": 1, "msg_off": payload_off,
                    "msg_size": len(payload),
                })
            if entries:
                tx = [TxInstruction(ED25519_PROGRAM_ID, [],
                                    build_ed_instruction_data(entries))]
            else:
                tx = []
            tx.append(release_ix)
        elif ed_plan == "none":
            tx = [release_ix]
        elif ed_plan == "after":
            entries = [
                {"pk": self.entries[i].ed25519_pubkey,
                 "sig": self.keys[i].sign(payload), "msg": payload}
                for i in range(min(3, len(self.keys)))
            ]
            ed_ix = TxInstruction(ED25519_PROGRAM_ID, [],
                                  build_ed_instruction_data(entries))
            tx = [release_ix, ed_ix]
        else:
            tx = list(ed_plan)

        # The runtime executes ed instructions in order; a failure aborts
        # the transaction. release runs LAST (current_index = len(tx)-1).
        for ix in tx[:-1]:
            if ix.program_id == ED25519_PROGRAM_ID:
                execute_ed_instruction(ix, tx)
        # "after": the trailing ed instruction never executes before
        # release — model it as not-yet-executed (introspection cannot
        # see the future anyway).
        return _release(tx=tx, current_index=len(tx) - 1)

    def destination_balance(self):
        return self.m.accounts[self.destination].lamports

    def vault_balance(self):
        return self.m.accounts[self.vault_addr].lamports


# ═════════════════════════════════════════════════════════════════════════════
# PART 2 — attack battery
# ═════════════════════════════════════════════════════════════════════════════

def expect_reject(w, fn, variants, name="", notes=""):
    """Assert fn raises ProgErr with one of `variants` (or AnchorErr /
    TxRejected — an account-constraint failure or a runtime transaction
    abort is also a fail-closed rejection)."""
    try:
        fn()
    except ProgErr as e:
        if e.variant in variants:
            return True
        return f"wrong error: {e.variant} (want {variants}) {notes}"
    except AnchorErr:
        return True          # account-constraint rejection is also fail-closed
    except TxRejected:
        return True          # the runtime aborted the whole transaction
    return f"NOT REJECTED — attack succeeded {notes}"


PASSED = []
FAILED = []


def check(name, cond, detail=""):
    if cond is True:
        PASSED.append(name)
        print(f"  OK   {name}")
    else:
        FAILED.append((name, detail))
        print(f"  FAIL {name}" + (f" — {detail}" if detail else ""))


def happy_paths():
    w = World()
    payload = w.make_payload()
    env = w.make_envelope(payload, [0, 1, 2])
    result = w.release(payload, env)
    ok = (
        result == "released"
        and w.destination_balance() == w.amount
        and w.vault_balance() == 0
        and w.m.accounts[w.consumed_addr].data.is_set == 1
        and w.m.accounts[w.escrow_addr].data.state == RELEASED
        and any(ev[0] == "EscrowReleased" for ev in w.m.events)
    )
    check("valid certificate releases: funds move exactly once, consumed PDA written", ok)

    # boundary: now == issued_at + ttl is still valid (inclusive upper bound)
    w2 = World()
    p2 = w2.make_payload(issued_at=w2.m.now - 3_600, ttl=3_600)
    check("certificate exactly at expiry boundary still valid (now == issued+ttl)",
          w2.release(p2, w2.make_envelope(p2, [0, 1, 2])) == "released")

    # boundary: issued_at 60s in the future is tolerated (drift, lower bound only)
    w3 = World()
    p3 = w3.make_payload(issued_at=w3.m.now + 60, ttl=3_600)
    check("certificate 60s future-dated accepted (drift tolerance lower bound)",
          w3.release(p3, w3.make_envelope(p3, [0, 1, 2])) == "released")

    # tier-2 boundary: d=0.5 → 0.75 quorum; 3 of 4 signers = exactly 0.75 → valid
    w4 = World(diversity=500_000)
    p4 = w4.make_payload()
    check("tier-2 quorum met at exactly 0.75 (4·signed == 3·total)",
          w4.release(p4, w4.make_envelope(p4, [0, 1, 2])) == "released")


def structure_attacks():
    w = World()
    good = w.make_payload()
    env = w.make_envelope(good, [0, 1, 2])
    check("wrong payload width rejected (345 bytes)",
          expect_reject(w, lambda: w.release(good[:-1], env), ["MalformedCertificate"]))
    bad_tag = bytearray(good); bad_tag[0] = 0x58
    check("bad domain tag rejected",
          expect_reject(w, lambda: w.release(bytes(bad_tag), env), ["MalformedCertificate"]))
    p2 = w.make_payload(certificate_kind=2)          # bootstrap kind — §14.4 undecided
    check("kind=2 (bootstrap) rejected — fail-closed pending governance",
          expect_reject(w, lambda: w.release(p2, w.make_envelope(p2, [0, 1, 2])),
                        ["UnknownCertificateKind"]))
    p3 = w.make_payload(protocol_version=pack_version(2, 0, 0))
    check("protocol_version 2.0.0 rejected (verifier supports 1.0.0)",
          expect_reject(w, lambda: w.release(p3, w.make_envelope(p3, [0, 1, 2])),
                        ["VersionIncompatible"]))
    check("family=1 (secp256k1) envelope rejected on SVM",
          expect_reject(w, lambda: w.release(good, w.make_envelope(good, [0, 1, 2], family=1)),
                        ["WrongSignatureFamily"]))
    check("2 signers rejected (< 3 liveness floor)",
          expect_reject(w, lambda: w.release(good, w.make_envelope(good, [0, 1])),
                        ["InsufficientSigners"]))
    env_dup = w.make_envelope(good, [0, 1, 2])
    env_dup["signatures"][2]["validator_id"] = env_dup["signatures"][0]["validator_id"]
    check("duplicate validator_id rejected (power double-count blocked)",
          expect_reject(w, lambda: w.release(good, env_dup), ["DuplicateSigner"]))
    env_bad = w.make_envelope(good, [0, 1, 2])
    env_bad["signatures"][0]["signature"] = env_bad["signatures"][0]["signature"][:-1]
    check("63-byte signature rejected",
          expect_reject(w, lambda: w.release(good, env_bad), ["MalformedSignature"]))
    check("cert_epoch argument != payload epoch rejected",
          expect_reject(w, lambda: w.release(good, env, cert_epoch=2),
                        ["EpochArgumentMismatch"]))


def epoch_attacks():
    # future epoch: registry PDA for that epoch does not exist → fail-closed
    w = World()
    p = w.make_payload(validator_epoch=2, certificate_nonce=2)
    check("future epoch (unregistered registry PDA) rejected",
          expect_reject(w, lambda: w.release(p, w.make_envelope(p, [0, 1, 2]), cert_epoch=2),
                        ["EpochFuture"]))
    # stale epoch beyond the 2-epoch grace: register 2, 3, 4 → latest 4,
    # grace floor 2 → an epoch-1 certificate is stale even though its
    # registry account still exists
    w2 = World()
    keys = make_keys(4, "rotated")
    entries = [ValidatorEntry(canonical_validator_id(e, i), pub_of(k), 1_000_000, 700_000)
               for e in (2, 3, 4) for i, k in enumerate(keys)]
    for e in (2, 3, 4):
        w2.m.register_epoch(w2.registrar, e, entries[(e - 2) * 4:(e - 1) * 4],
                            World.THRESHOLD)
    stale = w2.make_payload()          # epoch 1 cert, registry-1 exists
    check("stale epoch (1, latest 4, grace 2) rejected",
          expect_reject(w2, lambda: w2.release(stale, w2.make_envelope(stale, [0, 1, 2])),
                        ["EpochStale"]))
    # fresh epoch within grace releases fine
    w3 = World()
    keys3 = make_keys(4, "epoch2")
    entries3 = [ValidatorEntry(canonical_validator_id(2, i), pub_of(k), 1_000_000, 700_000)
                for i, k in enumerate(keys3)]
    registry2_addr = w3.m.register_epoch(w3.registrar, 2, entries3,
                                         World.THRESHOLD)
    total3 = sum(effective_power(v) for v in entries3)
    p3 = w3.make_payload(validator_epoch=2, certificate_nonce=5,
                         total_effective_power=total3)
    env3 = {"family": 2, "signatures": [
        {"validator_id": entries3[i].validator_id, "stake_weight": 1_000_000,
         "diversity_weight": 700_000, "signature": keys3[i].sign(p3)}
        for i in (0, 1, 2)]}
    check("fresh epoch (2, latest 2) releases within grace",
          w3.release(p3, env3, cert_epoch=2,
                     registry=registry2_addr) == "released")
    # no epoch registered at all → fail closed
    w4 = World()
    w4.m._get_typed(pda(SEED_CONFIG), "config").latest_epoch = 0
    p4 = w4.make_payload()
    check("no registered epoch rejects every certificate (fail-closed bootstrap)",
          expect_reject(w4, lambda: w4.release(p4, w4.make_envelope(p4, [0, 1, 2])),
                        ["NoEpochRegistered"]))
    # min_validator_count policy (launch threshold)
    w5 = World(min_validator_count=5)
    p5 = w5.make_payload()
    check("registry below deployment min_validator_count rejected (launch threshold)",
          expect_reject(w5, lambda: w5.release(p5, w5.make_envelope(p5, [0, 1, 2])),
                        ["TooFewValidators"]))


def freshness_attacks():
    w = World()
    p = w.make_payload(issued_at=w.m.now - 4_000, ttl=3_600)
    check("expired certificate rejected (now > issued+ttl)",
          expect_reject(w, lambda: w.release(p, w.make_envelope(p, [0, 1, 2])),
                        ["CertificateExpired"]))
    w2 = World()
    p2 = w2.make_payload(issued_at=w2.m.now + 61)
    check("certificate 61s future-dated rejected (drift is 60s, lower bound only)",
          expect_reject(w2, lambda: w2.release(p2, w2.make_envelope(p2, [0, 1, 2])),
                        ["CertificateFutureDated"]))
    w3 = World()
    p3 = w3.make_payload(ttl=0)
    check("ttl=0 rejected (born expired)",
          expect_reject(w3, lambda: w3.release(p3, w3.make_envelope(p3, [0, 1, 2])),
                        ["InvalidTtl"]))
    w4 = World()
    p4 = w4.make_payload(ttl=CERT_TTL_MAX + 1)
    check("ttl > 7 days rejected (canonical max)",
          expect_reject(w4, lambda: w4.release(p4, w4.make_envelope(p4, [0, 1, 2])),
                        ["InvalidTtl"]))


def consensus_attacks():
    w = World()
    p = w.make_payload(hhi_at_emission=4_001)
    check("hhi_at_emission 4001 rejected (L4.8 CRITICAL)",
          expect_reject(w, lambda: w.release(p, w.make_envelope(p, [0, 1, 2])),
                        ["HhiCritical"]))
    w2 = World()
    p2 = w2.make_payload(awa_enforced=False)
    check("awa_enforced=0 rejected (emission was frozen)",
          expect_reject(w2, lambda: w2.release(p2, w2.make_envelope(p2, [0, 1, 2])),
                        ["AwaNotEnforced"]))
    w3 = World()
    p3 = w3.make_payload(coherence=549_999)      # < threshold 550_000
    check("coherence < threshold rejected (not isSafe)",
          expect_reject(w3, lambda: w3.release(p3, w3.make_envelope(p3, [0, 1, 2])),
                        ["CoherenceBelowThreshold"]))
    w4 = World()
    p4 = w4.make_payload(validator_count=5)      # registry has 4
    check("validator_count lie rejected (cert vs registry)",
          expect_reject(w4, lambda: w4.release(p4, w4.make_envelope(p4, [0, 1, 2])),
                        ["ValidatorCountMismatch"]))
    w5 = World()
    p5 = w5.make_payload(threshold=540_000)      # registry Θ = 550_000 (H-03)
    check("threshold != registered epoch Θ(t) rejected (H-03: proof cannot set its own bar)",
          expect_reject(w5, lambda: w5.release(p5, w5.make_envelope(p5, [0, 1, 2])),
                        ["ThresholdMismatch"]))


def signature_attacks():
    w = World()
    p = w.make_payload()
    # unregistered signer: a real ed25519 key NOT in the registry
    rogue = make_keys(1, "rogue")[0]
    rogue_id = sha3_256(b"rogue-validator")
    env = w.make_envelope(p, [0, 1])
    env["signatures"].append({
        "validator_id": rogue_id,
        "stake_weight": 1_000_000, "diversity_weight": 700_000,
        "signature": rogue.sign(p),
    })
    check("unregistered signer rejected (real sig, unknown validator_id)",
          expect_reject(w, lambda: w.release(p, env), ["UnregisteredValidator"]))
    # forged signature: registered validator_id, signature by a different key
    # — the runtime ed instruction (if the attacker even includes one)
    # fails to verify → the whole transaction aborts
    w2 = World()
    p2 = w2.make_payload()
    forged = {"family": 2, "signatures": [
        {"validator_id": w2.entries[i].validator_id, "stake_weight": 1_000_000,
         "diversity_weight": 700_000,
         "signature": make_keys(1, "attacker")[0].sign(p2)}
        for i in (0, 1, 2)]}
    check("forged signature rejected (runtime ed25519 verify fails — tx aborted)",
          expect_reject(w2, lambda: w2.release(p2, forged),
                        ["SignatureVerificationFailed"]))
    # same forged envelope, but WITHOUT any ed instruction: introspection
    # finds no runtime-verified triple → fail-closed
    check("forged signature without ed instructions rejected (introspection fails)",
          expect_reject(w2, lambda: w2.release(p2, forged, ed_plan="none"),
                        ["SignatureVerificationFailed"]))
    # weight claim lie (envelope weight != registered)
    w3 = World()
    p3 = w3.make_payload()
    env3 = w3.make_envelope(p3, [0, 1, 2], weight_overrides={0: (1_000_000, 999_999)})
    check("envelope diversity-weight claim lie rejected (weights are claims, not authority)",
          expect_reject(w3, lambda: w3.release(p3, env3), ["WeightClaimMismatch"]))


def introspection_attacks():
    """§6 step 5a — the instructions-sysvar introspection discipline,
    including the Relay 'Wrong Offset' bypass class (Sept 2025)."""
    # (a) no Ed25519SigVerify instructions at all: the envelope alone is
    # NOT authority — this is the C-03 regression shape (a key that
    # controls the submitting wallet cannot release without the quorum's
    # signatures being runtime-verified)
    w = World()
    p = w.make_payload()
    env = w.make_envelope(p, [0, 1, 2])
    check("envelope without runtime ed verification rejected (no-key-release)",
          expect_reject(w, lambda: w.release(p, env, ed_plan="none"),
                        ["SignatureVerificationFailed"]))

    # (b) valid ed instructions placed AFTER the release instruction are
    # never introspected (only already-executed instructions count)
    w2 = World()
    p2 = w2.make_payload()
    check("ed instructions placed after release are not introspected (rejected)",
          expect_reject(w2, lambda: w2.release(p2, w2.make_envelope(p2, [0, 1, 2]),
                                               ed_plan="after"),
                        ["SignatureVerificationFailed"]))

    # (c) the RELAY WRONG-OFFSET BYPASS: the attacker's ed instruction
    # embeds the VICTIM validator's pubkey at offset 16 — exactly where a
    # naive hardcoded-offset parser (the Relay bug) reads the pubkey —
    # while public_key_offset actually points at the ATTACKER's key and
    # the attacker's own genuine signature over the payload. The runtime
    # verifies the attacker's triple (the tx passes!); only the program's
    # offsets-faithful three-way match refuses to credit it.
    w3 = World()
    p3 = w3.make_payload()
    victim_pk = w3.entries[0].ed25519_pubkey
    attacker_key = make_keys(1, "wrong-offset-attacker")[0]
    attacker_pk = attacker_key.public_key().public_bytes_raw()
    attacker_sig = attacker_key.sign(p3)
    # blob layout (after the 16-byte header):
    #   [16..48)   victim_pk   — the naive-parser decoy
    #   [48..112)  attacker_sig
    #   [112..144) attacker_pk — what public_key_offset REALLY points at
    #   [144..490) payload     — the message under verification
    header_len = 2 + ED_IX_OFFSETS_LEN
    malicious = (
        struct.pack("<BB", 1, 0)
        + struct.pack(
            "<7H",
            header_len + 32, U16_MAX,                    # sig → attacker_sig
            header_len + 32 + 64, U16_MAX,               # pk  → attacker_pk
            header_len + 32 + 64 + 32, len(p3), U16_MAX, # msg → payload
        )
        + victim_pk + attacker_sig + attacker_pk + p3
    )
    # the trap is real: offset 16 (where the Relay-style hardcoded parser
    # reads the pubkey) really does hold the VICTIM key
    check("wrong-offset attack: decoy victim pubkey sits at the naive parser's offset",
          malicious[16:48] == victim_pk)
    attacker_tx = [
        TxInstruction(ED25519_PROGRAM_ID, [], malicious),
        TxInstruction(PROGRAM_ID, [], b"release"),
    ]
    env3 = w3.make_envelope(p3, [0, 1, 2])
    # the attacker replaces the envelope's first signature with its own
    # (entries 1-2 have no ed entries: the attacker cannot produce the
    # quorum's signatures — that is the whole point of the certificate)
    env3["signatures"][0]["signature"] = attacker_sig
    # first: prove the RUNTIME accepts the malicious instruction (the
    # attacker's signature is genuinely valid over the payload)
    runtime_ok = True
    try:
        execute_ed_instruction(attacker_tx[0], attacker_tx)
    except TxRejected:
        runtime_ok = False
    check("wrong-offset attack: the runtime DOES verify the attacker's triple",
          runtime_ok, "runtime should pass (attacker sig is genuine)")
    # and the program still refuses: entry 0 must be covered by
    # (victim pubkey, envelope sig, payload) — the runtime never verified
    # the victim key signing anything
    check("wrong-offset attack rejected (Relay bypass class closed by three-way match)",
          expect_reject(
              w3,
              lambda: w3.m.release_escrow(
                  w3.submitter, w3.registry_addr, w3.escrow_addr, w3.vault_addr,
                  w3.destination, w3.consumed_addr, p3, 1, env3,
                  tx=attacker_tx, current_index=1),
              ["SignatureVerificationFailed"]))

    # (d) cross-instruction reference that resolves to a FOREIGN message:
    # the runtime verifies (victim key, sig, different message) — no match
    # against the payload under verification
    w4 = World()
    p4 = w4.make_payload()
    other_msg = sha3_256(b"not-the-payload")
    foreign_tx = [
        TxInstruction(ED25519_PROGRAM_ID, [],
                      build_ed_instruction_data([
                          {"pk": w4.entries[0].ed25519_pubkey,
                           "sig": w4.keys[0].sign(other_msg),
                           "msg": other_msg}])),
        TxInstruction(PROGRAM_ID, [], b"release"),
    ]
    env4 = w4.make_envelope(p4, [0, 1, 2])
    env4["signatures"][0]["signature"] = w4.keys[0].sign(other_msg)
    check("runtime-verified signature over a foreign message rejected (message mismatch)",
          expect_reject(
              w4,
              lambda: w4.m.release_escrow(
                  w4.submitter, w4.registry_addr, w4.escrow_addr, w4.vault_addr,
                  w4.destination, w4.consumed_addr, p4, 1, env4,
                  tx=foreign_tx, current_index=1),
              ["SignatureVerificationFailed"]))

    # (e) an ed instruction WITH ACCOUNTS is not a verification source
    # (the precompile is stateless — accounts disqualify it)
    w5 = World()
    p5 = w5.make_payload()
    env5 = w5.make_envelope(p5, [0, 1, 2])
    honest_entries = [
        {"pk": w5.entries[i].ed25519_pubkey, "sig": w5.keys[i].sign(p5),
         "msg": p5} for i in (0, 1, 2)]
    with_accounts_tx = [
        TxInstruction(ED25519_PROGRAM_ID, [b"fake-account"],
                      build_ed_instruction_data(honest_entries)),
        TxInstruction(PROGRAM_ID, [], b"release"),
    ]
    check("ed instruction carrying accounts is not a verification source",
          expect_reject(
              w5,
              lambda: w5.m.release_escrow(
                  w5.submitter, w5.registry_addr, w5.escrow_addr, w5.vault_addr,
                  w5.destination, w5.consumed_addr, p5, 1, env5,
                  tx=with_accounts_tx, current_index=1),
              ["SignatureVerificationFailed"]))

    # (f) POSITIVE: cross-instruction references ARE a valid verification
    # source when the referenced bytes really are the payload — this is
    # the budget-saving client layout from the integration guide
    w6 = World()
    p6 = w6.make_payload()
    check("cross-instruction message reference (payload in the release ix) releases",
          w6.release(p6, w6.make_envelope(p6, [0, 1, 2]), ed_plan="cross_ref")
          == "released")

    # (g) malicious out-of-bounds offsets resolve to nothing → no match
    # (message_data_offset far past the end of the instruction data)
    w7 = World()
    p7 = w7.make_payload()
    env7 = w7.make_envelope(p7, [0, 1, 2])
    oob_data = (
        struct.pack("<BB", 1, 0)
        + struct.pack("<7H", 16, U16_MAX, 16 + 64, U16_MAX, 60_000, len(p7), U16_MAX)
        + w7.keys[0].sign(p7) + w7.entries[0].ed25519_pubkey
    )
    oob_tx = [
        TxInstruction(ED25519_PROGRAM_ID, [], oob_data),
        TxInstruction(PROGRAM_ID, [], b"release"),
    ]
    check("out-of-bounds message offset resolves to nothing (fail-closed)",
          expect_reject(
              w7,
              lambda: w7.m.release_escrow(
                  w7.submitter, w7.registry_addr, w7.escrow_addr, w7.vault_addr,
                  w7.destination, w7.consumed_addr, p7, 1, env7,
                  tx=oob_tx, current_index=1),
              ["SignatureVerificationFailed"]))


def quorum_attacks():
    # tier 1 (D=0.7), 6 equal validators: 3 signers (exactly half the
    # power, above the 3-signer liveness floor) → no quorum
    w = World(n_validators=6)
    p = w.make_payload()
    check("low-weight quorum rejected (3 of 6 signers, tier 1)",
          expect_reject(w, lambda: w.release(p, w.make_envelope(p, [0, 1, 2])),
                        ["InsufficientQuorum"]))
    # exactly-2/3 is NOT a quorum (STRICT): 6 validators, 4 sign
    w2 = World(n_validators=6)
    p2 = w2.make_payload()
    check("exactly-2/3 signed power rejected (tier-1 STRICT: 3·signed == 2·total)",
          expect_reject(w2, lambda: w2.release(p2, w2.make_envelope(p2, [0, 1, 2, 3])),
                        ["InsufficientQuorum"]))
    check("5 of 6 signed power accepted (strictly above 2/3)",
          w2.release(p2, w2.make_envelope(p2, [0, 1, 2, 3, 4])) == "released")
    # tier 2 (D=0.5): 6 validators, 3 signers (0.5 < 0.75) rejected
    w3 = World(n_validators=6, diversity=500_000)
    p3 = w3.make_payload()
    check("tier-2 quorum 0.5 of power rejected (needs ≥ 0.75)",
          expect_reject(w3, lambda: w3.release(p3, w3.make_envelope(p3, [0, 1, 2])),
                        ["InsufficientQuorum"]))
    # tier 3 (D=0.3): 3 of 4 (0.75 < 0.85) rejected
    w4 = World(diversity=300_000)
    p4 = w4.make_payload()
    check("tier-3 quorum 0.75 of power rejected (needs ≥ 0.85)",
          expect_reject(w4, lambda: w4.release(p4, w4.make_envelope(p4, [0, 1, 2])),
                        ["InsufficientQuorum"]))
    # power lie: certificate claims a bigger set
    w5 = World()
    p5 = w5.make_payload(total_effective_power=999_999_999)
    check("total_effective_power lie rejected (cert lied about the set)",
          expect_reject(w5, lambda: w5.release(p5, w5.make_envelope(p5, [0, 1, 2])),
                        ["PowerMismatch"]))
    # registry corruption: stored power drifts from entries
    w6 = World()
    p6 = w6.make_payload()
    w6.m.accounts[w6.registry_addr].data.total_effective_power += 1
    check("registry stored-power drift rejected (RegistryPowerMismatch)",
          expect_reject(w6, lambda: w6.release(p6, w6.make_envelope(p6, [0, 1, 2])),
                        ["RegistryPowerMismatch"]))


def binding_attacks():
    cases = [
        ("escrow_id mismatch", dict(escrow_id=sha3_256(b"other-escrow")), ["EscrowMismatch"]),
        ("route_id mismatch", dict(route_id=sha3_256(b"other-route")), ["RouteMismatch"]),
        ("intent_hash mismatch", dict(intent_hash=sha3_256(b"other-intent")), ["IntentMismatch"]),
        ("entity_id mismatch", dict(entity_id=sha3_256(b"other-entity")), ["EntityMismatch"]),
        ("destination mismatch (settlement tuple)", dict(destination=sha3_256(b"evil-dest")),
         ["DestinationMismatch"]),
        ("amount mismatch (settlement tuple)", None, ["AmountMismatch"]),
        ("amount above u64 rejected", dict(amount=2**64), ["AmountTooLarge"]),
        ("source_chain mismatch", dict(source_chain=2), ["ChainMismatch"]),
        # lib.rs checks escrow-binding first (ChainMismatch), then the
        # deployment firewall (WrongChain) — both fail-closed
        ("dest_chain != self_chain", dict(dest_chain=999),
         ["WrongChain", "ChainMismatch"]),
        ("anchor_bh mismatch", dict(anchor_bh=sha3_256(b"other-anchor")), ["AnchorMismatch"]),
        ("execution_bh mismatch", dict(execution_bh=sha3_256(b"other-exec")),
         ["ExecutionMismatch"]),
        ("coherence above Θ but below escrow min_coherence",
         dict(coherence=699_999), ["CoherenceInsufficient"]),
    ]
    for name, overrides, variants in cases:
        w = World()
        if name.startswith("amount mismatch"):
            overrides = {"amount": w.amount - 1}
        p = w.make_payload(**overrides)
        check(f"binding: {name} rejected",
              expect_reject(w, lambda p=p: w.release(p, w.make_envelope(p, [0, 1, 2])),
                            variants))


def replay_attacks():
    # idempotent resubmission: same certificate → no-op, no double pay
    w = World()
    p = w.make_payload()
    env = w.make_envelope(p, [0, 1, 2])
    w.release(p, env)
    bal = w.destination_balance()
    result = w.release(p, env)
    check("replayed identical certificate is an idempotent no-op (no second payment)",
          result == "idempotent" and w.destination_balance() == bal)
    # same (epoch, escrow, nonce) but different payload → conflict + evidence
    w2 = World()
    p_a = w2.make_payload(coherence=820_000)
    w2.release(p_a, w2.make_envelope(p_a, [0, 1, 2]))
    p_b = w2.make_payload(coherence=850_000)     # same nonce 1, different hash
    check("same-nonce different-certificate conflict rejected + equivocation event",
          expect_reject(w2, lambda: w2.release(p_b, w2.make_envelope(p_b, [0, 1, 2])),
                        ["CertificateConflict"])
          and any(ev[0] == "EquivocationDetected" for ev in w2.m.events))
    # fully valid HIGHER-nonce second certificate cannot double-release
    w3 = World()
    p1 = w3.make_payload(certificate_nonce=1)
    w3.release(p1, w3.make_envelope(p1, [0, 1, 2]))
    bal = w3.destination_balance()
    p2 = w3.make_payload(certificate_nonce=2)
    check("double-release via higher-nonce valid certificate rejected (exactly-once)",
          expect_reject(w3, lambda: w3.release(p2, w3.make_envelope(p2, [0, 1, 2])),
                        ["CertificateConflict"])
          and w3.destination_balance() == bal)


def account_attacks():
    w = World()
    p = w.make_payload()
    env = w.make_envelope(p, [0, 1, 2])
    # wrong registry address (PDA derivation mismatch — anchor seeds constraint)
    check("wrong registry PDA address rejected (seeds constraint)",
          expect_reject(w, lambda: w.release(p, env, registry=sha3_256(b"fake-registry")),
                        [], ""))
    # wrong vault address
    check("wrong vault PDA address rejected (seeds constraint)",
          expect_reject(w, lambda: w.release(p, env, vault=sha3_256(b"fake-vault")),
                        [], ""))
    # fake destination account (anchor address = escrow.destination)
    check("fake destination account rejected (address constraint + settlement tuple)",
          expect_reject(w, lambda: w.release(p, env, destination=sha3_256(b"fake-dest")),
                        [], ""))
    # fake escrow account at the wrong PDA
    check("wrong escrow PDA address rejected (seeds constraint)",
          expect_reject(w, lambda: w.release(p, env, escrow=sha3_256(b"fake-escrow")),
                        [], ""))
    # vault underfunded → typed error before transfer
    w2 = World()
    p2 = w2.make_payload()
    w2.m.accounts[w2.vault_addr].lamports = 1
    check("underfunded vault rejected (InsufficientFunds)",
          expect_reject(w2, lambda: w2.release(p2, w2.make_envelope(p2, [0, 1, 2])),
                        ["InsufficientFunds"]))


def state_attacks():
    # release on a reverted escrow
    w = World()
    w.m.revert_escrow(w.owner, w.escrow_addr, w.vault_addr, w.funder, REASON_MANUAL)
    p = w.make_payload()
    check("release on REVERTED escrow rejected (terminal state)",
          expect_reject(w, lambda: w.release(p, w.make_envelope(p, [0, 1, 2])),
                        ["NotHolding"]))
    # release after slot timeout
    w2 = World()
    w2.m.slot = w2.m.accounts[w2.escrow_addr].data.lock_slot + 10_001
    p2 = w2.make_payload()
    check("release after escrow slot timeout rejected (release-after-timeout refused)",
          expect_reject(w2, lambda: w2.release(p2, w2.make_envelope(p2, [0, 1, 2])),
                        ["Expired"]))


def old_authority_attacks():
    """The original C-03: the single oracle key WAS the release authority."""
    w = World()
    oracle_key = sha3_256(b"trion-oracle-key")
    w.m.bind_pause_authority(w.owner, oracle_key)
    p = w.make_payload()

    # (a) the old release call shape (no certificate) — garbage payload
    check("oracle key cannot release without a certificate (C-03: no-key-release)",
          expect_reject(w, lambda: w.release(b"release everything please",
                                             {"family": 2, "signatures": []}),
                        ["MalformedCertificate"]))
    # (b) the oracle key submits a certificate signed only by itself
    forged = {"family": 2, "signatures": [
        {"validator_id": sha3_256(b"oracle-as-validator"),
         "stake_weight": 1_000_000, "diversity_weight": 700_000,
         "signature": make_keys(1, "oracle-fake")[0].sign(p)}] * 3}
    env_forged = {"family": 2, "signatures": [
        {**forged["signatures"][0]},
        {**forged["signatures"][1], "validator_id": sha3_256(b"oracle-as-validator-2")},
        {**forged["signatures"][2], "validator_id": sha3_256(b"oracle-as-validator-3")},
    ]}
    check("oracle-key signatures are unregistered validators (not in epoch set)",
          expect_reject(w, lambda: w.release(p, env_forged), ["UnregisteredValidator"]))
    # (c) pause semantics: pause blocks NEW locks but NEVER release/revert
    w.m.pause(oracle_key)
    try:
        w.m.lock_escrow(
            relayer=w.relayer, vault_funder=w.funder,
            escrow_id=sha3_256(b"escrow-b"), route_id=sha3_256(b"route-b"),
            intent_hash=sha3_256(b"intent-b"), entity_id=sha3_256(b"entity-b"),
            amount=1_000, min_coherence=700_000, source_chain=1,
            dest_chain=World.SELF_CHAIN, anchor_bh=sha3_256(b"anchor-b"),
            execution_bh=sha3_256(b"execution-b"), timeout_slots=100,
            destination=sha3_256(b"dest-b"))
        lock_blocked = False
    except ProgErr as e:
        lock_blocked = e.variant == "Paused"
    except AnchorErr:
        lock_blocked = True
    check("pause blocks NEW locks", lock_blocked)
    check("pause does NOT block certificate release (settlement proceeds)",
          w.release(p, w.make_envelope(p, [0, 1, 2])) == "released")
    w.m.unpause(oracle_key)
    try:
        w.m.lock_escrow(
            relayer=w.relayer, vault_funder=w.funder,
            escrow_id=sha3_256(b"escrow-b"), route_id=sha3_256(b"route-b"),
            intent_hash=sha3_256(b"intent-b"), entity_id=sha3_256(b"entity-b"),
            amount=1_000, min_coherence=700_000, source_chain=1,
            dest_chain=World.SELF_CHAIN, anchor_bh=sha3_256(b"anchor-b"),
            execution_bh=sha3_256(b"execution-b"), timeout_slots=100,
            destination=sha3_256(b"dest-b"))
        lock_ok = True
    except (ProgErr, AnchorErr):
        lock_ok = False
    check("unpause restores locking", lock_ok)
    # (d) a non-authority cannot pause
    w2 = World()
    try:
        w2.m.pause(sha3_256(b"random-key"))
        pause_blocked = False
    except ProgErr as e:
        pause_blocked = e.variant == "NotAuthorized"
    check("random key cannot pause", pause_blocked)
    # (e) one-way pause-authority binding
    w3 = World()
    w3.m.bind_pause_authority(w3.owner, sha3_256(b"pause-key-1"))
    try:
        w3.m.bind_pause_authority(w3.owner, sha3_256(b"pause-key-2"))
        oneway = False
    except ProgErr as e:
        oneway = e.variant == "NotAuthorized"
    check("pause-authority binding is one-way (cannot rebind)", oneway)


def revert_attacks():
    # timeout revert is permissionless
    w = World()
    w.m.slot = w.m.accounts[w.escrow_addr].data.lock_slot + 10_001
    random_caller = sha3_256(b"anyone")
    res = w.m.revert_escrow(random_caller, w.escrow_addr, w.vault_addr, w.funder,
                            REASON_TIMEOUT)
    check("timeout revert permissionless (funds returned to locker)",
          res == "reverted" and w.m.accounts[w.funder].lamports >= w.amount)
    # second revert refused (terminal)
    try:
        w.m.revert_escrow(random_caller, w.escrow_addr, w.vault_addr, w.funder,
                          REASON_TIMEOUT)
        terminal = False
    except ProgErr as e:
        terminal = e.variant == "NotHolding"
    check("second revert refused (terminal state)", terminal)
    # E6: 7-day emergency revert permissionless even with huge timeout
    w2 = World()
    w2.m.now += EMERGENCY_REVERT_SECONDS + 1
    res2 = w2.m.revert_escrow(sha3_256(b"anyone"), w2.escrow_addr, w2.vault_addr,
                              w2.funder, REASON_EMERGENCY)
    check("E6: permissionless 7-day emergency revert",
          res2 == "reverted"
          and w2.m.accounts[w2.escrow_addr].data.state == EMERGENCY_REVERTED)
    # emergency before 7 days by a random caller is refused
    w3 = World()
    try:
        w3.m.revert_escrow(sha3_256(b"anyone"), w3.escrow_addr, w3.vault_addr,
                           w3.funder, REASON_EMERGENCY)
        early = False
    except ProgErr as e:
        early = e.variant == "NotRelayerForRevert"
    check("emergency revert before 7 days by a random caller refused", early)
    # non-timeout revert by random caller refused
    w4 = World()
    try:
        w4.m.revert_escrow(sha3_256(b"anyone"), w4.escrow_addr, w4.vault_addr,
                           w4.funder, REASON_MANUAL)
        manual = False
    except ProgErr as e:
        manual = e.variant == "NotRelayerForRevert"
    check("non-timeout manual revert by a random caller refused", manual)


def admin_attacks():
    # initialize twice fails (init constraint)
    w = World()
    try:
        w.m.initialize(sha3_256(b"deployer-2"), 900)
        twice = False
    except AnchorErr:
        twice = True
    check("initialize can only be called once (init constraint)", twice)
    # register_epoch: wrong admin
    w2 = World()
    try:
        w2.m.register_epoch(sha3_256(b"not-admin"), 2, w2.entries, World.THRESHOLD)
        wrong_admin = False
    except ProgErr as e:
        wrong_admin = e.variant == "NotRegistryAdmin"
    check("register_epoch by a non-admin rejected", wrong_admin)
    # re-register the same epoch / lower epoch
    w3 = World()
    try:
        w3.m.register_epoch(w3.registrar, 1, w3.entries, World.THRESHOLD)
        re_reg = False
    except ProgErr as e:
        re_reg = e.variant == "EpochAlreadyRegistered"
    check("re-registering the same epoch rejected (immutable sets)", re_reg)
    try:
        w3.m.register_epoch(w3.registrar, 0, w3.entries, World.THRESHOLD)
        zero = False
    except ProgErr as e:
        zero = e.variant == "InvalidEpoch"
    check("epoch 0 rejected (epochs start at 1)", zero)
    # duplicate validator ids
    w4 = World()
    dup = list(w4.entries)
    dup[1] = ValidatorEntry(dup[0].validator_id, pub_of(make_keys(1, "dup")[0]),
                            1_000_000, 700_000)
    try:
        w4.m.register_epoch(w4.registrar, 2, dup, World.THRESHOLD)
        dup_ids = False
    except ProgErr as e:
        dup_ids = e.variant == "DuplicateValidator"
    check("duplicate validator_id in registration rejected", dup_ids)
    # duplicate pubkeys
    dup_keys = [ValidatorEntry(canonical_validator_id(2, i), pub_of(w4.keys[0]),
                               1_000_000, 700_000) for i in range(3)]
    try:
        w4.m.register_epoch(w4.registrar, 2, dup_keys, World.THRESHOLD)
        dup_pks = False
    except ProgErr as e:
        dup_pks = e.variant == "DuplicateValidatorKey"
    check("duplicate validator pubkey in registration rejected (key-sharing inflation)",
          dup_pks)
    # bad weights / threshold
    bad_w = [ValidatorEntry(canonical_validator_id(2, i), pub_of(w4.keys[i]),
                            0, 700_000) for i in range(3)]
    try:
        w4.m.register_epoch(w4.registrar, 2, bad_w, World.THRESHOLD)
        bad_weight = False
    except ProgErr as e:
        bad_weight = e.variant == "InvalidWeight"
    check("zero stake weight rejected at registration", bad_weight)
    try:
        w4.m.register_epoch(w4.registrar, 2, w4.entries, 0)
        bad_thr = False
    except ProgErr as e:
        bad_thr = e.variant == "InvalidThreshold"
    check("zero epoch threshold rejected at registration", bad_thr)
    # set_relayer by non-owner
    w5 = World()
    try:
        w5.m.set_relayer(sha3_256(b"not-owner"), sha3_256(b"new-relayer"))
        set_rel = False
    except ProgErr as e:
        set_rel = e.variant == "NotOwner"
    check("set_relayer by non-owner rejected", set_rel)


def lock_attacks():
    w = World()
    def lock(**kw):
        args = dict(
            relayer=w.relayer, vault_funder=w.funder,
            escrow_id=sha3_256(b"escrow-x"), route_id=sha3_256(b"route-x"),
            intent_hash=sha3_256(b"intent-x"), entity_id=sha3_256(b"entity-x"),
            amount=1_000, min_coherence=700_000, source_chain=1,
            dest_chain=World.SELF_CHAIN, anchor_bh=sha3_256(b"anchor-x"),
            execution_bh=sha3_256(b"execution-x"), timeout_slots=100,
            destination=sha3_256(b"dest-x"))
        args.update(kw)
        return w.m.lock_escrow(**args)
    try:
        lock(relayer=sha3_256(b"random"))
        auth = False
    except ProgErr as e:
        auth = e.variant == "NotAuthorized"
    check("lock by an unauthorized relayer rejected", auth)
    try:
        lock(dest_chain=999)
        chain = False
    except ProgErr as e:
        chain = e.variant == "WrongChain"
    check("lock with dest_chain != self_chain rejected", chain)
    try:
        lock(source_chain=0)
        sc = False
    except ProgErr as e:
        sc = e.variant == "ZeroChain"
    check("lock with source_chain=0 rejected", sc)
    try:
        lock(amount=0)
        amt = False
    except ProgErr as e:
        amt = e.variant == "ZeroAmount"
    check("lock with amount=0 rejected", amt)
    try:
        lock(min_coherence=1_000_001)
        coh = False
    except ProgErr as e:
        coh = e.variant == "InvalidCoherence"
    check("lock with min_coherence above 1e6 rejected (INV-003: cannot loosen above scale)",
          coh)
    try:
        lock(min_coherence=549_999)
        floor = False
    except ProgErr as e:
        floor = e.variant == "CoherenceFloor"
    check("lock with sub-floor min_coherence rejected (INV-003 follow-on 2: tighten-only)",
          floor)
    check("lock at exactly the 0.55 floor (550_000) accepted",
          lock(min_coherence=550_000,
               escrow_id=sha3_256(b"escrow-floor-ok")) is not None)
    funder_before = w.m.accounts[w.funder].lamports
    lock()  # valid
    check("lock encumbers exactly the amount (funder balance drops by amount only)",
          w.m.accounts[w.funder].lamports == funder_before - 1_000)
    try:
        lock()  # same escrow_id again
        dup = False
    except AnchorErr:
        dup = True
    check("duplicate escrow_id rejected (escrow exists)", dup)


# ═════════════════════════════════════════════════════════════════════════════
# PART 3 — static parity against the Rust source
# ═════════════════════════════════════════════════════════════════════════════

def static_parity():
    src = LIB_RS.read_text()
    common = COMMON_RS.read_text()

    # 1. the payload slice offsets in lib.rs == the reference OFFSETS table
    found = sorted(
        (int(a), int(b)) for a, b in re.findall(r"&p\[(\d+)\.\.(\d+)\]", src)
    )
    # single-byte / special fields are checked by dedicated substrings below
    expected = sorted(
        (start, end) for (start, end) in OFFSETS.values()
        if (start, end) not in {(13, 14), (14, 17), (329, 330)}
    )
    check("static: payload slice offsets in lib.rs == certificate.py OFFSETS",
          found == expected,
          f"found={found} expected={expected}")

    # 2. the special single-byte / uint24 decodes
    for needle in ("p[13]", "p[14], p[15], p[16]", "p[329]"):
        check(f"static: decode uses {needle}", needle in src)

    # 3. §6 step markers appear IN ORDER
    positions = []
    for i in range(1, 10):
        m = re.search(rf"§6 STEP {i} ", src)
        positions.append((i, m.start() if m else -1))
    ok = all(p >= 0 for _, p in positions) and all(
        positions[i][1] < positions[i + 1][1] for i in range(len(positions) - 1)
    )
    check("static: §6 verification steps 1-9 present and in order", ok,
          str(positions))

    # 4. required guards / API usage in lib.rs
    lib_needles = [
        # the Ed25519SigVerify introspection machinery (§6 step 5a)
        "ed25519_program::id()",
        "load_current_index_checked",
        "load_instruction_at_checked",
        "ix_sysvar::id()",
        "u16::MAX",
        "ED_IX_OFFSETS_LEN",
        "read_ed_offsets",
        "ed_slice",
        "verify_ed25519_signature",
        # account constraints / seeds
        "seeds = [SEED_TRION, SEED_VALIDATORS, &cert_epoch.to_be_bytes()]",
        "seeds = [SEED_TRION, SEED_CONSUMED, &escrow.escrow_id]",
        "seeds = [SEED_VAULT, &escrow.escrow_id]",
        "seeds = [SEED_ESCROW, &escrow.escrow_id]",
        "init_if_needed",
        "address = escrow.destination",
        "address = escrow.locked_by",
        "hash::hash",                              # SHA-256 syscall consumed key
        "TRION-EPOCHSET",
        "binary_search_by",
        "windows(2)",
        "EscrowState::EmergencyReverted",
        "RevertReason::Emergency",
        "EMERGENCY_REVERT_SECONDS",
        "cert.coherence >= escrow.min_coherence",
        "require!(min_coherence >= MIN_COHERENCE_FLOOR, BTCPError::CoherenceFloor)",
        "escrow.state == EscrowState::Holding",
        "escrow.is_expired(clock.slot)",
        "3u128", "2u128", "4u128", "20u128", "17u128",   # tier literals
        "checked_mul", "checked_add",
        "declare_id!(\"54r6REJKQ3d2MSV7zYikwiPmck3h7QRaeG44vnRHetWZ\")",
    ]
    for needle in lib_needles:
        check(f"static: lib.rs contains {needle!r}", needle in src)

    def strip_comments(text):
        return "\n".join(line.split("//")[0] for line in text.splitlines())

    code_only, common_code = strip_comments(src), strip_comments(common)

    # 4b. the in-flight BROKEN verification imports are gone from CODE
    # (doc comments may discuss them as rejected alternatives): the CPI
    # pattern (ed25519_dalek / new_ed25519_instruction) does not exist in
    # solana-program 1.18 and the runtime rejects precompile CPI — the
    # introspection pattern replaced it.
    for gone in ("ed25519_dalek", "new_ed25519_instruction"):
        check(f"static: {gone!r} removed from lib.rs code (CPI pattern replaced)",
              gone not in code_only)

    # 5. every mirror error variant is actually guarded in lib.rs
    variants_used = [
        "MalformedCertificate", "UnknownCertificateKind", "VersionIncompatible",
        "WrongSignatureFamily", "InsufficientSigners", "MalformedSignature",
        "SignatureVerificationFailed", "DuplicateSigner", "EpochArgumentMismatch",
        "NoEpochRegistered", "EpochFuture", "EpochStale", "RegistryEpochMismatch",
        "InvalidTtl", "CertificateExpired", "CertificateFutureDated", "HhiCritical",
        "AwaNotEnforced", "CoherenceBelowThreshold", "ValidatorCountMismatch",
        "TooFewValidators", "UnregisteredValidator", "WeightClaimMismatch",
        "PowerMismatch", "RegistryPowerMismatch", "ThresholdMismatch",
        "InsufficientQuorum", "EscrowMismatch", "RouteMismatch", "IntentMismatch",
        "EntityMismatch", "DestinationMismatch", "AmountMismatch", "AmountTooLarge",
        "ChainMismatch", "WrongChain", "AnchorMismatch", "ExecutionMismatch",
        "CertificateConflict", "InconsistentReplayState", "Paused",
        "NotRegistryAdmin", "RegistryCorrupt", "InvalidInstructionSysvar",
    ]
    missing = [v for v in variants_used if f"BTCPError::{v}" not in src]
    check("static: all certificate-gate error variants are guarded in lib.rs",
          not missing, f"missing: {missing}")

    # 6. the oracle-key release gate is GONE (comments stripped so doc
    # mentions do not mask real code)
    for gone in ("is_release_authority", "bind_oracle", "pub oracle:"):
        check(f"static: {gone!r} removed from lib.rs code", gone not in code_only)
    check("static: no unsafe code in either crate",
          "unsafe" not in code_only and "unsafe" not in common_code)

    # 7. checked-math discipline: saturating only in the two sanctioned spots
    sat_add = src.count("saturating_add")
    sat_sub = src.count("saturating_sub")
    check("static: saturating_add only in Escrow::is_expired",
          sat_add == 1 and "self.lock_slot.saturating_add(self.timeout_slots)" in src,
          f"count={sat_add}")
    check("static: saturating_sub only in the epoch grace floor",
          sat_sub == 1 and "latest_epoch.saturating_sub(CERT_EPOCH_GRACE)" in src,
          f"count={sat_sub}")

    # 8. constants in btcp_common match the canonical values
    def const_u64(name, text, expected_val):
        m = re.search(rf"{name}: [^=]*= ([0-9_]+)", text)
        return m and int(m.group(1).replace("_", "")) == expected_val

    common_consts = [
        ("CERT_PAYLOAD_WIDTH", 346), ("CERT_KIND_ESCROW_RELEASE", 1),
        ("CERT_FAMILY_ED25519", 2), ("CERT_ED25519_SIG_LEN", 64),
        ("CERT_MIN_SIGNERS", 3), ("CERT_EPOCH_GRACE", 2),
        ("CERT_HHI_MAX", 4_000), ("CERT_TTL_MAX", 604_800),
        ("CERT_DRIFT_TOLERANCE_SECS", 60), ("D_CONSENSUS_TIER1", 600_000),
        ("D_CONSENSUS_TIER2", 400_000), ("MAX_VALIDATORS", 256),
        ("MIN_COHERENCE_FLOOR", 550_000),
    ]
    bad = [n for n, v in common_consts if not const_u64(n, common, v)]
    check("static: btcp_common certificate constants match the canonical doc",
          not bad, f"mismatched: {bad}")
    check("static: CERT_DOMAIN_TAG == TRION-CERT-V1",
          'CERT_DOMAIN_TAG: &[u8] = b"TRION-CERT-V1"' in common)

    # 9. seed constants
    for seed in ("SEED_TRION", "SEED_VALIDATORS", "SEED_CONSUMED"):
        check(f"static: {seed} defined in btcp_common",
              re.search(rf"pub const {seed}: &\[u8\] = b\"", common) is not None)

    # 10. the golden vector decodes identically through the MIRROR decoder
    golden_payload = bytes.fromhex(golden_mod.GOLDEN_PAYLOAD_HEX)
    decoded = decode_payload(golden_payload)
    gc = golden_mod.golden_certificate()
    pairs = {
        "kind": gc.certificate_kind, "protocol_version": gc.protocol_version,
        "validator_epoch": gc.validator_epoch, "certificate_nonce": gc.certificate_nonce,
        "escrow_id": gc.escrow_id, "route_id": gc.route_id,
        "intent_hash": gc.intent_hash, "entity_id": gc.entity_id,
        "source_chain": gc.source_chain, "dest_chain": gc.dest_chain,
        "destination": gc.destination, "amount": gc.amount,
        "anchor_bh": gc.anchor_bh, "execution_bh": gc.execution_bh,
        "coherence": gc.coherence, "threshold": gc.threshold,
        "hhi_at_emission": gc.hhi_at_emission,
        "total_effective_power": gc.total_effective_power,
        "validator_count": gc.validator_count,
        "awa_enforced": 1 if gc.awa_enforced else 0,
        "issued_at": gc.issued_at, "ttl": gc.ttl,
    }
    bad = [k for k, v in pairs.items() if decoded[k] != v]
    check("static: mirror decoder reproduces the GOLDEN 346-byte vector field-for-field",
          not bad and len(golden_payload) == PAYLOAD_WIDTH, f"mismatched: {bad}")

    # 11. quorum tier discipline in the mirror == the reference EpochSet math
    # (EpochSet / EpochSetEntry come from the bootstrapped reference module)
    def tier_quorum(d, s_frac, n=4):
        es = EpochSet(1, [EpochSetEntry(canonical_validator_id(1, i), 1_000_000, d)
                          for i in range(n)])
        signers = [e.validator_id for i, e in enumerate(es.entries) if i < s_frac * n]
        return es.quorum_met(signers)[0]

    for d, s_frac, expect in (
        (700_000, 0.5, False), (700_000, 0.75, True),
        (500_000, 0.5, False), (500_000, 0.75, True),
        (300_000, 0.75, False),
    ):
        got = tier_quorum(d, s_frac)
        check(f"static: reference EpochSet quorum d={d} signers={s_frac} == {expect}",
              got == expect)


def main():
    print("═" * 78)
    print("SVM btcp_escrow — canonical certificate release gate (C-03 closure)")
    print("═" * 78)
    print("\n— happy paths —"); happy_paths()
    print("\n— structure attacks (§6.1) —"); structure_attacks()
    print("\n— epoch attacks (§6.2) —"); epoch_attacks()
    print("\n— freshness attacks (§6.3) —"); freshness_attacks()
    print("\n— consensus precondition attacks (§6.4) —"); consensus_attacks()
    print("\n— signature attacks (§6.5) —"); signature_attacks()
    print("\n— introspection attacks (§6.5a — the Relay wrong-offset class) —"); introspection_attacks()
    print("\n— quorum attacks (§6.6) —"); quorum_attacks()
    print("\n— binding attacks (§6.7) —"); binding_attacks()
    print("\n— replay / equivocation attacks (§6.8) —"); replay_attacks()
    print("\n— account-derivation attacks (anchor constraints) —"); account_attacks()
    print("\n— escrow-state attacks (§6.9) —"); state_attacks()
    print("\n— C-03 old-authority attacks (oracle key) —"); old_authority_attacks()
    print("\n— revert / E6 escape attacks —"); revert_attacks()
    print("\n— admin-surface attacks —"); admin_attacks()
    print("\n— lock-validation attacks —"); lock_attacks()
    print("\n— static parity vs lib.rs —"); static_parity()

    print("\n" + "═" * 78)
    print(f"RESULT: {len(PASSED)} passed, {len(FAILED)} failed")
    if FAILED:
        for name, detail in FAILED:
            print(f"  FAIL {name} — {detail}")
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
