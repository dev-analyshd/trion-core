# Risk Register — Remaining Risks After the Fix Waves

**Task ID:** 9-c · **Write time:** 2026-09-05, after fix waves 7-a…7-f / 8-a…8-c and a parallel lane (cold-start/CEX-forward/indexer-remainder fixes — observed in the working tree at write time, regression tests re-run green by this agent). **Refreshed 10-b** after waves 9-a…10-b (R-15 closure, R-20…R-22 additions, final-suite state) — then **independently re-verified by the 10-b final-verification pass**: the full-suite re-run reproduced **1831P / 2F / 27S / 1x / 1E identically** (485.55s vs the original 463.16s), the tron `blockID` fix re-checked (field match vs `fetch_tron_block` + brace balance 58/58·47/47·216/216), the two-chain BH-ledger experiment re-run (`per_chain {solana: 1, ethereum: 1}` — distinct tx hashes; a shared tx hash dedups by design), and R-22's grep re-confirmed (0 X-API-Key matches under core/{trading,agent,auditor,akashic}). Fix-wave changes were committed by **10-c** as a 9-commit hardening series and pushed to origin/main (R-19 closed).

Risk IDs below are this register's own (R-*); SEC-* refer to SECURITY_AUDIT.md; M-* to REQUIREMENTS_MATRIX.md.

---

## 1. Externally-blocked (cannot close inside the repo/sandbox)

| ID | Risk | Blocks | Evidence / gate |
|---|---|---|---|
| R-01 | **cargo verification gap** — all Rust edits this session (5 indexer hash fixes + hedera + event-byte fixes + botchain regression module + faiss.rs key headers + the parallel lane's 6 more crates) are hand-verified only; no cargo build/test ever ran | indexers/, rust/ trion-btcp, contracts/{cosmwasm,svm,ink} | no cargo in sandbox (worklog Tasks 3/7-d/8-a/8-b); mandatory follow-up: `cargo check && cargo test` in indexers/ and rust/ |
| R-02 | **Go verification gap** — validator/ + network/ statically verified only (36 tests never executed here) | validator fleet software | no go toolchain in sandbox |
| R-03 | **ZK trusted-setup ceremony** — no zkeys/r1cs/ptau/verifiers; circuits unverifiable (SEC-08) | M-145/209/211, sensing-oracle ZK leg, IAP privacy | requires real Powers-of-Tau MPC — external coordination |
| R-04 | **Validator fleet** — no live validators; emission is single-signature relayer (SEC-07); certificate emission-side signing has no producer | M-184, M-185, M-247–M-252, M-288, falsification windows, quorum reality | registry launch gate exists; fleet is operational work |
| R-05 | **Funded custody / live value legs** — no funded escrows; BTC legs simulated; escrow-bound cert fix is test-proven, not value-proven | any mainnet escrow release | MAINNET_RUNBOOK gates |
| R-06 | **Professional audit** — runbook REQUIRES it before mainnet; this session is an internal audit, not a substitute | mainnet (M-288) | docs/MAINNET_RUNBOOK.md gates: audit, 6-month observation-only, ≥100 validators, INIT ceremony, fresh deployer key |
| R-07 | **Live-chain legs** — indexer RPC streams, relayer submissions, deployments are testnet/self-reported; the "34,600 vectors / deployed contracts" figures are self-reported | any live-operations claim | deployment records "unverified — self-reported"; one fabricated Solana devnet record was purged historically |

## 2. Known residuals (open, in-repo)

| ID | Risk | Status at write time | Evidence |
|---|---|---|---|
| R-08 | **SEC-15 delivery-time SSRF pinning** — webhook registration resolves + rejects private/non-global IPs, but each delivery still resolves through the egress path (DNS-rebinding at delivery time) | OPEN (documented in-code; egress-proxy owned) | api/cex_integration.py `_resolve_webhook_ips` + residual comment |
| R-09 | **FAISS rate limiting** — auth closed the poisoning paths; no request-rate limiter on the FAISS service (Flask has 300/60s/IP) | OPEN | SECURITY_AUDIT.md SEC-01 residual |
| R-10 | **SEC-24 message scope** — PQC signing endpoint authenticated but signs caller-supplied payloads (no type-tagged domain separation) | OPEN (keyed callers only; ephemeral key) | faiss_service.py:5731 |
| R-11 | **SEC-26 Bug 2 availability** — fork/resurrection/convergence endpoints 0% under 60s load (event-loop blocking, ~13 rps write ceiling) | OPEN | tests/unit/ANIMA_STRESS_REPORT.md |
| R-12 | **SEC-12 TON u64 unit hazard** — whole-unit ledger vs DECIMALS=18 metadata; caller-enforced invariant | OPEN (TRUTHFUL-NOTE) | contracts/ton/token.fc:19-30 |
| R-13 | **SEC-07 single-sig relayer** — one key = unilateral publication on quorum-1 chains | OPEN (honest label; 7-of-12 multisig is the pre-mainnet fix) | relayer/relayer.js:16-27 |
| R-14 | **Python TON streamer tip-hash anchoring** — Python fetcher anchors ALL seqnos to the tip's root_hash; Rust now uses per-seqno hashes → Rust↔Python TON digests match only for the tip block | OPEN (Python path documented as not-the-real-path; cross-referenced SWEEP-B Wave-4 header + D3 residual) | worklog 7-d coordinator note; SWEEP-B.md:9,169 |
| R-16 | **Cairo contracts/starknet crate** — 34 pre-existing corelib-skew errors in 4 files: trion_certificate 17, btcp_escrow 15, BTCFiGuard 1, trion_epoch_registry 1 (felt PartialOrd, u32/u64 mismatches; corelib version skew) | OPEN — **status unchanged through 10-b**: chains/starknet compiles (SEC-06 fixed) and BIRPAttestation compiles clean in isolation (both scarb 2.8.4 + 2.10.1), but the contracts/starknet crate itself was never buildable in this environment; twin-pinned to contracts/cairo. Needs a cairo-owner migration pass (target scarb 2.10.1 corelib or pin 2.8.x consistently) | worklog 7-b; LANGUAGE_MATRIX.md |
| R-17 | **evm_extras supervisor gap** — test_evm_extras_supervisor_has_all_three_chains fails at HEAD (BNB_TESTNET missing from supervisors/evm_extras_indexers.sh) | OPEN (pre-existing, untouched) | worklog 7-d |
| R-18 | **INV-015 dispute window** — the repo's only xfail: on-chain 72h dispute window unenforceable | OPEN (honest) | tests, M-186 evidence |
| R-19 | **Commit closed (10-c)** — the session's hardening series has been committed (9 commits: faiss auth, api-side keys, flask surface, birp attestations, escrow binding, real block hashes, silence/provenance, private-key printing, master-audit docs) and pushed to origin/main; the 10-b tron §9 fix is included — still cargo-unverified until a `cargo check` run (R-01) | CLOSED 10-c — commits landed on origin/main on top of c0ccb14, working tree clean after push | git log origin/main |
| R-20 | **CEX BH construction diverges from canonical L0.1 recomputation** — the CEX lane builds its own sense/antisense pair (best-effort forward thread) instead of the canonical 93-byte payload + dual-strand SHA3-256; the ledger's `verified` complementarity counter therefore stays 0 for CEX-sourced records (and for suite fixtures that hardcode hexes) | OPEN — owner decision pending: either adopt canonical_bh construction on the CEX path or accept verified=0 for CEX rows (add_tx_bh_batch's context is already pinned to "0" per the in-code comment, faiss_service.py:3840-3842) | faiss_service.py:3833-3850; tests/unit/test_cex_faiss_forward.py (schema pinned, construction not) |
| R-21 | **Python cosmos fetcher parent-hash drift** — bh_streamer.py reads `header.last_block_id.hash` (the PARENT block) where the Rust trion-cosmos crate reads `block_id.hash` (current block) → the same cosmos block hashes differently on the two paths | OPEN (Python-side only; Rust path canonical since 10-a) | SWEEP-B.md:9,169 (D3 residual) |
| R-22 | **core/-side internal FAISS clients without key/env integration** — `core/trading/{live_feed,signal_engine,agent_interface}.py`, `core/agent/safety_pipeline.py`, `core/auditor/contract_auditor.py`, `core/akashic/genesis.py` still call the FAISS service with constructor-default URLs and no X-API-Key/`faiss_client` usage; against a keyed service they fail closed (safe posture, non-functional). Off the pytest import path (untested) | OPEN (fail-closed direction; migrate to api/faiss_client.py helpers — URL env + key chain already canonical in api/, bh_streamer, and all 19 genesis_backfill scripts) | rg "X-API-Key" core/{trading,agent,auditor,akashic} → no matches; api/faiss_client.py:29-44 |

### Closed during this session (recorded so future readers don't re-flag)

| Was | Closed by | Verification |
|---|---|---|
| **R-15 — SWEEP-B §9 crate arms (incl. Python APTOS stale key)** — the Python aptos fetcher's stale `previous_block_hash` key (silently degraded every block to "0x0") AND the last unassigned Rust §9 arm | 10-a (Python fetcher now reads the live `block_hash` field + `_synthetic_tx_sender` single-hash fix) and 10-b (trion-tron `blockID` verbatim, missing → warn + "0x0", synthetic `bh_id("tron_block:…")` deleted — the 21st/last crate) | golden + chain_registry 150P (10-a); field cross-check vs `fetch_tron_block`'s `blockID` read + lifetime/char/string-aware brace-balance check (10-b, re-verified: `{`=58/`}`=58, `[`=47/`]`=47, `(`=216/`)`=216); SWEEP-B §1 row, Wave-4 header, D3 all closed. **Cargo gap remains** (R-01 — toolchain absent in every wave, all 21 crate fixes static-verified only); the fix is committed and pushed (R-19 closed by 10-c) |
| CEX→FAISS forward schema drift (silent 422 since forever; 8-a flagged) | parallel lane (write-time observation) | _forward_to_faiss posts TxBhBatchPayload; tests/unit/test_cex_faiss_forward.py 5P (re-run by this agent) |
| Cold-start signal-route 500s (KeyError plane_breakdown; GOVERNANCE h[33] IndexError; 8-c flagged) | parallel lane | tests/unit/test_api_cold_start.py 8P (re-run by this agent) |
| transduction_integrity unkeyed FAISS calls (8-a follow-up) | parallel lane | `_faiss_headers()` :39 + attachments :159/:171/:194 |
| self_verification_routes FAISS_URL alias-only resolution (env drift) | parallel lane | FAISS_SERVICE_URL precedence in the working tree; tests/unit/test_self_verification_auth.py 11P (re-run by this agent) |
| SWEEP-B D3 remainder + vechain/algorand/cardano re-encode class (8-b flags) | parallel lane | 6 crates now verbatim-hash; golden + registry 150P re-run |

## 3. Contradiction register (pointers)

- **Repo-internal K1–K22 (+ R-BH-01, R-SG-05, R-CH-02, R-TK-01):** docs/audit/CANONICAL_SPEC_MATRIX.md — 22 recorded spec-vs-code conflicts resolved by the canonical reconstruction; spec-hygiene pass still recommended (worklog item 10).
- **New this session (Task 5 matrix): 19 doc-vs-doc contradictions** — REQUIREMENTS_MATRIX.md §CONTRADICTORY (M-002, M-006, M-008, M-021, M-053, M-054, M-059, M-072, M-073, M-110, M-168, M-172, M-181, M-195, M-203, M-233, M-277, M-293, M-296). None resolved by code fixes — they are documentation-level; a spec reconciliation pass is the only closure path.

## 4. Structural (not bugs — permanent until the fleet exists)

- Bootstrap planes Σ/K/A fixed values in some emission paths (M-110) — disclosed, engines real.
- TimescaleDB 17/35 declaration-only (M-215).
- Falsification conditions F1–F15 designed-not-operating (fleet-gated; matrix domain 13).
- ANIMA sub-scale (59 languages / 36 sources vs 1000-crawler spec).
- The four "proofs" are prose; Haskell Theorems is the strongest formal artifact.
- Governance vote/timelock mechanics (M-270/M-272) unimplemented.

## 5. Highest-leverage next actions (owner: coordinator)

1. ~~Run the final full pytest suite~~ **DONE (10-b, re-verified):** 1831P/2F/27S/1x/1E with FAISS+Flask live, reproduced identically by an independent verification re-run — the 3 remaining items are classified (a) GitHub rate-limit, (b) boot-deadline contention flake, (d) pre-existing beo coverage gap; zero session regressions (FINAL_TEST_REPORT.md final section). ~~Commit the session (R-19)~~ DONE (10-c — committed and pushed to origin/main).
2. `cargo check && cargo test` in indexers/ + rust/ (R-01) — the single largest unverified surface this session touched.
3. Cairo corelib migration pass for contracts/starknet (R-16).
4. Spec reconciliation pass for the 19 doc contradictions + K1–K22 hygiene (owner: docs conformance).
5. Fleet/ceremony/audit/funding gates per the runbook (R-03…R-07) — the only path to L10.
