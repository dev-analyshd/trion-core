# zk_travel_rule

**BTCP Master Implementation Spec §14.1 Phase 4, item 22 — FATF Travel Rule compliance proof + `TravelRuleCompliance.sol`.**

"SNARK proving disclosure submitted to VASP": the sending VASP proves, **without revealing PII on-chain**, that the FATF-required disclosure was made and hashed correctly.

## Statement proven

Knowledge of `(disclosure_fields[6], nonce)` such that:

1. `disclosure_hash === Poseidon(disclosure_fields ‖ nonce)` — the hash stored in `TravelRuleCompliance.sol` commits to the FATF-required originator/beneficiary data,
2. `disclosure_submitted === 1` — the disclosure was transmitted to the beneficiary VASP (off-chain, over TRP/IVMS 101); a valid proof with this public flag asserted *is* the SNARK attestation of submission,
3. `amount === disclosure_fields[2]` — the public transfer amount matches the committed disclosure (threshold accounting is public data; the identity fields are not),
4. `amount` is range-checked (`< 2^96`).

The PII only ever exists in the off-chain VASP-to-VASP message; a regulator with a warrant reconstructs the fields and verifies the hash. The public `disclosure_hash` is what the contract stores.

### Signals (IVMS 101 layout)

| Signal | Visibility | Meaning |
|---|---|---|
| `disclosure_fields[6]` | private | `originator_id, beneficiary_id, amount, origin_vasp_id, dest_vasp_id, transfer_reference` |
| `nonce` | private | domain-separation nonce |
| `disclosure_hash` | public | stored in `TravelRuleCompliance.sol` |
| `disclosure_submitted` | public | attestation flag (constrained `=== 1`) |
| `amount` | public | transfer amount |

## Circuit metrics — SELF-REPORTED (circom 2.1.9), UNVERIFIED

FIX-CLAIMS: the counts below require a local circom build to reproduce; no
build artifacts (`.r1cs`/`.zkey`/`verifier.sol`) are committed and `node_modules`
is not vendored, so they are not verifiable from this repo.

- **Constraints:** 477 non-linear + 1 linear (1 × `Poseidon(7)` + `Num2Bits(96)`)
- **Proving scheme:** Groth16 over BN254 (snarkjs) — proof ≈ ~200 bytes
- **Public inputs:** 3 · **Private inputs:** 7 (6 witness) · **Template instances:** 80

## Build & trusted setup

```bash
npm install
npm run compile:travel

# Powers of Tau + phase 2: see zk-circuits/README.md (shared ceremony)
npx snarkjs groth16 setup zk_travel_rule/build/circuit.r1cs pot13_final.ptau zk_travel_rule/build/circuit_0000.zkey
npx snarkjs zkey contribute zk_travel_rule/build/circuit_0000.zkey zk_travel_rule/build/circuit_final.zkey --name="TRION phase2 1" -v
npx snarkjs zkey export verificationkey zk_travel_rule/build/circuit_final.zkey zk_travel_rule/build/verification_key.json

npx snarkjs wtns calculate zk_travel_rule/build/circuit_js/circuit.wasm zk_travel_rule/input.example.json zk_travel_rule/build/witness.wtns
npx snarkjs groth16 prove zk_travel_rule/build/circuit_final.zkey zk_travel_rule/build/witness.wtns zk_travel_rule/build/proof.json zk_travel_rule/build/public.json
npx snarkjs groth16 verify zk_travel_rule/build/verification_key.json zk_travel_rule/build/public.json zk_travel_rule/build/proof.json
```

Validated: `input.example.json` produces a valid witness.

## verifier.sol template note

Generated, not committed:

```bash
npx snarkjs zkey export solidityverifier zk_travel_rule/build/circuit_final.zkey zk_travel_rule/verifier.sol
```

Deploy the generated verifier alongside `TravelRuleCompliance.sol` (spec §14.1: "ZK Travel Rule proof storage, FATF mode"). The compliance contract stores `disclosure_hash + proof` and exposes `verifyProof(...)` for auditors/regulators.

## Integration points

- `contracts/solidity/TravelRuleCompliance.sol` — proof storage, FATF mode toggle
- `core/btcp/router.py` — `Route.travel_rule_proof` field (`TravelRuleProof` type in spec §4 schema)
- `rust/src/btcp_router.rs` — attaches the proof to routes whose value exceeds the FATF threshold
- `anima-service` — REGULATORY_BEHAVIORAL signal cross-reference
