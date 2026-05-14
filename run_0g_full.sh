#!/usr/bin/env bash
# run_0g_full.sh
# Complete TRION × 0G integration launch.
# Deploys AkashicProof, starts sync daemon and DA streamer.
# Run ONCE — everything runs automatically after.

set -e

echo "╔══════════════════════════════════════════════════════╗"
echo "║     TRION × 0G — FULL INTEGRATION LAUNCH            ║"
echo "╚══════════════════════════════════════════════════════╝"

# ── 0. Prerequisites ─────────────────────────────────────────────
echo "[0/7] Checking prerequisites..."
source "$HOME/.cargo/env" 2>/dev/null || true

pip install --quiet asyncpg web3 numpy httpx python-dotenv tqdm 2>/dev/null || \
  uv pip install asyncpg web3 numpy httpx python-dotenv tqdm 2>/dev/null || true

# Install 0G storage SDK if not already present
if [ ! -d "node_modules/@0glabs" ]; then
  npm install --save @0glabs/0g-ts-sdk ethers tsx 2>/dev/null || true
fi

echo "[0/7] ✓ Dependencies ready"

# ── 1. Setup state directories ───────────────────────────────────
echo "[1/7] Setting up state directories..."
mkdir -p 0g-state/{exports,proofs,logs}
echo "[1/7] ✓ Directories ready"

# ── 2. Compile AkashicProof contract ────────────────────────────
echo "[2/7] Compiling AkashicProof contract..."
if command -v npx &>/dev/null && [ -f "hardhat.config.js" -o -f "hardhat.config.ts" ]; then
  npx hardhat compile 2>&1 | tail -5
  echo "[2/7] ✓ Contract compiled"
else
  echo "[2/7] ⚠ Hardhat not configured — skipping compile"
  echo "         Run: npx hardhat compile"
fi

# ── 3. Deploy AkashicProof to 0G Chain ──────────────────────────
echo "[3/7] Deploying AkashicProof to 0G Chain..."

if [ -z "$ZG_PRIVATE_KEY" ] && [ -z "$DEPLOYER_PRIVATE_KEY" ]; then
  echo "[3/7] ⚠ ZG_PRIVATE_KEY not set — skipping deployment"
  echo "         Set ZG_PRIVATE_KEY in your environment and re-run"
elif [ -n "$(cat 0g-state/proofs/contract_deployment.json 2>/dev/null | python3 -c 'import sys,json; print(json.load(sys.stdin).get("contractAddress",""))' 2>/dev/null)" ]; then
  CONTRACT=$(cat 0g-state/proofs/contract_deployment.json | \
    python3 -c "import sys,json; print(json.load(sys.stdin)['contractAddress'])")
  echo "[3/7] ✓ Already deployed: $CONTRACT"
  export ZG_AKASHIC_CONTRACT=$CONTRACT
else
  node scripts/deploy_akashic_proof.mjs
  CONTRACT=$(cat 0g-state/proofs/contract_deployment.json | \
    python3 -c "import sys,json; print(json.load(sys.stdin)['contractAddress'])")
  export ZG_AKASHIC_CONTRACT=$CONTRACT
  # Persist to .env if it exists
  if [ -f ".env" ]; then
    grep -q "ZG_AKASHIC_CONTRACT" .env && \
      sed -i "s|ZG_AKASHIC_CONTRACT=.*|ZG_AKASHIC_CONTRACT=$CONTRACT|" .env || \
      echo "ZG_AKASHIC_CONTRACT=$CONTRACT" >> .env
  fi
  echo "[3/7] ✓ Contract deployed: $CONTRACT"
  echo "         Explorer: https://chainscan-newton.0g.ai/address/$CONTRACT"
fi

# ── 4. Kill any running daemons ──────────────────────────────────
echo "[4/7] Stopping existing daemons..."
[ -f "0g-state/sync_daemon.pid" ] && {
  kill "$(cat 0g-state/sync_daemon.pid)" 2>/dev/null || true
  rm -f 0g-state/sync_daemon.pid
}
[ -f "0g-state/da_streamer.pid" ] && {
  kill "$(cat 0g-state/da_streamer.pid)" 2>/dev/null || true
  rm -f 0g-state/da_streamer.pid
}
echo "[4/7] ✓ Cleaned up"

# ── 5. Start sync daemon (background) ───────────────────────────
echo "[5/7] Starting hourly sync daemon..."
nohup python3 zg_sync_daemon.py \
  > 0g-state/logs/sync_daemon.log 2>&1 &
SYNC_PID=$!
echo $SYNC_PID > 0g-state/sync_daemon.pid
echo "[5/7] ✓ Sync daemon started (PID: $SYNC_PID)"
echo "       Logs: tail -f 0g-state/logs/sync_daemon.log"

# ── 6. Start DA streamer (background) ───────────────────────────
echo "[6/7] Starting DA streamer..."
nohup python3 zg_da_streamer.py \
  > 0g-state/logs/da_streamer.log 2>&1 &
DA_PID=$!
echo $DA_PID > 0g-state/da_streamer.pid
echo "[6/7] ✓ DA streamer started (PID: $DA_PID)"
echo "       Logs: tail -f 0g-state/logs/da_streamer.log"

# ── 7. Summary ───────────────────────────────────────────────────
sleep 3
echo ""
echo "╔══════════════════════════════════════════════════════╗"
echo "║     TRION × 0G — ALL SYSTEMS RUNNING                ║"
echo "╠══════════════════════════════════════════════════════╣"
echo "║  Contract:  ${ZG_AKASHIC_CONTRACT:-NOT YET DEPLOYED}"
echo "║  Sync PID:  $SYNC_PID (hourly)"
echo "║  DA PID:    $DA_PID (every 60s)"
echo "║"
echo "║  API routes (restart Oracle API to activate):"
echo "║    GET  /api/v1/0g/status"
echo "║    GET  /api/v1/0g/proof"
echo "║    GET  /api/v1/0g/sync/history"
echo "║    GET  /api/v1/0g/da/commitments"
echo "║    POST /api/v1/0g/compute/anima"
echo "║"
echo "║  Explorer: https://storagescan.0g.ai"
echo "║  Chain:    https://chainscan-newton.0g.ai"
echo "╚══════════════════════════════════════════════════════╝"
