#!/usr/bin/env bash
# Multi-Chain Relayer + 0G ExecutionGate Relayer Supervisor
# Oracle API (Flask, port 5000) is started separately by the "Start application" workflow.

set -euo pipefail

ROOT="$(cd "$(dirname "$0")/.." && pwd)"
ORACLE_API_URL="${ORACLE_API_URL:-http://127.0.0.1:5000}"
POLL_INTERVAL_MS="${POLL_INTERVAL_MS:-60000}"
ZG_EXECUTION_GATE_ADDR="${ZG_EXECUTION_GATE_ADDR:-0xDB5910Dc6CfD219D00F64be1F23DA0289901356d}"
ZG_POLL_INTERVAL_MS="${ZG_POLL_INTERVAL_MS:-120000}"
ZG_CHAIN_ID="${ZG_CHAIN_ID:-16602}"
ZERO_G_RPC="${ZERO_G_RPC:-https://evmrpc-testnet.0g.ai}"

echo "======================================================"
echo " TRION Relayer + 0G ExecutionGate"
echo "======================================================"
echo " TRION Relayer    : ORACLE_API_URL=${ORACLE_API_URL}"
echo " 0G Gate          : ${ZG_EXECUTION_GATE_ADDR}"
echo " 0G Chain         : ${ZG_CHAIN_ID}"
echo " 0G RPC           : ${ZERO_G_RPC}"
echo ""

run_trion_relayer() {
  while true; do
    echo "[TRION-RELAYER] Starting …"
    ORACLE_API_URL="$ORACLE_API_URL" \
    POLL_INTERVAL_MS="$POLL_INTERVAL_MS" \
      node relayer/relayer.js 2>&1 | sed 's/^/[trion] /' || true
    echo "[TRION-RELAYER] Exited — restarting in 10s …"
    sleep 10
  done
}

run_zg_relayer() {
  while true; do
    echo "[0G-GATE-RELAYER] Starting …"
    ZG_EXECUTION_GATE_ADDR="$ZG_EXECUTION_GATE_ADDR" \
    ORACLE_API_URL="$ORACLE_API_URL" \
    ZG_POLL_INTERVAL_MS="$ZG_POLL_INTERVAL_MS" \
    ZG_CHAIN_ID="$ZG_CHAIN_ID" \
    ZERO_G_RPC="$ZERO_G_RPC" \
      node relayer/zg_execution_gate_relayer.js 2>&1 | sed 's/^/[0g-gate] /' || true
    echo "[0G-GATE-RELAYER] Exited — restarting in 10s …"
    sleep 10
  done
}

run_trion_relayer &
TRION_PID=$!

run_zg_relayer &
ZG_PID=$!

echo "PIDs: TRION=${TRION_PID}  0G-Gate=${ZG_PID}"


# Sync ZG relayer state to public dir every 30s so the dashboard can read it
sync_zg_state() {
  local PUBLIC_DIR="${ORACLE_PUBLIC_DIR:-./akashic-oracle/public}"
  while true; do
    sleep 30
    if [ -f "/tmp/trion_zg_gate_relayer.json" ]; then
      cp /tmp/trion_zg_gate_relayer.json "${PUBLIC_DIR}/zg_gate_state.json" 2>/dev/null || true
    fi
  done
}
sync_zg_state &
SYNC_PID=$!

# Auto-sync FAISS index to 0G Storage every 30 minutes (best-effort, dry-run
# unless RELAYER_PRIVATE_KEY is set with funded wallet)
run_zg_storage_sync() {
  echo "[0G-STORAGE-SYNC] Auto-sync loop started (interval: 30m)"
  # Initial delay to let FAISS accumulate vectors before first sync
  sleep 120
  while true; do
    echo "[0G-STORAGE-SYNC] Running zg_storage_sync.mjs …"
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
run_zg_storage_sync &
ZG_STORAGE_PID=$!

trap "kill $TRION_PID $ZG_PID $SYNC_PID $ZG_STORAGE_PID 2>/dev/null; exit 0" SIGTERM SIGINT

wait
