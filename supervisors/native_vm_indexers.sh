#!/usr/bin/env bash
# ============================================================
# TRION Native VM Indexers Supervisor — Pure Rust L0
# Runs NEAR, TON, Polkadot/PVM, and StarkNet Rust indexers.
# All binaries compiled from rust-indexers/crates/.
# Usage: bash supervisors/native_vm_indexers.sh
# ============================================================
set -euo pipefail

ROOT="$(cd "$(dirname "$0")/.." && pwd)"
BIN_DIR="$ROOT/rust-indexers/target/debug"
FAISS_URL="${FAISS_SERVICE_URL:-http://127.0.0.1:8000}"
LOG_DIR="/tmp/trion-rust-logs"
mkdir -p "$LOG_DIR"

log()  { echo "[$(date -u +%H:%M:%S)] [NATIVE-VM] $*"; }

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

# ── Native VM Rust Indexers ──────────────────────────────────
# NEAR Testnet      (chain_id 1201) — trion-near
# TON Testnet       (chain_id 1101) — trion-ton
# Polkadot Westend  (chain_id 901)  — trion-pvm
# StarkNet Sepolia  (chain_id 1300) — trion-starknet

INDEXERS=(
    "trion-near"
    "trion-ton"
    "trion-pvm"
    "trion-starknet"
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

log "Native VM Rust indexers started: ${INDEXERS[*]}"
log "Logs: $LOG_DIR/"

wait "${pids[@]}"
