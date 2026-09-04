"""
WAVE 4 — AGENT P RED-TEAM BATTERY (EVM / consensus math / storage / BH)
========================================================================

Master command §18/§30: attack, do not fix. Every attack below was RUN
against the real implementation (py-solcx 0.8.24 + eth_tester/py-evm for
the EVM tier, live module calls for py/storage/BH). Results:

CONFIRMED EXPLOITS (asserted as CURRENT behavior + TODO(Wave-5) — the fix
is the Wave 5 work order, not mine):

  P-EVM-01  Cross-chain certificate replay: the canonical certificate's
            dest_chain is NEVER checked at the consumption point
            (BTCPEscrow._checkCanonicalBinding, contracts/solidity/
            BTCPEscrow.sol:479-491 — spec CANONICAL_CERTIFICATE.md §8 row 1
            says "replay cert on another chain → dest_chain ≠ that chain →
            step 7"; Solana btcp_escrow/src/lib.rs:1126 and Move
            btcp_escrow.move:552 DO check it; EVM and TON
            (contracts/ton/escrow.fc:518 loads + discards) do not).
            Damage: the same quorum-signed certificate settles identical
            escrow tuples on any number of EVM deployments ("chains") —
            the validators authorized ONE release on ONE chain.
  P-EVM-02  Timeout bypass via enterPendingAkashic: enterPendingAkashic
            (BTCPEscrow.sol:769) has NO expiry check — a block-expired
            HOLDING escrow can be flipped to PENDING_AKASHIC by the
            relayer, after which releaseEscrowCanonical only checks the
            24 h wall-clock Akashic window (measured from LOCK time), not
            timeoutBlocks. The user's block-timeout protection reverts to
            a relayer-controlled 24 h release extension.
  P-PY-01   canonical_magnitude_norm(float('nan')) == 1.0 — a NaN raw
            magnitude forges a MAXIMUM-magnitude BH (NaN comparisons are
            always False, so the <= 0 guard is skipped and
            min(1.0, nan) == 1.0). core/primitives/behavioral_hash.py:144.
  P-PY-02   BH payload chain_id is MASKED (& 0xFFFFFFFF), not validated —
            chain_id 2**32+1 aliases chain 1 in the canonical 93-byte
            payload (low severity: inputs are registry uint32 ids; the
            aliasing is still an identity-confusion surface).

PINNED DEFENSES (attack attempted, BLOCKED — asserted so a regression
that reopens the hole fails CI):
  - ed25519-family signature confusion on the EVM path (width + membership)
  - batch discipline: duplicate signer, unsorted batch, empty batch,
    envelope weight-claim forgery (incl. zero claims for real validators)
  - payload structure: 345/347-byte width, HHI 4000/4001 boundary
  - epoch registry governance: duplicates, unsorted, zero/oversized stake,
    diversity range, weight/power overflow, non-sequential/backward
    registration, epoch 0, non-registrar, grace bounds, HHI critical,
    total power is registry-computed (not claimable)
  - registry epoch-key namespace: two registries with the same epoch
    number do not alias (cross-registry epoch collision blocked); escrow
    registry re-bind impossible
  - escrow state machine: reentrancy (attacker contract on the canonical
    release), legacy↔canonical double-release interleavings both
    directions, post-release revert/emergency, G1 settlement-check gate,
    same-certificate replay, sweepETH cannot touch in-flight funds
    (only force-sent excess), akashic window expiry
  - L4.2 tier math boundaries on-chain AND in py (exactly-2/3 strict,
    3/4 inclusive, 17/20 inclusive, just-below rejection)
  - storage: concurrent consume_certificate is serialized (exactly one
    CONSUMED), SQL injection via crafted ids is inert, escrow/route key
    namespaces cannot alias
  - BH pipeline: 92/94-byte payloads rejected, double-ingest dedup,
    legacy chain-id migration is idempotent
  - AWA: the SILENCE hatch in assert_emission_allowed exists but is NOT
    wired to any data-carrying API path (pinned by live gate test +
    source assertion)

DOCUMENTED ACCEPTANCES (registrar trust — recorded as findings, not bugs
in scope of this battery; see the W4-P report):
  - registerEpoch does NOT cross-check the claimed d_consensus / hhi
    against the registered weights (a dictatorial set can register with
    a lying sub-4000 HHI). Bounded by the R-4 single-registrar trust
    model; §5.3 spirit violated. Wave-5 hardening candidate.

Run: pytest tests/adversarial/test_red_team_wave4.py -q
"""
import importlib.util as _ilu
import os
import sqlite3
import sys
import tempfile
import threading

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

# ── EVM classes skip fast when the toolchain is absent; the pure-py /
# storage / BH / AWA attacks still run everywhere. ──────────────────────────
try:
    import solcx  # noqa: F401
    import web3  # noqa: F401
    import eth_tester  # noqa: F401
    _EVM_OK = True
except Exception:  # pragma: no cover — env gap
    _EVM_OK = False

_evm_skip = pytest.mark.skipif(not _EVM_OK, reason="solcx/web3/eth_tester absent")


# ════════════════════════════════════════════════════════════════════════════
# Shared real-EVM fixture: one chain, registry ×2 + escrow ×2 + oracle +
# attack contracts (compiled once per module).
# ════════════════════════════════════════════════════════════════════════════

ESCROW_ATTACKERS = r"""
// SPDX-License-Identifier: MIT
pragma solidity ^0.8.24;

interface ICanonicalEscrow {
    function releaseEscrowCanonical(
        bytes calldata payload, uint256[] calldata envelopeWeights,
        bytes calldata signatures) external returns (bool);
}

/// Reenters releaseEscrowCanonical from receive() while the escrow is
/// mid-transfer (state already RELEASED + nonReentrant — both must hold).
contract CanonicalReleaseReentrancer {
    ICanonicalEscrow public escrow;
    bytes public payload;
    uint256[] public envelope;
    bytes public sigs;
    uint256 public reentryAttempts;
    uint256 public reentrySuccesses;

    constructor(address e) { escrow = ICanonicalEscrow(e); }

    function arm(bytes calldata p, uint256[] calldata w, bytes calldata s) external {
        payload = p; envelope = w; sigs = s;
    }

    function attack() external returns (bool) {
        return escrow.releaseEscrowCanonical(payload, envelope, sigs);
    }

    receive() external payable {
        reentryAttempts += 1;
        try escrow.releaseEscrowCanonical(payload, envelope, sigs) returns (bool ok) {
            reentrySuccesses += ok ? 1 : 0;
        } catch {}
    }
}

/// Force-sends ETH into the escrow outside any lock (selfdestruct ingress).
contract ForceSender {
    constructor() payable {}
    function die(address to) external { selfdestruct(payable(to)); }
}
"""


@pytest.fixture(scope="module")
def evm():  # pragma: no cover — guarded by _evm_skip on every consumer
    class _Evm:
        pass
    h = _sh.EvmHarness()
    evm = _Evm()
    evm.h = h
    evm.w3 = h.w3
    evm.chain_id = h.w3.eth.chain_id

    # real repo contracts
    esc = h.compile([h.path("BTCPEscrow.sol")], names=["BTCPEscrow"])["BTCPEscrow"]
    reg = h.compile([h.path("TrionEpochRegistry.sol")], names=["TrionEpochRegistry"])["TrionEpochRegistry"]
    orc = h.compile([h.path("TRIONOracleV3.sol")], names=["TRIONOracleV3"])["TRIONOracleV3"]

    evm.registry = h.deploy(*reg)
    evm.registry2 = h.deploy(*reg)                      # second "chain" registry
    evm.escrowA = h.deploy(*esc)                        # "chain A" escrow
    evm.escrowB = h.deploy(*esc)                        # "chain B" escrow
    evm.oracle = h.deploy(*orc)

    h.tx(evm.escrowA.functions.setEpochRegistry(evm.registry.address))
    h.tx(evm.escrowB.functions.setEpochRegistry(evm.registry.address))
    h.tx(evm.oracle.functions.setEpochRegistry(evm.registry.address))

    # attack helpers (tiny, compiled without via_ir)
    import solcx
    outs = solcx.compile_source(ESCROW_ATTACKERS, output_values=["abi", "bin"],
                                solc_version="0.8.24", optimize=True)
    by_name = {k.split(":")[-1]: (v["abi"], v["bin"]) for k, v in outs.items()}
    evm.attacker = h.deploy(*by_name["CanonicalReleaseReentrancer"],
                            args=(evm.escrowA.address,))
    abi, bin_ = by_name["ForceSender"]
    c = h.w3.eth.contract(abi=abi, bytecode=bin_)
    txh = c.constructor().transact({"from": h.acct, "value": h.w3.to_wei(1, "ether"),
                                    "gas": 1_000_000})
    rcpt = h.w3.eth.wait_for_transaction_receipt(txh)
    evm.forcer = h.w3.eth.contract(address=rcpt.contractAddress, abi=abi)

    # validator sets (deterministic keys, numerically ordered by address)
    evm.vals = _sh.make_validators(5)
    evm.vals2 = _sh.make_validators(
        3, seed_start=0xABCD_0000_0000_0000_0000_0000_0000_0001)
    return evm


def _register(h, registry, epoch, addrs, stakes, divs, d_cons, theta, hhi,
              sender=None):
    return h.tx(registry.functions.registerEpoch(
        epoch, addrs, stakes, divs, d_cons, theta, hhi), sender=sender)


def _sorted_vals(vals):
    return sorted(vals, key=lambda v: int(v["addr"], 16))


def _next_epoch(evm, registry=None):
    return (registry or evm.registry).functions.latestEpoch().call() + 1


def _fresh_epoch(evm, n=5, divs=None):
    """Register the next epoch with the standard 5-validator tier-1 set."""
    h = evm.h
    vals = _sorted_vals(evm.vals)[:n]
    epoch = _next_epoch(evm)
    _register(h, evm.registry, epoch, [v["addr"] for v in vals],
              [1_000_000] * n, (divs or [800_000] * n), 800_000, 550_000, 1_200)
    return epoch


def _lock_funded(h, escrow, escrow_id, route_id, entity_id, dest, amount_wei,
                 min_coherence=800_000, timeout_blocks=10_000, settle=True):
    """lock + fund + (optional) G1 settlement check — the relayer flow."""
    txh = escrow.functions.lockEscrow(
        escrow_id, route_id, entity_id, dest, min_coherence, timeout_blocks
    ).transact({"from": h.acct, "value": amount_wei, "gas": 5_000_000})
    rcpt = h.w3.eth.wait_for_transaction_receipt(txh)
    assert rcpt["status"] == 1, "lockEscrow failed"
    if settle:
        h.tx(escrow.functions.verifySettlementCheck(
            escrow_id, h.w3.keccak(text="g1-" + escrow_id.hex())))
    return escrow


def _release_args(h, vals, epoch, power, theta, escrow_id, route_id,
                  entity_id, dest, amount, **kw):
    kw.setdefault("validator_count", len(vals))
    cert = _sh.make_cert(
        validator_epoch=epoch,
        total_effective_power=power, threshold=theta,
        escrow_id=escrow_id, route_id=route_id, entity_id=entity_id,
        destination=b"\x00" * 12 + bytes.fromhex(dest[2:]),
        amount=amount, issued_at=h.now(), **kw)
    stakes = {v["addr"]: 1_000_000 for v in vals}
    divs = {v["addr"]: 800_000 for v in vals}
    sigs, st, dv, _ = _sh.sign_cert_with_weights(h, cert, vals, stakes, divs)
    env = []
    for s, d in zip(st, dv):
        env.extend((s, d))
    return env, b"".join(sigs), cert.encode_payload()


# ════════════════════════════════════════════════════════════════════════════
# 1. CROSS-VM / CROSS-CHAIN CERTIFICATE CONFUSION
# ════════════════════════════════════════════════════════════════════════════

@_evm_skip
class TestCrossChainCertificateConfusion:

    def test_cert_for_foreign_dest_chain_settles_here(self, evm):
        """P-EVM-01 CONFIRMED: a certificate whose dest_chain points at a
        DIFFERENT chain than this EVM deployment still releases the escrow.
        TODO(Wave-5): bind self-chain/escrow dest_chain in
        BTCPEscrow._checkCanonicalBinding per CANONICAL_CERTIFICATE.md §8."""
        h, escrow = evm.h, evm.escrowA
        epoch = _fresh_epoch(evm)
        escrow_id = h.w3.keccak(text="p-evm-01-wrong-chain")
        route_id = h.w3.keccak(text="route-p01")
        entity_id = h.w3.keccak(text="entity-1")
        amount = h.w3.to_wei(1, "ether")
        _lock_funded(h, escrow, escrow_id, route_id, entity_id, h.dest, amount)

        # the certificate is destined for a foreign chain — NOT this EVM
        # chain (dest_chain 999 is a completely different registry chain)
        env, sigs, payload = _release_args(
            h, evm.vals, epoch, 4_000_000, 550_000, escrow_id, route_id,
            entity_id, h.dest, amount, dest_chain=999)

        dest_before = h.balance(h.dest)
        rcpt = h.tx(escrow.functions.releaseEscrowCanonical(payload, env, sigs),
                    gas=5_000_000)
        assert rcpt["status"] == 1
        # CURRENT (broken) behavior: the release SUCCEEDS despite
        # dest_chain=999 != the deployment's chain id.
        assert h.balance(h.dest) - dest_before == amount
        assert evm.chain_id != 999  # sanity: it really is a foreign chain

    def test_same_cert_double_pay_across_two_deployments(self, evm):
        """P-EVM-01 amplifier: the SAME quorum certificate settles identical
        escrow tuples on TWO escrow deployments — the destination is paid
        TWICE from one validator authorization. TODO(Wave-5) with P-EVM-01."""
        h = evm.h
        epoch = _fresh_epoch(evm)
        escrow_id = h.w3.keccak(text="p-evm-01-double-pay")
        route_id = h.w3.keccak(text="route-dbl")
        entity_id = h.w3.keccak(text="entity-dbl")
        amount = h.w3.to_wei(1, "ether")
        _lock_funded(h, evm.escrowA, escrow_id, route_id, entity_id, h.dest, amount)
        _lock_funded(h, evm.escrowB, escrow_id, route_id, entity_id, h.dest, amount)

        env, sigs, payload = _release_args(
            h, evm.vals, epoch, 4_000_000, 550_000, escrow_id, route_id,
            entity_id, h.dest, amount)

        before = h.balance(h.dest)
        h.tx(evm.escrowA.functions.releaseEscrowCanonical(payload, env, sigs),
             gas=5_000_000)
        h.tx(evm.escrowB.functions.releaseEscrowCanonical(payload, env, sigs),
             gas=5_000_000)
        paid = h.balance(h.dest) - before
        # CURRENT (broken) behavior: one certificate, two payments.
        assert paid == 2 * amount

    def test_ed25519_signature_family_rejected_on_evm(self, evm):
        """PINNED DEFENSE: a py/ed25519-family certificate batch (64-byte
        signatures) cannot be submitted to the EVM path — the family-1
        width check rejects it before any ecrecover; a width-aligned
        garbage batch fails at recovery/membership."""
        h, escrow = evm.h, evm.escrowA
        epoch = _fresh_epoch(evm)
        escrow_id = h.w3.keccak(text="p01-ed25519")
        route_id = h.w3.keccak(text="route-ed")
        entity_id = h.w3.keccak(text="entity-ed")
        amount = h.w3.to_wei(1, "ether")
        _lock_funded(h, escrow, escrow_id, route_id, entity_id, h.dest, amount)
        env, _, payload = _release_args(
            h, evm.vals, epoch, 4_000_000, 550_000, escrow_id, route_id,
            entity_id, h.dest, amount)

        ed_batch = b"\x11" * 64 + b"\x22" * 64 + b"\x33" * 64  # 3 ed sigs
        assert h.must_revert(
            escrow.functions.releaseEscrowCanonical(payload, env, ed_batch),
            gas=3_000_000)  # 192 % 65 != 0 → SIGNATURE_WIDTH
        garbage = b"\x99" * 195                              # 3 × 65 random
        assert h.must_revert(
            escrow.functions.releaseEscrowCanonical(payload, env[:6], garbage),
            gas=3_000_000)  # bad certificate signature / not in epoch set

    def test_epoch_number_collision_across_registries_blocked(self, evm):
        """PINNED DEFENSE: two registries can both hold "epoch 1" with
        DIFFERENT sets; a certificate signed by registry-2's set cannot
        settle an escrow bound to registry-1 (signers are not members)."""
        h = evm.h
        vals2 = _sorted_vals(evm.vals2)
        # registry2: its own epoch 1 with a DIFFERENT validator set
        _register(h, evm.registry2, 1, [v["addr"] for v in vals2],
                  [1_000_000] * 3, [800_000] * 3, 800_000, 550_000, 1_200)
        epoch = _fresh_epoch(evm)
        escrow_id = h.w3.keccak(text="p01-registry-collision")
        route_id = h.w3.keccak(text="route-rc")
        entity_id = h.w3.keccak(text="entity-rc")
        amount = h.w3.to_wei(1, "ether")
        _lock_funded(h, evm.escrowA, escrow_id, route_id, entity_id, h.dest,
                     amount)
        # certificate CLAIMS registry-1's set shape (count=5, power=4e6)
        # but is SIGNED by registry-2's keys — membership fails
        env, sigs, payload = _release_args(
            h, vals2, epoch, 4_000_000, 550_000, escrow_id, route_id,
            entity_id, h.dest, amount, validator_count=5)
        assert h.must_revert(
            evm.escrowA.functions.releaseEscrowCanonical(payload, env, sigs),
            gas=3_000_000)

    def test_registry_rebind_blocked(self, evm):
        """PINNED DEFENSE: an escrow bound to one registry cannot be
        re-pointed at another (one-way binding — no registry substitution)."""
        assert evm.h.must_revert(
            evm.escrowA.functions.setEpochRegistry(evm.registry2.address))


# ════════════════════════════════════════════════════════════════════════════
# 2. EPOCH REGISTRY GOVERNANCE ATTACKS
# ════════════════════════════════════════════════════════════════════════════

@_evm_skip
class TestEpochRegistryGovernance:

    def test_duplicate_validator_addresses_rejected(self, evm):
        h, reg = evm.h, evm.registry
        addrs = [v["addr"] for v in _sorted_vals(evm.vals)]
        dup = [addrs[0]] + addrs[:2]           # first address twice
        assert h.must_revert(reg.functions.registerEpoch(
            _next_epoch(evm), dup, [1_000_000] * 3, [800_000] * 3,
            800_000, 550_000, 1_200))

    def test_unsorted_validator_addresses_rejected(self, evm):
        h, reg = evm.h, evm.registry
        addrs = [v["addr"] for v in _sorted_vals(evm.vals)]
        unsorted = [addrs[1], addrs[0], addrs[2]]
        assert h.must_revert(reg.functions.registerEpoch(
            _next_epoch(evm), unsorted, [1_000_000] * 3, [800_000] * 3,
            800_000, 550_000, 1_200))

    def test_zero_and_oversized_stake_rejected(self, evm):
        h, reg = evm.h, evm.registry
        addrs = [v["addr"] for v in _sorted_vals(evm.vals)]
        assert h.must_revert(reg.functions.registerEpoch(
            _next_epoch(evm), addrs[:3], [0, 1, 1], [800_000] * 3,
            800_000, 550_000, 1_200))          # s >= 1
        assert h.must_revert(reg.functions.registerEpoch(
            _next_epoch(evm), addrs[:3],
            [2**64, 1, 1], [800_000] * 3, 800_000, 550_000, 1_200))  # s range

    def test_diversity_range_and_weight_overflow_contained(self, evm):
        h, reg = evm.h, evm.registry
        addrs = [v["addr"] for v in _sorted_vals(evm.vals)]
        # d > 1e6 rejected
        assert h.must_revert(reg.functions.registerEpoch(
            _next_epoch(evm), addrs[:3], [1] * 3, [1_000_001, 1, 1],
            800_000, 550_000, 1_200))
        # max-uint64 stake × full diversity → w = s (no multiplication
        # overflow), but three of them → total power > uint64 → contained
        big = 2**64 - 1
        assert h.must_revert(reg.functions.registerEpoch(
            _next_epoch(evm), addrs[:3], [big, big, big],
            [1_000_000] * 3, 800_000, 550_000, 1_200))

    def test_epoch_set_too_small_rejected(self, evm):
        h, reg = evm.h, evm.registry
        addrs = [v["addr"] for v in _sorted_vals(evm.vals)]
        assert h.must_revert(reg.functions.registerEpoch(
            _next_epoch(evm), addrs[:2], [1_000_000] * 2, [1] * 2,
            800_000, 550_000, 1_200))          # MIN_EPOCH_SET_SIZE = 3

    def test_nonsequential_backward_and_epoch0_rejected(self, evm):
        h, reg = evm.h, evm.registry
        latest = reg.functions.latestEpoch().call()
        addrs = [v["addr"] for v in _sorted_vals(evm.vals)]
        assert h.must_revert(reg.functions.registerEpoch(
            latest + 2, addrs[:3], [1_000_000] * 3, [1] * 3, 800_000, 550_000, 1_200))
        assert h.must_revert(reg.functions.registerEpoch(
            latest, addrs[:3], [1_000_000] * 3, [1] * 3, 800_000, 550_000, 1_200))
        assert h.must_revert(reg.functions.registerEpoch(
            0, addrs[:3], [1_000_000] * 3, [1] * 3, 800_000, 550_000, 1_200))

    def test_non_registrar_cannot_register(self, evm):
        h, reg = evm.h, evm.registry
        addrs = [v["addr"] for v in _sorted_vals(evm.vals)]
        assert h.must_revert(reg.functions.registerEpoch(
            _next_epoch(evm), addrs[:3], [1_000_000] * 3, [1] * 3,
            800_000, 550_000, 1_200), sender=h.other)

    def test_total_power_is_registry_computed_not_claimed(self, evm):
        """PINNED DEFENSE: the epoch's total power is COMPUTED from the
        registered weights — the total_power ≠ Σw attack has no surface."""
        h, reg = evm.h, evm.registry
        addrs = [v["addr"] for v in _sorted_vals(evm.vals)]
        epoch = _next_epoch(evm)
        stakes = [1_000_000, 2_000_000, 3_000_000]
        divs = [800_000, 400_000, 600_000]
        _register(h, reg, epoch, addrs[:3], stakes, divs, 600_000, 550_000, 1_200)
        expected = sum((s * d) // 1_000_000 for s, d in zip(stakes, divs))
        assert reg.functions.epochTotalPower(epoch).call() == expected
        assert reg.functions.epochValidatorCount(epoch).call() == 3

    def test_hhi_critical_epoch_registration_rejected(self, evm):
        h, reg = evm.h, evm.registry
        addrs = [v["addr"] for v in _sorted_vals(evm.vals)]
        assert h.must_revert(reg.functions.registerEpoch(
            _next_epoch(evm), addrs[:3], [1_000_000] * 3, [1] * 3,
            800_000, 550_000, 4_001))
        # exactly 4000 is the boundary: accepted (documented)
        _register(h, reg, _next_epoch(evm), addrs[:3], [1_000_000] * 3, [1] * 3,
                  800_000, 550_000, 4_000)

    def test_grace_and_admin_bounds(self, evm):
        h, reg = evm.h, evm.registry
        assert h.must_revert(reg.functions.setGrace(11), sender=h.acct)
        h.tx(reg.functions.setGrace(10))
        assert reg.functions.epochGrace().call() == 10
        h.tx(reg.functions.setGrace(2))
        assert h.must_revert(reg.functions.setRegistrar(h.other), sender=h.other)

    def test_dictatorial_set_registers_with_lying_hhi(self, evm):
        """DOCUMENTED ACCEPTANCE (registrar trust): a set where one
        validator holds ~100% of the power registers fine with a CLAIMED
        hhi of 1200 (true HHI ≈ 10000 — the L4.8 CRITICAL tier). The
        firewall that still holds: MIN_SIGNERS=3 distinct signatures, so
        the dictator alone cannot emit. Recorded as a Wave-5 hardening
        finding (§5.3 spirit: HHI should be recomputed from the registered
        weights, not claimed)."""
        h, reg = evm.h, evm.registry
        addrs = [v["addr"] for v in _sorted_vals(evm.vals)]
        epoch = _next_epoch(evm)
        big = 2**64 - 3          # dictator + 2 dust validators fits uint64 total
        # stakes: dictator + two dust validators; d = 1e6 → w = s
        _register(h, reg, epoch, addrs[:3], [big, 1, 1],
                  [1_000_000] * 3, 600_000, 550_000, 1_200)
        # accepted — with a lying HHI and a dictatorial power distribution
        met, signed, total, tier = reg.functions.epochQuorum(
            epoch, addrs[:3]).call()
        assert met is True and tier == 1
        assert total == big + 2
        assert reg.functions.epochHHI(epoch).call() == 1_200  # the lie stands


# ════════════════════════════════════════════════════════════════════════════
# 3. L4.2 QUORUM TIER MATH BOUNDARIES (on-chain, real EVM)
# ════════════════════════════════════════════════════════════════════════════

@_evm_skip
class TestQuorumTierBoundaries:

    def _epoch(self, evm, stakes, d_cons):
        h, reg = evm.h, evm.registry
        addrs = [v["addr"] for v in _sorted_vals(evm.vals)]
        epoch = _next_epoch(evm)
        _register(h, reg, epoch, addrs[:len(stakes)], stakes,
                  [1_000_000] * len(stakes), d_cons, 550_000, 1_200)
        return epoch, addrs[:len(stakes)]

    def test_tier1_exactly_two_thirds_is_not_a_quorum(self, evm):
        # weights [2e6, 5e5, 5e5] → total 3e6; v1 alone = exactly 2/3
        epoch, addrs = self._epoch(evm, [2_000_000, 500_000, 500_000], 600_000)
        met, _, _, tier = evm.registry.functions.epochQuorum(
            epoch, [addrs[0]]).call()
        assert tier == 1
        assert met is False            # 3·signed > 2·total — STRICT
        met, _, _, _ = evm.registry.functions.epochQuorum(
            epoch, [addrs[0], addrs[1]]).call()
        assert met is True             # 2.5e6/3e6 > 2/3

    def test_tier2_three_quarters_is_inclusive(self, evm):
        epoch, addrs = self._epoch(evm, [1_500_000, 1_500_000, 1_000_000], 400_000)
        met, _, _, tier = evm.registry.functions.epochQuorum(
            epoch, [addrs[0], addrs[1]]).call()
        assert tier == 2
        assert met is True             # 4·signed >= 3·total — exactly 3/4 passes
        met, _, _, _ = evm.registry.functions.epochQuorum(
            epoch, [addrs[0]]).call()
        assert met is False

    def test_tier3_17_of_20_inclusive_just_below_rejected(self, evm):
        epoch, addrs = self._epoch(evm, [1_700_000, 200_000, 100_000], 399_999)
        met, _, _, tier = evm.registry.functions.epochQuorum(
            epoch, [addrs[0]]).call()
        assert tier == 3
        assert met is True             # 20·signed >= 17·total — exactly 17/20
        met, _, _, _ = evm.registry.functions.epochQuorum(
            epoch, [addrs[1], addrs[2]]).call()
        assert met is False
        epoch2, addrs2 = self._epoch(evm, [1_699_999, 200_001, 100_000], 0)
        met, _, _, _ = evm.registry.functions.epochQuorum(
            epoch2, [addrs2[0]]).call()
        assert met is False            # 1.699999e6/2e6 just below 17/20

    def test_hhi_boundary_payload_side(self, evm):
        """PINNED DEFENSE: hhi=4000 accepted, 4001 rejected at the payload
        level (checkPayload) on the escrow consumption path."""
        h = evm.h
        epoch = _fresh_epoch(evm)
        route_id = h.w3.keccak(text="route-hhi")
        entity_id = h.w3.keccak(text="entity-hhi")
        amount = h.w3.to_wei(1, "ether")
        for hhi, tag, ok in ((4_000, "hhi-4000", True), (4_001, "hhi-4001", False)):
            escrow_id = h.w3.keccak(text=tag)
            _lock_funded(h, evm.escrowA, escrow_id, route_id, entity_id,
                         h.dest, amount)
            env, sigs, payload = _release_args(
                h, evm.vals, epoch, 4_000_000, 550_000, escrow_id, route_id,
                entity_id, h.dest, amount, hhi_at_emission=hhi)
            if ok:
                h.tx(evm.escrowA.functions.releaseEscrowCanonical(
                    payload, env, sigs), gas=5_000_000)
            else:
                assert h.must_revert(
                    evm.escrowA.functions.releaseEscrowCanonical(
                        payload, env, sigs), gas=3_000_000)


# ════════════════════════════════════════════════════════════════════════════
# 4. ESCROW STATE-MACHINE BYPASS ATTEMPTS (real EVM)
# ════════════════════════════════════════════════════════════════════════════

@_evm_skip
class TestEscrowStateMachineBypass:

    def _armed_escrow(self, evm, escrow, tag, timeout_blocks=10_000):
        h = evm.h
        epoch = _fresh_epoch(evm)
        escrow_id = h.w3.keccak(text=f"esc-{tag}")
        route_id = h.w3.keccak(text=f"route-{tag}")
        entity_id = h.w3.keccak(text="entity-1")
        amount = h.w3.to_wei(1, "ether")
        _lock_funded(h, escrow, escrow_id, route_id, entity_id, h.dest,
                     amount, timeout_blocks=timeout_blocks)
        env, sigs, payload = _release_args(
            h, evm.vals, epoch, 4_000_000, 550_000, escrow_id, route_id,
            entity_id, h.dest, amount)
        return escrow_id, payload, env, sigs

    def test_reentrancy_on_canonical_release_blocked(self, evm):
        """PINNED DEFENSE: a destination contract that re-enters
        releaseEscrowCanonical from receive() gets exactly one payment."""
        h, escrow, attacker = evm.h, evm.escrowA, evm.attacker
        epoch = _fresh_epoch(evm)
        escrow_id = h.w3.keccak(text="esc-reent")
        route_id = h.w3.keccak(text="route-reent")
        entity_id = h.w3.keccak(text="entity-1")
        amount = h.w3.to_wei(1, "ether")
        _lock_funded(h, escrow, escrow_id, route_id, entity_id,
                     attacker.address, amount)
        env, sigs, payload = _release_args(
            h, evm.vals, epoch, 4_000_000, 550_000, escrow_id, route_id,
            entity_id, attacker.address, amount)
        h.tx(attacker.functions.arm(payload, env, sigs))
        before = h.balance(attacker.address)
        rcpt = h.tx(attacker.functions.attack(), gas=5_000_000)
        assert rcpt["status"] == 1
        assert attacker.functions.reentryAttempts().call() == 1
        assert attacker.functions.reentrySuccesses().call() == 0  # blocked
        assert h.balance(attacker.address) - before == amount     # paid once

    def test_double_release_legacy_then_canonical_blocked(self, evm):
        h, escrow = evm.h, evm.escrowA
        escrow_id, payload, env, sigs = self._armed_escrow(evm, escrow, "dbl-l-c")
        # legacy release first (trusted-relayer mode: oracle unbound)
        h.tx(escrow.functions.releaseEscrow(escrow_id, h.w3.keccak(text="bh"), 900_000))
        assert escrow.functions.getEscrowCore(escrow_id).call()[6] == 3  # RELEASED
        # canonical attempt must fail — NOT_RELEASABLE
        assert h.must_revert(
            escrow.functions.releaseEscrowCanonical(payload, env, sigs),
            gas=3_000_000)
        assert h.must_revert(
            escrow.functions.releaseFromPendingAkashic(
                escrow_id, b"\x00" * 32, 900_000))

    def test_double_release_canonical_then_legacy_blocked(self, evm):
        h, escrow = evm.h, evm.escrowA
        escrow_id, payload, env, sigs = self._armed_escrow(evm, escrow, "dbl-c-l")
        h.tx(escrow.functions.releaseEscrowCanonical(payload, env, sigs),
             gas=5_000_000)
        assert h.must_revert(
            escrow.functions.releaseEscrow(escrow_id, h.w3.keccak(text="bh2"), 900_000))
        assert h.must_revert(escrow.functions.revertEscrow(escrow_id, 3))
        assert h.must_revert(escrow.functions.revertEmergency(escrow_id))
        # re-release of the SAME certificate: state machine is exactly-once
        assert h.must_revert(
            escrow.functions.releaseEscrowCanonical(payload, env, sigs),
            gas=3_000_000)

    def test_g1_settlement_check_required(self, evm):
        """PINNED DEFENSE: no settlement check → canonical release blocked."""
        h, escrow = evm.h, evm.escrowA
        epoch = _fresh_epoch(evm)
        escrow_id = h.w3.keccak(text="esc-g1")
        route_id = h.w3.keccak(text="route-g1")
        entity_id = h.w3.keccak(text="entity-1")
        amount = h.w3.to_wei(1, "ether")
        _lock_funded(h, escrow, escrow_id, route_id, entity_id, h.dest,
                     amount, settle=False)
        env, sigs, payload = _release_args(
            h, evm.vals, epoch, 4_000_000, 550_000, escrow_id, route_id,
            entity_id, h.dest, amount)
        assert h.must_revert(
            escrow.functions.releaseEscrowCanonical(payload, env, sigs),
            gas=3_000_000)  # SETTLEMENT_NOT_VERIFIED

    def test_expired_escrow_akashic_flip_extends_release_window(self, evm):
        """P-EVM-02 CONFIRMED: enterPendingAkashic has no expiry check —
        a block-expired escrow becomes canonically releasable for the full
        24 h wall-clock Akashic window (measured from LOCK time).
        TODO(Wave-5): reject enterPendingAkashic on expired escrows (or
        measure the window from state entry)."""
        h, escrow = evm.h, evm.escrowA
        # timeout_blocks=1: expires after the very next block
        escrow_id, payload, env, sigs = self._armed_escrow(
            evm, escrow, "expired-akashic", timeout_blocks=1)
        h.t.mine_blocks(3)
        assert escrow.functions.isExpired(escrow_id).call() is True
        # the legacy path now refuses to release (EXPIRED)
        assert h.must_revert(
            escrow.functions.releaseEscrow(escrow_id, b"\x00" * 32, 900_000),
            gas=3_000_000)
        # ATTACK: relayer flips the expired escrow to PENDING_AKASHIC …
        h.tx(escrow.functions.enterPendingAkashic(escrow_id))
        dest_before = h.balance(h.dest)
        # … and the canonical release SUCCEEDS (current behavior)
        rcpt = h.tx(escrow.functions.releaseEscrowCanonical(payload, env, sigs),
                    gas=5_000_000)
        assert rcpt["status"] == 1
        assert h.balance(h.dest) - dest_before == h.w3.to_wei(1, "ether")

    def test_akashic_window_expiry_blocks_canonical_release(self, evm):
        """PINNED DEFENSE: PENDING_AKASHIC beyond the 24 h window is NOT
        canonically releasable (AKASHIC_WINDOW_EXPIRED fires before the
        certificate checks)."""
        h, escrow = evm.h, evm.escrowA
        escrow_id, payload, env, sigs = self._armed_escrow(evm, escrow, "ak-exp")
        h.tx(escrow.functions.enterPendingAkashic(escrow_id))
        h.t.time_travel(h.now() + 24 * 3600 + 10)
        assert h.must_revert(
            escrow.functions.releaseEscrowCanonical(payload, env, sigs),
            gas=3_000_000)

    def test_sweepETH_cannot_touch_in_flight_funds(self, evm):
        """PINNED DEFENSE: while escrows HOLD the contract balance, the
        owner sweep fails — in-flight value is unreachable by governance;
        after a force-send (selfdestruct ingress) only the EXCESS may be
        swept and the locked pool is untouched."""
        h, escrow = evm.h, evm.escrowB
        locked = escrow.functions.totalLockedBalance().call()
        balance = h.balance(escrow.address)
        if balance <= locked:
            assert h.must_revert(escrow.functions.sweepETH(h.acct))
        # force-send 1 ETH outside any lock (selfdestruct ingress)
        h.tx(evm.forcer.functions.die(escrow.address))
        excess = escrow.functions.sweepableExcess().call()
        # locked pool invariant holds either way
        assert escrow.functions.totalLockedBalance().call() == locked
        if excess > 0:  # pre-EIP-6780 semantics: destruct transfers balance
            owner_before = h.balance(h.acct)
            h.tx(escrow.functions.sweepETH(h.acct))
            delta = h.balance(h.acct) - owner_before
            # the swept amount is the excess minus the caller's own gas
            assert 0 < delta <= excess
            assert excess - delta < 1e15          # gas dust only
            assert escrow.functions.sweepableExcess().call() == 0
            assert h.balance(escrow.address) == \
                escrow.functions.totalLockedBalance().call()

    def test_same_certificate_replay_blocked_by_state(self, evm):
        """PINNED DEFENSE: settling an escrow consumes it exactly once —
        resubmitting the SAME certificate (same nonce) cannot pay twice."""
        h, escrow = evm.h, evm.escrowA
        escrow_id, payload, env, sigs = self._armed_escrow(evm, escrow, "replay-once")
        dest_before = h.balance(h.dest)
        h.tx(escrow.functions.releaseEscrowCanonical(payload, env, sigs),
             gas=5_000_000)
        assert h.balance(h.dest) - dest_before == h.w3.to_wei(1, "ether")
        # resubmission: state is RELEASED → NOT_RELEASABLE
        assert h.must_revert(
            escrow.functions.releaseEscrowCanonical(payload, env, sigs),
            gas=3_000_000)


# ════════════════════════════════════════════════════════════════════════════
# 5. ORACLE ATTESTATION FORGERY ATTEMPTS (TRIONOracleV3, real EVM)
# ════════════════════════════════════════════════════════════════════════════

@_evm_skip
class TestOracleAttestationForgery:

    def _cert(self, evm, epoch, escrow_id, **kw):
        h = evm.h
        cert = _sh.make_cert(
            validator_epoch=epoch, validator_count=5,
            total_effective_power=4_000_000, threshold=550_000,
            escrow_id=escrow_id, issued_at=h.now(), **kw)
        stakes = {v["addr"]: 1_000_000 for v in evm.vals}
        divs = {v["addr"]: 800_000 for v in evm.vals}
        sigs, st, dv, _ = _sh.sign_cert_with_weights(h, cert, evm.vals, stakes, divs)
        env = []
        for s, d in zip(st, dv):
            env.extend((s, d))
        return env, b"".join(sigs), cert.encode_payload()

    def test_empty_signature_batch_rejected(self, evm):
        h, oracle = evm.h, evm.oracle
        env, _, payload = self._cert(evm, _fresh_epoch(evm),
                                     h.w3.keccak(text="o-empty"))
        assert h.must_revert(oracle.functions.submitCertificateAttestation(
            payload, env, b""), gas=3_000_000)

    def test_truncated_and_extended_payload_rejected(self, evm):
        h, oracle = evm.h, evm.oracle
        env, sigs, payload = self._cert(evm, _fresh_epoch(evm),
                                        h.w3.keccak(text="o-width"))
        assert h.must_revert(oracle.functions.submitCertificateAttestation(
            payload[:-1], env, sigs), gas=3_000_000)   # 345 bytes
        assert h.must_revert(oracle.functions.submitCertificateAttestation(
            payload + b"\x00", env, sigs), gas=3_000_000)  # 347 bytes

    def test_duplicate_signer_and_unsorted_batch_rejected(self, evm):
        h, oracle = evm.h, evm.oracle
        env, sigs, payload = self._cert(evm, _fresh_epoch(evm),
                                        h.w3.keccak(text="o-dup"))
        sig_list = [sigs[i * 65:(i + 1) * 65] for i in range(len(sigs) // 65)]
        dup = b"".join(sig_list[:1] + sig_list[:1] + sig_list[2:4])
        assert h.must_revert(oracle.functions.submitCertificateAttestation(
            payload, env[:8], dup), gas=3_000_000)
        unsorted = b"".join(list(reversed(sig_list)))
        assert h.must_revert(oracle.functions.submitCertificateAttestation(
            payload, env, unsorted), gas=3_000_000)

    def test_envelope_zero_claim_mismatch_rejected(self, evm):
        """PINNED DEFENSE: claiming s=0/d=0 for a validator that the
        registry knows with real weights fails step 5c — self-reported
        weights are never authority (C-06)."""
        h, oracle = evm.h, evm.oracle
        env, sigs, payload = self._cert(evm, _fresh_epoch(evm),
                                        h.w3.keccak(text="o-claim"))
        forged = list(env)
        forged[0] = 0
        forged[1] = 0
        assert h.must_revert(oracle.functions.submitCertificateAttestation(
            payload, forged, sigs), gas=3_000_000)

    def test_valid_submission_still_records(self, evm):
        """Sanity control — the forgery rejections above are not just
        'everything fails': a well-formed attestation is accepted."""
        h, oracle = evm.h, evm.oracle
        esc = h.w3.keccak(text="o-valid")
        env, sigs, payload = self._cert(evm, _fresh_epoch(evm), esc)
        rcpt = h.tx(oracle.functions.submitCertificateAttestation(payload, env, sigs))
        assert rcpt["status"] == 1
        rec = oracle.functions.canonicalBinding(esc).call()
        assert rec[0] is True


# ════════════════════════════════════════════════════════════════════════════
# 6. PY CANONICAL MATH + CERTIFICATE STRUCTURE
# ════════════════════════════════════════════════════════════════════════════

def _py_cert(**kw):
    import hashlib
    from core.consensus.certificate import CanonicalCertificate
    h = lambda s: hashlib.sha3_256(s.encode()).digest()
    base = dict(
        validator_epoch=1, certificate_nonce=1, escrow_id=h("e"),
        route_id=h("r"), intent_hash=h("i"), entity_id=h("en"),
        source_chain=1, dest_chain=1,
        destination=bytes(12) + bytes(range(20)), amount=10**18,
        anchor_bh=h("a"), execution_bh=h("x"), coherence=900_000,
        threshold=550_000, hhi_at_emission=1_200,
        total_effective_power=2_400_000, validator_count=3,
        awa_enforced=True, issued_at=1_700_000_000, ttl=3_600)
    base.update(kw)
    return CanonicalCertificate(**base)


def _py_envelope(n=3):
    import hashlib
    from core.consensus.certificate import (
        CertificateEnvelope, SignatureFamily, WeightedSignatureEntry)
    h = lambda s: hashlib.sha3_256(s.encode()).digest()
    return CertificateEnvelope(
        family=int(SignatureFamily.ED25519),
        signatures=[WeightedSignatureEntry(
            h(f"v{i}"), 1_000_000, 800_000, bytes(64)) for i in range(n)])


class TestPyCanonicalMath:

    def test_hhi_boundary_and_scale_confusion(self):
        from core.consensus.certificate import verify_structure
        # 4000 accepted / 4001 rejected (0-10000 scale)
        ok, _ = verify_structure(_py_cert(hhi_at_emission=4_000), _py_envelope())
        assert ok
        ok, reasons = verify_structure(_py_cert(hhi_at_emission=4_001), _py_envelope())
        assert not ok and any("hhi" in r for r in reasons)
        # SCALE CONFUSION BLOCKED AT THE ENCODER: a 0-1e6-scale HHI
        # (4_000_000) cannot even be constructed — fail-closed at __post_init__
        with pytest.raises(ValueError, match="hhi_at_emission"):
            _py_cert(hhi_at_emission=4_000_000)
        # 0-1 scale (0.4 → 0) is IN range (degenerate but not critical)
        ok, _ = verify_structure(_py_cert(hhi_at_emission=0), _py_envelope())
        assert ok

    def test_quorum_tier_boundaries_py(self):
        from core.consensus.certificate import EpochSet, EpochSetEntry
        import hashlib
        h = lambda s: hashlib.sha3_256(s.encode()).digest()

        def eset(stakes, divs):
            return EpochSet(1, [EpochSetEntry(h(f"v{i}"), stake_weight=s,
                                              diversity_weight=d)
                                for i, (s, d) in enumerate(zip(stakes, divs))])

        # tier 1 (mean d ≥ 0.6): exactly 2/3 weight is NOT a quorum (strict >)
        # d=0.8 ×3 → tier 1; stakes ×0.8 = weights [2e6, 5e5, 5e5]
        es = eset([2_500_000, 625_000, 625_000], [800_000] * 3)
        ids = [e.validator_id for e in es.entries]
        met, sp, tp, tier = es.quorum_met(ids[:1])      # 2e6 of 3e6 = 2/3
        assert tier == 1 and met is False
        met, _, _, _ = es.quorum_met(ids[:2])
        assert met is True
        # tier 2 (0.4 ≤ mean d < 0.6): exactly 3/4 IS a quorum (inclusive)
        # d=0.5 ×3 → tier 2; stakes ×0.5 = weights [1.5e6, 1.5e6, 1e6]
        es = eset([3_000_000, 3_000_000, 2_000_000], [500_000] * 3)
        ids = [e.validator_id for e in es.entries]
        met, _, _, tier = es.quorum_met(ids[:2])
        assert tier == 2 and met is True
        # tier 3 (mean d < 0.4): exactly 17/20 inclusive
        # d=0.3 ×3 → tier 3; stakes ×0.3 ≈ weights [1.7e6, 2e5, 1e5]
        es = eset([5_666_667, 666_667, 333_334], [300_000] * 3)
        ids = [e.validator_id for e in es.entries]
        met, _, _, tier = es.quorum_met(ids[:1])
        assert tier == 3 and met is True

    def test_payload_width_strictness(self):
        p = _py_cert().encode_payload()
        assert len(p) == 346
        from core.consensus.certificate import CanonicalCertificate
        with pytest.raises(ValueError):
            CanonicalCertificate.from_payload(p[:-1])
        with pytest.raises(ValueError):
            CanonicalCertificate.from_payload(p + b"\x00")

    def test_verify_structure_epoch_and_dup_signers(self):
        from core.consensus.certificate import (
            verify_structure, CertificateEnvelope, SignatureFamily,
            WeightedSignatureEntry)
        # future epoch (latest=1) rejected
        ok, reasons = verify_structure(_py_cert(validator_epoch=10),
                                       _py_envelope(), latest_registered_epoch=1)
        assert not ok and any("future" in r for r in reasons)
        # duplicate signers are rejected AT ENVELOPE CONSTRUCTION
        # ("padding is not consensus" §4 inv. 2) — even stronger than the
        # verify_structure list check
        import hashlib
        h = lambda s: hashlib.sha3_256(s.encode()).digest()
        same = WeightedSignatureEntry(h("v0"), 1_000_000, 800_000, bytes(64))
        with pytest.raises(ValueError, match="duplicate signer"):
            CertificateEnvelope(family=int(SignatureFamily.ED25519),
                                signatures=[same, same, same])
        # beyond-grace epoch rejected
        ok, reasons = verify_structure(_py_cert(validator_epoch=1),
                                       _py_envelope(), latest_registered_epoch=10)
        assert not ok and any("grace" in r for r in reasons)


# ════════════════════════════════════════════════════════════════════════════
# 7. CANONICAL BH / BH PIPELINE EDGES
# ════════════════════════════════════════════════════════════════════════════

class TestBhPipelineEdges:

    def test_nan_magnitude_forges_max_magnitude(self):
        """P-PY-01 CONFIRMED: canonical_magnitude_norm(NaN) == 1.0 — a NaN
        raw value forges the MAXIMUM magnitude (NaN <= 0 is False; Python's
        min(1.0, nan) returns 1.0). TODO(Wave-5): clamp or reject NaN in
        canonical_magnitude_norm (and check the rust twin for parity)."""
        from core.primitives.behavioral_hash import canonical_magnitude_norm
        assert canonical_magnitude_norm(float("nan"), 18) == 1.0
        # controls: negative → 0, huge → 1, zero → 0
        assert canonical_magnitude_norm(-5, 18) == 0.0
        assert canonical_magnitude_norm(10**30, 18) == 1.0
        assert canonical_magnitude_norm(0, 18) == 0.0

    def test_chain_id_masking_aliases_2p32_offset(self):
        """P-PY-02 CONFIRMED (low): BH payload chain_id is MASKED
        (& 0xFFFFFFFF), not validated — chain 2**32+1 produces the SAME
        dual-strand BH as chain 1. TODO(Wave-5): validate, don't mask."""
        from core.primitives.behavioral_hash import (
            BehavioralEvent, EventType, compute_behavioral_hash)

        def bh_for(chain_id):
            return compute_behavioral_hash(BehavioralEvent(
                entity_id=b"\x01" * 32, event_type=EventType.TRANSFER,
                magnitude_raw=10**18, magnitude_decimals=18,
                magnitude_max_90d=10**21, timestamp=1_700_000_000,
                block_number=1, block_hash=b"\x05" * 32, chain_id=chain_id))

        a = bh_for(1)
        b = bh_for(2**32 + 1)
        assert a["sense_hex"] == b["sense_hex"]
        assert a["antisense_hex"] == b["antisense_hex"]  # aliased identity

    def test_rust_hex_payload_width_strict(self):
        from core.primitives.behavioral_hash import bh_from_rust_hex
        good = "ab" * 93
        with pytest.raises(ValueError):
            bh_from_rust_hex(good[:-2])
        with pytest.raises(ValueError):
            bh_from_rust_hex(good + "ab")

    def test_ledger_double_ingest_is_idempotent(self):
        """PINNED DEFENSE: re-processing the same tx writes ONE row
        (tx_hash UNIQUE + INSERT OR IGNORE — the streamer's exact write)."""
        path = os.path.join(tempfile.mkdtemp(), "bh.db")
        conn = sqlite3.connect(path)
        conn.execute("""CREATE TABLE IF NOT EXISTS bh_ledger (
            id INTEGER PRIMARY KEY AUTOINCREMENT, tx_hash TEXT UNIQUE,
            entity_id TEXT, from_addr TEXT, to_addr TEXT,
            event_type INTEGER, event_type_name TEXT,
            magnitude_norm REAL, value_wei TEXT, selector TEXT,
            sense_hex TEXT, antisense_hex TEXT,
            block_num INTEGER, block_hash TEXT,
            chain_id INTEGER, chain_label TEXT, ts REAL, valid INTEGER DEFAULT 1)""")
        row = ("0xdead", "e1", "a", "b", 1, "TRANSFER", 0.5, "1", "0xsel",
               "s", "as", 1, "0xh", 1, "eth", 0.0, 1)
        for _ in range(3):
            conn.execute("""INSERT OR IGNORE INTO bh_ledger
                (tx_hash, entity_id, from_addr, to_addr, event_type,
                 event_type_name, magnitude_norm, value_wei, selector,
                 sense_hex, antisense_hex, block_num, block_hash, chain_id,
                 chain_label, ts, valid) VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)""",
                row)
        conn.commit()
        assert conn.execute(
            "SELECT COUNT(*) FROM bh_ledger").fetchone()[0] == 1
        conn.close()

    def test_legacy_chain_id_migration_is_idempotent(self):
        """PINNED DEFENSE: the c93d237 legacy chain-id re-key is an
        idempotent UPDATE (re-running _init_db cannot corrupt rows)."""
        import core.realtime.bh_streamer as bs
        path = os.path.join(tempfile.mkdtemp(), "bh.db")
        conn = sqlite3.connect(path)
        conn.execute("""CREATE TABLE bh_ledger (
            id INTEGER PRIMARY KEY AUTOINCREMENT, tx_hash TEXT UNIQUE,
            entity_id TEXT, from_addr TEXT, to_addr TEXT,
            event_type INTEGER, event_type_name TEXT,
            magnitude_norm REAL, value_wei TEXT, selector TEXT,
            sense_hex TEXT, antisense_hex TEXT,
            block_num INTEGER, block_hash TEXT,
            chain_id INTEGER, chain_label TEXT, ts REAL, valid INTEGER DEFAULT 1)""")
        old_id = next(iter(bs._LEGACY_STREAMER_CHAIN_IDS))
        new_id = bs._LEGACY_STREAMER_CHAIN_IDS[old_id]
        conn.execute("INSERT INTO bh_ledger (tx_hash, chain_id) VALUES ('0x1', ?)",
                     (old_id,))
        conn.commit()
        conn.close()
        # run the migration directly (twice — the re-run attack);
        # BHStreamer.start() is what invokes _init_db in production
        s = bs.BHStreamer(db_path=path, chains={})
        s._init_db()
        s2 = bs.BHStreamer(db_path=path, chains={})
        s2._init_db()
        conn = sqlite3.connect(path)
        rows = conn.execute("SELECT chain_id FROM bh_ledger").fetchall()
        assert rows == [(new_id,)]  # migrated exactly once, no new rows
        assert conn.execute(
            "SELECT COUNT(*) FROM bh_ledger").fetchone()[0] == 1
        conn.close()


# ════════════════════════════════════════════════════════════════════════════
# 8. STORAGE — consumed-certificate races, injection, key namespace
# ════════════════════════════════════════════════════════════════════════════

class TestStorageAttacks:

    def _store(self):
        from core.btcp.state_store import BtcpStateStore
        return BtcpStateStore(state_db=os.path.join(
            tempfile.mkdtemp(prefix="w4p-store-"), "s.db"))

    def test_concurrent_consume_certificate_exactly_one_consumed(self):
        """PINNED DEFENSE: two concurrent consume_certificate calls on the
        same key serialize under the store RLock/transaction — exactly one
        CONSUMED, the rest REPLAY. No double-execute verdict."""
        from core.btcp.state_store import CertificateConsumption
        store = self._store()
        results = []
        barrier = threading.Barrier(8)

        def worker(_i):
            barrier.wait()
            results.append(store.consume_certificate(
                b"\xab" * 32, "ESCROW_RELEASE", 1,
                chain_id=1, escrow_id="esc-1"))

        threads = [threading.Thread(target=worker, args=(i,)) for i in range(8)]
        for t in threads:
            t.start()
        for t in threads:
            t.join()
        assert results.count(CertificateConsumption.CONSUMED) == 1
        assert results.count(CertificateConsumption.REPLAY) == 7
        store.close()

    def test_sql_injection_via_crafted_ids_is_inert(self):
        """PINNED DEFENSE: quotes/semicolons in escrow/route ids are bound
        parameters — no SQL execution, no extra rows, table intact."""
        store = self._store()
        evil = "e1'; DROP TABLE btcp_consumed_certificates; --"
        v = store.consume_certificate(b"\x01" * 32, "ESCROW_RELEASE", 1,
                                      escrow_id=evil)
        assert v.value == "CONSUMED"
        rows = store.read_consumed_certificates()
        assert len(rows) == 1
        assert rows[0]["escrow_id"] == evil
        v = store.consume_certificate(b"\x02" * 32, "ESCROW_RELEASE", 1,
                                      escrow_id=evil)
        assert v.value == "EQUIVOCATION"
        store.close()

    def test_consumption_key_namespace_cannot_alias(self):
        """PINNED DEFENSE: escrow- and route-namespaced keys never alias
        (type-tagged entities); different chains never share a key; a
        colon-stuffed escrow id cannot forge a route-scoped key."""
        from core.btcp.state_store import (
            certificate_consumption_key as key)
        a = key("ESCROW_RELEASE", 1, chain_id=1, escrow_id="x")
        b = key("ESCROW_RELEASE", 1, chain_id=1, route_id="x")
        assert a != b
        assert a != key("ESCROW_RELEASE", 1, chain_id=2, escrow_id="x")
        assert key("ESCROW_RELEASE", 1, chain_id=1, escrow_id="route:x") != b
        store = self._store()
        store.consume_certificate(b"\x01" * 32, "ESCROW_RELEASE", 7,
                                  escrow_id="x", chain_id=1)
        verdict = store.consume_certificate(b"\x01" * 32, "ESCROW_RELEASE", 7,
                                            route_id="x", chain_id=1)
        assert verdict.value == "CONSUMED"  # distinct key → fresh consumption
        store.close()


# ════════════════════════════════════════════════════════════════════════════
# 9. AWA — SILENCE smuggling surface
# ════════════════════════════════════════════════════════════════════════════

class TestAwaSilenceSmuggling:

    def test_silence_hatch_exists_but_is_not_wired_to_data_paths(self):
        """PINNED DEFENSE: assert_emission_allowed('SILENCE') passes while
        frozen (the documented MD §11 hatch) — but /api/v1/publish always
        asserts 'VALUATION' (even for computed SILENCE payloads), so no
        data-carrying emission can smuggle through the freeze. The real
        singleton is left untouched (a throwaway gate is swapped in)."""
        import core.governance.awa as awa
        gate = awa.EmissionGate()
        gate.freeze("w4p-red-team", "test")
        original = awa._emission_gate
        awa._emission_gate = gate
        try:
            with pytest.raises(awa.EmissionFrozenError):
                awa.assert_emission_allowed("VALUATION")
            awa.assert_emission_allowed("SILENCE")  # the documented hatch
        finally:
            awa._emission_gate = original
        # source pin: the publish route asserts a literal VALUATION — the
        # hatch is unreachable from any caller-controlled signal type
        src = open(os.path.join(ROOT, "api", "app.py")).read()
        assert 'assert_emission_allowed("VALUATION")' in src
        assert 'assert_emission_allowed(data["signal_type"])' not in src
