// TRION Protocol — DW-BFT consensus engine test suite.
//
// Tendermint-rule coverage (the properties a BFT engine must hold):
//
//   §1  Happy path: 4 validators, no faults → commit in round 0, chain grows,
//       every node converges on identical block hashes.
//   §2  Byzantine equivocator: 1-of-4 double-precommits at the same
//       height+round → evidence recorded on every honest node, validator
//       slashed + tombstoned + removed from the set at the next height, and
//       the chain STILL commits (safety and liveness under f=1, n=4).
//   §3  Leader timeout: the round-0 proposer is partitioned → view change to
//       round 1 with doubled timeouts → commit succeeds.
//   §4  Proposer selection frequency follows diversity-weighted power
//       (s_j·d_j) — fixed-seed statistical check over 10 000 (height, round)
//       samples.
//   §5  Deterministic replay: the same message sequence yields identical
//       block hashes; a different chain ID yields different hashes.
//   §6  Exactly-2/3 precommit power does NOT commit (strict >2/3 rule);
//       adding the remaining validator's precommit does.
//   §7  Unit tests: quorum arithmetic, block-hash determinism, evidence-hash
//       canonical ordering, mempool, slashing idempotency, signatures,
//       timeout doubling, validator-set operations, JSON wire round-trip.
//
// The network harness (testNet) is fully deterministic: FIFO message queue,
// fixed delivery order, deterministic ed25519 keys from a seeded stream, and
// (for hash-replay tests) no wall clock — the engine derives block
// timestamps from the parent tip when Config.Clock is nil.
//
// Author: TRION Protocol — Originator: Hudu Yusuf (Analys)
// License: CC0

package consensus

import (
        "crypto/ed25519"
        "encoding/json"
        "fmt"
        "io"
        "log"
        "math"
        "strings"
        "sync"
        "testing"
        "time"

        "github.com/trion-protocol/validator/internal/p2p"
        "github.com/trion-protocol/validator/internal/p2p/meshsha3"
)

// ─────────────────────────────────────────────────────────────────────────────
// Deterministic key generation (fixed seeds)
// ─────────────────────────────────────────────────────────────────────────────

// detRand is a deterministic io.Reader: a SHA3-256 keyed counter stream.
// Same seed → same bytes → same ed25519 keys → same validator set → same
// proposer schedule → same block hashes. This is what makes every test here
// reproducible (and what the "fixed-seed" statistical check relies on).
type detRand struct {
        seed    string
        counter uint64
        block   [32]byte
        off     int
}

func (r *detRand) Read(p []byte) (int, error) {
        n := 0
        for n < len(p) {
                if r.off == 0 || r.off >= len(r.block) {
                        buf := make([]byte, 0, 16+len(r.seed)+8)
                        buf = append(buf, r.seed...)
                        buf = appendUint64(buf, r.counter)
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

func genKeys(t *testing.T, seed string, n int) []ed25519.PrivateKey {
        t.Helper()
        rnd := &detRand{seed: "trion-test/" + seed}
        keys := make([]ed25519.PrivateKey, n)
        for i := range keys {
                _, priv, err := ed25519.GenerateKey(rnd)
                if err != nil {
                        t.Fatalf("ed25519 keygen: %v", err)
                }
                keys[i] = priv
        }
        return keys
}

func addrOf(key ed25519.PrivateKey) Hash {
        return Hash(meshsha3.Sum256(key.Public().(ed25519.PublicKey)))
}

// ─────────────────────────────────────────────────────────────────────────────
// Deterministic in-process network harness
// ─────────────────────────────────────────────────────────────────────────────

type netMsg struct {
        from Hash
        m    ConsensusMessage
}

// testNet is a deterministic network: every engine's Outbound callback
// appends to a FIFO queue; the pump delivers each message to every engine in
// engine order. Timer-driven tests (view change) use pumpUntil, which also
// handles messages produced asynchronously by timeout callbacks.
type testNet struct {
        mu      sync.Mutex
        engines []*Engine
        queue   []netMsg
        dropped map[Hash]bool // partitioned validators: their messages are dropped
}

func (n *testNet) enqueue(from Hash, m ConsensusMessage) {
        n.mu.Lock()
        n.queue = append(n.queue, netMsg{from: from, m: m})
        n.mu.Unlock()
}

func (n *testNet) next() (netMsg, bool) {
        n.mu.Lock()
        defer n.mu.Unlock()
        if len(n.queue) == 0 {
                return netMsg{}, false
        }
        qm := n.queue[0]
        n.queue = n.queue[1:]
        return qm, true
}

// deliver fans one message out to every engine. dropped is written only
// during setup (before any pumping) and read-only afterwards.
func (n *testNet) deliver(qm netMsg) {
        if n.dropped[qm.from] {
                return
        }
        for _, e := range n.engines {
                e.HandleMessage(qm.m)
        }
}

// pumpUntil delivers messages until cond() holds or the timeout expires.
// Returns cond()'s final value.
func (n *testNet) pumpUntil(cond func() bool, timeout time.Duration) bool {
        deadline := time.Now().Add(timeout)
        for !cond() {
                qm, ok := n.next()
                if ok {
                        n.deliver(qm)
                        continue
                }
                if time.Now().After(deadline) {
                        return cond()
                }
                time.Sleep(2 * time.Millisecond)
        }
        return true
}

// testWorld bundles one test network with its validator material.
type testWorld struct {
        net     *testNet
        keys    []ed25519.PrivateKey
        addrs   []Hash
        valSet  *ValidatorSet
        ledger  *StakeLedger
        engines []*Engine
        chains  []*Blockchain
}

// newTestNet builds n validators (equal power: stake 1, d=1) with
// deterministic keys, a shared StakeLedger, one engine + chain + mempool per
// validator, and wires each engine's Outbound into the shared FIFO queue.
// Timeouts default to 10s so purely message-driven tests never race timers;
// the view-change test overrides them per engine.
func newTestNet(t *testing.T, seed, chainID string, n int, cfgFn func(cfg *Config)) *testWorld {
        t.Helper()
        keys := genKeys(t, seed, n)
        vals := make([]*Validator, n)
        for i, k := range keys {
                vals[i] = NewValidator(k, 1_000_000, 1_000_000) // power = 1.0 (micro units)
        }
        valSet, err := NewValidatorSet(vals)
        if err != nil {
                t.Fatalf("NewValidatorSet: %v", err)
        }
        stakes := make(map[Hash]uint64, n)
        for _, v := range valSet.Validators() {
                stakes[v.Address] = v.StakeMicro
        }
        ledger := NewStakeLedger(DefaultSlashPolicy(), stakes)

        w := &testWorld{
                net:   &testNet{dropped: make(map[Hash]bool)},
                keys:  keys,
                valSet: valSet,
                ledger: ledger,
        }
        for _, k := range keys {
                me := addrOf(k)
                w.addrs = append(w.addrs, me)
                cfg := Config{
                        ChainID:           chainID,
                        Key:               k,
                        ProposeTimeout:    10 * time.Second,
                        PrevoteTimeout:    10 * time.Second,
                        PrecommitTimeout:  10 * time.Second,
                        Slasher:           ledger,
                        Logger:            silentLogger(),
                }
                if cfgFn != nil {
                        cfgFn(&cfg)
                }
                net := w.net
                cfg.Outbound = func(m ConsensusMessage) { net.enqueue(me, m) }
                chain := NewBlockchain(chainID)
                eng, err := NewEngine(cfg, valSet, chain, nil)
                if err != nil {
                        t.Fatalf("NewEngine: %v", err)
                }
                w.engines = append(w.engines, eng)
                w.net.engines = append(w.net.engines, eng) // the net fans out to every engine
                w.chains = append(w.chains, chain)
        }
        return w
}

// startAll starts every engine; startExcept starts all but the given indexes.
func (w *testWorld) startAll() {
        for _, e := range w.engines {
                e.Start()
        }
}

func (w *testWorld) startExcept(skip map[int]bool) {
        for i, e := range w.engines {
                if skip[i] {
                        continue
                }
                e.Start()
        }
}

func (w *testWorld) stopAll() {
        for _, e := range w.engines {
                e.Stop()
        }
}

// allAtHeight reports whether every (non-skipped) engine's chain tip is ≥ h.
func (w *testWorld) allAtHeight(h uint64, skip map[int]bool) bool {
        for i, e := range w.engines {
                if skip[i] {
                        continue
                }
                if e.ChainHeight() < h {
                        return false
                }
        }
        return true
}

// checkChainsEqual asserts all (non-skipped) engines share identical block
// hashes from genesis..maxH.
func (w *testWorld) checkChainsEqual(t *testing.T, skip map[int]bool, maxH uint64) {
        t.Helper()
        var ref []Hash
        for i, c := range w.chains {
                if skip[i] {
                        continue
                }
                var hs []Hash
                for h := uint64(0); h <= maxH; h++ {
                        b := c.BlockAt(h)
                        if b == nil {
                                t.Fatalf("engine %d: missing block at height %d", i, h)
                        }
                        hs = append(hs, b.Hash())
                }
                if ref == nil {
                        ref = hs
                        continue
                }
                for h := range hs {
                        if hs[h] != ref[h] {
                                t.Fatalf("chain divergence at height %d: engine %d has %s, reference %s",
                                        h, i, hs[h].Short(), ref[h].Short())
                        }
                }
        }
}

// testAttestation builds a validly dual-strand-signed attestation.
func testAttestation(entityID string, c float64, ts int64) p2p.BehavioralAttestation {
        payload := []byte(fmt.Sprintf("%s|%s|%.6f|%d", entityID, "BEHAVIORAL_COHERENCE", c, ts))
        sense, antisense := p2p.DualStrandSign(payload)
        return p2p.BehavioralAttestation{
                EntityID:           entityID,
                SignalType:         "BEHAVIORAL_COHERENCE",
                CoherenceC:         c,
                ThresholdTheta:     0.5,
                ValidatorID:         "trion-test-validator",
                DiversityWeight:    1.0,
                Timestamp:          ts,
                BlockNumber:        uint64(ts),
                SignatureSense:     sense,
                SignatureAntisense: antisense,
        }
}

// silentLogger swallows engine logs in tests (Config.Logger is *log.Logger).
func silentLogger() *log.Logger { return log.New(io.Discard, "", 0) }

// ─────────────────────────────────────────────────────────────────────────────
// §1  Happy path
// ─────────────────────────────────────────────────────────────────────────────

func TestHappyPath4ValidatorsCommitRound0(t *testing.T) {
        w := newTestNet(t, "happy", "trion-happy", 4, nil)
        defer w.stopAll()

        atts := []p2p.BehavioralAttestation{
                testAttestation("entity-alpha", 0.72, 1000),
                testAttestation("entity-beta", 0.81, 1001),
        }
        for _, e := range w.engines {
                for _, a := range atts {
                        e.SubmitAttestation(a)
                }
        }
        w.startAll()

        if !w.net.pumpUntil(func() bool { return w.allAtHeight(3, nil) }, 10*time.Second) {
                for i, e := range w.engines {
                        t.Fatalf("engine %d: chain height %d after 10s (want ≥3)", i, e.ChainHeight())
                }
        }

        // No faults, chain grew, all chains identical.
        for i, e := range w.engines {
                if err := e.Fault(); err != nil {
                        t.Fatalf("engine %d fault: %v", i, err)
                }
                if e.ChainHeight() < 3 {
                        t.Fatalf("engine %d: height %d < 3", i, e.ChainHeight())
                }
        }
        w.checkChainsEqual(t, nil, 3)

        // Block 1 committed in round 0 and carries both attestations.
        b1 := w.chains[0].BlockAt(1)
        if b1.Round != 0 {
                t.Fatalf("block 1 committed in round %d, want 0", b1.Round)
        }
        if len(b1.Txs) != 2 {
                t.Fatalf("block 1 carries %d txs, want 2", len(b1.Txs))
        }
        // Deterministic ordering: txs sorted by canonical hash ascending.
        if AttestationHash(&b1.Txs[0]).Hex() > AttestationHash(&b1.Txs[1]).Hex() {
                t.Fatalf("block 1 txs not in canonical hash order")
        }
        // Mempool drained on commit → later blocks are empty but still commit.
        for h := uint64(2); h <= 3; h++ {
                if b := w.chains[0].BlockAt(h); len(b.Txs) != 0 {
                        t.Fatalf("block %d unexpectedly carries %d txs after mempool drain", h, len(b.Txs))
                }
        }

        // Finalized-block notifications: ≥3, first is height 1, round 0, with a
        // >2/3 precommit justification.
        fbCount := 0
        var first FinalizedBlock
        for {
                select {
                case fb := <-w.engines[0].FinalizedBlocks():
                        fbCount++
                        if fbCount == 1 {
                                first = fb
                        }
                default:
                        goto drained
                }
        }
drained:
        if fbCount < 3 {
                t.Fatalf("got %d finalized notifications, want ≥3", fbCount)
        }
        if first.Block.Height != 1 || first.CommitRound != 0 {
                t.Fatalf("first finalized block: height %d round %d, want 1/0", first.Block.Height, first.CommitRound)
        }
        // 4/4 honest precommits in the justification.
        var power int64
        for i := range first.Precommits {
                if v := w.valSet.Get(first.Precommits[i].ValidatorAddress); v != nil {
                        power += v.Power
                }
        }
        if !hasQuorum(power, w.valSet.TotalPower()) {
                t.Fatalf("finalized justification power %d/%d is not >2/3", power, w.valSet.TotalPower())
        }
}

// ─────────────────────────────────────────────────────────────────────────────
// §2  Byzantine equivocator (1 of 4)
// ─────────────────────────────────────────────────────────────────────────────

func TestByzantineEquivocatorSlashedTombstonedChainStillCommits(t *testing.T) {
        w := newTestNet(t, "byz", "trion-byz", 4, nil)
        defer w.stopAll()

        // Pick a byzantine validator that is NOT the height-1 round-0 proposer
        // (so the honest round-0 proposal is produced and delivered).
        prop0 := w.valSet.GetProposer(1, 0).Address
        byzIdx := -1
        for i, a := range w.addrs {
                if a != prop0 {
                        byzIdx = i
                        break
                }
        }
        if byzIdx < 0 {
                t.Fatal("no candidate byzantine validator")
        }
        byzAddr := w.addrs[byzIdx]
        byzKey := w.keys[byzIdx]
        byz := map[int]bool{byzIdx: true}

        // The byzantine validator double-PRECOMMITS at (height 1, round 0) for
        // two different hashes. Both votes are correctly signed — the conflict
        // itself is the fault. Injected BEFORE the engines start, so the evidence
        // is pending when the height-1 block is assembled and gets committed in
        // block 1 itself.
        mkPrecommit := func(h Hash) *Vote {
                v := &Vote{
                        Type:             VoteTypePrecommit,
                        Height:           1,
                        Round:            0,
                        BlockHash:        h,
                        ValidatorAddress: byzAddr,
                }
                v.Signature = ed25519.Sign(byzKey, v.SignBytes())
                return v
        }
        hashX := Hash(meshsha3.Sum256([]byte("byz-value-X")))
        hashY := Hash(meshsha3.Sum256([]byte("byz-value-Y")))
        vx, vy := mkPrecommit(hashX), mkPrecommit(hashY)
        for _, e := range w.engines {
                e.HandleMessage(ConsensusMessage{Kind: MsgKindVote, Vote: vx})
                e.HandleMessage(ConsensusMessage{Kind: MsgKindVote, Vote: vy})
        }

        // Evidence recorded on every honest engine before consensus even starts.
        for i, e := range w.engines {
                if i == byzIdx {
                        continue
                }
                if got := e.Metrics().EvidenceDetected; got != 1 {
                        t.Fatalf("engine %d: EvidenceDetected=%d, want 1", i, got)
                }
        }
        // Slashed immediately on detection: 5% default policy.
        if w.ledger.SlashedTotal(byzAddr) == 0 {
                t.Fatal("byzantine validator not slashed on detection")
        }
        wantSlash := uint64(float64(w.ledger.InitialStake(byzAddr)) *
                float64(DefaultSlashPolicy().SlashFractionMicro) / 1_000_000)
        if got := w.ledger.SlashedTotal(byzAddr); got != wantSlash {
                t.Fatalf("slashed %d, want %d", got, wantSlash)
        }
        if !w.ledger.IsTombstoned(byzAddr) {
                t.Fatal("byzantine validator not tombstoned")
        }

        // Start the 3 honest engines only (the byzantine one is "down" — its
        // two precommits were its entire contribution to the round).
        w.startExcept(byz)

        // Chain STILL commits: heights 1 and 2 with the byzantine validator still
        // in the set (3/4 honest power > 2/3)…
        if !w.net.pumpUntil(func() bool { return w.allAtHeight(2, byz) }, 10*time.Second) {
                for i, e := range w.engines {
                        if i == byzIdx {
                                continue
                        }
                        t.Fatalf("engine %d: height %d after 10s (want ≥2)", i, e.ChainHeight())
                }
        }

        // Block 1 carries the committed evidence against the byzantine validator.
        b1 := w.chains[0].BlockAt(1)
        if len(b1.Evidence) != 1 {
                t.Fatalf("block 1 carries %d evidence entries, want 1", len(b1.Evidence))
        }
        if b1.Evidence[0].ValidatorAddress != byzAddr {
                t.Fatalf("evidence names %s, want the byzantine validator %s",
                        b1.Evidence[0].ValidatorAddress.Short(), byzAddr.Short())
        }

        // …and keeps committing AFTER the equivocator's power is removed at the
        // next height (3 honest validators, total power 3, quorum 3).
        if !w.net.pumpUntil(func() bool { return w.allAtHeight(4, byz) }, 10*time.Second) {
                for i, e := range w.engines {
                        if i == byzIdx {
                                continue
                        }
                        t.Fatalf("engine %d: height %d after 10s (want ≥4)", i, e.ChainHeight())
                }
        }
        for i, e := range w.engines {
                if i == byzIdx {
                        continue
                }
                if err := e.Fault(); err != nil {
                        t.Fatalf("engine %d fault: %v", i, err)
                }
        }
        // Chains converged at every height including across the validator-set
        // change (this also exercises the prevValSet refresh on unchanged
        // heights — a stale previous-set would reject block 3+ LastCommits).
        w.checkChainsEqual(t, byz, 4)

        // By height ≥3 the byzantine validator is out of the validator set.
        for i, e := range w.engines {
                if i == byzIdx {
                        continue
                }
                snap := e.ValidatorSetSnapshot()
                if len(snap) != 3 {
                        t.Fatalf("engine %d: validator set has %d members at height %d, want 3",
                                i, len(snap), e.Height())
                }
                for _, v := range snap {
                        if v.Address == byzAddr {
                                t.Fatalf("engine %d: byzantine validator still in set", i)
                        }
                }
        }

        // Slashing was applied exactly once (idempotent across detection,
        // gossip replay and block commit).
        if got := len(w.ledger.Events()); got != 1 {
                t.Fatalf("%d slash events recorded, want 1 (idempotency broken)", got)
        }
        if ev := w.ledger.Events()[0]; ev.TombstonedTo < 1+DefaultSlashPolicy().TombstoneBlocks {
                t.Fatalf("tombstoned-to %d, want ≥ %d", ev.TombstonedTo, 1+DefaultSlashPolicy().TombstoneBlocks)
        }
}

// ─────────────────────────────────────────────────────────────────────────────
// §3  Leader timeout → view change
// ─────────────────────────────────────────────────────────────────────────────

func TestLeaderTimeoutViewChangeCommitsRound1(t *testing.T) {
        w := newTestNet(t, "viewchange", "trion-viewchange", 4, func(cfg *Config) {
                cfg.ProposeTimeout = 20 * time.Millisecond
                cfg.PrevoteTimeout = 20 * time.Millisecond
                cfg.PrecommitTimeout = 20 * time.Millisecond
        })
        defer w.stopAll()

        // Partition the height-1 round-0 proposer: its messages are dropped, so
        // round 0 cannot progress and every engine must time out through
        // Propose → Prevote(nil) → Precommit(nil) → +2/3 precommit-nil → round 1.
        silenced := w.valSet.GetProposer(1, 0).Address
        if p1 := w.valSet.GetProposer(1, 1); p1.Address == silenced {
                t.Fatal("test seed produced the same proposer for rounds 0 and 1; change the seed")
        }
        w.net.dropped[silenced] = true

        w.startAll()

        if !w.net.pumpUntil(func() bool { return w.allAtHeight(2, nil) }, 15*time.Second) {
                for i, e := range w.engines {
                        t.Fatalf("engine %d: height %d after 15s (want ≥2)", i, e.ChainHeight())
                }
        }
        for i, e := range w.engines {
                if err := e.Fault(); err != nil {
                        t.Fatalf("engine %d fault: %v", i, err)
                }
        }

        // View change actually happened: block 1 was first proposed in round ≥1.
        b1 := w.chains[0].BlockAt(1)
        if b1.Round < 1 {
                t.Fatalf("block 1 committed from round %d, want ≥1 (no view change)", b1.Round)
        }
        // At least one engine moved through ≥2 rounds.
        roundsStarted := uint64(0)
        for _, e := range w.engines {
                if m := e.Metrics(); m.RoundsStarted > roundsStarted {
                        roundsStarted = m.RoundsStarted
                }
        }
        if roundsStarted < 2 {
                t.Fatalf("engines started only %d rounds total; view change did not fire", roundsStarted)
        }
        // Convergence across the partition.
        w.checkChainsEqual(t, nil, 2)

        // Timeout doubling sanity at the unit level (view-change backoff).
        if got := doublePerRound(20*time.Millisecond, 0, 10); got != 20*time.Millisecond {
                t.Fatalf("doublePerRound(r=0) = %v", got)
        }
        if got := doublePerRound(20*time.Millisecond, 1, 10); got != 40*time.Millisecond {
                t.Fatalf("doublePerRound(r=1) = %v", got)
        }
        if got := doublePerRound(20*time.Millisecond, 3, 10); got != 160*time.Millisecond {
                t.Fatalf("doublePerRound(r=3) = %v", got)
        }
        // Cap at MaxRoundShift.
        if got := doublePerRound(20*time.Millisecond, 40, 4); got != 320*time.Millisecond {
                t.Fatalf("doublePerRound(r=40, cap 4) = %v, want 320ms", got)
        }
}

// ─────────────────────────────────────────────────────────────────────────────
// §4  Proposer selection frequency follows power
// ─────────────────────────────────────────────────────────────────────────────

func TestProposerSelectionFrequencyMatchesPower(t *testing.T) {
        const nVals = 4
        // Effective powers 1:2:3:6 → selection shares 1/12, 2/12, 3/12, 6/12.
        powers := []int64{1, 2, 3, 6}
        keys := genKeys(t, "prop-stats", nVals)
        vals := make([]*Validator, nVals)
        for i, k := range keys {
                vals[i] = NewValidator(k, uint64(powers[i])*1_000_000, 1_000_000)
        }
        valSet, err := NewValidatorSet(vals)
        if err != nil {
                t.Fatalf("NewValidatorSet: %v", err)
        }

        // Fixed (height, round) enumeration = the "fixed seed". 10 000 samples.
        const heights = 40
        const rounds = 250
        counts := make(map[Hash]int)
        for h := uint64(1); h <= heights; h++ {
                for r := uint32(0); r < rounds; r++ {
                        p := valSet.GetProposer(h, r)
                        if p == nil {
                                t.Fatal("GetProposer returned nil")
                        }
                        counts[p.Address]++
                }
        }
        samples := heights * rounds
        if samples != 10_000 {
                t.Fatalf("sample count %d", samples)
        }
        total := valSet.TotalPower()
        for i, v := range valSet.Validators() {
                expected := float64(v.Power) / float64(total)
                observed := float64(counts[v.Address]) / float64(samples)
                // Binomial σ at p=0.5 over 10 000 samples ≈ 0.005; the 0.04 bound is
                // ~8σ for the largest share and ~25σ for the smallest — a hash-uniform
                // selection passes with overwhelming margin, a biased one fails.
                if math.Abs(observed-expected) > 0.04 {
                        t.Fatalf("validator %d (power %d/%d): observed selection frequency %.4f, expected %.4f",
                                i, v.Power, total, observed, expected)
                }
        }

        // Determinism: an identically-constructed set selects identically.
        valSet2, err := NewValidatorSet(vals)
        if err != nil {
                t.Fatalf("NewValidatorSet (2nd): %v", err)
        }
        for h := uint64(1); h <= 100; h++ {
                for r := uint32(0); r < 10; r++ {
                        if valSet.GetProposer(h, r).Address != valSet2.GetProposer(h, r).Address {
                                t.Fatalf("proposer selection not deterministic at h=%d r=%d", h, r)
                        }
                }
        }
}

// ─────────────────────────────────────────────────────────────────────────────
// §5  Deterministic replay
// ─────────────────────────────────────────────────────────────────────────────

func TestDeterministicReplaySameMessagesIdenticalHashes(t *testing.T) {
        atts := []p2p.BehavioralAttestation{
                testAttestation("entity-alpha", 0.72, 1000),
                testAttestation("entity-beta", 0.81, 1001),
                testAttestation("entity-gamma", 0.65, 1002),
        }

        run := func(chainID string) []Hash {
                w := newTestNet(t, "replay", chainID, 4, nil)
                defer w.stopAll()
                for _, e := range w.engines {
                        for _, a := range atts {
                                e.SubmitAttestation(a)
                        }
                }
                w.startAll()
                if !w.net.pumpUntil(func() bool { return w.allAtHeight(3, nil) }, 10*time.Second) {
                        t.Fatalf("run(chainID=%s): chain did not reach height 3", chainID)
                }
                for i, e := range w.engines {
                        if err := e.Fault(); err != nil {
                                t.Fatalf("run(chainID=%s) engine %d fault: %v", chainID, i, err)
                        }
                }
                // Every engine in the run must agree…
                w.checkChainsEqual(t, nil, 3)
                var hs []Hash
                for h := uint64(1); h <= 3; h++ {
                        hs = append(hs, w.chains[0].BlockAt(h).Hash())
                }
                return hs
        }

        hashesA := run("trion-replay")
        hashesB := run("trion-replay") // same seed, same chain ID → same everything
        if len(hashesA) != 3 || len(hashesB) != 3 {
                t.Fatalf("unexpected chain lengths %d/%d", len(hashesA), len(hashesB))
        }
        for h := range hashesA {
                if hashesA[h] != hashesB[h] {
                        t.Fatalf("replay divergence at block %d: %s vs %s",
                                h+1, hashesA[h].Short(), hashesB[h].Short())
                }
        }

        // A different chain ID changes the genesis, hence every descendant hash.
        hashesC := run("trion-replay-OTHER")
        for h := range hashesA {
                if hashesA[h] == hashesC[h] {
                        t.Fatalf("different chain ID produced identical block %d hash %s",
                                h+1, hashesA[h].Short())
                }
        }
}

// ─────────────────────────────────────────────────────────────────────────────
// §6  Exactly-2/3 precommit power does NOT commit
// ─────────────────────────────────────────────────────────────────────────────

func TestExactlyTwoThirdsPrecommitsDoNotCommit(t *testing.T) {
        // 3 validators with power 2 each (total 6): two of them hold exactly
        // 2/3 of the power — the boundary the strict rule must reject.
        const nVals = 3
        keys := genKeys(t, "twothirds", nVals)
        vals := make([]*Validator, nVals)
        for i, k := range keys {
                vals[i] = NewValidator(k, 2_000_000, 1_000_000)
        }
        valSet, err := NewValidatorSet(vals)
        if err != nil {
                t.Fatalf("NewValidatorSet: %v", err)
        }

        // Sanity: 4/6 is exactly 2/3 and must fail the quorum check; 5/6 passes.
        if hasQuorum(4, 6) {
                t.Fatal("hasQuorum(4,6) = true; exactly-2/3 must not be a quorum")
        }
        if !hasQuorum(5, 6) {
                t.Fatal("hasQuorum(5,6) = false")
        }

        engines := make([]*Engine, nVals)
        chains := make([]*Blockchain, nVals)
        for i, k := range keys {
                chains[i] = NewBlockchain("trion-twothirds")
                engines[i], err = NewEngine(Config{ChainID: "trion-twothirds", Key: k, Logger: silentLogger()},
                        valSet, chains[i], nil)
                if err != nil {
                        t.Fatalf("NewEngine: %v", err)
                }
        }
        defer func() {
                for _, e := range engines {
                        e.Stop()
                }
        }()

        // A valid height-1 round-0 proposal from the deterministic proposer.
        propIdx := -1
        propAddr := valSet.GetProposer(1, 0).Address
        for i, k := range keys {
                if addrOf(k) == propAddr {
                        propIdx = i
                        break
                }
        }
        if propIdx < 0 {
                t.Fatal("proposer key not found")
        }
        block := AssembleBlock(1, 0, chains[0].Tip(), 1000, propAddr, nil, nil, nil)
        prop := &Proposal{
                Height:      1,
                Round:       0,
                POLRound:    -1,
                BlockHash:   block.Hash(),
                Block:       block,
                TimestampMs: 1000,
                Proposer:    propAddr,
        }
        prop.Signature = ed25519.Sign(keys[propIdx], prop.SignBytes())
        for _, e := range engines {
                e.HandleMessage(ConsensusMessage{Kind: MsgKindProposal, Proposal: prop})
        }

        // Two of three validators (exactly 2/3 power) precommit the block.
        mkPrecommit := func(i int) *Vote {
                v := &Vote{
                        Type:             VoteTypePrecommit,
                        Height:           1,
                        Round:            0,
                        BlockHash:        block.Hash(),
                        ValidatorAddress: addrOf(keys[i]),
                }
                v.Signature = ed25519.Sign(keys[i], v.SignBytes())
                return v
        }
        for _, i := range []int{0, 1} { // the first two validators hold exactly 2/3 power
                v := mkPrecommit(i)
                for _, e := range engines {
                        e.HandleMessage(ConsensusMessage{Kind: MsgKindVote, Vote: v})
                }
        }

        // NOT committed: exactly-2/3 power is below the strict >2/3 threshold.
        time.Sleep(50 * time.Millisecond) // no timers are armed, but be explicit
        for i, e := range engines {
                if h := e.ChainHeight(); h != 0 {
                        t.Fatalf("engine %d committed height %d on exactly-2/3 power", i, h)
                }
                if e.Fault() != nil {
                        t.Fatalf("engine %d fault: %v", i, e.Fault())
                }
        }

        // The last validator's precommit lifts power to 6/6 → commit.
        v := mkPrecommit(2) // signers were 0 and 1
        for _, e := range engines {
                e.HandleMessage(ConsensusMessage{Kind: MsgKindVote, Vote: v})
        }
        for i, e := range engines {
                if h := e.ChainHeight(); h != 1 {
                        t.Fatalf("engine %d: height %d after full quorum, want 1", i, h)
                }
                if b := chains[i].BlockAt(1); b == nil || b.Hash() != block.Hash() {
                        t.Fatalf("engine %d: committed block does not match the proposal", i)
                }
        }
}

// ─────────────────────────────────────────────────────────────────────────────
// §7  Unit tests
// ─────────────────────────────────────────────────────────────────────────────

func TestHasQuorumStrictBoundaries(t *testing.T) {
        cases := []struct {
                power, total int64
                want         bool
        }{
                {0, 0, false},
                {0, 3, false},
                {1, 1, true},
                {1, 2, false}, // 3·1 = 3 is NOT > 2·2 = 4
                {2, 3, false}, // exactly 2/3
                {3, 4, true},  // 3/4 > 2/3
                {4, 6, false}, // exactly 2/3
                {5, 6, true},
                {6, 6, true},
                {66, 99, false}, // exactly 2/3
                {67, 99, true},
        }
        for _, c := range cases {
                if got := hasQuorum(c.power, c.total); got != c.want {
                        t.Errorf("hasQuorum(%d,%d) = %v, want %v", c.power, c.total, got, c.want)
                }
        }
}

func TestBlockHashDeterministicAndOrdered(t *testing.T) {
        key := genKeys(t, "blk", 1)[0]
        proposer := addrOf(key)
        txs := []p2p.BehavioralAttestation{
                testAttestation("e1", 0.5, 1),
                testAttestation("e2", 0.6, 2),
                testAttestation("e3", 0.7, 3),
        }
        lc := &CommitInfo{Height: 4, Round: 1, BlockHash: Hash(meshsha3.Sum256([]byte("p")))}
        // Two assemblies with the inputs in DIFFERENT order → identical block.
        b1 := AssembleBlock(5, 1, ZeroHash, 1234, proposer, txs, nil, lc)
        b2 := AssembleBlock(5, 1, ZeroHash, 1234, proposer,
                []p2p.BehavioralAttestation{txs[2], txs[0], txs[1]}, nil, lc)
        if b1.Hash() != b2.Hash() {
                t.Fatalf("same block content, different hashes: %s vs %s", b1.Hash().Short(), b2.Hash().Short())
        }
        if b1.AppHash != b1.ComputeAppHash() {
                t.Fatal("app-hash mismatch")
        }
        // Hash memoization returns the same value.
        if b1.Hash() != b1.Hash() {
                t.Fatal("hash not stable across calls")
        }
        // Any header change changes the hash.
        b3 := AssembleBlock(5, 1, ZeroHash, 1235, proposer, txs, nil, lc)
        if b3.Hash() == b1.Hash() {
                t.Fatal("timestamp change did not change the hash")
        }
        b4 := AssembleBlock(5, 2, ZeroHash, 1234, proposer, txs, nil, lc)
        if b4.Hash() == b1.Hash() {
                t.Fatal("round change did not change the hash")
        }
        b5 := AssembleBlock(6, 1, ZeroHash, 1234, proposer, txs, nil, lc)
        if b5.Hash() == b1.Hash() {
                t.Fatal("height change did not change the hash")
        }
        // LastCommit is NOT hash-covered (commit signature sets may differ
        // between correct nodes — see Block.Hash doc).
        b6 := AssembleBlock(5, 1, ZeroHash, 1234, proposer, txs, nil, nil)
        if b6.Hash() != b1.Hash() {
                t.Fatal("lastCommit presence changed the block hash (it must not)")
        }
        // Body change changes the hash.
        b7 := AssembleBlock(5, 1, ZeroHash, 1234, proposer, txs[:2], nil, lc)
        if b7.Hash() == b1.Hash() {
                t.Fatal("tx-set change did not change the hash")
        }
}

func TestEvidenceHashCanonicalUnderVoteSwap(t *testing.T) {
        key := genKeys(t, "ev", 1)[0]
        addr := addrOf(key)
        mk := func(h Hash) *Vote {
                v := &Vote{Type: VoteTypePrevote, Height: 3, Round: 1, BlockHash: h, ValidatorAddress: addr}
                v.Signature = ed25519.Sign(key, v.SignBytes())
                return v
        }
        ha := Hash(meshsha3.Sum256([]byte("A")))
        hb := Hash(meshsha3.Sum256([]byte("B")))
        va, vb := mk(ha), mk(hb)

        evAB, err := MakeEquivocationEvidence(va, vb)
        if err != nil {
                t.Fatalf("MakeEquivocationEvidence: %v", err)
        }
        evBA, err := MakeEquivocationEvidence(vb, va)
        if err != nil {
                t.Fatalf("MakeEquivocationEvidence (swapped): %v", err)
        }
        if evAB.Hash() != evBA.Hash() {
                t.Fatalf("evidence hash depends on vote order: %s vs %s", evAB.Hash().Short(), evBA.Hash().Short())
        }
        if !evAB.Conflict() || !evBA.Conflict() {
                t.Fatal("conflict detection failed")
        }
        if err := evAB.VerifySignatures(key.Public().(ed25519.PublicKey)); err != nil {
                t.Fatalf("VerifySignatures: %v", err)
        }
        // Non-conflicting pairs are rejected.
        if _, err := MakeEquivocationEvidence(va, mk(ha)); err == nil {
                t.Fatal("same-value pair accepted as equivocation")
        }
        // Tampered evidence fails verification.
        bad := *evAB
        bad.VoteA = mk(hb)
        if err := bad.VerifySignatures(key.Public().(ed25519.PublicKey)); err == nil {
                t.Fatal("tampered evidence verified")
        }
}

func TestMempoolDedupAndDeterministicOrder(t *testing.T) {
        m := NewMempool()
        atts := []p2p.BehavioralAttestation{
                testAttestation("e3", 0.3, 3),
                testAttestation("e1", 0.1, 1),
                testAttestation("e2", 0.2, 2),
        }
        for _, a := range atts {
                if _, added := m.Add(a); !added {
                        t.Fatal("first add reported duplicate")
                }
        }
        if _, added := m.Add(atts[1]); added {
                t.Fatal("duplicate add reported new")
        }
        if m.Size() != 3 {
                t.Fatalf("size %d, want 3", m.Size())
        }
        snap := m.Snapshot(10)
        if len(snap) != 3 {
                t.Fatalf("snapshot %d, want 3", len(snap))
        }
        for i := 1; i < len(snap); i++ {
                if AttestationHash(&snap[i-1]).Hex() > AttestationHash(&snap[i]).Hex() {
                        t.Fatal("snapshot not in hash-ascending order")
                }
        }
        // RemoveTxs drains committed txs only.
        m.RemoveTxs(atts[:1])
        if m.Size() != 2 {
                t.Fatalf("size after remove %d, want 2", m.Size())
        }
        snap2 := m.Snapshot(1)
        if len(snap2) != 1 || snap2[0].EntityID != snap[0].EntityID {
                t.Fatal("snapshot(1) did not respect deterministic order")
        }
}

func TestStakeLedgerIdempotentEnforcement(t *testing.T) {
        key := genKeys(t, "ledger", 1)[0]
        addr := addrOf(key)
        policy := SlashPolicy{SlashFractionMicro: 500_000, TombstoneBlocks: 100} // 50%
        ledger := NewStakeLedger(policy, map[Hash]uint64{addr: 1_000_000})

        mk := func(h Hash, height uint64) *Vote {
                v := &Vote{Type: VoteTypePrecommit, Height: height, Round: 0, BlockHash: h, ValidatorAddress: addr}
                v.Signature = ed25519.Sign(key, v.SignBytes())
                return v
        }
        ev, err := MakeEquivocationEvidence(
                mk(Hash(meshsha3.Sum256([]byte("x"))), 9),
                mk(Hash(meshsha3.Sum256([]byte("y"))), 9))
        if err != nil {
                t.Fatalf("MakeEquivocationEvidence: %v", err)
        }
        for i := 0; i < 3; i++ { // detection, gossip replay, block commit
                if err := ledger.Enforce(ev); err != nil {
                        t.Fatalf("Enforce #%d: %v", i, err)
                }
        }
        if got := len(ledger.Events()); got != 1 {
                t.Fatalf("%d slash events, want 1", got)
        }
        if got := ledger.Stake(addr); got != 500_000 {
                t.Fatalf("stake after 50%% slash = %d, want 500000", got)
        }
        if !ledger.IsTombstonedAt(addr, 108) || ledger.IsTombstonedAt(addr, 109) {
                t.Fatalf("tombstone window wrong: until %d", ledger.TombstonedUntil(addr))
        }
        // A second, different equivocation at a higher height extends the tombstone.
        ev2, err := MakeEquivocationEvidence(
                mk(Hash(meshsha3.Sum256([]byte("x2"))), 50),
                mk(Hash(meshsha3.Sum256([]byte("y2"))), 50))
        if err != nil {
                t.Fatalf("MakeEquivocationEvidence (2): %v", err)
        }
        if err := ledger.Enforce(ev2); err != nil {
                t.Fatalf("Enforce (2): %v", err)
        }
        if ledger.TombstonedUntil(addr) != 150 {
                t.Fatalf("tombstone until %d, want 150", ledger.TombstonedUntil(addr))
        }
        if !ledger.IsTombstonedAt(addr, 100) {
                t.Fatal("not tombstoned inside window")
        }
}

func TestVoteAndProposalSignatures(t *testing.T) {
        key := genKeys(t, "sig", 2)
        pub := key[0].Public().(ed25519.PublicKey)

        v := &Vote{Type: VoteTypePrevote, Height: 7, Round: 2, BlockHash: ZeroHash, ValidatorAddress: addrOf(key[0])}
        v.Signature = ed25519.Sign(key[0], v.SignBytes())
        if !v.Verify(pub) {
                t.Fatal("valid vote failed verification")
        }
        v2 := *v
        v2.BlockHash = Hash(meshsha3.Sum256([]byte("other")))
        if v2.Verify(pub) {
                t.Fatal("tampered vote verified")
        }
        // Cross-key verification fails.
        if v.Verify(key[1].Public().(ed25519.PublicKey)) {
                t.Fatal("vote verified against wrong key")
        }

        p := &Proposal{Height: 7, Round: 2, POLRound: -1, TimestampMs: 5, Proposer: addrOf(key[0])}
        p.Signature = ed25519.Sign(key[0], p.SignBytes())
        if !p.Verify(pub) {
                t.Fatal("valid proposal failed verification")
        }
        p2 := *p
        p2.POLRound = 1
        if p2.Verify(pub) {
                t.Fatal("tampered proposal verified")
        }
}

func TestValidatorSetOperations(t *testing.T) {
        keys := genKeys(t, "vset", 4)
        vals := make([]*Validator, 4)
        for i, k := range keys {
                vals[i] = NewValidator(k, 1_000_000, 1_000_000)
        }
        vs, err := NewValidatorSet(vals)
        if err != nil {
                t.Fatalf("NewValidatorSet: %v", err)
        }
        if vs.Size() != 4 || vs.TotalPower() != 4_000_000 {
                t.Fatalf("size/power = %d/%d", vs.Size(), vs.TotalPower())
        }
        // Duplicates rejected.
        if _, err := NewValidatorSet(append(append([]*Validator{}, vals...), vals[0])); err == nil {
                t.Fatal("duplicate address accepted")
        }
        // Zero power rejected (d_j = 0 → coordinated validator has no power).
        zero := NewValidator(genKeys(t, "vset0", 1)[0], 1_000_000, 0)
        if _, err := NewValidatorSet([]*Validator{zero}); err == nil {
                t.Fatal("zero power accepted")
        }
        // Empty set rejected.
        if _, err := NewValidatorSet(nil); err == nil {
                t.Fatal("empty set accepted")
        }
        // Without() removes power deterministically.
        drop := []Hash{vals[0].Address, vals[2].Address}
        next := vs.Without(drop)
        if next == nil || next.Size() != 2 {
                t.Fatalf("Without left %d validators", next.Size())
        }
        if next.Contains(vals[0].Address) || next.Contains(vals[2].Address) {
                t.Fatal("Without did not remove the requested validators")
        }
        if next.TotalPower() != 2_000_000 {
                t.Fatalf("power after removal %d", next.TotalPower())
        }
        if vs.Without([]Hash{vals[0].Address, vals[1].Address, vals[2].Address, vals[3].Address}) != nil {
                t.Fatal("removing everyone must yield nil")
        }
}

func TestNewValidatorSetFromP2PDiversityWeighting(t *testing.T) {
        keys := genKeys(t, "vsetp2p", 3)
        infos := []p2p.ValidatorInfo{
                {ID: "v0", Stake: 1.0},
                {ID: "v1", Stake: 1.0},
                {ID: "v2", Stake: 1.0},
        }
        keyMap := map[string]ed25519.PrivateKey{"v0": keys[0], "v1": keys[1], "v2": keys[2]}

        // Decorrelated model outputs → corr ≈ 0 → d ≈ 1 → full power.
        models := map[string][]float64{
                "v0": {1, 0, 1, 0},
                "v1": {0, 1, 0, 1},
                "v2": {1, 1, 0, 0},
        }
        median := []float64{0.5, 0.5, 0.5, 0.5}
        vs, err := NewValidatorSetFromP2P(infos, keyMap, models, median)
        if err != nil {
                t.Fatalf("NewValidatorSetFromP2P: %v", err)
        }
        for _, v := range vs.Validators() {
                if v.Power < 900_000 {
                        t.Fatalf("validator %s: decorrelated power %d, want ~1_000_000", v.Address.Short(), v.Power)
                }
        }

        // Perfectly coordinated outputs (each validator's series has
        // correlation 1 with the median series) → d = 1 − corr = 0 → zero
        // effective power → set construction fails. (A constant series has
        // zero variance — p2p.ComputeDiversityWeight deliberately returns
        // d=1.0 for that degenerate case, so the series must vary.)
        models = map[string][]float64{
                "v0": {1, 2, 1, 2},
                "v1": {1, 2, 1, 2},
                "v2": {1, 2, 1, 2},
        }
        median = []float64{1, 2, 1, 2}
        if _, err := NewValidatorSetFromP2P(infos, keyMap, models, median); err == nil {
                t.Fatal("coordinated validators (d=0) were given voting power")
        }

        // Negative stake is rejected.
        badInfos := []p2p.ValidatorInfo{{ID: "v0", Stake: -1}}
        if _, err := NewValidatorSetFromP2P(badInfos, keyMap, models, median); err == nil {
                t.Fatal("negative stake accepted")
        }
}

func TestConsensusMessageJSONRoundTrip(t *testing.T) {
        // The mesh wire format is JSON; every consensus object must survive a
        // marshal/unmarshal round-trip with hashes intact (Hash ↔ hex).
        key := genKeys(t, "json", 1)[0]
        addr := addrOf(key)
        blk := AssembleBlock(2, 1, ZeroHash, 42, addr,
                []p2p.BehavioralAttestation{testAttestation("e1", 0.5, 1)}, nil, nil)
        prop := &Proposal{
                Height: 2, Round: 1, POLRound: -1,
                BlockHash: blk.Hash(), Block: blk, TimestampMs: 42, Proposer: addr,
        }
        prop.Signature = ed25519.Sign(key, prop.SignBytes())
        vote := &Vote{Type: VoteTypePrecommit, Height: 2, Round: 1, BlockHash: blk.Hash(), ValidatorAddress: addr}
        vote.Signature = ed25519.Sign(key, vote.SignBytes())

        for _, m := range []ConsensusMessage{
                {Kind: MsgKindProposal, Proposal: prop},
                {Kind: MsgKindVote, Vote: vote},
        } {
                data, err := json.Marshal(m)
                if err != nil {
                        t.Fatalf("marshal: %v", err)
                }
                var back ConsensusMessage
                if err := json.Unmarshal(data, &back); err != nil {
                        t.Fatalf("unmarshal: %v", err)
                }
                switch m.Kind {
                case MsgKindProposal:
                        if back.Proposal == nil || back.Proposal.BlockHash != prop.BlockHash ||
                                back.Proposal.Block.Hash() != prop.BlockHash {
                                t.Fatal("proposal round-trip lost the block hash")
                        }
                        if !back.Proposal.Verify(key.Public().(ed25519.PublicKey)) {
                                t.Fatal("proposal signature broke in round-trip")
                        }
                case MsgKindVote:
                        if back.Vote == nil || back.Vote.BlockHash != vote.BlockHash ||
                                !back.Vote.Verify(key.Public().(ed25519.PublicKey)) {
                                t.Fatal("vote round-trip corrupted hash or signature")
                        }
                }
        }

        // Hash text encoding: compact hex, and the empty string decodes as zero.
        h := blk.Hash()
        text, err := h.MarshalText()
        if err != nil {
                t.Fatalf("MarshalText: %v", err)
        }
        if len(text) != 64 || strings.Contains(string(text), " ") {
                t.Fatalf("hash text encoding %q", string(text))
        }
        var z Hash
        if err := z.UnmarshalText(nil); err != nil || !z.IsZero() {
                t.Fatal("empty text must decode to the zero hash")
        }
        var bad Hash
        if err := bad.UnmarshalText([]byte("zz")); err == nil {
                t.Fatal("short hex accepted")
        }
}
