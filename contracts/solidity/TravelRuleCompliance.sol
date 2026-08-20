// SPDX-License-Identifier: MIT
pragma solidity ^0.8.24;

/// @title TravelRuleCompliance — ZK Travel Rule proof storage (FATF compliant)
/// @notice Stores ZK proofs of Travel Rule compliance without revealing PII.
/// @dev Implements whitepaper BTCP §10 (Travel Rule Compliance) and Primitive 4
///      (Behavioral ZK Proofs). On-chain stores only commitment hashes + tier;
///      actual compliance data is proven via Schnorr-Pedersen NIZK off-chain.
contract TravelRuleCompliance {
    /// @notice FATF Travel Rule threshold (USD) — transactions above this require proof
    uint256 public fatfThresholdUSD = 1000;

    /// @notice Compliance tiers
    enum Tier { OPEN, BASIC, ENHANCED, INSTITUTIONAL }

    struct Proof {
        bytes32 proofId;            // unique proof identifier
        bytes32 entityId;           // BEO identifier
        bytes32 commitmentHash;     // Pedersen commitment to compliance data
        bytes32 jurisdictionHash;   // hash of jurisdiction (not raw country code)
        Tier    tier;
        uint256 amountUSD;          // transaction amount covered by this proof
        uint256 expiresAt;          // proof expiration timestamp
        bool    verified;           // true after off-chain verification
        uint256 createdAt;
        address submitter;
    }

    mapping(bytes32 => Proof) public proofs;
    bytes32[] public proofList;
    uint256 public proofCount;

    /// @notice Jurisdiction registry (jurisdictionHash → threshold override)
    mapping(bytes32 => uint256) public jurisdictionThresholds;

    address public owner;
    address public relayer;

    event ProofSubmitted(bytes32 indexed proofId, bytes32 indexed entityId, bytes32 commitmentHash, Tier tier, uint256 amountUSD);
    event ProofVerified(bytes32 indexed proofId, bool verified);
    event ProofRevoked(bytes32 indexed proofId);
    event JurisdictionThresholdSet(bytes32 indexed jurisdictionHash, uint256 threshold);
    event RelayerUpdated(address indexed oldRelayer, address indexed newRelayer);

    modifier onlyOwner() { require(msg.sender == owner, "NOT_OWNER"); _; }
    modifier onlyRelayer() { require(msg.sender == relayer || msg.sender == owner, "NOT_RELAYER"); _; }

    constructor() {
        owner = msg.sender;
        relayer = msg.sender;
    }

    /// @notice Submit a ZK Travel Rule proof.
    /// @dev Proof is not verified on-chain — the relayer performs off-chain
    ///      Schnorr-Pedersen verification and marks it as verified.
    function submitProof(
        bytes32 proofId,
        bytes32 entityId,
        bytes32 commitmentHash,
        bytes32 jurisdictionHash,
        Tier    tier,
        uint256 amountUSD,
        uint256 expiresAt
    ) external onlyRelayer returns (bool) {
        require(proofs[proofId].proofId == bytes32(0), "PROOF_EXISTS");
        require(commitmentHash != bytes32(0), "ZERO_COMMITMENT");
        require(uint8(tier) <= 3, "INVALID_TIER");
        require(expiresAt > block.timestamp, "EXPIRY_PAST");

        proofs[proofId] = Proof({
            proofId:         proofId,
            entityId:        entityId,
            commitmentHash:  commitmentHash,
            jurisdictionHash: jurisdictionHash,
            tier:            tier,
            amountUSD:       amountUSD,
            expiresAt:       expiresAt,
            verified:        false,
            createdAt:       block.timestamp,
            submitter:       msg.sender
        });

        proofList.push(proofId);
        proofCount++;
        emit ProofSubmitted(proofId, entityId, commitmentHash, tier, amountUSD);
        return true;
    }

    /// @notice Mark a proof as verified (after off-chain ZK verification).
    function verifyProof(bytes32 proofId, bool verified) external onlyRelayer returns (bool) {
        require(proofs[proofId].proofId != bytes32(0), "PROOF_NOT_FOUND");
        proofs[proofId].verified = verified;
        emit ProofVerified(proofId, verified);
        return true;
    }

    /// @notice Check if an entity has a valid travel rule proof for a given amount.
    function hasValidProof(bytes32 entityId, uint256 amountUSD) external view returns (bool) {
        if (amountUSD < fatfThresholdUSD) return true; // Below FATF threshold — no proof needed

        for (uint256 i = 0; i < proofList.length; i++) {
            Proof storage p = proofs[proofList[i]];
            if (p.entityId == entityId &&
                p.verified &&
                block.timestamp < p.expiresAt &&
                p.amountUSD >= amountUSD) {
                return true;
            }
        }
        return false;
    }

    /// @notice Revoke a proof (e.g., if compliance data changes).
    function revokeProof(bytes32 proofId) external onlyRelayer returns (bool) {
        require(proofs[proofId].proofId != bytes32(0), "PROOF_NOT_FOUND");
        proofs[proofId].verified = false;
        emit ProofRevoked(proofId);
        return true;
    }

    /// @notice Set jurisdiction-specific threshold (e.g., EU €1000, US $3000).
    function setJurisdictionThreshold(bytes32 jurisdictionHash, uint256 threshold) external onlyOwner returns (bool) {
        jurisdictionThresholds[jurisdictionHash] = threshold;
        emit JurisdictionThresholdSet(jurisdictionHash, threshold);
        return true;
    }

    /// @notice Get the applicable threshold for a jurisdiction.
    function getJurisdictionThreshold(bytes32 jurisdictionHash) external view returns (uint256) {
        uint256 custom = jurisdictionThresholds[jurisdictionHash];
        if (custom > 0) return custom;
        return fatfThresholdUSD;
    }

    function getProof(bytes32 proofId) external view returns (Proof memory) {
        return proofs[proofId];
    }

    function setRelayer(address newRelayer) external onlyOwner {
        // PHASE-1-SECURITY: zero-address check.
        require(newRelayer != address(0), "ZERO_RELAYER");
        emit RelayerUpdated(relayer, newRelayer);
        relayer = newRelayer;
    }
}
