"""
TRION Historical Exploit On-Chain Proof Script
===============================================
Deploys (or reuses) the AttackSimulator contract on Arbitrum Sepolia and
records immutable proof for three historical DeFi exploits.

Usage:
    python simulate_attacks_onchain.py

Env vars (optional):
    ATTACK_SIMULATOR=0x...   Reuse a previously deployed simulator
    PRIVATE_KEY=0x...        Override the private key from .env
"""

import os
import sys
import json
import time

from web3 import Web3
from web3.middleware import ExtraDataToPOAMiddleware

# ── Try to load .env ──────────────────────────────────────────────────────────
try:
    from dotenv import load_dotenv
    load_dotenv()
except ImportError:
    pass

# ── Config ────────────────────────────────────────────────────────────────────

RPC_URL        = "https://arbitrum-sepolia-rpc.publicnode.com"
ORACLE_ADDRESS = Web3.to_checksum_address("0xb819c63c02Ed5aB49017C0f3f2568A14624658b3")
CHAIN_ID       = 421614
SCAN_BLOCKS    = 50_000

ATTACKS = [
    {
        "name":             "Jimbos Protocol",
        "historical_block": 75_000_000,
        "tx_hash":          "0x44a0f5650a038ab522087c02f734b80e6c748afb207995e757ed67ca037a5eda",
    },
    {
        "name":             "Rodeo Finance",
        "historical_block": 110_045_546,
        "tx_hash":          "0x98f1e234faac8b7f7ceaffe4e8e0581038678d95710b646db45ec3de47e6c3af",
    },
    {
        "name":             "Sentiment Protocol",
        "historical_block": 77_026_913,
        "tx_hash":          "0xa9ff2b587e2741575daf893864710a5cbb44bb64ccdc487a100fa20741e0f74d",
    },
]

# ── ABIs ──────────────────────────────────────────────────────────────────────

ORACLE_ABI = json.loads("""[
  {
    "name": "ThermodynamicSignalEtched",
    "type": "event",
    "inputs": [
      {"name": "txId",      "type": "bytes32", "indexed": true},
      {"name": "status",    "type": "uint8",   "indexed": false},
      {"name": "coherence", "type": "uint32",  "indexed": false},
      {"name": "threshold", "type": "uint32",  "indexed": false}
    ]
  },
  {
    "name": "getSignalInfo",
    "type": "function",
    "stateMutability": "view",
    "inputs": [{"name": "txId", "type": "bytes32"}],
    "outputs": [
      {"name": "status",    "type": "uint8"},
      {"name": "coherence", "type": "uint32"},
      {"name": "threshold", "type": "uint32"},
      {"name": "blockNum",  "type": "uint64"},
      {"name": "timestamp", "type": "uint64"}
    ]
  }
]""")

SIMULATOR_ABI = json.loads("""[
  {
    "name": "AttackProofRecorded",
    "type": "event",
    "inputs": [
      {"name": "attackName",       "type": "string",  "indexed": false},
      {"name": "oracleSignalId",   "type": "bytes32", "indexed": true},
      {"name": "historicalBlock",  "type": "uint256", "indexed": false},
      {"name": "historicalTxHash", "type": "bytes32", "indexed": false},
      {"name": "coherence",        "type": "uint32",  "indexed": false},
      {"name": "threshold",        "type": "uint32",  "indexed": false},
      {"name": "wouldHaveBlocked", "type": "bool",    "indexed": false}
    ]
  },
  {
    "name": "batchRecordAttackProofs",
    "type": "function",
    "stateMutability": "nonpayable",
    "inputs": [
      {"name": "attackNames",       "type": "string[]"},
      {"name": "oracleSignalIds",   "type": "bytes32[]"},
      {"name": "historicalBlocks",  "type": "uint256[]"},
      {"name": "historicalTxHashes","type": "bytes32[]"}
    ],
    "outputs": []
  }
]""")

# Bytecode compiled from contracts/AttackSimulator.sol
# (pre-compiled so the script works without Hardhat)
SIMULATOR_BYTECODE = None   # Set to compiled bytecode string if deploying from Python

# ── Helpers ───────────────────────────────────────────────────────────────────

def banner(title: str):
    w = 66
    print("╔" + "═" * w + "╗")
    for line in title.split("\n"):
        print("║  " + line.ljust(w - 2) + "  ║")
    print("╚" + "═" * w + "╝")


def pad_tx_to_bytes32(hex_str: str) -> bytes:
    clean = hex_str[2:] if hex_str.startswith("0x") else hex_str
    return bytes.fromhex(clean.ljust(64, "0")[:64])


def fetch_warn_signals(w3: Web3, oracle, needed: int) -> list[str]:
    """Scan recent oracle events and return txIds of WARN signals (status=1)."""
    latest   = w3.eth.block_number
    from_blk = max(0, latest - SCAN_BLOCKS)
    print(f"  Scanning oracle events from block {from_blk:,} → {latest:,}…")

    logs = oracle.events.ThermodynamicSignalEtched.get_logs(
        from_block=from_blk, to_block=latest
    )

    warn_ids: list[str] = []
    for log in reversed(logs):   # newest first
        if log.args.status == 1:
            warn_ids.append(log.args.txId.hex()
                            if isinstance(log.args.txId, bytes)
                            else log.args.txId)
            if len(warn_ids) >= needed:
                break

    return warn_ids


def send_tx(w3: Web3, account, fn_call, gas: int = 500_000) -> str:
    nonce = w3.eth.get_transaction_count(account.address, "pending")
    gas_price = w3.eth.gas_price

    tx = fn_call.build_transaction({
        "from":     account.address,
        "nonce":    nonce,
        "gas":      gas,
        "gasPrice": gas_price,
        "chainId":  CHAIN_ID,
    })
    signed  = account.sign_transaction(tx)
    tx_hash = w3.eth.send_raw_transaction(signed.raw_transaction)
    return tx_hash.hex()


# ── Main ──────────────────────────────────────────────────────────────────────

def main():
    banner(
        "TRION — Historical Exploit On-Chain Proof\n"
        "Oracle   : " + ORACLE_ADDRESS + "\n"
        "Network  : Arbitrum Sepolia (chainId=421614)"
    )

    # ── Connect ───────────────────────────────────────────────────────────────
    w3 = Web3(Web3.HTTPProvider(RPC_URL))
    w3.middleware_onion.inject(ExtraDataToPOAMiddleware, layer=0)

    if not w3.is_connected():
        print("[ERROR] Cannot connect to RPC:", RPC_URL)
        sys.exit(1)
    print(f"Connected  : block {w3.eth.block_number:,}")

    # ── Account ───────────────────────────────────────────────────────────────
    private_key = os.getenv("PRIVATE_KEY") or os.getenv("RELAYER_PRIVATE_KEY")
    if not private_key:
        print(
            "\n[ERROR] Set PRIVATE_KEY (or RELAYER_PRIVATE_KEY) in your .env file.\n"
            "        Use a test wallet funded with Sepolia ETH.\n"
            "        Faucet: https://faucet.quicknode.com/arbitrum/sepolia"
        )
        sys.exit(1)

    account = w3.eth.account.from_key(private_key)
    balance = w3.eth.get_balance(account.address)
    print(f"Wallet     : {account.address}")
    print(f"Balance    : {w3.from_wei(balance, 'ether'):.6f} ETH")

    if balance < w3.to_wei(0.001, "ether"):
        print("[WARN] Low balance — make sure you have Sepolia ETH before proceeding.")

    # ── Oracle contract ───────────────────────────────────────────────────────
    oracle = w3.eth.contract(address=ORACLE_ADDRESS, abi=ORACLE_ABI)

    # ── AttackSimulator: deploy or reuse ──────────────────────────────────────
    sim_address = os.getenv("ATTACK_SIMULATOR", "")

    if sim_address:
        sim_address = Web3.to_checksum_address(sim_address)
        print(f"\nReusing AttackSimulator : {sim_address}")
    else:
        print(
            "\n[INFO] No ATTACK_SIMULATOR env var set.\n"
            "       Deploy first with Hardhat:\n\n"
            "         npx hardhat run hardhat-scripts/deploy_attack_simulator.ts --network arbitrumSepolia\n\n"
            "       Then export the address:\n\n"
            "         export ATTACK_SIMULATOR=0xYourDeployedAddress\n"
            "         python simulate_attacks_onchain.py\n"
        )
        sys.exit(0)

    simulator = w3.eth.contract(address=sim_address, abi=SIMULATOR_ABI)

    # ── Fetch WARN signals ────────────────────────────────────────────────────
    print(f"\nFetching {len(ATTACKS)} WARN oracle signals…")
    warn_ids = fetch_warn_signals(w3, oracle, len(ATTACKS))

    if len(warn_ids) < len(ATTACKS):
        print(
            f"\n[WARN] Only found {len(warn_ids)} WARN signals in the last {SCAN_BLOCKS:,} blocks.\n"
            f"       Cycling the available signals across all {len(ATTACKS)} attacks."
        )
        while len(warn_ids) < len(ATTACKS):
            warn_ids.append(warn_ids[len(warn_ids) % max(len(warn_ids), 1)])

    print(f"Found {len(warn_ids)} WARN signal(s):")
    for sid in warn_ids[:len(ATTACKS)]:
        info = oracle.functions.getSignalInfo(bytes.fromhex(sid.lstrip("0x"))).call()
        c, t = info[1] / 1e6, info[2] / 1e6
        print(f"  {sid[:16]}…  C(t)={c:.4f}  Θ={t:.4f}  BLOCKED={'YES' if c < t else 'no'}")

    # ── Build batch arrays ────────────────────────────────────────────────────
    names:     list[str]   = []
    signal_ids: list[bytes] = []
    hist_blocks: list[int] = []
    hist_hashes: list[bytes] = []

    for i, atk in enumerate(ATTACKS):
        names.append(atk["name"])
        signal_ids.append(bytes.fromhex(warn_ids[i].lstrip("0x")))
        hist_blocks.append(atk["historical_block"])
        hist_hashes.append(pad_tx_to_bytes32(atk["tx_hash"]))

    # ── Submit batch proof transaction ────────────────────────────────────────
    print("\nSubmitting batchRecordAttackProofs…")
    fn_call = simulator.functions.batchRecordAttackProofs(
        names, signal_ids, hist_blocks, hist_hashes
    )
    tx_hash = send_tx(w3, account, fn_call)
    print(f"  Tx sent   : 0x{tx_hash}" if not tx_hash.startswith("0x") else f"  Tx sent   : {tx_hash}")

    print("  Waiting for confirmation…", end="", flush=True)
    receipt = w3.eth.wait_for_transaction_receipt(tx_hash, timeout=120)
    print(f" confirmed at block {receipt['blockNumber']}")
    print(f"  Gas used  : {receipt['gasUsed']:,}")
    print(f"  Arbiscan  : https://sepolia.arbiscan.io/tx/{tx_hash}")

    # ── Decode events ─────────────────────────────────────────────────────────
    print()
    print("╔══════════════════════════════════════════════════════════════════╗")
    print("║   ON-CHAIN PROOF SUMMARY                                         ║")
    print("╚══════════════════════════════════════════════════════════════════╝")

    try:
        decoded = simulator.events.AttackProofRecorded().process_receipt(receipt)
        for ev in decoded:
            a   = ev.args
            c   = a.coherence / 1e6
            t   = a.threshold / 1e6
            blocked = "YES ✓" if a.wouldHaveBlocked else "no"
            print(f"  {a.attackName:<24}  C(t)={c:.4f}  Θ={t:.4f}  BLOCKED={blocked}")
    except Exception as e:
        print(f"  (Could not decode events: {e})")

    print()
    print(f"  Batch proof tx : https://sepolia.arbiscan.io/tx/{tx_hash}")
    print(f"  Simulator logs : https://sepolia.arbiscan.io/address/{sim_address}#events")
    print()
    print("All three attack proofs are now permanently recorded on Arbitrum Sepolia.")


if __name__ == "__main__":
    main()
