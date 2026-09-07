# TRION BTC↔Starknet Zero-Bridge — Mainnet Runbook

## Checkpoint Selection Rule
- Select a Bitcoin block at depth >= 4032 from the current tip (approximately 4 weeks).
- The checkpoint block hash + height + bits + time are set via `set_genesis_tip()`.
- After setting, call `renounce_genesis_ability()` — this makes the checkpoint immutable.

## Deploy Sequence
1. Deploy BTCSPVVerifier with `mainnet_strict=true` (constructor: owner, true).
2. Deploy BTCPEscrowV2 (constructor: owner).
3. Call `set_genesis_tip(checkpoint_hash, height, bits, time)` on SPV.
4. Call `renounce_genesis_ability()` on SPV.
5. Call `add_validator()` for each of the 5 DW-BFT validators on EscrowV2.
6. Call `set_quorum_required(3)` on EscrowV2.
7. Call `set_trion_oracle(oracle_address)` on EscrowV2 (one-way, immutable).

## Quorum Onboarding
- Validators are added via `add_validator()` (owner-only).
- The validator set should be 5 DW-BFT validators with geographic and infrastructure diversity.
- Quorum threshold: 3-of-5 (configurable via `set_quorum_required()`).
- Bootstrap mode (unbound) is NOT allowed on mainnet — quorum must be set before any escrow is locked.

## Rollback / Reorg Procedure
1. Owner calls `initiate_rewind()` — starts a 24-hour time lock.
2. During the 24h window, the competing header chain must be submitted via `submit_block_header()` (each header PoW+linkage verified).
3. After 24h, owner calls `execute_rewind(new_tip_hash, new_tip_height)` — switches the tip to the stored block.
4. Anchors on the orphaned branch will fail `verify_anchor` (depth may be insufficient relative to the new tip).

## Monitoring Alerts
- **Linkage stall**: no new headers submitted for > 2 hours → alert relayer.
- **Quorum loss**: attestation count < quorum_required for > 5 minutes → alert validators.
- **Depth-gate starvation**: verify_anchor calls reverting with "SPV: depth insufficient" → relayer needs to sync more headers.
- **Dispute state**: `AttestationMismatch` event emitted → investigate validator disagreement.

## Gas Budget Estimate
- `submit_block_header`: ~80-byte SHA-256 double hash + linkage + retarget = ~200k-500k gas.
- `verify_anchor`: Merkle proof + anchor recomputation = ~100k-300k gas.
- `release_escrow` (quorum-bound): attestation checks + coherence floor = ~50k-100k gas.

## Ownership/Upgrade Policy
- Contracts deployed WITHOUT proxy (immutable bytecode).
- No upgrade path — bug fixes require redeployment + re-checkpoint.
- This is the safest policy for a trust-minimization-focused system.

## Trust Statement
"Trust = one immutable genesis checkpoint (renounced after init) + code + multi-source ingestion honesty at fetch time. Release authority = DW-BFT quorum (3-of-5), not relayer."
