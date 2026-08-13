// TRION Protocol — P2P Go API Gateway
// Whitepaper Part 11 / Section 21 Tech Stack:
// "API gateway — all subsystems exposed via a single HTTP entry point."
//
// The gateway aggregates: health monitor, ANIMA crawler coordinator,
// validator mesh status, DW-BFT consensus results, and system diagnostics.
// All routes are non-blocking; long-running operations start goroutines.
//
// Author: TRION Protocol — Originator: Hudu Yusuf (Analys)
// License: CC0

package p2p

import (
	"encoding/json"
	"fmt"
	"log"
	"net/http"
	"time"
)

// APIGateway is the unified HTTP gateway for all P2P subsystems.
type APIGateway struct {
	port    int
	crawler *CrawlerPool
	mesh    *MeshNode
	server  *http.Server
}

// NewAPIGateway wires up the crawler pool and mesh node behind the gateway.
func NewAPIGateway(port int, crawler *CrawlerPool, mesh *MeshNode) *APIGateway {
	return &APIGateway{port: port, crawler: crawler, mesh: mesh}
}

// Start registers all routes and begins listening. Blocks until error.
func (g *APIGateway) Start() error {
	mux := http.NewServeMux()

	// ── Health & diagnostics ─────────────────────────────────────────────
	mux.HandleFunc("/", g.handleRoot)
	mux.HandleFunc("/health", g.handleHealth)
	mux.HandleFunc("/health/chains", g.handleHealthChains)
	mux.HandleFunc("/health/services", g.handleHealthServices)

	// ── ANIMA crawler coordinator ────────────────────────────────────────
	mux.HandleFunc("/anima/crawl", g.handleAnimaCrawl)
	mux.HandleFunc("/anima/agreement", g.handleAnimaAgreement)

	// ── Validator mesh ───────────────────────────────────────────────────
	mux.HandleFunc("/mesh/attest", g.handleMeshAttest)
	mux.HandleFunc("/mesh/quorum", g.handleMeshQuorum)

	// ── Consensus (DW-BFT) ───────────────────────────────────────────────
	mux.HandleFunc("/consensus/sigma", g.handleConsensusSigma)
	mux.HandleFunc("/consensus/hhi", g.handleConsensusHHI)

	g.server = &http.Server{
		Addr:         fmt.Sprintf(":%d", g.port),
		Handler:      mux,
		ReadTimeout:  15 * time.Second,
		WriteTimeout: 15 * time.Second,
	}

	log.Printf("[TRION gateway] P2P API gateway listening on port %d", g.port)
	log.Printf("[TRION gateway] Routes: /health /health/chains /anima/crawl /anima/agreement /mesh/attest /mesh/quorum /consensus/sigma /consensus/hhi")
	return g.server.ListenAndServe()
}

// Stop shuts down the gateway gracefully.
func (g *APIGateway) Stop() {
	if g.server != nil {
		g.server.Close()
	}
}

// ── Route Handlers ─────────────────────────────────────────────────────────

func (g *APIGateway) handleRoot(w http.ResponseWriter, r *http.Request) {
	w.Header().Set("Content-Type", "application/json")
	json.NewEncoder(w).Encode(map[string]interface{}{
		"name":    "TRION Protocol P2P Go Network Layer",
		"version": "1.0.0",
		"routes": []string{
			"GET  /health",
			"GET  /health/chains",
			"GET  /health/services",
			"GET  /anima/crawl?entity=<id>",
			"GET  /anima/agreement?entity=<id>",
			"POST /mesh/attest",
			"GET  /mesh/quorum?entity=<id>",
			"POST /consensus/sigma",
			"GET  /consensus/hhi",
		},
		"why": "goroutine model handles thousands of concurrent connections",
	})
}

func (g *APIGateway) handleHealth(w http.ResponseWriter, r *http.Request) {
	// Only check internal services for /health (fast path)
	internal := []Chain{
		{"FAISS_ANIMA", 0, "http://127.0.0.1:8000/health", "INTERNAL"},
		{"ORACLE_API", 0, "http://127.0.0.1:5000/health", "INTERNAL"},
	}
	health := RunHealthCheck(internal, 3*time.Second)
	w.Header().Set("Content-Type", "application/json")
	json.NewEncoder(w).Encode(health)
}

func (g *APIGateway) handleHealthChains(w http.ResponseWriter, r *http.Request) {
	health := RunHealthCheck(DefaultChains, 5*time.Second)
	w.Header().Set("Content-Type", "application/json")
	json.NewEncoder(w).Encode(health)
}

func (g *APIGateway) handleHealthServices(w http.ResponseWriter, r *http.Request) {
	services := []Chain{
		{"FAISS_ANIMA", 0, "http://127.0.0.1:8000/health", "INTERNAL"},
		{"ORACLE_API", 0, "http://127.0.0.1:5000/health", "INTERNAL"},
		{"ATTACK_WEBHOOK", 0, "http://127.0.0.1:6000/health", "INTERNAL"},
	}
	health := RunHealthCheck(services, 3*time.Second)
	w.Header().Set("Content-Type", "application/json")
	json.NewEncoder(w).Encode(health)
}

func (g *APIGateway) handleAnimaCrawl(w http.ResponseWriter, r *http.Request) {
	entityID := r.URL.Query().Get("entity")
	if entityID == "" {
		entityID = "trion_protocol"
	}
	signals := g.crawler.Run(entityID)
	ca := CrossSourceAgreement(signals)
	w.Header().Set("Content-Type", "application/json")
	json.NewEncoder(w).Encode(map[string]interface{}{
		"entity_id":              entityID,
		"signals_collected":      len(signals),
		"cross_source_agreement": ca,
		"crawlers_launched":      len(g.crawler.configs),
	})
}

func (g *APIGateway) handleAnimaAgreement(w http.ResponseWriter, r *http.Request) {
	entityID := r.URL.Query().Get("entity")
	if entityID == "" {
		entityID = "trion_protocol"
	}
	signals := g.crawler.Run(entityID)
	ca := CrossSourceAgreement(signals)
	w.Header().Set("Content-Type", "application/json")
	json.NewEncoder(w).Encode(map[string]interface{}{
		"entity_id":              entityID,
		"cross_source_agreement": ca,
		"signal_count":           len(signals),
	})
}

func (g *APIGateway) handleMeshAttest(w http.ResponseWriter, r *http.Request) {
	if r.Method != http.MethodPost {
		http.Error(w, "POST only", http.StatusMethodNotAllowed)
		return
	}
	var att BehavioralAttestation
	if err := json.NewDecoder(r.Body).Decode(&att); err != nil {
		http.Error(w, err.Error(), http.StatusBadRequest)
		return
	}
	g.mesh.Attest(att)
	w.WriteHeader(http.StatusAccepted)
	json.NewEncoder(w).Encode(map[string]string{"status": "attested"})
}

func (g *APIGateway) handleMeshQuorum(w http.ResponseWriter, r *http.Request) {
	entityID := r.URL.Query().Get("entity")
	count := g.mesh.AttestationCount(entityID)
	w.Header().Set("Content-Type", "application/json")
	json.NewEncoder(w).Encode(map[string]interface{}{
		"entity_id":         entityID,
		"attestation_count": count,
		"quorum_threshold":  3,
		"quorum_possible":   count >= 3,
	})
}

func (g *APIGateway) handleConsensusSigma(w http.ResponseWriter, r *http.Request) {
	if r.Method != http.MethodPost {
		http.Error(w, "POST only", http.StatusMethodNotAllowed)
		return
	}
	var payload struct {
		Messages   []*ConsensusMessage       `json:"messages"`
		Validators map[string]*ValidatorInfo  `json:"validators"`
		Volatility float64                    `json:"volatility"`
		DeltaBase  float64                    `json:"delta_base"`
	}
	if err := json.NewDecoder(r.Body).Decode(&payload); err != nil {
		http.Error(w, err.Error(), http.StatusBadRequest)
		return
	}
	if payload.DeltaBase == 0 {
		payload.DeltaBase = 0.10
	}
	result := ComputeSigma(payload.Messages, payload.Validators, payload.Volatility, payload.DeltaBase)
	w.Header().Set("Content-Type", "application/json")
	json.NewEncoder(w).Encode(result)
}

func (g *APIGateway) handleConsensusHHI(w http.ResponseWriter, r *http.Request) {
	// Demo: compute HHI over the example weight distribution
	weights := []float64{0.85, 0.72, 0.60, 0.45, 0.40, 0.35}
	hhi := MeshHHI(weights)
	w.Header().Set("Content-Type", "application/json")
	json.NewEncoder(w).Encode(map[string]interface{}{
		"hhi":       hhi,
		"tier":      HHITier(hhi),
		"threshold": map[string]int{"warning": HHIWarningThreshold, "danger": HHIDangerThreshold, "critical": HHICriticalThreshold},
	})
}
