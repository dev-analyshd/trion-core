// SPDX-License-Identifier: MIT
pragma solidity ^0.8.24;

/**
 * @title TRIONSignal — TRION Protocol L0 On-Chain Signal Registry
 * @notice Stores cryptographically verified behavioral signals on-chain.
 * @dev Phase 10 scaffold. signal_value in [0,1e18] (1e18 = 1.0)
 */
contract TRIONSignal {

    // ── Types ─────────────────────────────────────────────────────────────

    enum SignalType {
        VALUATION,
        GENESIS_INFERENCE,
        SILENCE,
        MANIPULATION_ALERT,
        LIQUIDITY_HEALTH,
        ECOSYSTEM_HEALTH,
        GOVERNANCE_INTEGRITY,
        SYSTEMIC_RISK,
        RESURRECTION,
        FORK_DIVERGENCE,
        DORMANCY_CLASSIFICATION,
        TRAJECTORY_ANOMALY,
        CROSS_CHAIN_CONTINUITY,
        TEMPORAL_ANOMALY,
        BEHAVIORAL_SHIFT,
        VALIDATOR_HEALTH,
        AKASHIC_MILESTONE,
        NEGATIVE_SPACE,
        SOVEREIGN_ASSESSMENT
    }

    struct Signal {
        bytes32    entity_id;
        uint256    signal_value;    // fixed-point 1e18 = 1.0 — this IS C(t), the five-plane coherence score
        uint256    ci_lo;           // 1e18 = 1.0
        uint256    ci_hi;           // 1e18 = 1.0
        uint256    conf_genesis;    // 1e18 = 1.0
        uint64     chain_id;
        uint64     block_height;
        SignalType signal_type;
        bytes32    genomic_sense;
        bytes32    genomic_antisense;
        bytes32    genomic_invariant; // complement_invariant = NOT(anti_raw)
        uint256    timestamp;
        address    publisher;
        // ── Added to close TRION_AUDIT_REPORT.md finding S1 (13 → 24+ fields) ──
        uint256    theta;                 // Θ(t) — dynamic silence threshold at emission time
        uint256    phi_adj;               // Physical plane, 1e18 = 1.0
        uint256    m_adj;                 // Mental plane, 1e18 = 1.0
        uint256    sigma;                 // Spiritual/consensus plane, 1e18 = 1.0
        uint256    k_score;               // Conscious plane, 1e18 = 1.0
        uint256    a_score;               // ANIMA plane, 1e18 = 1.0
        bytes32    limiting_plane;        // ascii-packed name of the lowest-scoring plane (L5.2)
        uint256    mf_score;              // Manipulation fingerprint score, 1e18 = 1.0
        uint256    validator_hhi;         // Herfindahl-Hirschman index of validator weight distribution
        uint64     brt_phase;             // Biological Rhythm Timer phase (0-3) at emission
        uint64     ttl_seconds;           // Signal validity window
        bytes32    prev_signal_hash;      // Provenance chain: hash of this entity's previous signal
    }

    // ── State ─────────────────────────────────────────────────────────────

    address public owner;
    address public oracle;

    /// entity_id => array of signals (append-only ledger)
    mapping(bytes32 => Signal[]) public signals;

    /// Latest signal index per entity (for fast lookup)
    mapping(bytes32 => uint256) public latestIndex;

    uint256 public totalSignals;

    // ── Events ────────────────────────────────────────────────────────────

    event SignalPublished(
        bytes32 indexed entity_id,
        SignalType      signal_type,
        uint256         signal_value,
        uint256         timestamp
    );

    event SilenceEmitted(
        bytes32 indexed entity_id,
        uint256         timestamp,
        uint256         c_gap
    );

    event OracleUpdated(address indexed old_oracle, address indexed new_oracle);

    // ── Errors ────────────────────────────────────────────────────────────

    error NotOracle(address caller);
    error NotOwner(address caller);
    error InvalidSignalValue(uint256 value);
    error CINotOrdered(uint256 lo, uint256 hi);
    error GenomicInvariantViolated();

    // ── Modifiers ─────────────────────────────────────────────────────────

    modifier onlyOracle() {
        if (msg.sender != oracle) revert NotOracle(msg.sender);
        _;
    }

    modifier onlyOwner() {
        if (msg.sender != owner) revert NotOwner(msg.sender);
        _;
    }

    // ── Constructor ───────────────────────────────────────────────────────

    constructor(address _oracle) {
        owner  = msg.sender;
        oracle = _oracle;
    }

    // ── Core functions ────────────────────────────────────────────────────

    /**
     * @notice Publish a verified behavioral signal on-chain.
     * @dev Validates genomic invariant before storage.
     *      Silence signals (c_gap > 0) emit SilenceEmitted instead.
     */
    /// @dev Grouped into a struct (rather than 20+ loose parameters) to avoid
    ///      "stack too deep" compilation errors now that the payload includes
    ///      the full plane breakdown and provenance fields (finding S1 fix).
    struct PublishSignalInput {
        bytes32    entity_id;
        uint256    signal_value;
        uint256    ci_lo;
        uint256    ci_hi;
        uint256    conf_genesis;
        uint64     chain_id;
        uint64     block_height;
        SignalType signal_type;
        bytes32    genomic_sense;
        bytes32    genomic_antisense;
        bytes32    genomic_invariant;
        uint256    theta;
        uint256    phi_adj;
        uint256    m_adj;
        uint256    sigma;
        uint256    k_score;
        uint256    a_score;
        bytes32    limiting_plane;
        uint256    mf_score;
        uint256    validator_hhi;
        uint64     brt_phase;
        uint64     ttl_seconds;
        bytes32    prev_signal_hash;
    }

    function publishSignal(PublishSignalInput calldata input) external onlyOracle {
        // Validate signal_value in [0, 1e18]
        if (input.signal_value > 1e18) revert InvalidSignalValue(input.signal_value);

        // Validate CI ordering
        if (input.ci_lo >= input.ci_hi) revert CINotOrdered(input.ci_lo, input.ci_hi);

        // Validate genomic XOR invariant: sense XOR antisense == invariant
        bytes32 computed_invariant = input.genomic_sense ^ input.genomic_antisense;
        if (computed_invariant != input.genomic_invariant) revert GenomicInvariantViolated();

        Signal memory sig = Signal({
            entity_id:           input.entity_id,
            signal_value:        input.signal_value,
            ci_lo:               input.ci_lo,
            ci_hi:               input.ci_hi,
            conf_genesis:        input.conf_genesis,
            chain_id:            input.chain_id,
            block_height:        input.block_height,
            signal_type:         input.signal_type,
            genomic_sense:       input.genomic_sense,
            genomic_antisense:   input.genomic_antisense,
            genomic_invariant:   input.genomic_invariant,
            timestamp:           block.timestamp,
            publisher:           msg.sender,
            theta:               input.theta,
            phi_adj:             input.phi_adj,
            m_adj:               input.m_adj,
            sigma:               input.sigma,
            k_score:             input.k_score,
            a_score:             input.a_score,
            limiting_plane:      input.limiting_plane,
            mf_score:            input.mf_score,
            validator_hhi:       input.validator_hhi,
            brt_phase:           input.brt_phase,
            ttl_seconds:         input.ttl_seconds,
            prev_signal_hash:    input.prev_signal_hash
        });

        signals[input.entity_id].push(sig);
        latestIndex[input.entity_id] = signals[input.entity_id].length - 1;
        totalSignals++;

        if (input.signal_type == SignalType.SILENCE) {
            emit SilenceEmitted(input.entity_id, block.timestamp, 0);
        } else {
            emit SignalPublished(input.entity_id, input.signal_type, input.signal_value, block.timestamp);
        }
    }

    // ── View functions ────────────────────────────────────────────────────

    function getLatestSignal(bytes32 entity_id)
        external view returns (Signal memory)
    {
        require(signals[entity_id].length > 0, "No signals for entity");
        return signals[entity_id][latestIndex[entity_id]];
    }

    function getSignalCount(bytes32 entity_id) external view returns (uint256) {
        return signals[entity_id].length;
    }

    function verifyGenomicInvariant(
        bytes32 sense,
        bytes32 antisense,
        bytes32 invariant
    ) external pure returns (bool) {
        return (sense ^ antisense) == invariant;
    }

    // ── Admin ─────────────────────────────────────────────────────────────

    function setOracle(address new_oracle) external onlyOwner {
        emit OracleUpdated(oracle, new_oracle);
        oracle = new_oracle;
    }

    function transferOwnership(address new_owner) external onlyOwner {
        owner = new_owner;
    }
}
