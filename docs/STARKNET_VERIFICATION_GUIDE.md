# Starknet Contract Source Code Verification Guide

This guide provides step-by-step instructions for verifying the source code of all 7 TRION Protocol contracts deployed on Starknet Sepolia using Voyager's verification system.

## Prerequisites

- Source code files in `contracts/starknet/src/`
- Compiler version: **Cairo 2.10.1** (Scarb 2.10.1)
- Scarb.toml configuration: `contracts/starknet/Scarb.toml`

## Why Verification Is Needed

While all 7 contracts are deployed and fully functional on Starknet Sepolia (verified by 32/32 on-chain state reads), the **source code** has not yet been verified on Voyager. This means:

- ✅ Contracts are deployed and working (on-chain state verified)
- ✅ Class hashes match deployment records
- ✅ All functions are callable
- ⚠️ Source code not yet verified on Voyager (shows "VERIFY SOURCE CODE" button)

Voyager's API is behind Cloudflare protection, which prevents programmatic verification. The source code must be submitted manually through the Voyager web interface.

## Manual Verification Steps (Per Contract)

For each of the 7 contracts, follow these steps:

### Step 1: Open the Contract Page

Go to the contract page on Voyager:
```
https://sepolia.voyager.online/contract/<CONTRACT_ADDRESS>
```

### Step 2: Click "Verify Source Code"

On the contract page, find the yellow "VERIFY SOURCE CODE" button and click it.

### Step 3: Fill in Verification Details

- **Compiler Version:** `2.10.1`
- **Cairo Version:** `2`
- **Contract Name:** (see table below)
- **Source Code:** Paste the contents of the corresponding `.cairo` file

### Step 4: Submit and Verify

Click the verify button. Voyager will compile the submitted source code and compare it against the deployed class hash. If they match, the contract will show as "Verified" with a green checkmark.

---

## Contract Verification Details

| # | Contract Name | Address | Source File | Class Hash |
|---|---|---|---|---|
| 1 | TRIONOracle | `0x3ccfb9fcc9603ef545cbc53f863cda8b0a9e39096c0a2e840e8a712bd391714` | `TRIONOracle.cairo` | `0x293d5b39bf5813c15c59989baaf315a0e34ed6a82f61bc857e972ba7a4a3235` |
| 2 | BEOAttestation | `0x54025ed77656677e6835a9b7752b426d59f0e643490fba09ddcf7690446e687` | `BEOAttestation.cairo` | `0x624bdad0b7367c899b5214751c6a5e81f0e72f028fcf2b5c848b243784a0c17` |
| 3 | BTCFiGuard | `0x28348cf996cd64737a7bfab31ffb00d9ebfc66d978b0fdfcbab372258ad8a85` | `BTCFiGuard.cairo` | `0x1d243dd5faf161d874885a5dfb5b056515ebe147bad3fa42eab87beb3f62999` |
| 4 | BTCPIntent | `0x54ac236fbc96793d3a89db9f84d69c708ee374ec7b53f4f89504778bfdb7915` | `btcp_intent.cairo` | `0x5cf5edb68aa2e54f7b83ae63c704ceb7637580d0af55a30ea2942c45d92eba7` |
| 5 | BTCPRoute | `0xb0dedb7666e2a409f592b77ef381edc30b17edb823fbb2d6dd7d335896d2a` | `btcp_route.cairo` | `0x5343269bc7a162ac077eb822066c251c5546cf206ae824015786cbe9984079b` |
| 6 | BTCPEscrow | `0x494a9aea83de43cb66de126d8225bfabcac84c02a677623b61bee0fc3db5e36` | `btcp_escrow.cairo` | `0x7e34da08b997ec149bdc793307c829a5de103f65de64561901d048cf6d04969` |
| 7 | LiquidityOcean | `0x74f9d79a3eb1b8b71d482e2e6663f0c3617a1991769c4181642c27c9c98bf74` | `liquidity_ocean.cairo` | `0x7201ade293ec04d6a48fd9de469838265e38c5e71d3aab1f42742a867530c7` |

## Source File Locations

All source files are in:
```
contracts/starknet/src/
```

The Scarb.toml configuration is at:
```
contracts/starknet/Scarb.toml
```

## Compiler Settings

- **Compiler:** Scarb 2.10.1
- **Cairo edition:** 2024_07
- **Starknet dependency:** `starknet = "2.10.1"`
- **SIERRA output:** enabled
- **CASM output:** enabled
- **Optimizer:** enabled (default)

## Verification API (For Reference)

The Voyager verification API endpoint is:
```
POST https://sepolia.voyager.online/api/contract/{address}/code
```

However, this endpoint is behind Cloudflare protection and cannot be accessed programmatically without a browser session. The API requires the source code as the POST body.

---

## Current On-Chain Verification Status

All 7 contracts have been verified **on-chain** (not source code verification on Voyager):

```
✅ TRIONOracle       — 4/4 checks pass (owner, class hash, score_count)
✅ BEOAttestation     — 4/4 checks pass (attester, class hash, total_attestations)
✅ BTCFiGuard         — 5/5 checks pass (owner, oracle link, threshold, class hash)
✅ BTCPIntent         — 4/4 checks pass (100 intents registered, class hash)
✅ BTCPRoute          — 4/4 checks pass (71 routes registered, class hash)
✅ BTCPEscrow         — 4/4 checks pass (72 escrows processed, class hash)
✅ LiquidityOcean     — 7/7 checks pass (owner, relayer, threshold=300000, class hash)

Total: 32/32 on-chain checks passed (100%)
```

See: `docs/proofs/starknet_verification_report.json` for full on-chain verification data.

---

*This guide will be updated once source code verification is completed on Voyager.*
