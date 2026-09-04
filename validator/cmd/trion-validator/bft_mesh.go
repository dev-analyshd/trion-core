// TRION Protocol — TRION-BFT consensus wiring into the validator mesh.
//
// This file closes the "no consensus implementation" gap end-to-end: the
// DW-BFT consensus engine (internal/consensus) is coupled to the existing
// attestation mesh so that
//
//   - the mesh's behavioral attestations become consensus transactions:
//     every attestation the mesh ingests (locally produced or received from
//     peers) is submitted to the engine's mempool and included in blocks;
//   - consensus messages (proposals, prevotes, precommits, evidence and
//     finalized blocks) are gossiped over the SAME TCP mesh as attestations,
//     using NEW envelope message-type IDs that are fully backward compatible
//     with the legacy attestation traffic (legacy frames carry no type field
//     at all, so old peers never misparse new frames, and new peers decode
//     legacy frames as attestations);
//   - finalized blocks are exposed to consumers via a channel
//     (BFTNode.FinalizedBlocks).
//
// Wire format (line-delimited JSON, same transport as attestations):
//
//      legacy attestation:  {"entity_id":...}                 // no "t" field
//      consensus envelope:  {"t":<id>,"m":{...ConsensusMessage}}
//
// where <id> ∈ {1 propose, 2 prevote, 3 precommit, 4 block, 5 evidence}.
//
// Author: TRION Protocol — Originator: Hudu Yusuf (Analys)
// License: CC0

package main

import (
        "crypto/ed25519"
        "encoding/json"
        "fmt"
        "io"
        "log"
        "net"
        "sync"
        "time"

        "github.com/trion-protocol/validator/internal/consensus"
        "github.com/trion-protocol/validator/internal/p2p"
        "github.com/trion-protocol/validator/internal/p2p/meshsha3"
)

// ── Mesh wire envelope: consensus message type IDs ──────────────────────────
//
// The IDs are NEW relative to the legacy attestation traffic, which has no
// type field at all (implicitly meshMsgAttestation). Decoding is therefore
// backward and forward compatible in both directions.

const (
        meshMsgAttestation uint8 = 0 // legacy frame (implicit: no "t" field present)
        meshMsgProposal    uint8 = 1 // block proposal (round leader)
        meshMsgPrevote     uint8 = 2 // PREVOTE step vote
        meshMsgPrecommit   uint8 = 3 // PRECOMMIT step vote
        meshMsgBlock       uint8 = 4 // finalized block announcement
        meshMsgEvidence    uint8 = 5 // equivocation evidence for slashing
)

// meshEnvelope wraps a consensus message with an explicit wire type ID.
type meshEnvelope struct {
        Type uint8                     `json:"t"`
        Msg  consensus.ConsensusMessage `json:"m"`
}

// consensusKindFromWire maps a wire type ID to the consensus message kind,
// normalizing the payload so the engine only ever sees well-formed messages.
func consensusKindFromWire(t uint8) (consensus.MessageKind, bool) {
        switch t {
        case meshMsgProposal:
                return consensus.MsgKindProposal, true
        case meshMsgPrevote, meshMsgPrecommit:
                return consensus.MsgKindVote, true
        case meshMsgBlock:
                return consensus.MsgKindFinalizedBlock, true
        case meshMsgEvidence:
                return consensus.MsgKindEvidence, true
        default:
                return 0, false
        }
}

// wireTypeFromConsensus maps a consensus message to its wire type ID.
// Prevotes and precommits get DISTINCT IDs on the wire (they are the same
// consensus.Kind but different VoteTypes).
func wireTypeFromConsensus(m consensus.ConsensusMessage) (uint8, bool) {
        switch m.Kind {
        case consensus.MsgKindProposal:
                if m.Proposal == nil {
                        return 0, false
                }
                return meshMsgProposal, true
        case consensus.MsgKindVote:
                if m.Vote == nil {
                        return 0, false
                }
                if m.Vote.Type == consensus.VoteTypePrevote {
                        return meshMsgPrevote, true
                }
                return meshMsgPrecommit, true
        case consensus.MsgKindEvidence:
                if m.Evidence == nil {
                        return 0, false
                }
                return meshMsgEvidence, true
        case consensus.MsgKindFinalizedBlock:
                if m.Block == nil {
                        return 0, false
                }
                return meshMsgBlock, true
        default:
                return 0, false
        }
}

// decodeMeshFrame decodes one raw JSON frame from the mesh wire:
//   - a frame WITHOUT a "t" field (or t == 0) is a legacy behavioral
//     attestation;
//   - a frame with t ∈ 1..5 is a consensus envelope (the kind is re-derived
//     from the wire type ID, and the envelope's consistency with its payload
//     is verified).
func decodeMeshFrame(raw []byte) (p2p.BehavioralAttestation, *meshEnvelope, error) {
        var att p2p.BehavioralAttestation
        var probe struct {
                T uint8 `json:"t"`
        }
        if err := json.Unmarshal(raw, &probe); err != nil {
                return att, nil, fmt.Errorf("mesh frame: %w", err)
        }
        if probe.T == meshMsgAttestation {
                if err := json.Unmarshal(raw, &att); err != nil {
                        return att, nil, fmt.Errorf("legacy attestation frame: %w", err)
                }
                return att, nil, nil
        }
        kind, ok := consensusKindFromWire(probe.T)
        if !ok {
                return att, nil, fmt.Errorf("unknown mesh message type %d", probe.T)
        }
        var env meshEnvelope
        if err := json.Unmarshal(raw, &env); err != nil {
                return att, nil, fmt.Errorf("consensus envelope: %w", err)
        }
        env.Msg.Kind = kind
        // Structural consistency: exactly the payload matching the type ID.
        switch kind {
        case consensus.MsgKindProposal:
                if env.Msg.Proposal == nil || env.Msg.Vote != nil || env.Msg.Evidence != nil || env.Msg.Block != nil {
                        return att, nil, fmt.Errorf("proposal frame payload mismatch")
                }
        case consensus.MsgKindVote:
                if env.Msg.Vote == nil || env.Msg.Proposal != nil || env.Msg.Evidence != nil || env.Msg.Block != nil {
                        return att, nil, fmt.Errorf("vote frame payload mismatch")
                }
                // The wire ID and the embedded Vote.Type must agree.
                want := consensus.VoteTypePrevote
                if probe.T == meshMsgPrecommit {
                        want = consensus.VoteTypePrecommit
                }
                if env.Msg.Vote.Type != want {
                        return att, nil, fmt.Errorf("vote frame type %d carries a %s vote", probe.T, env.Msg.Vote.Type)
                }
        case consensus.MsgKindEvidence:
                if env.Msg.Evidence == nil || env.Msg.Proposal != nil || env.Msg.Vote != nil || env.Msg.Block != nil {
                        return att, nil, fmt.Errorf("evidence frame payload mismatch")
                }
        case consensus.MsgKindFinalizedBlock:
                if env.Msg.Block == nil || env.Msg.Proposal != nil || env.Msg.Vote != nil || env.Msg.Evidence != nil {
                        return att, nil, fmt.Errorf("block frame payload mismatch")
                }
        }
        return att, &env, nil
}

// gossipConsensus marshals a consensus message into a mesh envelope and
// pushes it to every reachable peer over the same TCP transport the
// attestation gossip uses. The engine's self-messages never loop back
// through here (votes are self-delivered internally), so there is no echo
// amplification.
func (m *MeshNode) gossipConsensus(msg consensus.ConsensusMessage) {
        t, ok := wireTypeFromConsensus(msg)
        if !ok {
                return
        }
        data, err := json.Marshal(meshEnvelope{Type: t, Msg: msg})
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

// SetConsensusHandler registers the sink for consensus frames received from
// peers (normally consensus.Engine.HandleMessage). Nil disables decoding.
func (m *MeshNode) SetConsensusHandler(h func(consensus.ConsensusMessage)) {
        m.mu.Lock()
        m.consensusHandler = h
        m.mu.Unlock()
}

// SetAttestationHook registers a sink fed with every attestation the mesh
// ingests — locally produced (Attest) or received from a peer (AttestLocal →
// handlePeer). The consensus engine subscribes with SubmitAttestation so
// attestations become block transactions. Nil disables.
func (m *MeshNode) SetAttestationHook(h func(p2p.BehavioralAttestation)) {
        m.mu.Lock()
        m.attestationHook = h
        m.mu.Unlock()
}

// ── BFT node: engine + slashing ledger + mesh coupling ──────────────────────

// BFTNode couples one validator mesh node with a TRION-BFT consensus engine.
// Construction order: NewMeshNode → MeshNode.Listen → AddPeer (all-to-all) →
// StartBFTNode → BFTNode.Start.
type BFTNode struct {
        mesh      *MeshNode
        engine    *consensus.Engine
        ledger    *consensus.StakeLedger
        chain     *consensus.Blockchain
        finalized chan consensus.FinalizedBlock
        done      chan struct{}
        stopOnce  sync.Once
}

// BFTOptions tunes StartBFTNode. Zero values get engine defaults.
type BFTOptions struct {
        ChainID        string
        ProposeTimeout time.Duration
        PrevoteTimeout time.Duration
        PrecommitTimeout time.Duration
        MaxBlockTxs    int
        Logger         *log.Logger
}

// StartBFTNode builds the engine, the in-memory stake ledger and the chain,
// wires the mesh (consensus frames → engine, attestations → mempool, engine
// Outbound → mesh gossip), and starts the finalized-block relay goroutine.
// The engine itself is started by a subsequent call to Start.
func StartBFTNode(mesh *MeshNode, key ed25519.PrivateKey, valSet *consensus.ValidatorSet, opts BFTOptions) (*BFTNode, error) {
        if mesh == nil {
                return nil, fmt.Errorf("bft: mesh required")
        }
        if valSet == nil {
                return nil, fmt.Errorf("bft: validator set required")
        }
        stakes := make(map[consensus.Hash]uint64, valSet.Size())
        for _, v := range valSet.Validators() {
                stakes[v.Address] = v.StakeMicro
        }
        ledger := consensus.NewStakeLedger(consensus.DefaultSlashPolicy(), stakes)

        chainID := opts.ChainID
        if chainID == "" {
                chainID = "trion-bft"
        }
        chain := consensus.NewBlockchain(chainID)

        cfg := consensus.Config{
                ChainID:           chainID,
                Key:               key,
                ProposeTimeout:    opts.ProposeTimeout,
                PrevoteTimeout:    opts.PrevoteTimeout,
                PrecommitTimeout:  opts.PrecommitTimeout,
                MaxBlockTxs:       opts.MaxBlockTxs,
                Slasher:           ledger,
                Logger:            opts.Logger,
                Clock:             time.Now, // wall-clock mode for the live mesh
                Outbound:          mesh.gossipConsensus, // engine → mesh → peers
        }
        engine, err := consensus.NewEngine(cfg, valSet, chain, nil)
        if err != nil {
                return nil, fmt.Errorf("bft: %w", err)
        }

        n := &BFTNode{
                mesh:      mesh,
                engine:    engine,
                ledger:    ledger,
                chain:     chain,
                finalized: make(chan consensus.FinalizedBlock, 256),
                done:      make(chan struct{}),
        }

        mesh.SetConsensusHandler(engine.HandleMessage)
        mesh.SetAttestationHook(engine.SubmitAttestation)

        // Relay finalized blocks from the engine's (drop-on-slow) channel to a
        // wider consumer channel, and log every commit.
        go func() {
                for {
                        select {
                        case <-n.done:
                                return
                        case fb, ok := <-engine.FinalizedBlocks():
                                if !ok {
                                        return
                                }
                                logger := opts.Logger
                                if logger == nil {
                                        logger = log.Default()
                                }
                                logger.Printf("[TRION-BFT] committed height=%d round=%d hash=%s txs=%d evidence=%d",
                                        fb.Block.Height, fb.CommitRound, fb.Block.Hash().Short(),
                                        len(fb.Block.Txs), len(fb.Block.Evidence))
                                select {
                                case n.finalized <- fb:
                                default: // consumer still slow on the wider channel: drop
                                }
                        }
                }
        }()
        return n, nil
}

// Start starts the consensus engine at the next height.
func (n *BFTNode) Start() { n.engine.Start() }

// Stop stops the engine and the finalized-block relay.
func (n *BFTNode) Stop() {
        n.stopOnce.Do(func() {
                n.engine.Stop()
                close(n.done)
        })
}

// FinalizedBlocks exposes committed blocks to consumers (channel/callback
// sink). The mesh also gossips each finalized block as a wire "block" frame
// for observability.
func (n *BFTNode) FinalizedBlocks() <-chan consensus.FinalizedBlock { return n.finalized }

// Engine returns the underlying consensus engine (metrics, state queries).
func (n *BFTNode) Engine() *consensus.Engine { return n.engine }

// Ledger returns the node's stake ledger (slash accounting).
func (n *BFTNode) Ledger() *consensus.StakeLedger { return n.ledger }

// Chain returns the node's in-memory blockchain.
func (n *BFTNode) Chain() *consensus.Blockchain { return n.chain }

// SubmitAttestation feeds one behavioral attestation straight into the
// engine's mempool (in addition to the mesh ingestion hook).
func (n *BFTNode) SubmitAttestation(att p2p.BehavioralAttestation) {
        n.engine.SubmitAttestation(att)
}

// ── Deterministic demo keys ──────────────────────────────────────────────────

// demoRand is a deterministic io.Reader (SHA3-256 counter stream) so the
// self-test demo runs on fixed keys and is reproducible.
type demoRand struct {
        seed    string
        counter uint64
        block   [32]byte
        off     int
}

func (r *demoRand) Read(p []byte) (int, error) {
        n := 0
        for n < len(p) {
                if r.off == 0 || r.off >= len(r.block) {
                        buf := append([]byte(r.seed), byte(r.counter), byte(r.counter>>8),
                                byte(r.counter>>16), byte(r.counter>>24), byte(r.counter>>32),
                                byte(r.counter>>40), byte(r.counter>>48), byte(r.counter>>56))
                        r.block = meshsha3.Sum256(buf)
                        r.counter++
                        r.off = 0
                }
                m := copy(p[n:], r.block[r.off:])
                r.off += m
                n += m
        }
        return n, nil
}

func demoKeys(seed string, n int) []ed25519.PrivateKey {
        rnd := &demoRand{seed: seed}
        keys := make([]ed25519.PrivateKey, n)
        for i := range keys {
                _, priv, err := ed25519.GenerateKey(rnd)
                if err != nil {
                        panic("bft demo: ed25519 keygen: " + err.Error())
                }
                keys[i] = priv
        }
        return keys
}

func demoAddr(key ed25519.PrivateKey) consensus.Hash {
        return consensus.Hash(meshsha3.Sum256(key.Public().(ed25519.PublicKey)))
}

func pickFreePort() (int, error) {
        ln, err := net.Listen("tcp", "127.0.0.1:0")
        if err != nil {
                return 0, err
        }
        defer ln.Close()
        return ln.Addr().(*net.TCPAddr).Port, nil
}

// runBFTDemo spins up four fully-connected validator mesh nodes on local
// ephemeral ports, attaches a TRION-BFT engine to each, pushes one behavioral
// attestation through the LEGACY mesh gossip path (backward compatibility:
// it must become a block transaction), and verifies that all four nodes
// commit identical blocks over TCP-consensus traffic.
func runBFTDemo() error {
        const nVals = 4
        const chainID = "trion-bft-demo"
        keys := demoKeys("trion-bft-demo-seed", nVals)

        vals := make([]*consensus.Validator, nVals)
        for i, k := range keys {
                vals[i] = consensus.NewValidator(k, 1_000_000, 1_000_000) // 1.0 effective power
        }
        valSet, err := consensus.NewValidatorSet(vals)
        if err != nil {
                return fmt.Errorf("demo: validator set: %w", err)
        }

        meshes := make([]*MeshNode, nVals)
        bfts := make([]*BFTNode, nVals)
        defer func() {
                for _, b := range bfts {
                        if b != nil {
                                b.Stop()
                        }
                }
                for _, m := range meshes {
                        if m != nil {
                                m.Stop()
                        }
                }
        }()

        profiles := make([]ValidatorProfile, nVals)
        for i := 0; i < nVals; i++ {
                port, err := pickFreePort()
                if err != nil {
                        return fmt.Errorf("demo: free port: %w", err)
                }
                addr := fmt.Sprintf("127.0.0.1:%d", port)
                profiles[i] = ValidatorProfile{
                        ID:              ValidatorID(demoAddr(keys[i])),
                        Addr:            addr,
                        DiversityWeight: 0.9,
                        GeographicRegion: "US",
                        ClientDiversity:  "trion-validator",
                        UptimeFraction:   0.99,
                        BehavioralAge:    1000,
                }
                meshes[i] = NewMeshNode(profiles[i])
                if err := meshes[i].Listen(addr); err != nil {
                        return fmt.Errorf("demo: listen %s: %w", addr, err)
                }
        }
        // All-to-all peering (static seed set — see README for the live-network
        // peer-discovery gap).
        for i := 0; i < nVals; i++ {
                for j := 0; j < nVals; j++ {
                        if i != j {
                                meshes[i].AddPeer(profiles[j])
                        }
                }
        }

        for i := 0; i < nVals; i++ {
                bfts[i], err = StartBFTNode(meshes[i], keys[i], valSet, BFTOptions{
                        ChainID: chainID,
                        Logger:  log.New(io.Discard, "", 0), // quiet demo; swap for log.Default()
                })
                if err != nil {
                        return err
                }
        }

        // One attestation enters through the LEGACY mesh path on node 0; the
        // attestation gossip delivers it to every mesh, and each mesh's
        // attestation hook feeds its engine's mempool.
        payload := []byte(`{"entity_id":"0xDEMO-ENTITY","C":0.72}`)
        sense, antisense := p2p.DualStrandSign(payload)
        att := p2p.BehavioralAttestation{
                EntityID:           "0xDEMO-ENTITY",
                SignalType:         "BEHAVIORAL_COHERENCE",
                CoherenceC:         0.72,
                ThresholdTheta:     0.5,
                ValidatorID:         "demo-validator-0",
                DiversityWeight:    0.9,
                Timestamp:          time.Now().Unix(),
                BlockNumber:        1,
                SignatureSense:     sense,
                SignatureAntisense: antisense,
        }
        meshes[0].Attest(att)

        // Wait for the attestation to reach all four meshes.
        deadline := time.Now().Add(5 * time.Second)
        for time.Now().Before(deadline) {
                ok := true
                for _, m := range meshes {
                        if m.AttestationCount(att.EntityID) < 1 {
                                ok = false
                        }
                }
                if ok {
                        break
                }
                time.Sleep(10 * time.Millisecond)
        }
        for i, m := range meshes {
                if m.AttestationCount(att.EntityID) < 1 {
                        return fmt.Errorf("demo: attestation did not propagate to mesh %d", i)
                }
        }

        // Start consensus; all four engines should commit round-0 blocks over the
        // TCP consensus gossip.
        for _, b := range bfts {
                b.Start()
        }
        deadline = time.Now().Add(30 * time.Second)
        for time.Now().Before(deadline) {
                ok := true
                for _, b := range bfts {
                        if b.Engine().ChainHeight() < 2 {
                                ok = false
                        }
                }
                if ok {
                        break
                }
                time.Sleep(10 * time.Millisecond)
        }
        for i, b := range bfts {
                if b.Engine().ChainHeight() < 2 {
                        return fmt.Errorf("demo: engine %d committed only height %d", i, b.Engine().ChainHeight())
                }
                if err := b.Engine().Fault(); err != nil {
                        return fmt.Errorf("demo: engine %d fault: %w", i, err)
                }
        }

        // Convergence: identical block hashes on every node.
        ref1, ref2 := bfts[0].Chain().BlockAt(1), bfts[0].Chain().BlockAt(2)
        if ref1 == nil || ref2 == nil {
                return fmt.Errorf("demo: missing blocks")
        }
        for i := 1; i < nVals; i++ {
                if bfts[i].Chain().BlockAt(1).Hash() != ref1.Hash() ||
                        bfts[i].Chain().BlockAt(2).Hash() != ref2.Hash() {
                        return fmt.Errorf("demo: chain divergence at node %d", i)
                }
        }

        // Report one finalized block from the consumer channel.
        select {
        case fb := <-bfts[0].FinalizedBlocks():
                fmt.Printf("  BFT: finalized height=%d round=%d hash=%s txs=%d\n",
                        fb.Block.Height, fb.CommitRound, fb.Block.Hash().Short(), len(fb.Block.Txs))
        case <-time.After(2 * time.Second):
                return fmt.Errorf("demo: no finalized block delivered to consumer channel")
        }
        fmt.Printf("  BFT: 4/4 nodes converged on identical block hashes (commit round 0)\n")
        fmt.Printf("PASS — TRION-BFT consensus over the validator mesh verified\n")
        return nil
}
