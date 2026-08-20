# =============================================================================
# TRION Protocol — Development Image
# Oracle API (Flask, port 5000) + FAISS ANIMA (FastAPI, port 8000)
#
# Quick start:
#   cp .env.example .env
#   docker compose up --build
#
# Endpoints:
#   http://localhost:5000/app/           Dashboard
#   http://localhost:5000/api/v1/health  Oracle API health
#   http://localhost:8000/health         FAISS ANIMA health
# =============================================================================
FROM python:3.11-slim

LABEL maintainer="TRION Protocol"
LABEL description="TRION Protocol — Dev image (Oracle API + FAISS ANIMA)"
LABEL version="4.0.0"
LABEL org.opencontainers.image.source="https://github.com/dev-analyshd/trion-core"

RUN apt-get update && apt-get install -y --no-install-recommends \
        curl bash ca-certificates gcc g++ libssl-dev libpq-dev \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /app

# ── Python deps ───────────────────────────────────────────────────────────────
COPY api/requirements.txt              ./api/requirements.txt
COPY anima-service/requirements.txt    ./anima-service/requirements.txt
RUN pip install --no-cache-dir \
        -r api/requirements.txt \
        -r anima-service/requirements.txt \
        numpy scipy scikit-learn

# ── Source ────────────────────────────────────────────────────────────────────
COPY api/              ./api/
COPY anima-service/    ./anima-service/
COPY core/             ./core/
# src/ was removed (deprecated shim layer) — all code is in core/
COPY trion-0g/         ./trion-0g/
COPY contracts/        ./contracts/
COPY config/           ./config/
COPY shared/           ./shared/
COPY serve.py          ./serve.py
COPY main.py           ./main.py
COPY deployments.json  ./deployments.json
COPY zg/               ./zg/
COPY schema.sql        ./schema.sql
COPY proof-ledger/     ./proof-ledger/

# Runtime dirs + ensure bh_ledger.db exists at root
RUN mkdir -p 0g-state/logs 0g-state/exports 0g-state/proofs anima-service/data && \
    python3 -c "import sqlite3; c=sqlite3.connect('/app/bh_ledger.db'); c.execute('CREATE TABLE IF NOT EXISTS bh_ledger (id INTEGER PRIMARY KEY AUTOINCREMENT, tx_hash TEXT UNIQUE, entity_id TEXT, from_addr TEXT, to_addr TEXT, event_type INTEGER, event_type_name TEXT, magnitude_norm REAL, value_wei TEXT, selector TEXT, sense_hex TEXT, antisense_hex TEXT, block_num INTEGER, block_hash TEXT, chain_id INTEGER, chain_label TEXT, ts REAL)'); c.execute('CREATE INDEX IF NOT EXISTS bh_ledger_entity ON bh_ledger(entity_id)'); c.execute('CREATE INDEX IF NOT EXISTS bh_ledger_chain ON bh_ledger(chain_id)'); c.execute('CREATE INDEX IF NOT EXISTS bh_ledger_ts ON bh_ledger(ts DESC)'); c.commit(); c.close(); print('bh_ledger.db initialized')"

# ── Environment ───────────────────────────────────────────────────────────────
ENV PORT=5000 \
    FAISS_PORT=8000 \
    FAISS_SERVICE_URL=http://127.0.0.1:8000 \
    FAISS_URL=http://127.0.0.1:8000 \
    ZG_NETWORK=mainnet \
    ZG_CHAIN_ID=16661 \
    ZERO_G_RPC=https://evmrpc.0g.ai \
    ZG_EXECUTION_GATE_ADDR=0xA85B49C73B5710d9ddB1CB5a94c52D0F33c4199b \
    PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1

EXPOSE 5000 8000

HEALTHCHECK --interval=15s --timeout=5s --start-period=45s --retries=5 \
    CMD curl -fs http://localhost:${PORT:-5000}/api/v1/health || exit 1

# Start Oracle API (FAISS ANIMA started separately via docker-compose or manually)
CMD ["python3", "serve.py"]
