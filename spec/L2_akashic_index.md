# TRION Protocol -- L2 Akashic Index Specification

> **Reference:** TRION Whitepaper, Section 4 (Akashic Memory Layer).
> L2 is the persistent memory of all behavioral entities, dormant or active.

## Scope

L2 maintains a time-decaying index of every BEO ever observed by the chain. It
enables genesis detection, resurrection inference, fork resolution, and trajectory
anomaly detection.

---

## L2.1 Akashic Depth

Each BEO has an Akashic Depth that quantifies how deeply it is buried in memory.

### Formula

```
D(t) = integral from t0 to t of exp( -lambda * (t - tau) ) * activity(tau) dtau
```

Where:

- `t0` = first observation time of the BEO.
- `activity(tau)` = observed activity intensity at time `tau` in `[0, 1]`.
- `lambda` = decay constant (default `0.01` per epoch).

### Depth Tiers

```
D(t) > 10    ->  active       (routinely present)
1 < D(t) <= 10  ->  shallow   (recently dormant)
0.1 < D(t) <= 1  ->  deep     (long dormant)
D(t) <= 0.1  ->  fossilized   (effectively forgotten)
```

### Invariants

- `D(t)` is monotonically non-increasing when `activity = 0`.
- Fossilized BEOs are eligible for pruning after `t - t_pruned > 90 * lambda^-1`.

---

## L2.2 Archetype Similarity

Each BEO is matched against canonical archetypes stored in the index.

### Similarity Score

```
Sim(BEO, Archetype_j) = cos( vec(BEO), vec(Archetype_j) )
                      = (vec(BEO) . vec(Archetype_j))
                        / ( ||vec(BEO)|| * ||vec(Archetype_j)|| )
```

Where `vec()` is the 9-dimensional Physical Richness vector from L1.1.

### Archetype Assignment

```
assigned_archetype := argmax_j Sim(BEO, Archetype_j)
if max Sim < tau_arch (default 0.55):
    declare new archetype
```

### Invariants

- Archetypes are append-only; existing archetypes cannot be deleted.
- A new archetype triggers a GENESIS signal (see signal_types.md).

---

## L2.3 Genesis Confidence Decay

A newly detected entity is provisionally labeled GENESIS. Confidence that this is
truly a novel entity decays with time, allowing resurrection claims to override it.

### Formula

```
GC(t) = GC_0 * exp( -mu * (t - t_genesis) )
```

### Default Parameters

```
GC_0 = 1.00
mu   = 0.005  per epoch
```

### Override Rule

```
if exists BEO_dormant : D(BEO_dormant) > 0.1 AND Sim(BEO_dormant, BEO_new) > 0.85:
    GC(BEO_new) := 0
    merge(BEO_dormant, BEO_new)
    emit RESURRECTION signal
```

### Invariants

- Genesis confidence is bounded in `[0, 1]`.
- A BEO with `GC < 0.05` for `>= 30 epochs` is considered canonically established.

---

## L2.4 Resurrection Inference

Five dormancy types determine how a dormant BEO may be revived.

### Dormancy Type Registry

```
ID  | TYPE              | MIN DORMANCY | REVIVAL SIGNATURE
----|-------------------|--------------|---------------------------------
R1  | HIBERNATION       | 7 epochs     | identical PR vector, delta_t small
R2  | LATENT_DEVELOPMENT| 30 epochs    | evolved PR vector (drift < 0.2)
R3  | OBLIVION          | 90 epochs    | partial PR match (>0.6), new archetype
R4  | TRANSMIGRATION    | 365 epochs   | different address, same behavioral code
R5  | ANCESTRAL_RETURN  | > 3 years    | archetype match only, no address link
```

### Resurrection Score

```
RR(Rk) = w_sim * Sim(BEO_new, BEO_dormant)
       + w_dormancy * dormancy_match(Rk, t_now - t_last)
       + w_lineage * lineage_overlap(BEO_new, BEO_dormant)
```

With defaults:

```
w_sim = 0.50,  w_dormancy = 0.30,  w_lineage = 0.20
```

### Revival Decision

```
if exists k : RR(Rk) > tau_revive (default 0.70):
    revive(BEO_dormant) -> canonical merge
    emit RESURRECTION { type: Rk, score: RR(Rk), dormancy: t_now - t_last }
```

### Invariants

- Transmigration (R4) requires an explicit BIRP identity proof (see novel_primitives.md P6).
- Ancestral return (R5) cannot trigger a merge; it can only emit an advisory signal.

---

## L2.5 Convergence Theorem

The Akashic index is guaranteed to converge to a stable archetype set under bounded input.

### Theorem Statement

```
Let A_n be the archetype set at epoch n.
If sum_{n} H(input_n) < infinity  AND  activity is bounded in [0, 1],
then exists N : for all n > N, |A_n| - |A_{n+1}| < epsilon.
```

### Convergence Criterion

```
C_conv = (1 / (1 + |A_n| - |A_{n-1}|)) * exp( -alpha * variance(input_entropy) )
```

### Default

```
alpha = 0.1
```

### Invariants

- A chain with `C_conv > 0.95` for `>= 14 epochs` is in steady state.
- A divergence (`|A_n| - |A_{n-1}| > 5` in one epoch) emits a PHASE_TRANSITION signal.

---

## L2.6 Fork Resolution

When two observation streams diverge, the Akashic index is the canonical arbiter.

### Resolution Rule

```
score(fork_X) = sum_{BEO in fork_X} D(BEO) * Sim(BEO, A_canonical)
winner := argmax_X score(fork_X)
```

### Tie-Breaker

```
if |score(X) - score(Y)| < tau_tie (default 0.05):
    winner := fork with deeper cumulative D(BEO) at time of fork
```

### Invariants

- A fork with `score < 0.10` is rejected outright and labeled orphaned.
- A successful fork resolution emits a FORK_DIVERGENCE signal.

---

## L2.7 Trajectory Anomaly

Trajectory anomalies detect BEOs whose behavior departs from their archetype.

### Anomaly Score

```
TA(t) = || PR(t) - PR_expected(archetype, t) ||_2
```

Where `PR_expected` is the running centroid of the archetype.

### Anomaly Tiers

```
TA > 2.5   ->  critical (TRAJECTORY signal emitted, BEO quarantined)
1.5 < TA <= 2.5  ->  elevated (TRAJECTORY signal emitted, monitoring)
0.7 < TA <= 1.5  ->  drift (logged only)
TA <= 0.7  ->  nominal
```

### Invariants

- A critical anomaly on a sovereign entity triggers an immediate L4 slashing review.
- Three consecutive critical anomalies on the same BEO trigger an archetype re-evaluation.

---

## Cross-References

- L0.2 -- BEO resolution populates the Akashic index.
- L1.1 -- Physical Richness vectors are stored per BEO.
- L3 -- Mental layer reads Akashic depth to compute M(t).
- `signal_types.md` -- GENESIS, RESURRECTION, FORK_DIVERGENCE, TRAJECTORY,
  NEGATIVE_SPACE, PHASE_TRANSITION are emitted from L2.
