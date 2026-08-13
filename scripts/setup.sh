#!/usr/bin/env bash
# TRION Protocol — Replit Setup Script
# Run once after cloning/importing to install all Node.js dependencies across
# every subproject in the workspace.
#
# Python dependencies are managed via uv (pyproject.toml) and are installed
# automatically when the workflows start (via `uv run`).
#
# Usage:
#   bash scripts/setup.sh

set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$ROOT"

echo "========================================================"
echo " TRION Protocol — Dependency Setup"
echo "========================================================"

install_node() {
  local label="$1"
  local dir="$2"
  local flags="${3:-}"
  echo ""
  echo ">>> $label"
  cd "$ROOT/$dir" && npm install $flags
}

# ── Root workspace ────────────────────────────────────────
install_node "[1/11] root (ArbiLink agent + multi-chain adapters)" "." "--legacy-peer-deps"

# ── Unified relayers (2) ─────────────────────────────────
install_node "[2/11] relayer/ (EVM + non-EVM unified relayers)" "relayer"

# ── Per-VM chain executor scripts ─────────────────────────
install_node "[3/11] chains/svm/"      "chains/svm"
install_node "[4/11] chains/near/"     "chains/near"
install_node "[5/11] chains/ton/"      "chains/ton"
install_node "[6/11] chains/pvm/"      "chains/pvm"
install_node "[7/11] chains/starknet/" "chains/starknet"
install_node "[9/11] chains/sui/"      "chains/sui"

# ── 0G integration module ─────────────────────────────────
install_node "[10/11] trion-0g/ (0G storage / DA / compute)" "trion-0g" "--legacy-peer-deps"

# ── Backtest suite ────────────────────────────────────────
install_node "[11/11] backtest/" "backtest"

echo ""
echo "========================================================"
echo " All Node.js dependencies installed."
echo "========================================================"

# ── bh_ledger.db symlink ──────────────────────────────────
# The Oracle API and protocol segmentation module expect a root-level
# bh_ledger.db symlink pointing into akashic/.  serve.py also recreates
# it at startup, but creating it here ensures it survives container resets
# and is present before any workflow starts.
echo ""
echo ">>> Creating bh_ledger.db → akashic/bh_ledger.db symlink"
if [ ! -e "$ROOT/bh_ledger.db" ]; then
  ln -sf akashic/bh_ledger.db "$ROOT/bh_ledger.db"
  echo "    Created."
else
  echo "    Already exists — skipping."
fi

echo ""
echo "========================================================"
echo " Setup complete."
echo ""
echo " Next steps:"
echo "  1. Add Replit Secrets for your signing keys"
echo "     (see 'Secrets Required' section in replit.md)"
echo "  2. Start all workflows from the Replit Workflows panel:"
echo "     Start application → FAISS ANIMA → Rust Indexers →"
echo "     TRION Relayer → Extended Chain Relayer → Native Relayer →"
echo "     Attack Alert Webhook → Genesis Backfill"
echo "========================================================"
