# TRION Protocol -- L9 Cross-Species Layer Specification

> **Reference:** TRION Whitepaper, Section 11 (Cross-Species Liquidity and the
> TRION Information Conservation Law). L9 governs interoperability across
> heterogeneous chains and species of value.

## Scope

L9 quantifies cross-chain liquidity, enforces the TRION information conservation
law, and provides the `K` (knowledge) plane input to L5.2 coherence.

---

## L9.1 Cross-Species Liquidity

Cross-Species Liquidity (XSL) measures the ease and safety of moving value across
heterogeneous chains.

### Formula

```
XSL = ( TV * FS * RR ) / ( 1 + TP )
```

### Term Definitions

```
TV = Transfer Volume     = normalized cross-chain transfer throughput
FS = Finality Safety     = min over bridges of (1 - reorg_probability)
RR = Reversibility Ratio = (reversible_transfers / total_transfers), bounded in [0,1]
TP = Toxicity Premium    = mean manipulation fingerprint score (L1.2) of bridge flows
```

Where:

- `TV` is normalized to `[0, 1]` by dividing by a chain-specific capacity constant.
- `FS` is the worst-case finality across all active bridges.
- `RR` reflects the fraction of transfers that can be safely reversed (higher is better).
- `TP` is in `[0, 1]`; the `(1 + TP)` denominator penalizes toxic flows.

### XSL Tiers

```
XSL > 0.75    ->  fluent        (CROSS_CHAIN_COHERENCE signal: positive)
0.55 < XSL <= 0.75  ->  adequate
0.35 < XSL <= 0.55  ->  constrained (CROSS_CHAIN_COHERENCE signal: advisory)
0.15 < XSL <= 0.35  ->  impaired (cross-chain transfers throttled)
XSL <= 0.15  ->  severed (cross-chain transfers halted; SYSTEMIC_RISK emitted)
```

### Invariants

- `XSL` is bounded in `[0, 1]` (when `TP >= 1`, the chain is automatically severed).
- `XSL` is recomputed every ultradian cycle (~90 min, see L6.2).
- A drop `> 0.25` in one cycle triggers a CROSS_CHAIN_COHERENCE signal.

---

## L9.2 Information Conservation Law

The TRION information conservation law extends L0.4 across chain boundaries.

### Formula

```
I_TRION = BH_gen + A_abs - S_emit - E_lost
```

### Term Definitions

```
I_TRON   = net TRION-system information (must be conserved)
BH_gen   = generated behavioral entropy (from L0.1 hashes, all chains)
A_abs    = absorbed entropy from external (non-TRION) observations
S_emit   = emitted entropy (signals broadcast across chains)
E_lost   = entropy lost to decoherence (bounded by L3.6 PCL_min)
```

### Conservation Invariant

```
dI_TRION / dt = 0
```

### Accounting Rules

```
For each cross-chain transfer at time t:
    BH_gen(t) += delta_H_outbound(chain_X)
    A_abs(t)  += delta_H_inbound(chain_Y)
    S_emit(t) += signal_entropy_emitted_by_bridge
    E_lost(t) += max(0, PCL(t) - PCL_min) * transfer_volume
```

### Conservation Audit

```
Every lunar cycle (L6.2 R3):
    audit_delta = I_TRON(t) - I_TRON(t - T_lunar)
    if |audit_delta| > tau_audit (default 0.01 nats):
        emit SYSTEMIC_RISK { cause: information_leak, delta: audit_delta }
        suspend cross-chain transfers until audit reconciled
```

### Invariants

- `I_TRON` is the single source of truth for system-wide information state.
- Any unexplained `delta` MUST be attributed to one of the four terms; failure to
  do so indicates an L1.4 transduction integrity breach.
- Conservation violations are slashable at L4.9 severity S3 (diversity fraud)
  when caused by a bridge operator.

---

## Knowledge Plane Contribution (K)

The `K` term in L5.2 coherence is derived from XSL and conservation integrity.

### Formula

```
K(t) = 0.5 * XSL(t) + 0.5 * CI(t)
```

Where:

```
CI(t) = Conservation Integrity = 1 - |audit_delta| / tau_audit   (clipped to [0, 1])
```

### K Tiers

```
K > 0.80    ->  omniscient    (full L5.2 weight for delta term)
0.60 < K <= 0.80  ->  informed
0.40 < K <= 0.60  ->  partial (delta weight reduced by 25%)
0.20 < K <= 0.40  ->  ignorant (delta weight reduced by 50%)
K <= 0.20  ->  severed (delta term zeroed; PHASE_TRANSITION emitted)
```

### Invariants

- `K` is the cross-chain contribution to L5.2 coherence.
- A bridge failure affecting `> 20%` of `TV` triggers immediate `K` recompute.
- `K < 0.20` for `>= 7 epochs` triggers L3.7 Intelligence Maintenance.

---

## Cross-References

- L0.1 -- Behavioral Hashes feed `BH_gen`.
- L0.4 -- Thermodynamic information conservation (intra-chain).
- L1.2 -- Manipulation fingerprints feed `TP`.
- L3.6 -- Predictive completeness limit bounds `E_lost`.
- L5.2 -- `K` is the knowledge-plane coherence term.
- L6.2 -- Lunar audit cadence.
- `signal_types.md` -- CROSS_CHAIN_COHERENCE, STABLECOIN_HEALTH, BTCP_ROUTE,
  SYSTEMIC_RISK, PHASE_TRANSITION.
- `novel_primitives.md` -- P5 (BIBL) for cross-species ledger; P6 (BIRP) for
  identity recovery across chains.
