// SPDX-License-Identifier: MIT
pragma solidity ^0.8.20;

interface ITRIONOracle {
    function isSafe(bytes32 txId) external view returns (bool);
}
