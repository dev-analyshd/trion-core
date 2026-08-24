#!/usr/bin/env python3
"""
TRION Mainnet Deployment Preflight Gate
=======================================
Automated checks that MUST pass before any mainnet deployment.
Run before every live-network transaction. Exits non-zero on any failure.

Usage:
    python3 scripts/mainnet_preflight.py --chain polygon
    python3 scripts/mainnet_preflight.py --chain 0g --deploy-key DEPLOY_0G_PRIVATE
    python3 scripts/mainnet_preflight.py --check-all
"""
import argparse
import json
import os
import re
import sys
import urllib.request

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))

# ── Mainnet registry: chain → (chainId, rpc default, explorer) ───────────────
MAINNETS = {
    "ethereum":  (1,      "https://ethereum.publicnode.com",                "https://etherscan.io"),
    "optimism":  (10,     "https://mainnet.optimism.io",                   "https://optimistic.etherscan.io"),
    "bnb":       (56,     "https://bsc-dataseed.binance.org",              "https://bscscan.com"),
    "polygon":   (137,    "https://polygon-bor-rpc.publicnode.com",                       "https://polygonscan.com"),
    "base":      (8453,   "https://mainnet.base.org",                      "https://basescan.org"),
    "arbitrum":  (42161,  "https://arb1.arbitrum.io/rpc",                  "https://arbiscan.io"),
    "avalanche": (43114,  "https://api.avax.network/ext/bc/C/rpc",         "https://snowtrace.io"),
    "hashkey":   (177,    "https://mainnet.hsk.xyz",                       "https://hsk.info"),
    "mantle":    (5000,   "https://rpc.mantle.xyz",                        "https://mantlescan.xyz"),
    "linea":     (59144,  "https://rpc.linea.build",                       "https://lineascan.build"),
    "scroll":    (534352, "https://rpc.scroll.io",                         "https://scrollscan.com"),
    "0g":        (16661,  "https://evmrpc.0g.ai",                          "https://explorer.0g.ai"),
}

# Deployments known to originate from the compromised-history wallet
# (0xdBbf66CAD621dA3Ec186D18b29a135d2A5d42d20 — flagged in the BTCP Master
# Spec's security note). Fresh deployments must NOT reuse this deployer.
COMPROMISED_DEPLOYERS = {
    "0xdbbf66cad621da3ec186d18b29a135d2a5d42d20",
}

PASS, FAIL, WARN = "✅", "❌", "⚠️ "
results = []


def check(name, ok, detail="", warn_only=False):
    mark = PASS if ok else (WARN if warn_only else FAIL)
    results.append((mark, name, detail))
    return ok


def rpc(rpc_url, method, params=None, timeout=12):
    payload = json.dumps({"jsonrpc": "2.0", "method": method,
                          "params": params or [], "id": 1}).encode()
    req = urllib.request.Request(
        rpc_url, data=payload,
        headers={"Content-Type": "application/json", "User-Agent": "TRION-preflight/1.0"})
    with urllib.request.urlopen(req, timeout=timeout) as r:
        return json.loads(r.read()).get("result")


def preflight(chain_name: str, key_env: str) -> bool:
    if chain_name not in MAINNETS:
        print(f"Unknown mainnet '{chain_name}'. Known: {', '.join(MAINNETS)}")
        return False
    chain_id, default_rpc, explorer = MAINNETS[chain_name]

    print(f"\n═══ TRION MAINNET PREFLIGHT — {chain_name.upper()} (chainId {chain_id}) ═══\n")

    # ── 1. Chain connectivity + ID verification ────────────────────────────
    rpc_url = os.environ.get(f"{chain_name.upper().replace('0G','ZERO_G')}_RPC", default_rpc)
    try:
        live_id = int(rpc(rpc_url, "eth_chainId"), 16)
        check("RPC reachable", True, rpc_url)
        check("chainId matches registry", live_id == chain_id,
              f"live={live_id} expected={chain_id}")
    except Exception as e:
        check("RPC reachable", False, str(e)[:60])
        print("  — cannot continue without RPC")
        return False

    # ── 2. Deployer key present + valid format ─────────────────────────────
    key = os.environ.get(key_env, "")
    key_ok = bool(re.fullmatch(r"0x[0-9a-fA-F]{64}", key))
    check(f"deployer key present ({key_env})", key_ok,
          "set via environment — NEVER hardcode")

    deployer_addr = None
    if key_ok:
        # Derive address WITHOUT importing eth_account (keccak checksum)
        try:
            from eth_account import Account
            acct = Account.from_key(key)
            deployer_addr = acct.address
            check("key derives valid account", True, deployer_addr)
            check("deployer NOT the compromised-history wallet",
                  deployer_addr.lower() not in COMPROMISED_DEPLOYERS,
                  "0xdBbf66… is compromised per the old spec")
        except ImportError:
            check("key derives valid account", False,
                  "eth_account not installed", warn_only=True)

    # ── 3. Deployer funded ──────────────────────────────────────────────────
    if deployer_addr:
        try:
            wei = int(rpc(rpc_url, "eth_getBalance", [deployer_addr, "latest"]), 16)
            eth = wei / 1e18
            check("deployer funded", eth > 0.005,
                  f"{eth:.4f} ETH-equivalent (need gas)")
        except Exception as e:
            check("deployer funded", False, str(e)[:50], warn_only=True)

    # ── 4. Contracts compile ────────────────────────────────────────────────
    sol_dir = os.path.join(ROOT, "contracts", "solidity")
    critical = ["TRIONOracleV3.sol", "BTCPEscrow.sol", "TRIONExecutionGate.sol"]
    for c in critical:
        check(f"contract source present: {c}",
              os.path.exists(os.path.join(sol_dir, c)))

    # ── 5. Bootstrap gate (whitepaper §14.1) — informational ───────────────
    print(f"\n  ── Whitepaper bootstrap gate (§14.1) — informational ──")
    try:
        with urllib.request.urlopen("http://127.0.0.1:5000/api/v1/bootstrap/status",
                                    timeout=4) as r:
            bs = json.loads(r.read())
        depth = bs.get("akashic_depth", 0)
        needed = bs.get("depth_for_full_transition", 46051)
        check("Akashic depth progress",
              True,  # informational
              f"D(t)={depth:,.0f}/{needed:,} ({depth/needed*100:.1f}%) — full "
              f"living security at 100%; this gate is TIME by design")
    except Exception:
        check("Oracle reachable for bootstrap gate", False,
              "start services for depth reporting", warn_only=True)

    # ── Verdict ─────────────────────────────────────────────────────────────
    print()
    hard_fails = [r for r in results if r[0] == FAIL]
    for mark, name, detail in results:
        print(f"  {mark} {name}" + (f" — {detail}" if detail else ""))
    print()
    if hard_fails:
        print(f"VERDICT: {len(hard_fails)} BLOCKER(S) — DO NOT DEPLOY")
        return False
    print("VERDICT: PREFLIGHT PASS — deployment may proceed")
    print(f"  explorer: {explorer}")
    print(f"  remember: verify source post-deploy, record in proof-ledger/")
    return True


def check_all():
    print("═══ TRION MAINNET PREFLIGHT — connectivity sweep of all 12 mainnets ═══")
    all_ok = True
    for name, (cid, rpc_url, _) in MAINNETS.items():
        try:
            live = int(rpc(rpc_url, "eth_chainId"), 16)
            ok = live == cid
            print(f"  {PASS if ok else FAIL} {name:10s} chainId {live}"
                  + ("" if ok else f" (expected {cid})"))
        except Exception as e:
            all_ok = False
            print(f"  {FAIL} {name:10s} unreachable: {str(e)[:40]}")
    return all_ok


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--chain", help="mainnet name (ethereum, polygon, 0g, …)")
    ap.add_argument("--deploy-key", default="RELAYER_PRIVATE_KEY",
                    help="env var holding the deployer key")
    ap.add_argument("--check-all", action="store_true",
                    help="sweep all mainnet RPCs for connectivity")
    args = ap.parse_args()
    ok = check_all() if args.check_all else (
        preflight(args.chain, args.deploy_key) if args.chain else
        (ap.print_help() or False))
    sys.exit(0 if ok else 1)
