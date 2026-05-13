#!/bin/bash
# TRION Starknet — Build Cairo contracts and verify environment
# Run from starknet-trion/: bash scripts/build-and-verify.sh

set -e
cd "$(dirname "$0")/.."
ROOT=$(pwd)

echo "═══════════════════════════════════════════════════════════"
echo "   TRION × Starknet — Build & Verify                       "
echo "═══════════════════════════════════════════════════════════"

# 1. Compile Cairo contracts with Scarb
echo ""
echo "── Step 1: Compile Cairo contracts ──────────────────────"
SCARB_BIN="$ROOT/../.local/share/scarb-install/2.10.1/bin/scarb"
if [ ! -f "$SCARB_BIN" ]; then
  echo "  Installing Scarb v2.10.1..."
  curl -fsSL https://docs.swmansion.com/scarb/install.sh | bash -s -- -v 2.10.1
  SCARB_BIN="$ROOT/../.local/share/scarb-install/2.10.1/bin/scarb"
fi

SCARB_VER=$("$SCARB_BIN" --version 2>/dev/null || echo "unknown")
echo "  Scarb: $SCARB_VER"
"$SCARB_BIN" build
echo "  ✓ Cairo contracts compiled"

# 2. Check artifacts
echo ""
echo "── Step 2: Check compiled artifacts ────────────────────"
ls target/dev/*.json 2>/dev/null | while read f; do
  echo "  $f"
done

# 3. Run TypeScript verifier
echo ""
echo "── Step 3: Starknet environment verify ──────────────────"
export PATH="$HOME/.local/bin:$PATH"
pnpm verify

echo ""
echo "═══════════════════════════════════════════════════════════"
echo "   All steps complete!"
echo "   Next: pnpm deploy (needs STARKNET_PRIVATE_KEY secret)"
echo "═══════════════════════════════════════════════════════════"
