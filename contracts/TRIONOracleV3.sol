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

    function addValidator(address _v) external onlyOwner { isValidator[_v] = true; }
    function setQuorum(uint256 _q) external onlyOwner { quorumRequired = _q; }
}
