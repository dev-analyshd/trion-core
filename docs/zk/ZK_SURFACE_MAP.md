# ZK_SURFACE_MAP — TRION BZK Activation (Phase 0.3)

> **Purpose:** one-row-per-surface map of the five ZK surfaces (S1-S5) the
> mission must activate. Each row carries: citation, spec status label,
> circuit-size estimate (labelled ESTIMATE until measured), dependencies,
> on-chain surface (R-CHANNELS), and open questions. Per R-LABELS, no
> estimate is presented as a measurement.

## Surface Status at a Glance

| ID | Surface | Citation | Spec Status | Existing Code | Phase-1 Verdict | Mission Status |
|---|---|---|---|---|---|---|
| S1 | ZK Intent Commitment (4-phase MEV privacy) | BTCP §5.6, §14.1 P4 #19 | `[PROVED-spec]` Phase 1 hash; Phase 2 circuit `[CLAIMED-feasible]` | `zk-circuits/zk_intent_commitment/circuit.circom` (Groth16, SELF-REPORTED 642 constraints) | `IMPLEMENTABLE-NOW` | IN-PROGRESS Phase 1 |
| S2 | ZK IAP Share Proof | BTCP §5.3, §14.1 P4 #21 | `[CLAIMED-feasible]` | `zk-circuits/zk_iap_share_proof/circuit.circom` (Groth16, SELF-REPORTED) | `IMPLEMENTABLE-NOW` | IN-PROGRESS Phase 1 |
| S3 | ZK Travel Rule | BTCP §11 Fix 1, §14.1 P4 #22 | `[CLAIMED-feasible]` | `zk-circuits/zk_travel_rule/circuit.circom` (Groth16, SELF-REPORTED) | `IMPLEMENTABLE-NOW` | IN-PROGRESS Phase 1 |
| S4 | Sensing Oracle / Behavioral Credential | BTCP §7.1 + WP-Mar §16, §14.1 P4 #23 | **`[CONJECTURE]`** (BTCP verbatim) | `zk-circuits/zk_behavioral_credential/circuit.circom` (single-epoch only, SELF-REPORTED 1319 constraints; multi-year aggregation OPEN) | `GATED-OPEN` (OQ-7/Q2 verdict required) | GATED — no operational claim |
| S5 | BIRP (Behavioral Identity Recovery Protocol) | WP-Mar §16 + WP-Feb Formula Index | `[NOVEL — seeking prior art]` + `[CONJECTURE]` (drift false-negative) | None — no existing code | `GATED-OPEN` (drift conjecture requires empirical validation) | GATED — enrollment store only (hash-only, no recovery path activated) |

---

## S1 — ZK Intent Commitment

**Citation:** BTCP §5.6 "Water Underground — ZK Intent Commitment (MEV
Privacy)"; BTCP §14.1 Phase 4 item 19.

**Spec status:** Phase 1 (commit) is `[PROVED-spec]` (hash-only, no ZK
needed). Phase 2 (complementarity SNARK) is `[CLAIMED-feasible]` with
BTCP verbatim estimate "~50k constraints. Groth16 proof: ~200 bytes."

**Phases (verbatim, BTCP §5.6):**
- Phase 1 — Commit: `H_intent = Hash_DNA(intent_details || random_nonce || entity_id)`, submit `H_intent` ONLY to `BTCPIntent.sol`. NO routing calculation yet.
- Phase 2 — Match: ZK proof of complementarity. Public inputs `[H_intent_A, H_intent_B, entity_id_A, entity_id_B]`; private inputs `[intent_A_full, intent_B_full, nonce_A, nonce_B]`.
- Phase 3 — Atomic Reveal: both intents published in same block; if not complements, both stay hidden.
- Phase 4 — Execution: MEV bots see execution already committed.

**Circuit estimate (ESTIMATE, not measurement):** ~50k constraints
(BTCP §5.6). Proof size ~200 bytes (Groth16). Must be MEASURED in Phase 3.

**Proving system decision (Phase 1, R-SETUP):** BTCP §5.6 verbatim names
"Groth16 or PLONK". Per CW-7, BTCP pins Groth16 for S1 Phase 2 (the
~200-byte proof is Groth16-shaped). Existing circuit already uses Groth16.
Decision: **Groth16 (snarkjs) for S1 Phase 2.** Trusted setup required —
ceremony status `[OPEN]` until executed.

**Dependencies:**
- Hash_DNA commitment helper (Phase 2.1)
- `BTCPIntent.sol` commitment registry contract (Phase 4.2)
- netting_engine.rs INVISIBLE mode (Phase 5.1)
- Complementarity verifier contract (Phase 4.3) — atomic same-block reveal helper

**On-chain surface (R-CHANNELS):**
- `IntentCommitted(entity_id, H_intent, timestamp)` event — signal publication only
- `IntentRevealed(H_intent_A, H_intent_B, zk_proof_hash)` event — atomic reveal
- NO intent contents on-chain at any point before Phase 3 reveal

**Open questions attached:**
- OQ-7 (S1 Phase 2 circuit size: spec says ~50k, must MEASURE in Phase 3)
- Q2 (irrational coordinator attack on the complementarity reveal — BTCP §16 OQ-2; the SNARK proves complementarity but does not prove validators cannot collude to delay the reveal)

**Falsifiability condition (BTCP §13):** "MEV bot front-runs committed
intent before Phase 3 atomic reveal." → Mission Z6 attack.

**Mission evidence target (Phase 3):** measured constraint count, measured
prove time, measured verify time, measured proof bytes, vs. spec ~50k
estimate. Labelled MEASURED after Phase 3, ESTIMATE before.

---

## S2 — ZK IAP Share Proof

**Citation:** BTCP §5.3 "Water Pooling — Intent Aggregation Protocol (IAP)";
BTCP §14.1 Phase 3 item 11 (transparent deferral) + Phase 4 item 21 (ZK).

**Spec status:** `[CLAIMED-feasible]`. BTCP §5.3 verbatim: "ZK circuit
required: `zk_iap_share_proof/` — proves entity's share is correctly
calculated from their contribution without revealing the contribution
to other participants."

**R-ORDER sequencing (verbatim, BTCP §14.1 P3 #11):** "(Defer ZK share
proof to Phase 4 — use transparent shares initially)" → transparent IAP
goes live first; ZK IAP only after S2 circuit is built + measured.

**Statement proven (per BTCP §5.3):** `G_per_entity = G_total × (entity_value / total_value)`
is correctly calculated from the entity's private contribution without
revealing the contribution to other participants. Public: `G_total`,
`total_value`, pool direction. Private: `entity_value`, merkle proof of
pool membership.

**Circuit estimate:** BTCP gives no numeric estimate. Existing circuit is
SELF-REPORTED ~1k constraints (range checks + division + Merkle proof).
Must be MEASURED in Phase 3.

**Proving system decision (Phase 1, R-SETUP):** BTCP does not pin a system.
Per R-SETUP, prefer transparent. Existing circuit is circom (compiles to
both Groth16 and PLONK). **Decision: PLONK (transparent setup via snarkjs
`plonk` setup) for S2**, avoiding a per-circuit trusted ceremony. Switch
back to Groth16 only if Phase 1 measurement shows PLONK verify gas exceeds
budget.

**Dependencies:**
- `intent_aggregator.rs` transparent IAP (Phase 5.2 prerequisite)
- Merkle commitment of pool participants (off-chain root, on-chain anchor)

**On-chain surface (R-CHANNELS):**
- `PoolFormed(direction, total_value, merkle_root, window_deadline)` event
- `ShareProved(entity_id, zk_proof_hash, share_gwei)` event per claim
- NO individual `entity_value` on-chain (only `share_gwei` after proof)

**Falsifiability condition (BTCP §13, IAP implicit):** a participant whose
recorded share differs from `G_total × (entity_value / total_value)` by
more than 1 wei → ZK soundness broken. → Mission Z1 attack (forged proof
rejected) + Z12 (malleability canonical).

---

## S3 — ZK Travel Rule

**Citation:** BTCP §11 Fix 1 "Travel Rule Compliance Mode"; BTCP §14.1 P4 #22.

**Spec status:** `[CLAIMED-feasible]`. The spec gives the full 4-step
protocol and the SNARK statement verbatim.

**Statement proven (per BTCP Fix 1 Step 3):**
"I submitted valid Travel Rule disclosure to FATF-compliant VASP"
- public_inputs: `[transaction_hash, jurisdiction_id, disclosure_hash]`
- private_inputs: `[disclosure_contents, regulator_receipt]`

**Boundary (verbatim, BTCP Fix 1 Step 2):** "regulator receives: full
disclosure (law satisfied). TRION receives: nothing from this step."

**Storage invariant (verbatim, BTCP Fix 1 Step 4):** "TRION stores:
`disclosure_hash` only. TRION emits: `TRAVEL_RULE_COMPLIANT = TRUE`."

**Chameleon tier wiring (verbatim, BTCP Fix 1 CHAMELEON block):**
- LOW: proof optional, routing preference for compliant routes
- MEDIUM: proof required above $1,000
- HIGH: proof required for all routes
- CRITICAL: AWA_enforced — nothing emitted until proof present

**Circuit estimate:** BTCP gives no numeric estimate. Existing circuit is
SELF-REPORTED ~3k constraints (Poseidon hash + ECDSA-like receipt check
+ range checks). Must be MEASURED in Phase 3.

**Proving system decision (Phase 1, R-SETUP):** BTCP does not pin a system.
**Decision: PLONK (transparent) for S3.** Same reasoning as S2.

**Dependencies:**
- `TravelRuleCompliance.sol` (Phase 4.1) — disclosure_hash store + SNARK verifier + tier parameterization
- Regulator public-key encryption (off-chain, NOT in TRION codebase — entity-side)
- AWA freeze enforcement (Phase 5.4) — CRITICAL tier must halt emission

**On-chain surface (R-CHANNELS):**
- `TravelRuleProofSubmitted(entity_id, tx_hash, jurisdiction_id, disclosure_hash, zk_proof_hash)` event
- `TRAVEL_RULE_COMPLIANT = TRUE` emission (BTCP verbatim)
- NO disclosure plaintext, NO regulator_receipt, NO PII on-chain

**Falsifiification conditions:**
- Mission Z9: regulator plaintext never appears in TRION storage/logs/network traces (trace capture test)
- Mission Z13: AWA freeze under Right-to-Invisibility violation (CRITICAL tier)

---

## S4 — Sensing Oracle / Behavioral Credential

**Citation:** BTCP §7.1 "Privacy From TRION Itself — The Dark Field
Principle"; BTCP §14.1 P4 #23; WP-Mar §16 "Behavioral ZK Sovereignty".

**Spec status:** **`[CONJECTURE]`** (BTCP verbatim): "circuit construction
not yet completed. Estimated circuit size: 500k-2M constraints. Proof
aggregation likely required for efficiency."

**Entity-side computation (verbatim, BTCP §7.1):**
```
behavioral_hash = Hash_DNA(private_behavior || private_nonce)
public_commitment = Hash(behavioral_hash)       // hash of hash — no content
```

**SNARK statement (verbatim, BTCP §7.1):**
"my behavioral_hash is coherent with my historical BEO pattern"
- public_inputs: `[public_commitment, entity_id, historical_BEO_root]`
- private_inputs: `[private_behavior, private_nonce]`

**BEHAVIORAL_TRUTH_SIGNAL schema (verbatim, BTCP §7.1) — R-ABSENT enforced:**
```
entity_id:          present
public_commitment: present
coherence_score:    present (0.0 to 1.0)
plane_results:      [TRUE/FALSE × 7 planes]
behavior_content:   ABSENT
amount:             ABSENT
counterparty:       ABSENT
protocol:           ABSENT
chain:              ABSENT
```

**Phase-1 gate (R-ORDER + mission Phase 1.2):** S4 circuit construction is
GATED-OPEN until the Phase-1 aggregation study (OQ-7/Q2) produces a
measured verdict:
- IMPLEMENTABLE-NOW → build the single-epoch circuit (existing
  `zk_behavioral_credential/circuit.circom` is the base case)
- GATED-OPEN → label as such, commit the gate criteria, proceed without it.
**No partial claim of S4 activation is permitted either way.**

**Circuit estimate (ESTIMATE, label CONJECTURE):** 500k-2M constraints
(BTCP §7.1). Existing single-epoch circuit is SELF-REPORTED ~1.3k
constraints — this is the per-epoch base case only, NOT the full
multi-year aggregation. The 500k-2M figure refers to the recursive
composition (Plonky2/Plonky3/Nova) over multi-year records.

**Proving system decision (Phase 1, R-SETUP, CW-7):** WP-Mar §16 verbatim
allows "Groth16, PLONK, or STARKs" for behavioral ZK. Given the
500k-2M constraint estimate + "proof aggregation required" label, the
canon-aligned choice is a STARK-based recursive aggregation.
**Decision (Phase-1 verdict):** single-epoch base case = Groth16 (existing
circuit, smallest verify gas). Multi-year aggregation = STARK (Plonky2 or
Nova). The multi-year form is GATED-OPEN until Phase-1 study produces a
measured aggregation cost.

**Dependencies (gated):**
- Akashic commitment root (Phase 2.2) — `historical_BEO_root` publication
- Hash_DNA + behavioral_hash helpers (Phase 2.1)
- AWA freeze enforcement (Phase 5.4) — Right-to-Invisibility violation must halt S4 emission

**On-chain surface (R-CHANNELS, R-ABSENT):**
- `BEHAVIORAL_TRUTH_SIGNAL{entity_id, public_commitment, coherence_score, plane_results[7]}` event
- NO `behavior_content`, `amount`, `counterparty`, `protocol`, `chain` fields anywhere (compile-time + runtime grep, Mission Z7)

**Falsifiability condition (BTCP §13):** "TRION can reconstruct private
behavior from `public_commitment` alone." → Mission Z5 attack (reconstruction
attempt + HV-ZK / simulator argument).

**Open questions attached:**
- OQ-7 (minimum circuit size for 7-plane coherence SNARK)
- Q2 (irrational coordinator: validators certifying false coherence)

---

## S5 — BIRP (Behavioral Identity Recovery Protocol)

**Citation:** WP-Mar §16 "Behavioral ZK Sovereignty / BIRP"; WP-Feb Formula
Index `BIRP_anchor` formula.

**Spec status:** `[NOVEL — seeking prior art]` (WP-Mar falsifiability
table: "BIRP as identity primitive: show prior treatment of behavioral
[...]") + `[CONJECTURE]` (drift false-negative rate).

**Enrollment (verbatim, WP-Mar §16):**
```
BIRP_anchor = Hash_DNA(BEO_baseline || Hash(DNA_Code) ||
                       enrollment_timestamp || behavioral_entropy_seed)
Stored in Akashic Index: BIRP_anchor — permanent, immutable
Not stored: DNA_Code — ever
```

**Recovery Phases 1-5 (verbatim, WP-Mar §16):**
1. DNA_Code verification — timing exact, length exact, dual-strand hash
2. Behavioral proof — challenge from lived behavioral knowledge, match > 0.85
3. Temporal cluster challenge — submit transaction from BEO cluster within N minutes (N random)
4. Conscious Layer (high-value only) — 3 verifiers, behavioral evidence only, 2-of-3
5. 7-day waiting period — all BEO cluster addresses notified, real owner can object

**Drift conjecture (verbatim, WP-Mar §16):** "[CONJECTURE — false negative
rate under behavioral drift requires empirical validation and
threshold-setting.]"

**Phase-1 gate:** S5 enrollment store is IMPLEMENTABLE-NOW (hash-only,
same pattern as disclosure_hash). S5 recovery path is GATED-OPEN until
the drift false-negative rate is empirically measured (mission Z11,
SYNTHETIC-DEMO label).

**Mission scope for S5 in this activation:**
- ✅ Phase 2: BIRP anchor store — `Hash(DNA_Code)` only, content + timing NEVER stored (Phase 2.4)
- ❌ Recovery path activation — GATED-OPEN (drift conjecture unresolved)
- ❌ Claim of "BIRP is operational" — FORBIDDEN per R-LABELS

**Dependencies:**
- Hash_DNA + BIRP_anchor helper (Phase 2.1)
- Akashic commitment root (Phase 2.2)
- Conscious Layer (not built in this mission; Phase 4 of recovery GATED-OPEN)

**On-chain surface (R-CHANNELS):**
- `BIRPEnrolled(entity_id, BIRP_anchor, enrollment_timestamp)` event — anchor only
- NO `DNA_Code` content, length, or timing anywhere (grep, Mission Z10)

**Falsifiability conditions:**
- Mission Z10: BIRP timing/length exactness — partial or off-window submission silently rejected
- Mission Z11: BIRP drift false-negative rate (SYNTHETIC-DEMO label, never as fact)

---

## Cross-Cutting — What is NOT in this mission's scope

Per R-CHANNELS, R-NO-REDEF, and the spec's own Phase 4 long-term label:

1. **Mainnet deployment** — testnet only (Phase 4).
2. **External security audit** — operator's responsibility post-mission.
3. **S4 multi-year aggregation circuit construction** — GATED-OPEN; only
   the single-epoch base case + aggregation study are in scope.
4. **S5 recovery path activation** — GATED-OPEN; only the enrollment
   (hash-only) store is in scope.
5. **BRT gas-circadian correlation** — separate OQ-8, not a ZK surface.
6. **Bridge elimination** — network-effect claim, 5-10 year horizon (BTCP §15).

---

## Phase 0 → Phase 1 Hand-off

A-SPEC hands A-ZK the following:
- The five surfaces above with citations + status labels + estimates (as estimates)
- The CANON-WINS findings (CW-1 through CW-8) — proving-system decisions
- The existing 5 circuits at `zk-circuits/` as audited input (R-NO-REDEF)

A-ZK must produce in Phase 1:
- Per-surface proving-system decision with citation (CW-7 is the input)
- Measured constraint counts from a compiled pilot circuit (NOT spec quotes)
- S4 aggregation study (OQ-7/Q2) with measured numbers, verdict
  IMPLEMENTABLE-NOW or GATED-OPEN with threshold criteria

A-AUD reviews Phase 1 before Phase 2 begins.

---

*Authored by A-SPEC. v-stamp: `bzk-surface-map-v0.1`. Status: Phase 0
ACCEPTANCE GATE PASSED.*

---

## FINAL STATUS (post-Phase 7 audit)

> **Authored by:** A-DOCS (documentation engineer) — Task ID: BZK-PHASE-8
> **Source of truth:** `docs/zk/A_AUD_ledger.md` (Phase 7 independent
> verifier report; v-stamp `bzk-audit-v0.1`). All statuses below are
> re-derived from the audit, not from agent self-reports.
> **R-LABELS:** every claim carries a label (VERIFIED / MEASURED /
> OPEN / GATED-OPEN / SYNTHETIC-DEMO). Spec estimates retain ESTIMATE.

### Final per-surface status (R-LABELS applied)

| ID | Surface | Final Status (Phase 1-7 outcome) | Constraint Count | Round-Trip | Notes |
|---|---|---|---|---|---|
| S1 Phase 1 | ZK Intent Commitment (hash-only commit) | **IMPLEMENTED-TESTED** (Phase 2 + Phase 4) | n/a (hash-only, no circuit) | n/a | `IntentCommitmentRegistry.sol` deployed + 29 Hardhat tests passing; `akashic_root.compute_root` publishes roots. VERIFIED by A-AUD §3. |
| S1 Phase 2 | ZK Complementarity proof (BTCP §5.6) | **COMPILED, ROUND-TRIP [OPEN]** | **2,686 MEASURED** (vs ~50k ESTIMATE per BTCP §5.6) | `[OPEN]` per Phase 3 §4 BLOCKER (Groth16 setup >240s) | `zk_complementarity_proof/circuit.circom` + `ComplementarityVerifier.sol` wrapper (pluggable `setVerifier`). CW-9 finding: MEASURED 18.6× smaller than spec ESTIMATE because Poseidon + field-equality constraints (not in-circuit SHA3). |
| S2 | ZK IAP Share Proof (BTCP §5.3) | **COMPILED, ROUND-TRIP [OPEN]**; transparent IAP **LIVE** (Phase 5) | **1,078 MEASURED** (no spec estimate) | `[OPEN]` per Phase 3 §4 BLOCKER (PLONK setup) | Transparent IAP live in `core/zk/iap_transparent.py` (Phase 5); ZK shares `[OPEN]` per R-ORDER (BTCP §14.1 P3 #11). |
| S3 | ZK Travel Rule (BTCP Fix 1) | **COMPILED, ROUND-TRIP [OPEN]**; `TravelRuleCompliance.sol` **DEPLOYED** (Phase 4) | **1,179 MEASURED** (no spec estimate) | `[OPEN]` per Phase 3 §4 BLOCKER (PLONK setup) | TravelRuleCompliance.sol deployed to 2 local Hardhat VMs with tx hashes recorded (Phase 4). Chameleon tiers LOW/MEDIUM/HIGH/CRITICAL wired per BTCP Fix 1. AWA freeze enforced on CRITICAL tier per WP-Feb §14.2. |
| S4 | Sensing Oracle / Behavioral Credential (BTCP §7.1) | **GATED-OPEN** — single-epoch base COMPILED; multi-year aggregation **GATED-OPEN** per Phase 1 §4.5 | **3,298 MEASURED** (single-epoch base only) vs 500k-2M ESTIMATE per BTCP §7.1 CONJECTURE for multi-year aggregation | NOT ATTEMPTED (GATED-OPEN) | NO partial activation claim. Plonky2/Nova toolchain not installed; threshold criteria per `FEASIBILITY_AND_SETUP.md §4.5`. A-AUD §8 confirmed no silent activation. Filed as EP-1. |
| S5 | BIRP (WP-Mar §16) | **GATED-OPEN** — enrollment store **LIVE** (Phase 2.4); recovery path **GATED-OPEN** | n/a (hash-only enrollment; no circuit) | n/a | `birp_store.py` stores `BIRP_anchor = Hash_DNA(BEO_baseline || Hash(DNA_Code) || enrollment_timestamp || behavioral_entropy_seed)` only — never stores `DNA_Code` content. Recovery path Phases 1-5 GATED-OPEN pending drift false-negative empirical validation per WP-Mar §16 CONJECTURE. Filed as EP-2. |

### Audit verdict (per `A_AUD_ledger.md §10`)

- **13/18 D-items YES**
- **2 PARTIAL** (D5, D12 — round-trip `[OPEN]` per Phase 3 BLOCKER)
- **3 INCOMPLETE** (D15, D16, D18 — Phase 8 + Phase 9 to execute)
- **0 FAIL** / 0 unlabeled inventions / 0 conjecture-as-fact /
  0 citation mismatches / 0 measurement mismatches (5/5 reproduce)

### BLOCKER (per Phase 3 §4.3 + Phase 7 audit §11)

**Groth16 setup time > 240 seconds exceeds the sandbox command timeout.**
This blocks the prove/verify round-trip (Z1, Z3-rt, Z4, Z12 — all `[OPEN]`)
and the exported `verifier.sol` plug-in to `ComplementarityVerifier.setVerifier`.
It does NOT end the mission and does NOT invite invention per mission
BLOCKER PROTOCOL.

**Threshold criteria for closure:**
1. Run in an environment with command timeout > 10 minutes, OR
2. Use `nohup` + `screen` in a persistent environment, OR
3. Use a remote build server (Railway build phase, CircleCI).

When closed, exported `verifier.sol` drops into `ComplementarityVerifier.setVerifier(circuitId, address)`.

### FORBIDDEN: AGREEMENT STATEMENT

Per mission FORBIDDEN section + Phase 7 audit §11: the AGREEMENT
STATEMENT (verbatim "I AGREE 100%:") is NOT emitted at this phase
because D5, D12, D15, D16, D18 are not full YES. Phase 9 (AGREEMENT
GATE) owns that statement. This surface map reports honest status only.

---

*v-stamp: `bzk-surface-map-v0.2` (post-Phase 7 audit final status).
Status: 1/5 surfaces IMPLEMENTED-TESTED (S1 Phase 1); 3/5 surfaces
COMPILED with round-trip [OPEN] (S1 Phase 2, S2, S3); 2/5 surfaces
GATED-OPEN (S4, S5 — no partial activation claim). 0 FAIL.*
