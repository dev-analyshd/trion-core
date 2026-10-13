#!/bin/bash
# run-50tx-daemon.sh — Run the 50-tx test in a way that survives shell session resets.
# Restarts on crash (the test script is resumable — it skips completed tests).
set -u
cd "$(dirname "$0")"
LOG=/tmp/run-50tx.log
PIDFILE=/tmp/run-50tx.pid

# Loop forever — restarts the test if it dies, until all 50 tests complete.
while true; do
  # Check if all 50 tests are done
  RESULTS=/home/z/my-project/trion-core/proofs/btcp-zero-bridge/stacks/v3-50tx-results.json
  if [ -f "$RESULTS" ]; then
    COMPLETED=$(python3 -c "import json; d=json.load(open('$RESULTS')); print(d.get('summary',{}).get('completed',0))" 2>/dev/null || echo 0)
    if [ "$COMPLETED" -ge 50 ]; then
      echo "[$(date +%H:%M:%S)] All 50 tests completed. Exiting." >> "$LOG"
      break
    fi
  fi
  echo "[$(date +%H:%M:%S)] Starting run-50tx-tests.mjs (PID $$)..." >> "$LOG"
  echo $$ > "$PIDFILE"
  node run-50tx-tests.mjs >> "$LOG" 2>&1
  EXIT=$?
  echo "[$(date +%H:%M:%S)] run-50tx-tests.mjs exited with code $EXIT" >> "$LOG"
  # Check completion again
  if [ -f "$RESULTS" ]; then
    COMPLETED=$(python3 -c "import json; d=json.load(open('$RESULTS')); print(d.get('summary',{}).get('completed',0))" 2>/dev/null || echo 0)
    if [ "$COMPLETED" -ge 50 ]; then
      echo "[$(date +%H:%M:%S)] All 50 tests completed. Exiting." >> "$LOG"
      break
    fi
  fi
  echo "[$(date +%H:%M:%S)] Sleeping 10s before restart..." >> "$LOG"
  sleep 10
done
