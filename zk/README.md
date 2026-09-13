# TRION ZK Layer

One root, two independent prover paths, shared parity.

```
zk/
├── groth16/          — Circom circuits, EVM verifier exports, commitment layer,
│                       snarkjs scripts, Z-battery tests (from zk-circuits/)
├── stark/            — Cairo circuits + zk_verifier contract subpackage,
│                       Scarb workspace, on-chain proof evidence
├── shared/           — cross-prover canonical vectors + parity pins
├── facade/           — Python ZK facade (ZKProofSystem) for orchestrator
└── archive/           — superseded artifacts with PROVENANCE.md
```

## Canon citations

- S1 ZK Intent Commitment: BTCP §5.6 (4-phase MEV privacy protocol)
- S2 ZK IAP Share Proof: BTCP §5.3 (prove share without revealing contribution)
- S3 ZK Travel Rule: BTCP §11 Fix 1 (FATF compliance, Chameleon tiers)
- S4 Sensing Oracle: BTCP §7.1 + C3 §16 (behavioral credential, ABSENT schema)
- S5 BIRP: C3 §16 (enrollment + recovery phases 1-5)

## Prover paths

### Groth16 (zk/groth16/)
- 5 Circom circuits (compiled with circom 2.2.3)
- MEASURED constraint counts: 1,688 / 2,686 / 1,078 / 1,179 / 3,298
- Proving system: Groth16 (snarkjs) for S1 Phase 2; PLONK for S2/S3
- Status: COMPILED, round-trip [OPEN] (Groth16 setup time exceeds sandbox)
- Trusted setup: REQUIRED for Groth16; NOT required for PLONK

### Stark (zk/stark/)
- 7 Cairo modules (hash_dna, s1-s5, zk_verifier)
- MEASURED: 21/21 tests green (Scarb 2.9.2 + cairo_test plugin)
- Proving system: STARK (transparent, no trusted setup)
- Status: COMPILED + TESTED; deployed on Starknet Sepolia
- Contract: 0x0222c170d97af28d9cb964e81b9394be3bf9a4e1d96a85df1084a7667ef40029
- Deploy tx: 0x01408e9cbd87bad551c515cdc232ba85d29a5d02ecfd939e9e13f5a3e2e4031b
- AWA freeze on-chain: PASS (commit_intent reverted while awa_frozen=true)
- R-NATIVE: grep-proven zero wrapper/adapter/shim/secp256k1 in zk/stark/

## Cross-prover parity (zk/shared/)
- Hash_DNA construction identical across Python, Cairo, and Solidity
- Same intent → H_intent identical in groth16 and Cairo hash_dna
- Same behavioral_hash → public_commitment identical
- Status: GATED-OPEN (parity pins to be created in P7)

## S4 aggregation status
- Single-epoch base case: MEASURED (3,298 constraints Cairo; 3,298 Circom)
- Multi-year aggregation: GATED-OPEN per OQ-7 (requires Plonky2/Nova)
- Status label: [CONJECTURE] per BTCP §7.1 verbatim

## R-COMPLIANCE
ZK proves compliance, never concealment. The Akashic record persists
append-only. ZK changes who observes the record, not whether it exists.
(C3 §17 verbatim)
