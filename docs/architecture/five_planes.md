# TRION Protocol — Five Behavioral Planes

## Overview

TRION's master coherence score C(t) integrates five planes of behavioral intelligence.

```
C(t) = α·Φ_adj(t) + β·M_adj(t) + γ·Σ(t) + δ·K(t) + ε·A(t)
```

Where:
- **Φ** = Physical Plane (on-chain behavioral entropy)
- **M** = Mental Plane (model prediction confidence)
- **Σ** = Spiritual Plane (validator consensus)
- **K** = Conscious Plane (human annotation)
- **A** = ANIMA (cross-lingual sentiment)

## Dynamic Threshold

```
Θ(t) = Θ_min + (Θ_max - Θ_min) × V(t)
Θ_min = 0.55,  Θ_max = 0.92
```

As volatility rises, the threshold rises — making it **harder** to emit a
positive signal in volatile markets. This is the oracle's built-in conservatism.

## Physical Plane — Φ(t)

Nine Shannon entropy features:

| Feature | Description | Formula |
|---------|-------------|---------|
| f1 | Volume entropy | H(tx value distribution) |
| f2 | Counterparty diversity | H(unique counterparties) |
| f3 | Temporal spacing | H(inter-tx time gaps) |
| f4 | Smart contract entropy | H(contract interactions) |
| f5 | Value flow directionality | H(in vs out flows) |
| f6 | Wallet architecture | H(EOA vs contract) |
| f7 | Cross-protocol | H(protocol categories) |
| f8 | Gas pattern | H(gas usage buckets) |
| f9 | MEV interaction | H(5 MEV categories) |

```
Φ(t) = Σ_i w_i · f_i(t),   Σ w_i = 1
```

**Manipulation filter**: `Φ_adj = Φ_raw × (1 - MF_score)`

## Mental Plane — M(t)

```
M(t) = 1 - (PI_t / PI_baseline)
M_adj(t) = M_base(t) × (1 - OE_factor(t))
```

- PI_t = current prediction interval width (95% confidence)
- OE_factor = observer effect: correlation between signal publication
  and subsequent behavioral change

## Spiritual Plane — Σ(t)

Diversity-weighted BFT consensus:

```
Σ(t) = Σ_j [s_j · d_j · 1(|v_j - M̄| ≤ δ(t))] / Σ_j [s_j · d_j]
d_j = 1 - corr(M_j, M̄)    [diversity weight]
δ(t) = δ_base × (1 + V(t)) [dynamic window]
```

**Byzantine defeat property**: correlated Byzantine validators have
d_j ≈ 0, suppressing their influence automatically.

## Conscious Plane — K(t)

Human annotation network (mainnet):
- 5 annotators per review, 3-of-5 majority
- Commit-reveal voting (prevents herding)
- Pseudonymous identities, 12-month terms
- Cultural context weighting

## ANIMA Plane — A(t)

```
A(t) = PCR(t) × HA(t) × CA(t)
```

- PCR = Positive Cultural Reception (cross-lingual NLP)
- HA  = Historical Alignment (vs 90d baseline)
- CA  = Cross-lingual Agreement (consensus across languages)
- Activation: D(t) ≥ 10,000 behavioral events

## Asset Weight Profiles

| Profile | α(Φ) | β(M) | γ(Σ) | δ(K) | ε(A) |
|---------|------|------|------|------|------|
| DEFAULT_BALANCED | 0.25 | 0.30 | 0.25 | 0.10 | 0.10 |
| NEW_TOKEN (<90d) | 0.40 | 0.15 | 0.30 | 0.10 | 0.05 |
| MATURE_PROTOCOL  | 0.20 | 0.30 | 0.20 | 0.15 | 0.15 |
| STABLECOIN       | 0.25 | 0.35 | 0.25 | 0.05 | 0.10 |
| GOVERNANCE_TOKEN | 0.15 | 0.20 | 0.25 | 0.25 | 0.15 |
| BRIDGE_ASSET     | 0.30 | 0.25 | 0.30 | 0.05 | 0.10 |
| WRAPPED_ASSET    | 0.20 | 0.25 | 0.35 | 0.05 | 0.15 |
