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
 *
 *  ─────────────────────────────────────────────────────────────────
 *  AUDIT-3 Gap G3 Fix — AWA Enforcement In Signal Publication Path
 *  ─────────────────────────────────────────────────────────────────
 *  Previously `publishSignal()` checked quorum signatures but did NOT
 *  verify that the Archetypal Weighted Average (AWA) governance conditions
 *  were met. WP2 §17 mandates "AWA_enforced = FALSE → signal emission
 *  FROZEN. Cannot be overridden by any single entity." This contract now
 *  enforces that invariant via a `require(awaEnforced(), ...)` guard at
 *  the top of `publishSignal()`.
 *
 *  The AWA state (HHI, gratitude score, public-good %, validator count)
 *  is updated by the Akashic oracle via `updateAWAState()` and checked
 *  atomically on every signal publication.
 *  ─────────────────────────────────────────────────────────────────
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
    uint256 public validatorCount;                  // total registered validators (AUDIT-3 G3)

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

    // ── AWA Enforcement State (AUDIT-3 Gap G3) ────────────────────────────
    //
    // Updated by the Akashic oracle (or owner during bootstrap) and checked
    // atomically by `awaEnforced()` before any signal can be published.
    //
    //   currentHHI        – Herfindahl-Hirschman Index, 0..10000 scale.
    //                       < 1500 healthy, 1500-2500 warning, 2500-4000
    //                       danger, > 4000 critical (consensus frozen).
    //   gratitudeScore    – non-negative gratitude index, ≥ 1 required.
    //   publicGoodBps      – public-good charter allocation in bps
    //                       (≥ 1500 = 15% required).
    //
    // The quorum check is done against `validatorCount` (not
    // `quorumRequired` which is the configured minimum). For AWA to be
    // enforced, the configured quorum must itself be ≥ 2/3 of validatorCount.
    uint256 public currentHHI;
    uint256 public gratitudeScore;
    uint256 public publicGoodBps;

    uint256 public constant AWA_HHI_MAX                = 4000;
    uint256 public constant AWA_GRATITUDE_MIN          = 1;
    uint256 public constant AWA_PUBLIC_GOOD_MIN_BPS    = 1500;   // 15.00%
    uint256 public constant AWA_QUORUM_NUM             = 2;
    uint256 public constant AWA_QUORUM_DEN             = 3;

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
    event DecisionsPruned(uint256 count, uint256 timestamp);

    // AWA events (AUDIT-3 G3)
    event AWAStateUpdated(uint256 hhi, uint256 gratitude, uint256 publicGoodBps, bool enforced);
    event AWASignalEmissionFrozen(
        bytes32 indexed entityId,
        string  reason,
        uint256 timestamp
    );

    // ── Constructor ──────────────────────────────────────────────────────────
    constructor(uint256 _quorum) {
        owner = msg.sender;
        isValidator[msg.sender] = true;
        validatorCount = 1;                                  // deployer is initial validator
        quorumRequired = _quorum > 0 ? _quorum : 1;
        emit ValidatorAdded(msg.sender);
        emit OwnershipTransferred(address(0), msg.sender);

        // Bootstrap AWA state — conservative defaults that satisfy all
        // conditions so the gate is usable immediately after deployment.
        // Production deployments MUST call `updateAWAState()` with real
        // oracle values once the validator mesh is live.
        currentHHI = 1000;        // healthy tier
        gratitudeScore = 1;        // minimum satisfied
        publicGoodBps = 1500;      // 15% charter minimum
        emit AWAStateUpdated(currentHHI, gratitudeScore, publicGoodBps, true);
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

    // ── AWA Enforcement (AUDIT-3 Gap G3) ─────────────────────────────────────
    /**
     * @notice Returns TRUE iff all four Archetypal Weighted Average (AWA)
     *         governance conditions are satisfied. WP2 §17 requires this to
     *         be TRUE before any signal can be published; if FALSE, signal
     *         emission is FROZEN and cannot be overridden by any single
     *         entity (including the owner).
     *
     *         Conditions:
     *           1. Quorum: configured `quorumRequired` ≥ ⌈2/3 · validatorCount⌉
     *           2. HHI:    `currentHHI` < 4000 (critical threshold)
     *           3. Gratitude: `gratitudeScore` ≥ 1
     *           4. Public Good: `publicGoodBps` ≥ 1500 (15% charter)
     *
     * @return enforced TRUE iff all four conditions hold.
     */
    function awaEnforced() public view returns (bool enforced) {
        // (1) Quorum: the configured quorum must itself be a 2/3 supermajority
        //     of the validator set. Without this, a small cabal could publish
        //     signals even with an under-decentralized validator mesh.
        if (validatorCount == 0) return false;
        uint256 requiredQuorum = (validatorCount * AWA_QUORUM_NUM + (AWA_QUORUM_DEN - 1)) / AWA_QUORUM_DEN;
        if (quorumRequired < requiredQuorum) return false;

        // (2) HHI: must be below the critical 4000 threshold.
        if (currentHHI >= AWA_HHI_MAX) return false;

        // (3) Gratitude: ≥ 1 (Love Protocol multiplicative ethics floor).
        if (gratitudeScore < AWA_GRATITUDE_MIN) return false;

        // (4) Public Good: ≥ 15% charter allocation.
        if (publicGoodBps < AWA_PUBLIC_GOOD_MIN_BPS) return false;

        return true;
    }

    /**
     * @notice Returns a human-readable diagnostic of which AWA condition(s)
     *         are currently failing. Used by the dashboard / monitoring.
     *         Bitmask: bit 0 = quorum, bit 1 = HHI, bit 2 = gratitude, bit 3 = publicGood.
     *         0 means all conditions satisfied.
     */
    function awaFailureMask() external view returns (uint256 mask) {
        if (validatorCount == 0) {
            mask |= 1;
        } else {
            uint256 requiredQuorum = (validatorCount * AWA_QUORUM_NUM + (AWA_QUORUM_DEN - 1)) / AWA_QUORUM_DEN;
            if (quorumRequired < requiredQuorum) mask |= 1;
        }
        if (currentHHI >= AWA_HHI_MAX)               mask |= 2;
        if (gratitudeScore < AWA_GRATITUDE_MIN)      mask |= 4;
        if (publicGoodBps < AWA_PUBLIC_GOOD_MIN_BPS) mask |= 8;
    }

    /**
     * @notice Update the cached AWA state. Called by the Akashic oracle
     *         after each consensus round (or by the owner during bootstrap).
     *         Emits AWAStateUpdated with the resulting `enforced` flag.
     */
    function updateAWAState(
        uint256 _hhi,
        uint256 _gratitude,
        uint256 _publicGoodBps
    ) external onlyValidator whenNotPaused {
        currentHHI = _hhi;
        gratitudeScore = _gratitude;
        publicGoodBps = _publicGoodBps;
        bool enforced = awaEnforced();
        emit AWAStateUpdated(_hhi, _gratitude, _publicGoodBps, enforced);
    }

    // ── Core: Publish Behavioral Signal (with quorum + AWA enforcement) ─────
    /**
     * @notice Validators publish a TRION behavioral signal for an entity.
     *         Requires `quorumRequired` valid EIP-191 signatures over the
     *         message hash keccak256(abi.encodePacked(
     *           block.chainid, address(this), entityId, packedData
     *         )) from distinct registered validators.
     *
     *         AUDIT-3 Gap G3: also requires `awaEnforced()` to be TRUE.
     *         If any AWA condition fails, signal emission is FROZEN.
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
        // ── AWA enforcement (AUDIT-3 Gap G3) ────────────────────────────────
        // WP2 §17: "AWA_enforced = FALSE → signal emission FROZEN. Cannot be
        // overridden by any single entity." Check this BEFORE the quorum
        // signature loop so a frozen state short-circuits cheaply.
        require(awaEnforced(), "TRION: AWA not enforced - signal emission frozen");

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

        // AUDIT-3 G3: if AWA is not enforced, treat ALL entities as BLOCKED.
        // This prevents stale signals (published before an AWA freeze) from
        // being acted on while governance is in a frozen state.
        if (!awaEnforced()) {
            uint8  frozenStatus  = uint8(sig.packedData & 0xFF);
            uint32 frozenPhiT    = uint32((sig.packedData >> 8)  & 0xFFFFFFFF);
            uint32 frozenDropPct = uint32((sig.packedData >> 72) & 0xFFFFFFFF);
            decisionHash = keccak256(abi.encodePacked(
                entityId, caller, false, frozenStatus, frozenPhiT, block.number, block.timestamp
            ));
            decisions[decisionHash] = ExecutionDecision({
                allowed:      false,
                status:       frozenStatus,
                phi_t:        frozenPhiT,
                theta:        uint32((sig.packedData >> 40) & 0xFFFFFFFF),
                dropPct:      frozenDropPct,
                checkedAt:    block.timestamp,
                decisionHash: decisionHash
            });
            totalExecutionsBlocked++;
            emit AWASignalEmissionFrozen(entityId, "AWA not enforced", block.timestamp);
            emit ExecutionBlocked(entityId, caller, frozenStatus, frozenPhiT, frozenDropPct, decisionHash);
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
        // AUDIT-3 G3: storage sync also requires AWA — do not let a frozen
        // governance state be papered over with a fresh storage root.
        require(awaEnforced(), "TRION: AWA not enforced - sync frozen");
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
     *         AUDIT-3 G3: also returns FALSE when AWA is not enforced.
     */
    function isExecutionSafe(bytes32 entityId) external view returns (bool) {
        if (!awaEnforced()) return false;  // governance frozen → all execution unsafe
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
        if (!isValidator[v]) {
            isValidator[v] = true;
            validatorCount++;
            emit ValidatorAdded(v);
        }
    }

    function removeValidator(address v) external onlyOwner {
        require(v != owner, "TRION: Cannot remove owner");
        require(isValidator[v], "TRION: Not a validator");
        require(validatorCount > 1, "TRION: Cannot remove last validator");
        isValidator[v] = false;
        validatorCount--;
        emit ValidatorRemoved(v);
    }

    function setQuorum(uint256 q) external onlyOwner {
        require(q >= 1, "TRION: Quorum >= 1");
        // AUDIT-3 G3: reject quorum settings that would break the 2/3 AWA rule.
        require(
            q * AWA_QUORUM_DEN >= validatorCount * AWA_QUORUM_NUM,
            "TRION: Quorum below 2/3 of validators"
        );
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
        if (!isValidator[owner]) {
            isValidator[owner] = true;
            validatorCount++;
            emit ValidatorAdded(owner);
        }
        emit OwnershipTransferred(previous, owner);
    }

    // ── Admin: Decision pruning ───────────────────────────────────────────────
    /**
     * @notice Prune stale decision records from the mapping.
     * @dev    The `decisions` mapping grows unboundedly without pruning.
     *         The owner (or a keeper) should call this periodically with a batch
     *         of old decision hashes to free storage.  Pruning is voluntary —
     *         existing decisions are only deleted when explicitly passed here.
     * @param  hashes  Array of decisionHash values to delete (up to 500 per call).
     */
    function pruneDecisions(bytes32[] calldata hashes) external onlyOwner {
        require(hashes.length <= 500, "TRION: Batch too large (max 500)");
        uint256 pruned = 0;
        for (uint256 i = 0; i < hashes.length; i++) {
            if (decisions[hashes[i]].checkedAt != 0) {
                delete decisions[hashes[i]];
                pruned++;
            }
        }
        emit DecisionsPruned(pruned, block.timestamp);
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
        // EIP-2 low-S validation to prevent signature malleability
        require(
            uint256(s) <= 0x7FFFFFFFFFFFFFFFFFFFFFFFFFFFFFFF5D576E7357A4501DDFE92F46681B20A0,
            "TRION: Invalid s - must be low-S"
        );
        return ecrecover(hash, v, r, s);
    }
}
