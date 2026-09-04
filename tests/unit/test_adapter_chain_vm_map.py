"""
test_adapter_chain_vm_map.py — W4-Q registry-consistency pin for the adapter
chain map.

W3-C left one open item: ``adapters/__init__.py::CHAIN_VM_MAP`` is a
hand-maintained chain_id → VMType dispatch table (the adapter layer's own
routing data — NOT a copy of the chain registry). It must never silently
contradict the canonical ``config/chain_registry.json``: every entry either
agrees with the registry's VM family or is on the documented exception list
below.

Documented exceptions (grep-proven at W4-Q, HEAD e280ea7 — update this list
ONLY with a documented reason, the same discipline as the W3-C disposition
matrix):

  5       Goerli — deprecated Ethereum testnet; NOT a registry member.
           EVM semantics identical; entry kept for legacy-parity dispatch.
  10002   Juno   — adapter dispatch distinguishes COSMWASM execution from
           the registry's coarser COSMOS family (the registry has 18
           families and no "COSMWASM"; both agree Juno is Cosmos-ecosystem).
  20002   Fuel   — the OOA (Object-Oriented Architecture) research adapter;
           Fuel is not a member of the 129-chain registry.

This test enforces:
  1. every CHAIN_VM_MAP id in the registry maps to the same VM family
     (modulo the exceptions),
  2. every exception id still exists in CHAIN_VM_MAP (pruning an exception
     without cleaning both lists fails loudly),
  3. the map has no DUPLICATE ids pointing at different VMs (dict literal
     with repeated keys would silently keep the last one — assert the
     source text has no such collision).

Run: python3 -m pytest tests/unit/test_adapter_chain_vm_map.py -q
"""
import json
import re
from pathlib import Path

from adapters import CHAIN_VM_MAP, VMType

REPO_ROOT = Path(__file__).resolve().parents[2]
REGISTRY_PATH = REPO_ROOT / "config" / "chain_registry.json"
ADAPTERS_PATH = REPO_ROOT / "adapters" / "__init__.py"

# {chain_id: reason} — see module docstring
DOCUMENTED_EXCEPTIONS = {
    5: "Goerli (deprecated Ethereum testnet, EVM-identical, not in registry)",
    10002: "Juno (adapter COSMWASM vs registry COSMOS family — coarser registry granularity)",
    20002: "Fuel (OOA research adapter, not a registry member)",
}


def _registry_vm_by_chain_id():
    registry = json.loads(REGISTRY_PATH.read_text())
    return {c["chainId"]: c["vm"] for c in registry["chains"]}


def test_chain_vm_map_agrees_with_registry_or_documented_exception():
    reg = _registry_vm_by_chain_id()
    for cid, vm in sorted(CHAIN_VM_MAP.items()):
        if cid in DOCUMENTED_EXCEPTIONS:
            continue
        assert cid in reg, (
            f"adapters CHAIN_VM_MAP[{cid}] ({vm}) is not in the canonical "
            "registry and not on the documented exception list — either add "
            "the chain to config/chain_registry.json or document the "
            "exception in test_adapter_chain_vm_map.py"
        )
        assert reg[cid].lower() == vm.name.lower(), (
            f"adapters CHAIN_VM_MAP[{cid}] says {vm.name} but the canonical "
            f"registry says {reg[cid]} — W3-C open item regressed; align the "
            "adapter map with config/chain_registry.json"
        )


def test_exception_list_has_no_stale_entries():
    for cid in DOCUMENTED_EXCEPTIONS:
        assert cid in CHAIN_VM_MAP, (
            f"exception chain {cid} ({DOCUMENTED_EXCEPTIONS[cid]}) no longer "
            "exists in CHAIN_VM_MAP — remove it from the documented "
            "exception list"
        )


def test_chain_vm_map_has_no_duplicate_id_literals():
    """A dict literal with a duplicated key keeps only the last entry — a
    silent-dispatch bug this pins shut (source-text check)."""
    src = ADAPTERS_PATH.read_text()
    block = re.search(r"CHAIN_VM_MAP:\s*Dict\[int,\s*VMType\]\s*=\s*\{(.*?)\n\}", src, re.S)
    assert block, "CHAIN_VM_MAP literal not found in adapters/__init__.py"
    ids = re.findall(r"^\s*(\d+):\s*VMType\.", block.group(1), re.M)
    assert len(ids) == len(set(ids)), (
        f"duplicate chain-id keys in CHAIN_VM_MAP literal: "
        f"{sorted(i for i in ids if ids.count(i) > 1)}"
    )
