# zk_intent_commitment

**BTCP Master Implementation Spec §14.1 Phase 4, item 19 — "Water Underground" (spec §5.6), Phase 1 (Commit).**

ZK intent commitment for MEV privacy: the user submits ONLY `commitment = Poseidon(intent_hash, nonce)` to `BTCPIntent.sol`. MEV bots observe a commitment hash — no direction, no amount, nothing actionable.

## Statement proven

Knowledge of `(intent_fields[6], nonce, entity_id)` such that — **without revealing any of them**:

1. `intent_hash === Poseidon(intent_fields ‖ nonce ‖ entity_id)` — the public `H_intent` from spec §5.6 Phase 1 (`Hash_DNA(intent_details ‖ random_nonce ‖ entity_id)`, Poseidon realization),
2. `commitment === Poseidon(intent_hash ‖ nonce)` — the submitted commitment binds the same nonce, so the Phase 3 atomic reveal is verifiable.

### Signals

| Signal | Visibility | Meaning |
|---|---|---|
| `intent_fields[6]` | private | `chain_in, chain_out, asset_in, asset_out, magnitude, deadline` |
| `nonce` | private | random 248-bit Phase 1 entropy |
| `entity_id` | public | BEO identifier (field element) |
| `intent_hash` | public | `H_intent` stored in `BTCPIntent.sol` |
| `commitment` | public | `Poseidon(intent_hash, nonce)` submitted on-chain |

## Circuit metrics (compiled with circom 2.1.9)

- **Constraints:** 642 non-linear (2 × Poseidon: `Poseidon(8)` + `Poseidon(2)`)
- **Proving scheme:** Groth16 over BN254 (snarkjs) — proof ≈ 128 fields / ~200 bytes on-chain calldata
- **Public inputs:** 3 · **Private inputs:** 7 · **Template instances:** 148

## Build & trusted setup

```bash
npm install                       # circomlib (circuits) + snarkjs
npm run compile:intent            # → build/circuit.r1cs + build/circuit_js/circuit.wasm

# Powers of Tau (one-time per ceremony; 2^13 covers all five TRION circuits)
npx snarkjs powersoftau new bn128 13 pot13_0000.ptau -v
npx snarkjs powersoftau contribute pot13_0000.ptau pot13_0001.ptau --name="TRION contribution 1" -v
npx snarkjs powersoftau prepare phase2 pot13_0001.ptau pot13_final.ptau -v

# Phase 2 (per-circuit, MUST be a multiparty ceremony in production)
npx snarkjs groth16 setup zk_intent_commitment/build/circuit.r1cs pot13_final.ptau zk_intent_commitment/build/circuit_0000.zkey
npx snarkjs zkey contribute zk_intent_commitment/build/circuit_0000.zkey zk_intent_commitment/build/circuit_final.zkey --name="TRION phase2 1" -v
npx snarkjs zkey export verificationkey zk_intent_commitment/build/circuit_final.zkey zk_intent_commitment/build/verification_key.json

# Prove & verify (see input.example.json for a valid witness)
npx snarkjs wtns calculate zk_intent_commitment/build/circuit_js/circuit.wasm zk_intent_commitment/input.example.json zk_intent_commitment/build/witness.wtns
npx snarkjs groth16 prove zk_intent_commitment/build/circuit_final.zkey zk_intent_commitment/build/witness.wtns zk_intent_commitment/build/proof.json zk_intent_commitment/build/public.json
npx snarkjs groth16 verify zk_intent_commitment/build/verification_key.json zk_intent_commitment/build/public.json zk_intent_commitment/build/proof.json
```

Status: the full pipeline above (compile → witness → setup → prove → verify) has been executed end-to-end successfully with `input.example.json` (`snarkjs groth16 verify` → `OK!`).

## verifier.sol template note

The Solidity verifier is **generated**, not hand-written:

```bash
npx snarkjs zkey export solidityverifier zk_intent_commitment/build/circuit_final.zkey zk_intent_commitment/verifier.sol
```

`verifier.sol` is intentionally NOT committed — it is a build artifact bound to a specific trusted-setup `zkey`. Generate it as part of the deployment pipeline and deploy alongside `BTCPIntent.sol` (Arbitrum Sepolia per `deployments.json`). The generated contract exposes `verifyProof(uint[2] a, uint[2][2] b, uint[2] c, uint[N] pubSignals)`.

## Integration points

- `contracts/solidity/BTCPIntent.sol` — stores `commitment → (timestamp, entity_id)`; calls generated verifier
- `rust/src/btcp_router.rs` — Phase 2 match search triggers `zk_complementarity_proof`
- `core/btcp/orchestrator.py` — Python NIZK reference (`PrivacyLevel.ZK_CREDENTIAL | INVISIBLE`)
- Spec §5.6 Phases 1–4: Commit → Match → Atomic Reveal → Execution (front-running window: zero)
