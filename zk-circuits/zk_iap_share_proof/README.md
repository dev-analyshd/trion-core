# zk_iap_share_proof

**BTCP Master Implementation Spec §14.1 Phase 4, item 21 — Intent Aggregation Protocol (IAP) gas distribution.**

Phase 3 of the spec defers the ZK share proof ("Defer ZK share proof to Phase 4 — use transparent shares initially"). This circuit ends the deferral: it enables **fully private IAP participation**.

Spec (§14.1 item 11): "Gas distribution: `G_per_entity = G_total × share`" where `share_i = value_i / total_value`.

## Statement proven

Knowledge of `(value_i, others[N-1])` such that — **without revealing the prover's value or the pool's individual values**:

1. `total_value === value_i + Σ_j others_j` — the public pool total is the honest sum of the prover's value and all other participants' (one linear constraint; prevents inflating/deflating the pool total to game one's share),
2. `gas_i × total_value === gas_total × value_i` — the prover's gas allocation is **exactly** the IAP share: `gas_i = gas_total · value_i / total_value`. The identity is exact integer arithmetic: if `gas_total · value_i` is not divisible by `total_value`, no valid witness with integer `gas_i` exists,
3. range checks (`value_i, others_j < 2^96`, `gas_i, gas_total < 2^96`, `total_value < 2^104`) — keep the quadratic products sound over the ~254-bit BN254 scalar field (products must not wrap mod p).

### Signals

| Signal | Visibility | Meaning |
|---|---|---|
| `value_i` | private | prover's intent value — never revealed |
| `others[7]` | private | other participants' values — never revealed |
| `total_value` | public | pool total (Σ all values) |
| `gas_total` | public | `G_total` paid by the pool |
| `gas_i` | public | `G_i` attributed to the prover |

Template parameters: `ZKIAPShareProof(nOthers, valBits, gasBits)` — pool size and ranges are configurable (`main` uses 7 others / 96-bit / 96-bit).

## Circuit metrics — SELF-REPORTED (circom 2.1.9), UNVERIFIED

FIX-CLAIMS: the counts below require a local circom build to reproduce; no
build artifacts (`.r1cs`/`.zkey`/`verifier.sol`) are committed and `node_modules`
is not vendored, so they are not verifiable from this repo.

- **Constraints:** 1,066 non-linear (2 quadratic share constraints + 10 × `Num2Bits` range checks ≈ 1,050)
- **Proving scheme:** Groth16 over BN254 (snarkjs) — proof ≈ ~200 bytes
- **Public inputs:** 3 · **Private inputs:** 8 (7 witness) · **Template instances:** 3

Scaling: constraints grow linearly with pool size (`~104 + 96·(n+1)`); a 100-participant pool is ~10k constraints — still trivially Groth16-provable in seconds.

## Build & trusted setup

```bash
npm install
npm run compile:iap

# Powers of Tau + phase 2: see zk-circuits/README.md (shared ceremony)
npx snarkjs groth16 setup zk_iap_share_proof/build/circuit.r1cs pot13_final.ptau zk_iap_share_proof/build/circuit_0000.zkey
npx snarkjs zkey contribute zk_iap_share_proof/build/circuit_0000.zkey zk_iap_share_proof/build/circuit_final.zkey --name="TRION phase2 1" -v
npx snarkjs zkey export verificationkey zk_iap_share_proof/build/circuit_final.zkey zk_iap_share_proof/build/verification_key.json

npx snarkjs wtns calculate zk_iap_share_proof/build/circuit_js/circuit.wasm zk_iap_share_proof/input.example.json zk_iap_share_proof/build/witness.wtns
npx snarkjs groth16 prove zk_iap_share_proof/build/circuit_final.zkey zk_iap_share_proof/build/witness.wtns zk_iap_share_proof/build/proof.json zk_iap_share_proof/build/public.json
npx snarkjs groth16 verify zk_iap_share_proof/build/verification_key.json zk_iap_share_proof/build/public.json zk_iap_share_proof/build/proof.json
```

Validated: `input.example.json` (`value_i = 400`, others summing to `1,000`, `gas_total = 100` ⇒ `gas_i = 40`) produces a valid witness.

## verifier.sol template note

Generated, not committed:

```bash
npx snarkjs zkey export solidityverifier zk_iap_share_proof/build/circuit_final.zkey zk_iap_share_proof/verifier.sol
```

`verifier.sol` is a build artifact of the per-circuit `zkey`; regenerate during deployment.

## Integration points

- `rust/src/intent_aggregator.rs` — pool detection (N ≥ 3 same-direction intents within window W) requests per-participant share proofs before gas distribution
- `core/btcp/modules.py` — `IntentAggregator` (Python reference, transparent shares)
- IAP gas refunds on `BTCPRoute.sol` settlement — verifier call gates each `gas_i` refund
- Phase 3 spec item 11 note: "Defer ZK share proof to Phase 4" — resolved by this circuit
