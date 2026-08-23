// SPDX-License-Identifier: MIT
pragma solidity ^0.8.24;

/// @title BTCFiGuard — Behavioral Risk Firewall for BTCFi Protocols
/// @notice Composable anti-sybil module: call `assessRisk(beoId)` before
///         accepting BTC collateral. Risk tiers: 0=SAFE 1=CAUTION 2=HIGH_RISK
///         3=HOSTILE. Back-port of the deployed Starknet BTCFiGuard.cairo.
/// @dev    Reads live behavioral scores from an on-chain TRIONOracleV3 (or any
///         contract exposing the minimal ITRIONScoreReader surface below).
interface ITRIONScoreReader {
    /// @return animaScore          ANIMA score ×10000 (PCR·HA·CA)
    /// @return genesisConfidence   1-e^(-λD) ×10000
    /// @return trajectoryAlert     0=CLEAR 1=WARN 2=MANIPULATION
    /// @return akashicDepth        D(t)
    /// @return updateCount         sequential update count (0 = never scored)
    function getScore(bytes32 beoId)
        external view
        returns (uint64 animaScore, uint64 genesisConfidence, uint8 trajectoryAlert, uint64 akashicDepth, uint64 updateCount);
}

contract BTCFiGuard {
    // ── Risk tiers ─────────────────────────────────────────────────────────
    uint8 public constant SAFE       = 0;
    uint8 public constant CAUTION    = 1;
    uint8 public constant HIGH_RISK  = 2;
    uint8 public constant HOSTILE    = 3;

    // ── Scoring thresholds (scores ×10000) ─────────────────────────────────
    uint64 private constant SAFE_ANIMA_MIN    = 5_500; // 0.55
    uint64 private constant SAFE_GC_MIN       = 4_000; // 0.40
    uint64 private constant CAUTION_ANIMA_MIN = 2_500; // 0.25
    uint64 private constant CAUTION_GC_MIN    = 1_500; // 0.15

    uint8 private constant ALERT_WARN         = 1;
    uint8 private constant ALERT_MANIPULATION = 2;

    // ── State ──────────────────────────────────────────────────────────────
    address public owner;
    ITRIONScoreReader public oracle;
    /// @notice Protocols should reject deposits when tier > safeThreshold.
    uint8 public safeThreshold = CAUTION;

    // ── Events ─────────────────────────────────────────────────────────────
    event OracleUpdated(address indexed oldOracle, address indexed newOracle);
    event ThresholdUpdated(uint8 indexed oldThreshold, uint8 indexed newThreshold);
    event OwnershipTransferred(address indexed previousOwner, address indexed newOwner);

    error Unauthorized();

    modifier onlyOwner() {
        if (msg.sender != owner) revert Unauthorized();
        _;
    }

    constructor(address _oracle) {
        require(_oracle != address(0), "BTCFi: zero oracle");
        owner  = msg.sender;
        oracle = ITRIONScoreReader(_oracle);
    }

    // ── Core: risk assessment ──────────────────────────────────────────────

    /// @notice Primary integration point — returns the entity's risk tier.
    function assessRisk(bytes32 beoId) external view returns (uint8) {
        (uint64 anima, uint64 gc, uint8 alert,, uint64 updates) = oracle.getScore(beoId);
        return _computeTier(anima, gc, alert, updates);
    }

    /// @notice Batch assessment (bounded to avoid gas exhaustion).
    function batchAssess(bytes32[] calldata beoIds) external view returns (uint8[] memory) {
        uint8[] memory results = new uint8[](beoIds.length);
        for (uint256 i = 0; i < beoIds.length; i++) {
            (uint64 anima, uint64 gc, uint8 alert,, uint64 updates) = oracle.getScore(beoIds[i]);
            results[i] = _computeTier(anima, gc, alert, updates);
        }
        return results;
    }

    /// @notice Pure tier computation — no oracle lookup.
    function scoreToTier(uint64 animaScore, uint8 trajectoryAlert, uint64 genesisConfidence)
        external pure returns (uint8)
    {
        return _computeTier(animaScore, genesisConfidence, trajectoryAlert, 1);
    }

    function _computeTier(
        uint64 animaScore,
        uint64 genesisConfidence,
        uint8  trajectoryAlert,
        uint64 updateCount
    ) private pure returns (uint8) {
        // HOSTILE: active TRION manipulation signal
        if (trajectoryAlert == ALERT_MANIPULATION) return HOSTILE;
        // HIGH_RISK: no behavioral history on-chain
        if (updateCount == 0) return HIGH_RISK;
        // HIGH_RISK: extremely weak scores
        if (animaScore < CAUTION_ANIMA_MIN && genesisConfidence < CAUTION_GC_MIN) return HIGH_RISK;
        // CAUTION: partial history or warning-level trajectory or borderline scores
        if (trajectoryAlert == ALERT_WARN
            || animaScore < SAFE_ANIMA_MIN
            || genesisConfidence < SAFE_GC_MIN) return CAUTION;
        return SAFE;
    }

    // ── Admin ──────────────────────────────────────────────────────────────

    function setSafeThreshold(uint8 threshold) external onlyOwner {
        require(threshold <= 2, "BTCFi: threshold must be 0-2");
        emit ThresholdUpdated(safeThreshold, threshold);
        safeThreshold = threshold;
    }

    function setOracle(address newOracle) external onlyOwner {
        require(newOracle != address(0), "BTCFi: zero oracle");
        emit OracleUpdated(address(oracle), newOracle);
        oracle = ITRIONScoreReader(newOracle);
    }

    function transferOwnership(address newOwner) external onlyOwner {
        require(newOwner != address(0), "BTCFi: zero owner");
        emit OwnershipTransferred(owner, newOwner);
        owner = newOwner;
    }
}
