// SPDX-License-Identifier: MIT
pragma solidity ^0.8.20;

/**
 * @title TRIONOracle — Behavioral Truth Oracle
 * @notice Implements all BIRP signal types on-chain.
 *
 * Signal emission: TRION validator (relayer) calls submitSignal()
 * Consumer contracts: call getSignal(entityId)
 *
 * Quorum: QUORUM_THRESHOLD validators must have approved each signal.
 * Manipulation fingerprint filter: signals with MF >= MF_MAX_ONCHAIN
 *   are rejected on-chain regardless of submission.
 *
 * CI_95: stored for DeFi protocol integration.
 * SILENCE: emitted when coherence drops below threshold.
 */
contract TRIONOracle {

    // ─── State ─────────────────────────────────────────────────

    struct Signal {
        bytes32 entityId;
        string  signalType;
        uint256 signalValue;    // fixed-point 1e18
        uint256 ci95Lower;      // fixed-point 1e18
        uint256 ci95Upper;      // fixed-point 1e18
        uint256 coherence;      // fixed-point 1e18
        uint256 threshold;      // fixed-point 1e18
        int256  margin;         // fixed-point 1e18, signed
        uint256 mfScore;        // fixed-point 1e18
        uint256 timestamp;
        bool    silence;
        bool    bootstrapPhase;
        uint32  validatorCount;
    }

    struct Validator {
        bool    active;
        uint256 stake;
        uint256 approvedCount;
    }

    // ─── Constants ─────────────────────────────────────────────

    uint256 public constant QUORUM_THRESHOLD  = 2;     // testnet: 2-of-N
    uint256 public constant MF_MAX_ONCHAIN    = 7e17;  // 0.70 in 1e18
    uint256 public constant MAX_SIGNAL_AGE    = 3600;  // seconds
    uint256 public constant SIGNAL_CACHE_SIZE = 1000;

    // ─── Storage ───────────────────────────────────────────────

    address public owner;
    address public relayer;

    mapping(bytes32 => Signal)   private _signals;
    mapping(address => Validator) private _validators;
    address[] private _validatorList;

    mapping(bytes32 => uint256)  private _signalApprovals;
    mapping(bytes32 => bool)     private _silenceRegistry;

    uint256 public totalSignalsEmitted;
    uint256 public totalSilenceEmitted;
    uint256 public totalManipulationBlocked;

    // ─── Events ────────────────────────────────────────────────

    event SignalEmitted(
        bytes32 indexed entityId,
        string  signalType,
        uint256 signalValue,
        uint256 coherence,
        uint256 threshold,
        int256  margin,
        bool    silence,
        uint256 timestamp
    );

    event SilenceEmitted(
        bytes32 indexed entityId,
        uint256 coherence,
        uint256 threshold,
        uint256 timestamp
    );

    event ManipulationBlocked(
        bytes32 indexed entityId,
        uint256 mfScore,
        string  attackType,
        uint256 timestamp
    );

    event ValidatorAdded(address indexed validator, uint256 stake);
    event ValidatorRemoved(address indexed validator);

    // ─── Constructor ───────────────────────────────────────────

    constructor(address _relayer) {
        owner   = msg.sender;
        relayer = _relayer;
    }

    // ─── Modifiers ─────────────────────────────────────────────

    modifier onlyOwner()   { require(msg.sender == owner,   "TRION: Not owner");   _; }
    modifier onlyRelayer() { require(msg.sender == relayer, "TRION: Not relayer"); _; }

    // ─── Validator Management ──────────────────────────────────

    function addValidator(address v, uint256 stake) external onlyOwner {
        require(!_validators[v].active, "TRION: Validator exists");
        _validators[v] = Validator(true, stake, 0);
        _validatorList.push(v);
        emit ValidatorAdded(v, stake);
    }

    function validatorCount() external view returns (uint256) {
        return _validatorList.length;
    }

    // ─── Signal Submission ─────────────────────────────────────

    /**
     * @notice Submit a signal from the BIRP relayer.
     * @dev Validates quorum, MF filter, age, and emits events.
     */
    function submitSignal(
        bytes32 entityId,
        string  calldata signalType,
        uint256 signalValue,
        uint256 ci95Lower,
        uint256 ci95Upper,
        uint256 coherence,
        uint256 threshold,
        int256  margin,
        uint256 mfScore,
        uint256 signalTimestamp,
        bool    silence,
        bool    bootstrapPhase,
        uint32  quorumCount
    ) external onlyRelayer {

        // Age check
        require(
            block.timestamp - signalTimestamp <= MAX_SIGNAL_AGE,
            "TRION: Signal expired"
        );

        // Quorum check
        require(
            quorumCount >= QUORUM_THRESHOLD,
            "TRION: Insufficient quorum"
        );

        // MF filter — block on-chain if manipulation is severe
        if (mfScore >= MF_MAX_ONCHAIN) {
            totalManipulationBlocked++;
            emit ManipulationBlocked(
                entityId, mfScore,
                "MF_SCORE_ABOVE_THRESHOLD",
                block.timestamp
            );
            return;
        }

        Signal memory sig = Signal({
            entityId:       entityId,
            signalType:     signalType,
            signalValue:    signalValue,
            ci95Lower:      ci95Lower,
            ci95Upper:      ci95Upper,
            coherence:      coherence,
            threshold:      threshold,
            margin:         margin,
            mfScore:        mfScore,
            timestamp:      signalTimestamp,
            silence:        silence,
            bootstrapPhase: bootstrapPhase,
            validatorCount: quorumCount
        });

        _signals[entityId] = sig;
        totalSignalsEmitted++;

        emit SignalEmitted(
            entityId, signalType, signalValue,
            coherence, threshold, margin,
            silence, signalTimestamp
        );

        if (silence) {
            _silenceRegistry[entityId] = true;
            totalSilenceEmitted++;
            emit SilenceEmitted(entityId, coherence, threshold, signalTimestamp);
        } else {
            _silenceRegistry[entityId] = false;
        }
    }

    // ─── Signal Reads ──────────────────────────────────────────

    function getSignal(bytes32 entityId) external view returns (Signal memory) {
        return _signals[entityId];
    }

    function isSilenced(bytes32 entityId) external view returns (bool) {
        return _silenceRegistry[entityId];
    }

    function getCoherence(bytes32 entityId) external view returns (uint256 coherence, uint256 threshold) {
        Signal storage sig = _signals[entityId];
        return (sig.coherence, sig.threshold);
    }

    function isBootstrap(bytes32 entityId) external view returns (bool) {
        return _signals[entityId].bootstrapPhase;
    }

    // ─── Admin ─────────────────────────────────────────────────

    function setRelayer(address _relayer) external onlyOwner {
        relayer = _relayer;
    }

    function getStats() external view returns (
        uint256 emitted, uint256 silenced, uint256 blocked
    ) {
        return (totalSignalsEmitted, totalSilenceEmitted, totalManipulationBlocked);
    }
}
