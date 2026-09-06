"""
WAVE 5 — FINAL INDEPENDENT RED-TEAM PASS 2 (Agent W5-RED2, master §30)
======================================================================

A COMPLETELY FRESH attack sweep — none of the Wave-4 (Agent P) attack
classes are re-used. Every attack below was RUN against the real
implementation (py-solcx 0.8.24 + eth_tester/py-evm for the Solidity tier,
vyper 0.3.10 + eth_tester for the Vyper tier, live module/Flask calls for
the py/API/storage tiers) before being pinned here.

CONFIRMED EXPLOITS — asserted as strict-xfail "desired behavior" tests with
TODO(W5-lead): when the lead lands the fix, the test XPASSes, strict mode
fails CI, and the marker is flipped to a defense pin (the Wave-4→Wave-5
exploit-fix workflow, inverted so the fix itself is what forces the flip).

  P-EVM-03  HIGH  Dest-chain gate uint32 truncation aliasing: the P-EVM-01
            fix compares CanonicalCertificate.destChainOf(payload) ==
            uint32(block.chainid) (BTCPEscrow.sol:495). The cast TRUNCATES
            a deployment chain id ≥ 2^32 modulo 2^32, so a certificate
            destined for registry chain X settles on ANY deployment whose
            chainid ≡ X (mod 2^32). Verified on a real EVM with the CHAINID
            opcode reporting 4294967297 (uint32 → 1): a chain-1 certificate
            (full valid quorum) settled a 1-ETH escrow there — the exact
            double-pay class P-EVM-01 closed, re-opened for high-id chains
            (py-evm's own default artificial id 131277322940537 is already
            > 2^32; any future/enterprise high-id network aliases every
            registry chain). Fix: compare full-width
            block.chainid == uint256(destChainOf(payload)) — which also
            fails closed for deployments outside the u32 registry space.

  P-VY-01   HIGH  Vyper BTCP_ESCROW.release() has NO block-timeout guard:
            an escrow PAST its lock+timeout_blocks is still releasable with
            a FRESH quorum verdict — the funds go to destination and the
            funder's timeout refund protection is void. INV-004 ("no
            release after timeout" — BTCP_STATE_MACHINE.md R7 lists
            "releasing funds after timeout" as a FORBIDDEN alternative) is
            enforced in the py tier (test_invariants.py INV-004) and in the
            Solidity tier (P-EVM-02 fix's EXPIRED checks), but absent in
            contracts/vyper/BTCP_ESCROW.vy release() (line ~168). Verified
            on real EVM: locked 1 ETH with timeout=3 blocks, mined past
            timeout, submitted a fresh 2-attestation verdict → destination
            paid, funder got nothing. Same damage class as P-EVM-02.
            Fix: require block.number <= lock_block + timeout_blocks in
            release() (parity with the Solidity tier).

  P-API-03  HIGH  Incomplete P-API-02 remediation: the Wave-5 write-path
            set (_WRITE_PATHS, api/app.py:168) covers only publish /
            zg/da/submit / zg/storage/store. The OTHER two GET-registered
            write routes named in the original P-API-02 report remain open:
              /api/v1/zg/sync      (GET+POST) — spawns the 0G MAINNET
                                   storage-sync node process (verified:
                                   unauthenticated GET → 200 + process
                                   spawn while TRION_API_KEY is set);
              /api/v1/zg/compute/infer (GET+POST) — submits an 0G Compute
                                   job with ATTACKER-CONTROLLED entity_id
                                   and prompt (verified: unauthenticated
                                   GET ?id=…&prompt=… → 200 + job args
                                   captured).
            Fix: add both paths to _WRITE_PATHS.

  P-API-04  MED   Rate-limit bypass via X-Forwarded-For spoofing:
            _get_client_ip() (api/app.py:71) returns the FIRST
            client-supplied XFF entry with no trusted-proxy allowlist. An
            attacker rotating a fake XFF per request gets a FRESH rate
            bucket per request (verified: 40 requests, zero 429s, vs 429 at
            request #6 for a fixed IP) — the per-IP limiter is fully
            defeated. Reverse direction also verified: spoofed XFF can FILL
            a victim IP's bucket, 429ing the victim's genuine traffic
            (targeted DoS framing). Fix: key on request.remote_addr unless
            an explicit trusted-proxy config is present (env-gated).

  P-API-05  MED   AWA emission freeze is NOT enforced on the 0G publication
            surfaces: while the protocol-wide EmissionGate is frozen, the
            /api/v1/zg/da/submit and /api/v1/zg/storage/store routes still
            publish ATTACKER-CONTROLLED behavioral-signal data (entity_id,
            coherence_score, arbitrary fields) to 0G mainnet (verified live
            with the frozen singleton: publish → 503 fail-closed, zg DA
            submit → 200 with the attacker blob submitted). MD §17's
            "silence is information / truth publication fails closed" is
            wired only into /api/v1/publish. Fix: assert_emission_allowed
            in the zg write handlers (or a shared pre-write hook).

  P-PY-03   MED   Off-registry chain routes derive VERIFIED settlement
            gates: BTCPOrchestrator.create_route performs NO canonical
            registry membership check — CrossVMGateway.get_vm_type
            defaults unknown ids to EVM and the adapter factory returns a
            default EVM encoding, so a route to chain 999 (off-registry)
            or a fully fabricated id (2^30) is created, persisted, and
            FULLY PROOF-VERIFIED (verified live: verify_route_proofs →
            True; through the API: POST /api/v1/btcp/orchestrate
            dest_chain=999 → POST /api/v1/continuum/settlement →
            btcp_route_verified=True, provenance
            "derived_from_persisted_route_proofs", triggered=True). The
            M2 truth discipline derives the gate from persisted proofs but
            never checks the route's chains exist in
            config/chain_registry.json. Fix: registry membership check in
            create_route (fail-closed error) for both legs.

  P-PY-04   MED   Per-entity intent nonce TOCTOU: the W3-D store-backed
            counter _next_persisted_entity_nonce
            (core/btcp/orchestrator.py:782) does read (load_all) →
            compute (last+1, OUTSIDE _ENTITY_NONCE_LOCK) → save. Two
            concurrent create_route calls with the same entity interleave
            the read and both return the SAME nonce (verified: 8 threads /
            barrier → nonce collision ×3, deterministic with a
            barrier-instrumented load_all). Consequence (verified): the
            second intent's btcp_cross_chain_messages row is SILENTLY
            DROPPED by the (sender, source, target, nonce) UNIQUE index +
            INSERT OR IGNORE — 8 routes → 6 message rows. Spec §4.1
            per-entity monotonicity broken; the replay-prevention log
            loses rows without any error. Fix: hold one lock across
            load+compute+save (or a SQL-side atomic upsert-returning).

  P-PY-05   LOW   AkashicClipboard.execute_paste has no expiry re-check:
            D2's clipboard expiry enforcement covers MATCH
            (find_complement requires `now` and rejects expired intents)
            but phase 3 PASTE (modules.py:933) takes no clock — a matched
            pair whose deadlines BOTH pass before the paste still
            transitions to FILLED (verified live). In-memory matcher tier
            only (no funds, no API surface) — parity/audit-truth note.
            Fix: pass `now` to execute_paste and refuse dead commitments.

PINNED DEFENSES (attack attempted, BLOCKED — asserted so a regression that
reopens the hole fails CI):

  - dest_chain == 0 is rejected at the payload level ("CERT: dest chain
    unbound") — the gate's zero case fails closed.
  - akashic two-window chaining: an escrow with a HUGE block timeout
    (1e6 blocks) flipped into PENDING_AKASHIC is still hard-bounded by the
    24h WALL CLOCK measured from LOCK — both releaseEscrowCanonical and
    releaseFromPendingAkashic refuse past lock+24h even when the block
    timeout is nowhere near; the permissionless akashic-expiry revert then
    refunds the funder. The relayer cannot extend a release lifetime past
    lock+24h by chaining the two windows.
  - G1 settlement-check setter is relayer/owner-only: a third party cannot
    set (or grief with) a settlementCheckHash; it also cannot be set on a
    PENDING_AKASHIC escrow (NOT_HOLDING). (The hash VALUE is an assertion
    by the relayer — never cross-checked at release — documented here as
    an observation, bounded by the relayer trust model.)
  - _lockedBalance accounting is exact across every terminal path: settle
    one + revert one → 0; a cascade CYCLE (A parent B, B parent A) reverts
    both exactly once; a SELF-parent escrow reverts without a phantom
    cascade; sweepETH only ever moves the excess above the live pool — no
    fake "in-flight" state can wedge owner funds after all escrows settle.
  - cross-CONNECTION (two-process model) consume_certificate: two
    independent stores on one DB file hammered from two threads yield
    exactly one CONSUMED and cross-store EQUIVOCATION detection — BEGIN
    IMMEDIATE + busy-timeout serializes the file correctly (W4 pinned the
    in-process race; this pins the cross-process one).
  - rate-limiter core: fixed-IP traffic DOES hit the 429 limit (the bypass
    is the XFF trust, not a broken limiter).
  - the three Wave-5 write-gated paths (publish, zg/da/submit,
    zg/storage/store) still 401 unauthenticated GETs; path-confusion
    variants (missing trailing segment, URL-encoded dots, double slashes)
    fail closed — no write executes unauthenticated.
  - math boundaries: coherence == threshold passes (the ≥ verdict rule),
    HHI exactly 4000 combined with exactly-17/20 tier-3 quorum passes and
    each +1 past the boundary fails; the §9 clock drift widens the
    freshness LOWER bound by exactly 60s (61 rejected); ttl expiry is
    inclusive (now == issued+ttl valid, +1 rejected).
  - Vyper verdict freshness: a future-dated verdict (ts > block.timestamp)
    reverts under Vyper's checked arithmetic — no underflow window.

DOCUMENTED OBSERVATIONS (spec gaps / latent hazards, recorded not pinned
as exploits):
  - a SELF-LOOP certificate (source_chain == dest_chain == deployment
    chain) settles; CANONICAL_CERTIFICATE.md §2/§8 defines both fields but
    never forbids source == dest, and source_chain is not gated anywhere
    (a foreign source_chain settles here fine). Both are quorum-signed
    inputs, so forging them is not an attacker capability — recorded as a
    spec-semantics gap for the lead.
  - certificate_consumption_key components are colon-joined WITHOUT
    escaping: a crafted scope containing a colon can alias a different
    (scope, chain_id) pair. scope/chain_id are internal constants at every
    current call site (no production caller passes attacker data), so this
    is a latent-hazard pin, not a live exploit.

Run: pytest tests/adversarial/test_final_red_team.py -q
"""
import importlib.util as _ilu
import json
import os
import sqlite3
import sys
import tempfile
import threading
import time

import pytest

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(os.path.dirname(HERE))

# ── import the real-EVM harness by file path (repo import-hygiene policy) ───
_spec = _ilu.spec_from_file_location(
    "tests.contracts.sol_helpers",
    os.path.join(ROOT, "tests", "contracts", "sol_helpers.py"))
_sh = _ilu.module_from_spec(_spec)
sys.modules[_spec.name] = _sh
_spec.loader.exec_module(_sh)

# ── EVM classes skip fast when the toolchain is absent; pure-py / API /
# storage / math attacks still run everywhere. ──────────────────────────────
try:
    import solcx  # noqa: F401
    import web3  # noqa: F401
    import eth_tester  # noqa: F401
    _EVM_OK = True
except Exception:  # pragma: no cover — env gap
    _EVM_OK = False

_evm_skip = pytest.mark.skipif(not _EVM_OK, reason="solcx/web3/eth_tester absent")

try:
    import vyper  # noqa: F401
    _VY_OK = True
except Exception:  # pragma: no cover — env gap
    _VY_OK = False

_vy_skip = pytest.mark.skipif(not _VY_OK, reason="vyper absent")


# ════════════════════════════════════════════════════════════════════════════
# Shared real-EVM fixture (chain id 1 — registry space): escrow + registry,
# compiled once per module. Raw artifacts are kept so the high-chainid
# truncation attack can redeploy them on a second harness without a second
# compile.
# ════════════════════════════════════════════════════════════════════════════

@pytest.fixture(scope="module")
def evm():  # pragma: no cover — guarded by _evm_skip on every consumer
    class _Evm:
        pass
    h = _sh.EvmHarness()          # CHAINID opcode pinned to 1
    evm = _Evm()
    evm.h = h
    evm.w3 = h.w3

    esc = h.compile([h.path("BTCPEscrow.sol")], names=["BTCPEscrow"])["BTCPEscrow"]
    reg = h.compile([h.path("TrionEpochRegistry.sol")],
                    names=["TrionEpochRegistry"])["TrionEpochRegistry"]
    evm.esc_art = esc
    evm.reg_art = reg

    evm.registry = h.deploy(*reg)
    evm.escrowA = h.deploy(*esc)
    evm.escrowB = h.deploy(*esc)
    h.tx(evm.escrowA.functions.setEpochRegistry(evm.registry.address))
    h.tx(evm.escrowB.functions.setEpochRegistry(evm.registry.address))

    evm.vals = _sh.make_validators(5)
    return evm


def _sorted_vals(vals):
    return sorted(vals, key=lambda v: int(v["addr"], 16))


def _fresh_epoch(evm):
    h, reg = evm.h, evm.registry
    vals = _sorted_vals(evm.vals)
    epoch = reg.functions.latestEpoch().call() + 1
    h.tx(reg.functions.registerEpoch(
        epoch, [v["addr"] for v in vals], [1_000_000] * 5,
        [800_000] * 5, 800_000, 550_000, 1_200))
    return epoch


def _lock_funded(h, escrow, escrow_id, route_id, entity_id, dest, amount_wei,
                 timeout_blocks=10_000, settle=True):
    txh = escrow.functions.lockEscrow(
        escrow_id, route_id, entity_id, dest, 800_000, timeout_blocks
    ).transact({"from": h.acct, "value": amount_wei, "gas": 5_000_000})
    rcpt = h.w3.eth.wait_for_transaction_receipt(txh)
    assert rcpt["status"] == 1, "lockEscrow failed"
    if settle:
        h.tx(escrow.functions.verifySettlementCheck(
            escrow_id, h.w3.keccak(text="g1-" + escrow_id.hex())))


def _release_args(h, vals, epoch, escrow_id, route_id, entity_id, dest, amount,
                  escrow, **kw):
    """Build a release call for `escrow` — the quorum signs the
    deployment-BOUND digest (SEC-21), so the batch is only valid on that
    escrow contract."""
    kw.setdefault("validator_count", len(vals))
    cert = _sh.make_cert(
        validator_epoch=epoch,
        total_effective_power=4_000_000, threshold=550_000,
        escrow_id=escrow_id, route_id=route_id, entity_id=entity_id,
        destination=b"\x00" * 12 + bytes.fromhex(dest[2:]),
        amount=amount, issued_at=h.now(), **kw)
    stakes = {v["addr"]: 1_000_000 for v in vals}
    divs = {v["addr"]: 800_000 for v in vals}
    sigs, st, dv, _ = _sh.sign_cert_with_weights(
        h, cert, vals, stakes, divs, escrow_address=escrow.address)
    env = []
    for s, d in zip(st, dv):
        env.extend((s, d))
    return env, b"".join(sigs), cert.encode_payload()


# ════════════════════════════════════════════════════════════════════════════
# 1. THE DEST-CHAIN GATE, FRESH ANGLES (P-EVM-03 + semantics)
# ════════════════════════════════════════════════════════════════════════════

@_evm_skip
class TestDestChainGateFreshAngles:

    def _deploy_on_chainid(self, evm, chain_id):
        """Second harness whose CHAINID opcode reports `chain_id` (>= 2^32).

        eth_tester's chain class is shared across harnesses, so the class
        attribute is restored afterwards to keep the module fixture intact.
        """
        h = evm.h
        saved = _sh.EvmHarness.TEST_CHAIN_ID
        _sh.EvmHarness.TEST_CHAIN_ID = chain_id
        try:
            h2 = _sh.EvmHarness()
            escrow2 = h2.deploy(*evm.esc_art)
            registry2 = h2.deploy(*evm.reg_art)
            h2.tx(escrow2.functions.setEpochRegistry(registry2.address))
            return h2, escrow2, registry2
        finally:
            _sh.EvmHarness.TEST_CHAIN_ID = saved
            # restore the shared chain class id for the module fixture
            type(h.t.backend.chain).chain_id = saved

    # FIXED (Wave 5, lead) — the exploit is closed; the test below now
    # asserts the DEFENSE, not the vulnerability.
    def test_high_chainid_truncation_aliases_registry_chain(self, evm):
        """Desired behavior: a certificate DESTINED FOR REGISTRY CHAIN 1
        must be rejected on a deployment whose chainid is 2^32+1 — that
        deployment is NOT chain 1, truncated comparison or not."""
        h2, escrow2, registry2 = self._deploy_on_chainid(evm, 2**32 + 1)
        vals = _sorted_vals(evm.vals)
        epoch = registry2.functions.latestEpoch().call() + 1
        h2.tx(registry2.functions.registerEpoch(
            epoch, [v["addr"] for v in vals], [1_000_000] * 5,
            [800_000] * 5, 800_000, 550_000, 1_200))
        route_id = h2.w3.keccak(text="route-trunc")
        entity_id = h2.w3.keccak(text="entity-trunc")
        amount = h2.w3.to_wei(1, "ether")
        escrow_id = h2.w3.keccak(text="w5r2-trunc")
        _lock_funded(h2, escrow2, escrow_id, route_id, entity_id,
                     h2.dest, amount)

        # the certificate is destined for registry chain 1 — NOT this
        # chainid=2^32+1 deployment (its truncated u32 view aliases to 1)
        env, sigs, payload = _release_args(
            h2, vals, epoch, escrow_id, route_id, entity_id, h2.dest, amount,
            escrow2, source_chain=137, dest_chain=1)
        dest_before = h2.balance(h2.dest)
        assert h2.must_revert(
            escrow2.functions.releaseEscrowCanonical(payload, env, sigs),
            gas=5_000_000), (
            "chain-1 certificate settled on a chainid=2^32+1 deployment "
            "(uint32 truncation aliasing — P-EVM-03; see module docstring)")
        assert h2.balance(h2.dest) - dest_before == 0

    def test_dest_chain_zero_rejected(self, evm):
        """PINNED DEFENSE: dest_chain == 0 fails the payload-level
        "CERT: dest chain unbound" check — the gate's zero case is closed."""
        h, escrow = evm.h, evm.escrowA
        epoch = _fresh_epoch(evm)
        escrow_id = h.w3.keccak(text="w5r2-dc0")
        route_id = h.w3.keccak(text="route-w5r2")
        entity_id = h.w3.keccak(text="entity-w5r2")
        amount = h.w3.to_wei(1, "ether")
        _lock_funded(h, escrow, escrow_id, route_id, entity_id, h.dest, amount)
        env, sigs, payload = _release_args(
            h, evm.vals, epoch, escrow_id, route_id, entity_id, h.dest,
            amount, escrow, dest_chain=0)
        assert h.must_revert(
            escrow.functions.releaseEscrowCanonical(payload, env, sigs),
            gas=5_000_000)
        assert escrow.functions.getEscrowCore(escrow_id).call()[6] == 1  # HOLDING

    def test_self_loop_certificate_settles_documented(self, evm):
        """DOCUMENTED OBSERVATION (spec gap, not an exploit): a certificate
        with source_chain == dest_chain == this deployment's chain settles.
        CANONICAL_CERTIFICATE.md defines both fields (§2 rows 10/11) and
        §8's replay table keys only on dest_chain — no rule forbids a
        self-loop route, and source_chain is ungated everywhere (a foreign
        source_chain settles fine too). Both are quorum-SIGNED inputs, so
        an attacker cannot forge either — recorded for the lead as a
        semantics decision (reject source==dest? gate source_chain?)."""
        h, escrow = evm.h, evm.escrowA
        epoch = _fresh_epoch(evm)
        route_id = h.w3.keccak(text="route-w5r2")
        entity_id = h.w3.keccak(text="entity-w5r2")
        amount = h.w3.to_wei(1, "ether")

        # self-loop: source == dest == this chain
        escrow_id = h.w3.keccak(text="w5r2-selfloop")
        _lock_funded(h, escrow, escrow_id, route_id, entity_id, h.dest, amount)
        env, sigs, payload = _release_args(
            h, evm.vals, epoch, escrow_id, route_id, entity_id, h.dest,
            amount, escrow, source_chain=1, dest_chain=1)
        h.tx(escrow.functions.releaseEscrowCanonical(payload, env, sigs),
             gas=5_000_000)
        assert escrow.functions.getEscrowCore(escrow_id).call()[6] == 3

        # foreign source chain, this dest chain — also accepted
        escrow_id2 = h.w3.keccak(text="w5r2-src-foreign")
        _lock_funded(h, escrow, escrow_id2, route_id, entity_id, h.dest, amount)
        env2, sigs2, payload2 = _release_args(
            h, evm.vals, epoch, escrow_id2, route_id, entity_id, h.dest,
            amount, escrow, source_chain=999, dest_chain=1)
        h.tx(escrow.functions.releaseEscrowCanonical(payload2, env2, sigs2),
             gas=5_000_000)
        assert escrow.functions.getEscrowCore(escrow_id2).call()[6] == 3


# ════════════════════════════════════════════════════════════════════════════
# 2. AKASHIC WINDOW CHAINING + G1 SETTER + sweepETH ACCOUNTING
# ════════════════════════════════════════════════════════════════════════════

@_evm_skip
class TestAkashicWindowChaining:

    def test_wall_clock_24h_bounds_huge_block_timeout(self, evm):
        """PINNED DEFENSE: chaining the two windows cannot extend a release
        lifetime past lock+24h. An escrow with timeoutBlocks = 1e6 (block
        timeout unreachable) is flipped into PENDING_AKASHIC; past the 24h
        WALL CLOCK both release paths refuse, and the permissionless
        akashic-expiry revert refunds the funder. The relayer's flip is
        bounded by lock time, not by flip time."""
        h, escrow = evm.h, evm.escrowA
        epoch = _fresh_epoch(evm)
        escrow_id = h.w3.keccak(text="w5r2-akashic")
        route_id = h.w3.keccak(text="route-w5r2")
        entity_id = h.w3.keccak(text="entity-w5r2")
        amount = h.w3.to_wei(1, "ether")
        _lock_funded(h, escrow, escrow_id, route_id, entity_id, h.dest,
                     amount, timeout_blocks=1_000_000)
        h.tx(escrow.functions.enterPendingAkashic(escrow_id))
        assert escrow.functions.getEscrowCore(escrow_id).call()[6] == 2

        h.t.time_travel(h.now() + 24 * 3600 + 10)
        # block timeout is NOWHERE near (1e6 blocks) — only the wall clock
        # can bound this escrow, and it does:
        env, sigs, payload = _release_args(
            h, evm.vals, epoch, escrow_id, route_id, entity_id, h.dest,
            amount, escrow)
        assert h.must_revert(
            escrow.functions.releaseEscrowCanonical(payload, env, sigs),
            gas=5_000_000)                      # AKASHIC_WINDOW_EXPIRED
        assert h.must_revert(
            escrow.functions.releaseFromPendingAkashic(
                escrow_id, b"\x00" * 32, 900_000), gas=3_000_000)
        dest_before = h.balance(h.dest)
        # the permissionless akashic-expiry revert refunds the funder
        h.tx(escrow.functions.revertEscrow(escrow_id, 0), sender=h.other)
        assert escrow.functions.getEscrowCore(escrow_id).call()[6] == 4
        assert h.balance(h.dest) - dest_before == 0

    def test_g1_setter_is_relayer_only(self, evm):
        """PINNED DEFENSE: verifySettlementCheck is relayer/owner-only — a
        third party cannot set (nor grief with) a settlementCheckHash, and
        it cannot be set on a PENDING_AKASHIC escrow. Observation pinned
        alongside: the hash VALUE is a relayer assertion, never
        cross-checked at release (only != 0) — bounded by the relayer
        trust model, documented in the module docstring."""
        h, escrow = evm.h, evm.escrowA
        escrow_id = h.w3.keccak(text="w5r2-g1")
        route_id = h.w3.keccak(text="route-w5r2")
        entity_id = h.w3.keccak(text="entity-w5r2")
        amount = h.w3.to_wei(1, "ether")
        _lock_funded(h, escrow, escrow_id, route_id, entity_id, h.dest,
                     amount, settle=False)
        assert h.must_revert(
            escrow.functions.verifySettlementCheck(
                escrow_id, h.w3.keccak(text="evil")), sender=h.other)
        # relayer-chosen (arbitrary) hash still enables a legit release —
        # the hash value is an assertion, not a proof
        h.tx(escrow.functions.verifySettlementCheck(
            escrow_id, h.w3.keccak(text="relayer-chosen")))
        epoch = _fresh_epoch(evm)
        env, sigs, payload = _release_args(
            h, evm.vals, epoch, escrow_id, route_id, entity_id, h.dest,
            amount, escrow)
        before = h.balance(h.dest)
        h.tx(escrow.functions.releaseEscrowCanonical(payload, env, sigs),
             gas=5_000_000)
        assert h.balance(h.dest) - before == amount

        # NOT_HOLDING: G1 cannot be (re)set on a PENDING_AKASHIC escrow
        escrow_id2 = h.w3.keccak(text="w5r2-g1b")
        _lock_funded(h, escrow, escrow_id2, route_id, entity_id, h.dest,
                     amount, settle=False)
        h.tx(escrow.functions.enterPendingAkashic(escrow_id2))
        assert h.must_revert(escrow.functions.verifySettlementCheck(
            escrow_id2, h.w3.keccak(text="x")))

    def test_locked_pool_accounting_survives_every_terminal_path(self, evm):
        """PINNED DEFENSE (the sweepETH "fake in-flight" question): the
        aggregate locked pool is EXACT across every terminal transition —
        settle+revert → 0, a parent/child CYCLE reverts each escrow exactly
        once, a SELF-parent escrow reverts without a phantom cascade — so
        no accounting wedge can fake in-flight value and lock owner funds
        forever; sweepETH only ever sees the excess above the live pool."""
        h, escrow = evm.h, evm.escrowB
        route_id = h.w3.keccak(text="route-w5r2")
        entity_id = h.w3.keccak(text="entity-w5r2")
        amount = h.w3.to_wei(1, "ether")
        epoch = _fresh_epoch(evm)

        # settle one + revert one → pool exactly 0
        ea = h.w3.keccak(text="w5r2-swp-a")
        eb = h.w3.keccak(text="w5r2-swp-b")
        _lock_funded(h, escrow, ea, route_id, entity_id, h.dest, amount)
        _lock_funded(h, escrow, eb, route_id, entity_id, h.dest, amount)
        assert escrow.functions.totalLockedBalance().call() == 2 * amount
        env, sigs, payload = _release_args(
            h, evm.vals, epoch, ea, route_id, entity_id, h.dest, amount, escrow)
        h.tx(escrow.functions.releaseEscrowCanonical(payload, env, sigs),
             gas=5_000_000)
        h.tx(escrow.functions.revertEscrow(eb, 3))   # MANUAL (non-timeout)
        assert escrow.functions.totalLockedBalance().call() == 0

        # cascade cycle: A's parent is B, B's parent is A — reverting A
        # cascades to B exactly once; pool → 0, both terminal
        e1 = h.w3.keccak(text="w5r2-cyc-1")
        e2 = h.w3.keccak(text="w5r2-cyc-2")
        for eid, parent in ((e1, e2), (e2, e1)):
            txh = escrow.functions.lockEscrow(
                eid, route_id, entity_id, h.dest, 800_000, 1_000, parent
            ).transact({"from": h.acct, "value": amount, "gas": 5_000_000})
            rcpt = h.w3.eth.wait_for_transaction_receipt(txh)
            assert rcpt["status"] == 1
        assert escrow.functions.totalLockedBalance().call() == 2 * amount
        h.tx(escrow.functions.revertEscrow(e1, 3))
        assert escrow.functions.totalLockedBalance().call() == 0
        assert escrow.functions.getEscrowCore(e1).call()[6] == 4
        assert escrow.functions.getEscrowCore(e2).call()[6] == 4

        # self-parent escrow: no phantom cascade, pool → 0
        e3 = h.w3.keccak(text="w5r2-self-parent")
        txh = escrow.functions.lockEscrow(
            e3, route_id, entity_id, h.dest, 800_000, 1_000, e3
        ).transact({"from": h.acct, "value": amount, "gas": 5_000_000})
        assert h.w3.eth.wait_for_transaction_receipt(txh)["status"] == 1
        h.tx(escrow.functions.revertEscrow(e3, 3))
        assert escrow.functions.totalLockedBalance().call() == 0
        assert escrow.functions.getEscrowCore(e3).call()[6] == 4

        # with every escrow terminal, the sweep can only see the true
        # excess (0 here — nothing force-sent) — never the escrow pool
        assert escrow.functions.sweepableExcess().call() == 0
        assert h.must_revert(escrow.functions.sweepETH(h.acct))


# ════════════════════════════════════════════════════════════════════════════
# 3. VYPER TIER — release-after-timeout (P-VY-01) + freshness defenses
# ════════════════════════════════════════════════════════════════════════════

_VY_MOCK_ORACLE = """
# @version ^0.3.10
# Minimal TRIONOracleV3 mock for the W5-RED2 Vyper attacks: routeBinding()
# + minRouteAttestations() (the exact surface BTCP_ESCROW consumes).
# NOT for production.
struct Verdict:
    anchor_bh:         bytes32
    attestation_count: uint256
    is_safe:           bool
    coherence:         uint256
    threshold:         uint256
    ts:                uint256

validator_count: public(uint256)
verdicts: public(HashMap[bytes32, Verdict])

@external
def __init__():
    self.validator_count = 3

@external
def set_validator_count(n: uint256):
    self.validator_count = n

@external
def set_verdict(
    route_id: bytes32,
    anchor_bh: bytes32,
    attestation_count: uint256,
    is_safe: bool,
    coherence: uint256,
    threshold: uint256,
    ts: uint256,
):
    self.verdicts[route_id] = Verdict({
        anchor_bh:         anchor_bh,
        attestation_count: attestation_count,
        is_safe:           is_safe,
        coherence:         coherence,
        threshold:         threshold,
        ts:                ts,
    })

@external
@view
def verifyExecution(txId: bytes32) -> (bool, uint32, uint32):
    v: Verdict = self.verdicts[txId]
    return v.is_safe, convert(v.coherence, uint32), convert(v.threshold, uint32)

@external
@view
def routeBinding(routeId: bytes32) -> (bytes32, uint256, bool, uint256, uint256, uint256):
    v: Verdict = self.verdicts[routeId]
    return v.anchor_bh, v.attestation_count, v.is_safe, v.coherence, v.threshold, v.ts

@external
@view
def minRouteAttestations() -> uint256:
    required: uint256 = (self.validator_count * 2 + 2) / 3
    if required < 2:
        required = 2
    return required
"""


def _vy_compile(src):
    out = vyper.compile_code(src, output_formats=["bytecode", "abi"])
    return out["abi"], bytes.fromhex(out["bytecode"].removeprefix("0x"))


@_vy_skip
class TestVyperEscrowFresh:

    @pytest.fixture(scope="class")
    def vy(self):
        class _Vy:
            pass
        from web3 import Web3
        from web3.providers.eth_tester import EthereumTesterProvider
        from eth_tester import EthereumTester
        t = EthereumTester()
        w3 = Web3(EthereumTesterProvider(t))
        v = _Vy()
        v.w3 = w3
        v.acct = w3.eth.accounts[0]
        v.dest = w3.eth.accounts[1]
        v.other = w3.eth.accounts[2]

        def deploy(abi, bytecode, ctor_args=()):
            c = w3.eth.contract(abi=abi, bytecode=bytecode)
            tx = c.constructor(*ctor_args).transact(
                {"from": v.acct, "gas": 3_000_000})
            addr = w3.eth.wait_for_transaction_receipt(tx).contractAddress
            return w3.eth.contract(address=addr, abi=abi)

        oracle_abi, oracle_bin = _vy_compile(_VY_MOCK_ORACLE)
        with open(os.path.join(ROOT, "contracts", "vyper",
                               "BTCP_ESCROW.vy")) as f:
            escrow_src = f.read()
        escrow_abi, escrow_bin = _vy_compile(escrow_src)
        v.oracle = deploy(oracle_abi, oracle_bin)
        v.escrow = deploy(escrow_abi, escrow_bin, (v.oracle.address,))
        return v

    def _lock(self, vy, label, timeout_blocks, value_eth=1):
        w3 = vy.w3
        txh = vy.escrow.functions.lock(
            w3.keccak(text=f"intent-{label}"),
            w3.keccak(text=f"entity-{label}"),
            timeout_blocks, vy.dest,
        ).transact({"from": vy.acct, "value": w3.to_wei(value_eth, "ether"),
                    "gas": 500_000})
        rcpt = w3.eth.wait_for_transaction_receipt(txh)
        return rcpt.logs[0]["topics"][1]

    def _set_verdict(self, vy, route, escrow_id, count=2, ts=None):
        now = vy.w3.eth.get_block("latest")["timestamp"]
        vy.oracle.functions.set_verdict(
            route, escrow_id, count, True, 900_000, 800_000,
            now if ts is None else ts).transact({"from": vy.acct})

    def _must_revert(self, vy, fn_call, sender):
        txh = fn_call.transact({"from": sender, "gas": 500_000})
        return vy.w3.eth.wait_for_transaction_receipt(txh)["status"] == 0

    def test_control_release_before_timeout_works(self, vy):
        """Control: the SAME verdict machinery releases an unexpired
        escrow — the P-VY-01 xfail below is an expiry issue, not a broken
        harness."""
        w3 = vy.w3
        escrow_id = self._lock(vy, "ctl", 10)
        route = w3.keccak(text="route-ctl")
        self._set_verdict(vy, route, escrow_id)
        before = w3.eth.get_balance(vy.dest)
        vy.escrow.functions.release(escrow_id, route).transact(
            {"from": vy.other, "gas": 500_000})
        assert w3.eth.get_balance(vy.dest) - before == w3.to_wei(1, "ether")

    # FIXED (Wave 5, lead) — the exploit is closed; the test below now
    # asserts the DEFENSE, not the vulnerability.
    def test_release_after_timeout_rejected(self, vy):
        """INV-004 (BTCP_STATE_MACHINE.md R7 — 'releasing funds after
        timeout' is a forbidden alternative): an escrow past
        lock+timeout_blocks must NOT be releasable, even with a fresh
        quorum-safe verdict bound to it. Verified exploit path today: the
        destination is paid, the funder never refunded."""
        w3 = vy.w3
        escrow_id = self._lock(vy, "exp", 3)
        for _ in range(5):   # mine past the 3-block timeout
            w3.eth.send_transaction({"from": vy.acct, "to": vy.other, "value": 1})
        route = w3.keccak(text="route-late")
        self._set_verdict(vy, route, escrow_id)   # FRESH verdict
        dest_before = w3.eth.get_balance(vy.dest)
        funder_before = w3.eth.get_balance(vy.acct)
        released = not self._must_revert(
            vy, vy.escrow.functions.release(escrow_id, route), vy.other)
        # desired: release refused after timeout
        assert released is False, (
            "expired escrow released with a fresh verdict (P-VY-01)")
        assert w3.eth.get_balance(vy.dest) - dest_before == 0
        assert w3.eth.get_balance(vy.acct) == funder_before

    def test_future_dated_verdict_reverts(self, vy):
        """PINNED DEFENSE: a verdict dated in the FUTURE makes
        block.timestamp - ts underflow Vyper's checked arithmetic — the
        freshness check fails closed, no underflow window."""
        w3 = vy.w3
        escrow_id = self._lock(vy, "fut", 10)
        route = w3.keccak(text="route-fut")
        now = w3.eth.get_block("latest")["timestamp"]
        self._set_verdict(vy, route, escrow_id, ts=now + 3600)
        assert self._must_revert(
            vy, vy.escrow.functions.release(escrow_id, route), vy.other)
        assert vy.escrow.functions.escrow_state(escrow_id).call() == 1


# ════════════════════════════════════════════════════════════════════════════
# 4. PY ORCHESTRATOR — nonce TOCTOU (P-PY-04) + off-registry chains (P-PY-03)
# ════════════════════════════════════════════════════════════════════════════

_IAP = {"total_gas": 1_000_000, "entity_gas": 151_000,
        "total_btcp_fee_wei": 10**16, "entity_share_wei": 15 * 10**14,
        "num_participants": 10}


class TestOrchestratorFresh:

    def test_control_sequential_routes_are_monotonic(self, tmp_path):
        """Control: sequential same-entity create_route calls produce a
        strictly increasing per-entity nonce and one message row each —
        the base W3-D behavior the TOCTOU below corrupts."""
        from core.btcp.orchestrator import BTCPOrchestrator
        orch = BTCPOrchestrator(state_db=str(tmp_path / "nonce.db"))
        entity = "0x" + "ab" * 20
        n1 = orch.create_route(
            1, 137, entity, "0x" + "22" * 20, 100, "0x" + "aa" * 20).route.intent.nonce
        n2 = orch.create_route(
            1, 137, entity, "0x" + "22" * 20, 101, "0x" + "aa" * 20).route.intent.nonce
        assert n2 > n1
        rows = orch._store.read_btcp_table("btcp_cross_chain_messages")
        assert len(rows) == 2

    # FIXED (Wave 5, lead) — the exploit is closed; the test below now
    # asserts the DEFENSE, not the vulnerability.
    def test_concurrent_create_route_no_duplicate_nonce(self, tmp_path):
        """Spec §4.1: the intent nonce is per-entity MONOTONIC. Two
        concurrent create_route calls with the same entity (the
        barrier-instrumented load_all below forces the deterministic
        interleave: both threads read the same store snapshot) must
        produce DISTINCT nonces and TWO cross-chain message rows."""
        from core.btcp.orchestrator import BTCPOrchestrator
        orch = BTCPOrchestrator(state_db=str(tmp_path / "nonce.db"))
        entity = "0x" + "ab" * 20
        # seed the persisted counter so both threads take the last+1 path
        orch.create_route(1, 137, entity, "0x" + "22" * 20, 100,
                          "0x" + "aa" * 20)

        real_load_all = orch._store.load_all
        gate = threading.Barrier(2, timeout=30)

        def synced_load_all(kind):
            if kind == "entity_nonce":
                gate.wait()   # both threads inside the read, same snapshot
            return real_load_all(kind)

        orch._store.load_all = synced_load_all

        results = []

        def worker(amount):
            r = orch.create_route(1, 137, entity, "0x" + "22" * 20, amount,
                                  "0x" + "aa" * 20)
            results.append((r.route.route_id, r.route.intent.nonce))

        threads = [threading.Thread(target=worker, args=(100 + i,))
                   for i in range(2)]
        for t in threads:
            t.start()
        for t in threads:
            t.join()

        nonces = [n for _, n in results]
        assert len(set(nonces)) == 2, (
            f"duplicate per-entity nonce {nonces} — the TOCTOU fired "
            "(P-PY-04)")
        rows = orch._store.read_btcp_table("btcp_cross_chain_messages")
        assert len(rows) == 3   # seed + 2 concurrent routes all recorded

    # FIXED (Wave 5, lead) — the exploit is closed; the test below now
    # asserts the DEFENSE, not the vulnerability.
    def test_off_registry_chain_route_cannot_verify(self, tmp_path):
        """A route whose destination chain is NOT in the canonical registry
        (999 — the relayer's documented off-registry HyperLiquid entry —
        or the fully fabricated id 2^30) must NOT derive a verified
        settlement gate: the registry is the single source of truth for
        what chains exist."""
        from core.btcp.orchestrator import BTCPOrchestrator, PrivacyLevel
        orch = BTCPOrchestrator(state_db=str(tmp_path / "reg.db"))
        for bad_chain in (999, 2**30):
            r = orch.create_route(
                1, bad_chain, "0x" + "11" * 20, "0x" + "22" * 20,
                100, "0x" + "aa" * 20,
                privacy_level=PrivacyLevel.BASIC, iap_economics=_IAP)
            ok, _errs = orch.verify_route_proofs(r.route.route_id)
            assert ok is False, (
                f"route to off-registry chain {bad_chain} verified")

    def test_control_registry_chain_route_verifies(self, tmp_path):
        """Control: the same shape with an in-registry dest chain (137)
        verifies — the xfail above is a registry-membership issue, not a
        broken proof pipeline."""
        from core.btcp.orchestrator import BTCPOrchestrator, PrivacyLevel
        orch = BTCPOrchestrator(state_db=str(tmp_path / "reg.db"))
        r = orch.create_route(
            1, 137, "0x" + "11" * 20, "0x" + "22" * 20,
            100, "0x" + "aa" * 20,
            privacy_level=PrivacyLevel.BASIC, iap_economics=_IAP)
        ok, errs = orch.verify_route_proofs(r.route.route_id)
        assert ok is True, errs

    # FIXED (Wave 5, lead) — the exploit is closed; the test below now
    # asserts the DEFENSE, not the vulnerability.
    def test_api_settlement_gate_for_off_registry_chain(self):
        """The M2 settlement gate is DERIVED from persisted proofs — but
        nothing checks the route's chains exist in the canonical registry,
        so the API asserts 'verified settlement' about a nonexistent
        chain."""
        import flask
        import api.btcp_continuum_routes as btcp_routes
        from api.btcp_continuum_routes import btcp_bp
        btcp_routes._ESCROW_STORES.clear()
        btcp_routes._ORCHESTRATOR = None
        btcp_routes._SANCTIONS_ORACLE = None
        try:
            app = flask.Flask(__name__)
            app.register_blueprint(btcp_bp)
            client = app.test_client()
            r = client.post("/api/v1/btcp/orchestrate", json={
                "source_chain": 1, "dest_chain": 999,
                "source_address": "0x" + "11" * 20,
                "dest_address": "0x" + "22" * 20,
                "amount": 100, "asset": "0x" + "aa" * 20,
                "privacy_level": "BASIC", "iap_economics": _IAP})
            route_id = r.get_json()["route"]["route_id"]
            r2 = client.post("/api/v1/continuum/settlement", json={
                "route_id": route_id, "btcp_route_verified": False,
                "coherence_a": 0.9, "threshold_a": 0.55,
                "coherence_b": 0.9, "threshold_b": 0.55})
            b2 = r2.get_json()
            assert b2["btcp_route_verified"] is False, (
                "settlement gate derived TRUE for off-registry chain 999")
            assert b2["triggered"] is False
        finally:
            btcp_routes._ESCROW_STORES.clear()
            btcp_routes._ORCHESTRATOR = None
            btcp_routes._SANCTIONS_ORACLE = None


# ════════════════════════════════════════════════════════════════════════════
# 5. API — residual write-gate gaps (P-API-03), XFF rate-limit bypass
#    (P-API-04), AWA-freeze bypass on 0G surfaces (P-API-05)
# ════════════════════════════════════════════════════════════════════════════

@pytest.fixture(scope="module")
def full_app_client():
    """Test client for the FULL api.app (routes + middleware), imported
    once per module. Rate-limit buckets cleared so middleware tests start
    from a clean slate (same pattern as the Wave-4 API battery)."""
    from api.app import app  # noqa: import side effects match other tests
    import api.app as api_app
    with api_app._rl_lock:
        api_app._rl_buckets.clear()
    return app.test_client()


class TestApiFreshAttacks:

    def test_control_fixed_write_paths_still_401(self, full_app_client,
                                                monkeypatch):
        """Control: the three Wave-5-gated write paths reject
        unauthenticated GETs — the P-API-03 xfails below are the residual
        two routes, not a wholesale regression of the fix."""
        import api.app as api_app
        monkeypatch.setattr(api_app, "_TRION_API_KEY", "w5r2-redteam-key")
        for p in ("/api/v1/publish/some-entity-id",
                  "/api/v1/zg/da/submit?id=x",
                  "/api/v1/zg/storage/store?id=x"):
            r = full_app_client.get(p)
            assert r.status_code == 401, (p, r.status_code)

    # FIXED (Wave 5, lead) — the exploit is closed; the test below now
    # asserts the DEFENSE, not the vulnerability.
    def test_zg_sync_get_requires_key(self, full_app_client, monkeypatch):
        import api.app as api_app
        monkeypatch.setattr(api_app, "_TRION_API_KEY", "w5r2-redteam-key")
        spawned = []

        class _FakeProc:
            pid = 4242

        import subprocess
        monkeypatch.setattr(
            subprocess, "Popen", lambda *a, **k: spawned.append(a) or _FakeProc())
        r = full_app_client.get("/api/v1/zg/sync")
        assert r.status_code == 401, (
            f"unauthenticated GET on the 0G sync write route → {r.status_code}")
        assert not spawned, "node process spawned without a key"

    # FIXED (Wave 5, lead) — the exploit is closed; the test below now
    # asserts the DEFENSE, not the vulnerability.
    def test_zg_compute_infer_get_requires_key(self, full_app_client,
                                               monkeypatch):
        import api.app as api_app
        monkeypatch.setattr(api_app, "_TRION_API_KEY", "w5r2-redteam-key")
        jobs = []
        monkeypatch.setattr(
            api_app, "_run_zg_module",
            lambda cmd, *a, **k: jobs.append((cmd, a)) or {"ok": True})
        r = full_app_client.get(
            "/api/v1/zg/compute/infer?id=evil-entity&prompt=free-gpu")
        assert r.status_code == 401, (
            f"unauthenticated GET on the 0G compute write route → {r.status_code}")
        assert not jobs, "compute job submitted without a key"

    def test_control_fixed_ip_rate_limit_holds(self, full_app_client,
                                               monkeypatch):
        """Control: for a fixed source IP the limiter DOES engage — the
        P-API-04 xfail is the XFF trust, not a broken limiter core."""
        import api.app as api_app
        monkeypatch.setattr(api_app, "_RL_MAX_REQS", 5)
        with api_app._rl_lock:
            api_app._rl_buckets.clear()
        codes = [full_app_client.get("/api/v1/signal/batch?ids=a").status_code
                 for _ in range(7)]
        assert codes[:5] == [200] * 5
        assert 429 in codes[5:], codes

    # FIXED (Wave 5, lead) — the exploit is closed; the test below now
    # asserts the DEFENSE, not the vulnerability.
    def test_rotating_xff_cannot_bypass_rate_limit(self, full_app_client,
                                                   monkeypatch):
        import api.app as api_app
        monkeypatch.setattr(api_app, "_RL_MAX_REQS", 5)
        with api_app._rl_lock:
            api_app._rl_buckets.clear()
        codes = []
        for i in range(40):
            fake = f"10.77.{(i // 254) % 254 + 1}.{i % 254 + 1}"
            codes.append(full_app_client.get(
                "/api/v1/signal/batch?ids=a",
                headers={"X-Forwarded-For": fake}).status_code)
        assert 429 in codes, "spoofed XFF fully bypassed the rate limiter"

        # framing direction: spoofed XFF fills the VICTIM's bucket → the
        # victim's genuine (headerless) request is denied
        with api_app._rl_lock:
            api_app._rl_buckets.clear()
        victim = "203.0.113.7"
        for _ in range(6):
            full_app_client.get("/api/v1/signal/batch?ids=a",
                                headers={"X-Forwarded-For": victim})
        r = full_app_client.get("/api/v1/signal/batch?ids=a",
                                environ_base={"REMOTE_ADDR": victim})
        assert r.status_code == 200, (
            "spoofed XFF framed a victim IP out of the API (429)")

    # FIXED (Wave 5, lead) — the exploit is closed; the test below now
    # asserts the DEFENSE, not the vulnerability.
    def test_awa_freeze_blocks_zg_publication(self, full_app_client,
                                              monkeypatch):
        import api.app as api_app
        import core.governance.awa as awa
        monkeypatch.setattr(api_app, "_TRION_API_KEY", "w5r2-redteam-key")

        gate = awa.EmissionGate()
        gate.freeze("w5r2-red-team", "attack probe")
        original = awa._emission_gate
        awa._emission_gate = gate
        submitted = []
        monkeypatch.setattr(
            api_app, "_run_zg_module",
            lambda cmd, *a, **k: submitted.append((cmd, a)) or
            {"ok": True, "commitment": "fake"})
        try:
            # control: the publish route fails closed under the freeze
            rp = full_app_client.get("/api/v1/publish/some-entity-id",
                                     headers={"X-API-Key": "w5r2-redteam-key"})
            assert rp.status_code == 503, "publish not frozen (control)"

            r = full_app_client.post(
                "/api/v1/zg/da/submit",
                headers={"X-API-Key": "w5r2-redteam-key"},
                json={"entity_id": "attacker-entity",
                      "coherence_score": 0.9999,
                      "note": "weaponized-narrative"})
            assert r.status_code != 200 or not submitted, (
                "behavioral data published to 0G DA while AWA is frozen")
            assert not submitted, "0G DA submission ran during the freeze"
        finally:
            awa._emission_gate = original

    def test_write_gate_path_confusion_fails_closed(self, full_app_client,
                                                    monkeypatch):
        """PINNED DEFENSE: path-confusion variants against the write gate
        (missing entity segment, URL-encoded traversal, double slashes,
        trailing-slash on exact-match paths) never reach a handler that
        writes — they 404/308 before any side effect, and the gate itself
        fails closed on the prefix path."""
        import api.app as api_app
        monkeypatch.setattr(api_app, "_TRION_API_KEY", "w5r2-redteam-key")
        for path in (
            "/api/v1/publish",                 # no entity segment
            "/api/v1/publish/",                # empty entity segment
            "/api/v1/publish/%2e%2e/onchain/x",  # encoded traversal
            "//api/v1/publish/some-entity-id",   # double leading slash
            "/api/v1/zg/da/submit/",           # trailing slash (exact-match)
            "/api/v1/zg/storage/store/",
            "/API/V1/PUBLISH/some-entity-id",   # case confusion
        ):
            r = full_app_client.get(path)
            assert r.status_code in (401, 404, 308), (path, r.status_code)


# ════════════════════════════════════════════════════════════════════════════
# 6. STORAGE — cross-connection consumption race + key-aliasing hazard
# ════════════════════════════════════════════════════════════════════════════

class TestStorageFresh:

    def test_two_connection_consumption_race_exactly_one(self, tmp_path):
        """PINNED DEFENSE: two INDEPENDENT stores (separate connections and
        RLocks — the two-process model) hammered on the same consumption
        key from two threads yield exactly one CONSUMED and no errors:
        BEGIN IMMEDIATE + SQLite busy-timeout serializes the file across
        processes; a different certificate for the same key is detected as
        EQUIVOCATION cross-store. (Wave 4 pinned the in-process race; this
        pins the cross-process one.)"""
        from core.btcp.state_store import BtcpStateStore
        db = str(tmp_path / "xproc.db")
        store_a = BtcpStateStore(state_db=db)
        store_b = BtcpStateStore(state_db=db)

        results = []
        lock = threading.Lock()

        def hammer(store):
            for _ in range(20):
                try:
                    v = store.consume_certificate(
                        b"\xcd" * 32, "ESCROW_RELEASE", 77,
                        chain_id=1, escrow_id="esc-race")
                    with lock:
                        results.append(v.value)
                except Exception as e:  # pragma: no cover — must not happen
                    with lock:
                        results.append(f"ERR:{type(e).__name__}")

        threads = [threading.Thread(target=hammer, args=(s,))
                   for s in (store_a, store_b)]
        for t in threads:
            t.start()
        for t in threads:
            t.join()

        assert results.count("CONSUMED") == 1, results[:8]
        assert all(not r.startswith("ERR") for r in results)
        assert len(store_a.read_consumed_certificates()) == 1
        # cross-store equivocation detection
        v1 = store_a.consume_certificate(b"\x01" * 32, "ESCROW_RELEASE", 88,
                                         chain_id=1, escrow_id="esc-x")
        v2 = store_b.consume_certificate(b"\x02" * 32, "ESCROW_RELEASE", 88,
                                         chain_id=1, escrow_id="esc-x")
        assert v1.value == "CONSUMED" and v2.value == "EQUIVOCATION"

    def test_consumption_key_colon_aliasing_documented(self):
        """DOCUMENTED HAZARD (latent, LOW): certificate_consumption_key
        joins its components with ':' WITHOUT escaping, so a scope
        containing a colon can alias a different (scope, chain_id) pair.
        Every current call site passes internal constants (scope literals
        like "ESCROW_RELEASE", int chain ids), so no attacker data reaches
        the components today — pinned as current behavior so a future fix
        (escaping or length-prefixing the components) flips this test."""
        from core.btcp.state_store import certificate_consumption_key as key
        aliased = key("ESCROW_RELEASE:B", 1, chain_id=1, escrow_id="e")
        other = key("ESCROW_RELEASE", 1, chain_id="B:1", escrow_id="e")
        assert aliased == other   # the hazard, on record


# ════════════════════════════════════════════════════════════════════════════
# 7. MATH — boundary combinations the checks pass individually
# ════════════════════════════════════════════════════════════════════════════

class TestMathBoundariesFresh:

    def _cert(self, **kw):
        from core.consensus.certificate import CanonicalCertificate
        import hashlib
        h = lambda s: hashlib.sha3_256(s.encode()).digest()
        base = dict(
            validator_epoch=1, certificate_nonce=1, escrow_id=h("e"),
            route_id=h("r"), intent_hash=h("i"), entity_id=h("en"),
            source_chain=1, dest_chain=1,
            destination=bytes(12) + bytes(range(20)), amount=10**18,
            anchor_bh=h("a"), execution_bh=h("x"), coherence=900_000,
            threshold=550_000, hhi_at_emission=1_200,
            total_effective_power=2_400_000, validator_count=3,
            awa_enforced=True, issued_at=int(time.time()), ttl=3_600)
        base.update(kw)
        return CanonicalCertificate(**base)

    def _envelope(self, n=3):
        from core.consensus.certificate import (
            CertificateEnvelope, SignatureFamily, WeightedSignatureEntry)
        import hashlib
        h = lambda s: hashlib.sha3_256(s.encode()).digest()
        return CertificateEnvelope(
            family=int(SignatureFamily.ED25519),
            signatures=[WeightedSignatureEntry(
                h(f"v{i}"), 1_000_000, 800_000, bytes(64)) for i in range(n)])

    def test_boundary_combination_matrix(self):
        """PINNED DEFENSE (the 'passes individually, violates the spirit?'
        question): every threshold boundary that passes is the SPEC's own
        inclusive boundary, and each +1 past it fails —
          • coherence == threshold passes (the verdict rule is ≥)
          • HHI exactly 4000 passes (CRITICAL tier is > 4000), 4001 fails
          • tier-3 quorum exactly 17/20 passes (inclusive), just-below fails
          • combining all three boundary values still passes — each is
            spec-conformant, not a smuggling gap."""
        from core.consensus.certificate import (
            EpochSet, EpochSetEntry, verify_structure)
        import hashlib
        h = lambda s: hashlib.sha3_256(s.encode()).digest()

        ok, _ = verify_structure(
            self._cert(coherence=550_000, threshold=550_000), self._envelope())
        assert ok                      # == threshold is the boundary
        ok, _ = verify_structure(
            self._cert(coherence=549_999, threshold=550_000), self._envelope())
        assert not ok                  # one below fails

        # the full boundary combination: HHI 4000 + 17/20 tier-3 + equality
        es = EpochSet(1, [EpochSetEntry(h(f"t3-{i}"),
                                        1_700_000 if i == 0 else
                                        (200_000 if i == 1 else 100_000),
                                        300_000) for i in range(3)])
        ids = [e.validator_id for e in es.entries]
        met, _, _, tier = es.quorum_met(ids[:1])
        assert tier == 3 and met is True        # exactly 17/20 (inclusive)
        ok, _ = verify_structure(self._cert(hhi_at_emission=4_000),
                                 self._envelope())
        assert ok
        ok, reasons = verify_structure(self._cert(hhi_at_emission=4_001),
                                       self._envelope())
        assert not ok and any("hhi" in r for r in reasons)

    def test_freshness_drift_and_ttl_boundaries(self):
        """PINNED DEFENSE: the §9 clock drift widens the freshness LOWER
        bound by EXACTLY 60s (a certificate dated now+60 is accepted,
        now+61 rejected — expiry never widened), and ttl expiry is
        inclusive (now == issued+ttl valid, +1 rejected)."""
        now = int(time.time())
        assert self._cert(issued_at=now + 60).fresh_at(now) is True
        assert self._cert(issued_at=now + 61).fresh_at(now) is False
        c = self._cert(issued_at=now, ttl=100)
        assert c.fresh_at(now + 100) is True    # inclusive expiry
        assert c.fresh_at(now + 101) is False


# ════════════════════════════════════════════════════════════════════════════
# 8. BITP CLIPBOARD — paste-after-expiry TOCTOU (P-PY-05)
# ════════════════════════════════════════════════════════════════════════════

class TestClipboardExpiry:

    # FIXED (Wave 5, lead) — the exploit is closed; the test below now
    # asserts the DEFENSE, not the vulnerability.
    def test_paste_after_deadline_refused(self):
        """Phase 3 (PASTE) must not fill a commitment whose deadline has
        passed — the clipboard's expiry enforcement (required `now` in
        MATCH) should hold through the terminal transition."""
        from core.btcp.modules import BITPIntent, AkashicClipboard
        NOW = 1_000_000.0

        def intent(entity, chain):
            return BITPIntent(entity_id=entity, asset_in=b"BTC",
                              asset_out=b"BTC", magnitude=1000.0,
                              chain_id=chain, deadline=int(NOW + 100))

        cb = AkashicClipboard()
        a = intent(b"\x0a" * 32, 1)
        b = intent(b"\x0b" * 32, 137)
        ca = cb.execute_cut(a)
        cb.execute_cut(b)
        matched = cb.find_complement(a, now=NOW)
        assert matched is b                 # matched while unexpired

        # both deadlines pass; the pair is still pending paste — the
        # deadline-aware paste (now=after both deadlines) REFUSES them
        ok = cb.execute_paste(ca, cb._commitment(matched), now=NOW + 200)
        assert ok is False, "expired commitments were FILLED (P-PY-05)"
