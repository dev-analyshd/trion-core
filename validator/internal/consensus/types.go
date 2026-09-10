// Package consensus implements the TRION-BFT consensus engine.
//
// This package closes due-diligence finding S4/C1 ("no consensus
// implementation"): before it existed, the Go validator was an attestation
// mesh only — no block production, no leader election, no view-change, no
// commit/finality, and slashing never executed anywhere.
//
// TRION-BFT is a Tendermint-family BFT consensus (whitepaper:
// "Consensus: TRION-BFT (Tendermint-family), instant finality, 2/3
// diversity-weighted") extended with DW-BFT diversity weighting
// (whitepaper L4.1-4.2, Σ(t) = Σ_j [s_j·d_j] / Σ_j [s_j·d_j]):
//
//   - Height/round/step state machine: NewHeight → Propose → Prevote →
//     Precommit → Commit, with locked proposals and a valid-round tracker.
//   - Leader election weighted by effective power s_j·d_j (stake × diversity
//     factor), deterministic from a (height, round, validator-set) seed.
//     The diversity factor reuses the existing p2p package's
//     ComputeDiversityWeight computation.
//   - View-change: rounds increment on step timeouts or +2/3 precommit-nil;
//     step timeouts double per round.
//   - Commit rule: STRICTLY more than 2/3 of voting power precommitting the
//     same block hash (3·power > 2·total, integer arithmetic — no floats in
//     quorum math). Committed blocks are applied to an in-memory chain and
//     published to consumers via a channel.
//   - Safety: equivocation (a validator prevoting or precommiting two
//     different values at the same height+round+step) is detected
//     automatically; evidence is recorded, broadcast so peers can verify and
//     independently apply it, and handed to a SlashingEnforcer.
//
// Signature scheme: consensus votes/proposals are signed with ed25519
// (crypto/ed25519, standard library). The mesh's behavioral attestations keep
// their existing dual-strand SHA3-256 construction (see internal/p2p); they
// are the block transactions.
//
// Author: TRION Protocol — Originator: Hudu Yusuf (Analys)
// License: CC0
package consensus

import (
        "crypto/ed25519"
        "encoding/binary"
        "encoding/hex"
        "fmt"
        "math"
)

// Hash is a 32-byte SHA3-256 hash (see internal/p2p/meshsha3 — SHA3, not
// SHA-2, for cross-system compatibility with the Rust/Python pipelines).
type Hash [32]byte

// ZeroHash is the zero value used to represent "nil" votes (no block).
var ZeroHash Hash

// IsZero reports whether h is the zero hash.
func (h Hash) IsZero() bool { return h == ZeroHash }

// Hex returns the full lowercase hex encoding of h.
func (h Hash) Hex() string { return hex.EncodeToString(h[:]) }

// String implements fmt.Stringer (full hex).
func (h Hash) String() string { return h.Hex() }

// Short returns a 16-char prefix for logs.
func (h Hash) Short() string {
        s := h.Hex()
        if len(s) >= 16 {
                return s[:16]
        }
        return s
}

// HashFromHex decodes a 64-char hex string into a Hash.
func HashFromHex(s string) (Hash, error) {
        var h Hash
        b, err := hex.DecodeString(s)
        if err != nil || len(b) != 32 {
                return h, fmt.Errorf("invalid hash hex %q", s)
        }
        copy(h[:], b)
        return h, nil
}

// MarshalText encodes Hash as lowercase hex when embedded in JSON (used by
// the mesh wire format). Without it, encoding/json would emit a 32-element
// number array for the [32]byte — valid Go-to-Go but bulky and hostile to
// non-Go peers.
func (h Hash) MarshalText() ([]byte, error) { return []byte(h.Hex()), nil }

// UnmarshalText parses a 64-char hex string into a Hash (inverse of
// MarshalText; also accepts the empty string as the zero hash, for JSON
// producers that omit the field entirely).
func (h *Hash) UnmarshalText(b []byte) error {
        if len(b) == 0 {
                *h = ZeroHash
                return nil
        }
        if len(b) != 64 {
                return fmt.Errorf("invalid hash hex length %d", len(b))
        }
        parsed, err := HashFromHex(string(b))
        if err != nil {
                return err
        }
        *h = parsed
        return nil
}

// Step is the consensus state-machine step within a round.
// NewHeight → Propose → Prevote → Precommit → Commit.
type Step uint8

const (
        // StepNewHeight is the transient state while moving to the next height.
        StepNewHeight Step = iota
        // StepPropose is waiting for (or producing) a proposal.
        StepPropose
        // StepPrevote is the prevote step.
        StepPrevote
        // StepPrecommit is the precommit step.
        StepPrecommit
        // StepCommit is the terminal step for a height (block decided).
        StepCommit
)

func (s Step) String() string {
        switch s {
        case StepNewHeight:
                return "NewHeight"
        case StepPropose:
                return "Propose"
        case StepPrevote:
                return "Prevote"
        case StepPrecommit:
                return "Precommit"
        case StepCommit:
                return "Commit"
        default:
                return fmt.Sprintf("Step(%d)", uint8(s))
        }
}

// VoteType distinguishes prevotes from precommits.
type VoteType uint8

const (
        // VoteTypePrevote is a PREVOTE (the "prepare" phase vote).
        VoteTypePrevote VoteType = 21
        // VoteTypePrecommit is a PRECOMMIT (the "commit" phase vote).
        VoteTypePrecommit VoteType = 22
)

func (v VoteType) String() string {
        switch v {
        case VoteTypePrevote:
                return "Prevote"
        case VoteTypePrecommit:
                return "Precommit"
        default:
                return fmt.Sprintf("VoteType(%d)", uint8(v))
        }
}

// MessageKind tags gossip messages on the consensus wire.
type MessageKind uint8

const (
        // MsgKindProposal carries a signed block proposal.
        MsgKindProposal MessageKind = 1
        // MsgKindVote carries a signed prevote or precommit.
        MsgKindVote MessageKind = 2
        // MsgKindEvidence carries equivocation evidence for slashing.
        MsgKindEvidence MessageKind = 3
        // MsgKindFinalizedBlock announces a committed block (observability /
        // future catch-up sync; receiving it does NOT commit it locally).
        MsgKindFinalizedBlock MessageKind = 4
)

func (m MessageKind) String() string {
        switch m {
        case MsgKindProposal:
                return "Proposal"
        case MsgKindVote:
                return "Vote"
        case MsgKindEvidence:
                return "Evidence"
        case MsgKindFinalizedBlock:
                return "FinalizedBlock"
        default:
                return fmt.Sprintf("MessageKind(%d)", uint8(m))
        }
}

// Vote is a signed consensus vote. BlockHash == ZeroHash means "vote nil".
type Vote struct {
        Type             VoteType `json:"type"`
        Height           uint64   `json:"height"`
        Round            uint32   `json:"round"`
        BlockHash        Hash     `json:"block_hash"`
        ValidatorAddress Hash     `json:"validator_address"`
        Signature        []byte   `json:"signature,omitempty"`
}

// SignBytes returns the canonical byte encoding covered by the signature.
// Deterministic: no timestamps, no maps, no floats.
func (v *Vote) SignBytes() []byte {
        b := make([]byte, 0, 1+8+4+32+32)
        b = appendUint8(b, byte(v.Type))
        b = appendUint64(b, v.Height)
        b = appendUint32(b, v.Round)
        b = appendHash(b, v.BlockHash)
        b = appendHash(b, v.ValidatorAddress)
        return b
}

// Verify checks the ed25519 signature against the validator's public key.
func (v *Vote) Verify(pk ed25519.PublicKey) bool {
        if len(v.Signature) != ed25519.SignatureSize || len(pk) != ed25519.PublicKeySize {
                return false
        }
        return ed25519.Verify(pk, v.SignBytes(), v.Signature)
}

// Proposal is a signed block proposal from the round's leader.
type Proposal struct {
        Height    uint64 `json:"height"`
        Round     uint32 `json:"round"`
        POLRound  int32  `json:"pol_round"` // round of the justification polka; -1 = fresh proposal
        BlockHash Hash   `json:"block_hash"`
        Block     *Block `json:"block"`
        // TimestampMs is the proposal timestamp. In deterministic mode (Config.Clock
        // == nil) it is derived from the parent block, which makes replay
        // deterministic; with a wall clock configured it is max(now, parent+1).
        TimestampMs int64  `json:"timestamp_ms"`
        Proposer    Hash   `json:"proposer"`
        Signature   []byte `json:"signature,omitempty"`
}

// SignBytes returns the canonical byte encoding covered by the signature.
func (p *Proposal) SignBytes() []byte {
        b := make([]byte, 0, 8+4+4+32+8+32)
        b = appendUint64(b, p.Height)
        b = appendUint32(b, p.Round)
        b = appendInt32(b, p.POLRound)
        b = appendHash(b, p.BlockHash)
        b = appendInt64(b, p.TimestampMs)
        b = appendHash(b, p.Proposer)
        return b
}

// Verify checks the ed25519 signature against the proposer's public key.
func (p *Proposal) Verify(pk ed25519.PublicKey) bool {
        if len(p.Signature) != ed25519.SignatureSize || len(pk) != ed25519.PublicKeySize {
                return false
        }
        return ed25519.Verify(pk, p.SignBytes(), p.Signature)
}

// ConsensusMessage is the gossip unit exchanged between consensus engines.
// Exactly one payload pointer matches the Kind.
type ConsensusMessage struct {
        Kind     MessageKind           `json:"kind"`
        Proposal *Proposal             `json:"proposal,omitempty"`
        Vote     *Vote                 `json:"vote,omitempty"`
        Evidence *EquivocationEvidence `json:"evidence,omitempty"`
        Block    *FinalizedBlock       `json:"finalized_block,omitempty"`
}

// FinalizedBlock is the commit notification handed to consumers and gossiped
// for observability. It carries the committed block, the round the commit
// quorum formed in, and the justifying precommits.
type FinalizedBlock struct {
        Block       *Block `json:"block"`
        CommitRound uint32 `json:"commit_round"`
        Precommits  []Vote `json:"precommits"`
}

// ── Canonical encoding helpers ─────────────────────────────────────────────
// All hashes and signatures cover canonical binary encodings. Fixed-width
// big-endian integers, length-prefixed bytes, raw 32-byte hashes. No JSON, no
// floats, no maps — anything that could break determinism.

func appendUint8(b []byte, v uint8) []byte { return append(b, v) }

func appendUint32(b []byte, v uint32) []byte {
        var tmp [4]byte
        binary.BigEndian.PutUint32(tmp[:], v)
        return append(b, tmp[:]...)
}

func appendUint64(b []byte, v uint64) []byte {
        var tmp [8]byte
        binary.BigEndian.PutUint64(tmp[:], v)
        return append(b, tmp[:]...)
}

func appendInt32(b []byte, v int32) []byte {
        var tmp [4]byte
        binary.BigEndian.PutUint32(tmp[:], uint32(v)) // two's complement, deterministic
        return append(b, tmp[:]...)
}

func appendInt64(b []byte, v int64) []byte {
        var tmp [8]byte
        binary.BigEndian.PutUint64(tmp[:], uint64(v)) // two's complement, deterministic
        return append(b, tmp[:]...)
}

func appendHash(b []byte, h Hash) []byte { return append(b, h[:]...) }

func appendBytes(b []byte, xs []byte) []byte {
        b = appendUint32(b, uint32(len(xs)))
        return append(b, xs...)
}

func appendString(b []byte, s string) []byte { return appendBytes(b, []byte(s)) }

// appendFloat64 encodes a float64 as its IEEE-754 bit pattern (big endian) —
// a fully deterministic encoding, unlike decimal text.
func appendFloat64(b []byte, f float64) []byte {
        var tmp [8]byte
        binary.BigEndian.PutUint64(tmp[:], math.Float64bits(f))
        return append(b, tmp[:]...)
}
