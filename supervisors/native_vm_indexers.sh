#!/usr/bin/env bash
# ============================================================
# TRION Native VM Indexers Supervisor — Pure Rust L0
# Runs NEAR, TON, Polkadot/PVM, and StarkNet Rust indexers.
# All binaries compiled from indexers/crates/.
# Usage: bash supervisors/native_vm_indexers.sh
# ============================================================
set -euo pipefail

ROOT="$(cd "$(dirname "$0")/.." && pwd)"
# Production binaries live at /app/bin (set via RUST_BIN_DIR in Dockerfile.render).
# In Replit dev mode RUST_BIN_DIR is unset, so fall back to the local debug build.
BIN_DIR="${RUST_BIN_DIR:-$ROOT/indexers/target/debug}"
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
        if command -v cargo > /dev/null 2>&1; then
            log "Binary $bin not found — building workspace with cargo..."
            cd "$ROOT/indexers" && cargo build --workspace 2>&1 | tail -20
            log "Build complete."
        else
            log "WARN: $bin not found at $BIN_DIR/$bin and cargo is not available (production image). Skipping."
            return 1
        fi
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
if build_if_needed "trion-near"; then
    restart_process "trion-near" \
        env FAISS_SERVICE_URL="$FAISS_URL" \
        "$BIN_DIR/trion-near" &
    pids+=($!)
    sleep 0.3
fi

# TON Mainnet (TON_TESTNET not set → defaults to mainnet)
if build_if_needed "trion-ton"; then
    restart_process "trion-ton" \
        env FAISS_SERVICE_URL="$FAISS_URL" \
        "$BIN_DIR/trion-ton" &
    pids+=($!)
    sleep 0.3
fi

# PVM (Polkadot Mainnet — chain_id 25000, matching indexers/crates/trion-pvm)
# audit fix (REG-3): comment previously claimed chain_id 900, colliding with
# the canonical SVM/Solana 900 in config/chain_registry.json (the unified
# registry, formerly shared/chain_registry_complete.json).
if build_if_needed "trion-pvm"; then
    restart_process "trion-pvm" \
        env FAISS_SERVICE_URL="$FAISS_URL" \
        "$BIN_DIR/trion-pvm" &
    pids+=($!)
    sleep 0.3
fi

# StarkNet Mainnet
if build_if_needed "trion-starknet"; then
    restart_process "trion-starknet" \
        env FAISS_SERVICE_URL="$FAISS_URL" \
        "$BIN_DIR/trion-starknet" &
    pids+=($!)
fi

# audit fix (REG-3): chain ids now match the actual indexer constants
# (trion-near 23000, trion-ton 22000, trion-pvm 25000, trion-starknet 24000).
log "Native VM Rust indexers started: trion-near(23000) trion-ton(22000) trion-pvm(25000) trion-starknet(24000) — all mainnet"
log "Logs: $LOG_DIR/"

wait "${pids[@]}"
