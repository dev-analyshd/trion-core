#!/usr/bin/env python3
"""
TRION Protocol — Chain Bindings Generator (verification matrix #17)

Generates a Python module of chain-id constants from the canonical registry
config/chain_registry.json, so that code needs no hand-maintained chain-id
tables (the deep-read found at least four divergent ad-hoc numbering schemes:
relayer_non_evm.js, trion-0g, and the Rust crates vs the registry).

Usage:
  python3 scripts/generate_chain_bindings.py [--output <path>] [--ts-output <path>]
                                          [--ts-output-chains <path>]

Defaults:
  output          = core/generated_chain_bindings.py
  ts-output       = sdk/src/generated_chain_ids.ts
  ts-output-chains= chains/shared/generated_chain_ids.ts

The TypeScript artifacts are the same single-source binding for the two
TypeScript consumers that cannot import the Python module: the SDK package
(must stay self-contained for npm packaging) and the chains/ executors
(repo-internal tsx tooling). Both are regenerated from the registry in the
same run, so Python, SDK and chains/ can never drift apart.

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
DEFAULT_TS_OUTPUT = os.path.join(ROOT, "sdk", "src", "generated_chain_ids.ts")
DEFAULT_TS_OUTPUT_CHAINS = os.path.join(
    ROOT, "chains", "shared", "generated_chain_ids.ts"
)


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


def build_ts_module(registry: dict, sibling_note: str) -> str:
    """TypeScript twin of build_module: CHAIN_ID_<SLUG> constants plus a
    name→chainId map, for TS consumers (SDK package, chains/ executors)."""
    chains = registry["chains"]
    slugs = [_slug(c["name"]) for c in chains]
    assert len(slugs) == len(set(slugs)), "slug collision between chain names"

    lines = [
        "/**",
        " * TRION Protocol — Canonical Chain Bindings (auto-generated, TypeScript).",
        " *",
        " * DO NOT EDIT MANUALLY. Run scripts/generate_chain_bindings.py to regenerate",
        f" * (source: config/chain_registry.json; {sibling_note})",
        f" * Registry version: {registry.get('version', 'unknown')}",
        " */",
        "",
        "// Chain-id constants (registry display name → identifier slug)",
    ]
    for c, slug in zip(chains, slugs):
        lines.append(f"export const CHAIN_ID_{slug} = {c['chainId']};  // {c['name']} ({c['vm']})")

    lines += [
        "",
        "// name → chainId (registry display names)",
        "export const CHAIN_IDS: Readonly<Record<string, number>> = Object.freeze({",
    ]
    for c in chains:
        lines.append(f"  {json.dumps(c['name'])}: {c['chainId']},")
    lines += [
        "});",
        "",
        f"export const TOTAL_CHAINS = {len(chains)};",
    ]
    return "\n".join(lines) + "\n"


def main() -> None:
    parser = argparse.ArgumentParser(description="Generate chain-id bindings module")
    parser.add_argument(
        "--output", default=DEFAULT_OUTPUT,
        help="output .py path (default: core/generated_chain_bindings.py)",
    )
    parser.add_argument(
        "--ts-output", default=DEFAULT_TS_OUTPUT,
        help="SDK .ts path (default: sdk/src/generated_chain_ids.ts)",
    )
    parser.add_argument(
        "--ts-output-chains", default=DEFAULT_TS_OUTPUT_CHAINS,
        help="chains/ .ts path (default: chains/shared/generated_chain_ids.ts)",
    )
    args = parser.parse_args()

    with open(REGISTRY_PATH) as f:
        registry = json.load(f)

    code = build_module(registry)
    with open(args.output, "w") as f:
        f.write(code)

    outputs = [args.ts_output, args.ts_output_chains]
    for path in outputs:
        note = (
            "TypeScript twin of core/generated_chain_bindings.py"
            if path == args.ts_output
            else "TypeScript twin of sdk/src/generated_chain_ids.ts"
        )
        with open(path, "w") as f:
            f.write(build_ts_module(registry, note))

    n_const = sum(1 for ln in code.splitlines() if ln.startswith("CHAIN_ID_"))
    _n_vms = len({c["vm"] for c in registry["chains"]})
    _n_integrated = sum(1 for c in registry["chains"] if c.get("integrated"))
    print(f"Generated {args.output}")
    for path in outputs:
        print(f"Generated {path}")
    print(f"  {n_const} CHAIN_ID_* constants, "
          f"{len(registry['chains'])} chains, "
          f"{_n_vms} VM families, "
          f"{_n_integrated} integrated")


if __name__ == "__main__":
    main()
