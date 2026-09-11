# BZK — Behavioral Zero-Knowledge Reference (TRION Protocol)

> **v-stamp:** `bzk-reference-v0.1`
> **Authored by:** A-DOCS (documentation engineer) — Task ID: BZK-PHASE-8
> **Canon sources (verbatim, with SHA-256 — per `CANON_EXTRACT.md §0.1`):**
> - BTCP `BTCP_MASTER_IMPLEMENTATION_SPEC.md.pdf` (Apr 2026) — `758528cf8910eb02c205b6a4850a70c9350472bb2507e5367d71ac57bd4fb420`
> - WP-Feb `TRION_PROTOCOL_White_paper.pdf` (Feb 2026) — `80ebc82f0f9ba8e5bf58d110b870796ae48145c410be411a9a0378566398d183`
> - WP-Mar `TRION_Protocol_Whitepaper.md.pdf` (Mar 2026 update) — `40321eaa277c1a62804691819a181cdb7d8242062cdb3cd0d69538fe5541e094`
>
> **Scope:** this is the spec-anchored reference for the BZK (Behavioral
> Zero-Knowledge) activation delivered across Phases 0–7 of the TRION BZK
> Activation Mission. Every claim carries an R-LABELS tag
> (VERIFIED / MEASURED / OPEN / ESTIMATE / GATED-OPEN / SYNTHETIC-DEMO).
> Per mission FORBIDDEN: TRION is NOT reducible to "a zk protocol".
> BZK is one projection of the Witness World's privacy law — see
> `COMMUNITY_ADDENDUM_DRAFT.md` for the FULL TRION framing.
>
> **Source of truth for what's earned vs OPEN:** `docs/zk/A_AUD_ledger.md`
> (Phase 7 independent verifier report; v-stamp `bzk-audit-v0.1`).

---

## 1. R-COMPLIANCE Statement (verbatim, WP-Mar §17)

> **Critical clarification:** TRION does not help users evade laws. ZK
> proofs prove **compliance** — they do not hide non-compliance. An
> illegal transaction with a ZK behavioral privacy proof is still
> illegal and the behavioral record still exists in the Akashic Index.
> What ZK changes is who can observe the record — not whether it exists.

— *WP-Mar §17 (Critical clarification)* — verbatim per `CANON_EXTRACT.md §6.3`.

**Mission interpretation (R-LABELS: VERIFIED by A-AUD §7 citation match):**
BZK is not privacy-for-privacy's-sake. BZK is **compliance-proof +
invisibility-right**. The Akashic Index retains the behavioral record;
ZK only controls who can observe it. An entity that is non-compliant
cannot obtain a valid BZK proof — the circuit constraints (hardcoded
equality + range checks; MEASURED in Phase 3) refuse to produce a
witness for non-compliant inputs.

---

## 2. Per-Surface Reference (S1-S5)

Each surface carries: (a) canon citation, (b) final status post-Phase 7
audit, (c) MEASURED vs ESTIMATE labels per R-LABELS. All MEASURED values
reproduced 5/5 in the A-AUD fresh-process audit (`A_AUD_ledger.md §6`).

### S1 — ZK Intent Commitment (BTCP §5.6 "Water Underground")

**Citation (verbatim):**
- Phase 1 Commit: `H_intent = Hash_DNA(intent_details || random_nonce || entity_id)` (BTCP §5.6)
- Phase 2 Match: `public_inputs [H_intent_A, H_intent_B, entity_id_A, entity_id_B]`, `private_inputs [intent_A_full, intent_B_full, nonce_A, nonce_B]` (BTCP §5.6)
- Phase 3 Atomic Reveal: both intents published in same block (BTCP §5.6)
- Phase 4 Execution: MEV front-running window = 0 (BTCP §5.6)
- Build guide: BTCP §14.1 P4 item 19 (intent commitment), item 20 (complementarity)

**Final status:**
- **Phase 1 (commit, hash-only): IMPLEMENTED-TESTED** — `IntentCommitmentRegistry.sol` deployed + 29 Hardhat tests passing (Phase 4); `hash_dna.py` + `akashic_root.compute_root` publish roots (Phase 2). VERIFIED by A-AUD §3 + §4.
- **Phase 2 (complementarity circuit): COMPILED, ROUND-TRIP [OPEN]** — `zk_complementarity_proof/circuit.circom` compiles to **2,686 MEASURED constraints** (14 private inputs, 5 public inputs). `ComplementarityVerifier.sol` wrapper deployed (pluggable `setVerifier(circuitId, address)`). Round-trip `[OPEN]` per Phase 3 §4 BLOCKER.

**Measurement (R-LABELS):**
- MEASURED 2,686 constraints (Phase 3, reproduced in A-AUD §6)
- ESTIMATE ~50,000 constraints (BTCP §5.6 verbatim)
- **CW-9 finding:** MEASURED is 18.6× smaller than ESTIMATE. Cause: Poseidon hash (~250 constraints) instead of in-circuit dual-strand SHA3 (~10k+); complementarity equality is field-element constraints (1 each), not hash equality. NOT a redefinition — both labels honest per R-LABELS.

---

### S2 — ZK IAP Share Proof (BTCP §5.3 "Water Pooling")

**Citation (verbatim):**
- "ZK circuit required: `zk_iap_share_proof/` — proves entity's share is correctly calculated from their contribution without revealing the contribution to other participants." (BTCP §5.3)
- Gas sharing formula (public; ZK proves per-entity calculation): `G_per_entity = G_total × (entity_value / total_value)` (BTCP §5.3)
- R-ORDER sequencing: "(Defer ZK share proof to Phase 4 — use transparent shares initially)" (BTCP §14.1 P3 item 11)
- Build guide: BTCP §14.1 P4 item 21

**Final status:**
- **COMPILED, ROUND-TRIP [OPEN]; transparent IAP LIVE (Phase 5)**
- `zk_iap_share_proof/circuit.circom` compiles to **1,078 MEASURED constraints** (8 private, 3 public).
- Transparent IAP live in `core/zk/iap_transparent.py` (Phase 5).
- ZK shares `[OPEN]` per R-ORDER (BTCP §14.1 P3 #11 — transparent first, ZK after).
- Proving system: PLONK (transparent) per Phase 1 R-SETUP (BTCP does not pin a system; R-SETUP prefers transparent).

**Measurement (R-LABELS):**
- MEASURED 1,078 constraints (Phase 3, reproduced A-AUD §6)
- ESTIMATE: BTCP provides no numeric estimate
- Proof size: ~400-500 bytes ESTIMATE (PLONK spec); not yet MEASURED (round-trip `[OPEN]`)

---

### S3 — ZK Travel Rule (BTCP §11 Fix 1)

**Citation (verbatim):**
- Step 1 (entity private): `disclosure = {originator_name, originator_address, originator_account, beneficiary, value, timestamp}`
- Step 2 (boundary — TRION receives NOTHING): "regulator receives: full disclosure (law satisfied). TRION receives: nothing from this step."
- Step 3 (SNARK): statement "I submitted valid Travel Rule disclosure to FATF-compliant VASP"; `public_inputs [transaction_hash, jurisdiction_id, disclosure_hash]`; `private_inputs [disclosure_contents, regulator_receipt]`
- Step 4 (storage invariant): "TRION stores: `disclosure_hash` only. TRION emits: `TRAVEL_RULE_COMPLIANT = TRUE`."
- Chameleon tiers: LOW (proof optional) / MEDIUM ($1,000+) / HIGH (all routes) / CRITICAL (AWA_enforced — nothing emitted until proof present)
- Build guide: BTCP §14.1 P4 item 22; contract name `TravelRuleCompliance.sol` (R-GENERIC — no chain prefix)

**Final status:**
- **COMPILED, ROUND-TRIP [OPEN]; `TravelRuleCompliance.sol` DEPLOYED (Phase 4)**
- `zk_travel_rule/circuit.circom` compiles to **1,179 MEASURED constraints** (7 private, 3 public).
- `TravelRuleCompliance.sol` deployed to 2 local Hardhat testnet VMs with tx hashes recorded:
  - VM 1 (localhost): `0xe32cb166aa8d18e8cf195abb5effef2d72843daed288ef2089f99df3182dc0f7`
  - VM 2 (hardhat): `0xda1d93ce8a6a9cc8350facbf50b296529da008f92abda4ed243463e46556b794`
- Chameleon tiers LOW/MEDIUM/HIGH/CRITICAL wired per BTCP Fix 1.
- AWA freeze enforced on CRITICAL tier (Hardhat test "CRITICAL tier: emission reverts when awaFrozen" — reverts with `AWAFrozen`).
- Proving system: PLONK (transparent) per Phase 1 R-SETUP.

**Measurement (R-LABELS):**
- MEASURED 1,179 constraints (Phase 3, reproduced A-AUD §6)
- ESTIMATE: BTCP provides no numeric estimate
- ABSENT-field enforcement: VERIFIED by A-AUD §4 — 0 matches across all artifacts for `disclosure_contents`, `regulator_receipt`, `private_behavior`, `behavior_content`, `amount:`, `counterparty:`, `protocol:`
- Mainnet deployment: `[OPEN]` (testnet only per mission scope; R-LABELS)

---

### S4 — Sensing Oracle / Behavioral Credential (BTCP §7.1 + WP-Mar §16)

**Citation (verbatim):**
- Entity-side: `behavioral_hash = Hash_DNA(private_behavior || private_nonce)`; `public_commitment = Hash(behavioral_hash)` (BTCP §7.1)
- SNARK statement: "my behavioral_hash is coherent with my historical BEO pattern"; `public_inputs [public_commitment, entity_id, historical_BEO_root]`; `private_inputs [private_behavior, private_nonce]`
- TRION receives: `public_commitment + entity_id + historical_BEO_root + zk_proof`; TRION stores: `public_commitment` ONLY; TRION emits: `COHERENCE_SIGNAL (TRUE/FALSE) + coherence_score`
- ABSENT schema: see §4 below (BTCP §7.1 BEHAVIORAL_TRUTH_SIGNAL block)
- CONJECTURE label (verbatim BTCP §7.1): "[CONJECTURE — circuit construction not yet completed. Estimated circuit size: 500k-2M constraints. Proof aggregation likely required for efficiency.]"
- Build guide: BTCP §14.1 P4 item 23 (LONG TERM — requires proof aggregation)
- Conceptual framing: WP-Mar §16 "Behavioral ZK Sovereignty"

**Final status: GATED-OPEN (no partial activation claim)**
- Single-epoch base case: `zk_behavioral_credential/circuit.circom` compiles to **3,298 MEASURED constraints** (10 private, 3 public). This is the per-epoch base ONLY, not the multi-year aggregation.
- Multi-year aggregation: **GATED-OPEN** per Phase 1 §4.5 — Plonky2/Nova toolchain not installed; threshold criteria documented.
- A-AUD §8 VERIFIED: no silent activation of S4 in any later phase. S4 NOT wired into any Phase 5 integration module.

**Measurement (R-LABELS):**
- MEASURED 3,298 constraints (single-epoch base; Phase 3, reproduced A-AUD §6)
- ESTIMATE 500k-2M constraints (BTCP §7.1 CONJECTURE — refers to multi-year recursive composition)
- Filed as **EP-1** in `EXTENSION_PROPOSALS.md` (segregated, NOT merged into core)

---

### S5 — BIRP (Behavioral Identity Recovery Protocol, WP-Mar §16 + WP-Feb Formula Index)

**Citation (verbatim):**
- The BIRP Claim (WP-Mar §16): "Behavioral history is a stronger identity root than secret possession. Three years of consistent on-chain behavior cannot be stolen, lost, or forgotten — it is permanently recorded in an append-only immutable ledger."
- Enrollment (WP-Mar §16): `BIRP_anchor = Hash_DNA(BEO_baseline || Hash(DNA_Code) || enrollment_timestamp || behavioral_entropy_seed)`; "Stored in Akashic Index: `BIRP_anchor` — permanent, immutable. Not stored: `DNA_Code` — ever."
- Recovery Phases 1-5 (WP-Mar §16): Phase 1 DNA_Code verification (timing exact, length exact, dual-strand hash) → Phase 2 behavioral proof (match > 0.85) → Phase 3 temporal cluster → Phase 4 Conscious Layer (2-of-3) → Phase 5 7-day waiting period.
- Drift CONJECTURE (WP-Mar §16 verbatim): "[CONJECTURE — false negative rate under behavioral drift requires empirical validation and threshold-setting.]"
- BIRP as identity primitive: NOVEL (WP-Mar falsifiability table — seeking prior art)
- Formula: `BIRP_anchor` formula verbatim from WP-Feb Formula Index

**Final status: GATED-OPEN (enrollment store LIVE; recovery path GATED-OPEN)**
- Enrollment store LIVE in `zk-circuits/commitments/birp_store.py` (Phase 2.4) — stores `BIRP_anchor` only; NEVER stores `DNA_Code` content, length, or timing.
- Recovery path Phases 1-5: **GATED-OPEN** pending:
  1. Empirical drift false-negative rate (mission Z11 — SYNTHETIC-DEMO only, NEVER as fact per WP-Mar §16 CONJECTURE)
  2. Conscious Layer 2-of-3 implementation (out of scope; operator's responsibility post-mission)
  3. 7-day waiting period + BEO cluster notification wiring (operational)

**Measurement (R-LABELS):**
- No circuit (enrollment is hash-only per WP-Mar §16 verbatim)
- Z10 Part A (enrollment round-trip on real Phase 2.4 code): VERIFIED
- Z11 (drift false-negative rate): SYNTHETIC-DEMO — 0 false negatives across 1,000 synthetic profiles; CONJECTURE status preserved (NEVER as fact)
- Filed as **EP-2** in `EXTENSION_PROPOSALS.md` (segregated)

---

## 3. R-CHANNELS Restatement (WP-Mar §15 verbatim)

Per `CANON_EXTRACT.md §7.1` — verbatim:

> ```
> ═══════════════════════════════════════════════════
> SMART CONTRACTS — OUTPUT ONLY:
>   Signal publication (Solidity)
>   Economic coordination (Vyper)
> ═══════════════════════════════════════════════════
> ```

— *WP-Mar §15 (20-channel communication map closing block)*

**Mission surface audit (A-AUD §4 + Phase 4 worklog):** VERIFIED.
The 3 deployed contracts (`TravelRuleCompliance.sol`, `IntentCommitmentRegistry.sol`, `ComplementarityVerifier.sol`) emit signal publication events ONLY. No on-chain proof generation, no economic coordination, no routing calculation. Proof generation stays offchain. The on-chain verifier contracts receive opaque `bytes proof` + `uint256[] publicInputs` and forward to circuit-specific snarkjs-generated leaf verifiers that perform read-only pairing checks.

---

## 4. R-ABSENT Enforcement Summary (BTCP §7.1 verbatim)

Per `CANON_EXTRACT.md §4.4` — verbatim BEHAVIORAL_TRUTH_SIGNAL schema:

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

**5 ABSENT fields (verbatim):** `behavior_content`, `amount`, `counterparty`, `protocol`, `chain`. Plus the cross-surface ABSENT fields: `disclosure_contents` (BTCP Fix 1 Step 4), `regulator_receipt` (BTCP Fix 1 Step 3), `DNA_Code content` (WP-Mar §16).

**Mission enforcement (VERIFIED by A-AUD §4 — fresh-process grep across `zk-circuits/commitments/`, `contracts/zk/`, `core/zk/`):**

```bash
grep -rn -E "disclosure_contents|regulator_receipt|private_behavior|DNA_Code.*content|behavior_content|amount:|counterparty:|protocol:" \
    zk-circuits/commitments/ contracts/zk/ core/zk/ 2>/dev/null \
    | grep -vE "//|#|\"\"\"|test_|leakage_grep|README|\.md:"
```

**Result: 0 matches.** R-ABSENT enforcement holds at compile + runtime + storage layers.

Runtime self-checks (Phase 2 commit `565e314`):
- `disclosure_store.assert_no_plaintext()` — passes
- `birp_store.assert_no_dna_code_content()` — passes

Mission attack Z7 (R-ABSENT grep): **PASS, VERIFIED** (cross-artifact grep across `zk-circuits/` + `contracts/zk/` + `core/zk/`).

---

## 5. AWA / Right-to-Invisibility (WP-Feb §14.2 + WP-Mar §17)

Per `CANON_EXTRACT.md §6.1` — verbatim AWA_enforced condition:

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

— *WP-Feb §14.2 (and restated WP-Mar §17 AWA block)* — both WPs agree per CW-4.

Per `CANON_EXTRACT.md §6.2` — verbatim Right-to-Invisibility enforcement:

> ```
> AWA_enforced = FALSE if Right_to_Invisibility_enforced = FALSE
> → signal emission FROZEN
>
> This is not a policy. It is an architectural enforcement condition.
> The system cannot function while violating individual privacy.
> ```

— *WP-Mar §16 (The Right to Invisibility)*

**Mission enforcement (VERIFIED by A-AUD §5 — fresh-process grep):**

```bash
grep -rniE "forceResume|overrideFreeze|forceThaw|bypassAwa|emergencyUnfreeze" \
    contracts/zk/ core/zk/ docs/zk/ 2>/dev/null
```

**Result: 0 matches.** No override path exists.

Architectural enforcement (Phase 4 commit `2f13f17` + Phase 5 commit `20a6b30`):
- `setAwaState` callers (grep): only the `awaOracle` address (modifier `onlyAwaOracle` on `TravelRuleCompliance.sol`). Deployer cannot call post-handover.
- Two-step handover (`nominateAwaOracle` + `acceptAwaOracleNomination`) prevents single-transaction takeover.
- `awaFrozen` defaults `true` at construction (R-FAILCLOSED).
- Hardhat tests verify (3 dedicated tests in `zk_contracts.test.ts`):
  - "AWA freeze: stranger cannot thaw" — reverts with `NotAwaOracle`
  - "AWA freeze: deployer cannot thaw post-handover" — reverts with `NotAwaOracle`
  - "CRITICAL tier: emission reverts when awaFrozen" — reverts with `AWAFrozen`
- Python integration `core/zk/awa_freeze.py` (Phase 5): subscribes to AWA state; on TRUE→FALSE transition, emits `AWA_FREEZE_TRIGGERED` + halts downstream signal emission; resume checks ALL 6 AWA conditions per WP-Feb §14.2 verbatim.

Mission attack Z13 (AWA freeze fresh re-verify): **PASS, VERIFIED**.

---

## 6. BLOCKER (per Phase 3 §4.3 + Phase 7 audit §11)

**The BLOCKER:** Groth16 setup time > 240 seconds exceeds the sandbox
command timeout. The sandbox process timeout is 120 s default; we
extended to 240 s and the Groth16 setup step (`snarkjs groth16 setup
circuit.r1cs pot14_final.ptau circuit_0000.zkey`) was killed before
completion. Background attempts via `nohup` were sandbox-killed before
completion.

**What is blocked (R-LABELS: [OPEN]):**
- Prove/verify round-trip on all 4 compiled circuits (S1 Phase 2, S2, S3, S4 single-epoch)
- Exported `verifier.sol` per circuit (via `snarkjs zkey export solidityverifier`)
- Mission attacks requiring round-trip: Z1 (forged/mutated proof), Z3 round-trip (complementarity soundness), Z4 (completeness 100/100), Z12 (malleability)
- D5 (S1-S3 round-trip green) — PARTIAL: circuits built + MEASURED; round-trip `[OPEN]`
- D12 (SILENCE preservation under ZK paths) — PARTIAL: PASS at constraint level + SILENCE gate at TRION-emission layer (R-CHANNELS) per BTCP §7.1 "TRION emits: COHERENCE_SIGNAL (TRUE/FALSE)"; round-trip `[OPEN]`

**What is NOT blocked:**
- R1CS compilation + constraint MEASUREMENT (all 5 circuits reproduced 5/5 in A-AUD §6)
- Contract deployment (Phase 4 complete; 3 contracts deployed to 2 VMs with tx hashes)
- Hardhat test suite (29 tests passing)
- ABSENT + AWA freeze enforcement (greps clean)
- Z2, Z7, Z13, Z14 (VERIFIED — constraint-level or above, no round-trip required)
- Z5, Z6, Z9, Z10 Part A, Z11 (SYNTHETIC-DEMO — no round-trip required)

**Threshold criteria for closure (per Phase 3 §4.3):**
1. Run in an environment with command timeout > 10 minutes, OR
2. Use `nohup` + `screen` in a persistent environment, OR
3. Use a remote build server (Railway build phase, CircleCI, GitHub Actions with `timeout-minutes: 30`).

**When the BLOCKER closes, the round-trip artifacts will be:**
- `zk-circuits/zk_*/build/circuit_final.zkey` (proving key)
- `zk-circuits/zk_*/build/verification_key.json` (verifying key)
- `zk-circuits/zk_*/build/proof.json` (sample proof)
- `zk-circuits/zk_*/build/public.json` (public inputs)
- `zk-circuits/zk_*/verifier.sol` (Solidity verifier exported via `snarkjs zkey export solidityverifier`)

The exported `verifier.sol` files plug into `ComplementarityVerifier.setVerifier(bytes32 circuitId, address verifierContract)` (Phase 4 wrapper, deployed at `0x5FbDB2315678afecb367f032d93F642f64180aa3` on both local Hardhat VMs).

**Per mission BLOCKER PROTOCOL:** the BLOCKER reorders the mission but does NOT end it and does NOT invite invention. Phase 5 integration proceeded with a `MockComplementarityGroth16Verifier` for tests; the real verifier is dropped in when the BLOCKER closes.

---

## 7. Audit Verdict (per `A_AUD_ledger.md §10`)

- **13/18 D-items YES**
- **2 PARTIAL** (D5, D12 — round-trip `[OPEN]` per Phase 3 BLOCKER)
- **3 INCOMPLETE** (D15, D16, D18 — Phase 8 + Phase 9 to execute)
- **0 FAIL** / 0 unlabeled inventions / 0 conjecture-as-fact /
  0 citation mismatches / 0 measurement mismatches (5/5 reproduce)

Per mission FORBIDDEN + Phase 7 audit §11: the AGREEMENT STATEMENT
(verbatim "I AGREE 100%:") is NOT emitted at this phase because D5,
D12, D15, D16, D18 are not full YES. Phase 9 (AGREEMENT GATE) owns
that statement.

---

## 8. What BZK is NOT (per mission FORBIDDEN)

- BZK is NOT "a zk protocol". BZK is the privacy law of the Witness
  World — one projection, never the definition. See
  `COMMUNITY_ADDENDUM_DRAFT.md` for the FULL TRION framing.
- BZK is NOT privacy-for-privacy's-sake. BZK is compliance-proof +
  invisibility-right per R-COMPLIANCE (§1 above).
- BZK is NOT complete. S4 multi-year aggregation is GATED-OPEN
  (EP-1); S5 recovery path is GATED-OPEN (EP-2); mainnet deployment
  is `[OPEN]` (EP-3); external security audit is operator's
  responsibility (EP-4); multi-source ingestion is `[OPEN]` (EP-5).
  See `EXTENSION_PROPOSALS.md` for the segregated proposals.

---

## 9. References (canonical paths)

- Canon extract: `docs/zk/CANON_EXTRACT.md` (Phase 0.2 — verbatim with citations)
- Surface map: `docs/zk/ZK_SURFACE_MAP.md` (Phase 0.3 + Phase 8.1 final status)
- Feasibility + setup: `docs/zk/FEASIBILITY_AND_SETUP.md` (Phase 1 — MEASURED + S4 gate)
- Phase 3 benchmarks: `docs/zk/PHASE3_BENCHMARKS.md` (MEASURED constraint counts + BLOCKER)
- Z-battery results: `docs/zk/Z_BATTERY_RESULTS.md` (Phase 6 — Z1-Z14)
- Phase 7 audit: `docs/zk/A_AUD_ledger.md` (independent verifier; v-stamp `bzk-audit-v0.1`)
- Evidence ledger: `docs/proofs/bzk_activation.json` (Phase 8.3 — machine-readable consolidation)
- Run-it-yourself: `docs/RUN_IT_YOURSELF.md` § "ZK Activation (BZK)" (Phase 8.4)
- Community addendum: `docs/zk/COMMUNITY_ADDENDUM_DRAFT.md` (Phase 8.5 — DRAFT)
- Extension proposals: `docs/zk/EXTENSION_PROPOSALS.md` (Phase 8 — D16)

---

*v-stamp: `bzk-reference-v0.1`. Authored by A-DOCS (Phase 8.2).
Status: BZK reference complete. 1/5 surfaces IMPLEMENTED-TESTED
(S1 Phase 1); 3/5 surfaces COMPILED with round-trip [OPEN] (S1 Phase 2,
S2, S3); 2/5 surfaces GATED-OPEN (S4, S5 — no partial activation
claim). 0 FAIL. Per Phase 7 audit §11, AGREEMENT STATEMENT NOT emitted
— D5, D12, D15, D16, D18 are not full YES.*

*TRION-AGG v-stamp: `trion-agg-bzk-v0.1` (BZK projection of the
TRION Aggregate; one projection, never the definition).*
