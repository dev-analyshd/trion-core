// SPDX-License-Identifier: MIT
pragma solidity ^0.8.24;

/// @title ITRIONOracleV3 — Advanced TRION Behavioral Oracle (V3)
/// @notice Interface for the V3 oracle with BTCP route support and legacy
///         thermodynamic signal packing. The on-chain contract is documented in
///         contracts/TRIONOracleV3.sol — this interface mirrors its public surface
///         so other contracts (AttackSimulator, hardhat scripts, external
///         integrators) can compile against it without importing the full
///         implementation.
///
/// Packed signal layout (uint256):
///   bits [0..7]    status       (1=NOMINAL, 2=WARN, 3=COLLAPSE, 4=HOSTILE)
///   bits [8..39]   coherence    (C(t) × 1e6)
///   bits [40..71]  threshold    (Θ(t) × 1e6)
///   bits [72..135] blockNumber
///   bits [136..199] timestamp
interface ITRIONOracleV3 {
    /// @notice Emitted when a thermodynamic signal is etched on-chain.
    event ThermodynamicSignalEtched(
        bytes32 indexed txId,
        uint8 status,
        uint32 coherence,
        uint32 threshold
    );

    /// @notice Emitted when a signal with status=NOMINAL (1) is published.
    event EntropyNominal(bytes32 indexed txId, uint32 coherence, uint32 threshold, uint64 blockNum);

    /// @notice Emitted when a signal is intercepted due to thermodynamic collapse.
    event ThermodynamicCollapseIntercepted(
        bytes32 indexed txId,
        address indexed caller,
        uint32 coherence,
        uint32 threshold,
        uint256 packedData
    );

    /// @notice Emitted when a BTCP route is published.
    event BTCPRoutePublished(bytes32 indexed routeId, bool isSafe);

    /// @notice Emitted when a full behavioral signal is published on-chain.
    event BehavioralSignalPublished(
        bytes32 indexed entityId,
        bytes32 publicCommitment,
        uint256 coherenceScore,
        uint256 threshold,
        uint256 moatFactor,
        bool coherent,
        uint8 limitingPlane,
        uint256 planesPacked,
        uint64 signalBlock,
        uint64 signalTimestamp
    );

    /// @notice Emitted when SILENCE is formally recorded (C(t) < Θ(t)).
    event SilenceRecorded(
        bytes32 indexed entityId,
        uint256 coherenceScore,
        uint256 threshold,
        uint8 limitingPlane,
        uint256 coherenceGap,
        uint64 signalBlock
    );

    struct Signal {
        uint256 packedData;
        bool initialized;
    }

    struct BTCPRoute {
        bytes32 anchorBH;
        bytes32 executionBH;
        uint256 coherence;
        uint256 threshold;
        bool isSafe;
        uint256 timestamp;
    }

    /// @notice Full behavioral signal with entity context and plane data.
    /// @dev Plane scores are packed into `planesPacked` (×1e6, 32 bits each):
    ///      phi[0..32) mental[32..64) sigma[64..96) conscious[96..128) anima[128..160).
    ///      signalBlock/signalTimestamp packed into `timingPacked` (64 bits each).
    ///      Packing keeps the struct within EVM stack limits for viaIR codegen.
    struct BehavioralSignal {
        bytes32 entityId;
        bytes32 publicCommitment;
        uint256 coherenceScore;
        uint256 threshold;
        uint256 moatFactor;
        bool coherent;
        uint8 limitingPlane;
        uint256 planesPacked;
        uint256 timingPacked;
        bool initialized;
    }

    /// @notice Unpack a plane score from planesPacked. planeIndex 0=phi 1=mental 2=sigma 3=conscious 4=anima.
    function unpackPlane(uint256 planesPacked, uint8 planeIndex) external pure returns (uint64);

    /// @notice Pack five plane scores (×1e6) into one uint256.
    function packPlanes(uint64 phi, uint64 mental, uint64 sigma, uint64 conscious, uint64 anima)
        external pure returns (uint256);

    /// @notice Publish a behavioral signal (legacy path).
    function publishSignal(
        bytes32 txId,
        uint256 packedData,
        bytes[] calldata signatures
    ) external;

    /// @notice Publish a BTCP route with anchor + execution BH linkage.
    function publishBTCPRoute(
        bytes32 routeId,
        bytes32 anchorBH,
        bytes32 executionBH,
        uint256 coherenceScore,
        uint256 thresholdScore
    ) external;

    /// @notice Verify whether an execution is safe given a txId or routeId.
    /// @return isSafe      True if the entity may execute.
    /// @return coherence   Coherence score × 1e6.
    /// @return threshold   Threshold score × 1e6.
    function verifyExecution(bytes32 txId)
        external
        view
        returns (bool isSafe, uint32 coherence, uint32 threshold);

    /// @notice Get the full signal info for a txId.
    function getSignalInfo(bytes32 txId)
        external
        view
        returns (
            uint8 status,
            uint32 coherence,
            uint32 threshold,
            uint64 blockNumber,
            uint64 timestamp
        );

    /// @notice Publish a full behavioral signal with entity context and plane data.
    /// @param s Complete BehavioralSignal struct (signalBlock/timestamp/initialized set on-chain).
    function publishBehavioralSignal(BehavioralSignal calldata s) external;

    /// @notice Get the core behavioral signal fields for an entity.
    function getBehavioralSignal(bytes32 entityId) external view returns (
        bytes32 publicCommitment,
        uint256 coherenceScore,
        uint256 threshold,
        uint256 moatFactor,
        bool coherent,
        uint8 limitingPlane,
        bool initialized
    );

    /// @notice Get the five-plane breakdown for an entity's signal.
    function getBehavioralSignalPlanes(bytes32 entityId) external view returns (
        uint64 phiPlane,
        uint64 mentalPlane,
        uint64 sigmaPlane,
        uint64 consciousPlane,
        uint64 animaPlane,
        uint64 signalBlock,
        uint64 signalTimestamp
    );

    function addValidator(address v) external;
    function setQuorum(uint256 q) external;
    function isValidator(address v) external view returns (bool);
    function quorumRequired() external view returns (uint256);
    function signalCountByEntity(bytes32 entityId) external view returns (uint256);
    function totalBehavioralSignals() external view returns (uint256);
}
