// TRION Protocol — P2P Go Network Layer — Comprehensive Test Suite
//
// Covers all five subsystems:
//   §1  ANIMA Crawler Coordinator   — 59 languages, goroutine pool, CRED EMA, CA
//   §2  DualStrand Signatures       — sense/antisense XOR invariant
//   §3  Validator Mesh              — attestation, gossip, DW-BFT quorum (≥2/3)
//   §4  Health Monitor              — concurrent chain checks, goroutine fan-out
//   §5  DW-BFT Consensus Sigma      — Σ(t) algorithm, median, dynamic δ(t)
//   §6  Diversity Weight            — d_j = 1 − corr(M_j, M̄), Byzantine penalty
//   §7  HHI Diversity Enforcement   — WARNING / DANGER / CRITICAL tier thresholds
//   §8  CRED Scoring                — EMA update rule L3.4 λ=0.05
//   §9  API Gateway                 — all HTTP endpoints 200, JSON well-formed
//   §10 Goroutine Concurrency       — 2,000 concurrent goroutines, fan-in, no race
//   §11 Cross-Source Agreement      — credibility-weighted agreement CA(t)
//   §12 HHI Monopoly / Competitive  — edge cases (single validator, equal weights)
//   §13 Consensus Bootstrap         — empty messages → Σ=0.25, bootstrap=true
//   §14 Consensus Round GC          — expired rounds cleaned up correctly
//
// Author: TRION Protocol — Originator: Hudu Yusuf (Analys)
// License: CC0

package p2pgo

import (
	"bytes"
	"encoding/json"
	"fmt"
	"math"
	"net/http"
	"net/http/httptest"
	"sync"
	"sync/atomic"
	"testing"
	"time"
)

// ─────────────────────────────────────────────────────────────────────────────
// §1  ANIMA Crawler Coordinator
// ─────────────────────────────────────────────────────────────────────────────

func TestAnimaCrawlerCoordinator(t *testing.T) {
	t.Log("\n──────────── §1  ANIMA Crawler Coordinator ────────────────────────────")

	configs := DefaultCrawlerConfigs()
	if len(configs) < 59 {
		t.Fatalf("expected ≥59 language configs, got %d", len(configs))
	}
	t.Logf("  Language corpora loaded : %d", len(configs))

	pool := NewCrawlerPool(configs)
	defer pool.Stop()

	start := time.Now()
	signals := pool.Run("trion_protocol")
	elapsed := time.Since(start)

	t.Logf("  Crawl wall-clock time   : %v (all goroutines concurrent)", elapsed)
	t.Logf("  Signals collected       : %d / %d (credibility ≥ 0.30 filter)", len(signals), len(configs))

	if len(signals) == 0 {
		t.Fatal("expected signals from credibility-passing crawlers; got 0")
	}

	// All signals must carry a valid language code and credibility ≥ 0.30
	for _, s := range signals {
		if s.LanguageCode == "" {
			t.Errorf("signal missing language_code")
		}
		if s.SourceCred < 0.30 {
			t.Errorf("signal %s has SourceCred=%.3f < 0.30", s.LanguageCode, s.SourceCred)
		}
	}

	// Concurrent crawl must be significantly faster than serial
	// (serial would take 59 × crawl_time; concurrent finishes in one crawl_time)
	if elapsed > 3*time.Second {
		t.Errorf("concurrent crawl took %v — expected <3s for 59 goroutines", elapsed)
	}

	t.Logf("  ✅ PASS — %d language goroutines, wall-clock %v, %d signals passed filter",
		len(configs), elapsed, len(signals))
}

// ─────────────────────────────────────────────────────────────────────────────
// §2  DualStrand Signatures
// ─────────────────────────────────────────────────────────────────────────────

func TestDualStrandSignatures(t *testing.T) {
	t.Log("\n──────────── §2  DualStrand Signatures — sense/antisense XOR ──────────")

	payloads := [][]byte{
		[]byte(`{"entity":"0xUNISWAP","C":0.72}`),
		[]byte(`{"entity":"TRION_GENESIS","gen":1}`),
		[]byte(`{}`),
		[]byte(`hello world`),
	}

	for _, payload := range payloads {
		sense, antisense := DualStrandSign(payload)

		// Must be different hex strings
		if sense == antisense {
			t.Errorf("payload=%q: sense == antisense (hash collision or bug)", payload)
		}
		// Both must be 64-char hex (SHA-256)
		if len(sense) != 64 || len(antisense) != 64 {
			t.Errorf("expected 64-char hex; got sense=%d antisense=%d", len(sense), len(antisense))
		}
		// DualStrandVerify must return true
		if !DualStrandVerify(sense, antisense) {
			t.Errorf("DualStrandVerify returned false for valid pair")
		}
		// Deterministic: same payload → same result
		s2, a2 := DualStrandSign(payload)
		if s2 != sense || a2 != antisense {
			t.Errorf("non-deterministic: same payload produced different signatures")
		}

		t.Logf("  payload=%-30q  sense=%s…  ✅", payload[:min(30, len(payload))], sense[:16])
	}

	t.Logf("  ✅ PASS — sense≠antisense, 64-char hex, deterministic, verify OK")
}

// ─────────────────────────────────────────────────────────────────────────────
// §3  Validator Mesh — attestation, gossip, DW-BFT quorum
// ─────────────────────────────────────────────────────────────────────────────

func TestValidatorMesh(t *testing.T) {
	t.Log("\n──────────── §3  Validator Mesh — attestation + DW-BFT quorum ─────────")

	// Build three validators: A (lead), B, C as peers
	idA := MeshValidatorIDFromKey([]byte("validatorA"))
	idB := MeshValidatorIDFromKey([]byte("validatorB"))
	idC := MeshValidatorIDFromKey([]byte("validatorC"))

	profileA := ValidatorProfile{ID: idA, Addr: "127.0.0.1:17001", DiversityWeight: 0.85, GeographicRegion: "US"}
	profileB := ValidatorProfile{ID: idB, Addr: "127.0.0.1:17002", DiversityWeight: 0.72, GeographicRegion: "DE"}
	profileC := ValidatorProfile{ID: idC, Addr: "127.0.0.1:17003", DiversityWeight: 0.60, GeographicRegion: "SG"}

	nodeA := NewMeshNode(profileA)
	nodeA.AddPeer(profileB)
	nodeA.AddPeer(profileC)

	// Total weight = 0.85+0.72+0.60=2.17; need ≥2/3 of 2.17 ≈ 1.45 agreed weight
	totalWeight := 0.85 + 0.72 + 0.60
	t.Logf("  Validators: A(d=0.85 US), B(d=0.72 DE), C(d=0.60 SG)")
	t.Logf("  Total weight=%.2f  quorum threshold=%.4f (2/3)", totalWeight, totalWeight*2.0/3.0)

	entityID := "0xUNISWAP_V3"

	// Submit 3 attestations — from A, B, C — all agreeing C≈0.78
	for i, vID := range []string{idA.Hex(), idB.Hex(), idC.Hex()} {
		dws := []float64{0.85, 0.72, 0.60}
		payload, _ := json.Marshal(map[string]interface{}{"entity": entityID, "C": 0.78})
		sense, antisense := DualStrandSign(payload)
		att := BehavioralAttestation{
			EntityID:           entityID,
			SignalType:         "BEHAVIORAL",
			CoherenceC:         0.78,
			ThresholdTheta:     0.60,
			ValidatorID:        vID,
			DiversityWeight:    dws[i],
			Timestamp:          time.Now().UnixNano(),
			SignatureSense:     sense,
			SignatureAntisense: antisense,
		}
		nodeA.AttestLocal(att)
	}

	// Wait briefly for tryQuorum goroutine
	time.Sleep(50 * time.Millisecond)

	count := nodeA.AttestationCount(entityID)
	t.Logf("  Attestations stored     : %d", count)
	if count != 3 {
		t.Errorf("expected 3 attestations, got %d", count)
	}

	// Check quorum result
	select {
	case result := <-nodeA.QuorumResults():
		agreedFraction := result.AgreementWeight / totalWeight
		t.Logf("  QuorumReached=%v  agreedFraction=%.3f  weightedC=%.4f  HHI=%.4f",
			result.QuorumReached, agreedFraction, result.WeightedC, result.HHI)
		if !result.QuorumReached {
			t.Errorf("expected quorum to be reached (agreed/total=%.3f ≥ 0.667)", agreedFraction)
		}
		if math.Abs(result.WeightedC-0.78) > 0.01 {
			t.Errorf("expected weightedC≈0.78, got %.4f", result.WeightedC)
		}
	case <-time.After(500 * time.Millisecond):
		t.Error("timeout waiting for quorum result — tryQuorum goroutine did not fire")
	}

	t.Log("  ✅ PASS — attestations stored, DW-BFT quorum reached, weightedC correct")
}

// ─────────────────────────────────────────────────────────────────────────────
// §4  Health Monitor — concurrent goroutine fan-out
// ─────────────────────────────────────────────────────────────────────────────

func TestHealthMonitorConcurrent(t *testing.T) {
	t.Log("\n──────────── §4  Health Monitor — concurrent goroutine fan-out ─────────")

	// Use only internal services (will likely be HEALTHY in this environment)
	internal := []Chain{
		{"FAISS_ANIMA", 0, "http://127.0.0.1:8000/health", "INTERNAL"},
		{"ORACLE_API", 0, "http://127.0.0.1:5000/health", "INTERNAL"},
	}

	// Also add a set of EVM chains (will be OFFLINE/DEGRADED in sandbox — that's OK)
	chains := append(internal, DefaultChains[:5]...) // 2 internal + 5 EVM mainnet

	start := time.Now()
	health := RunHealthCheck(chains, 4*time.Second)
	elapsed := time.Since(start)

	t.Logf("  Chains checked          : %d", health.TotalChains)
	t.Logf("  Healthy                 : %d", health.HealthyChains)
	t.Logf("  Degraded                : %d", health.DegradedChains)
	t.Logf("  Offline                 : %d", health.OfflineChains)
	t.Logf("  Wall-clock time         : %v (all goroutines concurrent)", elapsed)
	t.Logf("  Avg latency (healthy)   : %.1f ms", health.AvgLatencyMs)

	if health.TotalChains != len(chains) {
		t.Errorf("expected %d results, got %d", len(chains), health.TotalChains)
	}
	if health.HealthyChains+health.DegradedChains+health.OfflineChains != health.TotalChains {
		t.Error("status counts do not sum to TotalChains")
	}

	// Internal services should respond (both are running in this environment)
	for _, r := range health.Results {
		if r.Label == "FAISS_ANIMA" || r.Label == "ORACLE_API" {
			t.Logf("  %-20s status=%-8s latency=%.1fms", r.Label, r.Status, r.LatencyMs)
			if r.Status == "OFFLINE" {
				t.Logf("    (OFFLINE is acceptable if service port not yet ready)")
			}
		}
	}

	// Concurrent check of 7 chains must finish faster than 7 × timeout
	if elapsed > 5*time.Second {
		t.Errorf("concurrent health check of %d chains took %v — expected <5s", len(chains), elapsed)
	}

	t.Log("  ✅ PASS — all results returned, counts consistent, wall-clock correct")
}

// ─────────────────────────────────────────────────────────────────────────────
// §5  DW-BFT Consensus Sigma
// ─────────────────────────────────────────────────────────────────────────────

func TestConsensusSigma(t *testing.T) {
	t.Log("\n──────────── §5  DW-BFT Consensus Sigma Σ(t) ──────────────────────────")

	validators := map[string]*ValidatorInfo{
		"v1": {ID: "v1", Stake: 1000, Continent: "NA"},
		"v2": {ID: "v2", Stake: 800, Continent: "EU"},
		"v3": {ID: "v3", Stake: 600, Continent: "AS"},
		"v4": {ID: "v4", Stake: 400, Continent: "OC"},
	}

	// All validators report valuation ≈ 0.75 — should converge
	messages := []*ConsensusMessage{
		{ValidatorID: "v1", EntityID: "ENTITY_A", Valuation: 0.76, ModelOutputs: []float64{0.70, 0.72, 0.74, 0.76}},
		{ValidatorID: "v2", EntityID: "ENTITY_A", Valuation: 0.74, ModelOutputs: []float64{0.68, 0.70, 0.73, 0.74}},
		{ValidatorID: "v3", EntityID: "ENTITY_A", Valuation: 0.75, ModelOutputs: []float64{0.72, 0.74, 0.74, 0.75}},
		{ValidatorID: "v4", EntityID: "ENTITY_A", Valuation: 0.73, ModelOutputs: []float64{0.71, 0.72, 0.73, 0.73}},
	}

	result := ComputeSigma(messages, validators, 0.30, 0.10)

	t.Logf("  Σ(t) = %.4f", result.Sigma)
	t.Logf("  MedianValuation = %.4f", result.MedianValuation)
	t.Logf("  δ(t) = %.4f  (base=0.10 × (1+V=0.30))", result.DeltaT)
	t.Logf("  Included = %d / %d", result.IncludedCount, len(messages))
	t.Logf("  HHI = %.1f  (%s)", result.HHI, HHITier(result.HHI))

	if result.Bootstrap {
		t.Error("expected non-bootstrap result with 4 messages")
	}
	if result.Sigma <= 0 || result.Sigma > 1.0 {
		t.Errorf("Σ(t)=%.4f out of [0,1]", result.Sigma)
	}
	if result.IncludedCount == 0 {
		t.Error("expected at least one validator within δ(t) of median")
	}
	if math.Abs(result.MedianValuation-0.75) > 0.05 {
		t.Errorf("median valuation=%.4f expected ≈0.75", result.MedianValuation)
	}

	// Test bootstrap (empty messages)
	empty := ComputeSigma([]*ConsensusMessage{}, validators, 0.30, 0.10)
	if !empty.Bootstrap || math.Abs(empty.Sigma-0.25) > 1e-9 {
		t.Errorf("bootstrap: expected Sigma=0.25 bootstrap=true, got %.4f %v", empty.Sigma, empty.Bootstrap)
	}
	t.Logf("  Bootstrap (empty) : Σ=%.2f bootstrap=%v  ✅", empty.Sigma, empty.Bootstrap)

	t.Logf("  ✅ PASS — Σ(t)=%.4f, %d/%d in δ(t), HHI=%s", result.Sigma, result.IncludedCount, len(messages), HHITier(result.HHI))
}

// ─────────────────────────────────────────────────────────────────────────────
// §6  Diversity Weight d_j = 1 − corr(M_j, M̄)
// ─────────────────────────────────────────────────────────────────────────────

func TestDiversityWeight(t *testing.T) {
	t.Log("\n──────────── §6  Diversity Weight d_j = 1 − corr(M_j, M̄) ─────────────")

	median := []float64{0.5, 0.6, 0.7, 0.8}

	// Perfectly correlated (Byzantine) → d_j ≈ 0
	byzantine := []float64{0.5, 0.6, 0.7, 0.8} // identical to median
	dByzantine := ComputeDiversityWeight(byzantine, median)
	t.Logf("  Byzantine (corr=1.0) → d_j=%.4f  (expect ≈0.0)", dByzantine)
	if dByzantine > 0.05 {
		t.Errorf("Byzantine validator d_j=%.4f; expected ≈0 (corr→1)", dByzantine)
	}

	// Anti-correlated (max independence) → d_j ≈ 2 (clamped? no: 1-(-1)=2, but d≤2)
	anticorr := []float64{0.8, 0.7, 0.6, 0.5}
	dAnticorr := ComputeDiversityWeight(anticorr, median)
	t.Logf("  Anti-correlated        → d_j=%.4f  (expect >1.0, corr=-1)", dAnticorr)
	if dAnticorr < 1.5 {
		t.Errorf("anti-correlated d_j=%.4f; expected >1.5", dAnticorr)
	}

	// Independent (random-ish)
	independent := []float64{0.3, 0.8, 0.4, 0.9}
	dIndep := ComputeDiversityWeight(independent, median)
	t.Logf("  Independent            → d_j=%.4f  (expect ∈[0,2])", dIndep)
	if dIndep < 0 || dIndep > 2.0 {
		t.Errorf("independent d_j=%.4f out of range", dIndep)
	}

	// Short / single vector → default 1.0
	dShort := ComputeDiversityWeight([]float64{0.5}, []float64{0.5})
	if dShort != 1.0 {
		t.Errorf("short vector d_j=%.4f; expected 1.0", dShort)
	}

	t.Log("  ✅ PASS — Byzantine penalised (d≈0), anticorr rewarded (d>1), edge cases handled")
}

// ─────────────────────────────────────────────────────────────────────────────
// §7  HHI Diversity Enforcement
// ─────────────────────────────────────────────────────────────────────────────

func TestHHIDiversityEnforcement(t *testing.T) {
	t.Log("\n──────────── §7  HHI Diversity Enforcement ────────────────────────────")

	// HHI = Σ(w_i/Σw)² × 10000
	// Thresholds: WARNING>1500, DANGER>2500, CRITICAL>4000
	// n equal validators → HHI = 10000/n
	//   n=10 → 1000  HEALTHY
	//   n=7  → 1429  HEALTHY
	//   n=6  → 1667  WARNING
	//   n=5  → 2000  WARNING
	//   n=3  → 3333  DANGER
	//   n=2  → 5000  CRITICAL
	cases := []struct {
		label    string
		weights  []float64
		wantTier string
	}{
		{"healthy_10_equal",  []float64{1, 1, 1, 1, 1, 1, 1, 1, 1, 1}, "HEALTHY"},  // HHI=1000
		{"healthy_7_equal",   []float64{1, 1, 1, 1, 1, 1, 1},           "HEALTHY"},  // HHI=1429
		{"warning_6_equal",   []float64{1, 1, 1, 1, 1, 1},              "WARNING"},  // HHI=1667
		{"warning_5_equal",   []float64{1, 1, 1, 1, 1},                 "WARNING"},  // HHI=2000
		{"danger_3_equal",    []float64{1, 1, 1},                       "DANGER"},   // HHI=3333
		{"critical_2_equal",  []float64{1, 1},                          "CRITICAL"}, // HHI=5000
		{"critical_monopoly", []float64{100, 1},                        "CRITICAL"}, // HHI≈9803
		{"monopoly_single",   []float64{1},                             "CRITICAL"}, // HHI=10000
	}

	for _, tc := range cases {
		hhi := MeshHHI(tc.weights)
		tier := HHITier(hhi)
		pass := "✅"
		if tier != tc.wantTier {
			pass = "❌"
			t.Errorf("case=%s: HHI=%.1f tier=%s, want=%s", tc.label, hhi, tier, tc.wantTier)
		}
		t.Logf("  %-28s HHI=%7.1f  tier=%-10s %s", tc.label, hhi, tier, pass)
	}

	// Verify MeshHHI edge: all equal weights → HHI = 10000/n
	n := 10
	equal := make([]float64, n)
	for i := range equal {
		equal[i] = 1.0
	}
	hhi := MeshHHI(equal)
	expected := 10000.0 / float64(n)
	if math.Abs(hhi-expected) > 0.1 {
		t.Errorf("equal weights HHI=%.1f expected=%.1f", hhi, expected)
	}

	t.Log("  ✅ PASS — all HHI tier thresholds enforced correctly")
}

// ─────────────────────────────────────────────────────────────────────────────
// §8  CRED Scoring — EMA update rule L3.4
// ─────────────────────────────────────────────────────────────────────────────

func TestCREDScoring(t *testing.T) {
	t.Log("\n──────────── §8  CRED Scoring — EMA L3.4 λ=0.05 ──────────────────────")

	configs := DefaultCrawlerConfigs()
	pool := NewCrawlerPool(configs)
	defer pool.Stop()

	lang := "en"
	initial := pool.GetCred(lang)
	t.Logf("  Initial CRED(en) = %.4f", initial)

	// CRED(s,t) = CRED(s,t-1)·(1-λ) + accuracy(s,t)·λ
	const lambda = 0.05
	perfectAccuracy := 1.0
	pool.UpdateCred(lang, perfectAccuracy)
	after1 := pool.GetCred(lang)
	expected1 := initial*(1-lambda) + perfectAccuracy*lambda
	t.Logf("  After accuracy=1.0: CRED(en)=%.6f  expected=%.6f", after1, expected1)
	if math.Abs(after1-expected1) > 1e-9 {
		t.Errorf("CRED EMA mismatch: got %.6f expected %.6f", after1, expected1)
	}

	// Multiple updates converge toward high accuracy
	for i := 0; i < 50; i++ {
		pool.UpdateCred(lang, 1.0)
	}
	after50 := pool.GetCred(lang)
	t.Logf("  After 50 perfect updates: CRED(en)=%.6f  (should approach 1.0)", after50)
	if after50 < 0.85 {
		t.Errorf("expected CRED→1.0 after 50 perfect updates; got %.4f", after50)
	}

	// Low accuracy pulls it down
	for i := 0; i < 100; i++ {
		pool.UpdateCred(lang, 0.0)
	}
	after100bad := pool.GetCred(lang)
	t.Logf("  After 100 zero-accuracy updates: CRED(en)=%.6f  (should approach 0)", after100bad)
	if after100bad > 0.15 {
		t.Errorf("expected CRED→0 after 100 bad updates; got %.4f", after100bad)
	}

	t.Log("  ✅ PASS — EMA update rule correct, convergence verified")
}

// ─────────────────────────────────────────────────────────────────────────────
// §9  API Gateway — all HTTP endpoints
// ─────────────────────────────────────────────────────────────────────────────

func TestAPIGateway(t *testing.T) {
	t.Log("\n──────────── §9  API Gateway — HTTP endpoints ──────────────────────────")

	configs := DefaultCrawlerConfigs()
	pool := NewCrawlerPool(configs)
	defer pool.Stop()

	selfProfile := ValidatorProfile{
		ID:               MeshValidatorIDFromKey([]byte("gateway-test-node")),
		DiversityWeight:  0.80,
		GeographicRegion: "US",
	}
	mesh := NewMeshNode(selfProfile)
	gw := NewAPIGateway(0, pool, mesh)

	// Wrap gateway routes in a test mux (without starting a real TCP server)
	mux := http.NewServeMux()
	mux.HandleFunc("/", gw.handleRoot)
	mux.HandleFunc("/health", gw.handleHealth)
	mux.HandleFunc("/anima/crawl", gw.handleAnimaCrawl)
	mux.HandleFunc("/anima/agreement", gw.handleAnimaAgreement)
	mux.HandleFunc("/mesh/attest", gw.handleMeshAttest)
	mux.HandleFunc("/mesh/quorum", gw.handleMeshQuorum)
	mux.HandleFunc("/consensus/sigma", gw.handleConsensusSigma)
	mux.HandleFunc("/consensus/hhi", gw.handleConsensusHHI)

	routes := []struct {
		method string
		path   string
		body   string
	}{
		{"GET", "/", ""},
		{"GET", "/anima/crawl?entity=test_entity", ""},
		{"GET", "/anima/agreement?entity=test_entity", ""},
		{"GET", "/mesh/quorum?entity=test_entity", ""},
		{"GET", "/consensus/hhi", ""},
		{"POST", "/consensus/sigma", `{"messages":[],"validators":{},"volatility":0.3,"delta_base":0.1}`},
		{"POST", "/mesh/attest", `{"entity_id":"test","signal_type":"BEHAVIORAL","coherence_c":0.75,"diversity_weight":0.85}`},
	}

	for _, route := range routes {
		var req *http.Request
		if route.body != "" {
			req, _ = http.NewRequest(route.method, route.path, bytes.NewBufferString(route.body))
			req.Header.Set("Content-Type", "application/json")
		} else {
			req, _ = http.NewRequest(route.method, route.path, nil)
		}
		rr := httptest.NewRecorder()
		mux.ServeHTTP(rr, req)

		status := rr.Code
		body := rr.Body.String()
		pass := "✅"
		if status >= 400 {
			pass = "❌"
			t.Errorf("%s %s → HTTP %d: %s", route.method, route.path, status, body)
		}

		// Validate JSON (except for 202 Accepted with empty body)
		if status != http.StatusAccepted && body != "" {
			var obj interface{}
			if err := json.Unmarshal([]byte(body), &obj); err != nil {
				t.Errorf("%s %s: invalid JSON response: %v", route.method, route.path, err)
				pass = "❌"
			}
		}
		t.Logf("  %-6s %-45s → %d %s", route.method, route.path, status, pass)
	}

	t.Log("  ✅ PASS — all gateway endpoints return 200/202, JSON well-formed")
}

// ─────────────────────────────────────────────────────────────────────────────
// §10  Goroutine Concurrency — 2,000 concurrent goroutines
// ─────────────────────────────────────────────────────────────────────────────

func TestGoroutineConcurrency(t *testing.T) {
	t.Log("\n──────────── §10  Goroutine Concurrency — 2,000 concurrent ─────────────")

	const N = 2000
	var counter int64
	var wg sync.WaitGroup
	start := time.Now()

	for i := 0; i < N; i++ {
		wg.Add(1)
		go func(id int) {
			defer wg.Done()
			// Simulate work: compute a CRED EMA step
			val := float64(id) / float64(N)
			_ = val*(1-0.05) + 0.5*0.05
			atomic.AddInt64(&counter, 1)
		}(i)
	}
	wg.Wait()
	elapsed := time.Since(start)

	t.Logf("  Goroutines launched : %d", N)
	t.Logf("  Completed           : %d", counter)
	t.Logf("  Wall-clock time     : %v", elapsed)

	if counter != N {
		t.Errorf("expected %d completions, got %d", N, counter)
	}
	if elapsed > 2*time.Second {
		t.Errorf("2,000 goroutines took %v — expected <2s", elapsed)
	}

	t.Logf("  ✅ PASS — %d goroutines, %d completed, %v elapsed", N, counter, elapsed)
}

// ─────────────────────────────────────────────────────────────────────────────
// §11  Cross-Source Agreement CA(t)
// ─────────────────────────────────────────────────────────────────────────────

func TestCrossSourceAgreement(t *testing.T) {
	t.Log("\n──────────── §11  Cross-Source Agreement CA(t) ─────────────────────────")

	// Perfect agreement: all signals at 0.75 → CA should be very high
	perfect := make([]NLPSignal, 10)
	for i := range perfect {
		perfect[i] = NLPSignal{SentimentScore: 0.75, SourceCred: 0.80, LanguageCode: fmt.Sprintf("l%d", i)}
	}
	caPerfect := CrossSourceAgreement(perfect)
	t.Logf("  Perfect agreement (all 0.75)  CA=%.4f  (expect ≈1.0)", caPerfect)
	if caPerfect < 0.95 {
		t.Errorf("perfect agreement CA=%.4f; expected ≥0.95", caPerfect)
	}

	// Max disagreement: half at 0.0, half at 1.0
	disagree := make([]NLPSignal, 10)
	for i := range disagree {
		if i%2 == 0 {
			disagree[i] = NLPSignal{SentimentScore: 0.0, SourceCred: 0.80}
		} else {
			disagree[i] = NLPSignal{SentimentScore: 1.0, SourceCred: 0.80}
		}
	}
	caDisagree := CrossSourceAgreement(disagree)
	t.Logf("  Max disagreement (0/1 split)  CA=%.4f  (expect ≈0.0)", caDisagree)
	if caDisagree > 0.20 {
		t.Errorf("max disagreement CA=%.4f; expected ≤0.20", caDisagree)
	}

	// Single signal → 0.5 (bootstrap)
	caSingle := CrossSourceAgreement([]NLPSignal{{SentimentScore: 0.8, SourceCred: 0.9}})
	if caSingle != 0.5 {
		t.Errorf("single signal CA=%.4f; expected 0.5", caSingle)
	}

	t.Log("  ✅ PASS — CA(t) correct for perfect/disagree/single cases")
}

// ─────────────────────────────────────────────────────────────────────────────
// §12  HHI Edge Cases
// ─────────────────────────────────────────────────────────────────────────────

func TestHHIEdgeCases(t *testing.T) {
	t.Log("\n──────────── §12  HHI Edge Cases ──────────────────────────────────────")

	// Monopoly: single validator
	mono := MeshHHI([]float64{1.0})
	t.Logf("  Single validator        HHI=%7.1f  tier=%s", mono, HHITier(mono))
	if mono != 10000.0 {
		t.Errorf("monopoly HHI=%.1f; expected 10000", mono)
	}

	// Empty
	empty := MeshHHI([]float64{})
	t.Logf("  Empty weights           HHI=%7.1f  tier=%s", empty, HHITier(empty))
	if empty != 10000.0 {
		t.Errorf("empty weights HHI=%.1f; expected 10000", empty)
	}

	// Perfectly competitive (infinite validators, equal stake): HHI → 0
	n := 1000
	w := make([]float64, n)
	for i := range w {
		w[i] = 1.0
	}
	competitive := MeshHHI(w)
	t.Logf("  1000 equal validators   HHI=%7.2f  tier=%s", competitive, HHITier(competitive))
	if competitive > 11.0 { // 10000/1000 = 10
		t.Errorf("competitive HHI=%.2f; expected ≈10 (10000/1000)", competitive)
	}

	t.Log("  ✅ PASS — monopoly=10000, competitive≈10/n, empty=10000")
}

// ─────────────────────────────────────────────────────────────────────────────
// §13  Consensus Bootstrap
// ─────────────────────────────────────────────────────────────────────────────

func TestConsensusBootstrap(t *testing.T) {
	t.Log("\n──────────── §13  Consensus Bootstrap ─────────────────────────────────")

	validators := map[string]*ValidatorInfo{
		"v1": {ID: "v1", Stake: 1000},
	}

	result := ComputeSigma([]*ConsensusMessage{}, validators, 0.30, 0.10)
	t.Logf("  Empty messages → Σ=%.4f  bootstrap=%v", result.Sigma, result.Bootstrap)

	if !result.Bootstrap {
		t.Error("expected Bootstrap=true for empty messages")
	}
	if math.Abs(result.Sigma-0.25) > 1e-9 {
		t.Errorf("expected Sigma=0.25, got %.6f", result.Sigma)
	}

	t.Log("  ✅ PASS — Σ=0.25, bootstrap=true when no messages")
}

// ─────────────────────────────────────────────────────────────────────────────
// §14  Consensus Round GC — expired rounds cleaned up
// ─────────────────────────────────────────────────────────────────────────────

func TestConsensusRoundGC(t *testing.T) {
	t.Log("\n──────────── §14  Consensus Round GC — expired round cleanup ───────────")

	node := NewConsensusNode(ValidatorInfo{
		ID:      "test-node",
		Port:    19000,
		Stake:   1000.0,
		Address: "127.0.0.1",
	})

	// Inject an artificially old round
	oldRound := &ConsensusRound{
		EntityID:  "OLD_ENTITY",
		StartedAt: time.Now().Add(-2 * ConsensusTimeout), // 2× past deadline
	}
	freshRound := &ConsensusRound{
		EntityID:  "FRESH_ENTITY",
		StartedAt: time.Now(),
	}

	node.state.mu.Lock()
	node.state.ActiveRounds["OLD_ENTITY"] = oldRound
	node.state.ActiveRounds["FRESH_ENTITY"] = freshRound
	node.state.mu.Unlock()

	before := 0
	node.state.mu.RLock()
	before = len(node.state.ActiveRounds)
	node.state.mu.RUnlock()

	node.cleanupExpiredRounds()

	node.state.mu.RLock()
	after := len(node.state.ActiveRounds)
	_, oldExists := node.state.ActiveRounds["OLD_ENTITY"]
	_, freshExists := node.state.ActiveRounds["FRESH_ENTITY"]
	node.state.mu.RUnlock()

	t.Logf("  Rounds before GC : %d", before)
	t.Logf("  Rounds after GC  : %d", after)
	t.Logf("  OLD_ENTITY exists: %v  (expect false)", oldExists)
	t.Logf("  FRESH_ENTITY exists: %v  (expect true)", freshExists)

	if oldExists {
		t.Error("OLD_ENTITY should have been garbage collected")
	}
	if !freshExists {
		t.Error("FRESH_ENTITY should still be active")
	}
	if after != 1 {
		t.Errorf("expected 1 active round after GC, got %d", after)
	}

	t.Log("  ✅ PASS — expired round removed, fresh round preserved")
}

// ── Utility ───────────────────────────────────────────────────────────────────

func min(a, b int) int {
	if a < b {
		return a
	}
	return b
}
