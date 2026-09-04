# TRION Protocol — Deployment Guide

## Prerequisites
- Docker 24+ (or Railway/Render CLI)
- Node.js 20+ (for local frontend dev)
- Python 3.11+ (for local backend dev)

## Environment Variables
See `.env.example` for the complete list. Key variables:
- `PORT` — Railway-injected, defaults to 10000 (serve.py reads it; 5000 locally)
- `FAISS_SERVICE_URL` — internal FAISS URL (http://127.0.0.1:8000)
- `FLASK_URL` — internal Flask URL (http://127.0.0.1:5000)
- `DATABASE_URL` — SQLite or TimescaleDB connection string
- `EVM_PRIVATE_KEY` — Relayer signing key (for on-chain publication)
- `NEXT_PUBLIC_WS_URL` — optional; direct WebSocket base for the dashboard's
  live feed (e.g. `ws://127.0.0.1:5000` in dev). Empty = same-origin
  `/socket.io/` (works behind the nginx deploy; see "WebSocket push" below)
- `HEALTH_MONITOR_PORT` — Go network health monitor port (default 6001; see
  "Go services" below)

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
   - BH Streamer (96 workers: 60 EVM + 36 non-EVM, its own in-file registry; the canonical chain registry holds 129 chains / 18 VM families)
5. Health check: `GET /api/v1/health` (auto-configured, 300s timeout)

## Docker Compose (Local)
```bash
docker-compose up -d
```
The root `docker-compose.yml` dev profile is a SINGLE container (service
`trion`, image `trion-core:dev`) running the same contract as Railway:
serve.py (Flask + flask-socketio) + FAISS + the BH streamer, exposed on
:5000 (API, `$PORT`) and :8000 (FAISS). Profiles: `dev` (default),
`railway` (local parity test of `Dockerfile.railway`), `full` (all optional
subsystems), plus a `postgres` service.

A separate multi-service production stack (faiss / api / validator /
frontend / nginx / prometheus / grafana, each in its own container) lives in
`deploy/docker/docker-compose.yml`; nginx there also proxies the
`/socket.io/` websocket (see "WebSocket push" below and "Monitoring" for
its honest state).

## Manual Deployment
```bash
# 1. Install Python deps
pip install -r api/requirements.txt -r anima-service/requirements.txt
pip install numpy scipy scikit-learn gunicorn web3 feedparser vaderSentiment

# 2. Start FAISS
cd anima-service && python3 -m uvicorn faiss_service:app --host 0.0.0.0 --port 8000 &

# 3. Start Flask API + WebSocket push layer
#    serve.py = the Flask app wrapped with flask-socketio: REST on :5000 plus
#    the /socket.io/ /feed namespace the dashboard's live signal feed consumes.
cd .. && python3 serve.py &
#    (REST-only alternative, no websocket: gunicorn api.app:app --bind 0.0.0.0:5000 --workers 2)

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
5. Frontend at `/` → Dashboard with live data (the "Live Signal Feed" card
   shows `WS PUSH` when the socket channel is up, `POLLING` otherwise)

## Health Check URLs
- API liveness: `GET /healthz` (always 200)
- API readiness: `GET /readyz` (503 until FAISS is reachable)
- Main: `GET /api/v1/health` (deep state)
- FAISS: `GET http://localhost:8000/healthz` (also `/health`, `/readyz`, `/stats`)
- BH Stats: `GET /api/v1/bh/stats`
- Frontend: `GET /healthz` and `GET /readyz` (Next.js route handlers)

## WebSocket push
`serve.py` wraps the Flask app with flask-socketio (`api/socket_push.py`):
a background thread polls `/api/v1/feed` and pushes every new entry as a
`signal` event on the `/feed` namespace, plus a `health` stats packet every
10s. The dashboard consumes this with a dependency-free engine.io v4 client
(`frontend/src/lib/socketio.ts` → `useSocketFeed` hook) and falls back to its
normal REST polling when the socket is down. Routing:
- **Local dev**: set `NEXT_PUBLIC_WS_URL=ws://127.0.0.1:5000` (Next.js dev
  rewrites cannot proxy WebSocket upgrades).
- **nginx stack** (`deploy/nginx/trion.conf`): same-origin `/socket.io/` is
  proxied with Upgrade headers — no env var needed.
- **Railway single-container**: the Next.js entry cannot proxy WS, so the
  dashboard runs in polling mode there (by design, not a bug).

## Go services (external toolchain required)
The repo ships two Go components. **This environment has no Go toolchain —
both are static-audited only; build/run them on a machine with Go ≥ 1.21.**

### Network health monitor — `network/health_monitor.go`
```bash
cd network
go run .            # or: go build -o health_monitor . && ./health_monitor
```
- Serves `GET /health` and `GET /health/chains` on **:6001** (override with
  `HEALTH_MONITOR_PORT`).
- Concurrently probes 19 hardcoded endpoints: 14 EVM RPCs
  (`eth_blockNumber`), Solana/NEAR/TON HTTP endpoints, plus the internal
  FAISS (`127.0.0.1:8000/health`) and Flask (`127.0.0.1:5000/health`)
  services; returns HEALTHY/DEGRADED/OFFLINE per target with latency.
- Relation to the Python stack: Flask `/readyz` already gates on FAISS
  reachability and `/api/v1/health` reports deep state — the Go monitor
  independently re-checks those two PLUS external chain RPCs from a
  separate process and language (whitepaper Part 11 network layer). Keep
  it as an independent cross-check plane; it is NOT started by any deploy
  entrypoint (compose/systemd/Railway all leave it to the operator).
- Known code drift (filed for the Go owners — not fixed in this pass): the
  non-EVM entries carry placeholder `chain_id: 0` (canonical registry ids:
  Solana 900, NEAR 23000, TON 22000) and the ORACLE probe path should be
  `/healthz` — the Flask app exposes `/healthz`, `/readyz` and
  `/api/v1/health`, so a bare `/health` 404s and the monitor would report
  the oracle DEGRADED while it is healthy.

### Validator network — `validator/` (module `github.com/trion-protocol/validator`)
```bash
cd validator
go build ./... && go vet ./... && go test ./...   # full suite (see validator/README.md)
go run ./cmd/trion-validator/                    # mesh + TRION-BFT self-test
```
- `cmd/trion-validator` is a ONE-SHOT self-test: attestation-mesh
  primitives, dual-strand SHA3 signing and a 4-validator TRION-BFT
  consensus round over real TCP gossip. It prints PASS and exits —
  **there is no daemon and nothing listens on :6000.**
- The P2P HTTP gateway (`internal/p2p/gateway.go`, routes `/health`,
  `/anima/crawl`, `/mesh/quorum`, `/consensus/sigma`, …) is a library
  exercised by `go test ./internal/p2p/` only — wiring it to a port needs
  a `main` that builds crawler+mesh and calls
  `NewAPIGateway(port, crawler, mesh).Start()`.
- `TRION_ENABLE_VALIDATOR=1` (Railway/render entrypoints) runs the same
  self-test honestly instead of daemonizing a binary that exits; the old
  `VALIDATOR_PORT`/`VALIDATOR_URL`/`TRION_VALIDATOR_PORT` env vars were
  read by nothing and have been removed from the deploy configs.

## Monitoring
- Prometheus at `:9090` and Grafana at `:3001` (deploy/docker compose
  `prometheus` + `grafana` services; env toggles in Railway configs).
- HONEST STATE: neither the Flask API nor the FAISS service exposes a
  `/metrics` endpoint yet, so the TRION scrape jobs 404 and only `up`
  exists; the `trion_*` alert-rule metrics are not exported anywhere yet
  (documented inline in `deploy/monitoring/prometheus.yml` + `alerts.yml`).
- Log output via `docker logs trion` (root dev compose) or
  `docker logs trion-frontend` (deploy/docker stack)

## Troubleshooting
- **BH count = 0**: BH streamer needs 30-60s to produce first hashes. Check `bh_ledger.db`.
- **FAISS vectors = 0**: Backfill script runs 60s after startup. Check FAISS logs.
- **API 500**: Check `DATABASE_URL` — if empty, SQLite is used. Install `psycopg2` for TimescaleDB.
- **Frontend blank**: Check Next.js rewrites — `/api/*` must proxy to Flask at port 5000.
