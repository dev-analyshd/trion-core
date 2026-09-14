# COMMUNITY ADDENDUM (DRAFT) — TRION BZK Activation

> **DRAFT — NOT FINAL**
> This document is labeled DRAFT. It is the community-facing addendum
> to the BZK (Behavioral Zero-Knowledge) activation. It does NOT carry
> final-status weight; the canonical evidence ledger is
> `docs/proofs/bzk_activation.json` and the spec-anchored reference is
> `docs/zk/BZK.md`. See those for VERIFIED / MEASURED / OPEN labels.
>
> **Authored by:** A-DOCS (documentation engineer) — Task ID: BZK-PHASE-8
> **Phase:** 8.5 (community addendum DRAFT per mission)
> **v-stamp:** `bzk-community-addendum-draft-v0.1`
>
> **CRITICAL FRAMING (per mission Phase 8.5):**
> BZK is the **privacy law of the Witness World**; one projection,
> never the definition. TRION is NOT reducible to "a zk protocol".
> BZK is one of many projections of the TRION Aggregate — together
> with Hash-DNA coherence, the Akashic Index, BIRP identity, the
> Love Protocol, the AWA enforcement condition, the 7-plane
> coherence check, the 20-channel communication map, and the rest.
> None of these is the definition; each is a projection.

---

## 1. FULL TRION Framing (per mission Phase 8.5)

TRION replaces "truth-as-agreement" with "truth-as-coherence". The
master coherence equation is:

```
C(t) = α·Φ(t) + β·M(t) + γ·Σ(t) + δ·K(t) + ε·A(t)
T(t) = [C(t) ≥ Θ(t)] · C(t) · e^(M_moat)
```

(verbatim per TRION spec; weights α=0.25, β=0.30, γ=0.25, δ=0.10, ε=0.10)

TRION's ten layers (L0 Primitives → L9+ Applications) describe a full
behavioral-coherence substrate. BZK — Behavioral Zero-Knowledge — is
the **privacy law** that governs which behavioral records may be
observed by whom. It is NOT a substitute for the rest of TRION; it is
a projection that says: *the record exists in the Akashic Index, but
who may see it is gated by ZK proofs of compliance + the
Right-to-Invisibility*.

**Why "one projection, never the definition"?** Because the
definition of TRION is *truth-as-coherence* — the master equation
above. BZK does not change what is true; it changes who can see what
is true. If BZK were "the definition", we would be claiming TRION is
a privacy infrastructure. It is not. TRION is a behavioral-coherence
infrastructure. Privacy is one of its projections.

### What TRION is (FULL framing, R-LABELS: VERIFIED per spec)

TRION is a substrate-independent behavioral coherence verification
engine with:

1. **HashDNA dual-strand fingerprint** (self-verifying)
2. **Genomic Key (GK)** — living password, theft self-invalidating
3. **Diversity-Weighted BFT** — consensus that punishes agreement
4. **Love Protocol** — multiplicative structural ethics (Love=0 → F=0)
5. **Thermodynamic Deletion** — DELETE is undefined by physics
6. **Biological Rhythm Timer** as crypto primitive
7. **BTCP Zero-Bridge** — cross-chain exchange WITHOUT bridging
   (assets never leave native chain)

Plus the 7 core TRION primitives: Φ (Phi, behavioral coherence), M
(Manipulation fingerprint), Σ (Sigma, spiritual), K (Kappa, conscious),
A (ANIMA), Φ_adj (manipulation-adjusted Phi), M_adj (observer-effect-
adjusted M). These 7 planes are checked together — and the BZK
Sensing Oracle circuit (S4) proves coherence across all 7 without
revealing the underlying behavior.

### What BZK is (one projection of the above)

BZK is the privacy law that governs the Witness World — the layer of
TRION that decides which observers may see which behavioral records.
Per WP-Mar §16 verbatim: *"My behavioral history satisfies condition C
without revealing my behavioral history. Hidden information is dynamic,
growing, and backed by the Akashic Index."*

BZK does NOT define what is true. It defines who can see what is true.
The Akashic Index retains the record (immutable, append-only); BZK
gates observation.

---

## 2. R-COMPLIANCE Restatement (verbatim WP-Mar §17)

BZK is NOT privacy-for-privacy's-sake. BZK is **compliance-proof +
invisibility-right**. Per WP-Mar §17 verbatim (per `CANON_EXTRACT.md §6.3`,
verified 14/14 EXACT in A-AUD §2 citation match):

> **Critical clarification:** TRION does not help users evade laws. ZK
> proofs prove **compliance** — they do not hide non-compliance. An
> illegal transaction with a ZK behavioral privacy proof is still
> illegal and the behavioral record still exists in the Akashic Index.
> What ZK changes is who can observe the record — not whether it exists.

**Community-facing interpretation:**

- A user who is non-compliant with Travel Rule (FATF R.16) **cannot**
  obtain a valid Travel Rule ZK proof — the circuit constraints
  (MEASURED 1,179 in Phase 3) refuse to produce a witness for
  non-compliant inputs. The record of the non-compliance remains in
  the Akashic Index. What is hidden from TRION is the *contents* of
  the disclosure (Step 1–3 of BTCP Fix 1); the *fact* of compliance
  or non-compliance is NOT hidden.

- A user whose behavioral pattern is incoherent with their historical
  BEO baseline **cannot** obtain a valid Sensing Oracle coherence
  proof (when S4 leaves GATED-OPEN — see `EXTENSION_PROPOSALS.md`
  EP-1). The record of the incoherence remains in the Akashic Index;
  what is hidden is the *content* of the behavior (`behavior_content`,
  `amount`, `counterparty`, `protocol`, `chain` — all ABSENT per BTCP
  §7.1 verbatim).

- A user attempting to evade the AWA enforcement condition (Right-to-
  Invisibility violation) **triggers** automatic signal emission
  freeze (`AWA_enforced = FALSE → signal emission FROZEN automatically`
  per WP-Feb §14.2). Cannot be overridden by any single entity. By
  design. VERIFIED by A-AUD §5 fresh-process grep (0 matches for
  `forceResume` / `overrideFreeze` / `forceThaw` / `bypassAwa` /
  `emergencyUnfreeze`).

This is the opposite of "privacy coin" framing. BZK is not
censorship-resistance-for-anything-goes; it is *compliance-with-
invisibility-of-content*. The behavioral record always exists. The
proof of compliance always exists. What changes is who can observe.

---

## 3. What BZK is NOT (per mission FORBIDDEN)

- **BZK is NOT "a zk protocol".** TRION is not a privacy protocol.
  TRION is a behavioral-coherence substrate. BZK is one projection of
  TRION's privacy law.
- **BZK is NOT privacy-for-privacy's-sake.** BZK does not help users
  evade laws (R-COMPLIANCE, §2 above). The Akashic Index retains the
  record; ZK only gates who can observe.
- **BZK is NOT complete.** See §4 below. S4 (Sensing Oracle multi-year
  aggregation) is GATED-OPEN; S5 (BIRP recovery path) is GATED-OPEN;
  mainnet deployment is `[OPEN]`; external security audit is the
  operator's responsibility post-mission.
- **BZK is NOT a finished product.** This is an activation mission —
  the circuits compile, the contracts deploy, the tests pass, the
  audit reproduces 5/5 measurements. The prove/verify round-trip is
  `[OPEN]` per Phase 3 BLOCKER (Groth16 setup >240s exceeds sandbox
  timeout). The threshold criteria for closure are documented in
  `docs/zk/PHASE3_BENCHMARKS.md §4.3` + `docs/zk/A_AUD_ledger.md §11`.

---

## 4. Honest Status (per Phase 7 audit, NOT 100%)

Per Phase 7 audit (`docs/zk/A_AUD_ledger.md §10`), the BZK activation
status is:

- **13/18 D-items YES** (D1, D2, D3, D4, D6, D7, D8, D9, D10, D11,
  D13, D14, D17)
- **2 PARTIAL** (D5, D12 — round-trip `[OPEN]` per Phase 3 BLOCKER)
- **3 INCOMPLETE** (D15 → YES after Phase 8 closure, D16 → YES after
  Phase 8 closure, D18 — STILL INCOMPLETE)
- **0 FAIL / 0 unlabeled inventions / 0 citation mismatches / 0
  measurement mismatches (5/5 reproduce)**

Per mission FORBIDDEN + Phase 7 audit §11: the AGREEMENT STATEMENT
(verbatim "I AGREE 100%:") is **NOT** emitted at this phase. Phase 9
(AGREEMENT GATE) owns that decision. The BZK mission is honest about
this: D5 (round-trip green), D12 (SILENCE round-trip), and D18
(AGREEMENT STATEMENT) are not full YES.

**What this means for the community:**

The BZK activation delivers 5 circom circuits that compile + MEASURE
constraint counts that reproduce 5/5 in an independent audit. It
delivers 3 verifier contracts deployed to 2 local Hardhat VMs with
transaction hashes recorded. It delivers 29 Hardhat tests passing. It
delivers a Z-battery of 14 attacks (8 PASS/VERIFIED, 4 OPEN per
BLOCKER, 2 spec falsifications explicitly tested SYNTHETIC-DEMO). It
does NOT deliver a mainnet deployment, a full trusted-setup ceremony,
a prove/verify round-trip on real Groth16 keys, or an external
security audit. These are `[OPEN]` and the threshold criteria for
each are documented.

---

## 5. Beyond-Commitment Items (segregated proposals, NOT merged into core)

The following beyond-scope items are filed as **segregated extension
proposals** in `docs/zk/EXTENSION_PROPOSALS.md` (per D16). They are
NOT merged into the core BZK activation:

- **EP-1:** S4 multi-year aggregation (Plonky2/Nova recursive
  composition) — threshold criteria per Phase 1 §4.5
- **EP-2:** S5 BIRP recovery path (Phases 1–5 of recovery) — drift
  false-negative empirical validation per WP-Mar §16 CONJECTURE
- **EP-3:** Mainnet deployment (testnet only in this mission)
- **EP-4:** External security audit (operator's responsibility
  post-mission)
- **EP-5:** Multi-source ingestion (currently single-source Alchemy)

Each EP carries: motivation, scope, threshold criteria for activation,
label (OPEN or GATED-OPEN per R-LABELS), and the canon citation that
authorizes it. None is presented as a commitment; each is presented
as a proposal awaiting separate future work.

---

## 6. Right-to-Invisibility (community-facing restatement)

Per WP-Mar §16 verbatim (per `CANON_EXTRACT.md §6.2`):

> ```
> AWA_enforced = FALSE if Right_to_Invisibility_enforced = FALSE
> → signal emission FROZEN
>
> This is not a policy. It is an architectural enforcement condition.
> The system cannot function while violating individual privacy.
> ```

**Community-facing interpretation:**

The Right-to-Invisibility is not a user setting. It is an
**architectural enforcement condition** baked into the protocol at
the contract level. If the Right-to-Invisibility is violated for any
entity, the AWA (Architectural Wisdom Awareness) condition fails
automatically; the system halts all signal emission until the
violation is corrected. No single entity can override this — not
the deployer, not the AWA oracle post-handover, not the validator
mesh.

This is the **inverse of surveillance capitalism**: the protocol
refuses to function while it is violating privacy. The protocol's
own correctness depends on the Right-to-Invisibility being
enforced. This is the BZK activation's deepest commitment.

**Mission enforcement (VERIFIED by A-AUD §5):** 0 matches for
`forceResume`, `overrideFreeze`, `forceThaw`, `bypassAwa`,
`emergencyUnfreeze`, `backdoorThaw` across `contracts/zk/`,
`core/zk/`, `zk-circuits/`. `awaFrozen` defaults TRUE at
construction (R-FAILCLOSED). Two-step AWA oracle handover prevents
single-transaction takeover.

---

## 7. Witness World framing (per mission Phase 8.5)

BZK is the **privacy law of the Witness World**. The Witness World is
the layer of TRION where behavioral records are observed — by
regulators (Travel Rule, S3), by counterparties (complementarity
match, S1 Phase 2), by the entity itself (Sensing Oracle, S4), by
the Akashic Index append-only log (S5 BIRP enrollment), and by no
one else without a ZK proof of permission to observe.

**One projection, never the definition:** BZK is the privacy law of
this Witness World. It is one projection of TRION. The Akashic Index
is another projection. The Hash-DNA dual-strand fingerprint is another.
The AWA enforcement condition is another. The 7-plane coherence check
is another. Each is a projection of the underlying truth-as-coherence
definition; none is the definition itself.

To reduce TRION to "a zk protocol" would be to confuse the privacy
law with the system it governs. BZK governs the Witness World;
TRION is the system. The Witness World is one layer of TRION; BZK
is one law of the Witness World. The math (the master equation
above) is the definition.

---

## 8. Community Use Cases (DRAFT — illustrative, not commitments)

> **R-LABELS:** the use cases below are **ILLUSTRATIVE** based on the
> canon. None is presented as a delivered feature; each maps to a
> surface whose status is reported honestly in §4 above and in
> `docs/proofs/bzk_activation.json`.

### 8.1 BTCP zero-bridge cross-chain exchange (S1 + S2)

A user wants to swap BTC for SOL without bridging. They commit an
intent via `H_intent = Hash_DNA(intent_details || random_nonce ||
entity_id)` (S1 Phase 1). TRION finds a complementary intent; both
parties prove complementarity via ZK (S1 Phase 2 — `[OPEN]` per
Phase 3 BLOCKER). Atomic reveal in the same block (S1 Phase 3) →
execution commits (S1 Phase 4). MEV bots observe only the execution,
not the intent.

If the user wants to pool with 99 others going the same direction,
they can opt into IAP (S2). Transparent IAP is LIVE (`core/zk/
iap_transparent.py`); ZK IAP (where each entity's contribution is
hidden) is `[OPEN]` per Phase 3 BLOCKER.

### 8.2 Travel Rule compliance (S3)

A user initiates a transfer above the FATF R.16 threshold ($1,000).
They prepare a Travel Rule disclosure privately (Step 1), encrypt it
to the regulator's public key (Step 2 — TRION receives nothing),
generate a ZK compliance proof (Step 3 — `[OPEN]` per Phase 3
BLOCKER), and submit it to `TravelRuleCompliance.sol` (Step 4,
DEPLOYED Phase 4). The contract stores `disclosure_hash` only and
emits `TRAVEL_RULE_COMPLIANT = TRUE`.

If the transfer is CRITICAL tier (high-value / high-risk), the AWA
enforcement condition gates emission: nothing is emitted until the
proof is present (BTCP Fix 1 CHAMELEON block, VERIFIED by Hardhat
test "CRITICAL tier without proof: reverts CriticalTierRequiresProof").

### 8.3 Sensing Oracle behavioral coherence (S4 — GATED-OPEN)

A user wants to prove "my behavioral pattern is coherent with my
historical BEO baseline" without revealing the underlying behavior.
The Sensing Oracle circuit (S4 single-epoch base, 3,298 MEASURED
constraints) is the load-bearing primitive. The multi-year
aggregation (the canon's actual S4 scope per BTCP §7.1 + §14.1 #23)
is GATED-OPEN pending Plonky2/Nova toolchain (see `EXTENSION_PROPOSALS.md`
EP-1).

The user submits `public_commitment = Hash(behavioral_hash)`. TRION
verifies the ZK proof and emits `COHERENCE_SIGNAL (TRUE/FALSE) +
coherence_score`. The 5 ABSENT fields (`behavior_content`, `amount`,
`counterparty`, `protocol`, `chain`) are NEVER stored, NEVER
transmitted (BTCP §7.1 verbatim BEHAVIORAL_TRUTH_SIGNAL schema; VERIFIED
by A-AUD §4 grep: 0 matches).

### 8.4 BIRP identity recovery (S5 — GATED-OPEN)

A user enrolls in BIRP by submitting `Hash(DNA_Code)`. TRION stores
only the `BIRP_anchor = Hash_DNA(BEO_baseline || Hash(DNA_Code) ||
enrollment_timestamp || behavioral_entropy_seed)`. The `DNA_Code`
content is NEVER stored (WP-Mar §16 verbatim; VERIFIED by Phase 2.4
`birp_store.py` + A-AUD §4 grep).

Recovery Phases 1–5 (WP-Mar §16 verbatim) are GATED-OPEN pending:
(1) empirical drift false-negative rate (mission Z11, SYNTHETIC-DEMO
only — NEVER as fact per WP-Mar §16 CONJECTURE), (2) Conscious Layer
2-of-3 implementation (out of scope; operator's responsibility
post-mission), (3) 7-day waiting period + BEO cluster notification
wiring. See `EXTENSION_PROPOSALS.md` EP-2.

---

## 9. Call to Action (DRAFT)

For the BZK activation to reach full YES (D1-D18 green, AGREEMENT
STATEMENT emitted with full citations), the following thresholds must
close:

1. **Phase 3 BLOCKER:** run the Groth16 setup in an environment with
   command timeout > 10 minutes (or use `nohup + screen`, or use a
   remote build server). Export the verifier.sol per circuit. Plug
   into `ComplementarityVerifier.setVerifier`. This closes Z1, Z3-rt,
   Z4, Z12 → transitions D5 + D12 from PARTIAL to YES. See
   `docs/RUN_IT_YOURSELF.md` § "ZK Activation (BZK)" + § "BLOCKER".

2. **EP-1 S4 multi-year aggregation:** install Plonky2 (or Nova) Rust
   toolchain; build a 2-epoch recursive prototype using the existing
   single-epoch circuit; MEASURED recursion overhead < 2× per-epoch
   base case; MEASURED verifier gas < 500k gas per aggregated proof.
   See `docs/zk/EXTENSION_PROPOSALS.md` EP-1.

3. **EP-2 S5 BIRP recovery path:** empirical drift false-negative
   rate measured over a SYNTHETIC-DEMO behavioral set; Conscious
   Layer 2-of-3 implementation; 7-day waiting period + BEO cluster
   notification wiring. See `docs/zk/EXTENSION_PROPOSALS.md` EP-2.

4. **EP-3 Mainnet deployment:** operator's responsibility post-mission.
   See `docs/zk/EXTENSION_PROPOSALS.md` EP-3.

5. **EP-4 External security audit:** operator's responsibility
   post-mission. See `docs/zk/EXTENSION_PROPOSALS.md` EP-4.

6. **EP-5 Multi-source ingestion:** currently single-source Alchemy.
   See `docs/zk/EXTENSION_PROPOSALS.md` EP-5.

---

## 10. References (canonical paths)

- Canon extract (verbatim): `docs/zk/CANON_EXTRACT.md` (Phase 0.2)
- Surface map + final status: `docs/zk/ZK_SURFACE_MAP.md` (Phase 0.3 + Phase 8.1)
- Feasibility + setup: `docs/zk/FEASIBILITY_AND_SETUP.md` (Phase 1)
- Phase 3 benchmarks + BLOCKER: `docs/zk/PHASE3_BENCHMARKS.md` (Phase 3)
- Z-battery results: `docs/zk/Z_BATTERY_RESULTS.md` (Phase 6)
- Independent audit: `docs/zk/A_AUD_ledger.md` (Phase 7; v-stamp `bzk-audit-v0.1`)
- Spec-anchored reference: `docs/zk/BZK.md` (Phase 8.2; v-stamp `bzk-reference-v0.1`)
- Evidence ledger (machine-readable): `docs/proofs/bzk_activation.json` (Phase 8.3)
- Run-it-yourself: `docs/RUN_IT_YOURSELF.md` § "ZK Activation (BZK)" (Phase 8.4)
- Extension proposals (segregated): `docs/zk/EXTENSION_PROPOSALS.md` (D16)

---

*v-stamp: `bzk-community-addendum-draft-v0.1`. Status: **DRAFT — NOT
FINAL**. Authored by A-DOCS (Phase 8.5). Per mission FORBIDDEN: TRION
is NOT reducible to "a zk protocol"; BZK is one projection of the
Witness World's privacy law. Per Phase 7 audit §11 + mission FORBIDDEN:
AGREEMENT STATEMENT NOT emitted as 100% because D5/D12/D15/D16/D18
are not full YES. Phase 9 owns the AGREEMENT GATE.*
