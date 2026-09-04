# TRION BTCP — Solana Anchor Programs Integration Guide

This guide covers the full lifecycle: building, deploying, and integrating the
Solana BTCP programs into the TRION relayer and test framework.

---

## 📦 Project Structure

```
trion-svm/
├── Anchor.toml                      # Workspace configuration
├── Cargo.toml                       # Workspace Cargo manifest
├── programs/
│   ├── btcp_common/                 # Shared types, errors, constants
│   │   └── src/lib.rs
│   ├── btcp_escrow/                 # Two-state atomic escrow
│   │   ├── Cargo.toml
│   │   └── src/lib.rs
│   ├── btcp_intent/                 # Intent registry
│   │   ├── Cargo.toml
│   │   └── src/lib.rs
│   └── btcp_route/                  # Route proof tracking
│       ├── Cargo.toml
│       └── src/lib.rs
├── scripts/
│   ├── deploy.sh                    # One-shot deployment script
│   └── initialize_programs.ts       # Config PDA initialization
└── tests/                           # Anchor integration tests (TS)
```

---

## 🔧 Stage 1: Build

### Option A: Using Anchor CLI (recommended)

```bash
# Install Anchor if needed
cargo install --git https://github.com/coral-xyz/anchor avm --locked --force
avm install latest
avm use latest

# Build all programs
cd trion-svm
anchor build --arch sbf
```

### Option B: Using cargo-build-sbf directly

```bash
# Install Solana CLI tools if needed
sh -c "$(curl -sSfL https://release.solana.com/stable/install)"

# Build each program individually
cargo-build-sbf --manifest-path programs/btcp_common/Cargo.toml --sbf-out-dir target/deploy
cargo-build-sbf --manifest-path programs/btcp_escrow/Cargo.toml  --sbf-out-dir target/deploy
cargo-build-sbf --manifest-path programs/btcp_intent/Cargo.toml  --sbf-out-dir target/deploy
cargo-build-sbf --manifest-path programs/btcp_route/Cargo.toml   --sbf-out-dir target/deploy
```

### Verify compilation

```bash
# Host-target check (catches all type errors)
export CARGO_TARGET_DIR=/tmp/cargo_target
cargo check
# Expected: Finished `dev` profile — no errors, only cfg warnings
```

---

## 🚀 Stage 2: Deploy to Devnet

```bash
# Make sure your wallet has SOL
solana config set --url devnet
solana airdrop 2   # Repeat if needed

# Run deployment script
chmod +x scripts/deploy.sh
./scripts/deploy.sh
```

The script will:
1. Generate program keypairs (if not exist)
2. Update `declare_id!()` in each source file
3. Build for SBF target
4. Deploy all three programs
5. Save deployment addresses to `target/deploy/deployment_devnet_*.json`

### Manual deploy (alternative)

```bash
solana program deploy target/deploy/btcp_escrow.so  --program-id target/deploy/btcp_escrow-keypair.json
solana program deploy target/deploy/btcp_intent.so  --program-id target/deploy/btcp_intent-keypair.json
solana program deploy target/deploy/btcp_route.so   --program-id target/deploy/btcp_route-keypair.json
```

---

## ⚙️ Stage 3: Initialize Config PDAs

Each program needs its config PDA initialized **once** after deployment. This sets
the deployer as owner + initial relayer.

```bash
cd trion-svm
npm install @project-serum/anchor @solana/web3.js

# Set environment variables from deployment output
export BTCP_ESCROW_ID=<deployed_escrow_id>
export BTCP_INTENT_ID=<deployed_intent_id>
export BTCP_ROUTE_ID=<deployed_route_id>

# Run initialization
npx ts-node scripts/initialize_programs.ts
```

### Update relayer (after initialization)

Once the TRION relayer has its own Solana keypair, transfer relayer authority:

```typescript
// Call setRelayer on each program with the relayer's pubkey
await program.methods
  .setRelayer(new anchor.web3.PublicKey(RELAYER_PUBKEY))
  .accounts({
    config: configPda,
    owner: deployerWallet.publicKey,
  })
  .signers([deployerWallet])
  .rpc();
```

---

## 🔗 Stage 4: PDA Address Derivation

Clients and the relayer need to derive PDA addresses to interact with programs.

### In TypeScript:

```typescript
import { PublicKey } from "@solana/web3.js";

const SEED_CONFIG  = Buffer.from("config");
const SEED_ESCROW  = Buffer.from("escrow");
const SEED_INTENT  = Buffer.from("intent");
const SEED_ROUTE   = Buffer.from("route");
const SEED_VAULT   = Buffer.from("vault");

// Config PDA per program
const [configPda, configBump] = PublicKey.findProgramAddressSync(
  [SEED_CONFIG],
  BTCP_ESCROW_PROGRAM_ID
);

// Escrow PDA from escrow_id (32-byte Uint8Array)
const escrowIdBytes = Buffer.from(escrowIdHex, "hex");
const [escrowPda, escrowBump] = PublicKey.findProgramAddressSync(
  [SEED_ESCROW, escrowIdBytes],
  BTCP_ESCROW_PROGRAM_ID
);

// Vault PDA (holds the SOL)
const [vaultPda, vaultBump] = PublicKey.findProgramAddressSync(
  [SEED_VAULT, escrowIdBytes],
  BTCP_ESCROW_PROGRAM_ID
);

// Intent PDA from intent_hash (32 bytes)
const [intentPda] = PublicKey.findProgramAddressSync(
  [SEED_INTENT, intentHashBytes],
  BTCP_INTENT_PROGRAM_ID
);

// Route PDA from route_id (32 bytes)
const [routePda] = PublicKey.findProgramAddressSync(
  [SEED_ROUTE, routeIdBytes],
  BTCP_ROUTE_PROGRAM_ID
);
```

### In Python (for the existing test framework):

```python
from solders.pubkey import Pubkey
from solders.keypair import Keypair

SEED_CONFIG = b"config"
SEED_ESCROW = b"escrow"
SEED_INTENT = b"intent"
SEED_ROUTE  = b"route"
SEED_VAULT  = b"vault"

BTCP_ESCROW_ID = Pubkey.from_string("BTCP111111111111111111111111111111111111111")

# find_program_address returns (pda, bump)
escrow_id_bytes = bytes.fromhex(escrow_id_hex)
escrow_pda, escrow_bump = Pubkey.find_program_address(
    [SEED_ESCROW, escrow_id_bytes],
    BTCP_ESCROW_ID
)
```

---

## 🎮 Stage 5: Instruction Reference

### btcp_escrow — `lock_escrow`

**Accounts:**
| Name | Writable | Signer | Description |
|---|---|---|---|
| `config` | ✅ | ❌ | PDA: `["config"]` |
| `relayer` | ✅ | ✅ | Owner or relayer authority |
| `vault_funder` | ✅ | ✅ | Account providing the SOL to lock |
| `escrow` | ✅ | ❌ | PDA: `["escrow", escrow_id]` (init) |
| `vault` | ✅ | ❌ | PDA: `["vault", escrow_id]` |
| `destination` | ❌ | ❌ | Recipient address on release |
| `system_program` | ❌ | ❌ | System Program |

**Args:** `escrow_id: [u8; 32], route_id: [u8; 32], intent_hash: [u8; 32],
entity_id: BEOIdentity, amount: u64, min_coherence: u64, source_chain: u32,
dest_chain: u32, anchor_bh: [u8; 32], execution_bh: [u8; 32], timeout_slots: u64`

The full CANONICAL_CERTIFICATE.md §4.2-Step-3 binding set (intent hash,
route legs, anchor/execution behavioral hashes) is recorded at lock time
so every release certificate is checked against the escrow's OWN state
(step 7). `dest_chain` must equal the deployment's `self_chain`; pause
blocks new locks only.

**Lamports:** Only `amount` lamports (the Solidity `msg.value` analog) are
transferred from `vault_funder` to the vault PDA — the funder's remaining
balance stays untouched. The `relayer` pays the escrow account rent
(≈0.002 SOL).

---

### btcp_escrow — `release_escrow` (C-03 closure — certificate-gated)

**Accounts:**
| Name | Writable | Signer | Description |
|---|---|---|---|
| `config` | ❌ | ❌ | PDA: `["config"]` |
| `submitter` | ✅ | ✅ | **Permissionless** — no release authority; pays consumed-PDA rent |
| `registry` | ❌ | ❌ | PDA: `["trion", "validators", epoch_be]` — must exist for the cert epoch |
| `escrow` | ✅ | ❌ | PDA: `["escrow", escrow_id]` |
| `vault` | ✅ | ❌ | PDA: `["vault", escrow_id]` |
| `destination` | ✅ | ❌ | Must match `escrow.destination` AND the certificate settlement tuple |
| `consumed` | ✅ | ❌ | PDA: `["trion", "consumed", escrow_id]` (init_if_needed) |
| `instructions` | ❌ | ❌ | `SYSVAR_INSTRUCTIONS_PUBKEY` — the signature-introspection source |
| `system_program` | ❌ | ❌ | System Program |

**Args:** `payload: Vec<u8>` (the 346-byte canonical signing payload P),
`cert_epoch: u32` (must equal the payload's epoch — drives the registry
PDA seeds), `envelope: { family: u8, signatures: Vec<{ validator_id,
stake_weight, diversity_weight, signature: Vec<u8> }> }`

The instruction runs the CANONICAL_CERTIFICATE.md §6 sequence fail-closed:
structure → epoch + grace → freshness (Clock sysvar, 60 s drift lower-bound
only) → HHI/AWA/coherence/threshold preconditions → **runtime-verified
ed25519 signatures over the RAW P** (the transaction carries native
`Ed25519SigVerify` instructions before the release instruction; the program
introspects them through the instructions sysvar and requires the runtime
to have verified exactly (registered validator pubkey, envelope signature,
this payload) — one missing or divergent verification fails the whole
certificate) → weight-quorum recomputed from the registry (L4.2 tiers:
3·signed > 2·total strict / 4·signed ≥ 3·total / 20·signed ≥ 17·total) →
full binding against the escrow state (escrow/route/intent/entity ids,
settlement tuple, chains, anchor/execution BH, min_coherence floor) →
consumed-certificate replay/equivocation gate → state/timeout guard →
lamports transfer. Resubmitting the exact same certificate is an
idempotent no-op; a different certificate for a consumed escrow is a
CONFLICT and emits equivocation evidence.

**Transaction layout (client side):**

```ts
// 1. one ComputeBudget request (introspection + precompile CU)
// 2. Ed25519SigVerify instruction(s) covering every envelope signature:
//    either self-contained entries (publicKey+signature+message) via
//    web3.js Ed25519Program.createInstructionWithPublicKey(...), or a
//    hand-built instruction with 14-byte offsets entries whose signature /
//    message fields cross-reference the release instruction's data
//    (index = release instruction index, NOT u16::MAX) to save ~410 bytes
//    per signature — only the 32-byte pubkeys must be embedded.
// 3. escrow.releaseEscrow(payload, certEpoch, envelope) with the accounts
//    table above (do not forget instructions: SYSVAR_INSTRUCTIONS_PUBKEY).
```

The Ed25519SigVerify instruction must be placed **before** the release
instruction (the program only introspects already-executed instructions).
The program parses the precompile's offsets header with the runtime's own
index semantics and requires an exact three-way byte match — the
"wrong-offset" bypass class (Relay, Sept 2025) is closed.

**Compute budget & size ceiling:** the precompile charges CU per verified
signature — request a compute budget sized for the quorum. Solana
transactions are capped at ~1232 bytes: a release fits roughly 2
self-contained signatures, or ~4 signatures using cross-instruction
references (payload+signature live once in the release instruction).
Larger quorums (the 100-validator launch target) need aggregate
signatures (CANONICAL_CERTIFICATE.md §14.3, family 4 BLS — deferred) or a
future staged-certificate design; until then deploy with devnet-scale
validator sets.

---

### btcp_escrow — `revert_escrow`

**Accounts:**
| Name | Writable | Signer | Description |
|---|---|---|---|
| `config` | ❌ | ❌ | PDA: `["config"]` |
| `caller` | ❌ | ✅ | Anyone (for timeout) or relayer/owner |
| `escrow` | ✅ | ❌ | PDA: `["escrow", escrow_id]` |
| `vault` | ✅ | ❌ | PDA: `["vault", escrow_id]` |
| `locked_by` | ✅ | ❌ | Must match `escrow.locked_by` |
| `system_program` | ❌ | ❌ | System Program |

**Args:** `reason: u8` (0=Timeout, 1=CoherenceFailure, 2=RouteInvalid, 3=Manual)

---

### btcp_intent — `register_intent`

**Accounts:** `config`, `relayer` (signer, mut), `intent` (PDA init), `system_program`

**Args:** `intent_hash, entity_id, action, asset_in, asset_out, magnitude, deadline, max_total_gas, min_finality, min_nl_score, privacy`

---

### btcp_intent — `update_status`

**Accounts:** `config`, `relayer` (signer), `intent` (PDA, mut)

**Args:** `new_status: u8` (0=Pending, 1=Routing, 2=Executing, 3=Completed, 4=Failed, 5=Expired, 6=Resurrected)

---

### btcp_route — `publish_route`

**Accounts:** `config`, `relayer` (signer, mut), `route` (PDA init), `system_program`

**Args:** `route_id, intent_hash, anchor_bh, anchor_chain, execution_chain, entity_id, route_type`

---

### btcp_route — `finalize_route`

**Accounts:** `config`, `relayer` (signer), `route` (PDA, mut)

**Args:** `execution_bh, gas_saved_vs_bridge, beo_continuity, cc_coherence`

---

## 🔄 Relayer Integration

The existing `trion-svm` Rust indexer crate needs to be extended with a
**transaction executor** module that calls these programs.

### Key changes to `indexers/crates/trion-svm/`:

1. **Add RPC client** for sending transactions (not just reading)
2. **Add relayer keypair** loading from config/env
3. **Implement instruction builders** for each program instruction
4. **Add PDA derivation** helpers
5. **Integrate into the unified relayer** loop alongside EVM relaying

### Example: Cross-VM Zero-Bridge Flow in Relayer

```
1. Entity A registers intent on Solana:
   → btcp_intent.register_intent(
       intent_hash = hash("give 0.5 SOL, want 3 BOT on BOT Chain"),
       entity_id = BEO_A_solana,
       ...
     )

2. Entity B registers intent on BOT Chain (EVM):
   → BTCPIntent.registerIntent(
       intent_hash = hash("give 3 BOT, want 0.5 SOL on Solana"),
       entityId = BEO_B_evm,
       ...
     )

3. Relayer observes intents on BOTH chains, detects complementarity:
   → Entity A gives SOL ↔ Entity B wants SOL
   → Entity B gives BOT ↔ Entity A wants BOT
   ✓ Cross-VM: BEO binding verified

4. Relayer triggers escrow locks:
   → On Solana: btcp_escrow.lock_escrow(
       escrow_id, route_id, BEO_B_solana,
       amount = 500_000_000,        // 0.5 SOL in lamports — exactly what is locked
       min_coherence=500000, timeout_slots=300
     )
     [vault_funder = Entity A's Solana wallet, 0.5 SOL transferred to vault PDA]

   → On BOT Chain: BTCPEscrow.lockEscrow(...) already done in EVM

5. TRION consensus computes BTCP score:
   → BTCP_score = 0.8655 ≥ 0.50 threshold ✓ SAFE

6. Relayer triggers atomic releases:
   → On Solana: btcp_escrow.release_escrow(
        payload = P (346 bytes), cert_epoch, envelope = {family: 2, signatures})
      with the epoch-registry PDA ["trion", "validators", epoch_be], the
      consumed PDA ["trion", "consumed", escrow_id], the instructions
      sysvar, and — placed BEFORE the release instruction — the
      Ed25519SigVerify instructions covering every envelope signature
      (see the release_escrow reference above)
     )
     [vault PDA sends 0.5 SOL to Entity B's Solana address — the exact
      (destination, amount) settlement tuple the certificate signed]

   → On BOT Chain: BTCPEscrow.releaseEscrow(...) already done in EVM

7. Relayer publishes route proof:
   → btcp_route.publish_route(route_id, intent_hash, anchor_bh, ...)
   → btcp_route.finalize_route(route_id, execution_bh, gas_saved, ...)
```

---

## 🧪 Testing

### Unit tests (Rust)

```bash
cd trion-svm
cargo test -p btcp_escrow
cargo test -p btcp_intent
cargo test -p btcp_route
```

### Integration tests (Anchor + TypeScript)

```bash
# Start local test validator
solana-test-validator --reset &

# Run Anchor tests
anchor test --arch sbf --skip-build --skip-deploy
```

### Full cross-VM zero-bridge test

Once the relayer integration is complete, the existing Python test framework
(`run_btcp_crossvm_hybrid.py`) can be extended to:
1. Replace the "simulated" Solana side with actual RPC calls to these programs
2. Use the user's Solana private key (`3wdbxnjc...`) as Entity A
3. Execute the full 8-phase flow with BOTH chains fully on-chain

---

## 📊 Solidity ↔ Anchor Equivalence Reference

| Solidity Concept | Anchor Equivalent |
|---|---|
| `mapping(bytes32 => Escrow)` | PDA per ID: `["escrow", escrow_id]` |
| `msg.value` | Separate `vault_funder` signer + system program CPI |
| `address payable destination` | `Pubkey` destination account |
| `block.number` | `Clock::get()?.slot` |
| `block.timestamp` | `Clock::get()?.unix_timestamp` |
| `require(cond, "MSG")` | `require!(cond, BTCPError::Variant)` |
| `emit Event(...)` | `emit!(Event { ... })` |
| `modifier onlyRelayer` | Check in instruction body: `config.is_authorized(&relayer.key())` |
| `escrows[escrowId].state = State.RELEASED` | Mutate `escrow.state` account field |
| `destination.call{value: amount}("")` | `invoke_signed(&system_instruction::transfer(...), &[&[seeds, &[bump]]])` |

---

## 🔐 Security Notes

1. **Vault PDA authority**: The vault PDA is a program-derived address whose
   authority is the btcp_escrow program itself. SOL can only leave the vault
   via `releaseEscrow` or `revertEscrow` instructions with proper authorization.

2. **Release authority = canonical certificates (C-03 closure)**: the old
   single-oracle-key release gate is REMOVED. `release_escrow` verifies the
   TRION canonical certificate (346-byte payload, ed25519 family signatures
   verified by the Ed25519SigVerify precompile via instruction introspection,
   epoch registry PDA `["trion","validators",epoch_be]`, L4.2 weight quorum,
   freshness, settlement-tuple binding, consumed-certificate replay gate).
   The bound TRION key is a **pause authority only** — it can never release.
   There is NO trusted-relayer/dev fallback release path; before the first
   `register_epoch` every certificate fails closed.

3. **Relayer authority**: The relayer can lock escrows and trigger
   non-timeout reverts. The owner can change the relayer and the registry
   admin (role separation: owner / relayer / pause authority / registry
   admin, master command §10). In production, the relayer should be the
   TRION relayer service's dedicated keypair, not the deployer.

4. **Escrow state machine**: HOLDING → RELEASED | REVERTED |
   EMERGENCY_REVERTED. No other transitions; all three terminal states
   have no outgoing transitions. Second release refused (state ≠ HOLDING
   + consumed-certificate PDA).

5. **Timeout safety + E6 escape**: Anyone can trigger `revertEscrow` with
   reason=Timeout after `lock_slot + timeout_slots`, and anyone can trigger
   reason=Emergency (EMERGENCY_REVERTED) after 7 days — even if TRION is
   silent or the program is paused. This prevents permanent fund lockup.

6. **Coherence enforcement**: the certificate's coherence must meet the
   emission threshold (which must equal the registered epoch Θ(t)) AND the
   escrow's own `min_coherence` floor etched at lock time (INV-003:
   deployment-local tightening, never loosening).

7. **Pause semantics**: `pause()` (pause authority or owner) blocks NEW
   `lock_escrow` only — settling escrows with valid certificates and
   reverting/timeout escapes are never pausable (M2).

8. **Epoch rotation**: `register_epoch` (registry admin, strictly
   increasing epochs, immutable sets) is the one per-epoch write; release
   rejects epochs older than `latest_epoch − 2` (grace) and unregistered
   epochs. Weights and D_consensus are recomputed from the registered
   entries — envelope weight claims are cross-checked, never trusted.

---

## 📁 Files Created

| File | Purpose |
|---|---|
| `programs/btcp_common/src/lib.rs` | Shared types, errors, constants |
| `programs/btcp_escrow/src/lib.rs` | Two-state atomic escrow program |
| `programs/btcp_intent/src/lib.rs` | Intent registry program |
| `programs/btcp_route/src/lib.rs` | Route proof tracking program |
| `programs/*/Cargo.toml` | Per-program Cargo manifests |
| `Cargo.toml` | Workspace Cargo manifest |
| `Anchor.toml` | Anchor workspace configuration |
| `scripts/deploy.sh` | One-shot deployment script |
| `scripts/initialize_programs.ts` | Config PDA initialization |
