# TRION Protocol — Full Zero-Bridge Cross-VM Results

> **Complete bidirectional zero-bridge test across 8 VM families.**
> 31/33 loop test rounds passed (93.9%). `assets_bridged = false` on every round.

## Deployments

### Starknet Sepolia (7 contracts)
- TRIONOracle: `0x3ccfb9fcc9603ef545cbc53f863cda8b0a9e39096c0a2e840e8a712bd391714`
- BEOAttestation: `0x54025ed77656677e6835a9b7752b426d59f0e643490fba09ddcf7690446e687`
- BTCFiGuard: `0x28348cf996cd64737a7bfab31ffb00d9ebfc66d978b0fdfcbab372258ad8a85`
- BTCPIntent: `0x54ac236fbc96793d3a89db9f84d69c708ee374ec7b53f4f89504778bfdb7915`
- BTCPRoute: `0xb0dedb7666e2a409f592b77ef381edc30b17edb823fbb2d6dd7d335896d2a`
- BTCPEscrow: `0x494a9aea83de43cb66de126d8225bfabcac84c02a677623b61bee0fc3db5e36`
- LiquidityOcean: `0x74f9d79a3eb1b8b71d482e2e6663f0c3617a1991769c4181642c27c9c98bf74`

### EVM Sepolia (7 contracts across 4 chains)
- Base Sepolia: BTCPEscrow, BTCPIntent, BTCPRoute, LiquidityOcean
- Arbitrum Sepolia: BTCPEscrow, BTCPIntent
- OP Sepolia: BTCPEscrow, BTCPIntent, BTCPRoute, LiquidityOcean
- ETH Sepolia: BTCPEscrow, BTCPIntent, BTCPRoute, LiquidityOcean

### Other VMs
- NEAR testnet: BTCPContract on `trion.testnet`
- Solana devnet: Native BTCP escrow program `4TseNzK1Wm7CTNKvg6ciBRp4HzKyZfwxpoNG5Rg3WU3s`

## Test Results
- 31/33 loop test rounds passed (93.9%)
- 141 total on-chain transactions
- 8 VMs proven (identical BEO IDs)
- assets_bridged = false on EVERY round

## Full documentation
See: `docs/proofs/` for detailed reports
