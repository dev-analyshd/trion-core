// SPDX-License-Identifier: MIT
pragma solidity ^0.8.20;

/**
 * @title BTCSPVVerifier — Bitcoin SPV Light Client for Arbitrum
 * @notice Observation-Only Anchoring (OOA) — verifies Bitcoin block headers
 *         and transaction inclusion via Merkle proofs. NEVER holds ETH.
 *
 * Ported from contracts/starknet/src/btc_spv_verifier.cairo.
 */

contract BTCSPVVerifier {
    // ── Named Errors ────────────────────────────────────────────
    error NotOwner();
    error GenesisAlreadySet();
    error GenesisRenounced();
    error BlockAlreadyExists();
    error GenesisNotSet();
    error BadHeaderSize();
    error PoWFailed();
    error ChainLinkageBroken();
    error FutureTimestamp();
    error MtpPast();
    error BitsMismatchStrict();
    error TestnetMinDiffExpected();
    error BitsWalkbackFailed();
    error RetargetTooEasy();
    error RetargetTooHard();
    error BlockAboveTip();
    error DepthInsufficient();
    error UnknownBlock();
    error BadMerkleProof();
    error AnchorMismatch();
    error ZeroBlockHash();
    error ZeroMerkleRoot();

    address public owner;
    mapping(bytes32 => uint64) public blockHeight;
    mapping(bytes32 => bytes32) public blockMerkleRoot;
    mapping(bytes32 => uint64) public blockTime;
    mapping(bytes32 => bool) public blockExists;
    mapping(bytes32 => uint32) public blockBits;
    uint64 public blockCount;
    uint64 public verifiedAnchorCount;
    bytes32 public chainTip;
    uint64 public chainTipHeight;
    bool public chainTipSet;
    uint32 public boundaryBits;
    uint64 public boundaryHeight;
    uint64 public periodStartTime;
    uint32 public periodStartTarget;
    bool public mainnetStrict;
    bool public genesisAbilityRenounced;

    address constant SHA256_PRECOMPILE = address(0x02);

    event BlockHeaderSubmitted(bytes32 indexed blockHash, uint64 blockHeight, bytes32 merkleRoot, uint64 blockTime);
    event BlockHeaderVerified(bytes32 indexed blockHash, uint64 blockHeight, bytes32 prevBlockHash, bytes32 merkleRoot, uint32 bits, bool powValid);
    event GenesisTipSet(bytes32 indexed blockHash);
    event AnchorVerified(bytes32 indexed anchorBh, bytes32 indexed blockHash);

    constructor(address _owner, bool _mainnetStrict) {
        owner = _owner;
        mainnetStrict = _mainnetStrict;
    }

    modifier onlyOwner() { if (msg.sender != owner) revert NotOwner(); _; }

    function _sha256(bytes memory data) internal view returns (bytes32) {
        (bool ok, bytes memory result) = SHA256_PRECOMPILE.staticcall(data);
        require(ok && result.length == 32, "sha256 failed");
        return bytes32(result);
    }

    function _doubleSha256BE(bytes memory data) internal view returns (bytes32) {
        return _sha256(abi.encodePacked(_sha256(data)));
    }

    function _reverseBytes32(bytes32 v) internal pure returns (bytes32) {
        bytes memory b = abi.encodePacked(v);
        bytes memory r = new bytes(32);
        for (uint i = 0; i < 32; i++) r[i] = b[31 - i];
        return bytes32(r);
    }

    function _computeTarget(uint32 bits) internal pure returns (uint256) {
        uint32 exponent = bits >> 24;
        uint32 mantissa = bits & 0x007fffff;
        if (exponent <= 3) return uint256(mantissa) >> (8 * (3 - exponent));
        return uint256(mantissa) << (8 * (exponent - 3));
    }

    function _extractLE(bytes calldata header, uint offset) internal pure returns (bytes32) {
        bytes32 result;
        assembly { result := calldataload(add(header.offset, offset)) }
        return _reverseBytes32(result);
    }

    function _extractBits(bytes calldata header) internal pure returns (uint32) {
        bytes32 b = _extractLE(header, 72);
        return uint32(uint256(b));
    }

    function _extractTimestamp(bytes calldata header) internal pure returns (uint64) {
        bytes32 ts = _extractLE(header, 68);
        return uint64(uint32(uint256(ts)));
    }

    function _extractMerkleRoot(bytes calldata header) internal pure returns (bytes32) {
        return _extractLE(header, 36);
    }

    function _extractPrevBlockHash(bytes calldata header) internal pure returns (bytes32) {
        return _extractLE(header, 4);
    }

    function setGenesisTip(bytes32 blockHash, uint64 blockHeight_, uint32 bits, uint64 blockTime_) external onlyOwner {
        if (genesisAbilityRenounced) revert GenesisRenounced();
        if (chainTipSet) revert GenesisAlreadySet();
        if (blockHash == bytes32(0)) revert ZeroBlockHash();
        chainTip = blockHash;
        chainTipHeight = blockHeight_;
        chainTipSet = true;
        blockHeight[blockHash] = blockHeight_;
        blockTime[blockHash] = blockTime_;
        blockBits[blockHash] = bits;
        blockExists[blockHash] = true;
        blockCount = 1;
        boundaryBits = bits;
        boundaryHeight = blockHeight_;
        periodStartTime = blockTime_;
        periodStartTarget = bits;
        emit GenesisTipSet(blockHash);
    }

    function renounceGenesisAbility() external onlyOwner {
        if (genesisAbilityRenounced) revert GenesisRenounced();
        genesisAbilityRenounced = true;
    }

    function submitBlockHeader(bytes calldata header) external {
        if (header.length != 80) revert BadHeaderSize();
        if (!chainTipSet) revert GenesisNotSet();

        bytes32 hashBE = _doubleSha256BE(header);
        bytes32 hashLE = _reverseBytes32(hashBE);
        uint256 hashInt = uint256(hashLE);

        uint32 bits = _extractBits(header);
        uint256 target = _computeTarget(bits);
        if (hashInt >= target) revert PoWFailed();

        bytes32 blockHash = hashBE;
        bytes32 prevBlockHash = _extractPrevBlockHash(header);
        if (prevBlockHash != chainTip) revert ChainLinkageBroken();

        uint64 blockTime_ = _extractTimestamp(header);
        if (blockTime_ > block.timestamp + 7200) revert FutureTimestamp();
        uint64 prevTime = blockTime[chainTip];
        if (blockTime_ <= prevTime && (prevTime - blockTime_) > 7200) revert MtpPast();

        uint64 newHeight = chainTipHeight + 1;
        bool isBoundary = (newHeight % 2016 == 0);

        if (isBoundary) {
            uint256 oldTarget = _computeTarget(periodStartTarget);
            uint256 newTarget = _computeTarget(bits);
            if (newTarget >= oldTarget * 4 && newTarget != oldTarget) revert RetargetTooEasy();
            if (oldTarget >= newTarget * 4 && oldTarget != newTarget) revert RetargetTooHard();
            boundaryBits = bits;
            boundaryHeight = newHeight;
            periodStartTime = blockTime_;
            periodStartTarget = bits;
        } else {
            if (mainnetStrict) {
                if (bits != blockBits[chainTip]) revert BitsMismatchStrict();
            } else {
                if (blockTime_ > prevTime && (blockTime_ - prevTime) > 1200) {
                    if (bits != 0x1d00ffff) revert TestnetMinDiffExpected();
                } else {
                    if (blockBits[chainTip] != 0x1d00ffff) {
                        if (bits != blockBits[chainTip]) revert BitsWalkbackFailed();
                    }
                }
            }
        }

        if (blockExists[blockHash]) revert BlockAlreadyExists();
        bytes32 merkleRoot = _extractMerkleRoot(header);
        blockHeight[blockHash] = newHeight;
        blockMerkleRoot[blockHash] = merkleRoot;
        blockTime[blockHash] = blockTime_;
        blockBits[blockHash] = bits;
        blockExists[blockHash] = true;
        blockCount++;
        chainTip = blockHash;
        chainTipHeight = newHeight;
        emit BlockHeaderVerified(blockHash, newHeight, prevBlockHash, merkleRoot, bits, true);
    }

    function submitBlockHeaderTrusted(
        bytes32 blockHash, uint64 blockHeight_, bytes32 merkleRoot,
        uint64 blockTime_, uint32 bits
    ) external onlyOwner {
        if (blockHash == bytes32(0)) revert ZeroBlockHash();
        if (merkleRoot == bytes32(0)) revert ZeroMerkleRoot();
        if (blockExists[blockHash]) revert BlockAlreadyExists();
        blockHeight[blockHash] = blockHeight_;
        blockMerkleRoot[blockHash] = merkleRoot;
        blockTime[blockHash] = blockTime_;
        blockBits[blockHash] = bits;
        blockExists[blockHash] = true;
        blockCount++;
        if (!chainTipSet) {
            chainTip = blockHash;
            chainTipHeight = blockHeight_;
            chainTipSet = true;
            boundaryBits = bits;
            boundaryHeight = blockHeight_;
            periodStartTime = blockTime_;
            periodStartTarget = bits;
        } else if (blockHeight_ > chainTipHeight) {
            chainTip = blockHash;
            chainTipHeight = blockHeight_;
        }
        emit BlockHeaderSubmitted(blockHash, blockHeight_, merkleRoot, blockTime_);
    }

    function _verifyMerkleProof(bytes32 txid, uint32 txIndex, bytes32[] calldata merklePath) internal view returns (bytes32) {
        // Bitcoin merkle proof works in LE internal byte order.
        // Input txid and merklePath are in BE display order.
        // Convert to LE, hash, then convert result back to BE for comparison.
        bytes32 current = _reverseBytes32(txid);
        uint32 index = txIndex;
        for (uint i = 0; i < merklePath.length; i++) {
            bytes32 sibling = _reverseBytes32(merklePath[i]);
            bytes32 result;
            if (index % 2 == 0) {
                result = _doubleSha256Raw(abi.encodePacked(current, sibling));
            } else {
                result = _doubleSha256Raw(abi.encodePacked(sibling, current));
            }
            current = result;
            index /= 2;
        }
        // Convert final LE result back to BE display order
        return _reverseBytes32(current);
    }

    function _doubleSha256Raw(bytes memory data) internal view returns (bytes32) {
        // Returns raw hash (LE order) — NOT reversed
        bytes32 first = _sha256(data);
        return _sha256(abi.encodePacked(first));
    }

    function _computeAnchorBh(
        bytes32 entityId, uint8 eventType, uint64 magnitudeNano,
        uint64 blockTime_, uint32 chainId, bytes32 blockHash
    ) internal view returns (bytes32) {
        bytes memory payload = abi.encodePacked(
            entityId, eventType, magnitudeNano,
            uint64(0), blockTime_, chainId, blockHash
        );
        bytes memory senseInput = abi.encodePacked(payload, bytes1(0x00));
        return _sha256(senseInput);
    }

    function verifyAnchor(
        bytes32 anchorBh, bytes32 blockHash, bytes32 txid, uint32 txIndex,
        bytes32[] calldata merklePath, bytes32 entityId, uint8 eventType,
        uint64 magnitudeNano, uint64 blockTime_, uint32 chainId, uint64 valueUsd
    ) external returns (bool) {
        if (!blockExists[blockHash]) revert UnknownBlock();
        uint64 bHeight = blockHeight[blockHash];
        if (chainTipHeight < bHeight) revert BlockAboveTip();
        uint64 depth = chainTipHeight - bHeight;
        uint64 requiredDepth = valueUsd < 100_000 ? 6 : valueUsd < 1_000_000 ? 12 : 24;
        if (depth < requiredDepth) revert DepthInsufficient();

        bytes32 storedRoot = blockMerkleRoot[blockHash];
        bytes32 recomputedRoot = _verifyMerkleProof(txid, txIndex, merklePath);
        if (recomputedRoot != storedRoot) revert BadMerkleProof();

        bytes32 recomputedAnchor = _computeAnchorBh(entityId, eventType, magnitudeNano, blockTime_, chainId, blockHash);
        if (recomputedAnchor != anchorBh) revert AnchorMismatch();

        emit AnchorVerified(anchorBh, blockHash);
        return true;
    }

    function getBlockHeader(bytes32 blockHash) external view returns (uint64, bytes32, uint64, bool, uint32) {
        return (blockHeight[blockHash], blockMerkleRoot[blockHash], blockTime[blockHash], blockExists[blockHash], blockBits[blockHash]);
    }

    function getChainTip() external view returns (bytes32, uint64, bool) {
        return (chainTip, chainTipHeight, chainTipSet);
    }
}
