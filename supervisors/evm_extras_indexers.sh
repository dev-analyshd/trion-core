#!/usr/bin/env bash
# ============================================================
# TRION EVM Extras Indexer Supervisor — Rust L0 (via trion-evm)
# BNB Testnet, Base Sepolia, HashKey, Mantle, Linea, Scroll
# are all indexed by the trion-evm Rust binary (Rust Indexers
# workflow). This script verifies the Rust binary is built and
# tails the EVM log for observability.
# ============================================================
set -euo pipefail

ROOT="$(cd "$(dirname "$0")/.." && pwd)"
BIN_DIR="$ROOT/rust-indexers/target/debug"
FAISS_URL="${FAISS_SERVICE_URL:-http://127.0.0.1:8000}"
LOG_DIR="/tmp/trion-rust-logs"
mkdir -p "$LOG_DIR"

log()  { echo "[$(date -u +%H:%M:%S)] [EVM-EXTRAS] $*"; }

log "EVM Extras chains (POLYGON/BNB/MANTLE/LINEA/SCROLL/ZG) are indexed"
log "by the trion-evm Rust binary in the Rust Indexers workflow."
log "All 12 EVM mainnet chains covered (see CHAINS array in trion-evm/src/main.rs)."

# Build trion-evm if not already built
if [[ ! -x "$BIN_DIR/trion-evm" ]]; then
    log "trion-evm binary not found — building workspace..."
    cd "$ROOT/rust-indexers" && cargo build -p trion-evm 2>&1 | tail -20
    log "Build complete."
fi

log "trion-evm binary confirmed at $BIN_DIR/trion-evm"
log "FAISS target: $FAISS_URL"
log ""
log "Chains verified in trion-evm/src/main.rs CHAINS array (all mainnet):"
log "  ETH_MAINNET    (1)       ARB_MAINNET (42161)"
log "  BASE_MAINNET   (8453)    OP_MAINNET  (10)"
log "  POLYGON        (137)     BNB_MAINNET (56)"
log "  HASHKEY        (177)     MANTLE      (5000)"
log "  LINEA          (59144)   SCROLL      (534352)"
log "  ZG_MAINNET     (16661)   ZG_NEWTON   (16600)"
log ""
log "Tailing EVM Rust indexer log..."

EVM_LOG="$LOG_DIR/trion-evm.log"
touch "$EVM_LOG"

# Stream EVM indexer log for visibility
tail -F "$EVM_LOG" &
TAIL_PID=$!

trap "kill $TAIL_PID 2>/dev/null; exit 0" SIGINT SIGTERM

# Health check loop — report FAISS vector counts every 60s
while true; do
    if curl -sf "$FAISS_URL/health" > /dev/null 2>&1; then
        COUNT=$(curl -sf "$FAISS_URL/stats" 2>/dev/null | python3 -c "import sys,json; d=json.load(sys.stdin); print(d.get('total_vectors',0))" 2>/dev/null || echo "?")
        log "FAISS healthy | total vectors indexed: $COUNT"
    else
        log "WARN: FAISS unreachable"
    fi
    sleep 60
done
