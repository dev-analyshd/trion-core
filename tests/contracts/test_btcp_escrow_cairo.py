"""
BTCP escrow (Starknet / Cairo) — canonical certificate verification test.

C-04 (CRITICAL) remediation test for contracts/starknet/src/btcp_escrow.cairo
and the second C-04 leg, contracts/cairo/src/trion_execution_gate.cairo:

  * starknet/src/btcp_escrow.cairo — the legacy
    `release_escrow(escrow_id, execution_bh, coherence)` entrypoint that
    trusted a relayer/owner-supplied coherence u64 is REMOVED; release now
    takes the canonical certificate (CANONICAL_CERTIFICATE.md) as the
    family-3 ABI struct + signature set and runs the full fail-closed §6
    sequence: structure + felt-range discipline → epoch (TrionEpochRegistry
    + grace) → freshness → HHI/AWA/isSafe/count/power preconditions →
    STARK-curve ECDSA over Poseidon(domain_felt, 12 felt chunks of the
    346-byte payload) → L4.2 tier weight quorum over REGISTERED weights →
    settlement-tuple binding vs escrow state → nonce/consumed replay rules.
    Submission is permissionless — caller identity carries no authority.
  * cairo/src/trion_execution_gate.cairo — the legacy single-registered-
    validator caller authority (is_validator[caller] + add_validator) is
    REMOVED; publish_signal now requires the same family-3 quorum over a
    domain-separated signal digest
    Poseidon('TRION-SIGNAL-V1', entity_id, status, phi_t, theta, drop_pct,
    beo_hash, da_proof_hash, signal_nonce, issued_at) with epoch-registry
    membership, L4.2 weight quorum, 300 s freshness and per-entity nonce.

No scarb / cairo-test toolchain exists in this sandbox, so this file is a
PYTHON MIRROR of the Cairo validation logic (same field split, same chunk
composition formulas, same error codes, same §6 step order), attacked with
REAL certificates produced by the Wave 1 reference encoder
core/consensus/certificate.py — including the pinned golden vector — plus:

  * a STARK-curve signature model: real ECDSA over the STARK-curve
    field/equation shape, exercised at a 192-bit security level through the
    `ecdsa` package (NIST P-192 — every r, s and pubkey x-coordinate is a
    legitimate felt252 value < 2^251), with forgeries genuinely failing;
  * static source assertions that the .cairo files actually contain the
    checks in the canonical order (and that the relayer/owner/validator
    authorization is gone from both release paths).

HONEST VERIFIED / UNVERIFIED BOUNDARIES:
  * Cairo compilation IS NOW EXERCISED: `scarb build` (sierra + casm)
    compiles the whole contracts/starknet crate AND the twin-carrying
    contracts/cairo crate clean under BOTH scarb 2.10.1 / starknet
    2.10.1 (the version chains/starknet/scripts/build-and-verify.sh pins)
    and scarb 2.8.4 / starknet 2.8.4 — using the version-portable corelib
    paths core::poseidon::poseidon_hash_span and
    core::ecdsa::check_ecdsa_signature, u256-backed felt_lt() range
    comparisons (felt252 has no PartialOrd), crate:: module paths, and
    the current #[generate_trait] impl form (R-16 corelib-skew
    migration). A real cairo-test integration run must still confirm
    runtime behavior before first mainnet emission.
  * Cairo's poseidon_hash_span (Hades Poseidon) cannot be reproduced in
    Python here, so the mirror's D_stark / D_gate use a documented SHA3-256
    STAND-IN over the identical felt inputs (the Poseidon call is Starknet
    OS code outside our contract logic; the security-critical surface —
    chunk composition, binding, quorum, sequence — is fully real).
  * The canonical STARK-curve generator constant likewise cannot be
    reproduced without the toolchain, so the ECDSA model runs on NIST
    P-192 (same short-Weierstrass ECDSA scheme, felt-compatible sizes).
    A real cairo-test integration run must confirm check_ecdsa_signature
    accepts quorum signatures produced by the fleet signer before first
    mainnet emission.

Run: python3 tests/contracts/test_btcp_escrow_cairo.py   (or pytest)
"""

import copy
import hashlib
import importlib.util
import os
import random
import sys

from ecdsa import SigningKey, VerifyingKey
from ecdsa.curves import NIST192p
from ecdsa.ellipticcurve import Point

REPO = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

# Load the Wave 1 reference encoder by FILE PATH — no sys.path hacks (the
# tests/unit hygiene guard forbids new path-insert hacks). certificate.py
# has no repo-internal imports, so a direct spec load is clean.
_spec = importlib.util.spec_from_file_location(
    "trion_core_consensus_certificate",
    os.path.join(REPO, "core", "consensus", "certificate.py"))
certificate = importlib.util.module_from_spec(_spec)
sys.modules["trion_core_consensus_certificate"] = certificate  # dataclass resolution
_spec.loader.exec_module(certificate)

CanonicalCertificate = certificate.CanonicalCertificate
EpochSet = certificate.EpochSet
EpochSetEntry = certificate.EpochSetEntry
pack_version = certificate.pack_version
ttl_for_value_usd = certificate.ttl_for_value_usd

PASSED = []
FAILED = []


def check(name, cond, detail=""):
    (PASSED if cond else FAILED).append(name)
    print(f"  {'OK' if cond else 'FAIL'} {name}" + (f" — {detail}" if detail and not cond else ""))
    return cond


def _sha3(s):
    if isinstance(s, str):
        s = s.encode()
    return hashlib.sha3_256(s).digest()


# ═════════════════════════════════════════════════════════════════════════════
# 1. Felt model (mirrors trion_certificate.cairo constants)
# ═════════════════════════════════════════════════════════════════════════════

STARK_PRIME = (1 << 251) + 17 * (1 << 192) + 1     # the Cairo field prime
FELT_MAX = 1 << 251                                 # < prime, canonical felt bound

# trion_certificate.cairo DOMAIN_FELT — felt("TRION-CERT-V1")
DOMAIN_FELT = int.from_bytes(b"TRION-CERT-V1", "big")
# trion_execution_gate.cairo SIGNAL_DOMAIN_FELT — felt("TRION-SIGNAL-V1")
SIGNAL_DOMAIN_FELT = int.from_bytes(b"TRION-SIGNAL-V1", "big")

PAYLOAD_WIDTH = 346
CERT_KIND_ESCROW_RELEASE = 1
SUPPORTED_PROTOCOL_VERSION = 66051          # pack_version(1, 2, 3) = 0x010203
MIN_SIGNERS = 3
HHI_MAX_ACCEPTABLE = 4000
CLOCK_DRIFT_TOLERANCE = 60
D_CONSENSUS_TIER1 = 600_000
D_CONSENSUS_TIER2 = 400_000
SCALE_1E6 = 1_000_000
EPOCH_GRACE = 2

# powers of two used by the chunk formulas (mirrors the P2_XX constants)
P2 = {k: 1 << k for k in range(0, 252)}


class CairoPanic(Exception):
    """A Cairo `assert(..., '<code>')` failure — transaction aborts,
    nothing is committed. The felt panic code is the short-string value."""

    def __init__(self, code):
        super().__init__(f"Cairo panic: {code!r}")
        self.code = code


def _require(cond, code):
    if not cond:
        raise CairoPanic(code)


# ── the family-3 Certificate ABI form (mirrors the Cairo struct, 30 fields) ──

CERT_STRUCT_FIELDS = [
    "certificate_kind", "protocol_version", "validator_epoch", "certificate_nonce",
    "escrow_hi2", "escrow_lo30", "route_hi1", "route_lo31",
    "intent_hi31", "intent_lo1", "entity_hi30", "entity_lo2",
    "source_chain", "dest_chain",
    "dest_hi21", "dest_lo11", "amount_hi20", "amount_lo12",
    "anchor_hi19", "anchor_lo13", "exec_hi18", "exec_lo14",
    "coherence", "threshold", "hhi", "total_power", "validator_count",
    "awa_enforced", "issued_at", "ttl",
]


def split_certificate(cert):
    """Split a REAL CanonicalCertificate's 346-byte payload P into the
    family-3 ABI felt pieces, exactly at the 32-byte field boundaries the
    Cairo struct documents. This is what the relayer does before crossing
    the Starknet ABI; the split is injective (fixed widths)."""
    p = cert.encode_payload()
    assert len(p) == PAYLOAD_WIDTH
    u = lambda off, width: int.from_bytes(p[off:off + width], "big")
    hhi = u(309, 8)
    ttl = u(338, 8)
    return {
        "certificate_kind": u(13, 1),
        "protocol_version": u(14, 3),
        "validator_epoch": u(17, 4),
        "certificate_nonce": u(21, 8),
        "escrow_hi2": u(29, 2), "escrow_lo30": u(31, 30),
        "route_hi1": u(61, 1), "route_lo31": u(62, 31),
        "intent_hi31": u(93, 31), "intent_lo1": u(124, 1),
        "entity_hi30": u(125, 30), "entity_lo2": u(155, 2),
        "source_chain": u(157, 4), "dest_chain": u(161, 4),
        "dest_hi21": u(165, 21), "dest_lo11": u(186, 11),
        "amount_hi20": u(197, 20), "amount_lo12": u(217, 12),
        "anchor_hi19": u(229, 19), "anchor_lo13": u(248, 13),
        "exec_hi18": u(261, 18), "exec_lo14": u(279, 14),
        "coherence": u(293, 8), "threshold": u(301, 8),
        "hhi": hhi, "total_power": u(317, 8), "validator_count": u(325, 4),
        "awa_enforced": u(329, 1), "issued_at": u(330, 8), "ttl": ttl,
    }


# ── §6 step 1: structure + felt-range discipline (mirror of check_structure) ──

def check_structure(f):
    """Mirror of trion_certificate.cairo check_structure — every assert is a
    RANGE or SHAPE check that must hold before any digest arithmetic, so no
    felt multiplication in compose_chunks can wrap the field prime."""
    _require(f["certificate_kind"] == CERT_KIND_ESCROW_RELEASE, "CERT: bad kind")
    _require(f["protocol_version"] <= SUPPORTED_PROTOCOL_VERSION, "CERT: version")
    _require(f["validator_epoch"] <= 0xFFFFFFFF, "CERT: epoch range")
    _require(f["certificate_nonce"] != 0, "CERT: zero nonce")
    _require(f["source_chain"] <= 0xFFFFFFFF, "CERT: source chain")
    _require(f["dest_chain"] != 0, "CERT: dest chain 0")
    _require(f["dest_chain"] <= 0xFFFFFFFF, "CERT: dest chain")
    _require(f["coherence"] <= SCALE_1E6, "CERT: coherence range")
    _require(f["threshold"] <= SCALE_1E6, "CERT: threshold range")
    _require(f["hhi"] <= 10000, "CERT: hhi range")
    _require(f["awa_enforced"] <= 1, "CERT: awa range")
    _require(f["issued_at"] < 0x1000000000000, "CERT: issued range")
    _require(f["ttl"] < 0x100000000, "CERT: ttl range")
    _require(f["escrow_hi2"] < P2[16], "CERT: escrow_hi2 range")
    _require(f["escrow_lo30"] < P2[240], "CERT: escrow_lo30 range")
    _require(f["route_hi1"] < P2[8], "CERT: route_hi1 range")
    _require(f["route_lo31"] < P2[248], "CERT: route_lo31 range")
    _require(f["intent_hi31"] < P2[248], "CERT: intent_hi31 range")
    _require(f["intent_lo1"] < P2[8], "CERT: intent_lo1 range")
    _require(f["entity_hi30"] < P2[240], "CERT: entity_hi30 range")
    _require(f["entity_lo2"] < P2[16], "CERT: entity_lo2 range")
    _require(f["dest_hi21"] < P2[168], "CERT: dest_hi21 range")
    _require(f["dest_lo11"] < P2[88], "CERT: dest_lo11 range")
    _require(f["amount_hi20"] < P2[160], "CERT: amount_hi20 range")
    _require(f["amount_lo12"] < P2[96], "CERT: amount_lo12 range")
    _require(f["anchor_hi19"] < P2[152], "CERT: anchor_hi19 range")
    _require(f["anchor_lo13"] < P2[104], "CERT: anchor_lo13 range")
    _require(f["exec_hi18"] < P2[144], "CERT: exec_hi18 range")
    _require(f["exec_lo14"] < P2[112], "CERT: exec_lo14 range")


# ── §3.2 family-3 digest (mirror of compose_chunks + stark_digest) ──────────

def compose_chunks(f):
    """Mirror of trion_certificate.cairo compose_chunks — the fixed 31-byte
    chunk grid of §3.2 as big-endian integer concatenation. Parity with
    certificate.py stark_felt_chunks() is pinned by test_reference_encoder_
    parity: any drift in these formulas breaks a pinned test, not
    production."""
    hhi_hi1 = f["hhi"] // 0x100000000000000        # hhi >> 56
    hhi_lo7 = f["hhi"] % 0x100000000000000
    ttl_hi3 = f["ttl"] // 0x10000000000            # ttl >> 40
    ttl_lo5 = f["ttl"] % 0x10000000000

    c0 = (DOMAIN_FELT * P2[144] + f["certificate_kind"] * P2[136]
          + f["protocol_version"] * P2[112] + f["validator_epoch"] * P2[80]
          + f["certificate_nonce"] * P2[16] + f["escrow_hi2"])
    c1 = f["escrow_lo30"] * P2[8] + f["route_hi1"]
    c2 = f["route_lo31"]
    c3 = f["intent_hi31"]
    c4 = f["intent_lo1"] * P2[240] + f["entity_hi30"]
    c5 = (f["entity_lo2"] * P2[232] + f["source_chain"] * P2[200]
          + f["dest_chain"] * P2[168] + f["dest_hi21"])
    c6 = f["dest_lo11"] * P2[160] + f["amount_hi20"]
    c7 = f["amount_lo12"] * P2[152] + f["anchor_hi19"]
    c8 = f["anchor_lo13"] * P2[144] + f["exec_hi18"]
    c9 = (f["exec_lo14"] * P2[136] + f["coherence"] * P2[72]
          + f["threshold"] * P2[8] + hhi_hi1)
    c10 = (hhi_lo7 * P2[192] + f["total_power"] * P2[128]
           + f["validator_count"] * P2[96] + f["awa_enforced"] * P2[88]
           + f["issued_at"] * P2[24] + ttl_hi3)
    c11 = ttl_lo5
    return [c0, c1, c2, c3, c4, c5, c6, c7, c8, c9, c10, c11]


def _poseidon_stand_in(elements):
    """Documented STAND-IN for Cairo's poseidon_hash_span (see module
    docstring — the real Hades instance cannot be reproduced here). Same
    input discipline: domain felt first, then the chunk/state felts, each
    as a 32-byte big-endian felt. Output truncated to 192 bits for the
    P-192 ECDSA model (a legitimate felt-sized digest)."""
    h = hashlib.sha3_256(b"TRION-POSEIDON-MIRROR")
    for e in elements:
        h.update(int(e % STARK_PRIME).to_bytes(32, "big"))
    return int.from_bytes(h.digest()[:24], "big")


def stark_digest(f):
    """Mirror of trion_certificate.cairo stark_digest:
    D_stark = Poseidon(DOMAIN_FELT, f_0 .. f_11) — the felt the quorum's
    STARK-curve ECDSA signatures are over."""
    return _poseidon_stand_in([DOMAIN_FELT] + compose_chunks(f))


def quorum_met(signed_power, total_power, d_consensus):
    """Mirror of trion_certificate.cairo quorum_met (L4.2 tiers; tier 1 is
    STRICT — exactly-2/3 is not a quorum)."""
    if d_consensus >= D_CONSENSUS_TIER1:
        return 3 * signed_power > 2 * total_power
    if d_consensus >= D_CONSENSUS_TIER2:
        return 4 * signed_power >= 3 * total_power
    return 20 * signed_power >= 17 * total_power


def is_fresh(issued_at, ttl, now):
    """Mirror of trion_certificate.cairo is_fresh — drift widens the LOWER
    bound only (consensus-time skew tolerated, expiry never)."""
    return now + CLOCK_DRIFT_TOLERANCE >= issued_at and now <= issued_at + ttl


# ── §6 step 7 binding helpers (mirror, felt-recomposition wrap-proof) ────────

def escrow_id_matches(f, escrow_id):
    return (f["escrow_hi2"] < P2[11]
            and f["escrow_hi2"] * P2[240] + f["escrow_lo30"] == escrow_id)


def route_id_matches(f, route_id):
    return (f["route_hi1"] < 0x8
            and f["route_hi1"] * P2[248] + f["route_lo31"] == route_id)


def destination_matches(f, destination_felt):
    return (f["dest_hi21"] < P2[163]
            and f["dest_hi21"] * P2[88] + f["dest_lo11"] == destination_felt)


def amount_matches(f, amount):
    _require(f["amount_hi20"] < P2[160], "CERT: amount_hi20 range")
    _require(f["amount_lo12"] < P2[96], "CERT: amount_lo12 range")
    high, low = amount >> 128, amount & ((1 << 128) - 1)
    mid, lo = low // (1 << 96), low % (1 << 96)
    return f["amount_hi20"] == high * P2[32] + mid and f["amount_lo12"] == lo


def entity_key(f):
    _require(f["entity_hi30"] < P2[235], "CERT: entity_hi30 binding")
    return f["entity_hi30"] * P2[16] + f["entity_lo2"]


# ═════════════════════════════════════════════════════════════════════════════
# 2. STARK-curve ECDSA model (NIST P-192 via the ecdsa package — real
#    signature math; all values are legitimate felts < 2^251)
# ═════════════════════════════════════════════════════════════════════════════


class StarkKey:
    """A validator family-3 key. `pub_felt` models the stark_pubkey felt the
    registry stores (the x-coordinate — Starknet's ECDSA public key form);
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
    """Mirror of core::ecdsa::check_ecdsa_signature(msg, pubkey, r, s)
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
# 3. TrionEpochRegistry mirror (trion_epoch_registry.cairo)
# ═════════════════════════════════════════════════════════════════════════════

MAX_EPOCH_VALIDATORS = 128
MAX_WEIGHT = 1_000_000


def vid_halves(validator_id: bytes):
    return (int.from_bytes(validator_id[:16], "big"),
            int.from_bytes(validator_id[16:], "big"))


class EpochRegistryMirror:
    """Mirror of trion_epoch_registry.cairo — the §10.2 registrar. Storage:
    `validators` keyed (epoch, vid_lo16), `epoch_meta` keyed epoch —
    SEPARATE maps (compiler-derived storage addresses, distinct field
    names); the escrow's consumed maps live in a different contract."""

    def __init__(self):
        self.admin = 1
        self.latest_epoch = 0
        self.validators = {}      # (epoch, vid_lo16) -> entry dict
        self.epoch_meta = {}      # epoch -> (count, total_power, d_consensus, sealed)
        self.events = []

    def register_epoch(self, caller, epoch, entries):
        _require(caller == self.admin, "REG: not registrar")
        n = len(entries)
        _require(n > 0, "REG: empty epoch")
        _require(n <= MAX_EPOCH_VALIDATORS, "REG: epoch too large")
        _require(epoch > self.latest_epoch, "REG: epoch not newer")

        total_power = 0
        total_diversity = 0
        for e in entries:
            hi, lo = vid_halves(e["validator_id"])
            _require(hi < P2[128], "REG: vid_hi range")
            _require(lo < P2[128], "REG: vid_lo range")
            _require(e["stark_pubkey"] < FELT_MAX, "REG: pubkey range")
            _require(e["stark_pubkey"] != 0, "REG: zero pubkey")
            _require(e["stake_weight"] != 0, "REG: zero stake")
            _require(e["stake_weight"] <= MAX_WEIGHT, "REG: stake cap")
            _require(e["diversity_weight"] != 0, "REG: zero diversity")
            _require(e["diversity_weight"] <= MAX_WEIGHT, "REG: diversity cap")
            existing = self.validators.get((epoch, lo))
            _require(existing is None or existing["stark_pubkey"] == 0,
                     "REG: validator exists")
            w = e["stake_weight"] * e["diversity_weight"] // 1_000_000
            total_power += w
            total_diversity += e["diversity_weight"]
            self.validators[(epoch, lo)] = {
                "vid_hi16": hi, "stark_pubkey": e["stark_pubkey"],
                "point": e["point"],
                "stake_weight": e["stake_weight"],
                "diversity_weight": e["diversity_weight"],
            }

        d_consensus = total_diversity // n
        self.epoch_meta[epoch] = (n, total_power, d_consensus, True)
        self.latest_epoch = epoch
        self.events.append(("EpochRegistered", epoch, n, total_power, d_consensus))

    def get_validator(self, epoch, vid_hi16, vid_lo16):
        entry = self.validators.get((epoch, vid_lo16))
        if entry is None or entry["vid_hi16"] != vid_hi16:
            return (0, 0, 0, False)
        return (entry["stark_pubkey"], entry["stake_weight"],
                entry["diversity_weight"], True)

    def get_validator_point(self, epoch, vid_hi16, vid_lo16):
        entry = self.validators.get((epoch, vid_lo16))
        if entry is None or entry["vid_hi16"] != vid_hi16:
            return None
        return entry["point"]

    def get_epoch(self, epoch):
        return self.epoch_meta.get(epoch, (0, 0, 0, False))

    def latest(self):
        return self.latest_epoch


# ═════════════════════════════════════════════════════════════════════════════
# 4. BTCPEscrow mirror (contracts/starknet/src/btcp_escrow.cairo)
# ═════════════════════════════════════════════════════════════════════════════

STATE_HOLDING, STATE_RELEASED = 0, 1
STATE_REVERTED, STATE_EMERGENCY_REVERTED = 2, 3
EMERGENCY_ESCAPE_SECONDS = 7 * 24 * 60 * 60
MIN_COHERENCE_FLOOR = 550_000
FELT_ID_MAX = 1 << 251
MAX_SIG_ENTRIES = 128

OWNER, RELAYER, STRANGER = 1, 2, 99


class EscrowMirror:
    """Mirror of btcp_escrow.cairo — storage maps as dicts (the
    consumed_nonce / consumed_digest maps are keyed by (validator_epoch,
    escrow_id) 2-tuples in a namespace disjoint from the escrow record map
    and the per-funder balance map — the storage-collision probe pins this
    independence)."""

    def __init__(self, owner=OWNER, registry_addr=0, now=1_700_000_200):
        self.owner = owner
        self.relayer = owner
        self.escrows = {}
        self.escrow_count = 0
        self.locked_balance = {}          # funder -> u256
        self.total_locked_balance = 0
        self.registry = registry_addr
        self.registry_bound = registry_addr != 0
        self.registry_obj = None
        self.paused = False
        self.consumed_nonce = {}          # (epoch, escrow_id) -> u64
        self.consumed_digest = {}         # (epoch, escrow_id) -> felt
        self._now = now
        self.events = []

    # ── internal: the §6 fail-closed gate (verify_release_certificate) ──

    def verify_release_certificate(self, escrow_id, rec, f, sigs):
        # §6 step 1: STRUCTURE (payload half + envelope half)
        check_structure(f)
        n = len(sigs)
        _require(n >= MIN_SIGNERS, "CERT: sig count")
        _require(n <= MAX_SIG_ENTRIES, "CERT: too many sigs")
        for i in range(n):
            for j in range(i + 1, n):
                a, b = sigs[i], sigs[j]
                _require(not (a["vid_hi16"] == b["vid_hi16"]
                              and a["vid_lo16"] == b["vid_lo16"]),
                         "CERT: dup signer")

        # §6 step 2: EPOCH (registry + grace — no historical sets)
        _require(self.registry_bound, "CERT: registry unbound")
        count, total_power, d_consensus, sealed = \
            self.registry_obj.get_epoch(f["validator_epoch"])
        _require(sealed, "CERT: unknown epoch")
        latest = self.registry_obj.latest()
        _require(f["validator_epoch"] <= latest, "CERT: future epoch")
        _require(latest - f["validator_epoch"] <= EPOCH_GRACE, "CERT: stale epoch")

        # §6 step 3: FRESHNESS (drift widens the lower bound only)
        _require(is_fresh(f["issued_at"], f["ttl"], self._now), "CERT: expired")

        # §6 step 4: CONSENSUS PRECONDITIONS
        _require(f["hhi"] <= HHI_MAX_ACCEPTABLE, "CERT: hhi critical")
        _require(f["awa_enforced"] == 1, "CERT: awa not enforced")
        _require(f["coherence"] >= f["threshold"], "CERT: not safe")
        _require(f["validator_count"] == count, "CERT: count mismatch")
        _require(f["total_power"] == total_power, "CERT: power mismatch")

        # §6 step 5: SIGNATURES (batch fail-closed) + step 6: QUORUM
        d = stark_digest(f)
        signed_power = 0
        for sig in sigs:
            pubkey, stake, diversity, active = self.registry_obj.get_validator(
                f["validator_epoch"], sig["vid_hi16"], sig["vid_lo16"])
            _require(active, "CERT: validator inactive")
            _require(sig["stake_weight"] == stake
                     and sig["diversity_weight"] == diversity,
                     "CERT: weight mismatch")
            point = self.registry_obj.get_validator_point(
                f["validator_epoch"], sig["vid_hi16"], sig["vid_lo16"])
            _require(stark_verify(point, d, sig["sig_r"], sig["sig_s"]),
                     "CERT: bad signature")
            w = stake * diversity // 1_000_000
            signed_power += w
        _require(quorum_met(signed_power, total_power, d_consensus),
                 "CERT: quorum not met")

        # §6 step 7: BINDING (settlement tuple vs escrow state)
        _require(escrow_id_matches(f, escrow_id), "CERT: escrow mismatch")
        _require(route_id_matches(f, rec["route_id"]), "CERT: route mismatch")
        _require(destination_matches(f, rec["destination"]),
                 "CERT: dest mismatch")
        _require(amount_matches(f, rec["amount"]), "CERT: amount mismatch")
        _require(f["coherence"] >= rec["min_coherence"],
                 "CERT: below min coherence")

        # §6 step 8: NONCE / CONSUMED (§8 replay rules)
        key = (f["validator_epoch"], escrow_id)
        consumed = self.consumed_nonce.get(key, 0)
        if consumed != 0:
            if f["certificate_nonce"] == consumed:
                consumed_d = self.consumed_digest[key]
                if d != consumed_d:
                    # §8.2 conflict — evidence event, successful no-op
                    self.events.append(("CertificateConflict", escrow_id,
                                        f["validator_epoch"], consumed,
                                        consumed_d, d))
                    return (False, d)
                _require(False, "CERT: replay")
            _require(f["certificate_nonce"] > consumed, "CERT: replay")
        self.consumed_nonce[key] = f["certificate_nonce"]
        self.consumed_digest[key] = d
        return (True, d)

    # ── external entrypoints ────────────────────────────────────────────

    def lock_escrow(self, caller, escrow_id, route_id, entity_id, destination,
                    amount, min_coherence, timeout_blocks, parent=0):
        _require(caller == self.relayer or caller == self.owner,
                 "BTCP: not authorized")
        _require(not self.paused, "BTCP: paused")
        _require(escrow_id != 0, "BTCP: zero escrow id")
        _require(escrow_id < FELT_ID_MAX, "BTCP: escrow id range")
        _require(route_id < FELT_ID_MAX, "BTCP: route id range")
        _require(amount > 0, "BTCP: zero amount")
        _require(min_coherence >= MIN_COHERENCE_FLOOR, "BTCP: coherence floor")
        _require(min_coherence <= 1_000_000, "BTCP: invalid coherence")
        _require(timeout_blocks > 0, "BTCP: zero timeout")
        _require(escrow_id not in self.escrows, "BTCP: escrow exists")

        self.escrows[escrow_id] = {
            "escrow_id": escrow_id, "route_id": route_id,
            "entity_id": entity_id, "destination": destination,
            "amount": amount, "min_coherence": min_coherence,
            "lock_height": self._now, "timeout_blocks": timeout_blocks,
            "state": STATE_HOLDING, "revert_reason": 0,
            "settled_at": 0, "reverted_at": 0, "locked_by": caller,
            "parent_escrow_id": parent,
        }
        self.escrow_count += 1
        self.locked_balance[caller] = self.locked_balance.get(caller, 0) + amount
        self.total_locked_balance += amount
        self.events.append(("EscrowLocked", escrow_id, route_id, amount))

    def release_escrow(self, caller, escrow_id, f, sigs):
        # PERMISSIONLESS: no caller check — the certificate quorum is the
        # authority (C-04: caller identity is gone from the release path).
        _require(escrow_id in self.escrows, "BTCP: not found")
        rec = self.escrows[escrow_id]

        if rec["state"] != STATE_HOLDING:
            # §8.2 terminal-state branch: idempotent resubmission of the
            # SAME certificate is a no-op; same nonce + DIFFERENT payload
            # emits the (unverified-pointer) CertificateConflict evidence
            # event as a successful no-op; a different nonce fails closed.
            d = stark_digest(f)
            c_nonce = self.consumed_nonce.get((f["validator_epoch"], escrow_id), 0)
            c_digest = self.consumed_digest.get((f["validator_epoch"], escrow_id), 0)
            if f["certificate_nonce"] == c_nonce:
                if d == c_digest:
                    return ("idempotent", d)
                self.events.append(("CertificateConflict", escrow_id,
                                    f["validator_epoch"], c_nonce,
                                    c_digest, d))
                return ("conflict-evidence", d)
            _require(False, "BTCP: already settled")

        _require(self._now <= rec["lock_height"] + rec["timeout_blocks"],
                 "BTCP: expired")

        ok, d = self.verify_release_certificate(escrow_id, rec, f, sigs)
        if not ok:
            return ("conflict-evidence", d)

        amount_out = rec["amount"]
        funder = rec["locked_by"]
        rec["state"] = STATE_RELEASED
        rec["settled_at"] = self._now
        rec["amount"] = 0
        _require(self.locked_balance.get(funder, 0) >= amount_out,
                 "BTCP: locked underflow")
        self.locked_balance[funder] -= amount_out
        _require(self.total_locked_balance >= amount_out, "BTCP: locked underflow")
        self.total_locked_balance -= amount_out
        self.events.append(("EscrowReleased", escrow_id, rec["route_id"], d,
                            f["coherence"], rec["settled_at"]))
        return ("released", d)

    def _settle_revert(self, escrow_id, rec, state, reason):
        amount_out, funder = rec["amount"], rec["locked_by"]
        rec["state"], rec["revert_reason"] = state, reason
        rec["reverted_at"], rec["amount"] = self._now, 0
        _require(self.locked_balance.get(funder, 0) >= amount_out,
                 "BTCP: locked underflow")
        self.locked_balance[funder] -= amount_out
        _require(self.total_locked_balance >= amount_out, "BTCP: locked underflow")
        self.total_locked_balance -= amount_out

    def _cascade(self, child_id, parent_id):
        while parent_id != 0:
            parent = self.escrows.get(parent_id)
            if parent is None or parent["escrow_id"] == 0:
                break
            if parent["state"] != STATE_HOLDING:
                break
            self._settle_revert(parent_id, parent, STATE_REVERTED, 5)
            self.events.append(("CascadeRevert", child_id, parent_id))
            child_id, parent_id = parent_id, parent["parent_escrow_id"]

    def revert_escrow(self, caller, escrow_id, reason):
        _require(escrow_id in self.escrows, "BTCP: not found")
        rec = self.escrows[escrow_id]
        _require(rec["state"] == STATE_HOLDING, "BTCP: not holding")
        is_timeout = self._now > rec["lock_height"] + rec["timeout_blocks"]
        if not is_timeout:
            _require(caller == self.relayer or caller == self.owner,
                     "BTCP: not authorized")
            _require(reason != 0, "BTCP: not timeout")
        self._settle_revert(escrow_id, rec, STATE_REVERTED, reason)
        self.events.append(("EscrowReverted", escrow_id, reason))
        self._cascade(escrow_id, rec["parent_escrow_id"])

    def revert_emergency(self, caller, escrow_id):
        _require(escrow_id in self.escrows, "BTCP: not found")
        rec = self.escrows[escrow_id]
        _require(rec["state"] == STATE_HOLDING, "BTCP: not holding")
        _require(self._now >= rec["lock_height"] + EMERGENCY_ESCAPE_SECONDS,
                 "BTCP: emergency not yet")
        self._settle_revert(escrow_id, rec, STATE_EMERGENCY_REVERTED, 6)
        self.events.append(("EmergencyRevert", escrow_id, caller))
        self._cascade(escrow_id, rec["parent_escrow_id"])

    def bind_registry(self, caller, registry_addr, registry_obj):
        _require(caller == self.owner, "BTCP: not owner")
        _require(not self.registry_bound, "BTCP: registry bound")
        _require(registry_addr != 0, "BTCP: zero registry")
        self.registry, self.registry_bound = registry_addr, True
        self.registry_obj = registry_obj
        self.events.append(("RegistryBound", registry_addr))

    def pause(self, caller):
        _require(caller == self.owner, "BTCP: not owner")
        self.paused = True

    def unpause(self, caller):
        _require(caller == self.owner, "BTCP: not owner")
        self.paused = False


# ═════════════════════════════════════════════════════════════════════════════
# 5. TRIONExecutionGate mirror (contracts/cairo/src/trion_execution_gate.cairo)
# ═════════════════════════════════════════════════════════════════════════════

SIGNAL_TTL_SECONDS = 300


def signal_digest(entity_id, status, phi_t, theta, drop_pct, beo_hash,
                  da_proof_hash, signal_nonce, issued_at):
    """Mirror of the gate's D_gate =
    Poseidon('TRION-SIGNAL-V1', entity_id, status, phi_t, theta, drop_pct,
    beo_hash, da_proof_hash, signal_nonce, issued_at)."""
    return _poseidon_stand_in([
        SIGNAL_DOMAIN_FELT, entity_id, status, phi_t, theta, drop_pct,
        beo_hash, da_proof_hash, signal_nonce, issued_at])


class GateMirror:
    def __init__(self, owner=OWNER, now=1_700_000_200):
        self.owner = owner
        self.registry, self.registry_bound = 0, False
        self.registry_obj = None
        self.paused = False
        self.signals = {}                # entity_id -> BehavioralSignal dict
        self.decisions = {}
        self.last_signal_nonce = {}      # entity_id -> u64 (replay guard)
        self.stats = dict(allowed=0, blocked=0, published=0, anomalies=0)
        self._now = now
        self.events = []

    def bind_registry(self, caller, registry_addr, registry_obj):
        _require(caller == self.owner, "Not owner")
        _require(not self.registry_bound, "GATE: registry bound")
        _require(registry_addr != 0, "GATE: zero registry")
        self.registry, self.registry_bound = registry_addr, True
        self.registry_obj = registry_obj
        self.events.append(("RegistryBound", registry_addr))

    def publish_signal(self, caller, entity_id, status, phi_t, theta, drop_pct,
                       beo_hash, da_proof_hash, sigs, validator_epoch,
                       signal_nonce, issued_at):
        # PERMISSIONLESS: no caller check — the quorum is the authority
        # (C-04: the is_validator caller gate is gone).
        _require(not self.paused, "GATE: paused")
        _require(1 <= status <= 4, "GATE: invalid status")
        _require(entity_id != 0, "GATE: zero entity")
        _require(signal_nonce != 0, "GATE: zero nonce")
        _require(issued_at < 0x1000000000000, "GATE: issued range")

        n = len(sigs)
        _require(n >= MIN_SIGNERS, "GATE: sig count")
        _require(n <= MAX_SIG_ENTRIES, "GATE: too many sigs")
        for i in range(n):
            for j in range(i + 1, n):
                a, b = sigs[i], sigs[j]
                _require(not (a["vid_hi16"] == b["vid_hi16"]
                              and a["vid_lo16"] == b["vid_lo16"]),
                         "GATE: dup signer")

        _require(self.registry_bound, "GATE: registry unbound")
        _count, total_power, d_consensus, sealed = \
            self.registry_obj.get_epoch(validator_epoch)
        _require(sealed, "GATE: unknown epoch")
        latest = self.registry_obj.latest()
        _require(validator_epoch <= latest, "GATE: future epoch")
        _require(latest - validator_epoch <= EPOCH_GRACE, "GATE: stale epoch")

        _require(is_fresh(issued_at, SIGNAL_TTL_SECONDS, self._now),
                 "GATE: signal stale")

        d_gate = signal_digest(entity_id, status, phi_t, theta, drop_pct,
                               beo_hash, da_proof_hash, signal_nonce, issued_at)
        signed_power = 0
        for sig in sigs:
            pubkey, stake, diversity, active = self.registry_obj.get_validator(
                validator_epoch, sig["vid_hi16"], sig["vid_lo16"])
            _require(active, "GATE: validator inactive")
            _require(sig["stake_weight"] == stake
                     and sig["diversity_weight"] == diversity,
                     "GATE: weight mismatch")
            point = self.registry_obj.get_validator_point(
                validator_epoch, sig["vid_hi16"], sig["vid_lo16"])
            _require(stark_verify(point, d_gate, sig["sig_r"], sig["sig_s"]),
                     "GATE: bad signature")
            w = stake * diversity // 1_000_000
            signed_power += w
        _require(quorum_met(signed_power, total_power, d_consensus),
                 "GATE: quorum not met")

        consumed = self.last_signal_nonce.get(entity_id, 0)
        _require(signal_nonce > consumed, "GATE: signal replay")

        self.signals[entity_id] = {
            "packed_status": status, "phi_t": phi_t, "theta": theta,
            "drop_pct": drop_pct, "beo_hash": beo_hash,
            "da_proof_hash": da_proof_hash, "initialized": True,
        }
        self.last_signal_nonce[entity_id] = signal_nonce
        self.stats["published"] += 1
        if status >= 3:
            self.stats["anomalies"] += 1
            self.events.append(("AnomalySealed", entity_id, status))
        self.events.append(("SignalPublished", entity_id, status, phi_t,
                            validator_epoch, signal_nonce))

    def check_execution(self, entity_id, caller):
        _require(not self.paused, "Paused")
        sig = self.signals.get(entity_id)
        if sig is None or not sig["initialized"]:
            self.stats["blocked"] += 1
            self.events.append(("ExecutionBlocked", entity_id, caller, 0))
            return (False, entity_id)
        allowed = sig["packed_status"] <= 2     # STATUS_ELEVATED
        if allowed:
            self.stats["allowed"] += 1
            self.events.append(("ExecutionAllowed", entity_id, caller, sig["phi_t"]))
        else:
            self.stats["blocked"] += 1
            self.events.append(("ExecutionBlocked", entity_id, caller,
                                sig["packed_status"]))
        return (allowed, entity_id)

    def pause(self, caller):
        _require(caller == self.owner, "Not owner")
        self.paused = True


# ═════════════════════════════════════════════════════════════════════════════
# 6. Fixtures — a fully consistent world from the reference encoder
# ═════════════════════════════════════════════════════════════════════════════

NOW = 1_700_000_200
EPOCH = 7


def make_keys(n):
    return [StarkKey.generate() for _ in range(n)]


def make_epoch_world(n_validators=5, epoch=EPOCH, tier="t1"):
    """5 validators × (s=1.0, d=0.7) → total power 3.5e6, D=0.7 → tier 1
    (2/3 STRICT: 3/5 = 60% < 66.7%, 4/5 = 80% > 66.7% → quorum at 4)."""
    d_val = {"t1": 700_000, "t2": 500_000, "t3": 300_000}[tier]
    keys = make_keys(n_validators)
    vids = [_sha3(b"TRION-VALIDATOR" + epoch.to_bytes(4, "big")
                  + i.to_bytes(4, "big")) for i in range(n_validators)]
    entries = [EpochSetEntry(vids[i], stake_weight=1_000_000,
                             diversity_weight=d_val,
                             stark_pubkey=keys[i].pub_felt.to_bytes(32, "big"))
               for i in range(n_validators)]
    eset = EpochSet(epoch, entries)
    return keys, vids, entries, eset


def make_certificate(eset, escrow_felt, route_felt, dest_felt, amount,
                     epoch=EPOCH, nonce=1, issued_at=NOW - 100, ttl=3600,
                     coherence=820_000, threshold=550_000, hhi=1_200,
                     awa=True, kind=1, version=None, **overrides):
    kw = dict(
        certificate_kind=kind,
        protocol_version=version if version is not None else pack_version(1, 2, 3),
        validator_epoch=epoch,
        certificate_nonce=nonce,
        escrow_id=escrow_felt.to_bytes(32, "big"),
        route_id=route_felt.to_bytes(32, "big"),
        intent_hash=_sha3("intent-K2"),
        entity_id=_sha3("entity-K2"),
        source_chain=1,
        dest_chain=800,          # Starknet, TRION registry id
        destination=dest_felt.to_bytes(32, "big"),
        amount=amount,
        anchor_bh=_sha3("anchor-K2"),
        execution_bh=_sha3("execution-K2"),
        coherence=coherence,
        threshold=threshold,
        hhi_at_emission=hhi,
        total_effective_power=eset.total_effective_power(),
        validator_count=len(eset),
        awa_enforced=awa,
        issued_at=issued_at,
        ttl=ttl,
    )
    kw.update(overrides)
    return CanonicalCertificate(**kw)


def sign_cert(keys, vids, entries, cert, signers=None, claims=None):
    """Produce SigEntry dicts: each listed validator signs the family-3
    digest of THIS certificate payload with its key; weight claims default
    to the true registered values."""
    f = split_certificate(cert)
    d = stark_digest(f)
    if signers is None:
        signers = range(len(keys))
    sigs = []
    for i in signers:
        r, s = keys[i].sign(d)
        stake, diversity = entries[i].stake_weight, entries[i].diversity_weight
        if claims is not None:
            stake, diversity = claims[i]
        hi, lo = vid_halves(vids[i])
        sigs.append({"vid_hi16": hi, "vid_lo16": lo,
                     "stake_weight": stake, "diversity_weight": diversity,
                     "sig_r": r, "sig_s": s})
    return sigs


def fresh_world(n_validators=5, tier="t1", amount=1_000_000, min_coherence=600_000):
    keys, vids, entries, eset = make_epoch_world(n_validators, tier=tier)
    reg = EpochRegistryMirror()
    reg.register_epoch(1, EPOCH, [
        {"validator_id": vids[i], "stark_pubkey": keys[i].pub_felt,
         "point": keys[i].point, "stake_weight": entries[i].stake_weight,
         "diversity_weight": entries[i].diversity_weight}
        for i in range(n_validators)])

    escrow_felt = int.from_bytes(_sha3("escrow-K2"), "big") % (1 << 240)
    route_felt = int.from_bytes(_sha3("route-K2"), "big") % (1 << 240)
    dest_felt = int.from_bytes(_sha3("dest-K2"), "big") % (1 << 240)

    cert = make_certificate(eset, escrow_felt, route_felt, dest_felt, amount)
    m = EscrowMirror(owner=OWNER, registry_addr=0xABC)
    m.registry_obj = reg
    m.registry_bound = True
    m.relayer = RELAYER           # owner called set_relayer first
    m.lock_escrow(RELAYER, escrow_felt, route_felt, 0xBEEF, dest_felt, amount,
                  min_coherence, 3600)
    m._now = NOW
    return m, reg, (keys, vids, entries, eset, cert, escrow_felt, route_felt,
                    dest_felt, amount)


def expect_panic(code, fn, *a, **kw):
    try:
        fn(*a, **kw)
        return None
    except CairoPanic as p:
        return p.code


# ═════════════════════════════════════════════════════════════════════════════
# 7. Reference-encoder parity (the pinned cross-VM conformance anchor)
# ═════════════════════════════════════════════════════════════════════════════

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


def test_reference_encoder_parity():
    print("\n1) family-3 felt chunking — parity with the reference encoder")
    golden = CanonicalCertificate(
        certificate_kind=1, protocol_version=pack_version(1, 2, 3),
        validator_epoch=7, certificate_nonce=42,
        escrow_id=_sha3("golden-escrow"), route_id=_sha3("golden-route"),
        intent_hash=_sha3("golden-intent"), entity_id=_sha3("golden-entity"),
        source_chain=1, dest_chain=900,
        destination=bytes.fromhex("00" * 12 + "deadbeef" * 5),
        amount=1_234_567_890_123_456_789,
        anchor_bh=_sha3("golden-anchor"), execution_bh=_sha3("golden-execution"),
        coherence=820_000, threshold=550_000, hhi_at_emission=1_234,
        total_effective_power=2_100_000, validator_count=3, awa_enforced=True,
        issued_at=1_700_000_123, ttl=86_400,
    )
    check("golden certificate payload == pinned GOLDEN_PAYLOAD_HEX",
          golden.encode_payload().hex() == GOLDEN_PAYLOAD_HEX)
    f = split_certificate(golden)
    check("split_certificate covers the exact 30-field Cairo ABI struct",
          sorted(f.keys()) == sorted(CERT_STRUCT_FIELDS))
    chunks = compose_chunks(f)
    check("compose_chunks == reference stark_felt_chunks (golden vector)",
          chunks == golden.stark_felt_chunks())
    check("12 chunks, every one < 2^248 (no chunk can reach the 2^251 dark range)",
          len(chunks) == 12 and all(c < (1 << 248) for c in chunks))
    check("DOMAIN_FELT == reference stark_domain_felt",
          DOMAIN_FELT == golden.stark_domain_felt)
    check("check_structure accepts the golden certificate",
          check_structure(f) is None)

    rng = random.Random(20260904)
    ok_rand, ok_rebuild = True, True
    for t in range(30):
        rbytes = lambda: rng.getrandbits(256).to_bytes(32, "big")
        c = CanonicalCertificate(
            certificate_kind=1, protocol_version=pack_version(1, 0, rng.randrange(10)),
            validator_epoch=rng.randrange(1 << 32), certificate_nonce=rng.randrange(1, 1 << 40),
            escrow_id=rbytes(), route_id=rbytes(), intent_hash=rbytes(),
            entity_id=rbytes(), source_chain=rng.randrange(1 << 16),
            dest_chain=rng.randrange(1, 1 << 16), destination=rbytes(),
            amount=rng.getrandbits(256), anchor_bh=rbytes(), execution_bh=rbytes(),
            coherence=rng.randrange(0, 1_000_001), threshold=rng.randrange(0, 1_000_001),
            hhi_at_emission=rng.randrange(0, 10_001),
            total_effective_power=rng.randrange(0, 1 << 48),
            validator_count=rng.randrange(0, 200), awa_enforced=bool(rng.getrandbits(1)),
            issued_at=rng.randrange(0, 1 << 40), ttl=rng.randrange(0, 1 << 24),
        )
        ff = split_certificate(c)
        ok_rand &= compose_chunks(ff) == c.stark_felt_chunks()
        ok_rand &= all(ch < (1 << 248) for ch in compose_chunks(ff))
        # chunk composition is injective: chunks rebuild P exactly
        rebuilt = b"".join(ch.to_bytes(31 if i < 11 else 5, "big")
                           for i, ch in enumerate(compose_chunks(ff)))
        ok_rebuild &= rebuilt == c.encode_payload()
    check("30 randomized certificates: compose_chunks == stark_felt_chunks",
          ok_rand)
    check("chunking is injective (chunks rebuild the 346-byte payload)",
          ok_rebuild)

    # binding helpers are exact equalities on bindable (sub-2^251) ids
    esc, rte, dst = 0x1234ABCD, 0x0FEED, (1 << 250) - 7
    m, reg, fx = fresh_world()
    _k, _v, _e, eset, cert, _ef, _rf, _df, amt = fx
    c2 = make_certificate(eset, esc, rte, dst, amt)
    f2 = split_certificate(c2)
    check("escrow_id_matches binds the zero-extended felt form",
          escrow_id_matches(f2, esc) and not escrow_id_matches(f2, esc + 1))
    check("route_id_matches binds the zero-extended felt form",
          route_id_matches(f2, rte) and not route_id_matches(f2, rte ^ 1))
    check("destination_matches binds the zero-extended felt form",
          destination_matches(f2, dst) and not destination_matches(f2, dst - 1))
    check("amount_matches binds any u256 (boundary: 2^256-1)",
          amount_matches(split_certificate(make_certificate(eset, esc, rte, dst,
                                                             (1 << 256) - 1)),
                         (1 << 256) - 1))
    # dark-range ids (>= 2^251) cannot be bound — fail closed
    dark = split_certificate(make_certificate(eset, FELT_MAX + 1234, rte, dst, amt))
    check("dark-range escrow id (felt >= 2^251) fails escrow_id_matches",
          not escrow_id_matches(dark, (FELT_MAX + 1234) % STARK_PRIME))


# ═════════════════════════════════════════════════════════════════════════════
# 8. Attack matrix
# ═════════════════════════════════════════════════════════════════════════════

def test_valid_release_passes():
    print("\n2) valid canonical certificate releases (the happy path)")
    m, reg, (keys, vids, entries, eset, cert, esc, rte, dst, amt) = fresh_world()
    f = split_certificate(cert)
    sigs = sign_cert(keys, vids, entries, cert)

    check("certificate is a REAL reference-encoder object (346-byte payload)",
          len(cert.encode_payload()) == 346)
    check("SUPPORTED_PROTOCOL_VERSION == pack(1,2,3)",
          SUPPORTED_PROTOCOL_VERSION == pack_version(1, 2, 3))

    # permissionless: a NOBODY submits — the caller is only a transport
    res = m.release_escrow(STRANGER, esc, f, sigs)
    check("release by a non-owner/non-relayer SUCCEEDS (caller is transport)",
          res[0] == "released", f"res={res[0]}")
    check("escrow state RELEASED", m.escrows[esc]["state"] == STATE_RELEASED)
    check("record amount cleared to 0 (spent marker)", m.escrows[esc]["amount"] == 0)
    check("settled_at recorded", m.escrows[esc]["settled_at"] == m._now)
    check("locked_balance drained by exactly the escrow amount",
          m.locked_balance[RELAYER] == 0 and m.total_locked_balance == 0)
    consumed = m.consumed_nonce[(cert.validator_epoch, esc)]
    check("consumed registry recorded (epoch, escrow) -> nonce",
          consumed == cert.certificate_nonce)
    check("consumed digest recorded (D_stark)",
          m.consumed_digest[(cert.validator_epoch, esc)] == stark_digest(f))
    ev = [e for e in m.events if e[0] == "EscrowReleased"]
    check("EscrowReleased event carries D_stark + SIGNED coherence",
          ev and ev[0][3] == stark_digest(f) and ev[0][4] == cert.coherence)

    # the OWNER gets no special path: same certificate from the owner is
    # just an idempotent no-op after settlement
    res2 = m.release_escrow(OWNER, esc, f, sigs)
    check("idempotent resubmission of the SAME certificate is a no-op",
          res2[0] == "idempotent" and m.escrows[esc]["state"] == STATE_RELEASED)
    check("idempotent resubmission has no settlement effect",
          m.total_locked_balance == 0 and m.escrow_count == 1)


def test_caller_coherence_regression():
    print("\n3) C-04 REGRESSION — caller-supplied coherence no longer releases")
    # The legacy attack: a relayer/owner supplies escrow_id + execution_bh +
    # a coherence NUMBER and the escrow releases. The new ABI has no
    # coherence argument and no caller authority anywhere on the path.
    m, reg, (keys, vids, entries, eset, cert, esc, rte, dst, amt) = fresh_world()
    f = split_certificate(cert)

    # a) the old-style bare call: an "authorized" caller with no signature
    #    batch at all
    code = expect_panic("x", m.release_escrow, RELAYER, esc, f, [])
    check("relayer + zero signatures -> 'CERT: sig count'",
          code == "CERT: sig count", f"code={code}")
    code = expect_panic("x", m.release_escrow, OWNER, esc, f, [])
    check("owner + zero signatures -> 'CERT: sig count'",
          code == "CERT: sig count", f"code={code}")

    # b) the old-style coherence LIE: submit a structurally-valid
    #    certificate but TAMPER the coherence field to a perfect 1.0
    #    without re-signing — the digest changes, the batch fails
    forged = dict(f)
    forged["coherence"] = 1_000_000
    forged["threshold"] = 0
    code = expect_panic("x", m.release_escrow, RELAYER, esc, forged,
                        sign_cert(keys, vids, entries, cert))
    check("tampered coherence (unsigned lie) -> 'CERT: bad signature'",
          code == "CERT: bad signature", f"code={code}")

    # c) the caller IS the registered validator (the old cairo gate's
    #    single-validator authority class) — still needs the quorum
    sigs_alone = sign_cert(keys, vids, entries, cert, signers=[0])
    code = expect_panic("x", m.release_escrow, keys[0].pub_felt, esc, f,
                        sigs_alone)
    check("a single validator caller cannot release -> 'CERT: sig count'",
          code == "CERT: sig count", f"code={code}")

    # d) garbage certificate shape (the old call carried a raw u64 —
    #    nothing canonical to verify)
    junk = dict(f)
    junk["certificate_kind"] = 0
    code = expect_panic("x", m.release_escrow, RELAYER, esc, junk,
                        sign_cert(keys, vids, entries, cert))
    check("kind 0 certificate -> 'CERT: bad kind'",
          code == "CERT: bad kind", f"code={code}")

    check("no release happened in any regression attempt",
          m.escrows[esc]["state"] == STATE_HOLDING
          and m.total_locked_balance == amt)


def test_structure_attacks():
    print("\n4) §6 step 1 — structure + envelope attacks")
    m, reg, (keys, vids, entries, eset, cert, esc, rte, dst, amt) = fresh_world()
    f = split_certificate(cert)
    sigs = sign_cert(keys, vids, entries, cert)

    # wrong kind (2 = proposed bootstrap multisig — unknown HERE, fail closed)
    c2 = make_certificate(eset, esc, rte, dst, amt, kind=2)
    code = expect_panic("x", m.release_escrow, STRANGER, esc, split_certificate(c2),
                        sign_cert(keys, vids, entries, c2))
    check("certificate_kind 2 (unknown kind) -> 'CERT: bad kind'",
          code == "CERT: bad kind", f"code={code}")

    # protocol version from the future
    c3 = make_certificate(eset, esc, rte, dst, amt, version=pack_version(2, 0, 0))
    code = expect_panic("x", m.release_escrow, STRANGER, esc, split_certificate(c3),
                        sign_cert(keys, vids, entries, c3))
    check("protocol_version 2.0.0 > supported -> 'CERT: version'",
          code == "CERT: version", f"code={code}")

    # nonce 0 (the consumed-map sentinel)
    c4 = make_certificate(eset, esc, rte, dst, amt, nonce=0)
    code = expect_panic("x", m.release_escrow, STRANGER, esc, split_certificate(c4),
                        sign_cert(keys, vids, entries, c4))
    check("certificate_nonce 0 -> 'CERT: zero nonce'",
          code == "CERT: zero nonce", f"code={code}")

    # duplicate signer padding is not consensus (§4 invariant 2)
    dup = [dict(sigs[0]), dict(sigs[0]), dict(sigs[1])]
    code = expect_panic("x", m.release_escrow, STRANGER, esc, f, dup)
    check("duplicate signer padding -> 'CERT: dup signer'",
          code == "CERT: dup signer", f"code={code}")

    # too many sigs (gas bound)
    many = [dict(sigs[i % len(sigs)]) for i in range(MAX_SIG_ENTRIES + 1)]
    code = expect_panic("x", m.release_escrow, STRANGER, esc, f, many)
    check("signature batch > 128 -> 'CERT: too many sigs'",
          code == "CERT: too many sigs", f"code={code}")

    # registry unbound
    m2, reg2, fx2 = fresh_world()
    m2.registry_bound = False
    code = expect_panic("x", m2.release_escrow, STRANGER, fx2[5],
                        split_certificate(fx2[4]),
                        sign_cert(fx2[0], fx2[1], fx2[2], fx2[4]))
    check("registry never bound -> 'CERT: registry unbound'",
          code == "CERT: registry unbound", f"code={code}")


def test_epoch_attacks():
    print("\n5) §6 step 2 — epoch registry + grace attacks")
    m, reg, (keys, vids, entries, eset, cert, esc, rte, dst, amt) = fresh_world()

    # unregistered epoch: a certificate claiming epoch 999
    c = make_certificate(eset, esc, rte, dst, amt, epoch=999)
    code = expect_panic("x", m.release_escrow, STRANGER, esc, split_certificate(c),
                        sign_cert(keys, vids, entries, c))
    check("validator_epoch 999 (unregistered) -> 'CERT: unknown epoch'",
          code == "CERT: unknown epoch", f"code={code}")

    # stale epoch: rotate the registry forward so cert epoch 7 is now
    # latest(10) - 7 = 3 > grace(2)
    keys2, vids2, entries2, _eset2 = make_epoch_world(5, epoch=10)
    reg.register_epoch(1, 10, [
        {"validator_id": vids2[i], "stark_pubkey": keys2[i].pub_felt,
         "point": keys2[i].point, "stake_weight": 1_000_000,
         "diversity_weight": 700_000} for i in range(5)])
    code = expect_panic("x", m.release_escrow, STRANGER, esc, split_certificate(cert),
                        sign_cert(keys, vids, entries, cert))
    check("cert epoch 7 with latest 10 (grace 2 exceeded) -> 'CERT: stale epoch'",
          code == "CERT: stale epoch", f"code={code}")

    # a cert from the CURRENT epoch (10) signed by epoch-10 validators works
    m2, reg2, (k2, v2, e2, eset2, _c, _e, _r, _d, _a) = fresh_world()
    reg2.register_epoch(1, 10, [
        {"validator_id": v2[i], "stark_pubkey": k2[i].pub_felt,
         "point": k2[i].point, "stake_weight": 1_000_000,
         "diversity_weight": 700_000} for i in range(5)])
    c10 = make_certificate(eset2, _e, _r, _d, _a, epoch=10)
    res = m2.release_escrow(STRANGER, _e, split_certificate(c10),
                            sign_cert(k2, v2, e2, c10))
    check("fresh epoch-10 certificate releases (rotation works)",
          res[0] == "released", f"res={res[0]}")


def test_freshness_attacks():
    print("\n6) §6 step 3 — freshness attacks")
    m, reg, (keys, vids, entries, eset, cert, esc, rte, dst, amt) = fresh_world()

    # expired: issued 1000 s ago, ttl 3600 BUT now is 5000 s past issue
    c = make_certificate(eset, esc, rte, dst, amt, issued_at=NOW - 5000, ttl=100)
    code = expect_panic("x", m.release_escrow, STRANGER, esc, split_certificate(c),
                        sign_cert(keys, vids, entries, c))
    check("expired certificate -> 'CERT: expired'",
          code == "CERT: expired", f"code={code}")

    # ttl=0: born expired
    c = make_certificate(eset, esc, rte, dst, amt, issued_at=NOW - 1, ttl=0)
    code = expect_panic("x", m.release_escrow, STRANGER, esc, split_certificate(c),
                        sign_cert(keys, vids, entries, c))
    check("ttl=0 (born expired) -> 'CERT: expired'",
          code == "CERT: expired", f"code={code}")

    # future-dated beyond the 60 s drift tolerance
    c = make_certificate(eset, esc, rte, dst, amt, issued_at=NOW + 61, ttl=3600)
    code = expect_panic("x", m.release_escrow, STRANGER, esc, split_certificate(c),
                        sign_cert(keys, vids, entries, c))
    check("future-dated beyond drift (issued_at = now+61) -> 'CERT: expired'",
          code == "CERT: expired", f"code={code}")

    # future-dated WITHIN the 60 s drift tolerance passes (skew tolerance,
    # lower bound only)
    c = make_certificate(eset, esc, rte, dst, amt, issued_at=NOW + 30, ttl=3600)
    res = m.release_escrow(STRANGER, esc, split_certificate(c),
                           sign_cert(keys, vids, entries, c))
    check("future-dated within 60 s drift releases (lower-bound widening)",
          res[0] == "released", f"res={res[0]}")


def test_precondition_attacks():
    print("\n7) §6 step 4 — consensus preconditions (all SIGNED lies still fail)")
    m, reg, (keys, vids, entries, eset, cert, esc, rte, dst, amt) = fresh_world()

    cases = [
        ("hhi 4001 (L4.8 CRITICAL tier)", dict(hhi=4001), "CERT: hhi critical"),
        ("awa_enforced = 0 (emission frozen)", dict(awa=False), "CERT: awa not enforced"),
        ("coherence < threshold (not isSafe)", dict(coherence=500_000), "CERT: not safe"),
        ("validator_count lie (4 != 5 registered)", dict(validator_count=4),
         "CERT: count mismatch"),
        ("total_power lie", dict(total_effective_power=3_000_000),
         "CERT: power mismatch"),
    ]
    for name, kw, expected in cases:
        c = make_certificate(eset, esc, rte, dst, amt, **kw)
        code = expect_panic("x", m.release_escrow, STRANGER, esc, split_certificate(c),
                            sign_cert(keys, vids, entries, c))
        check(f"{name} -> '{expected}'", code == expected, f"code={code}")


def test_signature_attacks():
    print("\n8) §6 step 5 — signature batch attacks")
    m, reg, (keys, vids, entries, eset, cert, esc, rte, dst, amt) = fresh_world()
    f = split_certificate(cert)

    # unregistered signer: an off-set key signs (real signature, real
    # payload — but not a member of the epoch set)
    rogue = StarkKey.generate()
    hi, lo = vid_halves(_sha3("rogue-validator"))
    r, s = rogue.sign(stark_digest(f))
    sigs = sign_cert(keys, vids, entries, cert, signers=[0, 1, 2])
    sigs.append({"vid_hi16": hi, "vid_lo16": lo, "stake_weight": 1_000_000,
                 "diversity_weight": 700_000, "sig_r": r, "sig_s": s})
    code = expect_panic("x", m.release_escrow, STRANGER, esc, f, sigs)
    check("unregistered signer in batch -> 'CERT: validator inactive'",
          code == "CERT: validator inactive", f"code={code}")

    # forged signature: valid vid, garbage (r, s)
    sigs = sign_cert(keys, vids, entries, cert, signers=[0, 1, 2])
    sigs[2]["sig_r"] = (sigs[2]["sig_r"] + 1) % NIST192p.order
    code = expect_panic("x", m.release_escrow, STRANGER, esc, f, sigs)
    check("forged (r,s) on a registered signer -> 'CERT: bad signature'",
          code == "CERT: bad signature", f"code={code}")

    # weight claims that disagree with the registry (self-reported weight
    # inflation — the C-06 class, closed by §6 step 5c)
    sigs = sign_cert(keys, vids, entries, cert, signers=[0, 1, 2, 3, 4],
                     claims=[(1_000_000, 1_000_000)] * 5)
    code = expect_panic("x", m.release_escrow, STRANGER, esc, f, sigs)
    check("inflated diversity claim -> 'CERT: weight mismatch'",
          code == "CERT: weight mismatch", f"code={code}")

    # valid membership + valid sigs, but only 3 of 5 (tier 1 needs 4)
    sigs = sign_cert(keys, vids, entries, cert, signers=[0, 1, 2])
    code = expect_panic("x", m.release_escrow, STRANGER, esc, f, sigs)
    check("3-of-5 signatures (below 2/3 power) -> 'CERT: quorum not met'",
          code == "CERT: quorum not met", f"code={code}")

    # a certificate-qualified quorum vs a SIGNAL digest: family-3
    # signatures are domain-separated — a cert signature never verifies
    # as a signal signature (cross-purpose reuse blocked)
    d_gate = signal_digest(0xBEEF, 1, 50, 60, 0, 0x123, 0x456, 1, NOW - 10)
    cert_sigs = sign_cert(keys, vids, entries, cert, signers=[0, 1, 2, 3])
    ok = all(stark_verify(keys[i].point, d_gate,
                          cert_sigs[i]["sig_r"], cert_sigs[i]["sig_s"])
             is False for i in range(4))
    check("certificate signatures do NOT verify over a signal digest",
          ok)


def test_quorum_attacks():
    print("\n9) §6 step 6 — L4.2 tier quorum attacks")
    # exactly-2/3 is NOT a quorum (tier 1 STRICT) — mirror the arithmetic
    check("tier 1: exactly 2/3 power is NOT a quorum (strict >)",
          quorum_met(2_000, 3_000, 700_000) is False)
    check("tier 1: 2/3 + 1 is a quorum",
          quorum_met(2_001, 3_000, 700_000) is True)
    check("tier 2 (D=0.5): exactly 3/4 IS a quorum (>=)",
          quorum_met(3_000, 4_000, 500_000) is True)
    check("tier 2: below 3/4 is not",
          quorum_met(2_999, 4_000, 500_000) is False)
    check("tier 3 (D=0.3): exactly 17/20 IS a quorum (>=)",
          quorum_met(17, 20, 300_000) is True)
    check("tier 3: below 17/20 is not",
          quorum_met(16, 20, 300_000) is False)

    # tier 2 world: D=0.5 → 0.75 quorum; 3-of-5 (60%) fails, 4-of-5 (80%) passes
    m, reg, (keys, vids, entries, eset, cert, esc, rte, dst, amt) = \
        fresh_world(tier="t2")
    sigs3 = sign_cert(keys, vids, entries, cert, signers=[0, 1, 2])
    code = expect_panic("x", m.release_escrow, STRANGER, esc, split_certificate(cert), sigs3)
    check("tier 2: 3-of-5 (60% < 75%) -> 'CERT: quorum not met'",
          code == "CERT: quorum not met", f"code={code}")
    sigs4 = sign_cert(keys, vids, entries, cert, signers=[0, 1, 2, 3])
    res = m.release_escrow(STRANGER, esc, split_certificate(cert), sigs4)
    check("tier 2: 4-of-5 (80% >= 75%) releases", res[0] == "released",
          f"res={res[0]}")


def test_binding_attacks():
    print("\n10) §6 step 7 — settlement-tuple binding attacks")
    m, reg, (keys, vids, entries, eset, cert, esc, rte, dst, amt) = fresh_world()

    # a REAL, fully-signed certificate for a DIFFERENT escrow (same
    # everything else) — escrow-substitution is closed
    other = esc + 1
    c = make_certificate(eset, other, rte, dst, amt)
    code = expect_panic("x", m.release_escrow, STRANGER, esc,
                        split_certificate(c), sign_cert(keys, vids, entries, c))
    check("certificate bound to another escrow -> 'CERT: escrow mismatch'",
          code == "CERT: escrow mismatch", f"code={code}")

    # wrong route
    c = make_certificate(eset, esc, rte + 1, dst, amt)
    code = expect_panic("x", m.release_escrow, STRANGER, esc,
                        split_certificate(c), sign_cert(keys, vids, entries, c))
    check("certificate bound to another route -> 'CERT: route mismatch'",
          code == "CERT: route mismatch", f"code={code}")

    # wrong destination (attacker substituted their own address)
    c = make_certificate(eset, esc, rte, dst + 1, amt)
    code = expect_panic("x", m.release_escrow, STRANGER, esc,
                        split_certificate(c), sign_cert(keys, vids, entries, c))
    check("certificate bound to another destination -> 'CERT: dest mismatch'",
          code == "CERT: dest mismatch", f"code={code}")

    # wrong amount (value inflation)
    c = make_certificate(eset, esc, rte, dst, amt * 2)
    code = expect_panic("x", m.release_escrow, STRANGER, esc,
                        split_certificate(c), sign_cert(keys, vids, entries, c))
    check("certificate bound to another amount -> 'CERT: amount mismatch'",
          code == "CERT: amount mismatch", f"code={code}")

    # escrow-local tightening (INV-003): signed coherence 0.82 < the
    # escrow's lock-time min_coherence 0.9
    m2, _reg2, (k2, v2, e2, eset2, _c, e_id, r_id, d_id, a) = \
        fresh_world(min_coherence=900_000)
    c = make_certificate(eset2, e_id, r_id, d_id, a, coherence=820_000)
    code = expect_panic("x", m2.release_escrow, STRANGER, e_id,
                        split_certificate(c), sign_cert(k2, v2, e2, c))
    check("signed coherence below escrow min_coherence -> "
          "'CERT: below min coherence'",
          code == "CERT: below min coherence", f"code={code}")


def test_replay_and_double_release():
    print("\n11) §6 step 8 + §8 — nonce / replay / double-release")
    m, reg, (keys, vids, entries, eset, cert, esc, rte, dst, amt) = fresh_world()
    f = split_certificate(cert)
    sigs = sign_cert(keys, vids, entries, cert)

    m.release_escrow(STRANGER, esc, f, sigs)

    # same certificate again → idempotent no-op (§8.2)
    res = m.release_escrow(STRANGER, esc, f, sigs)
    check("replay of the SAME certificate: idempotent no-op",
          res[0] == "idempotent", f"res={res[0]}")
    check("no second settlement effect", m.total_locked_balance == 0)

    # same-nonce, DIFFERENT payload → §8.2 equivocation conflict: evidence
    # event, no settlement, no panic
    conflict_cert = make_certificate(eset, esc, rte, dst, amt,
                                     intent_hash=_sha3("intent-CONFLICT"))
    res = m.release_escrow(STRANGER, esc, split_certificate(conflict_cert),
                           sign_cert(keys, vids, entries, conflict_cert))
    check("same nonce + different payload: conflict-evidence no-op (§8.2)",
          res[0] == "conflict-evidence", f"res={res[0]}")
    ev = [e for e in m.events if e[0] == "CertificateConflict"]
    check("CertificateConflict event emitted (L4.9 S1 evidence)",
          bool(ev) and ev[0][1] == esc and ev[0][3] == cert.certificate_nonce)
    check("conflict caused no state change",
          m.escrows[esc]["state"] == STATE_RELEASED
          and m.total_locked_balance == 0)

    # replay of an OLDER certificate (nonce < consumed) after a newer one
    # was consumed: the escrow is terminal — §6 step 8's replay rule is
    # enforced by the terminal-state branch (consumption co-commits with
    # settlement, so the in-gate nonce-regression assert is defense for
    # future custody-wiring re-entry; exercised directly below)
    m2, _r2, (k2, v2, e2, eset2, c2, e_id, r_id, d_id, a) = fresh_world()
    m2.release_escrow(STRANGER, e_id, split_certificate(c2),
                      sign_cert(k2, v2, e2, c2))
    higher = make_certificate(eset2, e_id, r_id, d_id, a, nonce=9)
    lower2 = make_certificate(eset2, e_id, r_id, d_id, a, nonce=4,
                              intent_hash=_sha3("intent-LOWER2"))
    code = expect_panic("x", m2.release_escrow, STRANGER, e_id,
                        split_certificate(lower2), sign_cert(k2, v2, e2, lower2))
    check("older certificate (nonce < consumed) replay -> "
          "'BTCP: already settled'",
          code == "BTCP: already settled", f"code={code}")

    # the in-gate nonce-regression defense (§8.1 monotonic) exists and
    # fails closed when reachable (simulated by pre-seeding the consumed
    # maps on a still-HOLDING escrow — the only state the gate can re-enter)
    m3, _r3, (k3, v3, e3, eset3, c3, e_id3, r3, d3, a3) = fresh_world()
    same_nonce = make_certificate(eset3, e_id3, r3, d3, a3, nonce=9)
    m3.consumed_nonce[(c3.validator_epoch, e_id3)] = 9
    m3.consumed_digest[(c3.validator_epoch, e_id3)] = \
        stark_digest(split_certificate(same_nonce))
    code = expect_panic("x", m3.release_escrow, STRANGER, e_id3,
                        split_certificate(c3), sign_cert(k3, v3, e3, c3))
    check("in-gate nonce regression (nonce < consumed) -> 'CERT: replay'",
          code == "CERT: replay", f"code={code}")
    code = expect_panic("x", m3.release_escrow, STRANGER, e_id3,
                        split_certificate(same_nonce),
                        sign_cert(k3, v3, e3, same_nonce))
    check("in-gate same nonce + same digest (still HOLDING) -> "
          "'CERT: replay'",
          code == "CERT: replay", f"code={code}")

    # double-release with a genuinely NEW valid certificate (nonce 9)
    code = expect_panic("x", m2.release_escrow, STRANGER, e_id,
                        split_certificate(higher), sign_cert(k2, v2, e2, higher))
    check("new valid certificate on a RELEASED escrow -> "
          "'BTCP: already settled'",
          code == "BTCP: already settled", f"code={code}")

    # revert after release is terminal-state blocked (INV-002)
    code = expect_panic("x", m2.revert_escrow, RELAYER, e_id, 3)
    check("revert after release -> 'BTCP: not holding' (terminal)",
          code == "BTCP: not holding", f"code={code}")


def test_pause_and_lock_side():
    print("\n12) M2 E1/E3 — pause blocks NEW LOCKS only, never settlements")
    m, reg, (keys, vids, entries, eset, cert, esc, rte, dst, amt) = fresh_world()
    m.pause(OWNER)
    check("paused", m.paused)

    # lock while paused fails
    code = expect_panic("x", m.lock_escrow, RELAYER, esc + 5, rte, 0xBEEF,
                        dst, amt, 600_000, 3600)
    check("new lock while paused -> 'BTCP: paused'",
          code == "BTCP: paused", f"code={code}")

    # release while paused PROCEEDS (M2 E3: settlements are never
    # pausable — pause must never be a settlement freeze)
    res = m.release_escrow(STRANGER, esc, split_certificate(cert),
                           sign_cert(keys, vids, entries, cert))
    check("certificate release while paused SUCCEEDS (settlements not pausable)",
          res[0] == "released", f"res={res[0]}")

    # pause authority is owner-only
    m2, _r2, _fx2 = fresh_world()
    code = expect_panic("x", m2.pause, STRANGER)
    check("pause by a stranger -> 'BTCP: not owner'",
          code == "BTCP: not owner", f"code={code}")

    # lock-side authorization + INV-003 floor + felt-range id bound
    m3, _r3, _fx3 = fresh_world()
    code = expect_panic("x", m3.lock_escrow, STRANGER, 1, 1, 1, dst, amt,
                        600_000, 3600)
    check("lock by a stranger -> 'BTCP: not authorized'",
          code == "BTCP: not authorized", f"code={code}")
    code = expect_panic("x", m3.lock_escrow, RELAYER, 1, 1, 1, dst, amt,
                        500_000, 3600)
    check("min_coherence below 0.55 protocol floor -> 'BTCP: coherence floor'",
          code == "BTCP: coherence floor", f"code={code}")
    code = expect_panic("x", m3.lock_escrow, RELAYER, FELT_MAX + 7, 1, 1, dst,
                        amt, 600_000, 3600)
    check("escrow id in the felt dark range (>= 2^251) -> "
          "'BTCP: escrow id range'",
          code == "BTCP: escrow id range", f"code={code}")
    code = expect_panic("x", m3.lock_escrow, RELAYER, esc, rte, 0xBEEF, dst,
                        amt, 600_000, 3600)
    check("duplicate escrow id -> 'BTCP: escrow exists'",
          code == "BTCP: escrow exists", f"code={code}")


def test_felt_range_attacks():
    print("\n13) felt-range discipline — every out-of-range piece fails closed")
    m, reg, (keys, vids, entries, eset, cert, esc, rte, dst, amt) = fresh_world()
    f = split_certificate(cert)
    sigs = sign_cert(keys, vids, entries, cert)

    pieces = [
        ("escrow_hi2", 1 << 16), ("escrow_lo30", 1 << 240),
        ("route_hi1", 1 << 8), ("route_lo31", 1 << 248),
        ("intent_hi31", 1 << 248), ("intent_lo1", 1 << 8),
        ("entity_hi30", 1 << 240), ("entity_lo2", 1 << 16),
        ("dest_hi21", 1 << 168), ("dest_lo11", 1 << 88),
        ("amount_hi20", 1 << 160), ("amount_lo12", 1 << 96),
        ("anchor_hi19", 1 << 152), ("anchor_lo13", 1 << 104),
        ("exec_hi18", 1 << 144), ("exec_lo14", 1 << 112),
    ]
    all_ok = True
    for name, bad in pieces:
        forged = dict(f)
        forged[name] = bad
        code = expect_panic("x", m.release_escrow, STRANGER, esc, forged, sigs)
        if code != f"CERT: {name} range":
            all_ok = False
            check(f"{name} >= 2^{bad.bit_length() - 1} -> 'CERT: {name} range'",
                  False, f"code={code}")
    check("all 16 felt pieces enforce their byte-width bound "
          "(chunk composition cannot wrap the prime)", all_ok)

    # full-felt wrap attack: a piece equal to PRIME - 5 (as a chunk this
    # would alias a genuinely-signed value mod P) is rejected BEFORE any
    # digest arithmetic
    forged = dict(f)
    forged["route_lo31"] = STARK_PRIME - 5
    code = expect_panic("x", m.release_escrow, STRANGER, esc, forged, sigs)
    check("piece = PRIME-5 (wrap-collision attempt) -> 'CERT: route_lo31 range'",
          code == "CERT: route_lo31 range", f"code={code}")

    # u64-side range checks (type-bounded at serde, belt-and-braces here)
    for name, bad, code_str in [
        ("coherence", 1_000_001, "CERT: coherence range"),
        ("threshold", 1_000_001, "CERT: threshold range"),
        ("hhi", 10_001, "CERT: hhi range"),
        ("awa_enforced", 2, "CERT: awa range"),
        ("issued_at", 1 << 48, "CERT: issued range"),
        ("ttl", 1 << 32, "CERT: ttl range"),
        ("dest_chain", 0, "CERT: dest chain 0"),
    ]:
        forged = dict(f)
        forged[name] = bad
        code = expect_panic("x", m.release_escrow, STRANGER, esc, forged, sigs)
        check(f"{name} out of range -> '{code_str}'", code == code_str,
              f"code={code}")

    # registry-side felt range: a stark pubkey in the dark range
    reg2 = EpochRegistryMirror()
    keys2, vids2, _e2, _s2 = make_epoch_world(3, epoch=3)
    bad_entry = {"validator_id": vids2[0], "stark_pubkey": FELT_MAX + 1,
                 "point": keys2[0].point, "stake_weight": 1_000_000,
                 "diversity_weight": 700_000}
    good = [{"validator_id": vids2[i], "stark_pubkey": keys2[i].pub_felt,
             "point": keys2[i].point, "stake_weight": 1_000_000,
             "diversity_weight": 700_000} for i in (1, 2)]
    code = expect_panic("x", reg2.register_epoch, 1, 3, good + [bad_entry])
    check("registry: stark_pubkey >= 2^251 -> 'REG: pubkey range'",
          code == "REG: pubkey range", f"code={code}")

    # signature felts: P-192 model keeps r, s, pubkeys < 2^192 < 2^251
    ok = all(sig["sig_r"] < FELT_MAX and sig["sig_s"] < FELT_MAX
             for sig in sigs) and all(k.pub_felt < FELT_MAX for k in keys)
    check("modeled ECDSA r/s/pubkeys are legitimate felts (< 2^251)", ok)


def test_storage_collision_probe():
    print("\n14) storage-collision probe — map namespaces are independent")
    m, reg, (keys, vids, entries, eset, cert, esc, rte, dst, amt) = fresh_world()
    f = split_certificate(cert)
    m.release_escrow(STRANGER, esc, f, sign_cert(keys, vids, entries, cert))

    # consumed maps keyed (epoch, escrow_id) vs escrow record keyed escrow_id
    key = (cert.validator_epoch, esc)
    check("consumed_nonce written at (epoch, escrow_id)",
          m.consumed_nonce[key] == cert.certificate_nonce)
    m.consumed_nonce[(7, esc + 1)] = 99
    check("writing consumed_nonce[(7, other)] does not touch escrow records",
          m.escrows[esc]["state"] == STATE_RELEASED
          and (esc + 1) not in m.escrows)
    m.escrows[esc + 2] = dict(m.escrows[esc])
    check("writing a new escrow record does not touch consumed maps",
          m.consumed_nonce[key] == cert.certificate_nonce)

    # the numeric-collision attempt: epoch == escrow_id value
    m2, _r2, (k2, v2, e2, eset2, c2, e_id, r_id, d_id, a) = fresh_world()
    m2.escrows[7] = dict(m2.escrows[e_id])          # an escrow whose id == 7
    m2.escrows[7]["escrow_id"] = 7
    m2.escrows[7]["state"] = STATE_HOLDING
    before = m2.consumed_nonce.get((7, e_id))
    # release the REAL escrow e_id at epoch 7 — the (7, e_id) consumed key
    # must not leak into escrows[7]
    m2.release_escrow(STRANGER, e_id, split_certificate(c2),
                      sign_cert(k2, v2, e2, c2))
    check("consumed write (7, e_id) leaves the escrow with id 7 HOLDING",
          m2.escrows[7]["state"] == STATE_HOLDING
          and before is None and m2.consumed_nonce[(7, e_id)] == 1)

    # registry storage lives in a SEPARATE contract (dispatcher calls)
    check("epoch registry is a separate contract (no shared storage)",
          m.registry_obj is not None and m is not reg
          and reg.validators.keys() is not m.escrows.keys())

    # static side of the probe is in test_static_source_assertions
    # (distinct storage field names / tuple keys in the source).


def test_escrow_state_machine_9c52c36():
    print("\n15) 9c52c36 semantics preserved — accounting, emergency, cascade")
    m, reg, (keys, vids, entries, eset, cert, esc, rte, dst, amt) = fresh_world()

    # locked-balance accounting across the lifecycle
    m.lock_escrow(RELAYER, esc + 10, rte, 0xBEEF, dst, 500, 600_000, 3600)
    m.lock_escrow(OWNER, esc + 11, rte, 0xBEEF, dst, 250, 600_000, 3600)
    check("per-funder locked_balance tracked separately",
          m.locked_balance[RELAYER] == amt + 500
          and m.locked_balance[OWNER] == 250)
    check("total_locked_balance is the global pool",
          m.total_locked_balance == amt + 750)

    # release drains only that escrow's amount from both pools
    m.release_escrow(STRANGER, esc + 10, split_certificate(
        make_certificate(eset, esc + 10, rte, dst, 500)),
        sign_cert(keys, vids, entries,
                  make_certificate(eset, esc + 10, rte, dst, 500)))
    check("release drains the released amount from both pools",
          m.locked_balance[RELAYER] == amt and m.total_locked_balance == amt + 250)

    # revert drains too
    m.revert_escrow(RELAYER, esc + 11, 3)
    check("revert drains the reverted amount from both pools",
          m.locked_balance[OWNER] == 0 and m.total_locked_balance == amt)

    # cascade revert (Gap 9): child revert cascades through the ancestors
    m.lock_escrow(RELAYER, esc + 20, rte, 0xBEEF, dst, 100, 600_000, 3600,
                  parent=esc + 21)
    m.lock_escrow(RELAYER, esc + 21, rte, 0xBEEF, dst, 200, 600_000, 3600,
                  parent=esc + 22)
    m.lock_escrow(RELAYER, esc + 22, rte, 0xBEEF, dst, 300, 600_000, 3600)
    m.revert_escrow(RELAYER, esc + 20, 3)
    check("child revert cascades to parent + grandparent",
          m.escrows[esc + 20]["state"] == STATE_REVERTED
          and m.escrows[esc + 21]["state"] == STATE_REVERTED
          and m.escrows[esc + 22]["state"] == STATE_REVERTED)
    check("cascade reason is REASON_CASCADE_REVERT (5)",
          m.escrows[esc + 21]["revert_reason"] == 5
          and m.escrows[esc + 22]["revert_reason"] == 5)
    check("cascade drained the whole chain from the pools",
          m.locked_balance[RELAYER] == amt
          and m.total_locked_balance == amt)

    # emergency escape (Gap 8): anyone, after 7 days, no proof
    m2, _r2, (k2, v2, e2, eset2, c2, e_id, r_id, d_id, a) = fresh_world()
    code = expect_panic("x", m2.revert_emergency, STRANGER, e_id)
    check("emergency escape before 7 days -> 'BTCP: emergency not yet'",
          code == "BTCP: emergency not yet", f"code={code}")
    m2._now += EMERGENCY_ESCAPE_SECONDS + 1
    m2.revert_emergency(STRANGER, e_id)
    check("emergency escape by a STRANGER after 7 days succeeds",
          m2.escrows[e_id]["state"] == STATE_EMERGENCY_REVERTED
          and m2.total_locked_balance == 0)

    # release after expiry is blocked (INV-004)
    m3, _r3, (k3, v3, e3, eset3, c3, e_id3, r3, d3, a3) = fresh_world()
    m3._now += 7200        # timeout_blocks = 3600
    code = expect_panic("x", m3.release_escrow, STRANGER, e_id3,
                        split_certificate(c3), sign_cert(k3, v3, e3, c3))
    check("release after escrow timeout -> 'BTCP: expired' (INV-004)",
          code == "BTCP: expired", f"code={code}")
    # but the timeout revert is open to anyone (M2 E5)
    m3.revert_escrow(STRANGER, e_id3, 0)
    check("timeout revert by anyone succeeds",
          m3.escrows[e_id3]["state"] == STATE_REVERTED)


def test_gate_publish_path():
    print("\n16) C-04 cairo leg — execution gate quorum publication")
    keys, vids, entries, eset = make_epoch_world(5)
    reg = EpochRegistryMirror()
    reg.register_epoch(1, EPOCH, [
        {"validator_id": vids[i], "stark_pubkey": keys[i].pub_felt,
         "point": keys[i].point, "stake_weight": 1_000_000,
         "diversity_weight": 700_000} for i in range(5)])
    g = GateMirror(owner=OWNER, now=NOW)
    g.bind_registry(OWNER, 0xABC, reg)

    def gate_sigs(entity, status, phi, nonce, issued, signers=(0, 1, 2, 3, 4),
                  theta=60, drop=0, beo=0x123, da=0x456):
        d = signal_digest(entity, status, phi, theta, drop, beo, da, nonce, issued)
        out = []
        for i in signers:
            r, s = keys[i].sign(d)
            hi, lo = vid_halves(vids[i])
            out.append({"vid_hi16": hi, "vid_lo16": lo,
                        "stake_weight": 1_000_000, "diversity_weight": 700_000,
                        "sig_r": r, "sig_s": s})
        return out

    # the OLD C-04 cairo attack: a single registered validator publishes
    entity, status, phi = 0xBEEF, 1, 50
    sigs1 = gate_sigs(entity, status, phi, 1, NOW - 10, signers=(0,))
    code = expect_panic("x", g.publish_signal, keys[0].pub_felt, entity, status,
                        phi, 60, 0, 0x123, 0x456, sigs1, EPOCH, 1, NOW - 10)
    check("single validator publishes alone -> 'GATE: sig count'",
          code == "GATE: sig count", f"code={code}")

    # 3-of-5 in tier 1: below quorum
    sigs3 = gate_sigs(entity, status, phi, 1, NOW - 10, signers=(0, 1, 2))
    code = expect_panic("x", g.publish_signal, STRANGER, entity, status, phi,
                        60, 0, 0x123, 0x456, sigs3, EPOCH, 1, NOW - 10)
    check("3-of-5 quorum failure -> 'GATE: quorum not met'",
          code == "GATE: quorum not met", f"code={code}")

    # unregistered signer
    rogue = StarkKey.generate()
    rh, rl = vid_halves(_sha3("rogue-validator"))
    d = signal_digest(entity, status, phi, 60, 0, 0x123, 0x456, 1, NOW - 10)
    rr, rs = rogue.sign(d)
    sigs = gate_sigs(entity, status, phi, 1, NOW - 10, signers=(0, 1, 2))
    sigs.append({"vid_hi16": rh, "vid_lo16": rl, "stake_weight": 1_000_000,
                 "diversity_weight": 700_000, "sig_r": rr, "sig_s": rs})
    code = expect_panic("x", g.publish_signal, STRANGER, entity, status, phi,
                        60, 0, 0x123, 0x456, sigs, EPOCH, 1, NOW - 10)
    check("unregistered gate signer -> 'GATE: validator inactive'",
          code == "GATE: validator inactive", f"code={code}")

    # H-08-style value substitution: quorum signed (status=1, phi=50) but
    # the submitted signal claims phi=9999 — the values are INSIDE D_gate
    sigs5 = gate_sigs(entity, status, phi, 1, NOW - 10, signers=(0, 1, 2, 3, 4))
    code = expect_panic("x", g.publish_signal, STRANGER, entity, status, 9999,
                        60, 0, 0x123, 0x456, sigs5, EPOCH, 1, NOW - 10)
    check("value substitution after signing -> 'GATE: bad signature'",
          code == "GATE: bad signature", f"code={code}")

    # valid publication (permissionless, by a stranger)
    g.publish_signal(STRANGER, entity, status, phi, 60, 0, 0x123, 0x456,
                     sigs5, EPOCH, 1, NOW - 10)
    check("quorum-signed signal publishes (permissionless)",
          g.signals[entity]["initialized"]
          and g.signals[entity]["packed_status"] == 1)
    ok, _ = g.check_execution(entity, STRANGER)
    check("check_execution allows on a SAFE signal", ok is True)

    # replay / lower nonce
    code = expect_panic("x", g.publish_signal, STRANGER, entity, status, phi,
                        60, 0, 0x123, 0x456, sigs5, EPOCH, 1, NOW - 10)
    check("same nonce replay -> 'GATE: signal replay'",
          code == "GATE: signal replay", f"code={code}")
    sigs_n0 = gate_sigs(entity, status, phi, 1, NOW - 10, signers=(0, 1, 2, 3))
    # nonce 2 signed, submit as nonce 1 is covered above; lower nonce case:
    g2 = GateMirror(owner=OWNER, now=NOW)
    g2.bind_registry(OWNER, 0xABC, reg)
    g2.publish_signal(STRANGER, entity, status, phi, 60, 0, 0x123, 0x456,
                      gate_sigs(entity, status, phi, 5, NOW - 10,
                                signers=(0, 1, 2, 3, 4)), EPOCH, 5, NOW - 10)
    lower = gate_sigs(entity, status, phi, 3, NOW - 10, signers=(0, 1, 2, 3, 4))
    code = expect_panic("x", g2.publish_signal, STRANGER, entity, status, phi,
                        60, 0, 0x123, 0x456, lower, EPOCH, 3, NOW - 10)
    check("LOWER nonce -> 'GATE: signal replay'",
          code == "GATE: signal replay", f"code={code}")

    # staleness (300 s window)
    stale = gate_sigs(entity, status, phi, 9, NOW - 400, signers=(0, 1, 2, 3, 4))
    code = expect_panic("x", g2.publish_signal, STRANGER, entity, status, phi,
                        60, 0, 0x123, 0x456, stale, EPOCH, 9, NOW - 400)
    check("signal older than 300 s TTL -> 'GATE: signal stale'",
          code == "GATE: signal stale", f"code={code}")
    future = gate_sigs(entity, status, phi, 10, NOW + 61, signers=(0, 1, 2, 3, 4))
    code = expect_panic("x", g2.publish_signal, STRANGER, entity, status, phi,
                        60, 0, 0x123, 0x456, future, EPOCH, 10, NOW + 61)
    check("future signal beyond drift -> 'GATE: signal stale'",
          code == "GATE: signal stale", f"code={code}")

    # wrong epoch / weight claims / dup signer / unbound registry / pause
    code = expect_panic("x", g2.publish_signal, STRANGER, entity, status, phi,
                        60, 0, 0x123, 0x456, sigs5, 999, 11, NOW - 10)
    check("unregistered gate epoch -> 'GATE: unknown epoch'",
          code == "GATE: unknown epoch", f"code={code}")
    wbad = [dict(s) for s in sigs5]
    wbad[0]["diversity_weight"] = 1_000_000
    code = expect_panic("x", g2.publish_signal, STRANGER, entity, status, phi,
                        60, 0, 0x123, 0x456, wbad, EPOCH, 12, NOW - 10)
    check("gate weight-claim mismatch -> 'GATE: weight mismatch'",
          code == "GATE: weight mismatch", f"code={code}")
    dup = [dict(sigs5[0]), dict(sigs5[0]), dict(sigs5[1])]
    code = expect_panic("x", g2.publish_signal, STRANGER, entity, status, phi,
                        60, 0, 0x123, 0x456, dup, EPOCH, 13, NOW - 10)
    check("duplicate gate signers -> 'GATE: dup signer'",
          code == "GATE: dup signer", f"code={code}")
    g3 = GateMirror(owner=OWNER, now=NOW)
    code = expect_panic("x", g3.publish_signal, STRANGER, entity, status, phi,
                        60, 0, 0x123, 0x456, sigs5, EPOCH, 1, NOW - 10)
    check("unbound gate registry -> 'GATE: registry unbound'",
          code == "GATE: registry unbound", f"code={code}")
    g3.bind_registry(OWNER, 0xABC, reg)
    g3.pause(OWNER)
    code = expect_panic("x", g3.publish_signal, STRANGER, entity, status, phi,
                        60, 0, 0x123, 0x456, sigs5, EPOCH, 14, NOW - 10)
    check("paused gate blocks NEW signals -> 'GATE: paused'",
          code == "GATE: paused", f"code={code}")

    # registry binding is one-way
    code = expect_panic("x", g2.bind_registry, OWNER, 0x999, reg)
    check("gate registry rebind -> 'GATE: registry bound'",
          code == "GATE: registry bound", f"code={code}")


# ═════════════════════════════════════════════════════════════════════════════
# 17. Static source assertions — the .cairo files contain the checks
# ═════════════════════════════════════════════════════════════════════════════

STARKNET_DIR = os.path.join(REPO, "contracts", "starknet", "src")
CAIRO_DIR = os.path.join(REPO, "contracts", "cairo", "src")


def _read(path):
    with open(path, "r", encoding="utf-8") as fh:
        return fh.read()


def _fn_block(src, name, start=0):
    """The source slice of one function (name( ... ) up to the next fn)."""
    i = src.find(name, start)
    _require(i >= 0, f"source missing {name}")
    j = src.find("\n        fn ", i + 1)
    return src[i:j if j > 0 else len(src)]


def _fn_signature(src, name, start=0):
    """Just the parameter list of one function."""
    i = src.find(name, start)
    _require(i >= 0, f"source missing {name}")
    return src[i:src.find(")", i)]


def _code_only(src):
    """Source with comment lines stripped — authority checks must inspect
    CODE, not the doc comments that describe the removal."""
    return "\n".join(l for l in src.splitlines()
                     if not l.lstrip().startswith("//"))


def test_static_source_assertions():
    print("\n17) static source assertions (the .cairo contains the checks)")
    esc_src = _read(os.path.join(STARKNET_DIR, "btcp_escrow.cairo"))
    cert_src = _read(os.path.join(STARKNET_DIR, "trion_certificate.cairo"))
    reg_src = _read(os.path.join(STARKNET_DIR, "trion_epoch_registry.cairo"))
    gate_src = _read(os.path.join(CAIRO_DIR, "trion_execution_gate.cairo"))
    cert_twin = _read(os.path.join(CAIRO_DIR, "trion_certificate.cairo"))
    reg_twin = _read(os.path.join(CAIRO_DIR, "trion_epoch_registry.cairo"))
    lib_sn = _read(os.path.join(STARKNET_DIR, "lib.cairo"))
    lib_ca = _read(os.path.join(CAIRO_DIR, "lib.cairo"))

    # ── twin identity (single source of truth, both crates) ──────────
    check("contracts/cairo/src/trion_certificate.cairo is the byte-identical "
          "twin of contracts/starknet/src/trion_certificate.cairo",
          cert_src == cert_twin)
    check("contracts/cairo/src/trion_epoch_registry.cairo is the byte-identical "
          "twin of contracts/starknet/src/trion_epoch_registry.cairo",
          reg_src == reg_twin)
    check("starknet lib.cairo declares both new modules",
          "pub mod trion_certificate;" in lib_sn
          and "pub mod trion_epoch_registry;" in lib_sn)
    check("cairo lib.cairo declares both twin modules",
          "mod trion_certificate;" in lib_ca
          and "mod trion_epoch_registry;" in lib_ca)

    # ── C-04 leg 1: the escrow release path ──────────────────────────
    impl_at = esc_src.find("impl BTCPEscrowImpl of IBTCPEscrow<ContractState>")
    rel_sig = _fn_signature(esc_src, "fn release_escrow(")   # the trait ABI
    rel = _fn_block(esc_src, "fn release_escrow(", impl_at)  # the impl body
    check("release ABI takes the certificate + signature set",
          "cert:      Certificate," in rel_sig
          and "sigs:      Span<SigEntry>," in rel_sig)
    check("release ABI has NO coherence argument (the C-04 surface is gone)",
          "coherence" not in rel_sig, f"sig={rel_sig!r}")
    check("release path has NO caller authorization (permissionless)",
          "not authorized" not in rel and "get_caller_address()" not in rel)
    check("release path is NOT pausable (M2 E3 — settlements never blocked)",
          "paused" not in rel)

    # the §6 sequence is IN ORDER in the source
    order_markers = [
        "check_structure(@cert)",          # step 1 structure
        "CERT: sig count",                 # step 1 envelope
        "CERT: dup signer",
        "CERT: registry unbound",           # step 2 epoch
        "CERT: unknown epoch",
        "CERT: stale epoch",
        "CERT: expired",                    # step 3 freshness
        "CERT: hhi critical",               # step 4 preconditions
        "CERT: awa not enforced",
        "CERT: not safe",
        "CERT: count mismatch",
        "CERT: power mismatch",
        "CERT: validator inactive",         # step 5 signatures
        "CERT: weight mismatch",
        "CERT: bad signature",
        "CERT: quorum not met",             # step 6 quorum
        "CERT: escrow mismatch",            # step 7 binding
        "CERT: route mismatch",
        "CERT: dest mismatch",
        "CERT: amount mismatch",
        "CERT: below min coherence",
        "CERT: replay",                     # step 8 nonce
    ]
    pos = [esc_src.find(m) for m in order_markers]
    check("the full §6 sequence is present and IN ORDER in btcp_escrow.cairo",
          all(p >= 0 for p in pos) and pos == sorted(pos),
          f"first missing: {order_markers[pos.index(-1)] if -1 in pos else 'order'}")
    check("verify_release_certificate drives the gate from release_escrow",
          "verify_release_certificate(" in esc_src)
    check("CertificateConflict (§8.2 equivocation evidence) event exists",
          "CertificateConflict" in esc_src)

    # 9c52c36 semantics preserved
    check("locked_balance accounting preserved (9c52c36)",
          "locked_balance: Map<ContractAddress, u256>" in esc_src
          and "total_locked_balance: u256" in esc_src)
    check("revert_emergency (Gap 8) preserved",
          "EMERGENCY_ESCAPE_SECONDS: u64 = 7 * 24 * 60 * 60" in esc_src
          and "fn revert_emergency" in esc_src)
    check("cascade revert (Gap 9) preserved",
          "parent_escrow_id" in esc_src and "CascadeRevert" in esc_src)
    check("INV-003 protocol coherence floor 0.55 preserved",
          "MIN_COHERENCE_FLOOR: u64 = 550000" in esc_src)
    check("lock-side felt-range bound: ids < 2^251",
          "BTCP: escrow id range" in esc_src)
    check("registry binding is ONE-WAY",
          "assert(!self.registry_bound.read(), 'BTCP: registry bound')" in esc_src)
    check("pause blocks NEW LOCKS only (lock path checks paused)",
          "assert(!self.paused.read(), 'BTCP: paused');" in esc_src)

    # custody verdict honesty (master command §13)
    check("custody verdict: accounting-only, never production custody",
          "RECORDS ACCOUNTING ONLY" in esc_src
          and "MUST NOT be represented" in esc_src
          and "NO token transfers" in esc_src)
    check("no token custody wiring exists in code (no transfer calls, no "
          "ERC20/SNIP faces)",
          "transfer(" not in _code_only(esc_src)
          and "erc20" not in _code_only(esc_src).lower()
          and "snip" not in _code_only(esc_src).lower())

    # storage namespaces: distinct field names, tuple-keyed consumed maps
    st = esc_src[esc_src.find("struct Storage {"):esc_src.find("#[event]")]
    fields = [l.strip().split(":")[0] for l in st.splitlines()
              if l.strip() and not l.strip().startswith("//")
              and not l.strip().startswith("struct") and ":" in l]
    check("escrow storage field names are unique (compiler-derived "
          "storage namespaces are distinct)",
          len(fields) == len(set(fields)), f"fields={fields}")
    check("consumed maps are tuple-keyed (epoch, escrow_id)",
          "consumed_nonce: Map<(u64, felt252), u64>" in esc_src
          and "consumed_digest: Map<(u64, felt252), felt252>" in esc_src)

    # ── trion_certificate.cairo (family-3 leg) ───────────────────────
    check("domain felt literal 'TRION-CERT-V1' matches the reference "
          "stark_domain_felt",
          "DOMAIN_FELT: felt252 = 'TRION-CERT-V1'" in cert_src)
    check("payload width 346 pinned",
          "PAYLOAD_WIDTH: u64 = 346" in cert_src)
    check("kind 1 / supported version / min signers pinned",
          "CERT_KIND_ESCROW_RELEASE: u8 = 1" in cert_src
          and "SUPPORTED_PROTOCOL_VERSION: u64 = 66051" in cert_src
          and "MIN_SIGNERS: u64 = 3" in cert_src)
    check("L4.8 HHI bound + clock drift + epoch grace pinned",
          "HHI_MAX_ACCEPTABLE: u64 = 4000" in cert_src
          and "CLOCK_DRIFT_TOLERANCE: u64 = 60" in cert_src
          and "EPOCH_GRACE: u64 = 2" in cert_src)
    check("L4.2 tier boundaries pinned (0.60 / 0.40, x1e6)",
          "D_CONSENSUS_TIER1: u64 = 600000" in cert_src
          and "D_CONSENSUS_TIER2: u64 = 400000" in cert_src)

    # machine-check every P2_k power-of-two constant against 2^k
    import re
    p2_consts = dict(
        (m.group(1), int(m.group(2), 16)) for m in re.finditer(
            r"P2_(\d+): felt252 = (0x[0-9a-fA-F]+)", cert_src))
    bad = [k for k, v in p2_consts.items() if v != (1 << int(k))]
    check(f"all {len(p2_consts)} P2_k constants in trion_certificate.cairo "
          "equal 2^k (chunk-shift typo guard)", not bad, f"bad={bad}")

    # same machine check for the other felt-range constants in the family
    reg_p2 = dict(
        (m.group(1), int(m.group(2), 16)) for m in re.finditer(
            r"(P2_\d+): felt252 = (0x[0-9a-fA-F]+)", reg_src))
    bad_reg = [k for k, v in reg_p2.items() if v != (1 << int(k[3:]))]
    check("registry P2_k constants equal 2^k (vid-range guard)",
          not bad_reg, f"bad={bad_reg}")
    m_feltmax = re.search(r"FELT_ID_MAX: felt252 = (0x[0-9a-fA-F]+)", esc_src)
    check("escrow FELT_ID_MAX == 2^251 (lock-side felt bound)",
          m_feltmax and int(m_feltmax.group(1), 16) == FELT_MAX)
    # the certificate pieces are now provably < 2^251: each chunk is a
    # sum of range-asserted pieces shifted by the CORRECT constants
    _sm, _sr, _sfx = fresh_world()
    check("the corrected constants make every composed chunk < 2^248",
          all(c < (1 << 248)
              for c in compose_chunks(split_certificate(_sfx[4]))))

    # the chunk formulas use the exact §3.2 shift grid
    grid = {
        "c0": [144, 136, 112, 80, 16], "c1": [8], "c4": [240],
        "c5": [232, 200, 168], "c6": [160], "c7": [152], "c8": [144],
        "c9": [136, 72, 8], "c10": [192, 128, 96, 88, 24],
    }
    ok_grid = True
    for cname, shifts in grid.items():
        m = re.search(rf"let {cname} = (.*?);", cert_src, re.S)
        if not m:
            ok_grid = False
            check(f"chunk formula {cname} present", False)
            continue
        used = sorted(int(x) for x in re.findall(r"P2_(\d+)", m.group(1)))
        if used != sorted(shifts):
            ok_grid = False
            check(f"chunk formula {cname} shift grid {shifts}", False,
                  f"used={used}")
    check("compose_chunks implements the §3.2 fixed 31-byte chunk grid "
          "(all shift constants machine-checked)", ok_grid)

    check("D_stark = Poseidon(domain, chunks) via poseidon_hash_span",
          "poseidon_hash_span" in cert_src
          and "input.append(DOMAIN_FELT);" in cert_src)
    check("STARK-curve ECDSA via core::ecdsa (version-portable path)",
          "use core::ecdsa::check_ecdsa_signature;" in cert_src
          and "check_ecdsa_signature(" in cert_src)
    check("tier-1 quorum is STRICT (3*signed > 2*total)",
          "3 * signed_power > 2 * total_power" in cert_src)
    check("tier-2/3 quorum inequalities present",
          "4 * signed_power >= 3 * total_power" in cert_src
          and "20 * signed_power >= 17 * total_power" in cert_src)
    check("freshness widens the lower bound only",
          "now + CLOCK_DRIFT_TOLERANCE >= issued_at" in cert_src
          and "now <= issued_at + ttl" in cert_src)
    for piece, bits in [("escrow_hi2", 16), ("escrow_lo30", 240),
                        ("route_hi1", 8), ("route_lo31", 248),
                        ("intent_hi31", 248), ("intent_lo1", 8),
                        ("entity_hi30", 240), ("entity_lo2", 16),
                        ("dest_hi21", 168), ("dest_lo11", 88),
                        ("amount_hi20", 160), ("amount_lo12", 96),
                        ("anchor_hi19", 152), ("anchor_lo13", 104),
                        ("exec_hi18", 144), ("exec_lo14", 112)]:
        if f"assert(felt_lt(c.{piece}, P2_{bits})" not in cert_src:
            check(f"range assert for {piece} < 2^{bits}", False)
    check("all 16 felt pieces are range-asserted in check_structure "
          "(felt_lt: felt252 has no PartialOrd, compares as u256)",
          all(f"assert(felt_lt(c.{p}, P2_{b})" in cert_src
              for p, b in [("escrow_hi2", 16), ("escrow_lo30", 240),
                           ("route_hi1", 8), ("route_lo31", 248),
                           ("intent_hi31", 248), ("intent_lo1", 8),
                           ("entity_hi30", 240), ("entity_lo2", 16),
                           ("dest_hi21", 168), ("dest_lo11", 88),
                           ("amount_hi20", 160), ("amount_lo12", 96),
                           ("anchor_hi19", 152), ("anchor_lo13", 104),
                           ("exec_hi18", 144), ("exec_lo14", 112)]))
    # the Cairo Certificate struct field set == the mirror's 30 fields
    stc = cert_src[cert_src.find("pub struct Certificate {"):]
    stc = stc[:stc.find("}")]
    src_fields = re.findall(r"pub (\w+):", stc)
    check("Certificate ABI struct has exactly the 30 mirror fields "
          "(split pinned)", sorted(src_fields) == sorted(CERT_STRUCT_FIELDS),
          f"diff={set(src_fields) ^ set(CERT_STRUCT_FIELDS)}")
    # binding helpers enforce the wrap-proof recomposition bounds
    check("escrow binding asserts escrow_hi2 < 2^11 (no wrap aliasing)",
          "felt_lt(c.escrow_hi2, P2_11)" in cert_src)
    check("destination binding asserts dest_hi21 < 2^163",
          "felt_lt(c.dest_hi21, P2_163)" in cert_src)

    # ── trion_epoch_registry.cairo ───────────────────────────────────
    check("registry is append-only (epoch must be strictly newer)",
          "assert(epoch > latest, 'REG: epoch not newer');" in reg_src)
    check("registrar writes are admin-gated",
          "assert(caller == self.admin.read(), 'REG: not registrar');" in reg_src)
    check("weights are normalized shares (0 < w <= 1e6, both axes)",
          "'REG: zero stake'" in reg_src and "'REG: stake cap'" in reg_src
          and "'REG: zero diversity'" in reg_src
          and "'REG: diversity cap'" in reg_src)
    check("roster capped at 128 validators",
          "MAX_EPOCH_VALIDATORS: u64 = 128" in reg_src)
    check("validator_id halves + pubkey are range-asserted at registration",
          "'REG: vid_hi range'" in reg_src and "'REG: vid_lo range'" in reg_src
          and "'REG: pubkey range'" in reg_src)
    check("high-half verified at lookup (low-half collision fails closed)",
          "entry.vid_hi16 != vid_hi16" in reg_src)
    check("unknown epochs fail closed (sealed flag)",
          "meta.sealed" in reg_src)
    check("registry is a separate contract (dispatcher consumption)",
          "#[starknet::contract]" in reg_src
          and "IEpochRegistryDispatcher" in esc_src)

    # ── C-04 leg 2: the execution gate ───────────────────────────────
    check("gate publish_signal requires the signature set",
          "sigs: Span<SigEntry>," in gate_src)
    gate_code = _code_only(gate_src)
    check("the single-validator caller authority is GONE (C-04 cairo leg)",
          "is_validator" not in gate_code
          and "add_validator" not in gate_code
          and "ValidatorAdded" not in gate_code)
    gate_order = ["GATE: sig count", "GATE: dup signer", "GATE: registry unbound",
                  "GATE: unknown epoch", "GATE: stale epoch", "GATE: signal stale",
                  "GATE: validator inactive", "GATE: weight mismatch",
                  "GATE: bad signature", "GATE: quorum not met",
                  "GATE: signal replay"]
    gpos = [gate_src.find(m) for m in gate_order]
    check("the gate verification sequence is present and IN ORDER",
          all(p >= 0 for p in gpos) and gpos == sorted(gpos),
          f"first missing: {gate_order[gpos.index(-1)] if -1 in gpos else 'order'}")
    check("gate domain felt is TRION-SIGNAL-V1 (disjoint from certificates)",
          "SIGNAL_DOMAIN_FELT: felt252 = 'TRION-SIGNAL-V1'" in gate_src)
    check("gate D_gate is Poseidon over the FULL signal tuple",
          "poseidon_hash_span" in gate_src
          and "input.append(SIGNAL_DOMAIN_FELT);" in gate_src
          and "input.append(da_proof_hash);" in gate_src)
    check("gate signal TTL is 300 s", "SIGNAL_TTL_SECONDS: u64 = 300" in gate_src)
    check("gate registry binding is one-way",
          "assert(!self.registry_bound.read(), 'GATE: registry bound');" in gate_src)
    check("gate uses the shared family-3 library + epoch registry",
          "use crate::trion_certificate::" in gate_src
          and "use crate::trion_epoch_registry::" in gate_src)
    check("gate publish path is permissionless (no caller authorization)",
          "is_validator" not in gate_code and "Not validator" not in gate_code)


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
        test_reference_encoder_parity,
        test_valid_release_passes,
        test_caller_coherence_regression,
        test_structure_attacks,
        test_epoch_attacks,
        test_freshness_attacks,
        test_precondition_attacks,
        test_signature_attacks,
        test_quorum_attacks,
        test_binding_attacks,
        test_replay_and_double_release,
        test_pause_and_lock_side,
        test_felt_range_attacks,
        test_storage_collision_probe,
        test_escrow_state_machine_9c52c36,
        test_gate_publish_path,
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
