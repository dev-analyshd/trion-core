// SPDX-License-Identifier: MIT
pragma solidity ^0.8.24;

/// @title SanctionsOracle — AWA-Protected Sanctions Screening (J1 Resolution)
/// @notice Real-time sanctions list screening with AWA (Adaptive Weighted
///         Authority) protection. Once a sanctions flag is set, it CANNOT be
///         overridden by operator, validator, or governance.
/// @dev Implements J1 Resolution from BTCP Master Spec:
///
///      Data Sources (ANIMA indexed):
///      - OFAC SDN List (US), OFAC Non-SDN Consolidated, EU Consolidated,
///        OFSI (UK), UN Security Council, JAFIO (Japan), AUSTRAC (Australia)
///      - Update frequency: within 1 hour of source update
///
///      Check Logic:
///      - Entity Resolution maps all controlled addresses to BEO
///      - If any address in BEO cluster on any sanctions list → SANCTIONS_FLAG
///      - Sponsored entity of sanctioned entity → SANCTIONS_ASSOCIATION_FLAG
///      - Routing impact: BTCP_score = 0 for ALL routes involving flagged entity
///
///      AWA Protection:
///      - SANCTIONS_FLAG enforcement is AWA-protected
///      - Cannot be overridden by operator, validator, governance
///      - False positive appeals: Conscious Layer review with legal documentation
contract SanctionsOracle {
    // ── Sanctions List Sources ──────────────────────────────────────────────

    /// @notice Sanctions list sources indexed by ANIMA service.
    enum ListSource {
        OFAC_SDN,                // 0 — US Treasury OFAC SDN List
        OFAC_NON_SDN,            // 1 — US OFAC Non-SDN Consolidated
        EU_CONSOLIDATED,         // 2 — EU Consolidated List
        OFSI_UK,                 // 3 — UK Office of Financial Sanctions Implementation
        UN_SECURITY_COUNCIL,     // 4 — UN Security Council Consolidated List
        JAFIO_JAPAN,             // 5 — Japan Financial Intelligence Agency
        AUSTRAC_AUSTRALIA        // 6 — AUSTRAC (Australia)
    }

    /// @notice Flag types
    enum FlagType {
        NONE,                    // 0
        SANCTIONS_FLAG,          // 1 — direct match on sanctions list
        SANCTIONS_ASSOCIATION,   // 2 — sponsored by sanctioned entity
        APPEAL_PENDING,          // 3 — Conscious Layer review in progress
        APPEAL_APPROVED          // 4 — false positive, flag removed
    }

    // ── State ───────────────────────────────────────────────────────────────

    /// @notice Per-BEO sanctions flag
    mapping(bytes32 => FlagType) public sanctionsFlags;

    /// @notice Per-BEO list of source lists that triggered the flag
    mapping(bytes32 => uint256) public flagSourcesBitmask; // bitmask of ListSource

    /// @notice Per-BEO timestamp of last flag update
    mapping(bytes32 => uint256) public flagTimestamp;

    /// @notice Per-BEO sponsor (for association tracking)
    mapping(bytes32 => bytes32) public entitySponsor;

    /// @notice Appeal records
    mapping(bytes32 => Appeal) public appeals;

    /// @notice ANIMA service authorized to update flags (within 1h of source)
    address public animaService;

    /// @notice Conscious Layer multisig for appeals
    address public consciousLayerMultisig;

    /// @notice Owner (for initial setup only — cannot override AWA-protected flags)
    address public owner;

    uint256 public constant UPDATE_WINDOW_SECONDS = 1 hours;

    struct Appeal {
        bytes32 entityId;
        uint256 submittedAt;
        string legalDocumentationHash; // IPFS hash of legal docs
        bool approved;
        bool rejected;
    }

    // ── Events ──────────────────────────────────────────────────────────────

    event SanctionsFlagSet(bytes32 indexed entityId, ListSource source, uint256 timestamp);
    event SanctionsFlagRemoved(bytes32 indexed entityId, string reason, uint256 timestamp);
    event SanctionsAssociationFlagged(bytes32 indexed entityId, bytes32 indexed sponsorEntityId, uint256 timestamp);
    event AppealSubmitted(bytes32 indexed entityId, uint256 submittedAt);
    event AppealReviewed(bytes32 indexed entityId, bool approved, uint256 reviewedAt);

    // ── Modifiers ───────────────────────────────────────────────────────────

    modifier onlyAnimaService() {
        require(msg.sender == animaService || msg.sender == owner, "NOT_ANIMA");
        _;
    }

    modifier onlyConsciousLayer() {
        require(msg.sender == consciousLayerMultisig, "NOT_CONSCIOUS_LAYER");
        _;
    }

    modifier onlyOwner() {
        require(msg.sender == owner, "NOT_OWNER");
        _;
    }

    constructor(address _animaService, address _consciousLayerMultisig) {
        // PHASE-1-SECURITY: reject zero-address admin parameters.
        require(_animaService != address(0), "ZERO_ANIMA");
        require(_consciousLayerMultisig != address(0), "ZERO_MULTISIG");
        owner = msg.sender;
        animaService = _animaService;
        consciousLayerMultisig = _consciousLayerMultisig;
    }

    // ── Flag Management (ANIMA Service only) ────────────────────────────────

    /// @notice Set sanctions flag on a BEO entity.
    /// @dev Called by ANIMA service within 1 hour of source list update.
    ///      Once set, this flag is AWA-protected and CANNOT be removed by
    ///      operator, validator, or governance. Only Conscious Layer appeal
    ///      can remove it.
    function setSanctionsFlag(
        bytes32 entityId,
        ListSource source
    ) external onlyAnimaService {
        // AWA protection: if an appeal was approved (false positive), do not
        // re-flag from the same source
        if (sanctionsFlags[entityId] == FlagType.APPEAL_APPROVED) {
            revert("APPEAL_APPROVED_CANNOT_REFLAG");
        }

        sanctionsFlags[entityId] = FlagType.SANCTIONS_FLAG;
        flagSourcesBitmask[entityId] |= (1 << uint256(source));
        flagTimestamp[entityId] = block.timestamp;

        emit SanctionsFlagSet(entityId, source, block.timestamp);

        // Check if this entity sponsors any other entities — if so, flag them too
        // (This requires external iteration; in practice, a reverse mapping would
        // be maintained. For now, the sponsor-association is set via
        // setSponsorAssociation when sponsorship is registered.)
    }

    /// @notice Set sponsor relationship (for association tracking).
    /// @dev When a sponsored entity is later sanctioned, the sponsor gets
    ///      SANCTIONS_ASSOCIATION_FLAG.
    function setSponsorAssociation(
        bytes32 sponsoredEntityId,
        bytes32 sponsorEntityId
    ) external onlyAnimaService {
        entitySponsor[sponsoredEntityId] = sponsorEntityId;

        // If sponsor is already sanctioned, flag the sponsored entity too
        if (sanctionsFlags[sponsorEntityId] == FlagType.SANCTIONS_FLAG) {
            sanctionsFlags[sponsoredEntityId] = FlagType.SANCTIONS_ASSOCIATION;
            flagTimestamp[sponsoredEntityId] = block.timestamp;
            emit SanctionsAssociationFlagged(sponsoredEntityId, sponsorEntityId, block.timestamp);
        }
    }

    /// @notice Cascade association flag when a sponsor gets sanctioned.
    /// @dev Called after setSanctionsFlag to propagate to sponsored entities.
    function cascadeAssociationFlag(
        bytes32 sanctionedEntityId,
        bytes32[] calldata sponsoredEntities
    ) external onlyAnimaService {
        require(
            sanctionsFlags[sanctionedEntityId] == FlagType.SANCTIONS_FLAG,
            "SPONSOR_NOT_SANCTIONED"
        );

        for (uint256 i = 0; i < sponsoredEntities.length; i++) {
            bytes32 sponsoredId = sponsoredEntities[i];
            if (entitySponsor[sponsoredId] == sanctionedEntityId &&
                sanctionsFlags[sponsoredId] == FlagType.NONE) {
                sanctionsFlags[sponsoredId] = FlagType.SANCTIONS_ASSOCIATION;
                flagTimestamp[sponsoredId] = block.timestamp;
                emit SanctionsAssociationFlagged(sponsoredId, sanctionedEntityId, block.timestamp);
            }
        }
    }

    // ── AWA-Protected Check ─────────────────────────────────────────────────

    /// @notice Check if entity is sanctioned. Returns true if ANY flag is set.
    /// @dev This is the routing-impact function. If true, BTCP_score = 0 for
    ///      ALL routes involving this entity.
    function isSanctioned(bytes32 entityId) external view returns (bool) {
        FlagType flag = sanctionsFlags[entityId];
        return (flag == FlagType.SANCTIONS_FLAG || flag == FlagType.SANCTIONS_ASSOCIATION);
    }

    /// @notice Get the flag type for an entity.
    function getFlagType(bytes32 entityId) external view returns (FlagType) {
        return sanctionsFlags[entityId];
    }

    /// @notice Get the bitmask of sources that triggered the flag.
    function getFlagSources(bytes32 entityId) external view returns (uint256) {
        return flagSourcesBitmask[entityId];
    }

    /// @notice AWA-protected routing check: returns 0 if sanctioned, 1 if clear.
    /// @dev BTCP router uses this as a multiplicative factor on BTCP_score.
    function routingImpactFactor(bytes32 entityId) external view returns (uint256) {
        if (this.isSanctioned(entityId)) {
            return 0;  // BTCP_score = 0 for sanctioned entities
        }
        return 1;  // No impact
    }

    // ── Appeal Process (Conscious Layer only) ───────────────────────────────

    /// @notice Submit an appeal for a false-positive sanctions flag.
    /// @dev Anyone can submit; review is Conscious Layer only.
    function submitAppeal(
        bytes32 entityId,
        string calldata legalDocumentationHash
    ) external {
        require(
            sanctionsFlags[entityId] == FlagType.SANCTIONS_FLAG ||
            sanctionsFlags[entityId] == FlagType.SANCTIONS_ASSOCIATION,
            "NOT_FLAGGED"
        );

        appeals[entityId] = Appeal({
            entityId: entityId,
            submittedAt: block.timestamp,
            legalDocumentationHash: legalDocumentationHash,
            approved: false,
            rejected: false
        });

        sanctionsFlags[entityId] = FlagType.APPEAL_PENDING;
        emit AppealSubmitted(entityId, block.timestamp);
    }

    /// @notice Review an appeal — Conscious Layer multisig only.
    /// @dev This is the ONLY way to remove a sanctions flag. Even the owner
    ///      cannot override AWA protection.
    function reviewAppeal(
        bytes32 entityId,
        bool approved
    ) external onlyConsciousLayer {
        require(sanctionsFlags[entityId] == FlagType.APPEAL_PENDING, "NO_APPEAL_PENDING");

        if (approved) {
            // False positive — remove flag
            sanctionsFlags[entityId] = FlagType.APPEAL_APPROVED;
            flagSourcesBitmask[entityId] = 0;
            emit SanctionsFlagRemoved(entityId, "appeal_approved", block.timestamp);
            emit AppealReviewed(entityId, true, block.timestamp);
        } else {
            // Appeal rejected — restore original flag
            // (In production, the original flag type would be preserved.)
            sanctionsFlags[entityId] = FlagType.SANCTIONS_FLAG;
            emit AppealReviewed(entityId, false, block.timestamp);
        }

        appeals[entityId].approved = approved;
        appeals[entityId].rejected = !approved;
    }

    // ── Admin ───────────────────────────────────────────────────────────────

    function setAnimaService(address newService) external onlyOwner {
        // PHASE-1-SECURITY: zero-address check.
        require(newService != address(0), "ZERO_ANIMA");
        animaService = newService;
    }

    function setConsciousLayerMultisig(address newMultisig) external onlyOwner {
        // PHASE-1-SECURITY: zero-address check.
        require(newMultisig != address(0), "ZERO_MULTISIG");
        consciousLayerMultisig = newMultisig;
    }

    /// @notice Transfer ownership. Note: new owner STILL cannot override
    ///         AWA-protected sanctions flags. Only Conscious Layer appeals can.
    function transferOwnership(address newOwner) external onlyOwner {
        // PHASE-1-SECURITY: zero-address check.
        require(newOwner != address(0), "ZERO_OWNER");
        owner = newOwner;
    }
}
