"""
TRION × 0G — Full Stack Deployment Script
Compiles AkashicProof.sol, deploys to 0G Chain, saves ABI + address.
Run: python3 scripts/deploy_and_activate.py
"""
import os
import sys
import json
import time
from pathlib import Path

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
import sys; sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "zg"))
from zg_config import ZG

print("╔══════════════════════════════════════════════════════╗")
print("║  TRION × 0G — AkashicProof Deployment               ║")
print("╚══════════════════════════════════════════════════════╝")

# ── Step 1: Install and configure solc ───────────────────────────
print("\n[1/4] Setting up Solidity compiler...")
from solcx import install_solc, compile_source, set_solc_version
install_solc("0.8.24", show_progress=False)
set_solc_version("0.8.24")
print("      ✓ solc 0.8.24 ready")

# ── Step 2: Compile AkashicProof.sol ─────────────────────────────
print("\n[2/4] Compiling AkashicProof.sol...")
sol_path = Path("contracts/AkashicProof.sol")
source   = sol_path.read_text()

compiled = compile_source(
    source,
    output_values=["abi", "bin"],
    solc_version="0.8.24",
    optimize=True,
    optimize_runs=200,
)

contract_id  = "<stdin>:AkashicProof"
contract_ifc = compiled[contract_id]
abi          = contract_ifc["abi"]
bytecode     = "0x" + contract_ifc["bin"]

print(f"      ✓ Compiled: ABI has {len(abi)} entries, bytecode {len(bytecode)//2} bytes")

# Save ABI to canonical artifact path (used by sync daemon + API)
# audit fix (ABI-1): anchor to repo root (was CWD-relative — failed when the
# script was invoked from outside the repo root).
_REPO_ROOT = Path(__file__).resolve().parent.parent
artifact_dir = _REPO_ROOT / "artifacts" / "contracts" / "AkashicProof.sol"
artifact_dir.mkdir(parents=True, exist_ok=True)
artifact = {"abi": abi, "bytecode": bytecode, "contractName": "AkashicProof"}
artifact_path = artifact_dir / "AkashicProof.json"
artifact_path.write_text(json.dumps(artifact, indent=2))
print(f"      ✓ ABI saved: {artifact_path}")

# ── Step 3: Deploy to 0G Chain ────────────────────────────────────
print(f"\n[3/4] Deploying to 0G Chain ({ZG.RPC})...")
from web3 import Web3
from web3.middleware import ExtraDataToPOAMiddleware

private_key = ZG.PRIVATE_KEY
if not private_key:
    print("ERROR: ZG_PRIVATE_KEY not set")
    sys.exit(1)

w3 = Web3(Web3.HTTPProvider(ZG.RPC))
w3.middleware_onion.inject(ExtraDataToPOAMiddleware, layer=0)

if not w3.is_connected():
    print(f"ERROR: Cannot connect to {ZG.RPC}")
    sys.exit(1)

account   = w3.eth.account.from_key(private_key)
deployer  = account.address
balance   = w3.eth.get_balance(deployer)
block     = w3.eth.block_number

print(f"      Deployer:  {deployer}")
print(f"      Balance:   {w3.from_wei(balance, 'ether'):.6f} OG")
print(f"      Block:     {block:,}")

if balance == 0:
    print("ERROR: Deployer has 0 balance. Get testnet tokens from 0G faucet.")
    sys.exit(1)

contract   = w3.eth.contract(abi=abi, bytecode=bytecode)
nonce      = w3.eth.get_transaction_count(deployer)
gas_price  = w3.eth.gas_price

deploy_tx  = contract.constructor().build_transaction({
    "from":     deployer,
    "nonce":    nonce,
    "gas":      3_000_000,
    "gasPrice": gas_price,
})

signed  = account.sign_transaction(deploy_tx)
tx_hash = w3.eth.send_raw_transaction(signed.raw_transaction)
print(f"      Tx sent:   {tx_hash.hex()}")
print("      Waiting for confirmation...")

receipt  = w3.eth.wait_for_transaction_receipt(tx_hash, timeout=180)
address  = receipt["contractAddress"]
gas_used = receipt["gasUsed"]

print(f"      ✓ Deployed: {address}")
print(f"      Gas used:  {gas_used:,}")
print(f"      Explorer:  https://chainscan-newton.0g.ai/address/{address}")

# ── Step 4: Save deployment record ───────────────────────────────
print("\n[4/4] Saving deployment record...")
Path("0g-state/proofs").mkdir(parents=True, exist_ok=True)

record = {
    "contractAddress": address,
    "deployerAddress": deployer,
    "txHash":          tx_hash.hex(),
    "chainId":         ZG.CHAIN_ID,
    "network":         ZG.NETWORK,
    "rpc":             ZG.RPC,
    "deployedAt":      time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
    "blockNumber":     receipt["blockNumber"],
    "gasUsed":         gas_used,
    "explorerUrl":     f"https://chainscan-newton.0g.ai/address/{address}",
    "abiPath":         str(artifact_path),
}
record_path = "0g-state/proofs/contract_deployment.json"
Path(record_path).write_text(json.dumps(record, indent=2))
print(f"      ✓ Record:   {record_path}")

# Quick verify: call getFullProof()
deployed = w3.eth.contract(address=address, abi=abi)
proof    = deployed.functions.getFullProof().call()
print(f"\n      Contract verification:")
print(f"        Protocol: {proof[0]}")
print(f"        Version:  {proof[1]}")
print(f"        Deployed: {proof[2]}")
print(f"        Repo:     {proof[9]}")

print(f"""
╔══════════════════════════════════════════════════════╗
║  ✓ AkashicProof DEPLOYED & VERIFIED                  ║
║                                                      ║
║  Address:  {address[:20]}...          ║
║  Chain:    0G Testnet (chainId {ZG.CHAIN_ID})           ║
║  Explorer: chainscan-newton.0g.ai                    ║
╚══════════════════════════════════════════════════════╝

Set this env var to activate onchain proof updates:
  ZG_AKASHIC_CONTRACT={address}
""")
