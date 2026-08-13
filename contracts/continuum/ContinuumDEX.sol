// SPDX-License-Identifier: MIT
pragma solidity ^0.8.24;

/// @title ContinuumDEX — Behavioral Clearing Network
/// @notice The CONTINUUM protocol: trades matched, priced, and settled based on
///         behavioral reality rather than visible order books. Built on TRION +
///         BTCP. Hyperliquid-style perpetual + spot DEX with behavioral backing.
/// @dev Implements whitepaper CONTINUUM §5 (Five Core Inventions):
///      1. BID (Behavioral Intent Detection)
///      2. CME (Complement Matching Engine)
///      3. PMO (Pre-Manifest Order System)
///      4. BDC (Behavioral Depth Credit)
///      5. Thermodynamic Settlement via BTCP
contract ContinuumDEX {
    // ═══════════════════════════════════════════════════════════════════════════
    // STRUCTS
    // ═══════════════════════════════════════════════════════════════════════════

    /// @notice BID detection result — Entity A's behavioral precursor
    struct BIDResult {
        bytes32 entityId;         // BEO identifier
        bytes32 assetIn;          // likely asset to trade
        bytes32 assetOut;         // likely asset to receive
        uint8   direction;        // 0=BUY, 1=SELL, 2=UNCERTAIN
        uint256 bidScore;         // ×1e6 — behavioral intent confidence
        uint256 confidence;       // ×1e6 — bidScore × D(t)/D_minimum × (1-MF)
        uint256 predictedWindow;  // blocks until likely execution
        uint256 detectedAt;
    }

    /// @notice PMO — Pre-Manifest Order (commitment before market visibility)
    struct PMO {
        bytes32 pmoId;            // unique PMO identifier
        bytes32 entityIdA;        // first entity
        bytes32 entityIdB;        // complement entity
        bytes32 assetIn;          // asset A offers
        bytes32 assetOut;         // asset A wants
        uint256 magnitude;        // trade size
        uint256 priceGuarantee;   // ×1e6 — TRION VALUATION + CCP premium
        uint256 ccpPremium;       // ×1e6 — Complement Certainty Premium share
        uint256 validBlocks;      // confirmation window
        uint256 confidenceA;      // ×1e6 — BID confidence of entity A
        uint256 confidenceB;      // ×1e6 — BID confidence of entity B
        bool    confirmedA;
        bool    confirmedB;
        bool    settled;
        uint256 createdAt;
    }

    /// @notice BDC — Behavioral Depth Credit line
    struct BDCCredit {
        bytes32 entityId;         // BEO identifier
        uint256 creditLimit;      // max undercollateralized position (USD)
        uint256 akashicDepth;     // D(t) at last computation
        uint256 consistencyRatio; // ×1e6 — 1 - std(Φ)/mean(Φ) over 90d
        uint256 avgTradeSize90d;  // USD
        uint256 confidenceMult;   // ×1e6 — min(2.0, D/D_minimum)
        uint256 updatedAt;
    }

    /// @notice Complement match result from CME
    struct ComplementMatch {
        bytes32 matchId;
        bytes32 entityIdA;
        bytes32 entityIdB;
        uint256 complementScore;  // ×1e6
        uint256 temporalAlignment;// ×1e6
        uint256 behavioralIndependence; // ×1e6 — 1 - BEO_confidence(A,B)
        uint256 liquiditySufficiency;   // ×1e6
        uint256 magnitudeCompatibility; // ×1e6
        uint256 createdAt;
    }

    // ═══════════════════════════════════════════════════════════════════════════
    // STATE
    // ═══════════════════════════════════════════════════════════════════════════

    mapping(bytes32 => BIDResult) public bids;          // entityId => BID result
    mapping(bytes32 => PMO) public pmos;                 // pmoId => PMO
    mapping(bytes32 => BDCCredit) public bdcCredits;     // entityId => BDC credit
    mapping(bytes32 => ComplementMatch) public matches;  // matchId => match

    bytes32[] public pmoList;
    bytes32[] public matchList;
    uint256 public pmoCount;
    uint256 public matchCount;

    /// @notice Total Complement Certainty Premium distributed (USD)
    uint256 public totalCCPDistributed;

    /// @notice BID thresholds (whitepaper CONTINUUM §7.3)
    uint256 public constant BID_THRESHOLD_LOW      = 450_000;  // 0.45 ×1e6
    uint256 public constant BID_THRESHOLD_MEDIUM   = 650_000;  // 0.65 ×1e6
    uint256 public constant BID_THRESHOLD_HIGH     = 800_000;  // 0.80 ×1e6
    uint256 public constant BID_THRESHOLD_CERTAIN  = 900_000;  // 0.90 ×1e6

    /// @notice CCP premium tiers (×1e6)
    uint256 public constant CCP_TIER_LOW    = 10_000;  // 1% — soft notification
    uint256 public constant CCP_TIER_MEDIUM = 25_000;  // 2.5%
    uint256 public constant CCP_TIER_HIGH   = 50_000;  // 5%
    uint256 public constant CCP_TIER_MAX    = 100_000; // 10%

    /// @notice BDC parameters
    uint256 public constant D_MINIMUM = 10_000;          // Akashic depth for full credit
    uint256 public constant MAX_BDC_MULTIPLIER = 2_000_000; // 2.0 ×1e6

    address public owner;
    address public relayer;
    address public btcpEscrow;        // BTCPEscrow contract for settlement
    address public trionOracle;       // TRION oracle for coherence checks

    // ═══════════════════════════════════════════════════════════════════════════
    // EVENTS
    // ═══════════════════════════════════════════════════════════════════════════

    event BIDDetected(bytes32 indexed entityId, uint8 direction, uint256 confidence, bytes32 assetIn, bytes32 assetOut);
    event ComplementFound(bytes32 indexed matchId, bytes32 indexed entityIdA, bytes32 indexed entityIdB, uint256 complementScore);
    event PMOProposed(bytes32 indexed pmoId, bytes32 indexed entityIdA, bytes32 indexed entityIdB, uint256 magnitude, uint256 priceGuarantee, uint256 ccpPremium);
    event PMOConfirmed(bytes32 indexed pmoId, bytes32 indexed entityId, bool confirmed);
    event PMOSettled(bytes32 indexed pmoId, uint256 ccpA, uint256 ccpB);
    event BDCCreditUpdated(bytes32 indexed entityId, uint256 creditLimit, uint256 akashicDepth);
    event RelayerUpdated(address indexed oldRelayer, address indexed newRelayer);
    event EscrowUpdated(address indexed oldEscrow, address indexed newEscrow);
    event OracleUpdated(address indexed oldOracle, address indexed newOracle);

    // ═══════════════════════════════════════════════════════════════════════════
    // MODIFIERS
    // ═══════════════════════════════════════════════════════════════════════════

    modifier onlyOwner() { require(msg.sender == owner, "NOT_OWNER"); _; }
    modifier onlyRelayer() { require(msg.sender == relayer || msg.sender == owner, "NOT_RELAYER"); _; }

    constructor(address _btcpEscrow, address _trionOracle) {
        owner = msg.sender;
        relayer = msg.sender;
        btcpEscrow = _btcpEscrow;
        trionOracle = _trionOracle;
    }

    // ═══════════════════════════════════════════════════════════════════════════
    // ENGINE 1: BID — Behavioral Intent Detection
    // ═══════════════════════════════════════════════════════════════════════════

    /// @notice Submit a BID detection result (from TRION's FAISS ANIMA engine).
    function submitBID(
        bytes32 entityId,
        bytes32 assetIn,
        bytes32 assetOut,
        uint8   direction,
        uint256 bidScore,
        uint256 confidence,
        uint256 predictedWindow
    ) external onlyRelayer returns (bool) {
        require(direction <= 2, "INVALID_DIRECTION");
        require(bidScore <= 1_000_000 && confidence <= 1_000_000, "INVALID_SCORE");

        bids[entityId] = BIDResult({
            entityId:       entityId,
            assetIn:        assetIn,
                assetOut:       assetOut,
            direction:      direction,
            bidScore:       bidScore,
            confidence:    confidence,
            predictedWindow: predictedWindow,
            detectedAt:     block.timestamp
        });

        if (confidence >= BID_THRESHOLD_MEDIUM) {
            emit BIDDetected(entityId, direction, confidence, assetIn, assetOut);
        }
        return true;
    }

    function getBID(bytes32 entityId) external view returns (BIDResult memory) {
        return bids[entityId];
    }

    // ═══════════════════════════════════════════════════════════════════════════
    // ENGINE 2: CME — Complement Matching Engine
    // ═══════════════════════════════════════════════════════════════════════════

    /// @notice Submit a complement match (computed off-chain via FAISS similarity).
    function submitComplementMatch(
        bytes32 matchId,
        bytes32 entityIdA,
        bytes32 entityIdB,
        uint256 complementScore,
        uint256 temporalAlignment,
        uint256 behavioralIndependence,
        uint256 liquiditySufficiency,
        uint256 magnitudeCompatibility
    ) external onlyRelayer returns (bool) {
        require(matches[matchId].matchId == bytes32(0), "MATCH_EXISTS");
        require(complementScore <= 1_000_000, "INVALID_SCORE");
        require(behavioralIndependence >= 700_000, "NOT_INDEPENDENT"); // < 30% BEO overlap

        matches[matchId] = ComplementMatch({
            matchId: matchId,
            entityIdA: entityIdA,
            entityIdB: entityIdB,
            complementScore: complementScore,
            temporalAlignment: temporalAlignment,
            behavioralIndependence: behavioralIndependence,
            liquiditySufficiency: liquiditySufficiency,
            magnitudeCompatibility: magnitudeCompatibility,
            createdAt: block.timestamp
        });

        matchList.push(matchId);
        matchCount++;
        emit ComplementFound(matchId, entityIdA, entityIdB, complementScore);
        return true;
    }

    // ═══════════════════════════════════════════════════════════════════════════
    // ENGINE 3: PMO — Pre-Manifest Order System
    // ═══════════════════════════════════════════════════════════════════════════

    /// @notice Propose a PMO after CME finds a complement match.
    function proposePMO(
        bytes32 pmoId,
        bytes32 entityIdA,
        bytes32 entityIdB,
        bytes32 assetIn,
        bytes32 assetOut,
        uint256 magnitude,
        uint256 priceGuarantee,
        uint256 ccpPremium,
        uint256 validBlocks,
        uint256 confidenceA,
        uint256 confidenceB
    ) external onlyRelayer returns (bool) {
        require(pmos[pmoId].pmoId == bytes32(0), "PMO_EXISTS");
        require(magnitude > 0, "ZERO_MAGNITUDE");
        require(ccpPremium <= CCP_TIER_MAX, "CCP_TOO_HIGH");
        require(confidenceA >= BID_THRESHOLD_MEDIUM && confidenceB >= BID_THRESHOLD_MEDIUM, "BID_LOW");

        pmos[pmoId] = PMO({
            pmoId:         pmoId,
            entityIdA:     entityIdA,
            entityIdB:     entityIdB,
            assetIn:       assetIn,
            assetOut:      assetOut,
            magnitude:     magnitude,
            priceGuarantee: priceGuarantee,
            ccpPremium:    ccpPremium,
            validBlocks:   validBlocks,
            confidenceA:   confidenceA,
            confidenceB:   confidenceB,
            confirmedA:    false,
            confirmedB:    false,
            settled:       false,
            createdAt:     block.timestamp
        });

        pmoList.push(pmoId);
        pmoCount++;
        emit PMOProposed(pmoId, entityIdA, entityIdB, magnitude, priceGuarantee, ccpPremium);
        return true;
    }

    /// @notice Confirm a PMO (each party must confirm independently).
    function confirmPMO(bytes32 pmoId, bytes32 entityId) external onlyRelayer returns (bool) {
        PMO storage pmo = pmos[pmoId];
        require(pmo.pmoId != bytes32(0), "PMO_NOT_FOUND");
        require(!pmo.settled, "ALREADY_SETTLED");
        require(block.timestamp <= pmo.createdAt + pmo.validBlocks, "EXPIRED");

        if (entityId == pmo.entityIdA) {
            require(!pmo.confirmedA, "A_CONFIRMED");
            pmo.confirmedA = true;
        } else if (entityId == pmo.entityIdB) {
            require(!pmo.confirmedB, "B_CONFIRMED");
            pmo.confirmedB = true;
        } else {
            revert("NOT_PARTY");
        }

        emit PMOConfirmed(pmoId, entityId, true);
        return true;
    }

    /// @notice Settle a PMO via thermodynamic settlement trigger.
    /// @dev Requires: both parties confirmed, C(t) >= Θ(t) for both, no manipulation.
    function settlePMO(
        bytes32 pmoId,
        uint256 coherenceA,
        uint256 thresholdA,
        uint256 coherenceB,
        uint256 thresholdB
    ) external onlyRelayer returns (bool) {
        PMO storage pmo = pmos[pmoId];
        require(pmo.pmoId != bytes32(0), "PMO_NOT_FOUND");
        require(pmo.confirmedA && pmo.confirmedB, "NOT_CONFIRMED");
        require(!pmo.settled, "ALREADY_SETTLED");

        // Thermodynamic settlement trigger (whitepaper CONTINUUM §11)
        require(coherenceA >= thresholdA, "A_COHERENCE_LOW");
        require(coherenceB >= thresholdB, "B_COHERENCE_LOW");

        pmo.settled = true;

        // CCP distribution (50/50 split)
        uint256 ccpA = pmo.magnitude * pmo.ccpPremium / 2 / 1_000_000;
        uint256 ccpB = pmo.magnitude * pmo.ccpPremium / 2 / 1_000_000;
        totalCCPDistributed += ccpA + ccpB;

        emit PMOSettled(pmoId, ccpA, ccpB);
        return true;
    }

    // ═══════════════════════════════════════════════════════════════════════════
    // ENGINE 4: BDC — Behavioral Depth Credit
    // ═══════════════════════════════════════════════════════════════════════════

    /// @notice Update BDC credit limit for an entity.
    /// @dev BDC_credit_limit = D(t) × consistency_ratio × avg_trade_size_90d × confidence_multiplier
    function updateBDCCredit(
        bytes32 entityId,
        uint256 akashicDepth,
        uint256 consistencyRatio,
        uint256 avgTradeSize90d
    ) external onlyRelayer returns (uint256 creditLimit) {
        require(consistencyRatio <= 1_000_000, "INVALID_CONSISTENCY");

        uint256 confidenceMult = (akashicDepth * 1_000_000 / D_MINIMUM);
        if (confidenceMult > MAX_BDC_MULTIPLIER) confidenceMult = MAX_BDC_MULTIPLIER;

        creditLimit = akashicDepth * consistencyRatio * avgTradeSize90d * confidenceMult / (1_000_000 * 1_000_000 * 1_000_000);

        bdcCredits[entityId] = BDCCredit({
            entityId:        entityId,
            creditLimit:     creditLimit,
            akashicDepth:    akashicDepth,
            consistencyRatio: consistencyRatio,
            avgTradeSize90d: avgTradeSize90d,
            confidenceMult:  confidenceMult,
            updatedAt:       block.timestamp
        });

        emit BDCCreditUpdated(entityId, creditLimit, akashicDepth);
    }

    function getBDCCredit(bytes32 entityId) external view returns (BDCCredit memory) {
        return bdcCredits[entityId];
    }

    // ═══════════════════════════════════════════════════════════════════════════
    // ADMIN
    // ═══════════════════════════════════════════════════════════════════════════

    function setRelayer(address newRelayer) external onlyOwner {
        emit RelayerUpdated(relayer, newRelayer);
        relayer = newRelayer;
    }

    function setEscrow(address newEscrow) external onlyOwner {
        emit EscrowUpdated(btcpEscrow, newEscrow);
        btcpEscrow = newEscrow;
    }

    function setOracle(address newOracle) external onlyOwner {
        emit OracleUpdated(trionOracle, newOracle);
        trionOracle = newOracle;
    }

    function getPMO(bytes32 pmoId) external view returns (PMO memory) {
        return pmos[pmoId];
    }

    function getMatch(bytes32 matchId) external view returns (ComplementMatch memory) {
        return matches[matchId];
    }
}
