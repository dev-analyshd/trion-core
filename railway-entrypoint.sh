#!/usr/bin/env bash
# =============================================================================
# TRION Protocol — Railway Entrypoint
#
# CORE SERVICES (always started):
#   1. FAISS ANIMA Engine         (port 8000, internal)
#   2. BH Streamer                (background, 55 EVM chains)
#   3. Flask Oracle API           (port 5000, internal)
#   4. Next.js React Frontend     (port $PORT, exposed)
#
# OPTIONAL SERVICES (enable via env vars, default OFF):
#   TRION_ENABLE_VALIDATOR=1       — Go P2P Validator (port 6000)
#   TRION_ENABLE_INDEXERS=1        — Rust indexers (if built)
#   TRION_ENABLE_SIGNAL_PROCESSING=1 — C++ signal processing
#   TRION_ENABLE_MONITORING=1      — Prometheus/Grafana configs available
#
# All source code included in image: Rust indexers, Go validator,
# C++ signal processing, Haskell formal verification, Julia math,
# Solidity/Vyper contracts, TypeScript SDK, WebAssembly.
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

# ── 3c. Optional: Go P2P Validator Network ────────────────────────────────
if [ "${TRION_ENABLE_VALIDATOR:-0}" = "1" ] && command -v go >/dev/null 2>&1; then
    if [ -f /app/validator/go.mod ]; then
        log "Starting Go P2P Validator Network..."
        cd /app/validator
        # Build if not already built
        if [ ! -f /app/validator/trion-validator ]; then
            log "Building validator binary (first run)..."
            go build -o trion-validator ./cmd/validator/ 2>/dev/null || log "Validator build skipped (using source mode)"
        fi
        if [ -f /app/validator/trion-validator ]; then
            ./trion-validator --port "${TRION_VALIDATOR_PORT:-6000}" &
        else
            go run ./cmd/validator/ --port "${TRION_VALIDATOR_PORT:-6000}" &
        fi
        VALIDATOR_PID=$!
        log "Go Validator started (PID $VALIDATOR_PID, port ${TRION_VALIDATOR_PORT:-6000})"
    else
        log "Go Validator: source not found at /app/validator"
    fi
else
    if [ "${TRION_ENABLE_VALIDATOR:-0}" = "1" ]; then
        log "Go Validator enabled but 'go' command not found — skipping"
    fi
fi

# ── 3d. Optional: C++ Signal Processing Engine ───────────────────────────
if [ "${TRION_ENABLE_SIGNAL_PROCESSING:-0}" = "1" ] && command -v cmake >/dev/null 2>&1; then
    if [ -f /app/signal-processing/CMakeLists.txt ]; then
        log "Starting C++ Signal Processing Engine..."
        cd /app/signal-processing
        # Build if not already built
        if [ ! -d /app/signal-processing/build ]; then
            log "Building signal processing (first run)..."
            mkdir -p build && cd build
            cmake .. -DCMAKE_BUILD_TYPE=Release 2>/dev/null || log "CMake configure skipped"
            make -j$(nproc) 2>/dev/null || log "Signal processing build skipped"
            cd /app/signal-processing
        fi
        if [ -f /app/signal-processing/build/trion_signal ]; then
            ./build/trion_signal &
            SIGNAL_PID=$!
            log "C++ Signal Processing started (PID $SIGNAL_PID)"
        else
            log "Signal processing binary not built — source available at /app/signal-processing"
        fi
    fi
else
    if [ "${TRION_ENABLE_SIGNAL_PROCESSING:-0}" = "1" ]; then
        log "Signal Processing enabled but 'cmake' not found — skipping"
    fi
fi

# ── 3e. Optional: TimescaleDB Akashic Index ──────────────────────────────
if [ -n "${TIMESCALEDB_URL:-}" ]; then
    log "TimescaleDB configured — Akashic Index will persist to TimescaleDB"
    log "  Connection health check endpoint: /api/timescale/health"
else
    log "TimescaleDB not configured — Akashic Index using local storage only"
fi

# ── 3f. Optional: Prometheus Monitoring ─────────────────────────────────
if [ "${TRION_ENABLE_MONITORING:-0}" = "1" ]; then
    if [ -f /app/deploy/monitoring/prometheus.yml ]; then
        log "Monitoring enabled — config at /app/deploy/monitoring/prometheus.yml"
        log "  Prometheus port: ${TRION_PROMETHEUS_PORT:-9090}"
        log "  Grafana port: ${TRION_GRAFANA_PORT:-3001}"
        log "  (Install prometheus/grafana separately or use docker-compose for full monitoring)"
    fi
fi

# ── 4. Next.js React Frontend (exposed port) ─────────────────────────────────
log "============================================================"
log "TRION Protocol — Railway deployment starting on :${PORT}"
log "  Dashboard:  http://0.0.0.0:${PORT}/"
log "  API:        http://127.0.0.1:${PORT}/api/v1/health"
log "  Healthz:    http://127.0.0.1:${PORT}/healthz"
log "============================================================"

cd /app/frontend
exec node server.js
