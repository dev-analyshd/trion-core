#!/usr/bin/env bash
# ============================================================
# TRION Protocol — Stop All Services
# ============================================================
# Stops all TRION services started by start_trion.sh
#
# Usage:
#   ./scripts/stop_trion.sh
# ============================================================

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
WORKSPACE="$(dirname "$SCRIPT_DIR")"
LOG_DIR="$WORKSPACE/logs"

log() {
    echo "[$(date '+%H:%M:%S')] $1"
}

log "Stopping TRION services..."

# Stop by PID files
for service in faiss api validators frontend; do
    pid_file="$LOG_DIR/${service}.pid"
    if [ -f "$pid_file" ]; then
        pid=$(cat "$pid_file")
        if kill -0 "$pid" 2>/dev/null; then
            kill "$pid" 2>/dev/null
            log "✓ Stopped $service (PID $pid)"
        else
            log "⚠️  $service (PID $pid) not running"
        fi
        rm -f "$pid_file"
    fi
done

# Also kill any remaining Python processes that match TRION services
pkill -f "faiss_service.py" 2>/dev/null && log "✓ Stopped faiss_service.py" || true
pkill -f "serve.py" 2>/dev/null && log "✓ Stopped serve.py (Flask + socketio)" || true
pkill -f "api.app" 2>/dev/null && log "✓ Stopped api.app (gunicorn)" || true
# The old `trion_l0` module was removed long ago — the validator step in
# start_trion.sh is the one-shot Go self-test (go run ./cmd/trion-validator).
pkill -f "cmd/trion-validator" 2>/dev/null && log "✓ Stopped validator self-test" || true
pkill -f "run_bh_streamer" 2>/dev/null && log "✓ Stopped BH streamer" || true

log "All TRION services stopped"
