#!/usr/bin/env bash
# =============================================================================
# TRION Protocol — Federated Validator Full-Stack Launcher
# =============================================================================
# Boots the entire TRION stack on a single validator node:
#
#   1. ANIMA FAISS engine       (FastAPI uvicorn, port $FAISS_PORT = 8001)
#   2. Python Oracle API        (Flask, port $PORT        = 5000)
#   3. 1–2 Rust indexers        (binaries from indexers/target/release/)
#   4. Go validator daemon      (mesh on :7001, /healthz on :7080)
#
# Every process is launched with `nohup` in the background and tracked by a
# PID file under /tmp/trion-validator-*.pid. SIGTERM/SIGINT to this script
# cascades to every child, and `--stop` will tear them down on demand.
#
# This script is the ExecStart of systemd/trion-validator-full.service.
# It assumes the trion-core repo is checked out at $TRION_HOME (default
# /opt/trion) and that the Python venv / Rust release / Go binary are already
# built. Use docker-compose.federated.yml for a fully self-contained 4-node
# cluster that builds everything from source.
#
# Usage:
#   ./start_validator_full.sh             # start the full stack, wait healthy
#   ./start_validator_full.sh --stop      # stop every process started by this script
#   ./start_validator_full.sh --status    # show running processes + health
#   ./start_validator_full.sh --help     # this message
#
# Required env (see validator.env.example):
#   TIMESCALEDB_URL         — shared Postgres/TimescaleDB cluster
#   RELAYER_PRIVATE_KEY     — 0x-prefixed EVM private key (KMS_PROVIDER=env)
#   TRION_API_KEY           — Oracle API X-API-Key
#   FAISS_API_KEY           — ANIMA FAISS X-API-Key
#   TRION_VALIDATOR_REGION  — ISO-3166 region code (NA-US, EU-DE, AP-JP, ...)
#
# Author: TRION Protocol — Federated Deployment Creator (Task ID 2)
# License: CC0
# =============================================================================

set -euo pipefail

# ── Paths ────────────────────────────────────────────────────────────────────
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
# TRION_HOME is the repo root (one level up from deploy/federated/ when running
# from a checkout, or wherever the systemd unit pointed WorkingDirectory).
TRION_HOME="${TRION_HOME:-$(cd "${SCRIPT_DIR}/../.." && pwd)}"
TRION_HOME="$(cd "${TRION_HOME}" && pwd)"

PYTHON_BIN="${PYTHON_BIN:-/home/z/.venv/bin/python3}"
[ -x "${PYTHON_BIN}" ] || PYTHON_BIN="$(command -v python3 || echo python3)"

PID_DIR="${PID_DIR:-/tmp}"
LOG_DIR="${LOG_DIR:-${TRION_HOME}/logs}"
mkdir -p "${PID_DIR}" "${LOG_DIR}"

# ── Service ports (defaults match validator_mesh.go / serve.py / faiss_service.py)
FAISS_PORT="${FAISS_PORT:-8001}"
ORACLE_PORT="${ORACLE_PORT:-5000}"
VALIDATOR_MESH_PORT="${VALIDATOR_MESH_PORT:-7001}"
HEALTHZ_PORT="${HEALTHZ_PORT:-7080}"

# ── PID file registry (so --stop / --status can find every child) ────────────
PID_FAISS="${PID_DIR}/trion-validator-faiss.pid"
PID_ORACLE="${PID_DIR}/trion-validator-oracle.pid"
PID_VALIDATOR="${PID_DIR}/trion-validator-go.pid"
PID_INDEXERS="${PID_DIR}/trion-validator-indexers.pid"   # newline-separated list

# ── Logging helpers ──────────────────────────────────────────────────────────
log()  { printf '[%s] %s\n' "$(date '+%H:%M:%S')" "$*" >&2; }
warn() { printf '[%s] WARN: %s\n' "$(date '+%H:%M:%S')" "$*" >&2; }
die()  { printf '[%s] FATAL: %s\n' "$(date '+%H:%M:%S')" "$*" >&2; exit 1; }

# is_pid_alive <pid>
is_pid_alive() {
    local pid="$1"
    [ -n "${pid}" ] || return 1
    kill -0 "${pid}" 2>/dev/null
}

# http_ok <url> — returns 0 if the URL returns any 2xx/3xx within the curl
# timeout (10 s). curl is optional; if absent we fall back to a TCP probe.
http_ok() {
    local url="$1"
    if command -v curl >/dev/null 2>&1; then
        curl -fsS --max-time 10 -o /dev/null "${url}" 2>/dev/null
        return $?
    fi
    # Fallback: strip scheme + path, probe host:port with bash /dev/tcp.
    local hostport="${url#http://}"
    hostport="${hostport#https://}"
    hostport="${hostport%%/*}"
    [ -n "${hostport}" ] || return 1
    (exec 3<>/dev/tcp/"${hostport}") 2>/dev/null
}

# wait_healthy <name> <url> <pid-file> <max_seconds>
wait_healthy() {
    local name="$1" url="$2" pidfile="$3" max="${4:-60}"
    local attempt=0 pid
    pid="$(cat "${pidfile}" 2>/dev/null || true)"
    log "Waiting for ${name} on ${url} (pid=${pid:-unknown}, ${max}s budget)..."
    while ! http_ok "${url}"; do
        if [ -n "${pid}" ] && ! is_pid_alive "${pid}"; then
            warn "${name} (pid ${pid}) exited before becoming healthy — see ${LOG_DIR}/"
            return 1
        fi
        attempt=$((attempt + 1))
        if [ "${attempt}" -ge "${max}" ]; then
            warn "${name} did not become healthy within ${max}s (polling ${url})"
            return 1
        fi
        sleep 1
    done
    log "✓ ${name} healthy on ${url}"
    return 0
}

# ── Required-env guard ───────────────────────────────────────────────────────
require_env() {
    local missing=0
    local var
    for var in TIMESCALEDB_URL RELAYER_PRIVATE_KEY TRION_API_KEY FAISS_API_KEY TRION_VALIDATOR_REGION; do
        if [ -z "${!var:-}" ]; then
            warn "required env var ${var} is not set"
            missing=1
        fi
    done
    [ "${missing}" -eq 0 ] || die "missing required environment (see ${SCRIPT_DIR}/validator.env.example)"
}

# ── Validator ID — TRION_VALIDATOR_ID or hostname-derived ────────────────────
resolve_validator_id() {
    if [ -n "${TRION_VALIDATOR_ID:-}" ]; then
        printf '%s' "${TRION_VALIDATOR_ID}"
    else
        printf 'trion-validator-%s' "$(hostname 2>/dev/null || echo unknown)"
    fi
}

# ── Service starters ─────────────────────────────────────────────────────────

start_faiss() {
    log "Starting ANIMA FAISS engine on :${FAISS_PORT}..."
    (
        cd "${TRION_HOME}/anima-service"
        exec "${PYTHON_BIN}" -m uvicorn faiss_service:app \
            --host 0.0.0.0 --port "${FAISS_PORT}" --workers 1
    ) >"${LOG_DIR}/validator-faiss.log" 2>&1 &
    echo $! > "${PID_FAISS}"
}

start_oracle() {
    log "Starting Python Oracle API on :${ORACLE_PORT}..."
    # KMS_PROVIDER=env (software-key path) is the federated model — the relayer
    # reads RELAYER_PRIVATE_KEY directly. TRION_ALLOW_RAW_ENV_KEYS=1 acknowledges
    # that we are intentionally using env-custodied keys (no HSM).
    export KMS_PROVIDER="${KMS_PROVIDER:-env}"
    export TRION_ALLOW_RAW_ENV_KEYS="${TRION_ALLOW_RAW_ENV_KEYS:-1}"
    export PORT="${ORACLE_PORT}"
    export FAISS_SERVICE_URL="${FAISS_SERVICE_URL:-http://127.0.0.1:${FAISS_PORT}}"
    export FAISS_PORT
    export TRION_API_KEY
    export FAISS_API_KEY
    export TIMESCALEDB_URL
    export RELAYER_PRIVATE_KEY
    export TRION_VALIDATOR_ID
    export TRION_VALIDATOR_REGION
    # The in-process BH streamer is the right mode for the federated profile:
    # serve.py runs as a single Flask process (no separate gunicorn workers),
    # so exactly one streamer owns the SQLite/WAL writer.
    export TRION_STREAMER_INPROCESS="${TRION_STREAMER_INPROCESS:-1}"
    (
        cd "${TRION_HOME}"
        exec "${PYTHON_BIN}" serve.py
    ) >"${LOG_DIR}/validator-oracle.log" 2>&1 &
    echo $! > "${PID_ORACLE}"
}

start_indexers() {
    # INDEXER_FAMILIES is a space-separated list, e.g. "evm" or "evm svm utxo".
    # Each family maps to a pre-built binary at
    #   indexers/target/release/trion-<family>
    local families="${INDEXER_FAMILIES:-evm}"
    local started=()
    : > "${PID_INDEXERS}"   # truncate registry

    for fam in ${families}; do
        local bin="${TRION_HOME}/indexers/target/release/trion-${fam}"
        if [ ! -x "${bin}" ]; then
            warn "indexer binary not found: ${bin} — run 'cargo build --release -p trion-${fam}' in ${TRION_HOME}/indexers"
            continue
        fi
        log "Starting Rust indexer trion-${fam}..."
        (
            cd "${TRION_HOME}"
            FAISS_SERVICE_URL="http://127.0.0.1:${FAISS_PORT}" \
            FAISS_API_KEY="${FAISS_API_KEY}" \
            POLL_INTERVAL_MS="${POLL_INTERVAL_MS:-15000}" \
            exec "${bin}"
        ) >"${LOG_DIR}/validator-indexer-${fam}.log" 2>&1 &
        local pid=$!
        printf '%s %s\n' "${fam}" "${pid}" >> "${PID_INDEXERS}"
        started+=("${fam}")
    done
    if [ "${#started[@]}" -eq 0 ]; then
        warn "no Rust indexers were started — INDEXER_FAMILIES='${families}' produced no runnable binaries"
    fi
}

start_validator() {
    log "Starting Go validator daemon (mesh :${VALIDATOR_MESH_PORT}, healthz :${HEALTHZ_PORT})..."
    export TRION_VALIDATOR_ID
    export TRION_VALIDATOR_REGION
    export TRION_VALIDATOR_ADDR="${TRION_VALIDATOR_ADDR:-0.0.0.0:${VALIDATOR_MESH_PORT}}"
    export TRION_HEALTHZ_ADDR="${TRION_HEALTHZ_ADDR:-0.0.0.0:${HEALTHZ_PORT}}"
    export TRION_VALIDATOR_CLIENT="${TRION_VALIDATOR_CLIENT:-trion-core}"
    (
        cd "${TRION_HOME}"
        # Prefer a pre-built binary; fall back to `go run` for dev sandboxes.
        if [ -x "${TRION_HOME}/validator/trion-validator" ]; then
            exec "${TRION_HOME}/validator/trion-validator"
        elif command -v go >/dev/null 2>&1; then
            cd "${TRION_HOME}/validator"
            exec go run ./cmd/trion-validator
        else
            die "no trion-validator binary and no Go toolchain on PATH"
        fi
    ) >"${LOG_DIR}/validator-go.log" 2>&1 &
    echo $! > "${PID_VALIDATOR}"
}

# ── Stop helpers ─────────────────────────────────────────────────────────────

# kill_pidfile <file> — gracefully TERM a single PID, wait 8s, then KILL.
kill_pidfile() {
    local file="$1" pid
    [ -f "${file}" ] || return 0
    pid="$(cat "${file}" 2>/dev/null || true)"
    if [ -n "${pid}" ] && is_pid_alive "${pid}"; then
        log "Sending SIGTERM to pid ${pid} (${file})"
        kill -TERM "${pid}" 2>/dev/null || true
        local waited=0
        while is_pid_alive "${pid}" && [ "${waited}" -lt 8 ]; do
            sleep 1; waited=$((waited + 1))
        done
        if is_pid_alive "${pid}"; then
            warn "pid ${pid} did not exit, sending SIGKILL"
            kill -KILL "${pid}" 2>/dev/null || true
        fi
    fi
    rm -f "${file}"
}

stop_all() {
    log "Stopping TRION validator stack..."
    # Indexers first (they depend on FAISS), then validator, oracle, FAISS.
    if [ -f "${PID_INDEXERS}" ]; then
        while IFS=' ' read -r fam pid; do
            [ -n "${pid}" ] || continue
            if is_pid_alive "${pid}"; then
                log "Stopping indexer trion-${fam} (pid ${pid})"
                kill -TERM "${pid}" 2>/dev/null || true
            fi
        done < "${PID_INDEXERS}"
        # Give them a moment to drain, then SIGKILL stragglers.
        sleep 2
        while IFS=' ' read -r fam pid; do
            [ -n "${pid}" ] || continue
            is_pid_alive "${pid}" && kill -KILL "${pid}" 2>/dev/null || true
        done < "${PID_INDEXERS}"
        rm -f "${PID_INDEXERS}"
    fi
    kill_pidfile "${PID_VALIDATOR}"
    kill_pidfile "${PID_ORACLE}"
    kill_pidfile "${PID_FAISS}"
    log "All TRION validator processes stopped."
}

# ── Status table ─────────────────────────────────────────────────────────────

print_status_row() {
    local name="$1" pidfile="$2" url="$3"
    local pid status health
    pid="$(cat "${pidfile}" 2>/dev/null || echo '-')"
    if [ "${pid}" = "-" ] || ! is_pid_alive "${pid}"; then
        status="STOPPED"
        health="-"
    else
        status="RUNNING"
        if [ -n "${url}" ] && http_ok "${url}"; then
            health="healthy"
        else
            health="unhealthy"
        fi
    fi
    printf '  %-22s %-8s %-10s %-8s %s\n' "${name}" "${pid}" "${status}" "${health}" "${url:-n/a}"
}

print_indexer_rows() {
    [ -f "${PID_INDEXERS}" ] || return 0
    while IFS=' ' read -r fam pid; do
        [ -n "${pid}" ] || continue
        local status
        if is_pid_alive "${pid}"; then status="RUNNING"; else status="STOPPED"; fi
        printf '  %-22s %-8s %-10s %-8s %s\n' "indexer:${fam}" "${pid}" "${status}" "-" "-"
    done < "${PID_INDEXERS}"
}

show_status() {
    local vid
    vid="$(resolve_validator_id)"
    cat <<EOF
============================================================
TRION Federated Validator — Status
  Validator ID : ${vid}
  Region       : ${TRION_VALIDATOR_REGION:-<unset>}
  Repo root    : ${TRION_HOME}
  Python       : ${PYTHON_BIN}
  Logs         : ${LOG_DIR}
------------------------------------------------------------
  service                pid      state      health   url
EOF
    print_status_row "faiss (anima)"   "${PID_FAISS}"     "http://127.0.0.1:${FAISS_PORT}/health"
    print_status_row "oracle api"      "${PID_ORACLE}"    "http://127.0.0.1:${ORACLE_PORT}/api/v1/health"
    print_indexer_rows
    print_status_row "validator mesh"  "${PID_VALIDATOR}" "http://127.0.0.1:${HEALTHZ_PORT}/healthz"
    echo "============================================================"
}

# ── Graceful shutdown on signal ──────────────────────────────────────────────
cleanup() {
    log "Caught shutdown signal — tearing down TRION validator stack"
    stop_all
    exit 0
}
trap cleanup SIGTERM SIGINT

# ── Argument parsing ─────────────────────────────────────────────────────────
case "${1:-start}" in
    --stop|-S)    stop_all; exit 0 ;;
    --status|-s) show_status; exit 0 ;;
    --help|-h)
        sed -n '2,/^# =\{10,\}$/p' "${BASH_SOURCE[0]}" | sed 's/^# \{0,1\}//'
        exit 0 ;;
    start|"") : ;;   # fall through
    *) die "unknown argument: $1 (try --help)" ;;
esac

# ── Main ─────────────────────────────────────────────────────────────────────
require_env

# Export the resolved validator ID so every child inherits it.
TRION_VALIDATOR_ID="$(resolve_validator_id)"
export TRION_VALIDATOR_ID

cat >&2 <<EOF
============================================================
TRION Protocol — Federated Validator Full-Stack Startup
  Validator ID : ${TRION_VALIDATOR_ID}
  Region       : ${TRION_VALIDATOR_REGION}
  Repo root    : ${TRION_HOME}
  Python       : ${PYTHON_BIN}
  KMS provider : ${KMS_PROVIDER:-env}  (software-key model — NO HSM)
  TimescaleDB  : ${TIMESCALEDB_URL}
  Indexer fam. : ${INDEXER_FAMILIES:-evm}
============================================================
EOF

# Refuse to double-start: if any of the primary services is already running,
# ask the operator to --stop first (avoids port collisions on FAISS/Oracle).
for f in "${PID_FAISS}" "${PID_ORACLE}" "${PID_VALIDATOR}"; do
    pid="$(cat "${f}" 2>/dev/null || true)"
    if [ -n "${pid}" ] && is_pid_alive "${pid}"; then
        die "service with pid ${pid} is already running (pidfile ${f}). Run '$0 --stop' first."
    fi
done

# 1. FAISS — must be healthy before the Oracle / indexers try to call it.
start_faiss
wait_healthy "ANIMA FAISS" "http://127.0.0.1:${FAISS_PORT}/health" "${PID_FAISS}" 60 || warn "FAISS not yet healthy — continuing (oracle will retry)"

# 2. Oracle API — depends on FAISS + TimescaleDB.
start_oracle
wait_healthy "Oracle API" "http://127.0.0.1:${ORACLE_PORT}/api/v1/health" "${PID_ORACLE}" 90 || warn "Oracle API not yet healthy — see ${LOG_DIR}/validator-oracle.log"

# 3. Rust indexers — read FAISS_SERVICE_URL + FAISS_API_KEY, write BHs to FAISS.
start_indexers

# 4. Go validator daemon — last because it queries the Oracle for Σ-plane scores.
start_validator
wait_healthy "validator mesh" "http://127.0.0.1:${HEALTHZ_PORT}/healthz" "${PID_VALIDATOR}" 30 || warn "validator healthz not ready — see ${LOG_DIR}/validator-go.log"

echo ""
show_status
echo ""
log "TRION validator stack is up. Logs: ${LOG_DIR}/validator-*.log"
log "Stop with: $0 --stop   |   Status: $0 --status"
log "(script will now wait for SIGTERM/SIGINT — systemd keeps this process alive)"

# Long-running sentinel: block until the trap fires or a child dies, then exit
# non-zero so systemd's Restart=always picks the stack back up.
while true; do
    for f in "${PID_FAISS}" "${PID_ORACLE}" "${PID_VALIDATOR}"; do
        pid="$(cat "${f}" 2>/dev/null || true)"
        if [ -n "${pid}" ] && ! is_pid_alive "${pid}"; then
            warn "child ${pid} (${f}) died — bringing down the whole stack"
            stop_all
            exit 1
        fi
    done
    sleep 5
done
