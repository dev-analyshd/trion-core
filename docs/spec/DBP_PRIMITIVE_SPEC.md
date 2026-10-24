```
BIP: DBP
Title: Deterministic Behavioral Preimage (DBP) Primitive
Layer: Consensus / Cryptographic Primitive
Author: TRION Research (Cryptographic Primitive Formalizer)
Status: Draft — Research Specification
Type: Standards Track (Informational)
Created: 2026-10-24
```


# Deterministic Behavioral Preimage (DBP) — Formal Specification

> **Abstract.** We define the *Deterministic Behavioral Preimage* (DBP), a
> cryptographic primitive that turns a public, externally-derivable event
> (here: a Bitcoin block) into a SHA-256 preimage whose revelation
> authorises a UTXO spend. Unlike an HTLC preimage (chosen by an
> interactive recipient), a signature (held by a key-holder), or a DLC
> oracle attestation (issued by an oracle), a DBP preimage is a
> *deterministic function of public chain data* — it is not "chosen" by
> any party, only *derived* and *published*. We give the formal
> definition `DBP = (Setup, Compute, Commit, Reveal, Verify)`, a
> security game `DBP-Forge`, three theorems with proof sketches, the
> composition with Bitcoin's `OP_SHA256 OP_EQUAL`, a comparison to
> existing primitives, and the resulting safety/liveness trust model.
>
> The primitive is not hypothetical: an 80-byte DBP payload was used as
> the *sole* authorisation witness for a confirmed Bitcoin testnet
> spend (`edd5aa4a568e9974a4373038d6ee5270723d80c0770879113090e7e79fbf8f44`,
> block 5197632) with **no signature** on the spend path.


## 1. Primitive Definition

Let `λ = 128` denote the security parameter, fixed by the preimage
resistance of SHA-256 over an 80-byte domain. Let `{0,1}^*` denote
the set of byte strings and `{0,1}^λ` the set of 256-bit strings.

The DBP primitive is a tuple of five algorithms:

```
DBP = (Setup, Compute, Commit, Reveal, Verify)
```

**`Setup(1^λ) → params`**
Initialises the public parameters. For DBP, `params` is fixed and
implicit:

```
params = {
  H        : {0,1}^* → {0,1}^λ       // H := SHA-256
  L        : ℕ                        // L := 80   (payload byte length)
  Σ        : payload schema           // Σ := §1.1 layout
}
```

`Setup` is parameterless in practice — SHA-256 and the 80-byte layout
are constants — but we retain it for compositional clarity.

**`Compute(block_data) → payload ∈ {0,1}^(8L)`**
A *deterministic*, *public* function from a Bitcoin block (and an
event descriptor) to an 80-byte payload. Determinism is with respect
to the canonical byte layout defined in §1.1. There is no randomness,
no secret, and no interactive input. Anyone with the same `block_data`
re-derives the same `payload`.

**`Commit(payload) → H ∈ {0,1}^λ`**
The commitment is a single SHA-256 digest:

```
H = SHA-256(payload)
```

`Commit` is a pure function. `H` is the value embedded in Bitcoin
Script and published on-chain at lock time.

**`Reveal(payload)`**
The publication step: `payload` is broadcast (e.g. posted to a
Stacks contract, an indexed DA layer, or a public mempool). `Reveal`
is *informational* — it does not change `payload` or `H`; it only
makes `payload` available to parties who did not run `Compute`.

**`Verify(payload, H) → {0, 1}`**

```
Verify(payload, H) = 1  iff  SHA-256(payload) == H  and  |payload| == 80
                   = 0  otherwise.
```

### 1.1 The 80-byte payload layout

```
offset  width  field            type        encoding / semantics
──────  ─────  ───────────────  ──────────  ──────────────────────────────────────
  0     20     entity_id        bytes[20]   Leftmost 20 bytes of SHA3-256(normalise(btc_addr))
                                            (same width as a Bitcoin P2PKH HASH160)
 20      1     event_type       uint8       canonical TRION event id (TRANSFER=0, BRIDGE=10, …)
 21      8     magnitude_nano   uint64      ⌊ magnitude_norm × 10^9 ⌋, big-endian
 29      8     timestamp        uint64      block time (median-time-past), Unix seconds, big-endian
 37      4     chain_id         uint32      TRION chain registry id (Bitcoin = 100), big-endian
 41     32     block_hash       bytes[32]   SHA-256d of the Bitcoin block containing the lock tx
 73      7     reserved         bytes[7]    0x00 … 0x00 (MUST be all-zero in v1)
──────  ─────
 41+32  = 73  + 7  = 80 bytes total
```

Every field is derivable from public Bitcoin block data plus the
locking transaction; nothing in the payload is secret. The payload is
**cross-VM canonical**: the same bytes are produced by Python, Rust,
TypeScript, Solidity, Cairo, and Clarity, pinned by golden vectors.

### 1.2 Empirical reference

The deployed vault `tb1phvsndxyhzm83jpg6e2m97msadn2fnq6tud3ludq3d5ewvxqs3f4snmnrar`
commits `H = d93f341d6370c737b2c2f09ed88f7949fcdc87593440972a422c34a8bbbf92a2`
and was spent by revealing the following 80-byte payload as the sole
witness (no signature):

```
cc8aa95abbc7965be22cccc07b10c79520df838d  ← entity_id[20]
00                                        ← event_type = 0 (TRANSFER)
000114f737a8d60                           ← magnitude_nano
000000006a9dada7                          ← timestamp = 1788718503
00000064                                  ← chain_id = 100 (Bitcoin)
00000000000001a9562ec7227605f68ea1baf77dfa37d6794fcd55bca4a509f4  ← block_hash[32]
00000000000000                            ← reserved[7]
```

`SHA-256(payload) = H`, empirically confirming the construction.


## 2. Security Model

We define a single security game, `DBP-Forge`, capturing the
adversary's inability to produce *any* valid payload for a committed
`H` without the original `payload`.

### Game `DBP-Forge(λ, A)`

1. **Setup.** Challenger runs `Setup(1^λ) → params`.
2. **Sample.** Challenger selects a Bitcoin block `block_data`
   uniformly at random from blocks with height `≥ H₀` for some
   public `H₀`, and computes `payload ← Compute(block_data)`.
3. **Commit.** Challenger computes `H ← Commit(payload)`.
4. **Adversary input.** `A` receives `H` and `params`. `A` does
   **not** receive `payload` and has no oracle access to `Compute`
   beyond what it can re-derive itself from public chain data.
5. **Output.** `A` outputs `payload' ∈ {0,1}^*`.
6. **Win.** `A` wins the game iff
   ```
   Verify(payload', H) = 1   AND   payload' ≠ payload.
   ```

### Theorem 1 (Preimage Resistance)

For any probabilistic polynomial-time (PPT) adversary `A`,

```
Pr[ DBP-Forge(λ, A) = 1 ]  ≤  negl(λ),
```

where `negl(·)` is a negligible function, under the assumption that
SHA-256 is preimage-resistant over the 80-byte input domain.

### Proof sketch (by reduction)

Suppose, for contradiction, that there exists a PPT adversary `A`
such that `Pr[DBP-Forge(λ, A) = 1] ≥ ε(λ)` for non-negligible `ε`.
We construct a PPT adversary `B` that breaks the preimage
resistance of SHA-256 with the same advantage:

1. `B` is given a target hash `H* ∈ {0,1}^λ` drawn uniformly at
   random by the SHA-256 challenger (i.e. `H* = SHA-256(x)` for a
   uniformly random `x`).
2. `B` invokes `A` on input `H*` (and `params`).
3. `A` returns `payload'`.
4. `B` outputs `payload'` as its candidate preimage.

By the construction of `Verify`, `A` wins `DBP-Forge` iff
`SHA-256(payload') = H*`. Hence

```
Pr[ B wins preimage game ]
    ≥ Pr[ A wins DBP-Forge ]            (when H* is the DBP commitment)
    ≥ ε(λ),                              (by hypothesis)
```

contradicting the preimage resistance of SHA-256. ∎

> **Note on the domain.** `DBP-Forge` does not require the adversary
> to recover the *original* `payload` — only *any* `payload'` with
> the same image. This is exactly the preimage experiment; the
> 80-byte domain does not weaken the bound, because SHA-256's
> preimage resistance holds for every input length `≥ λ/8`.


## 3. Properties

| Property | Formal Statement |
|----------|------------------|
| **Determinism** | `∀ block_data: Compute(block_data) = Compute(block_data)` — a pure, total function; identical input yields identical output across all implementations and VMs. |
| **Preimage resistance** | Given `H = SHA-256(payload)` for `payload ∈ {0,1}^(8L)`, finding *any* `payload'` with `SHA-256(payload') = H` requires expected work `O(2^λ) = O(2^128)`. |
| **Public verifiability** | `Verify(payload, H)` is a pure, side-effect-free computation requiring only `payload`, `H`, and SHA-256. No secret key, no oracle, no chain state. |
| **Non-interactivity** | `Compute` is computed from public data alone. There are zero rounds of communication between the locker, the releaser, and the verifier. |
| **Censorship resistance after reveal** | Once `payload` has been published to *any* public medium, any party may copy it into a Bitcoin transaction. No party — including TRION — can retract or invalidate a published `payload`. |
| **Binding to Bitcoin reality** | `payload.block_hash` is the SHA-256d of a real Bitcoin block. Forging a payload with a fabricated `block_hash` requires fabricating a valid Bitcoin block, i.e. controlling ≥ 51% of Bitcoin hash power. |
| **Cross-VM canonicality** | The 80-byte layout is byte-identical across Python, Rust, TypeScript, Solidity, Cairo, and Clarity, pinned by golden vectors. |
| **Compactness** | `|payload| = 80` bytes fits comfortably in a Bitcoin Taproot witness item; the resulting witness discount keeps on-chain cost negligible (< 25 vBytes at 1 sat/vB). |


## 4. Composition with Bitcoin Script

The DBP commits *only* to the SHA-256 image of the payload, so it
composes natively with Bitcoin's `OP_SHA256` opcode. Let `H` be a
32-byte little-endian push of the committed hash.

### 4.1 Spend construction

```
scriptPubKey  (Taproot script-path leaf):
  OP_SHA256 <H:32B> OP_EQUAL

spend witness (script path):
  <payload:80B>  <script>  <controlBlock>
```

The witness item `payload` is **not** a signature; it is the raw
80-byte DBP payload. There is no `OP_CHECKSIG` on this path.

### 4.2 Theorem 2 (Spend Correctness)

**Claim.** If `Verify(payload, H) = 1`, then the Bitcoin Script
`OP_SHA256 <H> OP_EQUAL` evaluates to `TRUE` and the spend is
authorised.

**Proof.** Under BIP-342 (Tapscript) semantics:

1. `<payload>` is pushed onto the stack by the witness.
2. `OP_SHA256` pops the top stack item (`payload`), computes
   `SHA-256(payload)`, and pushes the resulting 32-byte digest.
3. `<H>` is pushed as a 32-byte literal.
4. `OP_EQUAL` pops the top two items (the computed digest and `H`),
   compares them byte-for-byte, and pushes `1` if equal, `0`
   otherwise.

By the hypothesis `Verify(payload, H) = 1`, we have
`SHA-256(payload) = H`, hence `OP_EQUAL` pushes `1`, the script
terminates with a non-zero top stack item, and the interpreter
returns `TRUE`. ∎

### 4.3 Theorem 3 (Spend Security)

**Claim.** If adversary `A` does not know any `payload*` satisfying
`SHA-256(payload*) = H`, then `A` cannot construct a valid witness
for the script of §4.1 (except with negligible probability).

**Proof.** A valid witness must contain a stack item `w` such that,
after `OP_SHA256` is applied, the top of the stack equals `H`. That
is, the witness must contain `w` with `SHA-256(w) = H`. Such a `w`
is by definition a SHA-256 preimage of `H`. Producing one is exactly
the preimage problem, which is infeasible by Theorem 1. ∎

### 4.4 Composition with a refund path (CSV safety)

In practice, the DBP script-path leaf is composed under a single
Taproot output with a second leaf:

```
Leaf 1 (release):  OP_SHA256 <H> OP_EQUAL
Leaf 2 (refund):   <borrower_pubkey> OP_CHECKSIGVERIFY
                   <csv_delta> OP_CHECKSEQUENCEVERIFY
```

The borrower's refund path is *independent* of TRION: it requires
only the borrower's signature and the passage of `csv_delta` blocks.
Hence DBP release authority is permissionless (anyone may relay a
published `payload`), while refund authority is unconditionally in
the borrower's hands.


## 5. Comparison to Existing Primitives

| Primitive | Preimage Type | Trust Model | Censorable? | Re-derivable from BTC? |
|-----------|---------------|-------------|-------------|------------------------|
| **HTLC (Lightning)** | Random secret chosen by recipient | Interactive — recipient decides | Yes (recipient can refuse to reveal) | No |
| **Signature (ECDSA / Schnorr)** | N/A — signature, not preimage | Key holder decides | Yes (key holder can refuse to sign) | No |
| **Timelock (CSV / CLTV)** | N/A — time-based | No trust | No (automatic on maturity) | N/A |
| **DLC Oracle** | Oracle signature over outcome | Oracle decides | Yes (oracle can refuse to attest) | No |
| **Adaptor Signature** | T-of-T secret, derived from signature | Signer decides | Yes (signer can withhold adaptor) | No |
| **Vault covenant (CTV/APO)** | N/A — covenant hash | Covenanter pre-commits | No (after commitment) | No |
| **DBP (this work)** | **Deterministic function of public chain data** | **Liveness only — TRION must publish `payload`** | **No, once published anyone can relay** | **Yes** |

DBP is the first primitive in this table whose authorisation
material is **simultaneously** (i) a hash preimage (so it composes
with `OP_SHA256`), (ii) deterministically re-derivable from Bitcoin
itself (so it is binding to Bitcoin reality), and (iii) publishable
by anyone (so it is post-publication censorship-resistant).


## 6. Trust Assumptions

We separate **safety** (funds cannot be stolen) from **liveness**
(funds can be moved when desired).

### 6.1 Safety — trustless

Safety of the Coherence Vault rests on:

- **SHA-256 preimage resistance** (`2^128` work to forge a release
  witness) — Theorem 1.
- **Borrower's CSV refund path** — a self-rescue available after
  `csv_delta` blocks, requiring only the borrower's signature
  (Theorem 2 + §4.4).
- **Pre-specified output addresses** — the release and refund
  transactions commit to fixed destination addresses at lock time;
  neither TRION nor the borrower can redirect funds.

**No trust in TRION is required for safety.** Even if TRION
disappears entirely, the borrower recovers their BTC after
`csv_delta` blocks.

### 6.2 Liveness — requires TRION publication

Liveness of the *release* path requires:

- TRION (or any party running `Compute`) publishes `payload` to a
  public medium.
- If TRION is offline, the release path is unusable *until* someone
  runs `Compute` on the same `block_data` and publishes the result.
  Because `Compute` is deterministic and public, this can be done by
  *anyone* — TRION has no monopoly on derivation, only on operational
  responsibility.
- Borrower's refund path remains available regardless; only the
  *lender's* position becomes illiquid if TRION is offline.

### 6.3 Liveness improvement over Babylon-style committee locks

In a Babylon-style design, a committee controls **both the decision**
*and* **the execution** (a signature is required to spend). If the
committee is offline or censoring, the release path is dead.

In DBP, TRION controls **the decision** (when to publish `payload`)
but **not the execution**: once `payload` is public, *anyone* can
relay the Bitcoin spend. This strictly dominates the committee model:

```
Babylon committee:   decision × execution ∈ committee  →  censored iff committee censors
DBP:                 decision ∈ {TRION, anyone running Compute}
                     execution ∈ {anyone with a copy of payload}
                     → censored iff ALL of {TRION, public} are censored
```

The set of parties that can suppress execution grows from `{committee}`
to `{everyone who has read the payload}`, which after publication is
effectively the union of all gossip-network participants.


## 7. Open Problems

1. **Decentralised publisher network.** `Compute` is public, so any
   node may derive `payload` once `block_data` is finalised. Open:
   how to ensure *at least one* such node remains available and
   economically incentivised, without re-introducing a committee?

2. **`OP_CAT` (and `OP_CHECKTEMPLATEVERIFY`-style) activation.**
   Today, Bitcoin Script verifies `SHA-256(payload) == H` but
   cannot inspect the *contents* of `payload`. With `OP_CAT` plus
   introspection opcodes, a script could additionally verify the
   structural fields (`event_type`, `chain_id`, `block_hash`,
   `reserved == 0`), eliminating the (already weak) assumption that
   the published payload has the correct internal structure.

3. **Formal proof of the full composition.** Prove, in a
   UC-style or simulation-based model, that
   `DBP + CSV + Taproot` realises an ideal "BTC lock with
   permissionless release and trustless refund" functionality, with
   precise quantification of the `(safety, liveness)` trade-off
   envelope as a function of `csv_delta`.

4. **Standardisation of the 80-byte payload.** A BIP-style standard
   for the §1.1 layout would let other protocols (cross-chain
   bridges, BTC-secured rollups, oracle-assisted vaults) reuse DBP
   verbatim, with cross-implementation test vectors.

5. **Aggregatability / batching.** Whether `k` independent DBP
   commitments can be aggregated (e.g. via a Merkle root of the
   `H_i`s) so a single on-chain commitment serves `k` vaults, with
   a single revealed payload per vault.

6. **Quantum-resistance of the refund path.** The release path is
   already post-quantum (SHA-256 preimage resistance survives
   Grover, yielding `2^64` quantum security). The refund path
   depends on the borrower's ECDSA/Schnorr key, which does not. An
   interesting question is whether the refund path can also be made
   hash-preimage-based.


## Appendix A — Notation

| Symbol | Meaning |
|--------|---------|
| `λ` | Security parameter; here `λ = 128` |
| `H` | A 256-bit hash value, `H ∈ {0,1}^λ` |
| `SHA-256` | NIST FIPS 180-4 hash function |
| `payload` | An 80-byte string per §1.1 |
| `negl(λ)` | A negligible function in `λ` |
| `PPT` | Probabilistic polynomial-time |
| `csv_delta` | Bitcoin relative timelock in blocks (`OP_CHECKSEQUENCEVERIFY`) |
| `block_hash` | `SHA-256d` of an 80-byte Bitcoin block header |

## Appendix B — Empirical Reference Values

| Field | Value (BTC testnet, 2026-10-24) |
|-------|---------------------------------|
| Vault address | `tb1phvsndxyhzm83jpg6e2m97msadn2fnq6tud3ludq3d5ewvxqs3f4snmnrar` |
| Committed `H` | `d93f341d6370c737b2c2f09ed88f7949fcdc87593440972a422c34a8bbbf92a2` |
| Funding txid | `36172ef4b754ea80e2a533406368a3c1f4db3c6611dfe3a7ea2d88cb926836c4` |
| Funding block | 5197629 |
| Spend txid | `edd5aa4a568e9974a4373038d6ee5270723d80c0770879113090e7e79fbf8f44` |
| Spend block | 5197632 |
| Spend type | `preimage-reveal (NO SIGNATURE — 80-byte HashDNA payload is the SOLE authorization)` |
| Witness item 0 | 80-byte DBP payload |
| Witness item 1 | 35-byte `OP_SHA256 <H> OP_EQUAL` script |
| Witness item 2 | 65-byte Taproot control block |
| Stacks contract | `ST969AZNDX2P7N1YJ0DNVGC8QEKT388DBMXGHR9Z.trioncoherencevault-v5` |

These values are reproduced verbatim from
`proofs/btcp-zero-bridge/stacks/e2e-full-results.json` and
`btc-tools/vault/vault-final.json`; the empirical spend is the
concrete realisation of Theorem 2.


## References

- BIP-341 — Taproot: SegWit version 1 spending rules.
- BIP-342 — Tapscript: Validation of Taproot script paths.
- NIST FIPS 180-4 — Secure Hash Standard (SHA-256).
- TRION Research — *TRION-Native Bitcoin Lock Design (Coherence Vault)*,
  Phase 0 Deep Research Report, 2026-09-14.
- TRION Protocol — `docs/protocol/CANONICAL_BH.md` (canonical 93-byte
  HashDNA payload; DBP is the 80-byte Bitcoin-Script-compatible subset).
