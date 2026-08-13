#!/usr/bin/env bash
# TRION Protocol — Unified Relayer Supervisor
# Manages exactly 2 relayers:
#   1. relayer.js          — EVM (63+ chains including 0G ExecutionGate)
#   2. relayer_non_evm.js  — Non-EVM (SVM/NEAR/TON/PVM/StarkNet + 32 extended chains)
# Plus 0G DA streamer + 0G sync daemon.

set -euo pipefail

ROOT="$(cd "$(dirname "$0")/.." && pwd)"
ORACLE_API_URL="${ORACLE_API_URL:-http://127.0.0.1:5000}"
FAISS_URL="${FAISS_URL:-http://127.0.0.1:8000}"
POLL_INTERVAL_MS="${POLL_INTERVAL_MS:-60000}"
EXTENDED_POLL_INTERVAL_MS="${EXTENDED_POLL_INTERVAL_MS:-90000}"
NATIVE_CYCLE_SLEEP_MS="${NATIVE_CYCLE_SLEEP_MS:-600000}"
ZG_EXECUTION_GATE_ADDR="${ZG_EXECUTION_GATE_ADDR:-0xA85B49C73B5710d9ddB1CB5a94c52D0F33c4199b}"
ZG_CHAIN_ID="${ZG_CHAIN_ID:-16661}"
ZERO_G_RPC="${ZERO_G_RPC:-https://evmrpc.0g.ai}"
LOG_DIR="${LOG_DIR:-/tmp/trion-relayer-logs}"
mkdir -p "$LOG_DIR"

echo "======================================================"
echo " TRION Protocol — Unified Relayer Supervisor"
echo "======================================================"
echo " 1. EVM Relayer     : ${ORACLE_API_URL} (63+ chains)"
echo " 2. Non-EVM Relayer : ${FAISS_URL} (38 chains)"
echo " 0G Gate            : ${ZG_EXECUTION_GATE_ADDR}"
echo " Logs               : ${LOG_DIR}/"
echo ""

restart_process() {
    local name="$1"; shift
    local logfile="$LOG_DIR/${name}.log"
    echo "[$(date -u +%H:%M:%S)] Starting [$name]"
    while true;
        "$@" >> "$logfile" 2>&1 || true
        echo "[$(date -u +%H:%M:%S)] [$name] exited — restarting in 10s"
        sleep 10
    done
}

pids=()

# ── 1. EVM Relayer (includes 0G ExecutionGate) ────────────────────────────────
restart_process "evm-relayer" \
    env ORACLE_API_URL="$ORACLE_API_URL" \
        POLL_INTERVAL_MS="$POLL_INTERVAL_MS" \
        ZG_EXECUTION_GATE_ADDR="$ZG_EXECUTION_GATE_ADDR" \
        ZG_CHAIN_ID="$ZG_CHAIN_ID" \
        ZERO_G_RPC="$ZERO_G_RPC" \
    node "$ROOT/relayer/relayer.js" &
pids+=($!)

# ── 2. Non-EVM Relayer (SVM/NEAR/TON/PVM/StarkNet + 32 extended) ──────────────
restart_process "non-evm-relayer" \
    env ORACLE_API_URL="$ORACLE_API_URL" \
        FAISS_URL="$FAISS_URL" \
        EXTENDED_POLL_INTERVAL_MS="$EXTENDED_POLL_INTERVAL_MS" \
        NATIVE_CYCLE_SLEEP_MS="$NATIVE_CYCLE_SLEEP_MS" \
    node "$ROOT/relayer/relayer_non_evm.js" &
pids+=($!)

# ── 3. 0G DA Streamer ─────────────────────────────────────────────────────────
if [[ "${TRION_ENABLE_ZG_DA:-1}" == "1" ]]; then
    restart_process "zg-da-streamer" \
        env FAISS_SERVICE_URL="$FAISS_URL" \
        ORACLE_API_URL="$ORACLE_API_URL" \
        ZG_CHAIN_ID="$ZG_CHAIN_ID" \
            "$ROOT/.venv/bin/python3" "$ROOT/zg_da_streamer.py" &
    pids+=($!)
fi

# ── 4. 0G Storage Sync Daemon ─────────────────────────────────────────────────
if [[ "${TRION_ENABLE_ZG_SYNC:-1}" == "1" ]]; then
    restart_process "zg-sync-daemon" \
        env FAISS_SERVICE_URL="$FAISS_URL" \
        ORACLE_API_URL="$ORACLE_API_URL" \
        ZG_EXECUTION_GATE_ADDR="$ZG_EXECUTION_GATE_ADDR" \
            "$ROOT/.venv/bin/python3" "$ROOT/zg_sync_daemon.py" &
    pids+=($!)
fi

echo "[$(date -u +%H:%M:%S)] All relayers started. PIDs: ${pids[*]}"
echo "[$(date -u +%H:%M:%S)] Logs: $LOG_DIR/"

trap 'echo "[$(date -u +%H:%M:%S)] Shutting down..."; kill ${pids[*]} 2>/dev/null; exit 0' SIGTERM SIGINT

wait "${pids[@]}"
