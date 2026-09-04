"""
TRION NEAR oracle (trion_oracle.rs) — C-05 canonical attestation compliance test.

C-05 (CRITICAL) remediation test for contracts/near/src/trion_oracle.rs:
publish_btcp_route was an owner/relayer-write route store (no signatures,
no quorum, no epoch, no freshness — the "TRION consensus is the only
oracle" invariant was absent). It is now the TRIONOracleV3
submitCertificateAttestation discipline ported to NEAR: the canonical
346-byte payload P (docs/protocol/CANONICAL_CERTIFICATE.md §2, byte-for-byte
the core/consensus/certificate.py reference) + Ed25519 attestations over
RAW P (§3.2 family 2 — NEAR's host ed25519_verify takes arbitrary-length
messages, no digest deviation), verified per §6 in order: structure →
epoch registry + grace → freshness (60 s drift, lower bound only) →
consensus preconditions (HHI/AWA/isSafe/Θ(t)-from-registry per H-03) →
signatures (batch fail-closed, sorted-distinct, membership, weight-claim
cross-check) → L4.2 tier quorum over REGISTERED s_j·d_j weights (u128
integer math) → etch-or-match binding → nonce/replay → write.

No cargo/rust toolchain exists in this sandbox, so this file is a PYTHON
MIRROR of the Rust logic (same check order, same assert messages) attacked
with REAL certificates produced by the Wave 1 reference encoder — the
ed25519 signatures verify over the exact P bytes with the `cryptography`
backend — plus static source assertions that the Rust contains the checks.

Run: python3 tests/contracts/test_trion_oracle_near.py   (or pytest)
"""

import copy
import hashlib
import importlib.util
import os
import sys

from cryptography.hazmat.primitives.asymmetric.ed25519 import (
    Ed25519PrivateKey,
    Ed25519PublicKey,
)

REPO = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

# Load the Wave 1 reference encoder by FILE PATH (no path-insert hacks —
# the tests/unit hygiene guard forbids new ones; same pattern as the TON
# mirror test). core/consensus/certificate.py has no repo-internal imports.
_spec = importlib.util.spec_from_file_location(
    "trion_core_consensus_certificate",
    os.path.join(REPO, "core", "consensus", "certificate.py"))
certificate = importlib.util.module_from_spec(_spec)
sys.modules["trion_core_consensus_certificate"] = certificate  # dataclass resolution
_spec.loader.exec_module(certificate)

CanonicalCertificate = certificate.CanonicalCertificate
EpochSetEntry = certificate.EpochSetEntry
EpochSet = certificate.EpochSet
pack_version = certificate.pack_version
ttl_for_value_usd = certificate.ttl_for_value_usd

PASSED = []
FAILED = []


def check(name, cond, detail=""):
    (PASSED if cond else FAILED).append(name)
    print(f"  {'OK' if cond else 'FAIL'} {name}" + (f" — {detail}" if detail and not cond else ""))
    return cond


# ═════════════════════════════════════════════════════════════════════════════
# 1. Constants mirrored from contracts/near/src/trion_oracle.rs
# ═════════════════════════════════════════════════════════════════════════════

PAYLOAD_WIDTH = 346
DOMAIN_TAG = b"TRION-CERT-V1"
CERT_KIND_ESCROW_RELEASE = 1
SUPPORTED_PROTOCOL_VERSION = 0x010203   # pack(1,2,3) — EVM parity
MIN_SIGNERS = 3
HHI_MAX_ACCEPTABLE = 4_000
CLOCK_DRIFT_TOLERANCE = 60
SCALE_1E6 = 1_000_000
D_CONSENSUS_TIER1 = 600_000
D_CONSENSUS_TIER2 = 400_000
EPOCH_GRACE_DEFAULT = 2
EPOCH_GRACE_MAX = 10


class NearPanic(Exception):
    """env::panic_str / assert! equivalent — aborts, nothing is committed."""

    def __init__(self, message):
        super().__init__(message)
        self.message = message


def _hex(b: bytes) -> str:
    return b.hex()


# ═════════════════════════════════════════════════════════════════════════════
# 2. Canonical payload P — strict parse (mirror of parse_payload)
# ═════════════════════════════════════════════════════════════════════════════

class ParsedCert:
    __slots__ = ("certificate_kind", "protocol_version", "validator_epoch",
                 "certificate_nonce", "escrow_id", "route_id", "intent_hash",
                 "entity_id", "source_chain", "dest_chain", "destination",
                 "amount", "anchor_bh", "execution_bh", "coherence",
                 "threshold", "hhi_at_emission", "total_effective_power",
                 "validator_count", "awa_enforced", "issued_at", "ttl")


def parse_payload(p: bytes):
    if len(p) != PAYLOAD_WIDTH:
        return None
    if p[0:13] != DOMAIN_TAG:
        return None
    # amount is a uint256 field; NEAR stores u128 — high 16 bytes must be zero
    if any(b != 0 for b in p[197:213]):
        return None
    c = ParsedCert()
    c.certificate_kind = p[13]
    c.protocol_version = int.from_bytes(p[14:17], "big")
    c.validator_epoch = int.from_bytes(p[17:21], "big")
    c.certificate_nonce = int.from_bytes(p[21:29], "big")
    c.escrow_id = p[29:61]
    c.route_id = p[61:93]
    c.intent_hash = p[93:125]
    c.entity_id = p[125:157]
    c.source_chain = int.from_bytes(p[157:161], "big")
    c.dest_chain = int.from_bytes(p[161:165], "big")
    c.destination = p[165:197]
    c.amount = int.from_bytes(p[213:229], "big")
    c.anchor_bh = p[229:261]
    c.execution_bh = p[261:293]
    c.coherence = int.from_bytes(p[293:301], "big")
    c.threshold = int.from_bytes(p[301:309], "big")
    c.hhi_at_emission = int.from_bytes(p[309:317], "big")
    c.total_effective_power = int.from_bytes(p[317:325], "big")
    c.validator_count = int.from_bytes(p[325:329], "big")
    c.awa_enforced = p[329]
    c.issued_at = int.from_bytes(p[330:338], "big")
    c.ttl = int.from_bytes(p[338:346], "big")
    return c


def certificate_hash(payload: bytes) -> bytes:
    """SHA3-256(P) — the canonical cross-VM id (§2.1/§7 NEAR row)."""
    return hashlib.sha3_256(payload).digest()


def quorum_met(signed_power: int, total_power: int, d_consensus: int) -> bool:
    if total_power == 0:
        return False
    if d_consensus >= D_CONSENSUS_TIER1:
        return 3 * signed_power > 2 * total_power      # STRICT: exactly-2/3 fails
    if d_consensus >= D_CONSENSUS_TIER2:
        return 4 * signed_power >= 3 * total_power
    return 20 * signed_power >= 17 * total_power


# ═════════════════════════════════════════════════════════════════════════════
# 3. The oracle mirror — Python twin of contracts/near/src/trion_oracle.rs
#    (C-05 path: register_epoch + publish_btcp_route; signal path reduced)
# ═════════════════════════════════════════════════════════════════════════════

class EpochRecord:
    def __init__(self, d_consensus, threshold, hhi, total_power, count,
                 registered_at=0, epoch_set_root=b"\x00" * 32):
        self.d_consensus = d_consensus
        self.threshold = threshold
        self.hhi = hhi
        self.total_power = total_power
        self.validator_count = count
        self.registered_at = registered_at
        self.epoch_set_root = epoch_set_root


class ValidatorEntry:
    def __init__(self, ed25519_pubkey, stake_weight, diversity_weight):
        self.ed25519_pubkey = ed25519_pubkey
        self.stake_weight = stake_weight
        self.diversity_weight = diversity_weight
        self.effective_weight = (stake_weight * diversity_weight) // SCALE_1E6


class Attestation:
    def __init__(self, validator_id, stake_weight, diversity_weight, signature):
        self.validator_id = validator_id
        self.stake_weight = stake_weight
        self.diversity_weight = diversity_weight
        self.signature = signature


class NearOracleMirror:
    """Mirrors trion_oracle.rs exactly: same check order, same assert
    messages. NEAR assertion failures abort the transaction — modeled as
    NearPanic raised mid-call with NO state commit (snapshot/restore)."""

    def __init__(self, owner="owner.near", relayer="relayer.near",
                 now=1_700_000_200):
        self.owner = owner
        self.relayer = relayer
        self.signals = {}
        self.routes = {}            # hex route_id → RouteRecord dict
        self.epochs = {}            # epoch → EpochRecord
        self.validators = {}        # (epoch, vid bytes) → ValidatorEntry
        self.highest_nonce = {}     # (epoch, escrow bytes) → u64
        self.nonce_digest = {}      # (epoch, escrow bytes) → 32B cert hash
        self.latest_epoch = 0
        self.epoch_grace = EPOCH_GRACE_DEFAULT
        self.signal_count = 0
        self.route_count = 0
        self._now = now
        self.predecessor = None
        self.logs = []

    # ── transaction wrapper (NEAR: assert aborts with no state commit) ──────
    def _txn(self, fn):
        snapshot = copy.deepcopy((self.routes, self.epochs, self.validators,
                                  self.highest_nonce, self.nonce_digest,
                                  self.latest_epoch, self.epoch_grace,
                                  self.route_count, self.signal_count,
                                  self.signals, self.logs))
        try:
            fn()
            return None
        except NearPanic as e:
            (self.routes, self.epochs, self.validators, self.highest_nonce,
             self.nonce_digest, self.latest_epoch, self.epoch_grace,
             self.route_count, self.signal_count, self.signals,
             self.logs) = copy.deepcopy(snapshot)
            return e.message

    # ── registrar administration (owner — documented trust root R-4) ────────
    def register_epoch(self, caller, epoch, validator_ids, ed25519_pubkeys,
                       stake_weights, diversity_weights, d_consensus,
                       threshold, hhi, epoch_set_root=b"\x00" * 32):
        def run():
            if caller != self.owner:
                raise NearPanic("TRION: not owner")
            if epoch != self.latest_epoch + 1:
                raise NearPanic("REG: epoch not sequential")
            n = len(validator_ids)
            if n < MIN_SIGNERS:
                raise NearPanic("REG: epoch set too small")
            if not (len(ed25519_pubkeys) == n and len(stake_weights) == n
                    and len(diversity_weights) == n):
                raise NearPanic("REG: shape")
            if d_consensus > SCALE_1E6:
                raise NearPanic("REG: d range")
            if threshold > SCALE_1E6:
                raise NearPanic("REG: theta range")
            if hhi > HHI_MAX_ACCEPTABLE:
                raise NearPanic("REG: hhi critical")
            total_power = 0
            last = b"\x00" * 32
            for i in range(n):
                vid = validator_ids[i]
                if not vid > last:
                    raise NearPanic("REG: validators must be ascending & distinct")
                last = vid
                s = stake_weights[i]
                d = diversity_weights[i]
                if s < 1:
                    raise NearPanic("REG: stake range")
                if d > SCALE_1E6:
                    raise NearPanic("REG: diversity range")
                w = (s * d) // SCALE_1E6
                self.validators[(epoch, vid)] = ValidatorEntry(
                    ed25519_pubkeys[i], s, d)
                total_power += w
            if total_power <= 0:
                raise NearPanic("REG: zero total power")
            if total_power > 2**64 - 1:
                raise NearPanic("REG: power range")
            self.epochs[epoch] = EpochRecord(d_consensus, threshold, hhi,
                                             total_power, n, self._now,
                                             epoch_set_root)
            self.latest_epoch = epoch
            self.logs.append(f"EpochRegistered:{epoch}")
        return self._txn(run)

    def set_epoch_grace(self, caller, grace):
        def run():
            if caller != self.owner:
                raise NearPanic("TRION: not owner")
            if grace > EPOCH_GRACE_MAX:
                raise NearPanic("REG: grace too wide")
            self.epoch_grace = grace
        return self._txn(run)

    # ── THE C-05 PATH: canonical certificate route publication ──────────────
    def publish_btcp_route(self, caller, payload: bytes, attestations):
        def run():
            # §6 1. STRUCTURE
            cert = parse_payload(payload)
            if cert is None:
                raise NearPanic("CERT: malformed payload")
            if cert.certificate_kind != CERT_KIND_ESCROW_RELEASE:
                raise NearPanic("CERT: unknown kind")
            if cert.protocol_version > SUPPORTED_PROTOCOL_VERSION:
                raise NearPanic("CERT: version too new")
            if cert.ttl == 0:
                raise NearPanic("CERT: zero ttl")
            if cert.dest_chain == 0:
                raise NearPanic("CERT: dest chain unbound")
            if len(attestations) < MIN_SIGNERS:
                raise NearPanic("CERT: below min signers")

            # §6 2. EPOCH — registered + within grace (fail-closed)
            epoch = cert.validator_epoch
            erec = self.epochs.get(epoch)
            if erec is None:
                raise NearPanic("CERT: validator epoch inactive")
            if not (self.latest_epoch >= epoch
                    and self.latest_epoch - epoch <= self.epoch_grace):
                raise NearPanic("CERT: validator epoch inactive")

            # registry conformance — the certificate may not lie about the
            # set; Θ(t) from the registry (H-03)
            if cert.validator_count != erec.validator_count:
                raise NearPanic("CERT: validator count mismatch")
            if cert.total_effective_power != erec.total_power:
                raise NearPanic("CERT: total power mismatch")
            if cert.threshold != erec.threshold:
                raise NearPanic("CERT: threshold not from registry")

            # §6 3. FRESHNESS — drift widens the LOWER bound only
            if cert.issued_at > self._now + CLOCK_DRIFT_TOLERANCE:
                raise NearPanic("CERT: future-dated")
            if self._now > cert.issued_at + cert.ttl:
                raise NearPanic("CERT: expired")

            # §6 4. CONSENSUS PRECONDITIONS
            if cert.hhi_at_emission > HHI_MAX_ACCEPTABLE:
                raise NearPanic("CERT: hhi critical")
            if cert.awa_enforced != 1:
                raise NearPanic("CERT: awa not enforced")
            if cert.coherence < cert.threshold:
                raise NearPanic("CERT: not safe")

            # §6 5. SIGNATURES — ed25519 over RAW P (family 2)
            signed_power = 0
            last_vid = b"\x00" * 32
            for att in attestations:
                if not att.validator_id > last_vid:
                    raise NearPanic("CERT: signer ordering required")
                last_vid = att.validator_id
                entry = self.validators.get((epoch, att.validator_id))
                if entry is None:
                    raise NearPanic("CERT: signer not in epoch set")
                if (att.stake_weight != entry.stake_weight
                        or att.diversity_weight != entry.diversity_weight):
                    raise NearPanic("CERT: envelope weight claim mismatch")
                try:
                    Ed25519PublicKey.from_public_bytes(
                        entry.ed25519_pubkey).verify(att.signature, payload)
                except Exception:
                    raise NearPanic("CERT: bad certificate signature")
                signed_power += entry.effective_weight

            # §6 6. QUORUM — L4.2 tier over REGISTERED D_consensus
            if not quorum_met(signed_power, erec.total_power, erec.d_consensus):
                raise NearPanic("CERT: weight quorum unmet")

            # §6 7. BINDING — etch-or-match (dispute fails closed)
            route_key = _hex(cert.route_id)
            existing = self.routes.get(route_key)
            if existing is not None:
                if not (existing["anchor_bh"] == _hex(cert.anchor_bh)
                        and existing["execution_bh"] == _hex(cert.execution_bh)
                        and existing["coherence"] == cert.coherence
                        and existing["threshold"] == cert.threshold
                        and existing["escrow_id"] == _hex(cert.escrow_id)
                        and existing["entity_id"] == _hex(cert.entity_id)
                        and existing["intent_hash"] == _hex(cert.intent_hash)
                        and existing["destination"] == _hex(cert.destination)
                        and existing["amount"] == cert.amount
                        and existing["source_chain"] == cert.source_chain
                        and existing["dest_chain"] == cert.dest_chain):
                    raise NearPanic("CERT: route values mismatch - disputed")

            # §6 8. NONCE ordering + conflict evidence (§8.2)
            scope = (epoch, cert.escrow_id)
            digest = certificate_hash(payload)
            highest = self.highest_nonce.get(scope, 0)
            if cert.certificate_nonce == highest:
                if digest == self.nonce_digest.get(scope, b"\x00" * 32):
                    return            # idempotent resubmission — no effect
                self.logs.append("CertificateEquivocation")
                return                # conflicting certificate rejected
            if cert.certificate_nonce < highest:
                raise NearPanic("CERT: stale certificate nonce")

            # §6 9. WRITE — only now may the route be written
            is_new = existing is None
            self.routes[route_key] = {
                "route_id": route_key,
                "anchor_bh": _hex(cert.anchor_bh),
                "execution_bh": _hex(cert.execution_bh),
                "coherence": cert.coherence,
                "threshold": cert.threshold,
                "is_safe": cert.coherence >= cert.threshold,
                "timestamp": self._now,
                "escrow_id": _hex(cert.escrow_id),
                "entity_id": _hex(cert.entity_id),
                "intent_hash": _hex(cert.intent_hash),
                "destination": _hex(cert.destination),
                "amount": cert.amount,
                "source_chain": cert.source_chain,
                "dest_chain": cert.dest_chain,
                "validator_epoch": epoch,
                "certificate_nonce": cert.certificate_nonce,
                "certificate_hash": digest,
                "signed_power": signed_power,
                "total_power": erec.total_power,
            }
            if is_new:
                self.route_count += 1
            self.highest_nonce[scope] = cert.certificate_nonce
            self.nonce_digest[scope] = digest
            self.logs.append("CertificateAttested")
        return self._txn(run)

    # ── signal path (relayer-gated — NOT route authority) ───────────────────
    def publish_signal(self, caller, entity_id, coherence, threshold, emits):
        def run():
            if caller != self.relayer:
                raise NearPanic("TRION: not relayer")
            if coherence > SCALE_1E6:
                raise NearPanic("TRION: invalid coherence")
            if threshold > SCALE_1E6:
                raise NearPanic("TRION: invalid threshold")
            self.signal_count += 1
        return self._txn(run)

    def verify_execution(self, route_id_hex):
        r = self.routes.get(route_id_hex)
        if r is None:
            return (False, 0, 0)
        return (r["is_safe"], r["coherence"], r["threshold"])


# ═════════════════════════════════════════════════════════════════════════════
# 4. Fixture: real canonical certificate + epoch set from the reference
# ═════════════════════════════════════════════════════════════════════════════

def _sha3(s: str) -> bytes:
    return hashlib.sha3_256(s.encode()).digest()


def make_fixture(n_validators=5, epoch=1, tier="t1", dest_seed="dest-N1"):
    keys = [Ed25519PrivateKey.generate() for _ in range(n_validators)]
    vids = [_sha3(f"validator-near-{i}") for i in range(n_validators)]
    d_val = {"t1": 700_000, "t2": 500_000, "t3": 300_000}[tier]

    entries = [EpochSetEntry(vids[i], stake_weight=3_000_000,
                             diversity_weight=d_val,
                             ed25519_pubkey=keys[i].public_key().public_bytes_raw())
               for i in range(n_validators)]
    eset = EpochSet(epoch, entries)

    escrow_id = _sha3("escrow-N1")
    route_id = _sha3("route-N1")
    destination = _sha3(dest_seed)
    amount = 3 * 10**24        # yoctoNEAR (u128 range)

    cert = CanonicalCertificate(
        validator_epoch=epoch,
        certificate_nonce=1,
        escrow_id=escrow_id,
        route_id=route_id,
        intent_hash=_sha3("intent-N1"),
        entity_id=_sha3("entity-N1"),
        source_chain=1,
        dest_chain=1316,       # NEAR, TRION registry id
        destination=destination,
        amount=amount,
        anchor_bh=_sha3("anchor-N1"),
        execution_bh=_sha3("execution-N1"),
        coherence=820_000,
        threshold=550_000,
        hhi_at_emission=1_200,
        total_effective_power=eset.total_effective_power(),
        validator_count=n_validators,
        awa_enforced=True,
        issued_at=1_700_000_100,
        ttl=ttl_for_value_usd(5_000.0),
    )
    return keys, vids, entries, eset, cert, escrow_id, route_id, destination, amount


def register_world(m: NearOracleMirror, keys, vids, entries, eset, cert,
                   now=1_700_000_200, epoch=None):
    """Registers the epoch set (ascending ids) + mirrors the cert fields."""
    order = sorted(range(len(vids)), key=lambda i: vids[i])
    return m.register_epoch(
        "owner.near", epoch if epoch is not None else cert.validator_epoch,
        [vids[i] for i in order],
        [keys[i].public_key().public_bytes_raw() for i in order],
        [entries[i].stake_weight for i in order],
        [entries[i].diversity_weight for i in order],
        eset.d_consensus(), cert.threshold, 1_200)


def attestations_for(keys, vids, entries, payload: bytes, signers=None):
    """Sorted ascending by validator_id (the V3 discipline); each signature
    is over RAW P — the family-2 digest on NEAR (host ed25519_verify)."""
    order = sorted(range(len(vids)), key=lambda i: vids[i])
    if signers is not None:
        order = [i for i in order if vids[i] in set(signers)]
    out = []
    for i in order:
        out.append(Attestation(vids[i], entries[i].stake_weight,
                               entries[i].diversity_weight,
                               keys[i].sign(payload)))
    return out


def fresh_world(tier="t1", n_validators=5, epoch=1):
    m = NearOracleMirror()
    fx = make_fixture(n_validators=n_validators, epoch=epoch, tier=tier)
    keys, vids, entries, eset, cert, escrow_id, route_id, dest, amount = fx
    register_world(m, keys, vids, entries, eset, cert)
    return m, fx


def mut(cert, **kw):
    c = copy.copy(cert)
    for k, v in kw.items():
        setattr(c, k, v)
    return c


def submit(m, cert, keys, vids, entries, caller="anyone.near", signers=None,
           payload=None):
    p = payload if payload is not None else cert.encode_payload()
    atts = attestations_for(keys, vids, entries, p, signers=signers)
    return m.publish_btcp_route(caller, p, atts)


# ═════════════════════════════════════════════════════════════════════════════
# 5. Attack matrix
# ═════════════════════════════════════════════════════════════════════════════

def test_valid_certificate_publishes_route():
    print("\n1) valid canonical certificate publishes the route (happy path)")
    m, (keys, vids, entries, eset, cert, escrow_id, route_id, dest, amount) = fresh_world()
    payload = cert.encode_payload()

    check("payload width is 346 bytes (§2)", len(payload) == PAYLOAD_WIDTH)
    check("domain tag TRION-CERT-V1 at offset 0",
          payload[:13] == b"TRION-CERT-V1")
    check("mirror certificate_hash == reference certificate_hash (SHA3-256)",
          certificate_hash(payload) == cert.certificate_hash())

    # permissionless: a NOBODY submits — the sender is only a transport
    err = submit(m, cert, keys, vids, entries, caller="total-stranger.near")
    check("submission by a non-owner/non-relayer SUCCEEDS (transport only)",
          err is None, f"err={err}")
    rec = m.routes.get(_hex(route_id))
    check("route record written keyed by hex(route_id)", rec is not None)
    check("is_safe recorded (coherence ≥ threshold)",
          m.verify_execution(_hex(route_id)) == (True, 820_000, 550_000))
    check("settlement tuple bound into the record (escrow/dest/amount)",
          rec["escrow_id"] == escrow_id.hex() and
          rec["destination"] == dest.hex() and rec["amount"] == amount)
    check("certificate_hash recorded = SHA3-256(P) cross-VM id",
          rec["certificate_hash"] == certificate_hash(payload))
    check("route_count == 1", m.route_count == 1)
    check("highest nonce recorded for (epoch, escrow)",
          m.highest_nonce.get((cert.validator_epoch, escrow_id)) == 1)


def test_c05_regression_owner_write_is_gone():
    print("\n2) C-05 regression — owner/relayer route writes no longer exist")
    m, (keys, vids, entries, eset, cert, escrow_id, route_id, dest, amount) = fresh_world()

    # the OLD C-05 surface: caller-supplied (route_id, anchor, execution,
    # coherence, threshold) written on an owner/relayer call. There is no
    # such entrypoint anymore — modeled here by the mirror accepting ONLY
    # (payload, attestations); a bare value-tuple cannot even be expressed.
    # The attacks that must fail, expressed through the new surface:
    err = m.publish_btcp_route("owner.near", cert.encode_payload(),
                               attestations_for(keys, vids, entries,
                                                cert.encode_payload())[:2])
    check("owner with 2 attestations (below min signers) rejected",
          err == "CERT: below min signers", f"err={err}")

    err = m.publish_btcp_route("relayer.near", cert.encode_payload(), [])
    check("relayer with NO attestations rejected (no authority path)",
          err == "CERT: below min signers", f"err={err}")

    # forged quorum: valid ids/claims but signatures by keys NOT registered
    rogue_keys = [Ed25519PrivateKey.generate() for _ in range(5)]
    payload = cert.encode_payload()
    atts = [Attestation(vids[i], entries[i].stake_weight,
                        entries[i].diversity_weight,
                        rogue_keys[i].sign(payload)) for i in range(5)]
    err = m.publish_btcp_route("owner.near", payload, atts)
    check("owner submitting FORGED signatures rejected (batch fail-closed)",
          err == "CERT: bad certificate signature", f"err={err}")
    check("no route written by the owner forgery attempt",
          _hex(route_id) not in m.routes and m.route_count == 0)

    # owner IS the registrar (validator governance) and registers an epoch —
    # but still cannot write a route without the registered keys signing
    err = submit(m, cert, keys, vids, entries, caller="owner.near")
    check("owner-submitted VALID envelope works (transport, not authority)",
          err is None, f"err={err}")


def test_signature_attacks():
    print("\n3) signature-set attacks (unregistered, bad sig, claims, order)")
    m, (keys, vids, entries, eset, cert, escrow_id, route_id, dest, amount) = fresh_world()
    payload = cert.encode_payload()

    # unregistered signer: swap one validator_id for an unknown one
    atts = attestations_for(keys, vids, entries, payload)
    rogue = _sha3("rogue-validator")
    atts[0] = Attestation(rogue, atts[0].stake_weight,
                          atts[0].diversity_weight, atts[0].signature)
    err = m.publish_btcp_route("x", payload, atts)
    check("unregistered signer rejected (CERT: signer not in epoch set)",
          err == "CERT: signer not in epoch set", f"err={err}")

    # forged signature (flip first byte)
    atts = attestations_for(keys, vids, entries, payload)
    sig = atts[0].signature
    atts[0] = Attestation(atts[0].validator_id, atts[0].stake_weight,
                          atts[0].diversity_weight,
                          bytes([sig[0] ^ 0xFF]) + sig[1:])
    err = m.publish_btcp_route("x", payload, atts)
    check("bad ed25519 signature rejected (CERT: bad certificate signature)",
          err == "CERT: bad certificate signature", f"err={err}")

    # weight claim mismatch (self-reported weights are never authority)
    atts = attestations_for(keys, vids, entries, payload)
    atts[0] = Attestation(atts[0].validator_id, atts[0].stake_weight + 1,
                          atts[0].diversity_weight, atts[0].signature)
    err = m.publish_btcp_route("x", payload, atts)
    check("envelope weight claim mismatch rejected",
          err == "CERT: envelope weight claim mismatch", f"err={err}")

    # duplicate signers (padding is not consensus)
    base = attestations_for(keys, vids, entries, payload)
    err = m.publish_btcp_route("x", payload, [base[0], base[0], base[1], base[2]])
    check("duplicate signer rejected (CERT: signer ordering required)",
          err == "CERT: signer ordering required", f"err={err}")

    # unsorted batch
    err = m.publish_btcp_route("x", payload, [base[1], base[0], base[2], base[3]])
    check("unsorted signer batch rejected",
          err == "CERT: signer ordering required", f"err={err}")

    # too few signers (liveness floor)
    err = m.publish_btcp_route("x", payload, base[:2])
    check("fewer than 3 signers rejected (CERT: below min signers)",
          err == "CERT: below min signers", f"err={err}")

    # signatures over a DIFFERENT payload must not publish this route
    other = mut(cert, amount=amount + 1)
    atts = attestations_for(keys, vids, entries, other.encode_payload())
    err = m.publish_btcp_route("x", payload, atts)
    check("signatures over a different P rejected (family-2 binding)",
          err == "CERT: bad certificate signature", f"err={err}")

    check("no route written by any signature attack",
          _hex(route_id) not in m.routes and m.route_count == 0)


def test_quorum_attacks():
    print("\n4) weight-quorum attacks (L4.2 tiers, registered weights only)")
    # tier 1 (D=0.70): 2/3 STRICT — exactly-2/3 must fail (6 equal weights)
    m6, (k6, v6, e6, es6, c6, _, rid6, _, _) = fresh_world(n_validators=6)
    err = submit(m6, c6, k6, v6, e6, signers=set(v6[:4]))
    check("tier1: exactly-2/3 weight (4/6) is NOT a quorum (strict >)",
          err == "CERT: weight quorum unmet", f"err={err}")
    err = submit(m6, c6, k6, v6, e6, signers=set(v6[:5]))
    check("tier1: 5/6 weight IS a quorum → route written",
          err is None and _hex(rid6) in m6.routes, f"err={err}")

    # tier 3 (D=0.30 → 0.85 bar): 2/3 weight must fail
    m3, (k3, v3, e3, es3, c3, _, rid3, _, _) = fresh_world(n_validators=6, tier="t3")
    err = submit(m3, c3, k3, v3, e3, signers=set(v3[:4]))
    check("tier3 (D<0.40): 2/3 weight FAILS the 0.85 bar",
          err == "CERT: weight quorum unmet", f"err={err}")
    err = submit(m3, c3, k3, v3, e3)
    check("tier3: full set signs → quorum met, route written",
          err is None and _hex(rid3) in m3.routes, f"err={err}")

    # low absolute weight: 3 signers of 5 (0.6) at tier1 fails
    m, (keys, vids, entries, eset, cert, escrow_id, route_id, _, _) = fresh_world()
    err = submit(m, cert, keys, vids, entries, signers=set(vids[:3]))
    check("tier1: 3/5 weight (0.6 < 2/3) rejected",
          err == "CERT: weight quorum unmet", f"err={err}")
    check("no route written by any quorum attack",
          _hex(route_id) not in m.routes and m.route_count == 0)


def test_epoch_binding_attacks():
    print("\n5) epoch binding (unknown / future / stale-beyond-grace)")
    m, (keys, vids, entries, eset, cert, escrow_id, route_id, _, _) = fresh_world()

    # unknown epoch (never registered)
    c = mut(cert, validator_epoch=99, certificate_nonce=5)
    err = submit(m, c, keys, vids, entries)
    check("unregistered (future) epoch rejected (CERT: validator epoch inactive)",
          err == "CERT: validator epoch inactive", f"err={err}")

    # stale beyond grace: cert epoch 1, rotate 2,3,4 — 4-1=3 > grace 2
    m2, fx2 = fresh_world()
    keys2, vids2, entries2, eset2, cert2 = fx2[0], fx2[1], fx2[2], fx2[3], fx2[4]
    for ep in (2, 3, 4):
        err = register_world(m2, keys2, vids2, entries2, eset2, cert2, epoch=ep)
        assert err is None
    err = submit(m2, cert2, keys2, vids2, entries2)
    check("epoch older than grace (1 vs latest 4) rejected",
          err == "CERT: validator epoch inactive", f"err={err}")

    # within grace still verifies
    m3, fx3 = fresh_world()
    keys3, vids3, entries3, eset3, cert3 = fx3[0], fx3[1], fx3[2], fx3[3], fx3[4]
    for ep in (2, 3):
        register_world(m3, keys3, vids3, entries3, eset3, cert3, epoch=ep)
    err = submit(m3, cert3, keys3, vids3, entries3)
    check("epoch within grace (1 vs latest 3) still verifies",
          err is None, f"err={err}")

    # registration itself is strictly sequential + owner-gated
    m4, fx4 = fresh_world()
    err = m4.register_epoch("owner.near", 99, fx4[1], [k.public_key().public_bytes_raw()
                                                       for k in fx4[0]],
                            [e.stake_weight for e in fx4[2]],
                            [e.diversity_weight for e in fx4[2]],
                            700_000, 550_000, 1200)
    check("epoch registration skipping epochs rejected (REG: epoch not sequential)",
          err == "REG: epoch not sequential", f"err={err}")
    err = m4.register_epoch("stranger.near", 2, fx4[1],
                            [k.public_key().public_bytes_raw() for k in fx4[0]],
                            [e.stake_weight for e in fx4[2]],
                            [e.diversity_weight for e in fx4[2]],
                            700_000, 550_000, 1200)
    check("non-owner cannot register epochs (TRION: not owner)",
          err == "TRION: not owner", f"err={err}")

    # mid-epoch membership swap impossible: re-registering the live epoch
    # is rejected by the sequential rule itself
    m5, fx5 = fresh_world()
    err = register_world(m5, fx5[0], fx5[1], fx5[2], fx5[3], fx5[4],
                         epoch=fx5[4].validator_epoch)
    check("re-registration of the LIVE epoch rejected (immutable set)",
          err == "REG: epoch not sequential", f"err={err}")

    # set the HHI CRITICAL bound at registration (frozen consensus cannot
    # register an emitting set — §5.3)
    m6, fx6 = fresh_world()
    err = m6.register_epoch("owner.near", 2, fx6[1],
                            [k.public_key().public_bytes_raw() for k in fx6[0]],
                            [e.stake_weight for e in fx6[2]],
                            [e.diversity_weight for e in fx6[2]],
                            700_000, 550_000, 4001)
    check("registration with hhi>4000 rejected (REG: hhi critical)",
          err == "REG: hhi critical", f"err={err}")


def test_freshness_and_preconditions():
    print("\n6) freshness + consensus preconditions (HHI/AWA/Θ(t)/count/power)")
    m, (keys, vids, entries, eset, cert, escrow_id, route_id, _, _) = fresh_world()

    def attempt(c, now=None, signers=None):
        mm, fx = fresh_world()
        if now is not None:
            mm._now = now
        return submit(mm, c, fx[0], fx[1], fx[2], signers=signers)

    check("expired certificate rejected (CERT: expired)",
          attempt(cert, now=cert.issued_at + cert.ttl + 1) == "CERT: expired")
    check("boundary: exactly issued_at+ttl still valid",
          attempt(cert, now=cert.issued_at + cert.ttl) is None)
    check("far-future certificate rejected (CERT: future-dated)",
          attempt(cert, now=cert.issued_at - CLOCK_DRIFT_TOLERANCE - 1)
          == "CERT: future-dated")
    check("drift tolerance: 59s future-dated accepted (lower bound only)",
          attempt(cert, now=cert.issued_at - 59) is None)

    check("ttl=0 rejected (CERT: zero ttl)",
          attempt(mut(cert, ttl=0)) == "CERT: zero ttl")
    check("hhi>4000 rejected (CERT: hhi critical)",
          attempt(mut(cert, hhi_at_emission=4001)) == "CERT: hhi critical")
    check("awa=0 rejected (CERT: awa not enforced)",
          attempt(mut(cert, awa_enforced=False)) == "CERT: awa not enforced")
    check("coherence<threshold rejected (CERT: not safe)",
          attempt(mut(cert, coherence=540_000)) == "CERT: not safe")
    # H-03: a quorum SIGNED a lowered bar (540_000 < registered 550_000) —
    # signatures pass, isSafe passes, the REGISTRY equality still rejects
    check("signed-but-lowered threshold ≠ registered Θ(t) rejected (H-03)",
          attempt(mut(cert, threshold=540_000))
          == "CERT: threshold not from registry")
    check("validator_count lie rejected",
          attempt(mut(cert, validator_count=4)) == "CERT: validator count mismatch")
    check("total_effective_power lie rejected",
          attempt(mut(cert, total_effective_power=cert.total_effective_power + 1))
          == "CERT: total power mismatch")
    check("unknown certificate_kind rejected (CERT: unknown kind)",
          attempt(mut(cert, certificate_kind=2)) == "CERT: unknown kind")
    check("future protocol_version rejected (CERT: version too new)",
          attempt(mut(cert, protocol_version=0x020000)) == "CERT: version too new")
    check("dest_chain=0 rejected (CERT: dest chain unbound)",
          attempt(mut(cert, dest_chain=0)) == "CERT: dest chain unbound")

    # malformed payloads (parse_payload — strict §2 decode)
    p = bytearray(cert.encode_payload())
    p[0] ^= 0x01
    err = m.publish_btcp_route("x", bytes(p),
                               attestations_for(keys, vids, entries, bytes(p)))
    check("corrupted domain tag rejected (CERT: malformed payload)",
          err == "CERT: malformed payload", f"err={err}")
    err = m.publish_btcp_route("x", cert.encode_payload()[:-1],
                               attestations_for(keys, vids, entries,
                                                cert.encode_payload()))
    check("wrong payload width rejected (CERT: malformed payload)",
          err == "CERT: malformed payload", f"err={err}")
    # amount exceeding u128 (high 16 bytes of the uint256 field non-zero)
    big = mut(cert, amount=2**130)
    err = m.publish_btcp_route("x", big.encode_payload(),
                               attestations_for(keys, vids, entries,
                                                big.encode_payload()))
    check("amount > u128 rejected (CERT: malformed payload — no truncation)",
          err == "CERT: malformed payload", f"err={err}")


def test_replay_and_binding_attacks():
    print("\n7) replay / nonce / route immutability")
    m, (keys, vids, entries, eset, cert, escrow_id, route_id, dest, amount) = fresh_world()

    err = submit(m, cert, keys, vids, entries)
    check("first certificate publishes the route", err is None)
    rec_before = m.routes[_hex(route_id)]
    ts_before = rec_before["timestamp"]

    # exact resubmission is an idempotent no-op (§8.2 observability)
    m._now += 500
    err = submit(m, cert, keys, vids, entries)
    check("exact certificate resubmission is an idempotent NO-OP",
          err is None, f"err={err}")
    check("route unchanged by resubmission (timestamp not refreshed)",
          m.routes[_hex(route_id)] == rec_before and
          m.routes[_hex(route_id)]["timestamp"] == ts_before)
    check("route_count still 1", m.route_count == 1)

    # lower nonce after consumption → rejected
    old = mut(cert, certificate_nonce=0)
    err = submit(m, old, keys, vids, entries)
    check("lower-nonce certificate rejected (CERT: stale certificate nonce)",
          err == "CERT: stale certificate nonce", f"err={err}")

    # same nonce, different payload → conflict: rejected, evidence logged,
    # the stored verdict is NOT overwritten (equivocation evidence class).
    # The conflicting cert keeps the route values identical (so it passes
    # §6 step 7 binding) and differs in an unbound field (issued_at).
    conflict = mut(cert, certificate_nonce=1, issued_at=cert.issued_at - 10)
    err = submit(m, conflict, keys, vids, entries)
    check("same-nonce different-payload rejected (conflict — no overwrite)",
          err is None, f"err={err}")
    check("conflict evidence logged (CertificateEquivocation)",
          "CertificateEquivocation" in m.logs)
    check("stored route NOT overwritten by the conflicting cert",
          m.routes[_hex(route_id)]["certificate_hash"]
          == certificate_hash(cert.encode_payload()))

    # higher nonce, same route values → refreshes the binding metadata
    higher = mut(cert, certificate_nonce=2)
    err = submit(m, higher, keys, vids, entries)
    check("higher-nonce certificate updates the route record",
          err is None and m.routes[_hex(route_id)]["certificate_nonce"] == 2,
          f"err={err}")

    # dispute: same route_id, different values → fail closed
    dispute = mut(cert, certificate_nonce=3, amount=amount + 1)
    err = submit(m, dispute, keys, vids, entries)
    check("conflicting values for the same route_id rejected (dispute)",
          err == "CERT: route values mismatch - disputed", f"err={err}")
    check("the disputed route record is unchanged",
          m.routes[_hex(route_id)]["amount"] == amount)


def test_signal_path_is_not_route_authority():
    print("\n8) the signal path stays relayer-gated and route-less")
    m, (keys, vids, entries, eset, cert, escrow_id, route_id, _, _) = fresh_world()
    check("relayer can publish signals (unchanged discipline)",
          m.publish_signal("relayer.near", "entity-1", 800_000, 500_000, True) is None)
    check("non-relayer cannot publish signals",
          m.publish_signal("stranger.near", "entity-1", 800_000, 500_000, True)
          == "TRION: not relayer")
    check("signals NEVER create routes (route_count 0, no route keys)",
          m.route_count == 0 and _hex(route_id) not in m.routes)


# ═════════════════════════════════════════════════════════════════════════════
# 6. Static source assertions — the Rust must contain the checks, in order
# ═════════════════════════════════════════════════════════════════════════════

def _method_body(src: str, name: str) -> str:
    start = src.index(f"pub fn {name}")
    end = src.index("pub fn", start + 1)
    return src[start:end]


def test_static_source_assertions():
    print("\n9) static source assertions (trion_oracle.rs / Cargo.toml)")
    src = open(os.path.join(REPO, "contracts", "near", "src",
                            "trion_oracle.rs")).read()
    cargo = open(os.path.join(REPO, "contracts", "near", "Cargo.toml")).read()
    body = _method_body(src, "publish_btcp_route")

    # C-05 core: publish_btcp_route is NOT owner/relayer-gated — the quorum
    # is the only route authority; the caller is transport only
    check("publish_btcp_route contains NO assert_owner call",
          "self.assert_owner();" not in body)
    check("publish_btcp_route contains NO assert_relayer call (C-05 closed)",
          "self.assert_relayer();" not in body)
    check("old route-exists immutability assert is gone (etch-or-match now)",
          '"TRION: route exists"' not in src)
    check("old caller-value signature (route_id: String, anchor_bh: String) gone",
          "route_id: String,\n        anchor_bh: String" not in src)

    # the primitives
    check("ed25519 host verification present (family 2)",
          "env::ed25519_verify(" in body)
    check("sha3 (FIPS SHA3-256) declared in Cargo.toml",
          'sha3 = "0.10"' in cargo)
    check("certificate hash computed with Sha3_256",
          "Sha3_256::new()" in src)
    check("payload width pinned at 346",
          "pub const PAYLOAD_WIDTH: usize = 346;" in src)
    check("domain tag TRION-CERT-V1 pinned",
          'b"TRION-CERT-V1"' in src)

    # §6 order: token positions strictly increasing in publish_btcp_route
    order = ["CERT: malformed payload", "CERT: unknown kind",
             "CERT: version too new", "CERT: zero ttl",
             "CERT: dest chain unbound", "CERT: below min signers",
             "CERT: validator epoch inactive",
             "CERT: validator count mismatch", "CERT: total power mismatch",
             "CERT: threshold not from registry",
             "CERT: future-dated", "CERT: expired",
             "CERT: hhi critical", "CERT: awa not enforced", "CERT: not safe",
             "CERT: signer ordering required", "CERT: signer not in epoch set",
             "CERT: envelope weight claim mismatch",
             "CERT: bad certificate signature",
             "CERT: weight quorum unmet",
             "CERT: route values mismatch - disputed",
             "CERT: stale certificate nonce",
             "route_count += 1", "highest_nonce.insert",
             "nonce_digest.insert"]
    pos = [body.index(tok) for tok in order]
    check("§6 verification order preserved in source (structure→epoch→"
          "freshness→preconditions→sigs→quorum→binding→nonce→write)",
          all(a < b for a, b in zip(pos, pos[1:])),
          f"order={[(t, p) for t, p in zip(order, pos) if True]}")

    # canonical constants
    check("MIN_SIGNERS = 3", "pub const MIN_SIGNERS: usize = 3;" in src)
    check("HHI_MAX_ACCEPTABLE = 4000 (§5.3)",
          "pub const HHI_MAX_ACCEPTABLE: u64 = 4_000;" in src)
    check("CLOCK_DRIFT_TOLERANCE = 60 (§9.1)",
          "pub const CLOCK_DRIFT_TOLERANCE: u64 = 60;" in src)
    check("tier thresholds D=600000/400000 (§5.2)",
          "pub const D_CONSENSUS_TIER1: u64 = 600_000;" in src and
          "pub const D_CONSENSUS_TIER2: u64 = 400_000;" in src)
    check("tier1 uses STRICT 3·signed > 2·total",
          "3 * signed_power > 2 * total_power" in src)
    check("tier2 uses 4·signed ≥ 3·total",
          "4 * signed_power >= 3 * total_power" in src)
    check("tier3 uses 20·signed ≥ 17·total",
          "20 * signed_power >= 17 * total_power" in src)
    check("quorum math is u128 integer (mandated)",
          "signed_power: u128" in src and "total_power: u128" in src)

    # H-03 threshold provenance + epoch discipline
    check("registry stores Θ(t) (EpochRecord.threshold)",
          "pub threshold:       u64," in src)
    check("cert threshold must equal registered Θ(t) (H-03)",
          "cert.threshold == erec.threshold" in body)
    check("epoch registration strictly sequential (forward-only)",
          '"REG: epoch not sequential"' in src)
    check("epoch grace default 2, bounded 10 (ED-G)",
          "EPOCH_GRACE_DEFAULT: u32 = 2" in src and
          "EPOCH_GRACE_MAX: u32 = 10" in src)
    check("freshness drift widens the LOWER bound only",
          "cert.issued_at <= now + CLOCK_DRIFT_TOLERANCE" in body and
          "now <= cert.issued_at + cert.ttl" in body)
    check("idempotent resubmission no-op present (§8.2)",
          "idempotent resubmission" in src)
    check("amount uint256 is enforced ≤ u128 (no truncation)",
          "p[197..213].iter().any(|&b| b != 0)" in src)


# ═════════════════════════════════════════════════════════════════════════════
# 7. Reference-encoder parity (golden cross-check)
# ═════════════════════════════════════════════════════════════════════════════

def test_reference_encoder_parity():
    print("\n10) reference encoder parity (payload semantics)")
    m, (keys, vids, entries, eset, cert, escrow_id, route_id, dest, amount) = fresh_world()
    p = cert.encode_payload()
    parsed = parse_payload(p)
    check("payload width is 346 bytes", len(p) == 346)
    check("mirror parse round-trips every §2 field",
          parsed.certificate_nonce == cert.certificate_nonce and
          parsed.certificate_kind == cert.certificate_kind and
          parsed.protocol_version == cert.protocol_version and
          parsed.validator_epoch == cert.validator_epoch and
          parsed.escrow_id == cert.escrow_id and
          parsed.route_id == cert.route_id and
          parsed.intent_hash == cert.intent_hash and
          parsed.entity_id == cert.entity_id and
          parsed.source_chain == cert.source_chain and
          parsed.dest_chain == cert.dest_chain and
          parsed.destination == cert.destination and
          parsed.amount == cert.amount and
          parsed.anchor_bh == cert.anchor_bh and
          parsed.execution_bh == cert.execution_bh and
          parsed.coherence == cert.coherence and
          parsed.threshold == cert.threshold and
          parsed.hhi_at_emission == cert.hhi_at_emission and
          parsed.total_effective_power == cert.total_effective_power and
          parsed.validator_count == cert.validator_count and
          parsed.awa_enforced == 1 and
          parsed.issued_at == cert.issued_at and
          parsed.ttl == cert.ttl)
    check("certificate_hash = SHA3-256(P) — the cross-VM id",
          certificate_hash(p) == hashlib.sha3_256(p).digest() == cert.certificate_hash())
    check("weights: registered total == Σ s·d/1e6 (×1e6 fixed point)",
          eset.total_effective_power() == sum(
              (e.stake_weight * e.diversity_weight) // SCALE_1E6
              for e in entries))
    # EVM-family digest differs from the canonical hash (never mixed);
    # NEAR family-2 signs RAW P — cross-family identical signed bytes
    try:
        Ed25519PublicKey.from_public_bytes(
            keys[0].public_key().public_bytes_raw()
        ).verify(keys[0].sign(p), p)
        raw_p_verifies = True
    except Exception:
        raw_p_verifies = False
    check("family-2 signed bytes are the raw 346-byte P",
          raw_p_verifies)


ALL_TESTS = [
    test_valid_certificate_publishes_route,
    test_c05_regression_owner_write_is_gone,
    test_signature_attacks,
    test_quorum_attacks,
    test_epoch_binding_attacks,
    test_freshness_and_preconditions,
    test_replay_and_binding_attacks,
    test_signal_path_is_not_route_authority,
    test_static_source_assertions,
    test_reference_encoder_parity,
]


def test_all_checks_passed():
    for t in ALL_TESTS:
        t()
    assert not FAILED, f"FAILED checks: {FAILED}"


def main():
    for t in ALL_TESTS:
        t()
    print(f"\n═══ RESULT: {len(PASSED)} passed, {len(FAILED)} failed ═══")
    if FAILED:
        print("FAILED:", FAILED)
        sys.exit(1)
    print("NEAR trion_oracle C-05: canonical attestation discipline verified "
          "(py mirror of the Rust + static source assertions; cargo build is "
          "the documented unverified boundary).")


if __name__ == "__main__":
    main()
