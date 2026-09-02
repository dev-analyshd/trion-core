# zk_complementarity_proof

**BTCP Master Implementation Spec §14.1 Phase 4, item 20 — "Water Underground" (spec §5.6), Phase 2 (Match).**

ZK proof of intent complementarity without revelation: TRION searches for `H_intent_B` that is the complement of `H_intent_A`; both parties prove complementarity through a single SNARK.

## Statement proven

Knowledge of `(intentA, intentB, nonceA, nonceB)` such that — **without revealing intent contents**:

1. `intent_hash_A === Poseidon(intentA ‖ nonceA ‖ entity_id_A)` and `intent_hash_B === Poseidon(intentB ‖ nonceB ‖ entity_id_B)` — the *identical* construction to `zk_intent_commitment` Phase 1, so the commitment chain verifies end-to-end,
2. `asset_in_A == asset_out_B`,
3. `asset_out_A == asset_in_B`,
4. `|magnitude_A − magnitude_B| ≤ tolerance` (public tolerance, scaled integer).

Public inputs: `[entity_id_A, entity_id_B, intent_hash_A, intent_hash_B, tolerance]` — exactly the spec §5.6 Phase 2 public inputs. Public output: `is_complement` (advisory aggregate flag for the verifier).

### Signals

| Signal | Visibility | Meaning |
|---|---|---|
| `intentA[6]`, `intentB[6]` | private | intent fields of both parties (never revealed) |
| `nonceA`, `nonceB` | private | Phase 1 nonces |
| `entity_id_A`, `entity_id_B` | public | BEO identifiers |
| `intent_hash_A`, `intent_hash_B` | public | commitments from Phase 1 |
| `tolerance` | public | magnitude tolerance (scaled) |

## Circuit metrics (compiled with circom 2.1.9)

- **Constraints:** 1,126 non-linear + 1 linear (dominated by 2 × `Poseidon(8)` ≈ 640 each; `LessThan(65)` × 2, `Num2Bits(64)` × 3, `IsEqual` × 2)
- **Proving scheme:** Groth16 over BN254 (snarkjs) — proof ≈ ~200 bytes
- **Public inputs:** 5 · **Private inputs:** 14 (12 witness) · **Public output:** 1

The spec's ~50k-constraint estimate covers the full `Hash_DNA`-based (SHA3-256, 93-byte payload) variant with per-asset Merkle membership proofs. This Poseidon scaffold is ~1.1k constraints and is the recommended v1 production shape; migrating the hash to the on-chain `HashDNA.sol` layout raises it toward the spec estimate.

## Build & trusted setup

```bash
npm install
npm run compile:complementarity

# Powers of Tau + phase 2: see zk-circuits/README.md (shared ceremony)
npx snarkjs groth16 setup zk_complementarity_proof/build/circuit.r1cs pot13_final.ptau zk_complementarity_proof/build/circuit_0000.zkey
npx snarkjs zkey contribute zk_complementarity_proof/build/circuit_0000.zkey zk_complementarity_proof/build/circuit_final.zkey --name="TRION phase2 1" -v
npx snarkjs zkey export verificationkey zk_complementarity_proof/build/circuit_final.zkey zk_complementarity_proof/build/verification_key.json

npx snarkjs wtns calculate zk_complementarity_proof/build/circuit_js/circuit.wasm zk_complementarity_proof/input.example.json zk_complementarity_proof/build/witness.wtns
npx snarkjs groth16 prove zk_complementarity_proof/build/circuit_final.zkey zk_complementarity_proof/build/witness.wtns zk_complementarity_proof/build/proof.json zk_complementarity_proof/build/public.json
npx snarkjs groth16 verify zk_complementarity_proof/build/verification_key.json zk_complementarity_proof/build/public.json zk_complementarity_proof/build/proof.json
```

Validated: `input.example.json` (complementary ETH→SOL / SOL→ETH intents) produces a valid witness; a tampered input with `asset_out_B ≠ asset_in_A` (hash bindings correctly recomputed) is **rejected** by the constraints — the complementarity check is binding.

## verifier.sol template note

Generated, not committed:

```bash
npx snarkjs zkey export solidityverifier zk_complementarity_proof/build/circuit_final.zkey zk_complementarity_proof/verifier.sol
```

Spec §5.6 lists `zk_complementarity_proof/verifier.sol` as a required file — deploy the generated verifier next to `BTCPRoute.sol` and gate route finalization on `verifyProof(...)`. The file is a build artifact of the per-circuit `zkey`; regenerate during deployment.

## Integration points

- `rust/src/netting_engine.rs` — INVISIBLE privacy mode: match → request both parties' Phase 1 commitments → aggregate proof
- `rust/src/bitp_matcher.rs` — BITP cut/paste complement verification
- `contracts/solidity/BTCPRoute.sol` — route finalization gated on the verifier call
- `core/btcp/orchestrator.py` — `PrivacyLevel.INVISIBLE` reference path (Python NIZK)
- Phase 3 (Atomic Reveal): both intents published in the same block once this proof verifies; if not complements, both remain hidden — no information leaked
