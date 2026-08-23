# TRION Protocol -- L5 TRION Master Layer Specification

> **Reference:** TRION Whitepaper, Section 7 (TRION Master: Dynamic Thresholds and
> Five-Plane Coherence). L5 is the apex consensus controller.

## Scope

L5 fuses the physical, mental, akashic, knowledge, and anima planes into a single
coherence score, compares it against a dynamic threshold, and emits the Master
Equation value that drives consensus weight.

---

## L5.1 Dynamic Threshold

The consensus threshold is not static; it adapts to system volatility.

### Formula

```
Theta(t) = Theta_min + (Theta_max - Theta_min) * V(t)
```

Where:

- `V(t)` is volatility in `[0, 1]`, computed from L1.1 feature variance.
- `Theta_min = 0.55` (permissive floor).
- `Theta_max = 0.90` (strict ceiling).

### Volatility Computation

```
V(t) = clip( (1/9) * sum_{i=1..9} sigma(f_i) / sigma_max_i, 0, 1 )
```

Where `sigma(f_i)` is the rolling standard deviation of feature `i` over the last
`W = 256` observations.

### Invariants

- `Theta(t)` is monotonically increasing in `V(t)`.
- `Theta_min <= Theta(t) <= Theta_max` always.
- A swing `|Theta(t) - Theta(t-1)| > 0.10` emits a CONSENSUS_ADAPTATION signal.

---

## L5.2 Five-Plane Coherence

The Master Coherence score fuses five orthogonal planes.

### Formula

```
C(t) = alpha * Phi + beta * M + gamma * Sigma + delta * K + epsilon * A
```

Where:

- `Phi` = physical plane (from L1.1 PR_scalar).
- `M` = mental plane (from L3.1 M(t)).
- `Sigma` = akashic plane (from L2.5 convergence `C_conv`).
- `K` = knowledge plane (from cross-chain coherence, see L9).
- `A` = anima plane (from L3.3 ANIMA score `A(t)`).

### Weight Constraints

```
alpha + beta + gamma + delta + epsilon = 1
all weights non-negative
```

### Six Asset-Type Profiles

Each asset class uses a distinct weight profile.

```
PROFILE             | alpha | beta | gamma | delta | epsilon | USE CASE
--------------------|-------|------|-------|-------|---------|---------------------------
P1 Currency         | 0.30  | 0.20 | 0.10  | 0.30  | 0.10    | stablecoins, payments
P2 Commodity        | 0.35  | 0.15 | 0.20  | 0.20  | 0.10    | tokenized resources
P3 Security         | 0.20  | 0.30 | 0.10  | 0.20  | 0.20    | regulated tokens
P4 Utility          | 0.25  | 0.20 | 0.15  | 0.25  | 0.15    | gas tokens, network access
P5 Sovereign        | 0.15  | 0.25 | 0.15  | 0.15  | 0.30    | CBDCs, sovereign behavioral
P6 Biological Asset | 0.20  | 0.20 | 0.20  | 0.20  | 0.20    | L6 biological capital tokens
```

### Coherence Tiers

```
C(t) >= 0.90  ->  harmonic (consensus weight 1.0)
0.75 <= C(t) < 0.90  ->  coherent (consensus weight 0.85)
0.60 <= C(t) < 0.75  ->  fragmented (consensus weight 0.60)
0.45 <= C(t) < 0.60  ->  degraded (consensus weight 0.35)
C(t) < 0.45  ->  incoherent (consensus weight 0; PHASE_TRANSITION emitted)
```

### Invariants

- The profile is chosen at asset registration and cannot change without a fork.
- The anima weight `epsilon` is highest for Sovereign assets (P5).

---

## L5.3 Consensus Degradation Tiers

When coherence drops, consensus degrades gracefully through four tiers.

### Tier Registry

```
TIER | CONDITION                | EFFECT
-----|--------------------------|--------------------------------------------
T0   | C(t) >= Theta(t)         | full consensus, weight = 1.0
T1   | 0.75*Theta <= C < Theta  | elevated quorum (Q_required + 0.05)
T2   | 0.50*Theta <= C < 0.75*Theta | reduced throughput, weight = 0.50
T3   | C < 0.50*Theta           | quarantine: only BOOTSTRAP and SOVEREIGN signals
```

### Tier Transitions

```
T0 -> T1 : emit CONSENSUS_ADAPTATION
T1 -> T2 : emit PHASE_TRANSITION
T2 -> T3 : emit SYSTEMIC_RISK, trigger L3.7 Intelligence Maintenance
T3 -> T0 : requires 3 consecutive epochs at C >= Theta (manual review)
```

### Invariants

- Tier transitions are monotonic during a single degradation event.
- Recovery requires staged ascent (T3 -> T2 -> T1 -> T0); skipping is forbidden.

---

## L5.4 Master Equation

The TRION Master Equation defines the canonical survival value of the chain.

### Formula

```
T(t) = [ C(t) >= Theta(t) ] * S(t) * exp( M_moat(t) * t )
```

Where:

- `[ C(t) >= Theta(t) ]` is the indicator function (1 if coherence meets threshold, 0 otherwise).
- `S(t)` is the Spiritual Security integrity (mean LSI across validators, see L4.3).
- `M_moat(t)` is the behavioral moat: cumulative distinct archetypes indexed (from L2.5).

### Interpretation

```
T(t) = 0             : chain is halted (coherence below threshold)
T(t) > 0             : chain is alive; value grows exponentially with the moat
T(t) growth rate     : bounded by M_moat(t) <= M_moat_max = 0.02 per epoch
```

### Master Equation Tiers

```
T(t) = 0                          ->  terminal (BIRP recovery, see novel_primitives.md P6)
0 < T(t) < T_min = 1.0            ->  critical (L3.7 maintenance invoked)
T_min <= T(t) < T_stable = 10.0   ->  vulnerable (heightened monitoring)
T(t) >= T_stable                  ->  sovereign (eligible for L8 assessment)
```

### Invariants

- `T(t)` is the primary input to L0.6 evolutionary fitness.
- A chain with `T(t) = 0` for `>= 7 epochs` is eligible for fork dissolution.
- The exponential term is bounded; `M_moat(t)` cannot exceed `M_moat_max`.

---

## Cross-References

- L1.1 -- `Phi` plane input (PR_scalar).
- L2.5 -- `Sigma` plane input (convergence score).
- L3.1, L3.3 -- `M` and `A` plane inputs.
- L4 -- `S(t)` from mean LSI.
- L9 -- `K` plane input (cross-chain coherence).
- `signal_types.md` -- CONSENSUS_ADAPTATION, PHASE_TRANSITION, SYSTEMIC_RISK.
