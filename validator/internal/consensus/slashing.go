// TRION Protocol — DW-BFT equivocation detection and slashing enforcement.
//
// Whitepaper L4.9 defines the slashing schedule and dispute resolution flow.
// This file implements the equivocation ("double-sign") condition:
//
//      A validator prevoting OR precommiting two different values in the same
//      (height, round, step) is auto-equivocating. The conflicting vote pair is
//      cryptographically self-evident (both votes are signed), so any node that
//      observes both votes can construct EquivocationEvidence and every other
//      node can verify it independently from the two embedded signatures.
//
// On evidence:
//   1. the local SlashingEnforcer slashes the validator's staked stake
//      (in-memory accounting for now),
//   2. the validator is tombstoned for N blocks,
//   3. the validator's voting power is removed from the consensus validator
//      set — protocol-level removal happens deterministically at the next
//      height after a block COMMITTING the evidence, so all nodes converge on
//      the same validator set (the engine also enforces locally on detection,
//      before commit, for accounting only).
//
// Evidence is broadcast as a signed gossiped message (MsgKindEvidence) so
// peers that never saw the raw conflicting votes can still verify and
// independently apply the slash.
//
// TODO(on-chain burn): today slashing is in-memory accounting only. The
// on-chain execution point is
//      contracts/vyper/TRIONStaking.vy::slash_validator(validator, slash_type,
//      evidence_hash) — the evidence hash here is EquivocationEvidence.Hash().
// TRIONStaking.vy currently implements the AUDIT-4 seven-type schedule
// (FALSE_COVERAGE_CLAIM_*, COORDINATION_COLLAPSE, COVERAGE_FRAUD,
// SOCKPUPPET_CONFIRMED, BTCP_SPOOF_FLAG) and routes slashed TRION 50/50 to
// insurance_pool + burn via TRIONToken.slash_validator, gated on
// akashic_oracle/governance authorization plus a 72-hour dispute window.
// Wiring this engine's evidence to that entry point requires (a) adding a
// DOUBLE_SIGN_EQUIVOCATION slash type (or mapping it to COORDINATION_COLLAPSE)
// and (b) an oracle relayer submitting verified evidence — both outstanding.
//
// Author: TRION Protocol — Originator: Hudu Yusuf (Analys)
// License: CC0
package consensus

import (
        "crypto/ed25519"
        "fmt"
        "sync"

        "github.com/trion-protocol/validator/internal/p2p/meshsha3"
)

// EquivocationEvidence proves that ValidatorAddress signed two conflicting
// votes at the same (height, round, vote type). The votes themselves are
// embedded: verification only needs the validator's public key.
type EquivocationEvidence struct {
        Height           uint64 `json:"height"`
        Round            uint32 `json:"round"`
        Type             VoteType `json:"type"`
        ValidatorAddress Hash   `json:"validator_address"`
        VoteA            *Vote  `json:"vote_a"`
        VoteB            *Vote  `json:"vote_b"`
}

// MakeEquivocationEvidence pairs two conflicting votes into evidence. It
// returns an error if the pair is not actually an equivocation.
func MakeEquivocationEvidence(a, b *Vote) (*EquivocationEvidence, error) {
        if a == nil || b == nil {
                return nil, fmt.Errorf("nil vote in evidence")
        }
        if a.ValidatorAddress != b.ValidatorAddress {
                return nil, fmt.Errorf("votes from different validators")
        }
        if a.Type != b.Type {
                return nil, fmt.Errorf("votes of different types")
        }
        if a.Height != b.Height || a.Round != b.Round {
                return nil, fmt.Errorf("votes from different height/round")
        }
        if a.BlockHash == b.BlockHash {
                return nil, fmt.Errorf("votes for the same value — not an equivocation")
        }
        return &EquivocationEvidence{
                Height:           a.Height,
                Round:            a.Round,
                Type:             a.Type,
                ValidatorAddress: a.ValidatorAddress,
                VoteA:            a,
                VoteB:            b,
        }, nil
}

// Hash is the evidence identity (referenced as evidence_hash when bridging to
// contracts/vyper/TRIONStaking.vy::slash_validator). Deterministic over the
// canonical encoding of the conflicting vote pair.
func (ev *EquivocationEvidence) Hash() Hash {
        // Encode the pair in sign-bytes order (lexicographically smaller first)
        // so every node derives the SAME hash regardless of which conflicting
        // vote it observed first — required for cross-node deduplication and
        // idempotent slashing.
        a, b := []byte(nil), []byte(nil)
        if ev.VoteA != nil {
                a = ev.VoteA.SignBytes()
        }
        if ev.VoteB != nil {
                b = ev.VoteB.SignBytes()
        }
        if b != nil && (a == nil || string(b) < string(a)) {
                a, b = b, a
        }
        buf := make([]byte, 0, 12+32+128)
        buf = append(buf, "TRION-EV"...)
        buf = appendUint64(buf, ev.Height)
        buf = appendUint32(buf, ev.Round)
        buf = appendUint8(buf, byte(ev.Type))
        buf = appendHash(buf, ev.ValidatorAddress)
        buf = append(buf, a...)
        buf = append(buf, b...)
        return meshsha3.Sum256(buf)
}

// Conflict performs the structural equivocation check (no cryptography).
func (ev *EquivocationEvidence) Conflict() bool {
        if ev == nil || ev.VoteA == nil || ev.VoteB == nil {
                return false
        }
        return ev.VoteA.ValidatorAddress == ev.VoteB.ValidatorAddress &&
                ev.VoteA.Type == ev.VoteB.Type &&
                ev.VoteA.Height == ev.VoteB.Height &&
                ev.VoteA.Round == ev.VoteB.Round &&
                ev.VoteA.BlockHash != ev.VoteB.BlockHash
}

// VerifySignatures checks both embedded vote signatures against the
// validator's public key. This is what allows nodes that never observed the
// raw votes to independently apply the evidence.
func (ev *EquivocationEvidence) VerifySignatures(pk ed25519.PublicKey) error {
        if !ev.Conflict() {
                return fmt.Errorf("evidence is not a structural equivocation")
        }
        if !ev.VoteA.Verify(pk) {
                return fmt.Errorf("vote A signature invalid")
        }
        if !ev.VoteB.Verify(pk) {
                return fmt.Errorf("vote B signature invalid")
        }
        return nil
}

// ── Slashing enforcer ───────────────────────────────────────────────────────

// SlashingEnforcer applies slashing penalties for verified equivocation
// evidence. Implementations must be idempotent per evidence hash.
//
// The engine calls Enforce:
//   - on local equivocation detection (both votes were signature-verified
//     during vote processing),
//   - on remote evidence messages after VerifySignatures,
//   - on evidence committed in a block (idempotent replay).
type SlashingEnforcer interface {
        // Enforce slashes and tombstones the validator named in the evidence.
        Enforce(ev *EquivocationEvidence) error
        // IsTombstonedAt reports whether the validator is tombstoned at height.
        IsTombstonedAt(addr Hash, height uint64) bool
}

// SlashPolicy configures the penalty schedule.
type SlashPolicy struct {
        // SlashFractionMicro is the slashed fraction of stake in micro units
        // (1_000_000 = 100%). Default 50_000 = 5%.
        SlashFractionMicro int64
        // TombstoneBlocks is how many blocks the validator is tombstoned for
        // (voting power removed). Default 10_000.
        TombstoneBlocks uint64
}

// DefaultSlashPolicy returns the default equivocation policy: 5% slash
// (aligned with the mildest TRIONStaking.vy tier, BTCP_SPOOF_FLAG at 5%) and
// a 10_000-block tombstone.
func DefaultSlashPolicy() SlashPolicy {
        return SlashPolicy{SlashFractionMicro: 50_000, TombstoneBlocks: 10_000}
}

// SlashEvent is a record of one applied slash (for accounting and tests).
type SlashEvent struct {
        EvidenceHash   Hash   `json:"evidence_hash"`
        Validator      Hash   `json:"validator"`
        Height         uint64 `json:"height"`
        SlashedMicro   uint64 `json:"slashed_micro"`
        TombstonedTo   uint64 `json:"tombstoned_until_height"`
        OnChainBurn    bool   `json:"on_chain_burn"` // always false until the TRIONStaking.vy bridge exists
}

// StakeLedger is the in-memory SlashingEnforcer: stake accounting, slashing
// and tombstoning. It is deliberately simple and explicit about being
// off-chain. Cryptographic verification of the evidence happens in the engine
// before Enforce is called; the ledger re-checks structure and idempotency.
//
// TODO(on-chain): replace/augment with a relayer calling
// contracts/vyper/TRIONStaking.vy::slash_validator (see file header).
type StakeLedger struct {
        mu       sync.Mutex
        policy   SlashPolicy
        stakes   map[Hash]uint64
        initial  map[Hash]uint64
        tombTo   map[Hash]uint64 // tombstoned until height (exclusive)
        applied  map[Hash]bool   // evidence hashes already applied
        events   []SlashEvent
}

// NewStakeLedger creates a ledger with the given initial stakes (micro-TRION).
func NewStakeLedger(policy SlashPolicy, stakes map[Hash]uint64) *StakeLedger {
        l := &StakeLedger{
                policy:  policy,
                stakes:  make(map[Hash]uint64, len(stakes)),
                initial: make(map[Hash]uint64, len(stakes)),
                tombTo:  make(map[Hash]uint64),
                applied: make(map[Hash]bool),
        }
        for a, s := range stakes {
                l.stakes[a] = s
                l.initial[a] = s
        }
        return l
}

// Enforce slashes and tombstones the evidence's validator. Idempotent per
// evidence hash; safe to call concurrently.
func (l *StakeLedger) Enforce(ev *EquivocationEvidence) error {
        if ev == nil || !ev.Conflict() {
                return fmt.Errorf("invalid equivocation evidence")
        }
        l.mu.Lock()
        defer l.mu.Unlock()
        h := ev.Hash()
        if l.applied[h] {
                return nil // idempotent
        }
        l.applied[h] = true

        addr := ev.ValidatorAddress
        stake := l.stakes[addr]
        slashed := uint64(float64(stake) * float64(l.policy.SlashFractionMicro) / 1_000_000)
        if slashed > stake {
                slashed = stake
        }
        l.stakes[addr] = stake - slashed

        tombTo := ev.Height + l.policy.TombstoneBlocks
        if tombTo > l.tombTo[addr] {
                l.tombTo[addr] = tombTo
        }
        l.events = append(l.events, SlashEvent{
                EvidenceHash: h,
                Validator:    addr,
                Height:       ev.Height,
                SlashedMicro: slashed,
                TombstonedTo: l.tombTo[addr],
        })
        return nil
}

// IsTombstonedAt reports whether the validator's tombstone covers height.
func (l *StakeLedger) IsTombstonedAt(addr Hash, height uint64) bool {
        l.mu.Lock()
        defer l.mu.Unlock()
        return l.tombTo[addr] > height
}

// IsTombstoned reports whether the validator is tombstoned at any height ≥
// the latest recorded evidence height. Convenience for tests/observability.
func (l *StakeLedger) IsTombstoned(addr Hash) bool {
        l.mu.Lock()
        defer l.mu.Unlock()
        _, ok := l.tombTo[addr]
        return ok
}

// Stake returns the current (post-slash) stake of a validator.
func (l *StakeLedger) Stake(addr Hash) uint64 {
        l.mu.Lock()
        defer l.mu.Unlock()
        return l.stakes[addr]
}

// InitialStake returns the pre-slash stake of a validator.
func (l *StakeLedger) InitialStake(addr Hash) uint64 {
        l.mu.Lock()
        defer l.mu.Unlock()
        return l.initial[addr]
}

// SlashedTotal returns the total micro-TRION slashed from a validator.
func (l *StakeLedger) SlashedTotal(addr Hash) uint64 {
        l.mu.Lock()
        defer l.mu.Unlock()
        return l.initial[addr] - l.stakes[addr]
}

// Events returns a copy of the applied slash events.
func (l *StakeLedger) Events() []SlashEvent {
        l.mu.Lock()
        defer l.mu.Unlock()
        out := make([]SlashEvent, len(l.events))
        copy(out, l.events)
        return out
}

// TombstonedUntil returns the height until which the validator is
// tombstoned (0 if never).
func (l *StakeLedger) TombstonedUntil(addr Hash) uint64 {
        l.mu.Lock()
        defer l.mu.Unlock()
        return l.tombTo[addr]
}
