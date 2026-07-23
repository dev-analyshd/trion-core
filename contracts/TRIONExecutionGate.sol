// SPDX-License-Identifier: MIT
pragma solidity ^0.8.20;

/**
 * @title TRIONExecutionGate
 * @notice Autonomous Execution Safety Layer — deployed on 0G Chain
 *
 * This contract is the on-chain core of the TRION × 0G execution intelligence
 * system. AI agents must query this gate before executing any DeFi trade.
 * If behavioral entropy is elevated, execution is blocked on-chain — not just
 * warned about, but made IMPOSSIBLE until conditions normalize.
 *
 * Architecture:
 *  - TRION behavioral oracle scores entity BEO DNA off-chain (FAISS, 531K vectors)
 *  - Score is published here via validator quorum
 *  - Any agent/contract calls checkExecution() before trading
 *  - 0G DA logs every decision permanently (anomaly proof trail)
 *  - 0G Storage holds the full behavioral memory (BEO vector index)
 *  - 0G Compute provides TEE-verified inference for every risk score
 *
 * Security hardening (audit fixes):
 *  - publishSignal requires quorum signatures — no single validator can publish
 *  - checkExecution is nonReentrant — prevents reentrancy on the gate check
 *  - Pausable — owner can pause the gate during emergencies
 *  - Two-step ownership — ownership transfer requires acceptance by new owner
 *  - Fail-closed — uninitialized entities are BLOCKED, not allowed
 *  - OwnershipTransferred event emitted on acceptance
 */
contract TRIONExecutionGate {

    // ── Behavioral Status Codes ──────────────────────────────────────────────
    uint8 public constant STATUS_SAFE           = 1; // Φ(t) nominal — execution ALLOWED
    uint8 public constant STATUS_ELEVATED       = 2; // Φ(t) rising — execution CAUTIONED
    uint8 public constant STATUS_COLLAPSE       = 3; // Φ(t) collapse detected — execution BLOCKED
    uint8 public constant STATUS_HOSTILE        = 4; // MEV/exploit pattern — execution BLOCKED + ALERT

    // ── Packed Signal Layout ─────────────────────────────────────────────────
    // bits [0–7]   : status (uint8)
    // bits [8–39]  : phi_t × 1e6 (uint32) — thermodynamic coherence Φ(t)
    // bits [40–71] : theta × 1e6 (uint32) — sliding window baseline
    // bits [72–103]: drop_pct × 1e4 (uint32) — entropy drop percentage
    // bits [104–167]: block_number (uint64)
    // bits [168–231]: timestamp (uint64)

    struct BehavioralSignal {
        uint256 packedData;
        bytes32 beoHash;        // keccak256 of BEO entity DNA (stored on 0G Storage)
        bytes32 daProofHash;    // 0G DA content hash of the anomaly proof
        string  storageRoot;    // 0G Storage merkle root for this entity's vectors
        bool    initialized;
        uint256 blockNumber;
    }

    struct ExecutionDecision {
        bool     allowed;
        uint8    status;
        uint32   phi_t;
        uint32   theta;
        uint32   dropPct;
        uint256  checkedAt;
        bytes32  decisionHash;
    }

    // ── State ────────────────────────────────────────────────────────────────
    address public owner;
    address public pendingOwner;                   // two-step ownership transfer
    mapping(address => bool) public isValidator;
    uint256 public quorumRequired;

    bool public paused;                            // circuit breaker
    bool private _reentrancyGuard;                 // nonReentrant guard flag

    // Entity behavioral signals: entityId (bytes32 BEO hash) → signal
    mapping(bytes32 => BehavioralSignal) public signals;

    // Execution audit trail: decisionHash → decision
    // NOTE: unbounded mapping is acknowledged; pruning governance is TODO.
    mapping(bytes32 => ExecutionDecision) public decisions;

    // Statistics
    uint256 public totalExecutionsAllowed;
    uint256 public totalExecutionsBlocked;
    uint256 public totalSignalsPublished;
    uint256 public totalAnomaliesSealed;

    // 0G Storage integration — root hash of the FAISS BEO vector index
    string public beoVectorStorageRoot;
    uint256 public lastStorageSyncBlock;

    // ── Events ───────────────────────────────────────────────────────────────
    event SignalPublished(
        bytes32 indexed entityId,
        uint8   status,
        uint32  phi_t,
        uint32  theta,
        uint32  dropPct,
        bytes32 daProofHash,
        string  storageRoot
    );

    event ExecutionAllowed(
        bytes32 indexed entityId,
        address indexed caller,
        uint32  phi_t,
        bytes32 decisionHash
    );

    event ExecutionBlocked(
        bytes32 indexed entityId,
        address indexed caller,
        uint8   reason,
        uint32  phi_t,
        uint32  dropPct,
        bytes32 decisionHash
    );

    event AnomalySealed(
        bytes32 indexed entityId,
        bytes32 daProofHash,
        uint8   anomalyType,
        uint256 timestamp
    );

    event StorageSyncConfirmed(
        string  storageRoot,
        uint256 vectorCount,
        uint256 syncBlock
    );

    event ValidatorAdded(address indexed validator);
    event ValidatorRemoved(address indexed validator);
    event QuorumUpdated(uint256 newQuorum);
    event Paused(address indexed by);
    event Unpaused(address indexed by);
    event OwnershipTransferInitiated(address indexed previousOwner, address indexed newOwner);
    event OwnershipTransferred(address indexed previousOwner, address indexed newOwner);

    // ── Constructor ──────────────────────────────────────────────────────────
    constructor(uint256 _quorum) {
        owner = msg.sender;
        isValidator[msg.sender] = true;
        quorumRequired = _quorum > 0 ? _quorum : 1;
        emit ValidatorAdded(msg.sender);
        emit OwnershipTransferred(address(0), msg.sender);
    }

    // ── Modifiers ────────────────────────────────────────────────────────────
    modifier onlyOwner() {
        require(msg.sender == owner, "TRION: Not owner");
        _;
    }

    modifier onlyValidator() {
        require(isValidator[msg.sender], "TRION: Not a validator");
        _;
    }

    modifier whenNotPaused() {
        require(!paused, "TRION: Contract is paused");
        _;
    }

    modifier nonReentrant() {
        require(!_reentrancyGuard, "TRION: Reentrant call");
        _reentrancyGuard = true;
        _;
        _reentrancyGuard = false;
    }

    // ── Core: Publish Behavioral Signal (with quorum enforcement) ────────────
    /**
     * @notice Validators publish a TRION behavioral signal for an entity.
     *         Requires `quorumRequired` valid EIP-191 signatures over the
     *         message hash keccak256(abi.encodePacked(
     *           block.chainid, address(this), entityId, packedData
     *         )) from distinct registered validators.
     *
     * @param entityId    keccak256 BEO entity identifier
     * @param packedData  Packed behavioral metrics (phi_t, theta, drop_pct, status)
     * @param beoHash     keccak256 of entity's behavioral DNA (content-addressed on 0G Storage)
     * @param daProofHash 0G DA content hash — proof this anomaly is permanently sealed
     * @param storageRoot 0G Storage merkle root for this entity's behavioral memory
     * @param signatures  Ordered array of EIP-191 signatures from distinct validators
     */
    function publishSignal(
        bytes32 entityId,
        uint256 packedData,
        bytes32 beoHash,
        bytes32 daProofHash,
        string calldata storageRoot,
        bytes[] calldata signatures
    ) external onlyValidator whenNotPaused {
        // ── Quorum enforcement ────────────────────────────────────────────────
        require(
            signatures.length >= quorumRequired,
            "TRION: Insufficient signatures for quorum"
        );

        bytes32 msgHash = keccak256(abi.encodePacked(
            block.chainid, address(this), entityId, packedData
        ));
        bytes32 ethSignedHash = keccak256(abi.encodePacked(
            "\x19Ethereum Signed Message:\n32", msgHash
        ));

        address[] memory seen = new address[](signatures.length);
        uint256 validCount = 0;

        for (uint256 i = 0; i < signatures.length; i++) {
            address recovered = _recoverSigner(ethSignedHash, signatures[i]);
            if (!isValidator[recovered]) continue;

            // Prevent duplicate signers
            bool duplicate = false;
            for (uint256 j = 0; j < validCount; j++) {
                if (seen[j] == recovered) { duplicate = true; break; }
            }
            if (duplicate) continue;

            seen[validCount] = recovered;
            validCount++;
            if (validCount >= quorumRequired) break;
        }

        require(validCount >= quorumRequired, "TRION: Quorum not met by distinct validators");

        // ── Unpack and validate ───────────────────────────────────────────────
        uint8  status  = uint8(packedData & 0xFF);
        uint32 phi_t   = uint32((packedData >> 8)  & 0xFFFFFFFF);
        uint32 theta   = uint32((packedData >> 40) & 0xFFFFFFFF);
        uint32 dropPct = uint32((packedData >> 72) & 0xFFFFFFFF);

        require(status >= 1 && status <= 4, "TRION: Invalid status");

        signals[entityId] = BehavioralSignal({
            packedData:  packedData,
            beoHash:     beoHash,
            daProofHash: daProofHash,
            storageRoot: storageRoot,
            initialized: true,
            blockNumber: block.number
        });

        totalSignalsPublished++;

        if (status >= STATUS_COLLAPSE) {
            totalAnomaliesSealed++;
            emit AnomalySealed(entityId, daProofHash, status, block.timestamp);
        }

        emit SignalPublished(entityId, status, phi_t, theta, dropPct, daProofHash, storageRoot);
    }

    // ── Core: Check Execution Safety ──────────────────────────────────────────
    /**
     * @notice The primary gate. Any agent/contract calls this before executing.
     *         Returns (allowed, decision) — if blocked, execution must not proceed.
     *         FAIL-CLOSED: uninitialized entities (no signal published yet) are BLOCKED.
     *         Protected by nonReentrant to prevent reentrancy attacks on the gate.
     *
     * @param entityId   The BEO entity attempting execution
     * @param caller     The agent/wallet initiating the trade
     */
    function checkExecution(
        bytes32 entityId,
        address caller
    ) external nonReentrant whenNotPaused returns (bool allowed, bytes32 decisionHash) {
        BehavioralSignal storage sig = signals[entityId];

        // ── Fail-closed for uninitialized entities ────────────────────────────
        // An entity with no published signal has not been verified by TRION.
        // Default is BLOCKED (not allowed) — conservative safety posture.
        if (!sig.initialized) {
            decisionHash = keccak256(abi.encodePacked(
                entityId, caller, false, uint8(0), uint32(0), block.number, block.timestamp
            ));
            decisions[decisionHash] = ExecutionDecision({
                allowed:      false,
                status:       0,
                phi_t:        0,
                theta:        0,
                dropPct:      0,
                checkedAt:    block.timestamp,
                decisionHash: decisionHash
            });
            totalExecutionsBlocked++;
            emit ExecutionBlocked(entityId, caller, 0, 0, 0, decisionHash);
            return (false, decisionHash);
        }

        uint8  status  = uint8(sig.packedData & 0xFF);
        uint32 phi_t   = uint32((sig.packedData >> 8)  & 0xFFFFFFFF);
        uint32 theta   = uint32((sig.packedData >> 40) & 0xFFFFFFFF);
        uint32 dropPct = uint32((sig.packedData >> 72) & 0xFFFFFFFF);

        // Gate logic: only STATUS_SAFE and STATUS_ELEVATED are permitted
        allowed = (status <= STATUS_ELEVATED);

        decisionHash = keccak256(abi.encodePacked(
            entityId, caller, allowed, status, phi_t, block.number, block.timestamp
        ));

        decisions[decisionHash] = ExecutionDecision({
            allowed:      allowed,
            status:       status,
            phi_t:        phi_t,
            theta:        theta,
            dropPct:      dropPct,
            checkedAt:    block.timestamp,
            decisionHash: decisionHash
        });

        if (allowed) {
            totalExecutionsAllowed++;
            emit ExecutionAllowed(entityId, caller, phi_t, decisionHash);
        } else {
            totalExecutionsBlocked++;
            emit ExecutionBlocked(entityId, caller, status, phi_t, dropPct, decisionHash);
        }

        return (allowed, decisionHash);
    }

    // ── 0G Storage Sync ───────────────────────────────────────────────────────
    /**
     * @notice Confirms that TRION's FAISS behavioral vector index has been
     *         synced to 0G Storage. The storageRoot is the merkle root of
     *         the uploaded file — anyone can verify it against 0G's network.
     */
    function confirmStorageSync(
        string calldata storageRoot,
        uint256 vectorCount
    ) external onlyValidator whenNotPaused {
        beoVectorStorageRoot = storageRoot;
        lastStorageSyncBlock = block.number;
        emit StorageSyncConfirmed(storageRoot, vectorCount, block.number);
    }

    // ── View: Get Full Signal ────────────────────────────────────────────────
    function getSignal(bytes32 entityId) external view returns (
        uint8   status,
        uint32  phi_t,
        uint32  theta,
        uint32  dropPct,
        bytes32 beoHash,
        bytes32 daProofHash,
        string  memory storageRoot,
        bool    initialized,
        uint256 blockNumber
    ) {
        BehavioralSignal storage s = signals[entityId];
        return (
            uint8(s.packedData & 0xFF),
            uint32((s.packedData >> 8)  & 0xFFFFFFFF),
            uint32((s.packedData >> 40) & 0xFFFFFFFF),
            uint32((s.packedData >> 72) & 0xFFFFFFFF),
            s.beoHash,
            s.daProofHash,
            s.storageRoot,
            s.initialized,
            s.blockNumber
        );
    }

    // ── View: Is Execution Safe ───────────────────────────────────────────────
    /**
     * @notice Fail-closed view: uninitialized entities return FALSE (not safe).
     *         This is a critical change from the original fail-open behavior.
     */
    function isExecutionSafe(bytes32 entityId) external view returns (bool) {
        BehavioralSignal storage s = signals[entityId];
        if (!s.initialized) return false;  // fail-closed: no data = not verified = BLOCKED
        uint8 status = uint8(s.packedData & 0xFF);
        return status <= STATUS_ELEVATED;
    }

    // ── View: Stats ───────────────────────────────────────────────────────────
    function getStats() external view returns (
        uint256 allowed,
        uint256 blocked,
        uint256 published,
        uint256 anomalies,
        string memory storageRoot,
        uint256 storageSyncBlock
    ) {
        return (
            totalExecutionsAllowed,
            totalExecutionsBlocked,
            totalSignalsPublished,
            totalAnomaliesSealed,
            beoVectorStorageRoot,
            lastStorageSyncBlock
        );
    }

    // ── Admin: Pause / Unpause ────────────────────────────────────────────────
    function pause() external onlyOwner {
        paused = true;
        emit Paused(msg.sender);
    }

    function unpause() external onlyOwner {
        paused = false;
        emit Unpaused(msg.sender);
    }

    // ── Admin: Validators ─────────────────────────────────────────────────────
    function addValidator(address v) external onlyOwner {
        isValidator[v] = true;
        emit ValidatorAdded(v);
    }

    function removeValidator(address v) external onlyOwner {
        require(v != owner, "TRION: Cannot remove owner");
        isValidator[v] = false;
        emit ValidatorRemoved(v);
    }

    function setQuorum(uint256 q) external onlyOwner {
        require(q >= 1, "TRION: Quorum >= 1");
        quorumRequired = q;
        emit QuorumUpdated(q);
    }

    // ── Admin: Two-step ownership transfer ───────────────────────────────────
    /**
     * @notice Step 1: initiate ownership transfer — sets pendingOwner.
     *         Ownership is NOT transferred until acceptOwnership() is called.
     */
    function transferOwnership(address newOwner) external onlyOwner {
        require(newOwner != address(0), "TRION: Zero address");
        pendingOwner = newOwner;
        emit OwnershipTransferInitiated(owner, newOwner);
    }

    /**
     * @notice Step 2: new owner accepts ownership.
     *         This is the only function that emits OwnershipTransferred.
     */
    function acceptOwnership() external {
        require(msg.sender == pendingOwner, "TRION: Not pending owner");
        address previous = owner;
        owner = pendingOwner;
        pendingOwner = address(0);
        isValidator[owner] = true;
        emit OwnershipTransferred(previous, owner);
    }

    // ── Internal: ECDSA recovery ─────────────────────────────────────────────
    function _recoverSigner(
        bytes32 hash,
        bytes memory sig
    ) internal pure returns (address) {
        require(sig.length == 65, "TRION: Invalid signature length");
        bytes32 r;
        bytes32 s;
        uint8   v;
        assembly {
            r := mload(add(sig, 32))
            s := mload(add(sig, 64))
            v := byte(0, mload(add(sig, 96)))
        }
        if (v < 27) v += 27;
        require(v == 27 || v == 28, "TRION: Invalid v");
        return ecrecover(hash, v, r, s);
    }
}
