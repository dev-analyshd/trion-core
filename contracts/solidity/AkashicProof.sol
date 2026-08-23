// SPDX-License-Identifier: MIT
pragma solidity ^0.8.24;

/**
 * @title AkashicProof — TRION x 0G
 * @notice Permanent onchain proof of behavioral truth.
 *         Updated every hour as new vectors are synced to 0G Storage.
 *         The living record of the world's first behavioral intelligence
 *         dataset on decentralized storage.
 *
 * @dev Deployed on 0G Chain (EVM, chainId 16600).
 *      Root hashes updated every sync cycle (~1hr).
 *      DA commitments recorded every minute.
 *      Cannot be deleted. Cannot be corrupted.
 *
 *      ─────────────────────────────────────────────────────────────────
 *      AUDIT-4 Gap 15 Fix — Decentralized Writes
 *      ─────────────────────────────────────────────────────────────────
 *      Previously all writes were gated by `onlyDeployer`, a centralized
 *      single point of trust/failure. This version introduces a quorum-
 *      based multi-sig path:
 *
 *        - The deployer bootstraps the validator set via `addValidator()`.
 *        - Once `validatorCount > 0`, the canonical Akashic merkle root
 *          MUST be published via `submitMerkleRoot(root, sigs)`, which
 *          requires >= ceil(2/3 * validatorCount) distinct validator
 *          EIP-191 signatures over keccak256(chainid || this || root || nonce).
 *        - The legacy `onlyDeployer` write functions (`updateCommitment`,
 *          `batchUpdateCommitments`, `recordSyncCycle`,
 *          `recordDACommitment`, `recordAkashicSnapshot`) are retained
 *          for bootstrap compatibility but are DEPRECATED — production
 *          callers should use `submitMerkleRoot` so every write is
 *          attested by a supermajority of independent validators.
 *      ─────────────────────────────────────────────────────────────────
 */
contract AkashicProof {

    // ── Core structs ─────────────────────────────────────────────

    struct StorageCommitment {
        bytes32 rootHash;
        bytes32 txHash;
        uint256 sizeBytes;
        uint64  vectorCount;
        uint64  recordCount;
        uint256 updatedAt;
        uint256 updateCount;
        string  storageUrl;
        string  label;
    }

    struct AkashicSnapshot {
        uint256 totalVectors;
        uint256 totalBHRecords;
        uint256 totalSignals;
        uint256 totalEntities;
        uint256 syncCycle;
        uint256 blockNumber;
        uint256 timestamp;
    }

    struct DACommitment {
        bytes32 dataHash;
        uint256 blobSize;
        uint256 blockNumber;
        uint256 epoch;
        uint256 quorumId;
        uint256 submittedAt;
        bool    verified;
    }

    struct SyncRecord {
        uint256 syncCycle;
        uint256 filesUploaded;
        uint256 vectorsAdded;
        uint256 recordsAdded;
        uint256 timestamp;
        bytes32 manifestHash;
    }

    // ── State ─────────────────────────────────────────────────────

    address public immutable DEPLOYER;
    uint256 public immutable DEPLOYED_AT;
    uint256 public immutable DEPLOYED_BLOCK;

    string  public constant PROTOCOL = "TRION";
    string  public constant VERSION  = "v1.1";   // bumped for Gap 15 fix
    string  public constant REPO     = "https://github.com/dev-analyshd/trion-core";

    mapping(string => StorageCommitment) public commitments;
    string[] public commitmentKeys;

    AkashicSnapshot[] public snapshots;
    AkashicSnapshot   public latestSnapshot;

    DACommitment[] public daCommitments;

    SyncRecord[] public syncHistory;

    uint256 public cumulativeVectors;
    uint256 public cumulativeBHRecords;
    uint256 public cumulativeSignals;
    uint256 public cumulativeSyncs;
    uint256 public cumulativeDABlobs;

    // ── Validator Quorum State (AUDIT-4 Gap 15) ───────────────────
    //
    // `validators`     – set of addresses authorized to sign merkle roots.
    // `validatorCount` – number of currently active validators.
    // `latestMerkleRoot` – the most recent root attested by >= 2/3 quorum.
    // `merkleRootUpdateCount` – monotonic nonce used to bind signatures to
    //                           a specific root submission (replay protection).
    mapping(address => bool) public validators;
    uint256 public validatorCount;
    bytes32 public latestMerkleRoot;
    uint256 public merkleRootUpdateCount;

    // Quorum numerator/denominator: 2/3 (66.67%). Required sigs =
    // ceil(validatorCount * QUORUM_NUM / QUORUM_DEN).
    uint256 public constant QUORUM_NUM = 2;
    uint256 public constant QUORUM_DEN = 3;

    // ── Events ────────────────────────────────────────────────────

    event StorageUpdated(
        string indexed key,
        bytes32 rootHash,
        uint256 indexed syncCycle,
        uint256 vectorCount
    );
    event SyncCompleted(
        uint256 indexed syncCycle,
        uint256 filesUploaded,
        uint256 vectorsAdded,
        uint256 timestamp
    );
    event DABlobSubmitted(
        bytes32 indexed dataHash,
        uint256 blobSize,
        uint256 indexed epoch
    );
    event AkashicMilestone(
        uint256 indexed totalVectors,
        uint256 indexed totalRecords,
        uint256 timestamp
    );

    event ValidatorAdded(address indexed validator);
    event ValidatorRemoved(address indexed validator);
    event MerkleRootSubmitted(
        bytes32 indexed root,
        uint256 sigCount,
        uint256 requiredSigs,
        uint256 indexed nonce,
        uint256 timestamp
    );

    // ── Modifiers ─────────────────────────────────────────────────

    modifier onlyDeployer() {
        require(msg.sender == DEPLOYER, "Not deployer");
        _;
    }

    /**
     * @notice Quorum modifier: requires that `sigs` contains >= ceil(2/3 * validatorCount)
     *         distinct EIP-191 validator signatures over `msgHash`.
     * @dev    Inline (not in a separate internal function) so the modifier
     *         captures all of the verification logic in one place. The
     *         modifier is invoked with the *message hash* the signers
     *         signed and the raw signature blob array.
     */
    modifier onlyValidatorQuorum(bytes32 msgHash, bytes[] memory sigs) {
        require(validatorCount > 0, "Akashic: no validators registered");
        uint256 required = _requiredQuorum();
        require(sigs.length >= required, "Akashic: insufficient sigs for 2/3 quorum");

        bytes32 ethSignedHash = keccak256(
            abi.encodePacked("\x19Ethereum Signed Message:\n32", msgHash)
        );

        address[] memory seen = new address[](sigs.length);
        uint256 validCount = 0;

        for (uint256 i = 0; i < sigs.length; i++) {
            address recovered = _recoverSigner(ethSignedHash, sigs[i]);
            if (recovered == address(0) || !validators[recovered]) continue;

            // Prevent duplicate signers
            bool duplicate = false;
            for (uint256 j = 0; j < validCount; j++) {
                if (seen[j] == recovered) { duplicate = true; break; }
            }
            if (duplicate) continue;

            seen[validCount] = recovered;
            validCount++;
            if (validCount >= required) break;
        }
        require(validCount >= required, "Akashic: quorum not met by distinct validators");
        _;
    }

    constructor() {
        DEPLOYER       = msg.sender;
        DEPLOYED_AT    = block.timestamp;
        DEPLOYED_BLOCK = block.number;
    }

    // ── Validator Management (bootstrap — only deployer) ─────────
    //
    // The deployer seeds the initial validator set. After bootstrap, the
    // deployer SHOULD rotate keys / add validators via on-chain governance
    // (out of scope here) and the deployer key SHOULD be retired.

    function addValidator(address v) external onlyDeployer {
        require(v != address(0), "Akashic: zero address");
        require(!validators[v], "Akashic: already validator");
        validators[v] = true;
        validatorCount++;
        emit ValidatorAdded(v);
    }

    function removeValidator(address v) external onlyDeployer {
        require(validators[v], "Akashic: not a validator");
        require(validatorCount > 1, "Akashic: cannot remove last validator");
        validators[v] = false;
        validatorCount--;
        emit ValidatorRemoved(v);
    }

    function isValidator(address v) external view returns (bool) {
        return validators[v];
    }

    /**
     * @notice Required number of validator signatures for a 2/3 quorum,
     *         computed as ceil(validatorCount * 2 / 3).
     */
    function requiredQuorum() external view returns (uint256) {
        return _requiredQuorum();
    }

    function _requiredQuorum() internal view returns (uint256) {
        // ceil(N * 2 / 3) = (N * 2 + 3 - 1) / 3 = (N * 2 + 2) / 3
        // Minimum of 1.
        if (validatorCount == 0) return 1;
        return (validatorCount * QUORUM_NUM + (QUORUM_DEN - 1)) / QUORUM_DEN;
    }

    // ── Decentralized Write: submitMerkleRoot (canonical path) ───
    //
    // Replaces the centralized `onlyDeployer` write path with a 2/3
    // validator quorum. The Akashic merkle root is the trustless ground
    // truth for BTCP route proofs (AUDIT-4 Gap 15).

    /**
     * @notice Submit a new Akashic merkle root attested by a 2/3 quorum
     *         of registered validators. Each signature MUST be an EIP-191
     *         signature over:
     *
     *           keccak256(abi.encodePacked(
     *               block.chainid, address(this), root, merkleRootUpdateCount
     *           ))
     *
     *         where `merkleRootUpdateCount` is the current (pre-update)
     *         nonce — i.e. the index of the root being submitted. This
     *         binds each signature to a specific submission slot and
     *         prevents replay attacks.
     *
     * @param root  The new Akashic merkle root.
     * @param sigs  Array of 65-byte EIP-191 signatures from distinct
     *              validators. Order does NOT matter (duplicates are
     *              de-duplicated). At least `requiredQuorum()` valid
     *              signatures are required.
     */
    function submitMerkleRoot(bytes32 root, bytes[] calldata sigs)
        external
        onlyValidatorQuorum(
            keccak256(abi.encodePacked(
                block.chainid, address(this), root, merkleRootUpdateCount
            )),
            sigs
        )
    {
        uint256 nonce = merkleRootUpdateCount;
        latestMerkleRoot = root;
        merkleRootUpdateCount = nonce + 1;

        // Mirror the root into the per-key commitment table so existing
        // readers (`commitments("akashic_root")`, getAllRootHashes) keep
        // working without code changes.
        string memory key = "akashic_root";
        bool isNew = bytes(commitments[key].label).length == 0;
        if (isNew) commitmentKeys.push(key);

        commitments[key] = StorageCommitment({
            rootHash:    root,
            txHash:      bytes32(0),
            sizeBytes:   0,
            vectorCount: 0,
            recordCount: 0,
            updatedAt:   block.timestamp,
            updateCount: isNew ? 1 : commitments[key].updateCount + 1,
            storageUrl:  "",
            label:       "akashic_root"
        });

        emit StorageUpdated(key, root, cumulativeSyncs, 0);
        emit MerkleRootSubmitted(root, sigs.length, _requiredQuorum(), nonce, block.timestamp);
    }

    // ── Legacy Writes (DEPRECATED — bootstrap only) ──────────────
    //
    // The functions below remain `onlyDeployer` for backward compatibility
    // with existing relayer / sync-daemon callers. New deployments SHOULD
    // use `submitMerkleRoot` for the canonical Akashic root and rely on
    // these only for non-critical metadata (file listings, sync cycle
    // bookkeeping). All state-changing writes that affect BTCP proofs
    // MUST go through the quorum path.

    /**
     * @notice Update storage commitment for one file.
     *         Called by sync daemon after each 0G Storage upload.
     * @dev DEPRECATED — Use submitMerkleRoot for Akashic root updates. Retained
     *             for backward compatibility with the file-level sync daemon.
     */
    function updateCommitment(
        string  calldata key,
        string  calldata label,
        bytes32 rootHash,
        bytes32 txHash,
        uint256 sizeBytes,
        uint64  vectorCount,
        uint64  recordCount,
        string  calldata storageUrl
    ) external onlyDeployer {
        bool isNew = bytes(commitments[key].label).length == 0;
        if (isNew) commitmentKeys.push(key);

        commitments[key] = StorageCommitment({
            rootHash:    rootHash,
            txHash:      txHash,
            sizeBytes:   sizeBytes,
            vectorCount: vectorCount,
            recordCount: recordCount,
            updatedAt:   block.timestamp,
            updateCount: isNew ? 1 : commitments[key].updateCount + 1,
            storageUrl:  storageUrl,
            label:       label
        });

        emit StorageUpdated(key, rootHash, cumulativeSyncs, vectorCount);
    }

    /**
     * @notice Batch update — gas efficient for multiple files per sync.
     * @dev DEPRECATED — Use submitMerkleRoot for Akashic root updates.
     */
    function batchUpdateCommitments(
        string[]  calldata keys,
        bytes32[] calldata rootHashes,
        bytes32[] calldata txHashes,
        uint256[] calldata sizes
    ) external onlyDeployer {
        require(keys.length == rootHashes.length, "Length mismatch");
        for (uint i = 0; i < keys.length; i++) {
            bool isNew = bytes(commitments[keys[i]].label).length == 0;
            if (isNew) commitmentKeys.push(keys[i]);
            commitments[keys[i]].rootHash    = rootHashes[i];
            commitments[keys[i]].txHash      = txHashes[i];
            commitments[keys[i]].sizeBytes   = sizes[i];
            commitments[keys[i]].updatedAt   = block.timestamp;
            commitments[keys[i]].updateCount =
                isNew ? 1 : commitments[keys[i]].updateCount + 1;
            emit StorageUpdated(keys[i], rootHashes[i], cumulativeSyncs, 0);
        }
    }

    /**
     * @notice Record completion of one hourly sync cycle.
     * @dev DEPRECATED — Use submitMerkleRoot for Akashic root updates.
     */
    function recordSyncCycle(
        uint256 filesUploaded,
        uint256 vectorsAdded,
        uint256 recordsAdded,
        bytes32 manifestHash
    ) external onlyDeployer {
        cumulativeSyncs++;
        cumulativeVectors   += vectorsAdded;
        cumulativeBHRecords += recordsAdded;

        syncHistory.push(SyncRecord({
            syncCycle:     cumulativeSyncs,
            filesUploaded: filesUploaded,
            vectorsAdded:  vectorsAdded,
            recordsAdded:  recordsAdded,
            timestamp:     block.timestamp,
            manifestHash:  manifestHash
        }));

        emit SyncCompleted(cumulativeSyncs, filesUploaded, vectorsAdded, block.timestamp);

        if (cumulativeVectors % 100_000 == 0 && cumulativeVectors > 0) {
            emit AkashicMilestone(cumulativeVectors, cumulativeBHRecords, block.timestamp);
        }
    }

    /**
     * @notice Record DA blob submission.
     * @dev DEPRECATED — Use submitMerkleRoot for Akashic root updates.
     */
    function recordDACommitment(
        bytes32 dataHash,
        uint256 blobSize,
        uint256 blockNumber,
        uint256 epoch,
        uint256 quorumId
    ) external onlyDeployer {
        cumulativeDABlobs++;
        daCommitments.push(DACommitment({
            dataHash:    dataHash,
            blobSize:    blobSize,
            blockNumber: blockNumber,
            epoch:       epoch,
            quorumId:    quorumId,
            submittedAt: block.timestamp,
            verified:    false
        }));
        emit DABlobSubmitted(dataHash, blobSize, epoch);
    }

    /**
     * @notice Record Akashic state snapshot (called every sync).
     * @dev DEPRECATED — Use submitMerkleRoot for Akashic root updates.
     */
    function recordAkashicSnapshot(
        uint256 totalVectors,
        uint256 totalBHRecords,
        uint256 totalSignals,
        uint256 totalEntities
    ) external onlyDeployer {
        AkashicSnapshot memory snap = AkashicSnapshot({
            totalVectors:   totalVectors,
            totalBHRecords: totalBHRecords,
            totalSignals:   totalSignals,
            totalEntities:  totalEntities,
            syncCycle:      cumulativeSyncs,
            blockNumber:    block.number,
            timestamp:      block.timestamp
        });
        snapshots.push(snap);
        latestSnapshot    = snap;
        cumulativeSignals = totalSignals;
    }

    // ── Read ──────────────────────────────────────────────────────

    function getAllRootHashes()
        external view
        returns (string[] memory keys, bytes32[] memory hashes)
    {
        keys   = commitmentKeys;
        hashes = new bytes32[](commitmentKeys.length);
        for (uint i = 0; i < commitmentKeys.length; i++) {
            hashes[i] = commitments[commitmentKeys[i]].rootHash;
        }
    }

    function getLatestSyncRecord()
        external view
        returns (SyncRecord memory)
    {
        require(syncHistory.length > 0, "No syncs yet");
        return syncHistory[syncHistory.length - 1];
    }

    function getLatestDACommitment()
        external view
        returns (DACommitment memory)
    {
        require(daCommitments.length > 0, "No DA commitments yet");
        return daCommitments[daCommitments.length - 1];
    }

    /**
     * @notice Complete proof summary — call this to verify TRION deployment.
     */
    function getFullProof() external view returns (
        string memory protocol,
        string memory version,
        uint256 deployedAt,
        uint256 totalFiles,
        uint256 totalVectors,
        uint256 totalBHRecords,
        uint256 totalSyncs,
        uint256 totalDABlobs,
        uint256 totalSignals,
        string  memory repo
    ) {
        return (
            PROTOCOL,
            VERSION,
            DEPLOYED_AT,
            commitmentKeys.length,
            cumulativeVectors,
            cumulativeBHRecords,
            cumulativeSyncs,
            cumulativeDABlobs,
            cumulativeSignals,
            REPO
        );
    }

    function getSyncCount()     external view returns (uint256) { return syncHistory.length; }
    function getDABlobCount()   external view returns (uint256) { return daCommitments.length; }
    function getSnapshotCount() external view returns (uint256) { return snapshots.length; }
    function getFileCount()     external view returns (uint256) { return commitmentKeys.length; }

    // ── Internal: ECDSA recovery ──────────────────────────────────
    // PHASE-1-SECURITY: explicit s-malleability guard (EIP-2) + zero-address
    // check on recovered signer. Prevents an attacker from reusing a single
    // validator attestation as two distinct 'votes' in the quorum loop.
    function _recoverSigner(bytes32 hash, bytes memory sig)
        internal pure returns (address)
    {
        require(sig.length == 65, "Akashic: invalid signature length");
        bytes32 r;
        bytes32 s;
        uint8   v;
        assembly {
            r := mload(add(sig, 32))
            s := mload(add(sig, 64))
            v := byte(0, mload(add(sig, 96)))
        }
        if (v < 27) v += 27;
        require(v == 27 || v == 28, "Akashic: invalid v");
        // EIP-2: s must be in the lower half of the secp256k1 curve order.
        require(
            uint256(s) <= 0x7FFFFFFFFFFFFFFFFFFFFFFFFFFFFFFF5D576E7357A4501DDFE92F46681B20A0,
            "Akashic: invalid s (malleable)"
        );
        address recovered = ecrecover(hash, v, r, s);
        require(recovered != address(0), "Akashic: invalid signature (zero recovered)");
        return recovered;
    }
}
