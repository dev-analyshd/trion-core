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
# NEAR Mainnet      (chain_id 1200) — trion-near
# TON Mainnet       (chain_id 1100) — trion-ton
# Polkadot Westend  (chain_id 901)  — trion-pvm
# StarkNet Mainnet  (chain_id 8000) — trion-starknet

pids=()

# NEAR Mainnet
build_if_needed "trion-near"
restart_process "trion-near" \
    env FAISS_SERVICE_URL="$FAISS_URL" \
    "$BIN_DIR/trion-near" &
pids+=($!)
sleep 0.3

# TON Mainnet (TON_TESTNET not set → defaults to mainnet)
build_if_needed "trion-ton"
restart_process "trion-ton" \
    env FAISS_SERVICE_URL="$FAISS_URL" \
    "$BIN_DIR/trion-ton" &
pids+=($!)
sleep 0.3

# PVM (Polkadot Westend — only available testnet for Polkadot's substrate)
build_if_needed "trion-pvm"
restart_process "trion-pvm" \
    env FAISS_SERVICE_URL="$FAISS_URL" \
    "$BIN_DIR/trion-pvm" &
pids+=($!)
sleep 0.3

# StarkNet Mainnet
build_if_needed "trion-starknet"
restart_process "trion-starknet" \
    env FAISS_SERVICE_URL="$FAISS_URL" \
    "$BIN_DIR/trion-starknet" &
pids+=($!)

log "Native VM Rust indexers started: trion-near trion-ton trion-pvm trion-starknet (all mainnet)"
log "Logs: $LOG_DIR/"

wait "${pids[@]}"
