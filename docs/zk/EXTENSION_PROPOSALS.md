# EXTENSION_PROPOSALS — TRION BZK Activation (D16)

> **Authored by:** A-DOCS (documentation engineer) — Task ID: BZK-PHASE-8
> **D-item:** D16 — EXTENSION-PROPOSALS filed, segregated, not merged
> **v-stamp:** `bzk-extension-proposals-v0.1`
>
> **PURPOSE (per mission Phase 8 + D16):** this file segregates the
> beyond-scope items as explicit extension proposals (EP-1 through
> EP-5). They are **NOT merged into the core BZK activation docs**
> (`docs/zk/BZK.md`, `docs/proofs/bzk_activation.json`,
> `docs/zk/ZK_SURFACE_MAP.md`). Each EP is a proposal awaiting
> separate future work; none is presented as a commitment.
>
> **R-LABELS:** every EP carries a label (OPEN or GATED-OPEN per
> R-LABELS). Each carries: motivation, scope, threshold criteria
> for activation, label, and the canon citation that authorizes it.

---

## EP-1: S4 Multi-Year Aggregation (Plonky2/Nova Recursive Composition)

**Label:** `GATED-OPEN`

**Canon citation:**
- BTCP §7.1 verbatim (per `CANON_EXTRACT.md §4.6`): "[CONJECTURE — circuit construction not yet completed. Estimated circuit size: 500k-2M constraints. Proof aggregation likely required for efficiency.]"
- BTCP §14.1 Phase 4 item 23 verbatim (per `CANON_EXTRACT.md §4.9`): "23. `zk_behavioral_credential/` (LONG TERM — requires proof aggregation). Multi-year behavioral record as ZK circuit input. Proof aggregation (recursive proofs) for efficiency."
- WP-Mar §16 verbatim (per `CANON_EXTRACT.md §4.7`): "Behavioral ZK: 'My behavioral history satisfies condition C without revealing my behavioral history.' Hidden information is dynamic, growing, and backed by the Akashic Index."
- WP-Mar §16 verbatim (per `CANON_EXTRACT.md §4.8`): "[CONJECTURE — technical feasibility]: ZK proofs over behavioral commitments are constructible using Groth16, PLONK, or STARKs. Computational cost is non-trivial but decreasing. Specific circuit construction requires cryptographic engineering work not yet completed."
- BTCP §16 OQ-7 verbatim (per `CANON_EXTRACT.md §4.10`): "OQ-7 — ZK Circuit Efficiency: What is the minimum circuit size for behavioral coherence ZK-SNARK satisfying the 7-plane check? Is it gas-efficient enough for high-frequency BTCP routes?"

**Motivation:**
The single-epoch base case for S4 (Sensing Oracle) is MEASURED at
3,298 constraints (Phase 3, reproduced 5/5 in A-AUD §6). This proves
the per-epoch circuit is well-formed. The canon's actual S4 scope per
BTCP §14.1 #23 is "Multi-year behavioral record as ZK circuit input.
Proof aggregation (recursive proofs) for efficiency" — i.e., the
recursive composition over many epochs. The 500k-2M CONJECTURE
estimate (BTCP §7.1) refers to this multi-year aggregation, NOT the
per-epoch base.

A naive verifier-chain approach (Approach (a) in `FEASIBILITY_AND_SETUP.md §4.3`) is N × 3,298 constraints with N verify calls on-chain. For 1,000 epochs: ~3.3M constraints + ~1,000 verify calls (~250k gas each = 250M gas total — exceeds Ethereum block gas limit of 30M). NOT gas-efficient per OQ-7.

The recursive composition (Approach (b) Nova folding or Approach (c)
Plonky2/Plonky3 STARK recursion) gives constant-size proof regardless
of N with a single verify call. This is the canon-aligned path.

**Scope:**
- Install Plonky2 (or Nova) Rust toolchain
- Build a 2-epoch recursive prototype using the existing single-epoch circuit (`zk-circuits/zk_behavioral_credential/circuit.circom`) as the base case
- MEASURED recursion overhead per fold
- MEASURED verifier gas per aggregated proof
- Comparison vs Approach (a) verifier-chain (linear cost)
- Multi-year dataset integration with Akashic Index append-only log
- 7-plane coherence check preservation under recursive composition

**Threshold criteria for activation (per Phase 1 §4.5):**
1. Plonky2 (or Nova) Rust toolchain installed in build environment
2. 2-epoch recursive prototype built using existing single-epoch circuit as base
3. MEASURED recursion overhead < 2× per-epoch base case (i.e., < 6,596 constraints added per fold)
4. MEASURED verifier gas < 500k gas per aggregated proof
5. 7-plane coherence check soundness preserved under recursion
6. Independent verifier (A-AUD or successor) reproduces MEASURED values 5/5

When all 6 criteria are met, S4 status changes from GATED-OPEN to
IMPLEMENTABLE-NOW. Per mission R-ORDER + CW-3: **NO partial claim of
S4 activation is made until all 6 criteria are met.** A-AUD §8
verified no silent activation in Phases 2–7.

**Owner:** operator's responsibility post-mission (or future mission
phase). Out of scope for BZK-PHASE-8.

**Status:** `GATED-OPEN`. Threshold criteria documented.

---

## EP-2: S5 BIRP Recovery Path (Phases 1-5 of Recovery)

**Label:** `GATED-OPEN`

**Canon citation:**
- WP-Mar §16 verbatim (per `CANON_EXTRACT.md §5.1`): "The BIRP Claim: Behavioral history is a stronger identity root than secret possession. Three years of consistent on-chain behavior cannot be stolen, lost, or forgotten — it is permanently recorded in an append-only immutable ledger."
- WP-Mar §16 verbatim (per `CANON_EXTRACT.md §5.2`): "BIRP_anchor = Hash_DNA(BEO_baseline || Hash(DNA_Code) || enrollment_timestamp || behavioral_entropy_seed). Stored in Akashic Index: BIRP_anchor — permanent, immutable. Not stored: DNA_Code — ever."
- WP-Mar §16 verbatim (per `CANON_EXTRACT.md §5.3`): "Recovery Phases 1-5: Phase 1 DNA_Code verification (timing_window: exact, zero tolerance; length_check: exact, partial submission silently rejected; hash_check: dual-strand verification) → Phase 2 Behavioral proof (TRION queries Akashic Index for BEO; generates challenge from lived behavioral knowledge; behavioral_match required > 0.85) → Phase 3 Temporal cluster challenge → Phase 4 Conscious Layer verification (3 independent human verifiers; 2-of-3 required) → Phase 5 7-day waiting period (notification sent to all BEO cluster addresses; real owner can object; fraudulent recovery: blocked and permanently recorded)."
- WP-Mar §16 verbatim (per `CANON_EXTRACT.md §5.4`): "[CONJECTURE — false negative rate under behavioral drift requires empirical validation and threshold-setting.]"
- WP-Mar §16 verbatim (per `CANON_EXTRACT.md §5.6`): "BIRP as identity primitive: NOVEL — seeking prior art."

**Motivation:**
The S5 enrollment store is LIVE in `zk-circuits/commitments/birp_store.py`
(Phase 2.4). It stores `BIRP_anchor` only — NEVER stores `DNA_Code`
content, length, or timing (VERIFIED by A-AUD §4 grep). The recovery
path (WP-Mar §16 Phases 1-5) is a multi-factor verification protocol
involving:
1. DNA_Code verification (timing, length, dual-strand hash) — Z10 Part B SYNTHETIC-DEMO only
2. Behavioral proof (challenge from lived behavioral knowledge; match > 0.85) — Z11 SYNTHETIC-DEMO only (NEVER as fact per WP-Mar §16 CONJECTURE)
3. Temporal cluster challenge — not built
4. Conscious Layer (high-value accounts, 3 human verifiers, 2-of-3) — not built (operator's responsibility post-mission)
5. 7-day waiting period + BEO cluster notification — operational but not built

The drift false-negative rate is CONJECTURE per WP-Mar §16 verbatim.
Mission Z11 tested it SYNTHETIC-DEMO only (0 false negatives across
1,000 synthetic profiles, drift σ=0.01 over 100 epochs, cosine
similarity threshold > 0.85). NEVER presented as fact.

**Scope:**
- Empirical drift false-negative rate measurement over a real behavioral dataset (or a larger SYNTHETIC-DEMO set with documented assumptions)
- Temporal cluster challenge implementation
- Conscious Layer 2-of-3 verification implementation (requires human verifier infrastructure; operator's responsibility)
- 7-day waiting period + BEO cluster notification wiring
- Recovery path integration tests with full negative-pair coverage
- Independent verifier reproduction

**Threshold criteria for activation:**
1. Empirical drift false-negative rate measured over a documented dataset (real or larger SYNTHETIC-DEMO with documented assumptions)
2. Drift false-negative rate below an agreed threshold (per WP-Mar §16 CONJECTURE — threshold TBD by separate study)
3. Temporal cluster challenge implemented + tested
4. Conscious Layer 2-of-3 verification implemented (operator infrastructure)
5. 7-day waiting period + BEO cluster notification wired
6. Recovery path integration tests passing (full negative-pair coverage)
7. Independent verifier (A-AUD or successor) confirms no CONJECTURE-as-fact violations

When all 7 criteria are met, S5 recovery path status changes from
GATED-OPEN to IMPLEMENTABLE-NOW. Per mission R-ORDER: **NO partial
claim of S5 recovery activation is made until all 7 criteria are met.**
A-AUD §8 verified no silent activation in Phases 2–7.

**Owner:** operator's responsibility post-mission (Conscious Layer
requires human verifier infrastructure; drift study requires real
behavioral dataset or documented SYNTHETIC-DEMO assumptions).

**Status:** `GATED-OPEN`. Threshold criteria documented.

---

## EP-3: Mainnet Deployment

**Label:** `OPEN`

**Canon citation:**
- BTCP §14.1 Phase 4 (per `CANON_EXTRACT.md §1.6, §2.4, §3.6, §4.9`) — Phase 4 items 19-23 (ZK circuits build); mission scope per Phase 0 R-CHANNELS / R-NO-REDEF: "Mainnet deployment — testnet only (Phase 4)" (per `docs/zk/ZK_SURFACE_MAP.md` § Cross-Cutting)
- Phase 4 worklog: "Mainnet deployment [OPEN] per R-LABELS (operator's responsibility post-mission)."

**Motivation:**
Phase 4 deployed the 3 verifier contracts (`TravelRuleCompliance.sol`,
`IntentCommitmentRegistry.sol`, `ComplementarityVerifier.sol`) to 2
local Hardhat testnet VMs with transaction hashes recorded (R-LABELS:
VERIFIED). Mainnet deployment is OUT OF SCOPE per mission Phase 0
R-CHANNELS / R-NO-REDEF decision: "Mainnet deployment — testnet only
(Phase 4)."

**Scope:**
- Deploy `TravelRuleCompliance.sol`, `IntentCommitmentRegistry.sol`,
  `ComplementarityVerifier.sol` to a public EVM testnet (Sepolia /
  Holesky / Polygon Amoy / etc.) — Stage 1
- After testnet soak + external audit, deploy to EVM mainnet — Stage 2
- Plug in real Groth16 leaf verifiers (exported `verifier.sol` per
  circuit — requires Phase 3 BLOCKER closure first)
- Mainnet ceremony for Groth16 trusted setup (Powers of Tau phase 1 +
  phase 2 — at least 3 independent contributors per R-SETUP)
- Mainnet monitoring + incident response

**Threshold criteria for activation:**
1. Phase 3 BLOCKER closed (Groth16 setup + prove/verify round-trip executed)
2. Exported `verifier.sol` plugged into `ComplementarityVerifier.setVerifier`
3. Z1, Z3-rt, Z4, Z12 transition from `[OPEN]` to `VERIFIED` (round-trip)
4. D5 + D12 transition from PARTIAL to YES
5. External security audit (EP-4) completed
6. Testnet soak period (suggested: 30-90 days) with no incidents
7. Mainnet ceremony executed (Groth16 Powers of Tau phase 1 + phase 2 with at least 3 independent contributors per R-SETUP)

**Owner:** operator's responsibility post-mission.

**Status:** `OPEN`. Testnet deployments exist (2 local Hardhat VMs);
public testnet deployment is the next milestone; mainnet is a
future milestone gated by Phase 3 BLOCKER closure + EP-4 external
audit + ceremony.

---

## EP-4: External Security Audit

**Label:** `OPEN`

**Canon citation:**
- Mission Phase 0 R-CHANNELS / R-NO-REDEF (per `docs/zk/ZK_SURFACE_MAP.md` § Cross-Cutting): "External security audit — operator's responsibility post-mission."
- Mission Phase 7 audit (`docs/zk/A_AUD_ledger.md`): independent verifier (A-AUD) — but A-AUD is an internal mission agent, NOT an external security firm. The audit verifies canon-citation match, R-ORDER, ABSENT enforcement, AWA freeze no-override, measurement reproduction, label-evidence match, S4 status. It is NOT a formal external security audit covering side-channel analysis, formal verification of Solidity (e.g., Certora), Groth16 algebraic soundness proofs, etc.

**Motivation:**
The Phase 7 audit (A-AUD) is internal to the mission. A formal external
security audit is required before mainnet deployment (EP-3 Stage 2). This
audit should cover:
- Solidity formal verification (Certora or similar)
- Side-channel analysis (timing, memory, storage)
- Groth16 algebraic soundness proofs (independent cryptographic review)
- Circom circuit soundness review (no under-constrained signals)
- Trusted setup ceremony review (when EP-3 Stage 2 executes)
- Integration test coverage review (Phase 5 modules + Phase 6 Z-battery)
- Threat model review (Beyond-TRION-ZK surface — what BZK does NOT cover)

**Scope:**
- Engage an external security firm (e.g., Trail of Bits, OpenZeppelin, Least Authority, etc.)
- Provide: canon extract, surface map, Phase 3 benchmarks, Phase 4 contracts + Hardhat tests, Phase 5 integration modules, Phase 6 Z-battery results, Phase 7 audit ledger, Phase 8 documentation set
- External firm produces: audit report with findings + severity ratings + remediation plan
- Findings remediated before EP-3 Stage 2 (mainnet deployment)

**Threshold criteria for activation:**
1. Phase 3 BLOCKER closed (so the round-trip artifacts exist for external review)
2. EP-3 Stage 1 (public testnet deployment) completed
3. External security firm engaged
4. External audit report produced (no critical findings, or critical findings remediated)
5. Re-audit after remediation (if any critical findings)

**Owner:** operator's responsibility post-mission.

**Status:** `OPEN`. Not engaged. Required before mainnet deployment
(EP-3 Stage 2).

---

## EP-5: Multi-Source Ingestion

**Label:** `OPEN`

**Canon citation:**
- Mission Phase 0 R-CHANNELS / R-NO-REDEF (per `docs/zk/ZK_SURFACE_MAP.md` § Cross-Cutting): single-source ingestion (Alchemy) is the current BZK mission's operational assumption. Multi-source ingestion is not a ZK surface per se, but it is a precondition for the Witness World's data integrity (the Akashic Index is append-only; multi-source ingestion prevents single-source censorship).

**Motivation:**
The current BZK activation uses single-source ingestion (Alchemy) for
EVM testnet data (BTC lock tx verification, BTCPIntent monitoring,
BTCPRoute monitoring, BTCPEscrow monitoring). This is acceptable for
testnet soak but is a single point of failure for mainnet.

Multi-source ingestion would:
- Diversify RPC providers (Alchemy + Infura + QuickNode + self-hosted
  reth/erigon + P2P (devp2p))
- Cross-validate block headers + transaction receipts across sources
  (redundant verification)
- Detect provider-level censorship (e.g., if Alchemy silently filters
  a transaction, the other sources would surface it)
- Support the Akashic Index append-only invariant (multi-source
  confirmation before commit)

**Scope:**
- Multi-source RPC client abstraction in `rust/src/adapters/evm.rs`
  (currently single-source Alchemy)
- Cross-validation layer (redundant block header verification)
- Censorship detection (provider-level anomaly detection)
- Multi-source Akashic Index commit (multi-source confirmation before
  `akashic_root.compute_root`)
- Test suite for multi-source scenarios (provider failure, provider
  censorship, provider divergence)

**Threshold criteria for activation:**
1. Multi-source RPC client abstraction implemented
2. Cross-validation layer implemented + tested
3. Censorship detection implemented + tested
4. Multi-source Akashic Index commit implemented + tested
5. Test suite covering: provider failure, provider censorship, provider divergence, multi-source agreement
6. Independent verifier (A-AUD or successor) confirms Akashic Index append-only invariant preserved under multi-source

**Owner:** operator's responsibility post-mission (or future mission
phase).

**Status:** `OPEN`. Not in scope for BZK-PHASE-8. Documented as a
precondition for mainnet-grade Witness World data integrity.

---

## Summary Table

| EP | Title | Label | Threshold Criteria Count | Owner |
|---|---|---|---|---|
| EP-1 | S4 multi-year aggregation (Plonky2/Nova) | GATED-OPEN | 6 | operator post-mission |
| EP-2 | S5 BIRP recovery path | GATED-OPEN | 7 | operator post-mission |
| EP-3 | Mainnet deployment | OPEN | 7 | operator post-mission |
| EP-4 | External security audit | OPEN | 5 | operator post-mission |
| EP-5 | Multi-source ingestion | OPEN | 6 | operator post-mission |

**Total:** 5 extension proposals. 2 GATED-OPEN (EP-1, EP-2 — threshold
criteria documented per Phase 1 §4.5 + WP-Mar §16 CONJECTURE). 3 OPEN
(EP-3, EP-4, EP-5 — awaiting operator's post-mission work).

**Segregation policy:** these proposals are NOT merged into the core
BZK activation docs. The core docs are:
- `docs/zk/CANON_EXTRACT.md` (Phase 0.2 verbatim canon)
- `docs/zk/ZK_SURFACE_MAP.md` (Phase 0.3 + Phase 8.1 final status)
- `docs/zk/FEASIBILITY_AND_SETUP.md` (Phase 1 verdicts)
- `docs/zk/PHASE3_BENCHMARKS.md` (Phase 3 MEASURED + BLOCKER)
- `docs/zk/Z_BATTERY_RESULTS.md` (Phase 6 Z1-Z14)
- `docs/zk/A_AUD_ledger.md` (Phase 7 audit, v-stamp `bzk-audit-v0.1`)
- `docs/zk/BZK.md` (Phase 8.2 spec-anchored reference)
- `docs/proofs/bzk_activation.json` (Phase 8.3 evidence ledger)
- `docs/RUN_IT_YOURSELF.md` § "ZK Activation (BZK)" (Phase 8.4)
- `docs/zk/COMMUNITY_ADDENDUM_DRAFT.md` (Phase 8.5 DRAFT)

The core docs report honest status (13/18 YES, 2 PARTIAL, 3 INCOMPLETE,
0 FAIL). The extension proposals document the beyond-scope items
without merging them into the core activation claims. Per mission
FORBIDDEN: the AGREEMENT STATEMENT is NOT emitted at this phase
because D5, D12, D18 are not full YES (D5 + D12 PARTIAL; D18 STILL
INCOMPLETE).

---

*v-stamp: `bzk-extension-proposals-v0.1`. Authored by A-DOCS (Phase 8,
D16). Status: 5 extension proposals filed, segregated, not merged.
2 GATED-OPEN (EP-1, EP-2). 3 OPEN (EP-3, EP-4, EP-5). Per mission
FORBIDDEN: AGREEMENT STATEMENT NOT emitted — Phase 9 owns the
AGREEMENT GATE.*
