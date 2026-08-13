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
    string  public constant VERSION  = "v1.0";
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

    // ── Modifiers ─────────────────────────────────────────────────

    modifier onlyDeployer() {
        require(msg.sender == DEPLOYER, "Not deployer");
        _;
    }

    constructor() {
        DEPLOYER       = msg.sender;
        DEPLOYED_AT    = block.timestamp;
        DEPLOYED_BLOCK = block.number;
    }

    // ── Write: called by sync daemon every hour ───────────────────

    /**
     * @notice Update storage commitment for one file.
     *         Called by sync daemon after each 0G Storage upload.
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
}
