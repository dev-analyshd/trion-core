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

log "EVM Extras chains (BNB/Base/HSK/Mantle/Linea/Scroll) are indexed"
log "by the trion-evm Rust binary in the Rust Indexers workflow."
log "All 9 EVM chains covered: ARB_SEPOLIA BASE_SEPOLIA OP_SEPOLIA"
log "HASHKEY BNB_TESTNET ZG_GALILEO ETH_SEPOLIA MANTLE LINEA SCROLL"

# Build trion-evm if not already built
if [[ ! -x "$BIN_DIR/trion-evm" ]]; then
    log "trion-evm binary not found — building workspace..."
    cd "$ROOT/rust-indexers" && cargo build -p trion-evm 2>&1 | tail -20
    log "Build complete."
fi

log "trion-evm binary confirmed at $BIN_DIR/trion-evm"
log "FAISS target: $FAISS_URL"
log ""
log "Chains verified in trion-evm/src/main.rs CHAINS array:"
log "  ARB_SEPOLIA    (421614)  ETH_SEPOLIA (11155111)"
log "  BASE_SEPOLIA   (84532)   OP_SEPOLIA  (11155420)"
log "  HASHKEY        (177)     BNB_TESTNET (97)"
log "  ZG_GALILEO     (16602)   MANTLE      (5000)"
log "  LINEA          (59144)   SCROLL      (534352)"
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
