"""
BTCPEscrow.sol — oracle-gated release compliance test (real EVM execution).

Complements test_btcp_escrow_vy.py: exercises the SOLIDITY tier's
setTRIONOracle binding + _consensusGate (H1 route-binding, M2/M4 quorum,
unbound trusted-relayer mode).

Run: python3 tests/contracts/test_btcp_escrow_sol.py
"""

import os
import sys

from web3 import Web3
from web3.providers.eth_tester import EthereumTesterProvider
from eth_tester import EthereumTester
import solcx

REPO = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
SOLC_VERSION = "0.8.24"

PASSED = []
FAILED = []


def check(name, cond, detail=""):
    (PASSED if cond else FAILED).append(name)
    print(f"  {'OK' if cond else 'FAIL'} {name}" + (f" — {detail}" if detail and not cond else ""))


def must_revert(w3, fn_call, sender):
    txh = fn_call.transact({"from": sender, "gas": 2_000_000})
    rcpt = w3.eth.wait_for_transaction_receipt(txh)
    return rcpt["status"] == 0


# Minimal mock of the TRIONOracleV3 views the escrow consumes.
MOCK_ORACLE = """
// SPDX-License-Identifier: MIT
pragma solidity ^0.8.24;

contract MockTRIONOracle {
    struct Verdict {
        bytes32 anchorBH;
        uint256 attestationCount;
        bool isSafe;
        uint256 coherence;
        uint256 threshold;
        uint256 ts;
    }
    mapping(bytes32 => Verdict) public verdicts;

    function setVerdict(bytes32 routeId, bytes32 anchorBH, uint256 count,
                        bool isSafe, uint256 coherence, uint256 threshold, uint256 ts) external {
        verdicts[routeId] = Verdict(anchorBH, count, isSafe, coherence, threshold, ts);
    }

    function verifyExecution(bytes32 txId) external view
        returns (bool isSafe, uint32 coherence, uint32 threshold)
    {
        Verdict memory v = verdicts[txId];
        return (v.isSafe, uint32(v.coherence), uint32(v.threshold));
    }

    function routeBinding(bytes32 routeId) external view
        returns (bytes32 anchorBH, uint256 attestationCount, bool isSafe,
                 uint256 coherence, uint256 threshold, uint256 timestamp)
    {
        Verdict memory v = verdicts[routeId];
        return (v.anchorBH, v.attestationCount, v.isSafe, v.coherence, v.threshold, v.ts);
    }

    // M-05: the escrow pins the dynamic route-quorum view at BIND time
    // (setTRIONOracle reverts without it). V3 formula: max(2, ceil(2n/3)).
    uint256 public validatorCount = 2;  // quorum = 2: keeps the count-calibrated cases below meaningful
    function minRouteAttestations() external view returns (uint256) {
        uint256 n = validatorCount;
        uint256 twoThirds = (2 * n + 2) / 3;
        return twoThirds > 2 ? twoThirds : 2;
    }
}
"""


def main():
    t = EthereumTester()
    w3 = Web3(EthereumTesterProvider(t))
    acct = w3.eth.accounts[0]     # owner / relayer
    dest = w3.eth.accounts[1]
    other = w3.eth.accounts[2]

    solcx.install_solc(SOLC_VERSION)
    escrow_out = solcx.compile_files(
        [os.path.join(REPO, "contracts/solidity/BTCPEscrow.sol")],
        output_values=["abi", "bin"], optimize=True, solc_version=SOLC_VERSION, via_ir=True)
    oracle_out = solcx.compile_source(MOCK_ORACLE, output_values=["abi", "bin"],
                                      solc_version=SOLC_VERSION)

    esc_key = [k for k in escrow_out if k.endswith(":BTCPEscrow")][0]
    esc_abi, esc_bin = escrow_out[esc_key]["abi"], escrow_out[esc_key]["bin"]
    or_key = list(oracle_out.keys())[0]
    or_abi, or_bin = oracle_out[or_key]["abi"], oracle_out[or_key]["bin"]

    oracle = w3.eth.contract(abi=or_abi, bytecode=or_bin)
    tx = oracle.constructor().transact({"from": acct, "gas": 3_000_000})
    oracle = w3.eth.contract(address=w3.eth.wait_for_transaction_receipt(tx).contractAddress, abi=or_abi)

    escrow = w3.eth.contract(abi=esc_abi, bytecode=esc_bin)
    tx = escrow.constructor().transact({"from": acct, "gas": 5_000_000})
    escrow = w3.eth.contract(address=w3.eth.wait_for_transaction_receipt(tx).contractAddress, abi=esc_abi)

    print("\n1) lock + settlement check (trusted-relayer mode, oracle unbound)")
    escrow_id = w3.keccak(text="escrow-S1")
    route_id = w3.keccak(text="route-S1")
    escrow.functions.lockEscrow(
        escrow_id, route_id, w3.keccak(text="entity-S"), dest,
        800_000, 1000, b"\x00" * 32
    ).transact({"from": acct, "value": w3.to_wei(1, "ether"), "gas": 2_000_000})
    escrow.functions.verifySettlementCheck(escrow_id, w3.keccak(text="check")).transact({"from": acct})

    # Unbound mode: release works with caller-supplied coherence (documented
    # trusted-relayer model).
    escrow.functions.releaseEscrow(escrow_id, w3.keccak(text="execBH"), 900_000).transact(
        {"from": acct, "gas": 1_000_000})
    # split getter (via-ir stack budget): state is field 6 of getEscrowCore
    core = escrow.functions.getEscrowCore(escrow_id).call()
    check("unbound mode releases via trusted relayer",
          core[6] == 3)
    # state field index verified below via a second lock

    # INV-003 follow-on 2 — lock-side tightening-only floor (fail-fast):
    # sub-floor min_coherence is rejected AT LOCK (Move/Cairo/SVM/TON
    # parity); exactly 550_000 (0.55 ×1e6) is accepted. Still unbound
    # here so the cleanup release uses the trusted-relayer path.
    esc_floor = w3.keccak(text="escrow-floor")
    check("lock with sub-floor min_coherence reverts (INV-003 tighten-only)",
          must_revert(w3, escrow.functions.lockEscrow(
              esc_floor, route_id, w3.keccak(text="entity-F"), dest,
              549_999, 1000, b"\x00" * 32), acct))
    escrow.functions.lockEscrow(
        esc_floor, route_id, w3.keccak(text="entity-F"), dest,
        550_000, 1000, b"\x00" * 32
    ).transact({"from": acct, "value": w3.to_wei(1, "ether"), "gas": 2_000_000})
    core_floor = escrow.functions.getEscrowCore(esc_floor).call()
    check("lock at exactly the 0.55 floor accepted (HOLDING)",
          core_floor[0] == esc_floor and core_floor[6] == 1)
    # restore a clean state for the section below (release the floor escrow)
    escrow.functions.verifySettlementCheck(esc_floor, w3.keccak(text="checkF")).transact({"from": acct})
    escrow.functions.releaseEscrow(esc_floor, w3.keccak(text="bhF"), 900_000).transact({"from": acct, "gas": 1_000_000})

    print("\n2) one-way oracle binding")
    escrow.functions.setTRIONOracle(oracle.address).transact({"from": acct})
    check("oracle bound", escrow.functions.trionOracle().call() == oracle.address)
    check("re-binding reverts",
          must_revert(w3, escrow.functions.setTRIONOracle(oracle.address), acct))
    check("binding zero address reverts",
          must_revert(w3, escrow.functions.setTRIONOracle("0x" + "00" * 20), acct))

    print("\n3) H1 — route verdict must be BOUND to the escrow")
    esc_id2 = w3.keccak(text="escrow-S2")
    route2 = w3.keccak(text="route-S2")
    escrow.functions.lockEscrow(
        esc_id2, route2, w3.keccak(text="entity-S2"), dest,
        800_000, 10000, b"\x00" * 32
    ).transact({"from": acct, "value": w3.to_wei(1, "ether"), "gas": 2_000_000})
    escrow.functions.verifySettlementCheck(esc_id2, w3.keccak(text="check2")).transact({"from": acct})

    now = w3.eth.get_block("latest")["timestamp"]

    # 3a. A fresh quorum-safe verdict for a DIFFERENT escrow id (route spoof)
    oracle.functions.setVerdict(
        route2, w3.keccak(text="someone-else"), 3, True, 900_000, 800_000, now
    ).transact({"from": acct})
    check("H1: foreign-bound verdict reverts release",
          must_revert(w3, escrow.functions.releaseEscrow(esc_id2, w3.keccak(text="bh"), 900_000), acct))

    # 3b. Verdict bound to THIS escrow but below quorum (1 attestation)
    oracle.functions.setVerdict(
        route2, esc_id2, 1, True, 900_000, 800_000, now
    ).transact({"from": acct})
    check("quorum=1 verdict reverts release",
          must_revert(w3, escrow.functions.releaseEscrow(esc_id2, w3.keccak(text="bh"), 900_000), acct))

    # 3c. Safe, bound, quorum met — releases
    oracle.functions.setVerdict(
        route2, esc_id2, 2, True, 900_000, 800_000, now
    ).transact({"from": acct})
    dest_before = w3.eth.get_balance(dest)
    escrow.functions.releaseEscrow(esc_id2, w3.keccak(text="bh"), 900_000).transact(
        {"from": acct, "gas": 1_000_000})
    check("bound verdict releases to destination",
          w3.eth.get_balance(dest) - dest_before == w3.to_wei(1, "ether"))

    print("\n4) stale verdict + coherence gates")
    esc_id3 = w3.keccak(text="escrow-S3")
    route3 = w3.keccak(text="route-S3")
    escrow.functions.lockEscrow(
        esc_id3, route3, w3.keccak(text="entity-S3"), dest,
        800_000, 10000, b"\x00" * 32
    ).transact({"from": acct, "value": w3.to_wei(1, "ether"), "gas": 2_000_000})
    escrow.functions.verifySettlementCheck(esc_id3, w3.keccak(text="check3")).transact({"from": acct})

    oracle.functions.setVerdict(
        route3, esc_id3, 2, True, 900_000, 800_000, now - 400
    ).transact({"from": acct})
    check("stale verdict (400s) reverts release",
          must_revert(w3, escrow.functions.releaseEscrow(esc_id3, w3.keccak(text="bh"), 900_000), acct))

    oracle.functions.setVerdict(
        route3, esc_id3, 2, True, 700_000, 800_000, now
    ).transact({"from": acct})
    check("oracle coherence < threshold reverts release",
          must_revert(w3, escrow.functions.releaseEscrow(esc_id3, w3.keccak(text="bh"), 900_000), acct))

    oracle.functions.setVerdict(
        route3, esc_id3, 2, False, 900_000, 800_000, now
    ).transact({"from": acct})
    check("unsafe verdict reverts release",
          must_revert(w3, escrow.functions.releaseEscrow(esc_id3, w3.keccak(text="bh"), 900_000), acct))

    print(f"\n═══ RESULT: {len(PASSED)} passed, {len(FAILED)} failed ═══")
    if FAILED:
        print("FAILED:", FAILED)
        sys.exit(1)
    print("BTCPEscrow oracle gate (H1 binding, quorum, freshness) verified on real EVM.")


def test_full_battery_runs_clean():
    """pytest entry point (battery-integrity fix, follow-on-2 loop): the
    script battery must run clean whenever the pytest contracts battery
    runs — main() exits non-zero on any check() failure. Script-mode
    ("python3 tests/contracts/<file>.py") keeps working unchanged."""
    main()


if __name__ == "__main__":
    main()
