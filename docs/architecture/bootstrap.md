# TRION Protocol — Bootstrap Phase Architecture

## Honest Disclosure

TRION operates transparently about its current bootstrap phase. Three of the five
behavioral planes are in bootstrap mode during testnet deployment:

| Plane    | Bootstrap Value | Activation Trigger |
|----------|-----------------|--------------------|
| Σ (Spiritual) | 0.25       | Full validator network at mainnet |
| K (Conscious) | 0.10       | Human annotation onboarding at mainnet |
| A (ANIMA)     | 0.10       | D(t) ≥ 10,000 Akashic depth entries |

The Physical plane (Φ) and Mental plane (M) are **fully live** from block 1.

## What "Bootstrap" Means

- The bootstrap values are **not hardcoded** — they are the baseline priors
  in the absence of real data.
- The system **honestly reports** bootstrap status in every signal via the
  `bootstrap_phase` field.
- As the network grows, bootstrap values are replaced with real computed values.

## Activation Timeline

### ANIMA (A)
- **Activation condition**: D_asset ≥ 10,000 behavioral events
- **Current status**: ~1.2M vectors indexed, ANIMA activating per-entity
- **Formula**: `A(t) = PCR(t) × HA(t) × CA(t)` once D ≥ 10,000

### Spiritual (Σ)
- **Activation condition**: Mainnet validator network deployed
- **Current status**: Bootstrap (0.25 = neutral uncertainty baseline)
- **Architecture**: Fully implemented per whitepaper (diversity-weighted BFT)
- **Formula**: `Σ = Σ_j [s_j · d_j · 1(|v_j - M̄| ≤ δ(t))] / Σ_j [s_j · d_j]`

### Conscious (K)
- **Activation condition**: Human annotation network onboarding
- **Current status**: Bootstrap (0.10 = low-uncertainty prior)
- **Architecture**: Commit-reveal voting, pseudonymous annotators, 12-month terms
- **Formula**: `K(t) = weighted_k × temporal_consistency`

## Why Bootstrap Values Are Set This Way

- **Σ = 0.25**: Reflects genuine validator uncertainty. Setting it higher
  would be dishonest.
- **K = 0.10**: Low prior reflecting absence of human annotation data.
- **A = 0.10**: Conservative — ANIMA only activates when there is sufficient
  behavioral history to be meaningful.

## What Is Fully Live Now

- **Φ(t)**: All 9 Shannon entropy features computed from real on-chain data
  (Arbitrum, Ethereum, Solana, Base, BNB, StarkNet, Near, TON, Polkadot)
- **M(t)**: Prediction interval width scoring (requires prediction data)
- **D(t)**: 1.26M+ behavioral events indexed in FAISS, growing every block
- **MF detector**: All 7 manipulation patterns active
- **NL engine**: Natural Liquidity scoring from on-chain pool data
- **BTCP Score**: Full routing score computation
- **BIRP delivery**: Live relayer broadcasting to 6 testnets
- **GK evolution**: Per-entity genomic key evolution every block
- **CRISPR defense**: 4 historical attack signatures seeded

## Falsifiability

TRION makes falsifiable predictions:

1. Entities with Φ < 0.30 will demonstrate wash trading within 90 days
2. NL < 0.30 pools will suffer slippage > 10% on large swaps
3. Σ SILENCE during governance votes predicts reversal within 30 days
4. MF > 0.70 precedes exploits by ≤ 3 blocks in 80% of cases

These predictions are logged and publicly verifiable.
