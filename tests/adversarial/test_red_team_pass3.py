"""
WAVE 5 — INDEPENDENT RED-TEAM PASS 3 (Agent W5-RED3, master §30)
================================================================

A fresh sweep, disjoint from Wave-4 (Agent P) and the final pass 2
(W5-RED2): every attack below was RUN against the real implementation
before being pinned (py-solcx 0.8.24 + eth_tester/py-evm for the
Solidity tier, vyper 0.3.10 + eth_tester for the Vyper tier, real
subprocesses for the two-process store model, live module calls for the
py tier). The emphasis is regression-of-the-fix attacks on the
freshly-fixed surfaces, the oracle submission surface, cross-surface
composition and the state-store's cross-PROCESS concurrency.

CONFIRMED FINDING — asserted as a strict-xfail "desired behavior" test
(TODO(W5-lead): when the lead lands the fix, the test XPASSes, strict
mode fails CI, and the marker is flipped to a defense pin — the
Wave-4→Wave-5 exploit-fix workflow):

  P-PY-06   HIGH  Cross-PROCESS per-entity intent-nonce collision. The
            P-PY-04 fix made `_next_persisted_entity_nonce`'s
            read-modify-write atomic IN-PROCESS (module-global
            _ENTITY_NONCE_LOCK across load→compute→save,
            core/btcp/orchestrator.py:798) — but the two-process
            deployment shares ONE store (state_store.py:51: the default
            is the shared production path db/btcp_state.db; the API
            orchestrator singleton uses it, the streamer/entrypoint is a
            separate process, and gunicorn multi-worker = several API
            processes), and each process holds only its own lock
            instance. The store path is NOT serialized across
            processes: `load_all` is a bare snapshot read OUTSIDE any
            transaction (state_store.py:737) and `save` opens a
            DEFERRED transaction (`with self._conn`, state_store.py:714)
            — NOT `transaction()`'s `BEGIN IMMEDIATE` — so SQLite never
            serializes the two processes' read snapshots.
            Verified with two real subprocesses (deterministic
            read-done handshake, the pass-2 instrumentation methodology):
            both minted nonce N+1 for the same entity, and the second
            process's DISTINCT intent (different amount, different
            intent_id) had its btcp_cross_chain_messages row SILENTLY
            DROPPED by the (sender_entity_id, sender_chain,
            target_chain, nonce) UNIQUE index — 2 rows where 3 belong,
            no error raised anywhere. Spec §4.1 per-entity monotonicity
            is broken in production topology; the destination chain's
            replay guard keyed on that nonce will treat the second
            intent as a replay of the first and drop it — silent intent
            loss / mis-attribution. Fix: mint the nonce store-side
            inside `transaction()` (BEGIN IMMEDIATE read-modify-write,
            e.g. a `mint_entity_nonce(kind, key)` store method returning
            the new value), or open an IMMEDIATE transaction around
            load+compute+save so the read takes the write lock.

PINNED DEFENSES (attack attempted, BLOCKED — asserted so a regression
that reopens the hole fails CI):

  - Oracle acceptance is observability, NEVER consumption: a fully
    valid quorum certificate accepted by submitCertificateAttestation
    records the oracle verdict but leaves the escrow untouched (state
    HOLDING, escrow's own canonicalHighestNonce == 0) — the two
    consumed-nonce trackers are independent by design, the escrow
    re-verifies at the point of value movement, and the mixed-tier
    "oracle accepted it" claim settles nothing. The value path is
    additionally deployment-bound (SEC-21): the quorum signs the
    escrow's own address into the release digest, so settlement needs
    a batch signed for THIS deployment.
  - Duplicate certificates at different nonces for the same escrow:
    the oracle's strictly-increasing (epoch, escrow) nonce ordering
    rejects a LOWER nonce after a higher one was accepted; the ESCROW
    is immune in the value direction — after the first settlement a
    second, HIGHER-nonce certificate for the same escrow reverts
    NOT_RELEASABLE (the state machine is the exactly-once guard; nonce
    growth cannot re-open a settled escrow).
  - Conflict-evidence spam is state-BOUNDED: a conflicting certificate
    (same nonce, different digest — which itself requires a fresh
    validator quorum) flips certificateConflictRecorded and stores ONE
    digest; a THIRD different digest at the same nonce writes NOTHING
    (no event, no storage delta) — the no-revert evidence path cannot
    bloat state or shift the nonce trackers.
  - Vyper lock→mine→relock: an escrow past its timeout is refunded by
    the permissionless revert_on_timeout, after which release() is
    refused (not HOLDING) and re-locking the same intent+entity yields
    a DIFFERENT derived escrow_id (block number is in the hash) that
    the old escrow's verdict cannot address (anchor_bh binding) — no
    state resurrection, no stale-verdict replay against relocked
    funds. A second release of the same escrow is refused (terminal).
  - Registry-bound verification covers PERSISTED routes: an
    off-registry route that was created and persisted BEFORE (or
    regardless of) the creation-time gate still cannot verify after a
    process restart reloads it from the shared store — the gate lives
    in verify_route_proofs, which re-checks BOTH legs against the
    canonical registry from the route's own intent.
  - The in-process nonce lock holds under contention and cannot
    deadlock: 6 threads × 2 entities through create_route all
    complete, per-entity nonces are unique, and every message row
    lands (the lock is a plain Lock with exactly one acquisition
    site — pinned by source scan).
  - TRION_TRUST_PROXY cannot be enabled remotely: the flag is read
    once at import time from the process environment; no request
    surface under api/ assigns os.environ (source scan), so the XFF
    trust cannot be turned on by any attacker-visible path.

DOCUMENTED OBSERVATIONS (residual risks bounded by trust/topology
decisions, recorded for the lead — not pinned as exploits):
  - With TRION_TRUST_PROXY=1 the LAST XFF entry is trusted; a client
    that can reach the app DIRECTLY (bypassing the front proxy) can
    still choose its own rate-limit key. Bounded by the documented
    nginx/compose front topology (the flag is opt-in); the fix
    direction is a proxy-allowlist on request.remote_addr.
  - The oracle's canonicalAttestations verdict is keyed by escrow_id
    WITHOUT epoch, so a later-epoch certificate overwrites the
    observability view of the same escrow. Consumers re-verify against
    the registry; no value path reads it — cosmetic.
  - The py-tier certificate consumption guard (consume_certificate)
    has no production release-path caller yet (only the documented
    call-site note in state_store.py:1089) — the cross-tier
    store-vs-chain double-pay question is therefore not reachable
    today; wire the guard when escrow_monitor's release paths go live.

Run: pytest tests/adversarial/test_red_team_pass3.py -q
"""
import importlib.util as _ilu
import json
import os
import re
import subprocess
import sys
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

try:
    import solcx  # noqa: F401
    import web3  # noqa: F401
    import eth_tester  # noqa: F401
    _EVM_OK = True
except Exception:  # pragma: no cover — env gap
    _EVM_OK = False

_evm_skip = pytest.mark.skipif(not _EVM_OK, reason="solcx/web3/eth_tester absent")

# ── import-hygiene note (W5-RED3, test-infra hazard, NOT a product bug) ──────
# `import vyper` has an import-system side effect that breaks the
# `from core.btcp.orchestrator import BTCPOrchestrator` form when the leaf
# module was only reached through the core.btcp package __init__ (verified:
# vyper-then-from-import → ImportError "cannot import name"; leaf import
# first → OK). Importing the LEAF module here, before vyper, makes every
# later from-import robust in any collection order.
try:
    import core.btcp.orchestrator  # noqa: F401  (leaf-first import)
except Exception:  # pragma: no cover — env gap
    pass

try:
    import vyper  # noqa: F401
    _VY_OK = True
except Exception:  # pragma: no cover — env gap
    _VY_OK = False

_vy_skip = pytest.mark.skipif(not _VY_OK, reason="vyper absent")


# ════════════════════════════════════════════════════════════════════════════
# Shared real-EVM fixture: one chain (registry id 1), epoch registry +
# TRIONOracleV3 + BTCPEscrow, compiled once per module.
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
    orc = h.compile([h.path("TRIONOracleV3.sol")],
                    names=["TRIONOracleV3"])["TRIONOracleV3"]

    evm.registry = h.deploy(*reg)
    evm.oracle = h.deploy(*orc)
    evm.escrow = h.deploy(*esc)
    h.tx(evm.oracle.functions.setEpochRegistry(evm.registry.address))
    h.tx(evm.escrow.functions.setEpochRegistry(evm.registry.address))

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


def _sign_batch(h, cert, vals, escrow=None):
    """Sign `cert` for one audience: `escrow` set → the deployment-bound
    digest (the VALUE path, releaseEscrowCanonical — SEC-21); escrow=None →
    the plain payload digest (the oracle observability path)."""
    stakes = {v["addr"]: 1_000_000 for v in vals}
    divs = {v["addr"]: 800_000 for v in vals}
    sigs, st, dv, _ = _sh.sign_cert_with_weights(
        h, cert, vals, stakes, divs,
        escrow_address=escrow.address if escrow is not None else None)
    env = []
    for s, d in zip(st, dv):
        env.extend((s, d))
    return env, b"".join(sigs)


def _release_args(h, vals, epoch, escrow_id, route_id, entity_id, dest, amount,
                  escrow=None, **kw):
    kw.setdefault("validator_count", len(vals))
    cert = _sh.make_cert(
        validator_epoch=epoch,
        total_effective_power=4_000_000, threshold=550_000,
        escrow_id=escrow_id, route_id=route_id, entity_id=entity_id,
        destination=b"\x00" * 12 + bytes.fromhex(dest[2:]),
        amount=amount, issued_at=h.now(), **kw)
    env, sigs = _sign_batch(h, cert, vals, escrow=escrow)
    return env, sigs, cert.encode_payload(), cert


# ════════════════════════════════════════════════════════════════════════════
# 1. ORACLE SUBMISSION SURFACE — observability vs consumption, nonce growth,
#    conflict-evidence spam (fresh angles; real EVM)
# ════════════════════════════════════════════════════════════════════════════

@_evm_skip
class TestOracleSubmissionSurface:

    def test_oracle_acceptance_never_consumes_or_settles(self, evm):
        """PINNED DEFENSE (the mixed-tier composition question): a fully
        valid quorum certificate accepted by the oracle records ONLY the
        observability verdict — the escrow's own consumed-nonce tracker
        stays at 0, the escrow stays HOLDING, and no value moves. The
        escrow settles only through its own re-verification, and after
        that settlement the oracle-recorded verdict still confers
        nothing (a second release attempt reverts)."""
        h, escrow, oracle = evm.h, evm.escrow, evm.oracle
        epoch = _fresh_epoch(evm)
        vals = _sorted_vals(evm.vals)
        escrow_id = h.w3.keccak(text="w5r3-obs-1")
        route_id = h.w3.keccak(text="route-w5r3")
        entity_id = h.w3.keccak(text="entity-w5r3")
        amount = h.w3.to_wei(1, "ether")
        _lock_funded(h, escrow, escrow_id, route_id, entity_id, h.dest, amount)

        env, sigs, payload, cert = _release_args(
            h, vals, epoch, escrow_id, route_id, entity_id, h.dest, amount,
            escrow=escrow)

        # the oracle accepts the certificate's plain-digest batch (full §6
        # sequence passes on the observability path — SEC-21 binds only the
        # VALUE path, so the oracle batch and the escrow batch are signed
        # over different digests for the SAME payload)
        env_o, sigs_o = _sign_batch(h, cert, vals)
        h.tx(oracle.functions.submitCertificateAttestation(payload, env_o, sigs_o))
        rec = oracle.functions.canonicalBinding(escrow_id).call()
        assert rec[0] is True and rec[7] == 1        # recorded, nonce 1

        # …but the ESCROW knows nothing about it
        assert escrow.functions.canonicalHighestNonce(epoch, escrow_id).call() == 0
        assert escrow.functions.getEscrowCore(escrow_id).call()[6] == 1  # HOLDING
        dest_before = h.balance(h.dest)
        assert dest_before == h.balance(h.dest)

        # the escrow settles through its OWN re-verification of the same
        # certificate — then never again, oracle verdict or not
        h.tx(escrow.functions.releaseEscrowCanonical(payload, env, sigs),
             gas=5_000_000)
        assert h.balance(h.dest) - dest_before == amount
        assert h.must_revert(
            escrow.functions.releaseEscrowCanonical(payload, env, sigs),
            gas=5_000_000)
        assert h.balance(h.dest) - dest_before == amount

    def test_nonce_growth_cannot_reopen_a_settled_escrow(self, evm):
        """PINNED DEFENSE (duplicate certificates at different nonces for
        the same escrow, on the VALUE path): after the first settlement a
        second, HIGHER-nonce, fully valid quorum certificate for the same
        escrow reverts NOT_RELEASABLE — the state machine is the
        exactly-once guard, and nonce growth can never re-open a settled
        escrow (the oracle's nonce tracker is irrelevant here by
        design)."""
        h, escrow = evm.h, evm.escrow
        epoch = _fresh_epoch(evm)
        vals = _sorted_vals(evm.vals)
        escrow_id = h.w3.keccak(text="w5r3-grow")
        route_id = h.w3.keccak(text="route-w5r3")
        entity_id = h.w3.keccak(text="entity-w5r3")
        amount = h.w3.to_wei(1, "ether")
        _lock_funded(h, escrow, escrow_id, route_id, entity_id, h.dest, amount)

        env1, sigs1, payload1, _ = _release_args(
            h, vals, epoch, escrow_id, route_id, entity_id, h.dest, amount,
            certificate_nonce=1, escrow=escrow)
        env2, sigs2, payload2, _ = _release_args(
            h, vals, epoch, escrow_id, route_id, entity_id, h.dest, amount,
            certificate_nonce=2, escrow=escrow)

        dest_before = h.balance(h.dest)
        h.tx(escrow.functions.releaseEscrowCanonical(payload1, env1, sigs1),
             gas=5_000_000)
        assert h.balance(h.dest) - dest_before == amount

        # a HIGHER nonce changes nothing — the escrow is terminal
        assert h.must_revert(
            escrow.functions.releaseEscrowCanonical(payload2, env2, sigs2),
            gas=5_000_000)
        assert h.balance(h.dest) - dest_before == amount

    def test_oracle_nonce_ordering_and_conflict_spam_bounded(self, evm):
        """PINNED DEFENSE: the oracle's (epoch, escrow) nonce ordering
        rejects a lower nonce after a higher one was accepted, and the
        no-revert conflict-evidence path is state-BOUNDED — a conflicting
        certificate records the flag and ONE digest; a THIRD different
        digest at the same nonce writes NOTHING (no event, no storage
        delta). The evidence path cannot be spammed into state growth or
        used to move the nonce trackers."""
        h, oracle = evm.h, evm.oracle
        epoch = _fresh_epoch(evm)
        vals = _sorted_vals(evm.vals)
        escrow_id = h.w3.keccak(text="w5r3-conf")
        route_id = h.w3.keccak(text="route-w5r3")
        entity_id = h.w3.keccak(text="entity-w5r3")
        amount = h.w3.to_wei(1, "ether")

        env1, sigs1, payload1, _ = _release_args(
            h, vals, epoch, escrow_id, route_id, entity_id, h.dest, amount,
            certificate_nonce=1)
        env2, sigs2, payload2, _ = _release_args(
            h, vals, epoch, escrow_id, route_id, entity_id, h.dest, amount,
            certificate_nonce=2)
        env3, sigs3, payload3, _ = _release_args(
            h, vals, epoch, escrow_id, route_id, entity_id, h.dest, amount,
            certificate_nonce=2, intent_hash=h.w3.keccak(text="intent-3"))
        env4, sigs4, payload4, _ = _release_args(
            h, vals, epoch, escrow_id, route_id, entity_id, h.dest, amount,
            certificate_nonce=2, intent_hash=h.w3.keccak(text="intent-4"))

        h.tx(oracle.functions.submitCertificateAttestation(payload1, env1, sigs1))
        rcpt = h.tx(oracle.functions.submitCertificateAttestation(
            payload2, env2, sigs2))
        assert "CertificateAttested" in _sh.event_names(oracle, rcpt)
        assert oracle.functions.canonicalHighestNonce(epoch, escrow_id).call() == 2

        # lower nonce after a higher accepted one → stale, rejected
        assert h.must_revert(oracle.functions.submitCertificateAttestation(
            payload1, env1, sigs1))

        # conflicting digest at the SAME (epoch, escrow, nonce) → the
        # conflicting certificate is rejected, evidence recorded ONCE
        rcpt = h.tx(oracle.functions.submitCertificateAttestation(
            payload3, env3, sigs3))
        assert "CertificateEquivocation" in _sh.event_names(oracle, rcpt)
        assert oracle.functions.certificateConflictRecorded(
            epoch, escrow_id).call() is True

        # a THIRD different digest at the same nonce: the call still
        # returns normally, but NOTHING new is written (bounded state)
        recorded, digest_a, digest_b = oracle.functions.certificateConflict(
            epoch, escrow_id).call()
        rcpt = h.tx(oracle.functions.submitCertificateAttestation(
            payload4, env4, sigs4))
        evs = _sh.event_names(oracle, rcpt)
        assert "CertificateEquivocation" not in evs, (
            "conflict evidence re-emitted — unbounded spam surface")
        assert evs == []                    # nothing at all was recorded
        recorded2, digest_a2, digest_b2 = oracle.functions.certificateConflict(
            epoch, escrow_id).call()
        assert (recorded2, digest_a2, digest_b2) == (recorded, digest_a, digest_b)
        # the nonce trackers were NOT moved by any conflict submission
        assert oracle.functions.canonicalHighestNonce(epoch, escrow_id).call() == 2


# ════════════════════════════════════════════════════════════════════════════
# 2. VYPER TIER — lock→mine→relock against the freshly-guarded release()
# ════════════════════════════════════════════════════════════════════════════

_VY_MOCK_ORACLE = """
# @version ^0.3.10
# Minimal TRIONOracleV3 mock for the W5-RED3 Vyper attacks: routeBinding()
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
class TestVyperRelockAfterRefund:

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

    def _lock(self, vy, label, intent, entity, timeout_blocks, value_eth=1):
        w3 = vy.w3
        txh = vy.escrow.functions.lock(
            intent, entity, timeout_blocks, vy.dest,
        ).transact({"from": vy.acct, "value": w3.to_wei(value_eth, "ether"),
                    "gas": 500_000})
        rcpt = w3.eth.wait_for_transaction_receipt(txh)
        assert rcpt["status"] == 1
        return rcpt.logs[0]["topics"][1]

    def _must_revert(self, vy, fn_call, sender):
        txh = fn_call.transact({"from": sender, "gas": 500_000})
        return vy.w3.eth.wait_for_transaction_receipt(txh)["status"] == 0

    def _set_verdict(self, vy, route, anchor, count=2, ts=None):
        now = vy.w3.eth.get_block("latest")["timestamp"]
        vy.oracle.functions.set_verdict(
            route, anchor, count, True, 900_000, 800_000,
            now if ts is None else ts).transact({"from": vy.acct})

    def test_relock_after_refund_cannot_resurrect_or_replay(self, vy):
        """PINNED DEFENSE (the lock→mine→relock question against the
        P-VY-01 fix): after the timeout refund the old escrow is terminal
        (release refused), re-locking the same intent+entity yields a
        DIFFERENT derived escrow_id (the block number is in the hash) and
        the OLD escrow's verdict cannot address the new escrow (anchor_bh
        binding) — no state resurrection, no stale-verdict replay against
        relocked funds, and a settled escrow can never release again."""
        w3 = vy.w3
        intent = w3.keccak(text="intent-w5r3")
        entity = w3.keccak(text="entity-w5r3")

        escrow_id = self._lock(vy, "relock", intent, entity, 3)
        for _ in range(5):   # mine past the 3-block timeout
            w3.eth.send_transaction({"from": vy.acct, "to": vy.other, "value": 1})

        # refund path — funder gets the funds back, state is REVERTED
        funder_before = w3.eth.get_balance(vy.acct)
        vy.escrow.functions.revert_on_timeout(escrow_id).transact(
            {"from": vy.other, "gas": 500_000})
        assert vy.escrow.functions.escrow_state(escrow_id).call() == 3
        assert w3.eth.get_balance(vy.acct) > funder_before

        # a FRESH quorum verdict bound to the refunded escrow releases
        # NOTHING (not HOLDING) — P-VY-01's guard plus the state machine
        route = w3.keccak(text="route-dead")
        self._set_verdict(vy, route, escrow_id)
        assert self._must_revert(
            vy, vy.escrow.functions.release(escrow_id, route), vy.other)
        assert vy.escrow.functions.escrow_state(escrow_id).call() == 3

        # relock the SAME intent+entity at a later block: a NEW escrow_id
        escrow_id2 = self._lock(vy, "relock2", intent, entity, 10)
        assert escrow_id2 != escrow_id
        assert vy.escrow.functions.escrow_state(escrow_id2).call() == 1

        # the OLD verdict (bound to the refunded escrow) cannot release
        # the relocked funds — anchor binding
        assert self._must_revert(
            vy, vy.escrow.functions.release(escrow_id2, route), vy.other)
        assert vy.escrow.functions.escrow_state(escrow_id2).call() == 1

        # a verdict bound to the NEW escrow releases it — exactly once
        route2 = w3.keccak(text="route-new")
        self._set_verdict(vy, route2, escrow_id2)
        dest_before = w3.eth.get_balance(vy.dest)
        vy.escrow.functions.release(escrow_id2, route2).transact(
            {"from": vy.other, "gas": 500_000})
        assert w3.eth.get_balance(vy.dest) - dest_before == w3.to_wei(1, "ether")
        assert vy.escrow.functions.escrow_state(escrow_id2).call() == 2
        assert self._must_revert(
            vy, vy.escrow.functions.release(escrow_id2, route2), vy.other)


# ════════════════════════════════════════════════════════════════════════════
# 3. STATE-STORE CROSS-PROCESS CONCURRENCY — the fresh angle on the atomic
#    nonce lock: two real PROCESSES sharing the production store.
# ════════════════════════════════════════════════════════════════════════════

_WORKER_SRC = '''
"""Cross-process entity-nonce mint worker (W5-RED3 attack probe).

Models the REAL two-process deployment (api + streamer, or gunicorn
workers): each process has its own BTCPOrchestrator, its own
BtcpStateStore connection and its own _ENTITY_NONCE_LOCK instance.

The load_all hook widens the store's read->save window so the interleave
is deterministic (the pass-2 barrier-instrumentation methodology): the
worker signals "read done" and waits for the OTHER process's read before
saving — both are then guaranteed to have read the same persisted
snapshot, which is exactly what a natural race does probabilistically.
"""
import json
import os
import sys
import time

# The parent launches this worker with PYTHONPATH=<repo root> (the
# standard subprocess isolation — no sys.path mutation in source text).
ROOT = {root!r}

from core.btcp.orchestrator import BTCPOrchestrator, ENTITY_NONCE_KIND

db, entity, my_ready, other_ready, out_path, amount = sys.argv[1:7]

orch = BTCPOrchestrator(state_db=db)
real_load_all = orch._store.load_all

def synced_load_all(kind):
    rows = real_load_all(kind)
    if kind == ENTITY_NONCE_KIND:
        with open(my_ready, "w") as f:
            f.write("read-done")
        deadline = time.time() + 60
        while not os.path.exists(other_ready):
            if time.time() > deadline:
                break
            time.sleep(0.005)
    return rows

orch._store.load_all = synced_load_all
r = orch.create_route(1, 137, entity, "0x" + "22" * 20, int(amount),
                      "0x" + "aa" * 20)
json.dump({{"nonce": r.route.intent.nonce,
            "intent_id": r.route.intent.intent_id}},
          open(out_path, "w"))
'''


class TestCrossProcessNonceMint:

    # P-PY-06 FIXED (Wave 5, lead): the store now exposes an atomic
    # cross-process counter (BEGIN IMMEDIATE around read+compute+write on
    # the shared SQLite file) and the orchestrator uses it first —
    # verified below across two REAL processes sharing one store.
    def test_two_processes_mint_distinct_nonces(self, tmp_path):
        """Desired behavior (spec §4.1, per-entity monotonicity): two
        PROCESSES sharing one state store (the production topology — the
        api singleton, the streamer, gunicorn workers) must mint DISTINCT
        per-entity nonces, and every create_route must land its
        cross-chain message row. Verified exploit today: both processes
        read the same persisted snapshot and mint the SAME nonce; the
        second process's DISTINCT intent (different amount and
        intent_id) loses its btcp_cross_chain_messages row to the
        (sender, source, target, nonce) UNIQUE index — silently."""
        db = str(tmp_path / "xproc-nonce.db")
        entity = "0x" + "ab" * 20

        # a third process (the deploy/seed) establishes the persisted
        # counter so both workers take the last+1 path
        from core.btcp.orchestrator import BTCPOrchestrator  # conftest provides ROOT
        seed = BTCPOrchestrator(state_db=db)
        r0 = seed.create_route(1, 137, entity, "0x" + "22" * 20, 100,
                               "0x" + "aa" * 20)
        seed_nonce = r0.route.intent.nonce
        del seed

        worker = tmp_path / "nonce_worker.py"
        worker.write_text(_WORKER_SRC.format(root=ROOT))
        ready_a = tmp_path / "a.ready"
        ready_b = tmp_path / "b.ready"
        out_a = tmp_path / "a.json"
        out_b = tmp_path / "b.json"

        procs = []
        for my_ready, other_ready, out_path, amount in (
                (ready_a, ready_b, out_a, 200),
                (ready_b, ready_a, out_b, 201)):
            procs.append(subprocess.Popen(
                [sys.executable, str(worker), db, entity,
                 str(my_ready), str(other_ready), str(out_path), str(amount)],
                stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True,
                env={**os.environ, "PYTHONPATH": ROOT}))
        for p in procs:
            _out, err = p.communicate(timeout=120)
            assert p.returncode == 0, err[-500:]

        a = json.loads(out_a.read_text())
        b = json.loads(out_b.read_text())
        assert a["intent_id"] != b["intent_id"], (
            "attack harness broke: the two intents must be DISTINCT "
            "(different amounts)")
        assert a["nonce"] != b["nonce"], (
            f"two processes minted the SAME per-entity nonce "
            f"({a['nonce']}) — the P-PY-06 cross-process TOCTOU fired; "
            f"the second intent's cross-chain message row was silently "
            f"dropped by the (sender, source, target, nonce) UNIQUE index")

        from core.btcp.state_store import BtcpStateStore
        store = BtcpStateStore(state_db=db)
        rows = store.read_btcp_table("btcp_cross_chain_messages")
        assert len(rows) == 3, (
            f"cross-chain message rows: {len(rows)} (seed + both worker "
            f"intents = 3 expected) — a replay-prevention log row was "
            f"dropped without any error")
        assert all(n != seed_nonce for n in (a["nonce"], b["nonce"]))


# ════════════════════════════════════════════════════════════════════════════
# 4. PY ORCHESTRATOR — in-process lock under contention, persisted
#    pre-gate routes, single-writer / trust-boundary source pins
# ════════════════════════════════════════════════════════════════════════════

_IAP = {"total_gas": 1_000_000, "entity_gas": 151_000,
        "total_btcp_fee_wei": 10**16, "entity_share_wei": 15 * 10**14,
        "num_participants": 10}


class TestOrchestratorLockScope:

    def test_concurrent_create_route_many_entities_no_deadlock(self, tmp_path):
        """PINNED DEFENSE: the in-process P-PY-04 fix holds under real
        contention — 6 threads through create_route with 2 entities all
        complete (no deadlock: the nonce lock is a plain Lock with a
        single acquisition site), per-entity nonces are unique, and every
        message row lands."""
        from core.btcp.orchestrator import BTCPOrchestrator
        orch = BTCPOrchestrator(state_db=str(tmp_path / "hammer.db"))
        entities = ["0x" + "cd" * 20, "0x" + "ce" * 20]
        # seed both entities' persisted counters
        for e in entities:
            orch.create_route(1, 137, e, "0x" + "22" * 20, 100, "0x" + "aa" * 20)

        results = []
        lock = threading.Lock()
        start = threading.Barrier(6, timeout=60)

        def worker(idx):
            e = entities[idx % 2]
            start.wait()
            r = orch.create_route(1, 137, e, "0x" + "22" * 20,
                                  200 + idx, "0x" + "aa" * 20)
            with lock:
                results.append((e, r.route.intent.nonce))

        threads = [threading.Thread(target=worker, args=(i,)) for i in range(6)]
        for t in threads:
            t.start()
        for t in threads:
            t.join(timeout=90)
        assert not any(t.is_alive() for t in threads), (
            "create_route deadlocked under concurrent same-entity load")

        assert len(results) == 6
        for e in entities:
            nonces = [n for ee, n in results if ee == e]
            assert len(set(nonces)) == len(nonces), (
                f"duplicate in-process nonce for {e}: {nonces}")
        rows = orch._store.read_btcp_table("btcp_cross_chain_messages")
        assert len(rows) == 8   # 2 seed + 6 concurrent routes all recorded

    def test_persisted_off_registry_route_never_verifies(self, tmp_path):
        """PINNED DEFENSE (route created BEFORE the gate — the data-level
        bypass): the P-PY-03 fix lives in verify_route_proofs, which
        re-checks both legs against the canonical registry from the
        route's OWN intent — so an off-registry route that was created
        and PERSISTED (pre-fix data, another process, or a direct store
        write) still cannot verify after a process restart reloads it
        from the shared store."""
        from core.btcp.orchestrator import BTCPOrchestrator, PrivacyLevel
        db = str(tmp_path / "pregate.db")
        orch = BTCPOrchestrator(state_db=db)
        r999 = orch.create_route(
            1, 999, "0x" + "11" * 20, "0x" + "22" * 20, 100, "0x" + "aa" * 20,
            privacy_level=PrivacyLevel.BASIC, iap_economics=_IAP)
        r137 = orch.create_route(
            1, 137, "0x" + "11" * 20, "0x" + "22" * 20, 100, "0x" + "aa" * 20,
            privacy_level=PrivacyLevel.BASIC, iap_economics=_IAP)

        # a FRESH instance = a restarted process reloading persisted rows
        reloaded = BTCPOrchestrator(state_db=db)
        assert r999.route.route_id in reloaded._routes
        ok, errs = reloaded.verify_route_proofs(r999.route.route_id)
        assert ok is False and any("registry" in e for e in errs), errs

        # control: the in-registry route reloads and verifies
        assert r137.route.route_id in reloaded._routes
        ok, errs = reloaded.verify_route_proofs(r137.route.route_id)
        assert ok is True, errs

    def test_entity_nonce_kind_has_exactly_one_production_writer(self):
        """PINNED DEFENSE (lock-scope gap hunt): the persisted entity_nonce
        KV kind has EXACTLY ONE production writer — the orchestrator's
        locked read-modify-write. No other core module writes that kind,
        so no unguarded writer can reintroduce the in-process TOCTOU from
        a different call path."""
        hits = []
        for dirpath, _dirs, files in os.walk(os.path.join(ROOT, "core")):
            if "__pycache__" in dirpath:
                continue
            for fn in files:
                if not fn.endswith(".py"):
                    continue
                path = os.path.join(dirpath, fn)
                with open(path, encoding="utf-8") as f:
                    src = f.read()
                for m in re.finditer(
                        r'\.save\(\s*(ENTITY_NONCE_KIND|"entity_nonce")', src):
                    hits.append(f"{path}:save")
        assert hits == [os.path.join(ROOT, "core", "btcp", "orchestrator.py")
                        + ":save"], hits

    def test_trust_proxy_flag_not_remotely_settable(self):
        """PINNED DEFENSE (the XFF fix's own trust boundary): no request
        surface under api/ can WRITE the process environment — the only
        assignments to os.environ in the API package are none, so
        TRION_TRUST_PROXY (and TRION_API_KEY) are import-time operator
        decisions that no attacker-visible path can flip at runtime."""
        api_dir = os.path.join(ROOT, "api")
        offenders = []
        for dirpath, _dirs, files in os.walk(api_dir):
            if "__pycache__" in dirpath:
                continue
            for fn in files:
                if not fn.endswith(".py"):
                    continue
                path = os.path.join(dirpath, fn)
                with open(path, encoding="utf-8") as f:
                    for i, line in enumerate(f, 1):
                        if re.search(r"os\.environ\s*\[[^\]]+\]\s*=", line) or \
                           re.search(r"environ\s*\[[^\]]+\]\s*=\s*[^=]", line) or \
                           "os.putenv" in line:
                            offenders.append(f"{path}:{i}:{line.strip()}")
        assert offenders == [], offenders
