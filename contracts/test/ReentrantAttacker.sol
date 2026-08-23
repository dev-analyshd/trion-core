// SPDX-License-Identifier: MIT
pragma solidity ^0.8.20;

/**
 * @title ReentrantAttacker
 * @notice Test helper that attempts to re-enter TRIONExecutionGate.checkExecution
 *         from within a receive() or fallback() call.  Used to verify that
 *         nonReentrant is enforced correctly.
 */
interface IExecutionGate {
    function checkExecution(bytes32 entityId, address caller)
        external returns (bool allowed, bytes32 decisionHash);
}

contract ReentrantAttacker {
    IExecutionGate private immutable gate;
    bytes32 private storedEntityId;
    bool    private attacking;

    constructor(address _gate) {
        gate = IExecutionGate(_gate);
    }

    /** Entry point for the test — initiates the reentrancy attempt. */
    function attack(bytes32 entityId) external {
        storedEntityId = entityId;
        attacking      = true;
        // First call — triggers checkExecution, which sets _reentrancyGuard = true
        gate.checkExecution(entityId, address(this));
    }

    /** Called by the gate's internal accounting path if it ever calls back. */
    receive() external payable {
        if (attacking) {
            attacking = false;
            // Re-enter — must revert with "TRION: Reentrant call"
            gate.checkExecution(storedEntityId, address(this));
        }
    }
}
