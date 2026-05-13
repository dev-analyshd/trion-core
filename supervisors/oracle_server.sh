#!/usr/bin/env bash
# TRION Oracle API + Frontend Server
# Starts the Flask-based Oracle API and serves the frontend on port 5000.

set -u
ROOT="$(cd "$(dirname "$0")/.." && pwd)"
cd "$ROOT"

echo "[ORACLE] Starting TRION Oracle API + Frontend on port 5000..."

while true; do
  PORT=5000 python3 serve.py 2>&1 | sed -u 's/^/[ORACLE] /'
  echo "[ORACLE] Server exited — restarting in 5s..."
  sleep 5
done
