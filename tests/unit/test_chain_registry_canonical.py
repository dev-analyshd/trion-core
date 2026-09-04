"""Canonical chain-registry enforcement — Wave 3, Agent C (matrix #17).

config/chain_registry.json is the ONE registry. This module pins the
registry's integrity invariants and the "zero scattered hardcoding"
property that Waves 1-3 established:

  1. counts declared == counts actual (129 / 18 / 40), everywhere they
     are restated in prose (docstrings included);
  2. all three generated binding artifacts regenerate byte-identical
     from the registry (Python + the two TypeScript twins);
  3. SCAN: no file outside the allow-list below may hardcode a canonical
     registry chain id. The allow-list entries are documented residuals
     (Rust static lists, Go static table, RPC-protocol ids, single-value
     defaults) — adding a NEW hardcoded registry id requires a conscious
     allow-list edit, exactly like tests/unit/test_no_sys_path_hacks.py;
  4. integrated=true means "has a live ingestion path": every integrated
     chain must resolve to a streamer worker, an indexer crate or a
     relayer entry, and every chain with NO path must be
     integrated=false (the Moonriver regression class, ce476c1);
  5. the ingestion surfaces themselves are cross-checked against the
     registry: relayer.js (boot-validated), indexer crates, the Go
     health table, and the chains/ executors (which import the
     generated TypeScript bindings — no literals at all).

Off-registry chains are NOT errors per se — they are pinned decisions:
hyperliquid 999 (Task 21-c), 0G Galileo 16602, 0G Newton 16600, and the
relayer_non_evm.js locals (provenance 4011, pi 8001, kadena 8500, icp
8600, bittensor 8700, flow 8900, zilliqa 9100, layerzero 9300) — see
tests/unit/test_backfill_chain_ids.py.

Run: pytest tests/unit/test_chain_registry_canonical.py -q
"""
import ast
import importlib.util
import json
import os
import re
import subprocess
import sys

from core import generated_chain_bindings as gcb

ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", ".."))
REGISTRY_PATH = os.path.join(ROOT, "config", "chain_registry.json")
GENERATOR_PATH = os.path.join(ROOT, "scripts", "generate_chain_bindings.py")
PY_BINDINGS = os.path.join(ROOT, "core", "generated_chain_bindings.py")
TS_BINDINGS_SDK = os.path.join(ROOT, "sdk", "src", "generated_chain_ids.ts")
TS_BINDINGS_CHAINS = os.path.join(ROOT, "chains", "shared", "generated_chain_ids.ts")
STREAMER_PY = os.path.join(ROOT, "core", "realtime", "bh_streamer.py")
RELAYER_JS = os.path.join(ROOT, "relayer", "relayer.js")
RELAYER_NON_EVM_JS = os.path.join(ROOT, "relayer", "relayer_non_evm.js")
HEALTH_GO = os.path.join(ROOT, "network", "health_monitor.go")
ZG_CONFIG_PY = os.path.join(ROOT, "zg", "zg_config.py")
DEPLOY_MAINNET_PY = os.path.join(ROOT, "scripts", "deploy_mainnet.py")
CRATES_DIR = os.path.join(ROOT, "indexers", "crates")

with open(REGISTRY_PATH) as _f:
    REGISTRY = json.load(_f)
REG_CHAINS = REGISTRY["chains"]
CANONICAL_IDS = {c["chainId"] for c in REG_CHAINS}
ID_TO_NAME = {c["chainId"]: c["name"] for c in REG_CHAINS}
INTEGRATED = {c["chainId"] for c in REG_CHAINS if c.get("integrated")}

# Off-registry chain ids that are DOCUMENTED decisions (see module docstring
# and tests/unit/test_backfill_chain_ids.py). Anything else off-registry in an
# ingestion path is a bug.
DOCUMENTED_OFF_REGISTRY = {
    999: "hyperliquid (HyperEVM native id, Task 21-c)",
    16602: "0G Galileo testnet",
    16600: "0G Newton testnet (own id; NOT Galileo's 16602)",
    4011: "provenance (relayer_non_evm local)",
    8001: "pi (relayer_non_evm local)",
    8500: "kadena (relayer_non_evm local)",
    8600: "icp (relayer_non_evm local)",
    8700: "bittensor (relayer_non_evm local)",
    8900: "flow (relayer_non_evm local)",
    9100: "zilliqa (relayer_non_evm local)",
    9300: "layerzero (relayer_non_evm local)",
}


# ── 1. registry integrity ────────────────────────────────────────────────────


def test_registry_counts_are_129_18_40():
    assert len(REG_CHAINS) == REGISTRY["total_chains"] == 129
    assert len({c["vm"] for c in REG_CHAINS}) == REGISTRY["vm_families"] == 18
    assert len(INTEGRATED) == REGISTRY["integrated_chains"] == 40
    assert sum(REGISTRY["vm_distribution"].values()) == 129


def test_api_registry_docstring_counts_match():
    """Prose counts must track the registry (the stale '41 integrated'
    after the Moonriver flip was exactly this class of drift)."""
    src = open(os.path.join(ROOT, "api", "chains_registry.py")).read()
    m = re.search(
        r"(\d+) chains across (\d+) VM families; (\d+) integrated", src
    )
    assert m, "api/chains_registry.py docstring no longer restates counts"
    assert int(m.group(1)) == 129
    assert int(m.group(2)) == 18
    assert int(m.group(3)) == 40


# ── 2. generated bindings regenerate byte-identical ──────────────────────────


def test_ts_bindings_regenerate_byte_identical(tmp_path):
    """Both TypeScript twins must be exactly what the generator emits for
    the current registry (the py twin is pinned by
    test_generated_chain_bindings.py::test_generator_output_is_up_to_date)."""
    out_sdk = tmp_path / "sdk_ids.ts"
    out_chains = tmp_path / "chains_ids.ts"
    out_py = tmp_path / "bindings.py"
    subprocess.run(
        [sys.executable, GENERATOR_PATH,
         "--output", str(out_py),
         "--ts-output", str(out_sdk),
         "--ts-output-chains", str(out_chains)],
        check=True, capture_output=True, timeout=60,
    )
    assert open(TS_BINDINGS_SDK).read() == out_sdk.read_text(), (
        "sdk/src/generated_chain_ids.ts is stale — run "
        "scripts/generate_chain_bindings.py and commit all three artifacts"
    )
    assert open(TS_BINDINGS_CHAINS).read() == out_chains.read_text(), (
        "chains/shared/generated_chain_ids.ts is stale — run "
        "scripts/generate_chain_bindings.py and commit all three artifacts"
    )


def test_py_bindings_still_byte_identical(tmp_path):
    out_py = tmp_path / "bindings.py"
    subprocess.run(
        [sys.executable, GENERATOR_PATH,
         "--output", str(out_py),
         "--ts-output", str(tmp_path / "a.ts"),
         "--ts-output-chains", str(tmp_path / "b.ts")],
        check=True, capture_output=True, timeout=60,
    )
    assert open(PY_BINDINGS).read() == out_py.read_text()


# ── 3. SCAN: no new hardcoded canonical chain ids ────────────────────────────

# Files that contain ≥1 canonical chain-id literal and why that is the
# documented, reviewed state. Everything else must derive ids from the
# registry / generated bindings. Adding an entry here is a conscious
# decision — justify it in the comment.
_SCAN_ALLOWLIST = {
    # Operator deployment table — cross-checked against the registry at
    # process start by validateChainsAgainstRegistry() (fail-closed), and
    # ids pinned by test_relayer_chains_join_registry below. Off-registry:
    # hyperliquid 999, 0g-galileo 16602 (both documented decisions).
    "relayer/relayer.js",
    # Re-keyed to canonical ids (e0bea25); off-registry locals are documented
    # in-file and pinned by tests/unit/test_backfill_chain_ids.py.
    "relayer/relayer_non_evm.js",
    # Rust indexer chain lists — static-only by mission order; ids and labels
    # are pinned against the registry by test_indexer_crates_match_registry.
    "indexers/crates/trion-algorand/src/main.rs",
    "indexers/crates/trion-aptos/src/main.rs",
    "indexers/crates/trion-botchain/src/main.rs",
    "indexers/crates/trion-cardano/src/main.rs",
    "indexers/crates/trion-cosmos/src/main.rs",
    "indexers/crates/trion-evm/src/main.rs",
    "indexers/crates/trion-hedera/src/main.rs",
    "indexers/crates/trion-movement/src/main.rs",
    "indexers/crates/trion-multiversx/src/main.rs",
    "indexers/crates/trion-near/src/main.rs",
    "indexers/crates/trion-pi/src/main.rs",
    "indexers/crates/trion-pvm/src/main.rs",
    "indexers/crates/trion-starknet/src/main.rs",
    "indexers/crates/trion-sui/src/main.rs",
    "indexers/crates/trion-svm/src/main.rs",
    "indexers/crates/trion-ton/src/main.rs",
    "indexers/crates/trion-tron/src/main.rs",
    "indexers/crates/trion-utxo/src/main.rs",
    "indexers/crates/trion-vechain/src/main.rs",
    "indexers/crates/trion-waves/src/main.rs",
    "indexers/crates/trion-xrpl/src/main.rs",
    # Go static health table — registry-anchored comment in-file; ids pinned
    # by test_go_health_monitor_ids_are_canonical.
    "network/health_monitor.go",
    # ethers.JsonRpcProvider(rpc, chainId) requires the chain's OWN EVM id —
    # an RPC-protocol value, not a TRION registry duplicate (they coincide).
    "evm-tools/deploy-cross-chain.mjs",
    "evm-tools/deploy-eth.mjs",
    "evm-tools/deploy-evm.mjs",
    "evm-tools/deploy-missing.mjs",
    # EVM Sepolia RPC provider ids in the EVM_CHAINS/EVM_CONFIG tables; the
    # BTCP cross-chain CHAIN maps import the generated bindings instead.
    "chains/starknet/src/loop-test.ts",
    "chains/starknet/src/per-vm-test.ts",
    # Single-target deploy scripts (ids are registry-equal by inspection).
    "scripts/deploy_execution_gate_0g.mjs",
    "scripts/zg_mainnet_deploy.mjs",
    # Demo/default single values (sample data, not registry tables).
    "scripts/init_trion.py",
    "scripts/simulate_attacks_onchain.py",
    # HTTP client SDK — must not import core; 421614 is a demo default.
    "sdk/trion_sdk.py",
    # core/ sample/test-vector/default parameter values (1, 137, 42161,
    # 8453, 421614) — single-value defaults, not chain tables. core/btcp is
    # Agent D/F territory (reported, not edited by C).
    "core/akashic/bibl.py",
    "core/akashic/bibl_pattern_store.py",
    "core/auditor/contract_auditor.py",
    "core/btcp/bibl_engine.py",
    "core/btcp/orchestrator.py",
    "core/btcp/router.py",
    "core/btcp/state_store.py",
    "core/governance/adaptive_consensus.py",
    "core/investment/investment_engine.py",
    "core/master/d_engine.py",
    "core/price/btcp_price_oracle.py",
    "core/primitives/behavioral_hash.py",
    "core/primitives/extended_payload.py",
    "core/trading/signal_engine.py",
    # M-owned API route file (Wave 3 Agent M): 0G block 16661 + demo default
    # 421614 — reported to M for registry derivation.
    "api/app.py",
}

_SCAN_DIRS = ("core", "api", "scripts", "sdk", "chains", "zg",
              "trion-0g", "evm-tools", "network", "relayer", "indexers/crates")
_SCAN_EXTS = (".py", ".ts", ".js", ".mjs", ".go", ".rs")
_SCAN_SKIP = {
    "core/generated_chain_bindings.py",       # the generated py bindings
    "chains/shared/generated_chain_ids.ts",   # generated TS twin
    "sdk/src/generated_chain_ids.ts",         # generated TS twin
}
_P_ASSIGN = re.compile(r"(?:\w*CHAIN\w*|\bchain_?[iI]d\w*)[^=\n]{0,40}=\s*(\d+)")
_P_KEY_CAMEL = re.compile(r"\bchainId\s*:\s*(\d+)")
_P_KEY_SNAKE = re.compile(r"\bchain_id\s*:\s*(\d+)")
_P_GO_TUPLE = re.compile(r'\{"[A-Z0-9_]+",\s*(\d+)\s*,')
_P_RS_TUPLE = re.compile(r'\(\s*(\d+)\s*,\s*"\w+_(?:MAINNET|TESTNET)"\)')


def _scan_hardcoded_ids():
    """{relative_path: set(canonical ids hardcoded there)} over the sweep dirs."""
    found = {}
    for d in _SCAN_DIRS:
        for dirpath, dirnames, filenames in os.walk(os.path.join(ROOT, d)):
            dirnames[:] = [x for x in dirnames
                           if x not in ("node_modules", "target", "__pycache__")]
            for fn in filenames:
                if not fn.endswith(_SCAN_EXTS):
                    continue
                rel = os.path.relpath(os.path.join(dirpath, fn), ROOT)
                if rel in _SCAN_SKIP:
                    continue
                try:
                    src = open(os.path.join(dirpath, fn), encoding="utf-8").read()
                except (OSError, UnicodeDecodeError):
                    continue
                ids = set()
                for pat in (_P_ASSIGN, _P_KEY_CAMEL, _P_KEY_SNAKE):
                    ids |= {int(m.group(1)) for m in pat.finditer(src)}
                if rel.endswith(".go"):
                    ids |= {int(m.group(1)) for m in _P_GO_TUPLE.finditer(src)}
                if rel.endswith(".rs"):
                    ids |= {int(m.group(1)) for m in _P_RS_TUPLE.finditer(src)}
                canon = ids & CANONICAL_IDS
                if canon:
                    found[rel] = canon
    return found


def test_no_new_hardcoded_canonical_chain_ids():
    """Snapshot pin (test_no_sys_path_hacks style): a canonical registry id
    may only be hardcoded in the allow-listed files. A NEW file (or a new
    literal in a clean file) fails here — derive from the registry or the
    generated bindings instead, or justify + allow-list consciously.

    NOTE: static scans are best-effort (a determined rename evades them);
    the pin's value is making the common path — copy-pasting a chain id —
    a visible, reviewable decision."""
    found = _scan_hardcoded_ids()
    unlisted = set(found) - _SCAN_ALLOWLIST
    assert not unlisted, (
        f"files hardcoding canonical chain ids outside the allow-list: "
        f"{sorted(unlisted)} — import the registry/generated bindings "
        f"(core.generated_chain_bindings / chains/shared/generated_chain_ids.ts "
        f"/ sdk/src/generated_chain_ids.ts) or add a justified allow-list entry"
    )
    stale = _SCAN_ALLOWLIST - set(found)
    assert not stale, (
        f"allow-list entries with no hardcoded canonical ids left (clean them "
        f"out): {sorted(stale)}"
    )


# ── 4. integrated == has a live ingestion path ───────────────────────────────


def _streamer_ids():
    src = open(STREAMER_PY).read()
    ids = set()
    for marker in ("CHAIN_RPCS: Dict[int, Dict] = {",
                   "NON_EVM_CHAINS: Dict[int, Dict] = {"):
        block = src[src.index(marker):]
        block = block[:block.index("\n}\n")]
        ids |= {int(m.group(1)) for m in
                re.finditer(r"^\s{4}(\d+):\s*\{", block, re.M)}
    return ids


def _crate_ids():
    ids = set()
    for name in sorted(os.listdir(CRATES_DIR)):
        main_rs = os.path.join(CRATES_DIR, name, "src", "main.rs")
        if not os.path.isfile(main_rs):
            continue
        src = open(main_rs).read()
        ids |= {int(m.group(1)) for m in re.finditer(r"chain_id:\s*(\d+)", src)}
        ids |= {int(m.group(1)) for m in _P_ASSIGN.finditer(src)}
        ids |= {int(m.group(1)) for m in _P_RS_TUPLE.finditer(src)}
    return ids


def _relayer_entry_ids():
    src = open(RELAYER_JS).read()
    ids = {int(m.group(1)) for m in
           re.finditer(r"chainId:\s*(\d+)", src)}
    src2 = open(RELAYER_NON_EVM_JS).read()
    block = src2[src2.index("const EXTENDED_CHAINS = ["):]
    block = block[:block.index("\n];")]
    ids |= {int(m.group(1)) for m in re.finditer(r"chainId:\s*(\d+)", block)}
    return ids


def _ingestion_paths():
    return {
        "streamer": _streamer_ids(),
        "crates": _crate_ids(),
        "relayer": _relayer_entry_ids(),
    }


def test_integrated_chains_have_live_ingestion_paths():
    """integrated=true must mean a streamer worker, indexer crate or
    relayer entry exists for that chain (the Moonriver class of lie)."""
    paths = _ingestion_paths()
    union = set().union(*paths.values())
    missing = INTEGRATED - union
    assert not missing, (
        f"integrated chains with no ingestion path anywhere: "
        f"{sorted(ID_TO_NAME.get(i, i) for i in missing)} — flip them to "
        f"integrated=false or add the ingestion path"
    )


def test_no_path_chains_are_not_integrated():
    """The honest inverse: a registry chain with no live path must claim
    integrated=false (agent 20-b's documented state — currently 25 chains)."""
    paths = _ingestion_paths()
    union = set().union(*paths.values())
    liars = [ID_TO_NAME[i] for i in sorted(CANONICAL_IDS - union)
             if i in INTEGRATED]
    assert not liars, f"no-path chains claiming integrated=true: {liars}"


# ── 5. ingestion surfaces vs the registry ────────────────────────────────────


def _relayer_entries():
    src = open(RELAYER_JS).read()
    return re.findall(
        r'\{\s*key:\s*"([^"]+)",\s*name:\s*"([^"]+)",\s*chainId:\s*(\d+)', src
    )


def test_relayer_chains_join_registry():
    """The relayer table is registry data joined by id: every canonical id
    must belong to the chain the entry claims (token-join with the two
    documented display-name aliases), off-registry entries are exactly the
    two documented decisions."""
    aliases = {"okt-chain": "OKB Chain (OKTC)", "bot-chain": "BotChain"}
    off_registry = {"hyperliquid": 999, "0g-galileo": 16602}
    generic = {"mainnet", "testnet", "chain", "network", "evm", "l2", "one"}
    toks = lambda s: {t for t in re.split(r"[^a-z0-9]+", s.lower())
                      if len(t) >= 2 and t not in generic}
    for key, name, cid in _relayer_entries():
        cid = int(cid)
        if key in off_registry:
            assert cid == off_registry[key], (
                f"off-registry chain {key} drifted from documented id "
                f"{off_registry[key]} to {cid}"
            )
            continue
        assert cid in CANONICAL_IDS, (
            f"relayer chain {key} ({name}) uses non-canonical id {cid}"
        )
        entry_name = aliases.get(key, name)
        reg_name = ID_TO_NAME[cid]
        assert toks(entry_name) & toks(reg_name) or \
            entry_name.replace(" ", "").lower() == reg_name.replace(" ", "").lower(), (
            f"relayer chain {key} (chainId {cid}) is named {name!r} but the "
            f"registry says id {cid} is {reg_name!r} — cross-chain id swap"
        )


def test_relayer_boot_validation_is_present():
    """The runtime join must not be deletable silently (it is the relayer's
    live guard; this test is its static twin)."""
    src = open(RELAYER_JS).read()
    assert "validateChainsAgainstRegistry" in src
    assert 'new URL("../config/chain_registry.json", import.meta.url)' in src
    assert "_OFF_REGISTRY_CHAINS" in src


def test_indexer_crates_match_registry():
    """Rust chain lists (static-only): ids are canonical or the documented
    off-registry set; labels are unique; ZG_NEWTON is Newton's own 16600
    (NOT Galileo 16602 — the pre-Wave-3 mislabel)."""
    all_labels = {}
    for name in sorted(os.listdir(CRATES_DIR)):
        main_rs = os.path.join(CRATES_DIR, name, "src", "main.rs")
        if not os.path.isfile(main_rs):
            continue
        src = open(main_rs).read()
        ids = {int(m.group(1)) for m in re.finditer(r"chain_id:\s*(\d+)", src)}
        ids |= {int(m.group(1)) for m in _P_ASSIGN.finditer(src)}
        ids |= {int(m.group(1)) for m in _P_RS_TUPLE.finditer(src)}
        bad = ids - CANONICAL_IDS - set(DOCUMENTED_OFF_REGISTRY)
        assert not bad, (
            f"{name}: chain ids neither canonical nor documented off-registry: "
            f"{sorted(bad)}"
        )
        for m in re.finditer(r'label:\s*"([A-Z0-9_]+)",\s*chain_id:\s*(\d+)', src):
            label, cid = m.group(1), int(m.group(2))
            assert label not in all_labels, (
                f"duplicate indexer label {label} ({name} vs {all_labels[label]})"
            )
            all_labels[label] = name
    # ZG_NEWTON regression: label says Newton, id must be Newton's own 16600
    evm_src = open(os.path.join(CRATES_DIR, "trion-evm", "src", "main.rs")).read()
    m = re.search(r'label:\s*"ZG_NEWTON",\s*chain_id:\s*(\d+)', evm_src)
    assert m and int(m.group(1)) == 16600, (
        "ZG_NEWTON must use 0G Newton's own chain id 16600 (16602 is Galileo)"
    )
    gal = re.search(r'chainId:\s*16602|chain_id:\s*16602', evm_src)
    assert gal is None or "ZG_GALILEO" in evm_src


def test_go_health_monitor_ids_are_canonical():
    """Go static table: ids canonical (or the documented 0/service ids) and
    the VM classification matches the registry per chain (a mislabelled
    id would classify under the wrong VM)."""
    src = open(HEALTH_GO).read()
    entries = re.findall(r'\{"([A-Z0-9_]+)",\s*(\d+)\s*,\s*"([A-Z]+|INTERNAL)"', src)
    labels = [e[0] for e in entries]
    assert len(labels) == len(set(labels)), "duplicate health-monitor labels"
    vm_by_id = {c["chainId"]: c["vm"] for c in REG_CHAINS}
    for label, cid, vm_type in entries:
        cid = int(cid)
        if cid == 0 or cid == 16602:
            continue  # internal services / documented off-registry Galileo
        assert cid in CANONICAL_IDS, (
            f"health_monitor.go {label}: off-registry id {cid}"
        )
        assert vm_type == vm_by_id[cid], (
            f"health_monitor.go {label} (id {cid}): vm {vm_type} vs registry "
            f"{vm_by_id[cid]} — mislabelled chain id"
        )


def test_chains_executors_import_generated_ids():
    """All chains/<vm>/execute.ts files derive their chain id from the
    generated TypeScript bindings — zero literals (scan-pinned too)."""
    for vm in ("near", "ton", "starknet", "sui", "svm", "pvm", "botchain"):
        path = os.path.join(ROOT, "chains", vm, "execute.ts")
        src = open(path).read()
        assert "generated_chain_ids.js" in src, (
            f"{path} no longer imports the generated chain bindings"
        )
        assert not re.search(r"\bCHAIN_ID\w*\s*(?::\s*\w+\s*)?=\s*\d+", src), (
            f"{path} reintroduced a literal chain id"
        )


def test_no_legacy_chain_ids_in_chains_dir():
    """The pre-Wave-3 legacy namespace (starknet 1300 / near 1200 / ton
    1100) must not come back anywhere under chains/ (comments documenting
    the history are fine — only live code is checked)."""
    for dirpath, dirnames, filenames in os.walk(os.path.join(ROOT, "chains")):
        dirnames[:] = [x for x in dirnames
                       if x not in ("node_modules", "target", "__pycache__")]
        for fn in filenames:
            if not fn.endswith((".ts", ".js", ".mjs")):
                continue
            src = open(os.path.join(dirpath, fn), encoding="utf-8").read()
            # strip // and /* */ comments so history notes stay legal
            src = re.sub(r"/\*.*?\*/", "", src, flags=re.S)
            src = re.sub(r"//[^\n]*", "", src)
            for legacy, canonical in ((1300, 24001), (1200, 23000), (1100, 22000)):
                assert not re.search(
                    rf"(?:CHAIN|STARKNET|NEAR|TON)\s*:\s*{legacy}\b", src
                ), (
                    f"{fn}: legacy chain id {legacy} (canonical {canonical}) "
                    f"is back"
                )


def test_sdk_has_no_numeric_chain_ids():
    """The TS SDK derives ids from the generated bindings (no literals)."""
    for path in ("sdk/TrionSDK.ts", "sdk/src/index.ts"):
        src = open(os.path.join(ROOT, path)).read()
        assert not re.search(r"chainId:\s*\d+", src), (
            f"{path} hardcodes a numeric chainId — import the generated "
            f"bindings (sdk/src/generated_chain_ids.ts) instead"
        )
        assert "generated_chain_ids" in src


def test_zg_config_derives_ids_from_registry():
    spec = importlib.util.spec_from_file_location("zg_config_under_test", ZG_CONFIG_PY)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    assert mod.ZGConfig.MAINNET_CHAIN_ID == gcb.CHAIN_ID_0G_MAINNET == 16661
    assert mod.ZGConfig.TESTNET_CHAIN_ID == 16602  # documented off-registry


def test_deploy_mainnet_ids_derive_from_registry():
    tree = ast.parse(open(DEPLOY_MAINNET_PY).read())
    table = {}
    for node in ast.walk(tree):
        if isinstance(node, ast.Assign):
            for t in node.targets:
                if isinstance(t, ast.Name) and t.id == "MAINNET_CHAINS":
                    for k, v in zip(node.value.keys, node.value.values):
                        cid = None
                        for ck, cv in zip(v.keys, v.values):
                            if isinstance(ck, ast.Constant) and ck.value == "chain_id":
                                cid = cv
                        table[k.value] = cid
    assert table, "MAINNET_CHAINS table not found in deploy_mainnet.py"
    id_to_reg_name = {v: k for k, v in gcb.CHAIN_IDS.items()}
    expected = {
        "ethereum": "Ethereum",
        "arbitrum": "Arbitrum One",
        "optimism": "Optimism",
        "base": "Base",
        "polygon": "Polygon PoS",
        "bnb": "BNB Smart Chain",
        "avalanche": "Avalanche C-Chain",
        "solana": "Solana Mainnet",
        "0g": "0G Mainnet",
    }
    assert set(table) == set(expected), (
        f"deploy_mainnet.py chain set drifted: {sorted(set(table) ^ set(expected))}"
    )
    for key, cid_node in table.items():
        assert isinstance(cid_node, ast.Call) and \
            getattr(cid_node.func, "id", "") == "_cid", (
                f"deploy_mainnet.py {key}: chain_id is not registry-derived "
                f"(expected _cid(...) call)"
            )
        assert cid_node.args[0].value == expected[key], (
            f"deploy_mainnet.py {key}: resolves registry entry "
            f"{cid_node.args[0].value!r}, expected {expected[key]!r}"
        )
