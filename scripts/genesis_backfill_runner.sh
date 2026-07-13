#!/usr/bin/env bash
# TRION Genesis Backfill Runner — all integrated L1/L2s and VMs, from genesis,
# per whitepaper mandate. Thin wrapper so the workflow command stays stable;
# all chain logic lives in scripts/genesis_backfill_runner.py.
set -uo pipefail
cd "$(dirname "$0")/.."
export FAISS_SERVICE_URL="${FAISS_SERVICE_URL:-http://127.0.0.1:8000}"
exec python3 scripts/genesis_backfill_runner.py
