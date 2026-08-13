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
        uint256 packedData,
        uint256 timestamp
    );

    /// @notice Emitted when a signal with status=NOMINAL (1) is published.
    event EntropyNominal(bytes32 indexed txId, uint256 coherence, uint256 threshold);

    /// @notice Emitted when a signal is intercepted due to thermodynamic collapse.
    event ThermodynamicCollapseIntercepted(
        bytes32 indexed txId,
        uint8 status,
        uint256 coherence,
        uint256 threshold
    );

    /// @notice Emitted when a BTCP route is published.
    event BTCPRoutePublished(bytes32 indexed routeId, bool isSafe);

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

    function addValidator(address v) external;
    function setQuorum(uint256 q) external;
    function isValidator(address v) external view returns (bool);
    function quorumRequired() external view returns (uint256);
}
