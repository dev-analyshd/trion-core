#!/usr/bin/env python3
"""
generate_akashic_abi.py — regenerate the AkashicProof ABI artifact.

Audit fix (ABI-1): three zg modules + two deploy scripts referenced
`artifacts/contracts/AkashicProof.sol/AkashicProof.json`, which was never
committed — so the onchain DA-commitment / batchUpdateCommitments code was
dead unless the artifact happened to exist locally.

This script derives the artifact from the CANONICAL Solidity source at
contracts/solidity/AkashicProof.sol and writes a Hardhat-format artifact
(with empty bytecode — compile with `hardhat compile` in the hardhat/
project to obtain deployable bytecode; the ABI here is sufficient for all
read/decode paths the zg daemons and API routes use).

Regenerate after editing AkashicProof.sol:
    python3 scripts/generate_akashic_abi.py
Then, when a Solidity toolchain is available, refresh bytecode by copying
the artifact produced by `hardhat compile` over this file.

License: CC0 (TRION Protocol)
"""

from __future__ import annotations

import json
import os
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
SOURCE = ROOT / "contracts" / "solidity" / "AkashicProof.sol"
OUT = ROOT / "artifacts" / "contracts" / "AkashicProof.sol" / "AkashicProof.json"

# ── Struct definitions (from contracts/solidity/AkashicProof.sol) ────────────
STRUCTS = {
    "StorageCommitment": [
        ("bytes32", "rootHash"), ("bytes32", "txHash"), ("uint256", "sizeBytes"),
        ("uint64", "vectorCount"), ("uint64", "recordCount"), ("uint256", "updatedAt"),
        ("uint256", "updateCount"), ("string", "storageUrl"), ("string", "label"),
    ],
    "AkashicSnapshot": [
        ("uint256", "totalVectors"), ("uint256", "totalBHRecords"),
        ("uint256", "totalSignals"), ("uint256", "totalEntities"),
        ("uint256", "syncCycle"), ("uint256", "blockNumber"), ("uint256", "timestamp"),
    ],
    "DACommitment": [
        ("bytes32", "dataHash"), ("uint256", "blobSize"), ("uint256", "blockNumber"),
        ("uint256", "epoch"), ("uint256", "quorumId"), ("uint256", "submittedAt"),
        ("bool", "verified"),
    ],
    "SyncRecord": [
        ("uint256", "syncCycle"), ("uint256", "filesUploaded"),
        ("uint256", "vectorsAdded"), ("uint256", "recordsAdded"),
        ("uint256", "timestamp"), ("bytes32", "manifestHash"),
    ],
}


def _components(struct_name: str) -> list:
    return [
        {"internalType": t if t not in STRUCTS else f"struct AkashicProof.{t}",
         "name": n, "type": t}
        for t, n in STRUCTS[struct_name]
    ]


def _tuple_output(struct_name: str, name: str) -> dict:
    return {
        "internalType": f"struct AkashicProof.{struct_name}",
        "name": name,
        "type": "tuple",
        "components": _components(struct_name),
    }


def _input(type_: str, name: str) -> dict:
    it = type_ if type_ not in STRUCTS else f"struct AkashicProof.{type_}"
    d = {"internalType": it, "name": name, "type": type_}
    if type_ in STRUCTS:
        d["components"] = _components(type_)
    return d


def build_abi() -> list:
    abi: list = []

    # ── Events ──────────────────────────────────────────────────────────
    abi += [
        {"anonymous": False, "inputs": [
            {"indexed": True, "internalType": "string", "name": "key", "type": "string"},
            {"indexed": False, "internalType": "bytes32", "name": "rootHash", "type": "bytes32"},
            {"indexed": True, "internalType": "uint256", "name": "syncCycle", "type": "uint256"},
            {"indexed": False, "internalType": "uint256", "name": "vectorCount", "type": "uint256"},
        ], "name": "StorageUpdated", "type": "event"},
        {"anonymous": False, "inputs": [
            {"indexed": True, "internalType": "uint256", "name": "syncCycle", "type": "uint256"},
            {"indexed": False, "internalType": "uint256", "name": "filesUploaded", "type": "uint256"},
            {"indexed": False, "internalType": "uint256", "name": "vectorsAdded", "type": "uint256"},
            {"indexed": False, "internalType": "uint256", "name": "timestamp", "type": "uint256"},
        ], "name": "SyncCompleted", "type": "event"},
        {"anonymous": False, "inputs": [
            {"indexed": True, "internalType": "bytes32", "name": "dataHash", "type": "bytes32"},
            {"indexed": False, "internalType": "uint256", "name": "blobSize", "type": "uint256"},
            {"indexed": True, "internalType": "uint256", "name": "epoch", "type": "uint256"},
        ], "name": "DABlobSubmitted", "type": "event"},
        {"anonymous": False, "inputs": [
            {"indexed": True, "internalType": "uint256", "name": "totalVectors", "type": "uint256"},
            {"indexed": True, "internalType": "uint256", "name": "totalRecords", "type": "uint256"},
            {"indexed": False, "internalType": "uint256", "name": "timestamp", "type": "uint256"},
        ], "name": "AkashicMilestone", "type": "event"},
        {"anonymous": False, "inputs": [
            {"indexed": True, "internalType": "address", "name": "validator", "type": "address"},
        ], "name": "ValidatorAdded", "type": "event"},
        {"anonymous": False, "inputs": [
            {"indexed": True, "internalType": "address", "name": "validator", "type": "address"},
        ], "name": "ValidatorRemoved", "type": "event"},
        {"anonymous": False, "inputs": [
            {"indexed": True, "internalType": "bytes32", "name": "root", "type": "bytes32"},
            {"indexed": False, "internalType": "uint256", "name": "sigCount", "type": "uint256"},
            {"indexed": False, "internalType": "uint256", "name": "requiredSigs", "type": "uint256"},
            {"indexed": True, "internalType": "uint256", "name": "nonce", "type": "uint256"},
            {"indexed": False, "internalType": "uint256", "name": "timestamp", "type": "uint256"},
        ], "name": "MerkleRootSubmitted", "type": "event"},
    ]

    # ── Write functions ─────────────────────────────────────────────────
    abi += [
        {"inputs": [_input("address", "v")], "name": "addValidator",
         "outputs": [], "stateMutability": "nonpayable", "type": "function"},
        {"inputs": [_input("address", "v")], "name": "removeValidator",
         "outputs": [], "stateMutability": "nonpayable", "type": "function"},
        {"inputs": [_input("bytes32", "root"), _input("bytes[]", "sigs")],
         "name": "submitMerkleRoot", "outputs": [],
         "stateMutability": "nonpayable", "type": "function"},
        {"inputs": [
            _input("string", "key"), _input("string", "label"),
            _input("bytes32", "rootHash"), _input("bytes32", "txHash"),
            _input("uint256", "sizeBytes"), _input("uint64", "vectorCount"),
            _input("uint64", "recordCount"), _input("string", "storageUrl"),
        ], "name": "updateCommitment", "outputs": [],
         "stateMutability": "nonpayable", "type": "function"},
        {"inputs": [
            _input("string[]", "keys"), _input("bytes32[]", "rootHashes"),
            _input("bytes32[]", "txHashes"), _input("uint256[]", "sizes"),
        ], "name": "batchUpdateCommitments", "outputs": [],
         "stateMutability": "nonpayable", "type": "function"},
        {"inputs": [
            _input("uint256", "filesUploaded"), _input("uint256", "vectorsAdded"),
            _input("uint256", "recordsAdded"), _input("bytes32", "manifestHash"),
        ], "name": "recordSyncCycle", "outputs": [],
         "stateMutability": "nonpayable", "type": "function"},
        {"inputs": [
            _input("bytes32", "dataHash"), _input("uint256", "blobSize"),
            _input("uint256", "blockNumber"), _input("uint256", "epoch"),
            _input("uint256", "quorumId"),
        ], "name": "recordDACommitment", "outputs": [],
         "stateMutability": "nonpayable", "type": "function"},
        {"inputs": [
            _input("uint256", "totalVectors"), _input("uint256", "totalBHRecords"),
            _input("uint256", "totalSignals"), _input("uint256", "totalEntities"),
        ], "name": "recordAkashicSnapshot", "outputs": [],
         "stateMutability": "nonpayable", "type": "function"},
    ]

    # ── View functions ──────────────────────────────────────────────────
    abi += [
        {"inputs": [_input("address", "v")], "name": "isValidator",
         "outputs": [{"internalType": "bool", "name": "", "type": "bool"}],
         "stateMutability": "view", "type": "function"},
        {"inputs": [], "name": "requiredQuorum",
         "outputs": [{"internalType": "uint256", "name": "", "type": "uint256"}],
         "stateMutability": "view", "type": "function"},
        {"inputs": [], "name": "getAllRootHashes",
         "outputs": [
             {"internalType": "string[]", "name": "keys", "type": "string[]"},
             {"internalType": "bytes32[]", "name": "hashes", "type": "bytes32[]"},
         ], "stateMutability": "view", "type": "function"},
        {"inputs": [], "name": "getLatestSyncRecord",
         "outputs": [_tuple_output("SyncRecord", "")],
         "stateMutability": "view", "type": "function"},
        {"inputs": [], "name": "getLatestDACommitment",
         "outputs": [_tuple_output("DACommitment", "")],
         "stateMutability": "view", "type": "function"},
        {"inputs": [], "name": "getFullProof",
         "outputs": [
             {"internalType": "string", "name": "protocol", "type": "string"},
             {"internalType": "string", "name": "version", "type": "string"},
             {"internalType": "uint256", "name": "deployedAt", "type": "uint256"},
             {"internalType": "uint256", "name": "totalFiles", "type": "uint256"},
             {"internalType": "uint256", "name": "totalVectors", "type": "uint256"},
             {"internalType": "uint256", "name": "totalBHRecords", "type": "uint256"},
             {"internalType": "uint256", "name": "totalSyncs", "type": "uint256"},
             {"internalType": "uint256", "name": "totalDABlobs", "type": "uint256"},
             {"internalType": "uint256", "name": "totalSignals", "type": "uint256"},
             {"internalType": "string", "name": "repo", "type": "string"},
         ], "stateMutability": "view", "type": "function"},
        {"inputs": [], "name": "getSyncCount",
         "outputs": [{"internalType": "uint256", "name": "", "type": "uint256"}],
         "stateMutability": "view", "type": "function"},
        {"inputs": [], "name": "getDABlobCount",
         "outputs": [{"internalType": "uint256", "name": "", "type": "uint256"}],
         "stateMutability": "view", "type": "function"},
        {"inputs": [], "name": "getSnapshotCount",
         "outputs": [{"internalType": "uint256", "name": "", "type": "uint256"}],
         "stateMutability": "view", "type": "function"},
        {"inputs": [], "name": "getFileCount",
         "outputs": [{"internalType": "uint256", "name": "", "type": "uint256"}],
         "stateMutability": "view", "type": "function"},
    ]

    # ── Public state-variable getters ───────────────────────────────────
    simple_vars = [
        ("DEPLOYER", "address"), ("DEPLOYED_AT", "uint256"),
        ("DEPLOYED_BLOCK", "uint256"), ("PROTOCOL", "string"),
        ("VERSION", "string"), ("REPO", "string"),
        ("cumulativeVectors", "uint256"), ("cumulativeBHRecords", "uint256"),
        ("cumulativeSignals", "uint256"), ("cumulativeSyncs", "uint256"),
        ("cumulativeDABlobs", "uint256"), ("validatorCount", "uint256"),
        ("latestMerkleRoot", "bytes32"), ("merkleRootUpdateCount", "uint256"),
        ("QUORUM_NUM", "uint256"), ("QUORUM_DEN", "uint256"),
    ]
    for name, t in simple_vars:
        abi.append({
            "inputs": [], "name": name,
            "outputs": [{"internalType": t, "name": "", "type": t}],
            "stateMutability": "view", "type": "function",
        })

    mapping_vars = [
        ("commitments", "string", "StorageCommitment"),
        ("validators", "address", "bool"),
    ]
    for name, key_t, val_t in mapping_vars:
        out = ({"internalType": val_t, "name": "", "type": val_t}
               if val_t not in STRUCTS else
               {"internalType": f"struct AkashicProof.{val_t}", "name": "",
                "type": "tuple", "components": _components(val_t)})
        abi.append({
            "inputs": [_input(key_t, "")], "name": name,
            "outputs": [out],
            "stateMutability": "view", "type": "function",
        })

    array_vars = [
        ("commitmentKeys", "string"), ("snapshots", "AkashicSnapshot"),
        ("daCommitments", "DACommitment"), ("syncHistory", "SyncRecord"),
    ]
    for name, t in array_vars:
        out = ({"internalType": t, "name": "", "type": t} if t not in STRUCTS else
               {"internalType": f"struct AkashicProof.{t}", "name": "",
                "type": "tuple", "components": _components(t)})
        abi.append({
            "inputs": [_input("uint256", "")], "name": name,
            "outputs": [out],
            "stateMutability": "view", "type": "function",
        })
    # latestSnapshot is a public single struct
    abi.append({
        "inputs": [], "name": "latestSnapshot",
        "outputs": [_tuple_output("AkashicSnapshot", "")],
        "stateMutability": "view", "type": "function",
    })
    return abi


def verify_against_source(abi: list) -> int:
    """Cross-check every external/public `function NAME(` + public var in the
    Solidity source has an ABI entry (internal `_funcs` and type keywords excluded)."""
    src = SOURCE.read_text()
    # external/public functions only (skip internal helpers starting with _)
    src_funcs = set(
        f for f in re.findall(r"function\s+(\w+)\s*\(", src)
        if not f.startswith("_")
    )
    type_kw = {"address", "string", "bytes32", "uint256", "uint64", "uint8",
               "bool", "AkashicSnapshot", "DACommitment", "SyncRecord",
               "StorageCommitment"}
    public_vars = set(
        v for v in re.findall(r"^\s*(?:mapping\([^)]*\)\s+)?(\w+)\s+public\s", src, re.MULTILINE)
        if v not in type_kw
    )
    abi_names = {e.get("name") for e in abi if e.get("type") == "function"}
    missing = (src_funcs | public_vars) - abi_names
    if missing:
        print(f"[WARN] source symbols without ABI entry: {sorted(missing)}")
        return len(missing)
    print(f"[OK] all {len(src_funcs)} external functions + {len(public_vars)} public vars covered")
    return 0


def main() -> int:
    if not SOURCE.exists():
        print(f"[ERR] source not found: {SOURCE}", file=sys.stderr)
        return 1
    abi = build_abi()
    rc = verify_against_source(abi)
    artifact = {
        "_format": "hh3-sol-artifact-1",
        "contractName": "AkashicProof",
        "sourceName": "contracts/solidity/AkashicProof.sol",
        "abi": abi,
        "bytecode": "0x",
        "deployedBytecode": "0x",
        "linkReferences": {},
        "deployedLinkReferences": {},
        "_note": (
            "SOURCE-DERIVED ABI (audit fix ABI-1, 2026-09-01): generated by "
            "scripts/generate_akashic_abi.py from contracts/solidity/AkashicProof.sol. "
            "Bytecode fields intentionally empty — run `hardhat compile` in the hardhat/ "
            "project and copy the compiled artifact here to obtain deployable bytecode."
        ),
    }
    OUT.parent.mkdir(parents=True, exist_ok=True)
    OUT.write_text(json.dumps(artifact, indent=2) + "\n")
    print(f"[OK] wrote {OUT} ({len(abi)} ABI entries)")
    return rc


if __name__ == "__main__":
    raise SystemExit(main())
