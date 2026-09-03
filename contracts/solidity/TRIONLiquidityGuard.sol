// SPDX-License-Identifier: MIT
pragma solidity ^0.8.20;

/**
 * @title TRIONLiquidityGuard
 * @notice NL-score gated swap router guard.
 *         Blocks execution if NL < 0.30 (reproduces the simulated "AAVE March
 *         2026" scenario — a synthetic test vector from the NL test suite,
 *         NOT a real historical event).
 *
 * Integration: call checkNL(asset) before any swap/deposit.
 * Returns: (bool safe, uint256 nlScore, string reason)
 */
interface ITRIONOracle {
    struct Signal {
        bytes32 entityId;
        string  signalType;
        uint256 signalValue;
        uint256 ci95Lower;
        uint256 ci95Upper;
        uint256 coherence;
        uint256 threshold;
        int256  margin;
        uint256 mfScore;
        uint256 timestamp;
        bool    silence;
        bool    bootstrapPhase;
        uint32  validatorCount;
    }
    function getSignal(bytes32 entityId) external view returns (Signal memory);
}

contract TRIONLiquidityGuard {

    uint256 public constant NL_MINIMUM = 3e17;  // 0.30 in 1e18

    ITRIONOracle public oracle;
    address public owner;

    event NLGuardTriggered(bytes32 indexed assetId, uint256 nlScore, uint256 timestamp);

    constructor(address _oracle) {
        oracle = ITRIONOracle(_oracle);
        owner  = msg.sender;
    }

    /**
     * @notice Check if NL score permits routing.
     * @param entityId  keccak256 hash of asset address.
     * @return safe     true if NL >= 0.30
     * @return nlScore  current NL score (1e18 fixed point)
     * @return reason   human-readable rejection reason
     */
    function checkNL(bytes32 entityId)
        external
        returns (bool safe, uint256 nlScore, string memory reason)
    {
        ITRIONOracle.Signal memory sig = oracle.getSignal(entityId);

        // No signal — fail safe
        if (sig.timestamp == 0) {
            return (false, 0, "TRION: No NL signal — fail safe");
        }

        // Signal expired (> 1 hour)
        if (block.timestamp - sig.timestamp > 3600) {
            return (false, 0, "TRION: NL signal expired");
        }

        nlScore = sig.signalValue;

        if (nlScore < NL_MINIMUM) {
            emit NLGuardTriggered(entityId, nlScore, block.timestamp);
            return (
                false,
                nlScore,
                "TRION: NL below 0.30 — pool cannot safely absorb transaction"
            );
        }

        return (true, nlScore, "TRION: NL healthy");
    }

    function setOracle(address _oracle) external {
        require(msg.sender == owner, "Not owner");
        oracle = ITRIONOracle(_oracle);
    }
}
