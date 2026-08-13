// SPDX-License-Identifier: MIT
pragma solidity ^0.8.24;

/// @title BTCPRoute — Route ID tracking with anchor BH → execution BH linkage
/// @notice Records the behavioral proof of a cross-chain BTCP route.
/// @dev Each route links an anchor behavioral hash (on source chain) to an
///      execution behavioral hash (on target chain) with consensus proof.
contract BTCPRoute {
    struct Route {
        bytes32 routeId;
        bytes32 intentHash;       // linked BTCPIntent
        bytes32 anchorBH;         // Hash_DNA of anchor event on chain A
        bytes32 executionBH;      // Hash_DNA of execution event on chain B
        uint64  anchorChain;      // source chain ID
        uint64  executionChain;   // target chain ID
        bytes32 entityId;         // BEO identifier
        uint256 gasSavedVsBridge; // estimated gas saved vs traditional bridge
        uint256 beoContinuity;    // ×1e6 — continuity score
        uint256 ccCoherence;      // ×1e6 — cross-chain coherence
        uint8   routeType;        // 0=SingleChain, 1=Split, 2=Netting, 3=Parallel, 4=MultiHop, 5=Deferred, 6=BITP
        bool    isVerified;
        uint256 createdAt;
        uint256 finalizedAt;
    }

    mapping(bytes32 => Route) public routes;
    bytes32[] public routeList;
    uint256 public routeCount;

    address public owner;
    address public relayer;

    event RoutePublished(bytes32 indexed routeId, bytes32 indexed intentHash, bytes32 anchorBH, uint64 anchorChain, uint64 executionChain, uint8 routeType);
    event RouteFinalized(bytes32 indexed routeId, bytes32 executionBH, uint256 gasSaved, uint256 beoContinuity, uint256 ccCoherence);
    event RelayerUpdated(address indexed oldRelayer, address indexed newRelayer);

    modifier onlyOwner() { require(msg.sender == owner, "NOT_OWNER"); _; }
    modifier onlyRelayer() { require(msg.sender == relayer || msg.sender == owner, "NOT_RELAYER"); _; }

    constructor() {
        owner = msg.sender;
        relayer = msg.sender;
    }

    /// @notice Publish a new BTCP route with anchor BH.
    function publishRoute(
        bytes32 routeId,
        bytes32 intentHash,
        bytes32 anchorBH,
        uint64  anchorChain,
        uint64  executionChain,
        bytes32 entityId,
        uint8   routeType
    ) external onlyRelayer returns (bool) {
        require(routes[routeId].routeId == bytes32(0), "ROUTE_EXISTS");
        require(anchorBH != bytes32(0), "ZERO_ANCHOR");
        require(routeType <= 6, "INVALID_TYPE");

        routes[routeId] = Route({
            routeId:            routeId,
            intentHash:         intentHash,
            anchorBH:           anchorBH,
            executionBH:        bytes32(0),
            anchorChain:        anchorChain,
            executionChain:     executionChain,
            entityId:           entityId,
            gasSavedVsBridge:   0,
            beoContinuity:      0,
            ccCoherence:        0,
            routeType:          routeType,
            isVerified:         false,
            createdAt:          block.timestamp,
            finalizedAt:        0
        });

        routeList.push(routeId);
        routeCount++;
        emit RoutePublished(routeId, intentHash, anchorBH, anchorChain, executionChain, routeType);
        return true;
    }

    /// @notice Finalize a route with execution BH and savings data.
    function finalizeRoute(
        bytes32 routeId,
        bytes32 executionBH,
        uint256 gasSavedVsBridge,
        uint256 beoContinuity,
        uint256 ccCoherence
    ) external onlyRelayer returns (bool) {
        Route storage route = routes[routeId];
        require(route.routeId != bytes32(0), "ROUTE_NOT_FOUND");
        require(!route.isVerified, "ALREADY_VERIFIED");
        require(executionBH != bytes32(0), "ZERO_EXEC_BH");
        require(beoContinuity <= 1_000_000 && ccCoherence <= 1_000_000, "INVALID_SCORE");

        route.executionBH = executionBH;
        route.gasSavedVsBridge = gasSavedVsBridge;
        route.beoContinuity = beoContinuity;
        route.ccCoherence = ccCoherence;
        route.isVerified = true;
        route.finalizedAt = block.timestamp;

        emit RouteFinalized(routeId, executionBH, gasSavedVsBridge, beoContinuity, ccCoherence);
        return true;
    }

    function getRoute(bytes32 routeId) external view returns (Route memory) {
        return routes[routeId];
    }

    function getRouteList() external view returns (bytes32[] memory) {
        return routeList;
    }

    function setRelayer(address newRelayer) external onlyOwner {
        emit RelayerUpdated(relayer, newRelayer);
        relayer = newRelayer;
    }
}
