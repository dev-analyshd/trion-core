// TRION Protocol — Go Network Layer Health Monitor (whitepaper Part 11)
//
// Runs concurrent goroutine health checks across all 19 registered chains
// (EVM mainnet + testnet + non-EVM) and internal services (FAISS, Oracle API).
// One goroutine per chain — zero contention on shared state via pre-allocated result slice.
//
// Author: TRION Protocol — Originator: Hudu Yusuf (Analys)
// License: CC0

package p2p

import (
	"encoding/json"
	"fmt"
	"net/http"
	"strings"
	"sync"
	"time"
)

// DefaultChains lists all chains and internal services to health-check.
var DefaultChains = []Chain{
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
	// EVM — Testnet (active TRION contracts)
	{"ARB_SEPOLIA", 421614, "https://sepolia-rollup.arbitrum.io/rpc", "EVM"},
	{"BASE_SEPOLIA", 84532, "https://sepolia.base.org", "EVM"},
	{"OP_SEPOLIA", 11155420, "https://sepolia.optimism.io", "EVM"},
	{"ZG_GALILEO", 16602, "https://evmrpc-testnet.0g.ai", "EVM"},
	{"BNB_TESTNET", 97, "https://bsc-testnet-rpc.publicnode.com", "EVM"},
	// Non-EVM Mainnet
	{"SOLANA", 0, "https://api.mainnet-beta.solana.com", "SVM"},
	{"NEAR", 0, "https://rpc.mainnet.fastnear.com", "NEAR"},
	{"TON", 0, "https://toncenter.com/api/v2/jsonRPC", "TON"},
	// Internal TRION services
	{"FAISS_ANIMA", 0, "http://127.0.0.1:8000/health", "INTERNAL"},
	{"ORACLE_API", 0, "http://127.0.0.1:5000/health", "INTERNAL"},
}

// RunHealthCheck concurrently checks all chains and returns aggregated results.
// One goroutine per chain; all writes go to pre-indexed result slots (no lock needed).
func RunHealthCheck(chains []Chain, timeout time.Duration) SystemHealth {
	results := make([]HealthResult, len(chains))
	var wg sync.WaitGroup

	for i, chain := range chains {
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
		TotalChains:    len(chains),
		HealthyChains:  healthy,
		DegradedChains: degraded,
		OfflineChains:  offline,
		Results:        results,
		AvgLatencyMs:   avgLatency,
		UptimePct:      float64(healthy+degraded) / float64(len(chains)) * 100.0,
	}
}

func checkEVMChain(chain Chain, timeout time.Duration) HealthResult {
	start := time.Now()
	result := HealthResult{Label: chain.Label, CheckedAt: start}

	client := &http.Client{Timeout: timeout}
	body := `{"jsonrpc":"2.0","method":"eth_blockNumber","params":[],"id":1}`
	resp, err := client.Post(chain.RPC, "application/json", strings.NewReader(body))
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
	result.LatencyMs = float64(time.Since(start).Milliseconds())

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
