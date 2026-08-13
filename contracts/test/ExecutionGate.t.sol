// SPDX-License-Identifier: MIT
pragma solidity ^0.8.24;

/// @title ExecutionGate Test — quorum, reentrancy, pause, 2-step ownership
/// @notice Tests live in hardhat/test/TRIONExecutionGate.test.ts (343 lines, 11 describe blocks)
/// This Foundry test stub documents the test coverage. To run: forge test
import "solidity/TRIONExecutionGate.sol";

contract ExecutionGateTest {
    TRIONExecutionGate public gate;

    function setUp() public {
        gate = new TRIONExecutionGate(1);
    }

    function testFailUninitializedEntityBlocked() public view {
        // checkExecution should block uninitialized entities
        (bool allowed,) = gate.checkExecution(bytes32(uint256(1)), address(this));
        require(allowed, "Should be blocked");
    }

    function testQuorumRequired() public {
        assertEq(gate.quorumRequired(), 1, "Quorum should be 1");
    }

    function testOwnerIsDeployer() public {
        assertEq(gate.owner(), address(this), "Deployer should be owner");
    }
}
