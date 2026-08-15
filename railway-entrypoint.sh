#!/usr/bin/env bash
# =============================================================================
# TRION Protocol — Railway Entrypoint
#
# Starts 4 services in a single container:
#   1. FAISS ANIMA Engine         (port 8000, internal)
#   2. BH Streamer                (background, 55 EVM chains)
#   3. Flask Oracle API           (port 5000, internal)
#   4. Next.js React Frontend     (port $PORT, exposed)
#
# Next.js proxies /api/* to Flask — single exposed port.
# Railway auto-detects the PORT env var.
# =============================================================================
set -u

export PORT="${PORT:-10000}"
export HOSTNAME="0.0.0.0"
export FAISS_PORT="${FAISS_PORT:-8000}"
export FLASK_PORT="${FLASK_PORT:-5000}"
export FAISS_SERVICE_URL="${FAISS_SERVICE_URL:-http://127.0.0.1:${FAISS_PORT}}"
export FAISS_URL="${FAISS_URL:-http://127.0.0.1:${FAISS_PORT}}"
export ORACLE_API_URL="${ORACLE_API_URL:-http://127.0.0.1:${FLASK_PORT}}"
export FLASK_URL="${FLASK_URL:-http://127.0.0.1:${FLASK_PORT}}"
export PYTHONUNBUFFERED=1
export PYTHONDONTWRITEBYTECODE=1

log() { echo "[railway $(date +%H:%M:%S)] $*"; }

# ── 1. FAISS ANIMA Engine ────────────────────────────────────────────────────
log "Starting FAISS ANIMA Engine on :${FAISS_PORT}..."
cd /app/anima-service
OMP_NUM_THREADS=1 OPENBLAS_NUM_THREADS=1 MKL_NUM_THREADS=1 NUMEXPR_NUM_THREADS=1 \
PORT="${FAISS_PORT}" FAISS_PORT="${FAISS_PORT}" \
python3 -m uvicorn faiss_service:app --host 0.0.0.0 --port "${FAISS_PORT}" --workers 1 &
FAISS_PID=$!

# Wait for FAISS to be ready
for i in $(seq 1 30); do
    if curl -fs "http://127.0.0.1:${FAISS_PORT}/healthz" >/dev/null 2>&1; then
        log "FAISS ready after ${i}s"
        break
    fi
    sleep 1
done

# ── 2. BH Streamer (real-time behavioral hash ingestion) ─────────────────────
log "Starting BH Streamer (55 EVM chains)..."
cd /app
python3 /app/scripts/run_bh_streamer.py &
BH_PID=$!
log "BH Streamer PID: $BH_PID"

# ── 3. Flask Oracle API ──────────────────────────────────────────────────────
log "Starting Flask Oracle API on :${FLASK_PORT}..."
cd /app
gunicorn \
    --bind "0.0.0.0:${FLASK_PORT}" \
    --workers "${GUNICORN_WORKERS:-2}" \
    --threads "${GUNICORN_THREADS:-4}" \
    --timeout "${GUNICORN_TIMEOUT:-120}" \
    --keep-alive 5 \
    --log-level info \
    "api.app:app" &
FLASK_PID=$!

# Wait for Flask to be ready
for i in $(seq 1 30); do
    if curl -fs "http://127.0.0.1:${FLASK_PORT}/api/v1/health" >/dev/null 2>&1; then
        log "Flask ready after ${i}s"
        break
    fi
    sleep 1
done

# ── 3b. Auto-backfill BHs → FAISS vectors (background) ────────────────────
log "Starting BH → FAISS auto-backfill in background..."
(
    # Wait for Flask to be fully ready
    sleep 15
    # Give BH streamer time to accumulate some data
    sleep 45
    log "Running BH → FAISS backfill..."
    if [ -f /app/anima-service/backfill_entity_records.py ]; then
        cd /app/anima-service
        python3 backfill_entity_records.py --faiss-url "http://127.0.0.1:${FAISS_PORT}" --batch-size 500 2>&1 | tail -5 &
        BACKFILL_PID=$!
        log "Backfill started (PID $BACKFILL_PID)"
    else
        log "Backfill script not found — vectors will populate via scheduler (30min cycles)"
    fi
) &

# ── 4. Next.js React Frontend (exposed port) ─────────────────────────────────
log "============================================================"
log "TRION Protocol — Railway deployment starting on :${PORT}"
log "  Dashboard:  http://0.0.0.0:${PORT}/"
log "  API:        http://127.0.0.1:${PORT}/api/v1/health"
log "  Healthz:    http://127.0.0.1:${PORT}/healthz"
log "============================================================"

cd /app/frontend
exec node server.js
