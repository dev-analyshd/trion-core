#!/usr/bin/env bash
# TRION Genesis Backfill Runner — sequential, resumable, per whitepaper mandate.
# Order: Ethereum mainnet -> Solana mainnet -> Arbitrum mainnet.
# Each stage is checkpointed independently (genesis_backfill_checkpoint_*.json)
# so re-running this script picks up where it left off rather than restarting.
set -uo pipefail
cd "$(dirname "$0")/.."

export FAISS_SERVICE_URL="${FAISS_SERVICE_URL:-http://127.0.0.1:8000}"

echo "════════════════════════════════════════════════════════════════"
echo " TRION Genesis Backfill Runner — $(date -u)"
echo " Sequence: eth-mainnet -> sol-mainnet -> arb-mainnet"
echo "════════════════════════════════════════════════════════════════"

echo ""
echo ">>> [1/3] Ethereum mainnet — genesis to tip"
python3 akashic/genesis_backfill.py \
  --start-block 0 --end-block latest \
  --rpc https://ethereum-rpc.publicnode.com \
  --chain-name eth-mainnet --chain-id 1

echo ""
echo ">>> [2/3] Solana mainnet — genesis to tip"
python3 akashic/genesis_backfill_solana.py \
  --start-slot 0 --end-slot latest

echo ""
echo ">>> [3/3] Arbitrum mainnet — genesis to tip"
python3 akashic/genesis_backfill.py \
  --start-block 0 --end-block latest \
  --rpc https://arb1.arbitrum.io/rpc \
  --chain-name arb-mainnet --chain-id 42161

echo ""
echo "════════════════════════════════════════════════════════════════"
echo " All three chains reached tip. Restarting from each chain's"
echo " checkpoint to pick up new blocks produced since backfill began."
echo "════════════════════════════════════════════════════════════════"

# Once all three chains have caught up to their tip at least once, keep
# looping so newly produced blocks/slots keep landing — the live Rust
# indexers and relayers already do this going forward, but this loop
# keeps this script's own checkpoints current too.
while true; do
  python3 akashic/genesis_backfill.py --start-block 0 --end-block latest \
    --rpc https://ethereum-rpc.publicnode.com --chain-name eth-mainnet --chain-id 1
  python3 akashic/genesis_backfill_solana.py --start-slot 0 --end-slot latest
  python3 akashic/genesis_backfill.py --start-block 0 --end-block latest \
    --rpc https://arb1.arbitrum.io/rpc --chain-name arb-mainnet --chain-id 42161
  sleep 60
done
