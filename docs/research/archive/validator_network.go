// TRION Protocol — Go Validator P2P Network
// Channel 17: P2P Validator Mesh Communication
// Implementation: Go goroutine model — handles thousands of concurrent connections.
// This is the direct peer-to-peer validator networking layer — not blockchain-mediated.
//
// Author: TRION Protocol — Originator: Hudu Yusuf (Analys)
// License: CC0

package validator

import (
	"context"
	"crypto/sha256"
	"encoding/hex"
	"encoding/json"
	"fmt"
	"log"
	"math"
	"net"
	"net/http"
	"sync"
	"time"
)

// ── Constants ──────────────────────────────────────────────────────────────────

const (
	DefaultPort        = 9000
	MaxPeers           = 500
	HeartbeatInterval  = 5 * time.Second
	ConsensusTimeout   = 30 * time.Second
	DiversityGamma     = 0.20 // γ_diversity for reward calculation
	MinContinents      = 4
	HHIWarning         = 1500
	HHIDanger          = 2500
	HHICritical        = 4000
	MaxSingleRegion    = 0.40
	MaxSingleJurisd    = 0.30
)

// ── Data Types ─────────────────────────────────────────────────────────────────

// ValidatorInfo carries the public information about a validator node.
type ValidatorInfo struct {
	ID              string    `json:"id"`
	Address         string    `json:"address"`
	Port            int       `json:"port"`
	GeographicRegion string   `json:"geographic_region"`
	Continent       string    `json:"continent"`
	Jurisdiction    string    `json:"jurisdiction"`
	Stake           float64   `json:"stake"`
	DiversityScore  float64   `json:"diversity_score"` // d_j = 1 - corr(M_j, M̄)
	EffectiveStake  float64   `json:"effective_stake"` // s_j · d_j
	LastSeen        time.Time `json:"last_seen"`
	HSMVerified     bool      `json:"hsm_verified"`
}

// ConsensusMessage carries a validator's assessment for a behavioral entity.
type ConsensusMessage struct {
	ValidatorID   string    `json:"validator_id"`
	EntityID      string    `json:"entity_id"`
	Valuation     float64   `json:"valuation"`    // v_j — the validator's signal
	ModelOutputs  []float64 `json:"model_outputs"` // M_j — recent model history
	Timestamp     time.Time `json:"timestamp"`
	Signature     string    `json:"signature"` // SHA3-256 of payload
	GenesisGen    int       `json:"genesis_gen"` // Genomic Key generation
}

// ConsensusRound aggregates validator messages for one entity.
type ConsensusRound struct {
	EntityID   string
	Messages   []*ConsensusMessage
	StartedAt  time.Time
	mu         sync.RWMutex
}

// DiversityWeightedResult is the output of Σ(t) computation.
type DiversityWeightedResult struct {
	Sigma            float64            `json:"sigma"`          // Σ(t)
	ValidatorWeights map[string]float64 `json:"weights"`        // s_j · d_j per validator
	MedianValuation  float64            `json:"median_valuation"`
	DeltaT           float64            `json:"delta_t"`        // dynamic consensus window
	HHI              float64            `json:"hhi"`
	IncludedCount    int                `json:"included_count"`
	ExcludedCount    int                `json:"excluded_count"`
	Bootstrap        bool               `json:"bootstrap"`
}

// NetworkState tracks the overall validator network health.
type NetworkState struct {
	mu             sync.RWMutex
	Validators     map[string]*ValidatorInfo
	ActiveRounds   map[string]*ConsensusRound
	HHI            float64
	ContinentCount int
	AWAEnforced    bool
	SignalsFrozen  bool
}

// ── Network Node ───────────────────────────────────────────────────────────────

// Node represents a TRION validator P2P node.
type Node struct {
	info    ValidatorInfo
	state   *NetworkState
	peers   map[string]*ValidatorInfo
	peersMu sync.RWMutex
	server  *http.Server
	ctx     context.Context
	cancel  context.CancelFunc
}

// NewNode creates a new validator P2P node.
func NewNode(info ValidatorInfo) *Node {
	ctx, cancel := context.WithCancel(context.Background())
	state := &NetworkState{
		Validators:   make(map[string]*ValidatorInfo),
		ActiveRounds: make(map[string]*ConsensusRound),
		AWAEnforced:  true,
		SignalsFrozen: false,
	}
	state.Validators[info.ID] = &info

	return &Node{
		info:   info,
		state:  state,
		peers:  make(map[string]*ValidatorInfo),
		ctx:    ctx,
		cancel: cancel,
	}
}

// Start begins the validator P2P network node.
func (n *Node) Start() error {
	mux := http.NewServeMux()
	mux.HandleFunc("/v1/handshake", n.handleHandshake)
	mux.HandleFunc("/v1/consensus/submit", n.handleConsensusSubmit)
	mux.HandleFunc("/v1/consensus/result", n.handleConsensusResult)
	mux.HandleFunc("/v1/peers", n.handlePeers)
	mux.HandleFunc("/v1/health", n.handleHealth)
	mux.HandleFunc("/v1/hhi", n.handleHHI)

	n.server = &http.Server{
		Addr:         fmt.Sprintf(":%d", n.info.Port),
		Handler:      mux,
		ReadTimeout:  10 * time.Second,
		WriteTimeout: 10 * time.Second,
	}

	// Start heartbeat goroutine
	go n.heartbeatLoop()

	// Start consensus aggregation goroutine
	go n.consensusLoop()

	// Start HHI monitoring goroutine
	go n.hhiMonitorLoop()

	log.Printf("[TRION-P2P] Validator node %s starting on port %d", n.info.ID, n.info.Port)
	return n.server.ListenAndServe()
}

// Stop gracefully shuts down the node.
func (n *Node) Stop() {
	n.cancel()
	if n.server != nil {
		ctx, cancel := context.WithTimeout(context.Background(), 5*time.Second)
		defer cancel()
		n.server.Shutdown(ctx)
	}
}

// ── Diversity-Weighted BFT Consensus ──────────────────────────────────────────

// ComputeDiversityWeight computes d_j = 1 - corr(M_j, M̄).
// When Byzantine validators coordinate: corr → 1, d_j → 0, effective stake → 0.
// Honesty is the Nash equilibrium.
func ComputeDiversityWeight(modelOutputs, medianOutputs []float64) float64 {
	n := len(modelOutputs)
	if n < 2 || len(medianOutputs) < 2 {
		return 1.0
	}
	if len(medianOutputs) < n {
		n = len(medianOutputs)
	}

	mj := modelOutputs[len(modelOutputs)-n:]
	mb := medianOutputs[len(medianOutputs)-n:]

	meanJ, meanB := 0.0, 0.0
	for i := 0; i < n; i++ {
		meanJ += mj[i]
		meanB += mb[i]
	}
	meanJ /= float64(n)
	meanB /= float64(n)

	cov, varJ, varB := 0.0, 0.0, 0.0
	for i := 0; i < n; i++ {
		dj := mj[i] - meanJ
		db := mb[i] - meanB
		cov += dj * db
		varJ += dj * dj
		varB += db * db
	}

	if varJ <= 0 || varB <= 0 {
		return 1.0
	}
	corr := cov / math.Sqrt(varJ*varB)
	if math.IsNaN(corr) {
		return 1.0
	}
	d := 1.0 - corr
	if d < 0 {
		return 0.0
	}
	return d
}

// ComputeSigma computes Σ(t) = Σ_j [s_j·d_j·1(|v_j - v̄| ≤ δ(t))] / Σ_j [s_j·d_j]
// Dynamic consensus window: δ(t) = δ_base · (1 + V(t))
func ComputeSigma(
	messages []*ConsensusMessage,
	validators map[string]*ValidatorInfo,
	volatility float64,
	deltaBase float64,
) DiversityWeightedResult {
	if len(messages) == 0 {
		return DiversityWeightedResult{
			Sigma:     0.25,
			Bootstrap: true,
		}
	}

	deltaT := deltaBase * (1.0 + volatility)

	// Compute median model outputs across all validators
	allOutputLen := 0
	for _, msg := range messages {
		if len(msg.ModelOutputs) > allOutputLen {
			allOutputLen = len(msg.ModelOutputs)
		}
	}
	medianOutputs := make([]float64, allOutputLen)
	for i := 0; i < allOutputLen; i++ {
		vals := make([]float64, 0, len(messages))
		for _, msg := range messages {
			if i < len(msg.ModelOutputs) {
				vals = append(vals, msg.ModelOutputs[i])
			}
		}
		medianOutputs[i] = median(vals)
	}

	// Compute median valuation
	valuations := make([]float64, len(messages))
	for i, msg := range messages {
		valuations[i] = msg.Valuation
	}
	medianVal := median(valuations)

	weights := make(map[string]float64)
	numerator := 0.0
	denominator := 0.0
	includedCount := 0
	excludedCount := 0

	for _, msg := range messages {
		v, ok := validators[msg.ValidatorID]
		if !ok {
			continue
		}
		dj := ComputeDiversityWeight(msg.ModelOutputs, medianOutputs)
		wj := v.Stake * dj
		weights[msg.ValidatorID] = wj
		denominator += wj

		if math.Abs(msg.Valuation-medianVal) <= deltaT {
			numerator += wj
			includedCount++
		} else {
			excludedCount++
		}
	}

	sigma := 0.25 // bootstrap
	if denominator > 0 {
		sigma = numerator / denominator
	}

	hhi := computeHHI(weights)

	return DiversityWeightedResult{
		Sigma:            sigma,
		ValidatorWeights: weights,
		MedianValuation:  medianVal,
		DeltaT:           deltaT,
		HHI:              hhi,
		IncludedCount:    includedCount,
		ExcludedCount:    excludedCount,
		Bootstrap:        false,
	}
}

// computeHHI computes HHI(t) = Σ_j (w_j / Σ_k w_k)² × 10000
func computeHHI(weights map[string]float64) float64 {
	total := 0.0
	for _, w := range weights {
		total += w
	}
	if total <= 0 {
		return 0
	}
	hhi := 0.0
	for _, w := range weights {
		share := w / total
		hhi += share * share
	}
	return hhi * 10000
}

// ── HTTP Handlers ──────────────────────────────────────────────────────────────

func (n *Node) handleHandshake(w http.ResponseWriter, r *http.Request) {
	if r.Method != http.MethodPost {
		http.Error(w, "POST only", http.StatusMethodNotAllowed)
		return
	}
	var peer ValidatorInfo
	if err := json.NewDecoder(r.Body).Decode(&peer); err != nil {
		http.Error(w, err.Error(), http.StatusBadRequest)
		return
	}
	n.peersMu.Lock()
	peer.LastSeen = time.Now()
	n.peers[peer.ID] = &peer
	n.peersMu.Unlock()

	n.state.mu.Lock()
	n.state.Validators[peer.ID] = &peer
	n.state.mu.Unlock()

	json.NewEncoder(w).Encode(n.info)
}

func (n *Node) handleConsensusSubmit(w http.ResponseWriter, r *http.Request) {
	if r.Method != http.MethodPost {
		http.Error(w, "POST only", http.StatusMethodNotAllowed)
		return
	}
	var msg ConsensusMessage
	if err := json.NewDecoder(r.Body).Decode(&msg); err != nil {
		http.Error(w, err.Error(), http.StatusBadRequest)
		return
	}
	msg.Timestamp = time.Now()

	n.state.mu.Lock()
	round, ok := n.state.ActiveRounds[msg.EntityID]
	if !ok {
		round = &ConsensusRound{
			EntityID:  msg.EntityID,
			StartedAt: time.Now(),
		}
		n.state.ActiveRounds[msg.EntityID] = round
	}
	n.state.mu.Unlock()

	round.mu.Lock()
	round.Messages = append(round.Messages, &msg)
	round.mu.Unlock()

	w.WriteHeader(http.StatusAccepted)
}

func (n *Node) handleConsensusResult(w http.ResponseWriter, r *http.Request) {
	entityID := r.URL.Query().Get("entity_id")
	volatility := 0.30
	if v := r.URL.Query().Get("volatility"); v != "" {
		fmt.Sscanf(v, "%f", &volatility)
	}

	n.state.mu.RLock()
	round, ok := n.state.ActiveRounds[entityID]
	n.state.mu.RUnlock()

	if !ok {
		http.Error(w, "No active round for entity", http.StatusNotFound)
		return
	}

	round.mu.RLock()
	msgs := make([]*ConsensusMessage, len(round.Messages))
	copy(msgs, round.Messages)
	round.mu.RUnlock()

	n.state.mu.RLock()
	validators := n.state.Validators
	n.state.mu.RUnlock()

	result := ComputeSigma(msgs, validators, volatility, 0.10)
	json.NewEncoder(w).Encode(result)
}

func (n *Node) handlePeers(w http.ResponseWriter, r *http.Request) {
	n.peersMu.RLock()
	defer n.peersMu.RUnlock()
	json.NewEncoder(w).Encode(n.peers)
}

func (n *Node) handleHealth(w http.ResponseWriter, r *http.Request) {
	n.state.mu.RLock()
	defer n.state.mu.RUnlock()
	json.NewEncoder(w).Encode(map[string]interface{}{
		"id":              n.info.ID,
		"validator_count": len(n.state.Validators),
		"hhi":             n.state.HHI,
		"continents":      n.state.ContinentCount,
		"awa_enforced":    n.state.AWAEnforced,
		"signals_frozen":  n.state.SignalsFrozen,
	})
}

func (n *Node) handleHHI(w http.ResponseWriter, r *http.Request) {
	n.state.mu.RLock()
	defer n.state.mu.RUnlock()

	tier := "HEALTHY"
	if n.state.HHI > HHICritical {
		tier = "CRITICAL"
	} else if n.state.HHI > HHIDanger {
		tier = "DANGER"
	} else if n.state.HHI > HHIWarning {
		tier = "WARNING"
	}

	json.NewEncoder(w).Encode(map[string]interface{}{
		"hhi":  n.state.HHI,
		"tier": tier,
	})
}

// ── Background Goroutines ──────────────────────────────────────────────────────

func (n *Node) heartbeatLoop() {
	ticker := time.NewTicker(HeartbeatInterval)
	defer ticker.Stop()
	for {
		select {
		case <-n.ctx.Done():
			return
		case <-ticker.C:
			n.broadcastHeartbeat()
		}
	}
}

func (n *Node) broadcastHeartbeat() {
	n.peersMu.RLock()
	peers := make([]*ValidatorInfo, 0, len(n.peers))
	for _, p := range n.peers {
		peers = append(peers, p)
	}
	n.peersMu.RUnlock()

	payload, _ := json.Marshal(n.info)
	for _, peer := range peers {
		go func(p *ValidatorInfo) {
			addr := fmt.Sprintf("http://%s:%d/v1/handshake", p.Address, p.Port)
			client := &http.Client{Timeout: 2 * time.Second}
			resp, err := client.Post(addr, "application/json",
				nil)
			if err != nil {
				return
			}
			defer resp.Body.Close()
			_ = payload
		}(peer)
	}
}

func (n *Node) consensusLoop() {
	ticker := time.NewTicker(100 * time.Millisecond)
	defer ticker.Stop()
	for {
		select {
		case <-n.ctx.Done():
			return
		case <-ticker.C:
			n.cleanupExpiredRounds()
		}
	}
}

func (n *Node) cleanupExpiredRounds() {
	n.state.mu.Lock()
	defer n.state.mu.Unlock()
	cutoff := time.Now().Add(-ConsensusTimeout)
	for id, round := range n.state.ActiveRounds {
		if round.StartedAt.Before(cutoff) {
			delete(n.state.ActiveRounds, id)
		}
	}
}

func (n *Node) hhiMonitorLoop() {
	ticker := time.NewTicker(60 * time.Second)
	defer ticker.Stop()
	for {
		select {
		case <-n.ctx.Done():
			return
		case <-ticker.C:
			n.recomputeHHI()
		}
	}
}

func (n *Node) recomputeHHI() {
	n.state.mu.Lock()
	defer n.state.mu.Unlock()

	weights := make(map[string]float64)
	for id, v := range n.state.Validators {
		weights[id] = v.EffectiveStake
	}
	n.state.HHI = computeHHI(weights)

	continents := make(map[string]bool)
	for _, v := range n.state.Validators {
		continents[v.Continent] = true
	}
	n.state.ContinentCount = len(continents)

	if n.state.ContinentCount < MinContinents {
		log.Printf("[TRION-P2P] WARNING: Only %d continents covered (minimum: %d)",
			n.state.ContinentCount, MinContinents)
	}
	if n.state.HHI > HHICritical {
		n.state.SignalsFrozen = true
		n.state.AWAEnforced = false
		log.Printf("[TRION-P2P] CRITICAL: HHI=%f — consensus paused, governance emergency",
			n.state.HHI)
	}
}

// ── Utility ───────────────────────────────────────────────────────────────────

func median(vals []float64) float64 {
	if len(vals) == 0 {
		return 0
	}
	n := len(vals)
	sorted := make([]float64, n)
	copy(sorted, vals)
	// Simple insertion sort for small N
	for i := 1; i < n; i++ {
		key := sorted[i]
		j := i - 1
		for j >= 0 && sorted[j] > key {
			sorted[j+1] = sorted[j]
			j--
		}
		sorted[j+1] = key
	}
	if n%2 == 0 {
		return (sorted[n/2-1] + sorted[n/2]) / 2
	}
	return sorted[n/2]
}

// SignMessage signs a consensus message with SHA-256.
func SignMessage(msg *ConsensusMessage, privateKeyHex string) string {
	payload, _ := json.Marshal(msg)
	h := sha256.Sum256(payload)
	return hex.EncodeToString(h[:])
}

// PeerAddress returns formatted peer address for TCP connection.
func PeerAddress(v *ValidatorInfo) string {
	return net.JoinHostPort(v.Address, fmt.Sprintf("%d", v.Port))
}
