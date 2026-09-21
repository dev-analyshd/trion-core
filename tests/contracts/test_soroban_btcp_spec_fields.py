"""test_soroban_btcp_spec_fields.py — §4.1 Intent + §4.3 Route lifecycle
static source-pin for the Soroban (Stellar) btcp-intent and btcp-route
contracts.

BTCP-DEEP-4 (item #4 in the table) found that
contracts/soroban/btcp-intent/src/lib.rs and btcp-route/src/lib.rs were
generic placeholder stubs: `Record { entity_id, data_hash, status,
created, submitter }` — NO §4.1 fields, NO §4.3 lifecycle.

BTCP-FIX2-RUST-VM replaces the stubs with the real Intent struct + the
full create → prove → execute → finalize route lifecycle. This test
greps the source to pin every spec-mandated field and lifecycle step.

Run: python3 tests/contracts/test_soroban_btcp_spec_fields.py
"""

import os
import sys

REPO = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
INTENT_RS = os.path.join(REPO, "contracts/soroban/btcp-intent/src/lib.rs")
ROUTE_RS = os.path.join(REPO, "contracts/soroban/btcp-route/src/lib.rs")

PASSED = []
FAILED = []


def check(name, cond, detail=""):
    (PASSED if cond else FAILED).append(name)
    status = "OK" if cond else "FAIL"
    print(f"  {status} {name}" + (f" — {detail}" if detail and not cond else ""))


# ── §4.1 Intent Object — required fields (15) ────────────────────────────────

INTENT_FIELDS = (
    "intent_id",          # keccak256(abi.encode(intent))
    "entity_id",          # BEO identifier (bytes32) — same across ALL chains
    "source_chain",       # source chain id
    "dest_chain",         # destination chain id
    "source_address",     # source address on source_chain
    "dest_address",       # destination address on dest_chain
    "action",             # SWAP | TRANSFER | LIQUIDITY | STAKE | BORROW
    "value",              # amount in behavioral magnitude units (uint256 → u128)
    "asset_in",           # universal asset identifier (bytes32)
    "asset_out",          # universal asset identifier (bytes32)
    "deadline",           # block number or timestamp (uint64)
    "max_total_gas",      # USD equivalent across all chains (uint128)
    "min_finality",       # FAST | STANDARD | SECURE (uint8 enum)
    "min_nl_score",       # liquidity health floor, default 0.30 ×1000 → 300
    "chain_pref",         # OPTIMAL | [chain_list] | SINGLE_CHAIN
    "privacy",            # PUBLIC | ZK_CREDENTIAL | INVISIBLE (uint8 enum)
    "btcp_version",       # semver string (bytes12)
    "nonce",              # per-entity monotonic counter (uint64)
    "status",             # IntentStatus lifecycle enum
)

INTENT_ENUMS = (
    "Action", "Finality", "ChainPref", "Privacy", "IntentStatus",
)

ROUTE_FIELDS = (
    "route_id", "intent_id", "entity_id", "anchor_bh", "execution_bh",
    "anchor_chain", "execution_chain", "destination", "amount",
    "gas_saved", "btcp_version", "state", "created_ledger",
    "proved_ledger", "coherence_score", "parent_route_id", "finalized",
)

ROUTE_LIFECYCLE_METHODS = (
    "pub fn create(",       # §4.3 Step create
    "pub fn prove(",        # §4.3 Step prove — execution_bh + coherence
    "pub fn execute(",      # §4.3 Step execute
    "pub fn finalize(",     # §4.3 Step finalize — terminal success
    "pub fn revert(",       # §4.3 terminal revert + cascade (Gap 9)
    "pub fn get_route(",    # getter
)

ROUTE_STATES = ("Created", "Proved", "Executed", "Finalized", "Reverted")

# Spec §3 master equation — C(t) ≥ 0.55 floor enforced on-chain (×1000 = 550).
MIN_COHERENCE_SCORE_CONST = "pub const MIN_COHERENCE_SCORE: u32 = 550;"


def main():
    if not os.path.exists(INTENT_RS):
        print(f"FAIL — {INTENT_RS} missing")
        sys.exit(1)
    if not os.path.exists(ROUTE_RS):
        print(f"FAIL — {ROUTE_RS} missing")
        sys.exit(1)
    intent_src = open(INTENT_RS).read()
    route_src = open(ROUTE_RS).read()

    print("\n1) btcp-intent — §4.1 struct fields")
    for field in INTENT_FIELDS:
        pin = f"pub {field}:"
        check(f"Intent has field `{field}`", pin in intent_src,
              detail=f"expected `{pin}` in btcp-intent/src/lib.rs")

    print("\n2) btcp-intent — §4.1 enums")
    for enum in INTENT_ENUMS:
        pin = f"pub enum {enum}"
        check(f"enum `{enum}` declared", pin in intent_src)

    print("\n3) btcp-intent — lifecycle transition + nonce")
    check("transition() method present", "pub fn transition(" in intent_src)
    check("register_intent() method present", "pub fn register_intent(" in intent_src)
    check("get_intent() method present", "pub fn get_intent(" in intent_src)
    check("next_nonce() method present", "pub fn next_nonce(" in intent_src)
    check("entity_nonce map key",
          'KEY_ENTITY_NONCE: Symbol = symbol_short!("entnonce")' in intent_src)

    print("\n4) btcp-route — §4.3 RouteData fields")
    for field in ROUTE_FIELDS:
        pin = f"pub {field}:"
        check(f"RouteData has field `{field}`", pin in route_src,
              detail=f"expected `{pin}` in btcp-route/src/lib.rs")

    print("\n5) btcp-route — §4.3 lifecycle methods (create → prove → execute → finalize)")
    for pin in ROUTE_LIFECYCLE_METHODS:
        check(f"method `{pin.strip(' (')}` present", pin in route_src)

    print("\n6) btcp-route — §4.3 RouteState enum")
    for state in ROUTE_STATES:
        pin = f"{state},"
        # Enum variant declaration looks like `Created = 0,`
        check(f"RouteState::{state} variant", f"{state} =" in route_src)

    print("\n7) btcp-route — §3 0.55 coherence floor (×1000 = 550)")
    check("MIN_COHERENCE_SCORE = 550 const declared",
          MIN_COHERENCE_SCORE_CONST in route_src)
    check("prove() enforces CoherenceBelowFloor",
          "CoherenceBelowFloor" in route_src and
          "coherence_score < MIN_COHERENCE_SCORE" in route_src)
    check("prove() rejects score > 1000 sanity bound",
          "coherence_score > 1000" in route_src)

    print("\n8) btcp-route — cascade revert (Gap 9)")
    check("parent_route_id field on RouteData",
          "pub parent_route_id:" in route_src)
    check("revert() cascades to parent", "Self::revert(env, invoker, parent_id)" in route_src)

    print("\n9) Stub-replacement regression guards — generic Record must NOT exist")
    check("no generic `Record {` in btcp-intent", "struct Record {" not in intent_src)
    check("no generic `Record {` in btcp-route", "struct Record {" not in route_src)
    check("no `GenericContract` in btcp-intent", "GenericContract" not in intent_src)
    check("no `GenericContract` in btcp-route", "GenericContract" not in route_src)
    check("no `update_status` placeholder in btcp-intent", "update_status" not in intent_src)
    check("no `update_status` placeholder in btcp-route", "update_status" not in route_src)

    print(f"\n{'='*70}")
    print(f"PASS: {len(PASSED)}    FAIL: {len(FAILED)}")
    if FAILED:
        print("FAILED:")
        for n in FAILED:
            print(f"  - {n}")
        sys.exit(1)
    print("All §4.1 / §4.3 source pins verified.")


if __name__ == "__main__":
    main()
