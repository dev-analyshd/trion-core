# TRION + BTCP — Autonomous Master Worklog

Standing record of the autonomous canonical-reconstruction / security / architecture
loop. One section per wave. Never rewritten — append only.

Hierarchy of truth (fixed, per master command):
1. Authoritative TRION whitepaper/specification
2. Authoritative BTCP specification
3. Canonical math definitions and protocol invariants
4. Canonical security requirements derived from the specs
5. Existing implementation
6. Tests
7. Documentation/comments
8. Engineering judgment

Authoritative specification set (established at freeze, HEAD af09ab3, 2026-09-04):

| Document | Role | Status |
|---|---|---|
| spec/WHITEPAPER_MD.txt | Canonical whitepaper (Feb 2026, updated Mar 2026) — protocol semantics | AUTHORITATIVE (newest, wins semantic conflicts) |
| spec/WHITEPAPER_V2.txt | Complete implementation specification — every formula/component (Feb 2026, "all gaps filled", Parts 1–13 incl. Part 12 team roles) | AUTHORITATIVE (implementation detail; V2 wins where MD is silent) |
| spec/BTCP_SPEC.txt | BTCP master implementation spec (§4.1 intent, 6-step sequence, §5.x modules, §14 build order) | AUTHORITATIVE for BTCP |
| spec/L0–L9 layer docs | Layer-level definitions (universal primitives → cross-species) | AUTHORITATIVE (layer scope) |
| spec/DD_REPORT.txt | Due-diligence report (S1–S10, C1–C10) | AUDIT INPUT (not a spec) |
| spec/signal_types, novel_primitives, falsifiability_registry, communication_channels | Supporting normative tables | AUTHORITATIVE (their domain) |

Conflict rule: MD > V2 on protocol semantics (newer); V2 > MD on implementation
detail where MD is silent; BTCP_SPEC governs BTCP absolutely; DD_REPORT never
overrides a spec.

Baseline at Wave 1 open:
- HEAD af09ab3, working tree clean, origin/main synced, author dev-analyshd
- 691 unit tests + 9 skipped; tests/btcp 39; bitp 33; adversarial 120/121
  (1 failure = PQC libs absent — environmental, proven pre-existing)
- Task 20 (23 commits) + Task 21 (23 commits) landed and lead-verified; all
  open items from those waves closed; remaining items are external-toolchain
  (cargo, go, PQC libs, funded keys, live RPCs, validator fleet, TimescaleDB)
- External toolchain policy in force: static verification + deterministic tests
  + documented unverified boundaries; no fabricated verification

Wave plan (roles per master command §3–§21):
- W1: A (spec matrix), B (canonical BH + golden vectors), E (canonical
  certificate), F (invariants + BTCP state machine)
- W2: G (EVM/Solidity), H (Solana), I (Move), J (TON), K (Cairo), L (Vyper)
- W3: C (chain registry/indexers), D (Akashic/BEO/math), M (API/relayer/SDK),
  N (storage), O (deployment)
- W4: P (red team), Q (dead code), R (docs conformance)
- W5: S (final integration + fresh adversarial review + FINAL report)

---

## WAVE 1 — Foundation: canonical specifications, BH, certificate, invariants

Status: OPEN
Agents: A, B, E, F (parallel, disjoint file ownership)
Lead: freeze performed above; this worklog opened.

(Agents append per-wave results via the lead after integration; per-agent
detailed logs live in the shared engineering worklog outside the repo and in
each agent's final report to the lead.)

### WAVE 1 CLOSE (lead integration, HEAD 298a1d6)

Agents: A ✓, B ✓, E ✓ (report delivery timed out; all 3 commits landed and lead-verified), F ✓.
Commits: d7ca82e (spec matrix, 107 requirements, 22 spec conflicts K1-K22 resolved) ·
B: cf4cd71/8831b3a/dfab58d/c542504/3f6ce2e/31f823f (canonical BH doc v1 93-byte layout;
py/TS/rust builder parity fixes incl. deterministic rust magnitude+timestamps across
21 crates; 52 golden vectors / 134 tests) · E: d0d6e20/b9b2a87/298a1d6 (canonical
certificate doc with cross-VM domain separation; validator security audit = Wave 2
work order: 6 CRITICAL C-01..C-06, 8 HIGH H-01..H-08, M/L register; py reference
encoder core/consensus/certificate.py) · F: 65925e6/f3a27e7/9e2b84f/b160ba4/273805d/
d720105 (BTCP state machine 26 states/33 transitions; invariants register INV-001..022;
py-layer enforcement: 18 ENFORCED/3 PARTIAL/0 UNENFORCED; 49 attack tests).
Battery: 759 unit + 9 skipped, 134 golden, 87 btcp + 1 xfail (72h dispute window —
registered open), 33 bitp. Zero regressions.
Wave 2 dispatch: G/H/I/J/K/L against VALIDATOR_SECURITY_AUDIT.md + CANONICAL_CERTIFICATE.md.

### WAVE 2 CLOSE — VM SECURITY PARITY (lead integration, HEAD eaa5daa)

Agents: G/G2+lead, H/H2, I/I2, J/J2, K/K2, L. Context-deadline kills on report
delivery were absorbed by completion agents + lead; all work landed verified.
- G (EVM template tier): 942a503 CanonicalCertificate.sol library (py
  golden-vector parity) + f48c357 TrionEpochRegistry; lead-completed
  8817e72 (V4 submitCertificateAttestation: full §6 sequence, envelope
  [s_j,d_j] claims cross-checked vs registry, weight quorum, threshold
  provenance, nonce ordering + equivocation evidence) + eaa5daa (escrow
  releaseEscrowCanonical permissionless path; M-05 bind-time oracle-interface
  pinning; H-07 HashDNA input discipline; stack-safe split accessors after a
  via-ir StackTooDeep on the 16-field struct getter; mock upgraded to dynamic
  quorum). Real-EVM suites: certificate 38, epoch-registry 42, oracle 40,
  escrow 10 — all green.
- H (Solana/SVM): 6ba429c + cdb0111 — C-03 closed: oracle-key release gate
  replaced by certificate verification (ed25519, epoch registry PDA, weight
  quorum, settlement tuple, Clock freshness, consumed-nonce PDA, oracle key =
  pause only). 156 checks green.
- I (Move): 42f1e93 codec+registry modules + 64a9850 — C-02 closed:
  coherence_verified relayer flag REMOVED (dev-flag rejected as
  mainnet-reachable); permissionless release on canonical certificate
  (native AptosStdlib ed25519, §6 order, BCS-bound tuple, idempotent-hash
  replay). 130 checks green.
- J (TON + NEAR): 90a1104 C-01 closed (4-cell P tree, CHKSIGU, epoch dict,
  L4.2 quorum); J2 verified + 2995c5d (H-03 threshold cross-check) + 6e1bec7
  (forward-only epoch registration) + 52c4691 C-05 NEAR closed
  (publish_btcp_route full §6, env::ed25519_verify, u128 tier quorum; owner
  can administer registry but cannot forge consensus). TON 113 + NEAR 97
  checks green.
- K (Starknet/Cairo): d516c28 family-3 modules + 8be39b8 C-04 starknet
  escrow closed + 758be3b cairo execution-gate quorum-gated + 9eb15fc attack
  matrix. 18 pytest tests green (py-mirror + static).
- L (Vyper + PVM): 4c694e2 M-03 closed (dynamic quorum consult via
  minRouteAttestations, Vyper no-try/catch = structurally fail-closed; 2-
  attestation attack regression proven on real EVM, 35 tests) + b579b64/81059f9
  PVM legacy oracle honestly labeled non-production (43 tests). Incident:
  L's b579b64 accidentally staged G's in-flight files (shared-index race);
  untracked in 81059f9, G re-committed cleanly — resolved, protocol now uses
  pathspec-limited commits.
Battery at close: 759 unit + 9 skipped · 87 btcp + 1 xfail · 134 golden ·
47 contracts (pytest) + 574 direct-script checks across 9 suites · 120/121
adversarial (1 = known PQC-lib env gap).
Wave 3 dispatch: C/D/M/N/O per A's spec matrix remediation list.

### WAVE 3 CLOSE — INFRASTRUCTURE, MATH, API TRUTH (lead integration, HEAD 1de698d)

Agents: C, D/D2, M/M2, N, O (+lead). Report-delivery kills absorbed by completion
agents + lead; all work landed and verified.
- C: 2c2ceac + 5390e7c — one canonical registry enforced: hardcoded chain-id
  sites rewired/audited (disposition matrix), counts honest, scanner test added.
- D/D2: 17c2f82 AWA canonical 6-condition set + fail-closed EmissionGate
  (singleton, no unfreeze API, Chameleon WEAPONIZATION→freeze) · 39955a2 HHI
  4000-CRITICAL + §9.2 second TTL table (py/rust/certificate.py identical) ·
  a3c8334 24 canonical signals + 7 BTCP domain · 4ef65f2 wash-trading D_eff
  discount + conservation audit · 1b26967 clipboard enforced expiry + BEO
  witness binding + persisted per-entity nonces. 152 new tests; master
  formula verification 104/0/1 "ALL FORMULAS ENFORCED AS SPECIFIED".
- M/M2: f857b0f relayer submit-only + single-signature custody honesty ·
  a2a74ad SDK trust model (no client-side truth) · da04992 api truth
  boundaries (orchestrate witness_source/zk_pending surfaced; settlement gate
  DERIVED from persisted proofs; tolerance caps; gratitude/slashing/reputation/
  kv/sanctions/cex/price-feed provenance; SSRF guard; X-API-Key enforced) —
  34-test attack battery.
- N: dcda8d5 — all 35 schema.sql tables dispositioned (12 operative writers
  incl. blo/bitp/shadow/genesis + consumed-certificate/conflict guards;
  6 deploy-gated; 17 honest NONE markers), atomic step-6 writes,
  crash-injection tests, replay/equivocation store guard. 56 new tests.
- O: 7 commits + lead completion 9d298d5 — custody matrix, per-profile
  topology, runbook truth, zero dead env vars, render build fix.
- Lead: 1de698d — AWA EmissionGate wired into /api/v1/publish (MD §17 "silence
  is information" at the route boundary): frozen ⇒ 503 + silence:true + no
  chain write; adversarial freeze test + regression tests (24 AWA tests).
Battery at close: 1019 unit + 9 skipped · 87 btcp + 1 xfail · 134 golden ·
47 contracts (pytest) + direct suites green · master-formula 104/105 (1
documented) · api truth 34/34.
Wave 4 dispatch: P red team, Q dead-code restructure, R docs conformance.

### WAVE 4 CLOSE + WAVE 5 (exploit fixes) — HEAD 45eda91

Wave 4: P (red team — battery landed by lead after kill), Q (dead-code: e280ea7
hardhat byte-pins + compiled-artifact regeneration + drift guards; ec5c9d2
frontend dead hook; c0eed54 broken scripts; d4660f0 sdk/src isolated; 4889e1f
gitignore root-cause), R (docs: 60c9e77 conformance truth pass + 713c42c K1-K22
spec banners).
Wave 5 (lead, Agent S): five confirmed exploits CLOSED —
- 39cd184a-part-1: P-EVM-01 dest_chain binding (escrow + oracle reject
  certificates not destined for this chain — P's double-pay amplifier dead) +
  P-EVM-02 akashic expiry flip (enterPendingAkashic rejects expired escrows)
- part-2: P-PY-01 NaN magnitude raises (py; TS inherently safe via BigInt) +
  P-PY-02 chain_id validated not masked (py + rust static + TS)
- part-3: P-API-02 path-aware write gate (publish/zg-da/zg-storage require
  X-API-Key on EVERY method)
- 45eda91: test isolation — global EmissionGate singleton swapped in
  suite-level AWA tests (ordering flake root-caused and closed)
Red team battery: 59 + 13 tests; adversarial 179/180 (1 = PQC env). Units
1022+9. All five exploit tests flipped to assert-FIXED.
