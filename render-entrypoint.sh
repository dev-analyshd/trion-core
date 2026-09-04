#!/usr/bin/env bash
# =============================================================================
# TRION Protocol — Production Entrypoint  (v5.0 — React + Flask)
#
# Boots all TRION services, then runs Next.js React frontend in the foreground.
# Flask Oracle API runs on internal port 5000.
# Next.js proxies /api/* to Flask internally.
#
# Services:
#   1. FAISS ANIMA Engine         Python  port 8000 (internal)
#   2. Rust L0 Indexers           Rust    background
#   3. EVM + Non-EVM Indexers     Bash    background
#   4. Unified Relayer (2)        Node    background
#   5. 0G Sync + DA Daemon        Python  background
#   6. Flask Oracle API           gunicorn port 5000 (internal)
#   7. Next.js React Frontend     Node    port $PORT (exposed)
# =============================================================================
set -u

export PORT="${PORT:-10000}"
export FAISS_PORT="${FAISS_PORT:-8000}"
export FLASK_PORT="${FLASK_PORT:-5000}"
export FAISS_SERVICE_URL="${FAISS_SERVICE_URL:-http://127.0.0.1:${FAISS_PORT}}"
export FAISS_URL="${FAISS_URL:-http://127.0.0.1:${FAISS_PORT}}"
export ORACLE_API_URL="${ORACLE_API_URL:-http://127.0.0.1:${FLASK_PORT}}"
export RUST_BIN_DIR="${RUST_BIN_DIR:-/app/bin}"
export FLASK_URL="http://127.0.0.1:${FLASK_PORT}"

log() { echo "[entrypoint $(date +%H:%M:%S)] $*"; }

# ── Persistent data directory ─────────────────────────────────────────────────
DATA_DIR="${DATA_DIR:-/data}"
mkdir -p "${DATA_DIR}"

export FAISS_INDEX_PATH="${FAISS_INDEX_PATH:-${DATA_DIR}/akashic_faiss.index}"
export FAISS_CENTROIDS_PATH="${FAISS_CENTROIDS_PATH:-${DATA_DIR}/trion_archetype_centroids.npy}"
export FAISS_STATE_DB="${FAISS_STATE_DB:-${DATA_DIR}/akashic_state.db}"
export BH_LEDGER_DB="${BH_LEDGER_DB:-${DATA_DIR}/bh_ledger.db}"

# Seed /data from baked-in image files
for _seed_src in \
    "/app/anima-service/akashic_faiss.index:${FAISS_INDEX_PATH}" \
    "/app/anima-service/trion_archetype_centroids.npy:${FAISS_CENTROIDS_PATH}" \
    "/app/anima-service/akashic_state.db:${FAISS_STATE_DB}" \
    "/app/anima-service/bh_ledger.db:${BH_LEDGER_DB}" \
    "/app/bh_ledger.db:${BH_LEDGER_DB}"; do
    _src="${_seed_src%%:*}"; _dst="${_seed_src##*:}"
    if [[ -f "$_src" && ! -f "$_dst" ]]; then
        cp "$_src" "$_dst"; log "seeded ${_dst} from ${_src}"
    fi
done

# Ensure /app/bh_ledger.db exists
if [[ ! -f "/app/bh_ledger.db" ]]; then
    if [[ -f "${BH_LEDGER_DB}" ]]; then
        cp "${BH_LEDGER_DB}" /app/bh_ledger.db
    else
        # Use the canonical init script — the inline DDL that used to live here
        # created a PRE-migration schema (no `valid` column, 3/5 indexes), which
        # no streamer step ever migrated on this platform, so backfills writing
        # `valid` crashed on exactly the bug init_bh_ledger.py documents.
        python3 /app/scripts/init_bh_ledger.py \
            2>/dev/null || log "WARN: could not create bh_ledger.db"
    fi
fi
# Always run the migration pass (idempotent): a /data ledger copied in from an
# older deployment may still be pre-`valid`.
BH_LEDGER_DB="${BH_LEDGER_DB:-/app/bh_ledger.db}" \
    python3 /app/scripts/init_bh_ledger.py 2>/dev/null \
    || log "WARN: bh_ledger migration pass failed (non-fatal)"

# ── TimescaleDB connection ────────────────────────────────────────────────────
if [[ -n "${DATABASE_URL}" ]]; then
    log "TimescaleDB: DATABASE_URL is set — PostgreSQL connection enabled"
    export TIMESCALEDB_URL="${TIMESCALEDB_URL:-${DATABASE_URL}}"
else
    log "TimescaleDB: DATABASE_URL not set — using SQLite fallback (bh_ledger.db)"
fi

# ── Restart wrapper ───────────────────────────────────────────────────────────
spawn() {
    local label="$1"; shift
    (
        local backoff=5
        while true; do
            log "starting $label"
            "$@" 2>&1 | sed -u "s/^/[$label] /"
            local code=$?
            log "$label exited (code=$code), restart in ${backoff}s"
            sleep "$backoff"
            backoff=$(( backoff < 120 ? backoff * 2 : 120 ))
        done
    ) &
}

# ── 1. FAISS ANIMA Engine ─────────────────────────────────────────────────────
if [[ "${TRION_ENABLE_FAISS:-1}" == "1" ]]; then
    log "FAISS ANIMA on :${FAISS_PORT}"
    (
        cd /app/anima-service
        OMP_NUM_THREADS=1 OPENBLAS_NUM_THREADS=1 MKL_NUM_THREADS=1 NUMEXPR_NUM_THREADS=1 \
        PORT="${FAISS_PORT}" FAISS_PORT="${FAISS_PORT}" \
        python3 faiss_service.py
    ) 2>&1 | sed -u "s/^/[faiss] /" &

    log "waiting for FAISS (up to 90s)..."
    for i in $(seq 1 90); do
        curl -fs "http://127.0.0.1:${FAISS_PORT}/health" >/dev/null 2>&1 && \
            { log "FAISS ready after ${i}s"; break; }
        sleep 1
    done
fi

# ── 2. Rust L0 Indexers ───────────────────────────────────────────────────────
if [[ "${TRION_ENABLE_RUST:-1}" == "1" ]]; then
    if [[ -x "${RUST_BIN_DIR}/trion-evm" ]]; then
        spawn "rust-evm" env FAISS_SERVICE_URL="${FAISS_SERVICE_URL}" \
            "${RUST_BIN_DIR}/trion-evm"
        spawn "rust-botchain" env FAISS_SERVICE_URL="${FAISS_SERVICE_URL}" \
            "${RUST_BIN_DIR}/trion-botchain"
        log "Rust L0 indexers started (EVM + BOT Chain)"
    else
        log "WARN: Rust binaries not found — skipping L0 indexers"
    fi
fi

# ── 3. Extended + Native VM Indexers ──────────────────────────────────────────
if [[ "${TRION_ENABLE_EXTRAS:-1}" == "1" ]]; then
    spawn "ext-vm" bash /app/supervisors/extended_vm_indexers.sh
fi
if [[ "${TRION_ENABLE_NATIVE:-1}" == "1" ]]; then
    spawn "native-vm" bash /app/supervisors/native_vm_indexers.sh
fi

# ── 4. Unified Relayer (EVM + Non-EVM) ────────────────────────────────────────
if [[ "${TRION_ENABLE_RELAYER:-1}" == "1" ]]; then
    spawn "relayer" env \
        ORACLE_API_URL="${ORACLE_API_URL}" \
        FAISS_URL="${FAISS_URL}" \
        POLL_INTERVAL_MS="${POLL_INTERVAL_MS:-60000}" \
        EXTENDED_POLL_INTERVAL_MS="${EXTENDED_POLL_INTERVAL_MS:-90000}" \
        NATIVE_CYCLE_SLEEP_MS="${NATIVE_CYCLE_SLEEP_MS:-600000}" \
        ZG_EXECUTION_GATE_ADDR="${ZG_EXECUTION_GATE_ADDR:-0xA85B49C73B5710d9ddB1CB5a94c52D0F33c4199b}" \
        ZG_CHAIN_ID="${ZG_CHAIN_ID:-16661}" \
        ZERO_G_RPC="${ZERO_G_RPC:-https://evmrpc.0g.ai}" \
        bash /app/supervisors/trion_and_zg_relayer.sh
fi

# ── 5. 0G Sync + DA ───────────────────────────────────────────────────────────
if [[ "${TRION_ENABLE_ZG_SYNC:-1}" == "1" ]]; then
    spawn "zg-sync" python3 /app/zg/zg_sync_daemon.py
fi
if [[ "${TRION_ENABLE_ZG_DA:-1}" == "1" ]]; then
    spawn "zg-da" python3 /app/zg/zg_da_streamer.py
fi

# ── 6. Flask Oracle API (internal port 5000) ──────────────────────────────────
# BH Streamer — same contract as the railway entrypoint: standalone process,
# one per container (the app's in-process gate TRION_STREAMER_INPROCESS stays
# off; render used to run NO streamer at all, so its ledger never grew).
if [[ "${TRION_ENABLE_STREAMER:-1}" = "1" ]]; then
    log "Starting BH Streamer (supervised)..."
    BH_LEDGER_DB="${BH_LEDGER_DB:-/app/bh_ledger.db}" \
        spawn "bh-streamer" python3 /app/scripts/run_bh_streamer.py
else
    log "BH Streamer disabled (TRION_ENABLE_STREAMER=0)"
fi

log "Flask Oracle API starting on :${FLASK_PORT} (internal)"
(
    cd /app
    gunicorn \
        --bind "0.0.0.0:${FLASK_PORT}" \
        --workers "${GUNICORN_WORKERS:-2}" \
        --threads "${GUNICORN_THREADS:-4}" \
        --timeout "${GUNICORN_TIMEOUT:-120}" \
        --keep-alive 5 \
        --access-logfile - \
        --error-logfile - \
        --log-level info \
        "api.app:app"
) 2>&1 | sed -u "s/^/[flask] /" &

# Wait for Flask to be ready
log "waiting for Flask (up to 30s)..."
for i in $(seq 1 30); do
    curl -fs "http://127.0.0.1:${FLASK_PORT}/api/v1/health" >/dev/null 2>&1 && \
        { log "Flask ready after ${i}s"; break; }
    sleep 1
done

# ── 7. Next.js React Frontend (exposed port $PORT) ────────────────────────────
log "═══════════════════════════════════════════════════════════════"
log "TRION Protocol — React Frontend starting on :${PORT}"
log "Dashboard:  http://0.0.0.0:${PORT}/"
log "API:        http://0.0.0.0:${PORT}/api/v1/health (proxied to Flask:${FLASK_PORT})"
log "═══════════════════════════════════════════════════════════════"

# Set FLASK_URL so Next.js rewrites() can proxy to Flask
export FLASK_URL="http://127.0.0.1:${FLASK_PORT}"
# Next.js standalone server reads HOSTNAME and PORT env vars
export HOSTNAME="0.0.0.0"
export PORT="${PORT:-10000}"

# Check if Next.js standalone build exists (preferred — uses server.js)
if [[ -f "/app/frontend/server.js" ]]; then
    log "Starting Next.js standalone server (server.js)"
    cd /app/frontend
    exec node server.js
elif [[ -d "/app/frontend/.next" ]] && [[ -f "/app/frontend/package.json" ]]; then
    log "Starting Next.js via 'npx next start' (non-standalone)"
    cd /app/frontend
    exec npx next start -p "${PORT}" -H 0.0.0.0
else
    log "WARN: Next.js build not found — falling back to Flask-only mode"
    log "Serving Flask directly on :${PORT}"
    cd /app
    exec gunicorn \
        --bind "0.0.0.0:${PORT}" \
        --workers "${GUNICORN_WORKERS:-2}" \
        --threads "${GUNICORN_THREADS:-4}" \
        --timeout "${GUNICORN_TIMEOUT:-120}" \
        "api.app:app"
fi
