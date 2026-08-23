# TRION Protocol — Makefile
# Top-level build/test orchestration
# Usage: make test | make build | make deploy

.PHONY: test build clean deploy install lint

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
	cd sdk/src/wasm && wat2wasm signal_processor.wat -o signal_processor.wasm || true

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
deploy:
	bash scripts/deploy_testnet.sh

# ── Clean ─────────────────────────────────────────────────────────────────────
clean:
	find . -type d -name __pycache__ -exec rm -rf {} + 2>/dev/null || true
	find . -type f -name "*.pyc" -delete 2>/dev/null || true
	rm -rf indexers/target signal-processing/build validator/test_bin

# ── Lint ──────────────────────────────────────────────────────────────────────
lint:
	$(PYTHON) -m pyflakes core/ api/ anima-service/ || true
	cd indexers && cargo clippy --workspace 2>/dev/null || true
