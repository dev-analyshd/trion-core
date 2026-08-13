# TRION Protocol -- L6 Biological Capital Layer Specification

> **Reference:** TRION Whitepaper, Section 8 (Biological Capital and Rhythms).
> L6 quantifies living-system capital and aligns consensus with biological rhythms.

## Scope

L6 measures the biological capital carried by the chain's ecosystem (validators,
liquidity providers, sovereign actors) and synchronizes behavioral observation
windows to natural rhythms.

---

## L6.1 Biological Capital Index

The Biological Capital Index (BC) is a multiplicative composition of four sub-indices.

### Formula

```
BC = Flow * Resilience * Uniqueness * Interdependence
```

### Sub-Index Definitions

```
Flow          = (1/N) * sum_{i=1..N} normalized_activity(actor_i)
Resilience    = 1 - (n_failed_actors / N)
Uniqueness    = 1 - HHI(archetype_distribution)            -- from L2.2
Interdependence = (2 / (N * (N - 1))) * sum_{i != j} R(i, j)  -- L0.3 resonance
```

Where:

- `N` = number of active biological actors (validators + LPs + sovereigns).
- `normalized_activity` is the actor's L1.1 PR_scalar, bounded in `[0, 1]`.
- `n_failed_actors` = actors with `LSI < 0.875` (L4.3) or `F < 0.15` (L0.6).

### BC Tiers

```
BC > 0.75   ->  thriving     (BIOLOGICAL_CAPITAL signal: positive)
0.50 < BC <= 0.75  ->  healthy
0.30 < BC <= 0.50  ->  stressed (BIOLOGICAL_CAPITAL signal: advisory)
0.15 < BC <= 0.30  ->  critical (consensus weight reduced by 0.20)
BC <= 0.15  ->  collapsing (L3.7 Intelligence Maintenance invoked)
```

### Invariants

- `BC` is bounded in `[0, 1]`.
- A drop `BC(t) - BC(t-1) > 0.20` within one epoch triggers a SYSTEMIC_RISK signal.
- BC feeds the L5.2 P6 (Biological Asset) profile.

---

## L6.2 Biological Rhythm Timer

Behavioral observations are gated by four rhythmic cycles.

### Cycle Registry

```
ID  | RHYTHM    | PERIOD       | EFFECT ON CONSENSUS
----|-----------|--------------|--------------------------------------------
R1  | Circadian | 24 hours     | observation window scaling
R2  | Ultradian | ~90 minutes  | micro-batch aggregation
R3  | Lunar     | ~29.5 days   | governance proposal cadence
R4  | Seasonal  | ~365.25 days | validator recombination + key rotation
```

### Phase Computation

For each rhythm `Rk` with period `T_k`:

```
phase_k(t) = ( (t - t0_k) mod T_k ) / T_k      (in [0, 1))
```

### Window Scaling (Circadian)

```
W_effective(t) = W_base * (1 + 0.20 * sin(2 * pi * phase_1(t)))
```

With `W_base = 256` (the L1 default window).

### Aggregation (Ultradian)

```
Every 90 minutes, the ultradian micro-batch is sealed:
  - all L0.1 Behavioral Hashes in the window are committed to L2.
  - L1.2 fingerprints are re-evaluated against the sealed batch.
```

### Governance Cadence (Lunar)

```
- Proposals may only be submitted at phase_3 in [0.40, 0.60] (full moon window).
- Voting runs for the following 0.25 of the cycle (~7 days).
- Implementation is gated to phase_3 in [0.85, 1.0) (waning crescent).
```

### Recombination (Seasonal)

```
At phase_4 crossing 0.0 (vernal epoch):
  - L4.3 G5 (Genetic Recombination) executes chain-wide.
  - L4.7 G1 (Genetic Key) rotation is enforced.
  - HHI (L4.8) is audited against the previous season.
```

### Rhythm Coherence

```
RC(t) = (1/4) * sum_{k=1..4} | sin(pi * phase_k(t)) |
```

### Invariants

- `RC(t) > 0.75` (peak alignment) doubles the diversity bonus in L4.1.
- A seasonal recombination failure emits a BOOTSTRAP signal.
- Lunar proposals outside the submission window are rejected.

---

## Cross-References

- L0.3 -- Resonance `R(i, j)` feeds Interdependence.
- L0.6 -- Fitness `F` determines `n_failed_actors`.
- L2.2 -- Archetype distribution feeds Uniqueness.
- L4.3 -- `LSI` determines actor failure.
- L4.7 -- Seasonal recombination triggers G1 rotation.
- L5.2 -- P6 Biological Asset profile consumes BC.
- `signal_types.md` -- BIOLOGICAL_CAPITAL, BOOTSTRAP, SYSTEMIC_RISK, GOVERNANCE_SIGNAL.
