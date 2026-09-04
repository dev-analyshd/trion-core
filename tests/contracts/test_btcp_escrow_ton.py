"""
BTCP escrow (TON / FunC) — canonical certificate verification compliance test.

C-01 (CRITICAL) remediation test for contracts/ton/escrow.fc: op 0x02 now
requires the canonical certificate envelope of
docs/protocol/CANONICAL_CERTIFICATE.md and verifies it per §6 — epoch
registry, TVM-native Ed25519 (CHKSIGNU over BE32(cell_hash(P-root))),
L4.2 tier quorum over REGISTERED weights, freshness, settlement-tuple
binding, nonce/replay. The old caller-supplied-coherence release is gone.

No func toolchain exists in this sandbox, so this file is a PYTHON MIRROR of
the FunC validation logic (same field parse order, same error codes, same
§6 step order), attacked with REAL certificates produced by the Wave 1
reference encoder core/consensus/certificate.py. Plus:
  * a TVM cell model (bit-exact pinned layouts + the SHA-512 representation
    hash that TVM's cell_hash/HASHCU computes) so the signature digest path
    is modeled end-to-end;
  * static source assertions that the FunC actually contains the checks in
    the canonical order (and that the relayer/owner authorization is gone
    from the release path).

HONEST UNVERIFIED BOUNDARIES (no func/ton toolchain here):
  * FunC compilation is not exercised — the .fc is verified by the mirror
    + cell_layout.test.js (bit budgets) + static assertions;
  * the TVM cell-hash model (d1 = refs, d2 = ceil((bits+1)/8), data +
    completion tag + child hashes, SHA-512 truncated to 256 bits) follows
    the TVM spec's ordinary-cell construction; a real TON integration test
    must confirm HASHCU == this model before first mainnet emission.

Run: python3 tests/contracts/test_btcp_escrow_ton.py   (or pytest)
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

# Load the Wave 1 reference encoder by FILE PATH — no path bootstrapping at
# all (the tests/unit hygiene guard forbids new path-insert hacks; also no
# importlib sys.modules pollution beyond registering the loaded module).
# core/consensus/certificate.py has no repo-internal imports, so a direct
# spec load is clean and the same code object the unit golden vectors pin.
_spec = importlib.util.spec_from_file_location(
    "trion_core_consensus_certificate",
    os.path.join(REPO, "core", "consensus", "certificate.py"))
certificate = importlib.util.module_from_spec(_spec)
sys.modules["trion_core_consensus_certificate"] = certificate  # dataclass resolution
_spec.loader.exec_module(certificate)

CanonicalCertificate = certificate.CanonicalCertificate
EpochSet = certificate.EpochSet
EpochSetEntry = certificate.EpochSetEntry
CertificateEnvelope = certificate.CertificateEnvelope
WeightedSignatureEntry = certificate.WeightedSignatureEntry
SignatureFamily = certificate.SignatureFamily
pack_version = certificate.pack_version
ttl_for_value_usd = certificate.ttl_for_value_usd

PASSED = []
FAILED = []


def check(name, cond, detail=""):
    (PASSED if cond else FAILED).append(name)
    print(f"  {'OK' if cond else 'FAIL'} {name}" + (f" — {detail}" if detail and not cond else ""))
    return cond


# ═════════════════════════════════════════════════════════════════════════════
# 1. TVM cell model (pinned layouts, bit-exact)
# ═════════════════════════════════════════════════════════════════════════════

TVM_CELL_MAX_BITS = 1023


class TVMError(Exception):
    """Mirrors a TVM exception — transaction aborts, nothing is committed."""

    def __init__(self, code):
        super().__init__(f"TVM exception {code}")
        self.code = code


class Cell:
    def __init__(self, bits="", refs=None):
        self.bits = bits          # '0'/'1' string
        self.refs = refs or []    # list[Cell]


class Builder:
    def __init__(self):
        self.bits = ""
        self.refs = []

    def uint(self, value, n):
        assert 0 <= value < (1 << n), (value, n)
        self.bits += format(value, "0%db" % n)
        return self

    def bytes_(self, data, nbytes=None):
        nbytes = nbytes if nbytes is not None else len(data)
        self.bits += format(int.from_bytes(data, "big"), "0%db" % (nbytes * 8))
        return self

    def raw_bits(self, bits):
        self.bits += bits
        return self

    def ref(self, cell):
        self.refs.append(cell)
        return self

    def end(self):
        assert len(self.bits) <= TVM_CELL_MAX_BITS, f"cell overflow: {len(self.bits)} bits"
        assert len(self.refs) <= 4
        return Cell(self.bits, list(self.refs))


class SliceCursor:
    """Parse one cell: explicit-width loads; underflow ⇒ TVM exception 9."""

    def __init__(self, cell):
        self.cell = cell
        self.pos = 0
        self.refs_left = list(cell.refs)

    def _take(self, n):
        if self.pos + n > len(self.cell.bits):
            raise TVMError(9)  # cell underflow — fail closed, TVM native
        bits = self.cell.bits[self.pos:self.pos + n]
        self.pos += n
        return bits

    def load_uint(self, n):
        return int(self._take(n), 2)

    def load_int8(self):
        bits = self._take(8)
        v = int(bits, 2)
        return v - 256 if bits[0] == "1" else v

    def load_bits(self, n):
        return self._take(n)

    def load_ref(self):
        if not self.refs_left:
            raise TVMError(9)  # no ref left — underflow
        return self.refs_left.pop(0)

    def slice_empty(self):
        return self.pos == len(self.cell.bits) and not self.refs_left


def cell_hash_bytes(c: Cell) -> bytes:
    """TVM representation hash (HASHCU) of an ORDINARY cell:
    SHA-512 over  d1=ref_count, d2=ceil((bits+1)/8), data bits + completion
    tag zero-padded to a byte boundary, then each child's 32-byte hash —
    truncated to the first 256 bits."""
    d1 = len(c.refs)
    padded = c.bits + "1"
    padded += "0" * (-len(padded) % 8)
    d2 = len(padded) // 8
    data = int(padded, 2).to_bytes(d2, "big") if d2 else b""
    h = hashlib.sha512(bytes([d1, d2]) + data +
                       b"".join(cell_hash_bytes(r) for r in c.refs)).digest()
    return h[:32]


def cell_hash(c: Cell) -> int:
    return int.from_bytes(cell_hash_bytes(c), "big")


# ═════════════════════════════════════════════════════════════════════════════
# 2. Canonical envelope construction (real certificates from the reference)
# ═════════════════════════════════════════════════════════════════════════════
# The signer (validator) signs BE32(cell_hash(P0)) — the documented TVM
# family-2 digest (CHKSIGNU). P0..P3 are the PINNED 4-cell tree: the
# concatenation of all four cells' data bits is EXACTLY the 346-byte
# canonical payload P.

P_TREE_SPLITS = [(0, 93), (93, 197), (197, 293), (293, 346)]  # byte offsets


def build_p_tree(payload: bytes):
    chunks = [Builder().bytes_(payload[a:b], b - a) for (a, b) in P_TREE_SPLITS]
    cells = [None] * len(chunks)
    cells[-1] = chunks[-1].end()
    for i in range(len(chunks) - 2, -1, -1):
        cells[i] = chunks[i].ref(cells[i + 1]).end()
    return cells


def p_tree_bits_roundtrip(payload: bytes):
    tree = build_p_tree(payload)
    return "".join(c.bits for c in tree)


def build_sig_chain(sigs):
    """sigs: list of (validator_id bytes32, stake, div, signature bytes)
    — MUST already be sorted ascending by validator_id."""
    chunks = []
    for i, (vid, stake, div, sig) in enumerate(sigs):
        has_next = 1 if i + 1 < len(sigs) else 0
        chunks.append((Builder().uint(has_next, 1)
                       .bytes_(vid, 32)
                       .uint(stake, 64)
                       .uint(div, 64)
                       .bytes_(sig, 64)))
    cells = [None] * len(chunks)
    cells[-1] = chunks[-1].end()
    for i in range(len(chunks) - 2, -1, -1):
        cells[i] = chunks[i].ref(cells[i + 1]).end()
    return cells[0]


def build_release_body(escrow_id: bytes, p_tree, sig_chain: Cell) -> Cell:
    return (Builder().uint(0x02, 8)
            .bytes_(escrow_id, 32)
            .ref(p_tree[0])
            .ref(sig_chain)
            .end())


# ═════════════════════════════════════════════════════════════════════════════
# 3. The escrow mirror — Python twin of contracts/ton/escrow.fc (C-01 path)
# ═════════════════════════════════════════════════════════════════════════════
# Error codes are IDENTICAL to the FunC file (asserted statically below).

ERR_ESCROW_NOT_FOUND = 121
ERR_NOT_HOLDING = 122
ERR_EXPIRED = 123
ERR_COHERENCE_INSUFF = 124
ERR_PAUSED = 130
ERR_CERT_TAG = 131
ERR_CERT_KIND = 132
ERR_CERT_VERSION = 133
ERR_EPOCH_UNKNOWN = 134
ERR_EPOCH_STALE = 135
ERR_CERT_EXPIRED = 136
ERR_CERT_FUTURE = 137
ERR_CERT_TTL = 138
ERR_CERT_HHI = 139
ERR_CERT_AWA = 140
ERR_CERT_UNSAFE = 141
ERR_CERT_THRESHOLD = 161          # H-03: cert threshold != registered Θ(t)
ERR_CERT_COUNT = 142
ERR_CERT_POWER = 143
ERR_BIND_ESCROW = 144
ERR_BIND_ROUTE = 145
ERR_BIND_ENTITY = 146
ERR_BIND_DEST = 147
ERR_BIND_AMOUNT = 148
ERR_SIG_UNREGISTERED = 149
ERR_SIG_WEIGHT_CLAIM = 150
ERR_SIG_WEIGHT_BAD = 151
ERR_SIG_ORDER = 152
ERR_SIG_BAD = 153
ERR_SIG_TOO_FEW = 154
ERR_QUORUM = 155
ERR_CERT_REPLAY = 156
ERR_EPOCH_MISMATCH = 157
ERR_REG_MALFORMED = 158
ERR_CERT_TAIL = 159
ERR_UNKNOWN_OP = 160

TRION_CERT_V1_TAG = 0x5452494F4E2D434552542D5631  # "TRION-CERT-V1" (104 bits)
CERT_KIND_RELEASE = 1
CERT_VERSION_MAX = 0x010000
HHI_MAX_ACCEPTABLE = 4000
SCALE_1E6 = 1_000_000
D_CONSENSUS_TIER1 = 600_000
D_CONSENSUS_TIER2 = 400_000
MIN_SIGNERS = 3
EPOCH_GRACE = 2
CLOCK_DRIFT_SECS = 60

STATE_HOLDING, STATE_RELEASED, STATE_REVERTED, STATE_EMERGENCY_REVERTED = 0, 1, 2, 3


def dest_addr_bits(account_hash: int) -> str:
    """basechain MsgAddressInt: tag 10, no anycast, wc 0, 256-bit account."""
    return "10" + "0" + format(0, "08b") + format(account_hash, "0256b")


def is_bindable_destination(bits267: str) -> bool:
    return (bits267[:2] == "10" and bits267[2] == "0" and
            int(bits267[3:11], 2) == 0)  # wc signed 8 == 0


def dest_matches_canonical(bits267: str, canonical: int) -> bool:
    return is_bindable_destination(bits267) and int(bits267[11:267], 2) == canonical


def quorum_met(signed_power, total_power, d_consensus):
    if d_consensus >= D_CONSENSUS_TIER1:
        return 3 * signed_power > 2 * total_power      # STRICT: exactly-2/3 fails
    if d_consensus >= D_CONSENSUS_TIER2:
        return 4 * signed_power >= 3 * total_power
    return 20 * signed_power >= 17 * total_power


class EscrowRecord:
    def __init__(self, escrow_id, route_id, entity_id, dest_bits, amount,
                 min_coherence, lock_ts, timeout_secs, state=STATE_HOLDING,
                 revert_reason=0, settled_at=0, reverted_at=0, locked_by=""):
        self.escrow_id = escrow_id
        self.route_id = route_id
        self.entity_id = entity_id
        self.dest_bits = dest_bits                # 267-bit string
        self.amount = amount
        self.min_coherence = min_coherence
        self.lock_ts = lock_ts
        self.timeout_secs = timeout_secs
        self.state = state
        self.revert_reason = revert_reason
        self.settled_at = settled_at
        self.reverted_at = reverted_at
        self.locked_by = locked_by


class EpochEntry:
    def __init__(self, epoch, d_consensus, threshold, hhi, total_power, count,
                 validators, set_root=0, registered_at=0):
        self.epoch = epoch
        self.d_consensus = d_consensus
        self.threshold = threshold        # registered Θ(t) (H-03)
        self.hhi = hhi
        self.total_power = total_power
        self.count = count
        # validators: {validator_id int → (pubkey bytes32, stake, div, w)}
        self.validators = validators
        self.set_root = set_root
        self.registered_at = registered_at


class TVMEscrowMirror:
    """Python twin of contracts/ton/escrow.fc — the C-01 release path only
    (lock/revert/registration reduced to what the tests need). TVM
    transaction semantics: any exception aborts EVERYTHING (state, balance
    — modeled via snapshot/restore)."""

    def __init__(self, owner="owner", relayer="relayer", now=1_700_000_000):
        self.owner = owner
        self.relayer = relayer
        self.escrow_count = 0
        self.paused = 0
        self.current_epoch = 0
        self.escrows = {}
        self.epochs = {}
        self.consumed = {}
        self.vault_balance = 0
        self.dest_balances = {}
        self.dead_destinations = set()
        self._now = now

    # ── transaction wrapper (TVM atomicity) ──────────────────────────────────
    def _txn(self, fn):
        snapshot = copy.deepcopy((self.escrows, self.epochs, self.consumed,
                                  self.escrow_count, self.paused,
                                  self.current_epoch, self.vault_balance,
                                  self.dest_balances))
        try:
            fn()
            return None
        except TVMError as e:
            (self.escrows, self.epochs, self.consumed, self.escrow_count,
             self.paused, self.current_epoch, self.vault_balance,
             self.dest_balances) = copy.deepcopy(snapshot)
            return e.code

    # ── op 0x01 lock (relayer/owner; paused blocks new locks) ───────────────
    def lock(self, sender, value, escrow_id, route_id, min_coherence,
             timeout_secs, entity_id, dest_bits):
        def run():
            if sender not in (self.owner, self.relayer):
                raise TVMError(100)
            if self.paused:
                raise TVMError(ERR_PAUSED)
            if value <= 0:
                raise TVMError(125)
            if timeout_secs <= 0:
                raise TVMError(126)
            if min_coherence > 1_000_000:
                raise TVMError(128)
            if not is_bindable_destination(dest_bits):
                raise TVMError(ERR_BIND_DEST)
            if escrow_id in self.escrows:
                raise TVMError(120)
            self.escrows[escrow_id] = EscrowRecord(
                escrow_id, route_id, entity_id, dest_bits, value,
                min_coherence, self._now, timeout_secs, STATE_HOLDING,
                0, 0, 0, sender)
            self.escrow_count += 1
            self.vault_balance += value
        return self._txn(run)

    # ── op 0x07 register_epoch (owner = registrar, R-4) ─────────────────────
    def register_epoch(self, sender, entry: EpochEntry):
        def run():
            if sender != self.owner:
                raise TVMError(100)
            if entry.d_consensus > SCALE_1E6:
                raise TVMError(ERR_REG_MALFORMED)
            if entry.threshold > SCALE_1E6:
                raise TVMError(ERR_REG_MALFORMED)
            if entry.hhi > 10_000:
                raise TVMError(ERR_REG_MALFORMED)
            if entry.total_power <= 0:
                raise TVMError(ERR_REG_MALFORMED)
            if entry.count < MIN_SIGNERS:
                raise TVMError(ERR_REG_MALFORMED)
            if entry.epoch > self.current_epoch + 1:
                raise TVMError(ERR_REG_MALFORMED)
            # forward-only rotation: an already-registered epoch is immutable
            # (mid-epoch membership swap via overwrite is closed)
            if entry.epoch in self.epochs:
                raise TVMError(ERR_REG_MALFORMED)
            entry.registered_at = self._now
            self.epochs[entry.epoch] = entry
            if entry.epoch > self.current_epoch:
                self.current_epoch = entry.epoch
        return self._txn(run)

    # ── op 0x08 set_pause ────────────────────────────────────────────────────
    def set_pause(self, sender, paused):
        def run():
            if sender != self.owner:
                raise TVMError(100)
            self.paused = 1 if paused else 0
        return self._txn(run)

    # ── op 0x02 release — THE canonical certificate path (C-01) ──────────────
    # Mirrors escrow.fc exactly: §6 order, same error codes, permissionless.
    def release(self, sender, body: Cell):
        def run():
            # gas: accept_message() — modeled as a no-op (submitter pays)
            if self.paused:
                raise TVMError(ERR_PAUSED)
            b = SliceCursor(body)
            op = b.load_uint(8)
            assert op == 2, "mirror: release() only accepts op 0x02 bodies"
            body_escrow = b.load_uint(256)
            p0 = b.load_ref()
            sig_head = b.load_ref()
            if not b.slice_empty():
                raise TVMError(ERR_CERT_TAIL)

            # §6 1. STRUCTURE — pinned P tree, explicit widths, strict tails
            p = SliceCursor(p0)
            if p.load_uint(104) != TRION_CERT_V1_TAG:
                raise TVMError(ERR_CERT_TAG)
            if p.load_uint(8) != CERT_KIND_RELEASE:
                raise TVMError(ERR_CERT_KIND)
            if p.load_uint(24) > CERT_VERSION_MAX:
                raise TVMError(ERR_CERT_VERSION)
            cert_epoch = p.load_uint(32)
            cert_nonce = p.load_uint(64)
            cert_escrow = p.load_uint(256)
            cert_route = p.load_uint(256)
            p1 = SliceCursor(p.load_ref())
            if not p.slice_empty():
                raise TVMError(ERR_CERT_TAIL)
            p1.load_uint(256)          # intent_hash — bound transitively; no
            entity_id_c = p1.load_uint(256)  # escrow storage to compare yet
            p1.load_uint(32)           # source_chain
            p1.load_uint(32)           # dest_chain
            cert_dest = p1.load_uint(256)
            p2 = SliceCursor(p1.load_ref())
            if not p1.slice_empty():
                raise TVMError(ERR_CERT_TAIL)
            cert_amount = p2.load_uint(256)
            p2.load_uint(256)          # anchor_bh
            p2.load_uint(256)          # execution_bh
            p3 = SliceCursor(p2.load_ref())
            if not p2.slice_empty():
                raise TVMError(ERR_CERT_TAIL)
            coherence = p3.load_uint(64)
            threshold = p3.load_uint(64)
            hhi = p3.load_uint(64)
            total_power = p3.load_uint(64)
            val_count = p3.load_uint(32)
            awa = p3.load_uint(8)
            issued_at = p3.load_uint(64)
            ttl = p3.load_uint(64)
            if not p3.slice_empty():
                raise TVMError(ERR_CERT_TAIL)
            if ttl == 0:
                raise TVMError(ERR_CERT_TTL)

            # §6 2. EPOCH — registry + grace (fail-closed)
            if cert_epoch not in self.epochs:
                raise TVMError(ERR_EPOCH_UNKNOWN)
            entry = self.epochs[cert_epoch]
            if entry.epoch != cert_epoch:
                raise TVMError(ERR_EPOCH_MISMATCH)
            if cert_epoch > self.current_epoch:
                raise TVMError(ERR_EPOCH_STALE)
            if self.current_epoch - cert_epoch > EPOCH_GRACE:
                raise TVMError(ERR_EPOCH_STALE)

            # §6 3. FRESHNESS — now() clock, 60s drift on lower bound only
            if self._now > issued_at + ttl:
                raise TVMError(ERR_CERT_EXPIRED)
            if self._now < issued_at - CLOCK_DRIFT_SECS:
                raise TVMError(ERR_CERT_FUTURE)

            # §6 4. CONSENSUS PRECONDITIONS
            if hhi > HHI_MAX_ACCEPTABLE:
                raise TVMError(ERR_CERT_HHI)
            if awa != 1:
                raise TVMError(ERR_CERT_AWA)
            if coherence < threshold:
                raise TVMError(ERR_CERT_UNSAFE)
            if threshold != entry.threshold:
                raise TVMError(ERR_CERT_THRESHOLD)   # H-03 provenance
            if val_count != entry.count:
                raise TVMError(ERR_CERT_COUNT)
            if total_power != entry.total_power:
                raise TVMError(ERR_CERT_POWER)

            # §6 5. SIGNATURES — batch fail-closed, ascending-distinct,
            # registry membership, claims cross-check, TVM CHKSIGNU digest.
            p_hash = cell_hash(p0)
            signed_power = 0
            sig_count = 0
            last_vid = 0
            sc = SliceCursor(sig_head)
            more = 1
            while more:
                has_next = sc.load_uint(1)
                vid = sc.load_uint(256)
                stake_claim = sc.load_uint(64)
                div_claim = sc.load_uint(64)
                sig = sc.load_bits(512)
                if vid not in entry.validators:
                    raise TVMError(ERR_SIG_UNREGISTERED)
                reg_pub, reg_stake, reg_div, reg_w = entry.validators[vid]
                if stake_claim != reg_stake or div_claim != reg_div:
                    raise TVMError(ERR_SIG_WEIGHT_CLAIM)
                if reg_div > SCALE_1E6:
                    raise TVMError(ERR_SIG_WEIGHT_BAD)
                if reg_w != (reg_stake * reg_div) // SCALE_1E6:
                    raise TVMError(ERR_SIG_WEIGHT_BAD)
                if vid <= last_vid:
                    raise TVMError(ERR_SIG_ORDER)
                last_vid = vid
                try:
                    Ed25519PublicKey.from_public_bytes(
                        reg_pub).verify(int(sig, 2).to_bytes(64, "big"),
                                        p_hash.to_bytes(32, "big"))
                except Exception:
                    raise TVMError(ERR_SIG_BAD)
                signed_power += reg_w
                sig_count += 1
                if has_next:
                    nxt = sc.load_ref()
                    if not sc.slice_empty():
                        raise TVMError(ERR_CERT_TAIL)
                    sc = SliceCursor(nxt)
                else:
                    if not sc.slice_empty():
                        raise TVMError(ERR_CERT_TAIL)
                    more = 0
            if sig_count < MIN_SIGNERS:
                raise TVMError(ERR_SIG_TOO_FEW)

            # §6 6. QUORUM — registered weights, L4.2 tiers
            if not quorum_met(signed_power, entry.total_power, entry.d_consensus):
                raise TVMError(ERR_QUORUM)

            # §6 7. BINDING — this escrow's exact settlement tuple
            if body_escrow not in self.escrows:
                raise TVMError(ERR_ESCROW_NOT_FOUND)
            rec = self.escrows[body_escrow]
            if cert_escrow != body_escrow or cert_escrow != rec.escrow_id:
                raise TVMError(ERR_BIND_ESCROW)
            if cert_route != rec.route_id:
                raise TVMError(ERR_BIND_ROUTE)
            if entity_id_c != rec.entity_id:
                raise TVMError(ERR_BIND_ENTITY)
            if not dest_matches_canonical(rec.dest_bits, cert_dest):
                raise TVMError(ERR_BIND_DEST)
            if cert_amount != rec.amount:
                raise TVMError(ERR_BIND_AMOUNT)
            if coherence < rec.min_coherence:
                raise TVMError(ERR_COHERENCE_INSUFF)

            # §6 8. NONCE / CONSUMED — (epoch, escrow) scope, idempotent no-op
            if body_escrow in self.consumed:
                c_epoch, c_nonce, c_phash = self.consumed[body_escrow]
                if (c_epoch == cert_epoch and c_nonce == cert_nonce
                        and c_phash == p_hash):
                    return            # idempotent resubmission — no effect
                if c_nonce >= cert_nonce:
                    raise TVMError(ERR_CERT_REPLAY)

            # §6 9. SETTLEMENT
            if rec.state != STATE_HOLDING:
                raise TVMError(ERR_NOT_HOLDING)
            if self._now > rec.lock_ts + rec.timeout_secs:
                raise TVMError(ERR_EXPIRED)

            # CEI — state + consumed BEFORE the external send; the record
            # RETAINS the settlement tuple (state is the spent marker —
            # §8.2 idempotency must be able to pass binding after release)
            rec.state = STATE_RELEASED
            rec.settled_at = self._now
            self.consumed[body_escrow] = (cert_epoch, cert_nonce, p_hash)
            self.vault_balance -= rec.amount
            account = int(rec.dest_bits[11:267], 2)
            if account in self.dead_destinations:
                # bounceable payout failed — value returns to the VAULT
                self.vault_balance += rec.amount
            else:
                self.dest_balances[account] = (self.dest_balances.get(account, 0)
                                               + rec.amount)
        return self._txn(run)


# ═════════════════════════════════════════════════════════════════════════════
# 4. Fixture: real canonical certificate + epoch set from the reference encoder
# ═════════════════════════════════════════════════════════════════════════════

def _sha3(s: str) -> bytes:
    return hashlib.sha3_256(s.encode()).digest()


def make_fixture(n_validators=5, epoch=0, tier="t1", dest_seed="dest-1"):
    """Builds a fully consistent world: keys, epoch set, escrow, certificate,
    envelope — using core/consensus/certificate.py objects as the truth."""
    keys = [Ed25519PrivateKey.generate() for _ in range(n_validators)]
    vids = [_sha3(f"validator-{i}") for i in range(n_validators)]
    # tier t1: D=0.70 (2/3 strict); t2: D=0.50 (0.75); t3: D=0.30 (0.85)
    d_val = {"t1": 700_000, "t2": 500_000, "t3": 300_000}[tier]

    entries = [EpochSetEntry(vids[i], stake_weight=3_000_000,
                             diversity_weight=d_val,
                             ed25519_pubkey=keys[i].public_key().public_bytes_raw())
               for i in range(n_validators)]
    eset = EpochSet(epoch, entries)

    escrow_id = _sha3("escrow-J1")
    route_id = _sha3("route-J1")
    destination = _sha3(dest_seed)
    amount = 5_000_000_000  # nanoTON

    cert = CanonicalCertificate(
        validator_epoch=epoch,
        certificate_nonce=1,
        escrow_id=escrow_id,
        route_id=route_id,
        intent_hash=_sha3("intent-J1"),
        entity_id=_sha3("entity-J1"),
        source_chain=1,
        dest_chain=22000,          # TON mainnet, TRION registry id
        destination=destination,
        amount=amount,
        anchor_bh=_sha3("anchor-J1"),
        execution_bh=_sha3("execution-J1"),
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


def register_world(m: TVMEscrowMirror, entries, eset, cert, escrow_id, route_id,
                   destination, amount, now=1_700_000_200, tier="t1",
                   dest_seed="dest-1", min_coherence=600_000, timeout=3600):
    d_val = {"t1": 700_000, "t2": 500_000, "t3": 300_000}[tier]
    validators = {int.from_bytes(e.validator_id, "big"): (
        e.ed25519_pubkey, e.stake_weight, e.diversity_weight,
        (e.stake_weight * e.diversity_weight) // 1_000_000) for e in entries}
    entry = EpochEntry(cert.validator_epoch, d_val, cert.threshold, 1_200,
                       eset.total_effective_power(), len(entries), validators)
    m.register_epoch("owner", entry)
    m.lock("relayer", amount, int.from_bytes(escrow_id, "big"),
           int.from_bytes(route_id, "big"), min_coherence, timeout,
           int.from_bytes(_sha3("entity-J1"), "big"),
           dest_addr_bits(int.from_bytes(destination, "big")))
    m._now = now
    return entry


def sign_all(keys, vids, entries, payload_digest: bytes):
    """Sorted ascending by validator_id (the V3 discipline the contract
    enforces); each signs BE32(cell_hash(P0)) — the TVM family-2 digest."""
    order = sorted(range(len(vids)), key=lambda i: vids[i])
    sigs = []
    for i in order:
        sig = keys[i].sign(payload_digest)
        e = entries[i]
        sigs.append((vids[i], e.stake_weight, e.diversity_weight, sig))
    return sigs


def make_envelope(cert, keys, vids, entries, signers=None):
    p_tree = build_p_tree(cert.encode_payload())
    p_hash = cell_hash(p_tree[0])
    all_sigs = sign_all(keys, vids, entries, p_hash.to_bytes(32, "big"))
    if signers is not None:
        by_vid = {s[0]: s for s in all_sigs}
        all_sigs = [by_vid[v] for v in sorted(signers)]
    chain = build_sig_chain(all_sigs)
    body = build_release_body(cert.escrow_id, p_tree, chain)
    return body, p_hash, p_tree


# ═════════════════════════════════════════════════════════════════════════════
# 5. Attack matrix
# ═════════════════════════════════════════════════════════════════════════════

def fresh_world(tier="t1", n_validators=5, dest_seed="dest-1", epoch=0):
    fx = make_fixture(n_validators=n_validators, epoch=epoch, tier=tier,
                      dest_seed=dest_seed)
    keys, vids, entries, eset, cert, escrow_id, route_id, dest, amount = fx
    m = TVMEscrowMirror()
    register_world(m, entries, eset, cert, escrow_id, route_id, dest, amount,
                   tier=tier, dest_seed=dest_seed)
    return m, fx


def test_valid_release_passes():
    print("\n1) valid canonical certificate releases (the happy path)")
    m, (keys, vids, entries, eset, cert, escrow_id, route_id, dest, amount) = fresh_world()
    body, p_hash, _ = make_envelope(cert, keys, vids, entries)
    account = int.from_bytes(dest, "big")

    # the PINNED P tree is bit-exact the 346-byte canonical payload
    check("P-tree data bits == canonical 346-byte payload (pinned layout)",
          p_tree_bits_roundtrip(cert.encode_payload()) ==
          format(int.from_bytes(cert.encode_payload(), "big"), "02768b"))
    check("reference certificate_hash is SHA3-256(P) (cross-VM id)",
          cert.certificate_hash() == hashlib.sha3_256(cert.encode_payload()).digest())

    # permissionless: a NOBODY submits — sender is only a transport
    err = m.release("total-stranger", body)
    check("release by a non-owner/non-relayer SUCCEEDS (sender is transport only)",
          err is None, f"err={err}")
    check("escrow state RELEASED", m.escrows[int.from_bytes(escrow_id, 'big')].state == STATE_RELEASED)
    check("funds moved to the certificate's canonical destination",
          m.dest_balances.get(account) == amount)
    check("vault balance drained by exactly the escrow amount", m.vault_balance == 0)
    check("consumed registry recorded (epoch, nonce, phash)",
          m.consumed.get(int.from_bytes(escrow_id, 'big')) ==
          (cert.validator_epoch, cert.certificate_nonce, p_hash))


def test_old_vuln_caller_coherence_regressions():
    print("\n2) C-01 regression — caller-supplied coherence no longer exists")
    m, (keys, vids, entries, eset, cert, escrow_id, route_id, dest, amount) = fresh_world()
    eid_int = int.from_bytes(escrow_id, "big")
    # the OLD op-0x02 body: op, escrow_id, execution_bh, coherence — NO refs
    old_body = (Builder().uint(0x02, 8)
                .bytes_(escrow_id, 32)
                .bytes_(_sha3("fake-exec-bh"), 32)
                .uint(1_000_000, 64)   # caller claims max coherence
                .end())
    err = m.release("relayer", old_body)
    check("OLD release body (coherence in message, no envelope) rejected — underflow",
          err == 9, f"err={err}")
    check("no settlement on old-style body",
          m.escrows[eid_int].state == STATE_HOLDING and m.vault_balance == amount)

    # coherence field present but envelope refs garbage
    bad = (Builder().uint(0x02, 8).bytes_(escrow_id, 32).uint(1_000_000, 64).end())
    err = m.release("owner", bad)
    check("coherence + no refs rejected", err == 9, f"err={err}")

    # relayer cannot release even with the OLD authority assumption:
    # a *valid* envelope is required; check the relayer gets no shortcut
    body, _, _ = make_envelope(cert, keys, vids, entries)
    err = m.release("relayer", body)
    check("relayer-submitted VALID envelope still works (transport, not authority)",
          err is None, f"err={err}")


def test_signature_attacks():
    print("\n3) signature-set attacks (unregistered, bad sig, claims, order)")
    m, (keys, vids, entries, eset, cert, escrow_id, route_id, dest, amount) = fresh_world()
    eid_int = int.from_bytes(escrow_id, "big")

    # unregistered signer: swap one validator_id for an unknown one
    p_tree = build_p_tree(cert.encode_payload())
    p_hash = cell_hash(p_tree[0]).to_bytes(32, "big")
    sigs = sign_all(keys, vids, entries, p_hash)
    rogue_id = _sha3("rogue-validator")
    replaced = list(sigs)
    rogue_entry = (rogue_id, replaced[0][1], replaced[0][2], replaced[0][3])
    replaced[0] = rogue_entry
    chain = build_sig_chain(replaced)
    err = m.release("x", build_release_body(escrow_id, p_tree, chain))
    check("unregistered signer rejected (ERR_SIG_UNREGISTERED)",
          err == ERR_SIG_UNREGISTERED, f"err={err}")
    check("no settlement on unregistered signer",
          m.escrows[eid_int].state == STATE_HOLDING)

    # forged signature: flip bytes in one signature
    forged = list(sigs)
    vid, st, dv, sig = forged[0]
    forged[0] = (vid, st, dv, bytes([sig[0] ^ 0xFF]) + sig[1:])
    chain = build_sig_chain(forged)
    err = m.release("x", build_release_body(escrow_id, p_tree, chain))
    check("bad Ed25519 signature rejected (ERR_SIG_BAD, batch fail-closed)",
          err == ERR_SIG_BAD, f"err={err}")

    # weight claim mismatch: envelope claims differ from registry
    lied = list(sigs)
    vid, st, dv, sig = lied[0]
    lied[0] = (vid, st + 1, dv, sig)
    chain = build_sig_chain(lied)
    err = m.release("x", build_release_body(escrow_id, p_tree, chain))
    check("self-reported weight claim mismatch rejected (ERR_SIG_WEIGHT_CLAIM)",
          err == ERR_SIG_WEIGHT_CLAIM, f"err={err}")

    # unsorted / duplicate signers
    dup = [sigs[0], sigs[0], sigs[1], sigs[2]]
    chain = build_sig_chain(dup)
    err = m.release("x", build_release_body(escrow_id, p_tree, chain))
    check("duplicate signer (padding is not consensus) rejected (ERR_SIG_ORDER)",
          err == ERR_SIG_ORDER, f"err={err}")
    unsorted = [sigs[1], sigs[0], sigs[2], sigs[3]]
    chain = build_sig_chain(unsorted)
    err = m.release("x", build_release_body(escrow_id, p_tree, chain))
    check("unsorted signer batch rejected (ERR_SIG_ORDER)", err == ERR_SIG_ORDER, f"err={err}")

    # too few signers (liveness floor)
    chain = build_sig_chain(sigs[:2])
    err = m.release("x", build_release_body(escrow_id, p_tree, chain))
    check("fewer than 3 signers rejected (ERR_SIG_TOO_FEW)",
          err == ERR_SIG_TOO_FEW, f"err={err}")

    # a different payload signed by the SAME quorum must NOT verify:
    # family-2 TVM digest binds the exact 346 canonical bytes
    cert2 = copy.copy(cert)
    cert2.amount = amount + 1
    p_tree2 = build_p_tree(cert2.encode_payload())
    # sign the tampered payload with the real keys
    sigs2 = sign_all(keys, vids, entries, cell_hash(p_tree2[0]).to_bytes(32, "big"))
    chain2 = build_sig_chain(sigs2)
    # but submit it against a P tree built from the ORIGINAL cert payload
    # (signature-verification binding: sigs over P' must not release P)
    mixed = build_sig_chain(sigs2)
    err = m.release("x", build_release_body(escrow_id, p_tree, mixed))
    check("signatures over a DIFFERENT payload rejected (ERR_SIG_BAD)",
          err == ERR_SIG_BAD, f"err={err}")


def test_quorum_attacks():
    print("\n4) weight-quorum attacks (L4.2 tiers, registered weights only)")
    # tier 1 (D=0.70): 2/3 STRICT — exactly-2/3 must fail
    m, (keys, vids, entries, eset, cert, escrow_id, route_id, dest, amount) = fresh_world()
    p_tree = build_p_tree(cert.encode_payload())
    p_hash = cell_hash(p_tree[0]).to_bytes(32, "big")
    sigs = sign_all(keys, vids, entries, p_hash)
    # exactly 2/3: 4 of 6 equal-power validators... our set is 5 equal —
    # craft 2/3 exactly via a 6-validator set
    fx6 = make_fixture(n_validators=6)
    k6, v6, e6, es6, c6, _, _, _, _ = fx6
    m6 = TVMEscrowMirror()
    register_world(m6, e6, es6, c6, c6.escrow_id, c6.route_id, c6.destination, c6.amount)
    p6 = build_p_tree(c6.encode_payload())
    sigs6 = sign_all(k6, v6, e6, cell_hash(p6[0]).to_bytes(32, "big"))
    # 4 of 6 equal weights = exactly 2/3 → STRICT fail
    by_vid = {s[0]: s for s in sigs6}
    four = [by_vid[v] for v in sorted(by_vid)[:4]]
    chain = build_sig_chain(four)
    err = m6.release("x", build_release_body(c6.escrow_id, p6, chain))
    check("tier1: exactly-2/3 weight is NOT a quorum (strict >)",
          err == ERR_QUORUM, f"err={err}")
    five = [by_vid[v] for v in sorted(by_vid)[:5]]
    chain = build_sig_chain(five)
    err = m6.release("x", build_release_body(c6.escrow_id, p6, chain))
    check("tier1: 5/6 weight IS a quorum → settles", err is None, f"err={err}")

    # tier 3 (D=0.30 → 0.85 bar): 4/6 (0.667) must fail
    fx3 = make_fixture(n_validators=6, tier="t3")
    k3, v3, e3, es3, c3, _, _, _, _ = fx3
    m3 = TVMEscrowMirror()
    register_world(m3, e3, es3, c3, c3.escrow_id, c3.route_id, c3.destination, c3.amount, tier="t3")
    p3t = build_p_tree(c3.encode_payload())
    sigs3 = sign_all(k3, v3, e3, cell_hash(p3t[0]).to_bytes(32, "big"))
    by_vid = {s[0]: s for s in sigs3}
    four = [by_vid[v] for v in sorted(by_vid)[:4]]
    chain = build_sig_chain(four)
    err = m3.release("x", build_release_body(c3.escrow_id, p3t, chain))
    check("tier3 (D<0.40): 2/3 weight FAILS the 0.85 bar (ERR_QUORUM)",
          err == ERR_QUORUM, f"err={err}")
    six = [by_vid[v] for v in sorted(by_vid)[:6]]
    chain = build_sig_chain(six)
    err = m3.release("x", build_release_body(c3.escrow_id, p3t, chain))
    check("tier3: full set signs → quorum met, settles", err is None, f"err={err}")

    # low absolute weight: 3 signers of 5 (0.6) at tier1 fails
    m, (keys, vids, entries, eset, cert, escrow_id, route_id, dest, amount) = fresh_world()
    p_tree = build_p_tree(cert.encode_payload())
    sigs = sign_all(keys, vids, entries, cell_hash(p_tree[0]).to_bytes(32, "big"))
    by_vid = {s[0]: s for s in sigs}
    three = [by_vid[v] for v in sorted(by_vid)[:3]]
    chain = build_sig_chain(three)
    err = m.release("x", build_release_body(escrow_id, p_tree, chain))
    check("tier1: 3/5 weight (0.6 < 2/3) rejected (ERR_QUORUM)",
          err == ERR_QUORUM, f"err={err}")


def test_binding_attacks():
    print("\n5) settlement-tuple binding (escrow substitution closed)")
    m, (keys, vids, entries, eset, cert, escrow_id, route_id, dest, amount) = fresh_world()
    eid_int = int.from_bytes(escrow_id, "big")
    base = cert.encode_payload()

    def mutated_cert(**kw):
        c = copy.copy(cert)
        for k, v in kw.items():
            setattr(c, k, v)
        return c

    def attempt(c, signers=None):
        tree = build_p_tree(c.encode_payload())
        sigs = sign_all(keys, vids, entries, cell_hash(tree[0]).to_bytes(32, "big"))
        if signers is not None:
            by_vid = {s[0]: s for s in sigs}
            sigs = [by_vid[v] for v in sorted(signers)]
        chain = build_sig_chain(sigs)
        return m.release("x", build_release_body(escrow_id, tree, chain))

    # the signature check passes (quorum signed the mutated P) — the BINDING
    # check must reject: this proves binding is independent of signatures
    check("amount mismatch rejected (ERR_BIND_AMOUNT)",
          attempt(mutated_cert(amount=amount + 1)) == ERR_BIND_AMOUNT)
    check("destination mismatch rejected (ERR_BIND_DEST)",
          attempt(mutated_cert(destination=_sha3("other-dest"))) == ERR_BIND_DEST)
    check("entity mismatch rejected (ERR_BIND_ENTITY)",
          attempt(mutated_cert(entity_id=_sha3("other-entity"))) == ERR_BIND_ENTITY)
    check("route mismatch rejected (ERR_BIND_ROUTE)",
          attempt(mutated_cert(route_id=_sha3("other-route"))) == ERR_BIND_ROUTE)
    check("escrow_id mismatch (foreign escrow cert) rejected (ERR_BIND_ESCROW)",
          attempt(mutated_cert(escrow_id=_sha3("other-escrow"))) == ERR_BIND_ESCROW)
    check("no settlement happened during binding attacks",
          m.escrows[eid_int].state == STATE_HOLDING and m.vault_balance == amount)

    # body escrow_id vs P escrow_id disagreement: body points at a REAL
    # second escrow, P is bound to the first — the spoof direction that
    # must hit the BINDING check (not just a lookup miss)
    mB, fxB = fresh_world()
    eidB = int.from_bytes(_sha3("escrow-B"), "big")
    mB.lock("relayer", amount, eidB, int.from_bytes(_sha3("route-B"), "big"),
            600_000, 3600, int.from_bytes(_sha3("entity-B"), "big"),
            dest_addr_bits(int.from_bytes(_sha3("other-dest-B"), "big")))
    treeB = build_p_tree(cert.encode_payload())
    sigsB = sign_all(fxB[0], fxB[1], fxB[2], cell_hash(treeB[0]).to_bytes(32, "big"))
    wrong_body = build_release_body(_sha3("escrow-B"), treeB, build_sig_chain(sigsB))
    check("body escrow_id ≠ P escrow_id rejected (ERR_BIND_ESCROW)",
          mB.release("x", wrong_body) == ERR_BIND_ESCROW)
    check("escrow B untouched by the spoof attempt",
          mB.escrows[eidB].state == STATE_HOLDING and mB.vault_balance == 2 * amount)

    # escrow's own min_coherence floor (INV-003)
    m2, fx2 = fresh_world()
    m2.escrows[int.from_bytes(fx2[4].escrow_id, "big")].min_coherence = 900_000
    body, _, _ = make_envelope(fx2[4], fx2[0], fx2[1], fx2[2])
    check("escrow min_coherence floor above cert coherence rejected (124)",
          m2.release("x", body) == ERR_COHERENCE_INSUFF)


def test_freshness_and_preconditions():
    print("\n6) freshness + consensus preconditions (HHI/AWA/count/power)")
    m, (keys, vids, entries, eset, cert, escrow_id, route_id, dest, amount) = fresh_world()

    def attempt(c, now=None):
        mm, fx = fresh_world()
        if now is not None:
            mm._now = now
        tree = build_p_tree(c.encode_payload())
        sigs = sign_all(fx[0], fx[1], fx[2], cell_hash(tree[0]).to_bytes(32, "big"))
        chain = build_sig_chain(sigs)
        return mm.release("x", build_release_body(c.escrow_id, tree, chain))

    c = copy.copy(cert)
    check("expired certificate rejected (ERR_CERT_EXPIRED)",
          attempt(c, now=c.issued_at + c.ttl + 1) == ERR_CERT_EXPIRED)
    # boundary: exactly issued_at+ttl still valid (escrow timeout extended
    # so the freshness boundary is what is under test)
    mb, fxb = fresh_world()
    mb.escrows[int.from_bytes(fxb[4].escrow_id, "big")].timeout_secs = c.ttl * 2
    mb._now = c.issued_at + c.ttl
    bodyb, _, _ = make_envelope(fxb[4], fxb[0], fxb[1], fxb[2])
    check("boundary: exactly issued_at+ttl still valid",
          mb.release("x", bodyb) is None)
    check("far-future certificate rejected (ERR_CERT_FUTURE)",
          attempt(c, now=c.issued_at - CLOCK_DRIFT_SECS - 1) == ERR_CERT_FUTURE)
    check("drift tolerance: 59s future-dated accepted (lower bound only)",
          attempt(c, now=c.issued_at - 59) is None)

    check("ttl=0 rejected (ERR_CERT_TTL)", attempt(mut(cert, ttl=0)) == ERR_CERT_TTL)
    check("hhi>4000 rejected (ERR_CERT_HHI)",
          attempt(mut(cert, hhi_at_emission=4001)) == ERR_CERT_HHI)
    check("awa=0 rejected (ERR_CERT_AWA)",
          attempt(mut(cert, awa_enforced=False)) == ERR_CERT_AWA)
    check("coherence<threshold rejected (ERR_CERT_UNSAFE)",
          attempt(mut(cert, threshold=830_000)) == ERR_CERT_UNSAFE)
    # H-03 threshold provenance: a quorum SIGNED a lowered bar (540_000 <
    # the registered Θ(t) 550_000) — signatures pass, isSafe passes, the
    # REGISTRY equality still rejects: the bar is canonical state, never
    # the signed claim alone.
    check("signed-but-lowered threshold ≠ registered Θ(t) rejected (ERR_CERT_THRESHOLD, H-03)",
          attempt(mut(cert, threshold=540_000)) == ERR_CERT_THRESHOLD)
    check("validator_count lie rejected (ERR_CERT_COUNT)",
          attempt(mut(cert, validator_count=4)) == ERR_CERT_COUNT)
    check("total_effective_power lie rejected (ERR_CERT_POWER)",
          attempt(mut(cert, total_effective_power=cert.total_effective_power + 1))
          == ERR_CERT_POWER)
    check("bad domain tag rejected (ERR_CERT_TAG — cross-protocol theft)",
          _tag_attack(cert) == ERR_CERT_TAG)
    check("unknown certificate_kind rejected (ERR_CERT_KIND)",
          attempt(mut(cert, certificate_kind=2)) == ERR_CERT_KIND)
    check("future protocol_version rejected (ERR_CERT_VERSION)",
          attempt(mut(cert, protocol_version=0x020000)) == ERR_CERT_VERSION)


def mut(cert, **kw):
    c = copy.copy(cert)
    for k, v in kw.items():
        setattr(c, k, v)
    return c


def _tag_attack(cert):
    m, fx = fresh_world()
    payload = bytearray(cert.encode_payload())
    payload[0] ^= 0x01  # corrupt the domain tag
    tree = build_p_tree(bytes(payload))
    sigs = sign_all(fx[0], fx[1], fx[2], cell_hash(tree[0]).to_bytes(32, "big"))
    chain = build_sig_chain(sigs)
    return m.release("x", build_release_body(cert.escrow_id, tree, chain))


def test_epoch_and_replay_attacks():
    print("\n7) epoch binding + replay/double-release/nonces")
    m, (keys, vids, entries, eset, cert, escrow_id, route_id, dest, amount) = fresh_world()
    eid_int = int.from_bytes(escrow_id, "big")
    body, p_hash, _ = make_envelope(cert, keys, vids, entries)

    # unknown epoch
    m1, fx1 = fresh_world(epoch=0)
    c = copy.copy(fx1[4])
    c.validator_epoch = 99
    c.certificate_nonce = 5
    tree = build_p_tree(c.encode_payload())
    sigs = sign_all(fx1[0], fx1[1], fx1[2], cell_hash(tree[0]).to_bytes(32, "big"))
    chain = build_sig_chain(sigs)
    check("unregistered (future) epoch rejected (ERR_EPOCH_UNKNOWN)",
          m1.release("x", build_release_body(c.escrow_id, tree, chain)) == ERR_EPOCH_UNKNOWN)

    # stale beyond grace: cert epoch 0, then rotate 1..3 — 3-0 > grace 2
    m2, fx2 = fresh_world(epoch=0)
    entries2 = fx2[2]
    def reg(mm, ep):
        mm.register_epoch("owner", EpochEntry(
            ep, 700_000, fx2[4].threshold, 1200, fx2[3].total_effective_power(), 5,
            {int.from_bytes(e.validator_id, "big"): (
                e.ed25519_pubkey, e.stake_weight, e.diversity_weight,
                (e.stake_weight * e.diversity_weight) // 1_000_000)
             for e in entries2}))
    for ep in (1, 2, 3):
        reg(m2, ep)
    body2, _, _ = make_envelope(fx2[4], fx2[0], fx2[1], fx2[2])
    check("epoch older than grace (0 vs current 3, grace 2) rejected (ERR_EPOCH_STALE)",
          m2.release("x", body2) == ERR_EPOCH_STALE)

    # within grace still works
    m3, fx3 = fresh_world(epoch=0)
    def reg3(mm, ep):
        mm.register_epoch("owner", EpochEntry(
            ep, 700_000, fx3[4].threshold, 1200, fx3[3].total_effective_power(), 5,
            {int.from_bytes(e.validator_id, "big"): (
                e.ed25519_pubkey, e.stake_weight, e.diversity_weight,
                (e.stake_weight * e.diversity_weight) // 1_000_000)
             for e in fx3[2]}))
    for ep in (1, 2):
        reg3(m3, ep)
    body3, _, _ = make_envelope(fx3[4], fx3[0], fx3[1], fx3[2])
    check("epoch within grace (0 vs current 2) still verifies",
          m3.release("x", body3) is None)

    # replay: exact resubmission is an idempotent no-op (§8.2)
    err = m.release("x", body)
    check("first release settles", err is None, f"err={err}")
    vault_after = m.vault_balance
    dest_paid = m.dest_balances.get(int.from_bytes(dest, "big"))
    err = m.release("x", body)
    check("exact certificate resubmission is an idempotent NO-OP",
          err is None, f"err={err}")
    check("no double payment on resubmission",
          m.vault_balance == vault_after and
          m.dest_balances.get(int.from_bytes(dest, "big")) == dest_paid)

    # older nonce after consumption
    old = mut(cert, certificate_nonce=0)
    tree = build_p_tree(old.encode_payload())
    sigs = sign_all(keys, vids, entries, cell_hash(tree[0]).to_bytes(32, "big"))
    chain = build_sig_chain(sigs)
    check("lower-nonce certificate rejected (ERR_CERT_REPLAY)",
          m.release("x", build_release_body(escrow_id, tree, chain)) == ERR_CERT_REPLAY)

    # same nonce, different payload → conflict (equivocation evidence class).
    # The conflicting cert keeps the settlement tuple identical (so it
    # reaches step 8) and differs in an unbound field (anchor_bh).
    conflict = mut(cert, certificate_nonce=1, anchor_bh=_sha3("conflicting-anchor"))
    tree = build_p_tree(conflict.encode_payload())
    sigs = sign_all(keys, vids, entries, cell_hash(tree[0]).to_bytes(32, "big"))
    chain = build_sig_chain(sigs)
    check("same-nonce different-payload rejected (ERR_CERT_REPLAY — on-chain conflict)",
          m.release("x", build_release_body(escrow_id, tree, chain)) == ERR_CERT_REPLAY)

    # higher nonce on a RELEASED escrow → double-release blocked by state
    higher = mut(cert, certificate_nonce=2)
    tree = build_p_tree(higher.encode_payload())
    sigs = sign_all(keys, vids, entries, cell_hash(tree[0]).to_bytes(32, "big"))
    chain = build_sig_chain(sigs)
    check("fresh higher-nonce cert cannot double-release (ERR_NOT_HOLDING)",
          m.release("x", build_release_body(escrow_id, tree, chain)) == ERR_NOT_HOLDING)
    check("vault still drained exactly once",
          m.vault_balance == 0 and m.dest_balances.get(int.from_bytes(dest, "big")) == amount)

    # timeout: certificate valid but escrow past timeout (INV-004)
    m4, fx4 = fresh_world()
    m4._now = m4.escrows[int.from_bytes(fx4[4].escrow_id, "big")].lock_ts + 3601
    body4, _, _ = make_envelope(fx4[4], fx4[0], fx4[1], fx4[2])
    check("release after escrow timeout rejected (ERR_EXPIRED=123)",
          m4.release("x", body4) == ERR_EXPIRED)


def test_pause_and_admin():
    print("\n8) pause, registration validation, strict ops")
    m, (keys, vids, entries, eset, cert, escrow_id, route_id, dest, amount) = fresh_world()
    m.set_pause("owner", True)
    body, _, _ = make_envelope(cert, keys, vids, entries)
    check("paused contract rejects release (ERR_PAUSED)", m.release("x", body) == ERR_PAUSED)
    check("pause does not eat funds", m.vault_balance == amount)
    m.set_pause("owner", False)
    check("unpause restores release", m.release("x", body) is None)

    # registration validation
    bad = EpochEntry(11, 700_000, 550_000, 1200, 1, 5, {})
    check("registration with total_power=0 rejected (ERR_REG_MALFORMED)",
          m.register_epoch("owner", bad) == ERR_REG_MALFORMED)
    bad = EpochEntry(11, 700_000, 550_000, 1200, 100, 2, {})
    check("registration with <3 validators rejected (ERR_REG_MALFORMED)",
          m.register_epoch("owner", bad) == ERR_REG_MALFORMED)
    bad = EpochEntry(11, 700_000, 1_000_001, 1200, 100, 5, {})
    check("registration with Θ(t)>1e6 rejected (ERR_REG_MALFORMED, H-03 range)",
          m.register_epoch("owner", bad) == ERR_REG_MALFORMED)
    # epoch skipping: current=0, jumping straight to 99 is a registrar grief
    # guard (stale-ing all live certs in one tx)
    bad = EpochEntry(99, 700_000, 550_000, 1200, 100, 5, {})
    check("registration skipping epochs rejected (ERR_REG_MALFORMED)",
          m.register_epoch("owner", bad) == ERR_REG_MALFORMED)
    bad = EpochEntry(1, 700_000, 550_000, 1200, 100, 5, {})
    check("non-owner cannot register epochs (100)",
          m.register_epoch("relayer", bad) == 100)

    # forward-only rotation: overwriting the LIVE epoch's set is rejected
    # — a compromised registrar cannot swap in-grace membership mid-epoch
    m5, fx5 = fresh_world()
    live_epoch = m5.current_epoch         # the epoch the fixture registered
    rogue_keys = [Ed25519PrivateKey.generate() for _ in range(3)]
    rogue = EpochEntry(live_epoch, 700_000, 550_000, 1200, 3, 3,
                       {int.from_bytes(_sha3(f"rogue-{i}"), "big"): (
                           rogue_keys[i].public_key().public_bytes_raw(),
                           1_000_000, 700_000, 700_000) for i in range(3)})
    check("re-registration of a live epoch rejected (ERR_REG_MALFORMED)",
          m5.register_epoch("owner", rogue) == ERR_REG_MALFORMED)
    check("the live epoch's set is UNTOUCHED by the failed overwrite",
          live_epoch in m5.epochs and len(m5.epochs[live_epoch].validators) == 5
          and m5.current_epoch == live_epoch)
    body5, _, _ = make_envelope(fx5[4], fx5[0], fx5[1], fx5[2])
    check("certificates of the untouched live epoch still verify",
          m5.release("x", body5) is None)


def test_atomicity_and_bounce_safety():
    print("\n9) atomicity + bounced-message fund safety")
    m, (keys, vids, entries, eset, cert, escrow_id, route_id, dest, amount) = fresh_world()
    eid_int = int.from_bytes(escrow_id, "big")
    # failing release: signature over a different payload
    tampered = mut(cert, amount=amount + 7)
    tree = build_p_tree(tampered.encode_payload())
    sigs = sign_all(keys, vids, entries, cell_hash(tree[0]).to_bytes(32, "big"))
    chain = build_sig_chain(sigs)
    snap = (m.vault_balance, m.escrows[eid_int].state,
            m.consumed.get(eid_int), dict(m.dest_balances))
    err = m.release("x", build_release_body(escrow_id, tree, chain))
    check("failed release throws (ERR_BIND_AMOUNT)", err == ERR_BIND_AMOUNT, f"err={err}")
    check("failed release drains NOTHING (TVM atomic abort)",
          (m.vault_balance, m.escrows[eid_int].state, m.consumed.get(eid_int),
           m.dest_balances) == snap)

    # bounced payout: dead destination — value returns to the VAULT
    m2, fx2 = fresh_world()
    account = int.from_bytes(fx2[7], "big")
    m2.dead_destinations.add(account)
    body, _, _ = make_envelope(fx2[4], fx2[0], fx2[1], fx2[2])
    err = m2.release("x", body)
    check("release to dead destination settles (state RELEASED)", err is None, f"err={err}")
    check("bounced payout value RETAINED by the vault (not eaten)",
          m2.vault_balance == fx2[8] and account not in m2.dest_balances)


# ═════════════════════════════════════════════════════════════════════════════
# 6. Static source assertions — the FunC must contain the checks, in order
# ═════════════════════════════════════════════════════════════════════════════

def _release_block(src: str) -> str:
    start = src.index("if (op == 2) {")
    end = src.index(";; ── 0x03 revert_escrow")
    return src[start:end]


def test_static_source_assertions():
    print("\n10) static source assertions (escrow.fc / oracle.fc / stdlib.fc)")
    escrow = open(os.path.join(REPO, "contracts/ton/escrow.fc")).read()
    oracle = open(os.path.join(REPO, "contracts/ton/oracle.fc")).read()
    stdlib = open(os.path.join(REPO, "contracts/ton/stdlib.fc")).read()
    blk = _release_block(escrow)

    # C-01 core: relayer/owner authorization ELIMINATED from release
    check("release block contains NO is_authorized call (sender ≠ authority)",
          "is_authorized" not in blk)
    check("old caller-coherence release line is gone repo-file-wide",
          "int coherence    = in_msg_body~load_uint(64)" not in escrow)

    # the primitives
    check("stdlib.fc declares check_signature (CHKSIGNU)", 'asm "CHKSIGNU"' in stdlib)
    check("stdlib.fc declares accept_message (ACCEPT)", 'asm "ACCEPT"' in stdlib)
    check("release block accepts gas (accept_message)", "accept_message();" in blk)
    check("release block verifies with check_signature (TVM ed25519)",
          "check_signature(" in blk)

    # §6 order: token positions strictly increasing
    order = ["ERR_CERT_TAG", "ERR_CERT_KIND", "ERR_CERT_VERSION",
             "ERR_EPOCH_UNKNOWN", "ERR_EPOCH_STALE",
             "ERR_CERT_EXPIRED", "ERR_CERT_FUTURE",
             "ERR_CERT_HHI", "ERR_CERT_AWA", "ERR_CERT_UNSAFE",
             "ERR_CERT_THRESHOLD",
             "ERR_CERT_COUNT", "ERR_CERT_POWER",
             "ERR_SIG_UNREGISTERED", "ERR_SIG_WEIGHT_CLAIM", "ERR_SIG_ORDER",
             "ERR_SIG_BAD", "ERR_SIG_TOO_FEW",
             "ERR_QUORUM",
             "ERR_BIND_ESCROW", "ERR_BIND_ROUTE", "ERR_BIND_ENTITY",
             "ERR_BIND_DEST", "ERR_BIND_AMOUNT", "ERR_COHERENCE_INSUFF",
             "ERR_CERT_REPLAY",
             "ERR_NOT_HOLDING", "ERR_EXPIRED",
             "save_storage", "send_ton"]
    pos = [blk.index(tok) for tok in order]
    check("§6 verification order preserved in source (structure→epoch→freshness→"
          "preconditions→sigs→quorum→binding→nonce→settle)",
          all(a < b for a, b in zip(pos, pos[1:])), f"order={list(zip(order, pos))}")

    # canonical constants
    check("EPOCH_GRACE = 2 (ED-G)", "const int EPOCH_GRACE             = 2;" in escrow)
    check("CLOCK_DRIFT_SECS = 60 (§9.1, lower bound only)",
          "const int CLOCK_DRIFT_SECS        = 60;" in escrow)
    check("HHI_MAX_ACCEPTABLE = 4000 (§5.3)", "const int HHI_MAX_ACCEPTABLE      = 4000;" in escrow)
    check("MIN_SIGNERS = 3 (§4 liveness floor)",
          "const int MIN_SIGNERS             = 3;" in escrow)
    check("tier thresholds D=600000/400000 (§5.2)",
          "const int D_CONSENSUS_TIER1       = 600000;" in escrow and
          "const int D_CONSENSUS_TIER2       = 400000;" in escrow)
    check("tier1 uses STRICT 3·signed > 2·total",
          "return 3 * signed_power > 2 * total_power;" in escrow)
    check("tier2 uses 4·signed ≥ 3·total", "return 4 * signed_power >= 3 * total_power;" in escrow)
    check("tier3 uses 20·signed ≥ 17·total", "return 20 * signed_power >= 17 * total_power;" in escrow)

    # H-03: threshold provenance — the epoch entry stores the registered
    # Θ(t) and the release path cross-checks the signed claim against it
    check("epoch entry stores the registered Θ(t) (H-03)",
          ".store_uint(theta,     64)" in escrow)
    check("release cross-checks cert threshold == registered Θ(t) (H-03)",
          "throw_unless(ERR_CERT_THRESHOLD, threshold == r_threshold);" in blk)
    check("registration validates Θ(t) range (≤ 1e6)",
          "throw_unless(ERR_REG_MALFORMED, theta <= SCALE_1E6);" in escrow)

    # strict parsing + storage layout
    check("strict tail checks (slice_empty? on P cells)", "p3.slice_empty?()" in blk)
    check("unknown op throws (fail-closed)", "throw(ERR_UNKNOWN_OP);" in escrow)
    check("epoch registry dict in storage (key_len 32)",
          "epochs_dict~idict_set_ref(32, epoch, entry);" in escrow)
    check("epoch registration is forward-only (no overwrite of live sets)",
          "throw_if(ERR_REG_MALFORMED, already);" in escrow)
    check("consumed registry records (epoch, nonce, phash)",
          ".store_uint(cert_epoch, 32)" in blk and ".store_uint(p_hash, 256)" in blk)
    check("destination binding = basechain account hash (§7 TON)",
          "dest_matches_canonical" in blk)
    check("weight claims cross-checked (§6 5c)",
          "stake_claim == reg_stake" in blk)
    check("registry integrity: w = s·d/1e6 recomputed",
          "reg_w == (reg_stake * reg_div) / SCALE_1E6" in blk)
    check("idempotent resubmission no-op (§8.2)", "idempotent resubmission" in blk)

    # oracle.fc: no-op add_validator killed
    check("oracle.fc add_validator no-op killed", "if (op == 3)" not in oracle)
    check("oracle.fc rejects unknown ops", "throw(ERR_UNKNOWN_OP);" in oracle)

    # cell layout test covers the new pinned layouts
    layout = open(os.path.join(REPO, "contracts/ton/cell_layout.test.js")).read()
    check("cell_layout.test.js pins the canonical P tree",
          "'escrow.fc canonical payload P tree'" in layout)
    check("cell_layout.test.js pins the epoch/validator/consumed cells",
          "'escrow.fc epoch entry'" in layout and
          "'escrow.fc validator cell'" in layout and
          "'escrow.fc consumed cert cell'" in layout)


# ═════════════════════════════════════════════════════════════════════════════
# 7. Reference-encoder parity (golden cross-check)
# ═════════════════════════════════════════════════════════════════════════════

def test_reference_encoder_parity():
    print("\n11) reference encoder parity (payload semantics)")
    fx = make_fixture()
    cert = fx[4]
    p = cert.encode_payload()
    check("payload width is 346 bytes", len(p) == 346)
    check("domain tag is TRION-CERT-V1 at offset 0", p[:13] == b"TRION-CERT-V1")
    check("validator_epoch at byte offset 17 (§2 table)",
          int.from_bytes(p[17:21], "big") == cert.validator_epoch)
    check("certificate_nonce at byte offset 21",
          int.from_bytes(p[21:29], "big") == cert.certificate_nonce)
    check("amount at byte offset 197",
          int.from_bytes(p[197:229], "big") == cert.amount)
    check("ttl at byte offset 338", int.from_bytes(p[338:346], "big") == cert.ttl)
    # the P-tree split is at field boundaries — every cell parses exactly
    tree = build_p_tree(p)
    check("P tree: 4 cells, 744/832/768/424 bits",
          [len(c.bits) for c in tree] == [744, 832, 768, 424])
    check("P tree: single-ref chain P0→P1→P2→P3",
          tree[0].refs == [tree[1]] and tree[1].refs == [tree[2]] and
          tree[2].refs == [tree[3]] and tree[3].refs == [])
    # digest sensitivity: any field change flips the TVM signature digest
    h0 = cell_hash(tree[0])
    fx2 = make_fixture()
    c2 = mut(fx2[4], amount=fx2[4].amount + 1)
    check("cell_hash(P0) is payload-sensitive (amount change flips digest)",
          cell_hash(build_p_tree(c2.encode_payload())[0]) != h0)


ALL_TESTS = [
    test_valid_release_passes,
    test_old_vuln_caller_coherence_regressions,
    test_signature_attacks,
    test_quorum_attacks,
    test_binding_attacks,
    test_freshness_and_preconditions,
    test_epoch_and_replay_attacks,
    test_pause_and_admin,
    test_atomicity_and_bounce_safety,
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
    print("TON escrow C-01: canonical certificate verification verified "
          "(py mirror of the FunC + static source assertions).")


if __name__ == "__main__":
    main()
