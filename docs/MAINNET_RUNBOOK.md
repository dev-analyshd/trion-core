# TRION Mainnet Go-Live Runbook

**Status: CODE-READY — awaiting operational gates.**
This document is the complete, ordered procedure to take TRION from its
current state to live mainnet operation. Nothing here requires code changes;
everything here requires operational action that **cannot be done from a
development sandbox**.

---

## 0. Honest Current State (audited)

| Dimension | Status | Evidence |
|---|---|---|
| Contract suites (9 VM languages) | ✅ compile clean | solc 0.8.24 viaIR, Scarb, cargo (ink!/NEAR/CosmWasm/Anchor), FunC |
| Security hardening | ✅ applied | reentrancy guards, ACL, drain-proof sweep, timelocked bypass, route freshness — all in-tree |
| Test battery | ✅ green | as of 2026-09-03: 104/105 formulas (PQC check needs optional libs), 117 Rust `#[test]` (not compiled in sandbox), 6/6 ZK, 571 unit + 121 adversarial + 186 integration pytest, hardhat 43, 30/30 Golden Test |
| Key hygiene | ✅ fixed | relayer env-only; hardhat **fails closed** on mainnets without a key |
| Deployment infra | ✅ present | Docker ×3, compose, systemd ×4, nginx, Prometheus+alerts, webhook alerter |
| Preflight gate | ✅ new | `scripts/mainnet_preflight.py` — automated blocker detection |
| Professional audit | ❌ **REQUIRED** | No third-party audit exists. Non-negotiable before escrow holds funds. |
| Akashic depth D(t) | ❌ 18.3% | 8,439 / 46,051. Whitepaper: ~6 months of honest operation. **Cannot be shortcut.** |
| Validator network | ❌ bootstrap only | Whitepaper needs ≥100 validators on ≥4 continents before INIT_valid. |
| Deployer wallet | ❌ **TAINTED** | Prior mainnet deploys came from `0xdBbf66…42d20`, whose key was exposed in git history. **All contracts must be redeployed from a fresh key.** |

---

## Phase 1 — Pre-Flight (week 0)

### 1.1 Fresh key generation
```bash
# Generate DEDICATED deployment keys (never reuse, never commit):
#  - RELAYER_PRIVATE_KEY     → signal publication
#  - DEPLOY_0G_PRIVATE       → 0G mainnet deploys
# Store in a vault (AWS Secrets Manager / HashiCorp), never in files.
```

### 1.2 Professional security audit
- Engage a firm (Trail of Bits / OpenZeppelin / Quantstamp / Spearbit).
- Scope: `contracts/solidity/BTCPEscrow.sol`, `TRIONExecutionGate.sol`,
  `TRIONOracleV3.sol`, `BTCPGasAbstraction.sol`, `ConfidentialCoherenceVault.sol`,
  plus the Vyper token/staking pair.
- Fix all findings, re-run `tests/` battery, commit under `audit/<date>/`.

### 1.3 Automated preflight (repeat before EVERY deployment)
```bash
python3 scripts/mainnet_preflight.py --check-all          # 12 mainnet RPC sweep
python3 scripts/mainnet_preflight.py --chain arbitrum     # full gate per chain
python3 scripts/mainnet_preflight.py --chain 0g --deploy-key DEPLOY_0G_PRIVATE
```
The gate FAILS the run if: key missing/malformed, deployer is the tainted
wallet, deployer unfunded, chainId mismatch, or critical contract sources
missing. **Never bypass it.**

---

## Phase 2 — Observation-Only Mainnet (months 0–6)

Per the whitepaper's own bootstrap protocol — TRION **does not emit signals**
until INIT_valid. This phase builds D(t) honestly.

1. Deploy **publication-only** contracts (OracleV3, ExecutionGate) from the
   fresh key on the bootstrap chain set (Arbitrum, Base, Optimism, Polygon,
   Ethereum). These hold no funds — exposure is minimal while depth accrues.
2. Start the indexer fleet (registry chains, public RPCs, failover rotation):
   `node scripts/trion_master_indexer.mjs` + Rust indexers.
3. Keep services running: `docker-compose up -d` (healthchecks + restart
   policies already configured).
4. Monitor: Prometheus (`deploy/monitoring/`), `/api/v1/health` probes.
5. **Do not deploy BTCPEscrow. Do not route value.** Bootstrap-phase security
   is classical (multi-sig + rate-limit) per §L4.7; value transfer waits for
   the living-security transition.

Progress gate (check anytime):
```bash
curl -s localhost:5000/api/v1/bootstrap/status | jq '.akashic_depth, .stage'
```

---

## Phase 3 — Validator Network Formation (months 2–6, parallel)

- Recruit ≥100 independent operators across ≥4 continents
  (whitepaper §9.2 hardware spec: 32-core, 256GB, NVMe, HSM).
- Geographic enforcement is automatic: `/api/v1/governance/awa` and
  `compute_geo_enforcement()` block emission when concentration is violated.
- Validator onboarding runs the Go mesh: `validator/` (build+vet+test green).

---

## Phase 4 — INIT Ceremony + Signal Emission (month ~6)

All six whitepaper conditions must hold — the API enforces them:
```bash
curl -s localhost:5000/api/v1/governance/init    # INIT_valid state
curl -s localhost:5000/api/v1/governance/awa     # AWA_enforced must be true
curl -s localhost:5000/api/v1/bootstrap/status   # transition_complete: true
```
1. When D(t) ≥ 46,051 and validators qualify: execute the public INIT
   ceremony (witnessed, anchored in the Akashic Index — §14.1).
2. Enable the relayer with the funded RELAYER key (publication only).
3. Begin emitting signals; consumers integrate via the typed SDK
   (`sdk/`), SILENCE ≠ VALUATION enforced at their compile time.

---

## Phase 5 — BTCP Value Transfer (post-transition)

Only after Phase 4, with the audit clean and living security fully active:

1. Run preflight on both anchor and execution chains.
2. Deploy `BTCPEscrow` + `BTCPIntent` + `BTCPRoute` from the fresh key.
3. Verify source on explorers; record addresses in `proof-ledger/`.
4. Start with **capped-value pilot routes** (netting first — zero asset
   movement), then SPLIT routes, then BITP.
5. Monitor escrow health: `/api/v1/btcp/escrow_states`, alert webhook.

---

## Emergency Procedures

- **Signal freeze**: AWA auto-freezes emission on governance-condition
  violation — no action needed, by design.
- **Escrow stuck**: `revertEmergency()` is permissionless after 7 days
  (Gap 8 hatch) — users self-rescue; no admin key involved.
- **Key compromise**: rotating RELAYER key only affects new publications;
  escrows settle independently of the relayer.
- **Service down**: docker/systemd restart policies recover; the Akashic
  ledger is append-only SQLite + FAISS persisted on disk — no data loss.

## Never-Do List

- Never deploy from `0xdBbf66…42d20` (tainted history).
- Never disable the preflight gate.
- Never deploy BTCPEscrow before the audit and the D(t) transition.
- Never hardcode keys — the hardhat config now hard-fails mainnets without
  them, keep it that way.
