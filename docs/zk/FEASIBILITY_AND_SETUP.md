# FEASIBILITY_AND_SETUP — TRION BZK Activation (Phase 1)

> **Authored by:** A-ZK (circuits engineer)
> **Task ID:** BZK-PHASE-1
> **Inputs:** `docs/zk/CANON_EXTRACT.md` (verbatim canon), `docs/zk/ZK_SURFACE_MAP.md` (CW-7 proving-system decisions), existing `zk-circuits/` (5 circom circuits, audited as R-NO-REDEF input).
> **First Law:** every decision cites a canon section. Every measurement is labelled `MEASURED` or `ESTIMATE` per R-LABELS.

---

## 1. Environment — Toolchain Availability (Phase 1.0)

| Tool | Available | Version | Used For |
|---|---|---|---|
| `circom` | ✅ | 2.2.3 (system) | R1CS compilation |
| `snarkjs` | ✅ (node_modules/.bin) | 0.7.6 | Powers of Tau, Groth16 setup/prove/verify, R1CS info |
| `circomlib` | ✅ (node_modules) | 2.0.5 | Poseidon, Comparators, Bitify |
| Node.js | ✅ | 20.x | witness calculation |
| `npm` | ✅ | present | dependency management |

**Result:** the toolchain is sufficient to compile all 5 circuits and run
the R1CS info tool. **Groth16 setup/prove/verify requires ~110+ seconds
per circuit on this sandbox** and the sandbox command timeout is 120 s —
this is a **BLOCKER per mission BLOCKER PROTOCOL** for full prove/verify
round-trips. Mitigation: R1CS compilation + constraint measurement
succeeds (the load-bearing Phase-1 output); the ceremony/prove/verify
round-trip is labelled `[OPEN]` and re-attempted in Phase 3 with a longer
timeout or chunked setup.

---

## 2. MEASURED Constraint Counts (Phase 1.2 — R-LABELS: MEASURED)

All 5 circuits compiled successfully with `circom 2.2.3`. Constraint counts
extracted via `snarkjs r1cs info`:

| Circuit | Surface | MEASURED Constraints | MEASURED Wires | Private Inputs | Public Inputs | Spec Estimate | Source |
|---|---|---|---|---|---|---|---|
| `zk_intent_commitment` | S1 Phase 1 (commit) | **1,688** | 1,697 | 7 | 3 | (Phase 1 = hash only, no spec estimate) | BTCP §5.6 Phase 1, §14.1 #19 |
| `zk_complementarity_proof` | S1 Phase 2 (match) | **2,686** | 2,695 | 14 | 5 | ~50,000 (BTCP §5.6) | BTCP §5.6 Phase 2, §14.1 #20 |
| `zk_iap_share_proof` | S2 | **1,078** | 1,077 | 8 | 3 | (no spec estimate) | BTCP §5.3, §14.1 #21 |
| `zk_travel_rule` | S3 | **1,179** | 1,186 | 7 | 3 | (no spec estimate) | BTCP §11 Fix 1, §14.1 #22 |
| `zk_behavioral_credential` (single-epoch base case) | S4 base | **3,298** | 3,302 | 10 | 3 | 500k-2M (BTCP §7.1, for multi-year aggregation) | BTCP §7.1, §14.1 #23, WP-Mar §16 |

### 2.1 Critical Comparison vs. Spec Estimates

**S1 complementarity (Phase 2):** MEASURED 2,686 vs spec estimate ~50,000
constraints. The measured circuit is **18.6× smaller than the spec
estimate**. The spec estimate (BTCP §5.6 verbatim: "Estimated circuit
size: ~50k constraints. Groth16 proof: ~200 bytes. Feasible but requires
4-8 weeks of ZK engineering work.") is **labelled ESTIMATE in the spec**
and **was authored before circuit construction**. The MEASURED value is
smaller because the existing circuit (a) uses Poseidon (SNARK-friendly
hash, ~250 constraints per hash) instead of dual-strand SHA3 in-circuit
(SHA3 is far more expensive in R1CS), and (b) the complementarity check
(asset_in_A == asset_out_B etc.) is a series of equality constraints on
field elements (1 constraint each), not a full hash equality.

**Canon-wins note (CW-9, NEW):** The MEASURED constraint count is a
finding, not a redefinition of the spec. Per R-LABELS, the spec estimate
retains its ESTIMATE label in canon; the MEASURED value is the
mission's number for this specific circuit construction. The spec
estimate describes the general problem class; the MEASURED value
describes this specific circuit. Both are honest.

**S4 behavioral_credential (single-epoch base case):** MEASURED 3,298
constraints for the single-epoch base case. The spec estimate 500k-2M
(BTCP §7.1 verbatim, label CONJECTURE) **refers to the multi-year
aggregation**, NOT the per-epoch base case. The existing circuit is the
per-epoch base case only. The 500k-2M figure remains the correct
estimate for the recursive composition over multi-year records.

---

## 3. Per-Surface Proving-System Decision (Phase 1.1, with CW-7 citations)

### S1 — ZK Intent Commitment (Phase 1 commit + Phase 2 complementarity)

**Decision:** **Groth16 (snarkjs) for S1 Phase 2.**

**Citation (CW-7):** BTCP §5.6 verbatim: "Circuit: `zk_complementarity_proof/`
(MISSING — requires Groth16 or PLONK). Estimated circuit size: ~50k
constraints. Groth16 proof: ~200 bytes."

**Reasoning:** BTCP §5.6 explicitly names "Groth16" and quotes a
"~200 bytes" proof size, which is Groth16-shaped (PLONK proofs are
~400-500 bytes, STARK proofs are ~50-100 kB). The existing circuit
already uses Groth16 (snarkjs). The MEASURED constraint count (2,686)
is well within Groth16's practical range (up to ~10⁶ constraints with
Powers of Tau 2^20).

**Trusted setup:** REQUIRED for Groth16. Ceremony status: **`[OPEN]`**
per R-SETUP — Powers of Tau phase 1 + phase 2 contributions not yet
executed end-to-end in this environment (BLOCKER per §1 above). Plan:
use a shared Powers of Tau (size 2^14 covers all 5 circuits with headroom
for aggregation growth) with at least 3 contributions from independent
parties; record each contribution hash in the ceremony log per R-SETUP.

### S2 — ZK IAP Share Proof

**Decision:** **PLONK (snarkjs) for S2.**

**Citation (CW-7):** BTCP §5.3 verbatim specifies the ZK proof is required
("ZK circuit required: `zk_iap_share_proof/`") but does NOT pin a proving
system. Per mission R-SETUP: "prefer transparent (PLONK/STARK) unless
spec pins Groth16." BTCP does not pin Groth16 for S2.

**Reasoning:** S2's public-inputs profile is small (3 public inputs:
`total_value`, `pool_direction_hash`, `merkle_root`). PLONK's universal
setup (no per-circuit ceremony) is the R-SETUP-preferred choice. The
existing circom circuit compiles to both Groth16 and PLONK; only the
setup step differs.

**Trusted setup:** **NOT required** for PLONK (uses the universal Powers
of Tau). The universal SRS from S1's Powers of Tau phase 1 (2^14)
covers S2 as well. Label: **`[OPEN]`** until universal SRS is finalized.

### S3 — ZK Travel Rule

**Decision:** **PLONK (snarkjs) for S3.**

**Citation (CW-7):** BTCP §11 Fix 1 verbatim specifies the SNARK
statement but does NOT pin a proving system. Per mission R-SETUP, prefer
transparent. BTCP does not pin Groth16 for S3.

**Reasoning:** same as S2. The Travel Rule proof is high-frequency
(transfers > $1,000 per FATF R.16 threshold), so PLONK's slightly larger
proof size (~400-500 bytes vs Groth16's ~200 bytes) is an acceptable
tradeoff for avoiding per-circuit ceremony.

**Trusted setup:** NOT required (universal SRS). Label: `[OPEN]` until
universal SRS finalized.

### S4 — Sensing Oracle / Behavioral Credential

**Phase-1 verdict: GATED-OPEN** (per R-ORDER + CW-3, mission Phase 1.2).

**Decision (when gate passes):** **STARK-based recursive aggregation
(Plonky2/Plonky3 or Nova-style folding) for S4 multi-year.**

**Citation (CW-7):** WP-Mar §16 verbatim: "[CONJECTURE — technical
feasibility]: ZK proofs over behavioral commitments are constructible
using Groth16, PLONK, or STARKs. Computational cost is non-trivial but
decreasing. Specific circuit construction requires cryptographic
engineering work not yet completed." BTCP §7.1 verbatim: "Estimated
circuit size: 500k-2M constraints. Proof aggregation likely required for
efficiency." BTCP §14.1 Phase 4 item 23 verbatim: "(LONG TERM —
requires proof aggregation)."

**Reasoning:** the 500k-2M estimate + "aggregation required" label
rules out Groth16 (Groth16 at 500k constraints is on the edge of
practical; at 2M it requires a 2^22 Powers of Tau, which is a major
ceremony). STARK-based recursion (Plonky2/Plonky3) gives transparent
setup + recursive composition without a ceremony. Nova-style folding
over relaxed R1CS is the alternative — also transparent.

**Single-epoch base case:** the existing `zk_behavioral_credential`
circuit (3,298 constraints, MEASURED) is the per-epoch base case.
For an N-epoch credential, a naive verifier-chain approach is
N × (3,298 constraints) with N verify calls (linear cost). For multi-year
records (e.g., 1,000 epochs), this is ~3.3M constraints total —
feasible but expensive. The recursive aggregation approach (Plonky2
folding) would reduce this to a constant-size proof.

**Gate criteria (per R-ORDER, Phase 1.2):**
1. Install Plonky2 or Nova toolchain (Rust crates).
2. Build a 2-epoch recursive composition prototype; MEASURED recursion overhead (constraints added per fold).
3. If measured recursion overhead < 2× per-epoch base case →
   IMPLEMENTABLE-NOW.
4. If overhead > 2× or toolchain unavailable → GATED-OPEN with threshold.

**Current status:** toolchain not installed in this environment. S4
remains **GATED-OPEN**. The single-epoch base case is MEASURED (3,298
constraints); the aggregation verdict is deferred per R-ORDER.

### S5 — BIRP

**Phase-1 verdict: GATED-OPEN** (enrollment store only; recovery path conjectural).

**Decision:** **No ZK circuit for S5 enrollment** — it is hash-only per
WP-Mar §16 verbatim: "Stored in Akashic Index: `BIRP_anchor` — permanent,
immutable. Not stored: `DNA_Code` — ever." The Phase-2 commitment layer
(A-REG, completed) implements the enrollment store correctly (commit
`9dc42a5`).

**Recovery path:** WP-Mar §16 Phases 1-5 describe a multi-factor
verification protocol (timing, length, behavioral proof, temporal
cluster, Conscious Layer). This is NOT a single ZK circuit — it is a
protocol involving multiple proof systems and human verification. The
drift false-negative rate is `[CONJECTURE]` per WP-Mar §16 verbatim.

**Gate criteria for S5 recovery path activation:**
1. Empirical drift false-negative rate measured over a SYNTHETIC-DEMO
   behavioral set (mission Z11).
2. Conscious Layer 2-of-3 verification implemented (out of scope for
   this mission — operator's responsibility post-mission).
3. 7-day waiting period + BEO cluster notification wired (operational).

**Current status:** S5 recovery path **GATED-OPEN**. Only the
enrollment store is operational (hash-only, Phase 2 complete).

---

## 4. S4 Aggregation Study (Phase 1.2 — OQ-7/Q2 Verdict)

### 4.1 The Question (BTCP §16 OQ-7 verbatim)

> **OQ-7 — ZK Circuit Efficiency:** What is the minimum circuit size for
> behavioral coherence ZK-SNARK satisfying the 7-plane check? Is it
> gas-efficient enough for high-frequency BTCP routes?

### 4.2 The 7-Plane Coherence Check (BTCP §12.1 Formula Index verbatim)

```
C(t) = α·Φ_adj(t) + β·M_adj(t) + γ·Σ(t) + δ·K(t) + ε·A(t)
Φ_adj = Φ(t) × (1 - MF_score(t))
M_adj = M(t) × (1 - OE_factor(t))
Weights: α=0.25, β=0.30, γ=0.25, δ=0.10, ε=0.10
```

The 7 planes (per WP-Mar §16 + BTCP §7.1 verbatim "plane_results:
[TRUE/FALSE × 7 planes]"):
1. Φ (Phi) — behavioral coherence plane
2. M (Manipulation fingerprint)
3. Σ (Sigma, spiritual)
4. K (Kappa, conscious)
5. A (ANIMA)
6. Φ_adj (manipulation-adjusted Phi)
7. M_adj (observer-effect-adjusted M)

The existing `zk_behavioral_credential/circuit.circom` (3,298 constraints)
proves coherence with the pattern commitment for a SINGLE epoch over
these 7 planes (the `pattern_fields[7]` are `C, phi, m, sigma, k, anima, mf`).

### 4.3 Three Aggregation Approaches (per CW-7)

| Approach | Per-epoch constraints | Recursion overhead | Setup type | Maturity |
|---|---|---|---|---|
| (a) Per-epoch Groth16 + on-chain verifier chain | 3,298 (MEASURED) | 0 recursion; N verify calls on-chain | Per-circuit ceremony | Production-ready today |
| (b) Nova-style folding over relaxed R1CS | 3,298 base + ~2× per fold | ~6,600/fold (ESTIMATE) | Transparent | Research-grade; Nova library exists in Rust |
| (c) Plonky2/Plonky3 recursive STARK composition | ~50k base (STARK circuits are larger than R1CS) | ~100k/fold (ESTIMATE) | Transparent | Production-grade; used by Polygon zkEVM |

### 4.4 MEASURED Per-Epoch Base Case

The existing `zk_behavioral_credential` circuit, when compiled, produces
3,298 constraints for a single epoch. This is the MEASURED per-epoch base
case. For a multi-year credential of N epochs:

- Approach (a): N × 3,298 constraints total, N verifyProof calls on-chain.
  For 1,000 epochs: ~3.3M constraints, ~1,000 verify calls (~250k gas each
  = 250M gas total — exceeds Ethereum block gas limit of 30M).
  **Verdict: not gas-efficient for high-frequency BTCP routes per OQ-7.**
  Suitable for low-frequency credentials (annual reissuance).

- Approach (b/c): constant-size proof regardless of N. Single verify call.
  **Verdict: gas-efficient per OQ-7. Requires toolchain not available
  in this environment.**

### 4.5 Verdict (per mission Phase 1.2)

**S4: GATED-OPEN.**

- The single-epoch base case is MEASURED (3,298 constraints) and
  compiles successfully.
- The multi-year aggregation (the canon's actual S4 scope per BTCP §14.1
  #23 "Multi-year behavioral record as ZK circuit input. Proof aggregation
  (recursive proofs) for efficiency") requires either Nova or Plonky2,
  neither of which is installed in this environment.
- Per R-ORDER + mission Phase 1.2 + CW-3: **no partial claim of S4
  activation is made.** S4 status remains GATED-OPEN.

**Threshold criteria for S4 to become IMPLEMENTABLE-NOW:**
1. Install Plonky2 (or Nova) Rust toolchain.
2. Build a 2-epoch recursive prototype using the existing single-epoch
   circuit as the base case.
3. MEASURED recursion overhead < 2× per-epoch base case.
4. MEASURED verifier gas < 500k gas per aggregated proof.

When all 4 criteria are met, S4 status changes from GATED-OPEN to
IMPLEMENTABLE-NOW and the Phase 3 circuit construction can proceed.

---

## 5. Setup Policy Per Circuit (Phase 1.3 — R-SETUP)

| Circuit | Proving System | Trusted Setup Required? | Ceremony Status | Notes |
|---|---|---|---|---|
| S1 Phase 2 (complementarity) | Groth16 | YES (per-circuit) | **`[OPEN]`** | Per BTCP §5.6 verbatim "requires Groth16". Powers of Tau phase 1 (universal, 2^14) + phase 2 (circuit-specific). |
| S2 (IAP share) | PLONK | NO (universal SRS) | **`[OPEN]`** | Universal SRS from S1's Powers of Tau phase 1. R-SETUP compliant (transparent). |
| S3 (travel rule) | PLONK | NO (universal SRS) | **`[OPEN]`** | Same universal SRS as S2. |
| S4 base case (single-epoch) | Groth16 (existing circuit) | YES (per-circuit) | **`[OPEN]`** | Existing circuit uses Groth16. Ceremony same pattern as S1. |
| S4 multi-year (aggregation) | STARK (Plonky2/Plonky3) or Nova | NO (transparent) | **`[OPEN]`** | GATED-OPEN per §4.5 above. |

**Ceremony plan (when executed):**
- Phase 1: `snarkjs powersoftau new bn128 14 pot14_0000.ptau` (initiator)
- Phase 1 contributions: at least 3 independent parties contribute
  (per R-SETUP "any ceremony labeled [OPEN] until executed, then [V ceremony record]")
- Phase 2: `snarkjs powersoftau prepare phase2 pot14_final.ptau` (universal SRS)
- Per-circuit (S1 + S4 base only): `snarkjs groth16 setup circuit.r1cs pot14_final.ptau circuit_0000.zkey` + at least 1 contribution → `circuit_final.zkey`

**Ceremony record file:** to be created at `docs/zk/CEREMONY_RECORD.md`
when ceremony is executed. Currently does NOT exist — ceremony is `[OPEN]`.

---

## 6. Phase 1 Acceptance Gate

| Acceptance criterion (mission Phase 1) | Status | Evidence |
|---|---|---|
| Per-surface proving-system decision with citation | ✅ YES | §3 above (CW-7 citations per surface) |
| Constraint counts from a compiled pilot circuit (MEASURED, not spec quotes) | ✅ YES | §2 table — all 5 circuits compiled with circom 2.2.3, constraint counts via `snarkjs r1cs info` |
| S4 aggregation study (OQ-7/Q2) with measured numbers + verdict | ✅ YES (GATED-OPEN verdict) | §4 above — single-epoch base case MEASURED (3,298); aggregation approaches evaluated; toolchain unavailable is the gate |
| Setup policy per R-SETUP; ceremony plan if Groth16 pinned | ✅ YES | §5 above — per-circuit decisions + ceremony plan; ceremony status `[OPEN]` |

**Phase 1 ACCEPTANCE: GATE PASSED.**

---

## 7. Phase 3 Hand-off to A-ZK (next phase)

A-ZK (Phase 3, circuit constructor) receives:
- 5 compiled circuits (R1CS files at `zk-circuits/*/build/circuit.r1cs`)
- MEASURED constraint counts (§2 table)
- Per-surface proving-system decisions (§3)
- S4 GATED-OPEN status + threshold criteria (§4.5)
- Ceremony plan + `[OPEN]` ceremony status (§5)

Phase 3 must produce per BTCP Phase 4 items 19-23:
- S1 commit phase (no circuit — hash only, Phase 2.1 done)
- S1 complementarity circuit — round-trip prove/verify (BLOCKER: Groth16 setup needs >110s; mitigation: chunked setup or longer-timeout env)
- S2 IAP share-proof circuit — round-trip prove/verify
- S3 travel-rule SNARK — round-trip prove/verify + regulator-encryption boundary test
- S4 behavioral-credential circuit — **GATED-OPEN, NO build claimed this mission**
- Benchmark table: constraints, prove time, verify time, proof bytes per circuit (MEASURED vs spec ESTIMATE labels)

---

*Authored by A-ZK. Witnessed by A-AUD (audit ledger: `docs/zk/A_AUD_ledger.md`).
v-stamp: `bzk-feasibility-v0.1`. Status: Phase 1 ACCEPTANCE GATE PASSED with
S4 GATED-OPEN per R-ORDER + CW-3.*
