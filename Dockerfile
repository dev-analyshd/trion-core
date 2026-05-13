FROM python:3.11-slim

LABEL maintainer="Hudu Yusuf (Analys)"
LABEL description="TRION Protocol — Local development image (Oracle API + FAISS ANIMA)"
LABEL version="2.0.0"

RUN apt-get update && apt-get install -y --no-install-recommends \
    curl gcc g++ libssl-dev ca-certificates \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /app

COPY oracle_api/requirements.txt ./oracle_api/requirements.txt
RUN pip install --no-cache-dir -r oracle_api/requirements.txt

COPY akashic/requirements.txt ./akashic-req.txt
RUN pip install --no-cache-dir -r akashic-req.txt

COPY oracle_api/ ./oracle_api/
COPY frontend/   ./frontend/
COPY akashic/    ./akashic/
COPY src/        ./src/
COPY serve.py    ./serve.py
COPY deployments.json ./deployments.json

ENV PORT=5000 \
    FAISS_PORT=8000 \
    FAISS_SERVICE_URL=http://127.0.0.1:8000 \
    PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1

EXPOSE 5000 8000

HEALTHCHECK --interval=15s --timeout=5s --start-period=30s --retries=3 \
    CMD curl -fs http://localhost:5000/api/v1/health || exit 1

CMD ["python3", "serve.py"]
