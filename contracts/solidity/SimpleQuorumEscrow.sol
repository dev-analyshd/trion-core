// SPDX-License-Identifier: MIT
pragma solidity ^0.8.20;

contract SimpleQuorumEscrow {
    error NotOwner();
    error NotValidator();
    error AlreadyAttested();
    error QuorumNotReached();
    error NotHolding();
    error AlreadyReleased();
    error CoherenceMismatch();
    error StaleAttestation();
    error Disputed();
    error DepthInsufficient();

    struct Escrow { bytes32 routeId; address destination; uint256 amount; uint64 minCoherence; uint64 lockTime; uint64 timeout; uint8 state; }
    struct Attestation { uint64 coherence; bytes32 executionBh; uint32 count; uint64 lastTime; bool disputed; }

    address public owner;
    address public spvVerifier;
    mapping(address => bool) public isValidator;
    uint32 public validatorCount;
    uint32 public quorumRequired;
    mapping(bytes32 => Escrow) public escrows;
    mapping(bytes32 => Attestation) public attestations;
    mapping(bytes32 => bool) public hasAttested;
    uint256 public escrowCount;
    uint64 public constant MAX_ATTESTATION_AGE = 3600;

    event EscrowLocked(bytes32 indexed escrowId, bytes32 routeId, uint256 amount);
    event AttestationSubmitted(bytes32 indexed routeId, address validator, uint32 count);
    event EscrowReleased(bytes32 indexed escrowId, uint32 attestationCount);
    event EscrowReverted(bytes32 indexed escrowId, uint8 reason);

    constructor(address _owner) { owner = _owner; }

    function addValidator(address v) external {
        if (msg.sender != owner) revert NotOwner();
        if (!isValidator[v]) { isValidator[v] = true; validatorCount++; }
    }
    function setQuorumRequired(uint32 q) external {
        if (msg.sender != owner) revert NotOwner();
        quorumRequired = q;
    }
    function setSpvVerifier(address v) external {
        if (msg.sender != owner) revert NotOwner();
        spvVerifier = v;
    }

    function lockEscrow(bytes32 escrowId, bytes32 routeId, address destination, uint256 amount, uint64 minCoherence, uint64 timeout) external {
        if (escrows[escrowId].amount != 0) revert AlreadyReleased();
        escrows[escrowId] = Escrow(routeId, destination, amount, minCoherence, uint64(block.timestamp), timeout, 0);
        escrowCount++;
        emit EscrowLocked(escrowId, routeId, amount);
    }

    function submitAttestation(bytes32 routeId, uint64 coherence, bytes32 executionBh, uint64 attestationTime) external {
        if (!isValidator[msg.sender]) revert NotValidator();
        bytes32 key = keccak256(abi.encodePacked(routeId, msg.sender));
        if (hasAttested_v(key)) revert AlreadyAttested();
        Attestation storage a = attestations[routeId];
        if (a.count == 0) { a.coherence = coherence; a.executionBh = executionBh; }
        else if (coherence != a.coherence || executionBh != a.executionBh) { a.disputed = true; emit AttestationSubmitted(routeId, msg.sender, a.count); return; }
        a.count++;
        a.lastTime = attestationTime;
        emit AttestationSubmitted(routeId, msg.sender, a.count);
    }

    function hasAttested_v(bytes32 key) internal view returns (bool) {
        // simplified — in production use mapping
        return false;
    }

    function releaseEscrow(bytes32 escrowId, bytes32 executionBh, uint64 coherence) external {
        Escrow storage e = escrows[escrowId];
        if (e.amount == 0) revert NotHolding();
        if (e.state != 0) revert AlreadyReleased();
        Attestation storage a = attestations[e.routeId];
        if (a.count < quorumRequired) revert QuorumNotReached();
        if (a.disputed) revert Disputed();
        if (coherence != a.coherence) revert CoherenceMismatch();
        if (executionBh != a.executionBh) revert CoherenceMismatch();
        e.state = 1;
        emit EscrowReleased(escrowId, a.count);
    }

    function revertEscrow(bytes32 escrowId, uint8 reason) external {
        Escrow storage e = escrows[escrowId];
        if (e.amount == 0) revert NotHolding();
        if (e.state != 0) revert AlreadyReleased();
        e.state = 2;
        emit EscrowReverted(escrowId, reason);
    }

    function getEscrow(bytes32 id) external view returns (bytes32, address, uint256, uint64, uint8) {
        Escrow storage e = escrows[id];
        return (e.routeId, e.destination, e.amount, e.minCoherence, e.state);
    }
    function getRouteAttestation(bytes32 rid) external view returns (uint64, bytes32, uint32, uint64, bool) {
        Attestation storage a = attestations[rid];
        return (a.coherence, a.executionBh, a.count, a.lastTime, a.disputed);
    }
}