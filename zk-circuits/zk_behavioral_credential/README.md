# zk_behavioral_credential

**BTCP Master Implementation Spec §14.1 Phase 4, item 23 — Sensing Oracle behavioral coherence proof (LONG TERM).**

A behavioral credential lets a BEO prove "my behavioral history is coherent with the pattern commitment my credential was issued against" **without revealing the behavioral record**. Per the spec, this is the long-term item requiring proof aggregation (recursive proofs) for multi-year records.

## Statement proven

Knowledge of `(entity_id, pattern_fields[7], epoch, nonce)` such that — **without revealing the behavioral pattern**:

1. `behavioral_hash === Poseidon(entity_id ‖ pattern_fields ‖ epoch)` — the public on-chain BH digest is derived from the private five-plane pattern state,
2. `pattern_commitment === Poseidon(pattern_fields ‖ epoch ‖ nonce)` — the commitment the Sensing Oracle signed,
3. `credential === Poseidon(pattern_commitment ‖ entity_id ‖ epoch)` — the issued credential binds entity + epoch + pattern commitment,
4. range checks: pattern scores are 1e6-scaled values (`< 2^32`).

Together (1)∧(2)∧(3): the **behavioral_hash is coherent with the BEO pattern commitment** that the credential attests — all three public values are linked to the same private pattern through one proof.

### Signals (five-plane coherence state, ×1e6 scaled)

| Signal | Visibility | Meaning |
|---|---|---|
| `pattern_fields[7]` | private | `C, phi, m, sigma, k, anima, mf` — five-plane scores + manipulation factor |
| `entity_id`, `epoch`, `nonce` | private | BEO, credential epoch, blinding nonce |
| `behavioral_hash` | public | on-chain BH digest of the pattern |
| `pattern_commitment` | public | commitment the Sensing Oracle signed |
| `credential` | public | the issued ZK credential |

## Circuit metrics — SELF-REPORTED (circom 2.1.9), UNVERIFIED

FIX-CLAIMS: the counts below require a local circom build to reproduce; no
build artifacts (`.r1cs`/`.zkey`/`verifier.sol`) are committed and `node_modules`
is not vendored, so they are not verifiable from this repo.

- **Constraints:** 1,319 non-linear (3 × `Poseidon` + 7 × `Num2Bits(32)`)
- **Proving scheme:** Groth16 over BN254 (snarkjs) — proof ≈ ~200 bytes
- **Public inputs:** 3 · **Private inputs:** 10 · **Template instances:** 145

## Proof aggregation roadmap (spec: "multi-year behavioral record as ZK circuit input")

The single-epoch circuit above is the base case. Multi-year credentials should fold epochs recursively:

1. **v1 (this circuit):** one proof per epoch; verifier chains them (N×200 bytes, N verifyProof calls)
2. **v2:** Nova-style folding over per-epoch relaxed R1CS instances — constant-size proof for arbitrarily many epochs
3. **v3:** Plonky2/Plonky3 recursive composition with the FAISS ANIMA pattern root (128-dim behavioral vector Merkle commitment) as a private input

## Build & trusted setup

```bash
npm install
npm run compile:credential

# Powers of Tau + phase 2: see zk-circuits/README.md (shared ceremony)
npx snarkjs groth16 setup zk_behavioral_credential/build/circuit.r1cs pot13_final.ptau zk_behavioral_credential/build/circuit_0000.zkey
npx snarkjs zkey contribute zk_behavioral_credential/build/circuit_0000.zkey zk_behavioral_credential/build/circuit_final.zkey --name="TRION phase2 1" -v
npx snarkjs zkey export verificationkey zk_behavioral_credential/build/circuit_final.zkey zk_behavioral_credential/build/verification_key.json

npx snarkjs wtns calculate zk_behavioral_credential/build/circuit_js/circuit.wasm zk_behavioral_credential/input.example.json zk_behavioral_credential/build/witness.wtns
npx snarkjs groth16 prove zk_behavioral_credential/build/circuit_final.zkey zk_behavioral_credential/build/witness.wtns zk_behavioral_credential/build/proof.json zk_behavioral_credential/build/public.json
npx snarkjs groth16 verify zk_behavioral_credential/build/verification_key.json zk_behavioral_credential/build/public.json zk_behavioral_credential/build/proof.json
```

Validated: `input.example.json` (coherent five-plane state: C=0.72, Φ=0.75, M=0.70, Σ=0.68, K=0.65, A=0.71, MF=0.05) produces a valid witness.

## verifier.sol template note

Generated, not committed:

```bash
npx snarkjs zkey export solidityverifier zk_behavioral_credential/build/circuit_final.zkey zk_behavioral_credential/verifier.sol
```

`verifier.sol` is a build artifact of the per-circuit `zkey`; regenerate during deployment.

## Integration points

- Sensing Oracle (`api/` oracle service) — issues `credential` against `pattern_commitment`
- `anima-service/faiss_service.py` — 128-dim behavioral vector → pattern state (v3 Merkle input)
- `core/primitives/behavioral_hash.py` — Hash_DNA dual-strand reference; the circuit's `behavioral_hash` is the Poseidon field realization of the pattern state
- BIRP (`core/novel/behavioral_identity_recovery.py`) — credential used for identity recovery claims
