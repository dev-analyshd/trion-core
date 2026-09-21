#!/bin/bash
# TRION dev-services supervisor — starts Oracle API (5000) + ANIMA FAISS (8000)
# and keeps them alive. Robust against parent-shell termination via setsid.
set -u
ROOT="/home/z/my-project/trion-core"
cd "$ROOT"
set -a; source .env.local 2>/dev/null; set +a

# Kill any stale instances
pkill -f "flask --app api.app" 2>/dev/null
pkill -f "uvicorn faiss_service:app" 2>/dev/null
sleep 1

# Start ANIMA FAISS (must run from its own dir for local imports)
cd "$ROOT/anima-service"
setsid /home/z/.venv/bin/python3 -m uvicorn faiss_service:app \
    --host 127.0.0.1 --port 8000 \
    > /tmp/anima.log 2>&1 &
ANIMA_PID=$!
echo "ANIMA started PID=$ANIMA_PID"

# Start Oracle Flask API
cd "$ROOT"
setsid /home/z/.venv/bin/python3 -m flask --app api.app run \
    --host 127.0.0.1 --port 5000 \
    > /tmp/oracle.log 2>&1 &
ORACLE_PID=$!
echo "ORACLE started PID=$ORACLE_PID"

# Start Revenue Model Service (LOCAL ONLY — not in git; whitepaper §15.2)
setsid /home/z/.venv/bin/python3 revenue_model_service.py \
    > /tmp/revenue.log 2>&1 &
REV_PID=$!
echo "REVENUE started PID=$REV_PID"

# Wait for all three to be ready
echo "Waiting for services to be ready..."
for i in $(seq 1 40); do
  O=$(curl -sf -o /dev/null -w "%{http_code}" http://127.0.0.1:5000/api/v1/health 2>/dev/null)
  A=$(curl -sf -o /dev/null -w "%{http_code}" http://127.0.0.1:8000/health 2>/dev/null)
  R=$(curl -sf -o /dev/null -w "%{http_code}" http://127.0.0.1:5001/health 2>/dev/null)
  if [ "$O" = "200" ] && [ "$A" = "200" ] && [ "$R" = "200" ]; then
    echo "READY at iter=$i  Oracle=$O  ANIMA=$A  Revenue=$R"
    echo "ORACLE_PID=$ORACLE_PID" > /tmp/trion_pids
    echo "ANIMA_PID=$ANIMA_PID" >> /tmp/trion_pids
    echo "REV_PID=$REV_PID" >> /tmp/trion_pids
    exit 0
  fi
  sleep 1
done
echo "TIMEOUT — Oracle=$O ANIMA=$A Revenue=$R"
exit 1
