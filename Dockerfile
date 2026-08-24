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
LABEL version="5.0.0"
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
# PHASE-1-SECURITY: force-upgrade pynacl (cosmpy transitively pins 1.6.0
# which has PYSEC-2026-3002). --no-deps avoids the cosmpy resolver conflict.
RUN pip install --no-cache-dir --no-deps pynacl==1.6.2

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

# Runtime dirs + ensure bh_ledger.db exists with the current schema
COPY scripts/init_bh_ledger.py    ./scripts/init_bh_ledger.py
COPY scripts/deploy_preflight.py    ./scripts/deploy_preflight.py
RUN chmod +x ./scripts/init_bh_ledger.py ./scripts/deploy_preflight.py && \
    mkdir -p 0g-state/logs 0g-state/exports 0g-state/proofs anima-service/data && \
    python3 /app/scripts/init_bh_ledger.py

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

# Healthcheck uses /readyz (503 until FAISS chain healthy)
HEALTHCHECK --interval=15s --timeout=5s --start-period=45s --retries=5 \
    CMD curl -fs http://localhost:${PORT:-5000}/readyz || exit 1

# Start Oracle API (FAISS ANIMA started separately via docker-compose or manually)
CMD ["python3", "serve.py"]
