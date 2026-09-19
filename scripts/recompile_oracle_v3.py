#!/usr/bin/env python3
"""Compile TRIONOracleV3.sol with solcx and update the compiled artifact."""
import json
import sys
from pathlib import Path

from solcx import compile_standard, get_installed_solc_versions

REPO = Path("/home/z/my-project/trion-core")
SOL_ROOT = REPO / "contracts" / "solidity"
SRC = SOL_ROOT / "TRIONOracleV3.sol"
ART = REPO / "contracts" / "solidity" / "compiled" / "TRIONOracleV3.json"

with open(SRC) as f:
    source = f.read()

# Verify installed solc
installed = [str(v) for v in get_installed_solc_versions()]
print("installed solc versions:", installed)
target_version = "0.8.24"
if target_version not in installed:
    print(f"ERROR: solc {target_version} not installed")
    sys.exit(1)

# Standard-json input — give solc the source tree via "urls" so it can resolve
# relative imports itself. We feed in all three imported files + the main source.
sources = {
    "TRIONOracleV3.sol": {"content": source},
}
for path in [
    "interfaces/ITRIONOracleV3.sol",
    "interfaces/ITrionEpochRegistry.sol",
    "libraries/CanonicalCertificate.sol",
]:
    p = SOL_ROOT / path
    if p.exists():
        # Use the bare filename as the source key (matches how the import
        # statement resolves when the file is in the same dir as the importer).
        sources[path] = {"content": p.read_text()}

standard_json = {
    "language": "Solidity",
    "sources": sources,
    "settings": {
        "optimizer": {"enabled": True, "runs": 200},
        "viaIR": True,
        "outputSelection": {"*": {"*": ["abi", "evm.bytecode.object", "metadata"]}},
        "remappings": [],
    },
}

print(f"compiling TRIONOracleV3.sol with solc {target_version} ...")
compiled = compile_standard(standard_json, solc_version=target_version)

# Find the TRIONOracleV3 contract in the output (may be under "TRIONOracleV3.sol"
# or under the bare contract name depending on the solc output schema).
contract_name = "TRIONOracleV3"
if contract_name not in compiled["contracts"]:
    for src_key, contracts in compiled["contracts"].items():
        if contract_name in contracts:
            contract_name_full = contracts[contract_name]
            artifact = contract_name_full
            src_file = src_key
            break
    else:
        print("contract keys:", list(compiled["contracts"].keys()))
        print("ERROR: TRIONOracleV3 not found in compiled output")
        sys.exit(2)
else:
    src_file = "TRIONOracleV3.sol"
    artifact = compiled["contracts"][contract_name][contract_name]

abi = artifact["abi"]
bytecode = "0x" + artifact["evm"]["bytecode"]["object"]

print(f"abi entries: {len(abi)}")
print(f"bytecode length: {len(bytecode)}")
print(f"bytecode starts: {bytecode[:80]}")

# Verify publishSignalWithType is in the ABI
pswt = next((e for e in abi if e.get("name") == "publishSignalWithType"), None)
assert pswt is not None, "publishSignalWithType missing from ABI!"
print("publishSignalWithType ABI entry present. inputs:", len(pswt["inputs"]))

# Verify the bytecode contains the selector
from web3 import Web3
selector = "0x" + Web3.keccak(text="publishSignalWithType((bytes32,bytes32,uint256,uint256,uint256,bool,uint8,uint256,uint256,bool),uint8)").hex()[:8]
hex_sel = selector[2:]
in_bytecode = f"63{hex_sel}" in bytecode
print(f"publishSignalWithType selector {selector} present in bytecode: {in_bytecode}")
assert in_bytecode, "publishSignalWithType selector NOT in compiled bytecode!"

# Write artifact
out = {
    "contractName": contract_name,
    "abi": abi,
    "bytecode": bytecode,
    "compiler": {
        "version": f"{target_version}+commit.a1b79de6.Linux.g++",
    },
    "updatedAt": "2026-09-19T00:00:00.000Z",
    "recompiled": True,
    "source_path": "contracts/solidity/TRIONOracleV3.sol",
    "publishSignalWithType_selector": selector,
}
with open(ART, "w") as f:
    json.dump(out, f, indent=2)
print(f"wrote artifact: {ART}")
print("DONE — TRIONOracleV3 recompiled with publishSignalWithType.")
