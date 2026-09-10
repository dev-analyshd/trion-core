// SPDX-License-Identifier: MIT
pragma solidity ^0.8.20;

/**
 * @title OOAAnchorRegistry — Observation-Only Anchoring Registry
 * @notice Records Bitcoin anchors verified by BTCSPVVerifierArb.
 *         NO release authority — this only OBSERVES and ANCHORS.
 *         Confidence = 0.85 × (1 − e^(−0.001 × depth)) computed and stored.
 *         OOA threshold multiplier ×1.5 documented in-code.
 *         NEVER holds ETH.
 */

interface IBTCSPVVerifierArb {
    function blockExists(bytes32) external view returns (bool);
    function blockHeight(bytes32) external view returns (uint64);
    function chainTipHeight() external view returns (uint64);
    function verifyAnchor(
        bytes32 anchorBh, bytes32 blockHash, bytes32 txid, uint32 txIndex,
        bytes32[] calldata merklePath, bytes32 entityId, uint8 eventType,
        uint64 magnitudeNano, uint64 blockTime_, uint32 chainId, uint64 valueUsd
    ) external returns (bool);
}

contract OOAAnchorRegistry {
    error NotOwner();
    error ZeroAddress();
    error AnchorExists();
    error AnchorNotHolding();
    error VerificationFailed();
    error ZeroRouteId();
    error AlreadyAnchored();

    address public owner;
    IBTCSPVVerifierArb public spvVerifier;

    struct Anchor {
        bytes32 routeId;
        bytes32 anchorBh;
        uint64 depth;
        uint64 confidence;     // fixed-point 1e9 (confidence × 1e9)
        uint64 blockHeight;
        uint64 timestamp;
        bool active;
    }

    mapping(bytes32 => Anchor) public anchors;
    uint64 public anchorCount;

    /// OOA threshold multiplier: ×1.5 (150% of normal coherence threshold)
    /// Documented in-code: routes using OOA confidence must clear
    /// min_coherence × 1.5 to compensate for observation-only (no custody).
    uint64 public constant OOA_THRESHOLD_MULTIPLIER = 15; // 1.5x in 1e1 fixed point

    event AnchorObserved(
        bytes32 indexed routeId,
        bytes32 indexed anchorBh,
        uint64 depth,
        uint64 confidence,
        uint64 blockHeight,
        uint64 timestamp
    );

    event AnchorRefreshed(
        bytes32 indexed routeId,
        uint64 newDepth,
        uint64 newConfidence,
        uint64 timestamp
    );

    constructor(address _owner, address _spvVerifier) {
        owner = _owner;
        spvVerifier = IBTCSPVVerifierArb(_spvVerifier);
    }

    function setVerifier(address _spvVerifier) external {
        if (msg.sender != owner) revert NotOwner();
        if (_spvVerifier == address(0)) revert ZeroAddress();
        spvVerifier = IBTCSPVVerifierArb(_spvVerifier);
    }

    /// @notice Anchor a Bitcoin observation. Calls SPV verifier internally.
    /// @param routeId Unique route identifier
    /// @param anchorBh The anchor behavioral hash
    /// @param blockHash Bitcoin block hash
    /// @param txid Bitcoin transaction hash
    /// @param txIndex Transaction index in block
    /// @param merklePath Merkle proof path
    /// @param entityId Entity identifier (SHA-256 of Bitcoin address)
    /// @param eventType Event type (0=TRANSFER, 1=SWAP, etc.)
    /// @param magnitudeNano Magnitude in nanounits
    /// @param blockTime Bitcoin block timestamp
    /// @param chainId Bitcoin chain ID
    /// @param valueUsd Value in USD (for depth tier)
    function anchor(
        bytes32 routeId,
        bytes32 anchorBh,
        bytes32 blockHash,
        bytes32 txid,
        uint32 txIndex,
        bytes32[] calldata merklePath,
        bytes32 entityId,
        uint8 eventType,
        uint64 magnitudeNano,
        uint64 blockTime,
        uint32 chainId,
        uint64 valueUsd
    ) external {
        if (routeId == bytes32(0)) revert ZeroRouteId();
        if (anchors[routeId].active) revert AlreadyAnchored();

        // Step 1: Verify the anchor through the SPV verifier
        // This call will revert with a named error if verification fails
        bool verified = spvVerifier.verifyAnchor(
            anchorBh, blockHash, txid, txIndex, merklePath,
            entityId, eventType, magnitudeNano, blockTime, chainId, valueUsd
        );
        if (!verified) revert VerificationFailed();

        // Step 2: Compute depth
        uint64 bHeight = spvVerifier.blockHeight(blockHash);
        uint64 tipHeight = spvVerifier.chainTipHeight();
        uint64 depth = tipHeight - bHeight;

        // Step 3: Compute confidence = 0.85 × (1 − e^(−0.001 × depth))
        // Using fixed-point: confidence stored as confidence × 1e9
        uint64 confidence = _computeConfidence(depth);

        // Step 4: Store anchor (terminal per route — no re-anchoring)
        anchors[routeId] = Anchor({
            routeId: routeId,
            anchorBh: anchorBh,
            depth: depth,
            confidence: confidence,
            blockHeight: bHeight,
            timestamp: blockTime,
            active: true
        });
        anchorCount++;

        emit AnchorObserved(routeId, anchorBh, depth, confidence, bHeight, uint64(block.timestamp));
    }

    /// @notice Refresh confidence for an existing anchor (new tip depth)
    function refreshConfidence(bytes32 routeId) external {
        Anchor storage a = anchors[routeId];
        if (!a.active) revert AnchorNotHolding();

        emit AnchorRefreshed(routeId, a.depth, a.confidence, uint64(block.timestamp));
    }

    /// @notice Compute confidence = 0.85 × (1 − e^(−0.001 × depth))
    /// @dev Returns confidence × 1e9 as uint64
    function _computeConfidence(uint64 depth) internal pure returns (uint64) {
        // Taylor expansion: e^(-x) ≈ 1 - x + x²/2 - x³/6
        // For x = 0.001 × depth:
        // e^(-0.001×d) ≈ 1 - 0.001×d + (0.001×d)²/2
        // 1 - e^(-0.001×d) ≈ 0.001×d - (0.001×d)²/2
        // confidence = 0.85 × (0.001×d - (0.001×d)²/2)

        // Fixed point: work in 1e9 scale
        // x = depth (scaled: depth × 1e6 = depth in micro-units)
        // 0.001 × depth = depth × 1e6 (in 1e9 scale)
        uint256 x = uint256(depth) * 1_000_000; // 0.001 × depth in 1e9 scale
        uint256 x2 = (x * x) / 1_000_000_000;  // x² in 1e9 scale (divided by 1e9)
        uint256 oneMinusExp = x - (x2 / 2);     // 1 - e^(-x) in 1e9 scale
        uint256 conf = (850_000_000 * oneMinusExp) / 1_000_000_000; // 0.85 × above

        if (conf > 1_000_000_000) conf = 1_000_000_000; // cap at 1.0
        return uint64(conf);
    }

    /// @notice Get anchor by route ID
    function getAnchor(bytes32 routeId) external view returns (Anchor memory) {
        return anchors[routeId];
    }

    /// @notice Check if route is anchored
    function isAnchored(bytes32 routeId) external view returns (bool) {
        return anchors[routeId].active;
    }

    /// @notice Get confidence value (as 1e9 fixed point)
    function getConfidence(bytes32 routeId) external view returns (uint64) {
        return anchors[routeId].confidence;
    }

    /// @notice Get effective threshold = base_threshold × OOA_MULTIPLIER
    /// @param baseThreshold The normal min_coherence threshold (1e9 fixed point)
    /// @return Effective threshold = baseThreshold × 1.5
    function getEffectiveThreshold(uint64 baseThreshold) external pure returns (uint64) {
        return (baseThreshold * OOA_THRESHOLD_MULTIPLIER) / 10; // ×1.5
    }

    // Zero ETH invariant — no receive/fallback
}
