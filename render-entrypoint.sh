#!/usr/bin/env bash
# =============================================================================
# TRION Protocol — Production Entrypoint  (v4.0)
#
# Boots all 11 TRION services, then runs the Oracle API in the foreground
# under tini so Render/Docker health checks can probe:
#   http://localhost:$PORT/api/v1/health
#
# Services:
#   1.  FAISS ANIMA Engine         Python  port $FAISS_PORT (default 8000)
#   2.  Rust L0 Indexers           Rust    background  (EVM×14 + SVM)
#   3.  EVM Extras Supervisor      Bash    background
#   4.  Native VM Indexers         Bash    background  (NEAR/TON/Polkadot/StarkNet)
#   5.  Extended VM Indexers       Bash    background  (UTXO/Cosmos/Move/SUI/TRON/PI)
#   6.  TRION EVM Relayer          Node    background
#   7.  Native VM Relayer          Node    background
#   8.  Extended Chain Relayer     Node    background
#   9.  0G Sync Daemon             Python  background  (hourly FAISS → 0G Storage)
#  10.  0G DA Streamer             Python  background  (60s behavioral blobs → 0G DA)
#  11.  Oracle API + Frontend      gunicorn foreground  port $PORT
#
# Each background service is restarted automatically with exponential backoff.
# Only the foreground Oracle API propagates its exit code to Docker/Render.
# Toggle any service with TRION_ENABLE_<NAME>=0.
# =============================================================================
set -u

export PORT="${PORT:-10000}"
export FAISS_PORT="${FAISS_PORT:-8000}"
export FAISS_SERVICE_URL="${FAISS_SERVICE_URL:-http://127.0.0.1:${FAISS_PORT}}"
export FAISS_URL="${FAISS_URL:-http://127.0.0.1:${FAISS_PORT}}"
export ORACLE_API_URL="${ORACLE_API_URL:-http://127.0.0.1:${PORT}}"
export RUST_BIN_DIR="${RUST_BIN_DIR:-/app/bin}"

log() { echo "[entrypoint $(date +%H:%M:%S)] $*"; }

# ── Persistent data directory (Render disk mounted at /data) ─────────────────
# All FAISS index, centroids, and SQLite databases live here so they survive
# container restarts and redeployments. On first boot (empty /data), any
# pre-seeded files baked into the image are copied across.
DATA_DIR="${DATA_DIR:-/data}"
mkdir -p "${DATA_DIR}"

export FAISS_INDEX_PATH="${FAISS_INDEX_PATH:-${DATA_DIR}/akashic_faiss.index}"
export FAISS_CENTROIDS_PATH="${FAISS_CENTROIDS_PATH:-${DATA_DIR}/trion_archetype_centroids.npy}"
export FAISS_STATE_DB="${FAISS_STATE_DB:-${DATA_DIR}/akashic_state.db}"
export BH_LEDGER_DB="${BH_LEDGER_DB:-${DATA_DIR}/bh_ledger.db}"

# Seed /data from baked-in image files on first boot (only if target absent)
for _seed_src in \
    "/app/akashic_faiss.index:${FAISS_INDEX_PATH}" \
    "/app/trion_archetype_centroids.npy:${FAISS_CENTROIDS_PATH}" \
    "/app/akashic_state.db:${FAISS_STATE_DB}" \
    "/app/bh_ledger.db:${BH_LEDGER_DB}" \
    "/app/akashic/akashic_faiss.index:${FAISS_INDEX_PATH}" \
    "/app/akashic/akashic_state.db:${FAISS_STATE_DB}"; do
    _src="${_seed_src%%:*}"
    _dst="${_seed_src##*:}"
    if [[ -f "$_src" && ! -f "$_dst" ]]; then
        cp "$_src" "$_dst"
        log "seeded ${_dst} from ${_src} ($(du -sh "$_dst" | cut -f1))"
    fi
done

# ── Restart wrapper (exponential backoff 5s → 120s) ──────────────────────────
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

# ── 1. FAISS ANIMA Engine (Python/FastAPI, port 8000) ─────────────────────────
if [[ "${TRION_ENABLE_FAISS:-1}" == "1" ]]; then
    log "FAISS ANIMA on :${FAISS_PORT}"
    (
        cd /app/akashic
        OMP_NUM_THREADS=1 OPENBLAS_NUM_THREADS=1 MKL_NUM_THREADS=1 NUMEXPR_NUM_THREADS=1 \
        PORT="${FAISS_PORT}" FAISS_PORT="${FAISS_PORT}" \
        python3 faiss_service.py
    ) 2>&1 | sed -u "s/^/[faiss] /" &

    log "waiting for FAISS to become ready (up to 90s)..."
    for i in $(seq 1 90); do
        curl -fs "http://127.0.0.1:${FAISS_PORT}/health" >/dev/null 2>&1 && \
            { log "FAISS ready after ${i}s"; break; }
        sleep 1
    done
fi

# ── 2. Rust L0 Indexers (EVM×14 + SVM) ───────────────────────────────────────
if [[ "${TRION_ENABLE_RUST:-1}" == "1" ]]; then
    if [[ -x "${RUST_BIN_DIR}/trion-evm" ]]; then
        spawn "rust-evm" env FAISS_SERVICE_URL="${FAISS_SERVICE_URL}" \
            "${RUST_BIN_DIR}/trion-evm"
        spawn "rust-svm" env FAISS_SERVICE_URL="${FAISS_SERVICE_URL}" \
            "${RUST_BIN_DIR}/trion-svm"
        log "Rust L0 indexers started (EVM + SVM)"
    else
        log "WARN: Rust binaries not found at ${RUST_BIN_DIR} — skipping L0 indexers"
    fi
fi

# ── 3. EVM Extras Supervisor (BNB/Base/HashKey/Mantle/Linea/Scroll) ───────────
if [[ "${TRION_ENABLE_EXTRAS:-1}" == "1" ]]; then
    spawn "evm-extras" bash /app/supervisors/evm_extras_indexers.sh
fi

# ── 4. Native VM Indexers (NEAR/TON/Polkadot/StarkNet) ───────────────────────
if [[ "${TRION_ENABLE_NATIVE:-1}" == "1" ]]; then
    spawn "native-vm" bash /app/supervisors/native_vm_indexers.sh
fi

# ── 5. Extended VM Indexers (UTXO×4/Cosmos×6/Move×2/SUI/TRON/PI) ─────────────
if [[ "${TRION_ENABLE_EXTENDED:-1}" == "1" ]]; then
    spawn "ext-vm" bash /app/supervisors/extended_vm_indexers.sh
fi

# ── 6. TRION EVM Relayer (C(t) signals on EVM + 0G ExecutionGate) ─────────────
if [[ "${TRION_ENABLE_RELAYER:-1}" == "1" ]]; then
    spawn "evm-relayer" env \
        ORACLE_API_URL="${ORACLE_API_URL}" \
        POLL_INTERVAL_MS="${POLL_INTERVAL_MS:-60000}" \
        ZG_EXECUTION_GATE_ADDR="${ZG_EXECUTION_GATE_ADDR:-0xDB5910Dc6CfD219D00F64be1F23DA0289901356d}" \
        ZG_POLL_INTERVAL_MS="${ZG_POLL_INTERVAL_MS:-120000}" \
        bash /app/supervisors/trion_and_zg_relayer.sh
fi

# ── 7. Native VM Relayer (NEAR/TON/Polkadot/StarkNet signed txs) ──────────────
if [[ "${TRION_ENABLE_NATIVE_RELAYER:-1}" == "1" ]]; then
    spawn "native-relayer" env \
        ORACLE_API_URL="${ORACLE_API_URL}" \
        node /app/native-relayer/native_relayer.js
fi

# ── 8. Extended Chain Relayer (15 non-EVM chains every 90s) ──────────────────
if [[ "${TRION_ENABLE_EXT_RELAYER:-1}" == "1" ]]; then
    spawn "ext-relayer" env \
        ORACLE_API_URL="${ORACLE_API_URL}" \
        EXTENDED_POLL_INTERVAL_MS="${EXTENDED_POLL_INTERVAL_MS:-90000}" \
        node /app/relayer/extended_chain_relayer.js
fi

# ── 9. 0G Sync Daemon (hourly FAISS delta → 0G Storage) ──────────────────────
if [[ "${TRION_ENABLE_ZG_SYNC:-1}" == "1" ]]; then
    spawn "zg-sync" python3 /app/zg_sync_daemon.py
fi

# ── 10. 0G DA Streamer (60s behavioral blobs → 0G DA) ────────────────────────
if [[ "${TRION_ENABLE_ZG_DA:-1}" == "1" ]]; then
    spawn "zg-da" python3 /app/zg_da_streamer.py
fi

# ── 11. Oracle API + Frontend (gunicorn, foreground PID 1) ───────────────────
log "Oracle API + Frontend starting on :${PORT} (foreground)"
log "Dashboard: http://0.0.0.0:${PORT}/"
log "Health:    http://0.0.0.0:${PORT}/api/v1/health"
log "0G Judge:  http://0.0.0.0:${PORT}/api/v1/zg/integration"

exec gunicorn \
    --bind "0.0.0.0:${PORT}" \
    --workers "${GUNICORN_WORKERS:-2}" \
    --threads "${GUNICORN_THREADS:-4}" \
    --timeout "${GUNICORN_TIMEOUT:-120}" \
    --keep-alive 5 \
    --access-logfile - \
    --error-logfile - \
    --log-level info \
    "oracle_api.app:app"
