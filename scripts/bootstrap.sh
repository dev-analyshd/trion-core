#!/usr/bin/env bash
# scripts/bootstrap.sh
# ---------------------
# Installs all Node.js dependencies required by TRION's relayer and chain
# subdirectories, and creates the bh_ledger.db symlink expected by the Oracle API.
# Safe to run multiple times (npm install is idempotent).
#
# Usage: bash scripts/bootstrap.sh

set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$ROOT"

echo "=== TRION Bootstrap ==="

# ── Node packages ──────────────────────────────────────────────────────────────

declare -a NPM_DIRS=(
  "relayer"
  "chains/svm"
  "chains/near"
  "chains/ton"
  "chains/pvm"
  "chains/starknet"
  "chains/sui"
  "chains/botchain"
  "trion-0g"
)

for dir in "${NPM_DIRS[@]}"; do
  if [ -f "$ROOT/$dir/package.json" ]; then
    echo "  npm install — $dir"
    (cd "$ROOT/$dir" && npm install --legacy-peer-deps --silent) \
      && echo "    ✓ $dir" \
      || echo "    ✗ $dir (check npm logs)"
  else
    echo "  SKIP $dir — no package.json"
  fi
done

# ── bh_ledger.db symlink ───────────────────────────────────────────────────────
# FAISS ANIMA writes the DB to anima-service/bh_ledger.db; the Oracle API (via
# src/protocol/segmentation.py) looks for it at the workspace root.
BH_SRC="anima-service/bh_ledger.db"
BH_LINK="bh_ledger.db"

if [ ! -e "$ROOT/$BH_LINK" ]; then
  ln -sf "$BH_SRC" "$ROOT/$BH_LINK"
  echo "  ✓ symlink created: $BH_LINK → $BH_SRC"
else
  echo "  ✓ symlink already present: $BH_LINK"
fi

echo "=== Bootstrap complete ==="
