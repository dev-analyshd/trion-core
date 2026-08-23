# TRION Protocol -- L1 Physical Layer Specification

> **Reference:** TRION Whitepaper, Section 3 (Physical Richness and Manipulation Fingerprinting).
> L1 grounds every behavioral observation in measurable physical phenomena.

## Scope

L1 transforms raw on-chain and off-chain physical observations into the quantitative
inputs consumed by L0.1 (Behavioral Hash) and L5 (TRION Master).

---

## L1.1 Physical Richness

Every behavioral observation is decomposed into **nine Shannon-entropy features**
`f1..f9`, computed over a sliding observation window of length `W` (default `W = 256`).

### Feature Definitions

```
f1 = H(price_ticks)                  -- entropy of tick stream
f2 = H(volume_profile)               -- entropy of volume distribution
f3 = H(order_book_imbalance)         -- entropy of bid/ask asymmetry
f4 = H(gas_price_distribution)       -- entropy of fee market
f5 = H(inter-arrival_times)          -- entropy of event timing
f6 = H(address_activity_clusters)    -- entropy of actor concentration
f7 = H(oracle_updates)               -- entropy of price-feed updates
f8 = H(governance_proposals)         -- entropy of proposal submission
f9 = H(cross_chain_transfers)        -- entropy of bridge flows
```

### Combined Richness Vector

```
PR(t) = [ f1, f2, f3, f4, f5, f6, f7, f8, f9 ]   (each in [0, 1])
```

Each `f_i` is normalized:

```
f_i = H(raw_i) / log2(|alphabet_i|)
```

### Richness Aggregate

```
PR_scalar = (1/9) * sum_{i=1..9} f_i
```

### Invariants

- `0 <= f_i <= 1` for all `i`.
- A window with `PR_scalar < 0.05` triggers a SILENCE signal (see signal_types.md).
- A window with any single `f_i > 0.95` AND a correlated jump in another feature
  triggers a MANIPULATION_ALERT candidate (see L1.2).

---

## L1.2 Manipulation Fingerprint

Seven canonical manipulation archetypes. Each is a pattern recognizer over `PR(t)`
and an associated behavioral residue vector.

### Type Registry

```
ID  | TYPE                 | PRIMARY FEATURE COMBO          | THRESHOLD
----|----------------------|--------------------------------|---------
M1  | WASH_TRADING         | f1 high, f3 low, f6 low        | r_M1 > 0.80
M2  | COORDINATED_PUMP     | f1 high, f2 high, f5 low       | r_M2 > 0.85
M3  | ORACLE_ATTACK        | f7 high, f1 lagging            | r_M3 > 0.70
M4  | SYBIL_LIQUIDITY      | f6 high, f3 mid, f9 low        | r_M4 > 0.75
M5  | GOVERNANCE_CAPTURE   | f8 high, f6 low                | r_M5 > 0.72
M6  | MEV_EXTRACTION       | f4 high, f5 low, f3 high       | r_M6 > 0.78
M7  | FAKE_VOLUME          | f2 high, f1 low                | r_M7 > 0.80
```

### Fingerprint Score

```
r_Mk = w_a * normalized_feature_match + w_b * temporal_signature_match + w_c * residue_vector_match
```

With:

```
w_a + w_b + w_c = 1
w_a = 0.5,  w_b = 0.3,  w_c = 0.2   (defaults; tunable per asset type)
```

### Emission Rule

```
if exists k : r_Mk > threshold_Mk:
    emit MANIPULATION_ALERT {
        type: Mk,
        score: r_Mk,
        features: PR(t),
        window: [t - W, t],
        targets: affected_BEOs
    }
```

### Invariants

- A MANIPULATION_ALERT MUST NOT be downgraded to SILENCE.
- Two alerts of the same type within `2*W` are merged.
- The residue vector is preserved in the Akashic index (see L2).

---

## L1.3 Temporal Coherence

The physical layer must distinguish causally-linked events from coincidental noise.

### Coherence Function

```
TC(t1, t2) = exp( -|t1 - t2| / tau_coherence ) * cross_corr( PR(t1), PR(t2) )
```

### Default Parameter

```
tau_coherence = 6 * mean_inter_arrival_time
```

### Coherence Levels

```
TC > 0.85   ->  causal link (used in BEO resolution, see L0.2)
0.50 < TC <= 0.85  ->  correlated (observation retained)
0.15 < TC <= 0.50  ->  weak (retained but flagged)
TC <= 0.15  ->  noise (discarded)
```

### Invariants

- Causal links form a DAG; cycles are forbidden and trigger a TRAJECTORY anomaly.
- Temporal coherence MUST be computed before any L1.2 fingerprinting.

---

## L1.4 Transduction Integrity

The conversion of physical events into behavioral observations must preserve entropy.

### Integrity Score

```
TI = 1 - | H(physical_stream) - H(behavioral_stream) | / H(physical_stream)
```

### Integrity Tiers

```
TI > 0.98  ->  faithful (no compensation required)
0.90 < TI <= 0.98  ->  drift (compensation factor applied to f_i)
0.75 < TI <= 0.90  ->  degraded (PHASE_TRANSITION signal emitted)
TI <= 0.75  ->  corrupt (transducer replaced; SYSTEMIC_RISK emitted)
```

### Compensation

```
f_i_corrected = f_i * TI    (when 0.90 <= TI < 0.98)
```

### Invariants

- TI is recomputed every `W` observations.
- A drop of `Delta_TI > 0.10` within one window triggers a SYSTEMIC_RISK signal
  regardless of the absolute tier.
- Transducers with `TI <= 0.75` for three consecutive windows are quarantined.

---

## Cross-References

- L0.1 -- Behavioral Hash consumes the corrected feature vector.
- L2.7 -- Trajectory anomalies are derived from L1.3 coherence violations.
- L5.2 -- Physical plane contribution `Phi` to coherence uses `PR_scalar`.
- `signal_types.md` -- MANIPULATION_ALERT, PHASE_TRANSITION, SYSTEMIC_RISK,
  LIQUIDITY_HEALTH, MEV_EXPOSURE are emitted from L1.
