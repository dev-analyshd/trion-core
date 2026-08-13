// SPDX-License-Identifier: MIT
pragma solidity ^0.8.24;

/// @title GenesisCommitment — Sponsored Genesis & Identity Genesis Protocol
/// @notice Manages new-entity bootstrap with anti-Sybil protections.
/// @dev Implements whitepaper BTCP §9 (Genesis Commitments — The Null-State Theorem).
contract GenesisCommitment {
    enum GenesisType { SPONSORED, ORGANIC, IDENTITY }

    struct Commitment {
        bytes32 commitmentId;     // Hash_DNA(entity || sponsor || behavioral_seed)
        bytes32 entityId;         // BEO identifier of new entity
        bytes32 sponsorId;        // BEO identifier of sponsor (if SPONSORED)
        GenesisType gtype;
        uint256 stakeBond;        // stake locked by sponsor (anti-Sybil)
        uint256 confidence;       // ×1e6 — genesis confidence
        uint256 lockUntil;        // timestamp — bond locked until this time
        bool    validated;        // true after entity reaches D_minimum
        uint256 createdAt;
        address committer;
    }

    mapping(bytes32 => Commitment) public commitments;
    bytes32[] public commitmentList;
    uint256 public commitmentCount;

    /// @notice 5-layer Sybil resistance config
    uint256 public constant SYBIL_RESISTANCE_LAYERS = 5;
    uint256 public minStakeBond = 0.01 ether;       // minimum sponsor stake
    uint256 public minLockDuration = 30 days;        // minimum bond lock
    uint256 public maxSponsorshipsPerEntity = 10;    // rate limit per sponsor
    uint256 public minSponsorAkashicDepth = 10_000;  // D_minimum for sponsor
    uint256 public behavioralUniquenessThreshold = 800_000; // ×1e6

    mapping(bytes32 => uint256) public sponsorCount; // sponsorEntityId → count

    address public owner;
    address public relayer;

    event CommitmentCreated(bytes32 indexed commitmentId, bytes32 indexed entityId, bytes32 indexed sponsorId, GenesisType gtype, uint256 stakeBond);
    event CommitmentValidated(bytes32 indexed commitmentId, uint256 confidence);
    event BondReleased(bytes32 indexed commitmentId, address indexed to, uint256 amount);
    event RelayerUpdated(address indexed oldRelayer, address indexed newRelayer);

    modifier onlyOwner() { require(msg.sender == owner, "NOT_OWNER"); _; }
    modifier onlyRelayer() { require(msg.sender == relayer || msg.sender == owner, "NOT_RELAYER"); _; }

    constructor() {
        owner = msg.sender;
        relayer = msg.sender;
    }

    /// @notice Create a sponsored genesis commitment.
    /// @dev Sponsor must send stakeBond as value. Bond is locked until lockUntil.
    function createSponsoredCommitment(
        bytes32 commitmentId,
        bytes32 entityId,
        bytes32 sponsorId,
        uint256 sponsorAkashicDepth,
        uint256 behavioralUniqueness
    ) external payable onlyRelayer returns (bool) {
        require(commitments[commitmentId].commitmentId == bytes32(0), "COMMITMENT_EXISTS");
        require(msg.value >= minStakeBond, "INSUFFICIENT_BOND");
        require(sponsorAkashicDepth >= minSponsorAkashicDepth, "SPONSOR_DEPTH_LOW");
        require(behavioralUniqueness >= behavioralUniquenessThreshold, "NOT_UNIQUE_ENOUGH");
        require(sponsorCount[sponsorId] < maxSponsorshipsPerEntity, "SPONSOR_LIMIT_REACHED");

        commitments[commitmentId] = Commitment({
            commitmentId: commitmentId,
            entityId:     entityId,
            sponsorId:    sponsorId,
            gtype:        GenesisType.SPONSORED,
            stakeBond:    msg.value,
            confidence:   0,
            lockUntil:    block.timestamp + minLockDuration,
            validated:    false,
            createdAt:    block.timestamp,
            committer:    msg.sender
        });

        commitmentList.push(commitmentId);
        commitmentCount++;
        sponsorCount[sponsorId]++;
        emit CommitmentCreated(commitmentId, entityId, sponsorId, GenesisType.SPONSORED, msg.value);
        return true;
    }

    /// @notice Validate a commitment once the entity reaches D_minimum.
    function validateCommitment(bytes32 commitmentId, uint256 confidence) external onlyRelayer returns (bool) {
        Commitment storage c = commitments[commitmentId];
        require(c.commitmentId != bytes32(0), "COMMITMENT_NOT_FOUND");
        require(!c.validated, "ALREADY_VALIDATED");
        require(confidence <= 1_000_000, "INVALID_CONFIDENCE");
        c.validated = true;
        c.confidence = confidence;
        emit CommitmentValidated(commitmentId, confidence);
        return true;
    }

    /// @notice Release the sponsor's bond after lock period ends.
    function releaseBond(bytes32 commitmentId) external onlyRelayer returns (bool) {
        Commitment storage c = commitments[commitmentId];
        require(c.commitmentId != bytes32(0), "COMMITMENT_NOT_FOUND");
        require(block.timestamp >= c.lockUntil, "LOCK_ACTIVE");
        require(c.stakeBond > 0, "BOND_RELEASED");
        uint256 amount = c.stakeBond;
        c.stakeBond = 0;
        (bool ok, ) = c.committer.call{value: amount}("");
        require(ok, "REFUND_FAILED");
        emit BondReleased(commitmentId, c.committer, amount);
        return true;
    }

    function getCommitment(bytes32 commitmentId) external view returns (Commitment memory) {
        return commitments[commitmentId];
    }

    function setRelayer(address newRelayer) external onlyOwner {
        emit RelayerUpdated(relayer, newRelayer);
        relayer = newRelayer;
    }
}
