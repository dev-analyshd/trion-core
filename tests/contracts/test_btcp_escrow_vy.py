"""
BTCP_ESCROW.vy — whitepaper §14.3 compliance test (real EVM execution).

Deploys a MockTRIONOracle + BTCP_ESCROW (both compiled with vyper 0.3.10)
on py-evm via eth-tester and exercises the full two-state lifecycle:

  1. lock()        — payable, escrow_id derived, event emitted
  2. release()     — permissionless but oracle-gated:
                     fails on unsafe route / low coherence / non-HOLDING
  3. double release — rejected (terminal state)
  4. revert_on_timeout() — before timeout fails, after refunds funder
  5. no-governance — no owner/admin surface on the contract at all
  6. M-03 (Wave 2) — release quorum is DERIVED FROM THE ORACLE'S LIVE
     validator-set state (minRouteAttestations(), V3's
     max(2, ⌈2/3·validatorCount⌉) view), never a hardcoded floor:
       6a. valid release under the dynamic quorum
       6b. M-03 REGRESSION: the 2-attestation attack on a 7-validator set
           (required 5) FAILS; exactly 5 passes
       6c. mid-flight validator-set growth (7 → 12) tightens the gate on a
           verdict that used to suffice
       6d. a misbehaving oracle reporting a sub-floor quorum (1) is clamped
           back up to the hard floor of 2
       6e. interface mismatch FAILS CLOSED: an oracle WITHOUT the
           minRouteAttestations() view (the pre-M-03 mock) can never
           release — no fallback to a floor (the Solidity M-05 class is
           structurally impossible in the Vyper tier)
  7. minRouteAttestations() formula parity with TRIONOracleV3.sol
     (1→2, 2→2, 3→2, 4→3, 5→4, 6→4, 7→5, 9→6, 12→8)

Run: python3 tests/contracts/test_btcp_escrow_vy.py
"""

import os
import sys

from web3 import Web3
from web3.providers.eth_tester import EthereumTesterProvider
from eth_tester import EthereumTester
import vyper

REPO = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))


def compile_vy(path: str):
    src = open(path).read()
    out = vyper.compile_code(src, output_formats=["bytecode", "abi"])
    return out["abi"], bytes.fromhex(out["bytecode"].removeprefix("0x"))


def compile_vy_from_src(src: str):
    out = vyper.compile_code(src, output_formats=["bytecode", "abi"])
    return out["abi"], bytes.fromhex(out["bytecode"].removeprefix("0x"))


# Mock of the CURRENT TRIONOracleV3 surface the escrow consumes:
# routeBinding() + the M-03 dynamic-quorum view minRouteAttestations()
# (max(2, ⌈2/3·validatorCount⌉) over a settable live validator set — the
# addValidator growth model). NOT for production.
MOCK_ORACLE = """
# @version ^0.3.10
# TRIONOracleV3 mock for BTCP_ESCROW tests — mirrors the real V3 surface the
# escrow consumes: routeBinding() + minRouteAttestations() derived from a
# settable live validator set (the addValidator growth model).
# NOT for production.

struct Verdict:
    anchor_bh:         bytes32
    attestation_count: uint256
    is_safe:           bool
    coherence:         uint256
    threshold:         uint256
    ts:                uint256

validator_count:   public(uint256)
broken_quorum_floor: public(bool)
verdicts: public(HashMap[bytes32, Verdict])

@external
def __init__():
    # 3-registry mock: small honest set, deployer + 2 validators.
    self.validator_count = 3

@external
def add_validator():
    self.validator_count += 1

@external
def set_validator_count(n: uint256):
    self.validator_count = n

@external
def report_sub_floor_quorum():
    # models a MISBEHAVING oracle: reports a required quorum BELOW the
    # protocol hard floor of 2 (the escrow must clamp, never degrade).
    self.broken_quorum_floor = True

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
    # EXACT mirror of TRIONOracleV3.minRouteAttestations():
    #     required = max(2, ceil(2/3 * validatorCount))
    if self.broken_quorum_floor:
        return 1
    required: uint256 = (self.validator_count * 2 + 2) / 3
    if required < 2:
        required = 2
    return required
"""

# The PRE-M-03 mock: identical storage/verdicts but WITHOUT the
# minRouteAttestations() view. Used to prove the escrow fails CLOSED on an
# interface mismatch instead of falling back to a static floor (anti-M-05).
MOCK_ORACLE_LEGACY = """
# @version ^0.3.10
# LEGACY TRION oracle mock — the pre-M-03 interface: NO dynamic-quorum view.
# Used to prove BTCP_ESCROW fails closed when the bound oracle lacks
# minRouteAttestations(). NOT for production.

struct Verdict:
    anchor_bh:         bytes32
    attestation_count: uint256
    is_safe:           bool
    coherence:         uint256
    threshold:         uint256
    ts:                uint256

verdicts: public(HashMap[bytes32, Verdict])

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
"""

PASSED = []
FAILED = []

def must_revert(w3, fn_call, sender) -> bool:
    """eth-tester does not raise at transact() for reverts — the revert
    surfaces as receipt status 0. Returns True iff the tx reverted."""
    txh = fn_call.transact({"from": sender, "gas": 500_000})
    rcpt = w3.eth.wait_for_transaction_receipt(txh)
    return rcpt["status"] == 0



def check(name: str, cond: bool, detail: str = ""):
    (PASSED if cond else FAILED).append(name)
    print(f"  {'OK' if cond else 'FAIL'} {name}" + (f" — {detail}" if detail and not cond else ""))


def deploy(w3, abi, bytecode, sender, ctor_args=()):
    c = w3.eth.contract(abi=abi, bytecode=bytecode)
    tx = c.constructor(*ctor_args).transact({"from": sender, "gas": 3_000_000})
    addr = w3.eth.wait_for_transaction_receipt(tx).contractAddress
    return w3.eth.contract(address=addr, abi=abi)


def main():
    t = EthereumTester()
    w3 = Web3(EthereumTesterProvider(t))
    acct = w3.eth.accounts[0]
    dest = w3.eth.accounts[1]
    other = w3.eth.accounts[2]

    # ── compile ──
    oracle_abi, oracle_bytecode = compile_vy_from_src(MOCK_ORACLE)
    legacy_abi, legacy_bytecode = compile_vy_from_src(MOCK_ORACLE_LEGACY)
    escrow_abi, escrow_bytecode = compile_vy(os.path.join(REPO, "contracts/vyper/BTCP_ESCROW.vy"))

    # ── deploy mock oracle (current V3 surface incl. dynamic quorum) ──
    oracle = deploy(w3, oracle_abi, oracle_bytecode, acct)

    # ── deploy escrow bound to oracle ──
    escrow = deploy(w3, escrow_abi, escrow_bytecode, acct, (oracle.address,))

    print("\n1) lock() — payable, derived escrow_id, EscrowLocked event")
    intent_hash = w3.keccak(text="intent-A")
    entity_id = w3.keccak(text="entity-A")
    txh = escrow.functions.lock(
        intent_hash, entity_id, 10, dest
    ).transact({"from": acct, "value": w3.to_wei(1, "ether"), "gas": 500_000})
    rcpt = w3.eth.wait_for_transaction_receipt(txh)
    escrow_id = rcpt.logs[0]["topics"][1]  # indexed escrow_id from EscrowLocked
    events = escrow.events.EscrowLocked().process_receipt(rcpt)
    check("lock emits EscrowLocked with amount",
          bool(events) and events[0]["args"]["amount"] == w3.to_wei(1, "ether"))
    check("escrow in HOLDING", escrow.functions.escrow_state(escrow_id).call() == 1)

    print("\n2) release() - oracle-gated + escrow-BOUND")
    route_ok = w3.keccak(text="route-ok")
    route_low = w3.keccak(text="route-low")
    route_unsafe = w3.keccak(text="route-unsafe")
    route_foreign = w3.keccak(text="route-foreign")
    route_solo = w3.keccak(text="route-solo")
    route_stale = w3.keccak(text="route-stale")
    now = w3.eth.get_block("latest")["timestamp"]

    def set_verdict(route, anchor, count, safe, coh, thr, ts=None):
        oracle.functions.set_verdict(route, anchor, count, safe, coh, thr,
                                     now if ts is None else ts).transact({"from": acct})

    # 2a. release with NO verdict set must fail (fail-closed)
    check("release with no oracle verdict reverts",
          must_revert(w3, escrow.functions.release(escrow_id, w3.keccak(text="no-verdict")), other))

    # 2b. unsafe verdict (bound to THIS escrow) must fail
    set_verdict(route_unsafe, escrow_id, 3, False, 900_000, 800_000)
    check("release with is_safe=False reverts",
          must_revert(w3, escrow.functions.release(escrow_id, route_unsafe), other))

    # 2c. safe but coherence < threshold must fail
    set_verdict(route_low, escrow_id, 3, True, 700_000, 800_000)
    check("release with coherence < threshold reverts",
          must_revert(w3, escrow.functions.release(escrow_id, route_low), other))

    # 2c2. H1/M3 ROUTE-SPOOF: quorum-safe fresh verdict bound to a DIFFERENT
    # escrow id must fail (verdict replay / route substitution).
    set_verdict(route_foreign, w3.keccak(text="someone-elses-escrow"), 3, True, 900_000, 800_000)
    check("release with verdict bound to a FOREIGN escrow reverts (route-spoof)",
          must_revert(w3, escrow.functions.release(escrow_id, route_foreign), other))

    # 2c3. quorum=1 verdict bound to this escrow must fail (quorum floor)
    set_verdict(route_solo, escrow_id, 1, True, 900_000, 800_000)
    check("release with single attestation reverts (quorum unmet)",
          must_revert(w3, escrow.functions.release(escrow_id, route_solo), other))

    # 2c4. stale verdict (ts = now - 400) must fail (freshness)
    set_verdict(route_stale, escrow_id, 3, True, 900_000, 800_000, ts=now - 400)
    check("release with stale verdict reverts",
          must_revert(w3, escrow.functions.release(escrow_id, route_stale), other))

    # 2d. fully valid verdict BOUND to this escrow: release, permissionless.
    # Mock validator set = 3 → minRouteAttestations = 2 (V3 parity 3→2).
    set_verdict(route_ok, escrow_id, 2, True, 900_000, 800_000)
    dest_before = w3.eth.get_balance(dest)
    escrow.functions.release(escrow_id, route_ok).transact({"from": other, "gas": 500_000})
    check("release sends funds to destination",
          w3.eth.get_balance(dest) - dest_before == w3.to_wei(1, "ether"))
    check("escrow terminal RELEASED", escrow.functions.escrow_state(escrow_id).call() == 2)

    # 2e. M3 verdict-replay: the SAME fresh safe verdict must NOT release a
    # second (different) escrow even though it is still fresh + quorum-safe.
    txh = escrow.functions.lock(
        w3.keccak(text="intent-C"), w3.keccak(text="entity-C"), 10, dest
    ).transact({"from": acct, "value": w3.to_wei(3, "ether"), "gas": 500_000})
    eid3 = w3.eth.wait_for_transaction_receipt(txh).logs[0]["topics"][1]
    check("replaying the verdict on a second escrow reverts (M3)",
          must_revert(w3, escrow.functions.release(eid3, route_ok), other))

    print("\n3) terminal-state guards")
    check("double release reverts",
          must_revert(w3, escrow.functions.release(escrow_id, route_ok), other))

    print("\n4) revert_on_timeout()")
    txh = escrow.functions.lock(
        w3.keccak(text="intent-B"), w3.keccak(text="entity-B"), 3, dest
    ).transact({"from": acct, "value": w3.to_wei(2, "ether"), "gas": 500_000})
    eid2 = w3.eth.wait_for_transaction_receipt(txh).logs[0]["topics"][1]

    # 4a. before timeout → fail
    w3.eth.send_transaction({"from": acct, "to": other, "value": 1})
    check("revert before timeout reverts",
          must_revert(w3, escrow.functions.revert_on_timeout(eid2), other))

    # 4b. after timeout → refund to FUNDER (locker), not destination
    for _ in range(4):
        w3.eth.send_transaction({"from": acct, "to": other, "value": 1})
    funder_before = w3.eth.get_balance(acct)
    dest_before = w3.eth.get_balance(dest)
    escrow.functions.revert_on_timeout(eid2).transact({"from": other, "gas": 300_000})
    check("timeout refunds funder", w3.eth.get_balance(acct) > funder_before)
    check("timeout does NOT pay destination", w3.eth.get_balance(dest) == dest_before)
    check("escrow terminal REVERTED", escrow.functions.escrow_state(eid2).call() == 3)

    check("double revert reverts",
          must_revert(w3, escrow.functions.revert_on_timeout(eid2), other))

    print("\n5) zero-governance surface")
    abi_fns = {f["name"] for f in escrow_abi if f.get("type") == "function"}
    check("no owner/admin/pause functions",
          not (abi_fns & {"owner", "setOwner", "pause", "unpause",
                          "setRelayer", "sweep", "withdraw", "renounceOwnership"}))
    check("only spec surface exposed",
          abi_fns == {"lock", "release", "revert_on_timeout",
                      "escrow_state", "escrows", "trion_oracle"}, str(abi_fns))

    # ── 6) M-03: dynamic quorum from oracle live state ────────────────────────
    print("\n6) M-03 — release quorum derived from minRouteAttestations() (live set)")

    def lock_new(label, value_eth=1):
        txh = escrow.functions.lock(
            w3.keccak(text=f"intent-{label}"), w3.keccak(text=f"entity-{label}"), 10, dest
        ).transact({"from": acct, "value": w3.to_wei(value_eth, "ether"), "gas": 500_000})
        rcpt = w3.eth.wait_for_transaction_receipt(txh)
        return rcpt.logs[0]["topics"][1]

    # 6a. valid release under the dynamic quorum (set of 3 → required 2)
    oracle.functions.set_validator_count(3).transact({"from": acct})
    check("mock quorum view: 3 validators → 2 required",
          oracle.functions.minRouteAttestations().call() == 2)
    e6a = lock_new("F")
    route6a = w3.keccak(text="route-6a")
    set_verdict(route6a, e6a, 2, True, 900_000, 800_000)
    dest_before = w3.eth.get_balance(dest)
    escrow.functions.release(e6a, route6a).transact({"from": other, "gas": 500_000})
    check("6a valid release passes under dynamic quorum",
          w3.eth.get_balance(dest) - dest_before == w3.to_wei(1, "ether"))

    # 6b. THE M-03 REGRESSION: 7-validator set → required 5. The old code
    # (attestations >= 2) released here; the new code must NOT.
    oracle.functions.set_validator_count(7).transact({"from": acct})
    check("mock quorum view: 7 validators → 5 required",
          oracle.functions.minRouteAttestations().call() == 5)
    e6b = lock_new("G")
    route6b = w3.keccak(text="route-6b")
    set_verdict(route6b, e6b, 2, True, 900_000, 800_000)  # the 2-attestation attack
    check("6b M-03 regression: 2 attestations on a 5-quorum route REVERT",
          must_revert(w3, escrow.functions.release(e6b, route6b), other))
    set_verdict(route6b, e6b, 4, True, 900_000, 800_000)
    check("6b 4 attestations (still < 5) REVERT",
          must_revert(w3, escrow.functions.release(e6b, route6b), other))
    set_verdict(route6b, e6b, 5, True, 900_000, 800_000)
    dest_before = w3.eth.get_balance(dest)
    escrow.functions.release(e6b, route6b).transact({"from": other, "gas": 500_000})
    check("6b exactly 5 attestations releases (boundary)",
          w3.eth.get_balance(dest) - dest_before == w3.to_wei(1, "ether"))

    # 6c. mid-flight set growth: the SAME verdict that sufficed at n=7
    # (required 5) no longer suffices once the live set grows to 12
    # (required 8) — the gate consults LIVE state, not a cached floor.
    oracle.functions.set_validator_count(7).transact({"from": acct})
    e6c = lock_new("H")
    route6c = w3.keccak(text="route-6c")
    set_verdict(route6c, e6c, 5, True, 900_000, 800_000)
    oracle.functions.set_validator_count(12).transact({"from": acct})
    check("mock quorum view: 12 validators → 8 required",
          oracle.functions.minRouteAttestations().call() == 8)
    check("6c 5 attestations after set growth to 12 (required 8) REVERT",
          must_revert(w3, escrow.functions.release(e6c, route6c), other))
    set_verdict(route6c, e6c, 8, True, 900_000, 800_000)
    dest_before = w3.eth.get_balance(dest)
    escrow.functions.release(e6c, route6c).transact({"from": other, "gas": 500_000})
    check("6c 8 attestations releases after growth",
          w3.eth.get_balance(dest) - dest_before == w3.to_wei(1, "ether"))

    # ── 7) quorum-view formula parity with TRIONOracleV3.sol ──────────────────
    print("\n7) minRouteAttestations() formula parity (V3 docstring table)")
    # V3: 1→2, 2→2, 3→2, 4→3, 5→4, 6→4, 7→5, 9→6, 12→8
    parity_ok = True
    for n, expected in [(1, 2), (2, 2), (3, 2), (4, 3), (5, 4), (6, 4), (7, 5), (9, 6), (12, 8)]:
        oracle.functions.set_validator_count(n).transact({"from": acct})
        got = oracle.functions.minRouteAttestations().call()
        if got != expected:
            parity_ok = False
            print(f"    MISMATCH: validatorCount={n} expected {expected} got {got}")
    check("7 mock quorum view matches V3 table exactly", parity_ok)

    # 6d. misbehaving oracle reports a SUB-FLOOR quorum (1) — the escrow must
    # clamp to the hard floor of 2 (max(2, view)), never degrade.
    print("\n6d) sub-floor oracle report is clamped to the hard floor")
    oracle.functions.report_sub_floor_quorum().transact({"from": acct})
    check("mock quorum view: broken oracle reports 1",
          oracle.functions.minRouteAttestations().call() == 1)
    e6d = lock_new("I")
    route6d = w3.keccak(text="route-6d")
    set_verdict(route6d, e6d, 1, True, 900_000, 800_000)
    check("6d 1 attestation under a sub-floor oracle report REVERT (clamp)",
          must_revert(w3, escrow.functions.release(e6d, route6d), other))
    set_verdict(route6d, e6d, 2, True, 900_000, 800_000)
    dest_before = w3.eth.get_balance(dest)
    escrow.functions.release(e6d, route6d).transact({"from": other, "gas": 500_000})
    check("6d 2 attestations still release under the clamp",
          w3.eth.get_balance(dest) - dest_before == w3.to_wei(1, "ether"))

    # 6e. INTERFACE MISMATCH FAILS CLOSED: an oracle without the
    # minRouteAttestations() view (the pre-M-03 interface — exactly the mock
    # this suite used before the fix, whose 2-attestation verdict released
    # escrows in test 2d) can NO LONGER release anything. Vyper has no
    # try/catch: the missing view reverts the whole release. This kills the
    # M-05 fallback class (silent degradation to a static floor) in the
    # Vyper tier.
    print("\n6e) interface mismatch (oracle without the quorum view) fails CLOSED")
    legacy = deploy(w3, legacy_abi, legacy_bytecode, acct)
    escrow2 = deploy(w3, escrow_abi, escrow_bytecode, acct, (legacy.address,))
    txh = escrow2.functions.lock(
        w3.keccak(text="intent-L"), w3.keccak(text="entity-L"), 10, dest
    ).transact({"from": acct, "value": w3.to_wei(1, "ether"), "gas": 500_000})
    e6e = w3.eth.wait_for_transaction_receipt(txh).logs[0]["topics"][1]
    route6e = w3.keccak(text="route-6e")
    now6e = w3.eth.get_block("latest")["timestamp"]
    legacy.functions.set_verdict(route6e, e6e, 2, True, 900_000, 800_000,
                                 now6e).transact({"from": acct})
    # sanity: the verdict itself is perfect (bound, safe, fresh, coherent,
    # and 2 attestations — the very tuple that released under the OLD code)
    binding = legacy.functions.routeBinding(route6e).call()
    check("6e legacy oracle verdict is otherwise perfect",
          binding[0] == e6e and binding[1] == 2 and binding[2]
          and binding[3] >= binding[4] and now6e - binding[5] <= 300)
    check("6e release against a view-less oracle REVERTS (fail closed, no floor fallback)",
          must_revert(w3, escrow2.functions.release(e6e, route6e), other))
    check("6e escrow stays HOLDING after the failed release",
          escrow2.functions.escrow_state(e6e).call() == 1)

    print(f"\n═══ RESULT: {len(PASSED)} passed, {len(FAILED)} failed ═══")
    if FAILED:
        print("FAILED:", FAILED)
        sys.exit(1)
    print("BTCP_ESCROW.vy complies with whitepaper §14.3 semantics on real EVM execution.")
    print("M-03 CLOSED: release quorum derives from the oracle's live validator state; "
          "interface mismatch fails closed.")


if __name__ == "__main__":
    main()
