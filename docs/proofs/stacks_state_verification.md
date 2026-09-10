# Stacks State Verification — Phase 0

**Date:** 2026-09-10
**Network:** Stacks Testnet (chain 26001)
**Auditor:** A6 (independent)

## 0.1 Contract Deployment Verification

All 7 contracts verified deployed via Hiro API `/v2/contracts/source` endpoint:

| Contract | Contract ID | HTTP Status |
|----------|------------|:-----------:|
| btcspvverifier | ST969AZNDX2P7N1YJ0DNVGC8QEKT388DBMXGHR9Z.btcspvverifier | 200 DEPLOYED |
| spv-v2 | ST969AZNDX2P7N1YJ0DNVGC8QEKT388DBMXGHR9Z.spv-v2 | 200 DEPLOYED |
| btcpescrow | ST969AZNDX2P7N1YJ0DNVGC8QEKT388DBMXGHR9Z.btcpescrow | 200 DEPLOYED |
| btcpintent | ST969AZNDX2P7N1YJ0DNVGC8QEKT388DBMXGHR9Z.btcpintent | 200 DEPLOYED |
| btcproute | ST969AZNDX2P7N1YJ0DNVGC8QEKT388DBMXGHR9Z.btcproute | 200 DEPLOYED |
| liquidityocean | ST969AZNDX2P7N1YJ0DNVGC8QEKT388DBMXGHR9Z.liquidityocean | 200 DEPLOYED |
| behaviorallimitorder | ST969AZNDX2P7N1YJ0DNVGC8QEKT388DBMXGHR9Z.behaviorallimitorder | 200 DEPLOYED |

## 0.2 Validator Funding Verification

| Validator | Address | Balance (microSTX) | Funded |
|-----------|---------|--------------------:|:------:|
| V1 | ST2HTG5KX41N69DTSF49QGNP4W1XDGWKPP46ZMV67 | 1,700,000 | ✓ |
| V2 | ST227WJ8TFQZFWWP914FXF3GYXSETCRCJRF3N7NJA | 1,800,000 | ✓ |
| V3 | ST2SXN6HP9EBYN8RJSP9N4WKK6XM007A7R3YSXYA | 1,900,000 | ✓ |

3 distinct funded principals confirmed.

## 0.3 Q2 Release Transaction

- **TX Hash:** `0x7563960ead1931204233f9f88fcb719209b2c7fbf63746c0a0e0246906e8e176`
- **Status:** success
- **Block:** 309388
- **Function:** release-escrow
- **Contract:** ST969AZNDX2P7N1YJ0DNVGC8QEKT388DBMXGHR9Z.btcpescrow
- **Quorum:** 3-of-3 (3 distinct funded signers attested)

## 0.4 verify-anchor Transaction

- **TX Hash:** `0x01c3bdb45dd562b5affcad7621b9cfefa9977c819c62311dd8b2c9bb3a110d03`
- **Status:** success
- **Block:** 309526
- **Function:** verify-anchor
- **Contract:** ST969AZNDX2P7N1YJ0DNVGC8QEKT388DBMXGHR9Z.spv-v2

## 0.5 20/20 verify-anchor Rounds

All 20 rounds succeeded. TX hashes recorded in `docs/proofs/stacks_verify_anchor_results.json`.

| Round | TX Hash |
|------|---------|
| R1 | 0x7b5f8095aedad7917091905a66d6e0d94516228fd46a7f6f2c83f4bb936085d9 |
| R2 | 0x21dcb33d9e2d650761f30403d3f505bbc583dd1c8367e22d98aa4f1f4ae66717 |
| R3 | 0x12681353abef63d1bcef7b049b34d01d12026421e1a98ac589a3bc9442964171 |
| R4-R20 | See stacks_verify_anchor_results.json (all success) |

## 0.6 4-Way Anchor Parity

anchor_bh for tx `62bfe73f...` block `5128449`:

| Implementation | anchor_bh |
|---------------|-----------|
| Python reference | `0xae9775361e4acf32613c2d0b4c6760aec2d831bb7320d1cccb6821552636b55a` |
| Cairo (Starknet) | `0xae9775361e4acf32613c2d0b4c6760aec2d831bb7320d1cccb6821552636b55a` |
| Solidity (Arbitrum) | `0xae9775361e4acf32613c2d0b4c6760aec2d831bb7320d1cccb6821552636b55a` |
| Clarity (Stacks) | `0xae9775361e4acf32613c2d0b4c6760aec2d831bb7320d1cccb6821552636b55a` |

**All byte-identical.** ✓
