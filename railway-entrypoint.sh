#!/usr/bin/env bash
# =============================================================================
# TRION Protocol — Railway / Container Entrypoint  (v2)
#
# STARTUP ORDER (each step gates the next):
#   0.  Preflight (env / storage / RPC sanity)            — fails fast, exits
#   1.  BH ledger DB init                                  — fast, idempotent
#   2.  FAISS ANIMA Engine (port $FAISS_PORT)              — waits for /readyz
#   3.  Flask Oracle API (port $FLASK_PORT)                — waits for /readyz
#   4.  BH Streamer (background)                           — best-effort
#   5.  BH → FAISS backfill (background, delayed 60s)
#   6.  Next.js frontend (port $PORT — public)
#
# HEALTH MODEL
#   /healthz     — process is alive (always 200 once started)
#   /readyz      — service is ready to serve (200 only after deps up)
#   /api/v1/health  — Flask app-level health (deep, includes oracle stats)
#
# OPTIONAL SERVICES (env toggles, default OFF):
#   TRION_ENABLE_VALIDATOR=1       — Go P2P Validator (port 6000)
#   TRION_ENABLE_SIGNAL_PROCESSING=1 — C++ FFT signal engine
#   TRION_ENABLE_MONITORING=1       — Prometheus/Grafana
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
export BH_LEDGER_DB="${BH_LEDGER_DB:-/app/bh_ledger.db}"
export PYTHONUNBUFFERED=1
export PYTHONDONTWRITEBYTECODE=1

log()  { echo "[entrypoint $(date +%H:%M:%S)] $*"; }
warn() { echo "[entrypoint $(date +%H:%M:%S)] WARN: $*" >&2; }
die()  { echo "[entrypoint $(date +%H:%M:%S)] FATAL: $*" >&2; exit 1; }

# ── 0. Preflight (env / storage / RPC sanity) ─────────────────────────────
log "Running preflight checks..."
python3 /app/scripts/deploy_preflight.py || die "Preflight failed — refusing to start"

# ── 1. BH ledger init (idempotent — safe to re-run) ────────────────────────
log "Initializing BH ledger at ${BH_LEDGER_DB}..."
python3 /app/scripts/init_bh_ledger.py 2>&1 | head -3 || warn "BH init non-fatal"

# ── 2. FAISS ANIMA Engine ──────────────────────────────────────────────────
log "Starting FAISS ANIMA Engine on :${FAISS_PORT}..."
cd /app/anima-service
OMP_NUM_THREADS=1 OPENBLAS_NUM_THREADS=1 MKL_NUM_THREADS=1 NUMEXPR_NUM_THREADS=1 \
PORT="${FAISS_PORT}" FAISS_PORT="${FAISS_PORT}" \
python3 -m uvicorn faiss_service:app --host 0.0.0.0 --port "${FAISS_PORT}" --workers 1 &
FAISS_PID=$!

# Wait for FAISS to be READY (not just alive)
FAISS_READY=false
for i in $(seq 1 60); do
    if curl -fs "http://127.0.0.1:${FAISS_PORT}/readyz" >/dev/null 2>&1; then
        log "FAISS ready after ${i}s"
        FAISS_READY=true
        break
    fi
    # If /readyz 503s but /healthz 200s, index is still cold — keep waiting
    sleep 1
done
if [ "${FAISS_READY}" != "true" ]; then
    # Tolerate FAISS still warming — log warning, continue (Railway healthcheck
    # will block routing on /readyz anyway). The watchdog will kill the
    # container if FAISS truly dies (process not running).
    warn "FAISS /readyz not green after 60s — continuing (cold start)"
fi
cd /app

# ── 3. Flask Oracle API ────────────────────────────────────────────────────
log "Starting Flask Oracle API on :${FLASK_PORT}..."
cd /app
gunicorn \
    --bind "0.0.0.0:${FLASK_PORT}" \
    --workers "${GUNICORN_WORKERS:-2}" \
    --threads "${GUNICORN_THREADS:-4}" \
    --timeout "${GUNICORN_TIMEOUT:-120}" \
    --keep-alive 5 \
    --log-level info \
    --access-logfile - \
    --error-logfile - \
    "api.app:app" &
FLASK_PID=$!

# Wait for Flask to be READY (probe /readyz — which itself probes FAISS)
FLASK_READY=false
for i in $(seq 1 60); do
    if curl -fs "http://127.0.0.1:${FLASK_PORT}/readyz" >/dev/null 2>&1; then
        log "Flask ready after ${i}s"
        FLASK_READY=true
        break
    fi
    sleep 1
done
if [ "${FLASK_READY}" != "true" ]; then
    warn "Flask /readyz not green after 60s — continuing (FAISS may be cold)"
fi

# ── 4. BH Streamer (real-time behavioral hash ingestion) ──────────────────
if [ "${TRION_ENABLE_STREAMER:-1}" = "1" ]; then
    log "Starting BH Streamer..."
    python3 /app/scripts/run_bh_streamer.py &
    BH_PID=$!
    log "BH Streamer PID: $BH_PID"
else
    BH_PID=""
    log "BH Streamer disabled (TRION_ENABLE_STREAMER=0)"
fi

# ── 4b. Auto-backfill BHs → FAISS vectors (background, delayed) ───────────
(
    sleep 60   # let the streamer accumulate some data first
    log "Running BH → FAISS backfill..."
    if [ -f /app/anima-service/backfill_entity_records.py ]; then
        cd /app/anima-service
        python3 backfill_entity_records.py \
            --faiss-url "http://127.0.0.1:${FAISS_PORT}" \
            --bh-db "${BH_LEDGER_DB}" \
            --batch-size 500 2>&1 | tail -5 &
        log "Backfill started (PID $!)"
    else
        warn "Backfill script not found — vectors populate via 30min scheduler"
    fi
) &

# ── 5. Optional: Go P2P Validator Network ──────────────────────────────────
VALIDATOR_PID=""
if [ "${TRION_ENABLE_VALIDATOR:-0}" = "1" ]; then
    if command -v go >/dev/null 2>&1 && [ -f /app/validator/go.mod ]; then
        log "Starting Go P2P Validator Network..."
        cd /app/validator
        if [ ! -f /app/validator/trion-validator ]; then
            log "Building validator binary (first run)..."
            # audit fix: was ./cmd/validator/ (never existed) — actual package dir
            # is ./cmd/trion-validator/. Fixed 2026-09-01 (audit: ENTRY-3).
            go build -o trion-validator ./cmd/trion-validator/ 2>&1 | tail -5 || warn "Build failed"
        fi
        if [ -f /app/validator/trion-validator ]; then
            # audit fix (ENTRY-4): cmd/trion-validator is a ONE-SHOT self-test
            # (verifies mesh primitives: diversity weight, HHI, dual-strand
            # signing) — it exits immediately and ignores --port. The mesh
            # node library (MeshNode) has no server entrypoint yet. Run the
            # self-test honestly instead of daemonizing a binary that exits.
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
            # audit fix (ENTRY-5): CMake emits trion_fft_engine + trion_sensor_interface
            # (there was never a trion_signal target). fft_engine is the binary with
            # the --stdin JSON bridge used by core/native_bridge.py. Without a stdin
            # producer it exits immediately — so verify it runs rather than daemonize.
            echo '[1.0, 0.5, -0.25, 0.125]' | ./build/trion_fft_engine --stdin >/dev/null 2>&1 \
                && log "FFT engine stdin bridge verified" \
                || warn "FFT engine stdin bridge self-check failed"
        else
            warn "Signal processing binary not built (expected trion_fft_engine)"
        fi
    else
        warn "Signal processing enabled but cmake/source missing"
    fi
fi

# ── 6. Next.js frontend (PUBLIC PORT) ─────────────────────────────────────
# Started LAST so all upstream deps are already up — Next.js's /readyz
# probes Flask's /readyz which probes FAISS /readyz. Start earlier and the
# very first healthcheck might land during warmup.
log "Starting Next.js frontend on :${PORT}..."
cd /app/frontend
PORT="${PORT}" node server.js &
NEXT_PID=$!
cd /app
log "Next.js started (PID $NEXT_PID)"

# ── Trap: clean shutdown of all services (SIGTERM/SIGINT) ─────────────────
cleanup() {
    log "Shutting down TRION stack (signal received)..."
    for pid in $NEXT_PID $FLASK_PID $FAISS_PID $BH_PID $VALIDATOR_PID $SIGNAL_PID; do
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
            kill -TERM "$NEXT_PID" 2>/dev/null
            exit 1
        fi
        # Flask watchdog — critical
        if ! kill -0 "$FLASK_PID" 2>/dev/null; then
            warn "Flask process died — exiting for Railway restart"
            kill -TERM "$NEXT_PID" 2>/dev/null
            exit 1
        fi
        # BH Streamer watchdog — non-critical, just log
        if [ -n "$BH_PID" ] && ! kill -0 "$BH_PID" 2>/dev/null; then
            warn "BH Streamer process died — non-fatal, will restart in next deploy"
        fi
    done
) &
WATCHDOG_PID=$!
log "Watchdog active (PID $WATCHDOG_PID)"

# ── Periodic status log (Railway logs) ────────────────────────────────────
(
    while true; do
        sleep 300
        _bh_count=$(sqlite3 "${BH_LEDGER_DB}" "SELECT COUNT(*) FROM bh_ledger" 2>/dev/null || echo "?")
        _vec_count=$(curl -s --max-time 5 "http://127.0.0.1:${FAISS_PORT}/health" 2>/dev/null \
                     | grep -o '"indexed_vectors":[0-9]*' | cut -d: -f2 || echo "?")
        _flask_ok=$(kill -0 "$FLASK_PID" 2>/dev/null && echo UP || echo DOWN)
        _next_ok=$(kill -0 "$NEXT_PID" 2>/dev/null && echo UP || echo DOWN)
        log "STATUS bh_ledger=${_bh_count} vectors=${_vec_count:-busy} flask=${_flask_ok} next=${_next_ok}"
    done
) &

# ── Wait on Next.js (keep container alive) ────────────────────────────────
wait "$NEXT_PID"
log "Next.js exited — container shutting down"
cleanup
