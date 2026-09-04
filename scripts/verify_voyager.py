#!/usr/bin/env python3.13
"""
TRION Protocol — Starknet Source Code Verification on Voyager
=============================================================
Submits source code verification for all 7 deployed Starknet contracts
to Voyager (sepolia.voyager.online).

Uses cloudscraper to bypass Cloudflare protection.

For each contract:
  1. Prepare the Cairo source code files
  2. Submit to Voyager's verification API
  3. Check verification status

Live-RPC external tool — network calls, no test battery coverage.
"""
import json
import os
import sys
import time
import cloudscraper

# Repo-relative paths (W4-Q fix: the hardcoded /home/z/my-project/trion-core
# machine paths predated the repo move and the deployments/ restructure).
REPO = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
DEPLOYMENTS_FILE = os.path.join(REPO, "chains", "starknet", "starknet_sepolia_deployments.json")
with open(DEPLOYMENTS_FILE) as f:
    deployments = json.load(f)

CONTRACTS_DIR = os.path.join(REPO, "contracts", "starknet", "src")

scraper = cloudscraper.create_scraper()

# Map contract names to their source files
CONTRACT_FILES = {
    "TRIONOracle": "TRIONOracle.cairo",
    "BEOAttestation": "BEOAttestation.cairo",
    "BTCFiGuard": "BTCFiGuard.cairo",
    "BTCPIntent": "btcp_intent.cairo",
    "BTCPRoute": "btcp_route.cairo",
    "BTCPEscrow": "btcp_escrow.cairo",
    "LiquidityOcean": "liquidity_ocean.cairo",
}

# Compiler version used
COMPILER_VERSION = "2.10.1"

# Voyager API base URL
VOYAGER_API = "https://api.voyager.online/api"

results = []

def verify_contract(contract_name, address, class_hash, source_file):
    """Submit source code verification for a single contract."""
    print(f"\n{'='*60}")
    print(f"  Verifying: {contract_name}")
    print(f"  Address:   {address}")
    print(f"  Class Hash: {class_hash}")
    print(f"  Source:    {source_file}")
    print(f"{'='*60}")

    # Read the source code
    source_path = os.path.join(CONTRACTS_DIR, source_file)
    if not os.path.exists(source_path):
        print(f"  ❌ Source file not found: {source_path}")
        return {"contract": contract_name, "address": address, "status": "failed", "error": "source not found"}

    with open(source_path) as f:
        source_code = f.read()

    print(f"  Source code size: {len(source_code)} bytes")

    # Try multiple Voyager API endpoints
    endpoints = [
        f"{VOYAGER_API}/verify",
        f"{VOYAGER_API}/verify/code",
        f"{VOYAGER_API}/contract/verify",
        f"https://sepolia.voyager.online/api/verify",
    ]

    payload = {
        "contractAddress": address,
        "classHash": class_hash,
        "sourceCode": source_code,
        "compilerVersion": COMPILER_VERSION,
        "cairoVersion": "2",
        "contractName": contract_name,
        "network": "sepolia",
    }

    for endpoint in endpoints:
        try:
            print(f"\n  Trying endpoint: {endpoint}")
            r = scraper.post(endpoint, json=payload, timeout=30)
            print(f"  Status: {r.status_code}")
            if r.status_code == 200:
                try:
                    resp = r.json()
                    print(f"  Response: {json.dumps(resp)[:200]}")
                    if resp.get("success") or resp.get("verified"):
                        print(f"  ✅ Verification submitted successfully!")
                        return {"contract": contract_name, "address": address, "status": "submitted", "endpoint": endpoint, "response": resp}
                except:
                    pass
            elif r.status_code == 403:
                print(f"  ⚠ Forbidden (API key may be required)")
            elif r.status_code == 404:
                print(f"  ⚠ Endpoint not found")
            else:
                print(f"  Response: {r.text[:200]}")
        except Exception as e:
            print(f"  ❌ Error: {str(e)[:100]}")

    # Also try form-based submission
    try:
        print(f"\n  Trying form-based submission...")
        form_data = {
            "address": address,
            "classHash": class_hash,
            "sourceCode": source_code,
            "compilerVersion": COMPILER_VERSION,
            "contractName": contract_name,
        }
        r = scraper.post(f"https://sepolia.voyager.online/api/verify", data=form_data, timeout=30)
        print(f"  Status: {r.status_code}")
        print(f"  Response: {r.text[:200]}")
    except Exception as e:
        print(f"  ❌ Error: {str(e)[:100]}")

    return {"contract": contract_name, "address": address, "status": "failed", "error": "all endpoints failed"}

def check_verification_status(address):
    """Check if a contract is already verified on Voyager."""
    try:
        r = scraper.get(f"https://sepolia.voyager.online/api/contract/{address}", timeout=15)
        if r.status_code == 200:
            data = r.json()
            return data.get("verified", False)
    except:
        pass
    return None

def main():
    print("=" * 60)
    print("  TRION Protocol — Starknet Source Code Verification")
    print("  Submitting source code to Voyager for all 7 contracts")
    print("=" * 60)

    # First check current verification status
    print("\n── Checking current verification status ──")
    for c in deployments["contracts"]:
        name = c["name"]
        addr = c["address"]
        if name not in CONTRACT_FILES:
            continue
        status = check_verification_status(addr)
        print(f"  {name:20s} {addr[:20]}... verified={status}")

    # Submit verification for each contract
    print("\n── Submitting source code verification ──")
    for c in deployments["contracts"]:
        name = c["name"]
        addr = c["address"]
        ch = c.get("classHash", "")
        if name not in CONTRACT_FILES:
            continue
        result = verify_contract(name, addr, ch, CONTRACT_FILES[name])
        results.append(result)
        time.sleep(2)  # Rate limit

    # Summary
    print("\n" + "=" * 60)
    print("  VERIFICATION SUMMARY")
    print("=" * 60)
    for r in results:
        status = r.get("status", "unknown")
        icon = "✅" if status == "submitted" else "❌"
        print(f"  {r['contract']:20s} {icon} {status}")
    print("=" * 60)

    # Save results
    report = {
        "verifiedAt": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
        "compilerVersion": COMPILER_VERSION,
        "results": results,
    }
    report_path = os.path.join(REPO, "docs", "proofs", "voyager_verification_report.json")
    os.makedirs(os.path.dirname(report_path), exist_ok=True)
    with open(report_path, "w") as f:
        json.dump(report, f, indent=2)
    print(f"\n  Report saved: {report_path}")

if __name__ == "__main__":
    main()
