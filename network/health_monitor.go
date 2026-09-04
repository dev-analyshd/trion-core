// TRION Protocol — Go Network Layer Health Monitor (whitepaper Part 11)
//
// Go — Network Layer: P2P validator networking, API gateway, health monitoring,
// consensus messaging. WHY: goroutine model handles thousands of concurrent connections.
//
// This module implements the health monitoring component specified in Part 11.
// Runs concurrent health checks across its 19 configured endpoints
// (14 EVM RPCs, SOLANA/NEAR/TON, plus the FAISS and Oracle services).

package main

import (
	"encoding/json"
	"fmt"
	"log"
	"net/http"
	"os"
	"sync"
	"time"
)

// ── Chain configuration ───────────────────────────────────────────────────────

type Chain struct {
	Label   string `json:"label"`
	ChainID int    `json:"chain_id"`
	RPC     string `json:"rpc"`
	VMType  string `json:"vm_type"`
}

var CHAINS = []Chain{
	// EVM — Mainnet
	{"ETH_MAINNET", 1, "https://eth.llamarpc.com", "EVM"},
	{"ARB_MAINNET", 42161, "https://arb1.arbitrum.io/rpc", "EVM"},
	{"BASE_MAINNET", 8453, "https://mainnet.base.org", "EVM"},
	{"OP_MAINNET", 10, "https://mainnet.optimism.io", "EVM"},
	{"POLYGON", 137, "https://polygon-rpc.com", "EVM"},
	{"MANTLE", 5000, "https://rpc.mantle.xyz", "EVM"},
	{"LINEA", 59144, "https://rpc.linea.build", "EVM"},
	{"SCROLL", 534352, "https://rpc.scroll.io", "EVM"},
	{"HASHKEY", 177, "https://mainnet.hsk.xyz", "EVM"},
	// EVM — Testnet (active contracts)
	{"ARB_SEPOLIA", 421614, "https://sepolia-rollup.arbitrum.io/rpc", "EVM"},
	{"BASE_SEPOLIA", 84532, "https://sepolia.base.org", "EVM"},
	{"OP_SEPOLIA", 11155420, "https://sepolia.optimism.io", "EVM"},
	{"ZG_GALILEO", 16602, "https://evmrpc-testnet.0g.ai", "EVM"},
	{"BNB_TESTNET", 97, "https://bsc-testnet-rpc.publicnode.com", "EVM"},
	// Non-EVM Mainnet
	{"SOLANA", 0, "https://api.mainnet-beta.solana.com", "SVM"},
	{"NEAR", 0, "https://rpc.mainnet.fastnear.com", "NEAR"},
	{"TON", 0, "https://toncenter.com/api/v2/jsonRPC", "TON"},
	// Services
	{"FAISS_ANIMA", 0, "http://127.0.0.1:8000/health", "INTERNAL"},
	{"ORACLE_API", 0, "http://127.0.0.1:5000/health", "INTERNAL"},
}

// ── Health check types ────────────────────────────────────────────────────────

type HealthResult struct {
	Label        string        `json:"label"`
	Status       string        `json:"status"`
	LatencyMs    float64       `json:"latency_ms"`
	BlockNumber  uint64        `json:"block_number,omitempty"`
	Error        string        `json:"error,omitempty"`
	CheckedAt    time.Time     `json:"checked_at"`
}

type SystemHealth struct {
	Timestamp       time.Time       `json:"timestamp"`
	TotalChains     int             `json:"total_chains"`
	HealthyChains   int             `json:"healthy_chains"`
	DegradedChains  int             `json:"degraded_chains"`
	OfflineChains   int             `json:"offline_chains"`
	Results         []HealthResult  `json:"results"`
	AvgLatencyMs    float64         `json:"avg_latency_ms"`
	UptimePct       float64         `json:"uptime_pct"`
}

// ── Health check implementation ───────────────────────────────────────────────

func checkEVMChain(chain Chain, timeout time.Duration) HealthResult {
	start := time.Now()
	result := HealthResult{Label: chain.Label, CheckedAt: start}

	client := &http.Client{Timeout: timeout}
	body := `{"jsonrpc":"2.0","method":"eth_blockNumber","params":[],"id":1}`
	resp, err := client.Post(chain.RPC, "application/json",
		jsonReader(body))
	if err != nil {
		result.Status = "OFFLINE"
		result.Error = err.Error()
		result.LatencyMs = float64(time.Since(start).Milliseconds())
		return result
	}
	defer resp.Body.Close()

	var data map[string]interface{}
	if err := json.NewDecoder(resp.Body).Decode(&data); err != nil {
		result.Status = "DEGRADED"
		result.Error = "json decode error"
		result.LatencyMs = float64(time.Since(start).Milliseconds())
		return result
	}

	result.LatencyMs = float64(time.Since(start).Milliseconds())
	if hexBlock, ok := data["result"].(string); ok && len(hexBlock) > 2 {
		var blockNum uint64
		fmt.Sscanf(hexBlock[2:], "%x", &blockNum)
		result.BlockNumber = blockNum
		result.Status = "HEALTHY"
	} else {
		result.Status = "DEGRADED"
		result.Error = "no result field"
	}
	return result
}

func checkHTTPEndpoint(chain Chain, timeout time.Duration) HealthResult {
	start := time.Now()
	result := HealthResult{Label: chain.Label, CheckedAt: start}

	client := &http.Client{Timeout: timeout}
	resp, err := client.Get(chain.RPC)
	latency := float64(time.Since(start).Milliseconds())
	result.LatencyMs = latency

	if err != nil {
		result.Status = "OFFLINE"
		result.Error = err.Error()
		return result
	}
	defer resp.Body.Close()

	if resp.StatusCode < 300 {
		result.Status = "HEALTHY"
	} else {
		result.Status = "DEGRADED"
		result.Error = fmt.Sprintf("HTTP %d", resp.StatusCode)
	}
	return result
}

func jsonReader(s string) *jsonStringReader {
	return &jsonStringReader{data: []byte(s), pos: 0}
}

type jsonStringReader struct {
	data []byte
	pos  int
}

func (r *jsonStringReader) Read(p []byte) (n int, err error) {
	if r.pos >= len(r.data) {
		return 0, fmt.Errorf("EOF")
	}
	n = copy(p, r.data[r.pos:])
	r.pos += n
	return n, nil
}

// ── Concurrent health check ───────────────────────────────────────────────────

func RunHealthCheck(timeout time.Duration) SystemHealth {
	var wg sync.WaitGroup
	results := make([]HealthResult, len(CHAINS))

	for i, chain := range CHAINS {
		wg.Add(1)
		go func(idx int, c Chain) {
			defer wg.Done()
			switch c.VMType {
			case "EVM":
				results[idx] = checkEVMChain(c, timeout)
			default:
				results[idx] = checkHTTPEndpoint(c, timeout)
			}
		}(i, chain)
	}
	wg.Wait()

	healthy, degraded, offline := 0, 0, 0
	totalLatency := 0.0
	for _, r := range results {
		switch r.Status {
		case "HEALTHY":
			healthy++
			totalLatency += r.LatencyMs
		case "DEGRADED":
			degraded++
		default:
			offline++
		}
	}
	avgLatency := 0.0
	if healthy > 0 {
		avgLatency = totalLatency / float64(healthy)
	}

	return SystemHealth{
		Timestamp:      time.Now(),
		TotalChains:    len(CHAINS),
		HealthyChains:  healthy,
		DegradedChains: degraded,
		OfflineChains:  offline,
		Results:        results,
		AvgLatencyMs:   avgLatency,
		UptimePct:      float64(healthy+degraded) / float64(len(CHAINS)) * 100.0,
	}
}

// ── HTTP server ───────────────────────────────────────────────────────────────

func healthHandler(w http.ResponseWriter, r *http.Request) {
	health := RunHealthCheck(5 * time.Second)
	w.Header().Set("Content-Type", "application/json")
	w.Header().Set("Access-Control-Allow-Origin", "*")
	if err := json.NewEncoder(w).Encode(health); err != nil {
		http.Error(w, err.Error(), 500)
	}
}

func main() {
	port := os.Getenv("HEALTH_MONITOR_PORT")
	if port == "" {
		port = "6001"
	}

	http.HandleFunc("/health", healthHandler)
	http.HandleFunc("/health/chains", healthHandler)

	log.Printf("TRION Go Health Monitor — %d chains — port %s", len(CHAINS), port)
	log.Printf("Endpoints: GET /health, GET /health/chains")
	log.Printf("Language: Go (whitepaper Part 11 — Network Layer)")

	if err := http.ListenAndServe(":"+port, nil); err != nil {
		log.Fatalf("Health monitor failed: %v", err)
	}
}
