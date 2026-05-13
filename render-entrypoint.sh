#!/usr/bin/env bash
# =============================================================================
# trion-core — Render / Docker single-container entrypoint  (v3.0)
#
# Boots ALL 10 TRION services as background processes, then runs the Akashic
# Oracle in the foreground (PID 1 under tini) so Render's health check can
# probe http://localhost:$PORT/api/v1/health.
#
# Services:
#   1.  FAISS ANIMA Engine         Python  port 8000
#   2.  L0 EVM Indexer             Rust    background
#   3.  SVM Solana Indexer         Python  background
#   4.  EVM Extras Indexer         Node    supervisor  BNB/Base/HashKey
#   5.  Native VM Indexers         Node    supervisor  NEAR/TON/PVM/StarkNet
#   6.  Extended VM Indexers       Node    supervisor  UTXO/COSMOS/MOVE/SUI/TRON/PI
#   7.  EVM Relayer                Node    background  7 EVM chains
#   8.  Native VM Relayer          Node    background
#   9.  Extended Chain Relayer     Node    background  15 non-EVM chains
#  10.  Akashic Oracle             Rust    foreground  PID 1, port $PORT
#
# Each subsystem is independently toggleable via TRION_ENABLE_* (default: 1).
# Background crashes are restarted with exponential backoff — they never kill
# the container. Only the foreground Oracle binary propagates exit codes.
# =============================================================================
set -u

# ── Ports & URLs ─────────────────────────────────────────────────────────────
export PORT="${PORT:-10000}"
export FAISS_PORT="${FAISS_PORT:-8000}"
export FAISS_SERVICE_URL="${FAISS_SERVICE_URL:-http://127.0.0.1:${FAISS_PORT}}"
export FAISS_URL="${FAISS_URL:-http://127.0.0.1:${FAISS_PORT}}"
export ORACLE_API_URL="${ORACLE_API_URL:-http://127.0.0.1:${PORT}}"
export TRION_API_URL="${TRION_API_URL:-http://127.0.0.1:${PORT}}"
export ORACLE_PUBLIC_DIR="${ORACLE_PUBLIC_DIR:-/app/akashic-oracle/public}"

log() { echo "[entrypoint $(date +%H:%M:%S)] $*"; }

# Restart wrapper — keeps a service alive with exponential backoff (5s → 120s)
spawn() {
  local label="$1"; shift
  (
    local backoff=5
    while true; do
      log "starting $label"
      "$@" 2>&1 | sed -u "s/^/[$label] /"
      local code=$?
      log "$label exited (code $code), restart in ${backoff}s"
      sleep "$backoff"
      backoff=$(( backoff < 120 ? backoff * 2 : 120 ))
    done
  ) &
}

# ── 1. FAISS ANIMA Engine (Python, port 8000) ─────────────────────────────────
if [[ "${TRION_ENABLE_FAISS:-1}" == "1" ]]; then
  log "FAISS ANIMA on :${FAISS_PORT}"
  (
    cd /app/akashic
    OMP_NUM_THREADS=1 OPENBLAS_NUM_THREADS=1 MKL_NUM_THREADS=1 NUMEXPR_NUM_THREADS=1 \
    PORT="${FAISS_PORT}" FAISS_PORT="${FAISS_PORT}" \
    python3 faiss_service.py
  ) 2>&1 | sed -u "s/^/[faiss] /" &

  # Wait for FAISS to be reachable before launching dependents
  log "waiting for FAISS to become ready..."
  for i in $(seq 1 90); do
    curl -fs "http://127.0.0.1:${FAISS_PORT}/health" >/dev/null 2>&1 && \
      { log "FAISS ready after ${i}s"; break; }
    sleep 1
  done
fi

# ── 2. L0 EVM Indexer (Rust, Arbitrum mainnet) ────────────────────────────────
if [[ "${TRION_ENABLE_L0:-1}" == "1" ]]; then
  spawn "l0-evm" env \
    ARBITRUM_RPC_URL="${ARBITRUM_RPC_URL:-https://arb1.arbitrum.io/rpc}" \
    CHAIN_ID="${CHAIN_ID:-42161}" \
    FAISS_SERVICE_URL="${FAISS_SERVICE_URL}" \
    /app/bin/trion-l0
fi

# ── 3. SVM Solana Indexer (Python) ────────────────────────────────────────────
if [[ "${TRION_ENABLE_SVM:-1}" == "1" ]]; then
  spawn "svm" env \
    SOLANA_RPC_URL="${SOLANA_RPC_URL:-https://api.devnet.solana.com}" \
    SOLANA_CHAIN_ID="${SOLANA_CHAIN_ID:-103}" \
    SOLANA_LABEL="${SOLANA_LABEL:-SOLANA_DEVNET}" \
    POLL_SLEEP_MS="${POLL_SLEEP_MS:-1500}" \
    FAISS_SERVICE_URL="${FAISS_SERVICE_URL}" \
    python3 /app/trion-svm/svm_indexer.py
fi

# ── 4. EVM Extras Indexer (BNB Testnet / Base Sepolia / HashKey) ──────────────
if [[ "${TRION_ENABLE_EXTRAS:-1}" == "1" ]]; then
  spawn "evm-extras" bash /app/supervisors/evm_extras_indexers.sh
fi

# ── 5. Native VM Indexers (NEAR / TON / Polkadot / StarkNet) ─────────────────
if [[ "${TRION_ENABLE_NATIVE:-1}" == "1" ]]; then
  spawn "native-vm" bash /app/supervisors/native_vm_indexers.sh
fi

# ── 6. Extended VM Indexers (UTXO / COSMOS / MOVE / SUI / TRON / PI) ─────────
if [[ "${TRION_ENABLE_EXTENDED:-1}" == "1" ]]; then
  spawn "ext-vm" bash /app/supervisors/extended_vm_indexers.sh
fi

# ── 7. EVM Relayer (publishes C(t) on 7 EVM chains every 60s) ─────────────────
if [[ "${TRION_ENABLE_RELAYER:-1}" == "1" ]]; then
  spawn "evm-relayer" env \
    ORACLE_API_URL="${ORACLE_API_URL}" \
    POLL_INTERVAL_MS="${POLL_INTERVAL_MS:-60000}" \
    node /app/relayer/relayer.js
fi

# ── 8. Native VM Relayer (NEAR / TON / Polkadot / StarkNet signed txs) ────────
if [[ "${TRION_ENABLE_NATIVE:-1}" == "1" ]]; then
  spawn "native-relayer" env \
    ORACLE_API_URL="${ORACLE_API_URL}" \
    node /app/native-relayer/native_relayer.js
fi

# ── 9. Extended Chain Relayer (15 non-EVM chains every 90s) ──────────────────
if [[ "${TRION_ENABLE_EXT_RELAYER:-1}" == "1" ]]; then
  spawn "ext-relayer" env \
    ORACLE_API_URL="${ORACLE_API_URL}" \
    EXTENDED_POLL_INTERVAL_MS="${EXTENDED_POLL_INTERVAL_MS:-90000}" \
    node /app/relayer/extended_chain_relayer.js
fi

# ── 10. Akashic Oracle (Rust, foreground — PID 1 under tini) ─────────────────
log "Akashic Oracle on :${PORT} (foreground PID 1)"
exec /app/bin/akashic-oracle
