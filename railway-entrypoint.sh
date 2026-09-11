#!/usr/bin/env bash
# =============================================================================
# TRION Protocol — Railway / Container Entrypoint v3
#
# STARTUP ORDER:
#   0.  Preflight (env / storage sanity)
#   1.  BH ledger DB init
#   2.  FAISS ANIMA Engine (port $FAISS_PORT)
#   3.  Unified Server: serve.py (Flask + SocketIO on $PORT — public)
#   4.  BH Streamer (background)
#   5.  Optional: Go validator mesh, C++ signal processing
#
# serve.py IS the unified server — it serves Flask API + WebSocket + static
# frontend on $PORT. No separate gunicorn or Next.js needed.
# =============================================================================
set -u

export PORT="${PORT:-10000}"
export HOSTNAME="0.0.0.0"
export FAISS_PORT="${FAISS_PORT:-8000}"
export FLASK_PORT="${FLASK_PORT:-5000}"
export FAISS_SERVICE_URL="${FAISS_SERVICE_URL:-http://127.0.0.1:${FAISS_PORT}}"
export FAISS_URL="${FAISS_URL:-http://127.0.0.1:${FAISS_PORT}}"
export ORACLE_API_URL="${ORACLE_API_URL:-http://127.0.0.1:${PORT}}"
export FLASK_URL="${FLASK_URL:-http://127.0.0.1:${PORT}}"
export BH_LEDGER_DB="${BH_LEDGER_DB:-/app/bh_ledger.db}"
export PYTHONUNBUFFERED=1
export PYTHONDONTWRITEBYTECODE=1

log()  { echo "[entrypoint $(date +%H:%M:%S)] $*"; }
warn() { echo "[entrypoint $(date +%H:%M:%S)] WARN: $*" >&2; }
die()  { echo "[entrypoint $(date +%H:%M:%S)] FATAL: $*" >&2; exit 1; }

# ── 0. Preflight ───────────────────────────────────────────────────────────
log "Running preflight checks..."
python3 /app/scripts/deploy_preflight.py 2>/dev/null || warn "Preflight warnings (non-fatal)"

# ── 1. BH ledger init ──────────────────────────────────────────────────────
log "Initializing BH ledger at ${BH_LEDGER_DB}..."
python3 /app/scripts/init_bh_ledger.py 2>&1 | head -3 || warn "BH init non-fatal"

# ── 2. FAISS ANIMA Engine ──────────────────────────────────────────────────
log "Starting FAISS ANIMA Engine on :${FAISS_PORT}..."
cd /app/anima-service
OMP_NUM_THREADS=1 OPENBLAS_NUM_THREADS=1 MKL_NUM_THREADS=1 NUMEXPR_NUM_THREADS=1 \
PORT="${FAISS_PORT}" FAISS_PORT="${FAISS_PORT}" \
python3 -m uvicorn faiss_service:app --host 0.0.0.0 --port "${FAISS_PORT}" --workers 1 &
FAISS_PID=$!

# Wait for FAISS
FAISS_READY=false
for i in $(seq 1 60); do
    if curl -fs "http://127.0.0.1:${FAISS_PORT}/readyz" >/dev/null 2>&1; then
        log "FAISS ready after ${i}s"
        FAISS_READY=true
        break
    fi
    sleep 1
done
if [ "${FAISS_READY}" != "true" ]; then
    warn "FAISS /readyz not green after 60s — continuing (cold start)"
fi
cd /app

# ── 3. Unified Server (serve.py — Flask + SocketIO on $PORT) ──────────────
# serve.py serves:
#   - Flask API (all /api/v1/* routes)
#   - WebSocket push (/feed namespace)
#   - Static frontend (HTML/CSS/JS from api/static/)
#   - Health endpoints (/healthz, /readyz)
# It reads PORT from env and serves on 0.0.0.0:$PORT
log "Starting unified server (serve.py) on :${PORT}..."
cd /app
PORT="${PORT}" python3 serve.py &
SERVE_PID=$!
log "serve.py started (PID $SERVE_PID)"

# Wait for serve.py to be ready
SERVE_READY=false
for i in $(seq 1 60); do
    if curl -fs "http://127.0.0.1:${PORT}/readyz" >/dev/null 2>&1; then
        log "Server ready after ${i}s"
        SERVE_READY=true
        break
    fi
    # Also check /healthz (less strict — just process alive)
    if curl -fs "http://127.0.0.1:${PORT}/healthz" >/dev/null 2>&1; then
        log "Server alive after ${i}s (readyz may be pending FAISS)"
        SERVE_READY=true
        break
    fi
    sleep 1
done
if [ "${SERVE_READY}" != "true" ]; then
    warn "Server not ready after 60s — continuing (cold start)"
fi

# ── 4. BH Streamer (real-time behavioral hash ingestion) ──────────────────
BH_PID=""
if [ "${TRION_ENABLE_STREAMER:-1}" = "1" ]; then
    log "Starting BH Streamer..."
    python3 /app/scripts/run_bh_streamer.py &
    BH_PID=$!
    log "BH Streamer PID: $BH_PID"
else
    log "BH Streamer disabled"
fi

# ── 4b. Auto-backfill (delayed) ───────────────────────────────────────────
(
    sleep 60
    log "Running BH → FAISS backfill..."
    if [ -f /app/anima-service/backfill_entity_records.py ]; then
        cd /app/anima-service
        python3 backfill_entity_records.py \
            --faiss-url "http://127.0.0.1:${FAISS_PORT}" \
            --bh-db "${BH_LEDGER_DB}" \
            --batch-size 500 2>&1 | tail -5 &
        log "Backfill started (PID $!)"
    fi
) &

# ── 5. Optional: Go P2P Validator Network ──────────────────────────────────
VALIDATOR_PID=""
if [ "${TRION_ENABLE_VALIDATOR:-0}" = "1" ]; then
    if command -v go >/dev/null 2>&1 && [ -f /app/validator/go.mod ]; then
        log "Starting Go P2P Validator Network..."
        cd /app/validator
        if [ ! -f /app/validator/trion-validator ]; then
            log "Building validator binary..."
            go build -o trion-validator ./cmd/trion-validator/ 2>&1 | tail -5 || warn "Build failed"
        fi
        if [ -f /app/validator/trion-validator ]; then
            ./trion-validator && log "Validator mesh self-test PASSED" \
                                 || warn "Validator mesh self-test FAILED"
        else
            go run ./cmd/trion-validator/ && log "Validator mesh self-test PASSED" \
                                           || warn "Validator mesh self-test FAILED"
        fi
    else
        warn "Validator enabled but Go toolchain/source missing — skipping"
    fi
fi

# ── 5b. Optional: C++ Signal Processing Engine ────────────────────────────
SIGNAL_PID=""
if [ "${TRION_ENABLE_SIGNAL_PROCESSING:-0}" = "1" ]; then
    if command -v cmake >/dev/null 2>&1 && [ -f /app/signal-processing/CMakeLists.txt ]; then
        log "Starting C++ Signal Processing Engine..."
        cd /app/signal-processing
        if [ ! -d /app/signal-processing/build ]; then
            log "Building signal processing (first run)..."
            mkdir -p build && cd build
            cmake .. -DCMAKE_BUILD_TYPE=Release 2>&1 | tail -5 || warn "CMake configure failed"
            make -j"$(nproc)" 2>&1 | tail -5 || warn "Build failed"
            cd /app/signal-processing
        fi
        if [ -f /app/signal-processing/build/trion_fft_engine ]; then
            echo '[1.0, 0.5, -0.25, 0.125]' | ./build/trion_fft_engine --stdin >/dev/null 2>&1 \
                && log "FFT engine stdin bridge verified" \
                || warn "FFT engine stdin bridge self-check failed"
        else
            warn "Signal processing binary not built"
        fi
    else
        warn "Signal processing enabled but cmake/source missing"
    fi
fi

# ── Trap: clean shutdown of all services ────────────────────────────────────
cleanup() {
    log "Shutting down TRION stack (signal received)..."
    for pid in $SERVE_PID $FAISS_PID $BH_PID $VALIDATOR_PID $SIGNAL_PID; do
        [ -n "$pid" ] && kill -TERM "$pid" 2>/dev/null
    done
    wait 2>/dev/null
    exit 0
}
trap cleanup SIGTERM SIGINT

# ── Watchdog: restart-on-death of critical services ────────────────────────
(
    while true; do
        sleep 30
        # FAISS watchdog — critical
        if ! kill -0 "$FAISS_PID" 2>/dev/null; then
            warn "FAISS process died — exiting for Railway restart"
            kill -TERM "$SERVE_PID" 2>/dev/null
            exit 1
        fi
        # serve.py watchdog — critical
        if ! kill -0 "$SERVE_PID" 2>/dev/null; then
            warn "serve.py process died — exiting for Railway restart"
            exit 1
        fi
        # BH Streamer watchdog — non-critical
        if [ -n "$BH_PID" ] && ! kill -0 "$BH_PID" 2>/dev/null; then
            warn "BH Streamer process died — non-fatal"
        fi
    done
) &
WATCHDOG_PID=$!
log "Watchdog active (PID $WATCHDOG_PID)"

# ── Periodic status log ────────────────────────────────────────────────────
(
    while true; do
        sleep 300
        _bh_count=$(sqlite3 "${BH_LEDGER_DB}" "SELECT COUNT(*) FROM bh_ledger" 2>/dev/null || echo "?")
        _vec_count=$(curl -s --max-time 5 "http://127.0.0.1:${FAISS_PORT}/health" 2>/dev/null \
                     | grep -o '"indexed_vectors":[0-9]*' | cut -d: -f2 || echo "?")
        _serve_ok=$(kill -0 "$SERVE_PID" 2>/dev/null && echo UP || echo DOWN)
        _faiss_ok=$(kill -0 "$FAISS_PID" 2>/dev/null && echo UP || echo DOWN)
        log "STATUS bh_ledger=${_bh_count} vectors=${_vec_count:-busy} serve=${_serve_ok} faiss=${_faiss_ok}"
    done
) &

# ── Wait on serve.py (keep container alive) ──────────────────────────────────
wait "$SERVE_PID"
log "serve.py exited — container shutting down"
cleanup
