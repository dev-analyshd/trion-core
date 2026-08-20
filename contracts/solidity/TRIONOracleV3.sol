// SPDX-License-Identifier: MIT
pragma solidity ^0.8.20;

import "@openzeppelin/contracts/utils/cryptography/ECDSA.sol";
import "@openzeppelin/contracts/utils/cryptography/MessageHashUtils.sol";
import "@openzeppelin/contracts/access/Ownable.sol";
import "./interfaces/ITRIONOracleV3.sol";

contract TRIONOracleV3 is ITRIONOracleV3, Ownable {
    using ECDSA for bytes32;

    // ── Legacy signal storage ────────────────────────────────────────────────
    struct Signal {
        uint256 packedData; // [0-7: Status] [8-39: C(t)] [40-71: Threshold] [72-135: BlockNum] [136-199: Timestamp]
        bool initialized;
    }

    // ── Rich behavioral signal storage (V3 enhancement) ─────────────────────
    /// @notice Full behavioral signal with entity context and plane data.
    struct BehavioralSignal {
        bytes32 entityId;           // BEO entity identifier
        bytes32 publicCommitment;   // Hash of signal parameters (no behavior leakage)
        uint256 coherenceScore;     // C(t) × 1e6
        uint256 threshold;          // Θ(t) × 1e6
        uint256 moatFactor;         // Economic moat M_moat × 1e6
        bool coherent;              // C(t) ≥ Θ(t)
        uint8 limitingPlane;        // 0=Physical, 1=Mental, 2=Spiritual, 3=Conscious, 4=ANIMA
        uint64 phiPlane;            // Φ(t) × 1e6
        uint64 mentalPlane;         // M(t) × 1e6
        uint64 sigmaPlane;          // Σ(t) × 1e6
        uint64 consciousPlane;      // K(t) × 1e6
        uint64 animaPlane;          // A(t) × 1e6
        uint64 signalBlock;         // Block number of publication
        uint64 signalTimestamp;     // Timestamp of publication
        bool initialized;
    }

    mapping(bytes32 => BehavioralSignal) public behavioralSignals;
    mapping(bytes32 => uint256) public signalCountByEntity;
    uint256 public totalBehavioralSignals;

    mapping(bytes32 => Signal) public signals;
    mapping(address => bool) public isValidator;
    uint256 public quorumRequired = 2;

    // ── BTCP Route storage (Fix 1) ───────────────────────────────────────────
    struct BTCPRoute {
        bytes32 anchorBH;
        bytes32 executionBH;
        uint256 coherence;
        uint256 threshold;
        bool isSafe;
        uint256 timestamp;
    }

    mapping(bytes32 => BTCPRoute) public btcpRoutes;
    event BTCPRoutePublished(bytes32 indexed routeId, bool isSafe);

    /// @notice Emitted when a full behavioral signal is published on-chain.
    event BehavioralSignalPublished(
        bytes32 indexed entityId,
        bytes32 publicCommitment,
        uint256 coherenceScore,
        uint256 threshold,
        uint256 moatFactor,
        bool coherent,
        uint8 limitingPlane,
        uint64 phiPlane,
        uint64 mentalPlane,
        uint64 sigmaPlane,
        uint64 consciousPlane,
        uint64 animaPlane,
        uint64 signalBlock,
        uint64 signalTimestamp
    );

    /// @notice Emitted when SILENCE is formally recorded (C(t) < Θ(t)).
    event SilenceRecorded(
        bytes32 indexed entityId,
        uint256 coherenceScore,
        uint256 threshold,
        uint8 limitingPlane,
        uint256 coherenceGap,
        uint64 signalBlock
    );

    constructor() Ownable(msg.sender) {
        isValidator[msg.sender] = true;
    }

    // ── Publish BTCP Route signal (Fix 1) ────────────────────────────────────
    // Called by the relayer/owner BEFORE the escrow release attempt.
    // Stores the route with its coherence proof so verifyExecution returns true.
    function publishBTCPRoute(
        bytes32 routeId,
        bytes32 anchorBH,
        bytes32 executionBH,
        uint256 coherenceScore,
        uint256 thresholdScore
    ) external {
        require(
            msg.sender == owner() || isValidator[msg.sender],
            "TRION: not authorized"
        );
        btcpRoutes[routeId] = BTCPRoute({
            anchorBH:    anchorBH,
            executionBH: executionBH,
            coherence:   coherenceScore,
            threshold:   thresholdScore,
            isSafe:      coherenceScore >= thresholdScore,
            timestamp:   block.timestamp
        });
        emit BTCPRoutePublished(routeId, coherenceScore >= thresholdScore);
    }

    // ── Publish rich behavioral signal (V3 enhancement) ─────────────────────
    /// @notice Publish a full behavioral signal with entity context and plane data.
    /// @dev Only callable by owner or authorized validator.
    function publishBehavioralSignal(
        bytes32 entityId,
        bytes32 publicCommitment,
        uint256 coherenceScore,
        uint256 threshold,
        uint256 moatFactor,
        bool coherent,
        uint8 limitingPlane,
        uint64 phiPlane,
        uint64 mentalPlane,
        uint64 sigmaPlane,
        uint64 consciousPlane,
        uint64 animaPlane
    ) external {
        require(
            msg.sender == owner() || isValidator[msg.sender],
            "TRION: not authorized"
        );
        require(limitingPlane <= 4, "TRION: invalid plane index");

        uint64 blk = uint64(block.number);
        uint64 ts = uint64(block.timestamp);

        behavioralSignals[entityId] = BehavioralSignal({
            entityId: entityId,
            publicCommitment: publicCommitment,
            coherenceScore: coherenceScore,
            threshold: threshold,
            moatFactor: moatFactor,
            coherent: coherent,
            limitingPlane: limitingPlane,
            phiPlane: phiPlane,
            mentalPlane: mentalPlane,
            sigmaPlane: sigmaPlane,
            consciousPlane: consciousPlane,
            animaPlane: animaPlane,
            signalBlock: blk,
            signalTimestamp: ts,
            initialized: true
        });

        signalCountByEntity[entityId]++;
        totalBehavioralSignals++;

        emit BehavioralSignalPublished(
            entityId, publicCommitment, coherenceScore, threshold, moatFactor,
            coherent, limitingPlane, phiPlane, mentalPlane, sigmaPlane,
            consciousPlane, animaPlane, blk, ts
        );

        // Also emit SilenceRecorded when not coherent
        if (!coherent) {
            uint256 gap = threshold > coherenceScore ? threshold - coherenceScore : 0;
            emit SilenceRecorded(entityId, coherenceScore, threshold, limitingPlane, gap, blk);
        }
    }

    /// @notice Get the full behavioral signal for an entity.
    function getBehavioralSignal(bytes32 entityId) external view returns (
        bytes32 publicCommitment,
        uint256 coherenceScore,
        uint256 threshold,
        uint256 moatFactor,
        bool coherent,
        uint8 limitingPlane,
        uint64 phiPlane,
        uint64 mentalPlane,
        uint64 sigmaPlane,
        uint64 consciousPlane,
        uint64 animaPlane,
        uint64 signalBlock,
        uint64 signalTimestamp,
        bool initialized
    ) {
        BehavioralSignal memory s = behavioralSignals[entityId];
        return (
            s.publicCommitment, s.coherenceScore, s.threshold, s.moatFactor,
            s.coherent, s.limitingPlane, s.phiPlane, s.mentalPlane, s.sigmaPlane,
            s.consciousPlane, s.animaPlane, s.signalBlock, s.signalTimestamp, s.initialized
        );
    }

    // ── Legacy publishSignal ─────────────────────────────────────────────────
    function publishSignal(bytes32 txId, uint256 packedData, bytes[] calldata signatures) external {
        require(!signals[txId].initialized, "TRION: Signal already etched");
        require(signatures.length >= quorumRequired, "TRION: Insufficient quorum");

        bytes32 messageHash = MessageHashUtils.toEthSignedMessageHash(keccak256(abi.encodePacked(block.chainid, address(this), txId, packedData)));
        
        address lastSigner = address(0);
        for (uint256 i = 0; i < signatures.length; i++) {
            address signer = messageHash.recover(signatures[i]);
            require(isValidator[signer], "TRION: Invalid validator");
            require(signer > lastSigner, "TRION: Signer ordering required");
            lastSigner = signer;
        }

        signals[txId] = Signal(packedData, true);
        
        uint8 status = uint8(packedData & 0xFF);
        uint32 coherence = uint32((packedData >> 8) & 0xFFFFFFFF);
        uint32 threshold = uint32((packedData >> 40) & 0xFFFFFFFF);
        uint64 blockNum = uint64((packedData >> 72) & 0xFFFFFFFFFFFFFFFF);

        emit ThermodynamicSignalEtched(txId, status, coherence, threshold);
        if (status == 1) emit EntropyNominal(txId, coherence, threshold, blockNum);
        if (status != 1) emit ThermodynamicCollapseIntercepted(txId, msg.sender, coherence, threshold, packedData);
    }

    // ── verifyExecution — checks BTCP routes first, then legacy signals ──────
    // Fix 1: BTCP routes are checked before legacy signals. This ensures that
    // publishBTCPRoute() → verifyExecution() returns isSafe = true and the
    // escrow releases via TRION consensus rather than falling back to timeout.
    function verifyExecution(bytes32 txId)
        external view returns (bool isSafe, uint32 coherence, uint32 threshold)
    {
        // Check BTCP route registry first
        BTCPRoute memory route = btcpRoutes[txId];
        if (route.timestamp > 0) {
            return (
                route.isSafe,
                uint32(route.coherence > type(uint32).max ? type(uint32).max : route.coherence),
                uint32(route.threshold > type(uint32).max ? type(uint32).max : route.threshold)
            );
        }

        // Fallback: check legacy signal storage
        Signal memory s = signals[txId];
        if (!s.initialized) {
            return (false, 0, 0);
        }

        uint8 sigStatus = uint8(s.packedData & 0xFF);
        uint32 c = uint32((s.packedData >> 8) & 0xFFFFFFFF);
        uint32 t = uint32((s.packedData >> 40) & 0xFFFFFFFF);
        uint64 blockNum = uint64((s.packedData >> 72) & 0xFFFFFFFFFFFFFFFF);
        uint64 timestamp = uint64((s.packedData >> 136) & 0xFFFFFFFFFFFFFFFF);

        bool safe    = (sigStatus == 1);
        bool recent  = (block.timestamp - timestamp < 300);
        bool bounded = (block.number - blockNum < 50);

        return (safe && recent && bounded, c, t);
    }

    function getSignalInfo(bytes32 txId) external view returns (uint8, uint32, uint32, uint64, uint64) {
        uint256 p = signals[txId].packedData;
        return (uint8(p & 0xFF), uint32((p >> 8) & 0xFFFFFFFF), uint32((p >> 40) & 0xFFFFFFFF), uint64((p >> 72) & 0xFFFFFFFFFFFFFFFF), uint64((p >> 136) & 0xFFFFFFFFFFFFFFFF));
    }

    function addValidator(address _v) external onlyOwner {
        // PHASE-1-SECURITY: prevent registering the zero address as a validator.
        require(_v != address(0), "TRION: zero address");
        isValidator[_v] = true;
    }
    function setQuorum(uint256 _q) external onlyOwner {
        // PHASE-1-SECURITY: enforce a sane minimum quorum (>=1).
        require(_q >= 1, "TRION: quorum < 1");
        quorumRequired = _q;
    }
}
