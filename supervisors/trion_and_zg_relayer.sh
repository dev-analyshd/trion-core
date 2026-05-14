#!/usr/bin/env bash
# TRION Protocol — Multi-Chain Relayer + 0G Full Stack Supervisor
# Manages: TRION Relayer, 0G ExecutionGate Relayer, 0G DA Streamer, 0G Sync Daemon
# Oracle API (Flask, port 5000) is started separately by the "Start application" workflow.

set -euo pipefail

ROOT="$(cd "$(dirname "$0")/.." && pwd)"
ORACLE_API_URL="${ORACLE_API_URL:-http://127.0.0.1:5000}"
POLL_INTERVAL_MS="${POLL_INTERVAL_MS:-60000}"
ZG_EXECUTION_GATE_ADDR="${ZG_EXECUTION_GATE_ADDR:-0xDB5910Dc6CfD219D00F64be1F23DA0289901356d}"
ZG_POLL_INTERVAL_MS="${ZG_POLL_INTERVAL_MS:-120000}"
ZG_CHAIN_ID="${ZG_CHAIN_ID:-16602}"
ZERO_G_RPC="${ZERO_G_RPC:-https://evmrpc-testnet.0g.ai}"
LOG_DIR="${LOG_DIR:-/tmp/trion-relayer-logs}"
mkdir -p "$LOG_DIR"

echo "======================================================"
echo " TRION Protocol — Full Relayer + 0G Stack"
echo "======================================================"
echo " TRION Relayer    : ORACLE_API_URL=${ORACLE_API_URL}"
echo " 0G Gate          : ${ZG_EXECUTION_GATE_ADDR}"
echo " 0G Chain         : ${ZG_CHAIN_ID}"
echo " 0G RPC           : ${ZERO_G_RPC}"
echo " Logs             : ${LOG_DIR}/"
echo ""

# ---------------------------------------------------------------------------
# TRION multi-chain relayer
# ---------------------------------------------------------------------------
run_trion_relayer() {
  while true; do
    echo "[TRION-RELAYER] Starting ..."
    ORACLE_API_URL="$ORACLE_API_URL" \
    POLL_INTERVAL_MS="$POLL_INTERVAL_MS" \
      node relayer/relayer.js 2>&1 | sed 's/^/[trion] /' || true
    echo "[TRION-RELAYER] Exited — restarting in 10s ..."
    sleep 10
  done
}

# ---------------------------------------------------------------------------
# 0G ExecutionGate on-chain relayer
# ---------------------------------------------------------------------------
run_zg_relayer() {
  while true; do
    echo "[0G-GATE-RELAYER] Starting ..."
    ZG_EXECUTION_GATE_ADDR="$ZG_EXECUTION_GATE_ADDR" \
    ORACLE_API_URL="$ORACLE_API_URL" \
    ZG_POLL_INTERVAL_MS="$ZG_POLL_INTERVAL_MS" \
    ZG_CHAIN_ID="$ZG_CHAIN_ID" \
    ZERO_G_RPC="$ZERO_G_RPC" \
      node relayer/zg_execution_gate_relayer.js 2>&1 | sed 's/^/[0g-gate] /' || true
    echo "[0G-GATE-RELAYER] Exited — restarting in 10s ..."
    sleep 10
  done
}

# ---------------------------------------------------------------------------
# 0G DA Streamer (submits behavioral blobs to 0G DA every minute)
# ---------------------------------------------------------------------------
run_zg_da_streamer() {
  while true; do
    echo "[0G-DA-STREAMER] Starting ..."
    uv run python3 "$ROOT/zg_da_streamer.py" 2>&1 | sed 's/^/[0g-da] /' || true
    echo "[0G-DA-STREAMER] Exited — restarting in 30s ..."
    sleep 30
  done
}

# ---------------------------------------------------------------------------
# 0G Sync Daemon (uploads FAISS delta vectors to 0G Storage hourly)
# ---------------------------------------------------------------------------
run_zg_sync_daemon() {
  while true; do
    echo "[0G-SYNC-DAEMON] Starting ..."
    uv run python3 "$ROOT/zg_sync_daemon.py" 2>&1 | sed 's/^/[0g-sync] /' || true
    echo "[0G-SYNC-DAEMON] Exited — restarting in 60s ..."
    sleep 60
  done
}

# ---------------------------------------------------------------------------
# Dashboard state sync (copies relayer JSON to public dir every 30s)
# ---------------------------------------------------------------------------
sync_zg_state() {
  local PUBLIC_DIR="${ORACLE_PUBLIC_DIR:-./akashic-oracle/public}"
  while true; do
    sleep 30
    if [ -f "/tmp/trion_zg_gate_relayer.json" ]; then
      cp /tmp/trion_zg_gate_relayer.json "${PUBLIC_DIR}/zg_gate_state.json" 2>/dev/null || true
    fi
  done
}

# ---------------------------------------------------------------------------
# 0G Storage auto-sync (uploads FAISS index to 0G Storage every 30 min)
# ---------------------------------------------------------------------------
run_zg_storage_sync() {
  echo "[0G-STORAGE-SYNC] Auto-sync loop started (interval: 30m)"
  sleep 120
  while true; do
    echo "[0G-STORAGE-SYNC] Running zg_storage_sync.mjs ..."
    ZG_EXECUTION_GATE_ADDR="${ZG_EXECUTION_GATE_ADDR}" \
    ZG_CHAIN_ID="${ZG_CHAIN_ID}" \
    ZERO_G_RPC="${ZERO_G_RPC}" \
      node --experimental-vm-modules "${ROOT}/scripts/zg_storage_sync.mjs" 2>&1 | sed 's/^/[zg-sync] /' || \
    ( cd "${ROOT}/relayer" && \
      ZG_EXECUTION_GATE_ADDR="${ZG_EXECUTION_GATE_ADDR}" \
      ZG_CHAIN_ID="${ZG_CHAIN_ID}" \
      ZERO_G_RPC="${ZERO_G_RPC}" \
        node "${ROOT}/scripts/zg_storage_sync.mjs" 2>&1 | sed 's/^/[zg-sync] /' || true )
    echo "[0G-STORAGE-SYNC] Done — next sync in 30m"
    sleep 1800
  done
}

# ---------------------------------------------------------------------------
# Launch all services
# ---------------------------------------------------------------------------
run_trion_relayer &
TRION_PID=$!

run_zg_relayer &
ZG_GATE_PID=$!

run_zg_da_streamer &
ZG_DA_PID=$!

run_zg_sync_daemon &
ZG_SYNC_PID=$!

sync_zg_state &
STATE_SYNC_PID=$!

run_zg_storage_sync &
ZG_STORAGE_PID=$!

echo "[SUPERVISOR] All services started."
echo "[SUPERVISOR] PIDs: TRION=${TRION_PID}  0G-Gate=${ZG_GATE_PID}  DA=${ZG_DA_PID}  Sync=${ZG_SYNC_PID}  Storage=${ZG_STORAGE_PID}"

trap "kill $TRION_PID $ZG_GATE_PID $ZG_DA_PID $ZG_SYNC_PID $STATE_SYNC_PID $ZG_STORAGE_PID 2>/dev/null; exit 0" SIGTERM SIGINT

wait
