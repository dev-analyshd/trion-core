# TRION BTCP Zero-Bridge — Run It Yourself

## Requirements

- **Node.js** >= 20
- **Scarb** (only if rebuilding Cairo contracts) — install from https://docs.swmansion.com/scarb/install.html
- **starknet.js** (installed via `npm install` in the repo)
- A **Bitcoin testnet wallet** with >= 0.01 tBTC (faucet: https://coinfaucet.eu/en/btc-testnet/)
- A **Starknet Sepolia account** with ETH/STRK gas (~0.05 ETH equivalent)
- **Alchemy API key** (or use public RPCs as fallback)
- ~2-6 hours wall clock (Bitcoin confirmation depth gate waits)
- 2 GB RAM, 500 MB disk

## Step-by-Step

### 1. Clone and install

```bash
git clone https://github.com/dev-analyshd/trion-core.git
cd trion-core
npm install
```

### 2. Configure environment

Create a `.env` file in `chains/starknet/`:

```env
STARKNET_ACCOUNT_ADDRESS=0xYOUR_ACCOUNT_ADDRESS
STARKNET_PRIVATE_KEY=0xYOUR_PRIVATE_KEY
EVM_PRIVATE_KEY=0xYOUR_EVM_PRIVATE_KEY
```

Set RPC endpoints (or use defaults):

```bash
export STARKNET_RPC=https://starknet-sepolia.g.alchemy.com/starknet/version/rpc/v0_10/YOUR_KEY
export BITCOIN_RPC=https://bitcoin-testnet.g.alchemy.com/v2/YOUR_KEY
```

### 3. Fund wallets

- **Bitcoin testnet**: send tBTC to your address (faucet links above)
- **Starknet Sepolia**: ensure your account has ETH for gas

### 4. Run the full closeout suite

```bash
cd btc-tools
node full-closeout-alchemy.mjs
```

This runs all 42 checks:
- BTC lock tx verification
- SPV verifier state
- verify_anchor with real Merkle proof
- BTCP score computation
- Full Starknet settlement (5 steps)
- Relayer bypass revert
- Quorum Q1 (1 attestation → REVERT)
- A1-A20 adversarial battery
- 10 bidirectional rounds
- Independent verifier

### 5. Run the dual-side DeFi proof

```bash
node dual-side-defi-proof.mjs
```

This produces `docs/proofs/dual_side_defi_proof.json` with:
- 24 paired transactions (BTC + Starknet)
- Full DeFi journey (J1-J10)
- Negative paths (N1-N7)
- Fee/revenue ledger
- Self-audit checklist + agreement statement

### 6. Verify independently

```bash
# Re-derive the anchor_bh from Bitcoin data
curl "https://bitcoin-testnet.g.alchemy.com/v2/YOUR_KEY" \
  -d '{"jsonrpc":"2.0","method":"getrawtransaction","params":["62bfe73fab5ac18c64794493d3713c5eb3e92b839df401befecd68162ee1fcf7",true],"id":1}'

# Check the SPV verifier on Voyager
# https://sepolia.voyager.online/contract/0x6510323e3ddd0c91d7c021200ec62c91605f528d1873eface5c0dc6258616c1
```

## Why It Works

### (a) SPV On-Chain Verification
The Cairo contract computes `double_SHA256(block_header)` and checks `hash < target(bits)`. This proves the block was mined with real Bitcoin PoW. Merkle proofs prove the transaction is in the block. Chain linkage (prev_blockhash == tip) proves continuity.

### (b) BEO Identity Binding
`BEO = SHA3-256(normalize(bitcoin_address))` — the same hash across all chains. A Bitcoin holder's identity is recognized on Starknet without a bridge.

### (c) Quorum-Bound Escrow
Release requires 3-of-5 DW-BFT validator attestations. A relayer alone cannot release. Mismatches trigger dispute state (fail-closed).

### (d) Anchor Recomputation
The contract recomputes the anchor_bh from verified Bitcoin data. A relayer can't submit a fabricated anchor — it must match the recomputed value.

### (e) The Invariant: assets_bridged = false
BTC never leaves Bitcoin. No wrapped token is minted. The only thing that crosses chains is a cryptographic proof. This removes the honeypot — there's nothing to steal.

### (f) Fees and Revenue
- **Bitcoin side**: self-transfer lock fee (~1000 sats)
- **Starknet side**: gas for header submission + escrow operations
- **Revenue**: validator attestation fees, LiquidityOcean routing fees, IAP gas savings, 15% Behavioral Commons allocation

## Contract Addresses (Starknet Sepolia)

| Contract | Address |
|----------|---------|
| SPV Verifier | `0x6510323e3ddd0c91d7c021200ec62c91605f528d1873eface5c0dc6258616c1` |
| Escrow V2 | `0x4cc964a674bc4ff6f7e12462bdae963c7f42ef257af380e1604e71b01eb68dd` |
| TRIONOracle | `0x3ccfb9fcc9603ef545cbc53f863cda8b0a9e39096c0a2e840e8a712bd391714` |
| BEOAttestation | `0x54025ed77656677e6835a9b7752b426d59f0e643490fba09ddcf7690446e687` |
| BTCFiGuard | `0x28348cf996cd64737a7bfab31ffb00d9ebfc66d978b0fdfcbab372258ad8a85` |
| BTCPIntent | `0x54ac236fbc96793d3a89db9f84d69c708ee374ec7b53f4f89504778bfdb7915` |
| BTCPRoute | `0xb0dedb7666e2a409f592b77ef381edc30b17edb823fbb2d6dd7d335896d2a` |
| BTCPEscrow | `0x494a9aea83de43cb66de126d8225bfabcac84c02a677623b61bee0fc3db5e36` |
| LiquidityOcean | `0x74f9d79a3eb1b8b71d482e2e6663f0c3617a1991769c4181642c27c9c98bf74` |

## Bitcoin Testnet References

- Lock TX: `62bfe73fab5ac18c64794493d3713c5eb3e92b839df401befecd68162ee1fcf7`
- Block: `00000000000001a9562ec7227605f68ea1baf77dfa37d6794fcd55bca4a509f4`
- Address: `tb1q5d69fyxxxwdkr7pecmxyr245w5jqchm9zptkks`

---

## ZK Activation (BZK)

> **Authored by:** A-DOCS (documentation engineer) — Task ID: BZK-PHASE-8
> **v-stamp:** `bzk-run-it-yourself-v0.1`
> **Source of truth:** `docs/zk/A_AUD_ledger.md` (Phase 7 audit),
> `docs/zk/PHASE3_BENCHMARKS.md`, `docs/zk/BZK.md`.

This section reproduces the BZK (Behavioral Zero-Knowledge) activation
that Phases 0–7 of the BZK mission produced. Every claim carries an
R-LABELS tag (VERIFIED / MEASURED / OPEN / ESTIMATE / GATED-OPEN /
SYNTHETIC-DEMO). Per mission FORBIDDEN: TRION is NOT reducible to "a
zk protocol" — BZK is one projection of the Witness World's privacy
law (see `docs/zk/COMMUNITY_ADDENDUM_DRAFT.md`).

### Prerequisites

- **circom** 2.2.3 (system install) — R1CS compilation
- **snarkjs** 0.7.6 (in `node_modules/.bin` after `npm install`)
- **circomlib** 2.0.5 (in `node_modules` after `npm install`)
- **Node.js** >= 20 (witness calculation, Hardhat tests)
- **Hardhat** (in `hardhat/` subproject; `npm install` there)
- **Python 3.10+** (for Phase 2 commitment layer + Phase 5 integration + Phase 6 Z-battery tests)
- ~2 GB RAM, 500 MB disk for compiled artifacts

### Step-by-Step

#### 1. Clone and install dependencies

```bash
git clone https://github.com/dev-analyshd/trion-core.git
cd trion-core
npm install                       # snarkjs 0.7.6 + circomlib 2.0.5
cd hardhat && npm install && cd ..# Hardhat + ethers + mocha
```

Verify the toolchain:

```bash
circom --version                  # expect 2.2.3
node_modules/.bin/snarkjs --version   # expect 0.7.6
node --version                    # expect >= 20
```

#### 2. Compile the 5 circom circuits + MEASURED constraint counts

```bash
cd zk-circuits
for c in zk_intent_commitment zk_complementarity_proof zk_iap_share_proof \
         zk_travel_rule zk_behavioral_credential; do
    mkdir -p "$c/build"
    circom "$c/circuit.circom" --r1cs --wasm --sym --output "$c/build" 2>&1 | tail -1
    snarkjs r1cs info "$c/build/circuit.r1cs" 2>&1 \
        | grep -E "Constraints|Private Inputs|Public Inputs"
done
```

Expected output (R-LABELS: MEASURED — reproduced 5/5 in Phase 7 audit §6):

```
zk_intent_commitment:        #Wires=1697  #Constraints=1688  #Private=7   #Public=3
zk_complementarity_proof:    #Wires=2695  #Constraints=2686  #Private=14  #Public=5
zk_iap_share_proof:          #Wires=1077  #Constraints=1078  #Private=8   #Public=3
zk_travel_rule:              #Wires=1186  #Constraints=1179  #Private=7   #Public=3
zk_behavioral_credential:    #Wires=3302  #Constraints=3298  #Private=10  #Public=3
```

#### 3. Run the leakage greps (R-ABSENT + AWA freeze no-override)

```bash
# R-ABSENT: cross-artifact grep for forbidden fields
bash zk-circuits/commitments/leakage_grep.sh
# Expected: exit 0, 0 matches

# AWA freeze no-override grep
grep -rniE "forceResume|overrideFreeze|forceThaw|bypassAwa|emergencyUnfreeze" \
    hardhat/contracts/zk/ core/zk/ docs/zk/ 2>/dev/null
# Expected: 0 matches

# Extended R-ABSENT grep across all zk artifacts
bash core/zk/leakage_grep_zk_integration.sh
# Expected: exit 0
```

#### 4. Run the Hardhat test suite (29 tests, R-LABELS: VERIFIED)

```bash
cd hardhat
npx hardhat compile
npx hardhat test test/zk_contracts.test.ts
# Expected: 29 passing, 0 failing
```

Key tests that should pass:
- `constructor: awaFrozen defaults to TRUE (R-FAILCLOSED)`
- `AWA freeze: stranger cannot thaw (R-INVISIBILITY)`
- `CRITICAL tier without proof: reverts CriticalTierRequiresProof`
- `commitIntent: emits IntentCommitted (BTCP §5.6 Phase 1)`
- `revealIntent: invalid proof reverts ComplementarityProofFailed`
- `ComplementarityVerifier: two-step handover blocks single-entity takeover`

#### 5. Deploy the 3 verifier contracts to a local Hardhat VM (R-CHANNELS surface)

```bash
cd hardhat
npx hardhat node                         # terminal 1: local Hardhat VM
# terminal 2:
npx hardhat run scripts/deploy_zk_contracts.js --network localhost
# Outputs: hardhat/deploy-results/zk_phase4_localhost.json (with tx hashes)
```

The deploy script deploys:
- `ComplementarityVerifier.sol` — generic Groth16 wrapper (pluggable `setVerifier`)
- `IntentCommitmentRegistry.sol` — BTCP §5.6 Phase 1 commit + Phase 3 atomic reveal
- `TravelRuleCompliance.sol` — BTCP Fix 1 Step 4 + Chameleon tiers + AWA freeze

Verify `awaFrozen` defaults to TRUE at construction (R-FAILCLOSED).

#### 6. Run the Z-battery (Phase 6 — 14 attacks Z1-Z14)

```bash
cd zk-circuits
python3 tests/z1_z4_soundness_battery.py    # Z1 [OPEN] + Z2 VERIFIED + Z3 VERIFIED(constraint)+[OPEN](round-trip) + Z4 [OPEN]
python3 tests/z5_reconstruction_attempt.py   # Z5 PASS, SYNTHETIC-DEMO (BTCP §13 spec falsification)
python3 tests/z6_mev_simulation.py           # Z6 PASS, SYNTHETIC-DEMO (BTCP §13 spec falsification)
python3 tests/z7_absent_field_grep.py        # Z7 PASS, VERIFIED
python3 tests/z8_silence_preservation.py     # Z8 PASS(constraint) + [OPEN](round-trip) + FINDING
python3 tests/z9_travel_rule_trace.py       # Z9 PASS, SYNTHETIC-DEMO
python3 tests/z10_birp_timing.py             # Z10 PASS, VERIFIED(Part A) + SYNTHETIC-DEMO(Part B)
python3 tests/z11_birp_drift.py              # Z11 PASS, SYNTHETIC-DEMO (NEVER as fact per WP-Mar §16 CONJECTURE)
python3 tests/z12_malleability.py            # Z12 [OPEN] per BLOCKER
python3 tests/z13_awa_freeze_reverify.py     # Z13 PASS, VERIFIED
python3 tests/z14_ledger_integrity.py        # Z14 PASS, VERIFIED (9/9 invariants)
```

Expected aggregate: 8 PASS/VERIFIED, 4 [OPEN] per Phase 3 BLOCKER, 2 spec
falsifications explicitly tested (Z5 + Z6), 1 FINDING documented (Z8).
See `docs/zk/Z_BATTERY_RESULTS.md` for full per-attack evidence.

### BLOCKER — Groth16 Setup Exceeds Sandbox Timeout (per Phase 3 §4.3)

**The BLOCKER:** the Groth16 setup step
(`snarkjs groth16 setup circuit.r1cs pot14_final.ptau circuit_0000.zkey`)
takes >240 seconds on a typical sandboxed environment with the default
120-second command timeout. Even at 240 s timeout, the step is killed
before completion. Background attempts via `nohup` are sandbox-killed.

**What this blocks (R-LABELS: [OPEN]):**
- Prove/verify round-trip on all 4 compiled circuits (S1 Phase 2, S2, S3, S4 single-epoch)
- Exported `verifier.sol` per circuit (via `snarkjs zkey export solidityverifier`)
- Mission attacks requiring round-trip: Z1, Z3 round-trip, Z4, Z12

**Mitigation — run in an environment with longer timeout:**

Option A (preferred): run in a CI environment with `timeout-minutes: 30`:

```bash
# GitHub Actions, CircleCI, Railway build phase, etc.
# With timeout > 10 minutes, run:
cd zk-circuits/zk_intent_commitment
snarkjs powersoftau new bn128 14 pot14_0000.ptau
snarkjs powersoftau contribute pot14_0000.ptau pot14_0001.ptau --name="contributor1" -v
snarkjs powersoftau prepare phase2 pot14_0001.ptau pot14_final.ptau
snarkjs groth16 setup build/circuit.r1cs pot14_final.ptau circuit_0000.zkey
snarkjs zkey contribute circuit_0000.zkey circuit_final.zkey --name="contributor2" -v
snarkjs zkey export verificationkey circuit_final.zkey verification_key.json

# Generate a witness + proof + verify
node build/circuit_js/calculate_witness.js input.json witness.wtns
snarkjs groth16 prove circuit_final.zkey witness.wtns proof.json public.json
snarkjs groth16 verify verification_key.json public.json proof.json
# Expected: OK! (round-trip green; closes Z1, Z3-rt, Z4, Z12)

# Export the on-chain verifier
snarkjs zkey export solidityverifier circuit_final.zkey verifier.sol
```

Option B: use `nohup` + `screen` in a persistent environment:

```bash
screen -S bzk-setup
cd zk-circuits/zk_intent_commitment
nohup snarkjs groth16 setup build/circuit.r1cs pot14_final.ptau circuit_0000.zkey \
    > setup.log 2>&1 &
# Detach: Ctrl-A then D
# Reattach later: screen -r bzk-setup
```

Option C: remote build server (Railway build phase, CircleCI).

### When the BLOCKER closes — plug exported `verifier.sol` into `ComplementarityVerifier`

After producing `verifier.sol` via `snarkjs zkey export solidityverifier`,
plug it into the deployed `ComplementarityVerifier` wrapper:

```bash
# 1. Deploy the leaf verifier (the exported verifier.sol from snarkjs)
npx hardhat run scripts/deploy_leaf_verifier.js --network localhost
# Captures: leafVerifier address (e.g., 0xYOUR_LEAF_VERIFIER_ADDRESS)

# 2. Register the leaf verifier with the ComplementarityVerifier wrapper
#    via setVerifier(bytes32 circuitId, address verifierContract)
npx hardhat run scripts/register_verifier.js --network localhost
# Uses circuitId = keccak256("zk_complementarity_proof_v0.1") (R-GENERIC, no chain prefix)

# 3. End-to-end verify round-trip on-chain
npx hardhat run scripts/e2e_verify_round_trip.js --network localhost
# Calls ComplementarityVerifier.verifyComplementarityProof(bytes proof, uint256[] publicInputs)
# which forwards to the leaf verifier for the pairing check.
# Expected: returns TRUE; emits ComplementarityProofVerified event
```

Once this completes, Z1, Z3 round-trip, Z4, Z12 transition from `[OPEN]`
to `VERIFIED`, D5 + D12 transition from PARTIAL to YES, and Phase 9
(AGREEMENT GATE) owns the verbatim "I AGREE 100%:" decision (per Phase 7
audit §11, NOT emitted at Phase 8 because D5/D12/D15/D16/D18 are not
full YES at this phase).

### Audit Verdict (per `docs/zk/A_AUD_ledger.md §10`)

- **13/18 D-items YES** (D1, D2, D3, D4, D6, D7, D8, D9, D10, D11, D13, D14, D17)
- **2 PARTIAL** (D5, D12 — round-trip `[OPEN]` per Phase 3 BLOCKER above)
- **3 INCOMPLETE** (D15 → YES after Phase 8 closure, D16 → YES after Phase 8 closure, D18 — STILL INCOMPLETE)
- **0 FAIL / 0 unlabeled inventions / 0 citation mismatches / 0 measurement mismatches (5/5 reproduce)**

Per mission FORBIDDEN: the AGREEMENT STATEMENT (verbatim "I AGREE 100%:")
is NOT emitted at this phase. Phase 9 (AGREEMENT GATE) owns that decision.

### References (canonical paths in repo)

- `docs/zk/CANON_EXTRACT.md` — verbatim canon (Phase 0.2)
- `docs/zk/ZK_SURFACE_MAP.md` — five surfaces + final status (Phase 0.3 + Phase 8.1)
- `docs/zk/FEASIBILITY_AND_SETUP.md` — Phase 1 verdicts + S4 GATED-OPEN threshold
- `docs/zk/PHASE3_BENCHMARKS.md` — MEASURED constraints + BLOCKER
- `docs/zk/Z_BATTERY_RESULTS.md` — Z1-Z14 evidence
- `docs/zk/A_AUD_ledger.md` — Phase 7 independent verifier report (v-stamp `bzk-audit-v0.1`)
- `docs/zk/BZK.md` — spec-anchored reference (Phase 8.2, v-stamp `bzk-reference-v0.1`)
- `docs/proofs/bzk_activation.json` — evidence ledger (Phase 8.3, machine-readable)
- `docs/zk/COMMUNITY_ADDENDUM_DRAFT.md` — FULL TRION framing (Phase 8.5, DRAFT)
- `docs/zk/EXTENSION_PROPOSALS.md` — EP-1 through EP-5 (segregated, D16)

*v-stamp: `bzk-run-it-yourself-v0.1`. Authored by A-DOCS (Phase 8.4).*
