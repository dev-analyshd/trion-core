// SPDX-License-Identifier: MIT
pragma solidity ^0.8.20;

/**
 * @title ITRIONAggregatorV3
 * @notice Chainlink AggregatorV3Interface — drop-in compatible.
 *         Any protocol that already consumes Chainlink price feeds
 *         can swap in a TRIONPriceFeed address with zero code changes.
 *
 * Standard reference:
 *   https://docs.chain.link/data-feeds/api-reference#aggregatorv3interface
 */
interface ITRIONAggregatorV3 {
    function decimals()    external view returns (uint8);
    function description() external view returns (string memory);
    function version()     external view returns (uint256);

    function getRoundData(uint80 _roundId)
        external view
        returns (
            uint80  roundId,
            int256  answer,
            uint256 startedAt,
            uint256 updatedAt,
            uint80  answeredInRound
        );

    function latestRoundData()
        external view
        returns (
            uint80  roundId,
            int256  answer,
            uint256 startedAt,
            uint256 updatedAt,
            uint80  answeredInRound
        );

    function latestAnswer() external view returns (int256);
}
