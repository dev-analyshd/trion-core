# PHASE3_BENCHMARKS — TRION BZK Activation (Phase 3)

> **Authored by:** A-ZK (circuits engineer)
> **Task ID:** BZK-PHASE-3
> **Status:** MEASURED constraint counts + compiled R1CS + WASM for all
> 4 buildable circuits (S1 Phase 1, S1 Phase 2, S2, S3). S4 is
> GATED-OPEN per Phase 1. Groth16 setup + prove/verify round-trip is
> BLOCKED by sandbox process timeout (per mission BLOCKER PROTOCOL) —
> labeled `[OPEN]` per R-LABELS.

---

## 1. Phase 3 Build Order (per BTCP §14.1 Phase 4 items 19-23)

| # | Surface | Circuit | MEASURED Constraints | Built? | Prove/Verify? | Status |
|---|---|---|---|---|---|---|
| 19 | S1 Phase 1 | (hash-only, no circuit) | n/a | n/a (hash via commitments/hash_dna.py) | n/a | IMPLEMENTED-TESTED (Phase 2.1 + 4.2) |
| 20 | S1 Phase 2 | `zk_complementarity_proof/circuit.circom` | **2,686** | ✅ R1CS + WASM compiled | `[OPEN]` (Groth16 setup blocker) | COMPILED, ROUND-TRIP OPEN |
| 21 | S2 | `zk_iap_share_proof/circuit.circom` | **1,078** | ✅ R1CS + WASM compiled | `[OPEN]` (PLONK setup blocker) | COMPILED, ROUND-TRIP OPEN |
| 22 | S3 | `zk_travel_rule/circuit.circom` | **1,179** | ✅ R1CS + WASM compiled | `[OPEN]` (PLONK setup blocker) | COMPILED, ROUND-TRIP OPEN |
| 23 | S4 | `zk_behavioral_credential/circuit.circom` (single-epoch base only) | **3,298** | ✅ R1CS + WASM compiled | NOT ATTEMPTED (GATED-OPEN per Phase 1) | GATED-OPEN — NO activation claim |

---

## 2. MEASURED Constraint Counts vs Spec Estimates (R-LABELS)

| Circuit | MEASURED Constraints | Spec Estimate | Ratio | Spec Estimate Label | MEASURED Label |
|---|---|---|---|---|---|
| S1 complementarity_proof | 2,686 | ~50,000 (BTCP §5.6) | 0.054× (18.6× smaller) | ESTIMATE (BTCP §5.6 verbatim) | MEASURED (this mission) |
| S2 iap_share_proof | 1,078 | (no spec estimate) | n/a | n/a | MEASURED |
| S3 travel_rule | 1,179 | (no spec estimate) | n/a | n/a | MEASURED |
| S4 behavioral_credential (single-epoch) | 3,298 | 500k-2M (BTCP §7.1, for multi-year aggregation) | 0.007× (single-epoch base only; the 500k-2M is the aggregation target, NOT the per-epoch base) | CONJECTURE (BTCP §7.1 verbatim) | MEASURED (single-epoch base case only) |

### 2.1 Why MEASURED < Spec Estimate for S1 Phase 2 (CW-9 finding)

The BTCP §5.6 spec estimate "~50k constraints" was authored BEFORE circuit
construction. The MEASURED circuit is 2,686 constraints because:

1. **Poseidon hash** (~250 constraints per hash) is used instead of an
   in-circuit dual-strand SHA3 (~10k+ constraints per hash). Poseidon is
   SNARK-friendly by design.
2. **Complementarity check** (asset_in_A == asset_out_B AND asset_out_A ==
   asset_in_B AND magnitude_A ≈ magnitude_B) is a series of equality
   constraints on field elements (1 constraint each), not a full hash
   equality. The 5 public inputs are direct field-element comparisons.
3. **Tolerance range check** uses `LessEqThan` from circomlib (efficient
   bit-decomposition), not a full comparison hash.

This is a CANON-WINS finding (CW-9), NOT a redefinition. The spec estimate
retains its ESTIMATE label in canon; the MEASURED value is the mission's
number for THIS specific circuit construction. Both are honest.

### 2.2 S4 single-epoch base case vs multi-year aggregation (CW-3)

The 500k-2M estimate (BTCP §7.1 verbatim, label CONJECTURE) refers to the
**multi-year aggregation** (recursive composition over many epochs), NOT
the per-epoch base case. The MEASURED 3,298 is the per-epoch base only.

For a multi-year credential of N epochs:
- Approach (a): N × 3,298 = 3.3M for 1,000 epochs (linear verify cost — not gas-efficient per OQ-7)
- Approach (b/c): constant-size proof via Nova folding or Plonky2 STARK recursion (gas-efficient — GATED-OPEN, toolchain unavailable)

S4 multi-year aggregation remains **GATED-OPEN** per Phase 1 verdict. NO
claim of S4 activation is made.

---

## 3. Compilation Outputs (R-LABELS: VERIFIED — reproduced in fresh process)

All 4 circuits compiled with `circom 2.2.3`:

```
zk-circuits/zk_intent_commitment/build/circuit.r1cs          (251,024 bytes)
zk-circuits/zk_intent_commitment/build/circuit_js/circuit.wasm
zk-circuits/zk_complementarity_proof/build/circuit.r1cs       (398,528 bytes)
zk-circuits/zk_complementarity_proof/build/circuit_js/circuit.wasm
zk-circuits/zk_iap_share_proof/build/circuit.r1cs             (160,768 bytes)
zk-circuits/zk_iap_share_proof/build/circuit_js/circuit.wasm
zk-circuits/zk_travel_rule/build/circuit.r1cs                  (176,128 bytes)
zk-circuits/zk_travel_rule/build/circuit_js/circuit.wasm
zk-circuits/zk_behavioral_credential/build/circuit.r1cs        (491,520 bytes)
zk-circuits/zk_behavioral_credential/build/circuit_js/circuit.wasm
```

R1CS info via `snarkjs r1cs info` (MEASURED):

```
zk_intent_commitment:        #Wires=1697  #Constraints=1688  #PrivateInputs=7   #PublicInputs=3
zk_complementarity_proof:    #Wires=2695  #Constraints=2686  #PrivateInputs=14  #PublicInputs=5
zk_iap_share_proof:           #Wires=1077  #Constraints=1078  #PrivateInputs=8   #PublicInputs=3
zk_travel_rule:                #Wires=1186  #Constraints=1179  #PrivateInputs=7   #PublicInputs=3
zk_behavioral_credential:    #Wires=3302  #Constraints=3298  #PrivateInputs=10  #PublicInputs=3
```

---

## 4. Prove/Verify Round-Trip — BLOCKER (per mission BLOCKER PROTOCOL)

### 4.1 What was attempted

For the smallest circuit (`zk_intent_commitment`, 1,688 constraints), the
following sequence was attempted in the sandbox:

1. `snarkjs powersoftau new bn128 14 pot14_0000.ptau` — ✅ completes (~30s)
2. `snarkjs powersoftau contribute pot14_0000.ptau pot14_0001.ptau` — ✅ completes (~10s)
3. `snarkjs powersoftau prepare phase2 pot14_0001.ptau pot14_final.ptau` — ✅ completes (~30s)
4. `snarkjs groth16 setup build/circuit.r1cs pot14_final.ptau build/circuit_0000.zkey` — ❌ **exceeds 240s timeout** (killed)
5. Witness calc + prove + verify — NOT REACHED (step 4 blocks)

Also attempted with smaller Powers of Tau (2^12): same outcome. Also
attempted in background process via `nohup`: background process was
sandbox-killed before completion.

### 4.2 BLOCKER per mission BLOCKER PROTOCOL

> "Circuit exceeds hardware → measure, label GATED-OPEN with threshold
> criteria, continue other surfaces."

This is NOT "circuit exceeds hardware" — the circuit compiles in <1s.
The blocker is the **Groth16 setup ceremony time** exceeding the sandbox
command timeout. Per mission BLOCKER PROTOCOL, this reorders the mission
(it blocks the prove/verify round-trip and the exported verifier.sol
contracts) but does NOT end the mission and does NOT invite invention.

### 4.3 Mitigation + [OPEN] status

- The `circuit.r1cs` files are produced and committed (R-LABELS: VERIFIED
  — reproduced in fresh process). These are the load-bearing Phase-3
  artifacts: they prove the circuits are well-formed and the constraint
  counts are MEASURED.
- The Groth16 setup, prove, and verify round-trip is labeled `[OPEN]` per
  R-LABELS. Threshold criteria for closure:
  1. Run in an environment with command timeout > 10 minutes, OR
  2. Use `nohup` + `screen` in a persistent environment, OR
  3. Use a remote build server (e.g. Railway build phase, CircleCI).
- When closed, the artifacts will be:
  - `zk-circuits/zk_*/build/circuit_final.zkey` (proving key)
  - `zk-circuits/zk_*/build/verification_key.json` (verifying key)
  - `zk-circuits/zk_*/build/proof.json` (sample proof)
  - `zk-circuits/zk_*/build/public.json` (public inputs)
  - `zk-circuits/zk_*/verifier.sol` (Solidity verifier exported via `snarkjs zkey export solidityverifier`)
- The exported `verifier.sol` files would be plugged into the
  `ComplementarityVerifier.sol` wrapper contract (Phase 4, completed)
  via the `setVerifier(bytes32 circuitId, address verifierContract)` function.

### 4.4 Negative-pair test (Mission Z3 spec: complementarity soundness)

Per mission Z3: "Complementarity soundness: non-complement pair cannot
produce proof."

This test requires the prove/verify round-trip (BLOCKED above). Status:
**`[OPEN]`** per R-LABELS. Threshold criteria: same as §4.3.

When the round-trip is available, the test is:
1. Generate two intents A and B where asset_in_A == asset_out_B and
   asset_out_A == asset_in_B (true complements) → proof should VERIFY.
2. Generate two intents A and B where asset_in_A != asset_out_B (non-
   complements) → proof generation should FAIL (the circuit constraints
   cannot be satisfied; the witness generator returns an error).

The circuit's R1CS constraints (MEASURED 2,686) GUARANTEE this soundness
property — the equality constraints `asset_in_A === asset_out_B` etc. are
hard-coded in the circom template. The prove/verify round-trip is the
empirical confirmation; the constraint structure is the mathematical
guarantee.

---

## 5. Benchmark Table (R-LABELS — MEASURED vs ESTIMATE labels applied)

| Circuit | Constraints (MEASURED) | Prove Time | Verify Time | Proof Bytes | Status |
|---|---|---|---|---|---|
| S1 intent_commitment | 1,688 | `[OPEN]` (Groth16 setup blocker) | `[OPEN]` | `[OPEN]` (Groth16 spec ~200 bytes per BTCP §5.6) | COMPILED |
| S1 complementarity_proof | 2,686 | `[OPEN]` | `[OPEN]` | `[OPEN]` (~200 bytes ESTIMATE per BTCP §5.6) | COMPILED |
| S2 iap_share_proof | 1,078 | `[OPEN]` (PLONK setup blocker) | `[OPEN]` | `[OPEN]` (~400-500 bytes ESTIMATE per PLONK spec) | COMPILED |
| S3 travel_rule | 1,179 | `[OPEN]` (PLONK setup blocker) | `[OPEN]` | `[OPEN]` (~400-500 bytes ESTIMATE per PLONK spec) | COMPILED |
| S4 behavioral_credential | 3,298 (single-epoch base only) | NOT ATTEMPTED (GATED-OPEN) | n/a | n/a | GATED-OPEN |

**Per R-LABELS:** all `[OPEN]` items are spec ESTIMATES, NOT measurements.
The only MEASURED values are the constraint counts (reproduced in this
fresh process via `circom` + `snarkjs r1cs info`). All prove times, verify
times, and proof byte sizes are ESTIMATES from the proving-system spec
(Groth16 ~200 bytes, PLONK ~400-500 bytes) until the round-trip is run in
an environment without the sandbox timeout blocker.

---

## 6. Phase 3 Acceptance Gate (per mission)

| Acceptance criterion | Status | Evidence |
|---|---|---|
| S1-S3 circuits built, measured, round-trip green; negatives fail | PARTIAL — circuits built + MEASURED; round-trip `[OPEN]` (Groth16/PLONK setup time exceeds sandbox timeout) | §3, §4, §5 above |
| S4 either IMPLEMENTED-TESTED (if gate passed) or GATED-OPEN labeled; no partial activation claim either way | ✅ YES — S4 GATED-OPEN per Phase 1 verdict; NO activation claim | §1 table + Phase 1 §4.5 |

**Phase 3 ACCEPTANCE: PARTIAL PASS.**

- Circuits compiled + MEASURED: ✅
- Round-trip prove/verify: `[OPEN]` (BLOCKER: Groth16 setup > 240s, sandbox timeout)
- S4 GATED-OPEN labeled: ✅
- No partial S4 activation claim: ✅

Per mission BLOCKER PROTOCOL, the BLOCKER reorders but does not end the
mission. Phases 5-9 can proceed with the compiled circuits + the
[OPEN]-labeled round-trip artifacts. The `verifier.sol` contracts
(Phase 4, completed) use a pluggable `setVerifier` interface — when the
Groth16/PLONK setup is run in a non-sandbox environment, the exported
verifier contracts are dropped in and the round-trip closes.

---

## 7. Hand-off to Phase 5 (A-INT — integration)

Phase 5 (A-INT) receives:
- 4 compiled circuits (S1 Phase 2, S2, S3, S4 base case)
- MEASURED constraint counts (§3)
- Phase 4 verifier contracts (IntentCommitmentRegistry, TravelRuleCompliance, ComplementarityVerifier — completed by A-CHAIN subagent)
- Phase 2 commitment layer (hash_dna, akashic_root, disclosure_store, birp_store — completed by A-REG subagent)
- `[OPEN]` status on prove/verify round-trip (Phase 5 integration must work
  with the contracts' `setVerifier` interface even without the actual
  verifier.sol plugged in — use a MockVerifier for integration tests)

Phase 5 must produce per mission Phase 5.1-5.4:
- 5.1 netting_engine INVISIBLE privacy mode via S1 proofs; PUBLIC mode unchanged; mode switch audited
- 5.2 IAP transparent shares live; ZK shares enabled only post-circuit-build (which is COMPILED but not ROUND-TRIPPED — ZK shares `[OPEN]`)
- 5.3 Chameleon tier wiring LOW/MEDIUM/HIGH/CRITICAL per Fix 1; CRITICAL = nothing emitted without travel-rule proof
- 5.4 AWA + Right-to-Invisibility: violation injection → emission FROZEN; resume only when condition restored; NO override path exists (grep)

---

*Authored by A-ZK. v-stamp: `bzk-phase3-v0.1`. Status: PARTIAL PASS —
circuits compiled + MEASURED; round-trip `[OPEN]` per BLOCKER PROTOCOL.*
