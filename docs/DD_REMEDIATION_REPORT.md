# TRION Protocol — Due-Diligence Remediation Report

**Date:** 2026-09-04 · **Reference:** DD report `TRION_PROTOCOL_...Critical_Due_Diligence_Report.pdf` (TRION-DD-01)
**Method:** every finding from S1–S10, C1–C10 and Sections 3–7 was re-verified against the codebase first
(the earlier bulk "dd-remediation" commit had claimed several fixes that did not hold — S5, S6 and S10
were re-tested and found still broken, and a plaintext Bitcoin WIF key was discovered in a proofs doc).
Each finding was then fixed as an individual, verified commit. Keys were purged from git history and
the branch force-pushed, so hashes below are post-purge.

---

## Security findings (S1–S10)

| # | Finding | Resolution | Commit(s) |
|---|---------|------------|-----------|
| S1 | EVM deployer private key committed in 5 scripts; address self-listed as compromised | Removed from tree (prior commit `d67e38b` line, earlier repo history), then **purged from all git history** via filter-repo replace-text; force-pushed. Key fragments in the committed DD-report copy also redacted. Keys treated as burned. | `c3cce4c` (redactions) + history purge (force push `a3f5d18…5f2d800`) |
| S2 | Starknet deployer key committed beside its account address | Same treatment: tree clean (verified repo-wide scan), history purged alongside S1. | history purge (force push) |
| S1′ | **NEW finding during re-verification:** plaintext Bitcoin testnet WIF key in `docs/proofs/BTC_STARKNET_ZERO_BRIDGE.md:72` | Redacted with burned-wallet notice; purged from history. | `c3cce4c` + history purge |
| S3 | Escrow release trusts caller-supplied coherence; relayer = single trusted EOA | Route verdicts now require **ECDSA signature quorum** (`submitRouteAttestation`: recovered signers checked against validator registry, distinct-attestor counting, immutable value etching, dynamic quorum `max(2, ⌈2/3·N⌉)`); escrow `_consensusGate` reads the dynamic quorum; deploy scripts bind the oracle by default; trusted-relayer mode is an explicit dev opt-out; artifacts recompiled; 7 hardhat tests cover the release path. | `fbfb0ed`, `4b5c650`, `a86b742`, `a18b001`, `81bee7d` |
| S4 | No consensus implementation behind the "consensus-only oracle" claim | **Tendermint-style BFT engine in the Go validator**: height/round/step state machine, lock-on-precommit, view-change with timeout doubling, commit on strictly >2/3 voting power, diversity-weighted proposer selection, equivocation evidence → slash + tombstone + power removal; wired into the TCP mesh (backward-compatible frames); 15 engine tests + 5 wire tests, `go vet` clean. | `c2c41a8`, `fc750b5` |
| S5 | Sanctions screening fails open in SDK | Fail-closed: unreachable oracle ⇒ `sanctioned: true` with `SCREENING_UNAVAILABLE` marker and confidence 0. The missing `/api/btcp/sanctions/<address>` endpoint was implemented (coverage-aware, admin-gated feed upsert). | `ed91de2`, `11482ee` |
| S6 | Publish-signal API route dead (empty handler / broken body) | Body referenced undefined attributes (`self.w3` vs `self._w3`), passed 5 args to a 6-arg ABI, and the working implementation sat as unreachable dead code inside another function. Fixed and verified by mock-signing test. | `0d2eadb` |
| S7 | KMS/HSM broken; DRY_RUN default; in-memory trust state | (a) KMS address derivation used SHA3-256 instead of Keccak-256 — every non-env provider was dead; fixed with ethers keccak + DER-sig handling, KMS signers now sign transactions and quorum signatures. (b) Orchestrator routes, router reservations, escrow states, dispute cases now SQLite-persisted (WAL, write-through, reload on boot) — restart roundtrip verified. DRY_RUN remains the safe default absent a key. | `f79709a`, `b4eafce` |
| S8 | Fabricated incidents cited as evidence | Prior fix verified genuine: fabricated "March 12, 2026 AAVE" removed, replaced by real Euler Finance 2023 et al.; remaining simulated scenarios explicitly labeled. Re-verified repo-wide. | (verified; earlier `d67e38b` lineage) |
| S9 | Bounty uncapitalized; gmail contact; no PGP | Uncapitalized bounty is disclosed as such; SECURITY.md no longer instructs PGP-encrypted reports to a key that doesn't exist — states a key will be published before any paid program. (Generating a keypair for the maintainer is out of scope of a code repo.) | `c6e5ce3` |
| S10 | Broken Makefile (space-indented recipes) | Re-verified the earlier "fix" was fake (0 tab-indented lines). Converted to tabs **and** fixed `${VAR:-default}` being eaten by make (defaults silently vanished). All targets parse. | `bbb68c1` |

## Claim contradictions (C1–C10)

| # | Claim vs. code | Resolution | Commit(s) |
|---|----------------|------------|-----------|
| C1 | DW-BFT consensus "Tendermint-family" — not implemented | Real BFT engine shipped (see S4): blocks, views, slashing execution. Remaining-for-live-network gaps documented in `validator/README.md` (block persistence, peer exchange, state sync, on-chain slash relayer). | `c2c41a8`, `fc750b5` |
| C2 | "TRION consensus is the only release oracle" — contradicted | Escrow release now gated by recovered-signature quorum on-chain (see S3). | `fbfb0ed`, `4b5c650` |
| C3 | Zero-Bridge "not demonstrated" (same chain, one key, simulated UTXO) | Honest labeling completed: BEO "identity across 8 VMs" reframed as hash determinism (necessary, not sufficient); BTC leg's simulated-UTXO status and single-relayer trust documented in README; proof docs carry self-reported caveats. **Substance** (two distinct live chains, two keys) requires external infrastructure — documented as remaining. | `59ac473` (README), `c3cce4c` |
| C4 | Backtest "30/30, F1 85.71%" — degenerate flag-everything run | Detector recalibrated: replay engine feeds measured features through the production pipeline; **FPR 0.00, TN 10/10, separation 0.316, plane payloads populated**; threshold picked by Youden's J (disclosed); held-out 67/33 split run for the first time (test recall 1.00, Wilson CI 0.72–1.00); v1 artifacts preserved with PROVENANCE.md; superseded on-chain proof marked. README quotes v1/v2 side by side with caveats. | `139da36`, `59ac473` |
| C5 | "16 contracts verified" — testnet-only, undisclosed 0G mainnet claim | Deployment table now discloses the single 0G mainnet record explicitly (self-reported, deployment-gate function only); all other records labeled self-reported. | `59ac473` |
| C6 | Chain counts drift 31–174 across 9 values | Single source of truth: `config/chain_registry.json` (129 chains / 18 VMs / 41 integrated at this commit — **currently 40 integrated after the Wave 3 registry-honesty pass**). API derives at import; frontends use shared constants; 0g service counts at boot; manifest/deployment docs recomputed (71 EVM + 58 non-EVM, 8,256 pairs); API hardcoded 37/13/10 counts and 139/131 route metadata replaced with counted values (180 routes then — **measured 282 rules at Wave 4, 2026-09-04**). | `c09ff10`, `c03c2af` |
| C7 | "52/52 verified, 0 gaps" — table sums to 61; test counts drift | Table corrected to 61 with an explanatory note and a definition of what "implemented" means; test counts in README unified (609 unit + 121 adversarial + 186 integration; hardhat 43; go 15); historical counts in dated changelog entries left as dated history. | `c06621b`, `59ac473` |
| C8 | Tokenomics: three different stories, no distribution | All four token implementations (Vyper, NEAR, TON, ink!) now: fixed 1B supply @ 18 decimals, genesis-only mint, 15%/85% public-good/treasury carve-out enforced on-chain, burn path; canonical `docs/TOKENOMICS.md` with the full bucket table, vesting, and an on-chain vs. policy enforcement matrix; API distribution endpoint reports accurate enforcement per bucket. | `15e1e85`, `0d5db95`, `afff067`, `6db5849`, `a1bfb84`, `e38e347` |
| C9 | Living Security PQC "partial, offline" | PQC deps declared; tests now **skip with a clear reason** on a bare env instead of hard-failing (and still run at full strength with the libs — verified both paths). | `e38e347` |
| C10 | Validator fleet "not started" | Software side shipped earlier and verified: SQLite-persisted validator registry with 100-validator/4-continent launch gates + staking contracts (Vyper/NEAR/TON/ink!) with 7-type slashing; **hardware fleet remains external** (documented). | (verified; earlier `d67e38b` lineage) |

## Sections 3–7

| § | Critique | Resolution | Commit(s) |
|---|----------|------------|-----------|
| 3.3 | Fabricated validation incident (closed evidentiary loop) | See S8 — verified removed/labeled. | (verified) |
| 4.1 | Provenance: `trion-arbilink-agent` name, stale ARCHITECTURE.md, foreign `/home/user` paths, replit proxy lockfile | Package renamed `trion-core` with honest description; root ARCHITECTURE.md rewritten for the actual repo (historical note included); sandbox paths removed (env-var + /tmp defaults); 191 lockfile URLs moved off the Replit package firewall to registry.npmjs.org. (Dep pins verified valid against current registries.) | `6e3b410`, `86e750d`, `d7f043e`, `09f3593` |
| 4.2 | Non-EVM tiers: TON cell overflow, SVM full-balance lock, Move stub, Cairo missing hardening | TON serializers split across cells (all ≤1023 bits, layout test 30/30, dict-key type fixes); SVM verified already fixed; Move rewritten as a real registry; Cairo ported locked-balance accounting + 7-day emergency exit + cascade revert. | `60aa034`, `4686ade`, `4821127` |
| 5.1 | "52/52" verification matrix self-graded | See C7. | `c06621b` |
| 5.2 | Zero-Bridge proof docs refute themselves | See C3. | `59ac473`, `c3cce4c` |
| 5.3 | "75.8% sybil stake → 0.00%" — number in no test | The claim turned out **real**: 50-of-66 validators = 75.76% nominal → measured 0.00% effective. Now a passing test, plus the honest boundary the claim omitted (at cartel correlation 0.5, sybils retain 49.2% — 2/3 bound broken; collapse-to-zero requires near-perfect copying). HHI tiers and geographic caps also tested. | `2b4b7c6`, `736eb1a` |
| 5.4 | Tokenomics: one supply, three stories | See C8. | `15e1e85`–`a1bfb84` |
| 5.5 | Numerical drift as systemic property | See C6 — every count now derives from one registry. | `c09ff10`, `c03c2af` |
| 6.1 | Backtest selective quotation | See C4 — full v1/v2 metric table with caveats. | `59ac473` |
| 6.2 | Self-audits; "NO hardcoded private keys" falsified | Secret-scan claim corrected in-place with the lesson (scans must cover docs/proofs); 61≠52 table fixed; self-audit papers moved under `docs/audit/`. | `c06621b`, `5f2d800` |
| 6.3 | Probability-table items marketed as proven | BITP/ZK-intent bullets now carry their spec probabilities (70%/60%) with the ZK-simulation status; bridge-elimination claim carries the 30% figure; BEO proof relabeled. | `59ac473` |
| 7.1 | Committed credentials | See S1/S2/S1′ + history purge. | `c3cce4c` + force push |
| 7.2 | Centralized trust: sanctions fail-open, ~60 synthetic API endpoints with silent fallbacks, restart state loss, 20KB .env | Sanctions fail-closed + real endpoint (S5); last unlabeled synthetic fields (`_mf_score`, `_market_volatility`, constant tx_count) now labeled with sources (65 `is_synthetic` labels total); BTCP state persisted (S7); `.env.example` previously verified slim (7 placeholder slots). | `ed91de2`/`11482ee`, `e38e347`, `b4eafce` |

## Additional code-level bugs fixed (independent deep-read findings, verified then fixed individually)

| Bug | Commit |
|---|---|
| GBIF longitude read from `decimalLatitude` | `66482ce` |
| `compute_xsl` import shadowing (wrong engine exported) | `c344b8b` |
| CME temporal window never matched epoch timestamps | `4b506b9` |
| BIRP enrollment anchor dropped 3 of 4 inputs (precedence) | `d4e9978` |
| DNA code rotation chain claimed but inverted (replay passed, rotation failed) | `c9586b7` |
| Dead selector-length branch in event classification | `d3b652d` |
| 11 non-EVM fetchers collapsed all senders into one entity | `051727d` |
| Vulnerability docstring claimed 25 archetypes (20 exist) | `33be077` |
| Import-time `print` in API routes module | `5a7e75f` |
| Nonexistent setuptools build backend | `60cce4d` |
| Consensus/HHI module self-demos failed or misrepresented results | `736eb1a` |
| `serve.py` fallback schema missing `valid` column | `5f2d800` |

## Test posture after remediation

- `pytest tests/unit` — **609 passed, 5 skipped** (baseline 603/5 preserved; +6 consensus tests)
- `pytest tests/contracts` + phase-1 contracts — 36 passed
- Hardhat — **43 passing** (36 baseline + 7 new escrow-consensus tests)
- Go validator — build, vet, and tests clean: **15 consensus + 5 wire tests**, 4/4 packages
- TON layout guard — 30/30 pack/body shapes ≤ 1023 bits
- Vyper token — 29/29 functional checks on eth-tester
- Master formula suite — 105/105 with PQC libs; PQC checks skip cleanly without

## What remains (honest list — external or hardware)

1. **Live-network operation**: the BFT engine needs peer exchange, block persistence, state sync, and an on-chain slash relayer before a real network (documented in `validator/README.md`).
2. **Zero-Bridge substance**: one reproducible two-distinct-chains/two-keys demonstration with real BTC legs — requires funded testnet wallets and live RPCs.
3. **External security audit** by an identifiable firm (all current audits are self-authored and labeled as such).
4. **Validator fleet hardware**: HSMs, geographic distribution — the registry and staking software is ready.
5. **ZK layer**: real Groth16 setups (zkeys, proofs) — currently an honest simulation; circuits unbuilt.
6. **On-chain slashing bridge** from Go evidence to `TRIONStaking.vy`.
7. **PQC KMS live smoke tests** (AWS/GCP/YubiHSM with real keys) and Starknet/TON/Move toolchain compilation (no compilers in this environment; verified structurally).
8. **Bounty capitalization** and published PGP key before any paid disclosure program.

---

## Post-report residual sweep (2026-09-04, second pass)

A re-verification pass over the C6/5.5 count-drift family found the "count purge"
commits (`c09ff10`/`c03c2af`) had missed a tail of stale figures. Each was fixed
in its own verified commit (endpoint smoke-tested before commit; unit suite
608 passed / 6 skipped without a live server, stress suite 17/17 with one;
contract checks 36 + 10 + 19; Go 4/4 packages):

| Residual finding | Fix commit |
|---|---|
| `/api/v1/phases` still reported `chains_indexed: 37` | `4808490` |
| `/api/v1/zg/full_stack` still reported 37 chains / 13 VMs | `b0263f4` |
| `/api/v1/inversion` fell back to 37 when the moat service was down | `1907573` |
| Ψ(t) phase-transition estimate multiplied a 37-chain coverage into its math | `a663f76` |
| A dozen docstrings/descriptions still said "37 chains" / "13 Rust L0 crates" (21 exist) | `5254c24` |
| Phase-signal `akashic_coverage` and order-parameter adoption metrics said 37 | `5731bb4` |
| BTV price-engine confidence normalized active chains against a hardcoded 37 | `d54d6c5` |
| `mainnet_bootstrap` docstrings claimed 106 chains / 14 VMs while building 152 / 20 | `be869b1` |
| Institutional README view table said "160 unique · 22 VMs" | `87dc8fb` |
| `.gitignore` comment claimed hardhat ABI JSONs "stay tracked" — false since the later cleanup deleted them | `34040ea` |
| `/api/v1/bh/vm_feed` attribution line said "13 VM families" | `c837424` |
| `PROJECT_METRICS.tracked_files` said 956; the tree tracks 995 | `a7c282a` |
| Go health-monitor header claimed "35 chains"; its list has 19 endpoints | `e9d0858` (+ gofmt pass `8837467`) |

Also caught during the sweep: a stale server instance from the pre-purge code was
serving old counts on port 5000 (restarted; runtime state, not repo state), and
the Edit-tool tab-expansion accident on `health_monitor.go` was amended before push.
