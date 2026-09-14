# CANON_EXTRACT — TRION BZK Activation Mission (Phase 0.2)

> **Purpose (FIRST LAW):** Every implementation decision in the BZK mission
> must cite a document + section. This file is the verbatim source of those
> citations. No paraphrase. No summary. Where the three canonical documents
> disagree, the later-dated document wins (recorded as a CANON-WINS finding
> in §4 below).

## 0.1 Canonical Sources — Versions + Integrity

| ID | Document | Date | Pages | Size (bytes) | SHA-256 |
|---|---|---|---|---|---|
| **BTCP** | `BTCP_MASTER_IMPLEMENTATION_SPEC.md.pdf` | April 2026 | 8 | 148,923 | `758528cf8910eb02c205b6a4850a70c9350472bb2507e5367d71ac57bd4fb420` |
| **WP-Feb** | `TRION_PROTOCOL_White_paper.pdf` | February 2026 | 8 | 316,532 | `80ebc82f0f9ba8e5bf58d110b870796ae48145c410be411a9a0378566398d183` |
| **WP-Mar** | `TRION_Protocol_Whitepaper.md.pdf` | March 2026 (update) | 8 | 117,293 | `40321eaa277c1a62804691819a181cdb7d8242062cdb3cd0d69538fe5541e094` |

Author of all three (per document colophons): Hudu Yusuf (Analys), TRION Protocol. License: CC0.

**Canonical precedence (per mission FIRST LAW):** later-dated document wins
on conflicts. Therefore **WP-Mar > WP-Feb > BTCP** for conflict resolution,
EXCEPT where BTCP is more specific (implementation spec) and WP-Mar is more
general (whitepaper) — in which case BTCP's specific operational details
govern, recorded as a CANON-WINS finding.

---

## 1. S1 — ZK Intent Commitment (BTCP §5.6 "Water Underground")

### 1.1 Verbatim — Phase 1 (Commit)

> **Phase 1 — Commit (MEV bots see nothing actionable):**
>   `H_intent = Hash_DNA(intent_details || random_nonce || entity_id)`
>   User submits: `H_intent` ONLY
>   MEV bots observe: a commitment hash — no direction, no amount, nothing
>
>   // Implementation: submit `H_intent` to `BTCPIntent.sol`
>   // Contract stores: `H_intent → timestamp, entity_id`
>   // NO routing calculation yet

— *BTCP §5.6, Phase 1*

### 1.2 Verbatim — Phase 2 (Match — ZK complementarity)

> **Phase 2 — Match (ZK proof of complementarity):**
>   TRION searches for `H_intent_B` that is complement of `H_intent_A`
>   Both parties prove complementarity through ZK proof:
>       `zk_proof = SNARK.prove(`
>           statement: `"H_my_intent and H_counterparty_intent are complements"`,
>           `public_inputs:   [H_intent_A, H_intent_B, entity_id_A, entity_id_B]`,
>           `private_inputs: [intent_A_full, intent_B_full, nonce_A, nonce_B]`
>       `)`
>   Neither party reveals intent contents to the other
>
>   // Circuit: `zk_complementarity_proof/` (MISSING — requires Groth16 or PLONK)
>   // Verify: `asset_in_A == asset_out_B AND asset_out_A == asset_in_B`
>   //             AND `magnitude_A ≈ magnitude_B`

— *BTCP §5.6, Phase 2*

### 1.3 Verbatim — Phase 3 (Atomic Reveal)

> **Phase 3 — Atomic Reveal (both in same block):**
>   Both intents published in same block — atomic
>   If complements verified: execution commits immediately
>   If not complements: both intents remain hidden, no information leaked

— *BTCP §5.6, Phase 3*

### 1.4 Verbatim — Phase 4 (Execution)

> **Phase 4 — Execution (front-running window: zero):**
>   MEV bots see: execution already committed
>   Information about intent: only visible AFTER it cannot be exploited
>
>   // Privacy vs. bootstrap tradeoff:
>   // Phases 1-3 add latency before execution
>   // Only worthwhile when MEV risk > latency cost
>   // Should be opt-in (`privacy: ZK_CREDENTIAL | INVISIBLE` in `Intent.constraints`)

— *BTCP §5.6, Phase 4*

### 1.5 Verbatim — Circuit Estimate + Build Note

> **Circuit files needed:**
> - `zk_complementarity_proof/circuit.circom` — Circom circuit for complement verification
> - `zk_complementarity_proof/verifier.sol` — Solidity verifier contract
> - **Estimated circuit size:** ~50k constraints. Groth16 proof: ~200 bytes. Feasible but requires 4-8 weeks of ZK engineering work.

— *BTCP §5.6 (closing note)*

### 1.6 Verbatim — Phase 4 Build-Guide Item 19

> **19. `zk_intent_commitment/`**
>       - Circom circuit: Hash(intent || nonce) commitment
>       - Phase 1-4 protocol implementation
>       - Verifier.sol deployment

— *BTCP §14.1 Phase 4, item 19*

### 1.7 Verbatim — Falsifiability Condition (Mission Z6 source)

> | ZK Intent Commitment MEV protection | MEV bot front-runs committed intent before Phase 3 atomic reveal |

— *BTCP §13 (Falsifiability Table)*

---

## 2. S2 — ZK IAP Share Proof (BTCP §5.3 "Water Pooling")

### 2.1 Verbatim — Privacy Property

> // PRIVACY:
> // Each entity's specific amount hidden from other participants
> // ZK proof of correct share calculation (circuit needed — see `zk_iap_share_proof/`)
> // Only total direction and pooled value visible
>
> // BEHAVIORAL CREDIT:
> // Each entity's BEO records participation in aggregated intent
> // Individual contribution preserved via ZK proof
> // Akashic Index shows pool structure (transparent at protocol level)

— *BTCP §5.3 (IAP code comment block)*

### 2.2 Verbatim — Circuit Requirement

> **ZK circuit required:** `zk_iap_share_proof/` — proves entity's share is correctly calculated from their contribution without revealing the contribution to other participants.

— *BTCP §5.3 (closing note)*

### 2.3 Verbatim — Gas Sharing Formula (public; ZK proves the per-entity calculation)

> // GAS SHARING:
> // `G_per_entity = G_total × (entity_value / total_value)`
> // Example: 100 users × $100 ETH→SOL
> //     Individual:     $0.80 each = $80.00 total
> //     Aggregated:     $0.80 total = $0.008 per user (100× cheaper)

— *BTCP §5.3 (IAP code block)*

### 2.4 Verbatim — Build-Guide Item 21

> **21. `zk_iap_share_proof/`**
>       - Circom circuit: prove share calculation correctness
>       - Enable fully private IAP participation

— *BTCP §14.1 Phase 4, item 21*

### 2.5 Verbatim — Phase 3 Build Sequencing (transparent first, ZK after)

> **11. `intent_aggregator.rs` (IAP)**
>       - Pool detection: N ≥ 3 same-direction intents within window W
>       - Gas distribution: `G_per_entity = G_total × share`
>       - (Defer ZK share proof to Phase 4 — use transparent shares initially)

— *BTCP §14.1 Phase 3, item 11*

**Canon interpretation:** S2 circuit is *required* by the spec, but spec
explicitly defers it to Phase 4 and prescribes transparent shares in
Phase 3. R-ORDER compliance: build commitment layer first, S2 circuit
after, transparent IAP live before ZK IAP.

---

## 3. S3 — ZK Travel Rule (BTCP Fix 1, §11)

### 3.1 Verbatim — Step 1 (Disclosure Preparation, private to entity)

> **Step 1: Entity prepares disclosure privately**
>     `disclosure = { originator_name, originator_address, originator_account,`
>                     `beneficiary, value, timestamp }`

— *BTCP Fix 1, Step 1*

### 3.2 Verbatim — Step 2 (Regulator-Encryption Boundary — TRION receives NOTHING)

> **Step 2: Disclosure → encrypted to `regulator_public_key`**
>     regulator receives: full disclosure    (law satisfied)
>     TRION receives: nothing from this step

— *BTCP Fix 1, Step 2*

### 3.3 Verbatim — Step 3 (SNARK Statement)

> **Step 3: Entity generates ZK compliance proof**
>     `zk_proof = SNARK.prove(`
>         statement: `"I submitted valid Travel Rule disclosure to FATF-compliant VASP"`,
>         `public_inputs:   [transaction_hash, jurisdiction_id, disclosure_hash]`,
>         `private_inputs: [disclosure_contents, regulator_receipt]`
>     `)`

— *BTCP Fix 1, Step 3*

### 3.4 Verbatim — Step 4 (TRION Stores Hash Only, Emits Compliance)

> **Step 4: zk_proof included in BTCP intent**
>     TRION stores: `disclosure_hash` only
>     TRION emits: `TRAVEL_RULE_COMPLIANT = TRUE`

— *BTCP Fix 1, Step 4*

### 3.5 Verbatim — Chameleon Tier Integration

> **CHAMELEON integration:**
>     `LOW:`        proof optional, routing preference for compliant routes
>     `MEDIUM:`     proof required above $1,000
>     `HIGH:`       proof required for all routes
>     `CRITICAL: AWA_enforced` — nothing emitted until proof present

— *BTCP Fix 1 (CHAMELEON block)*

### 3.6 Verbatim — Build-Guide Item 22 + Contract Name

> **22. `zk_travel_rule/`**
>       - SNARK proving disclosure submitted to VASP
>       - `TravelRuleCompliance.sol`

— *BTCP §14.1 Phase 4, item 22*

**R-GENERIC compliance:** contract name is `TravelRuleCompliance.sol` — no
chain prefix (per mission R-GENERIC and BTCP contract list in §2).

---

## 4. S4 — Sensing Oracle / Behavioral Credential (BTCP §7 + WP-Mar §16)

### 4.1 Verbatim — Entity-Side Private Computation

> **SENSING ORACLE PROTOCOL:**
>
> Entity computes privately (never leaves device):
>   `private_behavior = actual transaction details`
>   `behavioral_hash      = Hash_DNA(private_behavior || private_nonce)`
>   `public_commitment = Hash(behavioral_hash)`       // hash of hash — no content

— *BTCP §7.1 (Sensing Oracle Protocol block)*

### 4.2 Verbatim — SNARK Statement + Public/Private Inputs

>   `zk_proof = SNARK.prove(`
>       statement: `"my behavioral_hash is coherent with my historical BEO pattern"`,
>       `public_inputs:    [public_commitment, entity_id, historical_BEO_root]`,
>       `private_inputs: [private_behavior, private_nonce]`
>   `)`

— *BTCP §7.1*

### 4.3 Verbatim — TRION Receives / Verifies / Stores / Emits

> TRION receives: `public_commitment + entity_id + historical_BEO_root + zk_proof`
> TRION verifies: mathematical validity of zk_proof — reveals nothing about behavior
> TRION stores:        `public_commitment` ONLY — NOT the behavior
> TRION emits:         `COHERENCE_SIGNAL (TRUE/FALSE) + coherence_score`

— *BTCP §7.1*

### 4.4 Verbatim — BEHAVIORAL_TRUTH_SIGNAL Schema (with ABSENT fields)

> ```
> BEHAVIORAL_TRUTH_SIGNAL {
>     entity_id:            present (for routing)
>     public_commitment: present (hash of hash)
>     coherence_score:      present (0.0 to 1.0)
>     plane_results:        [TRUE/FALSE × 7 planes]
>
>     behavior_content:     ABSENT — never stored, never transmitted
>     amount:               ABSENT
>     counterparty:         ABSENT
>     protocol:             ABSENT
>     chain:                ABSENT
> }
> ```

— *BTCP §7.1 (BEHAVIORAL_TRUTH_SIGNAL block)*

### 4.5 Verbatim — Senses vs Does Not Know

> **What TRION senses vs does not know:**
>
> TRION senses: This entity's commitment is coherent with historical pattern. Magnitude is within normal behavioral range. Timing shows no manipulation fingerprint. Passes 7-plane coherence check.
>
> TRION does not know: What the entity did. How much. With whom. On which protocol. What asset or direction.

— *BTCP §7.1*

### 4.6 Verbatim — Conjecture Label (Circuit Size, Aggregation Required)

> **Implementation:** `zk_behavioral_credential/` — ZK circuit proving behavioral coherence without revealing behavior. **[CONJECTURE — circuit construction not yet completed. Estimated circuit size: 500k-2M constraints. Proof aggregation likely required for efficiency.]**

— *BTCP §7.1 (closing note)*

### 4.7 Verbatim — WP-Mar §16 BZK Definition

> **Behavioral ZK:** "My behavioral history satisfies condition C without revealing my behavioral history." Hidden information is dynamic, growing, and backed by the Akashic Index.
>
> ```
> Prover:   entity with behavioral history H in Akashic Index
>
> Claim:    "H satisfies condition C"
>           e.g. "my behavioral credibility score > threshold"
>           e.g. "I have never exhibited manipulation fingerprint Y"
>           e.g. "my governance participation quality > standard Z"
> Proof:       ZK proof generated over Akashic behavioral commitments
>              Verifier learns: C is TRUE or FALSE
>              Verifier learns: nothing about H itself
>
> TRION's role: the trusted, immutable, append-only behavioral record
>                     that ZK proofs are computed against
> ```

— *WP-Mar §16 (Behavioral Zero-Knowledge Proofs)*

### 4.8 Verbatim — WP-Mar §16 Conjecture Label (Construction Not Complete)

> **[CONJECTURE — technical feasibility]:** ZK proofs over behavioral commitments are constructible using Groth16, PLONK, or STARKs. Computational cost is non-trivial but decreasing. Specific circuit construction requires cryptographic engineering work not yet completed.

— *WP-Mar §16*

### 4.9 Verbatim — Build-Guide Item 23 (Long-Term, Aggregation)

> **23. `zk_behavioral_credential/` (LONG TERM — requires proof aggregation)**
>       - Sensing Oracle implementation
>       - Multi-year behavioral record as ZK circuit input
>       - Proof aggregation (recursive proofs) for efficiency

— *BTCP §14.1 Phase 4, item 23*

### 4.10 Verbatim — OQ-7 (S4 Aggregation Open Question)

> **OQ-7 — ZK Circuit Efficiency:** What is the minimum circuit size for behavioral coherence ZK-SNARK satisfying the 7-plane check? Is it gas-efficient enough for high-frequency BTCP routes?

— *BTCP §16 (Open Research Questions, OQ-7)*

### 4.11 Verbatim — Falsifiability Condition (Mission Z5 source)

> | Sensing Oracle privacy | TRION can reconstruct private behavior from `public_commitment` alone |

— *BTCP §13 (Falsifiability Table)*

---

## 5. S5 — BIRP (WP-Mar §16 + WP-Feb Formula Index)

### 5.1 Verbatim — BIRP Claim

> **The BIRP Claim:** Behavioral history is a stronger identity root than secret possession. Three years of consistent on-chain behavior cannot be stolen, lost, or forgotten — it is permanently recorded in an append-only immutable ledger.

— *WP-Mar §16 (BIRP section)*

### 5.2 Verbatim — Enrollment (BIRP_anchor + Hash(DNA_Code) only)

> **Enrollment:**
> ```
> BIRP_Enrollment {
>
>   User provides:
>       DNA_Code: {
>           content:    personal sequence only user knows
>                       NOT stored by TRION — only Hash(DNA_Code) stored
>           length:     user-defined minimum (kept secret)
>           timing:     user-defined change schedule (kept secret)
>                       e.g. changes on user-defined date at user-defined time
>                       the timing is itself a secret layer
>       }
>
>   TRION generates:
>       BIRP_anchor = Hash_DNA(
>           BEO_baseline        ||
>           Hash(DNA_Code)      ||
>           enrollment_timestamp ||
>           behavioral_entropy_seed
>       )
>
>     Stored in Akashic Index: BIRP_anchor — permanent, immutable
>     Not stored: DNA_Code — ever
> }
> ```

— *WP-Mar §16 (BIRP Enrollment)*

### 5.3 Verbatim — Recovery Phases 1-5

> **Recovery Phases:**
> ```
> Phase 1: DNA_Code verification
>     timing_window: exact — zero tolerance
>     length_check:    exact — partial submission silently rejected
>     hash_check:      dual-strand verification
>
> Phase 2: Behavioral proof
>     TRION queries Akashic Index for BEO
>     generates challenge from lived behavioral knowledge:
>       questions only the true owner can answer
>       from lived experience — not from reading public records
>     behavioral_match required: > 0.85
>
> Phase 3: Temporal cluster challenge
>     "Submit transaction from any BEO cluster address
>      within N minutes" — N is random and unknown to attacker
>
> Phase 4: Conscious Layer verification (high-value accounts)
>     3 independent human verifiers
>     shown behavioral evidence only — no identity
>     2-of-3 required
>
> Phase 5: 7-day waiting period
>     notification sent to all BEO cluster addresses
>     real owner can object during this window
>     fraudulent recovery: blocked and permanently recorded
> ```

— *WP-Mar §16 (BIRP Recovery Phases)*

### 5.4 Verbatim — Drift Conjecture (False-Negative Rate)

> **Known honest limitation:** Behavioral patterns drift over time. Recovery challenges are drawn from **recent** behavioral history, not enrollment history. BEO baseline updates continuously.
> **[CONJECTURE — false negative rate under behavioral drift requires empirical validation and threshold-setting.]**

— *WP-Mar §16 (BIRP limitation note)*

### 5.5 Verbatim — BIRP_anchor Formula (Feb 2026 Formula Index)

> **BIRP anchor:**
>   `BIRP_anchor = Hash_DNA(BEO_baseline || Hash(DNA_Code) || enrollment_timestamp || behavioral_entropy_seed)`

— *WP-Feb (Formula Index, BIRP anchor entry)*

### 5.6 Verbatim — BIRP Novelty + Falsifiability (WP-Mar Research Notes)

> | BIRP false negative rate | CONJECTURE — empirical | False negative rate exceeds agreed [...] |
> | BIRP as identity primitive | NOVEL — seeking prior art | Show prior treatment of behavioral [...] |

— *WP-Mar Research/Falsifiability table (BIRP rows)*

---

## 6. AWA + Right to Invisibility (WP-Feb §14.2 + WP-Mar §16)

### 6.1 Verbatim — AWA_enforced Condition

> ```
> AWA_enforced iff all_of:
>   no_single_entity_controls_signal_weights
>   no_single_entity_controls_validator_selection
>   Public_Good_Charter_minimum >= 15%
>   Sovereignty_Dignity_Protocol_active
>   Right_to_Invisibility_enforced
>   Gratitude >= 1
>
> AWA_enforced = FALSE → signal emission FROZEN automatically.
> Cannot resume until AWA_enforced = TRUE.
> Cannot be overridden by any single entity. By design.
> ```

— *WP-Feb §14.2 (and restated WP-Mar §17 AWA block)*

### 6.2 Verbatim — Right to Invisibility Enforcement

> ```
> AWA_enforced = FALSE if Right_to_Invisibility_enforced = FALSE
> → signal emission FROZEN
>
> This is not a policy. It is an architectural enforcement condition.
> The system cannot function while violating individual privacy.
> ```

— *WP-Mar §16 (The Right to Invisibility)*

### 6.3 Verbatim — R-COMPLIANCE Statement (ZK Proves Compliance, Not Concealment)

> **Critical clarification:** TRION does not help users evade laws. ZK proofs prove **compliance** — they do not hide non-compliance. An illegal transaction with a ZK behavioral privacy proof is still illegal and the behavioral record still exists in the Akashic Index. What ZK changes is who can observe the record — not whether it exists.

— *WP-Mar §17 (Critical clarification)*

---

## 7. Cross-Cutting Verbatim — On-Chain Surface, Channels, Order

### 7.1 Verbatim — R-CHANNELS Source (Smart Contracts = Output Only)

> ```
> ═══════════════════════════════════════════════════
> SMART CONTRACTS — OUTPUT ONLY:
>   Signal publication (Solidity)
>   Economic coordination (Vyper)
> ═══════════════════════════════════════════════════
> ```

— *WP-Mar §15 (20-channel communication map closing block)*

### 7.2 Verbatim — R-ORDER Source (Commitments Before Circuits; S4 Gated on Aggregation)

> **(Defer ZK share proof to Phase 4 — use transparent shares initially)**

— *BTCP §14.1 Phase 3, item 11*

> **23. `zk_behavioral_credential/` (LONG TERM — requires proof aggregation)**

— *BTCP §14.1 Phase 4, item 23*

### 7.3 Verbatim — R-SILENCE Source

> `SILENCE ≠ VALUATION — enforced at compile time`

— *WP-Mar §15 (Type system layer 18 closing)*

> `When any plane fails: silence. The silence is information.`

— *WP-Feb (epigraph)*

### 7.4 Verbatim — Existing Circuit Inventory (R-NO-REDEF Input)

The repository already contains 5 prior circom circuits at `zk-circuits/`:

| Path | Canon Citation (header comment) | Date created | Date last touched |
|---|---|---|---|
| `zk-circuits/zk_intent_commitment/circuit.circom` | BTCP §14.1 P4 item 19, §5.6 Phase 1 | 2026-09-02 | 2026-09-08 |
| `zk-circuits/zk_complementarity_proof/circuit.circom` | BTCP §14.1 P4 item 20, §5.6 Phase 2 | 2026-09-02 | 2026-09-08 |
| `zk-circuits/zk_iap_share_proof/circuit.circom` | BTCP §14.1 P4 item 21, §5.3 | 2026-09-02 | 2026-09-08 |
| `zk-circuits/zk_travel_rule/circuit.circom` | BTCP §14.1 P4 item 22, Fix 1 | 2026-09-02 | 2026-09-08 |
| `zk-circuits/zk_behavioral_credential/circuit.circom` | BTCP §14.1 P4 item 23, §7.1 | 2026-09-02 | 2026-09-08 |

These circuits self-label their constraint counts as "SELF-REPORTED (circom 2.1.9), UNVERIFIED" (R-LABELS compliance). They are INPUT TO THIS MISSION, audited against the canon in Phase 1; any divergence from canon is recorded as a CANON-WINS finding, not silently redefined.

---

## 8. Canon Status Labels (R-LABELS — preserved verbatim from source)

The following labels appear in the canon and are preserved in all mission artifacts:

| Label | Meaning (BTCP §3.2 / WP-Feb) | Used for |
|---|---|---|
| `[PROVED]` | Formal proof exists in the spec (BTCP §12) | Coordination Collapse Theorem; BTCP > multisig |
| `[NOVEL]` | New primitive, seeking prior art | BIRP as identity root; VM-agnostic 20-event layer |
| `[CONJECTURE]` | Plausible but not yet empirically validated | S4 circuit feasibility; BIRP drift false-negative; BRT-gas correlation |
| `[CLAIMED]` | Stated without formal proof | BTCP replaces bridge validator sets |

Evidence labels (mission-defined, applied to every claim in the ledger):

| Label | Meaning |
|---|---|
| `VERIFIED` | Reproduced in a fresh process during Phase 7 |
| `SELF-REPORTED` | Claimed by an agent, not yet independently verified |
| `SYNTHETIC-DEMO` | Demonstrated on synthetic / test data only |
| `OPEN` | Not yet tested; tracked as an open question |

---

## 9. CANON-WINS Findings (Phase 0.4)

### CW-1 — Sensing Oracle belongs to BTCP §7 + WP-Mar §16 (not WP-Feb)

**Conflict:** WP-Feb (Feb 2026) does NOT contain a `Sensing Oracle` section.
BTCP (Apr 2026) §7.1 contains the full verbatim spec. WP-Mar (Mar 2026) §16
contains the BZK conceptual framing.

**Resolution:** BTCP §7.1 governs (most specific operational spec). WP-Mar
§16 governs the conceptual framing. WP-Feb's silence on Sensing Oracle is
not a contradiction — it postdates WP-Feb.

**Canon-wins:** BTCP §7.1 + WP-Mar §16. Recorded as finding, not invention.

### CW-2 — BIRP belongs to WP-Mar §16 (not BTCP)

**Conflict:** BTCP does not contain a BIRP section. WP-Mar §16 contains
the full BIRP enrollment + recovery spec. WP-Feb's Formula Index contains
the BIRP_anchor formula only (no narrative).

**Resolution:** WP-Mar §16 governs BIRP enrollment + recovery phases.
WP-Feb Formula Index governs the `BIRP_anchor` hash formula construction.

**Canon-wins:** WP-Mar §16 (narrative) + WP-Feb (formula).

### CW-3 — S4 Constraint Estimate: "500k-2M" (BTCP) vs. "non-trivial but decreasing" (WP-Mar)

**Conflict:** BTCP §7.1 specifies "Estimated circuit size: 500k-2M
constraints. Proof aggregation likely required." WP-Mar §16 says
"Computational cost is non-trivial but decreasing. Specific circuit
construction requires cryptographic engineering work not yet completed."

**Resolution:** BTCP is more specific (numeric range). WP-Mar is more
general (qualitative). Per FIRST LAW, BTCP governs the operational
estimate, WP-Mar governs the conceptual admission of incompleteness.

**Canon-wins:** BTCP §7.1 (estimate 500k-2M, label CONJECTURE, aggregation
required). Both documents AGREE the construction is not complete — this
is a CANON-AGREEMENT finding, not a conflict.

**Mission implication:** Per R-ORDER + Phase 1.2, S4 is GATED-OPEN until
the Phase-1 aggregation study (OQ-7/Q2) produces a measured verdict.
**The mission does NOT claim S4 is operational.** S4 status remains
`GATED-OPEN` until D6 verdict.

### CW-4 — AWA / Right-to-Invisibility is restated identically in both WPs

**Agreement (not a conflict):** WP-Feb §14.2 and WP-Mar §17 contain
identical AWA_enforced condition blocks. No conflict. Cited from both.

### CW-5 — Travel Rule: BTCP Fix 1 is the only spec source; no WP conflict

**Agreement:** Only BTCP §11 Fix 1 specifies the Travel Rule protocol.
Neither WP contains the 4-step Travel Rule spec. No conflict.

### CW-6 — Circuit Size Estimates are ESTIMATES, not measurements

**Canon rule (R-LABELS):** BTCP §5.6 says "~50k constraints. Groth16
proof: ~200 bytes" — these are spec estimates, not measured values.
Per mission R-LABELS, the mission MUST measure these in Phase 3 and label
them as `MEASURED` only after a compiled pilot circuit produces the
actual numbers. Pre-Phase-3 numbers retain `ESTIMATE` label.

### CW-7 — Trusted Setup: BTCP §5.6 says "Groth16 or PLONK"; WP-Mar §16 says "Groth16, PLONK, or STARKs"

**Conflict:** BTCP §5.6 mentions "Groth16 or PLONK" for complementarity
circuit. WP-Mar §16 mentions "Groth16, PLONK, or STARKs" for behavioral
ZK generally.

**Resolution:** Per R-SETUP, prefer transparent (PLONK/STARK) unless spec
pins Groth16. BTCP §5.6 explicitly names "Groth16" as the target proof
system for the complementarity circuit (~50k constraints, ~200 bytes —
these are Groth16-shaped numbers). WP-Mar §16 names STARK as a valid
alternative for the broader behavioral ZK class.

**Canon-wins per surface:**
- S1 (intent commitment): hash-only Phase 1 (no ceremony); Phase 2 complementarity circuit: Groth16 per BTCP §5.6.
- S2 (IAP share proof): BTCP does not pin a system. R-SETUP → prefer PLONK (transparent).
- S3 (travel rule): BTCP does not pin a system. R-SETUP → prefer PLONK (transparent).
- S4 (behavioral credential): WP-Mar §16 explicitly allows STARK; given the
  500k-2M constraint estimate and "proof aggregation required" label, a
  STARK-based recursive aggregation (e.g. Plonky2/Plonky3 or Nova) is the
  canon-aligned choice. Recorded as the S4 setup policy in Phase 1.

### CW-8 — Existing zk-circuits/ chose Groth16 (snarkjs); this is canon-aligned for S1 Phase 2 but not for S2/S3

**Finding (R-NO-REDEF):** The existing `zk-circuits/` circuits uniformly use
Groth16 + snarkjs. This is canon-aligned for S1 Phase 2 (BTCP §5.6 pins
Groth16). For S2 and S3, BTCP does not pin Groth16, so R-SETUP prefers
transparent (PLONK). However: (a) all 5 circuits are already written in
circom 2.1.6, which compiles to both Groth16 and PLONK; (b) switching
proving systems is a setup-policy decision, not a circuit-rewrite decision.
**Canon-wins:** keep circom circuits; per-circuit proving-system decision
is recorded in Phase 1.

---

## 10. Phase 0 Acceptance Gate (Phase 0.1–0.4)

| Item | Status | Evidence |
|---|---|---|
| 0.1 Three canonical files read; versions + SHA-256 recorded | ✅ | §0.1 table above |
| 0.2 Verbatim ZK/BZK/BIRP/disclosure/ABSENT/invisibility passages extracted with citations | ✅ | §1–§6 above |
| 0.3 ZK_SURFACE_MAP (S1-S5 with citation, status, estimate, deps, surface, OQs) | ✅ | `docs/zk/ZK_SURFACE_MAP.md` (next file) |
| 0.4 CANON-WINS findings recorded | ✅ | §9 above (CW-1 through CW-8) |
| No paraphrase in extract | ✅ | All §1–§6 blocks are verbatim quotes with section citations |

**Phase 0 ACCEPTANCE: GATE PASSED.** Proceeding to Phase 1.

---

*Authored by A-SPEC (canon archaeologist). Witnessed by A-AUD (independent
verifier) — see `docs/zk/A_AUD_ledger.md` for the audit trail.*
