// SPDX-License-Identifier: CC0-1.0
pragma solidity ^0.8.20;

// TRION Protocol — Complete Oracle Interface
// All signal types and oracle functions per whitepaper

interface ITRIONOracle {

    // Signal types (19 total)
    enum SignalType {
        VALUATION, SILENCE, MANIPULATION_ALERT,
        GENESIS, RESURRECTION, FORK_DIVERGENCE,
        TRAJECTORY, NEGATIVE_SPACE, PHASE_TRANSITION,
        SYSTEMIC_RISK, LIQUIDITY_HEALTH, GOVERNANCE_SIGNAL,
        CROSS_CHAIN_COHERENCE, STABLECOIN_HEALTH, MEV_EXPOSURE,
        INSTITUTIONAL_BHV, REGULATORY_BHV, ECOSYSTEM_HEALTH,
        BOOTSTRAP
    }

    struct TRIONSignal {
        bytes32 signalId;
        SignalType signalType;
        bytes32 entityId;
        uint256 signalValue;       // scaled by 1e6
        uint256 ci95Lower;         // scaled by 1e6 — NEVER zero
        uint256 ci95Upper;         // scaled by 1e6 — NEVER zero
        uint256 coherence;         // C(t) scaled by 1e6
        uint256 threshold;         // Θ(t) scaled by 1e6
        uint256 akashicDepth;
        bool    silence;           // true = SILENCE emitted
        uint256 silenceGap;        // Θ(t) - C(t) when silence
        uint8   limitingPlane;     // which plane limited C(t): 0-4
        uint256 timestamp;
    }

    // Core: verify execution — the integration primitive
    function verifyExecution(bytes32 txId)
        external view
        returns (bool isSafe, uint256 coherence, uint256 threshold);

    // Get full signal for entity
    function getSignal(bytes32 entityId)
        external view
        returns (TRIONSignal memory);

    // Natural Liquidity Score
    function getNLScore(address asset)
        external view
        returns (uint256 nlScore, uint256 timestamp);

    // Manipulation fingerprint
    function getMFScore(address entity)
        external view
        returns (uint256 mfScore, uint8 fingerprintType);

    // Publish BTCP route (called by relayer)
    function publishBTCPRoute(
        bytes32 routeId,
        bytes32 sourceTxHash,
        bytes32 destTxHash,
        uint256 coherence,
        uint256 threshold
    ) external;

    // Publish behavioral signal (called by relayer)
    function etchThermodynamicSignal(
        address entity,
        uint256 packedSignal
    ) external;

    // Events
    event SignalEmitted(bytes32 indexed entityId, uint8 signalType, uint256 coherence);
    event SilenceEmitted(bytes32 indexed entityId, uint256 gap, uint8 limitingPlane);
    event ManipulationAlert(address indexed entity, uint8 fingerprintType, uint256 score);
    event LiquidityHealthAlert(address indexed asset, uint256 nlScore);
}
