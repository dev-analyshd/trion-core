# Execution Path Map — Critical Runtime Paths

**Task ID:** 9-c (Master Command §5/§29) · **Repo:** /home/z/trion-core @ c0ccb14 + this session's fix waves (working tree, coordinator commit pending)
**Method:** derived from the deep-read worklog (Tasks 4-a…4-i, 7) and the fix-wave entries (7-a…7-f, 8-a…8-c); every arrow below was re-confirmed against the current tree (grep on the cited entry points) at write time. Chain format per Master Command §5: ENTRY → VALIDATION → TRANSFORM → LOGIC → SECURITY → STORAGE → OUTPUT.

Read this alongside `REQUIREMENTS_MATRIX.md` (what should exist) and `SECURITY_AUDIT.md` (what was hardened this session). Paths describe code topology, not live operation — no validator fleet, relayer is single-signature, deployments are testnet and self-reported.

---

## Path 1 — Chain event → BH → FAISS ingest → behavioral engine → signal → oracle publication → consumer

**ENTRY**
- Rust indexers: `indexers/crates/trion-evm/src/main.rs:706 index_chain()` polls per-chain RPC (55 EVM chains configured; one crate per non-EVM family, 22 workspace members). Block-level 128-dim φ vector + per-tx rows per block (header comment, main.rs:15).
- Python streamer: `core/realtime/bh_streamer.py` — 61 EVM + 14 non-EVM family fetchers (TON/πXRPL/MX/Hedera… read the same real chain hashes the Rust fix waves now use; TON Python path anchors all seqnos to the tip root_hash — known divergence, Rust is per-seqno, see RISK_REGISTER).

**VALIDATION**
- Field reads per chain (block hash / timestamp / magnitude decimals) per `docs/audit/canonical-sweep/SWEEP-B.md` §1 table; missing block hash → warn + honest `"0x0"` (CANONICAL_BH §9 — enforced this session for ton/pi/xrpl/mx (7-d) and hedera (8-b); vechain/algorand/cardano still carry the older fallback pattern — open residuals).
- Chain-id consts pinned per crate and registry-checked (15 single-chain + 14 multi-chain ids match `config/chain_registry.json`).

**TRANSFORM**
- `trion_common::hash_dna::canonical_bh` (indexers/crates/trion-common/src/hash_dna.rs:227) — 93-byte preimage `entity[32]|type[1]|mag_nano[8]|ctx[8]|ts[8]|chain[4]|block_hash[32]`, dual-strand SHA3-256 (sense/antisense-XOR-NOT). Event byte table 0–19 pinned at hash_dna.rs:20-24 (botchain MEV=16, Waves BURN=14 fixed this session, 7-d).
- Golden vectors: `tests/golden/vectors.json` + `cross_language_canonical_bh_vector` (hash_dna.rs:495) — tri-language parity (Python/Rust/TS).

**SECURITY** *(changed this session)*
- FAISS submissions now authenticate: `FaissClient` (indexers/crates/trion-common/src/faiss.rs:135-190) resolves `FAISS_API_KEY` once and attaches `X-API-Key` on `add_batch`/`add_tx_bh_batch` (:159/:187); `is_healthy` stays headerless (public `/health`).
- Python streamer: `FAISSAccumulator._flush_buffer` (core/realtime/bh_streamer.py:535-604) resolves the same 3-var key order and attaches the header on flush.

**STORAGE**
- FAISS service (`anima-service/faiss_service.py`, FastAPI, 165 routes): `/index/add` (:3467), `/index/add_batch`, `/index/add_tx_bh_batch`, `/index/bulk_backfill` → `akashic_faiss.index` (IndexFlatL2→IVFPQ) + `bh_ledger.db` (SQLite WAL) + optional PG/TimescaleDB dual-write (psycopg2 guarded).
- 0G DA/storage blobs with on-chain commitments (data-availability leg).

**LOGIC (behavioral engine)**
- Φ(t) from the 9 entropy features; `anima-service` `_compute_signal` builds plane values; `core/master/signal_factory.py build_signal` (34-field TRIONSignal schema, 24-type registry) applies the master equation T(t)=[C(t)≥Θ(t)]·S(t)·e^(M_moat·t); SILENCE payloads now derive limiting_plane/eta (M-004 fix, 8-c: `_derive_silence_payload` at signal_factory.py:334, `ETA_BLOCKS_PER_GAP=1000` at :321); validator provenance layer 5 (`_load_validator_registry`/`_resolve_validator_figures`, :410/:435 — registry-first, no fabrication).
- AWA emission gate (`core/governance/awa`) can freeze ALL emission (503).

**OUTPUT (oracle publication)**
- Flask Oracle `api/app.py` (~181 routes): `/api/v1/signal/{entity}` (public GET — relayer polls exactly this, relayer/relayer.js:694), `/api/v1/publish/*` (write paths, keyed). Publish path hashes entityId/commitment with SHA3-256 (SEC-20 fix, api/blockchain.py:242/:252).
- Relayer (relayer/relayer.js): fetches signal → packs 256-bit `packedData` bit layout → builds EIP-191 quorum digest → `TRIONOracleV3.publishSignal(txId, packed, [sig])` (:611) — **submits exactly ONE signature (its own)**; only passes on quorum-1 chains (honesty label, relayer.js:16-27, SEC-07 open).
- Consumer: `ITRIONConsumer.consumeSignal` interfaces + 256-bit packed encoding (`core/primitives/signal_packing`); frontends poll the Flask API through Next.js server-side proxies; SDK `getSignal/subscribe/verifySignal`.

**End-to-end status:** wired and test-covered locally (integration tests pass when FAISS :8000 is up); live chain legs (indexer RPCs, relayer submits) verified only in testnet/self-reported mode.

---

## Path 2 — Intent → BTCP route → escrow release (escrow-bound certificate verification)

**ENTRY**
- `POST /api/v1/route` (Flask, keyed write) or direct core call → `core/btcp/orchestrator.py` 6-step pipeline (:1007-1013: validate addresses → create intent → encode for both VMs → estimate gas → ZK proofs → track route) + Step 0 registry membership (:1028).
- Intent object: `rust/src/types.rs Intent` / core BITPIntent (§4.1 field-complete).

**VALIDATION**
- Registry membership (chain_registry 129 chains / 18 VM families); address validation; behavioral balance reservation (S7 persisted, SQLite write-through — no double-spend across concurrent routes); unknown chain → OOA adapter fail-closed (no silent EVM routing).
- Route validity gate: BTCP_score>0.10 ∧ NL>0.05 ∧ finality>0.80 ∧ ≥3 validators (core/btcp/router + rust/src/btcp_router.rs, MIN_BTCP_SCORE=0.10 lib.rs:105).

**TRANSFORM / LOGIC**
- Route types (SingleChain/Split/Netting/Parallel/OOA/ZK_Private/Wait) selected by BTCP_score priority (NETTING 0.95–0.99 > SINGLE > SPLIT > PARALLEL > OOA > ZK > WAIT); BITP complement matching, BLO expiry, netting engine, escrow monitor state machine (INV-003 coherence floor 0.55, cascade revert).
- Certificates: 346-byte canonical certificate (TRION-CERT-V1, 25 fields) assembled at consensus tier; `core/consensus/certificate.py` deliberately does NOT sign (emission-side signing belongs to the validator fleet — none live).

**SECURITY** *(changed this session — SEC-21 fix, 7-f)*
- `BTCPEscrow._verifyCanonicalCertificate` (contracts/solidity/BTCPEscrow.sol:447) recovers signers over the **escrow-bound digest** `CanonicalCertificate.escrowBoundEthDigestOf(payload, address(this))` (CanonicalCertificate.sol:262-286): keccak(ESCROW_BINDING_DOMAIN ‖ escrowDeployment ‖ keccak(P)), domain = keccak("TRION-ESCROW-BOUND-V1"). A certificate signed for escrow A fails (BAD_CERTIFICATE_SIGNATURE/SIGNER_NOT_IN_EPOCH_SET) on escrow B — the same-chain 2×-pay clone attack is closed; per-escrow nonce/digest registry (§8) kept as additive defense; the oracle plain-digest observability path (submitCertificateAttestation) is intentionally untouched.
- Escrow-bound twin on the test side: `tests/contracts/sol_helpers.py:224-250` (ESCROW_BINDING_DOMAIN + optional escrow_address= signer param).

**STORAGE**
- `rust/` state_store (12 SQLite projection tables) + `schema.sql` BTCP 5-table DDL (blo_orders, bitp_clipboard, btcp_intent_registry, btcp_routes, btcp_escrow_states + shadow/genesis = 7 Phase-0 tables); intent registered on-chain by hash (`BTCPIntent.sol` + IntentRegistered).

**OUTPUT**
- `releaseEscrowCanonical` (BTCPEscrow.sol:369) — pays destination exactly once per (cert, deployment); Vyper tier `BTCP_ESCROW.vy` (oracle-attestation tier, untouched by the fix); other VM escrow tiers (SVM/Move/TON/cairo) verify the plain canonical digest still — deployment binding for those tiers is a recorded follow-up.
- Regression: `tests/adversarial/test_red_team_wave4.py::test_same_cert_double_pay_across_two_deployments` (:302) — pinned-broken pre-fix (`paid == 2*amount`), now asserts second deployment reverts, total paid == amount, escrowB stays HOLDING.

**End-to-end status:** routing logic test-covered (147 Rust tests, static verification only — no cargo in sandbox); value legs never exercised on mainnet (no funded escrows); testnet deployments self-reported.

---

## Path 3 — BIRP attestation (oracle signature verification)

**ENTRY**
- Recovery request / behavioral tier gating → `contracts/starknet/src/BIRPAttestation.cairo::submit_proof(commitment, tier, confidence_bp, attestation_nonce, (r,s))` — permissionless submission (the signature carries the authority).

**VALIDATION** *(changed this session — SEC-04 fix, 7-b)*
- Contract asserts: tier≤3, conf≤10000, !active (not revoked), oracle_pubkey≠0, nonce≠0, !used_nonces[nonce], r≠0, s≠0, `core::ecdsa::check_ecdsa_signature(digest, pubkey, r, s)` — digest = `poseidon_hash_span(['BIRP-ATT-V1', commitment, tier, confidence_bp, nonce])` (InternalImpl). Replay nonces burned AFTER verification (one attestation usable exactly once, survives revocation). Oracle STARK pubkey pinned via `constructor(oracle, oracle_pubkey)` or `set_oracle_pubkey` (oracle-gated, zero refused); `OraclePubkeyChanged` event; views `get_oracle_pubkey/nonce_used`.
- Signing leg: `chains/starknet/src/birp-bridge.ts` mirrors the digest (`computePoseidonHashOnElements`), signs with `starkCurve.sign`, fails closed without `BIRP_ORACLE_PRIVATE_KEY` — the old `(0,0)` placeholder submission is gone.

**LOGIC / OUTPUT**
- Downstream consumers of `verify_commitment`/`is_above_tier` (BTCFi gating style) can now trust the tier — a self-attested "SAFE" no longer stores. Python-side BIRP core (`core/novel/birp` 5-phase §16 state machine) is the enrollment/recovery brain; the cairo contract is the on-chain attestation tier.
- Regression: `tests/contracts/test_birp_attestation_cairo.py` — Python mirror of the assert chain + attacks (self-attestation, placeholder sigs, tamper, replay incl. cross-commitment-after-revocation, zero nonce, pubkey rotation, bounds) + static source pins; 69/69 checks, pytest 11/11. Compiles under scarb 2.8.4 AND 2.10.1 (isolated crate, version-portable core:: paths).

**End-to-end status:** contract + bridge + tests in place; not deployed (no BIRP entry in starknet_sepolia_deployments.json); oracle key ceremony for the pinned pubkey is operational, not code.

---

## Path 4 — API request paths (new auth posture: public reads / keyed writes)

**ENTRY** — any HTTP client → Flask Oracle `:5000` (api/app.py, ~181 routes) or FAISS service `:8000` (anima-service/faiss_service.py, 165 routes).

**VALIDATION / SECURITY** *(changed this session — SEC-03/14 fix, 7-c; SEC-01/24, 7-a/8-a)*

Flask Oracle (`api/app.py`):
- `TRION_API_KEY` SET: GET/HEAD/OPTIONS public; `_WRITE_PATHS` (:203 — /api/v1/publish/, zg/da/submit, zg/storage/store, zg/sync, zg/compute/infer) keyed on every method; other POST/PUT/PATCH/DELETE keyed (401 missing / 403 wrong / 200 right, hmac.compare_digest); `/api/v1/health` exempt.
- `TRION_API_KEY` UNSET (new default — fail-closed): `_writes_disabled_response()` (:220) → 503 `auth_not_configured` on ANY method hitting `_WRITE_PATHS` and on POST/PUT/PATCH/DELETE elsewhere (health exempt); GET/HEAD/OPTIONS on non-write paths stay public (dashboard/terminal reads — the relayer's `/api/v1/signal/{entity}` poll keeps working).
- CORS: default = no Access-Control headers (same-origin); `TRION_CORS_ORIGINS="a,b"` → exact-origin echo + `Vary: Origin` + X-API-Key in allow-headers (:28-37); SocketIO same policy (api/socket_push.py:26). flask_cors wildcard init removed.
- Rate limit 300 req/60s/IP (pre-existing); path params regex-validated (api/validation.py); subprocess argv fixed; SSRF-facing fetches target fixed internal URLs.

**LOGIC / OUTPUT**
- Publish path: SHA3-256 entity/commitment (api/blockchain.py:242/:252 — SEC-20 fix, canonical BEO identity restored on-chain); webhook registration resolves hostnames and rejects private/reserved/non-global/multicast IPs (SEC-15 fix, `_resolve_webhook_ips` in api/cex_integration.py; delivery-time pinning still egress-proxy — open residual).
- Frontends reach the API ONLY through Next.js server-side proxies (frontend/next.config.js rewrites → 127.0.0.1:5000; institutional catch-all /api/trion/*) — no browser CORS dependency; their POST compute buttons now 503 on key-unset deployments until they inject X-API-Key (documented follow-up).

**Regression:** tests/unit/test_api_auth_failclosed.py (19), test_api_publish_hashing.py (6 golden vectors), test_awa_freeze.py + test_api_truth_boundaries.py (keyed updates); pre-fix failing-first run 8/19 → 11 failures were exactly the fixed behaviors.

---

## Path 5 — FAISS service auth boundary

**ENTRY** — internal callers only (by design): Flask API (18 urllib + 3 requests sites → `api/faiss_client.py` faiss_urlopen/faiss_headers), dashboard proxy (`api/dashboard_routes.py` `_proxy` — header attached ONLY on FAISS-URL calls so the FAISS key never leaks to the Oracle), CEX forwarder (api/cex_integration.py:565), BH streamer accumulator, 19 genesis backfill scripts + backfill_entity_records, Rust `FaissClient`, integration tests.

**VALIDATION / SECURITY** *(changed this session — SEC-01/24 fix, 7-a; threading, 8-a)*
- `enforce_api_key` middleware (anima-service/faiss_service.py:478) on ALL 165 routes: key resolves `FAISS_API_KEY → FAISS_SERVICE_API_KEY → TRION_API_KEY` (same order on every client, api/faiss_client.py docstring pins the contract).
  - Key SET: non-public routes require X-API-Key (constant-time compare, 401). Public set: /health /healthz /readyz /api/v1/health /stats /docs /redoc /openapi.json.
  - Key UNSET: fail-closed 503 on every non-GET **plus** privileged prefixes even on GET — `/index/*`, `/api/v1/slash*`, `/api/v1/pqc/sign` (the ML-DSA signing oracle is never unauthenticated — SEC-24); read-only GETs + public paths stay open.
- Bind: default `127.0.0.1` (faiss_service.py:11491, `FAISS_HOST` override for containers); docker-compose publishes `127.0.0.1:${FAISS_PORT:-8000}:8000` loopback-only (both profiles), in-container bind stays 0.0.0.0 via FAISS_HOST env; `.env.example` documents FAISS_API_KEY + resolution order.
- Startup log states auth status (WARNING when unset).

**STORAGE / OUTPUT**
- Poisoning paths closed: /index/add, /index/bulk_backfill (fabricated BH history), /beo/resolve_batch (forced entity merges), /api/v1/slash (validator slashing), /api/v1/pqc/sign (signing oracle), /phi/update_weights, /archetypes/train — all keyed/fail-closed; state persists in SQLite so this was restart-surviving poisoning pre-fix.

**Regression:** tests/integration/test_faiss_auth.py (11 tests, both modes; subprocess boots in temp workdirs, no sys.path hacks); adversarial 50-thread write burst now monkeypatches the key so it measures contention, not auth (tests/adversarial/test_adversarial_suite.py); E2E matrix 18/18 (Flask+FAISS both keyed, internal calls prove the threading).

**Residuals at write time:** rate limiting on the FAISS service still absent (SEC-01 partial). Two follow-ups flagged by 8-a were closed by a parallel lane during this session (verified in the working tree, regression tests green): core/physical/transduction_integrity.py now sends X-API-Key (`_faiss_headers()` at :39, attached :159/:171/:194, same 3-var order); cex_integration._forward_to_faiss now posts the proper TxBhBatchPayload shape (chain_id/chain_label/block_num/entries[…]) — the old silent-422 schema drift is pinned by tests/unit/test_cex_faiss_forward.py (5 passed at write time).

---

## Cross-path facts

- One key contract everywhere: X-API-Key from FAISS_API_KEY → FAISS_SERVICE_API_KEY → TRION_API_KEY; TRION_API_KEY additionally gates Flask. Unset = fail-closed writes on BOTH services (503), public reads stay open on both.
- All five paths end in trust boundaries that remain honestly single-party: no validator fleet (certs/quorum are test-side or static), single-sig relayer, no funded escrows, ZK circuits unbuilt (zk_pending honesty in the orchestrator).
- Unchanged pre-existing bugs on these paths were fixed by a parallel lane during this session (verified, pinned): `/api/v1/signal/type/*` COLD_START KeyError (api/app.py:6017) and the GOVERNANCE_SIGNAL digest-overflow IndexError (api/app.py:6137) — regression tests/unit/test_api_cold_start.py (8 passed at write time; all 19 signal types answer 200 on a cold entity). Write-time residual on this path: the Python-side APTOS fetcher reads a stale `previous_block_hash` key (degrades to "0x0" there) while the Rust crate now uses the real `block_hash` — noted in-repo as a core/-side follow-up.
