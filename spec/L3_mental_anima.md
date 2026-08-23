# TRION Protocol -- L3 Mental / ANIMA Layer Specification

> **Reference:** TRION Whitepaper, Section 5 (Mental Confidence and the Observer Effect).
> L3 models the chain's internal mental state, observer effects, and ANIMA scoring.

## Scope

L3 reconciles subjective observer influence with objective behavioral evidence. It
maintains the ANIMA score, source credibility, and the predictive completeness limit.

---

## L3.1 Mental Confidence

The mental confidence `M(t)` is the chain's confidence in its own behavioral model.

### Formula

```
M(t) = (1 - eta * O(t)) * (1 - gamma * PCL(t)) * B(t)
```

Where:

- `O(t)` = observer effect magnitude (see L3.2).
- `PCL(t)` = predictive completeness limit (see L3.6).
- `B(t)` = baseline empirical confidence from L1/L2.
- `eta` = observer sensitivity (default `0.5`).
- `gamma` = predictive-debt sensitivity (default `0.3`).

### Confidence Tiers

```
M(t) > 0.85  ->  lucid      (full consensus participation)
0.65 < M(t) <= 0.85  ->  aware
0.45 < M(t) <= 0.65  ->  dreamlike (degraded consensus weight, see L5.3)
0.20 < M(t) <= 0.45  ->  hallucinated (consensus quarantine)
M(t) <= 0.20  ->  dissociated (chain halts pending L4 review)
```

### Invariants

- `M(t)` is bounded in `[0, 1]`.
- A drop `M(t) - M(t-1) > 0.30` within one epoch triggers a SYSTEMIC_RISK signal.

---

## L3.2 Observer Effect

The act of observation modifies the observed state.

### Formula

```
O(t) = (1 / N_obs) * sum_{i=1..N_obs} | PR_observed_i(t) - PR_counterfactual(t) |
```

Where:

- `N_obs` = number of distinct observers in the window.
- `PR_observed_i(t)` = richness vector as seen by observer `i`.
- `PR_counterfactual(t)` = richness vector that would exist without observers
  (estimated via L0.4 thermodynamic conservation).

### Observer Effect Bounds

```
O(t) < 0.05  ->  negligible
0.05 <= O(t) < 0.20  ->  measurable (compensation applied to B(t))
0.20 <= O(t) < 0.40  ->  significant (M(t) dampened)
O(t) >= 0.40  ->  dominant (CONSENSUS_ADAPTATION signal emitted)
```

### Invariants

- Observer effect is computed before any L0.5 signal selection.
- An observer whose individual contribution `> 0.15` is flagged as a Sovereign
  observer and routed to L8.

---

## L3.3 ANIMA Score

The ANIMA (Animistic Mental Assertion) score is the chain's overall mental integrity.

### Formula

```
A(t) = PCR(t) * HA(t) * CA(t)
```

Where:

- `PCR(t)` = Predictive Coherence Ratio = `correct_predictions / total_predictions`.
- `HA(t)` = Historical Accuracy = `consistent_resolutions / total_resolutions`.
- `CA(t)` = Contextual Awareness = `1 - observer_blind_spot_ratio`.

### ANIMA Tiers

```
A(t) > 0.90  ->  enlightened  (eligible for L8 Sovereign Behavioral Assessment)
0.70 < A(t) <= 0.90  ->  lucid
0.50 < A(t) <= 0.70  ->  aware
0.30 < A(t) <= 0.50  ->  dim
A(t) <= 0.30  ->  unconscious (chain enters Intelligence Maintenance, L3.7)
```

### Invariants

- `A(t)` is bounded in `[0, 1]`.
- A drop of `> 0.20` in one epoch triggers a SYSTEMIC_RISK signal.
- ANIMA is the multiplicative mental contribution to L5.2 coherence (`A` term).

---

## L3.4 Source Credibility Evolution

Credibility of each observation source evolves based on predictive track record.

### Update Rule

```
C_source(t+1) = (1 - rho) * C_source(t) + rho * correctness(t)
```

With:

```
rho = 0.05   (default learning rate)
correctness(t) = 1 if prediction matched outcome else 0
```

### Credibility Tiers

```
C_source >= 0.85  ->  canonical  (full weight in M(t))
0.55 <= C_source < 0.85  ->  credible  (weight 0.75)
0.30 <= C_source < 0.55  ->  contested (weight 0.40)
C_source < 0.30  ->  unreliable (weight 0, signal quarantined)
```

### Invariants

- Credibility is reset to `0.50` after `>= 90 epochs` of inactivity.
- A canonical source that errs `>= 3` times within `7` epochs is downgraded.

---

## L3.5 ANIMA Reflexivity Dampening

Because ANIMA observes itself, a dampening loop prevents runaway feedback.

### Dampened ANIMA

```
A_dampened(t) = A(t) - kappa * (A(t) - A(t-1))^2
```

With:

```
kappa = 2.0   (default dampening strength)
```

### Activation Rule

```
if |A(t) - A(t-1)| > tau_reflex (default 0.10):
    A_canonical := A_dampened(t)
    emit CONSENSUS_ADAPTATION signal
else:
    A_canonical := A(t)
```

### Invariants

- The dampened score is what is fed into L5.2.
- Dampening cannot drive `A` below `0`; clamped at `max(0, A_dampened)`.

---

## L3.6 Predictive Completeness Limit

There is a fundamental limit to how much of the future the chain can predict.

### Formula

```
PCL(t) = H(future) / (H(present) + H(future))
```

Where `H(future)` is the conditional entropy of the future given the present.

### Bound

```
PCL(t) >= PCL_min = 0.05   (information can never be fully predicted)
```

### Effect on M(t)

```
M(t) is bounded:  M(t) <= (1 - gamma * PCL_min) * B(t) = 0.985 * B(t)
```

### Invariants

- A claim of `PCL(t) < PCL_min` is impossible and indicates a measurement error;
  emit a SYSTEMIC_RISK signal.
- Persistent `PCL > 0.40` indicates the chain's model is underspecified.

---

## L3.7 Intelligence Maintenance Protocol

When `A(t) <= 0.30`, the chain enters a maintenance state.

### Protocol Steps

```
1. Halt new BEO admissions (Akashic index becomes read-only).
2. Suspend non-critical consensus rounds (see L5.3 tier 3).
3. Run source credibility re-evaluation (L3.4 over last 30 epochs).
4. Purge sources with C_source < 0.20.
5. Rebuild archetype centroids (L2.2).
6. Exit maintenance when A(t) > 0.45 for 3 consecutive epochs.
```

### Time Limits

```
max maintenance duration = 24 epochs
if exceeded: chain declares dissociated, BIRP recovery initiated
```

### Invariants

- During maintenance, only BOOTSTRAP and SOVEREIGN_BEHAVIORAL signals may be emitted.
- Maintenance entry and exit are both logged as SYSTEMIC_RISK signals.

---

## Cross-References

- L0.4 -- Thermodynamic conservation feeds the counterfactual `PR` in L3.2.
- L2 -- Akashic depth and archetype similarity feed baseline confidence `B(t)`.
- L5.2 -- `M(t)` is the mental plane contribution; `A(t)` is the anima contribution.
- `signal_types.md` -- CONSENSUS_ADAPTATION, SYSTEMIC_RISK, BOOTSTRAP tie into L3.7.
