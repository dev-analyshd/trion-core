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

## The layer map (see docs/ARCHITECTURE.md for the full diagram)

| Layer | Where | What it does |
|---|---|---|
| Ingestion | `indexers/` (Rust), `anima-service/` (FAISS + TimescaleDB + crawlers) | Chain crawling, 93-byte Behavioral Hash events, entropy features |
| Planes & master equation | `core/` (Python, ~300 modules) | Φ/M/Σ/K/A coherence, C(t) vs Θ(t), manipulation fingerprints, governance engines |
| Consensus | `validator/` (Go) | DW-BFT engine: block production, rounds, view changes, slashing evidence; diversity-weighted proposers |
| Contracts | `contracts/` (Solidity, Vyper, Cairo, Move, FunC, ink!, CosmWasm, Soroban…) | Escrow with signature-quorum release gate, intents, routes, staking, token |
| Data availability | `trion-0g/` | 0G DA publishing |
| Services | `api/` (Flask), `relayer/` (Node), `frontend/`, `frontend-institutional/` (Next.js) | Oracle API, cross-chain relayer, dashboards |
| Formal & adversarial | `formal/` (Haskell), `hardhat/` (adversarial EVM tests), `zk-circuits/` (Circom, unbuilt) | Type-level theorems, red-team suites, ZK sketches |

## Entry points

- `api/app.py` — Flask oracle API (port 5000)
- `validator/cmd/trion-validator` — Go BFT validator node
- `relayer/relayer.js` — cross-chain relayer (KMS-backed signing)
- `Makefile` — build/test/deploy orchestration
- `scripts/deploy_preflight.py` — environment validation before any service starts

## Registry (single source of truth)

`config/chain_registry.json` — 129 chains, 18 VM families, 41 integrated. Every
chain/VM count in the API, frontends, and docs derives from this file.

## Deployment posture

Testnet-only except one self-reported 0G mainnet deployment-gate transaction
(see README "On-Chain Proofs" section — all records self-reported). The
validator network runs observation-only; see `docs/MAINNET_RUNBOOK.md` for the
gating conditions (professional audit required, not yet obtained).
