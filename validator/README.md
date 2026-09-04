# TRION Validator (Go) — Attestation Mesh + TRION-BFT Consensus

Go implementation of the TRION validator network: the P2P behavioral-attestation
mesh (`internal/p2p`) and the TRION-BFT consensus engine (`internal/consensus`).
This module closes due-diligence finding **S4/C1** ("no consensus
implementation — no blocks, no views, no slashing"): blocks, rounds/view
changes, commits and equivocation slashing now exist, are wired into the mesh,
and are covered by tests.

```
go build ./... && go vet ./...
go test ./...                              # full suite
go test ./internal/consensus/... -v        # BFT rule tests
go test ./internal/consensus/... -race
go run ./cmd/trion-validator               # mesh + 4-validator TCP consensus self-test
```

## Architecture

```
 behavioral attestations                     consensus messages (new wire IDs)
      (legacy frames, unchanged)             1=propose 2=prevote 3=precommit
              │                              4=block 5=evidence
              ▼                                        ▼
        ┌─────────────────── MeshNode (TCP gossip, line-delimited JSON) ──┐
        │  attestations ──► attestation hook ──► Engine.SubmitAttestation │
        │  consensus frames ──► consensus handler ──► Engine.HandleMessage│
        └───────────────────────────────┬──────────────────────────────────┘
                                        │ Engine.Outbound = mesh gossip
                                        ▼
        ┌─ Engine (internal/consensus) ──────────────────────────────────┐
        │ NewHeight → Propose → Prevote → Precommit → Commit             │
        │ mempool ─► block assembly ─► in-memory chain ─► FinalizedBlocks│
        │ equivocation detection ─► evidence ─► SlashingEnforcer         │
        └────────────────────────────────────────────────────────────────┘
```

- **`internal/consensus`** — Tendermint-family BFT ("The Latest Gossip on BFT
  Consensus") with TRION's diversity-weighted effective power `s_j·d_j`
  (whitepaper L4.1–4.2; the diversity factor reuses `p2p.ComputeDiversityWeight`,
  `d_j = 1 − corr(M_j, M̄)`).
  - `engine.go` — the state machine: propose/prevote/precommit steps,
    lock-on-precommit, valid-round tracking, view-change with per-round
    timeout doubling, commit on strictly > 2/3 precommit power (integer
    arithmetic, `3·power > 2·total`), deterministic power-weighted proposer
    selection, equivocation detection at the same height+round+step.
  - `block.go` — blocks (batches of attestations + evidence), deterministic
    tx ordering, Merkle app-hash, mempool, in-memory chain.
  - `slashing.go` — equivocation evidence (two signed conflicting votes —
    self-verifying), `SlashingEnforcer` interface, in-memory `StakeLedger`
    (slash + tombstone), slash policy.
  - `types.go` — votes/proposals/messages, canonical binary encodings (no
    floats-in-text, no maps), ed25519 signatures, SHA3-256 hashing (via
    `internal/p2p/meshsha3`, cross-language compatible with the Rust/Python
    pipelines).
- **`cmd/trion-validator`** — mesh + consensus wiring:
  - `validator_mesh.go` — the attestation mesh (unchanged legacy behavior)
    plus hooks: attestations feed the engine mempool, consensus frames are
    dispatched to the engine.
  - `bft_mesh.go` — wire envelope with NEW message type IDs (backward
    compatible: legacy frames carry no type field and still decode as
    attestations; old peers never misparse new frames), `BFTNode` adapter
    (engine + ledger + chain + finalized-block channel), and a 4-validator
    TCP self-test demo.

## What is implemented (and tested)

| Property | Status |
|---|---|
| Blocks (attestations as transactions, evidence, deterministic ordering) | ✅ `block.go`, tests |
| Views/rounds with timeout doubling on view change | ✅ `engine.go`, view-change test |
| Commit rule: strictly > 2/3 voting power | ✅ exactly-2/3 does **not** commit (test) |
| Proposer selection ∝ diversity-weighted power | ✅ 10 000-sample statistical test |
| Deterministic block hashing / deterministic replay | ✅ same messages → identical hashes (test) |
| Equivocation detection + slashing + tombstoning | ✅ 1-of-4 byzantine test; power removal at next height |
| Chain keeps committing with f=1 (n=4) faults | ✅ test commits before and after power removal |
| Lock-on-precommit, valid-round (POLRound) justification | ✅ engine rules; prevote rule per Tendermint |
| Backward-compatible mesh gossip of consensus frames | ✅ wire round-trip tests (legacy ↔ new) |
| Finalized blocks exposed to consumers | ✅ `Engine.FinalizedBlocks()` channel + `BFTNode` relay |
| Engine concurrency safety | ✅ `go test -race` clean |

## Honest gaps — what is still needed for a live network

1. **Block/state persistence.** The chain, mempool and stake ledger are
   in-memory only. A live validator needs a WAL/snapshot store (or 0G DA
   blobs) plus state-machine replication on restart. `block.go` carries a
   `TODO(persistence)`.
2. **Peer discovery beyond static seeds.** Peering is all-to-all from
   statically registered profiles (`AddPeer`); there is no peer exchange,
   DHT, or gossip-subscribe topic discovery. The engine also drops messages
   for heights more than one ahead (one-height lookahead only).
3. **Catch-up / state sync reactor.** A node that falls behind more than one
   height cannot resync from `MsgKindFinalizedBlock` announces — a block-sync
   protocol (request/response rounds + LastCommit-justified headers) is
   required. Message replay beyond the lookahead window is dropped and
   counted in metrics.
4. **On-chain slashing bridge.** Slashing is off-chain in-memory accounting.
   The intended execution point is
   `contracts/vyper/TRIONStaking.vy::slash_validator(validator, slash_type,
   evidence_hash)` (evidence hash = `EquivocationEvidence.Hash()`), which
   needs a `DOUBLE_SIGN_EQUIVOCATION` slash type and an oracle relayer —
   both outstanding (see `slashing.go` header).
5. **Validator-set changes beyond tombstone removal.** Only equivocation
   power-removal is implemented; no staking/unstaking transitions, no
   validator-set gossip for join/leave.
6. **Transport hardening.** Line-delimited JSON over TCP with per-message
   connections; no auth/encryption (no TLS/libp2p noise), no peer scoring,
   no message rate limiting, no frame size limits. ed25519 is the only
   signature scheme; no HSM integration yet.
7. **No execution/state machine.** Blocks commit; nothing "executes" them
   beyond evidence application and mempool drain (there is no on-chain
   state transition function yet).
8. **Quorum layering.** The legacy attestation-layer quorum
   (`p2p`/mesh, ≥ 2/3, floats) coexists with the strict engine quorum
   (> 2/3, integers). They serve different layers but the legacy layer
   should eventually be retired or reconciled.
9. **Deterministic timestamps are test-only.** Live nodes use
   `Config.Clock` (wall clock); deterministic replay relies on the
   nil-Clock mode used by tests and by any future deterministic replay tool.
10. **Fuzz/property suites and testnets.** The current suite is scenario +
    unit based (deterministic seeds); long-running randomized fault-injection
    (e.g. Tendermint-style simulation networks) has not been run.

Author: TRION Protocol — Originator: Hudu Yusuf (Analys) — License: CC0
