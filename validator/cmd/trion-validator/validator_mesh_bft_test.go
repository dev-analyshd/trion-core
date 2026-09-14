// TRION Protocol — validator mesh + BFT consensus wire-compatibility tests.
//
// The mesh gained consensus frames (bft_mesh.go) alongside the legacy
// behavioral-attestation traffic. These tests pin the compatibility contract:
//
//   §1  legacy frames (no "t" field) still decode as attestations;
//   §2  consensus envelopes decode with correct kinds, and malformed /
//       mismatched frames are rejected;
//   §3  real TCP round-trip: a consensus vote gossiped by one mesh arrives
//       at the peer's consensus handler, and a legacy attestation still
//       arrives through the attestation path (and the hook);
//   §4  a raw legacy producer (old binary) writing plain attestation JSON
//       is ingested by the new decoder;
//   §5  StartBFTNode smoke test.
//
// Author: TRION Protocol — Originator: Hudu Yusuf (Analys)
// License: CC0

package main

import (
	"crypto/ed25519"
	"encoding/json"
	"fmt"
	"net"
	"testing"
	"time"

	"github.com/trion-protocol/validator/internal/consensus"
	"github.com/trion-protocol/validator/internal/p2p"
	"github.com/trion-protocol/validator/internal/p2p/meshsha3"
)

func meshTestProfile(port int) ValidatorProfile {
	return ValidatorProfile{
		ID:              ValidatorID(meshsha3.Sum256([]byte(fmt.Sprintf("mesh-test-%d", port)))),
		Addr:            fmt.Sprintf("127.0.0.1:%d", port),
		DiversityWeight: 0.8,
		GeographicRegion: "US",
		ClientDiversity:  "trion-validator",
		UptimeFraction:   0.99,
	}
}

func freePort(t *testing.T) int {
	t.Helper()
	ln, err := net.Listen("tcp", "127.0.0.1:0")
	if err != nil {
		t.Fatalf("free port: %v", err)
	}
	defer ln.Close()
	return ln.Addr().(*net.TCPAddr).Port
}

// §1  Legacy frames decode as attestations.
func TestDecodeLegacyAttestationFrame(t *testing.T) {
	att := p2p.BehavioralAttestation{
		EntityID:        "entity-legacy",
		SignalType:      "BEHAVIORAL_COHERENCE",
		CoherenceC:      0.66,
		ThresholdTheta:  0.5,
		ValidatorID:      "legacy-peer",
		DiversityWeight: 0.7,
		Timestamp:       42,
		BlockNumber:     1,
	}
	raw, err := json.Marshal(att) // exactly what the OLD mesh wrote to the wire
	if err != nil {
		t.Fatal(err)
	}
	got, env, err := decodeMeshFrame(raw)
	if err != nil {
		t.Fatalf("legacy frame rejected: %v", err)
	}
	if env != nil {
		t.Fatal("legacy frame misclassified as consensus envelope")
	}
	if got.EntityID != att.EntityID || got.CoherenceC != att.CoherenceC ||
		got.SignatureSense != att.SignatureSense {
		t.Fatal("legacy frame decoded with wrong fields")
	}
}

// §2  Consensus envelope decoding (kinds, wire/vote-type agreement, errors).
func TestDecodeConsensusEnvelope(t *testing.T) {
	key := demoKeys("wire-test", 1)[0]
	addr := demoAddr(key)
	vote := func(typ consensus.VoteType) *consensus.Vote {
		v := &consensus.Vote{Type: typ, Height: 1, Round: 0,
			BlockHash: consensus.Hash(meshsha3.Sum256([]byte("blk"))), ValidatorAddress: addr}
		v.Signature = ed25519.Sign(key, v.SignBytes())
		return v
	}
	prop := &consensus.Proposal{Height: 1, Round: 0, POLRound: -1, TimestampMs: 1, Proposer: addr}

	marshal := func(ty uint8, m consensus.ConsensusMessage) []byte {
		data, err := json.Marshal(meshEnvelope{Type: ty, Msg: m})
		if err != nil {
			t.Fatal(err)
		}
		return data
	}

	// Prevote frame → Kind Vote, Type Prevote.
	_, env, err := decodeMeshFrame(marshal(meshMsgPrevote,
		consensus.ConsensusMessage{Kind: consensus.MsgKindVote, Vote: vote(consensus.VoteTypePrevote)}))
	if err != nil {
		t.Fatalf("prevote frame rejected: %v", err)
	}
	if env.Msg.Kind != consensus.MsgKindVote || env.Msg.Vote.Type != consensus.VoteTypePrevote {
		t.Fatal("prevote frame decoded wrong")
	}
	// Precommit frame → Kind Vote, Type Precommit.
	_, env, err = decodeMeshFrame(marshal(meshMsgPrecommit,
		consensus.ConsensusMessage{Kind: consensus.MsgKindVote, Vote: vote(consensus.VoteTypePrecommit)}))
	if err != nil {
		t.Fatalf("precommit frame rejected: %v", err)
	}
	if env.Msg.Vote.Type != consensus.VoteTypePrecommit {
		t.Fatal("precommit frame decoded wrong")
	}
	// Proposal frame.
	_, env, err = decodeMeshFrame(marshal(meshMsgProposal,
		consensus.ConsensusMessage{Kind: consensus.MsgKindProposal, Proposal: prop}))
	if err != nil {
		t.Fatalf("proposal frame rejected: %v", err)
	}
	if env.Msg.Kind != consensus.MsgKindProposal || env.Msg.Proposal == nil {
		t.Fatal("proposal frame decoded wrong")
	}

	// Wire/vote-type mismatch is rejected: a precommit ID carrying a prevote.
	if _, _, err := decodeMeshFrame(marshal(meshMsgPrecommit,
		consensus.ConsensusMessage{Kind: consensus.MsgKindVote, Vote: vote(consensus.VoteTypePrevote)})); err == nil {
		t.Fatal("precommit frame carrying a prevote accepted")
	}
	// Unknown type ID.
	if _, _, err := decodeMeshFrame([]byte(`{"t":99,"m":{}}`)); err == nil {
		t.Fatal("unknown type accepted")
	}
	// Payload mismatch: proposal ID, vote payload.
	if _, _, err := decodeMeshFrame(marshal(meshMsgProposal,
		consensus.ConsensusMessage{Kind: consensus.MsgKindProposal, Proposal: prop, Vote: vote(consensus.VoteTypePrevote)})); err == nil {
		t.Fatal("frame with mismatched payload accepted")
	}
	// Garbage.
	if _, _, err := decodeMeshFrame([]byte(`not json`)); err == nil {
		t.Fatal("garbage accepted")
	}

	// wireTypeFromConsensus round-trip: distinct IDs for prevote/precommit.
	ids := map[uint8]bool{}
	for _, m := range []consensus.ConsensusMessage{
		{Kind: consensus.MsgKindVote, Vote: vote(consensus.VoteTypePrevote)},
		{Kind: consensus.MsgKindVote, Vote: vote(consensus.VoteTypePrecommit)},
		{Kind: consensus.MsgKindProposal, Proposal: prop},
	} {
		id, ok := wireTypeFromConsensus(m)
		if !ok {
			t.Fatalf("wireTypeFromConsensus failed for kind %v", m.Kind)
		}
		if ids[id] {
			t.Fatalf("duplicate wire id %d", id)
		}
		ids[id] = true
	}
}

// §3  TCP round-trip: consensus frames reach the peer's handler; legacy
// attestations still flow through the attestation path and the hook.
func TestMeshTCPRoundTripConsensusAndAttestations(t *testing.T) {
	portA, portB := freePort(t), freePort(t)
	profA, profB := meshTestProfile(portA), meshTestProfile(portB)

	meshA := NewMeshNode(profA)
	meshB := NewMeshNode(profB)
	if err := meshA.Listen(profA.Addr); err != nil {
		t.Fatalf("listen A: %v", err)
	}
	if err := meshB.Listen(profB.Addr); err != nil {
		t.Fatalf("listen B: %v", err)
	}
	defer meshA.Stop()
	defer meshB.Stop()
	meshA.AddPeer(profB)
	meshB.AddPeer(profA)

	gotConsensus := make(chan consensus.ConsensusMessage, 4)
	meshB.SetConsensusHandler(func(m consensus.ConsensusMessage) { gotConsensus <- m })
	gotAtts := make(chan p2p.BehavioralAttestation, 4)
	meshB.SetAttestationHook(func(a p2p.BehavioralAttestation) { gotAtts <- a })

	// A gossips a signed prevote for B.
	key := demoKeys("tcp-test", 1)[0]
	v := &consensus.Vote{Type: consensus.VoteTypePrevote, Height: 9, Round: 2,
		BlockHash: consensus.Hash(meshsha3.Sum256([]byte("tcp"))), ValidatorAddress: demoAddr(key)}
	v.Signature = ed25519.Sign(key, v.SignBytes())
	meshA.gossipConsensus(consensus.ConsensusMessage{Kind: consensus.MsgKindVote, Vote: v})

	select {
	case m := <-gotConsensus:
		if m.Kind != consensus.MsgKindVote || m.Vote == nil || m.Vote.Height != 9 || m.Vote.Round != 2 {
			t.Fatalf("consensus frame corrupted in transit: %+v", m)
		}
		if !m.Vote.Verify(key.Public().(ed25519.PublicKey)) {
			t.Fatal("vote signature did not survive the wire round-trip")
		}
	case <-time.After(5 * time.Second):
		t.Fatal("consensus frame never arrived at the peer")
	}

	// A attests through the LEGACY path; B must receive it (mesh store + hook).
	att := p2p.BehavioralAttestation{
		EntityID: "entity-tcp", SignalType: "BEHAVIORAL_COHERENCE",
		CoherenceC: 0.5, ThresholdTheta: 0.5, ValidatorID: "tcp-peer",
		DiversityWeight: 0.8, Timestamp: 1, BlockNumber: 1,
	}
	meshA.Attest(att)
	select {
	case a := <-gotAtts:
		if a.EntityID != att.EntityID {
			t.Fatal("attestation corrupted in transit")
		}
	case <-time.After(5 * time.Second):
		t.Fatal("legacy attestation never arrived at the peer")
	}
	deadline := time.Now().Add(3 * time.Second)
	for meshB.AttestationCount(att.EntityID) == 0 && time.Now().Before(deadline) {
		time.Sleep(5 * time.Millisecond)
	}
	if meshB.AttestationCount(att.EntityID) == 0 {
		t.Fatal("attestation not stored at the peer mesh")
	}
}

// §4  A raw legacy producer (old binary) writing plain attestation JSON is
// still ingested by the new decoder.
func TestLegacyPeerRawWriteIngested(t *testing.T) {
	port := freePort(t)
	prof := meshTestProfile(port)
	mesh := NewMeshNode(prof)
	if err := mesh.Listen(prof.Addr); err != nil {
		t.Fatalf("listen: %v", err)
	}
	defer mesh.Stop()

	gotAtts := make(chan p2p.BehavioralAttestation, 1)
	mesh.SetAttestationHook(func(a p2p.BehavioralAttestation) { gotAtts <- a })

	att := p2p.BehavioralAttestation{
		EntityID: "entity-oldpeer", SignalType: "BEHAVIORAL_COHERENCE",
		CoherenceC: 0.9, ThresholdTheta: 0.5, ValidatorID: "old-binary",
		DiversityWeight: 0.6, Timestamp: 7, BlockNumber: 2,
	}
	raw, err := json.Marshal(att) // what the pre-consensus mesh wrote
	if err != nil {
		t.Fatal(err)
	}
	conn, err := net.DialTimeout("tcp", prof.Addr, 2*time.Second)
	if err != nil {
		t.Fatalf("dial: %v", err)
	}
	conn.SetWriteDeadline(time.Now().Add(2 * time.Second))
	conn.Write(raw)
	conn.Write([]byte("\n"))
	conn.Close()

	select {
	case a := <-gotAtts:
		if a.EntityID != att.EntityID || a.CoherenceC != 0.9 {
			t.Fatal("legacy raw frame decoded wrong")
		}
	case <-time.After(5 * time.Second):
		t.Fatal("legacy raw frame never ingested")
	}
}

// §5  StartBFTNode smoke test: engine, ledger, chain, channels and hooks.
func TestStartBFTNodeSmoke(t *testing.T) {
	keys := demoKeys("bft-smoke", 4)
	vals := make([]*consensus.Validator, 4)
	for i, k := range keys {
		vals[i] = consensus.NewValidator(k, 1_000_000, 1_000_000)
	}
	valSet, err := consensus.NewValidatorSet(vals)
	if err != nil {
		t.Fatalf("NewValidatorSet: %v", err)
	}
	port := freePort(t)
	prof := meshTestProfile(port)
	// Give the mesh node the identity of validator 0 so the engine accepts it.
	prof.ID = ValidatorID(demoAddr(keys[0]))
	mesh := NewMeshNode(prof)
	if err := mesh.Listen(prof.Addr); err != nil {
		t.Fatalf("listen: %v", err)
	}
	defer mesh.Stop()

	bft, err := StartBFTNode(mesh, keys[0], valSet, BFTOptions{ChainID: "bft-smoke"})
	if err != nil {
		t.Fatalf("StartBFTNode: %v", err)
	}
	defer bft.Stop()
	if bft.Engine() == nil || bft.Ledger() == nil || bft.Chain() == nil {
		t.Fatal("BFTNode incompletely wired")
	}
	select {
	case <-bft.FinalizedBlocks():
		t.Fatal("unexpected finalized block before Start")
	default:
	}
	// The attestation hook feeds the engine mempool.
	mesh.Attest(p2p.BehavioralAttestation{EntityID: "smoke", SignalType: "X",
		CoherenceC: 1, ThresholdTheta: 1, ValidatorID: "smoke", Timestamp: 1})
	if bft.Engine().Height() != 1 {
		t.Fatalf("engine height %d, want 1 (fresh chain)", bft.Engine().Height())
	}
	bft.Stop() // idempotent
	bft.Stop()
}
