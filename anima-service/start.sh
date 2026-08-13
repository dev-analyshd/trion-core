#!/bin/bash
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
cd "$SCRIPT_DIR"

# Render sets PORT; locally FAISS_PORT is used. Either works.
RESOLVED_PORT="${PORT:-${FAISS_PORT:-8000}}"
export FAISS_PORT="$RESOLVED_PORT"
export PORT="$RESOLVED_PORT"

echo "[FAISS] Starting TRION FAISS Intelligence Engine on port ${RESOLVED_PORT}..."

VENV_PYTHON="/home/runner/workspace/.venv/bin/python"
if [ -f "$VENV_PYTHON" ]; then
  PYTHON="$VENV_PYTHON"
else
  PYTHON="python3"
fi

# Start FAISS service in background
"$PYTHON" faiss_service.py &
FAISS_PID=$!

# Wait for FAISS to be healthy (up to 60s)
echo "[FAISS] Waiting for service to become healthy..."
for i in $(seq 1 60); do
  if curl -sf "http://127.0.0.1:${RESOLVED_PORT}/health" > /dev/null 2>&1; then
    echo "[FAISS] Service healthy — launching behavioral indexers..."
    break
  fi
  sleep 1
done

# ── Launch behavioral indexers ────────────────────────────────────────────────
WORKSPACE="/home/runner/workspace"
FAISS_URL="http://127.0.0.1:${RESOLVED_PORT}"

# SVM — Solana Devnet (chain_id 900)
if [ -d "$WORKSPACE/trion-svm/node_modules" ]; then
  FAISS_URL="$FAISS_URL" SVM_PRIVATE_KEY_B58="${SVM_PRIVATE_KEY_B58:-}" \
    pnpm --filter @workspace/trion-svm run dev >> /tmp/trion_svm_indexer.log 2>&1 &
  SVM_PID=$!
  echo "[SVM]  Indexer started (pid=$SVM_PID) — Solana Devnet → FAISS:${RESOLVED_PORT}"
else
  echo "[SVM]  Skipping — node_modules not found (run pnpm install)"
fi

# PVM — Polkadot Westend (chain_id 901)
if [ -d "$WORKSPACE/trion-pvm/node_modules" ]; then
  FAISS_URL="$FAISS_URL" pnpm --filter @workspace/trion-pvm run dev >> /tmp/trion_pvm_indexer.log 2>&1 &
  PVM_PID=$!
  echo "[PVM]  Indexer started (pid=$PVM_PID) — Polkadot Westend → FAISS:${RESOLVED_PORT}"
else
  echo "[PVM]  Skipping — node_modules not found (run pnpm install)"
fi

# TON — The Open Network (chain_id 1100)
if [ -d "$WORKSPACE/trion-ton/node_modules" ]; then
  FAISS_URL="$FAISS_URL" pnpm --filter @workspace/trion-ton run dev >> /tmp/trion_ton_indexer.log 2>&1 &
  TON_PID=$!
  echo "[TON]  Indexer started (pid=$TON_PID) — TON Mainnet → FAISS:${RESOLVED_PORT}"
else
  echo "[TON]  Skipping — node_modules not found (run pnpm install)"
fi

# NEAR — NEAR Protocol (chain_id 1201)
if [ -d "$WORKSPACE/trion-near/node_modules" ]; then
  FAISS_URL="$FAISS_URL" pnpm --filter @workspace/trion-near run dev >> /tmp/trion_near_indexer.log 2>&1 &
  NEAR_PID=$!
  echo "[NEAR] Indexer started (pid=$NEAR_PID) — NEAR Testnet → FAISS:${RESOLVED_PORT}"
else
  echo "[NEAR] Skipping — node_modules not found (run pnpm install)"
fi

# BNB — BNB Chain testnet (chain_id 97)
if [ -d "$WORKSPACE/trion-bnb/node_modules" ]; then
  FAISS_URL="$FAISS_URL" pnpm --filter @workspace/trion-bnb run dev >> /tmp/trion_bnb_indexer.log 2>&1 &
  BNB_PID=$!
  echo "[BNB]  Indexer started (pid=$BNB_PID) — BNB Testnet → FAISS:${RESOLVED_PORT}"
else
  echo "[BNB]  Skipping — node_modules not found (run pnpm install)"
fi

# Base — Base Sepolia (chain_id 84532)
if [ -d "$WORKSPACE/trion-base/node_modules" ]; then
  FAISS_URL="$FAISS_URL" pnpm --filter @workspace/trion-base run dev >> /tmp/trion_base_indexer.log 2>&1 &
  BASE_PID=$!
  echo "[BASE] Indexer started (pid=$BASE_PID) — Base Sepolia → FAISS:${RESOLVED_PORT}"
else
  echo "[BASE] Skipping — node_modules not found (run pnpm install)"
fi

echo ""
echo "[FAISS] All configured indexers launched."
echo "        Logs: /tmp/trion_{svm,pvm,ton,near,bnb,base}_indexer.log"
echo ""

# Wait for FAISS (main service) — if FAISS dies the workflow ends
wait $FAISS_PID
