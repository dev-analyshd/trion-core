# CANONICAL CHAIN REGISTRY AUDIT (Master Sweep 2026-09-04)

**Canonical source:** `config/chain_registry.json` — the single identity
authority (master command §19, "every chain must have one canonical identity").

## Declared == Actual (machine-checked this sweep)

| Metric | Declared | Recomputed | Verdict |
|---|---|---|---|
| total_chains | 129 | 129 | ✅ |
| vm_families | 18 | 18 | ✅ |
| integrated_chains | 40 | 40 | ✅ (was 41 at af09ab3; one chain honestly de-integrated in the 83-commit window) |
| duplicate chainIds | — | NONE | ✅ |

**Canonical pins verified:** Ethereum=1, Solana Mainnet=900, Stellar
Mainnet=27000, Polkadot=25000. Hyperliquid (999) correctly **absent** from the
registry (pinned off-registry, honestly disclosed). EVM=71 / non-EVM=58.

## Category separation (§19 — never collapsed)

| Category | Count | Meaning (verified) |
|---|---|---|
| REGISTERED | 129 | in chain_registry.json |
| INTEGRATED (live) | 40 | registry `integrated: true` = live indexer + oracle |
| TESTNETS | 23 | status tier derived (SWEEP-B derivation layer) |
| INDEXED-awaiting | 66 | registered, indexer not yet live |
| SUPPORTED (contracts) | 9 VM families | contract tiers shipped |
| TESTED | EVM family (real py-evm), Vyper, layout-tested TON, static others | per SWEEP-C |
| DEPLOYED | 0G Galileo (live), Arb/Base/OP Sepolia, Starknet Sepolia, NEAR testnet | self-reported + corroborated split (PURGE-2 discipline) |
| LIVE production value | **NONE** (external boundary) | no funded mainnet escrows |

## Derivation architecture (verified live)

One JSON → (a) `api/chains_registry.py` import-time derivation, (b) both
frontend const sets (`source: config/chain_registry.json`), (c) `trion-0g`
runtime `registry_counts.mjs` (null on read failure — never a stale number),
(d) 29 sampled Rust indexer consts match registry ids (SWEEP-B).

**Three-way agreement check (this sweep):** API `/api/v1/chains` ==
frontend consts == registry JSON == 129/18/40. ✅

## Findings closed this sweep

- 4 Rust indexers (hedera/vechain/algorand/cardano) wrote chain block hashes
  through SHA3 substitution — now the canonical §9 lenient decode (0ef64fd).
- Registry decimals=8 for Hedera vs indexer 1e18 division: **not a violation**
  — JSON-RPC serves weibars (1e18/HBAR); weibars/1e18 == tinybar/1e8 == HBAR
  human units (documented in-crate).
- Residual: `bh_streamer` chain-999 hyperliquid entry points at a testnet RPC
  in a mainnet-labeled table (LOW, pre-existing, labeled in streamer config).
