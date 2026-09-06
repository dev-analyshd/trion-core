# Security Audit — 26 Findings, Status After Fix Waves

**Task ID:** 9-c (consolidation of Task 6 red-team + Tasks 7-a…7-f / 8-a…8-c fix waves)
**Audit base:** upload/extracted/security_findings.md (26 findings, each verified at HEAD c0ccb14 with file:line evidence — read-only sweep)
**Fix waves:** 7-a (FAISS auth), 7-b (Cairo BIRP/lib.cairo/paths), 7-c (Flask fail-closed/CORS/SHA3/SSRF), 7-d (indexer integrity), 7-e (key hygiene), 7-f (escrow binding), 8-a (key threading), 8-b (hedera hash), 8-c (SILENCE/provenance — not a SEC finding, matrix-side). All changes live in the working tree (uncommitted; coordinator commit pending).
**Severity scale:** CRITICAL / HIGH / MEDIUM / LOW / INFO. Original severities from the red-team report are kept; resolution state is post-fix.

**Score after this session:** 14 of the 22 action-able findings FIXED (test-pinned), 2 already-fixed pre-audit (verified), 3 refuted/clean (verified), 6 open with documented residuals. Details per finding below.

---

## Consolidated table

| ID | Title | Sev | Original status | Resolution this session | Regression test |
|---|---|---|---|---|---|
| SEC-01 | FAISS service (:8000) fully unauthenticated, 0.0.0.0, host-published | CRITICAL | CONFIRMED | **FIXED (7-a/8-a)** — X-API-Key middleware all 165 routes; unset → fail-closed 503 on writes + privileged GETs; default bind 127.0.0.1; compose loopback-only; rate limit NOT added (residual) | tests/integration/test_faiss_auth.py (11/11) + E2E 18/18 |
| SEC-02 | derive-address.mjs prints raw EVM key + WIF to stdout | MEDIUM | CONFIRMED | **FIXED (7-e)** — stdout redacted; secrets only on stderr behind DEBUG_KEYS=1; export clause kept (no importers) | node --check + functional smoke (redaction + stderr gating proven with separated captures) |
| SEC-03 | Flask auth fail-open when TRION_API_KEY unset (181 routes) | HIGH | PARTIALLY CONFIRMED | **FIXED (7-c)** — fail-closed default: writes → 503 auth_not_configured; public GET reads kept; no public-write allowlist (none genuinely public) | tests/unit/test_api_auth_failclosed.py (19/19; was 8/19 failing-first pre-fix) |
| SEC-04 | BIRPAttestation ignores oracle_sig_r/s — self-attestable tiers | HIGH | CONFIRMED | **FIXED (7-b)** — Poseidon digest + core::ecdsa::check_ecdsa_signature vs storage-pinned pubkey; nonce replay burn; bridge signs real (r,s), fail-closed | tests/contracts/test_birp_attestation_cairo.py (69 checks, pytest 11/11; scarb 2.8.4+2.10.1 clean) |
| SEC-05 | Synthetic/substituted block hashes in indexers (BH §9) | MEDIUM | PARTIAL/CHANGED | **FIXED (7-d + 8-b)** — ton/pi/xrpl/multiversx/hedera now pass REAL chain hashes verbatim (toncenter root_hash, Horizon ledger hash, rippled ledger hash, MX hyperblock hash, Hashio block.hash); missing → warn + "0x0"; synthetic ids deleted | tests/golden/test_golden_vectors.py + tests/unit/test_chain_registry_canonical.py (150 passed, both waves) |
| SEC-06 | chains/starknet lib.cairo declares nonexistent module | MEDIUM | CONFIRMED | **FIXED (7-b)** — stale `pub mod cairo;` removed; comment points at contracts/starknet; module_root.cairo twin synced; crate now compiles (scarb 2.10.1 + 2.8.4) | static source assertions in test_birp_attestation_cairo.py + scarb build ✓ |
| SEC-07 | Relayer single-signature submission | MEDIUM | CONFIRMED (honest label) | **OPEN** — deliberate bootstrap disclosure; 7-of-12 multisig gated behind validator-network phase (runbook) | n/a (labels pinned by relayer.js:16-27 header + README honesty notes) |
| SEC-08 | ZK circuits: no zkeys, no trusted-setup ceremony | MEDIUM | CONFIRMED | **OPEN** — externally blocked (Powers-of-Tau ceremony); README honesty boxes unchanged | n/a (self-reported status boxes in zk-circuits/README.md) |
| SEC-09 | MAINNET_RUNBOOK TAINTED deployer note | INFO | CONFIRMED | No change — correct disclosure; enforcement intact (preflight blocklist scripts/mainnet_preflight.py:39-43) | preflight blocklist test path |
| SEC-10 | Hardhat key exposure history | LOW | CHANGED (remediated) | Verified already-fixed pre-audit (env-var + fail-closed mainnet, history purged, Hardhat #0 dev-key only); 7-e added adjacent hygiene | git blob check (oldest deploy blob shows ***REDACTED***) |
| SEC-11 | CosmWasm P1 recursion + multi-denom payout | INFO | CHANGED (fixed) | Verified already-fixed pre-audit (serde_json::from_slice; per-denom locked_coins, legacy multi-denom fails closed) | static verification (no cargo in sandbox) |
| SEC-12 | TON token u64 whole-unit supply vs decimals=18 metadata | LOW | CONFIRMED (TRUTHFUL-NOTE) | **OPEN** — documented unit hazard (caller-enforced invariant); fix = DECIMALS=0 or u128 re-base, deliberately deferred | TRUTHFUL-NOTE block in contracts/ton/token.fc:19-30 |
| SEC-13 | PQC downgrade test | INFO | REFUTED | No change — test asserts the correct protection; prior failure was missing libs (installed Task 3; baseline now includes it) | tests/adversarial/test_adversarial_matrix.py:126-132 (passing) |
| SEC-14 | Wildcard CORS (Flask + SocketIO) | LOW | CONFIRMED | **FIXED (7-c)** — flask_cors removed; headers only when TRION_CORS_ORIGINS set (exact-origin echo + Vary: Origin); SocketIO same policy | CORS assertions in test_api_auth_failclosed.py (no ACAO by default) |
| SEC-15 | Webhook SSRF guard literal-only | LOW | PARTIALLY CONFIRMED | **PARTIALLY FIXED (7-c)** — registration-time DNS resolution + private/reserved/non-global/multicast rejection, unresolvable = 400; delivery-time IP pinning still delegated to egress proxy (documented residual) | tests/unit/test_api_truth_boundaries.py (webhook cases, keyed; public-host success mocks resolver) |
| SEC-16 | ci.yml "ain, dev]" branch typo | INFO | REFUTED | No change — display artifact (od -c shows `[main, dev]`); matrix M-241 evidence corrected this session | od -c byte dump |
| SEC-17 | botchain MEV byte 17 (canonical 16) | MEDIUM | CONFIRMED | **FIXED (7-d)** — 17u8→16u8; dead fallback removed | #[cfg(test)] mev_detection_uses_canonical_byte_16 + hash_dna.rs pin (cargo run pending — RISK_REGISTER) |
| SEC-18 | Waves Burn→UPGRADE misclassification | MEDIUM | CONFIRMED | **FIXED (7-d)** — arm 16→14 (BURN); unreachable corrective deleted | static + golden vectors (150 passed) |
| SEC-19 | Cosmos proposer-fallback synthetic tx-BH (mag 0.5) | MEDIUM→LOW | CONFIRMED | **FIXED (7-d)** — magnitude 0.5→0.0 (utxo coinbase convention); synthetic proposer entry skipped + warn; et name canonicalized | static + golden vectors (150 passed) |
| SEC-20 | SHA-256 vs SHA3-256 in on-chain publish path | MEDIUM | CONFIRMED | **FIXED (7-c)** — _entity_to_bytes32/_commitment → hashlib.sha3_256 (write+read share helpers; contract stores opaque bytes32) | tests/unit/test_api_publish_hashing.py (6 golden vectors, SHA3-256) |
| SEC-21 | Same certificate pays 2× across two escrow deployments | HIGH | CONFIRMED (pinned broken) | **FIXED (7-f)** — escrow-bound digest escrowBoundEthDigestOf(P, address(this)); per-escrow nonce registry kept; oracle plain-digest path untouched | tests/adversarial/test_red_team_wave4.py::test_same_cert_double_pay_across_two_deployments — FLIPPED to regression (second deployment reverts, paid==amount); wave4 46P/pass3 9P/final_red_team 26P; tests/contracts 69P |
| SEC-22 | .env.railway tracked by git | LOW | CONFIRMED | **FIXED (7-e)** — git rm --cached + .env.railway.example created + .gitignore rules (ignore real, un-ignore example) | git check-ignore verification (both directions) |
| SEC-23 | Secrets/gitignore sweep | INFO | CLEAN | No change — clean at HEAD; re-verified during fix waves (no new secrets introduced) | repo-wide scans (7-a/7-c hygiene passes) |
| SEC-24 | Unauthenticated PQC signing oracle | MEDIUM | CONFIRMED | **FIXED (7-a)** — /api/v1/pqc/sign under the FAISS auth matrix: keyed 401, unset 503 (never unauthenticated); message domain separation NOT added (signs caller payload once keyed — residual noted) | test_faiss_auth.py (pqc/sign 401→200 keyed; 503 unset) |
| SEC-25 | 4 starknet test scripts read missing deployments file | INFO | CONFIRMED | **FIXED (7-b)** — path → docs/deployments/evm_sepolia.json + graceful skip+exit(0) when absent; scripts run past load to their documented env gates | static path assertions + bun execution past deployment load |
| SEC-26 | CRISPR _signatures AttributeError (stress Bug 1) | INFO | CHANGED (fixed) | Verified already-fixed pre-audit (`_library` attr); **Bug 2 residual OPEN** (fork/resurrection/convergence 0% under 60s load, ~13 rps write ceiling — event-loop blocking) | tests/unit/ANIMA_STRESS_REPORT.md documents both |

**Counts:** 26 findings — FIXED this session 14 (SEC-01/02/03/04/05/06/14/15*/17/18/19/20/21/22/24 + SEC-25; *partial) · already-fixed pre-audit (verified) 3 (SEC-10/11/26-bug1) · refuted/retired 2 (SEC-13/16) · clean 1 (SEC-23) · disclosure-only/no-change 1 (SEC-09) · **OPEN 5** (SEC-07, SEC-08, SEC-12, SEC-15-delivery-residual, SEC-26-bug2) — plus the SEC-24 domain-separation residual and the SEC-01 rate-limit residual recorded below.

---

## Open findings (detail)

### SEC-07 — Relayer single-signature (MEDIUM, OPEN)
`relayer/relayer.js:16-27` — the relayer submits exactly ONE signature (its own); only passes where quorumRequired==1. Compromise of the one key/process = unilateral signal publication. Fix = 7-of-12 relayer multisig, gated behind the validator-network phase per the mainnet runbook. Kept as an honest label; not a code bug.

### SEC-08 — ZK circuits without zkeys / ceremony (MEDIUM, OPEN)
`zk-circuits/` ships 5 Circom sources + README, no zkeys/r1cs/ptau/verification keys. Deployability gap, disclosed ("self-reported and NOT reproducible"). Requires a real Powers-of-Tau multiparty ceremony — external work, cannot land in-repo.

### SEC-12 — TON u64 whole-unit supply vs DECIMALS=18 metadata (LOW, OPEN)
`contracts/ton/token.fc:19-30` — total_supply is u64 whole units; per-address balances are TVM coins (can hold 18-decimal raw). Mixing invariant is caller-enforced. TRUTHFUL-NOTE documents it; fix (DECIMALS=0 or u128 re-base) deliberately deferred.

### Residuals on fixed findings
- **SEC-01 (rate limiting):** the FAISS service still has no rate limiter (Flask has 300/60s/IP). Auth now blocks the poisoning paths; a keyed-but-abusive client is unthrottled. The 8-a follow-up (core/physical/transduction_integrity.py unkeyed FAISS calls) was closed by a parallel lane during this session — verified in the working tree (`_faiss_headers()` :39, attached :159/:171/:194) with golden/registry still 150P.
- **SEC-15 (delivery-time pinning):** registration-time DNS check added; each delivery still resolves/fetches through the egress path — full rebinding protection (pin resolved IP per delivery) belongs at the egress proxy. Documented in-code.
- **SEC-24 (message scope):** the PQC signing endpoint is authenticated but still signs caller-supplied messages (no type-tagged domain separation). Keyed callers only; oracle key is ephemeral per boot.
- **SEC-26 Bug 2 (availability):** fork/resurrection/convergence endpoints 0% under 60s load (sync handlers block the event loop, ~13 rps write ceiling). Needs run_in_executor/threadpool conversion — not attempted this session.

---

## Verification boundary (honest limits)

- Rust fixes (SEC-05/17/18/19 + SEC-06 BIRP compile) verified: full-file reads, byte-map cross-checks against the Python EventType enum + CANONICAL_BH §9, brace/paren balance, scarb builds where the toolchain exists (installed 2.8.4/2.10.1). **cargo build/test on indexers/ was NOT run — no cargo in sandbox** (mandatory follow-up; the botchain regression test module is hand-verified only).
- EVM fixes (SEC-21) compile under BOTH toolchains: solc 0.8.24 via_ir (solcx) and solcjs 0.8.36 via the repo's own `node evm-tools/compile.mjs` (artifacts regenerated; pre-flight reproduced committed artifacts byte-for-byte except updatedAt, proving toolchain fidelity). Vyper 0.3.10 escrow tier clean.
- TS fixes (SEC-02/04-bridge/25): node --check / bun execution / tsc error-set diff vs pristine tree (no new type errors).
- Every FIXED claim above names its regression test; the full-suite run that would re-baseline everything is recorded in FINAL_TEST_REPORT.md (pending final run).
