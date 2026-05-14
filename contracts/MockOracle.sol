// SPDX-License-Identifier: MIT
pragma solidity ^0.8.20;

/**
 * @title MockOracle
 * @dev Simulates TRION L0 output for local Hardhat testing.
 *      Owner can flip network stability to simulate anomaly detection.
 */
contract MockOracle {
    bool public isNetworkStable;
    address public owner;

    event NetworkStateChanged(bool isStable, string reason);

    constructor() {
        owner = msg.sender;
        isNetworkStable = true;
    }

    modifier onlyOwner() {
        require(msg.sender == owner, "Not owner");
        _;
    }

    function setNetworkStable(bool _stable, string calldata _reason) external onlyOwner {
        isNetworkStable = _stable;
        emit NetworkStateChanged(_stable, _reason);
    }
}
