#!/usr/bin/env bash
# TRION Protocol — 0G Services Supervisor
# Runs both 0G DA Streamer and 0G Sync Daemon under one supervisor.
# Both services use uv run to ensure full dependency access.

set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
LOG_DIR="/tmp/trion-zg-logs"
mkdir -p "$LOG_DIR"

cleanup() {
    echo "[0G-SUPERVISOR] Shutting down 0G services..."
    kill "$DA_PID" "$SYNC_PID" 2>/dev/null || true
    wait "$DA_PID" "$SYNC_PID" 2>/dev/null || true
    echo "[0G-SUPERVISOR] Done."
}
trap cleanup EXIT INT TERM

echo "[0G-SUPERVISOR] Starting 0G DA Streamer..."
uv run python3 "$ROOT/zg_da_streamer.py" >"$LOG_DIR/da_streamer.log" 2>&1 &
DA_PID=$!
echo "[0G-SUPERVISOR] DA Streamer PID: $DA_PID"

echo "[0G-SUPERVISOR] Starting 0G Sync Daemon..."
uv run python3 "$ROOT/zg_sync_daemon.py" >"$LOG_DIR/sync_daemon.log" 2>&1 &
SYNC_PID=$!
echo "[0G-SUPERVISOR] Sync Daemon PID: $SYNC_PID"

echo "[0G-SUPERVISOR] Both 0G services running. Logs: $LOG_DIR/"
echo "[0G-SUPERVISOR] DA=$DA_PID  SYNC=$SYNC_PID"

# Monitor both processes — restart on crash
while true; do
    sleep 30
    if ! kill -0 "$DA_PID" 2>/dev/null; then
        echo "[0G-SUPERVISOR] DA Streamer crashed — restarting..."
        uv run python3 "$ROOT/zg_da_streamer.py" >"$LOG_DIR/da_streamer.log" 2>&1 &
        DA_PID=$!
        echo "[0G-SUPERVISOR] DA Streamer restarted. PID: $DA_PID"
    fi
    if ! kill -0 "$SYNC_PID" 2>/dev/null; then
        echo "[0G-SUPERVISOR] Sync Daemon crashed — restarting..."
        uv run python3 "$ROOT/zg_sync_daemon.py" >"$LOG_DIR/sync_daemon.log" 2>&1 &
        SYNC_PID=$!
        echo "[0G-SUPERVISOR] Sync Daemon restarted. PID: $SYNC_PID"
    fi
done
