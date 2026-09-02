# TRION Protocol — ZK Circuit Suite

**BTCP Master Implementation Spec §14.1 Phase 4 — ZK Layer (Weeks 25–40, parallel track).**

The five Circom circuits required by the spec (items 19–23), closing the "ZK CIRCUITS — MISSING (entirely new work)" audit gap. The Python NIZK reference implementation (`core/btcp/orchestrator.py`, `PrivacyLevel` 0–4) predates this suite; these circuits are the production SNARK realization.

## Circuits

| # | Circuit | Spec item | Proves | Constraints (circom 2.1.9) |
|---|---|---|---|---|
| 19 | `zk_intent_commitment` | §5.6 Phase 1 | knowledge of `(intent_fields, nonce)` s.t. `commitment == Poseidon(intent_hash, nonce)` — MEV bots see nothing actionable | 642 |
| 20 | `zk_complementarity_proof` | §5.6 Phase 2 | `asset_in_A == asset_out_B ∧ asset_out_A == asset_in_B ∧ \|mag_A − mag_B\| ≤ tolerance` without revealing values | 1,126 |
| 21 | `zk_iap_share_proof` | §14.1 item 21 | `gas_i × total_value == gas_total × value_i` and `total_value == Σ values` — private IAP gas shares | 1,066 |
| 22 | `zk_travel_rule` | §14.1 item 22 | `disclosure_hash == Poseidon(disclosure_fields)` and disclosure submitted (FATF R.16) | 477 |
| 23 | `zk_behavioral_credential` | §14.1 item 23 | behavioral_hash coherent with BEO pattern commitment (Sensing Oracle credential) | 1,319 |

All circuits: **Groth16** over BN254, **circom 2.1.x** syntax, **circomlib 2.x** `Poseidon`/`LessThan`/`IsEqual`/`Num2Bits` gadgets. Each directory contains `circuit.circom`, `README.md` (metrics, trusted setup, verifier note, integration points) and `input.example.json` (a valid witness input — all five have been witness-validated; `zk_intent_commitment` has been proven+verified end-to-end with Groth16).

## Prerequisites

```bash
# circom compiler ≥ 2.1.x  (https://docs.circom.io/getting-started/installation/)
#   rust + cargo:  cargo install --git https://github.com/iden3/circom.git --tag v2.1.9
# snarkjs + circomlib:
npm install          # installs circomlib ^2.0.5 (circuits) and snarkjs ^0.7.4 (devDependency)
```

`verifier.sol` contracts are **generated build artifacts** (bound to each circuit's trusted-setup `zkey`) — see each circuit's README for the exact `snarkjs zkey export solidityverifier` command.

## Build all circuits

```bash
npm run compile                  # all five → build/circuit.r1cs + build/circuit_js/circuit.wasm
npm run compile:intent           # (or individually — see package.json scripts)
```

## Trusted setup (Groth16)

```bash
# ── Powers of Tau (shared ceremony; 2^13 = 8192 ≥ every circuit's constraints) ──
npm run setup:powersoftau        # → pot14_final.ptau  (new + contribute + prepare phase2)
#                                 NOTE: production must run a real multiparty ceremony
#                                 (multiple independent contributions; see MPC docs)

# ── Phase 2 (per circuit — example: intent commitment) ──
npx snarkjs groth16 setup zk_intent_commitment/build/circuit.r1cs pot14_final.ptau zk_intent_commitment/build/circuit_0000.zkey
npx snarkjs zkey contribute zk_intent_commitment/build/circuit_0000.zkey zk_intent_commitment/build/circuit_final.zkey --name="TRION phase2 1" -v
npx snarkjs zkey export verificationkey zk_intent_commitment/build/circuit_final.zkey zk_intent_commitment/build/verification_key.json

# ── Prove / verify ──
npm run prove:intent
npm run verify:intent

# ── Export all Solidity verifiers ──
npm run export:verifiers
```

## Statement proven — why Poseidon

The spec's `H_intent = Hash_DNA(...)` is SHA3-256 over a byte layout (93-byte whitepaper / 420-byte BTCP formal spec). SHA3 is not SNARK-friendly (each hash ≈ tens of thousands of constraints). The circuits use the standard ZK practice: **Poseidon over BN254 field elements** (~320 constraints per 8-input hash) for in-circuit commitments, with the field-element layout documented per circuit. Cross-system binding to the on-chain `HashDNA.sol` digests happens via the public `intent_hash`/`behavioral_hash` inputs, which the off-chain prover maps from the SHA3 domain. The spec's ~50k-constraint estimate for `zk_complementarity_proof` corresponds to the full Hash_DNA/Merkle variant; the Poseidon shape here is the recommended v1.

## Integration points

| Circuit | Contract | Rust module | Python reference |
|---|---|---|---|
| `zk_intent_commitment` | `BTCPIntent.sol` | `rust/src/btcp_router.rs` | `core/btcp/orchestrator.py` |
| `zk_complementarity_proof` | `BTCPRoute.sol` (+ generated verifier) | `netting_engine.rs`, `bitp_matcher.rs` | `core/btcp/modules.py` (BITPMatcher) |
| `zk_iap_share_proof` | `BTCPRoute.sol` (gas refunds) | `intent_aggregator.rs` | `core/btcp/modules.py` (IntentAggregator) |
| `zk_travel_rule` | `TravelRuleCompliance.sol` | `btcp_router.rs` (`travel_rule_proof`) | `core/btcp/router.py` |
| `zk_behavioral_credential` | Sensing Oracle credential registry | `behavioral_state_channel.rs` | `anima-service/faiss_service.py`, `core/novel/birp.py` |

Spec §5.6 four-phase flow implemented by 19+20 together: **Commit** (zk_intent_commitment) → **Match** (zk_complementarity_proof) → **Atomic Reveal** (same block) → **Execution** (front-running window: zero).

## Status

- [x] All five circuits compile (circom 2.1.9) with constraint counts recorded per README
- [x] Valid example witnesses for all five (`input.example.json`, snarkjs `wtns calculate` OK)
- [x] End-to-end Groth16 prove+verify executed for `zk_intent_commitment` (`OK!`)
- [x] Soundness spot-check: `zk_complementarity_proof` rejects non-complementary intents
- [ ] Production multiparty ceremony (Powers of Tau + per-circuit phase 2)
- [ ] On-chain verifier deployments (Arbitrum Sepolia per `deployments.json`)
- [ ] v2 proof aggregation for `zk_behavioral_credential` (Nova folding / recursive proofs)
