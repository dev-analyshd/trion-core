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
        uint256    signal_value;    // fixed-point 1e18 = 1.0
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
    function publishSignal(
        bytes32    entity_id,
        uint256    signal_value,
        uint256    ci_lo,
        uint256    ci_hi,
        uint256    conf_genesis,
        uint64     chain_id,
        uint64     block_height,
        SignalType signal_type,
        bytes32    genomic_sense,
        bytes32    genomic_antisense,
        bytes32    genomic_invariant
    ) external onlyOracle {
        // Validate signal_value in [0, 1e18]
        if (signal_value > 1e18) revert InvalidSignalValue(signal_value);

        // Validate CI ordering
        if (ci_lo >= ci_hi) revert CINotOrdered(ci_lo, ci_hi);

        // Validate genomic XOR invariant: sense XOR antisense == invariant
        bytes32 computed_invariant = genomic_sense ^ genomic_antisense;
        if (computed_invariant != genomic_invariant) revert GenomicInvariantViolated();

        Signal memory sig = Signal({
            entity_id:           entity_id,
            signal_value:        signal_value,
            ci_lo:               ci_lo,
            ci_hi:               ci_hi,
            conf_genesis:        conf_genesis,
            chain_id:            chain_id,
            block_height:        block_height,
            signal_type:         signal_type,
            genomic_sense:       genomic_sense,
            genomic_antisense:   genomic_antisense,
            genomic_invariant:   genomic_invariant,
            timestamp:           block.timestamp,
            publisher:           msg.sender
        });

        signals[entity_id].push(sig);
        latestIndex[entity_id] = signals[entity_id].length - 1;
        totalSignals++;

        if (signal_type == SignalType.SILENCE) {
            emit SilenceEmitted(entity_id, block.timestamp, 0);
        } else {
            emit SignalPublished(entity_id, signal_type, signal_value, block.timestamp);
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
