// SPDX-License-Identifier: CC0-1.0
pragma solidity ^0.8.24;

/**
 * @title  TRIONSensingOracle
 * @notice Publishes BEHAVIORAL_TRUTH signals computed by the TRION oracle.
 *         Privacy guarantee: zero behavioral content is ever stored on-chain.
 *         Only the coherence score and public commitment hash are written.
 *         The raw behavior is never transmitted or stored.
 * @author Hudu Yusuf (Analys) | CC0
 */
contract TRIONSensingOracle {
    address public owner;
    mapping(address => bool) public authorizedRelayers;

    uint256 public constant FRESHNESS_BLOCKS = 300;
    uint256 public totalSignals;

    struct Signal {
        bytes32 entityId;
        bytes32 publicCommitment;
        uint256 coherenceScore;   // scaled ×1e6  (e.g. 847000 = 0.847)
        uint256 threshold;        // scaled ×1e6
        bool    coherent;
        uint8   limitingPlane;    // 0=Physical 1=Mental 2=Spiritual 3=Conscious 4=ANIMA
        uint64  signalBlock;
    }

    mapping(bytes32 => Signal)  public latestSignal;
    mapping(bytes32 => uint256) public signalCount;

    event BehavioralTruth(
        bytes32 indexed entityId,
        bytes32 publicCommitment,
        uint256 coherenceScore,
        uint256 threshold,
        bool    coherent,
        uint8   limitingPlane,
        uint256 blockNumber
    );
    event SilenceSignal(
        bytes32 indexed entityId,
        uint256 coherenceScore,
        uint256 threshold,
        uint8   limitingPlane,
        uint256 coherenceGap
    );
    event RelayerSet(address indexed relayer, bool authorized);

    constructor(address initialRelayer) {
        owner = msg.sender;
        authorizedRelayers[initialRelayer] = true;
        emit RelayerSet(initialRelayer, true);
    }

    modifier onlyOwner()   { require(msg.sender == owner, "Not owner"); _; }
    modifier onlyRelayer() { require(authorizedRelayers[msg.sender], "Not relayer"); _; }

    // ── Single publish ───────────────────────────────────────────────────────

    function publishBehavioralTruth(
        bytes32 entityId,
        bytes32 publicCommitment,
        uint256 coherenceScore,
        uint256 threshold,
        bool    coherent,
        uint8   limitingPlane
    ) external onlyRelayer {
        require(entityId != bytes32(0) && publicCommitment != bytes32(0), "Invalid input");
        require(limitingPlane <= 4, "Invalid plane");
        require(coherenceScore <= 1_000_000 && threshold <= 1_000_000, "Out of range");

        latestSignal[entityId] = Signal(
            entityId, publicCommitment, coherenceScore,
            threshold, coherent, limitingPlane,
            uint64(block.number)
        );
        signalCount[entityId]++;
        totalSignals++;

        if (coherent) {
            emit BehavioralTruth(
                entityId, publicCommitment, coherenceScore,
                threshold, coherent, limitingPlane, block.number
            );
        } else {
            uint256 gap = threshold > coherenceScore ? threshold - coherenceScore : 0;
            emit SilenceSignal(entityId, coherenceScore, threshold, limitingPlane, gap);
        }
    }

    // ── Batch publish ─────────────────────────────────────────────────────────

    function publishBatchBehavioralTruth(
        bytes32[] calldata entityIds,
        bytes32[] calldata commitments,
        uint256[] calldata scores,
        uint256[] calldata thresholds,
        bool[]    calldata coherents,
        uint8[]   calldata planes
    ) external onlyRelayer {
        uint256 len = entityIds.length;
        require(len > 0 && len <= 50, "Batch 1-50");
        require(
            commitments.length == len &&
            scores.length == len &&
            thresholds.length == len &&
            coherents.length == len &&
            planes.length == len,
            "Array length mismatch"
        );

        for (uint256 i = 0; i < len; i++) {
            require(planes[i] <= 4, "Invalid plane");
            require(scores[i] <= 1_000_000 && thresholds[i] <= 1_000_000, "Out of range");

            latestSignal[entityIds[i]] = Signal(
                entityIds[i], commitments[i], scores[i],
                thresholds[i], coherents[i], planes[i],
                uint64(block.number)
            );
            signalCount[entityIds[i]]++;
            totalSignals++;

            if (coherents[i]) {
                emit BehavioralTruth(
                    entityIds[i], commitments[i], scores[i],
                    thresholds[i], coherents[i], planes[i], block.number
                );
            } else {
                uint256 gap = thresholds[i] > scores[i] ? thresholds[i] - scores[i] : 0;
                emit SilenceSignal(entityIds[i], scores[i], thresholds[i], planes[i], gap);
            }
        }
    }

    // ── View functions ───────────────────────────────────────────────────────

    function isCoherent(bytes32 entityId) external view returns (bool) {
        Signal storage s = latestSignal[entityId];
        if (s.signalBlock == 0) return false;
        if (block.number > s.signalBlock + FRESHNESS_BLOCKS) return false;
        return s.coherent;
    }

    function getCoherenceDetail(bytes32 entityId)
        external view
        returns (
            uint256 score,
            uint256 thresh,
            bool    coherent,
            uint8   plane,
            uint256 blk,
            bool    fresh
        )
    {
        Signal storage s = latestSignal[entityId];
        return (
            s.coherenceScore, s.threshold, s.coherent,
            s.limitingPlane, s.signalBlock,
            block.number <= s.signalBlock + FRESHNESS_BLOCKS
        );
    }

    function planeName(uint8 p) external pure returns (string memory) {
        if (p == 0) return "Physical";
        if (p == 1) return "Mental";
        if (p == 2) return "Spiritual";
        if (p == 3) return "Conscious";
        if (p == 4) return "ANIMA";
        return "Unknown";
    }

    // ── Admin ────────────────────────────────────────────────────────────────

    function setRelayer(address r, bool auth) external onlyOwner {
        authorizedRelayers[r] = auth;
        emit RelayerSet(r, auth);
    }

    function transferOwnership(address n) external onlyOwner {
        require(n != address(0), "Zero address");
        owner = n;
    }
}
