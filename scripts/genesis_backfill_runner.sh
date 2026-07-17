#!/usr/bin/env bash
# TRION Genesis Backfill Runner — all integrated L1/L2s and VMs, from genesis,
# per whitepaper mandate. Thin wrapper so the workflow command stays stable;
# all chain logic lives in scripts/genesis_backfill_runner.py.
set -uo pipefail
cd "$(dirname "$0")/.."
export FAISS_SERVICE_URL="${FAISS_SERVICE_URL:-http://127.0.0.1:8000}"

# Wait for FAISS to be reachable before starting — prevents flooding logs with
# connection errors on cold boot (matches pattern used by rust_indexers.sh).
echo "[BACKFILL] Waiting for FAISS service at ${FAISS_SERVICE_URL} ..."
FAISS_WAIT=0
until curl -sf "${FAISS_SERVICE_URL}/health" >/dev/null 2>&1; do
  sleep 2
  FAISS_WAIT=$((FAISS_WAIT + 2))
  if [ $FAISS_WAIT -ge 120 ]; then
    echo "[BACKFILL] FAISS not reachable after 120s — starting anyway"
    break
  fi
done
echo "[BACKFILL] FAISS reachable after ${FAISS_WAIT}s — starting backfill runner"

exec python3 scripts/genesis_backfill_runner.py
