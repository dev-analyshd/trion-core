#!/usr/bin/env python3
"""TRION Protocol — Railway/Container Deployment Preflight

Run BEFORE the application entrypoint. Performs fast (<3s) sanity checks on:

  1. Required environment variables (PORT, FAISS_PORT, FLASK_PORT)
  2. Writable data directories (BH_LEDGER_DB, anima-service/data)
  3. SQLite schema sanity (bh_ledger has `valid` column)
  4. Outbound RPC reachability (sample of chain RPCs + 0G)
  5. Optional services — only validate env when toggle is on

Exit codes:
   0 = pass, start the app
  11 = env violation (fail-closed)
  12 = storage / DB failure
  13 = critical RPC unreachable AND TRION_REQUIRE_RPC=1
   0 with warnings otherwise (best-effort, do not block Railway)

Why best-effort on RPC: public RPC endpoints rate-limit, geo-block, or
flap; failing the container boot on a transient RPC error would create a
crash loop. The streamer has its own per-chain retry. The preflight only
hard-fails when the operator explicitly sets TRION_REQUIRE_RPC=1 (used
during pre-mainnet validation runs).
"""
from __future__ import annotations
import os, sys, sqlite3, socket, time, json, urllib.request, urllib.error
from pathlib import Path

REQUIRED_ENV = ("PORT",)              # Railway injects PORT — hard requirement
OPTIONAL_ENV_DEFAULTS = {
    "FAISS_PORT":         "8000",
    "FLASK_PORT":         "5000",
    "FAISS_SERVICE_URL":  "http://127.0.0.1:8000",
    "ORACLE_API_URL":     "http://127.0.0.1:5000",
    "FLASK_URL":          "http://127.0.0.1:5000",
    "BH_LEDGER_DB":       "/app/bh_ledger.db",
    "PYTHONUNBUFFERED":   "1",
}

CRITICAL_RPC_PROBES = [
    # Critical — 0G mainnet hosts the TRIONExecutionGate contract.
    ("0G mainnet",    "https://evmrpc.0g.ai",     "eth_blockNumber"),
]

# Informational probes — failures here are warnings, not fatal. Public EVM
# RPCs (LlamaRPC, Ankr, etc.) geo-block and rate-limit aggressively; the
# streamer has its own per-chain retry and failover list of 3-5 RPCs each.
INFO_RPC_PROBES = [
    ("Ethereum",      "https://eth.llamarpc.com", "eth_blockNumber"),
    ("Arbitrum",      "https://arb1.llamarpc.com","eth_blockNumber"),
    ("Polygon",       "https://polygon.llamarpc.com","eth_blockNumber"),
]

WARMUP_TIMEOUT = 3.0   # seconds per probe — must be fast


def _log(msg: str, *, level: str = "INFO") -> None:
    print(f"[preflight {level}] {msg}", flush=True)


def check_env() -> int:
    """Verify required env is present; apply optional defaults."""
    missing = []
    for name in REQUIRED_ENV:
        if not os.environ.get(name):
            missing.append(name)
    if missing:
        _log(f"Missing required env: {', '.join(missing)}", level="ERROR")
        _log("Railway auto-injects PORT at runtime — if running locally, "
             "export PORT=10000 before starting.", level="ERROR")
        return 11
    for k, v in OPTIONAL_ENV_DEFAULTS.items():
        os.environ.setdefault(k, v)
    _log(f"PORT={os.environ['PORT']}  "
         f"FAISS_PORT={os.environ['FAISS_PORT']}  "
         f"FLASK_PORT={os.environ['FLASK_PORT']}")
    return 0


def check_storage() -> int:
    """Ensure BH ledger DB path is writable and schema is up to date."""
    db_path = Path(os.environ["BH_LEDGER_DB"])
    try:
        db_path.parent.mkdir(parents=True, exist_ok=True)
        # touch the file so we know we own it
        if not db_path.exists():
            db_path.touch()
        # write+read sanity
        with open(db_path, "ab") as f:
            pass
    except OSError as e:
        _log(f"Cannot write BH ledger at {db_path}: {e}", level="ERROR")
        return 12

    # schema sanity
    try:
        conn = sqlite3.connect(str(db_path))
        cols = {row[1] for row in conn.execute("PRAGMA table_info(bh_ledger)").fetchall()}
        if cols and "valid" not in cols:
            _log("bh_ledger missing `valid` column — running migration", level="WARN")
            conn.execute("ALTER TABLE bh_ledger ADD COLUMN valid INTEGER DEFAULT 1")
            conn.commit()
            _log("Migration complete", level="INFO")
        conn.close()
    except sqlite3.Error as e:
        _log(f"bh_ledger schema check failed: {e}", level="WARN")
        # Non-fatal — the streamer's _init_db will create the table on first run.

    # anima-service/data directory
    anima_data = Path("/app/anima-service/data")
    try:
        anima_data.mkdir(parents=True, exist_ok=True)
    except OSError:
        # Non-fatal; the entrypoint will retry. We just warn.
        _log(f"Could not create {anima_data} (non-fatal)", level="WARN")

    _log(f"Storage OK: bh_ledger={db_path}")
    return 0


def check_rpcs() -> int:
    """Best-effort RPC probes — soft warn unless TRION_REQUIRE_RPC=1.

    Critical probes (0G mainnet) → fatal if unreachable AND TRION_REQUIRE_RPC=1.
    Informational probes (other EVM chains) → warnings only, never fatal.
    Public EVM RPCs geo-block and rate-limit; the streamer has its own
    per-chain failover list and should not be gated by a single RPC probe.
    """
    if os.environ.get("TRION_REQUIRE_RPC", "0") != "1":
        _log("RPC probe skipped (set TRION_REQUIRE_RPC=1 to enforce)")
        return 0

    # Critical RPC probes — 0G must be reachable for the oracle to read
    # on-chain state from the TRIONExecutionGate contract.
    crit_failures = []
    for label, url, method in CRITICAL_RPC_PROBES:
        try:
            req = urllib.request.Request(
                url,
                data=json.dumps({"jsonrpc": "2.0", "id": 1, "method": method, "params": []}).encode(),
                headers={"Content-Type": "application/json"},
                method="POST",
            )
            with urllib.request.urlopen(req, timeout=WARMUP_TIMEOUT) as r:
                payload = json.loads(r.read())
                if "result" in payload:
                    _log(f"  [crit] {label:14s} OK  ({payload['result']})")
                    continue
                crit_failures.append(f"{label}: no result")
        except (urllib.error.URLError, urllib.error.HTTPError, socket.timeout, OSError) as e:
            crit_failures.append(f"{label}: {type(e).__name__}")

    # Informational probes — failures here are warnings only
    info_failures = []
    for label, url, method in INFO_RPC_PROBES:
        try:
            req = urllib.request.Request(
                url,
                data=json.dumps({"jsonrpc": "2.0", "id": 1, "method": method, "params": []}).encode(),
                headers={"Content-Type": "application/json"},
                method="POST",
            )
            with urllib.request.urlopen(req, timeout=WARMUP_TIMEOUT) as r:
                payload = json.loads(r.read())
                if "result" in payload:
                    _log(f"  [info] {label:14s} OK  ({payload['result']})")
                    continue
                info_failures.append(f"{label}: no result")
        except (urllib.error.URLError, urllib.error.HTTPError, socket.timeout, OSError) as e:
            info_failures.append(f"{label}: {type(e).__name__}")

    if info_failures:
        _log(f"Info RPC unreachable (non-fatal, streamer will failover): "
             f"{', '.join(info_failures)}", level="WARN")

    if crit_failures:
        _log(f"Critical RPC probes failed: {', '.join(crit_failures)}", level="ERROR")
        return 13
    return 0


def main() -> int:
    _log("TRION preflight starting")
    t0 = time.time()
    for fn in (check_env, check_storage, check_rpcs):
        rc = fn()
        if rc:
            _log(f"Preflight FAILED with exit={rc} after {time.time()-t0:.1f}s",
                 level="ERROR")
            return rc
    _log(f"Preflight OK ({time.time()-t0:.1f}s)")
    return 0


if __name__ == "__main__":
    sys.exit(main())
