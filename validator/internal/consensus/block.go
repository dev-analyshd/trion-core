// TRION Protocol — DW-BFT block production: candidate blocks, deterministic
// transaction ordering, Merkle app-hash, the pending attestation mempool and
// the in-memory blockchain.
//
// Blocks are batches of behavioral attestations (the existing p2p
// attestation struct — reused verbatim). A block is:
//
//      {height, round, parent, timestamp, proposer, txs, evidence, lastCommit}
//
//   - Block.Round is the round at which the block was FIRST proposed. A
//     locked/valid block re-proposed in a later round keeps its original
//     bytes (and therefore its hash) so that lock semantics hold; validation
//     only requires proposal.round >= block.round.
//   - AppHash is a Merkle root over the canonical hashes of the txs and
//     evidence entries.
//   - Block.Hash() is SHA3-256 over the canonical encoding of all header
//     fields plus AppHash (which commits to the block body).
//
// Author: TRION Protocol — Originator: Hudu Yusuf (Analys)
// License: CC0
package consensus

import (
        "fmt"
        "sort"
        "sync"

        "github.com/trion-protocol/validator/internal/p2p"
        "github.com/trion-protocol/validator/internal/p2p/meshsha3"
)

// CommitInfo is the commit justification for the previous block, included in
// each block (Tendermint "LastCommit"). It allows chain validation without
// a separate catch-up protocol.
type CommitInfo struct {
        Height     uint64 `json:"height"`
        Round      uint32 `json:"round"`
        BlockHash  Hash   `json:"block_hash"`
        Precommits []Vote `json:"precommits"`
}

// Block is a TRION-BFT block. Fields are exported for JSON wire encoding;
// the unexported hash cache is never serialized.
type Block struct {
        Height      uint64                    `json:"height"`
        Round       uint32                    `json:"round"` // round of first proposal
        Parent      Hash                      `json:"parent"`
        TimestampMs int64                     `json:"timestamp_ms"`
        Proposer    Hash                      `json:"proposer"`
        Txs         []p2p.BehavioralAttestation `json:"txs,omitempty"`
        Evidence    []EquivocationEvidence    `json:"evidence,omitempty"`
        LastCommit  *CommitInfo               `json:"last_commit,omitempty"`
        AppHash     Hash                      `json:"app_hash"`

        hashOnce sync.Once
        hashVal  Hash
}

// ComputeAppHash computes the application hash:
//
//      SHA3-256("TRION-APP" || merkleRoot(txHashes) || merkleRoot(evidenceHashes))
//
// merkleRoot of an empty list is the zero hash.
func (b *Block) ComputeAppHash() Hash {
        txLeaves := make([]Hash, len(b.Txs))
        for i := range b.Txs {
                txLeaves[i] = AttestationHash(&b.Txs[i])
        }
        evLeaves := make([]Hash, len(b.Evidence))
        for i := range b.Evidence {
                evLeaves[i] = b.Evidence[i].Hash()
        }
        buf := make([]byte, 0, 9+32+32)
        buf = append(buf, "TRION-APP"...)
        buf = appendHash(buf, merkleRoot(txLeaves))
        buf = appendHash(buf, merkleRoot(evLeaves))
        return meshsha3.Sum256(buf)
}

// Hash returns SHA3-256 over the canonical header encoding (which includes
// AppHash, committing to the block body). LastCommit is deliberately NOT
// hash-covered — matching Tendermint, where commit signatures live outside
// the block hash: the set of justifying precommits a node has collected at
// commit time may differ between correct nodes (message arrival order), so
// binding it into the hash would make identical blocks hash differently.
// LastCommit is still fully signature-validated on every proposal.
//
// The result is memoized: blocks are immutable once constructed.
func (b *Block) Hash() Hash {
        b.hashOnce.Do(func() {
                buf := make([]byte, 0, 9+8+4+32+8+32+32)
                buf = append(buf, "TRION-BLK"...)
                buf = appendUint64(buf, b.Height)
                buf = appendUint32(buf, b.Round)
                buf = appendHash(buf, b.Parent)
                buf = appendInt64(buf, b.TimestampMs)
                buf = appendHash(buf, b.Proposer)
                buf = appendHash(buf, b.AppHash)
                b.hashVal = meshsha3.Sum256(buf)
        })
        return b.hashVal
}

// AssembleBlock builds a candidate block from a set of attestations and
// equivocation evidence, with DETERMINISTIC transaction ordering: entries are
// sorted by canonical hash. This is the block-production entry point used by
// the engine's proposer and by external builders.
func AssembleBlock(
        height uint64,
        round uint32,
        parent Hash,
        timestampMs int64,
        proposer Hash,
        txs []p2p.BehavioralAttestation,
        evidence []EquivocationEvidence,
        lastCommit *CommitInfo,
) *Block {
        sortedTxs := make([]p2p.BehavioralAttestation, len(txs))
        copy(sortedTxs, txs)
        sort.SliceStable(sortedTxs, func(i, j int) bool {
                return AttestationHash(&sortedTxs[i]).Hex() < AttestationHash(&sortedTxs[j]).Hex()
        })
        sortedEvs := make([]EquivocationEvidence, len(evidence))
        copy(sortedEvs, evidence)
        sort.SliceStable(sortedEvs, func(i, j int) bool {
                return sortedEvs[i].Hash().Hex() < sortedEvs[j].Hash().Hex()
        })
        b := &Block{
                Height:      height,
                Round:       round,
                Parent:      parent,
                TimestampMs: timestampMs,
                Proposer:    proposer,
                Txs:         sortedTxs,
                Evidence:    sortedEvs,
                LastCommit:  lastCommit,
        }
        b.AppHash = b.ComputeAppHash()
        return b
}

// merkleRoot computes a simple binary Merkle root over 32-byte leaves:
// pair up nodes (odd level: the last node is paired with itself) and hash
// SHA3-256(l || r). An empty leaf list yields the zero hash.
func merkleRoot(leaves []Hash) Hash {
        if len(leaves) == 0 {
                return ZeroHash
        }
        level := make([]Hash, len(leaves))
        copy(level, leaves)
        for len(level) > 1 {
                next := make([]Hash, 0, (len(level)+1)/2)
                for i := 0; i < len(level); i += 2 {
                        l := level[i]
                        r := l
                        if i+1 < len(level) {
                                r = level[i+1]
                        }
                        buf := make([]byte, 0, 64)
                        buf = appendHash(buf, l)
                        buf = appendHash(buf, r)
                        next = append(next, meshsha3.Sum256(buf))
                }
                level = next
        }
        return level[0]
}

// ── Canonical attestation encoding (block transactions) ────────────────────

// CanonicalAttestation returns the deterministic binary encoding of a
// behavioral attestation. Floats are encoded as IEEE-754 bit patterns so the
// encoding is byte-stable across platforms and runs.
func CanonicalAttestation(a *p2p.BehavioralAttestation) []byte {
        b := make([]byte, 0, 128)
        b = append(b, "TRION-ATT"...)
        b = appendString(b, a.EntityID)
        b = appendString(b, a.SignalType)
        b = appendFloat64(b, a.CoherenceC)
        b = appendFloat64(b, a.ThresholdTheta)
        b = appendString(b, a.ValidatorID)
        b = appendFloat64(b, a.DiversityWeight)
        b = appendInt64(b, a.Timestamp)
        b = appendUint64(b, a.BlockNumber)
        b = appendString(b, a.SignatureSense)
        b = appendString(b, a.SignatureAntisense)
        return b
}

// AttestationHash is the SHA3-256 of the canonical attestation encoding.
func AttestationHash(a *p2p.BehavioralAttestation) Hash {
        return meshsha3.Sum256(CanonicalAttestation(a))
}

// ── Mempool ─────────────────────────────────────────────────────────────────

// Mempool holds pending attestations awaiting inclusion in a block. Entries
// are deduplicated by canonical hash and returned in deterministic
// (hash-ascending) order. Transactions are removed when the block containing
// them is COMMITTED, not when a block proposing them is built — a failed
// round's transactions are re-proposed by the next proposer.
type Mempool struct {
        mu   sync.Mutex
        txs  map[Hash]p2p.BehavioralAttestation
        keys []Hash // sorted ascending
}

// NewMempool creates an empty mempool.
func NewMempool() *Mempool {
        return &Mempool{txs: make(map[Hash]p2p.BehavioralAttestation)}
}

// Add inserts an attestation, deduplicating by canonical hash. It returns the
// attestation hash and whether it was newly added.
func (m *Mempool) Add(att p2p.BehavioralAttestation) (Hash, bool) {
        h := AttestationHash(&att)
        m.mu.Lock()
        defer m.mu.Unlock()
        if _, ok := m.txs[h]; ok {
                return h, false
        }
        m.txs[h] = att
        i := sort.Search(len(m.keys), func(i int) bool { return m.keys[i].Hex() > h.Hex() })
        m.keys = append(m.keys, Hash{})
        copy(m.keys[i+1:], m.keys[i:])
        m.keys[i] = h
        return h, true
}

// Snapshot returns up to max attestations in deterministic hash-ascending
// order (the block-inclusion order). The mempool is not modified.
func (m *Mempool) Snapshot(max int) []p2p.BehavioralAttestation {
        m.mu.Lock()
        defer m.mu.Unlock()
        if max < 0 || max > len(m.keys) {
                max = len(m.keys)
        }
        out := make([]p2p.BehavioralAttestation, 0, max)
        for i := 0; i < max; i++ {
                out = append(out, m.txs[m.keys[i]])
        }
        return out
}

// RemoveTxs removes attestations (by canonical hash) — called when the block
// containing them commits.
func (m *Mempool) RemoveTxs(atts []p2p.BehavioralAttestation) {
        m.mu.Lock()
        defer m.mu.Unlock()
        for i := range atts {
                h := AttestationHash(&atts[i])
                if _, ok := m.txs[h]; !ok {
                        continue
                }
                delete(m.txs, h)
                j := sort.Search(len(m.keys), func(j int) bool { return m.keys[j].Hex() >= h.Hex() })
                if j < len(m.keys) && m.keys[j] == h {
                        m.keys = append(m.keys[:j], m.keys[j+1:]...)
                }
        }
}

// Size returns the number of pending attestations.
func (m *Mempool) Size() int {
        m.mu.Lock()
        defer m.mu.Unlock()
        return len(m.keys)
}

// ── Blockchain (in-memory) ──────────────────────────────────────────────────

// Blockchain is the in-memory finalized chain. Block at index i has
// Height i; index 0 is the genesis block whose hash depends on the chain ID.
//
// TODO(persistence): blocks live in memory only. A real deployment needs
// block/state persistence (e.g. a WAL + snapshot store, or 0G DA blobs).
type Blockchain struct {
        mu     sync.RWMutex
        blocks []*Block
        byHash map[Hash]*Block
}

// NewBlockchain creates a chain with a deterministic genesis block for the
// given chain ID. The genesis has height 0, no transactions and a
// chain-ID-bound AppHash.
func NewBlockchain(chainID string) *Blockchain {
        genesis := &Block{
                Height:      0,
                Round:       0,
                Parent:      ZeroHash,
                TimestampMs: 0,
                Proposer:    ZeroHash,
        }
        buf := make([]byte, 0, 14+len(chainID))
        buf = append(buf, "TRION-GENESIS"...)
        buf = appendString(buf, chainID)
        genesis.AppHash = meshsha3.Sum256(buf)
        bc := &Blockchain{
                blocks: []*Block{genesis},
                byHash: map[Hash]*Block{genesis.Hash(): genesis},
        }
        return bc
}

// Append validates and appends a committed block:
//   - height must be chain length (i.e. current tip height + 1),
//   - parent must be the current tip hash,
//   - AppHash must match a recomputation over the body,
//   - the block hash must be the canonical recomputation.
//
// Append is called by the engine's commit path; the block contents were
// already validated when the proposal was processed.
func (bc *Blockchain) Append(b *Block) error {
        bc.mu.Lock()
        defer bc.mu.Unlock()
        expectHeight := uint64(len(bc.blocks))
        if b.Height != expectHeight {
                return fmt.Errorf("block height %d, want %d", b.Height, expectHeight)
        }
        tip := bc.blocks[len(bc.blocks)-1]
        if b.Parent != tip.Hash() {
                return fmt.Errorf("block parent %s, want tip %s", b.Parent.Short(), tip.Hash().Short())
        }
        if b.AppHash != b.ComputeAppHash() {
                return fmt.Errorf("block app-hash mismatch at height %d", b.Height)
        }
        bc.blocks = append(bc.blocks, b)
        bc.byHash[b.Hash()] = b
        return nil
}

// Tip returns the hash of the highest committed block.
func (bc *Blockchain) Tip() Hash {
        bc.mu.RLock()
        defer bc.mu.RUnlock()
        return bc.blocks[len(bc.blocks)-1].Hash()
}

// Height returns the height of the highest committed block (0 = genesis only).
func (bc *Blockchain) Height() uint64 {
        bc.mu.RLock()
        defer bc.mu.RUnlock()
        return uint64(len(bc.blocks) - 1)
}

// TipTimestampMs returns the timestamp of the tip block.
func (bc *Blockchain) TipTimestampMs() int64 {
        bc.mu.RLock()
        defer bc.mu.RUnlock()
        return bc.blocks[len(bc.blocks)-1].TimestampMs
}

// BlockAt returns the block at the given height, or nil.
func (bc *Blockchain) BlockAt(h uint64) *Block {
        bc.mu.RLock()
        defer bc.mu.RUnlock()
        if h >= uint64(len(bc.blocks)) {
                return nil
        }
        return bc.blocks[h]
}

// Blocks returns a copy of the block slice (genesis first).
func (bc *Blockchain) Blocks() []*Block {
        bc.mu.RLock()
        defer bc.mu.RUnlock()
        out := make([]*Block, len(bc.blocks))
        copy(out, bc.blocks)
        return out
}
