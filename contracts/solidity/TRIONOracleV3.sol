// SPDX-License-Identifier: MIT
pragma solidity ^0.8.20;


// ── Minimal ECDSA (inlined — replaces @openzeppelin ECDSA dependency) ────────
// EIP-2 compliant: rejects s > secp256k1n/2 and v not in {27, 28}.
library ECDSA {
    function recover(bytes32 hash, bytes memory signature) internal pure returns (address) {
        if (signature.length != 65) return address(0);
        bytes32 r; bytes32 s; uint8 v;
        assembly {
            r := mload(add(signature, 0x20))
            s := mload(add(signature, 0x40))
            v := byte(0, mload(add(signature, 0x60)))
        }
        if (uint256(s) > 0x7FFFFFFFFFFFFFFFFFFFFFFFFFFFFFFF5D576E7357A4501DDFE92F46681B20A0) {
            return address(0); // EIP-2: reject high-s
        }
        if (v != 27 && v != 28) return address(0);
        return ecrecover(hash, v, r, s);
    }
}


// ── Minimal MessageHashUtils (inlined — replaces OZ dependency) ─────────────
library MessageHashUtils {
    function toEthSignedMessageHash(bytes32 hash) internal pure returns (bytes32) {
        return keccak256(abi.encodePacked("\x19Ethereum Signed Message:\n32", hash));
    }
}


// ── Minimal Ownable (inlined — replaces OZ dependency) ──────────────────────
abstract contract Ownable {
    address private _owner;
    event OwnershipTransferred(address indexed previousOwner, address indexed newOwner);
    constructor() { _transferOwnership(msg.sender); }
    modifier onlyOwner() { require(msg.sender == owner(), "Ownable: caller is not the owner"); _; }
    function owner() public view returns (address) { return _owner; }
    function transferOwnership(address newOwner) public virtual onlyOwner {
        require(newOwner != address(0), "Ownable: new owner is the zero address");
        _transferOwnership(newOwner);
    }
    function _transferOwnership(address newOwner) internal virtual {
        address oldOwner = _owner;
        _owner = newOwner;
        emit OwnershipTransferred(oldOwner, newOwner);
    }
}

import "./interfaces/ITRIONOracleV3.sol";

contract TRIONOracleV3 is ITRIONOracleV3, Ownable {
    using ECDSA for bytes32;

    // Signal struct inherited from ITRIONOracleV3

    // BehavioralSignal struct inherited from ITRIONOracleV3

    mapping(bytes32 => BehavioralSignal) public behavioralSignals;
    mapping(bytes32 => uint256) public signalCountByEntity;
    uint256 public totalBehavioralSignals;

    mapping(bytes32 => Signal) public signals;
    mapping(address => bool) public isValidator;
    uint256 public quorumRequired = 2;

    // BTCPRoute struct inherited from ITRIONOracleV3

    mapping(bytes32 => BTCPRoute) public btcpRoutes;
    // BTCPRoutePublished event inherited from ITRIONOracleV3

    /// @notice Emitted when a full behavioral signal is published on-chain.
    // BehavioralSignalPublished event inherited from ITRIONOracleV3

    /// @notice Emitted when SILENCE is formally recorded (C(t) < Θ(t)).
    // SilenceRecorded event inherited from ITRIONOracleV3

    /// @notice Emitted when SILENCE is formally recorded — V2 with the full
    ///         structured-null payload (coherence gap + eta). Both V1 and V2
    ///         are emitted on silence (V1 topic0 kept stable for existing
    ///         indexers).
    // SilenceRecordedV2 event inherited from ITRIONOracleV3

    constructor() {
        isValidator[msg.sender] = true;
    }

    /// @notice Freshness window for BTCP route safety verdicts (seconds).
    ///         Matches the legacy 300s signal freshness bound.
    uint256 public constant BTCP_ROUTE_FRESHNESS_SECONDS = 300;

    // ── BTCP route quorum attestations ────────────────────────────────────────
    // SECURITY (whitepaper: "TRION consensus is the only oracle"): a route
    // verdict must be backed by the same quorum discipline as signals.
    // Previously ANY single validator (or the owner) could mark any route
    // safe AND overwrite prior verdicts — strictly weaker than
    // publishSignal(), which already required quorumRequired ECDSA
    // validator signatures. Route values are now immutable after the first
    // attestation: later attestations must submit identical values (a
    // mismatch is a dispute — the route simply never reaches quorum,
    // fail-closed). A route only becomes verifiable once at least
    // quorumRequired distinct authorized attestors have attested.
    mapping(bytes32 => mapping(address => bool)) public routeAttested;
    mapping(bytes32 => uint256) public routeAttestationCount;

    // ── Publish/attest BTCP Route signal (Fix 1, quorum-gated) ──────────────
    // Called by relayers/validators BEFORE the escrow release attempt.
    // Each distinct authorized caller may attest once per routeId. The
    // first attestation writes the route values (immutable thereafter);
    // each new distinct attestor refreshes the freshness timestamp.
    // verifyExecution() only returns isSafe=true when
    // routeAttestationCount >= quorumRequired — the same bar as
    // publishSignal().
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

        BTCPRoute storage route = btcpRoutes[routeId];
        if (route.timestamp == 0) {
            // First attestation — values become immutable for this routeId.
            route.anchorBH    = anchorBH;
            route.executionBH = executionBH;
            route.coherence   = coherenceScore;
            route.threshold   = thresholdScore;
            route.isSafe      = coherenceScore >= thresholdScore;
            route.timestamp   = block.timestamp;
        } else {
            // Subsequent attestations must match the etched values exactly.
            // A mismatched validator is treated as a dispute — reverting
            // keeps the route below quorum (fail-closed) instead of letting
            // one party overwrite or flip another's verdict.
            require(
                route.anchorBH == anchorBH &&
                route.executionBH == executionBH &&
                route.coherence == coherenceScore &&
                route.threshold == thresholdScore,
                "TRION: route values mismatch - disputed"
            );
            route.timestamp = block.timestamp; // freshness refreshed by attestor
        }

        if (!routeAttested[routeId][msg.sender]) {
            routeAttested[routeId][msg.sender] = true;
            routeAttestationCount[routeId]++;
        }
        emit BTCPRoutePublished(routeId, coherenceScore >= thresholdScore);
    }

    // ── Publish rich behavioral signal (V3 enhancement) ─────────────────────
    /// @notice Publish a full behavioral signal with entity context and plane data.
    /// @dev Only callable by owner or authorized validator.
    function publishBehavioralSignal(BehavioralSignal calldata s) external {
        require(
            msg.sender == owner() || isValidator[msg.sender],
            "TRION: not authorized"
        );
        require(s.limitingPlane <= 4, "TRION: invalid plane index");

        BehavioralSignal memory sig = s;
        sig.timingPacked = (uint256(uint64(block.number)) << 64) | uint256(uint64(block.timestamp));
        sig.initialized  = true;

        behavioralSignals[s.entityId] = sig;

        signalCountByEntity[s.entityId]++;
        totalBehavioralSignals++;

        uint64 blk = uint64(sig.timingPacked >> 64);
        emit BehavioralSignalPublished(
            sig.entityId, sig.publicCommitment, sig.coherenceScore, sig.threshold,
            sig.moatFactor, sig.coherent, sig.limitingPlane, sig.planesPacked,
            blk, uint64(sig.timingPacked)
        );

        // Also emit SilenceRecorded when not coherent
        if (!sig.coherent) {
            uint256 gap = sig.threshold > sig.coherenceScore ? sig.threshold - sig.coherenceScore : 0;
            emit SilenceRecorded(sig.entityId, sig.coherenceScore, sig.threshold, sig.limitingPlane, gap, blk);
            // SECURITY FIX (P1, verification matrix #20): SILENCE emission must
            // carry coherence_gap AND eta. eta_blocks = int(gap × 1000) per
            // core/master/coherence.py, with the on-chain gap in ×1e6 fixed
            // point → etaBlocks = gap / 1000. V2 event adds the eta field while
            // V1 keeps its original topic0 for backward compatibility.
            uint256 etaBlocks = gap / 1000;
            emit SilenceRecordedV2(sig.entityId, sig.coherenceScore, sig.threshold, sig.limitingPlane, gap, etaBlocks, blk);
        }
    }

    /// @notice Unpack a plane score from planesPacked. planeIndex 0=phi 1=mental 2=sigma 3=conscious 4=anima.
    function unpackPlane(uint256 planesPacked, uint8 planeIndex) external pure returns (uint64) {
        return uint64(planesPacked >> (uint256(planeIndex) * 32));
    }

    /// @notice Pack five plane scores (×1e6) into one uint256.
    function packPlanes(uint64 phi, uint64 mental, uint64 sigma, uint64 conscious, uint64 anima)
        external pure returns (uint256)
    {
        return uint256(uint32(phi))
            | (uint256(uint32(mental)) << 32)
            | (uint256(uint32(sigma)) << 64)
            | (uint256(uint32(conscious)) << 96)
            | (uint256(uint32(anima)) << 128);
    }

    /// @notice Get the core behavioral signal fields for an entity.
    function getBehavioralSignal(bytes32 entityId)
        external view
        returns (
            bytes32 publicCommitment,
            uint256 coherenceScore,
            uint256 threshold,
            uint256 moatFactor,
            bool coherent,
            uint8 limitingPlane,
            bool initialized
        )
    {
        BehavioralSignal memory s = behavioralSignals[entityId];
        return (
            s.publicCommitment, s.coherenceScore, s.threshold, s.moatFactor,
            s.coherent, s.limitingPlane, s.initialized
        );
    }

    /// @notice Get the five-plane breakdown (unpacked) + block/timestamp.
    function getBehavioralSignalPlanes(bytes32 entityId)
        external view
        returns (
            uint64 phiPlane,
            uint64 mentalPlane,
            uint64 sigmaPlane,
            uint64 consciousPlane,
            uint64 animaPlane,
            uint64 signalBlock,
            uint64 signalTimestamp
        )
    {
        uint256 p = behavioralSignals[entityId].planesPacked;
        uint256 t = behavioralSignals[entityId].timingPacked;
        return (
            uint64(uint32(p)),
            uint64(uint32(p >> 32)),
            uint64(uint32(p >> 64)),
            uint64(uint32(p >> 96)),
            uint64(uint32(p >> 128)),
            uint64(t >> 64),
            uint64(t)
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
        // Check BTCP route registry first.
        // SECURITY: BTCP routes are subject to the same freshness window as
        // legacy signals — a stale "safe" verdict must not be replayable
        // forever (previously routes never expired).
        // SECURITY: a route verdict additionally requires
        // routeAttestationCount >= quorumRequired distinct attestations —
        // a single-attested route is NOT verifiable (fail-closed).
        BTCPRoute memory route = btcpRoutes[txId];
        if (route.timestamp > 0) {
            bool routeFresh = (block.timestamp - route.timestamp) < BTCP_ROUTE_FRESHNESS_SECONDS;
            bool routeQuorum = routeAttestationCount[txId] >= quorumRequired;
            return (
                route.isSafe && routeFresh && routeQuorum,
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
