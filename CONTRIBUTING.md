# Contributing to TRION Protocol

## Getting Started

1. Clone the repository
2. Run `make install` to install all dependencies
3. Run `make test` to verify everything works

## Read First (conformance contract)

The canonical specification set and its extracted requirements live in
`docs/audit/CANONICAL_SPEC_MATRIX.md` (107 requirements + K1–K22 conflict
resolutions), with the layer contracts in `docs/protocol/` and
`docs/security/CANONICAL_INVARIANTS.md`. Changes that touch protocol
semantics must cite the matrix row they implement. The layer specs in
`spec/*.md` carry SUPERSEDED banners where an older draft was resolved
against MD/V2 — respect the banners.

## Repository Structure

See `spec/` for canonical specifications. The codebase follows the
institutional-grade directory structure:

- `core/` — Python behavioral engine (the brain)
- `api/` — Oracle API (Flask, port 5000, 282 routes)
- `anima-service/` — FAISS ANIMA engine (FastAPI, port 8000)
- `indexers/` — Rust L0 chain indexers (21 per-VM crates + trion-common)
- `validator/` — Go P2P validator mesh
- `contracts/` — Solidity + Vyper + Cairo/Move/FunC/ink!/CosmWasm/Soroban contracts
- `sdk/` — TypeScript SDK
- `formal/` — Haskell formal verification
- `math/` — Julia mathematical validation
- `signal-processing/` — C++ FFT engine
- `relayer/` — Node.js relayer (submits, never authorizes)
- `tests/` — unit/ + integration/ + adversarial/ + btcp/ + golden/

## External toolchains (honest labels)

cargo / forge / solc / Go / hardhat-node are NOT available in every sandbox —
Rust, Solidity and Go changes are statically verified here and compiled in CI.
Do not claim a compile/test result you did not run; label verification method
explicitly (the repo's standing policy — no fabricated verification).

## Code Style

- Python: Follow PEP 8, use type hints
- Rust: Follow `cargo fmt` and `cargo clippy`
- Solidity: Use 0.8.24+, enable optimizer + viaIR
- Go: Follow `gofmt`

## Testing

- Every PR must pass `make test`
- Adversarial tests: `make test-adversarial`
- Stress tests: `make test-stress`
- BTCP machine tests: `pytest tests/btcp -q` (87 + 1 xfail at Wave 3 close)
- Golden vectors: `pytest tests/golden -q` (134)

## License

CC0 — This knowledge belongs to everyone.
