# RED-4 — Independent Red-Team Pass 4: Exploit Reproduction + Fresh Attack Surface

**Task ID:** RED-4 (Team H, master command §26/§27/§28)
**Repo:** /home/z/trion-core @ HEAD `c6c38e4e199b683c1e0cd381a7187289d82726fc` (read-only; `git show` for all pre-fix code)
**Harness:** py-evm via eth-tester + web3 + py-solcx 0.8.24 (viaIR), vyper 0.3.10, Flask test_client, real subprocesses for cross-process tests. All attack scripts throwaway under `/tmp/red4/`; zero repo modifications.

Method: every exploit below was **actually executed** — pre-fix code extracted with `git show <sha>:<path>`, compiled/deployed (or imported) OUTSIDE the repo tree, attacked (EXPLOITED confirmed), then the **identical attack** run against HEAD c6c38e4.

---

## PART 1 — SECURITY REGRESSION: ORIGINAL EXPLOIT REPRODUCTION (§26)

### 1. Route-spoof — escrow locked with an unrelated currently-safe routeId, then released
* **Pre-fix code:** `BTCPEscrow.sol` + `TRIONOracleV3.sol` at `6403a84^` (the H1 finding: *"a quorum-safe verdict for any unrelated route could release any escrow"*). 5496458 later closed the residual verdict-store trust with canonical certificates + registry weights. Both stages verified.
* **Attack run:** oracle quorum (owner + 1 registered validator = `quorumRequired=2` distinct attestors) marks route `R` safe via `publishBTCPRoute` — `R` is **unrelated** (its `anchorBH` is a foreign intent's anchor). Relayer locks escrow E1 (1 ETH) with `routeId = R`, then escrow E2 the same way. `verifySettlementCheck` + `releaseEscrow` on both.
* **OLD result: EXPLOITED.** `verifyExecution(R)` → `(true, 900000, 800000)`; E1 **released 1 ETH to destination** and E2 **released 1 ETH from the same verdict** — route substitution + one-verdict-pays-many-escrows, 2 ETH drained with one unrelated quorum-safe verdict. (`_consensusGate(routeId, minCoherence)` had no escrow binding, no attestation count, no freshness.)
* **NEW result: BLOCKED.**
  * Legacy path: `ORACLE_ROUTE_NOT_BOUND_TO_ESCROW` (anchorBH ≠ escrowId), 0 wei paid.
  * Canonical path, cert carrying the unrelated route: `CERT_ROUTE_MISMATCH`.
  * Canonical path, cert bound to a foreign escrow: `ESCROW_NOT_FOUND`.
  * Positive control: a cert matching the escrow's own tuple **settles** — the gate is precise, not blanket.
* **Verdict: CLOSED.**

### 2. svm-native btcp_escrow RELEASE with no authority (deleted crate)
* **Pre-fix code:** `contracts/svm-native/programs/btcp_escrow/src/lib.rs`, readable via `git show 5c9584f^:…` (deleted in 5c9584f "fix(p0): repair the six production-breaking bugs"). **Rust — not compiled here** (documented from source, per mission).
* **Exploit path (precise):** `process_instruction` RELEASE arm (discriminator `2`):
  1. Accounts parsed: config, "relayer", escrow, vault, **destination**, system. **No authority check exists** — the `relayer` account is never compared to `config.relayer`, is never required to be a signer, and `config`/`config.owner` are never consulted.
  2. Gates: `escrow.state == 0` (HOLDING), `clock.slot <= lock_slot + timeout_slots`, and `coherence = u64::from_le_bytes(instruction_data[0..8])` — a **caller-supplied u64** — must be `>= escrow.min_coherence`. Attacker sends `u64::MAX`. No certificate, no signature, no validator set, no quorum.
  3. Effects: `escrow.state = 1`, then `invoke_signed(system_instruction::transfer(vault, destination.key, escrow.amount))` — note the payout goes to the **instruction-supplied `destination` account**, not even the escrow's stored `destination` field: any key can drain any HOLDING escrow pre-timeout to any recipient.
  * (Adjacent hazard in the same crate: `LOCK` seizes `vault_funder.lamports()` — the funder's entire balance — later fixed by dbebd91.)
* **HEAD state:** `git ls-files | grep svm-native` → **0 files** (crate absent from the tree). The live SVM tier `contracts/svm/programs/btcp_escrow/src/lib.rs::release_escrow` (line 888) requires the full canonical §6 certificate sequence (structure/epoch/registry/freshness/Ed25519SigVerify precompile introspection/registry-weight quorum/tuple binding/consumed-cert nonce); the old single-key release-authority is documented REMOVED.
* **Verdict: CLOSED (deleted + replaced by certificate-gated release).**

### 3. P-PY-01 — NaN magnitude forges the maximum
* **Pre-fix code:** `core/primitives/behavioral_hash.py` at `411f295^`, executed from a /tmp copy.
* **Attack run:** `canonical_magnitude_norm(float('nan'), 18)`.
* **OLD result: EXPLOITED.** NaN poisons every comparison (`NaN <= 0` → False), `min(1.0, nan)` → **1.0**; `compute_behavioral_hash` serializes `magnitude_nano = 1_000_000_000` — the **top of the 8-byte nanounit field** — from malformed input (a NaN `magnitude_raw` forges a maximum-magnitude behavioral event).
* **NEW result: BLOCKED** — `ValueError: canonical_magnitude_norm: NaN magnitude is malformed input` (fail-closed, malformed input rejected); sanity: legitimate magnitudes (12345/18d → 1.8e-15) still work.
* **Verdict: CLOSED.**

### 4. P-API-02 — unauthenticated GET write
* **Pre-fix code:** `api/app.py` at `4205fd3^`, imported as a full Flask app in /tmp (repo root on sys.path for its deps), `TRION_API_KEY` set, relay/0G-module writes instrumented.
* **Attack run:** `GET /api/v1/publish/attacker-entity` and `GET /api/v1/zg/da/submit?id=attacker-entity` with **no X-API-Key**.
* **OLD result: EXPLOITED.** The key gate whitelisted every GET (`if request.method in ("GET", "HEAD", "OPTIONS"): return None`) while these routes answered GET with side effects: **200 + real `relay.publish_signal(...)` call (on-chain publication) + SSE feed push**, and **200 + `_run_zg_module('da_submit', …)` (0G DA submission)** — unauthenticated on-chain and external-DA writes.
* **NEW result: BLOCKED** — both GETs → **401**, write functions never called; POST without key → 401; correct key → 200 (gate precise).
* **Verdict: CLOSED.**

### 5. P-VY-01 — Vyper release after timeout
* **Pre-fix code:** `contracts/vyper/BTCP_ESCROW.vy` at `984087e^` (expiry guard landed in 1270c5c), compiled with vyper 0.3.10, deployed on py-evm with a minimal TRIONOracleV3 mock exposing `routeBinding`/`minRouteAttestations`.
* **Attack run:** lock 1 ETH with `timeout_blocks=5`, mine 8 blocks (past expiry), then submit a **fresh** quorum-safe verdict bound to the escrow and call `release()`.
* **OLD result: EXPLOITED.** `release()` had **no block-number expiry check** — the fresh late verdict **paid the destination 1 ETH** (state → RELEASED), voiding the funder's timeout refund protection.
* **NEW result: BLOCKED** — `execution reverted: BTCP: escrow expired`, destination paid 0, state stays HOLDING; the funder-protection path (`revert_on_timeout`) refunds the funder instead.
* **Verdict: CLOSED.**

### 6. P-PY-06 — cross-process per-entity nonce collision
* **Pre-fix code:** `core/btcp/orchestrator.py` + `core/btcp/state_store.py` at `49f368e^`, loaded from a /tmp package (`/tmp/red4/oldpkg`) so the plain-name fallback import picks the OLD store; `zk`/`adapters` resolved from the repo. Two **real subprocesses**, each with its own orchestrator/store connection/lock, deterministic read-done handshake on `load_all(ENTITY_NONCE_KIND)` (the pass-2/pass-3 methodology).
* **Attack run:** seed process mints nonce N; both workers create distinct routes for the same entity.
* **OLD result: EXPLOITED.** Both processes minted **the same nonce** (N+1 = 1849356432): the second process's DISTINCT intent (different amount + intent_id) had its `btcp_cross_chain_messages` row **silently dropped** by the `(sender, source, target, nonce)` UNIQUE index — 2 rows where 3 belong, no error anywhere (destination replay-guard treats intent 2 as a replay of intent 1).
* **NEW result: BLOCKED** — same two-process attack on HEAD: distinct nonces (…220, …221) and **all 3 message rows** land (store-side `next_entity_nonce` inside `BEGIN IMMEDIATE`).
* **Verdict: CLOSED.**

**PART 1 TOTAL: 6/6 reproduced on pre-fix code, 6/6 blocked at HEAD with the correct reasons → 6/6 CLOSED.**

---

## PART 2 — FRESH ATTACK SURFACE vs HEAD (§27)

11 attacks attempted (all executed live). 9 defended; **1 NEW exploit**; 1 residual re-confirmed.

| # | Attack (§) | Target | Result at HEAD c6c38e4 | Verdict |
|---|---|---|---|---|
| a | Certificate equivocation across EPOCHS: epoch-1 validators retired by epoch-2/3/4 registration; epoch-1 cert on new escrows; cert claiming epoch-2 signed by epoch-1 keys | EVM `TrionEpochRegistry`+`BTCPEscrow.releaseEscrowCanonical` | Old-epoch cert settles **only within the 2-epoch grace window** (`latestEpoch - epoch <= epochGrace`, bounded ≤ 10 — documented rotation semantics); wrong-epoch keys → `SIGNER_NOT_IN_EPOCH_SET`; beyond grace → `VALIDATOR_EPOCH_INACTIVE`; control epoch-1 cert settles its own escrow | DEFENDED (grace is documented + bounded) |
| b | TTL boundary off-by-one: `now == issued+ttl`, `+1`; `issued == now+60`, `+70` | `CanonicalCertificate.checkPayload` (payload offsets 330/338, CLOCK_DRIFT_TOLERANCE=60) | Boundary is exact: at `issued+ttl` → settles (spec `now ≤ issued+ttl`); at `+1` → `CERT: expired`; at tolerance edge (+60) → settles; beyond (+70) → `CERT: future-dated` | DEFENDED — no off-by-one |
| c | Weight-quorum `s·d/1e6` truncation: 3 validators × (s=1_500_000, d=999_999) → w_j floors to 1_499_998 (exact 4_499_995.5), tier-1 strict 2/3 boundary | py `EpochSet`/`EpochSetEntry.effective_power` vs Solidity `registerEpoch`+`quorumMet` | **Identical arithmetic both sides**: total power 4_499_994 py == sol (both floor); 2-of-3 at exact 2/3 → py `quorum_met=False` AND EVM revert (first `BELOW_MIN_SIGNERS` — the ≥3 signer floor, then quorum would fail); 3-of-3 → both pass. No producer/verifier divergence, no rounding-up anywhere | DEFENDED — consistent fail-closed rounding |
| d | **AWA freeze bypass** across every publication surface (§27-d) | `api/app.py` 0G handlers + `core.governance.awa.EmissionGate` | **NEW EXPLOIT — see RED-4-F1 below** | **EXPLOITED (MEDIUM)** |
| e | Malformed-input fuzz: negative timestamps, chain_id > u32, negative magnitude, non-hex ids, huge ints, bad planes on POST `/api/v1/btcp/hash_dna`, `/api/v1/btcp/route`, `/api/v1/btcp/coherence_7plane` | API BTCP endpoints | u32 overflow → 400 `int too big to convert`; negative ts/amount → 400; non-hex block_hash → 400; decimals out of range → 400; route endpoints → `no_valid_route` (route None); **zero 5xx**; documented string→keccak coercion for non-hex entity ids (deterministic, no aliasing) | DEFENDED — fail-closed everywhere |
| f | SQLite row corruption: garbage JSON payload in `btcp_state` route row + corrupted `payload_hash` in messages projection | `BtcpStateStore.load_all` / orchestrator restart | Corrupt rows **skipped** (store: "rebuildable cache, never crash startup"); orchestrator restart exit 0, malformed route skipped with stderr note; semi-corrupt (JSON-valid, schema-broken) rows also skipped | DEFENDED — honest skip, no crash |
| g | FAISS index corruption: truncated copies (50%/10%) of `akashic_faiss.index` | `faiss.read_index` / `anima-service/faiss_service` import | `RuntimeError` (fail-loud) on read; `faiss_service` **refuses to boot** (exit 1) with a corrupted index — no silent wrong vectors served | DEFENDED — fail-loud |
| h | Certificate replay across two different escrowIds (same chain, same tuple otherwise) | `releaseEscrowCanonical` binding key + consumed-nonce | Cert for escrow-A settles A only; resubmission pays **0** (idempotent nonce consumption); escrow-B **HOLDING, untouched** (lookup keyed by cert `escrow_id`) | DEFENDED |
| h′ | Same cert double-pay across **two escrow deployments on one chain** (identical tuple) | cert payload carries chainid but **no escrow-contract address** | The same valid quorum cert settled escrow deployment A **and** deployment B — destination paid **2× the certified amount** from one validator authorization (matches wave4's pinned `paid == 2*amount` TODO test, still passing at HEAD) | **RESIDUAL re-confirmed** (MED-LOW; requires the same relayer-controlled tuple locked on ≥2 same-chain deployments) |
| i | XFF spoofing on the rate limiter (edf4e5f claim: trusted-proxy-only, last entry) | `_get_client_ip` + `_rate_limit` | Default (`TRION_TRUST_PROXY` unset): 310 spoofed-XFF requests → all keyed on **one** socket-addr bucket, 429s fire — spoof ignored ✓. `=1`: last-entry trusted, multi-hop `"1.2.3.4, 5.6.7.8"` → key `5.6.7.8` (parsed correctly); direct-client bucket-choice residual confirmed (documented opt-in) | DEFENDED at default; opt-in residual as documented |
| j | Front-run / griefing probes: `verifySettlementCheck` hash overwrite, `lockEscrow` 1-wei griefing | `BTCPEscrow` | `verifySettlementCheck` is `onlyRelayer` + write-once (`ALREADY_VERIFIED`) — non-relayer cannot front-run or burn a bogus hash; `lockEscrow`/`enterPendingAkashic` relayer/owner-gated; `revertEmergency` is the only permissionless value path (by design, 7-day hatch) | DEFENDED |

### RED-4-F1 — NEW EXPLOIT: AWA emission freeze not enforced on three 0G publication surfaces (P-API-05 incomplete remediation)
* **Severity: MEDIUM** (authenticated — requires a valid API key; same class/rating as the original P-API-05 finding).
* **Where:** `api/app.py` — `zg_storage_store` (~line 2630), `zg_sync_trigger` (~line 2532), `zg_compute_infer` (~line 2707). No `assert_emission_allowed` call in any of the three handlers.
* **Reproduced live (Flask test_client, `get_emission_gate().freeze(...)` first, valid API key supplied):**
  * `GET/POST /api/v1/zg/storage/store` → **200, `storage_store` job executed** — behavioral-signal data (attacker-controlled on POST) published to 0G storage **while the protocol-wide emission gate is frozen**.
  * `GET /api/v1/zg/sync` → **200, 0G mainnet sync subprocess spawned** while frozen.
  * `GET /api/v1/zg/compute/infer` → **200, external compute job executed** (entity + prompt) while frozen.
  * Controls in the same run: `/api/v1/publish/*` → 503 silence ✓, `/api/v1/zg/da/submit` → 503 ✓ (P-API-05's fix covered **only** da/submit).
* **Why it's a miss:** the final-pass P-API-05 report (tests/adversarial/test_final_red_team.py:72) explicitly named **both** `/api/v1/zg/da/submit` **and** `/api/v1/zg/storage/store`; the landed fix and its pin test cover only da/submit. edf4e5f later added auth gating (P-API-03) for sync + compute/infer but no AWA gate. MD §17 "truth publication fails closed" is therefore still bypassable on three surfaces.
* **Fix direction:** call `assert_emission_allowed("VALUATION")` (with the 503 silence envelope) at the top of `zg_storage_store`, `zg_sync_trigger`, `zg_compute_infer` — or one shared pre-write hook for all `_WRITE_PATHS`.

---

## PART 3 — FAILURE INJECTION MATRIX (§28)

Injection via Flask test_client (dead `FAISS_SERVICE_URL`, dead chain RPC), direct EVM calls, and subprocess module loads. **Every release/publication path failed closed; the valid path still works (control).**

| Injected failure | Surface probed | Observed behavior | Fail-closed? |
|---|---|---|---|
| FAISS service unavailable (dead port) | `GET /api/v1/bh/ledger/<id>` | **503**, `bh_records: []`, error surfaced | ✅ |
| FAISS service unavailable | `GET /api/v1/signal/<id>` | **400** `invalid_entity_id` (input validated before any data path) | ✅ |
| FAISS service unavailable | `POST /api/v1/continuum/settlement` | 200 with `triggered=False` / gate not verified — no settlement | ✅ |
| FAISS service unavailable | `POST /api/v1/btcp/route` | 200 `reason=no_valid_route, route=None` — no route emitted | ✅ |
| Ledger missing (FAISS down) | bh ledger route | covered above (503 + empty records) | ✅ |
| Chain/KMS provider bogus (dead `ARB_SEPOLIA_RPC`) | `GET /api/v1/publish/<entity>` | 200 with `chain.published=False` + honest "relay not configured" error; **no partial on-chain write, no crash** | ✅ |
| Oracle / epoch registry unregistered | `releaseEscrowCanonical` (cert for epoch 1, none registered) | revert **`VALIDATOR_EPOCH_INACTIVE`** | ✅ |
| Quorum unmet (3-of-5 signers, signed power 3M) | `releaseEscrowCanonical` | revert **`WEIGHT_QUORUM_UNMET`** | ✅ |
| Freshness expired (issued 2h ago, ttl 1h) | `releaseEscrowCanonical` | revert **`CERT: expired`** | ✅ |
| Threshold provenance lie (cert θ 999_999 vs registry 550_000) | `releaseEscrowCanonical` | revert **`CERT: not safe`** (coherence 900k < fake θ rejected at the safety precondition — fail-closed before any value moves) | ✅ |
| Chains-registry file unreadable | `api/chains_registry` import | **fail-loud `ImportError`** ("canonical registry not readable … never serve stale counts") — no stale figures served | ✅ (fail-loud) |
| SQLite row payload corrupted | `BtcpStateStore.load_all` / orchestrator restart | corrupt rows skipped, clean restart, stderr note per malformed route | ✅ (honest skip) |
| FAISS index file corrupted/truncated | `faiss_service` import | **service refuses to boot** (exit 1, RuntimeError) — no silent wrong vectors | ✅ (fail-loud) |
| Control: no failure (valid cert, live deps) | `releaseEscrowCanonical` | settles; publish with correct key works | gate precise ✅ |

**PART 3 VERDICT: 13/13 injected failures fail closed (2 fail-loud by design: registry import, FAISS boot); 0 fail-open.**

---

## Summary

* **Part 1:** 6/6 historical exploits **reproduced on pre-fix code and blocked at HEAD** for the correct reasons → regression status **6/6 CLOSED**.
* **Part 2:** 11 fresh attacks: 9 defended, **1 NEW exploit (RED-4-F1, MEDIUM — AWA freeze bypass on `zg/storage/store`, `zg/sync`, `zg/compute/infer`)**, 1 residual re-confirmed (same-cert double-pay across same-chain escrow deployments — already pinned by wave4's TODO test).
* **Part 3:** 13/13 failure-injection cases fail closed.

Evidence scripts (throwaway): `/tmp/red4/exp1_route_spoof.py`, `exp3_nan.py`, `exp4_api_get_write.py`, `exp5_vyper_timeout.py`, `exp6_nonce_xproc.py` (+ `nonce_worker.py`), `p2a_fresh_evm.py`, `p2b_fresh_api.py`, `p2e_fuzz.py`, `p2i_xff.py`, `p3_injection.py`. Pre-fix sources under `/tmp/red4/old/` (git show extraction).
