#!/usr/bin/env bash
# TRION Protocol — Unified Relayer Supervisor
# Manages exactly 2 relayers:
#   1. relayer.js          — EVM (60 chains including 0G ExecutionGate)
#   2. relayer_non_evm.js  — Non-EVM (SVM/NEAR/TON/PVM/StarkNet + extended — 36 chains)
# Plus 0G DA streamer + 0G sync daemon (both optional, default ON — set
# TRION_ENABLE_ZG_DA=0 / TRION_ENABLE_ZG_SYNC=0 to disable when the parent
# entrypoint already supervises them itself, e.g. render-entrypoint.sh).
#
# SIGNING CUSTODY (master command §17):
#   relayer.js signs EVM txs via relayer/kms_provider.js:
#     KMS_PROVIDER=env (default)      → RELAYER_PRIVATE_KEY, DEV/TESTNET ONLY
#     KMS_PROVIDER=aws|gcp|yubihsm|pkcs11 → production KMS/HSM signing
#   relayer_non_evm.js has NO KMS path yet — its per-VM keys are env-only
#   (each VM is skipped/block-proof mode when its key is unset).
#   This supervisor REFUSES to start under TRION_ENV=production with any raw
#   env key set unless TRION_ALLOW_RAW_ENV_KEYS=1 acknowledges custody
#   (see DEPLOYMENT.md "Signing and key custody").

set -euo pipefail

# ── Signing-custody guard (master command §17) ────────────────────────────
if [ "${TRION_ENV:-development}" = "production" ] \
   && [ "${TRION_ALLOW_RAW_ENV_KEYS:-0}" != "1" ]; then
    for _key_var in RELAYER_PRIVATE_KEY ZG_PRIVATE_KEY DEPLOY_0G_PRIVATE \
                    DEPLOYER_PRIVATE_KEY SOLANA_RELAYER_PRIVATE_KEY \
                    SVM_PRIVATE_KEY_B58 NEAR_RELAYER_PRIVATE_KEY NEAR_PRIVATE_KEY \
                    TON_RELAYER_PRIVATE_KEY TON_PRIVATE_KEY_HEX \
                    PVM_RELAYER_MNEMONIC DOT_MNEMONIC \
                    STARKNET_RELAYER_PRIVATE_KEY STARKNET_PRIVATE_KEY \
                    BOT_CHAIN_PRIVATE_KEY BOT_CHAIN_RELAYER_PRIVATE_KEY; do
        if [ -n "$(eval "printf '%s' \"\${${_key_var}:-}\"")" ]; then
            echo "FATAL: TRION_ENV=production but raw env private key ${_key_var} is set." >&2
            echo "       Env keys are DEV/TESTNET-ONLY. EVM signing has a KMS/HSM path" >&2
            echo "       (KMS_PROVIDER=aws|gcp|yubihsm|pkcs11 — relayer/kms_provider.js);" >&2
            echo "       non-EVM relayers have no KMS path yet — either leave their keys" >&2
            echo "       unset (block-proof/read-only mode) or set TRION_ALLOW_RAW_ENV_KEYS=1" >&2
            echo "       to acknowledge documented env-secret custody." >&2
            exit 1
        fi
    done
fi

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

# Python for the 0G daemons: prefer the repo venv when it exists (local dev),
# fall back to PATH python3 (the render image has no .venv — its python3 is
# the system interpreter with all deps installed).
if [[ -n "${TRION_PYTHON:-}" ]]; then
    ZG_PY="${TRION_PYTHON}"
elif [[ -x "${ROOT}/.venv/bin/python3" ]]; then
    ZG_PY="${ROOT}/.venv/bin/python3"
else
    ZG_PY="python3"
fi

echo "======================================================"
echo " TRION Protocol — Unified Relayer Supervisor"
echo "======================================================"
echo " 1. EVM Relayer     : ${ORACLE_API_URL} (60 chains; KMS_PROVIDER=${KMS_PROVIDER:-env})"
echo " 2. Non-EVM Relayer : ${FAISS_URL} (36 chains)"
echo " 0G Gate            : ${ZG_EXECUTION_GATE_ADDR}"
echo " Logs               : ${LOG_DIR}/"
echo ""

restart_process() {
    local name="$1"; shift
    local logfile="$LOG_DIR/${name}.log"
    echo "[$(date -u +%H:%M:%S)] Starting [$name]"
    # (fix: the original `while true;` was missing its `do` — bash refused to
    # parse this file at all, so the whole relayer supervisor was dead-on-
    # arrival wherever it was spawned)
    while true; do
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

# ── 2. Non-EVM Relayer (SVM/NEAR/TON/PVM/StarkNet + 30 extended) ─────────────
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
            "$ZG_PY" "$ROOT/zg/zg_da_streamer.py" &
    pids+=($!)
fi

# ── 4. 0G Storage Sync Daemon ─────────────────────────────────────────────────
if [[ "${TRION_ENABLE_ZG_SYNC:-1}" == "1" ]]; then
    restart_process "zg-sync-daemon" \
        env FAISS_SERVICE_URL="$FAISS_URL" \
        ORACLE_API_URL="$ORACLE_API_URL" \
        ZG_EXECUTION_GATE_ADDR="$ZG_EXECUTION_GATE_ADDR" \
            "$ZG_PY" "$ROOT/zg/zg_sync_daemon.py" &
    pids+=($!)
fi

echo "[$(date -u +%H:%M:%S)] All relayers started. PIDs: ${pids[*]}"
echo "[$(date -u +%H:%M:%S)] Logs: $LOG_DIR/"

trap 'echo "[$(date -u +%H:%M:%S)] Shutting down..."; kill ${pids[*]} 2>/dev/null; exit 0' SIGTERM SIGINT

wait "${pids[@]}"
