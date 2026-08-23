// SPDX-License-Identifier: MIT
pragma solidity ^0.8.24;

/// @title BehavioralLimitOrder — Persistent behavioral order book for BTCP
/// @notice Implements whitepaper BTCP §5.5 (Water Finding Cracks in Time).
///         An intent that doesn't find an immediate complement becomes a BLO
///         and waits for a counterparty to fill it.
contract BehavioralLimitOrder {
    enum Status { OPEN, PARTIALLY_FILLED, FILLED, EXPIRED }

    struct BLO {
        bytes32 commitmentHash;   // Hash_DNA(entity || intent || expiry || behavioral_proof)
        bytes32 entityId;         // BEO identifier
        bytes32 intentHash;       // linked BTCPIntent
        bytes32 assetIn;          // asset being offered
        bytes32 assetOut;         // asset being requested
        uint256 magnitude;        // total order size
        uint256 filledAmount;     // cumulative filled amount
        uint256 expiryBlock;      // auto-expiry
        uint16  btcpScore;        // ×100 — behavioral quality of poster
        Status  status;
        uint256 createdAt;
        address poster;
    }

    mapping(bytes32 => BLO) public orders;
    bytes32[] public openOrders;
    uint256 public orderCount;

    // Index by asset pair for efficient complement lookup
    mapping(bytes32 => bytes32[]) public ordersByPair; // pairHash => orderHashes

    address public owner;
    address public relayer;

    event BLOPosted(bytes32 indexed commitmentHash, bytes32 indexed entityId, bytes32 assetIn, bytes32 assetOut, uint256 magnitude, uint256 expiryBlock);
    event BLOFilled(bytes32 indexed commitmentHash, bytes32 indexed fillerEntityId, uint256 fillAmount, uint256 remainingAmount);
    event BLOExpired(bytes32 indexed commitmentHash, uint256 expiredAt);
    event RelayerUpdated(address indexed oldRelayer, address indexed newRelayer);

    modifier onlyOwner() { require(msg.sender == owner, "NOT_OWNER"); _; }
    modifier onlyRelayer() { require(msg.sender == relayer || msg.sender == owner, "NOT_RELAYER"); _; }

    constructor() {
        owner = msg.sender;
        relayer = msg.sender;
    }

    /// @notice Post a new behavioral limit order.
    function postOrder(
        bytes32 commitmentHash,
        bytes32 entityId,
        bytes32 intentHash,
        bytes32 assetIn,
        bytes32 assetOut,
        uint256 magnitude,
        uint256 expiryBlock,
        uint16  btcpScore
    ) external onlyRelayer returns (bool) {
        require(orders[commitmentHash].commitmentHash == bytes32(0), "BLO_EXISTS");
        require(magnitude > 0, "ZERO_MAGNITUDE");
        require(expiryBlock > block.number, "EXPIRY_PAST");
        require(btcpScore <= 10000, "INVALID_SCORE");

        orders[commitmentHash] = BLO({
            commitmentHash: commitmentHash,
            entityId:       entityId,
            intentHash:     intentHash,
            assetIn:        assetIn,
            assetOut:       assetOut,
            magnitude:      magnitude,
            filledAmount:   0,
            expiryBlock:    expiryBlock,
            btcpScore:      btcpScore,
            status:         Status.OPEN,
            createdAt:      block.timestamp,
            poster:         msg.sender
        });

        openOrders.push(commitmentHash);
        orderCount++;

        // Index by asset pair
        bytes32 pairHash = _pairHash(assetIn, assetOut);
        ordersByPair[pairHash].push(commitmentHash);

        emit BLOPosted(commitmentHash, entityId, assetIn, assetOut, magnitude, expiryBlock);
        return true;
    }

    /// @notice Fill (partially or fully) an existing BLO.
    /// @dev Complement must have opposite asset_in/asset_out direction.
    function fillOrder(
        bytes32 commitmentHash,
        bytes32 fillerEntityId,
        uint256 fillAmount
    ) external onlyRelayer returns (bool) {
        BLO storage order = orders[commitmentHash];
        require(order.commitmentHash != bytes32(0), "BLO_NOT_FOUND");
        require(order.status == Status.OPEN || order.status == Status.PARTIALLY_FILLED, "NOT_FILLABLE");
        require(block.number <= order.expiryBlock, "EXPIRED");
        require(fillAmount > 0, "ZERO_FILL");
        require(order.filledAmount + fillAmount <= order.magnitude, "OVERFILL");

        order.filledAmount += fillAmount;
        if (order.filledAmount == order.magnitude) {
            order.status = Status.FILLED;
        } else {
            order.status = Status.PARTIALLY_FILLED;
        }

        emit BLOFilled(commitmentHash, fillerEntityId, fillAmount, order.magnitude - order.filledAmount);
        return true;
    }

    /// @notice Expire an unfilled or partially filled order.
    function expireOrder(bytes32 commitmentHash) external onlyRelayer returns (bool) {
        BLO storage order = orders[commitmentHash];
        require(order.commitmentHash != bytes32(0), "BLO_NOT_FOUND");
        require(order.status == Status.OPEN || order.status == Status.PARTIALLY_FILLED, "NOT_EXPIRABLE");
        require(block.number > order.expiryBlock, "NOT_YET_EXPIRED");

        order.status = Status.EXPIRED;
        emit BLOExpired(commitmentHash, block.timestamp);
        return true;
    }

    /// @notice Find complement orders for a given asset pair.
    /// @dev Returns up to `limit` open orders for the opposite direction.
    function findComplements(
        bytes32 assetIn,
        bytes32 assetOut,
        uint256 limit
    ) external view returns (bytes32[] memory) {
        bytes32 pairHash = _pairHash(assetOut, assetIn); // reversed — complement direction
        bytes32[] storage candidates = ordersByPair[pairHash];
        uint256 count = 0;
        for (uint256 i = 0; i < candidates.length && count < limit; i++) {
            BLO storage o = orders[candidates[i]];
            if ((o.status == Status.OPEN || o.status == Status.PARTIALLY_FILLED) && block.number <= o.expiryBlock) {
                count++;
            }
        }
        bytes32[] memory result = new bytes32[](count);
        uint256 idx = 0;
        for (uint256 i = 0; i < candidates.length && idx < count; i++) {
            BLO storage o = orders[candidates[i]];
            if ((o.status == Status.OPEN || o.status == Status.PARTIALLY_FILLED) && block.number <= o.expiryBlock) {
                result[idx++] = candidates[i];
            }
        }
        return result;
    }

    function getOrder(bytes32 commitmentHash) external view returns (BLO memory) {
        return orders[commitmentHash];
    }

    function _pairHash(bytes32 a, bytes32 b) internal pure returns (bytes32) {
        return keccak256(abi.encodePacked(a, b));
    }

    function setRelayer(address newRelayer) external onlyOwner {
        require(newRelayer != address(0), "BLO: zero relayer");
        emit RelayerUpdated(relayer, newRelayer);
        relayer = newRelayer;
    }
}
