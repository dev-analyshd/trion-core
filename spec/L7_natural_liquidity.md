# TRION Protocol -- L7 Natural Liquidity Layer Specification

> **Reference:** TRION Whitepaper, Section 9 (Natural Liquidity and Energy Participation).
> L7 distinguishes natural, organic liquidity from synthetic or manipulated flow.

## Scope

L7 scores liquidity on four natural-flow axes and quantifies the energy participation
of actors contributing to it. The output feeds the L5.2 P1 (Currency) profile and
the L9 cross-species liquidity.

---

## L7.1 Natural Liquidity Score

The Natural Liquidity (NL) score is a multiplicative composition of four sub-scores.

### Formula

```
NL = LD * LO * LC * LS
```

### Sub-Score Definitions

```
LD = Liquidity Diversity       = 1 - HHI(top_N_liquidity_providers)
LO = Liquidity Organicness    = organic_volume / total_volume
LC = Liquidity Continuity     = 1 - (gap_count / window_length)
LS = Liquidity Symmetry       = 1 - | bid_volume - ask_volume | / (bid_volume + ask_volume)
```

Where:

- `top_N_liquidity_providers` = top 20 providers by contribution.
- `organic_volume` = volume from sources with `C_source >= 0.55` (L3.4) AND
  not flagged by L1.2 manipulation fingerprints.
- `gap_count` = number of empty ticks in the window.
- `window_length` = total ticks in the observation window (default `W = 256`).

### NL Tiers

```
NL > 0.80    ->  natural       (LIQUIDITY_HEALTH signal: positive)
0.60 < NL <= 0.80  ->  healthy
0.40 < NL <= 0.60  ->  synthetic-leaning (LIQUIDITY_HEALTH signal: advisory)
0.20 < NL <= 0.40  ->  impaired (NL-weighted liquidity used for price discovery)
NL <= 0.20  ->  unnatural (price discovery suspended; SYSTEMIC_RISK emitted)
```

### Invariants

- `NL` is bounded in `[0, 1]`.
- Any single sub-score `< 0.10` triggers a LIQUIDITY_HEALTH advisory regardless of `NL`.
- A drop of `> 0.25` in one epoch triggers a SYSTEMIC_RISK signal.

---

## L7.2 Energy Participation Index

The Energy Participation (EP) index measures the active energy contributed by
ecosystem participants.

### Formula

```
EP = VC * PA * DC
```

### Sub-Score Definitions

```
VC = Validator Commitment     = (active_validators / total_registered_validators)
PA = Participation Activity   = mean L1.1 PR_scalar across active actors
DC = Diversity Contribution   = mean d_j (L4.1 diversity) across active validators
```

### EP Tiers

```
EP > 0.75    ->  energetic    (ENERGY_PARTICIPATION signal: positive)
0.55 < EP <= 0.75  ->  engaged
0.35 < EP <= 0.55  ->  passive (advisory ENERGY_PARTICIPATION signal)
0.15 < EP <= 0.35  ->  lethargic (consensus throughput reduced by 30%)
EP <= 0.15  ->  depleted (L3.7 Intelligence Maintenance invoked)
```

### Invariants

- `EP` is bounded in `[0, 1]`.
- `EP` is recomputed every ultradian cycle (~90 min, see L6.2).
- A drop in `VC` by `> 0.10` in one window emits a BOOTSTRAP signal
  (validator offboarding cascade risk).

---

## Composite Liquidity Health

The composite metric combines NL and EP for the L5.2 P1 profile.

```
LH_composite = sqrt( NL * EP )
```

### Tiers

```
LH_composite > 0.70   ->  robust
0.50 < LH <= 0.70     ->  adequate
0.30 < LH <= 0.50     ->  fragile
LH <= 0.30            ->  collapsed (price discovery halted)
```

### Invariants

- `LH_composite` is the primary input to the `Phi` plane for Currency assets (P1).
- A halt triggers a LIQUIDITY_HEALTH signal with severity `critical`.

---

## Cross-References

- L1.1 -- `PR_scalar` feeds `PA`.
- L1.2 -- Manipulation fingerprints filter `organic_volume`.
- L3.4 -- `C_source` filters organic providers.
- L4.1 -- Diversity `d_j` feeds `DC`.
- L5.2 -- P1 (Currency) profile uses `LH_composite`.
- L9 -- Cross-Species Liquidity `XSL` reads NL.
- `signal_types.md` -- LIQUIDITY_HEALTH, ENERGY_PARTICIPATION, SYSTEMIC_RISK, BOOTSTRAP.
