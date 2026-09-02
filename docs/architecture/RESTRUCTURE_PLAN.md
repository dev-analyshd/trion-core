# TRION Protocol — Repository Restructure Plan (BTCP Master Spec §3.1)

**Status:** PLANNED — this document is the deliverable of P3-CONSOLIDATE
(completion criterion: "P2 architectural gap documented with plan").
It records the target layout, the gap analysis, the TOP-20 migration map,
risk assessment, and phased migration order. **No mass move is performed in
this phase** — a one-shot restructure would break 100+ import paths; each
phase below is independently shippable and test-gated.

**Golden rule for every move:** `git mv` → update importers (grep-verified
zero stale references) → `python3 -m pytest tests/unit/ -q` must stay
green (baseline at authoring time: **568 passed, 6 skipped**) → commit
(≤5 files, evidence in message). The v2 restructure
(`scripts/restructure_core.py`, `src/` → `core/`) proved this playbook works.

---

## 1. Target directory structure (BTCP Master Spec §3.1)

```
trion-core/
├── core/                    # Behavioral engine (Python reference implementation)
│   ├── primitives/          # L0: BH, HashDNA, thermodynamics, signal packing
│   ├── physical/            # Φ plane
│   ├── mental/              # M plane (incl. anima/)
│   ├── spiritual/           # Σ plane (incl. living_security/, conscious/)
│   ├── akashic/             # Akashic records (BIBL, genesis, archetype, ...)
│   ├── master/              # C(t), master equation, moat, signal factory
│   ├── btcp/                # BTCP routing/reference modules
│   ├── extended/            # BC, XSL, SBA, NL, BRT
│   ├── price/               # Behavioral valuation / price oracle
│   └── governance/          # Love Protocol, AWA, slashing, falsifiability
├── contracts/               # Cross-VM smart contracts, one dir per VM family
│   ├── evm/                 # Solidity + Vyper + Hardhat project
│   ├── solana/              # SVM/Anchor programs
│   ├── aptos-sui/           # Move (Aptos/Sui) + Polkadot-VM Move contracts
│   ├── cosmos/              # CosmWasm
│   ├── starknet/            # Cairo
│   ├── near/                # NEAR Rust
│   └── ton/                 # TON Func
├── crates/                  # ALL Rust in one workspace
│   ├── btcp/                # rust/src BTCP crate (router, proofs, BIBL, ...)
│   └── indexers/            # indexers/crates/* (21 chain crates + trion-common)
├── services/                # Deployable long-running services
│   ├── api/                 # Flask Oracle API (api/)
│   ├── anima/               # FAISS ANIMA FastAPI (anima-service/)
│   ├── zg/                  # 0G DA/relay daemons (zg/)
│   └── relayer/             # Node relayers (relayer/, trion-0g/)
├── zk/                      # Circom circuits + proofs (zk/ + zk-circuits/)
├── sdk/
│   ├── ts/                  # TypeScript SDK
│   ├── py/                  # Python SDK
│   └── wasm/                # WAT/WASM signal processor
├── tests/                   # unit/ integration/ adversarial/ crossvm/ (as today)
├── config/                  # chain_registry.json, bh_schema_v1.json, config.yaml
├── docs/                    # documentation (incl. this plan)
├── frontend/                # Next.js retail dashboard (stays top-level)
├── frontend-institutional/  # Next.js institutional dashboard (stays top-level)
├── validator/               # Go P2P validator (separate module, stays)
├── indexers → moved into crates/indexers/
└── (scripts/, deploy/, supervisors/ stay; see §4 non-moves)
```

## 2. Current layout (tracked files after P3-CONSOLIDATE)

| Dir | Files | Role | Target |
|---|---|---|---|
| core/ | 151 | Behavioral engine, **26 subpackages** vs §3.1's 10 | core/ (trim subpackages) |
| contracts/ | 98 | Mixed by language: solidity, vyper, move, cosmwasm, svm, near, cairo, soroban, script, test | contracts/<vm>/ |
| chains/ | 89 | Per-chain TS executors + non-EVM contracts + SVM/PVM/Near Rust | split: contracts/<vm>/ + services/ |
| tests/ | 54 | unit/integration/adversarial/crossvm | unchanged |
| indexers/ | 53 | Rust workspace: 21 crates + trion-common | crates/indexers/ |
| frontend/ + frontend-institutional/ | 87 | Next.js apps | unchanged (top-level) |
| scripts/ | 37 | deploy/bootstrap/generate utilities | unchanged (deploy scripts → deploy/ later) |
| anima-service/ | 35 | FAISS FastAPI + ANIMA/genesis backfill modules | services/anima/ |
| docs/ + spec/ | 46 | documentation | unchanged |
| rust/ | 25 | BTCP Rust crate | crates/btcp/ |
| api/ | 22 | Flask Oracle API | services/api/ |
| proof-ledger/ | 20 | deployment receipts | unchanged |
| zk-circuits/ + zk/ | 18 | 5 Circom circuits + package | zk/ |
| hardhat/ | 15 | EVM test/deploy project | contracts/evm/hardhat/ |
| validator/ | 12 | Go P2P validator | unchanged |
| deploy/ | 12 | docker/systemd/nginx/monitoring | unchanged |
| trion-0g/ | 11 | 0G storage/DA/compute JS | services/zg/ or services/relayer/ |
| sdk/ | 10 | Mixed TS + PY + wasm | sdk/{ts,py,wasm}/ |
| backtest/ | 9 | backtest harness | unchanged |
| supervisors/ | 7 | indexer/relayer shell supervisors | unchanged |
| relayer/ | 5 | Node EVM + non-EVM relayers | services/relayer/ |
| signal-processing/, math/, formal/, network/, continuum/, zg/ | ~20 | C++ DSP, Julia math, Haskell proofs, Go monitor, engines, 0G daemons | see map |
| config/ | 5 | **chain_registry.json (new)**, config.yaml, bh_schema, event_types, deployment.env | unchanged |

**Import-fragility baseline (evidence for risk section):**
- `from core.*` / `import core.*`: **156 occurrences in 48 files**
- `sys.path.insert` hacks: **68 files** (root, api, anima-service, zg added to
  path because `anima-service` has an illegal hyphen and api/zg are not
  packages under a services/ root)
- `from api.*`: 3 files; bare `from faiss_service/nl_score_engine/...`: 6+ files
- Deployment path couplings: `Dockerfile(.render/.railway)` COPY
  api/, anima-service/, relayer/, trion-0g/, chains/ paths; CI jobs use
  `working-directory:` (hardhat, sdk, validator, indexers); supervisors
  `cd relayer && node ...`; `Makefile` install-node loops over chains/* dirs.

## 3. Consolidation state after P3-CONSOLIDATE (already done — this phase)

| Item | Status |
|---|---|
| Price oracle duplicate (matrix #18) | **DONE** — single `core/price/btcp_price_oracle.py`; `anima-service/` + `akashic/` copies deleted, importers migrated |
| Chain registry (matrix #17) | **DONE** — single `config/chain_registry.json` (129 chains/18 VMs, superset of both old files); readers migrated; `scripts/generate_chain_bindings.py` → `core/generated_chain_bindings.py` (+8 unit tests) |
| Replit platform files, `attack_alert_webhook.py`, `backtest/package-lock.json`, `hardhat/hardhat-cache/`, `hardhat-artifacts/build-info/` | **DONE** — deleted with grep-verified zero dependents; `.gitignore` rules added |

**Remaining duplicate census (from P2-PYTHON worklog + deep-read):**
| Duplicate set | Files | Disposition in this plan |
|---|---|---|
| BIBL ×3 | `core/akashic/bibl.py`, `core/akashic/bibl_pattern_store.py`, `core/btcp/bibl_engine.py` | Phase 5: `core/akashic/` keeps the pattern-store + engine; `core/btcp/bibl_engine.py` is the routing-view — keep one canonical engine, thin façade for the router |
| XSL ×2 | `core/extended/cross_species.py`, `core/extended/xsl_engine.py` | Phase 5: cross-species scoring engine vs XSL language engine — verify overlap, keep both only if genuinely distinct roles (audit says distinct: XSL = language, cross_species = scoring) |
| Slashing ×2 | `core/spiritual/slashing.py`, `core/governance/slashing.py` | Phase 5: spiritual = Σ-plane consensus slashing, governance = penalty policy; consolidate API surface, one implementation |
| Chain-id tables ×4 | `api/chains_registry.py` (160), `core/btcp/mainnet_bootstrap.py` (152), `relayer/relayer_non_evm.js` (ad-hoc ids), `trion-0g/src/index.mjs` (31) | Phase 4/5: derive Python registries from `config/chain_registry.json` (bindings exist: `core/generated_chain_bindings.py`); regenerate JS constants via a `--json` emit of the same generator |

## 4. TOP 20 most impactful moves (file-by-file migration map)

Ranked by (import sites touched × deployment coupling). "Importers" numbers
are current grep counts; every row gets grep re-verification at execution
time (the counts move as the repo evolves).

| # | Current | Target | Importers/consumers to update | Risk | Prereq |
|---|---|---|---|---|---|
| 1 | `anima-service/` (35 py) | `services/anima/` | 68 sys.path-insert files; `core/btcp/integration.py` (6 bare imports); `tests/conftest.py`; `Dockerfile*` COPY; CI `install-python` (`-r anima-service/requirements.txt`); Makefile; supervisors | **High** — the hyphen→package rename finally legalizes the import everyone hacks around | Phase 0 |
| 2 | `api/` (22 py) | `services/api/` | `main.py`, `serve.py`, `tests/golden_test.py`, `tests/chain_coverage_audit.py` (from api.*), Dockerfiles (CMD gunicorn api/app:app paths), systemd units, render/railway entrypoints | **High** — gunicorn app-module path + Docker CMD changes | Phase 0 |
| 3 | `rust/` (BTCP crate, 25) | `crates/btcp/` | `indexers/Cargo.toml` workspace merge; `rust/Cargo.lock` merged; `supervisors/rust_indexers.sh` binary path; docs paths (README §Rust) | **Medium** — cargo-only (no Python importers), but lockfile merge needs `cargo` (CI job exists) | cargo in CI |
| 4 | `indexers/crates/*` (21 crates) | `crates/indexers/*` | `indexers/Cargo.toml` → `crates/Cargo.toml`; CI `ci-rust.yml` working-directory; Makefile `test-rust`/`build-rust` (`cd indexers`); `supervisors/rust_indexers.sh` BIN_DIR; `scripts/restructure` N/A | **Medium** | cargo in CI |
| 5 | `contracts/solidity/` + `hardhat/` | `contracts/evm/` (+ `contracts/evm/hardhat/`) | `hardhat.config.ts` sources path; CI compile-solidity working-directory; `scripts/generate_akashic_abi.py` OUT path (`artifacts/...` root artifact stays); `phase7_contract_verify.py`; slither.config.json paths; `tests/unit/btcp_continuum/*` read_contract() path constants | **Medium** — repo has ~10 path constants reading `contracts/solidity/` | Phase 0 grep |
| 6 | `contracts/cairo/` + `chains/starknet/` | `contracts/starknet/` | Scarb.toml/Scarb.lock move together; `chains/starknet/src/*.ts` (provider/deploy) stay in services or move with contracts; deep-read paths in docs | **Low** — no compile here (no scarb in sandbox); CI absent for cairo | CI addition |
| 7 | `contracts/svm/` (Anchor) + `chains/svm/` | `contracts/solana/` | `contracts/svm/Anchor.toml`, program ids; `chains/svm/svm_indexer.py` + `execute.ts` import paths; INTEGRATION_GUIDE.md | **Low-Medium** | anchor in CI |
| 8 | `contracts/move/` + `chains/sui/` + `chains/pvm/` (Move-era contracts) | `contracts/aptos-sui/` (+ keep pvm Rust under `contracts/solana`? no — pvm = Polkadot-VM → stays its own dir or `contracts/cosmos` sibling; decide at execution) | `Move.toml`; `anima-service/genesis_backfill_move.py` (chain labels only); TS executors | **Medium** (VM-family naming debate) | spec owner sign-off |
| 9 | `contracts/near/` + `chains/near/` | `contracts/near/` | `Cargo.toml` (both dirs have one); `proof-ledger/deploy_near_contract.json` (record only); `chains/near/deploy_wasm.mjs` | **Low** | — |
| 10 | `chains/ton/contracts/*.fc` | `contracts/ton/` | `chains/ton/execute.ts`, `deploy_oracle.cjs` paths | **Low** | — |
| 11 | `contracts/cosmwasm/` | `contracts/cosmos/` | `tests/unit` references? (grep `cosmwasm` — README + docs + CI solidity job only) | **Low** | — |
| 12 | `zk-circuits/` + `zk/` | `zk/` | `zk-circuits/package.json` (snarkjs); `scripts/` references; deep-read docs | **Low** | — |
| 13 | `sdk/TrionSDK.ts`, `sdk/src/*.ts`, `sdk/src/package.json` | `sdk/ts/` | CI ci-typescript (`cd sdk && npx tsc`); frontend imports? (grep — frontends use own lib) | **Low** | — |
| 14 | `sdk/trion_sdk.py` | `sdk/py/` | `from trion_sdk` importers (grep: none in-repo — it's an external-facing SDK); tests/unit? none | **Low** | — |
| 15 | `sdk/src/wasm/` | `sdk/wasm/` | Makefile build-wasm path | **Low** | — |
| 16 | `zg/` + `trion-0g/` | `services/zg/` | `zg/zg_config.py` path constants; Dockerfile COPY; `supervisors/zg_services.sh`; run_0g_full.sh | **Medium** | Phase 0 |
| 17 | `relayer/` | `services/relayer/` | supervisors (cd relayer), Dockerfile.render COPY, `.replit` (deleted), render-entrypoint, kms_provider path | **Medium** | Phase 0 |
| 18 | `main.py` + `serve.py` (root) | `services/api/main.py` (+ root thin launcher kept) | Dockerfile CMD `gunicorn main:app` / serve.py; railway/render entrypoints; run_0g_full.sh | **Medium** — keep root `serve.py` as 3-line shim to preserve container entrypoints | Phase 0 |
| 19 | `core/` 16 extra subpackages → §3.1's 10 (e.g. `thermodynamics/`→`primitives/`, `planes/`+`realtime/`+`pipeline/`→`master/` or `physical/`, `trading/`+`investment/`→`extended/`, `auditor/`→`spiritual/living_security` sibling or `core/auditor` exception, `novel/`→`spiritual/`+`extended/` split, `ubl/`,`lifecycle/`,`reputation/`,`protocol/`,`agent/`,`api/`→closest plane or services) | 156 `from core.*` sites in 48 files | **HIGH** — biggest single import surface; only after services/contracts moves land | Phase 5 (last) |
| 20 | BIBL/Slashing dedup + `api/chains_registry.py` & `mainnet_bootstrap.py` deriving from `config/chain_registry.json` via `core/generated_chain_bindings.py` | `from core.btcp.bibl_engine` (5 test files), `api/app.py` 2 routes, `api/btcp_continuum_routes.py` | **Medium** — behavior-preserving façades first | bindings exist (done) |

**Explicit non-moves (stay top-level):** `frontend/`, `frontend-institutional/`
(JS apps with own build tooling — §3.1 silent on apps), `validator/` (Go
module), `tests/`, `docs/`, `spec/`, `config/`, `scripts/`, `supervisors/`,
`deploy/`, `proof-ledger/` (append-only audit receipts), `backtest/`,
`math/`, `formal/`, `signal-processing/`, `network/`, `continuum/` (single
module — fold into core in Phase 5 if a home is agreed).

## 5. Risk assessment

| Risk | Likelihood | Impact | Mitigation |
|---|---|---|---|
| Python import breakage | Certain if done ad-hoc | Suite red (golden rule violated) | Move ONE package per commit; grep importer list BEFORE the move; run `pytest tests/unit/ -q` after every single move; keep a one-release compatibility shim (`from x import *`) only when external callers exist (SDKs) |
| sys.path hack rot (68 files) | High | Runtime ImportError in prod entrypoints (not covered by unit tests) | After `anima-service`→`services/anima`, DELETE the path-insert lines in a dedicated commit per consumer group; add `tests/unit/test_no_sys_path_hacks.py` that greps the tree and fails if new hacks appear |
| Docker/CI path rot | Medium | Deploy/CI failures invisible locally | For every moved dir, grep `Dockerfile*`, `.github/workflows/*`, `deploy/`, `Makefile`, `supervisors/`, `render*.y*ml`, `railway*`, `fly.toml` for the old path and update in the SAME commit; ci-python/ci-rust/ci-typescript/solidity jobs are the canaries |
| Rust workspace/lockfile merge errors | Medium | crates/ unbuildable | Do `rust/`→`crates/btcp/` and `indexers/`→`crates/indexers/` as separate PRs; regenerate `Cargo.lock` in CI (cargo unavailable in the current sandbox) — never hand-merge locks |
| Deployed-contract path references | Low | Verification scripts misreport | `proof-ledger/` receipts are historical records — do NOT rewrite; only update forward-looking scripts (`phase7_contract_verify.py`, `deploy_*.mjs`) |
| Loss of git history/blame | Low | Archaeology pain | Use `git mv` (rename detection) — proven by the v2 restructure (commit 1c1475a lineage) and this phase's oracle move |
| Behavioral regressions | Low | Silent numeric changes | Moves must be pure renames; any logic change is a separate fix commit (this phase's oracle move was a verbatim `git mv`) |

## 6. Phased migration order

Each phase = a sequence of ≤5-file commits, each ending green
(`python3 -m pytest tests/unit/ -q` → 568+ passed, 0 failed) and, where
relevant, `npx tsc --noEmit` / CI jobs green.

- **Phase 0 — Prep (no moves).**
  1. Freeze baselines: unit suite, `tests/test_btcp_bitp_sba_bibl.py` (33),
     `tests/chain_coverage_audit.py`, CI matrix green on `main`.
  2. ~~Add `tests/unit/test_no_sys_path_hacks.py`~~ **DONE in P3-CONSOLIDATE**
     (allow-list of the 68 files; new hacks fail the suite; live count may
     only shrink).
  3. Add an import-lint (`pyflakes` already in Makefile lint target; make
     it blocking for `core/ services/ api/ anima-service/`).
  4. Extend `scripts/generate_chain_bindings.py` with `--json` emit for
     JS/TS consumers (feeds Phase 4/5 registry derivation).
- **Phase 1 — crates/ (Rust only, CI-gated).**
  `rust/` → `crates/btcp/`; `indexers/` → `crates/indexers/`; merge
  workspace roots; update Makefile/CI/supervisors. No Python touched.
- **Phase 2 — contracts/ re-org.**
  One VM family per commit: evm (sol 29 files + hardhat 15) → solana →
  aptos-sui → cosmos → starknet → near → ton. Update the ~10 path
  constants in scripts/tests per family. Root `artifacts/` AkashicProof
  ABI path is DEPLOY-CRITICAL (`scripts/deploy_akashic_proof.mjs:46`) —
  leave `artifacts/` untouched.
- **Phase 3 — services/ (biggest Python surface).**
  1. `anima-service/` → `services/anima/` (importable package!) + migrate
     the 6 bare imports in `core/btcp/integration.py` + conftest + Docker.
  2. `api/` → `services/api/`; root `serve.py`/`main.py` become thin
     shims (`from services.api.app import app`).
  3. `zg/` → `services/zg/`; `relayer/`+`trion-0g/` → `services/relayer/`.
  4. Delete the now-dead sys.path.insert lines (allow-list shrinks).
- **Phase 4 — sdk/ split.** `sdk/{ts,py,wasm}` — CI ci-typescript job path
  update; publish docs unchanged.
- **Phase 5 — core/ subpackage trim + duplicate consolidation.**
  1. Fold the 16 extra subpackages into the 10 §3.1 families (map in §4 #19),
     one subpackage per commit, 156 import sites updated incrementally.
  2. BIBL ×3 → canonical `core/akashic/bibl.py` + façade; Slashing ×2 →
     one implementation; registry-in-code → derive from
     `core/generated_chain_bindings.py`.
- **Phase 6 — JS registry derivation + follow-up fixes.**
  relayer_non_evm.js / trion-0g chain-id tables regenerated from
  `config/chain_registry.json`; fixes the still-open Movement
  5002-vs-20200 mismatch (deep-read 03 §4) and the stale
  `*.replit.app` example URLs in sdk docs.

## 7. Follow-ups logged during P3 (not blocking the plan)

- `BTCPIntegrationHub.initialize()` reports 4 anima-service modules failing
  to import their documented class names (`GasForecastEngine`,
  `LiquidityOceanEngine`, `BRTScheduler`, `RegulatoryEngine`) — pre-existing
  (classes have different names in those modules); fix in Phase 3.1 while
  touching the imports.
- Alerting replacement for the removed `attack_alert_webhook.py`:
  Prometheus alertmanager rules in `deploy/monitoring/` (runbook already
  points there).
- `scripts/genesis_backfill_runner.py` now works (was crashing on a
  nonexistent registry path) — smoke-test it against a live FAISS in a
  maintenance window.
- `docs/deep-read/*` and `TRION_AUDIT_REPORT.md` intentionally retain
  references to deleted files (historical audit records, not consumers).
