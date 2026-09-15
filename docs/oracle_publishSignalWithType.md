# TRION Oracle V3 — `publishSignalWithType` Deployment & Upgrade Path

This document explains how to deploy the canonical typed-signal
publication path (`publishSignalWithType` + `getSignalType`) added to
`TRIONOracleV3` (TRION-TEAM-E, canonical fix), and what an upgrade of
an already-deployed oracle contract looks like.

## What was added

Two new external functions and one new storage mapping were added to
`contracts/solidity/TRIONOracleV3.sol` and mirrored in the interface
`contracts/solidity/interfaces/ITRIONOracleV3.sol`:

| Symbol                  | Kind     | Purpose                                                     |
| ----------------------- | -------- | ---------------------------------------------------------- |
| `publishSignalWithType` | function | Publish a behavioral signal AND record its canonical 24-member signal type (0..23) in one transaction. Internally calls `_publishBehavioralSignal(s)` (the extracted shared publication path) and then stores `signalTypeByEntity[s.entityId] = signalType`. Emits `BehavioralSignalPublished` (or `SilenceRecordedV2`) plus the new `SignalTypeRecorded(entityId, signalType)` event. |
| `getSignalType`         | function | Read-only accessor for the recorded signal type of an entity. Default value 0 = `VALUATION` (the canonical default carrier). |
| `signalTypeByEntity`    | mapping  | `bytes32 entityId → uint8 signalType` (0..23). Per the spec invariant "Exactly 24 signal types are defined; new types require a protocol fork" (`spec/signal_types.md`), `publishSignalWithType` reverts with `TRION: signal_type out of range` when `signalType >= 24`. |
| `SignalTypeRecorded`    | event    | `SignalTypeRecorded(bytes32 indexed entityId, uint8 signalType)` — emitted on every typed publication so off-chain indexers (api/blockchain.py, anima-service, dashboards) can route by type without a second `eth_call`. |

The shared internal helper `_publishBehavioralSignal(BehavioralSignal
calldata s)` was extracted from `publishBehavioralSignal` so the two
external entrypoints stay in lock-step on auth, plane-index validation,
signal-counters and event emission (including the structured-SILENCE
`SilenceRecordedV2` event).

## Why this matters

Before this fix, the oracle stored the *coherence* components of a
signal (Φ, M, Σ, K, A, moat, gap, eta) but not its *type*. An indexer
reading `getBehavioralSignal(entityId)` could see "this entity is
coherent at 0.74" but could not tell whether that signal was a
`VALUATION`, `BIOLOGICAL_CAPITAL`, `ENERGY_PARTICIPATION`,
`SOVEREIGN_BEHAVIORAL`, `BTCP_ROUTE`, `CONSENSUS_ADAPTATION`, or any of
the 24 canonical types from `core/master/signal_factory.py:SignalType`.

The typed path lets relayers and the publication pipeline
(`core/pipeline/signal_publication.py`) record exactly which canonical
signal type was emitted, so consumers can:

- route the signal to the right downstream plane (ANIMA for XSL/BC/EP/SBA,
  Akashic for VALUATION, governance for SBA, etc.),
- filter feed subscriptions by type (SDK `subscribe(minCoherence, signalType)`),
- audit type-level invariants (e.g. "an entity cannot have a
  `VALUATION` and a `BIOLOGICAL_CAPITAL` certified in the same block").

## Deployment sequence

### 1. Compile

```bash
cd /home/z/my-project/trion-core
# solc 0.8.20+ (pragma in TRIONOracleV3.sol)
solc --via-ir --optimize --bin \
  contracts/solidity/TRIONOracleV3.sol \
  -o build/TRIONOracleV3/ --overwrite
```

The compiled ABI is regenerated as
`contracts/solidity/compiled/TRIONOracleV3.json` (already updated to
include the four new entries: `publishSignalWithType`, `getSignalType`,
`signalTypeByEntity`, `SignalTypeRecorded`).

### 2. Deploy (fresh testnet)

```bash
# Using the existing deploy infrastructure (scripts/deploy_mainnet.py
# / scripts/mainnet_preflight.py):
DEPLOY_ORACLE_V3=1 \
ARB_SEPOLIA_RPC=https://sepolia-rollup.arbitrum.io/rpc \
RELAYER_PRIVATE_KEY=0x... \
python3 scripts/deploy_mainnet.py --target oracle_v3

# Record the deployed address in:
#   - api/blockchain.py default (ORACLE_ADDRESS env wins)
#   - proof-ledger/first_signal.json (first_signal_tx_hash field)
```

### 3. Verify the new functions are present on-chain

```bash
cast function <ORACLE_ADDRESS> 'getSignalType(bytes32)(uint8)' \
  0x0000000000000000000000000000000000000000000000000000000000000000 \
  --rpc-url $ARB_SEPOLIA_RPC
# Expected: 0  (default VALUATION for an entity that has never published)

cast call <ORACLE_ADDRESS> 'signalTypeByEntity(bytes32)(uint8)' \
  0x0000000000000000000000000000000000000000000000000000000000000000 \
  --rpc-url $ARB_SEPOLIA_RPC
# Expected: 0
```

### 4. Wire the relayer to the typed path

`api/blockchain.py` already exposes `publish_behavioral_signal_v3()`
which calls `publishBehavioralSignal`. To use the typed path, add a
`publish_signal_with_type()` helper that invokes
`publishSignalWithType(s, signalType)` and forwards the
`SignalTypeRecorded` log to the publication ledger. Off-chain, the
publication pipeline (`core/pipeline/signal_publication.py:publish`)
already builds a full `TRIONSignal` via `signal_factory.build_signal()`
which carries `signal_type` and `signal_type_id` — those map 1:1 to the
on-chain `signalType` byte.

## Upgrade path (already-deployed oracle)

If `TRIONOracleV3` is already deployed on Arbitrum Sepolia (current
default `ORACLE_ADDRESS=0x1d129D34279d1246aB08a41dfE610EaF8D794237`)
without these functions, an upgrade is required. The contract is NOT
upgradeable (no proxy pattern) — the upgrade procedure is:

1. **Deploy a fresh `TRIONOracleV3`** with the new bytecode at a new address.
2. **Migrate state**:
   - For each `entityId` with `behavioralSignals[entityId].initialized == true`, call `publishSignalWithType(s, signalType)` on the new contract with the existing struct values + the matching `SignalType` from off-chain Akashic records (every previously published signal has a known type in `core/akashic/bibl.py`).
   - Validators (`isValidator` mapping) and `quorumRequired` are re-registered via `addValidator()` and `setQuorum()`.
   - The epoch registry binding is set via `setEpochRegistry()`.
3. **Cut over the relayer**: update `ORACLE_ADDRESS` env var to the new contract address; restart the relayer.
4. **Verify**: hit `/api/v1/onchain/<entity_id>` for a previously-published entity — should return the migrated signal + the new `signal_type` field.
5. **Decommission** the old contract: drain any relay-held ETH, mark the address as deprecated in `proofs/oracle/`, and document the migration in `proof-ledger/first_signal.json`.

## Backwards compatibility

The existing `publishBehavioralSignal(s)` entrypoint is unchanged — its
ABI, topic0 hash, and behavior are preserved. Indexers that listen only
to `BehavioralSignalPublished` and `SilenceRecordedV2` continue to work
without modification. `publishSignalWithType` simply emits
`BehavioralSignalPublished` (or `SilenceRecordedV2`) AND a new
`SignalTypeRecorded` event — old indexers ignore the new event, new
indexers consume it.

The compiled ABI at
`contracts/solidity/compiled/TRIONOracleV3.json` is the source of truth
consumed by `api/blockchain.py:ORACLE_ABI`. Consumers that loaded the
ABI at process start must restart to pick up the new entries.

## Falsifiability hook

`SignalTypeRecorded` makes the typed-publication ledger auditable: any
external party can verify the type-distribution invariant (e.g. "an
entity with a `SILENCE` signal in epoch N must not have a `VALUATION`
certified in the same epoch") by walking the event log — a concrete
falsification condition for F2 (Coordination Collapse) at the contract
level.
