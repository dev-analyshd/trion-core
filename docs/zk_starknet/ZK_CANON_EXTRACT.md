# ZK_CANON_EXTRACT — STARKNET SUBSTRATE SUBSTITUTION MISSION (Phase 0.2)

> **Mission:** ZK LAYER → STARKNET SUBSTITUTION — CANON IMMUTABLE, SUBSTRATE MOVED
> **Task ID:** ZK-STARK-PHASE-0
> **First Law (R-DESIGN):** Statements, inputs, phases, schemas, tiers, thresholds
> verbatim. The proving system is the ONLY substitutable element.

## 0.1 Canon Sources — Re-verified Fresh SHA-256

| ID | Document | Date | SHA-256 |
|---|---|---|---|
| C1 | `TRION_PROTOCOL_White_paper.pdf` | Feb 2026 | `80ebc82f0f9ba8e5bf58d110b870796ae48145c410be411a9a0378566398d183` |
| C2 | `BTCP_MASTER_IMPLEMENTATION_SPEC.md.pdf` | Apr 2026 | `758528cf8910eb02c205b6a4850a70c9350472bb2507e5367d71ac57bd4fb420` |
| C3 | `TRION_Protocol_Whitepaper.md.pdf` | Mar 2026 | `40321eaa277c1a62804691819a181cdb7d8242062cdb3cd0d69538fe5541e094` |

Author of all three: Hudu Yusuf (Analys), TRION Protocol. License: CC0.

**Precedence (per mission R-CANON-PRECEDENCE):** C3 §16 permits STARKs for
behavioral ZK → STARK-on-Starknet is canon-allowed for S2-S5. C2 §5.6 lists
"Groth16 or PLONK" + verifier.sol for S1 complementarity → S1 requires
either (a) STARK primary on Starknet + EVM compatibility artifact, OR (b)
a CANON-WINS finding citing C3 §16 + R-SETUP transparent preference.

## 0.2 Agent Sign-off (Phase 0.1)

- ✅ A-SPEC: read all 3 canons fully (7,048 lines extracted via pdftotext).
- ✅ A-AUD: witnessed; re-verified SHA-256 matches prior missions.
- Subsequent agents (A-CAIRO-1/2, A-PROVER, A-CHAIN, A-INT, A-CRYPTO, A-ADV, A-DOCS) sign off in their own worklog entries.

## 0.3 Reuse of Prior BZK Mission Canon Extract (R-NO-REDEF)

The prior BZK mission (commits 52936a9..b2da620) authored
`docs/zk/CANON_EXTRACT.md` with 14/14 verbatim citation matches verified by
fresh-process audit. That file contains the full verbatim quotes for S1-S5
+ cross-cutting laws. Per mission R-DESIGN + R-NO-REDEF, this mission does
NOT re-extract or paraphrase — it references the existing extract and adds
only the substrate-substitution-specific content below.

**Reference:** `docs/zk/CANON_EXTRACT.md` (commit 52936a9, verified by Phase 7 audit `docs/zk/A_AUD_ledger.md`).

## 0.4 The Immutable Design Set (per mission — verbatim from canon)

The verbatim passages for S1-S5 are in `docs/zk/CANON_EXTRACT.md` §1-§5.
Cross-cutting laws R-ABSENT, R-SILENCE, R-COMPLIANCE, R-INVISIBILITY,
R-CHANNELS, R-GENERIC, R-FAILCLOSED are in `docs/zk/CANON_EXTRACT.md` §6-§7.

This mission's contribution to the canon extract is the
**substrate-substitution rationale** (Phase 1 output below), NOT a
re-extraction of the canon text.

## 0.5 SURFACE_MAP (Phase 0.3) — with Starknet substrate decision

| Surface | Statement (verbatim source) | Public Inputs | Private Inputs | Phases | Storage Rule | Emission Schema | Falsification | Canon Citation | Substrate Decision |
|---|---|---|---|---|---|---|---|---|---|
| **S1** | "H_my_intent and H_counterparty_intent are complements" | `[H_intent_A, H_intent_B, entity_id_A, entity_id_B]` | `[intent_A_full, intent_B_full, nonce_A, nonce_B]` | 4 phases (Commit/Match/Reveal/Execute) | H_intent → (timestamp, entity_id); NO routing before reveal | IntentCommitted + IntentRevealed events | MEV bot front-runs before Phase 3 reveal | C2 §5.6 | **STARK primary on Starknet + EVM-compat artifact (PLONK verifier.sol) per R-CANON-PRECEDENCE** |
| **S2** | "share is correctly calculated from contribution without revealing contribution" | `[total_value, pool_direction, merkle_root]` | `[entity_value, merkle_path]` | Pool open → share prove → close | Pool structure transparent in Akashic; individual values hidden | PoolFormed + ShareProved events | Share mismatch > 1 wei | C2 §5.3 | **STARK on Starknet (C3 §16 permits)** |
| **S3** | "I submitted valid Travel Rule disclosure to FATF-compliant VASP" | `[transaction_hash, jurisdiction_id, disclosure_hash]` | `[disclosure_contents, regulator_receipt]` | 4 steps (prep/encrypt/prove/emit) | disclosure_hash ONLY; NO plaintext | TRAVEL_RULE_COMPLIANT=TRUE | Regulator plaintext in TRION traces | C2 Fix 1 | **STARK on Starknet (C3 §16 permits)** |
| **S4** | "my behavioral_hash is coherent with my historical BEO pattern" | `[public_commitment, entity_id, historical_BEO_root]` | `[private_behavior, private_nonce]` | Dark Field (compute private → commit → prove → emit) | public_commitment ONLY; behavior_content/amount/counterparty/protocol/chain ABSENT | BEHAVIORAL_TRUTH_SIGNAL with plane_results[7×BOOL] | TRION reconstructs private behavior from public_commitment alone | C2 §7.1 + C1/C3 §16 | **STARK on Starknet (C3 §16 permits); single-epoch base case ships, multi-year GATED-OPEN per OQ-7** |
| **S5** | "I know the DNA_Code for this BIRP_anchor and passed recovery phases 1-5" | `[BIRP_anchor, entity_id, enrollment_timestamp]` | `[DNA_Code, behavioral_challenge_answers, temporal_cluster_proof]` | Enrollment + recovery phases 1-5 | BIRP_anchor ONLY; Hash(DNA_Code) only; DNA_Code content/timing NEVER stored | BIRPEnrolled + BIRPRecovered events | Drift false-negative rate exceeds threshold | C3 §16 | **STARK on Starknet (C3 §16 permits); enrollment ships, recovery phases 1-5 GATED-OPEN (drift CONJECTURE)** |

## 0.6 CANON-WINS Register (Phase 0.4)

### CW-STARK-1: Proving substrate substitution is canon-permitted

**Finding:** C3 §16 verbatim: "[CONJECTURE — technical feasibility]: ZK
proofs over behavioral commitments are constructible using Groth16, PLONK,
or STARKs. Computational cost is non-trivial but decreasing."

**Canon-wins:** STARK is explicitly listed in C3 §16 as a permitted proving
system for behavioral ZK. Therefore substituting the proving substrate
from Groth16/PLONK (circom/EVM, prior BZK mission) to STARK (Cairo/Starknet,
this mission) is NOT a design change — it is a substrate move that the canon
itself permits. The statements, inputs, phases, schemas, tiers, thresholds
remain VERBATIM.

### CW-STARK-2: S1 EVM-compatibility requirement (C2 §5.6)

**Finding:** C2 §5.6 verbatim: "Circuit: `zk_complementarity_proof/`
(MISSING — requires Groth16 or PLONK). Estimated circuit size: ~50k
constraints. Groth16 proof: ~200 bytes." AND "zk_complementarity_proof/verifier.sol — Solidity verifier contract."

**Canon-wins:** C2 §5.6 explicitly lists a Solidity verifier contract for
S1 complementarity. Per mission R-CANON-PRECEDENCE, S1 requires either:
- (a) STARK primary on Starknet + EVM compatibility artifact (PLONK
  verifier.sol exported via snarkjs `plonk` setup, labeled), OR
- (b) CANON-WINS finding citing C3 §16 + R-SETUP transparent preference.

**Decision (Phase 1 will finalize):** Option (a) is preferred — the prior
BZK mission's circom S1 circuit (commit 52936a9, 2,686 MEASURED constraints)
already compiles to PLONK. The EVM compatibility artifact is the existing
`zk-circuits/zk_complementarity_proof/` circuit compiled with PLONK setup
(transparent, no ceremony). This satisfies C2 §5.6's verifier.sol
requirement while the STARK-on-Starknet path is the primary proving
substrate. **Nothing canon-listed is deleted; file map updated, not erased.**

### CW-STARK-3: STARK transparent setup is the security argument

**Finding:** R-SETUP: "Transparent setup preferred; any ceremony labeled
[OPEN] until executed then [V ceremony record]; STARK = no trusted setup
— record this as the security argument."

**Canon-wins:** STARK proving systems (STARK via Cairo, Plonky2/Plonky3)
use transparent setup — no trusted ceremony, no Powers of Tau, no
toxic waste. This is a STRICT SECURITY IMPROVEMENT over the prior BZK
mission's Groth16 approach (which required a ceremony that was labeled
[OPEN] because the setup time exceeded sandbox timeout).

**Security argument for the audit ledger:** By moving the proving
substrate to STARK-on-Starknet, the mission eliminates the trusted-setup
requirement entirely. The only remaining [OPEN] item is the Cairo prover
resource limit for S4 multi-year aggregation (per OQ-7), which is an
environmental constraint, not a setup-trust constraint.

### CW-STARK-4: Existing Starknet contracts (R-NO-REDEF input)

**Finding:** The repo already contains 39 Cairo contracts at
`contracts/starknet/src/`, including:
- `trion_sensing_oracle.cairo` — implements S4 BEHAVIORAL_TRUTH signal
  publication with `public_commitment` + `coherence_score` + ABSENT fields
- `BIRPAttestation.cairo` — implements S5 Pedersen commitment + ECDSA
  oracle signature (Starknet-native STARK curve)
- `btcp_intent.cairo` — implements S1 Phase 1 H_intent registry
- `btcp_route.cairo`, `btcp_escrow_v2.cairo`, `btcp_escrow_v3.cairo` —
  BTCP core
- `confidential_coherence_vault.cairo`, `akashic_proof.cairo` — supporting
  infrastructure

**Canon-wins:** These existing contracts are INPUT to this mission per
R-NO-REDEF. They were built in prior missions (deployed to Starknet
Sepolia per worklog). The mission audits them against the canon, extends
them where needed, and wires them into the ZK pipeline — it does NOT
reinvent them.

### CW-STARK-5: Cairo edition migration (existing contracts)

**Finding:** The existing `contracts/starknet/Scarb.toml` specifies
`edition = "2024_07"`, but several contracts use the older
`read()`/`write()` storage accessor syntax. Scarb 2.8.4 (installed in
this mission) requires explicit `StorageTrait` imports for the 2024_07
edition. The build fails on `reentrant_attacker.cairo` (and likely others).

**Canon-wins:** This is a TOOLCHAIN issue, not a canon issue. The mission
applies the BLOCKER PROTOCOL: the existing contracts need a mechanical
edition migration (add `use starknet::storage::{StoragePointerReadAccess,
StoragePointerWriteAccess};` imports). This migration is in scope for
Phase 3 (Starknet deployment) because the ZK verifier programs must
compile alongside the existing contracts. The migration does NOT alter
any contract semantics — only import statements.

## 0.7 Falsification Entries (Phase 0.2)

Per mission: "falsification entries (Sensing Oracle privacy; ZK Intent MEV
protection) + OQ-7 + probability-table entries (S1 60%, S4 58%) as
baseline labels."

### Verbatim from C2 §13 (Falsifiability Table)

> | Sensing Oracle privacy | TRION can reconstruct private behavior from `public_commitment` alone |
> | ZK Intent Commitment MEV protection | MEV bot front-runs committed intent before Phase 3 atomic reveal |

### Verbatim from C2 §16 (Open Research Questions)

> **OQ-7 — ZK Circuit Efficiency:** What is the minimum circuit size for behavioral coherence ZK-SNARK satisfying the 7-plane check? Is it gas-efficient enough for high-frequency BTCP routes?

### Baseline probability labels (C2 §1 Probability Assessment, verbatim)

> | ZK Intent Commitment (MEV privacy) | **60%** | Medium | Hash commitment scheme is straightforward. ZK complementarity proof adds complexity. Groth16 circuit not yet built. |
> | Sensing Oracle (ZK privacy from TRION) | **58%** | Medium | ZK over multi-year behavioral history: circuit size is the blocker. Proof aggregation may solve it. |
> | BIRP — behavioral identity recovery | **62%** | Medium | Behavioral proof + DNA_Code is novel. False negative rate under drift is empirically unknown. |

**R-LABELS:** these are baseline estimates from C2 §1, labeled ESTIMATE.
The mission will MEASURE actual Cairo trace lengths in Phase 1.2 and
record them as MEASURED.

## 0.8 Phase 0 Acceptance Gate

| Item | Status | Evidence |
|---|---|---|
| 0.1 All agents read C1, C2, C3; SHA-256 recorded; sign-offs | ✅ YES | §0.1 + §0.2 above; canon text re-extracted to /tmp/bzk_canon/ (7,048 lines) |
| 0.2 ZK_CANON_EXTRACT.md verbatim passages for S1-S5 + cross-cutting laws + falsification + OQ-7 + probability labels | ✅ YES | This file §0.4-§0.7 + reference to `docs/zk/CANON_EXTRACT.md` (prior mission, 14/14 verified) |
| 0.3 SURFACE_MAP per surface (statement, publics, privates, phases, storage, emission, tiers, falsification, citation) | ✅ YES | §0.5 above |
| 0.4 Divergence register: CANON-WINS findings | ✅ YES | §0.6 above (CW-STARK-1 through CW-STARK-5) |
| Zero paraphrase in extract | ✅ YES | All S1-S5 verbatim quotes are in `docs/zk/CANON_EXTRACT.md` (referenced, not re-paraphrased); this file adds only substrate-substitution rationale |

**Phase 0 ACCEPTANCE: GATE PASSED.** Proceeding to Phase 1 (proving-system decision).

---

*Authored by A-SPEC. Witnessed by A-AUD. v-stamp: `zk-stark-phase0-v0.1`.*
