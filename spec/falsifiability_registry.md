# TRION Protocol — Falsifiability Registry Specification

> **Canonical source:** TRION Whitepaper, **PART 13 — Formal Proofs and
> Falsifiability**, "Complete Falsifiability Table" (F1–F15).
>
> This document enumerates the 15 falsifiability conditions F1–F15. Each
> condition is an empirically testable claim with a precise metric,
> threshold, and observation window. If any condition is violated, the
> corresponding TRION claim is falsified.

## Scope

FIX-E (Gap 18) consolidation: TRION previously carried THREE divergent
F1–F15 registries:

1. **Whitepaper PART 13 "Complete Falsifiability Table"** — canonical.
2. API endpoint `/api/v1/falsifiability` (served by
   `core/governance/falsifiability_registry.py`) — previously followed
   WP2 §20 (which elevated BRT-gas-correlation to F14 and
   REGULATORY_BEHAVIORAL-24-month to F15 as CONJECTUREs).
3. This markdown registry — previously followed WP1's primitive-based
   per-layer mapping (F1=BH collision, F2=BEO monotonic, F3=Resonance
   AUC, F4=Conservation drift, F5=Signal entropy, F6=Fitness log-odds,
   F7=Physical Richness PCA, F8=MF recall/precision, F9=Resurrection
   accuracy, F10=DW-BFT halt rate, F11=ZK soundness, F12=BIBL drift,
   F13=ANIMA amplitude, F14=Threshold correlation, F15=XSL bounding).

Per Gap 18, both the API registry and this markdown file now mirror the
whitepaper PART 13 table VERBATIM. The retired WP1 and WP2 §20 mappings
are documented in `docs/audit/CANONICAL_SPEC_MATRIX.md` (K13) and in
`spec/open_research_questions.md` (for the long-horizon CONJECTUREs).

A scientific protocol must specify in advance the conditions under which
it would be proven wrong. TRION commits to 15 falsifiability conditions;
violation of any one triggers a protocol-level review and may require
parameter adjustment or protocol retirement.

---

## Complete Falsifiability Table (Whitepaper Part 13)

The table below is the verbatim Whitepaper Part 13 "Complete
Falsifiability Table". Each F-condition's `Claim`, `Falsification
Condition`, and `Window` are reproduced exactly as published in the
whitepaper.

| ID  | Claim Under Test        | Falsification Condition                                                      | Window                |
|-----|-------------------------|------------------------------------------------------------------------------|-----------------------|
| F1  | Manipulation resistance | Documented successful manipulation at D(t) > D_minimum                       | Any time              |
| F2  | Consensus safety        | Two contradictory signals certified for same asset simultaneously             | Any time              |
| F3  | ANIMA improves signals  | ANIMA-enhanced consistently less accurate than 3-plane alone                | 90-day rolling        |
| F4  | Quantum resistance      | LSS breached without causal history reproduction                             | Any time              |
| F5  | Signal convergence      | Persistent divergence not decreasing as D(t) grows                           | 12-month rolling      |
| F6  | Genesis Inference valid | Systematic divergence from realized outcomes                                | 90-day, 100+ events  |
| F7  | IM Protocol operational | Silent accuracy degradation lasting > 24 hours                               | Continuous            |
| F8  | Diversity enforced      | HHI > 2500 sustained > 30 consecutive days                                   | Continuous            |
| F9  | BC scores valid         | Systematic divergence from peer-reviewed ecosystem valuations                | 12-month rolling      |
| F10 | XSL early warning       | Species declines not preceded by XSL decline > 30 days                       | Per event             |
| F11 | SBA accuracy            | Systematic divergence from IMF/World Bank composites                         | 24-month rolling      |
| F12 | ANIMA calibration      | Probability distributions consistently miscalibrated                        | 90-day rolling        |
| F13 | Entity Resolution      | Known unified actors not clustered at > 95% rate                             | Quarterly audit       |
| F14 | Observer Effect corrected | M_adj not lower than M_base for high-OE assets                           | Continuous            |
| F15 | Silence is informative  | Gap field in Silence Signals uncorrelated with next-signal time              | 6-month rolling       |

---

## Per-Condition Reference

### F1 — Manipulation resistance

```
Claim      : No rational economic actor can profitably manipulate TRION
             signals for any asset with sufficient behavioral history
             (D(t) > D_minimum, > 6 months).
Falsified  : by documented successful manipulation for asset with
             D(t) > D_minimum.
Window     : Any time
Layer      : L1.2 (Manipulation Fingerprint) + L0.5 (Signal Selection)
Proof link : Whitepaper Part 13 Proof 1 — Manipulation Resistance
Action     : quarantine L1.2 fingerprints; expand manipulation archetypes;
             emit SYSTEMIC_RISK signal on all 20 channels
```

### F2 — Consensus safety

```
Claim      : TRION's diversity-weighted BFT is safe and live; honesty
             is the only rational equilibrium.
Falsified  : by two contradictory signals simultaneously certified for
             same asset at same time.
Window     : Any time
Layer      : L4.1 (Diversity-Weighted BFT)
Proof link : Whitepaper Part 13 Proof 2 — Consensus Safety
Action     : halt certification; re-evaluate d_j diversity floor; revert
             to single-strand validation
```

### F3 — ANIMA improves signals

```
Claim      : ANIMA (5th-plane) augmentation improves signal accuracy
             over the 3-plane-alone baseline.
Falsified  : if ANIMA-enhanced consistently less accurate than 3-plane
             alone.
Window     : 90-day rolling
Layer      : L3.3 (ANIMA Score)
Action     : re-evaluate ANIMA weight ε in C(t)=α·Φ+β·M+γ·Σ+δ·K+ε·A;
             re-fit PCR/HA/CA sub-scores
```

### F4 — Quantum resistance

```
Claim      : The Living Security System is resistant to attacks by
             arbitrarily powerful quantum computers (Kolmogorov bound
             grows without bound).
Falsified  : if LSS breached without demonstrably reproducing causal
             history.
Window     : Any time
Layer      : L4.3–L4.6 (Living Security System)
Proof link : Whitepaper Part 13 Proof 3 — Quantum Resistance of LSS
Action     : halt LSS; require causal-history reproduction for every
             attestation; emit SOVEREIGN_BEHAVIORAL signal
```

### F5 — Signal convergence

```
Claim      : lim_{D(t)→∞} E[|T(t) − V_true|] = H_irreducible
             (diversity-weighted consensus is a consistent estimator).
Falsified  : by persistent divergence from realized values that does
             not decrease as D(t) grows.
Window     : 12-month rolling
Layer      : L2.5 (Akashic Convergence)
Proof link : Whitepaper Part 13 Proof 4 — Signal Convergence
Action     : re-evaluate diversity-weighted estimator; audit d_j
             enforcement; tighten H_irreducible bound
```

### F6 — Genesis Inference valid

```
Claim      : Genesis inferences converge to behavioral reality as the
             bootstrapped entity accumulates history.
Falsified  : by systematic divergence from realized outcomes.
Window     : 90-day, 100+ events
Layer      : L2.3 (Genesis Confidence)
Action     : re-fit V₀=Σ sim(G,Aₖ)·Vₖ/Σ sim; re-evaluate w_CF/w_ST/w_SC/w_BP
```

### F7 — IM Protocol operational

```
Claim      : Intelligence Maintenance (IM) protocol detects and
             corrects any component degradation within 24 hours.
Falsified  : by silent accuracy degradation lasting > 24 hours.
Window     : Continuous
Layer      : L3.7 (Intelligence Maintenance)
Action     : re-tune Acc(t)/Acc(baseline) thresholds; expand IM
             observation window; quarantine degraded component
```

### F8 — Diversity enforced

```
Claim      : Validator HHI is bounded and geographic distribution is
             enforced by auto-corrective incentives.
Falsified  : if HHI > 2500 sustained > 30 consecutive days.
Window     : Continuous
Layer      : L4.8 (HHI + Geographic Enforcement)
Action     : activate underserved-chain coverage multiplier; force
             weight cap; pause consensus if not auto-corrected
```

### F9 — BC scores valid

```
Claim      : Biological Capital (BC) scores track peer-reviewed
             ecosystem valuations.
Falsified  : by systematic divergence from peer-reviewed ecosystem
             valuations.
Window     : 12-month rolling
Layer      : L6.1 (BC Index)
Action     : re-fit BC formula (currently (D·H·R)^(1/3); spec mandates
             4-factor); audit H/R component data sources
```

### F10 — XSL early warning

```
Claim      : Cross-Species Liquidity (XSL) decline precedes species
             declines by > 30 days at > 80% rate.
Falsified  : if species declines are not preceded by XSL signal
             decline by > 30 days at > 80% rate.
Window     : Per event
Layer      : L9.1 (XSL)
Action     : re-tune TV·FS·RR/(1+TP) components; re-evaluate TP
             (toxicity premium) normalization constant
```

### F11 — SBA accuracy

```
Claim      : Sovereign Behavioral Accuracy (SBA) scores track IMF/
             World Bank composite behavioral indicators.
Falsified  : by systematic divergence from IMF/World Bank composites.
Window     : 24-month rolling
Layer      : L8.1 (Sovereign Behavioral Accuracy)
Action     : re-fit SBA 5 components (0.30/0.25/0.20/0.15/0.10 weights);
             audit IMF DataMapper / World Bank API feeds
```

### F12 — ANIMA calibration

```
Claim      : ANIMA probability distributions are calibrated within
             95% ± 2% coverage.
Falsified  : if probability distributions consistently miscalibrated.
Window     : 90-day rolling
Layer      : L3.3 (ANIMA Score — Conformal Predictor)
Action     : re-fit conformal predictor; re-evaluate CI_95 calibration
             against realized outcomes
```

### F13 — Entity Resolution

```
Claim      : Known unified actors are clustered at > 95% rate.
Falsified  : if known unified actors not clustered at > 95% rate.
Window     : Quarterly audit
Layer      : L0.2 (BEO Entity Resolution)
Action     : re-evaluate BEO clustering thresholds; re-fit
             w_CF/w_ST/w_SC/w_BP weights; audit unified-actor labels
```

### F14 — Observer Effect corrected

```
Claim      : Observer Effect correction prevents circular reinforcement
             in TRION's own signals (M_adj < M_base when OE_factor > 0).
Falsified  : if M_adj not lower than M_base for high-OE assets.
Window     : Continuous
Layer      : L3.2 (Observer Effect)
Action     : increase κ (dampening strength); re-evaluate observer
             effect model; emit CONSENSUS_ADAPTATION signal
```

### F15 — Silence is informative

```
Claim      : Gap field in SILENCE signals is correlated with next-
             signal time (Silence carries predictive information).
Falsified  : if gap field in Silence Signals uncorrelated with next-
             signal time.
Window     : 6-month rolling
Layer      : L5 (TRION Master — SILENCE gap)
Action     : re-tune SILENCE gap estimator; re-evaluate limiting_plane
             attribution; quarantine SILENCE signal emission
```

---

## Registry Summary

```
ID  | CLAIM                          | WINDOW                | LAYER
----|--------------------------------|-----------------------|--------
F1  | Manipulation resistance        | Any time              | L1.2
F2  | Consensus safety               | Any time              | L4.1
F3  | ANIMA improves signals         | 90-day rolling        | L3.3
F4  | Quantum resistance             | Any time              | L4.3-4.6
F5  | Signal convergence             | 12-month rolling      | L2.5
F6  | Genesis Inference valid        | 90-day, 100+ events   | L2.3
F7  | IM Protocol operational        | Continuous            | L3.7
F8  | Diversity enforced (HHI 2500) | Continuous            | L4.8
F9  | BC scores valid                | 12-month rolling      | L6.1
F10 | XSL early warning              | Per event             | L9.1
F11 | SBA accuracy                   | 24-month rolling      | L8.1
F12 | ANIMA calibration              | 90-day rolling        | L3.3
F13 | Entity Resolution              | Quarterly audit       | L0.2
F14 | Observer Effect corrected      | Continuous            | L3.2
F15 | Silence is informative         | 6-month rolling       | L5
```

---

## Falsification Protocol

```
1. Detection   : any node may submit a falsification evidence transaction.
2. Verification: the evidence is verified by 2/3+ diversity-weighted
                 validators (L4.1).
3. Confirmation: if verified, the falsified condition is marked violated and:
   a. the relevant layer is quarantined (L5.3 tier T3),
   b. a SYSTEMIC_RISK signal is broadcast on all 20 channels,
   c. the prescribed Action (per the condition) is executed,
   d. a protocol upgrade is scheduled via L6.2 lunar governance cadence.
4. Recovery    : the condition is re-monitored; if it holds for 365 epochs
                 post-fix, the violation is closed.
```

## Invariants

- Exactly 15 falsifiability conditions are defined; new conditions require
  a fork.
- All conditions MUST be monitorable by any node without privileged access.
- A protocol that fails to action a confirmed falsification is itself
  falsified at the governance layer (SOVEREIGN_BEHAVIORAL signal,
  severity = breach).
- The `part_13_section` field on each API condition (returned by
  `GET /api/v1/falsifiability`) cites the canonical "Part 13 F<n> — <claim>"
  reference; this markdown registry must always agree with the API.

---

## Cross-References

- Whitepaper Part 13 — Complete Falsifiability Table (canonical source).
- `core/governance/falsifiability_registry.py` — live registry implementation
  (served by `/api/v1/falsifiability` and `/api/v1/governance/falsifiability`).
- `spec/open_research_questions.md` — long-horizon CONJECTUREs (BRT-gas
  correlation, REGULATORY_BEHAVIORAL 24-month) retired from the F1–F15
  table under FIX-E.
- `docs/audit/CANONICAL_SPEC_MATRIX.md` (K13) — historical record of the
  retired WP1 and WP2 §20 F1–F15 mappings.
- `signal_types.md` — SYSTEMIC_RISK, CONSENSUS_ADAPTATION,
  SOVEREIGN_BEHAVIORAL signals broadcast on falsification.
