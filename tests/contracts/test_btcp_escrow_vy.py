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


MOCK_ORACLE = """
# @version ^0.3.10
# Minimal TRION oracle mock for BTCP_ESCROW tests — verifyExecution is
# configurable per txId. NOT for production.

struct Verdict:
    is_safe:    bool
    coherence:  uint32
    threshold:  uint32

verdicts: public(HashMap[bytes32, Verdict])

@external
def set_verdict(tx_id: bytes32, is_safe: bool, coherence: uint32, threshold: uint32):
    self.verdicts[tx_id] = Verdict({
        is_safe:   is_safe,
        coherence: coherence,
        threshold: threshold,
    })

@external
@view
def verifyExecution(txId: bytes32) -> (bool, uint32, uint32):
    v: Verdict = self.verdicts[txId]
    return v.is_safe, v.coherence, v.threshold
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


def main():
    t = EthereumTester()
    w3 = Web3(EthereumTesterProvider(t))
    acct = w3.eth.accounts[0]
    dest = w3.eth.accounts[1]
    other = w3.eth.accounts[2]

    # ── compile ──
    oracle_abi, oracle_bytecode = compile_vy_from_src(MOCK_ORACLE)
    escrow_abi, escrow_bytecode = compile_vy(os.path.join(REPO, "contracts/vyper/BTCP_ESCROW.vy"))

    # ── deploy mock oracle ──
    oracle = w3.eth.contract(abi=oracle_abi, bytecode=oracle_bytecode)
    tx = oracle.constructor().transact({"from": acct, "gas": 2_000_000})
    oracle = w3.eth.contract(address=w3.eth.wait_for_transaction_receipt(tx).contractAddress, abi=oracle_abi)

    # ── deploy escrow bound to oracle ──
    escrow = w3.eth.contract(abi=escrow_abi, bytecode=escrow_bytecode)
    tx = escrow.constructor(oracle.address).transact({"from": acct, "gas": 3_000_000})
    escrow = w3.eth.contract(address=w3.eth.wait_for_transaction_receipt(tx).contractAddress, abi=escrow_abi)

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

    print("\n2) release() — oracle-gated")
    route_ok = w3.keccak(text="route-ok")
    route_low = w3.keccak(text="route-low")
    route_unsafe = w3.keccak(text="route-unsafe")

    # 2a. release with NO verdict set → must fail (fail-closed)
    check("release with no oracle verdict reverts",
          must_revert(w3, escrow.functions.release(escrow_id, w3.keccak(text="no-verdict")), other))

    # 2b. unsafe verdict → fail
    oracle.functions.set_verdict(route_unsafe, False, 900_000, 800_000).transact({"from": acct})
    check("release with is_safe=False reverts",
          must_revert(w3, escrow.functions.release(escrow_id, route_unsafe), other))

    # 2c. safe but coherence < threshold → fail
    oracle.functions.set_verdict(route_low, True, 700_000, 800_000).transact({"from": acct})
    check("release with coherence < threshold reverts",
          must_revert(w3, escrow.functions.release(escrow_id, route_low), other))

    # 2d. fully valid verdict → release to destination, permissionless caller
    oracle.functions.set_verdict(route_ok, True, 900_000, 800_000).transact({"from": acct})
    dest_before = w3.eth.get_balance(dest)
    escrow.functions.release(escrow_id, route_ok).transact({"from": other, "gas": 500_000})
    check("release sends funds to destination",
          w3.eth.get_balance(dest) - dest_before == w3.to_wei(1, "ether"))
    check("escrow terminal RELEASED", escrow.functions.escrow_state(escrow_id).call() == 2)

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

    print(f"\n═══ RESULT: {len(PASSED)} passed, {len(FAILED)} failed ═══")
    if FAILED:
        print("FAILED:", FAILED)
        sys.exit(1)
    print("BTCP_ESCROW.vy complies with whitepaper §14.3 semantics on real EVM execution.")


if __name__ == "__main__":
    main()
