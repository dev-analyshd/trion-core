#!/usr/bin/env bash
# ============================================================
# TRION Extended VM Indexers Supervisor — Pure Rust L0
# Runs UTXO, Cosmos, Aptos, Movement, SUI, TRON, PI indexers.
# All binaries compiled from rust-indexers/crates/.
# Usage: bash supervisors/extended_vm_indexers.sh
# ============================================================
set -euo pipefail

ROOT="$(cd "$(dirname "$0")/.." && pwd)"
BIN_DIR="$ROOT/rust-indexers/target/debug"
FAISS_URL="${FAISS_SERVICE_URL:-http://127.0.0.1:8000}"
LOG_DIR="/tmp/trion-rust-logs"
mkdir -p "$LOG_DIR"

log()  { echo "[$(date -u +%H:%M:%S)] [EXTENDED-VM] $*"; }

wait_faiss() {
    log "Waiting for FAISS service at $FAISS_URL ..."
    for i in $(seq 1 60); do
        if curl -sf "$FAISS_URL/health" > /dev/null 2>&1; then
            log "FAISS reachable after ${i}s"; return 0
        fi
        sleep 1
    done
    log "WARN: FAISS not reachable — starting indexers anyway"
}

build_if_needed() {
    local bin="$1"
    if [[ ! -x "$BIN_DIR/$bin" ]]; then
        log "Binary $bin not found — building workspace..."
        cd "$ROOT/rust-indexers" && cargo build --workspace 2>&1 | tail -20
        log "Build complete."
    fi
}

restart_process() {
    local name="$1"; shift
    local logfile="$LOG_DIR/${name}.log"
    log "Starting [$name]"
    while true; do
        "$@" >> "$logfile" 2>&1 || true
        log "[$name] exited — restarting in 5s"
        sleep 5
    done
}

wait_faiss

# ── Extended VM Rust Indexers ────────────────────────────────
# UTXO     (BTC/LTC/DOGE/DASH)        — trion-utxo
# Cosmos   (Hub/Kava/Inj/SEI/dYdX/Initia) — trion-cosmos
# Aptos    (Move VM, chain_id 5001)   — trion-aptos
# Movement (Move VM, chain_id 5002)   — trion-movement  ← NEW Rust L0
# SUI      (Sui Mainnet)              — trion-sui
# TRON     (TRON Mainnet)             — trion-tron
# PI       (Pi Network/Stellar)       — trion-pi

INDEXERS=(
    "trion-utxo"
    "trion-cosmos"
    "trion-aptos"
    "trion-movement"
    "trion-sui"
    "trion-tron"
    "trion-pi"
)

pids=()

for indexer in "${INDEXERS[@]}"; do
    build_if_needed "$indexer"
    restart_process "$indexer" \
        env FAISS_SERVICE_URL="$FAISS_URL" \
        "$BIN_DIR/$indexer" &
    pids+=($!)
    sleep 0.3
done

log "Extended VM Rust indexers started: ${INDEXERS[*]}"
log "Logs: $LOG_DIR/"

wait "${pids[@]}"
