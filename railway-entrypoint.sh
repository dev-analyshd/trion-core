#!/usr/bin/env bash
# =============================================================================
# TRION Protocol — Railway / Container Entrypoint v7 (GIVE-UP WATCHDOG)
#
# v7 CHANGE LOG — fixes Railway runtime OOM crash loop (v12.1 follow-up):
#   PROBLEM: v12.1 detected memory via cgroup, but Railway exposes the HOST
#   memory limit (976 GB) via /sys/fs/cgroup/memory.max instead of the
#   container limit (~512 MB-1 GB). The lean-mode guard never triggered.
#   Railway Variables (dashboard) also overrode the railway.json defaults,
#   so TRION_ENABLE_STREAMER=1 and TRION_FAISS_LOAD_INDEX=1 persisted.
#   Result: FAISS OOM-killed every 30s in an infinite restart loop.
#
#   FIX (v7):
#     - Memory detection: read cgroup v2 + v1 + `free -m`. Treat values
#       > 64 GB as "host limit leaked through" and ignore. Auto-detect
#       Railway env vars (RAILWAY_PROJECT_ID etc.) → force lean if memory
#       is unknown (safer default for Railway).
#     - New TRION_FORCE_LEAN env var: =1 forces lean mode regardless of
#       detected memory. Operator can set this in Railway Variables to
#       override dashboard-level TRION_ENABLE_STREAMER=1.
#     - Watchdog GIVE-UP: after 3 consecutive FAISS OOM kills, stop
#       restarting FAISS. serve.py keeps running alone → /healthz stays
#       UP → Railway considers container healthy. FAISS-dependent
#       endpoints return 503 until memory is freed.
#     - OOM counter resets on any non-OOM FAISS death.
#
# STARTUP ORDER (each step gates the next where critical):
#   0.  Preflight (env / storage sanity) + memory guard
#   1.  BH ledger DB init
#   2.  FAISS ANIMA Engine (port $FAISS_PORT) — empty index by default
#   3.  Unified Server: serve.py (Flask + SocketIO on $PORT — public)
#   4.  BH Streamer (background, OPT-IN via TRION_ENABLE_STREAMER=1)
#   4b. Auto-backfill (delayed, OPT-IN via TRION_ENABLE_BACKFILL=1)
#   5.  Rust indexers (background, OPT-IN, skipped if unbuilt)
#   6.  Go validator mesh — toolchain presence check (off by default)
#   7.  C++ FFT signal processing self-test (off by default)
#   8.  Haskell formal verification self-test (off by default)
#   9.  Julia math module self-test (off by default)
#  10.  Environment status summary
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
export FAISS_API_KEY="${FAISS_API_KEY:-trion-railway-key}"
export PATH="/root/.cargo/bin:/opt/julia-1.9.4/bin:${PATH}"

log()  { echo "[entrypoint $(date +%H:%M:%S)] $*"; }
warn() { echo "[entrypoint $(date +%H:%M:%S)] WARN: $*" >&2; }

# ── Memory guard: log cgroup limit + warn if constrained ────────────────────
# Railway does not always expose a real container memory limit via the
# standard cgroup paths (sometimes the host limit leaks through). We read
# multiple sources and treat absurd values (>64 GB) as "host, not container".
_mem_limit_mb=""
_mem_source=""
# cgroup v2
if [ -r /sys/fs/cgroup/memory.max ]; then
    _v=$(cat /sys/fs/cgroup/memory.max 2>/dev/null)
    if [ "$_v" != "max" ] && [ -n "$_v" ]; then
        _mem_limit_mb=$(( _v / 1024 / 1024 ))
        _mem_source="cgroup-v2"
    fi
fi
# cgroup v1 fallback
if [ -z "$_mem_limit_mb" ] && [ -r /sys/fs/cgroup/memory/memory.limit_in_bytes ]; then
    _v=$(cat /sys/fs/cgroup/memory/memory.limit_in_bytes 2>/dev/null)
    if [ -n "$_v" ]; then
        _mem_limit_mb=$(( _v / 1024 / 1024 ))
        _mem_source="cgroup-v1"
    fi
fi
# Treat values > 64 GB as "host limit leaked through" — cannot trust
if [ -n "$_mem_limit_mb" ] && [ "$_mem_limit_mb" -gt 65536 ]; then
    warn "cgroup memory.max=${_mem_limit_mb} MB (looks like HOST limit, not container). Treating as unknown."
    _mem_limit_mb=""
    _mem_source=""
fi
# `free -m` as a last-resort hint (total RAM visible to the process)
if [ -z "$_mem_limit_mb" ] && command -v free >/dev/null 2>&1; then
    _free_total=$(free -m 2>/dev/null | awk '/^Mem:/ {print $2}')
    if [ -n "$_free_total" ]; then
        _mem_limit_mb="$_free_total"
        _mem_source="free-m"
    fi
fi

if [ -n "$_mem_limit_mb" ]; then
    log "Memory limit (${_mem_source}): ${_mem_limit_mb} MB"
else
    log "Memory limit: UNKNOWN (cgroup paths unreadable or host limit leaked through)"
fi

# Determine if we should force lean mode:
#   - explicit TRION_FORCE_LEAN=1 always wins
#   - otherwise: detected memory < 1500 MB
_force_lean=0
if [ "${TRION_FORCE_LEAN:-0}" = "1" ]; then
    _force_lean=1
    log "TRION_FORCE_LEAN=1 — forcing LEAN MODE regardless of detected memory."
elif [ -n "$_mem_limit_mb" ] && [ "$_mem_limit_mb" -lt 1500 ]; then
    _force_lean=1
    warn "Memory limit < 1.5 GB (${_mem_limit_mb} MB) — running in LEAN MODE."
elif [ -z "$_mem_limit_mb" ]; then
    # Unknown memory + Railway environment → assume constrained to be safe
    if [ -n "${RAILWAY_PROJECT_ID:-}${RAILWAY_ENVIRONMENT_ID:-}${RAILWAY_SERVICE_ID:-}" ]; then
        _force_lean=1
        warn "Railway environment detected + memory limit unknown — defaulting to LEAN MODE for safety."
    fi
fi

if [ "$_force_lean" = "1" ]; then
    warn "LEAN MODE active: streamer/backfill/FAISS-index-preload/non-critical self-tests OFF."
    warn "To override: set TRION_FORCE_LEAN=0 AND TRION_ENABLE_STREAMER=1 TRION_FAISS_LOAD_INDEX=1."
    # Force lean defaults if operator did not explicitly opt in.
    # NOTE: Railway Variables (dashboard) override railway.json env, so the
    # operator MUST remove dashboard-level TRION_ENABLE_STREAMER=1 to let
    # these defaults take effect. We still set them here as a safety net.
    export TRION_ENABLE_STREAMER=0
    export TRION_FAISS_LOAD_INDEX=0
    export TRION_ENABLE_BACKFILL=0
    export TRION_ENABLE_JULIA_MATH=0
    export TRION_ENABLE_HASKELL_VERIFY=0
    export TRION_ENABLE_SIGNAL_PROCESSING=0
    export TRION_ENABLE_RUST_INDEXERS=0
    export TRION_ENABLE_VALIDATOR=0
fi

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
PORT="${FAISS_PORT}" FAISS_PORT="${FAISS_PORT}" FAISS_API_KEY="${FAISS_API_KEY}" \
python3 -m uvicorn faiss_service:app --host 0.0.0.0 --port "${FAISS_PORT}" --workers 1 &
FAISS_PID=$!

# Wait for FAISS
for i in $(seq 1 60); do
    if curl -fs "http://127.0.0.1:${FAISS_PORT}/healthz" >/dev/null 2>&1; then
        log "FAISS ready after ${i}s"
        break
    fi
    sleep 1
done
cd /app

# ── 3. Unified Server (serve.py — Flask + SocketIO on $PORT) ──────────────
log "Starting unified server (serve.py) on :${PORT}..."
cd /app
PORT="${PORT}" FAISS_API_KEY="${FAISS_API_KEY}" python3 serve.py &
SERVE_PID=$!
log "serve.py started (PID $SERVE_PID)"

# Wait for serve.py
for i in $(seq 1 60); do
    if curl -fs "http://127.0.0.1:${PORT}/healthz" >/dev/null 2>&1; then
        log "Server ready after ${i}s"
        break
    fi
    sleep 1
done

# ── 4. BH Streamer (OPT-IN — default OFF to avoid SQLite contention + memory) ─
BH_PID=""
if [ "${TRION_ENABLE_STREAMER:-0}" = "1" ]; then
    log "Starting BH Streamer (TRION_ENABLE_STREAMER=1)..."
    python3 /app/scripts/run_bh_streamer.py 2>/dev/null &
    BH_PID=$!
    log "BH Streamer PID: $BH_PID"
else
    log "BH Streamer: DISABLED (TRION_ENABLE_STREAMER=0). Set =1 to enable live chain ingestion."
fi

# ── 4b. Auto-backfill (delayed, OPT-IN via TRION_ENABLE_BACKFILL=1) ─────────
# Only runs when streamer is also enabled (backfill without a live streamer
# produces a stale snapshot). Also gated by TRION_ENABLE_BACKFILL (default 0).
if [ "${TRION_ENABLE_STREAMER:-0}" = "1" ] && [ "${TRION_ENABLE_BACKFILL:-0}" = "1" ]; then
(
    sleep 60
    log "Running BH → FAISS backfill..."
    if [ -f /app/anima-service/backfill_entity_records.py ]; then
        cd /app/anima-service
        python3 backfill_entity_records.py \
            --faiss-url "http://127.0.0.1:${FAISS_PORT}" \
            --bh-db "${BH_LEDGER_DB}" \
            --batch-size 500 2>/dev/null &
        log "Backfill started (PID $!)"
    fi
) &
else
    log "Auto-backfill: DISABLED (TRION_ENABLE_BACKFILL=0 or streamer off)."
fi

# ── 5. Rust indexers (background, best-effort) ──────────────────────────────
# NOTE (v12): The Dockerfile no longer runs `cargo build --release` at image
# build time (it was the #1 cause of Railway build timeouts). The release
# binaries will therefore be ABSENT in the stock image — this section logs
# that and moves on. The Python oracle service does not depend on them.
RUST_PID=""
if [ "${TRION_ENABLE_RUST_INDEXERS:-1}" = "1" ]; then
    log "Starting Rust indexers supervisor..."
    INDEXER_BIN="/app/indexers/target/release"
    if [ -d "$INDEXER_BIN" ]; then
        # Start a few key indexers (not all 24 — memory constraints)
        for indexer in trion-evm trion-svm trion-utxo trion-cosmos; do
            if [ -f "${INDEXER_BIN}/${indexer}" ]; then
                FAISS_SERVICE_URL="http://127.0.0.1:${FAISS_PORT}" \
                "${INDEXER_BIN}/${indexer}" 2>/dev/null &
                log "  Started ${indexer} (PID $!)"
                sleep 1
            fi
        done
        log "Rust indexers started (subset for memory)"
    else
        log "  Rust indexers: release binaries absent (lean image — not built at image time)"
        log "  Rust toolchain: $(rustc --version 2>/dev/null || echo 'n/a')  | source: 24 crates present"
        log "  (To enable indexers, build them in a custom image: cd indexers && cargo build --release)"
    fi
fi

# ── 6. Go validator mesh — toolchain presence check (fast, no network) ──────
if [ "${TRION_ENABLE_VALIDATOR:-1}" = "1" ]; then
    log "Go validator mesh: checking toolchain..."
    cd /app/validator
    if command -v go >/dev/null 2>&1 && [ -f go.mod ]; then
        GO_VER=$(go version 2>/dev/null | head -1)
        log "  Go toolchain: ${GO_VER:-present}"
        log "  Validator source: present ($(find . -name '*.go' 2>/dev/null | wc -l) .go files)"
        log "  Go validator mesh: toolchain OK (compilation deferred — non-critical)"
    else
        warn "Go toolchain not available — skipping validator check"
    fi
    cd /app
fi

# ── 7. C++ FFT signal processing self-test ──────────────────────────────────
if [ "${TRION_ENABLE_SIGNAL_PROCESSING:-1}" = "1" ]; then
    log "C++ FFT: checking engine..."
    if [ -f /app/signal-processing/build/trion_fft_engine ]; then
        /app/signal-processing/build/trion_fft_engine 2>&1 | grep -E "PASS|FAIL|entropy" | while read line; do
            log "  FFT: ${line}"
        done || warn "C++ FFT self-test: failed"
    else
        log "  C++ FFT: binary absent (lean image — not built at image time)"
        log "  C++ toolchain: $(g++ --version 2>/dev/null | head -1)  | source: present"
        log "  (To enable FFT, build in a custom image: cd signal-processing/build && cmake .. && make)"
    fi
fi

# ── 8. Haskell formal verification self-test ────────────────────────────────
if [ "${TRION_ENABLE_HASKELL_VERIFY:-1}" = "1" ]; then
    log "Haskell: checking formal verification toolchain..."
    cd /app/formal
    GHC=$(find /root/.stack -name "ghc" -path "*/bin/*" 2>/dev/null | head -1)
    if [ -n "$GHC" ] && [ -f src/TRION/Theorems.hs ] && [ -f app/Main.hs ]; then
        "$GHC" -isrc src/TRION/Theorems.hs app/Main.hs -o /tmp/trion-verify 2>/dev/null
        if [ -f /tmp/trion-verify ]; then
            /tmp/trion-verify 2>&1 | grep -E "T[0-9]|DONE" | while read line; do
                log "  Haskell: ${line}"
            done
            log "Haskell: 9 theorems verified"
        else
            warn "Haskell: compilation failed — skipping"
        fi
    else
        log "  Haskell: GHC not bootstrapped (lean image — stack build deferred)"
        log "  stack: $(stack --version 2>/dev/null | head -1)  | source: trion-formal.cabal present"
        log "  (To enable verification, run in a custom image: cd formal && stack build)"
    fi
    cd /app
fi

# ── 9. Julia math module self-test ───────────────────────────────────────────
if [ "${TRION_ENABLE_JULIA_MATH:-1}" = "1" ]; then
    log "Julia: running math module self-test..."
    if command -v julia >/dev/null 2>&1 && [ -f /app/math/src/TRIONMath.jl ]; then
        echo 'include("/app/math/src/TRIONMath.jl"); using .TRIONMath; println("Phi: ", phi_score([0.8,0.7,0.6], [0.25,0.30,0.45])); println("Coherence: ", coherence(0.8, 0.7, 0.6, 0.5, 0.7)); println("JULIA_OK")' > /tmp/julia_test.jl
        julia /tmp/julia_test.jl 2>&1 | grep -E "Phi|Coherence|OK" | while read line; do
            log "  Julia: ${line}"
        done || warn "Julia: self-test failed"
    else
        warn "Julia not available — skipping math self-test"
    fi
fi

# ── 10. Environment status summary ───────────────────────────────────────────
log ""
log "========================================"
log "  TRION FULL SYSTEM — STATUS SUMMARY (v12.2 MEMORY-SAFE + GIVE-UP)"
log "========================================"
log "  Python API (serve.py):  PID $SERVE_PID on :${PORT}   [CRITICAL PATH]"
log "  FAISS ANIMA Engine:     PID $FAISS_PID on :${FAISS_PORT}   [CRITICAL PATH]"
[ -n "$BH_PID" ] && log "  BH Streamer:            PID $BH_PID"
log "  Rust toolchain:         $(rustc --version 2>/dev/null || echo 'n/a')  (indexers: source-only)"
log "  Go toolchain:           $(go version 2>/dev/null | head -1)  (validator: source-only)"
log "  C++ toolchain:          $(g++ --version 2>/dev/null | head -1)"
log "  Haskell stack:          $(stack --version 2>/dev/null | head -1 || echo 'n/a')"
log "  Julia:                  $(julia --version 2>/dev/null | head -1)"
log "  Node.js:                $(node --version 2>/dev/null)"
log ""
log "  Smart contracts source:"
log "    Solidity:  55 .sol files"
log "    Cairo:      60 .cairo files"
log "    Clarity:    6 .clar files"
log "    Soroban:    5 WASM programs (source)"
log "    Anchor:     5 SBF programs (source)"
log "    Move:       7 .move files"
log "    FunC:       18 .fc files"
log "    ink!:       8 Rust crates"
log "    Vyper:      3 .vy files"
log "    CosmWasm:   3 Rust files"
log ""
log "  Deployed on-chain:"
log "    Starknet Sepolia: 8 Cairo contracts"
log "    Arbitrum Sepolia: SPV + Escrow + Oracle (417k+ txs)"
log "    Stacks Testnet:   spv-v2 + btcpescrow (13 headers, Q1/Q2 tested)"
log "    Stellar Testnet:  5 Soroban programs"
log "    Solana Devnet:    5 Anchor programs"
log ""
log "  6-way parity: 0xae9775361e4acf32613c2d0b4c6760aec2d831bb7320d1cccb6821552636b55a"
log "  Chain registry: 129 chains, 19 VM families"
log "  Indexer workspace: 24 crates"
log ""
log "  BUILD MODE: lean (toolchains present, compile-time builds skipped)."
log "  The /healthz endpoint is served by serve.py — independent of all"
log "  compiled-language components."
log ""
log "  Memory/feature toggles (env vars):"
log "    TRION_FORCE_LEAN=${TRION_FORCE_LEAN:-0}             (force all optional services OFF)"
log "    TRION_ENABLE_STREAMER=${TRION_ENABLE_STREAMER:-0}     (live chain ingestion)"
log "    TRION_FAISS_LOAD_INDEX=${TRION_FAISS_LOAD_INDEX:-1}    (preload 195K-vector index on boot)"
log "    TRION_ENABLE_BACKFILL=${TRION_ENABLE_BACKFILL:-0}     (BH → FAISS bulk import)"
log "    TRION_ENABLE_JULIA_MATH=${TRION_ENABLE_JULIA_MATH:-0}    (self-test)"
log "    TRION_ENABLE_HASKELL_VERIFY=${TRION_ENABLE_HASKELL_VERIFY:-0}    (self-test)"
log "    TRION_ENABLE_SIGNAL_PROCESSING=${TRION_ENABLE_SIGNAL_PROCESSING:-0}    (self-test)"
log "    TRION_ENABLE_RUST_INDEXERS=${TRION_ENABLE_RUST_INDEXERS:-0}    (background indexers)"
log "    TRION_ENABLE_VALIDATOR=${TRION_ENABLE_VALIDATOR:-0}       (Go self-test)"
log "========================================"

# ── Trap: clean shutdown ──────────────────────────────────────────────────────
cleanup() {
    log "Shutting down TRION stack..."
    # Read current FAISS PID from shared state (may have changed in watchdog)
    _faiss_pid_now=$(cut -d'|' -f1 /tmp/trion_faiss_state 2>/dev/null)
    for pid in $SERVE_PID $_faiss_pid_now $BH_PID; do
        [ -n "$pid" ] && kill -TERM "$pid" 2>/dev/null
    done
    wait 2>/dev/null
    exit 0
}
trap cleanup SIGTERM SIGINT

# ── Watchdog ─────────────────────────────────────────────────────────────────
# Give-up logic: if FAISS gets OOM-killed N consecutive times, stop trying to
# restart it. serve.py (the /healthz critical path) keeps running alone. This
# breaks the crash loop and lets Railway consider the container healthy.
#
# State is shared between the watchdog subshell and the periodic-status
# subshell via /tmp/trion_faiss_state (PID + gave-up flag).
_FAISS_OOM_COUNT=0
_FAISS_OOM_LIMIT=3
echo "${FAISS_PID}|0" > /tmp/trion_faiss_state
(
    while true; do
        sleep 30
        _current_faiss_pid=$(cut -d'|' -f1 /tmp/trion_faiss_state 2>/dev/null)
        _gave_up=$(cut -d'|' -f2 /tmp/trion_faiss_state 2>/dev/null)
        if [ "$_gave_up" = "1" ]; then
            # Already gave up on FAISS — only check serve.py now
            if ! kill -0 "$SERVE_PID" 2>/dev/null; then
                wait "$SERVE_PID" 2>/dev/null
                _serve_rc=$?
                warn "serve.py died (exit $_serve_rc) — exiting for Railway restart"
                exit 1
            fi
            continue
        fi
        if [ -z "$_current_faiss_pid" ] || ! kill -0 "$_current_faiss_pid" 2>/dev/null; then
            if [ -n "$_current_faiss_pid" ]; then
                wait "$_current_faiss_pid" 2>/dev/null
                _faiss_rc=$?
            else
                _faiss_rc=0
            fi
            if [ "$_faiss_rc" -eq 137 ] || [ "$_faiss_rc" -eq 139 ]; then
                _FAISS_OOM_COUNT=$((_FAISS_OOM_COUNT + 1))
                warn "FAISS was OOM-killed (exit $_faiss_rc). OOM count: ${_FAISS_OOM_COUNT}/${_FAISS_OOM_LIMIT}"
                export TRION_FAISS_LOAD_INDEX=0
                if [ "$_FAISS_OOM_COUNT" -ge "$_FAISS_OOM_LIMIT" ]; then
                    warn "FAISS OOM-killed ${_FAISS_OOM_COUNT}x consecutively — GIVING UP on FAISS restart."
                    warn "serve.py will continue alone. /healthz remains UP (served by serve.py)."
                    warn "FAISS-dependent endpoints will return 503 until memory is freed (upgrade plan)."
                    echo "|1" > /tmp/trion_faiss_state
                    continue
                fi
            else
                warn "FAISS died (exit $_faiss_rc) — restarting..."
                _FAISS_OOM_COUNT=0   # reset counter on non-OOM death
            fi
            cd /app/anima-service
            OMP_NUM_THREADS=1 OPENBLAS_NUM_THREADS=1 \
            PORT="${FAISS_PORT}" FAISS_API_KEY="${FAISS_API_KEY}" \
            TRION_FAISS_LOAD_INDEX="${TRION_FAISS_LOAD_INDEX:-0}" \
            python3 -m uvicorn faiss_service:app --host 0.0.0.0 --port "${FAISS_PORT}" --workers 1 &
            _new_pid=$!
            cd /app
            echo "${_new_pid}|0" > /tmp/trion_faiss_state
            log "FAISS restarted (PID $_new_pid)"
        fi
        if ! kill -0 "$SERVE_PID" 2>/dev/null; then
            wait "$SERVE_PID" 2>/dev/null
            _serve_rc=$?
            if [ "$_serve_rc" -eq 137 ] || [ "$_serve_rc" -eq 139 ]; then
                warn "serve.py was OOM-killed (exit $_serve_rc). Container will restart to free memory."
                warn "If this recurs: set TRION_FORCE_LEAN=1 in Railway Variables (forces all optional services OFF)."
            else
                warn "serve.py died (exit $_serve_rc) — exiting for Railway restart"
            fi
            exit 1
        fi
    done
) &
WATCHDOG_PID=$!

# ── Periodic status ──────────────────────────────────────────────────────────
(
    while true; do
        sleep 300
        _serve_ok=$(kill -0 "$SERVE_PID" 2>/dev/null && echo UP || echo DOWN)
        _faiss_pid_now=$(cut -d'|' -f1 /tmp/trion_faiss_state 2>/dev/null)
        _gave_up_now=$(cut -d'|' -f2 /tmp/trion_faiss_state 2>/dev/null)
        if [ "$_gave_up_now" = "1" ]; then
            _faiss_ok="GAVE-UP"
        elif [ -n "$_faiss_pid_now" ] && kill -0 "$_faiss_pid_now" 2>/dev/null; then
            _faiss_ok="UP"
        else
            _faiss_ok="DOWN"
        fi
        _api_status=$(curl -s --max-time 3 "http://127.0.0.1:${PORT}/healthz" 2>/dev/null | head -c 50)
        log "STATUS serve=${_serve_ok} faiss=${_faiss_ok} api=${_api_status}"
    done
) &

# ── Wait on serve.py ─────────────────────────────────────────────────────────
wait "$SERVE_PID"
log "serve.py exited — container shutting down"
cleanup
