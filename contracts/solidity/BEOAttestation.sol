// SPDX-License-Identifier: MIT
pragma solidity ^0.8.24;

/// @title BEOAttestation — BEO Identity Binding on EVM
/// @notice Binds EVM wallet addresses to TRION BEO identity fingerprints
///         (SHA3-256 of the normalized BEO identifier) with credibility tiers.
///         Back-port of the deployed Starknet BEOAttestation.cairo so every
///         integrated VM exposes the same identity surface.
/// @dev    The attester (TRION oracle bridge) is the only writer. Wallets can
///         hold exactly one active attestation; BEO→wallet is 1:1 enforced.
contract BEOAttestation {
    // ── Roles ──────────────────────────────────────────────────────────────
    address public attester;
    address public owner;

    // ── Identity record ────────────────────────────────────────────────────
    struct BEOIdentity {
        bytes32 beoId;              // SHA3-256 BEO fingerprint
        uint8   tier;               // 0=BOOTSTRAP (<0.30) 1=GENESIS (0.30-0.80) 2=MATURITY (>0.80)
        uint64  genesisConfidenceBp; // 0-10000 basis points
        uint64  attestedAt;
        bool    active;
    }

    mapping(address => BEOIdentity) public walletToBEO;
    mapping(bytes32 => address) public beoToWallet;
    uint256 public totalAttestations;

    // ── Events ─────────────────────────────────────────────────────────────
    event Attested(address indexed wallet, bytes32 indexed beoId, uint8 tier, uint64 genesisConfidenceBp, uint64 timestamp);
    event Revoked(address indexed wallet, bytes32 indexed beoId, uint64 timestamp);
    event AttesterChanged(address indexed oldAttester, address indexed newAttester);
    event OwnershipTransferred(address indexed previousOwner, address indexed newOwner);

    // ── Errors ─────────────────────────────────────────────────────────────
    error Unauthorized();
    error InvalidTier();
    error InvalidConfidence();
    error AlreadyBound(bytes32 beoId);
    error NotAttested();

    modifier onlyAttester() {
        if (msg.sender != attester) revert Unauthorized();
        _;
    }

    modifier onlyOwner() {
        if (msg.sender != owner) revert Unauthorized();
        _;
    }

    constructor(address _attester) {
        require(_attester != address(0), "BEO: zero attester");
        owner    = msg.sender;
        attester = _attester;
    }

    // ── Attestation lifecycle ──────────────────────────────────────────────

    /// @notice Bind `wallet` to `beoId` with a credibility tier.
    function attest(
        address wallet,
        bytes32 beoId,
        uint8   tier,
        uint64  genesisConfidenceBp
    ) external onlyAttester {
        if (wallet == address(0) || beoId == bytes32(0)) revert Unauthorized();
        if (tier > 2) revert InvalidTier();
        if (genesisConfidenceBp > 10_000) revert InvalidConfidence();
        // 1:1 binding: the BEO must not already map to another wallet
        if (beoToWallet[beoId] != address(0) && beoToWallet[beoId] != wallet) {
            revert AlreadyBound(beoId);
        }

        bool wasActive = walletToBEO[wallet].active;
        walletToBEO[wallet] = BEOIdentity({
            beoId:              beoId,
            tier:               tier,
            genesisConfidenceBp: genesisConfidenceBp,
            attestedAt:         uint64(block.timestamp),
            active:             true
        });
        beoToWallet[beoId] = wallet;

        if (!wasActive) {
            totalAttestations += 1;
        }
        emit Attested(wallet, beoId, tier, genesisConfidenceBp, uint64(block.timestamp));
    }

    /// @notice Deactivate a wallet's attestation (identity remains resolvable).
    function revoke(address wallet) external onlyAttester {
        BEOIdentity storage id = walletToBEO[wallet];
        if (!id.active) revert NotAttested();

        bytes32 beoId = id.beoId;
        id.active = false;
        if (beoToWallet[beoId] == wallet) {
            delete beoToWallet[beoId];
        }
        emit Revoked(wallet, beoId, uint64(block.timestamp));
    }

    // ── Reads ──────────────────────────────────────────────────────────────

    function getBEO(address wallet) external view returns (BEOIdentity memory) {
        return walletToBEO[wallet];
    }

    function getWallet(bytes32 beoId) external view returns (address) {
        return beoToWallet[beoId];
    }

    function isAttested(address wallet) external view returns (bool) {
        return walletToBEO[wallet].active;
    }

    // ── Admin ──────────────────────────────────────────────────────────────

    function setAttester(address newAttester) external onlyOwner {
        require(newAttester != address(0), "BEO: zero attester");
        emit AttesterChanged(attester, newAttester);
        attester = newAttester;
    }

    function transferOwnership(address newOwner) external onlyOwner {
        require(newOwner != address(0), "BEO: zero owner");
        emit OwnershipTransferred(owner, newOwner);
        owner = newOwner;
    }
}
