"""Chain bindings tests — verification matrix #17 (P3-CONSOLIDATE).

config/chain_registry.json is the single source of truth for chain ids /
VM families. core/generated_chain_bindings.py is generated from it by
scripts/generate_chain_bindings.py and must never drift from the registry.
"""
import json
import os
import subprocess
import sys

from core import generated_chain_bindings as gcb

ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", ".."))
REGISTRY_PATH = os.path.join(ROOT, "config", "chain_registry.json")
GENERATOR_PATH = os.path.join(ROOT, "scripts", "generate_chain_bindings.py")
MODULE_PATH = os.path.join(ROOT, "core", "generated_chain_bindings.py")

with open(REGISTRY_PATH) as _f:
    REGISTRY = json.load(_f)
REGISTRY_CHAINS = REGISTRY["chains"]


def test_registry_is_valid_json_with_expected_shape():
    """The canonical registry loads and its header counts match its contents."""
    assert len(REGISTRY_CHAINS) == REGISTRY["total_chains"] >= 100
    assert REGISTRY["vm_families"] == len({c["vm"] for c in REGISTRY_CHAINS}) >= 14
    assert REGISTRY["integrated_chains"] == sum(
        1 for c in REGISTRY_CHAINS if c.get("integrated")
    )
    # vm_distribution must sum to the total chain count
    assert sum(REGISTRY["vm_distribution"].values()) == REGISTRY["total_chains"]


def test_bindings_match_registry_exactly():
    """Every registry chain appears in the generated bindings with its id."""
    expected_ids = {c["name"]: c["chainId"] for c in REGISTRY_CHAINS}
    expected_vms = {c["name"]: c["vm"] for c in REGISTRY_CHAINS}
    assert gcb.CHAIN_IDS == expected_ids
    assert gcb.VM_BY_CHAIN == expected_vms
    assert gcb.TOTAL_CHAINS == len(REGISTRY_CHAINS)


def test_chain_ids_are_unique():
    """chain_id is a canonical BH input — a duplicate would corrupt identity."""
    ids = list(gcb.CHAIN_IDS.values())
    assert len(ids) == len(set(ids))


def test_id_to_name_is_exact_inverse():
    assert gcb.ID_TO_NAME == {v: k for k, v in gcb.CHAIN_IDS.items()}


def test_vm_families_match_registry():
    assert gcb.VM_FAMILIES == frozenset(c["vm"] for c in REGISTRY_CHAINS)
    assert "EVM" in gcb.VM_FAMILIES


def test_integrated_chain_ids_match_registry():
    expected = frozenset(
        c["chainId"] for c in REGISTRY_CHAINS if c.get("integrated")
    )
    assert gcb.INTEGRATED_CHAIN_IDS == expected
    assert gcb.INTEGRATED_CHAINS == len(expected)


def test_known_canonical_ids():
    """Spot-check the ids the deep-read verified against the Rust indexers
    (SVM=900 and PVM=25000 are the resolved chain-ID-900 collision pair)."""
    assert gcb.CHAIN_ID_ETHEREUM == 1
    assert gcb.CHAIN_ID_ARBITRUM_ONE == 42161
    assert gcb.CHAIN_ID_BASE == 8453
    assert gcb.CHAIN_ID_0G_MAINNET == 16661
    assert gcb.CHAIN_ID_SOLANA_MAINNET == 900
    assert gcb.CHAIN_ID_POLKADOT == 25000
    assert gcb.CHAIN_ID_COSMOS_HUB == 10000
    # merged from the former anima-service EVM registry (P3-CONSOLIDATE)
    assert gcb.CHAIN_ID_HARMONY == 1666600000
    assert gcb.CHAIN_ID_MONAD == 10143
    assert gcb.CHAIN_ID_ABSTRACT == 2741


def test_generator_output_is_up_to_date(tmp_path):
    """Regenerating must reproduce the committed module byte-for-byte —
    otherwise core/generated_chain_bindings.py is stale vs the registry."""
    out = tmp_path / "regenerated_bindings.py"
    subprocess.run(
        [sys.executable, GENERATOR_PATH, "--output", str(out)],
        check=True, capture_output=True, timeout=60,
    )
    committed = open(MODULE_PATH).read()
    regenerated = out.read_text()
    assert committed == regenerated, (
        "core/generated_chain_bindings.py is stale — run "
        "scripts/generate_chain_bindings.py and commit the result"
    )
