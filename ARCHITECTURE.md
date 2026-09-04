# TRION Protocol — Architecture (top-level map)

> Historical note: this file previously documented the pre-rebrand application
> ("TRION Sensing Oracle" — a ChainGPT-era coherence-gated vault for Arbitrum
> Sepolia, referencing files that no longer exist in this repository). That
> content was removed 2026-09-03; the current architecture lives in
> [`docs/ARCHITECTURE.md`](docs/ARCHITECTURE.md). What follows is the honest
> short version.

## What this repository is

A behavioral-truth oracle protocol: it ingests on-chain and off-chain behavioral
data, computes a five-plane coherence score C(t) per entity, publishes the
verdict on-chain, and (the BTCP layer) routes cross-chain settlement on top of
those verdicts instead of moving assets through bridges.

Since the Wave 1–3 canonical reconstruction, settlement authority on every VM
tier (EVM/Solidity+Vyper, Solana, Move, TON, NEAR, Starknet/Cairo) is the
**346-byte canonical certificate**: each verifier checks it against a
**per-epoch validator registry** with **weight quorum** (`w_j = s_j·d_j`, L4.2
tier table), fail-closed (no oracle fallback), replay-protected (nonces +
consumed-certificate tracking), and freshness-gated (second-based value-tier
TTL; `hhi_at_emission > 4000` ⇒ INVALID). Signal emission is gated by the AWA
(Anti-Weaponization Architecture, MD §17) EmissionGate — frozen ⇒ 503
`silence:true` at `/api/v1/publish`, no chain write.

## The layer map (see docs/ARCHITECTURE.md for the full diagram)

| Layer | Where | What it does |
|---|---|---|
| Ingestion (two paths) | `core/realtime/bh_streamer.py` (96 workers: 60 EVM + 36 non-EVM, Python hot path) · `indexers/crates/` (21 Rust crates + `trion-common`, the 40 integrated chains) | Chain crawling, 93-byte Behavioral Hash events, entropy features |
| Planes & master equation | `core/` (Python, ~300 modules) | Φ/M/Σ/K/A coherence, C(t) vs Θ(t), manipulation fingerprints, governance engines |
| Consensus & certificates | `validator/` (Go, external toolchain) · `core/consensus/certificate.py` (reference encoder) · `contracts/solidity/TrionEpochRegistry.sol` + per-VM registries | DW-BFT engine, block production, slashing evidence, diversity-weighted proposers; canonical certificate emission + per-epoch registry verification with weight quorum |
| Contracts | `contracts/` (Solidity, Vyper, Cairo, Move, FunC, ink!, CosmWasm, Soroban…) | Escrow release on canonical-certificate verification (weight quorum, forward-only epoch registration), intents, routes, staking, token |
| Data availability | `trion-0g/` | 0G DA publishing |
| Services | `api/` (Flask, 282 routes; X-API-Key write auth; truth-boundary labels), `relayer/` (Node, submit-only custody), `frontend/`, `frontend-institutional/` (Next.js) | Oracle API, cross-chain relayer, dashboards |
| Storage | `schema.sql` (35 tables, per-table writer dispositions: 12 operative / 6 deploy-gated / 17 NONE) + SQLite mirrors | Akashic persistence, BTCP step-6 atomic writes, replay/equivocation guards |
| Formal & adversarial | `formal/` (Haskell), `hardhat/` (adversarial EVM tests), `zk-circuits/` (Circom, unbuilt) | Type-level theorems, red-team suites, ZK sketches |

## Entry points

- `api/app.py` — Flask oracle API (port 5000)
- `validator/cmd/trion-validator` — Go BFT validator node (one-shot self-test; external toolchain)
- `relayer/relayer.js` — cross-chain relayer (submits, never authorizes; KMS-backed signing in production)
- `Makefile` — build/test/deploy orchestration
- `scripts/deploy_preflight.py` — environment validation before any service starts

## Registry (single source of truth)

`config/chain_registry.json` — 129 chains, 18 VM families, 40 integrated. Every
chain/VM count in the API, frontends, and docs derives from this file.

## Canonical specification set (read-first for conformance)

- `docs/audit/CANONICAL_SPEC_MATRIX.md` — 107 requirements + K1–K22 conflict resolutions
- `docs/protocol/CANONICAL_BH.md` — the 93-byte BH contract
- `docs/protocol/CANONICAL_CERTIFICATE.md` — the 346-byte certificate + verification algorithm
- `docs/protocol/BTCP_STATE_MACHINE.md` — 26 states / 33 transitions
- `docs/security/CANONICAL_INVARIANTS.md` — INV-001…022 with enforcement status

## Deployment posture

Testnet-only except one self-reported 0G mainnet deployment-gate transaction
(see README "On-Chain Proofs" section — all records self-reported). The
validator network runs observation-only; see `docs/MAINNET_RUNBOOK.md` for the
gating conditions (professional audit required, not yet obtained).
