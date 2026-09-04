#!/usr/bin/env bash
# ============================================================
# TRION Protocol — Full Stack Startup Script
# ============================================================
# Starts all TRION services in the correct order:
#   1. FAISS Akashic Intelligence Engine (port 8000)
#   2. TRION Oracle API (port 5000)
#   3. Validator P2P Network (port 6000)
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
VALIDATOR_PORT=${VALIDATOR_PORT:-6000}
FRONTEND_PORT=${FRONTEND_PORT:-3000}
FLASK_URL=${FLASK_URL:-"http://127.0.0.1:$API_PORT"}

LOG_DIR="$WORKSPACE/logs"
mkdir -p "$LOG_DIR"

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
    if [ "$BACKGROUND" = true ]; then
        cd "$WORKSPACE" && nohup python3 -m api.app \
            > "$LOG_DIR/api.log" 2>&1 &
        echo $! > "$LOG_DIR/api.pid"
    else
        cd "$WORKSPACE" && python3 -m api.app
    fi
}

start_validators() {
    log "Starting Validator P2P Network..."
    if [ "$BACKGROUND" = true ]; then
        cd "$WORKSPACE" && nohup python3 -m trion_l0.main \
            > "$LOG_DIR/validators.log" 2>&1 &
        echo $! > "$LOG_DIR/validators.pid"
    else
        cd "$WORKSPACE" && python3 -m trion_l0.main
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
        start_validators
        wait_for_port $VALIDATOR_PORT "Validator Network" || true
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
    if [ "$START_VALIDATORS" = true ]; then
        log "  Validator Net:   http://127.0.0.1:$VALIDATOR_PORT"
    fi
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
