# TRION Protocol — Railway Deployment Runbook

**Version 7.0.0** — production-grade Railway configuration with preflight validation,
readiness probes, and multi-service docker-compose parity.

---

## 1. Architecture (single container)

Railway deploys TRION as a single container that hosts four cooperating processes:

```
┌──────────────────────────────────────────────────────────────────┐
│  Container (trion-core:railway, image ~800MB)                   │
│                                                                  │
│   ┌────────────┐    ┌────────────┐    ┌─────────────────────┐   │
│   │  FAISS     │ ←──│  Flask     │ ←──│  Next.js (PORT)     │   │
│   │  :8000     │    │  :5000     │    │  public PORT        │   │
│   │  /readyz   │    │  /readyz   │    │  /readyz            │   │
│   └────────────┘    └────────────┘    └─────────────────────┘   │
│         ↑                  ↑                  ↑                  │
│         │                  │                  │                  │
│   ┌─────┴──────┐    ┌──────┴──────┐   Railway healthcheck      │
│   │  BH        │    │  Backfill    │   hits /readyz (port $PORT)│
│   │  Streamer  │    │  (delayed)   │                             │
│   └────────────┘    └─────────────┘                             │
│                                                                  │
│   Optional (off by default):                                     │
│   • Go validator self-test         — TRION_ENABLE_VALIDATOR=1  │
│     (one-shot mesh + TRION-BFT verification; no daemon,         │
│      nothing listens on :6000)                                  │
│   • C++ signal processing           — TRION_ENABLE_SIGNAL_PROCESSING=1 │
│   • Prometheus/Grafana              — TRION_ENABLE_MONITORING=1 │
└──────────────────────────────────────────────────────────────────┘
```

| Service            | Port  | Health path    | Ready path | Notes                          |
|--------------------|-------|----------------|------------|--------------------------------|
| Next.js frontend   | $PORT | /healthz       | /readyz    | Public; Railway healthcheck hits this |
| Flask Oracle API   | 5000  | /api/v1/health | /readyz    | Probes FAISS /readyz           |
| FAISS ANIMA Engine | 8000  | /healthz, /health | /readyz | Returns 503 until index loaded |
| BH Streamer        | —     | logs            | —          | Background process             |
| BH→FAISS backfill  | —     | logs            | —          | Delayed 60s, runs once        |

Note: Flask also runs a flask-socketio push layer (`serve.py` →
`api/socket_push.py`, `/feed` namespace) that the dashboard consumes when
reachable. Railway's Next.js entry cannot proxy WebSocket upgrades, so on
this single-container deployment the dashboard runs its live feed in REST
polling mode (by design); the nginx/docker-compose stack
(`deploy/nginx/trion.conf`) proxies `/socket.io/` and gets true push.

## 2. Health vs Readiness (why both)

| Endpoint | Returns | Used for                       |
|----------|---------|--------------------------------|
| `/healthz` | 200 (always, process alive) | Liveness probes, dashboards    |
| `/readyz`  | 200 when deps ready, 503 otherwise | Routing, deployment healthcheck |
| `/api/v1/health` | 200 with deep state | Application-level monitoring    |

Railway's `healthcheckPath: /readyz` means traffic is only routed to the
container once the entire chain — Next.js → Flask → FAISS — is ready to
serve. During cold-start (typically 30-90s), `/readyz` returns 503 and
Railway waits patiently without restarting.

## 3. Preflight validation

The entrypoint runs `scripts/deploy_preflight.py` before starting any
service. It validates:

1. **Required env** — `PORT` is set (Railway auto-injects).
2. **Storage** — `BH_LEDGER_DB` path is writable; if a stale pre-`valid`
   schema ledger exists, it auto-migrates.
3. **RPC reachability** — when `TRION_REQUIRE_RPC=1`, probes 0G mainnet
   (critical) + 3 EVM chains (informational). 0G is the only hard
   dependency; the BH streamer has its own per-chain failover.

Exit codes:
- `0` — pass, continue to entrypoint
- `11` — env violation (fail-closed)
- `12` — storage / DB failure
- `13` — critical RPC unreachable AND `TRION_REQUIRE_RPC=1`

## 4. Deployment Steps

### 4.1 First-time setup (Railway Dashboard)

1. Create a new Railway project.
2. **New Service → GitHub Repo** → select `dev-analyshd/trion-core`.
3. Railway auto-detects `railway.json` and uses `Dockerfile.railway`.
4. In **Variables** tab, set the following:

| Variable | Value | Source |
|----------|-------|--------|
| `PORT` | *(auto by Railway)* | Railway |
| `TRION_API_KEY` | random 32-byte hex | `openssl rand -hex 32` |
| `GUNICORN_WORKERS` | `2` (512MB) / `4` (8GB+) | plan-dependent |
| `TRION_MAX_CHAINS` | `12` (512MB) / `0` (8GB+; 0 = all 96) | plan-dependent |
| `TRION_REQUIRE_RPC` | `0` (default) — set to `1` only for pre-mainnet validation | operator |
| `DATABASE_URL` | *(empty → SQLite)* or Railway Postgres `$${{Postgres.DATABASE_URL}}` | optional |

5. Optional: add a Postgres database service in Railway and reference its
   `DATABASE_URL` to persist the Akashic Index beyond container restarts.

### 4.2 Deploy

Push to `main`:

```bash
git push origin main
```

Railway builds and deploys automatically. Watch the build log for:

```
[entrypoint HH:MM:SS] Running preflight checks...
[preflight INFO] PORT=... FAISS_PORT=8000 FLASK_PORT=5000
[preflight INFO] Storage OK: bh_ledger=/app/bh_ledger.db
[preflight INFO] Preflight OK (0.3s)
[entrypoint HH:MM:SS] Initializing BH ledger at /app/bh_ledger.db...
[entrypoint HH:MM:SS] Starting FAISS ANIMA Engine on :8000...
[entrypoint HH:MM:SS] FAISS ready after 3s
[entrypoint HH:MM:SS] Starting Flask Oracle API on :5000...
[entrypoint HH:MM:SS] Flask ready after 2s
[entrypoint HH:MM:SS] Starting BH Streamer...
[entrypoint HH:MM:SS] Starting Next.js frontend on :10000...
[entrypoint HH:MM:SS] Next.js started (PID ...)
```

First deploy takes ~5 minutes (image build + cold start). Subsequent
deploys take ~30s (cached layers + warm start).

### 4.3 Verify

Once Railway marks the service as **healthy**, hit the public URL:

```bash
export TRION_URL=https://your-app.up.railway.app

# 1. Readiness — should return 200 with status: ready
curl -fs $TRION_URL/readyz | jq

# 2. App-level health — includes Θ(t), block_number, chain_connected
curl -fs $TRION_URL/api/v1/health | jq

# 3. FAISS ANIMA stats — vector count, archetypes, entities
curl -fs $TRION_URL:8000/health 2>/dev/null || \
  echo "FAISS port not exposed (expected on Railway)"

# 4. Institutional dashboard (HTML)
curl -fsI $TRION_URL/ | head -5
```

## 5. Local Docker Parity Test

Before pushing, validate the Railway image locally:

```bash
cd trion-core

# Build and run with the same image Railway uses
docker compose --profile railway up --build

# In another terminal — hit the same endpoints
curl -fs http://localhost:10000/readyz | jq
curl -fs http://localhost:10000/api/v1/health | jq

# Tear down
docker compose --profile railway down
```

The `railway` profile uses `Dockerfile.railway` with identical env vars
to Railway production. If it works locally, it will work on Railway.

## 6. Environment Variables Reference

### Required
- `PORT` *(auto by Railway)* — public port

### Service toggles (all default to sensible values)
- `TRION_ENABLE_STREAMER=1` — start BH streamer (96 mainnet chains)
- `TRION_MAX_CHAINS=12` — cap concurrent chain indexers (12 for 512MB, 0 for 8GB+)
- `TRION_ENABLE_FAISS=1` — start FAISS ANIMA engine
- `TRION_ENABLE_VALIDATOR=0` — Go validator mesh/BFT self-test (one-shot
  verification run, not a daemon — nothing listens on :6000; see
  DEPLOYMENT.md "Go services")
- `TRION_ENABLE_SIGNAL_PROCESSING=0` — C++ FFT engine (off; needs cmake)
- `TRION_ENABLE_MONITORING=0` — Prometheus/Grafana configs (off)

### Tunable
- `GUNICORN_WORKERS=2` — Flask worker count
- `GUNICORN_THREADS=4` — threads per worker
- `GUNICORN_TIMEOUT=120` — request timeout seconds
- `RATE_LIMIT_MAX_REQUESTS=300` — per-IP per-minute

### Optional persistent storage
- `DATABASE_URL` — Postgres connection (Railway Postgres recommended)
- `TIMESCALEDB_URL` — alias for `DATABASE_URL`

### Pre-mainnet validation
- `TRION_REQUIRE_RPC=1` — fail-closed if 0G RPC unreachable

## 7. Operational Runbook

### 7.1 Cold start sequence (typical 30-90s)

1. Container starts; entrypoint runs preflight (~1s).
2. BH ledger DB initialized (~0.1s).
3. FAISS ANIMA engine boots, loads existing index (~5-15s).
4. Flask Oracle API starts; `/readyz` waits for FAISS /readyz (~2s).
5. BH Streamer starts in background; begins consuming blocks from 96 chains.
6. BH→FAISS backfill delayed 60s; runs once to populate vectors from existing ledger.
7. Next.js frontend starts; `/readyz` waits for Flask /readyz (~2s).

Until step 7 completes, Railway sees `/readyz` returning 503 and does
not route public traffic. This is by design — it prevents users from
hitting a half-booted stack.

### 7.2 Restart behavior

- **Process death (FAISS or Flask):** entrypoint watchdog detects within
  30s, kills Next.js, container exits. Railway restarts the container
  with `restartPolicyMaxRetries=5`.
- **OOM kill:** Railway restarts automatically. Volumes (faiss-data,
  zg-state) persist across restarts.
- **Image build failure:** Railway rolls back to previous successful deploy.

### 7.3 Viewing logs

```bash
# Live logs (Railway CLI)
railway logs

# Filter to entrypoint
railway logs | grep entrypoint

# Filter to preflight
railway logs | grep preflight

# Filter to a specific service
railway logs | grep -E "FAISS|Flask|Next.js|BH Streamer"
```

The entrypoint also emits a STATUS line every 5 minutes:

```
[entrypoint HH:MM:SS] STATUS bh_ledger=83614 vectors=24868 flask=UP next=UP
```

### 7.4 Scaling up

| Plan | TRION_MAX_CHAINS | GUNICORN_WORKERS | Notes |
|------|-------------------|------------------|-------|
| 512MB Hobby | 12 | 2 | Default; ~12 chains active |
| 8GB Pro | 0 (all 96) | 4 | Full mainnet coverage |
| 16GB+ | 0 | 8 | Add TRION_ENABLE_VALIDATOR=1 (Go mesh/BFT self-test) |

### 7.5 Adding Postgres persistence

1. In Railway: **+ New → Database → PostgreSQL**.
2. Railway creates a `Postgres` service with a `DATABASE_URL` variable.
3. In your trion service: **Variables → Reference Variable → `Postgres.DATABASE_URL`**.
4. Set `DATABASE_URL=$${{Postgres.DATABASE_URL}}` (note: double `$$`).
5. Redeploy. The Akashic Index will now persist behavioral memory to
   Postgres instead of local SQLite.

## 8. Troubleshooting

### 8.1 Container crashes on boot

```
[entrypoint] FATAL: Preflight failed — refusing to start
```

Likely cause: `PORT` env var not set (rare on Railway, common locally).
Fix: `export PORT=10000` locally, or rely on Railway auto-injection.

### 8.2 Healthcheck fails (503 forever)

```
[entrypoint] FAISS /readyz not green after 60s — continuing
```

The container starts but `/readyz` never returns 200. Likely cause:
FAISS index corruption from a hard restart. Fix:

```bash
# In Railway shell:
rm /app/anima-service/akashic_faiss.index
rm /app/anima-service/akashic_state.db
# Container will restart with a fresh index; backfill will repopulate from BH ledger
```

### 8.3 High memory usage

```bash
# Reduce concurrent chain count
TRION_MAX_CHAINS=8

# Reduce Flask workers
GUNICORN_WORKERS=1
```

### 8.4 0G RPC unreachable

```
[preflight ERROR] Critical RPC probes failed: 0G mainnet: URLError
```

0G mainnet RPC (`https://evmrpc.0g.ai`) is down or geo-blocked. Check
status at `https://chainscan.0g.ai`. If persistent, override:

```bash
ZERO_G_RPC=https://0g-evmrpc.chainode.tech  # community fallback
```

## 9. Rollback

Railway keeps every successful deploy. To roll back:

1. Railway Dashboard → **Deployments**.
2. Select the previous successful deploy.
3. Click **Promote to Production**.

Rollback takes ~30s (no rebuild — image is cached).

## 10. Local Development (without Docker)

```bash
# Install deps
pip install -r api/requirements.txt -r anima-service/requirements.txt
cd frontend && npm install --legacy-peer-deps && cd ..

# Terminal 1: FAISS
cd anima-service && uvicorn faiss_service:app --port 8000 --reload

# Terminal 2: Flask + WebSocket push layer (what the Railway entrypoint runs)
python serve.py
#   (REST-only alternative, no /socket.io/: gunicorn --bind 0.0.0.0:5000 --workers 2 "api.app:app")

# Terminal 3: BH Streamer
python scripts/run_bh_streamer.py

# Terminal 4: Next.js
cd frontend && npm run dev
```

Health probes:
- http://localhost:8000/readyz  (FAISS)
- http://localhost:5000/readyz  (Flask)
- http://localhost:3000/readyz  (Next.js)
