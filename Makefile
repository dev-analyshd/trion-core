# TRION Protocol — Makefile
# Top-level build/test orchestration
# Usage: make test | make build | make deploy

.PHONY: test build clean deploy install lint preflight docker-railway docker-dev docker-full docker-down railway-up railway-logs

# ── Python ────────────────────────────────────────────────────────────────────
PYTHON := python3
PIP := pip3

# ── Test ──────────────────────────────────────────────────────────────────────
test: test-python test-rust test-go

test-python:
	$(PYTHON) -m pytest tests/unit/ -q --tb=short

test-rust:
	cd indexers && cargo test -p trion-common --lib

test-go:
	cd validator && go test ./...

test-adversarial:
	$(PYTHON) scripts/simulate_attacks.py

test-stress:
	$(PYTHON) scripts/stress_test.py --ci || true

# ── Build ─────────────────────────────────────────────────────────────────────
build: build-rust build-go build-cpp

build-rust:
	cd indexers && cargo build --workspace --release

build-go:
	cd validator && go build ./...

build-cpp:
	cd signal-processing && mkdir -p build && cd build && cmake .. -DCMAKE_BUILD_TYPE=Release && cmake --build .

build-wasm:
	cd sdk/src/wasm && wat2wasm signal_processor.wat -o signal_processor.wasm

# ── Install ───────────────────────────────────────────────────────────────────
install: install-python install-node

install-python:
	$(PIP) install -r api/requirements.txt -r anima-service/requirements.txt

install-node:
	cd relayer && npm install --legacy-peer-deps
	for d in chains/svm chains/near chains/ton chains/pvm chains/starknet chains/sui chains/botchain trion-0g; do \
	cd $$d && npm install --legacy-peer-deps && cd -; \
	done

# ── Deploy ────────────────────────────────────────────────────────────────────
# audit fix (BUILD-1): the old target ran scripts/deploy_testnet.sh, which was
# removed in the mainnet-only restructure (commit 325ab95 "go-live gate").
# The real deploy flow is preflight → mainnet deploy.
deploy: preflight
	python3 scripts/deploy_mainnet.py

# ── Preflight (v7.0.0+) ─────────────────────────────────────────────────────
# Validates env, storage, and (optionally) RPC reachability before any service starts.
# Used by the Docker entrypoint; can also be run directly.
preflight:
	PORT=$${PORT:-10000} BH_LEDGER_DB=$${BH_LEDGER_DB:-/tmp/bh_ledger.db} \
	python3 scripts/deploy_preflight.py

preflight-strict:
	PORT=$${PORT:-10000} BH_LEDGER_DB=$${BH_LEDGER_DB:-/tmp/bh_ledger.db} \
	TRION_REQUIRE_RPC=1 python3 scripts/deploy_preflight.py

# ── Docker (v7.0.0+) ─────────────────────────────────────────────────────────
# Three profiles matching production / parity / full-subsystem:
#   docker-dev      - Oracle API + FAISS only (fastest, ~3 min build)
#   docker-railway  - parity-test the Railway image locally before pushing
#   docker-full     - all subsystems (validator, signal processing, monitoring)
docker-dev:
	docker compose up --build

docker-railway:
	docker compose --profile railway up --build

docker-full:
	docker compose --profile full up --build

docker-down:
	docker compose down

# ── Railway CLI (v7.0.0+) ────────────────────────────────────────────────────
# Requires `npm i -g @railway/cli` and `railway login` once.
railway-up:
	railway up

railway-logs:
	railway logs

# ── Clean ─────────────────────────────────────────────────────────────────────
clean:
	find . -type d -name __pycache__ -exec rm -rf {} + 2>/dev/null || true
	find . -type f -name "*.pyc" -delete 2>/dev/null || true
	rm -rf indexers/target signal-processing/build validator/test_bin

# ── Lint ──────────────────────────────────────────────────────────────────────
lint:
	$(PYTHON) -m pyflakes core/ api/ anima-service/ || true
	cd indexers && cargo clippy --workspace 2>/dev/null || true
