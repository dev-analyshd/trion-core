# DBP Implementation Plan — Making the Primitive Production-Ready

**Status:** DRAFT
**Date:** 2026-10-14
**Prerequisites:** DBP_PRIMITIVE_SPEC.md, DECENTRALIZED_PUBLISHER_NETWORK.md, DEFI_INTEGRATION_FLOW.md

---

## Current State (What's Proven)

| Component | Status | Evidence |
|-----------|--------|----------|
| DBP primitive (80-byte payload + SHA-256 commit) | ✅ Proven on Bitcoin testnet | Block 5197632, tx `edd5aa4a...` |
| CSV refund path (borrower self-rescue) | ✅ Proven on Bitcoin testnet | Block 5158921, tx `cd1c1bf6...` |
| Stacks v5 contract (register + publish-preimage) | ✅ Proven on Stacks testnet | Block 726560+ |
| Cross-chain hash parity (sha256 matches on both chains) | ✅ Proven | Same hash verified on BTC + Stacks |
| 15 Clarity contracts deployed | ✅ Live on Stacks testnet | ST969AZNDX2P7N1YJ0DNVGC8QEKT388DBMXGHR9Z.* |
| Formal spec written | ✅ Complete | docs/spec/DBP_PRIMITIVE_SPEC.md |
| Publisher network designed | ✅ Complete | docs/design/DECENTRALIZED_PUBLISHER_NETWORK.md |
| DeFi integration flow designed | ✅ Complete | docs/design/DEFI_INTEGRATION_FLOW.md |

## What's Missing (The Gap to Production)

### Phase 1: Publisher Network Contract (Week 1-2)

**Goal:** Eliminate the single-TRION liveness assumption.

**Deliverables:**
1. `PublisherRegistry.clar` — Stacks contract for publisher registration, staking, slashing
   - `register-publisher(stake-amount)` — publisher locks STX
   - `heartbeat()` — publisher proves liveness every 12 BTC blocks
   - `slash(publisher)` — permissionless slashing if publisher misses heartbeat
   - `withdraw()` — publisher exits after unstake delay (144 blocks)
   - `claim-bounty(vault-id)` — first relayer to broadcast BTC spend claims bounty

2. Publisher daemon (off-chain)
   - Monitors Stacks for liquidation events
   - Computes DBP payload from Bitcoin block data
   - Calls `publish-preimage` on Stacks
   - Sends heartbeat every 12 BTC blocks

3. Relayer daemon (off-chain)
   - Monitors Stacks for preimage publication events
   - Reads the 80-byte payload from the event
   - Constructs Bitcoin spend transaction (witness = [payload, script, controlBlock])
   - Broadcasts to Bitcoin
   - Claims bounty on Stacks

**Success criteria:** 3 independent publishers running, any one can trigger liquidation.

### Phase 2: Vault V6 Contract (Week 2-3)

**Goal:** Connect the vault to the lending protocol.

**Deliverables:**
1. `TRIONCoherenceVaultV6.clar` — extended vault with DeFi integration
   - New states: `ACTIVE`, `LIQUIDATING`, `LIQUIDATED`, `RELEASED`
   - `activate-vault(vault-id)` — lender activates after reviewing terms
   - `release-vault(vault-id)` — lender releases after borrower repays (happy path)
   - `mark-liquidating(vault-id)` — called by BTCPLend when loan defaults
   - `mark-liquidated(vault-id)` — called after BTC spend confirms
   - `release-clawback(vault-id)` — handles late-repay race condition
   - `is-vault-borrowable(vault-id)` — read-only check for BTCPLend

2. `BTCPLendV5.clar` — updated lending protocol
   - `borrow()` now checks `is-vault-borrowable` before allowing borrow
   - `liquidate()` now calls `mark-liquidating` on the vault
   - Escrow: 30 bps of borrow amount goes to publisher bounty fund

**Success criteria:** Full flow tested on testnet — borrow against BTC vault, default, liquidation triggered, preimage published, BTC spent to lender.

### Phase 3: Coherence Gate Integration (Week 3-4)

**Goal:** Wire the coherence engine to the liquidation trigger.

**Deliverables:**
1. `CoherenceGate.clar` — Stacks contract that gates liquidation
   - `check-coherence(entity-id) → (coherence, threshold)` — read-only
   - `gate-liquidation(vault-id)` — called before `mark-liquidating`
   - Asserts `coherence >= threshold` (0.55 minimum, dynamic up to 0.92)
   - If coherence drops, liquidation is BLOCKED (fail-closed)

2. Coherence oracle (off-chain)
   - Computes C(t) = α·Φ + β·M + γ·Σ + δ·K + ε·A
   - Publishes coherence score on Stacks every N blocks
   - Signs with DW-BFT quorum

**Success criteria:** Liquidation is blocked when coherence < 0.55. Liquidation proceeds when coherence >= 0.55.

### Phase 4: Security Hardening (Week 4-6)

**Goal:** Make the primitive production-ready.

**Deliverables:**
1. Third-party audit (Trail of Bits or OpenZeppelin)
   - Audit the Bitcoin Script (35 bytes + 37 bytes)
   - Audit the Clarity contracts (PublisherRegistry, VaultV6, BTCPLendV5, CoherenceGate)
   - Audit the 80-byte payload format

2. Bug bounty (Immunefi)
   - $1M critical tier
   - Scope: all deployed contracts + the Bitcoin Script
   - Duration: 90 days minimum

3. Formal verification
   - Lean 4 proof that `SHA-256(payload) == H` implies the Bitcoin Script evaluates to TRUE
   - Lean 4 proof that the CSV refund path is always available after `csv_blocks`
   - Z3 SMT verification of the state machine (no invalid transitions)

4. Test vector generation
   - 100 test vectors for the 80-byte payload format
   - Cross-implementation test (Python, JavaScript, Clarity all produce the same hash)

**Success criteria:** Audit passes with no critical findings. Bug bounty launches.

### Phase 5: Mainnet Deployment (Week 6-8)

**Goal:** Deploy on Bitcoin mainnet + Stacks mainnet.

**Deliverables:**
1. Deploy on Stacks mainnet
   - PublisherRegistry
   - TRIONCoherenceVaultV6
   - BTCPLendV5
   - CoherenceGate

2. Deploy publisher + relayer daemons
   - 5 independent publishers (different geographies, different teams)
   - Open relayer marketplace (anyone can run a relayer)

3. First mainnet vault
   - Borrower locks 0.01 BTC (real value)
   - Borrows against it
   - Repays (happy path test)
   - Then a second vault where the borrower defaults (liquidation test)

**Success criteria:** Real BTC locked and released on Bitcoin mainnet. No funds lost.

### Phase 6: Standardization (Week 8-12)

**Goal:** Make the DBP a recognized standard.

**Deliverables:**
1. BIP draft
   - Define the 80-byte payload format as a Bitcoin Improvement Proposal
   - Define the script template (`OP_SHA256 <hash> OP_EQUAL` + CSV refund)
   - Include test vectors and reference implementation

2. Academic paper
   - Submit to IACR ePrint
   - Formal security model + proofs
   - Comparison to existing BTC lock mechanisms

3. SDK
   - TypeScript library for generating vaults
   - Python library for computing DBP payloads
   - Rust library for relayer integration

4. Documentation
   - Developer guide
   - Integration guide for DeFi protocols
   - Security model documentation

**Success criteria:** BIP draft submitted. Paper on ePrint. SDK with 3 language bindings.

---

## Trust Model Summary

| Property | Before (current) | After (planned) |
|----------|-----------------|-----------------|
| Safety (can't steal BTC) | ✅ Trustless (SHA-256 + CSV) | ✅ Same |
| Liveness (can liquidate) | ❌ TRION must publish | ✅ Any 1-of-n publishers |
| Coherence gate | ❌ TRION decides | ✅ On-chain check (CoherenceGate.clar) |
| Relay censorship | ✅ Anyone can relay | ✅ Same + bounty incentive |
| Borrower self-rescue | ✅ CSV after timelock | ✅ Same |
| Audit | ❌ Self-audited only | ✅ Third-party (Trail of Bits) |
| Bug bounty | ❌ Not launched | ✅ $1M on Immunefi |
| Formal proof | ❌ Informal sketches | ✅ Lean 4 + Z3 SMT |
| Standardization | ❌ Internal only | ✅ BIP draft + ePrint paper |

---

## Timeline

| Phase | Duration | Key Milestone |
|-------|----------|--------------|
| 1. Publisher Network | 2 weeks | 3 publishers running on testnet |
| 2. Vault V6 + Lend V5 | 2 weeks | Full DeFi flow tested on testnet |
| 3. Coherence Gate | 2 weeks | Liquidation blocked when C(t) < Θ(t) |
| 4. Security Hardening | 3 weeks | Audit passes + bug bounty launches |
| 5. Mainnet | 2 weeks | Real BTC locked + released on mainnet |
| 6. Standardization | 4 weeks | BIP draft + ePrint paper + SDK |
| **Total** | **15 weeks** | **Production-ready primitive** |
