# Phase 0 — Research & Pins

## 0.1 Contract Deltas

| Contract | Status | Delta Needed |
|----------|--------|-------------|
| BTCSPVVerifierArb.sol | Exists, deployed | Rename → BTCSPVVerifier.sol (chain-agnostic) |
| OOAAnchorRegistry.sol | Exists | Already generic, keep |
| BTCPEscrow.sol | Exists | Add quorum 3-of-5, etch-once, freshness, dispute fail-closed |
| BTCPIntent.sol | Exists | Verify intent_hash storage |
| BTCPRoute.sol | Exists | Verify anchor_bh → execution_bh linkage |
| LiquidityOcean.sol | Exists | Verify threshold 300000 + OOA confidence formula |
| BehavioralLimitOrder.sol | Exists | Verify partial fill/expiry |

## 0.2 Anchor Parity

anchor_bh for tx 62bfe73f... block 5128449:
- Python/Solidity: 0xae9775361e4acf32613c2d0b4c6760aec2d831bb7320d1cccb6821552636b55a
- Starknet (0x6510323e...): 0xae9775361e4acf32613c2d0b4c6760aec2d831bb7320d1cccb6821552636b55a (verified in prior 20-round test)
- Parity: CONFIRMED byte-identical

## 0.3 Oracle Binding Decision

Decision: (b) Event linkage + relayer cross-ref.
The TRIONOracle submitSignal() uses a fixed Signal struct that doesn't accommodate anchor data.
OOAAnchorRegistry emits AnchorObserved events; relayer cross-references via entityId.
Oracle is untouched. Binding is off-chain reference, honestly labeled.

## 0.4 Gas Model

- SHA-256 precompile (0x02): 22,395 gas per 80-byte hash (measured via eth_estimateGas)
- Double-SHA-256: ~44,790 gas (2x precompile)
- Stylus: OPEN (precompile exists but cargo-stylus not available in environment)
- Production path: Solidity with precompile 0x02
