// SPDX-License-Identifier: MIT
pragma solidity ^0.8.24;

/// @title LiquidityOcean — Form-equivalent liquidity tracking across chains
/// @notice Aggregates NL (Natural Liquidity) scores across all integrated chains
///         to compute a global Liquidity Ocean score for routing decisions.
/// @dev Implements whitepaper BTCP §6 (The Liquidity Ocean).
contract LiquidityOcean {
    struct ChainLiquidity {
        uint64  chainId;
        uint256 nlScore;          // ×1e6 — Natural Liquidity Score for this chain
        uint256 weight;           // ×1e6 — routing weight (higher = preferred)
        uint256 tvl;              // total value locked (USD)
        uint256 lastUpdated;
        bool    active;
    }

    mapping(uint64 => ChainLiquidity) public chains;
    uint64[] public chainList;
    uint256 public chainCount;

    /// @notice Global Liquidity Ocean score ×1e6
    uint256 public oceanScore;

    /// @notice Routing threshold — routes with score below this are rejected
    uint256 public routingThreshold;

    address public owner;
    address public relayer;

    event ChainRegistered(uint64 indexed chainId, uint256 weight);
    event NLScoreUpdated(uint64 indexed chainId, uint256 nlScore, uint256 tvl);
    event OceanScoreUpdated(uint256 oceanScore, uint256 routingThreshold);
    event RelayerUpdated(address indexed oldRelayer, address indexed newRelayer);

    modifier onlyOwner() { require(msg.sender == owner, "NOT_OWNER"); _; }
    modifier onlyRelayer() { require(msg.sender == relayer || msg.sender == owner, "NOT_RELAYER"); _; }

    constructor() {
        owner = msg.sender;
        relayer = msg.sender;
        routingThreshold = 300_000; // 0.30 ×1e6 — whitepaper L7.1 alert threshold
    }

    /// @notice Register a chain with its routing weight.
    function registerChain(uint64 chainId, uint256 weight) external onlyOwner returns (bool) {
        require(!chains[chainId].active, "CHAIN_EXISTS");
        require(weight <= 1_000_000, "INVALID_WEIGHT");
        chains[chainId] = ChainLiquidity({
            chainId: chainId,
            nlScore: 0,
            weight: weight,
            tvl: 0,
            lastUpdated: 0,
            active: true
        });
        chainList.push(chainId);
        chainCount++;
        emit ChainRegistered(chainId, weight);
        return true;
    }

    /// @notice Update NL score and TVL for a chain (called by relayer on each block).
    function updateNLScore(uint64 chainId, uint256 nlScore, uint256 tvl) external onlyRelayer returns (bool) {
        require(chains[chainId].active, "CHAIN_NOT_FOUND");
        require(nlScore <= 1_000_000, "INVALID_NL");
        chains[chainId].nlScore = nlScore;
        chains[chainId].tvl = tvl;
        chains[chainId].lastUpdated = block.timestamp;
        emit NLScoreUpdated(chainId, nlScore, tvl);
        _recomputeOcean();
        return true;
    }

    /// @notice Compute the global Liquidity Ocean score.
    /// @dev L_ocean = Σ(NL_k × W_k × availability) / Σ W_k
    function _recomputeOcean() internal {
        uint256 weightedSum = 0;
        uint256 totalWeight = 0;
        for (uint256 i = 0; i < chainList.length; i++) {
            ChainLiquidity storage c = chains[chainList[i]];
            if (c.active) {
                weightedSum += c.nlScore * c.weight;
                totalWeight += c.weight;
            }
        }
        if (totalWeight == 0) {
            oceanScore = 0;
        } else {
            oceanScore = weightedSum / totalWeight;
        }
        emit OceanScoreUpdated(oceanScore, routingThreshold);
    }

    /// @notice Get the best chain for routing a given action.
    /// @dev Returns the chain with the highest NL × weight score.
    function getBestChain() external view returns (uint64 bestChain, uint256 bestScore) {
        bestScore = 0;
        for (uint256 i = 0; i < chainList.length; i++) {
            ChainLiquidity storage c = chains[chainList[i]];
            if (c.active && c.nlScore >= routingThreshold) {
                uint256 score = c.nlScore * c.weight / 1_000_000;
                if (score > bestScore) {
                    bestScore = score;
                    bestChain = c.chainId;
                }
            }
        }
    }

    /// @notice Get all chain liquidity data.
    function getAllChains() external view returns (ChainLiquidity[] memory) {
        ChainLiquidity[] memory result = new ChainLiquidity[](chainList.length);
        for (uint256 i = 0; i < chainList.length; i++) {
            result[i] = chains[chainList[i]];
        }
        return result;
    }

    function setRoutingThreshold(uint256 threshold) external onlyOwner returns (bool) {
        require(threshold <= 1_000_000, "INVALID_THRESHOLD");
        routingThreshold = threshold;
        return true;
    }

    function setRelayer(address newRelayer) external onlyOwner {
        emit RelayerUpdated(relayer, newRelayer);
        relayer = newRelayer;
    }
}
