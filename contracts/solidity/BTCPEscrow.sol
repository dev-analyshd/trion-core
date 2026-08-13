// SPDX-License-Identifier: MIT
pragma solidity ^0.8.24;

/// @title BTCPEscrow — Two-State Atomic Escrow for BTCP Cross-Chain Settlement
/// @notice Holds value in HOLDING state until TRION consensus verifies both
///         parties' behavioral coherence, then releases or reverts atomically.
/// @dev Implements whitepaper BTCP §4.3 (Six-Step Execution) and §11 (Five Final Fixes).
///      Release requires: status==HOLDING AND not expired AND coherence >= threshold.
///      Revert requires: status==HOLDING AND (expired OR relayer triggers failure).
contract BTCPEscrow {
    enum State { HOLDING, RELEASED, REVERTED }

    /// @notice Revert reasons (whitepaper BTCP §11)
    enum RevertReason { TIMEOUT, COHERENCE_FAILURE, ROUTE_INVALID, MANUAL }

    struct Escrow {
        bytes32 escrowId;          // unique escrow identifier
        bytes32 routeId;           // linked BTCP route
        bytes32 entityId;          // BEO identifier
        address payable destination;
        uint256 amount;            // native token amount locked
        uint256 minCoherence;      // ×1e6 — release threshold
        uint256 lockBlock;         // block at which escrow was locked
        uint256 timeoutBlocks;     // max blocks before auto-revert
        State state;
        RevertReason revertReason;
        uint256 settledAt;
        uint256 revertedAt;
        address lockedBy;
    }

    mapping(bytes32 => Escrow) public escrows;
    bytes32[] public escrowList;
    uint256 public escrowCount;

    address public owner;
    address public relayer;

    event EscrowLocked(bytes32 indexed escrowId, bytes32 indexed routeId, bytes32 indexed entityId, address destination, uint256 amount, uint256 minCoherence, uint256 timeoutBlocks);
    event EscrowReleased(bytes32 indexed escrowId, bytes32 indexed routeId, bytes32 executionBH, uint256 coherence, uint256 settledAt);
    event EscrowReverted(bytes32 indexed escrowId, RevertReason reason, uint256 revertedAt);
    event RelayerUpdated(address indexed oldRelayer, address indexed newRelayer);

    modifier onlyOwner() { require(msg.sender == owner, "NOT_OWNER"); _; }
    modifier onlyRelayer() { require(msg.sender == relayer || msg.sender == owner, "NOT_RELAYER"); _; }

    constructor() {
        owner = msg.sender;
        relayer = msg.sender;
    }

    /// @notice Lock native tokens in escrow. Caller must send value with tx.
    /// @dev Called by the BTCP router after both parties confirm the PMO.
    function lockEscrow(
        bytes32 escrowId,
        bytes32 routeId,
        bytes32 entityId,
        address payable destination,
        uint256 minCoherence,
        uint256 timeoutBlocks
    ) external payable onlyRelayer returns (bool) {
        require(escrows[escrowId].escrowId == bytes32(0), "ESCROW_EXISTS");
        require(msg.value > 0, "ZERO_AMOUNT");
        require(destination != address(0), "ZERO_DESTINATION");
        require(minCoherence <= 1_000_000, "INVALID_COHERENCE");
        require(timeoutBlocks > 0, "ZERO_TIMEOUT");

        escrows[escrowId] = Escrow({
            escrowId:       escrowId,
            routeId:        routeId,
            entityId:       entityId,
            destination:    destination,
            amount:         msg.value,
            minCoherence:   minCoherence,
            lockBlock:      block.number,
            timeoutBlocks:  timeoutBlocks,
            state:          State.HOLDING,
            revertReason:   RevertReason.TIMEOUT,
            settledAt:      0,
            revertedAt:     0,
            lockedBy:       msg.sender
        });

        escrowList.push(escrowId);
        escrowCount++;
        emit EscrowLocked(escrowId, routeId, entityId, destination, msg.value, minCoherence, timeoutBlocks);
        return true;
    }

    /// @notice Release escrow to destination. Requires TRION consensus verification.
    /// @param executionBH The execution behavioral hash linking anchor → execution.
    /// @param coherence   The coherence score (×1e6) at settlement time.
    function releaseEscrow(
        bytes32 escrowId,
        bytes32 executionBH,
        uint256 coherence
    ) external onlyRelayer returns (bool) {
        Escrow storage esc = escrows[escrowId];
        require(esc.escrowId != bytes32(0), "ESCROW_NOT_FOUND");
        require(esc.state == State.HOLDING, "NOT_HOLDING");
        require(block.number <= esc.lockBlock + esc.timeoutBlocks, "EXPIRED");
        require(coherence >= esc.minCoherence, "COHERENCE_INSUFFICIENT");

        esc.state = State.RELEASED;
        esc.settledAt = block.timestamp;

        // Transfer native tokens to destination
        (bool ok, ) = esc.destination.call{value: esc.amount}("");
        require(ok, "TRANSFER_FAILED");

        emit EscrowReleased(escrowId, esc.routeId, executionBH, coherence, esc.settledAt);
        return true;
    }

    /// @notice Revert escrow back to the original locker.
    /// @dev Auto-reverts on timeout; relayer can trigger on coherence failure or route invalidity.
    function revertEscrow(bytes32 escrowId, RevertReason reason) external returns (bool) {
        Escrow storage esc = escrows[escrowId];
        require(esc.escrowId != bytes32(0), "ESCROW_NOT_FOUND");
        require(esc.state == State.HOLDING, "NOT_HOLDING");

        // Anyone can trigger revert on timeout; only relayer for other reasons
        bool isTimeout = block.number > esc.lockBlock + esc.timeoutBlocks;
        if (!isTimeout) {
            require(msg.sender == relayer || msg.sender == owner, "NOT_RELAYER");
            require(reason != RevertReason.TIMEOUT, "NOT_TIMEOUT");
        }

        esc.state = State.REVERTED;
        esc.revertReason = reason;
        esc.revertedAt = block.timestamp;

        // Return funds to locker
        (bool ok, ) = esc.lockedBy.call{value: esc.amount}("");
        require(ok, "REFUND_FAILED");

        emit EscrowReverted(escrowId, reason, esc.revertedAt);
        return true;
    }

    /// @notice Get escrow state.
    function getEscrow(bytes32 escrowId) external view returns (Escrow memory) {
        return escrows[escrowId];
    }

    /// @notice Check if escrow is expired (can be auto-reverted).
    function isExpired(bytes32 escrowId) external view returns (bool) {
        Escrow storage esc = escrows[escrowId];
        return esc.state == State.HOLDING && block.number > esc.lockBlock + esc.timeoutBlocks;
    }

    function setRelayer(address newRelayer) external onlyOwner {
        emit RelayerUpdated(relayer, newRelayer);
        relayer = newRelayer;
    }
}
