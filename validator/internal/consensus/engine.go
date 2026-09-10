// TRION Protocol — DW-BFT consensus engine (Tendermint-family state machine).
//
// This is the security-critical core. The rules follow the Tendermint
// algorithm ("The Latest Gossip on BFT Consensus") with TRION's
// diversity-weighted effective power. Quorum arithmetic is integer-only and
// STRICT: a quorum requires strictly MORE than 2/3 of the total voting power
// (3·power > 2·total) — exactly 2/3 is not enough, by design (see the
// engine tests). Note the mesh's legacy attestation-layer quorum (≥ 2/3,
// floats) is a different, older layer and is untouched.
//
// State machine (per height H, round R):
//
//      NewHeight → Propose → Prevote → Precommit → Commit → NewHeight…
//
// Rules implemented (Tendermint semantics):
//
//   startRound(R): if we are the proposer for (H,R), broadcast
//   Proposal(value, POLRound) where value is the valid value if we saw a
//   polka, else the locked value, else a fresh block from the mempool.
//   Non-proposers arm ProposeTimeout(R) (doubling per round).
//
//   Propose step: on a valid proposal → Prevote. On ProposeTimeout →
//   Prevote(nil).
//
//   Prevote rule: prevote the proposal iff it is valid AND justified:
//   (lockedRound ≤ POLRound) OR (locked value == proposal). A proposal with
//   POLRound ≥ 0 additionally requires that we have SEEN the polka it cites
//   (2/3 prevotes for that hash at POLRound). Otherwise prevote nil.
//
//   On witnessing 2/3+ prevotes for value v at round R (a polka):
//   record valid(v, R). If we are in Prevote at round R: LOCK v
//   (lock-on-precommit — the lock is taken exactly when we precommit after
//   seeing the polka) and broadcast Precommit(v).
//   A polka for a different value in a LATER round than our lock is the only
//   "unlock" path: it replaces the lock (via the valid tracker and the
//   lockedRound ≤ POLRound prevote rule).
//
//   On 2/3+ prevotes for nil at the current round while in Prevote:
//   broadcast Precommit(nil). DELIBERATELY no unlock here: unlocking on a
//   nil polka lets an adversary with f → 1/3 flip exactly-2/3 honest quorums
//   into signing conflicting values at the same height (the 2/3 prevote-nil
//   quorum can be formed by the very validators that are locked, and after
//   unlocking they can prevote a fresh conflicting proposal; byzantine
//   precommits from the earlier round then form a second, conflicting commit
//   proof). The Tendermint paper and CometBFT have no unlock-on-nil for the
//   same reason. Liveness is preserved because locked validators keep
//   prevoting nil on conflicting fresh proposals until an honest proposer
//   re-proposes the locked value, which they prevote and commit.
//
//   On 2/3+ precommits for v (ANY round of the current height, ANY step):
//   COMMIT v — apply the block, append to the chain, publish, move to the
//   next height.
//
//   On 2/3+ precommits for nil at the current round while in Precommit, or
//   PrecommitTimeout(R): startRound(R+1) — view change.
//
// Leader election: deterministic weighted selection seeded by
// (validator-set hash, height, round) over effective power s_j·d_j — see
// ValidatorSet.GetProposer.
//
// Author: TRION Protocol — Originator: Hudu Yusuf (Analys)
// License: CC0
package consensus

import (
        "crypto/ed25519"
        "encoding/binary"
        "errors"
        "fmt"
        "log"
        "math"
        "sort"
        "sync"
        "time"

        "github.com/trion-protocol/validator/internal/p2p"
        "github.com/trion-protocol/validator/internal/p2p/meshsha3"
)

// MicroUnit is the fixed-point scale for power, stake and diversity factors.
const MicroUnit int64 = 1_000_000

// hasQuorum implements the STRICT >2/3 commit/polka rule in integer
// arithmetic: 3·power > 2·total. With power == 2/3·total exactly
// (e.g. 2 of 3 equal validators) this returns false.
func hasQuorum(power, total int64) bool {
        return total > 0 && 3*power > 2*total
}

// ── Validator set and leader election ──────────────────────────────────────

// Validator is one consensus participant. Power is the EFFECTIVE voting
// power s_j·d_j (stake times diversity factor), in micro units.
type Validator struct {
        Address        Hash              // SHA3-256(pubkey) — 32-byte identity
        PubKey         ed25519.PublicKey
        Power          int64             // s_j·d_j, micro units
        StakeMicro     uint64            // s_j
        DiversityMicro int64             // d_j, micro units
}

// NewValidator derives the validator identity from an ed25519 private key:
// address = SHA3-256(public key), matching the mesh's "32-byte identity
// derived from SHA3-256 of public key" convention.
func NewValidator(key ed25519.PrivateKey, stakeMicro uint64, diversityMicro int64) *Validator {
        pub := key.Public().(ed25519.PublicKey)
        addr := meshsha3.Sum256(pub)
        // Guard against int64 overflow in stake × diversity: saturate instead
        // of wrapping (a wrapped negative power would be rejected by
        // NewValidatorSet, but a wrapped positive one would silently corrupt
        // quorum arithmetic).
        power := int64(math.MaxInt64)
        if stakeMicro <= uint64(math.MaxInt64)/uint64(MicroUnit) {
                power = int64(stakeMicro) * diversityMicro / MicroUnit
        }
        if power < 0 {
                power = 0
        }
        return &Validator{
                Address:        addr,
                PubKey:         pub,
                Power:          power,
                StakeMicro:     stakeMicro,
                DiversityMicro: diversityMicro,
        }
}

// ValidatorSet is the (static per height) consensus validator set, sorted by
// address for deterministic iteration.
type ValidatorSet struct {
        vals    []*Validator // sorted by Address ascending
        cum     []int64      // cumulative power prefix sums
        total   int64
        setHash Hash
}

// NewValidatorSet builds a validator set. It rejects empty sets, zero total
// power, duplicate addresses and non-positive powers.
func NewValidatorSet(vals []*Validator) (*ValidatorSet, error) {
        if len(vals) == 0 {
                return nil, errors.New("validator set: empty")
        }
        sorted := make([]*Validator, len(vals))
        copy(sorted, vals)
        sort.Slice(sorted, func(i, j int) bool {
                return sorted[i].Address.Hex() < sorted[j].Address.Hex()
        })
        vs := &ValidatorSet{
                vals: sorted,
                cum:  make([]int64, len(sorted)),
        }
        seed := make([]byte, 0, 12+64*len(sorted))
        seed = append(seed, "TRION-VSET"...)
        var prev Hash
        for i, v := range sorted {
                if i > 0 && v.Address == prev {
                        return nil, fmt.Errorf("validator set: duplicate address %s", v.Address.Short())
                }
                prev = v.Address
                if v.Power <= 0 {
                        return nil, fmt.Errorf("validator set: non-positive power for %s", v.Address.Short())
                }
                if len(v.PubKey) != ed25519.PublicKeySize {
                        return nil, fmt.Errorf("validator set: bad pubkey size for %s", v.Address.Short())
                }
                vs.total += v.Power
                vs.cum[i] = vs.total
                seed = appendHash(seed, v.Address)
                seed = appendInt64(seed, v.Power)
        }
        vs.setHash = meshsha3.Sum256(seed)
        return vs, nil
}

// NewValidatorSetFromP2P builds a validator set from p2p.ValidatorInfo
// records plus ed25519 keys, REUSING the p2p package's diversity
// computation: d_j = p2p.ComputeDiversityWeight(modelOutputs_j, medianOutputs)
// (whitepaper L4.1-4.2, d_j = 1 − corr(M_j, M̄)). Effective power is then
// s_j·d_j. modelOutputs is keyed by ValidatorInfo.ID.
func NewValidatorSetFromP2P(
        infos []p2p.ValidatorInfo,
        keys map[string]ed25519.PrivateKey,
        modelOutputs map[string][]float64,
        medianOutputs []float64,
) (*ValidatorSet, error) {
        vals := make([]*Validator, 0, len(infos))
        for i := range infos {
                info := infos[i]
                key, ok := keys[info.ID]
                if !ok {
                        return nil, fmt.Errorf("no key for validator %q", info.ID)
                }
                if info.Stake < 0 || math.IsNaN(info.Stake) || math.IsInf(info.Stake, 0) {
                        return nil, fmt.Errorf("invalid stake %v for validator %q", info.Stake, info.ID)
                }
                dj := p2p.ComputeDiversityWeight(modelOutputs[info.ID], medianOutputs)
                stakeMicro := uint64(info.Stake * float64(MicroUnit))
                divMicro := int64(dj * float64(MicroUnit))
                vals = append(vals, NewValidator(key, stakeMicro, divMicro))
        }
        return NewValidatorSet(vals)
}

// Get returns the validator with the given address, or nil.
func (vs *ValidatorSet) Get(addr Hash) *Validator {
        i := sort.Search(len(vs.vals), func(i int) bool {
                return vs.vals[i].Address.Hex() >= addr.Hex()
        })
        if i < len(vs.vals) && vs.vals[i].Address == addr {
                return vs.vals[i]
        }
        return nil
}

// Contains reports whether addr is in the set.
func (vs *ValidatorSet) Contains(addr Hash) bool { return vs.Get(addr) != nil }

// TotalPower returns the summed effective power (micro units).
func (vs *ValidatorSet) TotalPower() int64 { return vs.total }

// Size returns the number of validators.
func (vs *ValidatorSet) Size() int { return len(vs.vals) }

// Validators returns a copy of the (address-sorted) validator slice.
func (vs *ValidatorSet) Validators() []*Validator {
        out := make([]*Validator, len(vs.vals))
        copy(out, vs.vals)
        return out
}

// Without returns a copy of the set with the given addresses removed. Used
// for slashing-driven power removal; returns the same set if nothing matches.
// Returns nil if everything would be removed (caller treats as fatal).
func (vs *ValidatorSet) Without(addrs []Hash) *ValidatorSet {
        drop := make(map[Hash]bool, len(addrs))
        for _, a := range addrs {
                drop[a] = true
        }
        vals := make([]*Validator, 0, len(vs.vals))
        for _, v := range vs.vals {
                if !drop[v.Address] {
                        vals = append(vals, v)
                }
        }
        if len(vals) == 0 {
                return nil
        }
        next, err := NewValidatorSet(vals)
        if err != nil {
                return nil
        }
        return next
}

// GetProposer deterministically selects the round leader from
// (validator-set hash, height, round). Selection is weighted by effective
// power: the SHA3-256 seed is mapped into [0, TotalPower) and resolved
// through the cumulative-power table, so over many rounds each validator is
// selected with frequency proportional to s_j·d_j. Safety does not depend on
// the rotation schedule (Tendermint safety holds for any proposer schedule);
// liveness needs honest proposers to come up, which proportional weighting
// gives. This is a deviation from incremental weighted round-robin: it is a
// pure function of (set, height, round) — replayable and stat-testable — at
// the cost of occasionally repeating a proposer in consecutive rounds.
// Modulo bias is ≤ total/2^64 — negligible at micro-unit scale.
func (vs *ValidatorSet) GetProposer(height uint64, round uint32) *Validator {
        if len(vs.vals) == 0 || vs.total <= 0 {
                return nil
        }
        seed := make([]byte, 0, 10+32+8+4)
        seed = append(seed, "TRION-PROP"...)
        seed = appendHash(seed, vs.setHash)
        seed = appendUint64(seed, height)
        seed = appendUint32(seed, round)
        h := meshsha3.Sum256(seed)
        x := binary.BigEndian.Uint64(h[0:8]) % uint64(vs.total)
        i := sort.Search(len(vs.cum), func(i int) bool {
                return vs.cum[i] > int64(x)
        })
        if i >= len(vs.vals) {
                i = len(vs.vals) - 1
        }
        return vs.vals[i]
}

// ── Engine configuration ────────────────────────────────────────────────────

// Config configures an Engine. Zero-value fields get defaults.
type Config struct {
        ChainID string

        // Key is this node's ed25519 validator key (required). Its derived
        // address must be in the validator set.
        Key ed25519.PrivateKey

        // Timeout bases; each doubles every round (capped at 2^MaxRoundShift).
        // Defaults follow Tendermint: 3s propose, 1s prevote, 1s precommit.
        ProposeTimeout    time.Duration
        PrevoteTimeout    time.Duration
        PrecommitTimeout  time.Duration
        MaxRoundShift     uint // exponent cap for per-round doubling (default 10)

        MaxBlockTxs        int // max attestations per block (default 100)
        MaxEvidencePerBlock int // max evidence entries per block (default 16)

        // Clock, if non-nil, supplies wall-clock time for proposal/block
        // timestamps (bounded to be monotonic: max(now, parent+1ms)). If nil the
        // engine is fully deterministic: timestamps derive from the parent
        // block (+1000ms per height), which is what makes deterministic replay
        // (same messages → same blocks) possible without a clock oracle.
        Clock func() time.Time

        // Slasher receives verified equivocation evidence. May be nil (evidence
        // is still detected, gossiped and committed in blocks).
        Slasher SlashingEnforcer

        // Outbound receives every message the engine emits (proposals, votes,
        // evidence, finalized-block announcements). Called without the engine
        // lock held. May be nil (e.g. single-process tests).
        Outbound func(ConsensusMessage)

        // Logger: if nil, the standard library logger is used.
        Logger *log.Logger
}

func (c *Config) setDefaults() {
        if c.ProposeTimeout <= 0 {
                c.ProposeTimeout = 3000 * time.Millisecond
        }
        if c.PrevoteTimeout <= 0 {
                c.PrevoteTimeout = 1000 * time.Millisecond
        }
        if c.PrecommitTimeout <= 0 {
                c.PrecommitTimeout = 1000 * time.Millisecond
        }
        if c.MaxRoundShift > 20 {
                c.MaxRoundShift = 20
        }
        if c.MaxRoundShift == 0 {
                c.MaxRoundShift = 10
        }
        if c.MaxBlockTxs <= 0 {
                c.MaxBlockTxs = 100
        }
        if c.MaxEvidencePerBlock <= 0 {
                c.MaxEvidencePerBlock = 16
        }
}

// Metrics is a snapshot of engine counters (observability).
type Metrics struct {
        VotesProcessed     uint64 `json:"votes_processed"`
        VotesDropped       uint64 `json:"votes_dropped"`
        ProposalsProcessed uint64 `json:"proposals_processed"`
        ProposalsDropped   uint64 `json:"proposals_dropped"`
        EvidenceDetected   uint64 `json:"evidence_detected"`
        RoundsStarted      uint64 `json:"rounds_started"`
        HeightsCommitted   uint64 `json:"heights_committed"`
        FinalizedDropped   uint64 `json:"finalized_dropped"`
}

// ── Engine internals ────────────────────────────────────────────────────────

type voteKey struct {
        addr Hash
        typ  VoteType
}

// roundVotes tallies all votes of the current height for one round.
type roundVotes struct {
        byKey        map[voteKey]*Vote // first vote per (validator, type)
        prevoteFor   map[Hash]int64    // tallied prevote power per block hash (incl. nil)
        precommitFor map[Hash]int64    // tallied precommit power per block hash (incl. nil)
        precommitVotes map[Hash][]*Vote // first precommits per hash (for LastCommit)
}

func newRoundVotes() *roundVotes {
        return &roundVotes{
                byKey:          make(map[voteKey]*Vote),
                prevoteFor:     make(map[Hash]int64),
                precommitFor:   make(map[Hash]int64),
                precommitVotes: make(map[Hash][]*Vote),
        }
}

type timeoutKind uint8

const (
        timeoutPropose timeoutKind = iota + 1
        timeoutPrevote
        timeoutPrecommit
)

type engineEvent interface{}

type startEvent struct{}
type attestationEvent struct{ att p2p.BehavioralAttestation }
type proposalEvent struct{ p *Proposal }
type voteEvent struct{ v *Vote }
type evidenceEvent struct {
        ev      *EquivocationEvidence
        verify  bool // verify signatures (remote evidence)
}
type timeoutEvent struct {
        kind   timeoutKind
        height uint64
        round  uint32
}

type pendingCommit struct {
        round uint32
        hash  Hash
}

// Engine is one validator's TRION-BFT consensus state machine.
//
// Concurrency model: a single mutex guards all state. Public entry points
// push an event onto a queue and drain it under the lock (no recursion:
// self-votes are queued, not processed inline — this also bounds the event
// cascade and prevents deadlocks between engines). Messages to emit are
// buffered and flushed AFTER the lock is released, so Outbound may safely
// call other engines (including back into this one).
type Engine struct {
        mu   sync.Mutex
        cfg  Config
        priv ed25519.PrivateKey
        me   Hash

        valSet     *ValidatorSet
        prevValSet *ValidatorSet // set governing the previous height (LastCommit validation)
        knownKeys  map[Hash]ed25519.PublicKey // every validator ever seen (evidence verification)

        chain   *Blockchain
        mempool *Mempool

        height uint64
        round  uint32
        step   Step

        proposals map[uint32]*Proposal  // first valid proposal per round (this height)
        blocks    map[Hash]*Block       // all valid proposed blocks (this height)
        rounds    map[uint32]*roundVotes // all vote tallies (this height)

        // One-height lookahead: a faster peer's messages for height+1 are
        // buffered (bounded) and replayed when we enter that height. Without
        // this, a node still finishing height h would permanently drop the
        // h+1 proposal/votes (there is no peer catch-up reactor yet — see
        // README). Messages for heights beyond +1 are dropped.
        futureProps map[uint64][]*Proposal
        futureVotes map[uint64][]*Vote

        lockedBlock *Block
        lockedRound int32
        lockedHash  Hash
        validBlock  *Block
        validRound  int32

        lastCommit    *CommitInfo
        pendingCommit *pendingCommit

        pendingEvidence    []*EquivocationEvidence
        evidenceSeen       map[Hash]bool
        removeNextHeight   map[Hash]bool

        queue    []engineEvent
        outbound []ConsensusMessage

        timer   *time.Timer
        stopped bool
        fault   error

        finalized chan FinalizedBlock
        metrics   Metrics
}

// NewEngine creates an engine. The engine's identity (SHA3 of the key's
// public half) must be in valSet. chain must be a fresh chain for this
// network; mempool may be nil (an empty one is created).
func NewEngine(cfg Config, valSet *ValidatorSet, chain *Blockchain, mempool *Mempool) (*Engine, error) {
        if len(cfg.Key) != ed25519.PrivateKeySize {
                return nil, errors.New("consensus: ed25519 private key required")
        }
        if valSet == nil || valSet.TotalPower() <= 0 {
                return nil, errors.New("consensus: invalid validator set")
        }
        if chain == nil {
                return nil, errors.New("consensus: chain required")
        }
        if mempool == nil {
                mempool = NewMempool()
        }
        cfg.setDefaults()
        pub := cfg.Key.Public().(ed25519.PublicKey)
        me := Hash(meshsha3.Sum256(pub))
        if !valSet.Contains(me) {
                return nil, fmt.Errorf("consensus: self %s not in validator set", me.Short())
        }
        known := make(map[Hash]ed25519.PublicKey, valSet.Size())
        for _, v := range valSet.Validators() {
                known[v.Address] = v.PubKey
        }
        e := &Engine{
                cfg:         cfg,
                priv:        cfg.Key,
                me:          me,
                valSet:      valSet,
                prevValSet:  valSet,
                knownKeys:   known,
                chain:       chain,
                mempool:     mempool,
                height:      chain.Height() + 1,
                round:       0,
                step:        StepNewHeight,
                proposals:   make(map[uint32]*Proposal),
                blocks:      make(map[Hash]*Block),
                rounds:      make(map[uint32]*roundVotes),
                futureProps: make(map[uint64][]*Proposal),
                futureVotes: make(map[uint64][]*Vote),
                lockedRound: -1,
                validRound:  -1,
                evidenceSeen: make(map[Hash]bool),
                removeNextHeight: make(map[Hash]bool),
                finalized:   make(chan FinalizedBlock, 64),
        }
        return e, nil
}

// Start begins consensus at the next height.
func (e *Engine) Start() { e.submit(startEvent{}) }

// Stop halts the engine (timers cancelled; further events ignored).
func (e *Engine) Stop() {
        e.mu.Lock()
        e.stopped = true
        if e.timer != nil {
                e.timer.Stop()
                e.timer = nil
        }
        e.mu.Unlock()
}

// SubmitAttestation queues a behavioral attestation into the mempool.
func (e *Engine) SubmitAttestation(att p2p.BehavioralAttestation) {
        e.submit(attestationEvent{att: att})
}

// HandleMessage ingests one gossiped consensus message.
func (e *Engine) HandleMessage(m ConsensusMessage) {
        switch m.Kind {
        case MsgKindProposal:
                if m.Proposal != nil {
                        e.submit(proposalEvent{p: m.Proposal})
                }
        case MsgKindVote:
                if m.Vote != nil {
                        e.submit(voteEvent{v: m.Vote})
                }
        case MsgKindEvidence:
                if m.Evidence != nil {
                        e.submit(evidenceEvent{ev: m.Evidence, verify: true})
                }
        case MsgKindFinalizedBlock:
                // Observability only: receiving an announce does not commit a block
                // locally. Catch-up sync from announces is a TODO (README).
                e.metrics.VotesDropped++ // counted as ignored inbound
        default:
                // unknown kind: ignore
        }
}

// FinalizedBlocks returns the channel of committed blocks. The channel is
// buffered; if the consumer is slow, announcements are dropped (counted in
// Metrics.FinalizedDropped) — blocks remain in the chain regardless.
func (e *Engine) FinalizedBlocks() <-chan FinalizedBlock { return e.finalized }

// Height returns the current (in-progress) height.
func (e *Engine) Height() uint64 { e.mu.Lock(); defer e.mu.Unlock(); return e.height }

// Round returns the current round.
func (e *Engine) Round() uint32 { e.mu.Lock(); defer e.mu.Unlock(); return e.round }

// Step returns the current step.
func (e *Engine) Step() Step { e.mu.Lock(); defer e.mu.Unlock(); return e.step }

// LockedRound returns the locked round (-1 if unlocked).
func (e *Engine) LockedRound() int32 { e.mu.Lock(); defer e.mu.Unlock(); return e.lockedRound }

// ValidRound returns the valid-round tracker value (-1 if none).
func (e *Engine) ValidRound() int32 { e.mu.Lock(); defer e.mu.Unlock(); return e.validRound }

// Metrics returns a counters snapshot.
func (e *Engine) Metrics() Metrics { e.mu.Lock(); defer e.mu.Unlock(); return e.metrics }

// Fault returns the engine fault, if any (e.g. chain append failure or event
// loop runaway).
func (e *Engine) Fault() error { e.mu.Lock(); defer e.mu.Unlock(); return e.fault }

// ValidatorSetSnapshot returns a copy of the current validator set records.
func (e *Engine) ValidatorSetSnapshot() []*Validator {
        e.mu.Lock()
        defer e.mu.Unlock()
        return e.valSet.Validators()
}

// ChainHeight returns the committed chain height (tip).
func (e *Engine) ChainHeight() uint64 { return e.chain.Height() }

// ── Event loop ──────────────────────────────────────────────────────────────

// submit queues an event, drains the queue under the lock, then flushes
// outbound messages with the lock released.
func (e *Engine) submit(ev engineEvent) {
        e.mu.Lock()
        if e.stopped {
                e.mu.Unlock()
                return
        }
        e.queue = append(e.queue, ev)
        e.drain()
        out := e.outbound
        e.outbound = nil
        e.mu.Unlock()
        for _, m := range out {
                if e.cfg.Outbound != nil {
                        e.cfg.Outbound(m)
                }
        }
}

// drain processes queued events until the queue is empty (lock held).
func (e *Engine) drain() {
        for n := 0; len(e.queue) > 0; n++ {
                if n > 1_000_000 {
                        e.fault = errors.New("consensus: event loop runaway guard tripped")
                        e.queue = nil
                        return
                }
                ev := e.queue[0]
                e.queue = e.queue[1:]
                e.apply(ev)
        }
}

func (e *Engine) apply(ev engineEvent) {
        switch ev := ev.(type) {
        case startEvent:
                e.enterNewHeight()
        case attestationEvent:
                e.mempool.Add(ev.att)
        case timeoutEvent:
                e.applyTimeout(ev)
        case proposalEvent:
                e.applyProposal(ev.p)
        case voteEvent:
                e.applyVote(ev.v)
        case evidenceEvent:
                e.applyEvidence(ev.ev, ev.verify)
        }
}

func (e *Engine) applyTimeout(ev timeoutEvent) {
        if ev.height != e.height || ev.round != e.round {
                return // stale timer
        }
        switch ev.kind {
        case timeoutPropose:
                if e.step == StepPropose {
                        e.enterPrevote()
                }
        case timeoutPrevote:
                if e.step == StepPrevote {
                        e.enterPrecommit(ZeroHash)
                }
        case timeoutPrecommit:
                if e.step == StepPrecommit {
                        e.startRound(e.round + 1)
                }
        }
}

// ── Height / round transitions ──────────────────────────────────────────────

// enterNewHeight moves to the next height: applies deterministic
// validator-set changes (power removal for tombstoned validators whose
// evidence committed), resets per-height state and starts round 0.
func (e *Engine) enterNewHeight() {
        // The set that governed the height we just finished becomes the
        // "previous" set: LastCommit inside blocks at the NEW height justifies
        // the previous height's block, whose commit quorum was formed by the
        // previous height's validators. This MUST be refreshed on EVERY height
        // transition, not only when the set changes: after a removal at height
        // h, the set governing h+1 differs from the set governing h+2's parent,
        // and validating h+2's LastCommit against a stale set would reject
        // honest signers ("signer not in previous set") and stall the chain.
        e.prevValSet = e.valSet
        if len(e.removeNextHeight) > 0 {
                addrs := make([]Hash, 0, len(e.removeNextHeight))
                for a := range e.removeNextHeight {
                        addrs = append(addrs, a)
                }
                next := e.valSet.Without(addrs)
                if next == nil {
                        e.fault = errors.New("consensus: all validators tombstoned")
                        return
                }
                e.valSet = next
                e.removeNextHeight = make(map[Hash]bool)
        }
        e.height = e.chain.Height() + 1
        e.round = 0
        e.step = StepNewHeight
        e.proposals = make(map[uint32]*Proposal)
        e.blocks = make(map[Hash]*Block)
        e.rounds = make(map[uint32]*roundVotes)
        e.lockedBlock = nil
        e.lockedRound = -1
        e.lockedHash = ZeroHash
        e.validBlock = nil
        e.validRound = -1
        e.pendingCommit = nil

        // Replay the lookahead buffered for this height: proposals first (so the
        // round-0 proposal is available to startRound), then votes (their quorum
        // transitions fire normally).
        props := e.futureProps[e.height]
        delete(e.futureProps, e.height)
        votes := e.futureVotes[e.height]
        delete(e.futureVotes, e.height)
        for _, p := range props {
                e.applyProposal(p)
        }
        e.startRound(0)
        for _, v := range votes {
                e.applyVote(v)
        }
}

// startRound begins a round: the proposer broadcasts immediately; everyone
// else arms the (round-doubling) propose timeout. A buffered proposal for
// the round is consumed immediately.
func (e *Engine) startRound(r uint32) {
        e.round = r
        e.step = StepPropose
        e.metrics.RoundsStarted++
        e.stopTimer()

        if e.valSet.Contains(e.me) && e.valSet.GetProposer(e.height, r).Address == e.me {
                block, polRound := e.valueToPropose()
                prop := &Proposal{
                        Height:      e.height,
                        Round:       r,
                        POLRound:    polRound,
                        BlockHash:   block.Hash(),
                        Block:       block,
                        TimestampMs: e.nextTimestampMs(),
                        Proposer:    e.me,
                }
                prop.Signature = ed25519.Sign(e.priv, prop.SignBytes())
                e.proposals[r] = prop
                e.blocks[block.Hash()] = block
                e.outbound = append(e.outbound, ConsensusMessage{Kind: MsgKindProposal, Proposal: prop})
                e.enterPrevote()
                return
        }

        e.setTimer(timeoutPropose, e.proposeTimeout(r))
        if p, ok := e.proposals[r]; ok && e.step == StepPropose {
                _ = p
                e.enterPrevote()
        }
}

// valueToPropose returns the value this proposer should propose: the valid
// (latest-polka'd) value, else the locked value, else a fresh mempool block.
func (e *Engine) valueToPropose() (*Block, int32) {
        if e.validBlock != nil {
                return e.validBlock, e.validRound
        }
        if e.lockedBlock != nil {
                return e.lockedBlock, e.lockedRound
        }
        return e.buildBlock(), -1
}

// buildBlock assembles a fresh candidate from the mempool and pending
// evidence (deterministic ordering via AssembleBlock).
func (e *Engine) buildBlock() *Block {
        txs := e.mempool.Snapshot(e.cfg.MaxBlockTxs)
        evs := e.pendingEvidenceSnapshot(e.cfg.MaxEvidencePerBlock)
        return AssembleBlock(e.height, e.round, e.chain.Tip(), e.nextTimestampMs(), e.me, txs, evs, e.lastCommit)
}

// pendingEvidenceSnapshot returns up to max pending evidence entries,
// deduplicated and deterministically ordered.
func (e *Engine) pendingEvidenceSnapshot(max int) []EquivocationEvidence {
        if max > len(e.pendingEvidence) {
                max = len(e.pendingEvidence)
        }
        out := make([]EquivocationEvidence, 0, max)
        seen := make(map[Hash]bool, max)
        for i := 0; i < len(e.pendingEvidence) && len(out) < max; i++ {
                ev := e.pendingEvidence[i]
                h := ev.Hash()
                if seen[h] {
                        continue
                }
                seen[h] = true
                out = append(out, *ev)
        }
        return out
}

// ── Proposal processing ─────────────────────────────────────────────────────

func (e *Engine) applyProposal(p *Proposal) {
        if p == nil || p.Block == nil {
                return
        }
        if p.Height == e.height+1 {
                if len(e.futureProps[p.Height]) < 128 {
                        e.futureProps[p.Height] = append(e.futureProps[p.Height], p)
                }
                return
        }
        if p.Height != e.height {
                e.metrics.ProposalsDropped++ // beyond lookahead: catch-up sync is a TODO
                return
        }
        if _, buffered := e.proposals[p.Round]; buffered {
                e.metrics.ProposalsDropped++ // one proposal per round is used for prevote decisions
                return
        }
        if err := e.validateProposal(p); err != nil {
                e.metrics.ProposalsDropped++
                e.logf("proposal rejected at h=%d r=%d: %v", p.Height, p.Round, err)
                return
        }
        e.proposals[p.Round] = p
        e.blocks[p.BlockHash] = p.Block
        e.metrics.ProposalsProcessed++

        // If a commit quorum already formed for this block but we were missing
        // the block itself, finish the commit now. The match is on the hash
        // only: the quorum (and its round, kept for the LastCommit) was
        // witnessed earlier, and the block may (re-)arrive in any round.
        if e.pendingCommit != nil && e.pendingCommit.hash == p.BlockHash {
                pc := *e.pendingCommit
                e.pendingCommit = nil
                e.commitBlock(pc.round, pc.hash)
                return
        }
        if p.Round == e.round && e.step == StepPropose {
                e.enterPrevote()
        }
}

// validateProposal performs full validation of a proposal:
// correct proposer for (height, round), ed25519 signature, canonical block
// hash and app hash, parent linkage to our chain tip, POLRound sanity,
// LastCommit justification (2/3 of the previous height's validator set) and
// evidence signature validity.
func (e *Engine) validateProposal(p *Proposal) error {
        expected := e.valSet.GetProposer(p.Height, p.Round)
        if expected == nil || expected.Address != p.Proposer {
                return fmt.Errorf("not the deterministic proposer (got %s)", p.Proposer.Short())
        }
        if !p.Verify(expected.PubKey) {
                return errors.New("proposal signature invalid")
        }
        b := p.Block
        if p.BlockHash != b.Hash() {
                return errors.New("proposal block hash mismatch")
        }
        if b.Height != p.Height {
                return fmt.Errorf("block height %d, proposal height %d", b.Height, p.Height)
        }
        if b.Round > p.Round {
                return fmt.Errorf("block first-proposed in round %d > proposal round %d", b.Round, p.Round)
        }
        if b.Parent != e.chain.Tip() {
                return fmt.Errorf("block parent %s is not chain tip", b.Parent.Short())
        }
        if b.Proposer != p.Proposer {
                return errors.New("block proposer mismatch")
        }
        if b.AppHash != b.ComputeAppHash() {
                return errors.New("block app-hash mismatch")
        }
        if p.POLRound < -1 || p.POLRound >= int32(p.Round) {
                return fmt.Errorf("invalid POLRound %d for round %d", p.POLRound, p.Round)
        }
        if p.POLRound >= 0 && !e.polkaFor(p.BlockHash, uint32(p.POLRound)) {
                return fmt.Errorf("cited polka (round %d) not seen", p.POLRound)
        }
        if err := e.validateLastCommit(b); err != nil {
                return fmt.Errorf("lastCommit: %w", err)
        }
        for i := range b.Evidence {
                if err := e.validateEvidence(&b.Evidence[i]); err != nil {
                        return fmt.Errorf("evidence[%d]: %w", i, err)
                }
        }
        return nil
}

// validateLastCommit checks the block's commit justification for its parent:
// correct height/hash, distinct validators of the previous height's set, valid
// signatures, and strictly more than 2/3 of that set's power.
func (e *Engine) validateLastCommit(b *Block) error {
        if b.Height == 1 {
                if b.LastCommit != nil {
                        return errors.New("height-1 block must not carry a lastCommit")
                }
                return nil
        }
        lc := b.LastCommit
        if lc == nil {
                return errors.New("missing lastCommit")
        }
        if lc.Height != b.Height-1 || lc.BlockHash != b.Parent {
                return errors.New("lastCommit does not justify the parent")
        }
        total := e.prevValSet.TotalPower()
        power := int64(0)
        seen := make(map[Hash]bool, len(lc.Precommits))
        for i := range lc.Precommits {
                v := &lc.Precommits[i]
                if v.Type != VoteTypePrecommit || v.Height != lc.Height || v.Round != lc.Round || v.BlockHash != lc.BlockHash {
                        return errors.New("precommit does not match lastCommit")
                }
                val := e.prevValSet.Get(v.ValidatorAddress)
                if val == nil {
                        return fmt.Errorf("lastCommit signer %s not in previous set", v.ValidatorAddress.Short())
                }
                if seen[v.ValidatorAddress] {
                        return errors.New("duplicate lastCommit signer")
                }
                seen[v.ValidatorAddress] = true
                if !v.Verify(val.PubKey) {
                        return errors.New("lastCommit precommit signature invalid")
                }
                power += val.Power
        }
        if !hasQuorum(power, total) {
                return fmt.Errorf("lastCommit power %d/%d is not >2/3", power, total)
        }
        return nil
}

// validateEvidence checks structural consistency plus both signatures
// against the known validator keys.
func (e *Engine) validateEvidence(ev *EquivocationEvidence) error {
        if !ev.Conflict() {
                return errors.New("not a structural equivocation")
        }
        if ev.Height != ev.VoteA.Height || ev.Round != ev.VoteA.Round ||
                ev.Type != ev.VoteA.Type || ev.ValidatorAddress != ev.VoteA.ValidatorAddress {
                return errors.New("evidence header inconsistent with embedded votes")
        }
        if ev.Height > e.height {
                return errors.New("evidence for a future height")
        }
        pk, ok := e.knownKeys[ev.ValidatorAddress]
        if !ok {
                return errors.New("evidence validator unknown")
        }
        return ev.VerifySignatures(pk)
}

// ── Vote processing ─────────────────────────────────────────────────────────

func (e *Engine) applyVote(v *Vote) {
        if v == nil {
                return
        }
        if v.Height == e.height+1 {
                if len(e.futureVotes[v.Height]) < 4096 {
                        e.futureVotes[v.Height] = append(e.futureVotes[v.Height], v)
                }
                return
        }
        if v.Height != e.height {
                e.metrics.VotesDropped++ // beyond lookahead: catch-up sync is a TODO
                return
        }
        if v.Type != VoteTypePrevote && v.Type != VoteTypePrecommit {
                e.metrics.VotesDropped++
                return
        }
        val := e.valSet.Get(v.ValidatorAddress)
        if val == nil {
                e.metrics.VotesDropped++ // not in the current set (e.g. already removed)
                return
        }
        if !v.Verify(val.PubKey) {
                e.metrics.VotesDropped++
                return
        }

        rv := e.rounds[v.Round]
        if rv == nil {
                rv = newRoundVotes()
                e.rounds[v.Round] = rv
        }
        k := voteKey{addr: v.ValidatorAddress, typ: v.Type}
        if first, ok := rv.byKey[k]; ok {
                if first.BlockHash != v.BlockHash {
                        // Equivocation: two different values at the same
                        // (height, round, type). Both signatures already verified.
                        ev, err := MakeEquivocationEvidence(first, v)
                        if err == nil {
                                e.processEvidenceLocked(ev)
                        }
                }
                return // duplicates and conflicting votes never tally
        }
        rv.byKey[k] = v
        if v.Type == VoteTypePrevote {
                rv.prevoteFor[v.BlockHash] += val.Power
        } else {
                rv.precommitFor[v.BlockHash] += val.Power
                rv.precommitVotes[v.BlockHash] = append(rv.precommitVotes[v.BlockHash], v)
        }
        e.metrics.VotesProcessed++
        e.checkQuorum(v, rv)
}

// checkQuorum fires the quorum-driven transitions (Tendermint rules; see the
// file header). rv is the vote's round's tally.
func (e *Engine) checkQuorum(v *Vote, rv *roundVotes) {
        total := e.valSet.TotalPower()

        if v.Type == VoteTypePrevote {
                if v.BlockHash != ZeroHash && hasQuorum(rv.prevoteFor[v.BlockHash], total) {
                        // Polka for (H, v.Round, hash) witnessed.
                        if int32(v.Round) > e.validRound {
                                if blk, ok := e.blocks[v.BlockHash]; ok {
                                        e.validBlock = blk
                                        e.validRound = int32(v.Round)
                                }
                        }
                        if v.Round == e.round && e.step == StepPrevote {
                                if blk, ok := e.blocks[v.BlockHash]; ok {
                                        e.lockedBlock = blk
                                        e.lockedRound = int32(v.Round)
                                        e.lockedHash = v.BlockHash
                                        e.enterPrecommit(v.BlockHash)
                                } else {
                                        // We have the quorum but not the block: wait for the
                                        // proposal (prevote timer covers liveness).
                                        e.logf("polka at h=%d r=%d for unknown block %s; waiting for proposal",
                                                e.height, v.Round, v.BlockHash.Short())
                                }
                        }
                        return
                }
                if v.BlockHash == ZeroHash && hasQuorum(rv.prevoteFor[ZeroHash], total) &&
                        v.Round == e.round && e.step == StepPrevote {
                        // +2/3 prevotes nil → precommit nil. NO unlock (see file header
                        // for the safety argument).
                        e.enterPrecommit(ZeroHash)
                }
                return
        }

        // Precommit:
        if v.BlockHash != ZeroHash && hasQuorum(rv.precommitFor[v.BlockHash], total) {
                if blk, ok := e.blocks[v.BlockHash]; ok && blk.Height == e.height {
                        e.commitBlock(v.Round, v.BlockHash)
                } else {
                        // Commit quorum observed but block unknown: defer until the
                        // proposal arrives (see applyProposal).
                        e.pendingCommit = &pendingCommit{round: v.Round, hash: v.BlockHash}
                }
                return
        }
        if v.BlockHash == ZeroHash && hasQuorum(rv.precommitFor[ZeroHash], total) &&
                v.Round == e.round && e.step == StepPrecommit {
                // View change on +2/3 precommit-nil.
                e.startRound(e.round + 1)
        }
}

// polkaFor reports whether we have recorded a 2/3+ prevote quorum for hash
// at the given round of the current height.
func (e *Engine) polkaFor(hash Hash, round uint32) bool {
        rv := e.rounds[round]
        if rv == nil {
                return false
        }
        return hasQuorum(rv.prevoteFor[hash], e.valSet.TotalPower())
}

// ── Step transitions ────────────────────────────────────────────────────────

// enterPrevote enters the prevote step and broadcasts our prevote: the
// proposal's hash if it is valid and justified, else nil.
func (e *Engine) enterPrevote() {
        e.step = StepPrevote
        e.setTimer(timeoutPrevote, e.prevoteTimeout(e.round))
        hash := ZeroHash
        if p, ok := e.proposals[e.round]; ok && e.proposalJustified(p) {
                hash = p.BlockHash
        }
        e.broadcastVote(VoteTypePrevote, hash)
}

// enterPrecommit enters the precommit step and broadcasts our precommit.
// Non-nil hashes MUST have been preceded by a witnessed polka (callers
// guarantee this — lock-on-precommit).
func (e *Engine) enterPrecommit(hash Hash) {
        e.step = StepPrecommit
        e.setTimer(timeoutPrecommit, e.precommitTimeout(e.round))
        e.broadcastVote(VoteTypePrecommit, hash)
}

// proposalJustified is the Tendermint prevote rule:
//
//      prevote the proposal iff valid AND
//        (lockedRound ≤ POLRound) OR (locked value == proposal value)
//
// with an additional requirement that the cited polka (POLRound ≥ 0) has
// actually been witnessed by us. When unlocked (lockedRound == -1) any valid
// proposal is justified. A polka in a round LATER than our lock justifies
// switching values — this is the unlock path.
func (e *Engine) proposalJustified(p *Proposal) bool {
        if p.POLRound < -1 || p.POLRound >= int32(p.Round) {
                return false
        }
        if e.lockedBlock == nil {
                if p.POLRound >= 0 {
                        return e.polkaFor(p.BlockHash, uint32(p.POLRound))
                }
                return true
        }
        if e.lockedHash == p.BlockHash {
                return true
        }
        // Locked on a different value: only a polka at a round ≥ our lockedRound
        // (necessarily > in practice — a same-round conflicting polka cannot form
        // with <1/3 byzantine power) justifies prevoting the new value.
        if p.POLRound >= 0 && p.POLRound >= e.lockedRound {
                return e.polkaFor(p.BlockHash, uint32(p.POLRound))
        }
        return false
}

// broadcastVote signs and emits a vote, and queues it for self-processing
// (self-delivery through the event queue, not recursion).
func (e *Engine) broadcastVote(typ VoteType, hash Hash) {
        if !e.valSet.Contains(e.me) {
                return // tombstoned/removed: observer mode
        }
        v := &Vote{
                Type:             typ,
                Height:           e.height,
                Round:            e.round,
                BlockHash:        hash,
                ValidatorAddress: e.me,
        }
        v.Signature = ed25519.Sign(e.priv, v.SignBytes())
        e.outbound = append(e.outbound, ConsensusMessage{Kind: MsgKindVote, Vote: v})
        e.queue = append(e.queue, voteEvent{v: v})
}

// ── Commit ──────────────────────────────────────────────────────────────────

// commitBlock applies a committed block: chain append, evidence application
// (slashing + next-height power removal), mempool drain, consumer
// notification, gossip announcement, and advance to the next height.
func (e *Engine) commitBlock(round uint32, hash Hash) {
        blk, ok := e.blocks[hash]
        if !ok || blk.Height != e.height {
                e.fault = fmt.Errorf("commit without block at h=%d r=%d hash=%s", e.height, round, hash.Short())
                return
        }
        // Canonical (validator-address-sorted) lastCommit precommits — the set a
        // node collects can differ between correct nodes by arrival order, and
        // the block hash must not depend on it (see Block.Hash).
        pcs := make([]*Vote, 0, len(e.rounds[round].precommitVotes[hash]))
        for _, v := range e.rounds[round].precommitVotes[hash] {
                pcs = append(pcs, v)
        }
        sort.SliceStable(pcs, func(i, j int) bool {
                return pcs[i].ValidatorAddress.Hex() < pcs[j].ValidatorAddress.Hex()
        })
        precommits := make([]Vote, 0, len(pcs))
        for _, v := range pcs {
                precommits = append(precommits, *v)
        }
        if err := e.chain.Append(blk); err != nil {
                e.fault = fmt.Errorf("chain append failed: %w", err)
                return
        }
        e.step = StepCommit
        e.lastCommit = &CommitInfo{
                Height:     e.height,
                Round:      round,
                BlockHash:  hash,
                Precommits: precommits,
        }
        e.metrics.HeightsCommitted++

        // Apply the block's evidence deterministically: slash, and remove the
        // equivocator's voting power at the next height.
        for i := range blk.Evidence {
                ev := blk.Evidence[i]
                e.applyCommittedEvidence(&ev)
        }
        e.mempool.RemoveTxs(blk.Txs)

        fb := FinalizedBlock{Block: blk, CommitRound: round, Precommits: precommits}
        select {
        case e.finalized <- fb:
        default:
                e.metrics.FinalizedDropped++
        }
        e.outbound = append(e.outbound, ConsensusMessage{Kind: MsgKindFinalizedBlock, Block: &fb})

        e.stopTimer()
        e.enterNewHeight()
}

// applyCommittedEvidence slashes (idempotently) and schedules the
// validator's power removal for the next height.
func (e *Engine) applyCommittedEvidence(ev *EquivocationEvidence) {
        h := ev.Hash()
        if e.cfg.Slasher != nil {
                if err := e.cfg.Slasher.Enforce(ev); err != nil {
                        e.logf("slash failed for %s: %v", ev.ValidatorAddress.Short(), err)
                }
        }
        e.evidenceSeen[h] = true
        e.removeNextHeight[ev.ValidatorAddress] = true
        // Drop from the local pending list (it is on-chain now).
        kept := e.pendingEvidence[:0]
        for _, p := range e.pendingEvidence {
                if p.Hash() != h {
                        kept = append(kept, p)
                }
        }
        e.pendingEvidence = kept
}

// ── Evidence processing ─────────────────────────────────────────────────────

// processEvidenceLocked records locally detected (already
// signature-verified) evidence: hand to the slasher, queue for inclusion in
// a future block, and broadcast so peers can verify and apply it.
func (e *Engine) processEvidenceLocked(ev *EquivocationEvidence) {
        h := ev.Hash()
        if e.evidenceSeen[h] {
                return
        }
        e.evidenceSeen[h] = true
        e.metrics.EvidenceDetected++
        e.pendingEvidence = append(e.pendingEvidence, ev)
        if e.cfg.Slasher != nil {
                if err := e.cfg.Slasher.Enforce(ev); err != nil {
                        e.logf("slash failed for %s: %v", ev.ValidatorAddress.Short(), err)
                }
        }
        e.outbound = append(e.outbound, ConsensusMessage{Kind: MsgKindEvidence, Evidence: ev})
}

// applyEvidence handles local or remote evidence. Remote evidence is fully
// verified (structure + both signatures) before it is applied.
func (e *Engine) applyEvidence(ev *EquivocationEvidence, verify bool) {
        if ev == nil {
                return
        }
        if verify {
                if err := e.validateEvidence(ev); err != nil {
                        e.metrics.VotesDropped++
                        e.logf("evidence rejected: %v", err)
                        return
                }
        }
        e.processEvidenceLocked(ev)
}

// ── Timeouts & time ─────────────────────────────────────────────────────────

func (e *Engine) setTimer(kind timeoutKind, d time.Duration) {
        h, r := e.height, e.round
        e.timer = time.AfterFunc(d, func() {
                e.submit(timeoutEvent{kind: kind, height: h, round: r})
        })
}

func (e *Engine) stopTimer() {
        if e.timer != nil {
                e.timer.Stop()
                e.timer = nil
        }
}

// proposeTimeout doubles per round (view-change backoff), exponent capped.
func (e *Engine) proposeTimeout(r uint32) time.Duration {
        return doublePerRound(e.cfg.ProposeTimeout, r, e.cfg.MaxRoundShift)
}

func (e *Engine) prevoteTimeout(r uint32) time.Duration {
        return doublePerRound(e.cfg.PrevoteTimeout, r, e.cfg.MaxRoundShift)
}

func (e *Engine) precommitTimeout(r uint32) time.Duration {
        return doublePerRound(e.cfg.PrecommitTimeout, r, e.cfg.MaxRoundShift)
}

// doublePerRound returns base << min(r, maxShift), saturating safely.
func doublePerRound(base time.Duration, r uint32, maxShift uint) time.Duration {
        if base <= 0 {
                base = time.Millisecond
        }
        if base > time.Hour {
                base = time.Hour
        }
        shift := r
        if uint64(shift) > uint64(maxShift) {
                shift = uint32(maxShift)
        }
        return base << shift
}

// nextTimestampMs: deterministic mode (no Clock) derives the timestamp from
// the parent tip (+1000ms); wall-clock mode uses max(now, parent+1) to keep
// monotonicity.
func (e *Engine) nextTimestampMs() int64 {
        tip := e.chain.TipTimestampMs()
        if e.cfg.Clock == nil {
                return tip + 1000
        }
        now := e.cfg.Clock().UnixMilli()
        if now <= tip {
                return tip + 1
        }
        return now
}

func (e *Engine) logf(format string, args ...interface{}) {
        if e.cfg.Logger != nil {
                e.cfg.Logger.Printf("[TRION-BFT "+e.me.Short()+"] "+format, args...)
                return
        }
        log.Printf("[TRION-BFT "+e.me.Short()+"] "+format, args...)
}
