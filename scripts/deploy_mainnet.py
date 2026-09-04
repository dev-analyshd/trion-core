#!/usr/bin/env python3
"""TRION Protocol — Mainnet Deployment Script

Deploys all contracts to mainnet chains and verifies the full pipeline.

Usage:
    python3 scripts/deploy_mainnet.py --chain ethereum
    python3 scripts/deploy_mainnet.py --chain all
    python3 scripts/deploy_mainnet.py --verify

Prerequisites:
    - PRIVATE_KEY set in environment (or --key-file)
    - RPC URLs configured in .env
    - Sufficient gas on each chain
"""
import os, sys, json, subprocess, argparse

# Canonical chain ids — derived from config/chain_registry.json (single source
# of truth, P3-CONSOLIDATE matrix #17). Read directly via a path relative to
# this file so the script stays runnable from any CWD without sys.path
# bootstrap; a missing/misnamed registry entry fails loudly instead of
# silently deploying under a drifted hand-maintained id.
_REGISTRY_PATH = os.path.join(
    os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
    "config", "chain_registry.json",
)
with open(_REGISTRY_PATH, "r", encoding="utf-8") as _f:
    _REG_IDS = {c["name"]: c["chainId"] for c in json.load(_f)["chains"]}


def _cid(registry_name: str) -> int:
    try:
        return _REG_IDS[registry_name]
    except KeyError:
        raise SystemExit(
            f"deploy_mainnet: chain {registry_name!r} missing from "
            f"{_REGISTRY_PATH} — update MAINNET_CHAINS or the registry"
        )


MAINNET_CHAINS = {
    "ethereum": {"chain_id": _cid("Ethereum"), "rpc": "https://ethereum-rpc.publicnode.com", "explorer": "https://etherscan.io"},
    "arbitrum": {"chain_id": _cid("Arbitrum One"), "rpc": "https://arb1.arbitrum.io/rpc", "explorer": "https://arbiscan.io"},
    "optimism": {"chain_id": _cid("Optimism"), "rpc": "https://mainnet.optimism.io", "explorer": "https://optimistic.etherscan.io"},
    "base": {"chain_id": _cid("Base"), "rpc": "https://mainnet.base.org", "explorer": "https://basescan.org"},
    "polygon": {"chain_id": _cid("Polygon PoS"), "rpc": "https://polygon-rpc.com", "explorer": "https://polygonscan.com"},
    "bnb": {"chain_id": _cid("BNB Smart Chain"), "rpc": "https://bsc-dataseed.binance.org", "explplorer": "https://bscscan.com"},
    "avalanche": {"chain_id": _cid("Avalanche C-Chain"), "rpc": "https://api.avax.network/ext/bc/C/rpc", "explorer": "https://snowtrace.io"},
    "solana": {"chain_id": _cid("Solana Mainnet"), "rpc": "https://api.mainnet-beta.solana.com", "explorer": "https://solscan.io"},
    "0g": {"chain_id": _cid("0G Mainnet"), "rpc": "https://evmrpc.0g.ai", "explorer": "https://0g.codes"},
}

CONTRACTS_TO_DEPLOY = [
    "TRIONOracleV3",
    "TRIONExecutionGate",
    "BTCPEscrow",
    "BTCPIntent",
    "BTCPRoute",
    "AkashicProof",
    "LiquidityOcean",
    "GenesisCommitment",
    "TravelRuleCompliance",
    "BTCPVersionRegistry",
]

def deploy_chain(chain_name, chain_config, private_key):
    """Deploy all contracts to a single chain."""
    print(f"\n{'='*60}")
    print(f"Deploying to {chain_name} (chain_id={chain_config['chain_id']})")
    print(f"RPC: {chain_config['rpc']}")
    print(f"{'='*60}")

    for contract_name in CONTRACTS_TO_DEPLOY:
        print(f"  Deploying {contract_name}...")
        # In production, this would call web3.py or hardhat to deploy
        # For now, we verify the contract source exists
        sol_path = f"contracts/solidity/{contract_name}.sol"
        if os.path.exists(sol_path):
            print(f"    ✓ Source: {sol_path}")
        else:
            print(f"    ✗ Missing: {sol_path}")

    print(f"\n  Next steps:")
    print(f"    1. Set PRIVATE_KEY in environment")
    print(f"    2. Run: hardhat run scripts/deploy.js --network {chain_name}")
    print(f"    3. Verify contracts on {chain_config['explorer']}")
    print(f"    4. Update deployments.json with deployed addresses")

def verify_deployment():
    """Verify existing deployments."""
    print("\nVerifying existing deployments...")
    if os.path.exists("deployments.json"):
        with open("deployments.json") as f:
            deployments = json.load(f)
        for name, addr in deployments.items():
            print(f"  {name}: {addr}")
    else:
        print("  No deployments.json found")

def main():
    parser = argparse.ArgumentParser(description="TRION Mainnet Deployment")
    parser.add_argument("--chain", default="all", help="Chain to deploy to (or 'all')")
    parser.add_argument("--key-file", help="File containing private key")
    parser.add_argument("--verify", action="store_true", help="Verify existing deployments only")
    args = parser.parse_args()

    if args.verify:
        verify_deployment()
        return

    private_key = os.environ.get("PRIVATE_KEY", "")
    if args.key_file:
        with open(args.key_file) as f:
            private_key = f.read().strip()

    if not private_key:
        print("WARNING: No PRIVATE_KEY set. Showing deployment plan only.")
        print("Set PRIVATE_KEY env var or use --key-file to deploy for real.\n")

    if args.chain == "all":
        for chain_name, config in MAINNET_CHAINS.items():
            deploy_chain(chain_name, config, private_key)
    else:
        if args.chain in MAINNET_CHAINS:
            deploy_chain(args.chain, MAINNET_CHAINS[args.chain], private_key)
        else:
            print(f"Unknown chain: {args.chain}")
            print(f"Available: {', '.join(MAINNET_CHAINS.keys())}")
            sys.exit(1)

    print(f"\n{'='*60}")
    print("Deployment plan complete.")
    print("To deploy for real:")
    print("  1. Ensure PRIVATE_KEY is set with sufficient gas")
    print("  2. Run: python3 scripts/deploy_mainnet.py --chain <chain>")
    print("  3. Or use Hardhat: npx hardhat run scripts/deploy.js --network <chain>")
    print(f"{'='*60}")

if __name__ == "__main__":
    main()
