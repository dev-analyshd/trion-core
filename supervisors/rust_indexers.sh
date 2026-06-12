#!/usr/bin/env bash
# ============================================================
# TRION Rust Indexer Supervisor — EVM + SVM core chains
# Manages trion-evm (9 EVM chains) and trion-svm (Solana).
# All other VMs are handled by native_vm_indexers.sh and
# extended_vm_indexers.sh (also Rust binaries).
# Usage: FAISS_SERVICE_URL=http://127.0.0.1:8000 bash supervisors/rust_indexers.sh
# ============================================================
set -euo pipefail

ROOT="$(cd "$(dirname "$0")/.." && pwd)"
BIN_DIR="$ROOT/rust-indexers/target/debug"
FAISS_URL="${FAISS_SERVICE_URL:-http://127.0.0.1:8000}"
LOG_DIR="/tmp/trion-rust-logs"
mkdir -p "$LOG_DIR"

log()  { echo "[$(date -u +%H:%M:%S)] [SUPERVISOR] $*"; }

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
        log "Binary $bin not found — building workspace (this may take ~2 min)..."
        cd "$ROOT/rust-indexers" && cargo build --workspace 2>&1 | tail -20
        log "Build complete."
    fi
}

restart_process() {
    local name="$1"; shift
    local logfile="$LOG_DIR/${name}.log"
    log "Starting [$name] → $*"
    while true; do
        "$@" >> "$logfile" 2>&1 || true
        log "[$name] exited — restarting in 5s"
        sleep 5
    done
}

# ── main ────────────────────────────────────────────────────
wait_faiss

# Core EVM + SVM Rust indexers
# (Native VMs: native_vm_indexers.sh | Extended VMs: extended_vm_indexers.sh)
INDEXERS=(
    "trion-evm"
    "trion-svm"
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

log "Core Rust indexers started (EVM×53 mainnet chains + SVM/Solana mainnet). PIDs: ${pids[*]}"
log "Logs: $LOG_DIR/"

wait "${pids[@]}"
