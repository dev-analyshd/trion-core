# Security Policy — TRION Protocol

## Supported Versions

| Version | Supported |
|---------|-----------|
| 1.x (testnet) | ✅ Active development |
| 0.x (alpha) | ❌ Deprecated |

## Reporting a Vulnerability

**Do NOT open a public GitHub issue for security vulnerabilities.**

Report security issues directly to: **trionprotocolbh@gmail.com**

<!-- audit fix (BUILD-4): the KEYS file was never committed — do not reference it.
     Until a PGP key is published, reports should be sent as plain email with
     the vulnerability description; coordinate encryption out-of-band. -->
Please include:

- Description of the vulnerability and affected component(s)
- Steps to reproduce (with minimal PoC if possible)
- Potential impact and attack scenarios
- Suggested fix or mitigation (if known)
- Whether you intend to be credited in the disclosure acknowledgments

### Coordinated Disclosure Timeline

| Time | Action |
|------|--------|
| T+0     | Reporter emails `trionprotocolbh@gmail.com`. A PGP key will be published here *before* any bounty program with monetary rewards goes live; until then, coordinate encryption out-of-band if the report is sensitive. |
| T+48h  | Maintainers acknowledge receipt and assign a tracking ID. |
| T+7d   | Maintainers confirm or reject the report. Initial triage. |
| T+30d  | Patch prepared on a private advisory branch. |
| T+90d  | Coordinated public disclosure OR extension by mutual agreement. |
| T+90d+ | Bounty / acknowledgement issued (see "Rewards" below). |

We commit to:
1. **Acknowledging** every credible report within 48 hours.
2. **Keeping** reporters informed of remediation progress at least weekly.
3. **Crediting** reporters in the public disclosure unless they prefer to remain anonymous.
4. **Not** pursuing legal action against good-faith reporters who follow this policy.

## Scope

### In Scope

After the v2 restructuring (src/ → core/), canonical paths are:

- `core/master/coherence.py` — C(t) master equation
- `core/master/btcp_score.py` — BTCP score composition (incl. MF penalty)
- `core/physical/manipulation_detector.py` — MF detection logic
- `core/extended/natural_liquidity.py` — Natural Liquidity (NL) computation
- `core/extended/biological_capital.py` — BC engine (IUCN integration)
- `core/extended/cross_species.py` — XSL engine (GBIF integration)
- `core/extended/sovereign_behavioral.py` — SBA engine (IMF/World Bank)
- `core/governance/awa.py` — Archetypal Weighted Average (AWA) enforcer
- `core/governance/falsifiability_registry.py` — F1–F15 falsifiability conditions
- `core/spiritual/sigma_engine.py` — Diversity-Weighted BFT (entity-DW-BFT)
- `core/spiritual/hhi_monitor.py` — HHI geographic / infrastructure caps
- `core/spiritual/living_security/` — Genomic Key, CRISPR, PQC layer
- `core/btcp/router.py` — BTCP route selection (Gap 12 determinism)
- `core/btcp/escrow_monitor.py` — BTCP escrow cascade revert (Gap 9)
- `core/akashic/timescale_store.py` — Akashic persistence layer (Gap 15)
- `core/akashic/depth.py` — D(t) Akashic depth computation
- `core/primitives/hash_dna.py` — HashDNA dual-strand fingerprint
- `core/primitives/entity_resolution.py` — L0.2 BEO confidence scoring
- `contracts/` — all Solidity (`.sol`) and Vyper (`.vy`) contracts
- `anima-service/` — FastAPI ANIMA service (FAISS endpoints, fetcher pool)
- `rust/src/` — BTCP zero-bridge core (Rust)
- `validator/` — Go P2P validator mesh
- `indexers/crates/` — Rust L0 indexers (14 crates)

### Out of Scope

- Testnet keys / wallets (use testnet funds only, no real value).
- Known bootstrap limitations (Σ=0.25, K=0.10, A=0.10 are by design — see WP2 §4.7).
- Denial-of-service against public testnet endpoints.
- Social engineering against TRION contributors.
- Vulnerabilities in third-party dependencies already disclosed publicly
  and tracked under CVE — please report those upstream.

## Rate Limiting

### API Server (Flask + FastAPI)

All public TRION API endpoints enforce layered rate limits:

| Layer | Scope | Default | Override Env |
|-------|------|---------|--------------|
| Global | Per-IP, all routes | 60 req/min | `RATE_LIMIT_GLOBAL_PER_MIN` |
| Write  | Per-IP, POST/PUT/DELETE | 10 req/min | `RATE_LIMIT_WRITE_PER_MIN` |
| Read   | Per-IP, GET | 120 req/min | `RATE_LIMIT_READ_PER_MIN` |
| Heavy  | Per-IP, expensive endpoints (`/api/v1/anima/*`, `/api/v1/btcp/score`) | 5 req/min | `RATE_LIMIT_HEAVY_PER_MIN` |
| API-key | Per-key, authenticated | 600 req/min | `RATE_LIMIT_API_KEY_PER_MIN` |

Rate-limit responses use HTTP 429 with `Retry-After` and `X-RateLimit-*`
headers. Repeated violations after a 429 are subject to escalating
backoff (1 min → 10 min → 1 hour → 24 hour IP ban).

To enable rate-limiting in production, set `RATE_LIMIT_ENABLED=true`
in `.env`. Defaults to `false` for local development.

### Smart-Contract Layer

On-chain write paths enforce additional DoS protection:

| Contract | Function | Protection |
|----------|----------|------------|
| `AkashicProof.sol` | `submitMerkleRoot` | 2/3 validator quorum + nonce-bound sigs (replay-proof) |
| `AkashicProof.sol` | `addValidator` / `removeValidator` | `onlyDeployer` (bootstrap; rotate to governance post-launch) |
| `TRIONExecutionGate.sol` | `publishSignal` | AWA-enforced + 2/3 quorum signatures |
| `TRIONExecutionGate.sol` | `checkExecution` | `nonReentrant` + `whenNotPaused` + fail-closed |
| `TRIONToken.vy` | `slash_validator` | `staking_contract`-only + 50% insurance / 50% burn |
| `TRIONToken.vy` | `burn` | Permissionless (deflationary mechanism — Gap 1) |
| `TRIONStaking.vy` | `register_validator` | Coverage-tier-scaled minimum stake (Gap 1) |
| `TRIONStaking.vy` | `slash_validator` | 72-hour dispute window (Gap 1) |

### External Data Fetcher Pool

The ANIMA fetcher pool (`anima-service/fetcher_pool.py`) enforces a
global request budget across all external data sources (IUCN, GBIF,
IMF, World Bank, arXiv, GitHub, news RSS, SEC EDGAR, CFTC):

- **Global ceiling**: `EXTERNAL_API_RATE_LIMIT_PER_MIN` (default 60 req/min).
- **Per-source ceiling**: configurable per fetcher (typically 1 req/sec).
- **Timeout**: `EXTERNAL_API_TIMEOUT` (default 30s).
- **Retries**: `EXTERNAL_API_RETRY_MAX` (default 3, exponential backoff
  base `EXTERNAL_API_RETRY_BACKOFF_BASE` = 2s → 2s/4s/8s).
- **HTTP 429 handling**: honors `Retry-After` and `X-RateLimit-Reset`
  response headers; suspends that fetcher for the indicated duration.

External credentials (IUCN/GBIF/IMF/World Bank tokens) are read from
`.env` — see section 18 of `.env.example`.

## Behavioral Security Architecture

TRION implements Living Security — cryptographic keys derived from behavioral entropy:

- **Genomic Keys**: Base key ⊕ SHA3(behavioral_vector ‖ block_hash ‖ time_window)
- **CRISPR Library**: 7 known attack fingerprints with evolution vectors
- **Chameleon Protocol**: Pre-signed emergency governance transitions
- **AWA (Archetypal Weighted Average)**: Signal emission frozen when any
  of the 6 governance conditions (WP2 §17) is violated. Enforced on-chain
  in `TRIONExecutionGate.sol::publishSignal` (AUDIT-3 Gap G3 fix) and
  in `TRIONStaking.vy::is_signal_emission_allowed`.
- **Falsifiability Registry**: 15 outcome-based F-conditions (WP2 §20),
  each with a specific test metric, threshold, and window.

These are defense mechanisms, not vulnerabilities. Do not attempt to
exploit them. Reports that simply restate the disclosed bootstrap
limitations as "vulnerabilities" will be closed as out-of-scope.

## Known Bootstrap Limitations (Not Vulnerabilities)

During testnet, three planes operate at bootstrap values per whitepaper §4.7:
- Σ (Spiritual) = 0.25 — awaiting validator network
- K (Conscious) = 0.10 — awaiting annotation network
- A (ANIMA) = 0.10 — awaiting D(t) ≥ D_minimum

These are disclosed honestly at `/api/v1/system/bootstrap`. They are not
security vulnerabilities.

## Rewards

We recognize and reward high-impact disclosures:

| Severity | Bounty (testnet phase) | Recognition |
|----------|------------------------|------------|
| Critical (funds at risk, consensus bypass) | Up to $10,000 USDC | Hall of Fame + advisory role |
| High (logic flaw, DoS vector) | Up to $2,500 USDC | Hall of Fame |
| Medium (info leak, minor DoS) | Up to $500 USDC | Acknowledgement |
| Low (best-practice improvements) | TRION swag | Acknowledgement |

Bounties are paid from the protocol's `unknown_unknown_reserve` (10% of
revenue, per WP1 §6 — `core/governance/unknown_unknown.py`) once that
reserve is capitalized on mainnet.

## Contact

- Security email: **trionprotocolbh@gmail.com** (PGP-encrypted preferred)
- PGP key: not yet published in this repository (audit fix BUILD-4 — the
  previously referenced `KEYS` file was never committed); request the current
  public key by email before sending encrypted reports
- General security questions: open a GitHub Discussion (NOT an issue)
