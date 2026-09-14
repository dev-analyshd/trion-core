#!/bin/bash
# Watchdog: restart the 100-proof script if it dies
LOG=/tmp/zk-100-proofs.log
PIDFILE=/tmp/zk-100-proofs.pid
cd /home/z/my-project/trion-core/btc-tools

MAX_RESTARTS=20
RESTARTS=0

while [ $RESTARTS -lt $MAX_RESTARTS ]; do
  # Check if we've completed 100 proofs
  if [ -f /home/z/my-project/trion-core/docs/proofs/zk_100_proofs.json ]; then
    COUNT=$(grep -c '"id":' /home/z/my-project/trion-core/docs/proofs/zk_100_proofs.json 2>/dev/null || echo 0)
    if [ "$COUNT" -ge 100 ]; then
      echo "[$(date +%T)] COMPLETED 100 proofs. Exiting watchdog."
      break
    fi
  fi
  
  echo "[$(date +%T)] Starting zk-p2p3 script (attempt $((RESTARTS+1)))..."
  NODE_PATH=/home/z/my-project/node_modules node zk-p2p3-100-proofs.mjs >> $LOG 2>&1
  EXIT_CODE=$?
  echo "[$(date +%T)] Script exited with code $EXIT_CODE"
  RESTARTS=$((RESTARTS+1))
  sleep 3
done

echo "[$(date +%T)] Watchdog finished after $RESTARTS restarts"
tail -20 $LOG
