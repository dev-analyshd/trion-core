#!/usr/bin/env python3
"""
TRION Protocol — Single-Source Enum Generator
Generates language-specific event type enums from bh_schema_v1.json.

Usage:
  python3 scripts/generate_enums.py

Outputs:
  config/event_types.json  (canonical source)
  core/primitives/event_types_generated.py  (Python)
  (Rust, TypeScript, Solidity are manually aligned but CI-verified)
"""
import json
import os

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
SCHEMA_PATH = os.path.join(ROOT, "config", "bh_schema_v1.json")

def main():
    with open(SCHEMA_PATH) as f:
        schema = json.load(f)

    event_types = schema["event_types"]

    # Generate canonical JSON
    canonical = {
        "version": schema["schema_version"],
        "event_types": [{"id": e["id"], "name": e["name"]} for e in event_types],
    }
    canonical_path = os.path.join(ROOT, "config", "event_types.json")
    with open(canonical_path, "w") as f:
        json.dump(canonical, f, indent=2)
    print(f"Generated {canonical_path}")

    # Generate Python
    py_code = '"""TRION Protocol — Canonical Event Types (auto-generated).\n\nDO NOT EDIT MANUALLY. Run scripts/generate_enums.py to regenerate.\nSource: config/bh_schema_v1.json\n"""\n\nfrom enum import IntEnum\n\n\nclass EventType(IntEnum):\n'
    for e in event_types:
        py_code += f'    {e["name"]} = {e["id"]}  # {e["id"]}\n'
    py_code += '\n\nEVENT_TYPE_NAMES = {e.value: e.name for e in EventType}\n'
    py_path = os.path.join(ROOT, "core", "primitives", "event_types_generated.py")
    with open(py_path, "w") as f:
        f.write(py_code)
    print(f"Generated {py_path}")

    # Verify count
    assert len(event_types) == 20, f"Expected 20 event types, got {len(event_types)}"
    print(f"Event types: {len(event_types)} (verified: 20)")

    # Print for CI verification
    print("\nCanonical event types for CI cross-check:")
    for e in event_types:
        print(f"  {e['id']:2d} = {e['name']}")

if __name__ == "__main__":
    main()
