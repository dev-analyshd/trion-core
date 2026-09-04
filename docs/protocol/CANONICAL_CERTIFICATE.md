# TRION Canonical Certificate — Cross-VM Consensus Attestation Specification

**Status:** NORMATIVE (Wave 1, master command §23 deliverable)
**Applies to:** every component that emits, relays, stores, or verifies a
TRION validator-consensus attestation that authorizes an action on a chain —
Solidity (`contracts/solidity/TRIONOracleV3.sol`, `BTCPEscrow.sol`,
`TRIONExecutionGate.sol`), Vyper (`contracts/vyper/`), Solana
(`contracts/svm/`), Move (`contracts/move/`), TON (`contracts/ton/`),
Cairo (`contracts/starknet/`, `contracts/cairo/`), NEAR (`contracts/near/`),
PVM (`contracts/pvm/`), the Go validator fleet (`validator/`), the Rust core
(`rust/src/`), the Python core (`core/spiritual/`, `core/btcp/`), and the
relayer (`relayer/`).
**Machine-readable twin / golden vectors:** the Python reference encoder
`core/consensus/certificate.py` and the pinned golden vectors in
`tests/unit/test_certificate_domain_separation.py`. Every Wave 2 VM
implementation MUST reproduce the 346-byte payload byte-for-byte and the
SHA3-256 certificate hash for the golden vector certificate.
**Companion specs:** `docs/protocol/CANONICAL_BH.md` (Agent B — the anchor
and execution behavioral hashes referenced here), `docs/protocol/
BTCP_STATE_MACHINE.md` (Agent F — escrow state machine that consumes this
certificate), `docs/audit/VALIDATOR_SECURITY_AUDIT.md` (Agent E — current
state per VM and the Wave 2 remediation work order).

> **One rule above all:** there is exactly ONE canonical certificate. The
> same 346-byte signing payload, signed by the same validator quorum, must be
> verifiable — through the VM-native encoding defined in §7 — on every
> destination VM. Any implementation whose signature verifies for a different
> payload, a different escrow, a different chain, or a different protocol
> version is a canonical violation.

---

## 1. What the certificate is

The canonical certificate is the **diversity-weighted BFT attestation that a
TRION consensus verdict has been reached for one escrow on one route**, and
the only artifact that authorizes releasing that escrow on the destination
chain.

It answers, in one signed object, the questions the BTCP spec's Step 3 proof
is meant to answer ("Chain B receives: anchor_BH + consensus_proof + intent;
verifies against known TRION validator set" — BTCP_SPEC §4.2 Step 3):

- **WHAT** was attested: one escrow, one route, one intent, one entity, one
  settlement tuple (destination, amount), one anchor and one execution
  behavioral hash.
- **WHO** attested it: which validators, with which epoch-scoped
  stake × diversity weights, reaching which quorum.
- **WHEN** and **HOW LONG**: issued_at / ttl.
- **UNDER WHICH RULES**: coherence C(t) vs threshold Θ(t), HHI at emission,
  AWA state, protocol version, validator epoch, certificate nonce.

Emission is performed by the DW-BFT validator set (the Go TRION-BFT engine
plus the spiritual plane's diversity computation — `core/spiritual/
consensus.py`, `validator/internal/consensus/`). Consumption is performed by
the escrow/oracle verifiers of Wave 2. This document defines the wire format,
the domain separation, the quorum derivation, the verification algorithm, the
replay rules, and the freshness rules that both sides MUST implement.

Bootstrap exception (spec: L2.1, L4.7): while `D(t) < D_minimum`, TRION
operates the classical fallback (multi-sig 7-of-12 + human oversight), not
DW-BFT certificates. Certificates emitted under bootstrap carry
`awa_enforced` semantics normally but MUST additionally be flagged out-of-band
by the emitter; verifiers MAY reject `validator_count < 100` (launch
threshold, V2 §9.2) — see §10.

---

## 2. Canonical payload (v1 — 346 bytes)

The signing payload `P` is a fixed-width, big-endian byte string. There are
**no dynamic-length fields, no floats, no maps, no timestamps other than
`issued_at`** — the same determinism discipline as the Go consensus canonical
encodings (`validator/internal/consensus/types.go:277-323`).

```
P = domain_tag || header || binding || consensus_state || validity
```

```
  offset  width  field                    type      scaled    bound value
  ──────  ─────  ───────────────────────  ────────  ────────  ─────────────────────────────
  0       13     domain_tag               ASCII     —         "TRION-CERT-V1"
  13      1      certificate_kind         uint8     —         1 = ESCROW_RELEASE
  14      3      protocol_version         uint24    —         semver packed major<<16|minor<<8|patch
  17      4      validator_epoch          uint32    —         epoch whose set/weights are used
  21      8      certificate_nonce        uint64    —         per (epoch, escrow_id) monotonic
  ── binding (what the certificate authorizes) ──────────────────────────────────
  29      32     escrow_id                bytes32   —         destination escrow identifier
  61      32     route_id                 bytes32   —         BTCP route identifier
  93      32     intent_hash              bytes32   —         hash of full §4.1 intent
  125     32     entity_id                bytes32   —         BEO identifier
  157     4      source_chain             uint32    —         TRION registry chain id (anchor)
  161     4      dest_chain               uint32    —         TRION registry chain id (execution)
  165     32     destination              bytes32   —         canonical destination account (§7)
  197     32     amount                   uint256   —         raw destination-native units
  229     32     anchor_bh                bytes32   —         anchor behavioral hash (CANONICAL_BH)
  261     32     execution_bh             bytes32   —         execution behavioral hash (CANONICAL_BH)
  ── consensus state at emission ────────────────────────────────────────────────
  293     8      coherence                uint64    ×1e6      C(t) at emission
  301     8      threshold                uint64    ×1e6      Θ(t) at emission
  309     8      hhi_at_emission          uint64    ×1e4      0–10000 scale (L4.8)
  317     8      total_effective_power    uint64    ×1e6      Σ_j s_j·d_j over the epoch set
  325     4      validator_count          uint32    —         N of the epoch set
  329     1      awa_enforced             uint8     —         1 iff AWA held at emission
  ── validity ──────────────────────────────────────────────────────────────────
  330     8      issued_at                uint64    —         unix seconds, consensus clock (§9)
  338     8      ttl                      uint64    —         seconds until expiry (§9)
  ──────  ─────
  346 bytes total
```

### 2.1 Canonical certificate hash

```
certificate_hash = SHA3-256(P)                      # FIPS 202 — the cross-VM ID
```

This is the object identifier used in the Akashic Index, in logs, and in
consumed-certificate registries on VMs that can recompute it. It follows the
L0.1 Hash_DNA discipline (SHA3-256, FIPS 202 — identical construction class
as `core/primitives/behavioral_hash.py`, Rust `Sha3_256`, Go `meshsha3`).

### 2.2 Why each field is bound (spec cite / engineering-decision cite)

| # | Field | Authority | Rationale |
|---|-------|-----------|-----------|
| 1 | `domain_tag` "TRION-CERT-V1" | ED-DS1 | Mirrors the BH pattern (MD L0.1 embeds `DOMAIN_SEPARATOR` and a version; BTCP_SPEC §4.2 commitment hashes embed `btcp_version`). Prevents a TRION validator signature from being interpreted as any other protocol's message (bridge-sig theft class). The tag is length-stable (13) and bumps with the format version. |
| 2 | `certificate_kind` | ED-K1 | One payload format, many statement types. Kind 1 = "this quorum authorizes releasing escrow E". Unknown kinds fail closed at verification (§6 step 1). Prevents a certificate minted for a future statement type from being silently reinterpreted. |
| 3 | `protocol_version` | SPEC | `BTCPProof.btcp_version` (BTCP_SPEC §4.2 Step 3), intent `btcp_version` (§4.1), BH payload `version` (MD L0.1). A certificate from protocol v1 must not be accepted by a v2 verifier without an explicit compatibility rule. |
| 4 | `validator_epoch` | ED-E2 | L4.2 / novel_primitives P3: "Diversity is recomputed every epoch." The d_j, s_j and the validator set are epoch-scoped; without binding the epoch, a retired or slashed validator set remains valid forever (the historical-set vulnerability in every current implementation — see VALIDATOR_SECURITY_AUDIT.md). |
| 5 | `certificate_nonce` | ED-N1 | The BH pattern terminates in `nonce` (MD L0.1); §4.1 intents carry a per-entity monotonic nonce. The certificate needs its own scope: re-attestations of the same escrow (e.g. after ttl expiry) must be distinguishable, and validators must have a slashing-evident equivocation boundary (§8). |
| 6 | `escrow_id` | ED-B1 | BTCP_SPEC has no escrow binding in `BTCPProof`; the EVM tier overloads `anchorBH` as the escrow id (TRIONOracleV3 §routeVerdictHash natspec, BTCPEscrow `_consensusGate` H1 fix). The canonical form binds **both** fields explicitly, removing the overload. |
| 7 | `route_id` | SPEC | `BTCPProof.btcp_route_id` (§4.2 Step 3), `BTCP_route.route_id` (§12.4). |
| 8 | `intent_hash` | SPEC | `BTCPProof.intent_hash` (§4.2 Step 3). Transitively binds the full §4.1 intent: entity, action, value, asset_in/asset_out, deadline, gas cap, finality, NL floor, chain pref, privacy, version, nonce. |
| 9 | `entity_id` | SPEC | `BTCP_route.entity_id` (§12.4), `BTCPRouteSignal.entity_id` (§4.2 Step 6). BEO identity continuity across chains is the core BTCP claim. |
| 10 | `source_chain` | SPEC | `BTCPProof.anchor_chain` (§4.2 Step 3). |
| 11 | `dest_chain` | SPEC | `BTCPProof.execution_chain` (§4.2 Step 3). Doubles as the cross-chain replay firewall (§8). |
| 12 | `destination` | ED-B2 | The settlement tuple (destination, amount) closes escrow-substitution: a certificate can only pay the exact destination the quorum saw. Mirrors the escrow's own record (`BTCPEscrow.Escrow.destination`, `EscrowLocked` event) and the Vyper escrow's destination. |
| 13 | `amount` | ED-B2 | Second half of the settlement tuple; also the input to the value-tier TTL (§9, A3 resolution). Raw destination-native units so the escrow can compare without conversion. |
| 14 | `anchor_bh` | SPEC | `BTCPProof.anchor_bh` — "Hash_DNA of anchor event on chain A" (§4.2 Step 3). Constructed per `docs/protocol/CANONICAL_BH.md`. |
| 15 | `execution_bh` | SPEC | `BTCP_route.execution_BH` (§12.4), `BTCPRouteSignal.execution_bh` (§4.2 Step 6), and the EVM `routeVerdictHash` already binds an execution BH. |
| 16 | `coherence` | SPEC | `ConsensusProof.coherence_score` — C(t) at emission (§4.2 Step 3). |
| 17 | `threshold` | SPEC | `ConsensusProof.threshold`/Θ(t) (rust types.rs `ConsensusProof.threshold`; L5.1 dynamic threshold). `threshold_margin = coherence − threshold` is derivable, so only the absolutes are bound. |
| 18 | `hhi_at_emission` | SPEC | `ConsensusProof.hhi_at_emission` (§4.2 Step 3); enforcement tiers at L4.8. |
| 19 | `total_effective_power` | ED-Q1 | Σ_j s_j·d_j over the epoch set (L4.1/L4.2, BTCP_SPEC §12.2 `w_j_effective = s_j · d_j`). Bound so the verifier can cross-check the certificate's claimed power total against the registered epoch set (fail-closed on mismatch) and so quorum is checkable without trusting envelope arithmetic. |
| 20 | `validator_count` | SPEC | Signal object `validator_count` (V2 Part 5), `DiversityCertificate.num_validators` (rust). N of the epoch set — needed for D_consensus. |
| 21 | `awa_enforced` | ED-A1 | MD §17 / V2 §17: AWA_enforced = FALSE → signal emission FROZEN. A certificate is an emission; the frozen state must be checkable on-chain. The signed bit is the verifiable equivalent of the emission-side gate (the receiving chain cannot observe TRION's internal AWA state any other way). |
| 22 | `issued_at` | SPEC | Signal object `timestamp` (V2 Part 5). |
| 23 | `ttl` | SPEC | Signal object `ttl` — "seconds until expiry" (V2 Part 5); unified with the A3/CERT_WINDOWS validity tiers (§9). |

### 2.3 Fields deliberately NOT bound (documented exclusions)

| Candidate | Decision | Why |
|---|---|---|
| `vm_type` | EXCLUDED (ED-X1) | The VM of `dest_chain` is a property of the canonical chain registry (config/chain_registry.json — 129 chains, 18 VM families), not of the attested fact. Binding vm_type breaks the moment a chain migrates VM or a new VM family is added; `dest_chain` + the registry already provide total replay firewalls. Wave 2 verifiers resolve vm_type via the registry at deployment, not via the signature. |
| `asset` / `asset_in` / `asset_out` | EXCLUDED (ED-X2) | The full asset pair is inside the §4.1 intent, hence inside `intent_hash` (the spec's own commitment: "intent registered by hash … `intent_hash = keccak256(abi.encode(intent))`"). A second, VM-specific asset encoding would create canonicalization drift (decimals/symbol per VM) with zero added security. |
| `threshold_margin` | EXCLUDED (ED-X3) | `coherence − threshold`, derivable; the spec's margin field adds no verification power. |
| `D_consensus` | EXCLUDED (ED-X4) | Mean d_j over the epoch set — recomputable from the registered set (§5); binding it would let the certificate self-attest its own quorum bar. |
| per-validator `d_j`, `s_j` | EXCLUDED from P (carried in the envelope, §4) | The spec's `DiversityCertificate` ("all d_j at emission") is realized as: per-signer weights in the envelope, cross-checked against the registered epoch set (§6 step 5c). Signed weights in the payload would make the quorum self-referential; registered weights make it externally checkable. |
| `feature_flags` / `min_verifier_ver` | EXCLUDED from P (envelope metadata) (ED-X5) | `BTCPProof.feature_flags` gate emitter capabilities, not the release authorization; `min_verifier_ver` is a routing hint. Both ride the envelope for relayers, unsigned. |
| verifying-contract address | EXCLUDED from P | Deliberate: one certificate must verify on the canonical escrow of its `dest_chain` regardless of which VM encoding hosts it. Deployment binding is enforced by escrow→oracle wiring and epoch-set registration per deployment (§7, residual risk R-2 documented in the audit). |

---

## 3. Signed payload construction and domain separation

### 3.1 The payload

Every validator signs the same `P` (§2). Signature families (§4) differ in
digest construction and primitive, never in `P`.

### 3.2 Per-family digests

```
FAMILY 1 — secp256k1 ECDSA recoverable (EVM, Vyper, NEAR, PVM-EVM-compat)
    D_evm          = keccak256(P)                                  # legacy keccak, EVM opcode
    signed message = EIP-191 wrap: keccak256("\x19Ethereum Signed Message:\n32" || D_evm)
    signature      = r[32] || s[32] || v[1]                        # 65 bytes
    verify         = ecrecover(EIP-191(D_evm), v, r, s) ∈ epoch set
    Rationale: matches the live repo discipline exactly —
    TRIONOracleV3.routeVerdictHash → MessageHashUtils.toEthSignedMessageHash,
    relayer.js signMessage, TRIONExecutionGate.publishSignal.

FAMILY 2 — Ed25519 (SVM, TVM, Move, NEAR optional)
    signed message = P                                             # raw payload — Ed25519 is its own hash
    signature      = 64 bytes
    verify         = ed25519_verify(pubkey, P, signature)
    Rationale: Ed25519 is native on Solana (ed25519 syscall), TON (crypto_chksig),
    Move (stdlib), and NEAR. No digest needed; signing raw P maximizes
    cross-family agreement (identical signed bytes).

FAMILY 3 — STARK-curve ECDSA over felts (Starknet / Cairo)
    P is chunked into felts: f_i = big-endian bytes [31·i, 31·(i+1)) of P,
    each < 2^252; 346 bytes → 12 felts (11 full 31-byte chunks + a final
    5-byte chunk read as one integer — chunk widths are FIXED by the format,
    so the chunking is injective and rebuilds P exactly).
    domain_felt     = felt("TRION-CERT-V1")                        # 13-char short string ≤ 31 bytes
    D_stark         = Poseidon(domain_felt, f_0 .. f_11)           # or Pedersen — fixed per deployment family
    signature       = (r, s) felt pair
    verify          = starknet ECDSA verify(D_stark, (r,s), stark_pubkey)
    Rationale: Starknet cannot cheaply verify keccak/secp256k1; the felt
    chunking is injective and deterministic, so the SAME semantic certificate
    (same P) verifies. Who bridges: the TRION epoch registrar publishes
    (validator_id, stark_pubkey, s_j, d_j) to the Starknet epoch-set contract
    each epoch boundary (§10); relays carry the certificate as a felt array.
```

`certificate_hash = SHA3-256(P)` (FIPS 202) is computed by the emitter and
stored in the Akashic Index; it is the canonical cross-VM identifier. Note:
Solidity's `keccak256` is the pre-standard Keccak (padding 0x01) — it is NOT
interchangeable with FIPS-202 SHA3-256 (padding 0x06). This is why the EVM
family digest and the canonical hash are deliberately different values; see
VALIDATOR_SECURITY_AUDIT.md finding H-07 for the pre-existing on-chain
HashDNA.sol mismatch this rule now governs.

### 3.3 Domain-separation guarantees

A valid certificate signature verifies for exactly one tuple:

| Replay target | Blocked by |
|---|---|
| another chain (same VM) | `dest_chain` + registry |
| another VM | `dest_chain` (→ VM family) + signature family of that VM |
| another escrow | `escrow_id` |
| another route / intent | `route_id`, `intent_hash` |
| another destination or amount | settlement tuple |
| another protocol version | `domain_tag` + `protocol_version` |
| another epoch's validator set | `validator_epoch` + epoch-set registration |
| another statement type | `certificate_kind` |
| a non-TRION protocol message | `domain_tag` |
| a Behavioral Hash / intent commitment | disjoint field layout + fixed 346-byte width + tag |

---

## 4. The envelope — signatures and weights

The certificate travels as a signed core plus an envelope. The envelope is
NOT signed as a whole; each validator signs `P` individually (the
`WeightedSignature` discipline of `rust/src/types.rs:377-382` and
BTCP_SPEC §4.2's `s_j · d_j · sign_j(...)`).

```
CertificateEnvelope v1:
    family              uint8        1 = secp256k1-recoverable, 2 = ed25519, 3 = stark-felt
    sig_len             uint8        65 | 64 | 2 (felt pair serialized as 64 bytes)
    signatures[]        repeated:
        validator_id        bytes32     SHA3-256(canonical validator id encoding)
        stake_weight        uint64  ×1e6  s_j — must equal epoch-set value
        diversity_weight    uint64  ×1e6  d_j — must equal epoch-set value
        signature           bytes[sig_len]
    feature_flags       (optional, unsigned) — BTCPProof feature flags for relayers
    min_verifier_ver    (optional, unsigned) — SemVer routing hint
```

Envelope invariants:

1. All signatures in one envelope belong to ONE family — the family of the
   destination VM (§3.2). Mixed-family envelopes fail closed.
2. `validator_id` values are distinct (duplicate signer padding is not
   consensus — the discipline already enforced in
   `rust/src/btcp_proof_builder.rs:212-216` and `TRIONOracleV3` sorted-signer
   batches).
3. `stake_weight` and `diversity_weight` are claims, not authority: the
   verifier MUST reject the certificate unless they equal the registered
   epoch-set values for that validator (§6 step 5c). This closes the
   self-reported-weight hole in the current Go mesh
   (`validator/internal/p2p/mesh.go` tryQuorum uses `att.DiversityWeight`
   from the attestation itself).
4. Minimum signature count: 3 (rust parity `InsufficientSigners`, a liveness
   floor; the real bar is the weight quorum of §5).

Per-validator keys: the epoch set registers, for each validator, one
canonical `validator_id` plus the public keys of every family that validator
serves (secp256k1 33-byte compressed, ed25519 32-byte, STARK-curve point).
`validator_id = SHA3-256("TRION-VALIDATOR" || epoch || key_index)`. A
validator MAY sign the same `P` once per family (cross-family duplicates are
never double-counted — only one family is examined per verification), and
signing two different payloads for the same `(epoch, escrow_id, nonce)` in
any family is equivocation (§10, L4.9 S1).

---

## 5. Quorum derivation

**Quorum is computed from the canonical validator state of the epoch — never
from caller-supplied values.** The only inputs are the registered epoch set
(s_j, d_j per validator) and the signature set (which validators signed).

### 5.1 Effective power

```
w_j = s_j · d_j                        # effective weight of validator j
total_power = Σ_j w_j  over the EPOCH SET          # == certificate.total_effective_power
signed_power = Σ_j w_j over VERIFIED SIGNERS       # recomputed by the verifier from
                                                   # registered weights, not from the envelope
```

Formula authority: BTCP_SPEC §12.2 (`w_j_effective = s_j · d_j`) and the MD
formula appendix (`d_j = 1 - corr(M_j, M)`, `w_j_effective = s_j · d_j`).
**Conflict resolved (see §12):** L4.1/P3 also define `P_j = stake_j · (1 +
δ·d_j)`. Hierarchy rule: the whitepaper (level 1) and BTCP_SPEC (governs BTCP
absolutely) both state `s_j · d_j`; the layer doc's bonus form is the
chain-internal voting-power variant. Certificate verification uses
`w_j = s_j · d_j` — the form the Coordination Collapse Theorem (§12.2) is
proved over. Weights are carried scaled ×1e6 as uint64; all arithmetic is
uint128.

### 5.2 Required quorum (L4.2 — tier table is normative)

```
D_consensus = (1/N) · Σ_j d_j          # over the epoch set (not the signers)

TIER 1: D_consensus ≥ 0.60        →  Q = 2/3   of total_power   (STRICT: 3·signed > 2·total)
TIER 2: 0.40 ≤ D_consensus < 0.60 →  Q = 0.75  of total_power   (4·signed ≥ 3·total)
TIER 3: D_consensus < 0.40        →  Q = 0.85  of total_power   (20·signed ≥ 17·total)
        and TRION emits GOVERNANCE_SIGNAL (off-chain; the certificate remains valid)
```

Scaled integer form (all uint128, weights ×1e6):

```
tier 1:  3 · signed_power            >  2 · total_power
tier 2:  4 · signed_power            ≥  3 · total_power
tier 3:  20 · signed_power           ≥  17 · total_power
```

Tier 1 uses strict inequality — exactly-2/3 is not a quorum (the discipline
of `validator/internal/consensus/engine.go:5-8` and its test
`hasQuorum(4,6) must fail`); tiers 2/3 are not on the 1/3 boundary and use ≥.
The continuous formula `Q = 2/3 + ε_div·(1 − D_consensus)` (L4.2, ε_div =
0.10) is the design rationale; the tier table is its normative
discretization and is always ≥ the continuous value (safe side).

### 5.3 Concentration preconditions (L4.8)

- `hhi_at_emission > 4000` → certificate is INVALID (CRITICAL tier = consensus
  paused; no valid emission could have occurred above it). Fail closed.
- `2500 < hhi ≤ 4000` (DANGER): valid, but the DANGER-tier weight caps (no
  cluster > 15% effective weight) must have been applied at epoch-set
  registration — enforced by the registrar, checked at audit.
- Geographic bounds (≥ 4 continents, region < 0.40, jurisdiction < 0.30) are
  registrar-side (V2 L4.8) and out of the per-certificate check.

### 5.4 Additional verdict preconditions

- `awa_enforced == 1` (else emission was frozen — MD §17).
- `coherence ≥ threshold` (the isSafe verdict; the escrow additionally
  enforces its own `min_coherence`, as BTCPEscrow does today).

---

## 6. Verification algorithm (fail-closed, in order)

Every consuming VM implements exactly these steps. Any failure rejects the
certificate (no partial acceptance, no fallback to weaker checks — the
DD-flagged "oracle fallback" class is prohibited).

```
verify(cert, escrow_state, now, epoch_registry):

 1. STRUCTURE. Envelope widths exact; family matches this VM's family;
    certificate_kind == 1 (unknown kinds → reject); protocol_version ≤
    supported max; sig_len matches family; len(signatures) ≥ 3;
    validator_ids distinct. (Rust parity: InsufficientSigners /
    DuplicateSigner / MalformedSignature / VersionIncompatible.)

 2. EPOCH. Look up validator_epoch in the local epoch registry (§10).
    Unknown epoch → REJECT (fail-closed; no historical-set acceptance).
    Also: epoch ≥ latest_registered_epoch − grace (default grace = 2)
    → stale-epoch certificates are rejected even within ttl.

 3. FRESHNESS. issued_at ≤ now ≤ issued_at + ttl, where now is the VM
    clock (§9) and the verifier's clock_drift_tolerance (default 60s) may
    widen the lower bound only. Expired or future-dated → REJECT.

 4. CONSENSUS PRECONDITIONS. hhi_at_emission ≤ 4000; awa_enforced == 1;
    coherence ≥ threshold; validator_count == N of the registered epoch set.

 5. SIGNATURES (per signature, in order):
    a. recover/verify the family signature over P (§3.2) — one bad
       signature fails the WHOLE certificate (batch fail-closed, the
       submitRouteAttestation discipline).
    b. recovered identity ∈ registered epoch set (membership by
       validator_id / address).
    c. envelope (stake_weight, diversity_weight) == registered values,
       scaled ×1e6, exact equality. Mismatch → REJECT.

 6. QUORUM. Recompute signed_power = Σ registered w_j over verified
    signers; cross-check total_effective_power == Σ w_j over the epoch set
    (mismatch → REJECT — the certificate lied about the set); check the
    L4.2 tier condition (§5.2) using D_consensus of the REGISTERED set.

 7. BINDING. Against the escrow's own state:
    escrow_id == target escrow; route_id == escrow.route_id;
    intent_hash == escrow.intent_hash (where the VM escrow stores it);
    destination == escrow.destination; amount == escrow.amount;
    source/dest chain == escrow's route legs; anchor_bh/execution_bh == the
    route's recorded behavioral hashes (where stored).

 8. NONCE / CONSUMED. certificate_nonce > highest consumed nonce for
    (validator_epoch, escrow_id) in this contract; consumption of this
    certificate records it. Same nonce + same certificate_hash → idempotent
    resubmission (allowed for observability). Same nonce + different
    certificate_hash → REJECT (conflict — this is on-chain equivocation
    evidence, §10).

 9. Only after steps 1–8 pass may settlement effects occur. Escrow state
    transitions remain the ultimate exactly-once guard (terminal
    RELEASED/REVERTED states — BTCP_STATE_MACHINE.md).
```

---

## 7. Cross-VM equivalence table

The SAME semantic certificate (same 346-byte `P`) on every VM:

| VM | P encoding | digest signed | signature family | epoch set source | clock | consumed-key | Notes |
|---|---|---|---|---|---|---|---|
| **EVM (Solidity)** | reconstructed in-contract via `abi.encodePacked` in §2 order (all fixed-width) | `EIP-191(keccak256(P))` | secp256k1 recoverable (ecrecover precompile) | `TrionEpochRegistry` contract: per-epoch `validatorId → (addr, w_j)`, `total_power`, `D_consensus`, registered via epoch-boundary tx | `block.timestamp` | `keccak256(P)` | Wave 2 (Agent G): extend `TRIONOracleV3.submitRouteAttestation` to the canonical field set; keep sorted-distinct-signer batches. Optional local hardening: per-deployment salt registered with the epoch set (documented deviation requires lead sign-off). |
| **EVM (Vyper)** | same packed fields | same | same (Vyper has no ecrecover precompile wrapper — call a tiny Solidity helper or verify via `raw_call` to precompile 0x01) | same registry | `block.timestamp` | same | Wave 2 (Agent L): `BTCP_ESCROW.vy` release() consumes the registry-backed verdict; replaces the static `attestations ≥ 2` floor. |
| **Solana (SVM)** | P as a 346-byte span across instruction data (borsh-free: fixed offsets) | raw `P` | Ed25519 (ed25519 syscall; secp256k1 syscall also available if family 1 ever needed) | `TrionEpochRegistry` account (PDA `["epoch", epoch_be]`), validator entries with 32-byte ed25519 keys + u64 weights | `Clock` sysvar unix seconds | SHA3-256 of P (compute on-chain or store as submitted+verified anchor: Solana has no SHA3 precompile — sha256 syscall + keccak exist; store `certificate_hash` as an oracle-published 32-byte value verified once at ingestion by a secp256k1/ed25519 cross-check, or key the registry on `P`'s SHA-256) | PDA-seeded domain note: the registry PDA derivation string "trion-epoch" + epoch BE is the SVM equivalent of the EIP-712 domain salt. |
| **Move (Aptos/Sui)** | P as `vector<u8>` in entry args | raw `P` | Ed25519 (`std::signature` / `aptos_stdlib` check on published ed25519 pubkey) | `trion_epoch_registry` resource under a dedicated account, table<validator_id, (pubkey, w_j)> | `timestamp::now_seconds()` | SHA3-256 via aptos_stdlib::sha3 (Move has SHA3 in stdlib on Aptos — no drift) | Domain note: the resource account address of the registry is the deployment binding; document in module docs. |
| **TON (TVM)** | P in a dedicated cell: root = `TRION-CERT-V1` cstring + 8 slices of TL fields; verifier rebuilds the exact 346-byte concatenation | raw `P` | Ed25519 (`chksign`) | registry contract: dict(validator_id → (ed25519 pubkey slice, w_j int)) written at epoch boundary by the registrar | `now()` (block creation unix time) | cell hash of the P root (TVM `cell_hash` = SHA3-512 variant — document the deviation; the consumed dict key is the 256-bit root hash) | Domain note: TVM has no keccak/FIPS-SHA3; the canonical `certificate_hash` is computed off-chain by the registrar and stored beside the epoch root. Cell layout must be pinned by `contracts/ton/cell_layout.test.js`-style tests. |
| **Starknet (Cairo)** | P as felt array (12 chunks, §3.2 family 3) | `Poseidon(domain_felt, f_0..f_11)` | STARK-curve ECDSA (`starknet::ecdsa`) | `TrionEpochRegistry` Starknet contract with felt validator entries + stark pubkeys; bridged each epoch by the TRION registrar relayer | block timestamp (unix seconds) | D_stark (felt) | Who bridges: the registrar relayer publishes the epoch set at each boundary (this is the ONE per-epoch on-chain write, not per certificate). Felts are < 2^252; the 31-byte chunking is injective and pinned by golden vectors. |
| **NEAR (Rust)** | P as `Vec<u8>` in method args | raw `P` (ed25519) or `EIP-191(keccak(P))` (secp family) | ed25519 native (`ed25519-dalek` / host) or secp256k1 | `trion_epoch_registry` LookupMap | block timestamp (ns → sec) | SHA3-256 of P (Rust `Sha3_256` — matches canonical hash exactly) | NEAR can compute the canonical hash natively — use it as the consumed key. |
| **PVM (ink!)** | P as `Vec<u8>` | raw `P` (sr25519/ed25519) or secp family if EVM-compat chain | ed25519/sr25519 native in ink! | `validators: Vec<AccountId>` + weights Mapping (extend the existing storage) | pallet timestamp | SHA3-256 via ink! sha3 | The existing `contracts/pvm/legacy_oracle.rs` route storage becomes the registry consumer. |
| **Go validator fleet** | emits P exactly per §2 | family of the destination | signs with the family key from the epoch key material | the DW-BFT engine's own state (`validator/internal/consensus`) | consensus TimestampMs (max(now, parent+1) — monotonic) | n/a (emitter) | Emission integration point: `FinalizedBlock`/quorum path extends to assemble the certificate once Σ-quorum is met. |
| **Rust core** | `rust/src/types.rs` gains `CanonicalCertificate` mirroring §2 (byte-for-byte) | — | — | — | — | — | Static parity tests pin the field set against this doc (same pattern as the BITPIntentData parity tests). |
| **Python core** | `core/consensus/certificate.py` — THE reference encoder | computes all three digests | — | reads `core/spiritual` consensus outputs | `issued_at` from consensus time | `certificate_hash` | Golden vectors in `tests/unit/test_certificate_domain_separation.py` are the cross-VM conformance anchor. |

**Bridging rule:** only TWO things ever cross VM boundaries per epoch: the
epoch-set registration (validator ids, family pubkeys, weights, totals) and
the certificates themselves. Both are pure data; no VM trusts another VM's
execution. The registrar (a TRION-controlled relayer role, auditable on the
TRION chain) is the single writer of epoch registrations — one tx per epoch
per chain, gas-bounded, signed by the TRION consensus itself.

---

## 8. Replay rules

### 8.1 Nonce scope

```
certificate_nonce : strictly increasing per (validator_epoch, escrow_id)
```

- Validators refuse to sign nonce n+1 ≤ highest signed n for the same scope
  (emission-side guard; a violation is equivocation evidence).
- Verifiers enforce: consumed_nonce[(epoch, escrow_id)] < nonce
  (monotonic), i.e. a re-attestation (e.g. after ttl expiry) must carry a
  higher nonce; replaying an older certificate after a newer one was consumed
  fails step 8.
- The certificate nonce is INDEPENDENT of the §4.1 per-entity intent nonce
  (different scopes, both exist, both are monotonic).

### 8.2 Consumed-certificate tracking

- First successful settlement consumption records the certificate (per-VM
  consumed-key of §7). Idempotent resubmission of the SAME certificate
  (same certificate_hash) is allowed (observability, retry safety) but has no
  settlement effect — the escrow state machine is the exactly-once guard.
- Same (epoch, escrow, nonce) with a different hash = conflict → reject and
  emit an equivocation-evidence event (feeds §10 slashing).

### 8.3 What the firewalls prevent (cross-VM)

| Attack | Firewall |
|---|---|
| replay cert on another chain | `dest_chain` ≠ that chain → step 7 |
| replay cert on another VM | family mismatch → step 1 |
| replay cert on another escrow (same chain) | `escrow_id` → step 7 |
| replay cert for another route/intent | `route_id`/`intent_hash` → step 7 |
| substitute a fresh verdict onto a stale escrow | settlement tuple + nonce scope → steps 7–8 |
| double-release the same escrow | escrow terminal states + consumed nonce |
| use a retired validator set | epoch registry + grace → step 2 |
| use a slashed-but-unrotated validator | epoch-boundary rotation (≤ 1 epoch residual, §10) |
| strip the TTL by resubmitting late | freshness → step 3 |
| cross-protocol signature theft | `domain_tag` → §3.3 |

---

## 9. Freshness rules

### 9.1 Semantics

```
issued_at : unix seconds, TRION consensus clock at emission
            (Go engine proposal timestamps: max(now, parent+1) — monotonic
            median of validator time; the certificate's time is CONSENSUS
            time, not a single host's wall clock)
ttl       : seconds until expiry, set at emission from the value tier

valid     iff   issued_at ≤ now ≤ issued_at + ttl     (now = VM clock, §7)
```

Clock sources per VM are listed in §7. Verifiers apply
`clock_drift_tolerance` (default 60s) to the LOWER bound only (a slightly
future-dated certificate from consensus-time skew is tolerated; an expired
one never is).

### 9.2 Value-tier TTL (A3 resolution, portable form)

The A3 certification windows are defined in BLOCKS of the anchor chain
(`core/btcp/modules.py:92-97`, `rust/src/btcp_proof_builder.rs:17-22` — note
the two tables disagree today; see audit finding H-06). Blocks are not
portable across VMs; the canonical TTL is in SECONDS:

| value (USD equivalent at emission) | canonical ttl |
|---|---|
| < $1,000 | 3,600 s (1 h) |
| < $100,000 | 86,400 s (24 h) |
| < $10,000,000 | 259,200 s (3 d) |
| ≥ $10,000,000 | 604,800 s (7 d) |

Rationale (ED-A3): risk-scaled validity mirroring the A3 intent (larger
value → deeper reorg-protection window), converted at the 12 s EVM block
cadence and clamped to a one-week maximum so that no certificate outlives a
full epoch-rotation cycle (§10). The anchor-side depth requirement (≥ tier
blocks on the ANCHOR chain before emission) remains an emission-side,
off-chain check. The EVM 300 s verdict-freshness discipline
(`BTCP_ROUTE_FRESHNESS_SECONDS`) is retained as an escrow-DEPLOYMENT-local
tightening (verifiers may always require a SHORTER window than ttl, never a
longer one).

---

## 10. Validator epochs and rotation

### 10.1 Epoch definition (ED-E1 — the spec never fixes a length)

The specs use "epoch" as the base time unit everywhere (diversity recomputed
every epoch, L4.2; G1 key rotation every 365 epochs, G5 recombination every
30 epochs, L4.3-4.6; dispute windows 3–14 epochs, L4.9; recovery thresholds
7–365 epochs, L2/L8) but never define its length. Derived constraint set:
the V2 dispute flow is "72-hour challenge window" while L4.9 gives 7–14
epochs for the same windows → 1 epoch ≈ 5–10 hours; with 365-epoch key
rotation landing on a ~quarterly horizon and 30-epoch recombination on ~1
week.

**Decision: 1 validator_epoch = 6 hours of TRION-BFT consensus wall time
(governance-parameterizable: `epoch_seconds`).** Consequences: dispute
windows 7–14 epochs = 42–84 h (brackets the V2 72 h); G5 recombination ≈
7.5 days; G1 rotation ≈ 91 days; L2 R4 transmigration 365 epochs ≈ 91 days.
`validator_epoch` itself is an opaque uint32 counter — verifiers never
compute it from time, they read the registry.

### 10.2 Registration and rotation

- At each epoch boundary the registrar publishes to every integrated chain:
  `epoch → { validator entries (id, family pubkeys, s_j, d_j),
  total_effective_power, D_consensus, hhi, geographic summary }` plus the
  epoch-set root `SHA3-256("TRION-EPOCHSET" || epoch || canonical entries)`.
- Validator-set changes (join/leave/slash-evict/HHI caps/key rotation) take
  effect ONLY at epoch boundaries; mid-epoch events mark the validator
  ineligible from the NEXT epoch.
- Verifier grace: certificates from epochs older than
  `latest_registered − grace` (default 2) are rejected (step 2) — bounds the
  residual window in which a just-slashed validator's signatures still
  verify (≤ 1 epoch + ttl overlap, ≤ ~10 h by default; documented residual
  risk R-1, see audit).

### 10.3 Slashing interplay (L4.9)

- **Equivocation / double signing** — one validator producing two different
  signature payloads for the same `(validator_epoch, escrow_id, nonce)` (any
  family): L4.9 S1 double signing (100% + eviction) and/or V2
  COORDINATED_ATTACK_CONFIRMED (50% + permanent exclusion) for false
  attestation. On-chain conflict events from §8.2 are admissible evidence;
  both conflicting signatures are self-authenticating (the
  `validator/internal/consensus/slashing.go` evidence model).
- **Diversity fraud** (forged M_j → forged d_j): L4.9 S3, 50%.
- **False cross-chain attestation** (a quorum certifying a false state):
  COORDINATED_ATTACK_CONFIRMED per V2 L4.9; the Coordination Collapse
  Theorem (BTCP §12.2) is the economic backstop.
- Disputes follow the V2 flow (72 h window, 3 validators + human council,
  evidence permanently logged in the Akashic Index).

---

## 11. Mapping to existing structures (conformance deltas)

| Existing structure | Field(s) | Canonical location | Delta for the owner |
|---|---|---|---|
| `BTCPProof` (rust `types.rs:404-414`, py `modules.py:68-78`) | anchor_bh, consensus_proof, intent_hash, btcp_route_id, anchor_chain, execution_chain, btcp_version, feature_flags, min_verifier_ver | all bound in P except flags/verifier-ver (envelope) | Wave 1/B+2: add `CanonicalCertificate` alongside; deprecate `BTCPProof` as the cross-chain artifact |
| `ConsensusProof` (rust `types.rs:395-400`, py `modules.py:37-42`) | validator_signatures, diversity_cert, coherence_score, threshold/margin | envelope + P fields | diversity_cert.d_j → envelope weights cross-checked vs registry; margin → derived |
| `DiversityCertificate` (rust `types.rs:386-391`) | hhi, num_validators, weights, block_number | P (hhi, validator_count) + registry (weights) | block_number replaced by issued_at (seconds, portable) + validator_epoch |
| `TRIONOracleV3` route verdict (`routeVerdictHash`:170-188) | chainid, this, routeId, anchorBH, executionBH, coherence, threshold | P adds escrow_id, intent/entity, settlement tuple, epoch, nonce, ttl, hhi, awa, power, version, kind; drops `address(this)` (§2.3) | Agent G extends the digest to the canonical field set in a V4 entrypoint |
| `submitRouteAttestation` (V3:260-341) | sorted distinct ECDSA batches, idempotent, fail-closed | becomes the canonical consumption path + registry checks | keep the batch discipline verbatim — it is already canonical-grade |
| Go `Vote.SignBytes` (`types.go:205-213`) | type, height, round, blockhash, validator_address | stays INTERNAL to TRION-BFT (chain-internal consensus votes are not cross-chain certificates) | add the domain tag "TRION-VOTE-V1" + chain id to kill cross-network vote replay (audit M-02) |
| `ValidatorSignatureAggregator` (`signature_aggregation.py`) | Schnorr per-signer challenge over caller message | signs P for family-1 digests in the py reference path | keep for aggregation analytics; the canonical verify is per-signer |
| Signal object (V2 Part 5) | timestamp, ttl, validator_count, validator_hhi, bootstrap_phase | issued_at, ttl, validator_count, hhi_at_emission; bootstrap via emission out-of-band flag | n/a (spec-level) |

---

## 12. Spec provenance and conflict resolutions

Normative inputs (per the master worklog hierarchy):

1. **MD whitepaper** — TRION-BFT 2/3 diversity-weighted (§6/L2.1); BH
   domain-separation pattern incl. version+nonce (L0.1); AWA freeze (§17);
   formula appendix `w_j_effective = s_j · d_j`.
2. **V2 whitepaper** — L4.1-4.2 DW-BFT + dynamic window; L4.8 HHI tiers;
   L4.9 slashing + dispute flow (72 h); Part 5 signal object
   (timestamp/ttl/validator_count/validator_hhi); §9.2 100 validators /
   4 continents.
3. **BTCP_SPEC** (governs BTCP absolutely) — §4.1 intent; §4.2 Step 3
   `BTCPProof`/`ConsensusProof`; Step 6 `BTCPRouteSignal`; §12.2 Coordination
   Collapse (`w_j_effective = s_j · d_j`); §12.4 `BTCP_route` (binds
   entity_id + execution_BH + "validator signatures on route").
4. **L4 layer spec** — quorum formula + TIERS (L4.2), effective power P_j
   (L4.1), epoch-scoped recomputation, slash registry S1–S6.
5. **novel_primitives P3** — quorum formula + invariants (diversity
   recomputed every epoch).

Conflicts resolved (documented per the hierarchy rule "MD > V2 semantics;
BTCP_SPEC governs BTCP absolutely"):

- **C-1 signing payload:** BTCP_SPEC §4.2 Step 3 sketch says
  `sign_j(anchor_BH)`; §12.4 says "validator signatures on route". RESOLVED:
  sign the full canonical payload P (route ⊇ anchor_BH — binding more is
  strictly stronger; §12.4 is the security-theorem section and wins over the
  inline sketch).
- **C-2 effective power:** `s_j · d_j` (MD appendix, BTCP §12.2) vs
  `s_j · (1 + δ·d_j)` (L4.1, P3). RESOLVED: `s_j · d_j` for certificates
  (hierarchy levels 1/3 agree; the bonus form is chain-internal).
- **C-3 quorum shape:** continuous `2/3 + ε_div(1−D)` (L4.2, P3) vs tier
  table 2/3 | 0.75 | 0.85 (L4.2). RESOLVED: tiers (normative
  discretization, always ≥ continuous; both live in the same L4.2).
- **C-4 slashing registry:** V2 five-condition table vs L4.9 S1–S6.
  RESOLVED: union applies; for certificates the operative conditions are
  S1/COORDINATED_ATTACK (equivocation, §10.3).
- **C-5 epoch length:** undefined everywhere. RESOLVED: ED-E1 (6 h,
  parameterizable, derived from the dispute-window constraints).
- **C-6 freshness units:** blocks (A3/CERT_WINDOWS, py+rust — which also
  disagree with each other) vs seconds (V2 signal ttl). RESOLVED: canonical
  seconds (§9.2) since blocks are not VM-portable.

Engineering decisions: ED-DS1 (domain tag), ED-K1 (kind), ED-E2 (epoch
bound), ED-N1 (nonce scope), ED-B1/B2 (explicit escrow + settlement tuple),
ED-Q1 (power bound), ED-A1 (AWA bit), ED-X1–X5 (exclusions, §2.3), ED-E1
(epoch length), ED-A3 (second-based TTLs), ED-G (grace = 2 epochs).

---

## 13. Reference implementations and Wave 2 obligations

- **Python reference (normative for byte layout):** `core/consensus/
  certificate.py` — `CanonicalCertificate.encode_payload()` (346 bytes),
  `certificate_hash()`, `evm_digest()`, `stark_felt_digest_chunks()`,
  structural verification, tiered quorum check, golden vectors in
  `tests/unit/test_certificate_domain_separation.py`. Every VM
  implementation MUST match these bytes exactly.
- **Wave 2 VM custodians** implement §3.2 (family digests), §6
  (verification), §8 (consumed tracking), §10.2 (epoch registration), per
  the file:line work order in `docs/audit/VALIDATOR_SECURITY_AUDIT.md`.
- **Go fleet** (post-Wave 2): emission integration in the DW-BFT engine
  (assemble P at quorum, sign with family keys, gossip the envelope).
- **Rust core:** static `CanonicalCertificate` twin of §2 with parity tests
  (Agent B's BITPIntentData parity-test pattern).

---

## 14. Open items (unresolved, tracked)

1. **Starknet Poseidon vs Pedersen for D_stark** — fixed per deployment
   family in §3.2 but the felt-hash choice needs a Cairo cost benchmark
   before Wave 2 freezes it (Agent K decision).
2. **Per-deployment binding for EVM** — the canonical payload deliberately
   omits `address(this)` (§2.3). If Wave 4 red-team demonstrates a same-chain
   fake-deployment data-integrity exploit that matters, the fix is an
   EIP-712-style deployment salt registered WITH the epoch set (one extra
   32-byte parameter to the EVM verifier, not a payload change).
3. **BLS aggregation** — per-signer ECDSA/Ed25519 is ~65–64 bytes × quorum
   (~67 of 100 validators ≈ 4.4 KB per certificate on-chain). BLS
   aggregation would compress this; deferred (no BLS precompile on most
   target VMs; the envelope format already leaves room for an
   aggregate-signature family 4).
4. **Bootstrap certificates** — during `D(t) < D_minimum` the 7-of-12
   multi-sig fallback (L2.1/L4.7) uses the same payload with a distinct
   `certificate_kind = 2` (proposed) — needs a Wave 2 governance decision
   before first mainnet emission.
5. **SR25519 family for PVM** — ink!'s native sr25519 is not ed25519; either
   add family 5 (sr25519) or standardize PVM on ed25519 — Agent J (PVM) to
   pick during Wave 2.
