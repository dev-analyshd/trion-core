// SPDX-License-Identifier: MIT
pragma solidity ^0.8.24;

/// @title BTCPIntent — Behavioral Transaction Continuity Protocol Intent Registry
/// @notice Registers user intents (what they want, not how to execute).
/// @dev Full intent object stored off-chain in Akashic Index; on-chain stores
///      only the intent hash + minimal routing metadata.
contract BTCPIntent {
    /// @notice Intent action types (whitepaper BTCP §4.1)
    enum Action { SWAP, TRANSFER, LIQUIDITY, STAKE, BORROW }

    /// @notice Intent status lifecycle
    enum Status { PENDING, ROUTING, EXECUTING, COMPLETED, FAILED, EXPIRED, RESURRECTED }

    struct Intent {
        bytes32 intentHash;       // keccak256(abi.encode(full intent object))
        bytes32 entityId;         // BEO identifier (same across all chains)
        Action   action;
        bytes32  assetIn;         // universal asset identifier
        bytes32  assetOut;        // universal asset identifier
        uint256  magnitude;       // amount in behavioral magnitude units
        uint64   deadline;        // block number or timestamp
        uint128  maxTotalGas;     // USD equivalent across all chains
        uint8    minFinality;     // 0=FAST, 1=STANDARD, 2=SECURE
        uint16   minNLScore;      // liquidity health floor (×1000, default 300 = 0.30)
        bytes    chainPref;       // §4.1 constraints.chain_pref: OPTIMAL | [chain_list] | SINGLE_CHAIN
        uint8    privacy;         // 0=PUBLIC, 1=ZK_CREDENTIAL, 2=INVISIBLE
        bytes12  btcpVersion;     // §4.1 btcp_version: semver (bytes12) — §11 Fix 3 governance
        uint64   nonce;           // §4.1 nonce: per-entity monotonic counter
        bytes32  travelRuleProof; // §11 Fix 1: disclosure_hash (TRION stores hash only)
        Status   status;
        uint64   createdAt;
        address  submitter;
    }

    mapping(bytes32 => Intent) public intents;
    bytes32[] public intentList;
    uint256 public intentCount;

    address public owner;
    address public relayer;

    // §12.4 BEO-continuity indexing: every event carries entityId. §11 Fix 3:
    // btcp_version/nonce surface in IntentRegistered for Akashic indexing.
    event IntentRegistered(
        bytes32 indexed intentHash,
        bytes32 indexed entityId,
        Action   action,
        uint256  magnitude,
        uint64   deadline,
        bytes12  btcpVersion,
        uint64   nonce
    );
    event IntentStatusUpdated(bytes32 indexed intentHash, bytes32 indexed entityId, Status oldStatus, Status newStatus);
    event TravelRuleCompliant(bytes32 indexed intentHash, bytes32 indexed entityId, bytes32 travelRuleProofHash);
    event RelayerUpdated(address indexed oldRelayer, address indexed newRelayer);

    modifier onlyOwner() { require(msg.sender == owner, "NOT_OWNER"); _; }
    modifier onlyRelayer() { require(msg.sender == relayer || msg.sender == owner, "NOT_RELAYER"); _; }

    constructor() {
        owner = msg.sender;
        relayer = msg.sender;
    }

    /// @notice Register a new intent. Caller must be the entity owner or relayer.
    /// @dev Spec §4.1 Intent Object + §11 Fix 1 (Travel Rule) + §11 Fix 3 (BTCP version).
    function registerIntent(
        bytes32 intentHash,
        bytes32 entityId,
        Action  action,
        bytes32 assetIn,
        bytes32 assetOut,
        uint256 magnitude,
        uint64  deadline,
        uint128 maxTotalGas,
        uint8   minFinality,
        uint16  minNLScore,
        bytes   calldata chainPref,
        uint8   privacy,
        bytes12 btcpVersion,
        uint64  nonce,
        bytes32 travelRuleProof
    ) external onlyRelayer returns (bool) {
        require(intents[intentHash].intentHash == bytes32(0), "INTENT_EXISTS");
        require(magnitude > 0, "ZERO_MAGNITUDE");
        require(deadline > block.timestamp, "DEADLINE_PAST");
        require(uint8(action) <= 4, "INVALID_ACTION");
        require(minFinality <= 2, "INVALID_FINALITY");
        require(privacy <= 2, "INVALID_PRIVACY");
        require(nonce > 0, "ZERO_NONCE");              // §4.1 per-entity monotonic counter
        require(btcpVersion != bytes12(0), "ZERO_VERSION"); // §11 Fix 3 governance version required

        intents[intentHash] = Intent({
            intentHash:       intentHash,
            entityId:         entityId,
            action:           action,
            assetIn:          assetIn,
            assetOut:         assetOut,
            magnitude:        magnitude,
            deadline:         deadline,
            maxTotalGas:      maxTotalGas,
            minFinality:      minFinality,
            minNLScore:       minNLScore,
            chainPref:        chainPref,
            privacy:          privacy,
            btcpVersion:      btcpVersion,
            nonce:            nonce,
            travelRuleProof:  travelRuleProof,
            status:           Status.PENDING,
            createdAt:        uint64(block.timestamp),
            submitter:        msg.sender
        });

        intentList.push(intentHash);
        intentCount++;
        emit IntentRegistered(intentHash, entityId, action, magnitude, deadline, btcpVersion, nonce);
        if (travelRuleProof != bytes32(0)) {
            // §11 Fix 1 Step 4: TRION emits TRAVEL_RULE_COMPLIANT=TRUE when proof present.
            emit TravelRuleCompliant(intentHash, entityId, travelRuleProof);
        }
        return true;
    }

    /// @notice Update intent status (only relayer). Enforces valid transitions.
    function updateStatus(bytes32 intentHash, Status newStatus) external onlyRelayer returns (bool) {
        Intent storage intent = intents[intentHash];
        require(intent.intentHash != bytes32(0), "INTENT_NOT_FOUND");

        Status old = intent.status;
        require(_validTransition(old, newStatus), "INVALID_TRANSITION");
        intent.status = newStatus;
        emit IntentStatusUpdated(intentHash, intent.entityId, old, newStatus);
        return true;
    }

    /// @notice Get intent by hash.
    function getIntent(bytes32 intentHash) external view returns (Intent memory) {
        return intents[intentHash];
    }

    /// @notice Get all intent hashes (for off-chain enumeration).
    function getIntentList() external view returns (bytes32[] memory) {
        return intentList;
    }

    /// @notice Valid status transitions per whitepaper BTCP §4.1
    function _validTransition(Status from, Status to) internal pure returns (bool) {
        // PENDING → ROUTING, FAILED, EXPIRED
        if (from == Status.PENDING) {
            return to == Status.ROUTING || to == Status.FAILED || to == Status.EXPIRED;
        }
        // ROUTING → EXECUTING, FAILED, EXPIRED
        if (from == Status.ROUTING) {
            return to == Status.EXECUTING || to == Status.FAILED || to == Status.EXPIRED;
        }
        // EXECUTING → COMPLETED, FAILED
        if (from == Status.EXECUTING) {
            return to == Status.COMPLETED || to == Status.FAILED;
        }
        // FAILED → RESURRECTED
        if (from == Status.FAILED) {
            return to == Status.RESURRECTED;
        }
        // Terminal states
        return false;
    }

    function setRelayer(address newRelayer) external onlyOwner {
        // PHASE-1-SECURITY: zero-address check.
        require(newRelayer != address(0), "ZERO_RELAYER");
        emit RelayerUpdated(relayer, newRelayer);
        relayer = newRelayer;
    }
}
