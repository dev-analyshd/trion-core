#!/usr/bin/env bash
# ============================================================
# TRION Protocol — Full Stack Startup Script
# ============================================================
# Starts all TRION services in the correct order:
#   1. FAISS Akashic Intelligence Engine (port 8000)
#   2. TRION Oracle API (port 5000)
#   3. Validator self-test (one-shot `go run ./cmd/trion-validator` —
#      mesh + TRION-BFT check that prints PASS and exits; NOT a
#      long-lived network listener, see DEPLOYMENT.md "Go services")
#   4. Frontend Next.js (port 3000)
#
# Usage:
#   ./scripts/start_trion.sh [--background] [--no-frontend] [--no-validators]
# ============================================================

set -e

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"

# ── Python path configuration ────────────────────────────────────────────────
# Support custom library locations (for environments where system pip is restricted).
# TRION_EXTRA_PYTHONPATH lets you prepend site-packages without editing this script.
if [ -n "${TRION_EXTRA_PYTHONPATH:-}" ]; then
    export PYTHONPATH="${TRION_EXTRA_PYTHONPATH}:${PYTHONPATH:-}"
fi
echo "PYTHONPATH configured: ${PYTHONPATH:-<default>}"
WORKSPACE="$(dirname "$SCRIPT_DIR")"
cd "$WORKSPACE"

# ── Configuration ─────────────────────────────────────────────
FAISS_PORT=${FAISS_PORT:-8000}
API_PORT=${API_PORT:-5000}
FRONTEND_PORT=${FRONTEND_PORT:-3000}
FLASK_URL=${FLASK_URL:-"http://127.0.0.1:$API_PORT"}

LOG_DIR="$WORKSPACE/logs"
mkdir -p "$LOG_DIR"

# ── Signing-custody guard (master command §17) ────────────────
# TRION_ENV=production REFUSES to start when a raw env private key is set:
# plaintext env keys are DEV/TESTNET-ONLY. The production signing path is
# KMS/HSM-backed (KMS_PROVIDER=aws|gcp|yubihsm|pkcs11 — relayer/kms_provider.js)
# or documented custody. The only escape hatch is TRION_ALLOW_RAW_ENV_KEYS=1,
# which the operator sets to explicitly acknowledge env-secret custody
# (secret-manager-injected vars only — never a committed value). See
# DEPLOYMENT.md "Signing and key custody".
if [ "${TRION_ENV:-development}" = "production" ] \
   && [ "${TRION_ALLOW_RAW_ENV_KEYS:-0}" != "1" ]; then
    for _key_var in RELAYER_PRIVATE_KEY PRIVATE_KEY ZG_PRIVATE_KEY \
                    DEPLOY_0G_PRIVATE DEPLOYER_PRIVATE_KEY \
                    SOLANA_RELAYER_PRIVATE_KEY SVM_PRIVATE_KEY_B58 \
                    NEAR_RELAYER_PRIVATE_KEY NEAR_PRIVATE_KEY \
                    TON_RELAYER_PRIVATE_KEY TON_PRIVATE_KEY_HEX \
                    PVM_RELAYER_MNEMONIC DOT_MNEMONIC \
                    STARKNET_RELAYER_PRIVATE_KEY STARKNET_PRIVATE_KEY \
                    BOT_CHAIN_PRIVATE_KEY BOT_CHAIN_RELAYER_PRIVATE_KEY; do
        if [ -n "$(eval "printf '%s' \"\${${_key_var}:-}\"")" ]; then
            echo "FATAL: TRION_ENV=production but raw env private key ${_key_var} is set." >&2
            echo "       Env keys are DEV/TESTNET-ONLY. Use KMS_PROVIDER=aws|gcp|yubihsm|pkcs11" >&2
            echo "       (relayer/kms_provider.js) or set TRION_ALLOW_RAW_ENV_KEYS=1 to" >&2
            echo "       acknowledge documented env-secret custody." >&2
            exit 1
        fi
    done
fi

# ── Parse arguments ───────────────────────────────────────────
BACKGROUND=false
START_FRONTEND=true
START_VALIDATORS=true

for arg in "$@"; do
    case $arg in
        --background|-b) BACKGROUND=true ;;
        --no-frontend) START_FRONTEND=false ;;
        --no-validators) START_VALIDATORS=false ;;
        --help|-h)
            echo "Usage: $0 [--background] [--no-frontend] [--no-validators]"
            echo "  --background, -b    Run services in background"
            echo "  --no-frontend       Skip frontend"
            echo "  --no-validators     Skip validator network"
            exit 0
            ;;
    esac
done

# ── Helper functions ──────────────────────────────────────────
log() {
    echo "[$(date '+%H:%M:%S')] $1"
}

wait_for_port() {
    local port=$1
    local service=$2
    local max_attempts=30
    local attempt=0
    
    log "Waiting for $service on port $port..."
    while ! nc -z 127.0.0.1 "$port" 2>/dev/null; do
        attempt=$((attempt + 1))
        if [ $attempt -ge $max_attempts ]; then
            log "⚠️  $service failed to start on port $port after ${max_attempts}s"
            return 1
        fi
        sleep 1
    done
    log "✓ $service is ready on port $port"
    return 0
}

# ── Python environment check ─────────────────────────────────
if ! python3 -c "import flask, fastapi, faiss, numpy, sqlalchemy, pydantic" 2>/dev/null; then
    log "⚠️  Some dependencies missing. Installing..."
    pip install --quiet flask fastapi faiss-cpu numpy sqlalchemy pydantic uvicorn apscheduler requests pandas 2>/dev/null || true
fi

# ── Service starters ─────────────────────────────────────────

start_faiss() {
    log "Starting FAISS Akashic Intelligence Engine..."
    if [ "$BACKGROUND" = true ]; then
        cd "$WORKSPACE/anima-service" && nohup python3 faiss_service.py \
            > "$LOG_DIR/faiss.log" 2>&1 &
        echo $! > "$LOG_DIR/faiss.pid"
    else
        cd "$WORKSPACE/anima-service" && python3 faiss_service.py
    fi
}

start_api() {
    log "Starting TRION Oracle API..."
    export FLASK_URL="$FLASK_URL"
    # Local dev profile: serve.py is a SINGLE process, so the in-process BH
    # streamer gate (TRION_STREAMER_INPROCESS, default 0 in app.py) is the
    # correct mode here — exactly one streamer, owned by the API process.
    # Set TRION_STREAMER_INPROCESS=0 if you run scripts/run_bh_streamer.py
    # yourself instead (the docker entrypoints do that).
    export TRION_STREAMER_INPROCESS="${TRION_STREAMER_INPROCESS:-1}"
    if [ "$BACKGROUND" = true ]; then
        cd "$WORKSPACE" && nohup python3 serve.py \
            > "$LOG_DIR/api.log" 2>&1 &
        echo $! > "$LOG_DIR/api.pid"
    else
        cd "$WORKSPACE" && python3 serve.py
    fi
}

start_validators() {
    # The old `python3 -m trion_l0.main` module was removed long ago — this
    # step used to crash the script (and silently log a python error in
    # background mode). The validator mesh is the Go binary now:
    if command -v go >/dev/null 2>&1; then
        log "Starting Validator P2P Network (go run)..."
        cd "$WORKSPACE/validator" && nohup go run ./cmd/trion-validator \
            > "$LOG_DIR/validators.log" 2>&1 &
        echo $! > "$LOG_DIR/validators.pid"
    else
        log "Skipping validator mesh: no Go toolchain on PATH (build validator/cmd/trion-validator where go exists)"
    fi
}

start_frontend() {
    log "Starting Frontend (Next.js)..."
    export FLASK_URL="$FLASK_URL"
    if [ "$BACKGROUND" = true ]; then
        cd "$WORKSPACE/frontend" && nohup npm run dev \
            > "$LOG_DIR/frontend.log" 2>&1 &
        echo $! > "$LOG_DIR/frontend.pid"
    else
        cd "$WORKSPACE/frontend" && npm run dev
    fi
}

# ── Main startup sequence ────────────────────────────────────
log "============================================================"
log "TRION PROTOCOL — FULL STACK STARTUP"
log "============================================================"
log "Workspace: $WORKSPACE"
log "Logs: $LOG_DIR"
log ""

# Kill any existing services
if [ -f "$LOG_DIR/faiss.pid" ]; then
    kill "$(cat "$LOG_DIR/faiss.pid")" 2>/dev/null || true
fi
if [ -f "$LOG_DIR/api.pid" ]; then
    kill "$(cat "$LOG_DIR/api.pid")" 2>/dev/null || true
fi

# Start services in order
if [ "$BACKGROUND" = true ]; then
    start_faiss
    wait_for_port $FAISS_PORT "FAISS Engine" || true
    
    start_api
    wait_for_port $API_PORT "Oracle API" || true
    
    if [ "$START_VALIDATORS" = true ]; then
        start_validators   # one-shot Go self-test — no port to wait for
    fi
    
    if [ "$START_FRONTEND" = true ]; then
        if command -v npm &>/dev/null; then
            start_frontend
            wait_for_port $FRONTEND_PORT "Frontend" || true
        else
            log "⚠️  npm not found — skipping frontend"
        fi
    fi
    
    log ""
    log "============================================================"
    log "ALL SERVICES STARTED"
    log "============================================================"
    log "  FAISS Engine:    http://127.0.0.1:$FAISS_PORT"
    log "  Oracle API:      http://127.0.0.1:$API_PORT"
    if [ "$START_FRONTEND" = true ] && command -v npm &>/dev/null; then
        log "  Frontend:        http://127.0.0.1:$FRONTEND_PORT"
    fi
    log ""
    log "  Logs: $LOG_DIR/"
    log "  Stop: ./scripts/stop_trion.sh"
    log "============================================================"
else
    # Foreground mode — start FAISS first in background, then API in foreground
    start_faiss &
    sleep 3
    start_api
fi
