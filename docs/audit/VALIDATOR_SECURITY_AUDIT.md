# Validator / Certificate Security Audit — Current State vs the Canonical Certificate

**Status:** AUDIT FINDINGS REGISTER (Wave 1, Agent E)
**Audited at:** initial pass at HEAD f91a19b; line citations re-verified
against HEAD 3f6ce2e after the sibling Wave 1 commits (A's spec matrix, B's
canonical BH + golden vectors, F's BTCP invariants) landed mid-audit —
F's INV-012 quorum-claim hardening is reflected in §2.2 and H-04.
**Normative reference:** `docs/protocol/CANONICAL_CERTIFICATE.md` (§ refs below
point at that document). Spec cites: WHITEPAPER_MD.txt (MD), WHITEPAPER_V2.txt
(V2), BTCP_SPEC.txt (BTCP), L4_spiritual_security.md (L4), novel_primitives.md
(P3), DD_REPORT.txt (DD).
**Purpose:** the Wave 2 work order. Each finding names the exact file:line, the
severity, and the remediation the owning VM custodian must implement. Nothing
here was edited — contracts/, core/btcp/, rust/src are Wave 2 / Agent F/B
territory; this register only READS them.
**Severity scale:** CRITICAL (funds loss / consensus forgery), HIGH (security
guarant broken but gated elsewhere), MEDIUM (spec non-conformance / weak
default), LOW (hardening), INFO (documentation/hygiene).

---

## 1. Executive summary

- The EVM tier (TRIONOracleV3 + BTCPEscrow) is the ONLY tier where a release
  is gated by **cryptographically verified validator signatures** with a
  **live-set-derived quorum**. It is the closest existing system to the
  canonical certificate and the natural template for Wave 2.
- Every OTHER VM tier (Vyper floor-2, Move relayer flag, TON caller coherence,
  Starknet/Cairo caller coherence, SVM single oracle key, NEAR/PVM owner
  write) releases on **trusted-relayer authority** — the exact class the DD
  report flagged as C2 ("release trusts a relayer-supplied coherence number").
- **No implementation anywhere binds a validator epoch**, so every attestation
  path accepts a historical validator set indefinitely (finding H-01 — the
  single largest gap the canonical certificate closes).
- **No implementation binds the settlement tuple (destination, amount)** into
  the signed payload; the EVM tier compensates with the escrow-state binding
  (`anchorBH == escrowId`), the other tiers have no compensation.
- Quorum is count-based everywhere (`⌈2n/3⌉` at best); the spec's
  diversity-weighted quorum with D_consensus tiers (L4.2) is computed in the
  math engines (py/Go) but never enforced at any consumption point.
- The Python core signs `intent_hash || pubkey` — no chain, escrow, epoch,
  nonce, or version in the payload (finding H-02): cross-chain/cross-escrow
  signature reuse is possible in the py reference path. (Upstream during this
  audit, Agent F's INV-012 fix closed the *prover-chosen quorum* half of the
  py verify path — count-based 2/3 floor now recomputed; H-04's py leg is
  downgraded accordingly, the payload and weight issues remain.)
- Rust `verify_proof` is structural-only (honestly disclosed in-source); the
  proof carries its own threshold (H-03).
- py and rust DISAGREE on the certification windows (H-06) and the EVM
  HashDNA library uses keccak where the canonical hash is FIPS SHA3-256
  (H-07).

Top 5 gaps Wave 2 must close (details in §5):
1. Epoch binding + epoch registration on every VM (H-01).
2. Canonical signed payload on every VM — replace intent-only / caller-value
   / relayer-flag authority (H-02, C-02, C-03, C-04, C-05, C-06, C-07).
3. Diversity-weighted quorum from registered state, not counts or floors
   (H-04, M-06).
4. Settlement-tuple + nonce binding with consumed-certificate tracking
   (H-05, M-04).
5. Fail-closed verification order incl. HHI/AWA preconditions and no
   weak-oracle fallbacks (M-01, M-02, M-05).

---

## 2. Consensus/certificate state per implementation

### 2.1 Python spiritual plane (DW-BFT math + signature layer)

| Aspect | Current state | File:line |
|---|---|---|
| d_j computation | `d_j = 1 − corr(M_j, M̄)`, effective `s_j·d_j` — matches spec | core/spiritual/consensus.py:112-139 |
| Quorum | plain `honest_eff > (2/3)·total` — the L4.2 tier table (0.75/0.85 at low D) is NOT implemented | core/spiritual/consensus.py:228-231 |
| HHI | 0-10000 scale, 4 tiers, matches L4.8 | core/spiritual/consensus.py:157-171, 239-246 |
| Signatures | Schnorr-MuSig on secp256k1, challenge `H("TRION-SCHNORR-v1"‖R‖M‖pk)` — M is CALLER-SUPPLIED, no chain/escrow/epoch/version in M | core/spiritual/signature_aggregation.py:167-174 |
| Quorum helper | `threshold_met(signer_count, total, quorum_fraction=2/3)` — COUNT-based, `quorum_fraction` is a caller parameter | core/spiritual/signature_aggregation.py:405-411 |
| Validator registry | SQLite validators; `address` is an unvalidated string; NO public keys, NO epoch, stake is a float | core/spiritual/validator_registry.py:70-102 |
| Epochs | absent everywhere | — |

### 2.2 Python BTCP proof builder (the py certificate path)

| Aspect | Current state | File:line |
|---|---|---|
| Proof fields | anchor_bh, consensus_proof, intent_hash, route_type, certification_block, certification_expiry, validator_key_version (4B) | core/btcp/modules.py:69-77 |
| Signed message | `msg = intent_hash ‖ pub` — binds intent + signer only. NOT bound: chain, escrow, route, entity, destination, amount, epoch, nonce, version, ttl | core/btcp/modules.py:373-382 (msg at 381) |
| Quorum | `DEFAULT_QUORUM_FRACTION = 2/3`; `threshold`/`quorum_fraction`/`total_validators` are CALLER-supplied parameters of build_consensus_proof | core/btcp/modules.py:328, 330-349, 367-372 |
| Verification | real aggregate EC verify over reconstructed messages + INV-012 quorum recompute: the proof dict's `threshold_met`/`quorum_fraction` are treated as claims and the count-quorum is RE-CHECKED against `max(claimed, 2/3)` — forged `{threshold_met: true, total_validators: 1}` no longer verifies (upstream fix by Agent F, commit b160ba4). Still COUNT-based — no weights, no L4.2 tiers. | core/btcp/modules.py:407-462 (INV-012 at 436-450) |
| Structural verify | shape-only (≥3 sigs, 65B, distinct ids, HHI ≤ 0.5 after scale normalize, coherence > 0, margin ≥ 0, expiry) — honest disclosure that crypto is on-chain's job | core/btcp/modules.py:277-318 |
| Freshness | value-tier windows in BLOCKS: (1k→10k, 100k→50k, 10M→200k, ∞→500k) | core/btcp/modules.py:92-104 |

### 2.3 Rust core (static verification only — no cargo in sandbox)

| Aspect | Current state | File:line |
|---|---|---|
| Structs | `WeightedSignature{validator_id, signature, stake_weight, diversity_weight}`, `DiversityCertificate{hhi, num_validators, weights, block_number}`, `ConsensusProof{validator_signatures, diversity_cert, coherence_score, threshold}`, `BTCPProof{anchor_bh, consensus_proof, intent_hash, btcp_route_id, anchor_chain, execution_chain, btcp_version, feature_flags, min_verifier_ver}` — the closest struct set to the spec's §4.2 | rust/src/types.rs:377-414 |
| Verification | structural only, best outcome `UnverifiedSignatures` (honest disclosure) | rust/src/btcp_proof_builder.rs:38-86, 184-231 |
| Threshold | `coherence_score < threshold` where `threshold` is a FIELD OF THE PROOF — the proof carries its own pass bar | rust/src/btcp_proof_builder.rs:195, types.rs:399 |
| Windows | (0→50k, 10k→100k, 100k→200k, 1M→500k) blocks — DISAGREES with the python table | rust/src/btcp_proof_builder.rs:17-22 vs core/btcp/modules.py:92-97 |
| Route id | `sha3(anchor‖intent‖route_type‖block)` — deterministic, unbound to chains/escrow | rust/src/btcp_proof_builder.rs:118-127 |
| Weights | carried in `WeightedSignature` (envelope) — never cross-checked against a set | rust/src/types.rs:377-382 |

### 2.4 Go validator fleet (TRION-BFT engine + mesh)

| Aspect | Current state | File:line |
|---|---|---|
| Consensus votes | ed25519 over `SignBytes = (type, height, round, blockhash, validator_address)` — NO domain tag, NO chain id, NO epoch → votes replay across TRION networks | validator/internal/consensus/types.go:194-221 |
| Quorum | STRICT `3·power > 2·total`, integer, weighted by `s_j·d_j` — the strongest quorum check in the repo | validator/internal/consensus/engine.go:5-8, 58 |
| Equivocation | detected, evidence broadcast, slashing enforcer wired (L4.9 S1 model) | validator/internal/consensus/slashing.go:51-153 |
| Attestations | `BehavioralAttestation` — `DiversityWeight` is INSIDE the attestation (self-reported by the attester); "signature" is the dual-strand hash (tamper-evidence, NOT authentication — anyone can produce it for any payload) | validator/internal/p2p/types.go:79-90 |
| Mesh quorum | `agreedWeight/totalWeight ≥ 2/3` where agreedWeight sums the SELF-REPORTED attestation weights; received attestations are never signature-verified before counting | validator/internal/p2p/mesh.go:104-146 |
| HTTP consensus | `ConsensusMessage.Signature` field exists but `handleConsensusSubmit` never verifies it; `volatility` is a URL parameter | validator/internal/p2p/consensus.go:290-336 |
| HHI/AWA | 4 tiers, freeze at HHI>4000 sets `SignalsFrozen`/`AWAEnforced=false` — matches V2 L4.8 | validator/internal/p2p/consensus.go:254-266, 440-465 |
| Epochs | absent (heights/rounds only) | — |

### 2.5 EVM (Solidity) — TRIONOracleV3 + BTCPEscrow (the reference tier)

| Aspect | Current state | File:line |
|---|---|---|
| Attestation digest | `keccak256(chainid, address(this), routeId, anchorBH, executionBH, coherenceScore, thresholdScore)` EIP-191-wrapped — chain + deployment bound (no cross-chain/deployment replay) | contracts/solidity/TRIONOracleV3.sol:164-188 |
| Signature check | ECDSA recover, sorted-distinct batch, registered-validator membership, one bad sig fails the batch (fail-closed) | contracts/solidity/TRIONOracleV3.sol:260-341 |
| Quorum | `max(2, ⌈2/3·validatorCount⌉)` DISTINCT validators — count-based, live-set-derived (NOT owner-settable below floor) | contracts/solidity/TRIONOracleV3.sol:146-154 |
| Escrow binding | `anchorBH == escrowId` (H1 route-spoof fix) + isSafe + dynamic quorum + 300 s freshness + coherence ≥ minCoherence AND ≥ oracle threshold | contracts/solidity/BTCPEscrow.sol:222-268 |
| Freshness | `BTCP_ROUTE_FRESHNESS_SECONDS = 300`; only NEW distinct attestors refresh timestamp (M2 fix) | contracts/solidity/TRIONOracleV3.sol:99-101, 320-326 |
| Replay | idempotent per (routeId, signer) mapping; escrow state machine terminal states | TRIONOracleV3.sol:127-128; BTCPEscrow.sol:429-459 |
| Validator set | owner-administered `addValidator` — no stake, no weights, no epoch, no slash; governance trust root is DOCUMENTED in-source | contracts/solidity/TRIONOracleV3.sol:553-579 |
| Legacy path | `publishSignal` uses the STATIC `quorumRequired` (default 2, owner-set) — the DD "quorum 2" class survives on the thermodynamic-signal path | contracts/solidity/TRIONOracleV3.sol:66, 475-499, 580-587 |
| Fallback | `_consensusGate` catches a missing `minRouteAttestations()` view and falls back to floor 2 — DD-flagged fallback class, documented as trusted-oracle-assumption | contracts/solidity/BTCPEscrow.sol:249-263 |
| Trusted-relayer mode | oracle unbound → caller-supplied coherence accepted (dev-only opt-out, disclosed) | contracts/solidity/BTCPEscrow.sol:227-229, 408-412 |
| NOT bound in digest | escrow-dest tuple, intent/entity, epoch, nonce, ttl, hhi, awa, protocol version, signature-family/version | §2 gaps → findings |

### 2.6 Per-VM escrow/oracle tiers (Wave 2 targets)

| VM | Release authority today | Quorum today | Oracle binding today | File:line |
|---|---|---|---|---|
| Vyper (EVM) | permissionless `release()` | STATIC `attestations ≥ 2` — no dynamic quorum call, no weights | routeBinding: anchor_bh==escrow_id, is_safe, 300 s, coherence ≥ threshold | contracts/vyper/BTCP_ESCROW.vy:136-177 |
| Solana (SVM) | `oracle` Pubkey when bound (single key), else owner | none | single key authority — no signatures, no set, no freshness | contracts/svm/programs/btcp_escrow/src/lib.rs:34-63, 130-132 |
| Move | relayer + `esc.coherence_verified` flag set by the relayer off-chain check | none | NONE — relayer calls `verify_coherence` to set the flag | contracts/move/sources/btcp_escrow.move:120-138, 196-207 |
| TON | relayer/owner op 0x02 | none | coherence is a CALLER-SUPPLIED message field; oracle.fc verdicts are owner-written, `add_validator` is a no-op | contracts/ton/escrow.fc:238-269; contracts/ton/oracle.fc:105-160 |
| Starknet (starknet/) | relayer/owner | none | CALLER-SUPPLIED coherence u64 | contracts/starknet/src/btcp_escrow.cairo:291-336 |
| Cairo (cairo/) | registered-validator caller (msg.sender) | none — single validator can publish signals | none (owner/validator write path) | contracts/cairo/src/trion_execution_gate.cairo:146-165 |
| NEAR | owner write | none | none (publish_btcp_route is an owner call) | contracts/near/src/trion_oracle.rs:61-95 |
| PVM (ink!) | owner/validator write | none | none (route storage only) | contracts/pvm/legacy_oracle.rs:1-30 |
| Solidity (ExecutionGate) | quorum signatures + AWA freeze | configured `quorumRequired` vs live `validatorCount` (⌈2n/3⌉ check) | `keccak256(chainid, this, entityId, packedData)` — but `beoHash/daProofHash/storageRoot` are NOT in the digest | contracts/solidity/TRIONExecutionGate.sol:319-344, 239-252 |
| BEOAttestation.sol | single `attester` key writes BEO identity | none | none | contracts/solidity/BEOAttestation.sol:9-13, 43 |

---

## 3. Findings register

### CRITICAL

| ID | Finding | Where | Severity | Remediation (Wave 2 owner) |
|---|---|---|---|---|
| C-01 | **TON escrow releases on caller-supplied coherence with no oracle consultation at all** — the relayer/owner message body carries `coherence[64]`; nothing on-chain checks any verdict, quorum, freshness, or binding. Any authorized key can release any escrow at any coherence claim. | contracts/ton/escrow.fc:238-269 (esp. 241-244, 258) | CRITICAL | Agent J: implement §6 verification in escrow release — op 0x02 must carry the canonical envelope; verify Ed25519 family sigs against the epoch registry dict; add escrow settlement-tuple + nonce checks. Until then, mainnet TON escrow must not hold value. |
| C-02 | **Move escrow release depends on a relayer-set boolean** (`esc.coherence_verified`), flipped by `verify_coherence(relayer, …)` with zero on-chain verification. Trusted-relayer is the ONLY mode; there is no oracle binding to upgrade to. | contracts/move/sources/btcp_escrow.move:120-138, 196-207 | CRITICAL | Agent I: replace the flag with canonical certificate verification (Ed25519 family over raw P; `std::signature`/ed25519 check against the epoch registry resource); keep the flag only behind an explicit dev-only feature. |
| C-03 | **SVM escrow binds a single oracle Pubkey as release authority** — one key, no signature set, no quorum, no freshness, no epoch. Compromise of that key = unilateral release of all SVM escrows. | contracts/svm/programs/btcp_escrow/src/lib.rs:34-63, 130-132 | CRITICAL | Agent H: replace `is_release_authority` oracle-key gate with certificate verification (ed25519 syscall over P; epoch registry PDA); oracle key may remain as a PAUSE authority only. |
| C-04 | **Starknet (starknet/) and Cairo (cairo/) escrows release on caller-supplied coherence under relayer/owner (or single-validator) authority** — no signatures, no quorum, no binding, no freshness. | contracts/starknet/src/btcp_escrow.cairo:291-336; contracts/cairo/src/trion_execution_gate.cairo:146-165 | CRITICAL | Agent K: implement family-3 verification (felt chunking + Poseidon domain felt + starknet::ecdsa) per CANONICAL_CERTIFICATE §3.2/§7; bridge the epoch set via the registrar; escrow checks the full §6 sequence. |
| C-05 | **NEAR and PVM oracles are owner-write route stores** — `publish_btcp_route` has no signatures/quorum; the "TRION consensus is the only oracle" invariant is absent on these VMs. | contracts/near/src/trion_oracle.rs:92-95; contracts/pvm/legacy_oracle.rs:18-30 | CRITICAL (NEAR), MEDIUM (PVM — no funded escrow consumer yet) | Agent J/I: port the V3 submitRouteAttestation discipline (ed25519 or secp family per §7) + epoch registry; escrows verify §6. |
| C-06 | **Go mesh counts self-reported diversity weights from unauthenticated attestations** — `tryQuorum` sums `att.DiversityWeight` (a field of the attacker-supplied attestation) and never verifies any signature on gossip receipt; `handleConsensusSubmit` ignores `ConsensusMessage.Signature`. Quorum forgery = sending 3 crafted attestations. | validator/internal/p2p/mesh.go:104-146; validator/internal/p2p/consensus.go:290-336 | CRITICAL (fleet-internal; the mesh feeds the attestations the EVM oracle's off-chain pipeline aggregates) | Fleet (post-W2): count only registry weights (§5), verify dual-strand+ed25519 on receipt, bind attestations to the epoch set. |

### HIGH

| ID | Finding | Where | Severity | Remediation |
|---|---|---|---|---|
| H-01 | **No epoch binding anywhere** — no implementation (py, rust, Go, EVM, or any VM) binds a validator epoch into the attestation or verifies against an epoch-scoped set. A retired/slashed/rotated validator set remains valid indefinitely; `validator_key_version` (py, 4B) and `min_verifier_ver` (rust SemVer) are caller-supplied and never checked against a registry. | core/btcp/modules.py:77, 118; rust/src/types.rs:413; contracts/solidity/TRIONOracleV3.sol:553-579 | HIGH | ALL Wave 2 agents: add `validator_epoch` (uint32) to the signed payload, deploy the per-epoch registry (§10.2), enforce registry membership + grace in §6 step 2. This is the top Wave 2 work item. |
| H-02 | **Python consensus-proof signing payload is `intent_hash ‖ pubkey` only** — a signature verifies for the same intent on ANY chain, ANY escrow, ANY route, ANY VM, ANY protocol version (no domain tag, no destination/amount, no nonce/ttl). Cross-context signature reuse is possible in the py reference path. | core/btcp/modules.py:373-380 (and the verifier reconstruction 432-441) | HIGH | Replace with the canonical 346-byte P (`core/consensus/certificate.py` is the reference); py `build_consensus_proof` becomes an emission helper over P. |
| H-03 | **Rust proof carries its own threshold** — `verify_proof` checks `coherence_score < threshold` where `threshold` is a ConsensusProof FIELD chosen by the builder; a malicious prover sets threshold low. Python mirrors it (`threshold_margin < 0` computed from builder-supplied threshold). | rust/src/btcp_proof_builder.rs:195; rust/src/types.rs:399; core/btcp/modules.py:297, 143 | HIGH | Threshold must come from canonical state (registered Θ(t) per epoch), not the proof: bind `threshold` in P AND cross-check against the registry's epoch threshold (§6 step 4). |
| H-04 | **Quorum is count-based everywhere; diversity-weighted tier quorum is never enforced at consumption.** Spec L4.2 (weights + D_consensus tiers) exists only in the math engines (consensus.py, Go ComputeSigma). V3's `⌈2n/3⌉` counts validators with equal weight; py build side still accepts caller quorum fractions (the py verify path now enforces a 2/3 count floor — INV-012, Agent F); Vyper floors at 2. | contracts/solidity/TRIONOracleV3.sol:151-154; core/btcp/modules.py:328-349, 436-450; core/spiritual/signature_aggregation.py:405-411; contracts/vyper/BTCP_ESCROW.vy:171; core/spiritual/consensus.py:228-231 | HIGH | All VMs: quorum from registered `w_j = s_j·d_j` (×1e6, uint64) with L4.2 tier integer checks (§5.2). The EVM registry makes this a straight upgrade of minRouteAttestations → weight check. |
| H-05 | **Settlement tuple (destination, amount) is not in any signed payload.** EVM compensates via escrow-state binding (anchorBH==escrowId); Vyper also binds via escrow state; the other VMs bind nothing. Escrow-substitution is closed only on the tiers that already check escrow state — and only there. | EVM digest TRIONOracleV3.sol:170-188; py modules.py:373-380 | HIGH | Bind destination+amount in P (§2, ED-B2) and check against escrow state (§6 step 7) on every VM. |
| H-06 | **py and rust certification windows disagree** (py: <1k→10k, <100k→50k, <10M→200k, else 500k blocks; rust: 0→50k, 10k→100k, 100k→200k, 1M→500k) and both are block-denominated (not VM-portable). | core/btcp/modules.py:92-97 vs rust/src/btcp_proof_builder.rs:17-22 | HIGH (cross-VM conformance) | Adopt the canonical second-based TTL table (§9.2); delete both block tables in favor of the shared constant (Wave 2 F for py/rust owners). |
| H-07 | **EVM HashDNA library hashes with `keccak256` while the canonical cross-language BH is FIPS SHA3-256** (py hashlib.sha3_256, rust `Sha3_256`, Go meshsha3) — the on-chain "behavioral hash" will not match the off-chain canonical BH for the same event, breaking the BH cross-verification invariant at the EVM boundary. | contracts/solidity/libraries/HashDNA.sol:8-44 vs core/primitives/behavioral_hash.py:57-60; rust/src/types.rs:5, 33-34; validator/internal/p2p/meshsha3 | HIGH | Agent G: pin the EVM-side digest choice per CANONICAL_CERTIFICATE §3.2 (EVM family digest = keccak of P — intentional, documented); HashDNA.sol must either (a) take the canonical BH as INPUT (compute off-chain, verify on-chain) or (b) document itself as the EVM-native variant with a bridged mapping. NEVER mix: `anchor_bh`/`execution_bh` submitted to EVM contracts must be the canonical (FIPS) BH values produced off-chain. |
| H-08 | **ExecutionGate signs only (chainid, this, entityId, packedData)** — `beoHash`, `daProofHash`, `storageRoot` are submission parameters NOT covered by the validator signatures; the submitting validator chooses them freely after the quorum signed. | contracts/solidity/TRIONExecutionGate.sol:319-344 | HIGH | Agent G: fold the full tuple into the digest (or migrate the gate onto the canonical certificate payload; §11 mapping). |

### MEDIUM

| ID | Finding | Where | Severity | Remediation |
|---|---|---|---|---|
| M-01 | **Static `quorumRequired` (default 2) on the V3 legacy `publishSignal` path** — the DD "quorum 2" class survives here (owner-settable, not set-derived). Route path is clean; the thermodynamic path is not. | contracts/solidity/TRIONOracleV3.sol:66, 475-499, 580-587 | MEDIUM | Agent G: derive the legacy path's minimum from `validatorCount` (⌈2n/3⌉ floored 2) or deprecate publishSignal in favor of the canonical path. |
| M-02 | **Go consensus votes have no domain tag / chain id / epoch in SignBytes** — a valid testnet vote verifies on mainnet (cross-network replay of consensus signatures). | validator/internal/consensus/types.go:203-256 | MEDIUM | Fleet: prepend "TRION-VOTE-V1" ‖ chain_id ‖ epoch to Vote/Proposal SignBytes (breaking mesh upgrade — schedule with the Wave 2 fleet rollout). |
| M-03 | **Vyper escrow quorum is a static floor of 2** — even with V3's dynamic route quorum live, the Vyper release never consults `minRouteAttestations()`; two attestations release any amount. | contracts/vyper/BTCP_ESCROW.vy:171 | MEDIUM→HIGH with value at risk | Agent L: call the dynamic quorum view (or the canonical weight quorum via the registry) — the EVM `_consensusGate` try/catch pattern is the template. |
| M-04 | **No certificate nonce / consumed-certificate tracking anywhere.** EVM replay protection = per-(route,signer) idempotency + escrow terminal states (adequate for release-exactly-once, inadequate for re-attestation ordering and on-chain equivocation evidence). | TRIONOracleV3.sol:127-128; all other tiers: none | MEDIUM | All VMs: `certificate_nonce` + consumed registry (§8) feeding L4.9 slashing evidence. |
| M-05 | **`_consensusGate` falls back to floor 2 when the oracle lacks `minRouteAttestations()`** — a bound weak/mock oracle silently degrades the quorum. Documented as trusted-oracle assumption, but it re-opens the DD class at the binding boundary. | contracts/solidity/BTCPEscrow.sol:249-263 | MEDIUM | Agent G: require the view (fail closed on missing interface) once all bound oracles are ≥V3; or pin a minimum interface version at `setTRIONOracle` time. |
| M-06 | **`validator_key_version` (py, 4 opaque bytes) / `min_verifier_ver` (rust SemVer) are caller-supplied and never validated** — version anti-downgrade is decorative. | core/btcp/modules.py:118; rust/src/btcp_proof_builder.rs:152-153, 222-225 | MEDIUM | Replace with `protocol_version` + `validator_epoch` in P, checked against the registry (§6 steps 1-2). |
| M-07 | **HHI/AWA/coherence preconditions are only partially enforced at consumption** — HHI ≤ 0.5 (rust, 0-1 scale) is checked structurally; py normalizes 0-10000→0-1 then rejects > 0.5 (=5000, NOT the spec's 4000 CRITICAL); AWA is never checked at any verifier. | rust/src/btcp_proof_builder.rs:200; core/btcp/modules.py:299-303 | MEDIUM | Canonical rules: reject hhi > 4000 (×1e4 scale), require awa_enforced, coherence ≥ threshold (§5.3-5.4, §6 step 4). |
| M-08 | **BEOAttestation.sol is a single-attester key registry** (identity writes, not consensus) — acceptable for its narrow role but must not be confused with validator attestation. | contracts/solidity/BEOAttestation.sol:43-60 | LOW/INFO | Document role separation; multi-attester only if BEO writes become release-relevant. |

### LOW / INFO

| ID | Finding | Where | Severity | Remediation |
|---|---|---|---|---|
| L-01 | py `verify_proof` normalizes HHI 0-10000 → 0-1 but rejects at > 0.5 (i.e. 5000) rather than the L4.8 CRITICAL 4000 | core/btcp/modules.py:299-303 | LOW | Align to 4000 (via §5.3). |
| L-02 | `Validator.address` in the py registry is an unvalidated string (not a checksummed address, no key linkage) | core/spiritual/validator_registry.py:71-78 | LOW | Fleet: registry entries gain family pubkeys + canonical validator_id. |
| L-03 | V3 `publishBTCPRoute` is now metadata-only (good) but still callable by owner/validators and emits `BTCPRoutePublished` on every call — event noise can mislead naive indexers | contracts/solidity/TRIONOracleV3.sol:204-236 | INFO | Agent G: consider gating the event emission to state changes. |
| L-04 | Go mesh `QuorumResult.HHI` uses attestation-weight squares (self-reported weights again) — same root cause as C-06 | validator/internal/p2p/mesh.go:135-138 | INFO | Fixed by C-06 remediation. |
| L-05 | `akasha count ≥ 3` floor is a liveness heuristic, not a security bar — documented as rust parity; keep, but only in ADDITION to the weight quorum | core/btcp/modules.py:292-294; rust/src/btcp_proof_builder.rs:204-207 | INFO | Retained in canonical §4 invariant 4. |
| L-06 | Trusted-relayer mode (oracle unbound) in EVM + owner-release bootstrap in SVM are documented dev-only opt-outs — enforce at deploy time (deploy scripts already bind by default) | BTCPEscrow.sol:408-412; svm lib.rs:130-132 | INFO | Deployment check in Wave 3 (Agent O): assert oracle bound before funding. |

---

## 4. Spec conformance matrix (consumption point of view)

| Requirement (spec cite) | py | rust | Go | EVM(Sol) | EVM(Vy) | SVM | Move | TON | Cairo/SN | NEAR | PVM |
|---|---|---|---|---|---|---|---|---|---|---|---|
| Signature-verified release (BTCP §4.2 step 3; V2 5.1) | ✗ | ✗ (structural) | ✗ | ✔ | ✔ (via V3) | ✗ | ✗ | ✗ | ✗ | ✗ | ✗ |
| Weighted quorum 2/3 (MD L2.1; L4.2) | ✗ | ✗ | ✔ (engine) | count-based | ✗ | ✗ | ✗ | ✗ | ✗ | ✗ | ✗ |
| Epoch-scoped validator set (L4.2) | ✗ | ✗ | ✗ | ✗ | ✗ | ✗ | ✗ | ✗ | ✗ | ✗ | ✗ |
| Diversity weights in quorum (L4.1; §12.2) | math only | carried, unchecked | engine ✔ / mesh ✗ | ✗ | ✗ | ✗ | ✗ | ✗ | ✗ | ✗ | ✗ |
| Escrow binding (H1-class) | ✗ | ✗ | n/a | ✔ | ✔ | ✗ | ✗ | ✗ | ✗ | ✗ | ✗ |
| Settlement tuple bound (ED-B2) | ✗ | ✗ | n/a | ✗ | ✗ | ✗ | ✗ | ✗ | ✗ | ✗ | ✗ |
| Freshness window (V2 Part 5 ttl) | blocks | blocks | ✗ | 300 s | 300 s | ✗ | ✗ | ✗ | ✗ | ✗ | ✗ |
| Replay/nonce protection (§8) | idem. | ✗ | height | idem. | state | ✗ | ✗ | ✗ | ✗ | ✗ | ✗ |
| HHI precondition (L4.8) | >5000 | >0.5 | freeze>4000 | ✗ | ✗ | ✗ | ✗ | ✗ | ✗ | ✗ | ✗ |
| AWA precondition (MD §17) | ✗ | ✗ | ✔ (state) | gate ✔ (V2 §17) | ✗ | ✗ | ✗ | ✗ | ✗ | ✗ | ✗ |
| Domain separation vs other chains (§3.3) | ✗ | ✗ | ✗ | ✔ (chainid+this) | ✔ (via V3) | ✗ | ✗ | ✗ | ✗ | ✗ | ✗ |

---

## 5. The Wave 2 work order (top 5 + per-agent pointers)

1. **Epoch binding + registration (closes H-01).** Every VM gets
   `validator_epoch` in the signed payload and a per-epoch registry
   (validator ids, family pubkeys, s_j·d_j weights ×1e6, total power,
   D_consensus, HHI). Registrar = one signed tx per epoch per chain.
   Registry layout per VM is in CANONICAL_CERTIFICATE §7.
2. **Canonical signed payload everywhere (closes H-02, C-01..C-05).**
   The 346-byte P from `core/consensus/certificate.py` replaces: py
   `intent_hash‖pub`, rust proof fields as authority, TON caller coherence,
   Move relayer flag, SVM oracle key, Cairo/SN caller coherence, NEAR/PVM
   owner writes. EVM keeps its V3 batch discipline but upgrades the digest
   field set (Agent G: new entrypoint, keep V3 live for compat window).
3. **Diversity-weighted tier quorum from registered state (closes H-04,
   M-03, M-01).** Integer tier checks of §5.2; delete static floors and
   caller-supplied fractions; kill the `_consensusGate` interface fallback
   (M-05).
4. **Settlement tuple + nonce + consumed tracking (closes H-05, M-04).**
   destination/amount in P, checked against escrow state; certificate_nonce
   monotonic per (epoch, escrow); consumed registry feeds equivocation
   evidence (L4.9 S1).
5. **Fail-closed verification order (closes M-07, L-01, and the DD oracle-
   fallback class).** The exact §6 sequence: structure → epoch → freshness →
   HHI/AWA/verdict preconditions → signature verification (batch
   fail-closed) → weight quorum → binding → nonce. No fallbacks to weaker
   checks on ANY VM.

Per-agent file targets (first files to touch):

- **G (EVM/Solidity):** `contracts/solidity/TRIONOracleV3.sol` (V4 canonical
  entrypoint + epoch registry contract), `BTCPEscrow.sol:222-268`
  (_consensusGate → canonical), `TRIONExecutionGate.sol:339-344` (digest
  completeness), `contracts/solidity/libraries/HashDNA.sol` (H-07 policy).
- **L (Vyper):** `contracts/vyper/BTCP_ESCROW.vy:136-177` (dynamic quorum +
  canonical binding; secp verify via helper).
- **H (Solana):** `contracts/svm/programs/btcp_escrow/src/lib.rs:34-63`
  (replace oracle-key authority; ed25519 syscall over P; registry PDA).
- **I (Move):** `contracts/move/sources/btcp_escrow.move:196-207`
  (verify_coherence → real verification; epoch registry resource).
- **J (TON):** `contracts/ton/escrow.fc:238-269` (op 0x02 must verify;
  chksig over P), `contracts/ton/oracle.fc` (registry role; kill no-op
  add_validator), `contracts/near/src/trion_oracle.rs:92-95` (signature
  path), `contracts/pvm/legacy_oracle.rs` (same).
- **K (Cairo/Starknet):** `contracts/starknet/src/btcp_escrow.cairo:291-336`
  + `contracts/cairo/src/trion_execution_gate.cairo:146-165` (family-3 felt
  verification, epoch registry, Poseidon domain felt).

Fleet/follow-on (post-Wave 2, tracked here): Go vote domain tags (M-02), Go
mesh authenticated weights (C-06), py `build_consensus_proof` payload swap
(H-02), rust `CanonicalCertificate` twin + parity tests, relayer emission
pipeline.

---

## 6. Residual risks accepted by the canonical design (documented, not fixed)

- **R-1 slashed-validator residual window:** signatures of a just-slashed
  validator verify until the next epoch boundary (≤ 1 epoch ≈ 6 h default) +
  ttl overlap. Mitigated by short epochs + ttl; not eliminated.
- **R-2 same-chain fake deployment:** real signatures can be replayed into a
  rogue same-chain deployment that registered the real validator set — the
  rogue deployment can only act on escrows it holds (no fund risk on real
  escrows; data-integrity noise). Fix path documented in
  CANONICAL_CERTIFICATE §14.2.
- **R-3 clock skew:** cross-VM clocks differ; `clock_drift_tolerance`
  (60 s default) tolerates consensus-time skew on the lower bound only.
- **R-4 registry write trust:** the per-epoch registration is a single
  registrar relayer role (auditable, one tx per epoch per chain); a
  registrar compromise is bounded to one epoch by the TRION-side
  epoch-set root.
