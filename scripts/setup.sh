#!/usr/bin/env bash
# TRION Protocol — Replit Setup Script
# Run once after cloning/importing to install all Node.js dependencies.
# Python dependencies are managed via uv (pyproject.toml) and are installed
# automatically when the workflows start.
#
# Usage:
#   bash scripts/setup.sh

set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$ROOT"

echo "========================================================"
echo " TRION Protocol — Dependency Setup"
echo "========================================================"

# ── Node.js: EVM relayer ──────────────────────────────────
echo ""
echo "[1/8] relayer/ (EVM + 0G relayer)"
cd "$ROOT/relayer" && npm install

# ── Node.js: Native VM relayer ────────────────────────────
echo ""
echo "[2/8] native-relayer/ (SVM / NEAR / TON / PVM / StarkNet)"
cd "$ROOT/native-relayer" && npm install

# ── Node.js: per-VM chain executor scripts ───────────────
echo ""
echo "[3/8] chains/svm/"
cd "$ROOT/chains/svm" && npm install

echo ""
echo "[4/8] chains/near/"
cd "$ROOT/chains/near" && npm install

echo ""
echo "[5/8] chains/ton/"
cd "$ROOT/chains/ton" && npm install

echo ""
echo "[6/8] chains/pvm/"
cd "$ROOT/chains/pvm" && npm install

echo ""
echo "[7/8] chains/starknet/"
cd "$ROOT/chains/starknet" && npm install

echo ""
echo "[8/8] chains/sui/"
cd "$ROOT/chains/sui" && npm install

echo ""
echo "========================================================"
echo " All Node.js dependencies installed."
echo ""
echo " Next: add Replit Secrets for your signing keys"
echo " (see 'Secrets Required' section in replit.md),"
echo " then start the workflows from the Workflows panel."
echo "========================================================"
