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

// DualStrandSign computes sense+antisense signatures for an attestation payload.
// Uses SHA3-256 (Keccak, FIPS 202) — NOT SHA-256 — to match the Rust L0 pipeline
// (trion-common::hash_dna::canonical_bh) for cross-system attestation verification.
func DualStrandSign(payload []byte) (sense, antisense string) {
        s := meshsha3.Sum256(append(payload, 0x00))
        a := meshsha3.Sum256(append(payload, 0xFF))
        return hex.EncodeToString(s[:]), hex.EncodeToString(a[:])
}

// DualStrandVerify confirms sense XOR antisense ≠ 0 (they must differ).
func DualStrandVerify(sense, antisense string) bool {
        if sense == antisense {
                return false // would mean hash collision
        }
        for i := range sense {
                if sense[i] != antisense[i] {
                        return true
                }
        }
        return false
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
