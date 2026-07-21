// TRION Protocol — P2P Go Network Layer — Main Entry Point
// Starts all five subsystems concurrently:
//   1. ANIMA Crawler Coordinator (59-language goroutine pool)
//   2. P2P Validator Mesh (TCP gossip, DW-BFT quorum)
//   3. Network Health Monitor (concurrent chain health checks)
//   4. DW-BFT Consensus Node (HTTP server, Σ(t) engine)
//   5. API Gateway (port 7700 — unified HTTP entry point for all subsystems)
//
// Author: TRION Protocol — Originator: Hudu Yusuf (Analys)
// License: CC0

package main

import (
	"fmt"
	"log"
	"os"
	"os/signal"
	"syscall"
	"time"

	p2p "trion/p2pgo"
)

func main() {
	log.SetFlags(log.Ltime | log.Lmicroseconds)

	fmt.Println("╔══════════════════════════════════════════════════════════════════╗")
	fmt.Println("║  TRION Protocol — P2P Go Network Layer                          ║")
	fmt.Println("║  WHY: goroutine model handles thousands of concurrent connections║")
	fmt.Println("╚══════════════════════════════════════════════════════════════════╝")

	// ── 1. ANIMA Crawler Coordinator ─────────────────────────────────────────
	configs := p2p.DefaultCrawlerConfigs()
	crawler := p2p.NewCrawlerPool(configs)
	log.Printf("[TRION p2p] ANIMA crawler pool  — %d language corpora loaded", len(configs))

	// Warm-up crawl (non-blocking)
	go func() {
		signals := crawler.Run("trion_protocol")
		ca := p2p.CrossSourceAgreement(signals)
		log.Printf("[TRION p2p] ANIMA warm-up done  — %d signals, CA=%.4f", len(signals), ca)
	}()

	// ── 2. P2P Validator Mesh ─────────────────────────────────────────────────
	meshProfile := p2p.ValidatorProfile{
		ID:               p2p.MeshValidatorIDFromKey([]byte("trion-p2p-primary")),
		Addr:             "127.0.0.1:7701",
		DiversityWeight:  0.85,
		GeographicRegion: "US",
		ClientDiversity:  "trion-go",
		UptimeFraction:   1.0,
		BehavioralAge:    0,
		LastSeen:         time.Now(),
	}
	mesh := p2p.NewMeshNode(meshProfile)
	if err := mesh.Listen("127.0.0.1:7701"); err != nil {
		log.Printf("[TRION p2p] Mesh listen warning (port may be in use): %v", err)
	}
	log.Printf("[TRION p2p] P2P validator mesh  — TCP gossip on :7701")

	// ── 3. Health Monitor ─────────────────────────────────────────────────────
	go func() {
		health := p2p.RunHealthCheck(p2p.DefaultChains, 5*time.Second)
		log.Printf("[TRION p2p] Health monitor done — %d/%d healthy, avg %.1f ms",
			health.HealthyChains, health.TotalChains, health.AvgLatencyMs)
	}()

	// ── 4. DW-BFT Consensus Node ──────────────────────────────────────────────
	consensusInfo := p2p.ValidatorInfo{
		ID:               "trion-consensus-primary",
		Address:          "127.0.0.1",
		Port:             7702,
		GeographicRegion: "US",
		Continent:        "NA",
		Jurisdiction:     "US",
		Stake:            1000.0,
		DiversityScore:   0.85,
		EffectiveStake:   850.0,
		HSMVerified:      false,
	}
	consensusNode := p2p.NewConsensusNode(consensusInfo)
	go func() {
		log.Printf("[TRION p2p] DW-BFT consensus    — HTTP server on :7702")
		if err := consensusNode.Start(); err != nil {
			log.Printf("[TRION p2p] Consensus node stopped: %v", err)
		}
	}()

	// ── 5. API Gateway ────────────────────────────────────────────────────────
	gwPort := 7700
	if p := os.Getenv("P2P_GATEWAY_PORT"); p != "" {
		fmt.Sscanf(p, "%d", &gwPort)
	}
	gw := p2p.NewAPIGateway(gwPort, crawler, mesh)
	go func() {
		log.Printf("[TRION p2p] API gateway         — HTTP server on :%d", gwPort)
		log.Printf("[TRION p2p]   GET  http://127.0.0.1:%d/health", gwPort)
		log.Printf("[TRION p2p]   GET  http://127.0.0.1:%d/health/chains", gwPort)
		log.Printf("[TRION p2p]   GET  http://127.0.0.1:%d/anima/crawl?entity=<id>", gwPort)
		log.Printf("[TRION p2p]   GET  http://127.0.0.1:%d/consensus/hhi", gwPort)
		if err := gw.Start(); err != nil {
			log.Printf("[TRION p2p] Gateway stopped: %v", err)
		}
	}()

	// Wait for SIGINT/SIGTERM
	sig := make(chan os.Signal, 1)
	signal.Notify(sig, syscall.SIGINT, syscall.SIGTERM)
	s := <-sig
	log.Printf("[TRION p2p] Signal received: %v — shutting down", s)
	crawler.Stop()
	mesh.Stop()
	consensusNode.Stop()
	gw.Stop()
}
