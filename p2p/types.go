// TRION Protocol — P2P Go Network Layer — Shared Types
// Whitepaper Part 11 / Channel 17 / Section 21 Tech Stack
// "Go — Network Layer: P2P validator networking, ANIMA crawler coordination,
//  API gateway, health monitoring, consensus messaging.
//  WHY: goroutine model handles thousands of concurrent connections."
//
// Author: TRION Protocol — Originator: Hudu Yusuf (Analys)
// License: CC0

package p2pgo

import (
        "encoding/hex"
        "time"

        "trion/p2pgo/meshsha3"
)

// ── ANIMA Crawler Types ─────────────────────────────────────────────────────

// NLPSignal mirrors src/planes/anima/anima_data_streams.py:NLPSignal
type NLPSignal struct {
        LanguageCode      string  `json:"language_code"`
        SourceType        string  `json:"source_type"`
        Timestamp         int64   `json:"timestamp"`
        SentimentScore    float64 `json:"sentiment_score"`
        Confidence        float64 `json:"confidence"`
        SourceCount       int     `json:"source_count"`
        SourceCred        float64 `json:"source_cred"`
        CommitVelocity    float64 `json:"commit_velocity,omitempty"`
        ContributorGrowth float64 `json:"contributor_growth,omitempty"`
        IssueClosureRate  float64 `json:"issue_closure_rate,omitempty"`
        PRMergeRate       float64 `json:"pr_merge_rate,omitempty"`
}

// CrawlerConfig defines one language corpus crawler.
type CrawlerConfig struct {
        LanguageCode string
        LanguageName string
        CredWeight   float64
        Sources      []string
}

// CrawlResult is the outcome of one crawler run.
type CrawlResult struct {
        Config    CrawlerConfig
        Signal    NLPSignal
        Error     error
        LatencyMs int64
}

// ── Validator Mesh Types ───────────────────────────────────────────────────

// MeshValidatorID — 32-byte identity derived from SHA3-256 of public key.
type MeshValidatorID [32]byte

func (v MeshValidatorID) Hex() string { return hex.EncodeToString(v[:]) }

// MeshValidatorIDFromKey creates a MeshValidatorID from any byte key.
// Uses SHA3-256 (Keccak, FIPS 202) — NOT SHA-256 — for cross-system compatibility
// with the Rust trion-common::hash_dna::canonical_bh pipeline.
func MeshValidatorIDFromKey(key []byte) MeshValidatorID {
        return MeshValidatorID(meshsha3.Sum256(key))
}

// ValidatorProfile holds diversity weighting factors per whitepaper L4.1.
type ValidatorProfile struct {
        ID               MeshValidatorID
        Addr             string
        DiversityWeight  float64
        GeographicRegion string
        ClientDiversity  string
        UptimeFraction   float64
        BehavioralAge    int64
        LastSeen         time.Time
}

// BehavioralAttestation is one validator's signed attestation of a behavioral signal.
type BehavioralAttestation struct {
        EntityID           string  `json:"entity_id"`
        SignalType         string  `json:"signal_type"`
        CoherenceC         float64 `json:"coherence_c"`
        ThresholdTheta     float64 `json:"threshold_theta"`
        ValidatorID        string  `json:"validator_id"`
        DiversityWeight    float64 `json:"diversity_weight"`
        Timestamp          int64   `json:"timestamp"`
        BlockNumber        uint64  `json:"block_number"`
        SignatureSense     string  `json:"signature_sense"`
        SignatureAntisense string  `json:"signature_antisense"`
}

// QuorumResult is the DW-BFT aggregated result.
// Weighted quorum: Σ d_j · vote_j / Σ d_j ≥ 2/3
type QuorumResult struct {
        EntityID         string
        WeightedC        float64
        QuorumReached    bool
        AttestationCount int
        TotalWeight      float64
        AgreementWeight  float64
        HHI              float64
        Timestamp        int64
}

// ── Consensus (DW-BFT) Types ───────────────────────────────────────────────

// ValidatorInfo carries public information about a validator node.
type ValidatorInfo struct {
        ID               string    `json:"id"`
        Address          string    `json:"address"`
        Port             int       `json:"port"`
        GeographicRegion string    `json:"geographic_region"`
        Continent        string    `json:"continent"`
        Jurisdiction     string    `json:"jurisdiction"`
        Stake            float64   `json:"stake"`
        DiversityScore   float64   `json:"diversity_score"`
        EffectiveStake   float64   `json:"effective_stake"`
        LastSeen         time.Time `json:"last_seen"`
        HSMVerified      bool      `json:"hsm_verified"`
}

// ConsensusMessage carries a validator's assessment for a behavioral entity.
type ConsensusMessage struct {
        ValidatorID  string    `json:"validator_id"`
        EntityID     string    `json:"entity_id"`
        Valuation    float64   `json:"valuation"`
        ModelOutputs []float64 `json:"model_outputs"`
        Timestamp    time.Time `json:"timestamp"`
        Signature    string    `json:"signature"`
        GenesisGen   int       `json:"genesis_gen"`
}

// DiversityWeightedResult is the output of Σ(t) computation.
type DiversityWeightedResult struct {
        Sigma           float64            `json:"sigma"`
        ValidatorWeights map[string]float64 `json:"weights"`
        MedianValuation float64            `json:"median_valuation"`
        DeltaT          float64            `json:"delta_t"`
        HHI             float64            `json:"hhi"`
        IncludedCount   int                `json:"included_count"`
        ExcludedCount   int                `json:"excluded_count"`
        Bootstrap       bool               `json:"bootstrap"`
}

// ── Health Monitor Types ───────────────────────────────────────────────────

// Chain defines one chain or internal service to health-check.
type Chain struct {
        Label   string `json:"label"`
        ChainID int    `json:"chain_id"`
        RPC     string `json:"rpc"`
        VMType  string `json:"vm_type"` // EVM | SVM | NEAR | TON | INTERNAL
}

// HealthResult is the outcome of one health check.
type HealthResult struct {
        Label       string    `json:"label"`
        Status      string    `json:"status"`
        LatencyMs   float64   `json:"latency_ms"`
        BlockNumber uint64    `json:"block_number,omitempty"`
        Error       string    `json:"error,omitempty"`
        CheckedAt   time.Time `json:"checked_at"`
}

// SystemHealth aggregates all health check results.
type SystemHealth struct {
        Timestamp      time.Time      `json:"timestamp"`
        TotalChains    int            `json:"total_chains"`
        HealthyChains  int            `json:"healthy_chains"`
        DegradedChains int            `json:"degraded_chains"`
        OfflineChains  int            `json:"offline_chains"`
        Results        []HealthResult `json:"results"`
        AvgLatencyMs   float64        `json:"avg_latency_ms"`
        UptimePct      float64        `json:"uptime_pct"`
}
