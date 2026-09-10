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
