"""
Legacy chain-id namespace cleanup — backfill / relayer / bootstrap
==================================================================

Prior audit (Task 20-b): the genesis backfill scripts, the non-EVM relayer
and the mainnet bootstrap carried legacy ad-hoc chain ids diverging from
the canonical 129-chain registry (config/chain_registry.json — the single
source of truth per P3-CONSOLIDATE, mirrored in
core/generated_chain_bindings.py).  The worst case was POLKADOT backfill
writing chain_id 900 — a hard collision with canonical Solana 900.

These tests pin the re-key (the c93d237 streamer treatment, applied to the
remaining ingestion paths):

  * anima-service/genesis_backfill_*.py — every chain that exists in the
    canonical registry is keyed by its canonical id (polkadot 25000,
    solana 900, stellar 27000, cosmos 10000-series, …).  Provenance is
    off-registry and keeps its legacy local id (documented in the script).
  * relayer/relayer_non_evm.js EXTENDED_CHAINS — canonical ids for every
    registry chain (stellar 8800 → 27000, btc 2000 → 21000, …);
    off-registry chains (pi, kadena, icp, bittensor, flow, zilliqa,
    layerzero, provenance) keep documented local ids.
  * core/btcp/mainnet_bootstrap.py — Solana is the canonical 900 (was a
    local 5773521), and no bootstrap chain id collides with a DIFFERENT
    canonical chain.
  * hyperliquid 999 decision, pinned: 999 is HyperEVM's native chain id,
  it does NOT collide with any canonical registry id, and the streamer
  keeps ingesting it as a documented off-registry chain (a 130th registry
  entry would ripple counts/bindings/api — not justified by a testnet-RPC
  streamer worker with no Rust indexer; see worklog Task 21-c).

Scripts are parsed with ast/regex instead of imported: the backfill
modules hit the network at import-adjacent call sites and must never run
inside the unit suite.

Run: pytest tests/unit/test_backfill_chain_ids.py -q
"""

import ast
import json
import os
import re

from core import generated_chain_bindings as gcb

ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", ".."))
BACKFILL_DIR = os.path.join(ROOT, "anima-service")
RELAYER_JS = os.path.join(ROOT, "relayer", "relayer_non_evm.js")
BOOTSTRAP_PY = os.path.join(ROOT, "core", "btcp", "mainnet_bootstrap.py")
STREAMER_PY = os.path.join(ROOT, "core", "realtime", "bh_streamer.py")

with open(os.path.join(ROOT, "config", "chain_registry.json")) as _f:
    _REGISTRY = json.load(_f)
CANONICAL_IDS = {c["chainId"] for c in _REGISTRY["chains"]}
CANONICAL_NAMES = {c["name"].lower() for c in _REGISTRY["chains"]}


# ── helpers ──────────────────────────────────────────────────────────────────


def _backfill_scripts():
    for fname in sorted(os.listdir(BACKFILL_DIR)):
        if fname.startswith("genesis_backfill") and fname.endswith(".py"):
            yield os.path.join(BACKFILL_DIR, fname)


def _module_constants(path):
    """{UPPER_CONSTANT_NAME: value} for module-level assignments."""
    tree = ast.parse(open(path).read())
    out = {}
    for node in tree.body:
        if isinstance(node, ast.Assign):
            for target in node.targets:
                if isinstance(target, ast.Name) and target.id.isupper():
                    try:
                        out[target.id] = ast.literal_eval(node.value)
                    except ValueError:
                        pass
        elif isinstance(node, ast.AnnAssign) and node.value is not None:
            if isinstance(node.target, ast.Name) and node.target.id.isupper():
                try:
                    out[target.id] = ast.literal_eval(node.value)
                except ValueError:
                    pass
    return out


def _dict_chain_ids(path, dict_name):
    """{chain-key: chain_id} for a module-level dict of per-chain configs."""
    tree = ast.parse(open(path).read())
    for node in tree.body:
        if isinstance(node, ast.Assign) and any(
            isinstance(t, ast.Name) and t.id == dict_name for t in node.targets
        ):
            entries = {}
            if not isinstance(node.value, ast.Dict):
                return {}
            for key_node, value_node in zip(node.value.keys, node.value.values):
                if not (isinstance(key_node, ast.Constant)
                        and isinstance(value_node, ast.Dict)):
                    continue
                chain_key = key_node.value
                for k, v in zip(value_node.keys, value_node.values):
                    if (isinstance(k, ast.Constant) and k.value == "chain_id"
                            and isinstance(v, ast.Constant)):
                        entries[chain_key] = v.value
            return entries
    return {}


def _relayer_extended_chains():
    """[(key, name, chainId)] parsed from relayer_non_evm.js EXTENDED_CHAINS."""
    src = open(RELAYER_JS).read()
    block = re.search(
        r"const EXTENDED_CHAINS = \[(.*?)\n\];", src, re.DOTALL
    ).group(1)
    return re.findall(
        r'\{\s*key:\s*"([^"]+)",\s*name:\s*"([^"]+)",\s*chainId:\s*(\d+)', block
    )


# legacy ids that must no longer appear as a keyed chain id anywhere in the
# re-keyed ingestion paths (the audit's third/fourth namespaces)
_LEGACY_IDS = {
    900: "polkadot-backfill (collides with canonical Solana 900)",
    101: "solana-backfill (canonical 900)",
    100001: "stellar-backfill (canonical 27000)",
    1100: "ton-backfill (canonical 22000)",
    1200: "near-backfill (canonical 23000)",
    8000: "starknet-backfill (canonical 24000)",
    70001: "xrpl-backfill (canonical 31000)",
    120001: "waves-backfill (canonical 30000)",
    110001: "vechain-backfill (canonical 29000)",
    40001: "btc-backfill (canonical 21000)",
    40002: "ltc-backfill (canonical 21004)",
    40003: "doge-backfill (canonical 21003)",
    40004: "dash-backfill (canonical 21005)",
    60001: "tron-backfill (canonical 26000)",
    50001: "sui-backfill (canonical 20100)",
    130001: "multiversx-backfill (canonical 32000)",
    30001: "aptos-backfill (canonical 20000)",
    30002: "movement-backfill (canonical 20200)",
    90001: "hedera-backfill (canonical 28000)",
    140001: "cardano-backfill (canonical 9400)",
    80001: "algorand-backfill (canonical 8200)",
    20001: "cosmos-hub-backfill (canonical 10000)",
    20002: "kava-backfill (canonical 10014)",
    20003: "injective-backfill (canonical 10004)",
    20004: "sei-backfill (canonical 10005)",
    20005: "dydx-backfill (canonical 10006)",
    20006: "initia-backfill (canonical 10015)",
    20007: "osmosis-backfill (canonical 10001)",
    20008: "neutron-backfill (canonical 10018)",
    20009: "celestia-backfill (canonical 10003)",
    20010: "terra-backfill (canonical 10009)",
    5773521: "bootstrap Solana (canonical 900)",
}


# ── genesis backfill scripts ─────────────────────────────────────────────────


def test_registry_ground_truth_is_129_chains():
    assert len(CANONICAL_IDS) == 129
    assert gcb.TOTAL_CHAINS == 129


def test_backfill_scripts_use_canonical_ids():
    """Every backfill chain id is either canonical or a documented
    off-registry local id (provenance); no legacy namespace remains."""
    off_registry_allowed = {20011: "provenance"}  # documented in the script
    for path in _backfill_scripts():
        for name, value in _module_constants(path).items():
            if name != "CHAIN_ID":
                continue
            assert value in CANONICAL_IDS or value in off_registry_allowed, (
                f"{os.path.basename(path)}: CHAIN_ID {value} is neither "
                f"canonical nor a documented off-registry id"
            )
        for dict_name in ("COSMOS_CHAINS", "UTXO_CHAINS", "MOVE_CHAINS"):
            for chain_key, cid in _dict_chain_ids(path, dict_name).items():
                assert cid in CANONICAL_IDS or chain_key in off_registry_allowed.values(), (
                    f"{os.path.basename(path)}: {chain_key} chain_id {cid} is "
                    f"not canonical"
                )


def test_polkadot_backfill_no_longer_collides_with_solana():
    consts = _module_constants(os.path.join(BACKFILL_DIR, "genesis_backfill_polkadot.py"))
    assert consts["CHAIN_ID"] == 25000  # canonical Polkadot
    assert consts["CHAIN_ID"] != gcb.CHAIN_ID_SOLANA_MAINNET  # 900 stays Solana-only


def test_solana_backfill_uses_canonical_900():
    consts = _module_constants(os.path.join(BACKFILL_DIR, "genesis_backfill_solana.py"))
    assert consts["CHAIN_ID"] == gcb.CHAIN_ID_SOLANA_MAINNET == 900


def test_stellar_backfill_uses_canonical_27000():
    consts = _module_constants(os.path.join(BACKFILL_DIR, "genesis_backfill_stellar.py"))
    assert consts["CHAIN_ID"] == gcb.CHAIN_ID_STELLAR_MAINNET == 27000


def test_no_legacy_ids_remain_in_backfill_scripts():
    """Redundant with the canonical-id test but stronger: the audit's legacy
    namespace values must not appear at all (900 stays legal ONLY where it is
    canonical — the solana script — and 20011 only for provenance)."""
    for path in _backfill_scripts():
        base = os.path.basename(path)
        ids = {v for v in _module_constants(path).values()
               if isinstance(v, int)}
        for dict_name in ("COSMOS_CHAINS", "UTXO_CHAINS", "MOVE_CHAINS"):
            ids |= set(_dict_chain_ids(path, dict_name).values())
        for legacy in _LEGACY_IDS:
            if legacy == 20011:
                continue  # provenance keeps its documented local id
            if legacy == 900 and base == "genesis_backfill_solana.py":
                continue  # 900 IS canonical Solana — legal in this script only
            assert legacy not in ids, (
                f"{base}: legacy id {legacy} "
                f"({_LEGACY_IDS[legacy]}) still present"
            )


def test_provenance_is_documented_off_registry():
    """Provenance has no canonical id — the script must say so."""
    src = open(os.path.join(BACKFILL_DIR, "genesis_backfill_cosmos.py")).read()
    assert "provenance is NOT in the canonical" in src
    assert 20011 not in CANONICAL_IDS  # and its local id collides with nothing


# ── relayer (non-EVM) ────────────────────────────────────────────────────────


def test_relayer_extended_chains_use_canonical_ids():
    """Registry chains carry canonical ids; off-registry chains are the
    documented local ones and collide with nothing canonical."""
    off_registry = {"provenance", "pi", "kadena", "icp", "bittensor",
                    "flow", "zilliqa", "layerzero"}
    for key, name, chain_id in _relayer_extended_chains():
        chain_id = int(chain_id)
        if key in off_registry:
            assert chain_id not in CANONICAL_IDS, (
                f"off-registry chain {key} unexpectedly uses canonical id "
                f"{chain_id} — reclassify it"
            )
        else:
            assert chain_id in CANONICAL_IDS, (
                f"relayer chain {key} ({name}) uses non-canonical id "
                f"{chain_id}"
            )


def test_relayer_stellar_is_canonical_27000():
    entries = {key: int(cid) for key, _n, cid in _relayer_extended_chains()}
    assert entries["stellar"] == 27000  # was 8800 (audit finding)


def test_relayer_ids_are_unique():
    entries = [int(cid) for _k, _n, cid in _relayer_extended_chains()]
    assert len(entries) == len(set(entries))


def test_relayer_off_registry_chains_are_documented():
    src = open(RELAYER_JS).read()
    for needle in ("NOT in the canonical 129-chain registry",
                   "not in the canonical registry"):
        assert needle in src


def test_no_legacy_relayer_ids_remain():
    src = open(RELAYER_JS).read()
    block = re.search(
        r"const EXTENDED_CHAINS = \[(.*?)\n\];", src, re.DOTALL
    ).group(1)
    for legacy, what in _LEGACY_IDS.items():
        if legacy == 20011:
            continue  # provenance keeps its documented local id
        assert f"chainId: {legacy}," not in block, (
            f"relayer still carries legacy id {legacy} ({what})"
        )


# ── mainnet bootstrap ────────────────────────────────────────────────────────


def test_bootstrap_solana_is_canonical_900():
    """The bootstrap plan no longer carries the local 5773521 namespace."""
    src = open(BOOTSTRAP_PY).read()
    assert re.search(r"ChainConfig\(900,\s*\"Solana\"", src)
    assert not re.search(r"ChainConfig\(5773521", src)


def test_bootstrap_ids_never_mislabel_a_canonical_chain():
    """A bootstrap id that is canonical must be the SAME chain as the
    registry entry (name-variant matches allowed, cross-chain ids are not)."""
    from core.btcp.mainnet_bootstrap import build_chain_registry

    canonical_by_id = {c["chainId"]: c["name"].lower()
                       for c in _REGISTRY["chains"]}
    variant_ok = {  # bootstrap display name → canonical registry name
        "polygon": "polygon pos", "bot chain": "botchain",
        "solana": "solana mainnet", "sui": "sui mainnet",
        "aptos": "aptos mainnet", "ton": "ton mainnet",
        "near protocol": "near mainnet", "dydx": "dydx",
        "sepolia": "ethereum sepolia", "holesky": "ethereum holesky",
        "chiado": "chiado (gnosis)", "okb chain": "okb chain (oktc)",
        "kaia (klaytn)": "kaia (klaytn)", "ethereum classic": "classic",
        "osmosis": "osmosis", "cosmos hub": "cosmos hub",
        "juno": "juno", "celestia": "celestia", "injective": "injective",
        "sei": "sei", "starknet": "starknet mainnet",
        "polkadot": "polkadot", "kusama": "kusama",
        "polkadot westend": "polkadot westend", "movement": "movement mainnet",
        "kava": "kava", "initia": "initia", "neutron": "neutron",
        "terra classic": "terra classic", "terra phoenix": "terra phoenix",
        "bitcoin": "bitcoin", "bitcoin cash": "bitcoin cash",
        "dogecoin": "dogecoin", "litecoin": "litecoin",
        "starknet sepolia": "starknet sepolia", "stellar mainnet": "stellar mainnet",
        "stellar testnet": "stellar testnet", "multiversx": "multiversx",
        "waves": "waves", "xrpl": "xrpl", "hedera": "hedera",
        "hedera testnet": "hedera testnet", "vechain": "vechain",
        "cardano preprod": "cardano preprod", "dash": "dash",
        "avalanche fuji": "avalanche fuji", "bnb testnet": "bnb testnet",
        "bitlayer": "bitlayer", "sei evm": "sei evm", "kava evm": "kava evm",
        "optopia": "optopia", "botanix": "botanix", "boba network": "boba network",
        "core": "core", "cyber": "cyber", "iota evm": "iota evm",
        "kroma": "kroma", "neon evm": "neon evm", "rootstock": "rootstock",
        "telos evm": "telos evm", "wemix": "wemix", "bob": "bob",
        "fraxtal": "fraxtal", "mantle": "mantle", "mode": "mode",
        "metis": "metis", "manta pacific": "manta pacific",
        "arbitrum one": "arbitrum one", "bnb smart chain": "bnb smart chain",
        "story protocol": "story protocol", "berachain": "berachain",
        "0g mainnet": "0g mainnet", "hashkey mainnet": "hashkey mainnet",
        "polygon zkevm": "polygon zkevm", "aurora": "aurora",
        "moonbeam": "moonbeam", "moonriver": "moonriver", "gnosis": "gnosis",
        "scroll": "scroll", "zksync era": "zksync era", "linea": "linea",
        "celo": "celo", "fantom": "fantom", "taiko": "taiko",
        "blast": "blast", "sonic": "sonic", "x layer": "x layer",
        "xdc network": "xdc network", "arbitrum sepolia": "arbitrum sepolia",
        "base sepolia": "base sepolia", "polygon amoy": "polygon amoy",
        "optimism sepolia": "optimism sepolia", "scroll sepolia": "scroll sepolia",
        "sui testnet": "sui testnet", "aptos testnet": "aptos testnet",
        "near testnet": "near testnet", "solana devnet": "solana devnet",
        "bitcoin testnet4": "bitcoin testnet4", "solana testnet": "solana testnet",
        "cardano": "cardano", "algorand": "algorand", "canto": "canto",
        "ethereum": "ethereum", "base": "base", "optimism": "optimism",
    }
    mismatches = []
    for c in build_chain_registry():
        canon_name = canonical_by_id.get(c.chain_id)
        if canon_name is None:
            continue  # bootstrap-local id (synthetic or legacy) — no collision
        bootstrap_name = c.name.lower()
        if canon_name == bootstrap_name:
            continue
        if variant_ok.get(bootstrap_name) == canon_name:
            continue  # display-name variant of the same chain
        mismatches.append((c.chain_id, c.name, canon_name))
    assert not mismatches, (
        "bootstrap chains whose id maps to a DIFFERENT canonical chain: "
        f"{mismatches}"
    )


# ── hyperliquid 999 decision (pinned) ────────────────────────────────────────


def test_hyperliquid_999_is_off_registry_and_collision_free():
    """Decision (Task 21-c): hyperliquid is ingested by the python streamer
    (bh_streamer.py worker → HyperEVM testnet RPC) and the EVM relayer under
    its NATIVE HyperEVM chain id 999.  It is absent from the canonical
    129-chain registry and its id collides with no registry chain, so it is
    documented as a known off-registry chain instead of being re-keyed or
    added as a 130th chain (which would ripple every count/bindings/api
    surface for a chain with no Rust indexer and a testnet RPC)."""
    assert 999 not in CANONICAL_IDS
    assert "hyperliquid" not in CANONICAL_NAMES
    assert "hyperliquid" not in {n.lower() for n in gcb.CHAIN_IDS}
    # the streamer worker keeps its native id (no re-key invented)
    src = open(STREAMER_PY).read()
    assert re.search(r"999:\s*\{\s*\"name\":\s*\"hyperliquid\"", src)
    # and the relayer entry documents the off-registry decision in place
    relayer_src = open(os.path.join(ROOT, "relayer", "relayer.js")).read()
    assert re.search(
        r'//\s*hyperliquid:\s*OFF-REGISTRY', relayer_src)
    assert re.search(r'chainId:\s*999,\s*rpcEnv:\s*"HYPERLIQ_RPC_URL"', relayer_src)
