// SPDX-License-Identifier: CC0-1.0
pragma solidity ^0.8.24;

/**
 * @title  ITRIONSensingOracle
 * @notice Minimal interface for DeFi protocols integrating TRION behavioral truth.
 * @dev    Deployments at https://github.com/dev-analyshd/trion-sensing-oracle
 */
interface ITRIONSensingOracle {
    /**
     * @notice Returns true if the entity's latest signal is coherent AND fresh
     *         (within FRESHNESS_BLOCKS of the current block).
     */
    function isCoherent(bytes32 entityId) external view returns (bool);

    /**
     * @notice Returns full coherence detail for an entity.
     * @return score    Coherence score scaled ×1e6
     * @return thresh   Threshold scaled ×1e6
     * @return coherent Whether score >= threshold
     * @return plane    Index of the limiting plane (0-4)
     * @return blk      Block number of the latest signal
     * @return fresh    Whether the signal is within FRESHNESS_BLOCKS
     */
    function getCoherenceDetail(bytes32 entityId)
        external view
        returns (
            uint256 score,
            uint256 thresh,
            bool    coherent,
            uint8   plane,
            uint256 blk,
            bool    fresh
        );
}
