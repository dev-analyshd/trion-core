# Deep Read: api/ + anima-service/ + akashic/ + adapters/ (agent 2-f)

Scope: 62 tracked files (`git ls-files api/ anima-service/ akashic/ adapters/`) — all read or fully characterized. Monsters read end-to-end in chunks: `api/app.py` (10,392 lines / 500KB), `anima-service/faiss_service.py` (11,257 lines / 484KB), `adapters/__init__.py` (2,677 lines), `anima-service/anima_engine.py` (1,862 lines).

---

## Overview

TRION's runtime is two cooperating services plus auxiliaries:

1. **Flask Oracle API** (`api/app.py`, port 5000, gunicorn) — the "front door". Computes `/api/v1/signal/{entity}` coherence, publishes to Arbitrum Sepolia via `api/blockchain.py` (web3.py, real tx), proxies to the FAISS engine, and exposes ~65 whitepaper "formula" endpoints. Registers 6 blueprints (zg/0G, cex, price_feed, protocol, self_verification, dashboard, btcp_continuum).
2. **FastAPI FAISS engine** (`anima-service/faiss_service.py`, port 8000, uvicorn) — the ANIMA/akashic store: 128-dim FAISS index (FlatL2 → auto-promoted IndexIVFPQ at ≥4,000 vectors), per-entity behavioral history, K-means archetypes (64 clusters), SQLite persistence (`akashic_state.db`, `bh_ledger.db`), TimescaleDB dual-write + cold-boot restore, Merkle accumulator, BFT sigma simulation, ANIMA score (delegates to `anima_engine.py`), 19-type TRIONSignal emission, conscious-plane annotation store, slashing/dispute ledger, living-security (GK/immune/epigenetic/noise/mito/CRISPR) endpoints.
3. **anima_engine.py** — genuinely real external crawlers: SEC EDGAR full-text + filing-body NLP (VADER), GitHub API (commits/contributors/issues), 19 news RSS feeds, CFTC/FCA/ESMA/MAS RSS, arXiv, StackExchange, HN Algolia, GDELT. CRED(s,t) credibility ledger, HA time-delayed verification loop, PCR, CA, reflexivity, manifestation-gap, IM protocol, APScheduler (crawl 30m, decay 24h, verify 6h, IM 24h).
4. **Genesis backfill scripts** (1 generic EVM + 21 chain-specific) — REAL RPC walkers (Arbitrum `eth_getBlockByNumber`, Solana `getBlock`, etc.) that extract 9 features per block and POST `/index/add_batch`. `backfill_entity_records.py` re-ingests bh_ledger rows into FAISS.
5. **adapters/__init__.py** — 6 VM adapter families (EVM/SVM/Cosmos/Move/CosmWasm/OOA) with public-RPC map (55 chains), stdlib-only JSON-RPC client, UniswapV2 ABI encoding, Jupiter quote API for Solana; `dry_run=True` by default; `dry_run=False` probes live RPCs (eth_call quote, unsigned tx envelope).

Data flows: Rust/TS indexers → `/index/add_tx_bh_batch` + `/index/add_batch` → FAISS+SQLite(+TSDB) → Flask `_plane_values()` → CoherenceEngine → TRIONSignal → (optional) on-chain publish → SSE/SocketIO feed → React dashboard.

---

## API route inventory (grouped)

### app.py core (route decorator count: 180; unique URLs ≈ 170)
- **Signal core**: `/api/v1/signal/{id}`, `/signal/{id}/full`, `/signal/type/{type}/{id}` (all 19 types), `/signal/types`, `/signal/batch` (POST/GET), `/trion/{id}` (master eq.), `/publish/{id}` (POST/GET on-chain), `/onchain/{id}`, `/validator/{id}`, `/annotation/{id}`, `/anima/{id}`, `/planes/{id}/(all|physical|mental|spiritual|conscious|anima)`, `/sigma/{id}`, `/gk/{id}`, `/falsifiability` (+alias), `/feed`, `/batch`, `/leaderboard`, `/health`, `/readyz`, `/stats`, `/` `/explorer` `/pitch` `/judge` `/demo` (redirects).
- **BH (L0.1)**: `/bh/{id}` GET, `/bh` POST, `/bh/v2/extended` POST (176-byte), `/bh/ledger/{id}`, `/bh/stats`, `/bh/recent_feed`, `/bh/vm_feed`, `/bh/chains` (+alias), `/tsdb/stats`.
- **Security/MF**: `/security/{id}/mf`, `/security/{id}/genomic`, `/security/sec`, `/security/complexity/{id}`, `/mev/{id}`, `/negative_space/{id}`, `/cross_chain/{id}`, `/stablecoin_health/{asset}`, `/dependency_graph`, `/dormancy/{id}`, `/transduction/{id}`, `/resurrection/{id}`, `/fork/{asset}`, `/fork_resolution/{id}`, `/trajectory/{id}` + `/trajectory_anomaly/{id}`, `/predictive_limit`, `/moat`, `/brt[/{id}]`, `/convergence[/{id}]`, `/resonance/{a}/{b}`.
- **Governance**: `/governance/awa`, `/governance/gratitude` GET/POST, `/governance/falsifiability`, `/governance/init`, `/governance/ceremony`, `/governance/geo`, `/governance/unknown_provision`, `/governance/slashing/(conditions|file|case/{id})`, `/bootstrap/status`, `/bootstrap/weight/{id}`, `/sba/{nation}`, `/xsl/{id}`, `/dw_bft`, `/validator/hhi` + `/validator_hhi` alias, `/validators` (proxy+fallback), `/validator/reward/{id}`, `/validator/hhi`, `/information/conservation`, `/fitness/{component}`, `/inversion`, `/inverted_price_feed[/{asset}]`, `/phase_signal[/{id}]`, `/order_parameter`, `/phase_transition`.
- **Vision modules**: `/audit/{address}`, `/audit/patterns`, `/agent/validate`, `/agent/{id}/profile`, `/agent/{id}/train`, `/agents`, `/akashic/archetypes`, `/akashic/match/{id}`, `/akashic/epigenetics/{id}[...]/pressure`, `/epigenetics/pressure/{id}`, `/thermodynamics/{id}`, `/lifecycle/{id}`, `/ubl/{id}`, `/ubl/schema`, `/ubl/compare`, `/reputation/observe`, `/reputation/{id}`, `/reputation/leaderboard`, `/reputation/{id}/endorse|dispute`, `/invest/{id}`, `/invest/scan`, `/vision`, `/immune/{id}`, `/chameleon/{id}`, `/manifestation_gap/{id}`, `/emergence/{id}`, `/living_index/{id}`, `/universal_asset/{chain}/{addr}[/equivalences]`, `/token/distribution`, `/token/utility`, `/phases`, `/convergence/{id}`.
- **0G**: `/api/v1/zg`, `/zg/proof`, `/zg/sync`, `/zg/integration`, `/zg/chain/status`, `/zg/chain/execute/{id}`, `/zg/storage/store|root`, `/zg/da/status|submit`, `/zg/compute/status|infer`, `/zg/vm-families`, `/zg/full_stack`, `/kv/status`, `/agent_id/{id}`, `/kv/signal/{id}` GET/POST, `/stack/native`.
- **Demo/marketing**: `/attacks`, `/demo/simulate_attack`, `/demo/stats`, `/love/{id}`, `/love/global`, `/trion/trade/{id}`, `/trion/revenue`, `/trion/vision`, `/genesis/fingerprint/{id}`, `/manipulation/attack_cost/{id}`, `/cex`-feed glue, `/backfill/status`, `/alerts(+/stats)`, `/relayers/status`, `/favicon.ico`, `/chains-legacy`, `/deployments.json`.
- **Blueprints**: `btcp_continuum` (24 routes: hash_dna, coherence_7plane, mf_score, route, escrow_states, bibl/snapshot, proof, modules, integration_status, private_bibl, pipeline_status, mainnet_bootstrap, streamer status/start, orchestrator/status, continuum engines ×6), `cex` (8: status/ingest/feed/hostile/webhook/alerts/ledger/stats), `price_feed` (8: pairs, forward, inverse, aggregator, seed, btv ×2, hierarchy), `protocol` (8: health/users/roles/attack-surface/distribution/sub-entities/supported-roles/monitor status), `dashboard` (~30 URL rules at /app/* + /app/api/*-live proxies + timescale), `self_verification` (2), plus zg blueprint from `zg/`.
- **FAISS FastAPI**: 165 route decorators (~150 unique endpoints) — ingestion (add/add_batch/add_tx_bh_batch/bulk_backfill), bh ledger/stats, depth/mental_confidence/volatility/archetype/genesis_confidence/dormancy/resurrection/convergence/fork/trajectory, anima + cred + reflexivity + manifestation_gap + im_status + crawl, spiritual BFT + validators + heartbeat + diversity, conscious annotate/challenge/resolve/annotators/knowledge_systems/elders, pqc sign/verify, crispr, living_security (gk/immune/epigenetic/noise/mitochondrial/composite), beo resolve_batch/deployer/resonance, conservation, fitness, ti, predictive limit, phi weights, coherence_trend, source_credibility, biological_capital, energy_participation, sovereign assessment/appeal, xsl, hhi + slash/dispute/vote, signals (schema/history/batch), route, trading (signal/agent decide/patterns/scan), audit, agent validate/profile, akashic/ubl/thermo/lifecycle re-exports, system bootstrap/falsifiability/status, index vm-status/status, healthz/health/readyz.

Total real route registrations ≈ 250 Flask + ~150 FastAPI ≈ 400; the file header's "194 Flask + 151 FAISS = 345" is approximately right in spirit, slightly under-counted on the Flask side today.

### The 22 BTCP endpoints (api/btcp_continuum_routes.py)
`/api/v1/btcp/`: hash_dna(POST), coherence_7plane(POST), mf_score(POST), route(POST), escrow_states, bibl/snapshot, proof, modules (18-module overview), bitp/match… (declared in docstring but see Bugs), netting, aggregate, failure_classify, version, validator_fee, sybil, private_bibl(POST), integration_status, pipeline_status, mainnet_bootstrap, streamer/status, streamer/start, orchestrator/status; plus `/api/v1/continuum/`: engines, bid(POST), cme(POST), pmo(POST), bdc(POST), settlement(POST), ccp(POST). Computation delegates to `core/` + `continuum/` packages (stateless request→computation endpoints, no persistence).

---

## Per-file findings (bullets)

### api/app.py (10,392 lines)
- Rate limiter: solid sliding-window per-IP (deque + lock + background eviction thread + 10k IP cap). Honest note that it's per-process under gunicorn. CORS `*` on `/api/*`. API-key gate for writes via `TRION_API_KEY` (hmac.compare_digest). 
- **`_compute_signal()` is the heart** (line 740-1001). Pipeline: `_plane_values()` → `_query_faiss_planes()` (HTTP to :8000 mental_confidence/anima/depth, 45s TTL lru_cache, returns None on neutral prior) → Σ via `_get_sigma_plane()` (validator mesh :6000 → FAISS validators → bootstrap 0.25) → K via `_get_k_plane()` (bootstrap 0.10) → `CoherenceEngine.compute_coherence` (core/master/coherence) → temporal coherence, TI (bootstrap defaults 0.80/0.85/0.75 with honest `bootstrap_mode=True`), conf_genesis, CI95, TTL, BRT, genomic sig, archetype, master eq T(t).
- **COLD_START enforcement (genuine honesty fix)**: `_plane_values()` (line 649) returns `_cold_start=True` when FAISS has no history → signal endpoint emits `SILENCE/COLD_START` (id 99) with `calibration_note` instead of fabricating hash-seeded planes. Comments document the removed SHA256-hash-seeding of Φ/M/A ("silently fabricated a behavioral record"). **But**: `_mf_score()` is still `sha256(eid+"mf")` (L730) and `_market_volatility()` is `sin(t/3600)+md5-noise` (L734) — volatility is synthetic everywhere (`theta = 0.55+0.37*vol`).
- **Greek/formula sanitizer** (L1004-1078): an `after_request` hook strips α,β,Σ,Θ,·×÷ etc. from ALL 200 JSON responses and rewrites `M_moat(t)`→"Moat Score" — consumer-facing cosmetics; makes API responses diverge from whitepaper notation.
- ~60 endpoints are **pure hash-seeded synthetic**: leaderboard (hardcoded 10 seed names, sha256-derived "signal_count"), SBA (`_seed()` from sha3 of nation), XSL, geo (12 hardcoded validators), validator_reward, resonance, negative_space, mev, cross_chain, stablecoin_health, dependency_graph (static TVL table), dormancy, epigenetics_pressure, fitness, phase_signal, order_parameter, genesis fallback, liquidity fallback, `agent_train_label` (fake training_id, no-op), `kv_root`/merkle "proofs" (hash of a string, not data), love protocol, trion_trade, emergence "90d" records (rng), manifestation_gap history (rng), intelligence_maintenance (time-modulated constants).
- **`_ATTACK_DB` (L7634-8243)**: ~40 real historical exploits (DAO, Harvest, Euler, Curve, Ronin, Wormhole, etc.) with real dates/addresses/losses + **fabricated "phi" phase values** presented as "what TRION would have detected"; `/api/v1/demo/simulate_attack` derives entropy features from those stored phis. Marketing/demo layer, clearly a simulation, but the endpoint reports `"final_verdict": "BLOCKED"` unconditionally.
- `/api/v1/zg` does **real web3.py calls** to 0G mainnet (`https://evmrpc.0g.ai`) against TRIONExecutionGate `0xA85B49…4199b`; on failure returns canned fallback numbers (published:0, sync_block 33317279) — fallback looks like stale live data rather than labeled failure.
- BH ledger endpoints query **real SQLite** (`bh_ledger.db`) with WAL, caching, stratified per-chain sampling — the most "real data" part of the Flask app.
- Falsifiability registry wired to live bh_ledger counts at startup (background thread, "millions of rows" note).
- `demo/stats` and `zg/full_stack` return **hardcoded marketing constants** ("test_coverage": "328 passed / 24 skipped", "bh_avg_ms": 0.023, "434×", "api_routes": 139 (stale — actual is ~250), "328 tests", "languages": 8, contracts_deployed: 6) alongside real counts (live BH via `_live_bh_count_str()`).
- **Route-count drift**: `/demo/stats` says `api_routes: 139`, `/inversion` says 131, header says 194 — three different numbers, none current.

### api/blockchain.py (536 lines)
- Real web3.py ChainRelay (Arbitrum Sepolia, POA middleware, gas bump). **BUG (refactor casualty)**: `publish_signal()` (L247-254) returns `{"error":"chain_not_ready"}` when not ready but has NO body when ready — the real publishing body was orphaned as unreachable dead code inside `get_behavioral_signal()` (L372-412, after return). So `/api/v1/publish/{id}` on a ready relay gets `chain_result=None` → AttributeError → 500. Also `get_behavioral_signal()` calls `getBehavioralSignal` which is not in the local ABI (would raise) — but the V3 path (`publish_behavioral_signal_v3`, `record_silence`) is correct and wired to the V3 ABI.
- `get_recent_events()` fetches real BehavioralTruth/SilenceSignal logs over last 100k blocks.

### api/validation.py (217) — Strict entity validation (64-hex BEO / EVM address / 15-alias allowlist resolving to `sha3("trion:protocol:{name}")`). Good input hygiene; used via decorator on ~25 routes only.

### api/btcp_continuum_routes.py (754) — 22+ POST compute endpoints delegating to core/continuum modules; BIBL snapshot explicitly "demo" sample; streamer endpoints gate on `TRION_ENABLE_STREAMER` env (documents the N×78-thread flood incident). Clean.

### api/chains_registry.py (325) — 100-chain catalog. **The "chain-stats honesty fix"**: `get_bh_stats()` returns real `bh_ledger.db` counts labeled `stats_source:"ledger"` when the chain has live records, else deterministic hash-seeded capacity estimates **explicitly labeled `stats_source:"estimated"`** ("never presented as indexed data", "never fabricate freshness"). Enrichment resolves bh_label aliases; 60s cache on DB counts.

### api/cex_integration.py (1,025) — Real bidirectional CEX ingest: PII guard (rejects user_id/email/ip/wallet), event mapping to 20 canonical EventTypes, real 93-byte canonical BH construction (SHA3 dual-strand, complementarity), own SQLite (`cex_bh_ledger.db`), webhook queue with real POST delivery, hostile-entity inverted feed computed from actual wash/flash ratios in the DB. Feed falls back to hash-seeded values when oracle down. CEX volumes in `/status` are hardcoded.

### api/price_feed_routes.py (532) — Chainlink AggregatorV3-compatible REST feed (roundId/answer/startedAt/updatedAt/decimals=8, inverse via 1e16). In-memory registry **bootstrapped with 15 hardcoded baseline prices** ("overwritten by relayer within minutes" — no relayer in repo pushes them); cross-rate synthesis; BTV endpoints delegate to `core/price/behavioral_price_engine` (real engine, per other agents).

### api/protocol_routes.py (394) + protocol_monitor.py (307) — Protocol health decomposition into (contract, caller) sub-entities, role classification, JSD distribution coherence, background monitor pushing grade/threat changes into feed. Engine in core/; monitor watches uniswap/aave/compound/0G gate.

### api/self_verification_routes.py (81) — Reflexive self-coherence monitor (core.physical.transduction_integrity), lazy `_feed_push` lookup to dodge circular import.

### api/socket_push.py (112) — SocketIO wrapper; broadcaster polls own `/api/v1/feed` every 3s and emits diffs; unbounded `_seen_keys` capped at 500 (evict-list via `list(_seen_keys)[:excess]` — O(n) but fine).

### api/requirements.txt — pinned with security-bump comments (flask 3.1.3 PYSEC notes, ecdsa no-fix note). 

### Static assets — author.png (690×739 PNG photo), trion_logo.png (384×404), trion_icon.png (actually JPEG mislabeled .png), favicon.svg, dashboard.css (24KB), dashboard.js (3.9KB).

### anima-service/faiss_service.py (11,257 lines)
- **Ingestion is real and carefully engineered**: thread-safety (`_INDEX_WRITE_LOCK`, `_DB_WRITE_LOCK`, `_db_write_with_retry` exponential backoff for cross-process Rust indexer contention), FlatL2→IVFPQ promotion at 4k vectors, per-vector lock granularity, atomic `tmp+rename` persistence every 60s/500-vectors/atexit/SIGTERM, WAL checkpoint, arch retrain every 6h on ≥5% growth. L0.5 signal-selection gate (`dI/dS > 0.5`), L0.4 conservation ledger, L0.2 BEO merge (CF/ST/SC/BP/GX 5-factor, threshold 0.75).
- **canonical_bh() is byte-identical to Rust** (`_hex_to_32bytes` port with invalid-hex→0 semantics, `as u64` truncation) — C1 audit fix; complementarity verification enforced on every add_tx_bh_batch entry.
- `calculate_depth()` (L1783): real integral `Σ mag_eff×entropy×(1+arch_sim)×time_weight` + WARM summaries; BASE_PRESENCE 0.02 floor for zero-value txs.
- `/api/v1/mental_confidence` (L2807): `M = arch_sim × (1 − pi_t/0.30)` from real std of stored arch_sims; **neutral prior 0.5 for unseen entities** with a long honest justification. This is what the Flask app's cold-start logic keys on.
- **Σ(t) BFT is simulated** (L4863-5034): 10 SEEDED validators with hardcoded stakes/regions; votes = `rng.gauss(signal_value, 0.05)` — i.e. **validators "observe" the oracle's own input and add noise**; two-pass δ-window exclusion + HHI freeze/discount is faithfully implemented, but the vote generation is circular (Σ ≈ noisy Φ_adj). Comment admits "Phase 1 testnet; real deployment via TRIONStaking.vy".
- K(t): real annotation store (submit/challenge/resolve with reputation updates, 100-TRION min stake) — starts empty; `k=0.85` prior with status `no_annotations_prior`; build_trion_signal uses REAL k when annotations exist, proxy `0.7σ+0.3a` otherwise (labeled in debug log).
- ANIMA (L4299): delegates to anima_engine (real crawls). Trading-signal endpoint falls back to hash-seeded phi_features when index.reconstruct() fails on IVFPQ (documented).
- `build_trion_signal()` (L8963-9212): full 19-type emission; phi_raw = mean|vector| over last 20 records (real vectors, but **not the 9-feature Shannon pipeline the whitepaper describes** — features f1..f9 in /planes/physical are `phi*0.15/0.10` fake decompositions of the same scalar!); MF 7-type detector is real (CV/frequency-spike/entropy-drop/pairwise-cosine/HHI/low-entropy counts over real records) + native C++ FFT cross-check via core.native_bridge; GK evolution + dual-strand genomic sig per signal; negative-space = genuine FAISS kNN density z-score vs centroid baseline; slash/dispute ledger in-memory dicts.
- Plane endpoints: `/planes/{id}/all` hardcodes sigma=0.25, k=0.10 with honest disclosure strings ("Σ bootstrap=0.25 until mainnet validators"); ANIMA "active" gate D≥10,000.
- Persistence: SQLite tables (entity_records capped by compress-to-WARM after 90d/1000 records, merkle_state, genesis locks, deployer, timing, phi_weights, block_features, l06_fitness) + TimescaleDB dual-write in background threads + cold-boot restore from akashic_vectors (last 500/entity).
- `/stats` deliberately reads `index.ntotal` WITHOUT the lock with a written justification (health-probe liveness > torn read) — sound call.
- Cleanup: `_resolve_vm_type` handles 11 VM families incl. the ZG-2 typo fix (16601→16661).

### anima-service/anima_engine.py (1,862) — see Overview; **the most genuinely "real" module in the repo**: real HTTP to efts.sec.gov (fetches actual 8-K/10-K bodies, VADER+keyword NLP), GitHub REST, 19 news feeds, 4 regulatory feeds (CFTC dead-feed 404 documented, ESMA 403 retry), arXiv Atom API, StackExchange, HN Algolia, GDELT. 33-source CRED registry with decay/events; HA verifies predictions against later crawl (non-circular), CRED updated VERIFIED/FALSIFIED; IM maintenance degrades CRED. Weighted composite stored per crawl; predictions recorded with 24h manifest window.

### Other anima-service files
- **nl_score_engine.py** (159): thin legacy shim delegating to core natural_liquidity (LD·LO·LC·LS); honest doc of prior non-spec approximation.
- **liquidity_ocean.py** (177): cross-chain NL aggregator + coherence + HHI + dynamic routing threshold; CHAIN_WEIGHTS for 8 chains. Pure math, no I/O.
- **btcp_gas_forecast.py** (151): EWMA + CV + CI95 gas forecasts; per-chain baseline profiles (hardcoded), bridge-baseline comparison. Fine.
- **multilingual_sentiment.py** (181): 10-language lexicons (zh/ja/ko/ru/ar/es/fr/de/pt/en), Unicode-script detection, CJK char-tokenization. Real but naive; **not wired into anima_engine** (which uses VADER only) — "54 languages" claim elsewhere vs 10 here.
- **brt_scheduler.py** (438): observed-timestamp circular statistics (Rayleigh R, peak/quiet hours), autocorrelation rhythm detection, BLO windows; **explicit `CONJECTURE` label until F14 90-day validation** — exemplary honesty.
- **anima_regulatory.py** (761): Schnorr-style NIZK over Pedersen commitments in pure Python (P-256 params, Fiat-Shamir), Travel-Rule proof, JurisdictionRegistry (runtime-configurable), JRS + regulatory master equation. Self-described as "real ZK… not a hash stub" — construction is plausible but uses scalar-mult over a hash-to-group domain, not a true curve group; "For production use Ristretto255" caveat.
- **btcp_price_oracle.py** (613): TWAP, 7-check manipulation detection (median dev, CV, bimodal), source diversity d_j, HHI, BITP exchange-rate bands, sanctions-oracle staleness. Pure computation on caller-supplied prices.
- **crawler_pool.py** (742): ThreadPoolExecutor pool (default 50, "scalable to 1000") wrapping core data-source connectors (GitHub events, news, GBIF+IUCN ecological, EDGAR, arXiv, multilingual). Infrastructure only.
- **exploit_precursor_analysis.py** (827) + report.json (944): Layer 1 = live bh_ledger entities with fingerprint concentration (real wallets); Layer 2 = forensic reconstruction for 20+ historical exploits, "clearly labelled as reconstruction — not fabricated". Report verified: layer1_live_threats = [] (empty — honest), layer2 entries with baseline/precursor planes.
- **genesis_backfill.py** (366) + 21 chain variants (algorand, cardano, cosmos, hedera, move, multiversx, near, polkadot, solana, starknet, stellar, sui, ton, tron, utxo, vechain, waves, xrpl): real RPC block walkers (verified public endpoints), 9-feature extraction mirroring trion-l0, 9→128-dim cosine-basis expansion (doc claims "lossless and invertible" — overstated), checkpoints every 1000 blocks, gap validation.
- **backfill_entity_records.py** (417): bh_ledger → FAISS re-ingest; vector layout documented as faithful to vector.rs (9 features + complement + cross-corr + stats + SHA3 noise + zeros); entropy floor tuned to pass L0.5 gate with justification.
- **batch_contract_audit.py** (1,105) + batch_audit_report.json (7,182 lines, verified valid): audits 52 real contracts (Uniswap V2 Router, Aave, etc.) with **pre-populated bytecode characteristics** (no live RPC; header says so), real pattern-matching engine over the 20-pattern library; report contains per-contract findings with evidence strings, CRISPR suggestions, similar exploits. Generated artifact, reproducible.
- **start.sh** (100): launches faiss_service then conditionally spawns 6 TS indexers (svm/pvm/ton/near/bnb/base) if node_modules exist; waits on FAISS pid.
- **requirements.txt**: faiss-cpu, fastapi, uvicorn, feedparser, vaderSentiment, apscheduler, httpx, psycopg2, sklearn, web3.
- **chains_registry_evm.json**: 52 EVM chains with public RPC URLs (hashkey, eth, arb, base, op, bnb, polygon, mantle, linea, scroll, 0g, avax, fantom, sonic, zksync, berachain, xlayer, xdc, story, blast, manta, mode, taiko, fraxtal, metis, celo, gnosis, moonbeam, kaia, core, bitlayer, bob, rootstock, cronos, aurora, harmony, iotex, conflux, monad, filecoin, abstract, zora, wemix, okt, oasis, telos, kroma, cyber, sei, canto, neon, iota).

### akashic/ — **Only 2 files exist** (`__init__.py`, `btcp_price_oracle.py` 16-line re-export shim because "anima-service" hyphen can't be imported as a package). Task brief mentioned `crispr_anomaly.py` and `brt.py` — **they do not exist** in akashic/ (CRISPR lives in core/spiritual/living_security and faiss_service; BRT in faiss_service + brt_scheduler).

### adapters/__init__.py (2,677) — 6 families: EVM (UniswapV2 calldata + real eth_call getAmountsOut quote + unsigned-tx envelope when dry_run=False), SVM (Jupiter v6 quote API, SPL Token program), Cosmos (ABCXI/bank-send), Move (Aptos/Sui BCS-ish JSON payloads), CosmWasm (inherits Cosmos), OOA (Fuel GraphQL). VMAdapterFactory + self-test. All execution defaults to DRY_RUN; broadcast deliberately NOT implemented (unsigned envelope only). `CHAIN_VM_MAP` covers 27 chains though `CHAIN_RPC_URLS` covers 55.

---

## Data flow architecture (signal end-to-end)

```
Rust/TS indexers (chains/*) ──POST /index/add_tx_bh_batch, /index/add_batch──▶ faiss_service :8000
   → verify BH complementarity → bh_ledger.db (SQLite WAL) [+ TimescaleDB dual-write]
   → index.add(vec) [lock] → entity_history[beo] (magnitude/entropy/arch_sim)
   → Merkle leaf → convergence → maybe compress→WARM → persist

Flask /api/v1/signal/{eid} → _query_faiss_planes (GET :8000 mental_confidence | anima | depth)
   mental_confidence: arch_sim(cosine to K-means centroid) × (1−std(arch_sims)/0.30)
   anima: anima_engine.get_anima_score = PCR(sequence vs archetype) × HA(verified 90d outcomes) × CA(CRED-weighted cross-source agreement from real crawls) × (1−0.5·reflexivity)
   Σ: seeded validators voting gauss(Φ_adj,0.05) → δ-window BFT (circular sim)
   K: annotation network (empty → 0.85 prior / proxy in signals)
→ _compute_signal: C=0.25Φ+0.30M+0.25Σ+0.10K+0.10A (CoherenceEngine w/ bootstrap planes)
→ COLD_START guard → TI×(1−MF) adj → Θ=0.55+0.37·V(sin-noise) → T(t)=C·e^moat
→ (POST /publish) ChainRelay.publishBehavioralSignal → Arbitrum Sepolia → feed ring buffer → SSE/WS
```

FAISS vector accumulation: FlatL2 at boot (or restored from TimescaleDB last-500/entity) → promote IVFPQ at 4k vectors → atomic 60s/500-vec/atexit/SIGTERM persistence → `indexed_vectors` reported by /health, /stats, and Flask /api/v1/faiss (max()'d against live streamer count with fallback floors 10,018/4,489).

---

## Code quality assessment

**Strengths** (surprisingly high for the genre):
- Real engineering discipline in faiss_service: locking strategy documented, retry/backoff for cross-process SQLite, atomic writes, torn-read tradeoffs reasoned in comments, restart survival (SQLite + TSDB cold-boot restore), honest `/stats` lock decision.
- canonical BH unified byte-for-byte with Rust (documented audit fix C1); complementarity invariant enforced at ingest; XOR-NOT invariant correctly implemented in 3 places.
- anima_engine does real multi-source crawling with real NLP, time-delayed self-verification, and credibility decay — an actual feedback loop, not a mock.
- Explicit honesty mechanisms: COLD_START refusal to fabricate; chains_registry "estimated" vs "ledger" labeling; BRT "CONJECTURE" until F14; planes disclosure strings; bootstrap_mode flags; exploit analysis "reconstruction, not fabricated"; batch audit "no live RPC, pre-populated bytecode".
- Input validation decorator, rate limiting, PII rejection in CEX ingest, constant-time API key compare.

**Weaknesses**:
- app.py is a 10k-line monolith mixing production endpoints with marketing/demo endpoints (revenue model, love protocol, vision) and hash-seeded synthetic formula endpoints at production paths.
- Massive duplication: archetype/thermo/ubl/reputation/invest endpoints exist in BOTH app.py (via core/) and faiss_service (re-implementations); two validators lists, two mental_confidence implementations, three route-count claims.
- Sanitizer mutates every 200 response (Greek stripping) — surprising global behavior.
- In-memory dicts for slash ledger, annotations, BFT registry — lost on restart (annotations notably NOT persisted despite SQLite existing for everything else).
- Sigma/K planes are simulated or prior; the 5-plane coherence's "spiritual" and "conscious" legs are bootstrap constants — C(t) is effectively Φ·M + constants today.

## Bugs / issues / inconsistencies (file:line)

1. **api/blockchain.py:247-254** — `publish_signal()` has no body after the not-ready guard; real publish code orphaned as dead code at :372-412 inside `get_behavioral_signal()` (unreachable, after return). A ready relay ⇒ `/api/v1/publish/{id}` crashes with AttributeError on `chain_result=None`... actually `relay.publish_signal()` returns None ⇒ app.py:1133 `chain_result.get(...)` → 500. The V3 publish path works but isn't called from app.py.
2. **api/blockchain.py:352** — `getBehavioralSignal` not in ORACLE_ABI (only latestSignal) → any call raises; masked by dead-code placement.
3. **api/app.py:4303** — `from adapters.evm import ...` — `adapters/evm.py` does NOT exist (only `adapters/__init__.py`); `/api/v1/stack/native` always 500s with ImportError. (dashboard_routes.py:442 correctly uses `core.native_bridge`.)
4. **api/app.py:8380** — `/demo/stats` reports `api_routes: 139`; header line 7 claims 194; `/inversion` claims 131; real ≈250. Internal inconsistency.
5. **api/app.py:734-738** — `_market_volatility()` is `sin(t/3600)+md5-noise`; drives Θ(t) across the whole API — synthetic "market" data by design, contradicting any "zero mock data" claim.
6. **api/app.py:2227** — `zg_proof` "merkle_root" over FAISS index is fake: leaves = `sha3(faiss_hash[2:i:2] + bytes([i%256]))` — hashes slices of a hex STRING, not index segments; not a Merkle tree of the file.
7. **api/app.py:2128-2149** — `/api/v1/agent/train` (label variant) fabricates `training_id` from a hash and stores nothing.
8. **api/app.py:5403-5406** — `bootstrap_planes` in signal-by-type derives flags from plane scores ≤ thresholds — inverted-ish heuristic vs actual bootstrap flags; cosmetic.
9. **anima-service/faiss_service.py:9886-9916** — `/planes/{id}/physical` "features f1..f9" are all `phi×(0.15|0.10)` — fabricated decomposition, not the 9 Shannon features computed by the indexers/backfills.
10. **faiss_service.py:4968** — BFT validator "observations" = `rng.gauss(signal_value, 0.05)`: Σ(t) is a noisy echo of the oracle's own Φ_adj — circular; disclosed only as "Phase 1 testnet" seed validators (10 hardcoded, L4865).
11. **faiss_service.py:10338-10426** — `/api/v1/trading/signal/{id}` fallback phi_features are hash-derived (`sum(ord(c))%100`); also searches FAISS with a 16-dim query derived from the entity string (index expects 128-dim; reshape(1,-1) passes 16 cols — FAISS will error → caught → fallback). Query-dimension mismatch caught by except, but sloppy.
12. **faiss_service.py** — annotations/annotator reputations/slash ledger/BFT rounds are memory-only (not in the SQLite persistence story) → reset on restart.
13. **anima_engine.py:531** — EDGAR full-text query uses `entity_id.replace("0x","")[:20]` — a hex BEO hash fragment as a company search term yields ~0 hits for on-chain entities; crawl quality depends on entity being a ticker-like string.
14. **anima_engine.py:655** — GitHub search uses `entity_id[:10]` similarly; "no_repos" default 0.45 for most entities.
15. **multilingual_sentiment.py** — claims are "50+ languages" in crawler_pool/docs; this module supports 10 and isn't imported by anima_engine (dead-ish code).
16. **api/dashboard_routes.py:315** — references `TIMESCALE_AVAILABLE`/`get_timescale_store` without visible import in the file section read (imported later in file via try block — OK if core module present; otherwise NameError at request time).
17. **genesis_backfill.py:152-160** — "lossless and invertible" 9→128 cosine-basis expansion claim is overstated (cos(kπ/14) projections of scalars + hash overwrites of last 10 dims).
18. **app.py:423-433** — `/api/v1/faiss` fallback hardcodes floors 10,018 vectors / 4,489 entities when both FAISS and streamer are down — presenting synthetic floors as "faiss_available": True.
19. **app.py:2562-2569** — startup falsifiability wiring thread reads `bh_ledger.db` from CWD-relative path `../bh_ledger.db` — works only when run from api/ or repo root layout; consistent with other relative DB paths (deployment assumption).
20. **Route duplication/conflicts** — `/api/v1/trajectory_anomaly/{id}` exists in faiss_service as both POST (vector) and GET (history) — fine; but Flask app.py ALSO has `/api/v1/trajectory_anomaly/{id}` (synthetic) — two different answers for the same URL depending on port. Same for genesis, liquidity, audit, agent, ubl, etc. — Flask versions are synthetic, FAISS versions are data-driven.

## Claims vs reality

| Claim | Reality |
|---|---|
| "194 Flask routes + 151 FAISS routes = 345" (app.py header) | ~250 Flask route registrations (app.py 180 decorators + blueprints 86) + ~150 unique FAISS endpoints — close-ish, but three conflicting self-reported counts (131/139/194). |
| "All signals published on-chain via publishBehavioralTruth()" | Only on explicit `/publish`; and the classic relay path is broken (dead-code bug); V3 path works. |
| Chain coverage "37 chains / 52 EVM / 100 catalog / 13 VM families" | 100-chain *catalog* (status mostly "indexed"/gap-filled), 52 EVM RPC registry, ~11-14 VM families across differing files; only chains with bh_ledger rows have real per-chain BH counts; rest labeled "estimated". |
| "Σ(t) diversity-weighted BFT consensus" | 10 seeded validators + Gaussian votes around the oracle's own signal — simulation, disclosed as Phase-1 testnet. |
| "K(t) human annotation network" | Real store/API, starts empty; 0.85 prior / proxy used in signals. |
| "zero mock data" (README-level) | False for app.py: leaderboard, SBA, XSL, MEV, negative space, stablecoin health, love, phases, revenue, attack-sim, price-feed baselines are hash-seeded or hardcoded; TRUE for bh_ledger, FAISS pipeline, ANIMA crawls, CEX ingest, backfills, TSDB. |
| "FAISS 128-dim Shannon entropy features" | Vectors ARE 128-dim and indexers/backfills compute real 9-feature bases, but /planes/physical f1..f9 responses are fabricated decompositions; ANIMA PCR/HA/CA operate on real vectors+real crawls. |
| "0.023ms BH, 434×, 328 tests" (demo/stats) | Hardcoded strings in endpoint, not measured there. |
| akashic/ crispr_anomaly.py, brt.py | Don't exist (task-brief mismatch; functionality lives elsewhere). |
| batch_audit_report.json "52 real contracts audited" | Real contract roster; bytecode characteristics pre-populated (documented), pattern engine live; report is a genuine generated artifact of that process. |

**Bottom line**: the ingestion → FAISS → SQLite/TSDB spine, the canonical BH, the ANIMA crawler layer, CEX ingest, backfills, and the VM adapters are genuinely real systems with unusually honest labeling in places. The Flask surface layers a large synthetic/marketing stratum on top (especially the ~60 hash-seeded formula endpoints, attack "simulations", price baselines, and demo stats), the Σ/K planes are bootstrap/simulated, and `blockchain.py`'s classic publish path is broken by a refactor accident. The project's own audit comments (C1, ZG-2, cold-start remediation, estimated-vs-ledger chain stats) show an active effort to replace fabrication with honest disclosure — partially complete.
