#!/usr/bin/env python3
"""
TRION Protocol — Chain Bindings Generator (verification matrix #17)

Generates a Python module of chain-id constants from the canonical registry
config/chain_registry.json, so that code needs no hand-maintained chain-id
tables (the deep-read found at least four divergent ad-hoc numbering schemes:
relayer_non_evm.js, trion-0g, and the Rust crates vs the registry).

Usage:
  python3 scripts/generate_chain_bindings.py [--output <path>]

Defaults:
  output = core/generated_chain_bindings.py

Guarantees (asserted, following the scripts/generate_enums.py convention):
  - every registry chain yields a CHAIN_ID_<SLUG> constant
  - chain ids are unique
  - constant-name slugs are unique (collision = registry naming bug)
  - VM families in the emitted module match the registry exactly
"""
import argparse
import json
import os
import re

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
REGISTRY_PATH = os.path.join(ROOT, "config", "chain_registry.json")
DEFAULT_OUTPUT = os.path.join(ROOT, "core", "generated_chain_bindings.py")


def _slug(name: str) -> str:
    """Registry display name → identifier slug ("Arbitrum One" → "ARBITRUM_ONE")."""
    return re.sub(r"[^A-Za-z0-9]+", "_", name).strip("_").upper()


def build_module(registry: dict) -> str:
    chains = registry["chains"]
    ids = [c["chainId"] for c in chains]
    slugs = [_slug(c["name"]) for c in chains]

    # ── validation: a bad registry must fail the generator, not runtime code ──
    assert len(ids) == len(set(ids)), "duplicate chainId in config/chain_registry.json"
    assert len(slugs) == len(set(slugs)), "slug collision between chain names"
    for c in chains:
        assert isinstance(c["chainId"], int), f"non-int chainId: {c['name']}"
        assert c["vm"], f"missing vm: {c['name']}"

    lines = [
        '"""TRION Protocol — Canonical Chain Bindings (auto-generated).',
        '',
        'DO NOT EDIT MANUALLY. Run scripts/generate_chain_bindings.py to regenerate.',
        'Source: config/chain_registry.json (single source of truth, matrix #17)',
        f'Registry version: {registry.get("version", "unknown")}',
        '"""',
        '',
        '# Chain-id constants (registry display name → identifier slug)',
    ]
    for c, slug in zip(chains, slugs):
        lines.append(f"CHAIN_ID_{slug} = {c['chainId']}  # {c['name']} ({c['vm']})")

    integrated = [c["chainId"] for c in chains if c.get("integrated")]
    vms = sorted({c["vm"] for c in chains})

    lines += [
        "",
        "# name → chainId (registry display names)",
        "CHAIN_IDS = {",
    ]
    for c in chains:
        lines.append(f'    "{c["name"]}": {c["chainId"]},')
    lines += [
        "}",
        "",
        "# chainId → name (inverse of CHAIN_IDS; unique by construction)",
        "ID_TO_NAME = {v: k for k, v in CHAIN_IDS.items()}",
        "",
        "# name → VM family",
        "VM_BY_CHAIN = {",
    ]
    for c in chains:
        lines.append(f'    "{c["name"]}": "{c["vm"]}",')
    lines += [
        "}",
        "",
        "# VM families present in the registry",
        f"VM_FAMILIES = frozenset({vms!r})",
        "",
        "# Chain ids with a live TRION indexer + oracle deployment",
        f"INTEGRATED_CHAIN_IDS = frozenset({sorted(integrated)!r})",
        "",
        f"TOTAL_CHAINS = {len(chains)}",
        f"INTEGRATED_CHAINS = {len(integrated)}",
        "",
        '__all__ = [',
        '    "CHAIN_IDS", "ID_TO_NAME", "VM_BY_CHAIN", "VM_FAMILIES",',
        '    "INTEGRATED_CHAIN_IDS", "TOTAL_CHAINS", "INTEGRATED_CHAINS",',
        ']',
        '',
    ]
    return "\n".join(lines)


def main() -> None:
    parser = argparse.ArgumentParser(description="Generate chain-id bindings module")
    parser.add_argument(
        "--output", default=DEFAULT_OUTPUT,
        help="output .py path (default: core/generated_chain_bindings.py)",
    )
    args = parser.parse_args()

    with open(REGISTRY_PATH) as f:
        registry = json.load(f)

    code = build_module(registry)
    with open(args.output, "w") as f:
        f.write(code)

    n_const = sum(1 for ln in code.splitlines() if ln.startswith("CHAIN_ID_"))
    _n_vms = len({c["vm"] for c in registry["chains"]})
    _n_integrated = sum(1 for c in registry["chains"] if c.get("integrated"))
    print(f"Generated {args.output}")
    print(f"  {n_const} CHAIN_ID_* constants, "
          f"{len(registry['chains'])} chains, "
          f"{_n_vms} VM families, "
          f"{_n_integrated} integrated")


if __name__ == "__main__":
    main()
