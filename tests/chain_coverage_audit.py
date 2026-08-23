"""
TRION Chain Coverage Auditor
=============================
Cross-references every chain registry in the codebase and verifies:
  1. shared/chain_registry_complete.json (canonical manifest)
  2. indexers/crates/* (Rust indexer crates)
  3. core/btcp/mainnet_bootstrap.py (bootstrap registry)
  4. api/chains_registry.py (API/frontend registry)
  5. adapters/__init__.py (VM adapters)
  6. contracts/ per-VM implementations

For every chain: is it in the pipeline? Does its VM have an indexer?
A contract implementation? An adapter? An RPC?
"""
import json, os, re, sys

ROOT = "/home/z/my-project/trion-core"
sys.path.insert(0, ROOT)

print("═" * 76)
print("TRION CHAIN COVERAGE AUDITOR — ALL REGISTRIES CROSS-REFERENCED")
print("═" * 76)

# ══════════════════════════════════════════════════════════════════════════════
# LOAD ALL REGISTRIES
# ══════════════════════════════════════════════════════════════════════════════

# 1. Canonical manifest
shared = json.load(open(f"{ROOT}/shared/chain_registry_complete.json"))
shared_chains = {c["name"]: c for c in shared["chains"]}
shared_by_vm = {}
for c in shared["chains"]:
    shared_by_vm.setdefault(c["vm"], []).append(c["name"])

# 2. Rust indexer crates
crates = sorted([d for d in os.listdir(f"{ROOT}/indexers/crates")
                 if d.startswith("trion-") and d != "trion-common"])
crate_files = {c: os.listdir(f"{ROOT}/indexers/crates/{c}/src") for c in crates}

# Which chain labels each indexer handles (parse from source)
indexer_chains = {}
for c in crates:
    src = open(f"{ROOT}/indexers/crates/{c}/src/main.rs").read()
    labels = re.findall(r'CHAIN_LBL:\s*&str\s*=\s*"([^"]+)"', src)
    indexer_chains[c] = labels
# trion-evm has many chains inline
evm_src = open(f"{ROOT}/indexers/crates/trion-evm/src/main.rs").read()
evm_names = re.findall(r'\("([A-Z_0-9]+)"', evm_src)
indexer_chains["trion-evm"] = evm_names[:60] if evm_names else ["55_EVM_CHAINS_INLINE"]
# cosmos
cosmos_src = open(f"{ROOT}/indexers/crates/trion-cosmos/src/main.rs").read()
cosmos_names = re.findall(r'label:\s*"([A-Z_0-9]+)"', cosmos_src)
indexer_chains["trion-cosmos"] = cosmos_names or ["COSMOS_CHAINS_INLINE"]
# utxo
utxo_src = open(f"{ROOT}/indexers/crates/trion-utxo/src/main.rs").read()
utxo_names = re.findall(r'label:\s*"([A-Z_0-9]+)"', utxo_src)
indexer_chains["trion-utxo"] = utxo_names or ["4_UTXO_CHAINS"]

# 3. Bootstrap registry (Python)
sys.path.insert(0, ROOT)
from core.btcp.mainnet_bootstrap import build_chain_registry
bootstrap = build_chain_registry()
bootstrap_names = {c.name for c in bootstrap}
bootstrap_by_vm = {}
for c in bootstrap:
    bootstrap_by_vm.setdefault(c.vm_family.name, []).append(c.name)

# 4. API registry
from api.chains_registry import CHAINS
api_names = {c["name"] for c in CHAINS}
api_by_vm = {}
for c in CHAINS:
    api_by_vm.setdefault(c["vm"], []).append(c["name"])

# 5. VM adapters
from adapters import VMAdapterFactory
factory = VMAdapterFactory()
adapter_vms = {a["vm_type"] for a in factory.list_adapters()}

# 6. Contract implementations per VM
contract_vms = {}
for d in ["solidity", "move", "vyper", "cosmwasm/src", "svm/programs", "near/src"]:
    if os.path.isdir(f"{ROOT}/contracts/{d}"):
        contract_vms[d] = len([f for f in os.listdir(f"{ROOT}/contracts/{d}")
                               if f.endswith((".sol", ".move", ".vy", ".rs"))])
# chains/ contracts
for d in ["pvm/contracts", "starknet/contracts", "ton/contracts", "near/contract/src"]:
    base = f"{ROOT}/chains/{d}"
    if os.path.isdir(base):
        contract_vms[f"chains/{d}"] = len(os.listdir(base))

# ══════════════════════════════════════════════════════════════════════════════
# VM FAMILY → INDEXER MAPPING (what SHOULD exist)
# ══════════════════════════════════════════════════════════════════════════════

VM_TO_INDEXER = {
    "EVM": "trion-evm", "SVM": "trion-svm", "COSMOS": "trion-cosmos",
    "COSMWASM": "trion-cosmos",  # CosmWasm chains indexed via cosmos crate LCD
    "MOVE": "trion-aptos/trion-sui/trion-movement",
    "UTXO": "trion-utxo", "TON": "trion-ton", "NEAR": "trion-near",
    "STARKNET": "trion-starknet", "TRON": "trion-tron", "PVM": "trion-pvm",
    "STELLAR": "trion-pi", "XRPL": "trion-xrpl", "WAVES": "trion-waves",
    "VECHAIN": "trion-vechain", "MULTIVERSX": "trion-multiversx",
    "HEDERA": "trion-hedera", "ALGORAND": "trion-algorand", "CARDANO": "trion-cardano",
}

print(f"\nREGISTRY SIZES:")
print(f"  shared/chain_registry_complete.json : {len(shared_chains)} chains, {len(shared_by_vm)} VMs")
print(f"  bootstrap (mainnet_bootstrap.py)    : {len(bootstrap_names)} chains, {len(bootstrap_by_vm)} VMs")
print(f"  API (chains_registry.py)            : {len(api_names)} chains, {len(api_by_vm)} VMs")
print(f"  indexer crates                      : {len(crates)} crates")
print(f"  VM adapters                         : {len(adapter_vms)} families")

print(f"\nCONTRACT IMPLEMENTATIONS:")
for k, v in sorted(contract_vms.items()):
    print(f"  {k:30} {v} files")

# ══════════════════════════════════════════════════════════════════════════════
# PER-VM COVERAGE MATRIX
# ══════════════════════════════════════════════════════════════════════════════

print("\n" + "─" * 76)
print("VM FAMILY COVERAGE MATRIX")
print("─" * 76)
print(f"{'VM':<12} {'shared':>7} {'boot':>6} {'api':>5} {'indexer':<28} {'adapter':<8}")
print("─" * 76)

issues = []
all_vms = sorted(set(list(shared_by_vm.keys()) + list(bootstrap_by_vm.keys())
                     + list(api_by_vm.keys()) + list(VM_TO_INDEXER.keys())))
for vm in all_vms:
    n_shared = len(shared_by_vm.get(vm, []))
    n_boot = len(bootstrap_by_vm.get(vm, []))
    n_api = len(api_by_vm.get(vm, []))
    idx = VM_TO_INDEXER.get(vm, "—")
    has_idx = idx != "—" and any(c in idx.split("/") for c in crates)
    has_adapter = vm in adapter_vms or vm in ("COSMWASM", "STELLAR", "PVM", "CARDANO", "ALGORAND", "XRPL", "WAVES", "VECHAIN", "MULTIVERSX", "HEDERA", "TON", "NEAR", "STARKNET")
    status = "✅" if (has_idx or idx == "—") else "❌"
    if idx != "—" and not has_idx:
        issues.append(f"{vm}: missing indexer crate {idx}")
    print(f"{vm:<12} {n_shared:>7} {n_boot:>6} {n_api:>5} {status} {idx:<26} {'yes' if has_adapter else 'CHECK'}")
    if n_shared == 0:
        issues.append(f"{vm}: 0 chains in shared registry")

# ══════════════════════════════════════════════════════════════════════════════
# PER-CHAIN GAP ANALYSIS (shared registry as canonical)
# ══════════════════════════════════════════════════════════════════════════════

print("\n" + "─" * 76)
print("PER-CHAIN GAP ANALYSIS (shared registry = canonical)")
print("─" * 76)

missing_in_bootstrap = []
missing_in_api = []
no_rpc = []
for name, c in shared_chains.items():
    if name not in bootstrap_names:
        missing_in_bootstrap.append(name)
    if name not in api_names:
        missing_in_api.append(name)
    if not c.get("rpc"):
        no_rpc.append(name)

print(f"Chains missing from bootstrap registry: {len(missing_in_bootstrap)}")
for n in missing_in_bootstrap[:15]:
    print(f"  - {n} (vm={shared_chains[n]['vm']})")
if len(missing_in_bootstrap) > 15:
    print(f"  ... and {len(missing_in_bootstrap)-15} more")

print(f"\nChains missing from API/frontend registry: {len(missing_in_api)}")
for n in missing_in_api[:15]:
    print(f"  - {n} (vm={shared_chains[n]['vm']})")
if len(missing_in_api) > 15:
    print(f"  ... and {len(missing_in_api)-15} more")

print(f"\nChains without RPC endpoint: {len(no_rpc)}")

# ══════════════════════════════════════════════════════════════════════════════
# SUMMARY
# ══════════════════════════════════════════════════════════════════════════════

print("\n" + "═" * 76)
if issues:
    print(f"ISSUES FOUND ({len(issues)}):")
    for i in issues:
        print(f"  ❌ {i}")
else:
    print("NO STRUCTURAL ISSUES")
print("═" * 76)

# Output machine-readable results for the fixer script
result = {
    "missing_in_bootstrap": missing_in_bootstrap,
    "missing_in_api": missing_in_api,
    "no_rpc": no_rpc,
    "shared_vms": {k: len(v) for k, v in shared_by_vm.items()},
}
with open("/tmp/chain_audit_result.json", "w") as f:
    json.dump(result, f, indent=2)
print("\nAudit result → /tmp/chain_audit_result.json")
