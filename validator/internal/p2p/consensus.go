// TRION Protocol — DW-BFT Consensus Engine
// Whitepaper Channel 17 / Section 21: "Diversity-Weighted Byzantine Fault Tolerant
// consensus — Σ(t) = Σ_j [s_j·d_j·1(|v_j−v̄|≤δ(t))] / Σ_j [s_j·d_j]"
//
// d_j = 1 − corr(M_j, M̄)  — penalises coordinated Byzantine validators.
// δ(t) = δ_base · (1 + V(t)) — dynamic window that widens with volatility.
// HHI enforcement: if HHI > 4000 → SignalsFrozen = true, AWA = false.
//
// Author: TRION Protocol — Originator: Hudu Yusuf (Analys)
// License: CC0

package p2p

import (
	"context"
	"encoding/json"
	"fmt"
	"log"
	"math"
	"net/http"
	"sync"
	"time"
)

// ── Constants ──────────────────────────────────────────────────────────────

const (
	ConsensusDefaultPort  = 9000
	MaxPeers              = 500
	HeartbeatInterval     = 5 * time.Second
	ConsensusTimeout      = 30 * time.Second
	DiversityGamma        = 0.20 // γ_diversity — reward multiplier
	MinContinents         = 4
	HHIWarningThreshold   = 1500
	HHIDangerThreshold    = 2500
	HHICriticalThreshold  = 4000
	MaxSingleRegionShare  = 0.40
	MaxSingleJurisdShare  = 0.30
)

// ConsensusRound aggregates validator messages for one entity.
type ConsensusRound struct {
	EntityID  string
	Messages  []*ConsensusMessage
	StartedAt time.Time
	mu        sync.RWMutex
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

// ConsensusNode is a TRION DW-BFT validator P2P node.
type ConsensusNode struct {
	info    ValidatorInfo
	state   *NetworkState
	peers   map[string]*ValidatorInfo
	peersMu sync.RWMutex
	server  *http.Server
	ctx     context.Context
	cancel  context.CancelFunc
}

// NewConsensusNode creates a new DW-BFT consensus node.
func NewConsensusNode(info ValidatorInfo) *ConsensusNode {
	ctx, cancel := context.WithCancel(context.Background())
	state := &NetworkState{
		Validators:    make(map[string]*ValidatorInfo),
		ActiveRounds:  make(map[string]*ConsensusRound),
		AWAEnforced:   true,
		SignalsFrozen: false,
	}
	state.Validators[info.ID] = &info
	return &ConsensusNode{
		info:   info,
		state:  state,
		peers:  make(map[string]*ValidatorInfo),
		ctx:    ctx,
		cancel: cancel,
	}
}

// Start begins the DW-BFT node: HTTP server + heartbeat + consensus + HHI goroutines.
func (n *ConsensusNode) Start() error {
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

	go n.heartbeatLoop()
	go n.consensusLoop()
	go n.hhiMonitorLoop()

	log.Printf("[TRION-consensus] DW-BFT node %s starting on port %d", n.info.ID, n.info.Port)
	return n.server.ListenAndServe()
}

// Stop gracefully shuts down the consensus node.
func (n *ConsensusNode) Stop() {
	n.cancel()
	if n.server != nil {
		ctx, cancel := context.WithTimeout(context.Background(), 5*time.Second)
		defer cancel()
		n.server.Shutdown(ctx)
	}
}

// GetState returns a snapshot of the current network state.
func (n *ConsensusNode) GetState() (hhi float64, continents int, frozen bool) {
	n.state.mu.RLock()
	defer n.state.mu.RUnlock()
	return n.state.HHI, n.state.ContinentCount, n.state.SignalsFrozen
}

// ── DW-BFT Core Algorithms ─────────────────────────────────────────────────

// ComputeDiversityWeight computes d_j = 1 − corr(M_j, M̄).
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

// ComputeSigma computes Σ(t) = Σ_j [s_j·d_j·1(|v_j−v̄|≤δ(t))] / Σ_j [s_j·d_j]
// Dynamic consensus window: δ(t) = δ_base · (1 + V(t))
func ComputeSigma(
	messages []*ConsensusMessage,
	validators map[string]*ValidatorInfo,
	volatility, deltaBase float64,
) DiversityWeightedResult {
	if len(messages) == 0 {
		return DiversityWeightedResult{Sigma: 0.25, Bootstrap: true}
	}

	deltaT := deltaBase * (1.0 + volatility)

	// Compute median model outputs across all validators
	maxLen := 0
	for _, msg := range messages {
		if len(msg.ModelOutputs) > maxLen {
			maxLen = len(msg.ModelOutputs)
		}
	}
	medianOutputs := make([]float64, maxLen)
	for i := 0; i < maxLen; i++ {
		vals := make([]float64, 0, len(messages))
		for _, msg := range messages {
			if i < len(msg.ModelOutputs) {
				vals = append(vals, msg.ModelOutputs[i])
			}
		}
		medianOutputs[i] = calcMedian(vals)
	}

	// Compute median valuation
	valuations := make([]float64, len(messages))
	for i, msg := range messages {
		valuations[i] = msg.Valuation
	}
	medianVal := calcMedian(valuations)

	weights := make(map[string]float64)
	numerator, denominator := 0.0, 0.0
	includedCount, excludedCount := 0, 0

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

	sigma := 0.25 // bootstrap default
	if denominator > 0 {
		sigma = numerator / denominator
	}

	return DiversityWeightedResult{
		Sigma:            sigma,
		ValidatorWeights: weights,
		MedianValuation:  medianVal,
		DeltaT:           deltaT,
		HHI:              computeHHI(weights),
		IncludedCount:    includedCount,
		ExcludedCount:    excludedCount,
		Bootstrap:        false,
	}
}

// HHITier returns the concentration tier for a given HHI value.
func HHITier(hhi float64) string {
	switch {
	case hhi > HHICriticalThreshold:
		return "CRITICAL"
	case hhi > HHIDangerThreshold:
		return "DANGER"
	case hhi > HHIWarningThreshold:
		return "WARNING"
	default:
		return "HEALTHY"
	}
}

// ── HTTP Handlers ──────────────────────────────────────────────────────────

func (n *ConsensusNode) handleHandshake(w http.ResponseWriter, r *http.Request) {
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

func (n *ConsensusNode) handleConsensusSubmit(w http.ResponseWriter, r *http.Request) {
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
		round = &ConsensusRound{EntityID: msg.EntityID, StartedAt: time.Now()}
		n.state.ActiveRounds[msg.EntityID] = round
	}
	n.state.mu.Unlock()
	round.mu.Lock()
	round.Messages = append(round.Messages, &msg)
	round.mu.Unlock()
	w.WriteHeader(http.StatusAccepted)
}

func (n *ConsensusNode) handleConsensusResult(w http.ResponseWriter, r *http.Request) {
	entityID := r.URL.Query().Get("entity_id")
	volatility := 0.30
	if v := r.URL.Query().Get("volatility"); v != "" {
		fmt.Sscanf(v, "%f", &volatility)
	}
	n.state.mu.RLock()
	round, ok := n.state.ActiveRounds[entityID]
	n.state.mu.RUnlock()
	if !ok {
		http.Error(w, "no active round for entity", http.StatusNotFound)
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

func (n *ConsensusNode) handlePeers(w http.ResponseWriter, r *http.Request) {
	n.peersMu.RLock()
	defer n.peersMu.RUnlock()
	json.NewEncoder(w).Encode(n.peers)
}

func (n *ConsensusNode) handleHealth(w http.ResponseWriter, r *http.Request) {
	n.state.mu.RLock()
	defer n.state.mu.RUnlock()
	json.NewEncoder(w).Encode(map[string]interface{}{
		"id":              n.info.ID,
		"validator_count": len(n.state.Validators),
		"hhi":             n.state.HHI,
		"hhi_tier":        HHITier(n.state.HHI),
		"continents":      n.state.ContinentCount,
		"awa_enforced":    n.state.AWAEnforced,
		"signals_frozen":  n.state.SignalsFrozen,
	})
}

func (n *ConsensusNode) handleHHI(w http.ResponseWriter, r *http.Request) {
	n.state.mu.RLock()
	defer n.state.mu.RUnlock()
	json.NewEncoder(w).Encode(map[string]interface{}{
		"hhi":  n.state.HHI,
		"tier": HHITier(n.state.HHI),
	})
}

// ── Background Goroutines ──────────────────────────────────────────────────

func (n *ConsensusNode) heartbeatLoop() {
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

func (n *ConsensusNode) broadcastHeartbeat() {
	n.peersMu.RLock()
	peers := make([]*ValidatorInfo, 0, len(n.peers))
	for _, p := range n.peers {
		peers = append(peers, p)
	}
	n.peersMu.RUnlock()

	for _, peer := range peers {
		go func(p *ValidatorInfo) {
			addr := fmt.Sprintf("http://%s:%d/v1/handshake", p.Address, p.Port)
			client := &http.Client{Timeout: 2 * time.Second}
			resp, err := client.Post(addr, "application/json", nil)
			if err != nil {
				return
			}
			resp.Body.Close()
		}(peer)
	}
}

func (n *ConsensusNode) consensusLoop() {
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

func (n *ConsensusNode) cleanupExpiredRounds() {
	n.state.mu.Lock()
	defer n.state.mu.Unlock()
	cutoff := time.Now().Add(-ConsensusTimeout)
	for id, round := range n.state.ActiveRounds {
		if round.StartedAt.Before(cutoff) {
			delete(n.state.ActiveRounds, id)
		}
	}
}

func (n *ConsensusNode) hhiMonitorLoop() {
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

func (n *ConsensusNode) recomputeHHI() {
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
		log.Printf("[TRION-consensus] WARNING: Only %d continents (minimum: %d)",
			n.state.ContinentCount, MinContinents)
	}
	if n.state.HHI > HHICriticalThreshold {
		n.state.SignalsFrozen = true
		n.state.AWAEnforced = false
		log.Printf("[TRION-consensus] CRITICAL: HHI=%.0f — consensus paused", n.state.HHI)
	}
}

// ── Utility ────────────────────────────────────────────────────────────────

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

func calcMedian(vals []float64) float64 {
	if len(vals) == 0 {
		return 0
	}
	n := len(vals)
	sorted := make([]float64, n)
	copy(sorted, vals)
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
