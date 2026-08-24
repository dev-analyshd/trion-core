// TRION Protocol — Go P2P Validator Mesh
// Whitepaper Section 21 Tech Stack / Channel 17:
// "P2P validator mesh communication (Go goroutine direct networking, not chain-mediated)"
//
// Validators communicate behavioral attestations directly (bypassing smart contracts)
// using goroutines and a lightweight TCP gossip protocol. DW-BFT quorum is checked
// after every received attestation.
//
// Author: TRION Protocol — Originator: Hudu Yusuf (Analys)
// License: CC0

package p2p

import (
        "context"
        "encoding/hex"
        "encoding/json"
        "fmt"
        "log"
        "math"
        "net"
        "sync"
        "time"

        "github.com/trion-protocol/validator/internal/p2p/meshsha3"
)

// MeshNode is a single node in the TRION P2P validator mesh.
type MeshNode struct {
        mu           sync.RWMutex
        self         ValidatorProfile
        peers        map[MeshValidatorID]*ValidatorProfile
        attestations map[string][]BehavioralAttestation // key: entity_id
        quorumCh     chan QuorumResult
        ctx          context.Context
        cancel       context.CancelFunc
}

// NewMeshNode constructs a validator mesh node.
func NewMeshNode(profile ValidatorProfile) *MeshNode {
        ctx, cancel := context.WithCancel(context.Background())
        return &MeshNode{
                self:         profile,
                peers:        make(map[MeshValidatorID]*ValidatorProfile),
                attestations: make(map[string][]BehavioralAttestation),
                quorumCh:     make(chan QuorumResult, 256),
                ctx:          ctx,
                cancel:       cancel,
        }
}

// AddPeer registers a peer validator into the local mesh view.
func (m *MeshNode) AddPeer(p ValidatorProfile) {
        m.mu.Lock()
        defer m.mu.Unlock()
        m.peers[p.ID] = &p
}

// Attest stores a behavioral attestation, gossips it to peers, and checks quorum.
func (m *MeshNode) Attest(a BehavioralAttestation) {
        m.mu.Lock()
        m.attestations[a.EntityID] = append(m.attestations[a.EntityID], a)
        m.mu.Unlock()
        go m.gossip(a)
        go m.tryQuorum(a.EntityID)
}

// AttestLocal stores an attestation without gossip (for use by handlePeer).
func (m *MeshNode) AttestLocal(a BehavioralAttestation) {
        m.mu.Lock()
        m.attestations[a.EntityID] = append(m.attestations[a.EntityID], a)
        m.mu.Unlock()
        go m.tryQuorum(a.EntityID)
}

// gossip sends the attestation to all reachable peers using simple TCP push.
// One goroutine per peer — thousands of concurrent dials are cheap in Go.
func (m *MeshNode) gossip(a BehavioralAttestation) {
        data, err := json.Marshal(a)
        if err != nil {
                return
        }
        m.mu.RLock()
        peers := make([]*ValidatorProfile, 0, len(m.peers))
        for _, p := range m.peers {
                peers = append(peers, p)
        }
        m.mu.RUnlock()

        var wg sync.WaitGroup
        for _, p := range peers {
                wg.Add(1)
                go func(addr string) {
                        defer wg.Done()
                        conn, err := net.DialTimeout("tcp", addr, 2*time.Second)
                        if err != nil {
                                return // peer may not be listening; silently skip
                        }
                        defer conn.Close()
                        conn.SetWriteDeadline(time.Now().Add(2 * time.Second))
                        conn.Write(data)
                        conn.Write([]byte("\n"))
                }(p.Addr)
        }
        wg.Wait()
}

// tryQuorum checks if DW-BFT quorum has been reached for an entity.
// Quorum condition: Σ d_j(agree) / Σ d_j(all) ≥ 2/3
func (m *MeshNode) tryQuorum(entityID string) {
        m.mu.RLock()
        atts := m.attestations[entityID]
        m.mu.RUnlock()

        if len(atts) < 3 { // need at least f+1 = 3 attestations
                return
        }

        // Collect all validator weights (self + peers)
        allWeights := make(map[string]float64)
        m.mu.RLock()
        for _, p := range m.peers {
                allWeights[p.ID.Hex()] = p.DiversityWeight
        }
        m.mu.RUnlock()
        allWeights[m.self.ID.Hex()] = m.self.DiversityWeight

        totalWeight := 0.0
        for _, w := range allWeights {
                totalWeight += w
        }

        // Diversity-weighted coherence aggregation
        weightedC, agreedWeight, weightSquaredSum := 0.0, 0.0, 0.0
        for _, att := range atts {
                dw := att.DiversityWeight
                weightedC += dw * att.CoherenceC
                agreedWeight += dw
                weightSquaredSum += dw * dw
        }
        if agreedWeight > 0 {
                weightedC /= agreedWeight
        }

        // HHI of weight distribution (diversity check, whitepaper L4.8)
        hhi := 0.0
        if agreedWeight > 0 {
                hhi = weightSquaredSum / (agreedWeight * agreedWeight)
        }

        quorumReached := totalWeight > 0 && (agreedWeight/totalWeight) >= (2.0/3.0)

        result := QuorumResult{
                EntityID:         entityID,
                WeightedC:        weightedC,
                QuorumReached:    quorumReached,
                AttestationCount: len(atts),
                TotalWeight:      totalWeight,
                AgreementWeight:  agreedWeight,
                HHI:              hhi,
                Timestamp:        time.Now().UnixNano(),
        }
        if quorumReached {
                select {
                case m.quorumCh <- result:
                default:
                }
        }
}

// Listen starts a TCP listener for incoming attestations from peers.
func (m *MeshNode) Listen(addr string) error {
        ln, err := net.Listen("tcp", addr)
        if err != nil {
                return fmt.Errorf("validator mesh listen error: %w", err)
        }
        log.Printf("[TRION mesh] validator %s listening on %s", m.self.ID.Hex()[:16], addr)
        go func() {
                defer ln.Close()
                for {
                        conn, err := ln.Accept()
                        if err != nil {
                                select {
                                case <-m.ctx.Done():
                                        return
                                default:
                                        continue
                                }
                        }
                        go m.handlePeer(conn)
                }
        }()
        return nil
}

func (m *MeshNode) handlePeer(conn net.Conn) {
        defer conn.Close()
        dec := json.NewDecoder(conn)
        var att BehavioralAttestation
        if err := dec.Decode(&att); err != nil {
                return
        }
        m.AttestLocal(att)
}

// Stop shuts down the mesh node.
func (m *MeshNode) Stop() { m.cancel() }

// QuorumResults returns the channel where quorum results are published.
func (m *MeshNode) QuorumResults() <-chan QuorumResult { return m.quorumCh }

// AttestationCount returns how many attestations exist for a given entity.
func (m *MeshNode) AttestationCount(entityID string) int {
        m.mu.RLock()
        defer m.mu.RUnlock()
        return len(m.attestations[entityID])
}

// ── Cryptographic Primitives ───────────────────────────────────────────────

// DualStrandSign computes sense+antisense signatures for an attestation payload
// using the canonical TRION dual-strand construction (whitepaper L0.1):
//
//      sense     = SHA3-256(payload || 0x00)
//      antisense = SHA3-256(payload || 0xFF) XOR NOT(sense)
//
// Uses SHA3-256 (Keccak, FIPS 202) — NOT SHA-256 — to match the Rust L0 pipeline
// (trion-common::hash_dna::canonical_bh) and Python core/primitives/behavioral_hash.py
// for cross-system attestation verification. The XOR-NOT complement transform is
// REQUIRED for cross-language consistency: it binds the two strands so that the
// invariant
//
//      sense XOR antisense == NOT(SHA3-256(payload || 0xFF))
//
// holds for every payload (verified identically in Python, Rust, TypeScript and
// the meshsha3 golden vectors). Without it the antisense strand is an
// uncorrelated hash and tampering with one strand is not detectable from the pair.
func DualStrandSign(payload []byte) (sense, antisense string) {
        // Build the two domain-separated messages without aliasing the caller's
        // backing array (append on a slice with spare capacity would mutate it).
        p00 := make([]byte, len(payload), len(payload)+1)
        copy(p00, payload)
        p00 = append(p00, 0x00)

        pff := make([]byte, len(payload), len(payload)+1)
        copy(pff, payload)
        pff = append(pff, 0xFF)

        s := meshsha3.Sum256(p00)
        hff := meshsha3.Sum256(pff)

        // antisense = SHA3-256(payload||0xFF) XOR NOT(sense)
        var a [32]byte
        for i := 0; i < len(s); i++ {
                a[i] = hff[i] ^ (s[i] ^ 0xFF) // hff[i] ^ ^s[i]
        }
        return hex.EncodeToString(s[:]), hex.EncodeToString(a[:])
}

// DualStrandVerify confirms the structural dual-strand invariant on a hex pair:
// both strands must decode as 32-byte values and must differ. A canonically
// signed pair always differs, because sense == antisense would require
// SHA3-256(p||0x00) == SHA3-256(p||0xFF) — a SHA3 collision.
//
// This is the strand-only (payload-less) check; for the full cryptographic
// cross-language invariant use DualStrandVerifyPayload.
func DualStrandVerify(sense, antisense string) bool {
        if len(sense) != 64 || len(antisense) != 64 {
                return false
        }
        s, err1 := hex.DecodeString(sense)
        a, err2 := hex.DecodeString(antisense)
        if err1 != nil || err2 != nil || len(s) != 32 || len(a) != 32 {
                return false
        }
        for i := range s {
                if s[i] != a[i] {
                        return true
                }
        }
        return false // identical strands → collision or non-canonical construction
}

// DualStrandVerifyPayload verifies the full canonical BH invariant
// (whitepaper L0.1; identical to core/primitives/behavioral_hash.py):
//
//      antisense == SHA3-256(payload || 0xFF) XOR NOT(sense)
//
// equivalently: sense XOR antisense == NOT(SHA3-256(payload || 0xFF)).
// This is the cross-language golden-vector check shared with the Rust, Python
// and TypeScript implementations.
func DualStrandVerifyPayload(payload []byte, sense, antisense string) bool {
        if len(sense) != 64 || len(antisense) != 64 {
                return false
        }
        s, err1 := hex.DecodeString(sense)
        a, err2 := hex.DecodeString(antisense)
        if err1 != nil || err2 != nil || len(s) != 32 || len(a) != 32 {
                return false
        }
        pff := make([]byte, len(payload), len(payload)+1)
        copy(pff, payload)
        pff = append(pff, 0xFF)
        hff := meshsha3.Sum256(pff)
        for i := range s {
                if a[i] != hff[i]^(s[i]^0xFF) {
                        return false
                }
        }
        return true
}

// MeshDiversityWeight computes d_j = sqrt(|S_j ∩ S_consensus| / max(|S_j|, 1))
func MeshDiversityWeight(agreementsWithConsensus, totalObservations int) float64 {
        if totalObservations == 0 {
                return 0.5 // bootstrap prior
        }
        overlap := float64(agreementsWithConsensus) / float64(totalObservations)
        return math.Sqrt(overlap)
}

// MeshHHI computes the Herfindahl-Hirschman Index of a weight slice.
// Used for geographic/client diversity enforcement (whitepaper L4.8).
// Returns value in [0, 10000].
func MeshHHI(weights []float64) float64 {
        total := 0.0
        for _, w := range weights {
                total += w
        }
        if total == 0 {
                return 10000 // monopoly
        }
        sum := 0.0
        for _, w := range weights {
                share := w / total
                sum += share * share
        }
        return sum * 10000
}
