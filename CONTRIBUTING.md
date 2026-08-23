# Contributing to TRION Protocol

## Getting Started

1. Clone the repository
2. Run `make install` to install all dependencies
3. Run `make test` to verify everything works

## Repository Structure

See `spec/` for canonical specifications. The codebase follows the
institutional-grade directory structure:

- `core/` — Python behavioral engine (the brain)
- `api/` — Oracle API (Flask, port 5000)
- `anima-service/` — FAISS ANIMA engine (FastAPI, port 8000)
- `indexers/` — Rust L0 chain indexers (14 crates)
- `validator/` — Go P2P validator mesh
- `contracts/` — Solidity + Vyper smart contracts
- `sdk/` — TypeScript SDK
- `formal/` — Haskell formal verification
- `math/` — Julia mathematical validation
- `signal-processing/` — C++ FFT engine
- `relayer/` — Node.js relayers (EVM + non-EVM)
- `tests/` — unit/ + integration/ + adversarial/

## Code Style

- Python: Follow PEP 8, use type hints
- Rust: Follow `cargo fmt` and `cargo clippy`
- Solidity: Use 0.8.24+, enable optimizer + viaIR
- Go: Follow `gofmt`

## Testing

- Every PR must pass `make test`
- Adversarial tests: `make test-adversarial`
- Stress tests: `make test-stress`

## License

CC0 — This knowledge belongs to everyone.
