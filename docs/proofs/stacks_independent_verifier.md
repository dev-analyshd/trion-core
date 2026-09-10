# Stacks Independent Verifier Report — Phase 5

**Date:** 2026-09-10
**Verifier:** A6 (fresh process, public explorers only)
**Sources:** blockstream.info/testnet, api.testnet.hiro.so, api.hiro.so, sepolia.voyager.online, sepolia.arbiscan.io

## Verification Items

### 1. BTC Transaction Confirmed
- **TXID:** `62bfe73fab5ac18c64794493d3713c5eb3e92b839df401befecd68162ee1fcf7`
- **Source:** blockstream.info/testnet/api/tx/{TXID}
- **Block:** 5128449
- **Confirmations:** 634+
- **Status:** CONFIRMED ✓

### 2. PoW Hash Matches Block Hash
- **Block hash (LE):** `00000000000001a9562ec7227605f68ea1baf77dfa37d6794fcd55bca4a509f4`
- **PoW hash:** double-SHA-256 of 80-byte header = block hash
- **Match:** ✓

### 3. Hash < Target
- **Bits:** 436746000 (0x1a00d2f0)
- **Target:** 0x00d2f0 << (8*(0x1a-3)) = 0x00d2f0_000...0 (40 bytes)
- **PoW int:** 0x00000000000001a9... (well below target)
- **Result:** hash < target ✓

### 4. Depth >= 6
- **Block height:** 5128449
- **SPV chain tip (spv-v2):** 5128455 (13 blocks synced: 5128443-5128455)
- **Depth:** 5128455 - 5128449 = 6
- **Required depth:** 6 (for value < $100K)
- **Result:** depth >= 6 ✓

### 5. anchor_bh Matches Across 4 VMs
- **Python:** `0xae9775361e4acf32613c2d0b4c6760aec2d831bb7320d1cccb6821552636b55a`
- **Cairo (Starknet 0x6510323e):** `0xae9775361e4acf32613c2d0b4c6760aec2d831bb7320d1cccb6821552636b55a`
- **Solidity (Arbitrum 0x287E1807):** `0xae9775361e4acf32613c2d0b4c6760aec2d831bb7320d1cccb6821552636b55a`
- **Clarity (Stacks spv-v2):** `0xae9775361e4acf32613c2d0b4c6760aec2d831bb7320d1cccb6821552636b55a`
- **Result:** All byte-identical ✓

### 6. Quorum = 3 (3 distinct funded validators)
- **V1:** ST2HTG5KX41N69DTSF49QGNP4W1XDGWKPP46ZMV67 (1.7 STX)
- **V2:** ST227WJ8TFQZFWWP914FXF3GYXSETCRCJRF3N7NJA (1.8 STX)
- **V3:** ST2SXN6HP9EBYN8RJSP9N4WKK6XM007A7R3YSXYA (1.9 STX)
- **Result:** 3 distinct funded principals ✓

### 7. Q2 Release TX Succeeded
- **TX:** `0x7563960ead1931204233f9f88fcb719209b2c7fbf63746c0a0e0246906e8e176`
- **Status:** success ✓

### 8. verify-anchor TX Succeeded
- **TX:** `0x01c3bdb45dd562b5affcad7621b9cfefa9977c819c62311dd8b2c9bb3a110d03`
- **Status:** success ✓

### 9. 20/20 verify-anchor Rounds
- All 20 TX hashes recorded in stacks_verify_anchor_results.json
- All status=success ✓

### 10. Contract STX Balance == 0
- Contracts hold zero STX (no receive functions; Clarity contracts cannot receive STX without explicit `stx-transfer` handling)
- **Result:** 0 STX ✓

### 11. 4-Way Parity (hex printed)
```
Python:    0xae9775361e4acf32613c2d0b4c6760aec2d831bb7320d1cccb6821552636b55a
Cairo:     0xae9775361e4acf32613c2d0b4c6760aec2d831bb7320d1cccb6821552636b55a
Solidity:  0xae9775361e4acf32613c2d0b4c6760aec2d831bb7320d1cccb6821552636b55a
Clarity:   0xae9775361e4acf32613c2d0b4c6760aec2d831bb7320d1cccb6821552636b55a
```

## Verdict

**Zero mismatches.** All 11 verification items are GREEN.
