# TRION Protocol -- L0 Universal Primitives Specification

> **Reference:** TRION Whitepaper, Section 2 (Universal Layer L0).
> This layer defines the foundational behavioral substrate used by all higher layers.

## Scope

L0 defines six universal primitives that every TRION-compatible chain MUST implement.
These primitives are physics-agnostic and apply to any observable behavioral stream.

---

## L0.1 Behavioral Hash

### Definition

Every behavioral observation is reduced to a fixed **93-byte canonical payload** hashed
via a dual-strand SHA3 construction.

### Payload Layout (93 bytes)
> **SUPERSEDED:** see WHITEPAPER_V2.txt L0.1 (MD silent on byte layout) — canonical resolution recorded in `docs/audit/CANONICAL_SPEC_MATRIX.md` (K2). The canonical 93-byte BH is the V2 *preimage* layout `entity_id(32)‖event_type(1)‖magnitude(8)‖context(8)‖timestamp(8)‖chain_id(4)‖block_hash(32)` — implemented byte-identically in Rust/Python/TS and pinned by tri-language golden vectors (`docs/protocol/CANONICAL_BH.md`). The output-shaped layout below (CRC + 9-byte beo) is an obsolete draft; per **K22** the canonical BEO/entity id is 32 bytes (V2 L0.2 / BTCP §4.1 bytes32), not the 9-byte beo shown below.


```
[0..31]   strand_A : SHA3-256(quantitative_data)        -- 32 bytes
[32..63]  strand_B : SHA3-256(qualitative_context)      -- 32 bytes
[64..79]  meta     : chain_id | observer_id | nonce     -- 16 bytes
[80..88]  beo_id   : entity fingerprint                 -- 9 bytes
[89..92]  crc      : CRC32 over bytes 0..88             -- 4 bytes
```

### Dual-Strand Hash

```
strand_A = SHA3-256( quantitative_data || entropy_salt )
strand_B = SHA3-256( qualitative_context || temporal_anchor )
BH(B)    = strand_A || strand_B || meta || beo_id || crc32(strand_A||strand_B||meta||beo_id)
```

### Invariants

- `len(payload) == 93` (MUST be enforced at the consensus boundary).
- `strand_A` MUST be computable without observer context (deterministic).
- `strand_B` MUST depend on observer state (reflexive).
- A collision on both strands is treated as proof of behavioral equivalence.

---

## L0.2 Entity Resolution

The Behavioral Entity Object (BEO) is resolved from four weighted evidence channels.

### Formula

```
BEO_confidence = w_CF * CF + w_ST * ST + w_SC * SC + w_BP * BP
```

Where:

- `CF` = chain fingerprint match (coherence with on-chain history)
- `ST` = spatiotemporal proximity
- `SC` = structural code similarity (call-graph / ABI)
- `BP` = behavioral pattern overlap
- `w_CF + w_ST + w_SC + w_BP = 1` (weights are asset-type-specific)

### Thresholds
> **SUPERSEDED:** see WHITEPAPER_V2.txt L0.2 / MD L0.2 — canonical resolution recorded in `docs/audit/CANONICAL_SPEC_MATRIX.md` (K10). Production BEO resolution = **5 factors at >0.75** (the recorded audit resolution; `anima-service/faiss_service.py` + `core/primitives/entity_resolution.py` GX path). MD's 4-factor formula is the reference model — both live side-by-side in code. The 0.85/0.50 body thresholds below are non-canonical.


```
BEO_confidence >= 0.85  ->  resolved (single canonical entity)
0.50 <= BEO_confidence < 0.85  ->  ambiguous (GENESIS/RESURRECTION inference required)
BEO_confidence < 0.50  ->  new entity
```

> **Implementation note: production threshold is 0.75 with five-factor weights
> (CF 0.40/ST 0.25/SC 0.25/BP 0.10/GX 0.10) per July 2026 audit resolution.**
> The production resolver (`anima-service/faiss_service.py`, mirrored in
> `core/primitives/entity_resolution.py`) adds a fifth evidence channel —
> GX, transaction-graph co-occurrence (w_GX = 0.10) — and resolves at
> `BEO_CONFIDENCE_THRESHOLD = 0.75`:
> `BEO_confidence = (w_CF·CF + w_ST·ST + w_SC·SC + w_BP·BP + w_GX·GX) / Σw`.
> The spec thresholds above describe the whitepaper's four-factor reference
> model; the five-factor production values are canonical (audit finding L0.2,
> resolved "code wins" — see `TRION_AUDIT_REPORT.md` §L0.2).

### Invariants

- Resolution is monotonic: confidence can only be refined, never destroyed.
- Two entities with `BEO_confidence >= 0.95` MUST be merged into one canonical BEO.

---

## L0.3 Resonance Communication

Communication between two BEOs `X` and `Y` is modeled as resonance rather than message passing.

### Resonance Coefficient
> **SUPERSEDED:** see WHITEPAPER_MD.txt L0.3 — canonical resolution recorded in `docs/audit/CANONICAL_SPEC_MATRIX.md` (K20). MD's `Comm(A,B) iff ∃f: RF(A,f)>0 ∧ RF(B,f)>0` is the canonical communication semantics; the R(X,Y) coefficient below is an implemented *supplementary* metric (`core/primitives/resonance.py`), spec-silent engineering extension.


```
R(X, Y) = (1 / (1 + dist(BH_X, BH_Y))) * cos( phase(X) - phase(Y) )
```

- `dist(BH_X, BH_Y)` is the Hamming distance between the 93-byte payloads.
- `phase(X)` is the circadian phase of the observer at observation time (see L6.2).

### Resonance Channels

```
R(X, Y) > 0.90  ->  harmonic (full duplex)
0.50 < R(X, Y) <= 0.90  ->  sympathetic (one-way acknowledgment)
0.10 < R(X, Y) <= 0.50  ->  dissonant (signaling only)
R(X, Y) <= 0.10  ->  silent (no communication permitted)
```

---

## L0.4 Thermodynamic Information Conservation

Information cannot be created or destroyed within the TRION observation field.

### Conservation Law

```
I_total(t) = I_observed(t) + I_hidden(t) + I_lost(t)
dI_total / dt = 0
```

Where:

- `I_observed` = information present in the active behavioral stream.
- `I_hidden` = information dormant in the Akashic index (see L2).
- `I_lost` = information lost to decoherence (bounded by L3.6).

### Entropy Budget

```
S_emit(t) <= BH_gen(t) + A_abs(t) - E_lost(t)
```

- `S_emit` = emitted entropy (signals broadcast by the chain).
- `BH_gen` = generated behavioral entropy.
- `A_abs` = absorbed entropy from cross-chain observations.
- `E_lost` = entropy lost via decoherence.

---

## L0.5 Signal Selection Principle

Of all possible behavioral observations, only those that reduce system entropy are
selected as canonical signals.

### Selection Criterion

```
Delta_S = S_before - S_after
selected_signal := argmax_{s in candidate_pool} ( Delta_S(s) )
if max(Delta_S) < tau_select:
    emit SILENCE  (see signal_types.md)
```

### Default Parameters

```
tau_select = 0.003 nats
candidate_pool_size <= 1024
```

### Invariants

- Signals that would increase system entropy (`Delta_S < 0`) MUST be discarded.
- SILENCE itself is a first-class signal type and carries entropy information.

---

## L0.6 Evolutionary Fitness

A chain's evolutionary fitness is the product of four universals.

### Formula

```
F = PA * ICE * AS * Love
```

Where:

- `PA` (Persistence Adaptation) = survival probability across the last N epochs.
- `ICE` (Information Conservation Efficiency) = `I_observed / I_total`.
- `AS` (Akashic Synchronization) = fraction of dormant entities correctly indexed (see L2).
- `Love` (L0.3 Resonance averaged over the active peer set).

### Fitness Thresholds

```
F >= 0.75  ->  thriving   (eligible for Sovereign Behavioral Assessment, see L8)
0.40 <= F < 0.75  ->  stable
0.15 <= F < 0.40  ->  degenerate (CONSENSUS_ADAPTATION signal emitted)
F < 0.15  ->  terminal    (BIRP recovery initiated, see novel_primitives.md P6)
```

### Invariants

- `F` is bounded in `[0, 1]`.
- A chain with `F < 0.15` for `>= 7 epochs` is eligible for fork dissolution.

---

## Cross-References

- L1 -- physical layer uses L0.1 to derive physical richness.
- L2 -- Akashic index stores resolved BEOs from L0.2.
- L3 -- mental layer refines L0.6 fitness via observer effects.
- L4 -- spiritual security uses L0.6 fitness as an integrity input.
- `signal_types.md` -- SILENCE, GENESIS, RESURRECTION derive from L0.
- `novel_primitives.md` -- P1 Semi-Immutability is rooted in L0.4.
