# TRION Protocol — Deployment Guide

## Prerequisites
- Docker 24+ (or Railway/Render CLI)
- Node.js 20+ (for local frontend dev)
- Python 3.11+ (for local backend dev)

## Environment Variables
See `.env.example` for the complete list. Key variables:
- `PORT` — Railway-injected, defaults to 10000
- `FAISS_SERVICE_URL` — internal FAISS URL (http://127.0.0.1:8000)
- `FLASK_URL` — internal Flask URL (http://127.0.0.1:5000)
- `DATABASE_URL` — SQLite or TimescaleDB connection string
- `EVM_PRIVATE_KEY` — Relayer signing key (for on-chain publication)

## Railway Deployment (Primary)
1. Connect your GitHub repo at railway.com
2. Railway auto-detects `railway.json` → uses `Dockerfile.railway`
3. Set secret env vars in Railway Dashboard:
   - `EVM_PRIVATE_KEY` (for on-chain signal publication)
   - `DATABASE_URL` (optional, defaults to SQLite)
4. Deploy — Railway builds and starts:
   - Next.js frontend on $PORT
   - Flask API on port 5000 (internal)
   - FAISS ANIMA engine on port 8000 (internal)
   - BH Streamer (71 EVM + 58 non-EVM chains — source: config/chain_registry.json)
5. Health check: `GET /api/v1/health` (auto-configured, 300s timeout)

## Docker Compose (Local)
```bash
docker-compose up -d
```
Services:
- `trion-frontend` — Next.js on port 3000
- `trion-api` — Flask on port 5000
- `trion-faiss` — FastAPI on port 8000
- `trion-bh-streamer` — BH indexer

## Manual Deployment
```bash
# 1. Install Python deps
pip install -r api/requirements.txt -r anima-service/requirements.txt
pip install numpy scipy scikit-learn gunicorn web3 feedparser vaderSentiment

# 2. Start FAISS
cd anima-service && python3 -m uvicorn faiss_service:app --host 0.0.0.0 --port 8000 &

# 3. Start Flask API
cd .. && gunicorn api.app:app --bind 0.0.0.0:5000 --workers 2 &

# 4. Start BH Streamer
python3 scripts/run_bh_streamer.py &

# 5. Start Frontend
cd frontend && npm install && npm run build && node .next/standalone/server.js
```

## Post-Deployment Verification
1. `GET /api/v1/health` → 200 OK with system stats
2. `GET /api/v1/bh/stats` → BH count > 0 (after 30s)
3. `GET /api/v1/signal/uniswap` → Coherence signal with C(t), T(t)
4. `GET /api/v1/btcp/orchestrator/status` → BTCP orchestrator status
5. Frontend at `/` → Dashboard with live data

## Health Check URLs
- Main: `GET /api/v1/health`
- FAISS: `GET http://localhost:8000/healthz`
- BH Stats: `GET /api/v1/bh/stats`

## Monitoring
- Prometheus metrics at `:9090` (if TRION_ENABLE_MONITORING=1)
- Grafana dashboards at `:3001`
- Log output via `docker logs trion-frontend`

## Troubleshooting
- **BH count = 0**: BH streamer needs 30-60s to produce first hashes. Check `bh_ledger.db`.
- **FAISS vectors = 0**: Backfill script runs 60s after startup. Check FAISS logs.
- **API 500**: Check `DATABASE_URL` — if empty, SQLite is used. Install `psycopg2` for TimescaleDB.
- **Frontend blank**: Check Next.js rewrites — `/api/*` must proxy to Flask at port 5000.
