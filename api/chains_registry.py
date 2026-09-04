"""
TRION Protocol — Chains Registry (API/frontend view)

DERIVED AT IMPORT from config/chain_registry.json — the canonical chain
registry (129 chains across 18 VM families; 41 integrated). This module is a
presentation layer over the registry: it adds display fields (status tier,
per-VM color, default indexer crate) and per-chain BH stats. The chain/VM
counts reported by /api/v1/chains and /api/v1/explorer/chains are therefore
always identical to the registry — the previous hand-maintained 160-entry /
22-VM table (which contradicted the registry by ~25%) is gone.

All BH proof counts and block heights are deterministic per chain using a hash
seed so they remain consistent across API calls.
"""
import hashlib
import json
import os
import re
import time

# ── Canonical registry load ──────────────────────────────────────────────────
# Single source of truth for chain/VM counts. Read relative to the repo root
# (this file lives in <root>/api/, the registry in <root>/config/).
_REGISTRY_PATH = os.path.normpath(
    os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "config", "chain_registry.json")
)
try:
    with open(_REGISTRY_PATH, "r", encoding="utf-8") as _f:
        _REGISTRY = json.load(_f)
except OSError as _e:  # pragma: no cover - fail loudly, never serve stale counts
    raise ImportError(
        f"api.chains_registry: canonical registry not readable at {_REGISTRY_PATH} ({_e}). "
        "This module derives every chain/VM figure from config/chain_registry.json."
    ) from _e

REGISTRY_CHAINS = _REGISTRY["chains"]

# ── Presentation tables (registry carries no UI metadata) ────────────────────

# Stable display color per VM family.
_VM_COLORS = {
    "EVM": "#627EEA", "SVM": "#9945FF", "COSMOS": "#2E3148", "MOVE": "#00C2FF",
    "UTXO": "#F7931A", "CARDANO": "#0D1E2D", "NEAR": "#00C08B", "STARKNET": "#FEBB53",
    "TON": "#0088CC", "TRON": "#FF0013", "STELLAR": "#9D4EDD", "PVM": "#E6007A",
    "XRPL": "#00AAE4", "WAVES": "#0155FF", "VECHAIN": "#15BDFF", "MULTIVERSX": "#23F7DD",
    "HEDERA": "#222222", "ALGORAND": "#000000",
}

# Default indexer crate per VM family (a registry `indexer` field wins when set).
_VM_INDEXER = {
    "EVM": "trion-evm", "SVM": "trion-svm", "COSMOS": "trion-cosmos",
    "MOVE": "trion-aptos", "UTXO": "trion-utxo", "CARDANO": "trion-cardano",
    "NEAR": "trion-near", "STARKNET": "trion-starknet", "TON": "trion-ton",
    "TRON": "trion-tron", "STELLAR": "trion-pi", "PVM": "trion-pvm",
    "XRPL": "trion-xrpl", "WAVES": "trion-waves", "VECHAIN": "trion-vechain",
    "MULTIVERSX": "trion-multiversx", "HEDERA": "trion-hedera",
    "ALGORAND": "trion-algorand",
}
# MOVE family has one crate per chain name.
_MOVE_INDEXER_BY_NAME = (
    ("Aptos", "trion-aptos"), ("Sui", "trion-sui"), ("Movement", "trion-movement"),
)

# Explicit bh_ledger chain_label overrides (aliases that do not follow the
# automatic id/name derivation below). Kept from the pre-derivation table.
_BH_LABEL = {
    "Ethereum": "ETH_MAINNET",
    "0G Mainnet": "ZG_MAINNET",
    "Manta Pacific": "MANTA_PACIFIC",
    "Monad": "MONAD_MAINNET",
    "Solana Devnet": "SOLANA_DEVNET",
}

# ── bh_ledger label → VM classification ──────────────────────────────────────
# The ledger's chain_label column carries TWO writer conventions: the Rust
# indexers write UPPERCASE labels (ETH_MAINNET, SOLANA_MAINNET, …) while the
# python streamer writes its registry-style names verbatim (ethereum,
# solana, zg_mainnet, cosmos_hub, …). Both must resolve to the same VM
# family — previously only the uppercase convention was recognised, so a
# streamer-fed ledger classified EVERY chain as non-EVM and the EVM/SVM/ZG
# buckets of /api/v1/bh/vm_feed and /api/v1/bh/chains stayed empty.
_BH_LABEL_VM_LEGACY = {
    **{lbl.lower(): "EVM" for lbl in (
        "ETH_MAINNET", "ARB_MAINNET", "BASE_MAINNET", "OP_MAINNET", "BNB_MAINNET",
        "LINEA_MAINNET", "LINEA", "MANTLE_MAINNET", "MANTLE", "SCROLL_MAINNET",
        "SCROLL", "HASHKEY_MAINNET", "HASHKEY", "ETH_SEPOLIA", "ARB_SEPOLIA",
        "BASE_SEPOLIA", "OP_SEPOLIA", "BNB_TESTNET",
    )},
    # 0G chains group together (the pre-registry endpoint put ZG_GALILEO in
    # the EVM bucket — a misclassification kept here no longer)
    "solana_mainnet": "SVM", "solana_devnet": "SVM",
    "zg_mainnet": "ZG", "zg_galileo": "ZG", "zg_newton": "ZG",
    # python streamer EVM short-names not equal to registry slugs
    "bnb": "EVM", "polygon": "EVM", "avalanche": "EVM", "blast": "EVM",
    "fraxtal": "EVM", "kava_evm": "EVM", "etc": "EVM", "iota_evm": "EVM",
    "bot_chain": "EVM", "hyperliquid": "EVM", "bitlayer": "EVM",
}


def _build_bh_label_vm_map() -> dict:
    """lowercased label → VM family, covering both ledger writers."""
    m = dict(_BH_LABEL_VM_LEGACY)
    # canonical registry: display name / slug / label forms, any case
    for c in CHAINS:
        vm = str(c.get("vm", "")).upper()
        name_l = str(c.get("name", "")).lower()
        # 0G chains group separately in the bh endpoints though registry VM
        # is EVM.
        grp = "ZG" if (vm == "EVM" and name_l.startswith("zg")) else vm
        for key in (name_l, name_l.replace(" ", "_"),
                    str(c.get("id", "") or "").lower().replace("-", "_")):
            if key:
                m.setdefault(key, grp)
    # the python streamer's own chain names are the live-path labels —
    # resolve them straight from its registries so nothing is missed
    try:
        from core.realtime.bh_streamer import CHAIN_RPCS as _st_evm, NON_EVM_CHAINS as _st_nonevm
        for _cfg in _st_evm.values():
            m.setdefault(str(_cfg.get("name", "")).lower(), "EVM")
        for _cfg in _st_nonevm.values():
            _vm = str(_cfg.get("vm", "")).upper()
            _nm = str(_cfg.get("name", "")).lower()
            m.setdefault(_nm, "ZG" if _nm.startswith("zg") else _vm)
    except Exception:  # streamer import unavailable (e.g. packaged api-only)
        pass
    return m


def classify_bh_label(label) -> str:
    """VM family for a bh_ledger chain_label (either writer convention).

    Returns the registry VM family (EVM, SVM, MOVE, COSMOS, …, ZG); labels
    unknown to both conventions classify as "UNKNOWN".
    """
    return BH_LABEL_VM.get(str(label or "").strip().lower(), "UNKNOWN")

# Testnet-name detection for the status tier (the registry marks integration,
# not environment tier).
_TESTNET_TOKENS = (
    "testnet", "sepolia", "devnet", "amoy", "fuji", "holesky",
    "shasta", "preprod", "bardock", "galileo", "westend",
)


def _slug(name: str) -> str:
    """Registry display name → URL-safe id ("Arbitrum One" → "arbitrum-one")."""
    return re.sub(r"[^a-z0-9]+", "-", name.lower()).strip("-")


def _status(chain: dict) -> str:
    """Status tier derived from the registry.

    testnet  — name identifies a testnet/staging environment
    live     — registry `integrated` is true (live indexer + oracle)
    indexed  — registered but not yet integrated
    """
    lowered = chain["name"].lower()
    if any(tok in lowered for tok in _TESTNET_TOKENS):
        return "testnet"
    if chain.get("integrated"):
        return "live"
    return "indexed"


def _indexer(chain: dict) -> str:
    if chain.get("indexer"):
        return chain["indexer"]
    if chain["vm"] == "MOVE":
        for prefix, crate in _MOVE_INDEXER_BY_NAME:
            if chain["name"].startswith(prefix):
                return crate
    return _VM_INDEXER.get(chain["vm"], "trion-evm")


# ── Chain catalog (derived) ──────────────────────────────────────────────────
# Each entry carries the full registry record (name, vm, chainId, rpc,
# finalitySec, gasUsd, explorer, nativeToken, decimals, notes, …) plus the
# presentation fields the frontend expects.
CHAINS = [
    {
        "id": _slug(c["name"]),
        "name": c["name"],
        "vm": c["vm"],
        "chain_id": c["chainId"],
        "status": _status(c),
        "color": _VM_COLORS.get(c["vm"], "#4b5563"),
        "indexer": _indexer(c),
        "bh_label": _BH_LABEL.get(c["name"]),
        "note": c.get("notes"),
        "rpc": c.get("rpc"),
        "explorer": c.get("explorer"),
        "native_token": c.get("nativeToken"),
        "decimals": c.get("decimals"),
        "finality_sec": c.get("finalitySec"),
        "gas_usd": c.get("gasUsd"),
        "integrated": bool(c.get("integrated")),
    }
    for c in REGISTRY_CHAINS
]

# Registry-derived counts (exported for anything that wants the canonical
# numbers without recomputing them).
TOTAL_CHAINS = len(CHAINS)
VM_FAMILIES = len({c["vm"] for c in CHAINS})
INTEGRATED_CHAINS = sum(1 for c in CHAINS if c["integrated"])

# Built after CHAINS (see _build_bh_label_vm_map above).
BH_LABEL_VM = _build_bh_label_vm_map()


# BH proof baselines per status tier
_PROOF_BASE = {"live": 2_400_000, "testnet": 180_000, "indexed": 45_000}
# Block height baselines per VM family (registry family codes)
_BLOCK_BASE = {
    "EVM": 50_000_000, "SVM": 280_000_000, "UTXO": 840_000,
    "CARDANO": 9_800_000, "COSMOS": 18_000_000, "MOVE": 3_200_000,
    "STARKNET": 620_000, "TON": 42_000_000, "TRON": 42_000_000,
    "PVM": 8_500_000, "NEAR": 120_000_000, "STELLAR": 47_000_000,
    "XRPL": 88_000_000, "ALGORAND": 36_000_000, "HEDERA": 62_000_000,
    "VECHAIN": 19_000_000, "MULTIVERSX": 7_800_000, "WAVES": 10_000_000,
}


def _seed(chain_id: str) -> int:
    """Deterministic 32-bit seed from chain id string."""
    h = hashlib.sha256(chain_id.encode()).digest()
    return int.from_bytes(h[:4], "big")


def get_bh_stats(chain: dict, live_records: int | None = None) -> dict:
    """
    Return BH stats for a chain.

    HONEST DATA MODEL (audit remediation):

      - When `live_records` (real bh_ledger.db count for this chain) is
        available, bh_proofs is the REAL count and stats_source="ledger".
      - Otherwise the deterministic baseline is returned explicitly labeled
        stats_source="estimated" — capacity-planning figures derived from
        the chain's status/VM, NOT live measurements. Never presented as
        indexed data.
    """
    s = _seed(chain["id"])
    status = chain["status"]
    vm = chain["vm"]

    if live_records is not None:
        return {
            "bh_proofs": int(live_records),
            "faiss_vectors": int(live_records),   # every BH has a FAISS vector
            "last_block": 0,
            "last_indexed_ts": None,
            "indexer": chain.get("indexer", "trion-evm"),
            "stats_source": "ledger",
        }

    # Deterministic capacity estimate (NOT live data)
    base_proofs = _PROOF_BASE.get(status, 45_000)
    base_block = _BLOCK_BASE.get(vm, 10_000_000)

    # jitter within ±30% using seed
    jitter = (s % 1000) / 1000.0 * 0.6 - 0.3
    bh_proofs = int(base_proofs * (1 + jitter))
    last_block = int(base_block * (1 + jitter * 0.5))

    # FAISS vectors: 70-90% of proof count
    faiss_frac = 0.70 + (s % 200) / 1000.0
    faiss_vectors = int(bh_proofs * faiss_frac)

    return {
        "bh_proofs": bh_proofs,
        "faiss_vectors": faiss_vectors,
        "last_block": last_block,
        "last_indexed_ts": None,   # never fabricate freshness for estimates
        "indexer": chain.get("indexer", "trion-evm"),
        "stats_source": "estimated",
    }


def enrich(chain: dict, live_records: int | None = None) -> dict:
    """Return chain dict enriched with BH stats (real ledger counts preferred)."""
    return {**chain, **get_bh_stats(chain, live_records)}


def get_live_chain_stats() -> dict:
    """
    Query bh_ledger.db for real per-chain BH record counts.
    Returns {chain_label: count} from live SQLite data.
    Falls back to empty dict if the DB is unavailable.
    Result is cached for 60 s to avoid per-request DB hits.
    """
    import sqlite3 as _sql
    import threading as _th
    _f = get_live_chain_stats
    if not hasattr(_f, "_cache"):
        _f._cache = {}
        _f._ts    = 0.0
        _f._lock  = _th.Lock()
    now = time.time()
    with _f._lock:
        if _f._cache and (now - _f._ts) < 60:
            return dict(_f._cache)
    db_path = os.path.normpath(
        os.path.join(os.path.dirname(__file__), "..", "bh_ledger.db")
    )
    try:
        conn = _sql.connect(db_path, timeout=3.0)
        conn.execute("PRAGMA query_only=1")
        rows = conn.execute(
            "SELECT chain_label, COUNT(*) FROM bh_ledger GROUP BY chain_label"
        ).fetchall()
        conn.close()
        result = {r[0]: r[1] for r in rows}
    except Exception:
        result = {}
    with _f._lock:
        _f._cache = result
        _f._ts    = now
    return result


def get_all_chains():
    return CHAINS


def get_enriched_chains():
    """Return all chains enriched with BH stats — REAL ledger counts preferred.

    Audit remediation: chains with live bh_ledger.db records report the actual
    count with stats_source="ledger"; all others are explicitly labeled
    stats_source="estimated" (deterministic capacity figures, never presented
    as indexed state).
    """
    live_stats = get_live_chain_stats()
    enriched = []
    for c in CHAINS:
        # Resolve the bh_ledger chain_label for this catalog entry
        explicit = c.get("bh_label")
        if explicit:
            label_candidates = [explicit]
        else:
            label_candidates = [
                c["id"].upper().replace("-", "_"),
                c["name"].upper().replace(" ", "_").replace("-", "_"),
                c["id"].upper().replace("-", "_") + "_MAINNET",
                c["id"].upper().replace("-", "_") + "_DEVNET",
                # python streamer writer convention (registry-style names)
                c["name"].lower().replace(" ", "_"),
                c["id"].lower().replace("-", "_"),
            ]
        live_records = None
        # Case-insensitive: the streamer writes lowercase names, the rust
        # indexers UPPERCASE — accept either for the same chain.
        live_stats_ci = {str(k).lower(): v for k, v in live_stats.items()}
        for lbl in label_candidates:
            if lbl.lower() in live_stats_ci:
                live_records = live_stats_ci[lbl.lower()]
                break

        e = enrich(c, live_records)
        if live_records is not None:
            e["bh_records_live"] = live_records
        enriched.append(e)
    return enriched


if __name__ == "__main__":  # pragma: no cover - manual smoke check
    live = sum(1 for c in CHAINS if c["status"] == "live")
    testnet = sum(1 for c in CHAINS if c["status"] == "testnet")
    indexed = sum(1 for c in CHAINS if c["status"] == "indexed")
    print(
        f"chains={TOTAL_CHAINS} vm_families={VM_FAMILIES} "
        f"integrated={INTEGRATED_CHAINS} "
        f"(live={live} testnet={testnet} indexed={indexed})"
    )
    assert TOTAL_CHAINS == _REGISTRY.get("total_chains"), "registry total mismatch"
    assert VM_FAMILIES == _REGISTRY.get("vm_families"), "registry VM mismatch"
    assert INTEGRATED_CHAINS == _REGISTRY.get("integrated_chains"), "registry integrated mismatch"
