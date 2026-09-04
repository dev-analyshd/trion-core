"""
test_solidity_source_sync.py — W4-Q duplication sync pins (single-source-of-truth enforcement).

The repo deliberately keeps two classes of *content-duplicated* Solidity/PVM
artifacts, each for an operational reason. This test makes drift impossible:

  1. hardhat/contracts/** — deployment/test twins of contracts/solidity/**.
     hardhat.config.ts keeps the harness self-contained (sources: ./contracts,
     artifacts/cache local). Re-pointing Hardhat's sources at ../contracts/
     solidity was evaluated and REJECTED (W4-Q): Hardhat compiles every file
     under sources/, and 25+ contracts in contracts/solidity have never been
     validated under the hardhat toolchain (0.8.28/cancun/viaIR) — plus the
     suite is external-toolchain (no node_modules here) so the change could
     not be verified. The twins are byte-identical copies instead, and this
     test pins them byte-identical. Wave-2 already synced them by hand; this
     automates the pin.

  2. evm-tools/compiled/*.json and contracts/solidity/compiled/*.json —
     solcjs artifacts mirrored by evm-tools/compile.mjs. Proven readers:
     chains/starknet/src/{zero-bridge,full-zero-bridge,loop,per-vm}-test.ts
     (escrow ABI), evm-tools/deploy-*.mjs (ABI + bytecode). They had gone
     STALE (compiled before the Wave-2 canonical-certificate escrow; missing
     releaseEscrowCanonical / setEpochRegistry / submitCertificateAttestation
     surface) because compile.mjs's flat source map had not been extended
     with the new imports — fixed in W4-Q and regenerated. This test pins the
     two trees identical AND pins each artifact's ABI signature set against a
     fresh compile of the current source, so the staleness class of drift
     fails the battery instead of shipping old bytecode to deploy scripts.

  3. chains/pvm/contract/lib.rs — relayer-side twin of
     contracts/pvm/legacy_oracle.rs (Wave-2 L synced them byte-identical;
     test_pvm_oracle.py checks it but via a print-only helper that does not
     fail under pytest — this file re-pins it with hard asserts).

Run: python3 -m pytest tests/contracts/test_solidity_source_sync.py
"""

import json
import os
import re

import pytest

REPO = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
SOLIDITY = os.path.join(REPO, "contracts", "solidity")
HARDHAT_CONTRACTS = os.path.join(REPO, "hardhat", "contracts")
EVM_TOOLS_COMPILED = os.path.join(REPO, "evm-tools", "compiled")
MIRROR_COMPILED = os.path.join(SOLIDITY, "compiled")

# hardhat twin → canonical source. Byte-identical or the test fails.
HARDHAT_TWIN_MAP = {
    "BTCPEscrow.sol": "BTCPEscrow.sol",
    "TRIONExecutionGate.sol": "TRIONExecutionGate.sol",
    "TRIONOracleV3.sol": "TRIONOracleV3.sol",
    "TrionEpochRegistry.sol": "TrionEpochRegistry.sol",
    "ReentrantAttacker.sol": "test/ReentrantAttacker.sol",
    "libraries/CanonicalCertificate.sol": "libraries/CanonicalCertificate.sol",
    "interfaces/ITRIONOracleV3.sol": "interfaces/ITRIONOracleV3.sol",
    "interfaces/ITrionEpochRegistry.sol": "interfaces/ITrionEpochRegistry.sol",
}

COMPILE_TARGETS = [
    "BTCPEscrow.sol",
    "BTCPIntent.sol",
    "BTCPRoute.sol",
    "LiquidityOcean.sol",
    "TRIONOracleV3.sol",
]


def _read(path):
    with open(path, "r", encoding="utf-8") as fh:
        return fh.read()


# ── 1. hardhat twins are byte-identical to contracts/solidity ───────────────

def test_hardhat_twins_byte_identical():
    for twin, canonical in sorted(HARDHAT_TWIN_MAP.items()):
        t = os.path.join(HARDHAT_CONTRACTS, twin)
        c = os.path.join(SOLIDITY, canonical)
        assert os.path.isfile(t), f"missing hardhat twin: {t}"
        assert os.path.isfile(c), f"missing canonical source: {c}"
        assert _read(t) == _read(c), (
            f"hardhat twin drifted from canonical source: {t} != {canonical}. "
            "Copy the canonical file over (the twin policy is byte-identity; "
            "see hardhat/README.md)."
        )


def test_hardhat_twin_set_is_exhaustive():
    """Any file under hardhat/contracts must be a pinned twin — no orphan
    copies that silently escape the byte-identity pin above."""
    found = set()
    for root, _dirs, files in os.walk(HARDHAT_CONTRACTS):
        for f in files:
            found.add(os.path.relpath(os.path.join(root, f), HARDHAT_CONTRACTS))
    assert found == set(HARDHAT_TWIN_MAP), (
        f"hardhat/contracts file set changed: extra={sorted(found - set(HARDHAT_TWIN_MAP))} "
        f"missing={sorted(set(HARDHAT_TWIN_MAP) - found)} — update HARDHAT_TWIN_MAP"
    )


# ── 2. compiled artifacts: mirror identity + ABI-vs-source staleness pin ────

def test_compiled_trees_mirror_identical():
    for name in [t[:-4] for t in COMPILE_TARGETS]:
        a = os.path.join(EVM_TOOLS_COMPILED, f"{name}.json")
        b = os.path.join(MIRROR_COMPILED, f"{name}.json")
        assert os.path.isfile(a) and os.path.isfile(b), f"missing compiled artifact: {name}"
        assert _read(a) == _read(b), (
            f"compiled trees drifted: evm-tools/compiled/{name}.json != "
            "contracts/solidity/compiled mirror — re-run `node evm-tools/compile.mjs` "
            "(it writes both trees)."
        )


def _abi_signature_set(abi):
    out = set()
    for entry in abi:
        kind = entry.get("type")
        if kind in ("function", "event", "error"):
            inputs = ",".join(i["type"] for i in entry.get("inputs", []))
            out.add(f"{kind}:{entry['name']}({inputs})")
    return out


def _walk_sources(rel, sources):
    if rel in sources:
        return
    content = _read(os.path.join(SOLIDITY, rel))
    sources[rel] = {"content": content}
    for m in re.finditer(r'import\s+["\']([^"\']+)["\']', content):
        imp = m.group(1)
        assert imp.startswith("./"), f"non-relative import {imp!r} in {rel} — extend the walker"
        _walk_sources(os.path.normpath(os.path.join(os.path.dirname(rel), imp)), sources)


@pytest.fixture(scope="module")
def fresh_abi_by_contract():
    """Fresh ABI-only compile of the current sources (mirrors the import walker
    in evm-tools/compile.mjs). ABI surface is compiler-version-stable, so
    comparing py-solcx output against the solcjs artifacts is sound."""
    import solcx

    sources = {}
    for t in COMPILE_TARGETS:
        _walk_sources(t, sources)
    compiled = solcx.compile_standard(
        {"language": "Solidity", "sources": sources,
         "settings": {"outputSelection": {"*": {"*": ["abi"]}}}},
        solc_version="0.8.24",
    )
    result = {}
    for t in COMPILE_TARGETS:
        name = t[:-4]
        result[name] = _abi_signature_set(compiled["contracts"][t][name]["abi"])
    return result


def test_compiled_abi_matches_current_source(fresh_abi_by_contract):
    for name, fresh in sorted(fresh_abi_by_contract.items()):
        artifact = json.loads(_read(os.path.join(EVM_TOOLS_COMPILED, f"{name}.json")))
        pinned = _abi_signature_set(artifact["abi"])
        assert pinned == fresh, (
            f"stale compiled artifact {name}.json — ABI drifted from the current "
            f"source (artifact-only: {sorted(pinned - fresh)}, source-only: "
            f"{sorted(fresh - pinned)}). Re-run `node evm-tools/compile.mjs`."
        )


# ── 3. PVM relayer-side twin byte-identical (hard-assert version) ───────────

def test_pvm_relayer_twin_byte_identical():
    canonical = os.path.join(REPO, "contracts", "pvm", "legacy_oracle.rs")
    twin = os.path.join(REPO, "chains", "pvm", "contract", "lib.rs")
    assert os.path.isfile(canonical) and os.path.isfile(twin)
    assert _read(twin) == _read(canonical), (
        "chains/pvm/contract/lib.rs drifted from contracts/pvm/legacy_oracle.rs — "
        "copy the canonical file over (twin policy is byte-identity)."
    )
