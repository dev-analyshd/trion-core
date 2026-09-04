# TRION Protocol -- L4 Spiritual Security Layer Specification

> **Reference:** TRION Whitepaper, Section 6 (Spiritual Security: Diversity-Weighted BFT
> and Living Security). L4 replaces static cryptographic security with biologically
> living, diversity-weighted consensus.

## Scope

L4 defines the validator selection, dispute resolution, slashing, and biological
security mechanisms that protect the TRION consensus.

---

## L4.1 Diversity-Weighted BFT -- Validator Diversity

Each validator `j` carries a diversity weight inversely proportional to its correlation
with the consensus mean behavior.

### Diversity Score

```
d_j = 1 - corr( M_j, M_bar )
```

Where:

- `M_j` = behavioral signature vector of validator `j` (from L0.1 Behavioral Hash).
- `M_bar` = mean behavioral signature across all validators.

### Effective Voting Power

```
P_j = stake_j * (1 + delta * d_j)
```

With `delta = 0.5` by default (diversity bonus up to 50%).

### Invariants

- `sum_j P_j` is normalized so total power = 1.
- A validator with `d_j < 0.05` (highly correlated) loses the diversity bonus.

---

## L4.2 Diversity-Weighted BFT -- Quorum

The BFT quorum is computed on diversity-weighted power, not raw stake.

### Quorum Formula

```
Q_required = 2/3 + epsilon_div * (1 - D_consensus)
D_consensus = (1/N) * sum_j d_j
epsilon_div = 0.10   (default; raises quorum when diversity is low)
```

### Quorum Tiers

```
D_consensus >= 0.60  ->  Q_required = 2/3 (standard)
0.40 <= D_consensus < 0.60  ->  Q_required = 0.75 (elevated)
D_consensus < 0.40  ->  Q_required = 0.85 (strict) + GOVERNANCE_SIGNAL emitted
```

### Invariants

- A block requires `Q_required` of weighted power to be finalized.
- Diversity is recomputed every epoch from L1 behavioral hashes.

---

## L4.3-4.6 Living Security -- The 8 DNA Components

Validator security is not a static key; it is a living genome with 8 components.

### Component Registry

```
ID  | COMPONENT               | FUNCTION
----|-------------------------|----------------------------------------------
G1  | Genetic Key (GK)        | long-term identity root (BIP-39 like)
G2  | Complementary Strand    | paired key required for any signature
G3  | Immune System           | anomaly detector over incoming proposals
G4  | Epigenetic Layer        | context-dependent key activation
G5  | Genetic Recombination   | periodic key mixing with peer validators
G6  | Cryptographic Noise     | injected entropy to prevent correlation
G7  | Mitochondrial Core      | emergency survival key (offline-capable)
G8  | CRISPR Defense          | targeted removal of compromised components
```

### Composite Security Integrity

```
LSI = (1/8) * sum_{k=1..8} integrity(Gk)
integrity(Gk) = 1 if component passes its health check else 0
```

### Component Rules

```
G1 (GK): rotated every 365 epochs; never exposed outside the validator.
G2 (Complementary): MUST be stored on a different physical device than G1.
G3 (Immune): trained on L1.2 manipulation fingerprints; blocks flagged proposals.
G4 (Epigenetic): activated only when G3 flags a contextual anomaly.
G5 (Recombination): every 30 epochs, mix G2 with peer G2 via MPC.
G6 (Noise): inject kappa_noise = 2^-16 random bits into every signature.
G7 (Mitochondrial): capable of signing consensus-critical messages offline.
G8 (CRISPR): if any Gk fails integrity, quarantine and replace that component.
```

### Invariants

- A validator with `LSI < 0.875` (i.e., any single Gk failed) is suspended.
- A validator with `LSI < 0.50` (4+ components failed) is slashed (see L4.9).
- CRISPR actions emit a BOOTSTRAP signal.

---

## L4.7 Security Bootstrap

A new validator must bootstrap its living security genome before participation.

### Bootstrap Sequence

```
1. Generate G1 (genetic key) from validator's entropy source.
2. Generate G2 (complementary strand) on a separate device.
3. Initialize G3 (immune system) with current L1.2 manipulation fingerprints.
4. Load G4 (epigenetic layer) with default context activations.
5. Defer G5 (recombination) until first 30 epochs complete.
6. Initialize G6 (cryptographic noise) with on-chain randomness beacon.
7. Pre-load G7 (mitochondrial) with offline emergency keys.
8. Initialize G8 (CRISPR) with current validator set whitelist.
```

### Bootstrap Verification

```
bootstrap_proof = ZK_proof( LSI == 1.0 AND genome_correctly_formed )
```

### Invariants

- Bootstrap proof MUST be verified before the validator can produce blocks.
- Bootstrap emits a BOOTSTRAP signal (see signal_types.md).

---

## L4.8 HHI Geographic Enforcement
> **SUPERSEDED:** see WHITEPAPER_MD.txt L4.1 / V2 L4.8 — canonical resolution recorded in `docs/audit/CANONICAL_SPEC_MATRIX.md` (K11). The canonical HHI is over effective stake ×10 000 with 1500/2500/4000 tiers (`core/spiritual/hhi_monitor.py`, Go mesh). The 0–1-scale per-jurisdiction/infra HHI below is a useful engineering *supplement* (infra-concentration is otherwise unspecified) — keep, documented as such.


Validator concentration is bounded using the Herfindahl-Hirschman Index.

### HHI Formula

```
HHI_geo = sum_j ( stake_j^2 )   (over validators within the same jurisdiction)
HHI_infra = sum_j ( stake_j^2 ) (over validators on the same infrastructure provider)
```

### Enforcement Thresholds

```
HHI_geo   <= 0.15  ->  compliant
0.15 < HHI_geo <= 0.25  ->  warning (GOVERNANCE_SIGNAL emitted)
HHI_geo > 0.25  ->  non-compliant (validator admissions from that jurisdiction paused)

HHI_infra <= 0.10  ->  compliant
0.10 < HHI_infra <= 0.18  ->  warning
HHI_infra > 0.18  ->  non-compliant (provider flagged,validator offboarding initiated)
```

### Invariants

- HHI is recomputed every epoch from validator self-reported locations.
- Misreporting location is a slashable offense (L4.9, condition S5).

---

## L4.9 Slashing Conditions and Dispute Resolution
> **SUPERSEDED:** see WHITEPAPER_V2.txt L4.9 — canonical resolution recorded in `docs/audit/CANONICAL_SPEC_MATRIX.md` (K12). V2 L4.9's five-condition registry (COORDINATED_ATTACK 50%, LOW_ACCURACY, HSM, UPTIME, SYBIL_CLUSTER) + 72h dispute is canonical (`core/spiritual/slashing.py`, `core/governance/slashing.py`, Go evidence-based double-signing). The S1–S6 conditions below must be read as merged into that one registry, not as a parallel schedule.


Six slashable conditions, each with a severity and dispute window.

### Slash Registry

```
ID  | OFFENSE                        | SLASH %  | DISPUTE WINDOW
----|--------------------------------|----------|----------------
S1  | Double signing                 | 100%     | 7 epochs
S2  | Liveness violation (>6 epochs) | 5%       | 3 epochs
S3  | Diversity fraud (forged M_j)   | 50%      | 14 epochs
S4  | Genome compromise (LSI < 0.5)  | 30%      | 7 epochs
S5  | Geographic misreporting        | 20%      | 7 epochs
S6  | Manipulation participation     | 100%     | 14 epochs
```

### Dispute Resolution Process

```
1. Slash proposal emitted with evidence hash.
2. Dispute window opens (length per table above).
3. Accused validator submits a Behavioral ZK Proof (novel_primitives.md P4)
   demonstrating innocence.
4. Validators vote on the dispute (diversity-weighted, Q_required = 2/3).
5. If dispute is upheld, slash is reversed and accuser is slashed at S3.
6. If dispute is rejected, slash executes.
```

### Slashing Formula

```
slash_amount = stake_j * slash_pct(Sk) * (1 + severity_multiplier)
severity_multiplier = 0.5 if repeat offense within 90 epochs else 0
```

### Invariants

- No slash may execute before its dispute window closes.
- All slashes emit a GOVERNANCE_SIGNAL.
- A validator slashed at 100% is permanently evicted and added to CRISPR denylist.

---

## Cross-References

- L0.1 -- Behavioral Hash produces the `M_j` vectors used in L4.1.
- L1.2 -- Manipulation fingerprints feed the Immune System (G3) and offense S6.
- L5.3 -- Consensus degradation tiers depend on L4 quorum availability.
- `signal_types.md` -- GOVERNANCE_SIGNAL, BOOTSTRAP, SYSTEMIC_RISK tie into L4.
- `novel_primitives.md` -- P3 (Diversity-Weighted BFT), P4 (Behavioral ZK Proofs).
