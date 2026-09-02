// SPDX-License-Identifier: MIT
pragma solidity ^0.8.24;

/// @title TRIONGuardV3 — Behavioral Pre-Execution Firewall Base
/// @notice Provides the `onlyWhenCoherent` modifier that derived contracts
///         (TRIONProtectedVault, future protected protocols) use to gate
///         state-changing functions on TRION behavioral coherence.
///
/// The guard reads from a deployed ITRIONOracleV3 contract. If the oracle
/// reports an unsafe status for the supplied txId, the call reverts with a
/// typed error before any state mutation occurs.
///
/// This contract is the V3 successor to TRIONFirewall.sol. It is intentionally
/// minimal — it contains no business logic beyond the gate itself, so the
/// consuming protocol can compose it freely.
interface ITRIONGuardOracle {
    function verifyExecution(bytes32 txId)
        external
        view
        returns (bool isSafe, uint32 coherence, uint32 threshold);
}

contract TRIONGuardV3 {
    /// @notice The MF (manipulation fingerprint) type codes used by protected
    ///         vaults to classify which attack vector a given gate is defending.
    uint8 public constant MF_TYPE_FLASH_LOAN         = 3;
    uint8 public constant MF_TYPE_SYBIL_LIQUIDITY    = 4;
    uint8 public constant MF_TYPE_GOVERNANCE_CAPTURE = 5;

    ITRIONGuardOracle public oracle;
    address public owner;
    bool public trionBypassActive;
    /// @notice SECURITY: bypass is TIME-LIMITED — auto-expires after this window.
    uint256 public constant BYPASS_MAX_WINDOW = 24 hours;
    /// @notice SECURITY FIX (P1): lifetime budget of bypass (re-)arms. The 24h
    ///         window + 1h cool-down alone let a persistent owner keep the
    ///         firewall OFF ~96% of the time (24h on, 1h wait, re-arm forever).
    ///         After BYPASS_MAX_RE_ARMS emergency windows the escape hatch is
    ///         permanently exhausted — fail-closed by design; resetting it
    ///         requires a governance-approved contract upgrade, not a call.
    uint256 public constant BYPASS_MAX_RE_ARMS = 3;
    uint256 public bypassExpiresAt;
    uint256 public lastBypassExpiry;
    /// @notice Number of bypass windows ever armed (max BYPASS_MAX_RE_ARMS).
    uint256 public bypassReArmsUsed;

    event OracleUpdated(address indexed previous, address indexed next);
    event TrionBypassToggled(bool active);
    event GateBlocked(bytes32 indexed txId, uint8 mfType, string reason);

    error CoherenceGateFailed(bytes32 txId);
    error Unauthorized();
    error BypassActive();
    /// @notice SECURITY FIX (P1): raised once the lifetime bypass budget
    ///         (BYPASS_MAX_RE_ARMS) is spent — the firewall can no longer be
    ///         disabled without a contract upgrade.
    error BypassBudgetExhausted(uint256 used, uint256 max);

    modifier onlyOwner() {
        if (msg.sender != owner) revert Unauthorized();
        _;
    }

    modifier onlyWhenCoherent(bytes32 txId) {
        // SECURITY: bypass auto-expires — no indefinite firewall-off state
        if (trionBypassActive && block.timestamp >= bypassExpiresAt) {
            trionBypassActive = false;
            lastBypassExpiry = bypassExpiresAt;
            emit TrionBypassToggled(false);
        }
        if (trionBypassActive) {
            // Emergency bypass — only governance can enable, and only for a
            // limited window. All bypass uses are logged on-chain.
            emit TrionBypassToggled(true);
        } else {
            (bool isSafe, uint32 coherence, ) = oracle.verifyExecution(txId);
            if (!isSafe) {
                emit GateBlocked(txId, 0, "Coherence gate failed");
                revert CoherenceGateFailed(txId);
            }
            // Coherence must be > 0 (silence enforces no-trade by reverting).
            if (coherence == 0) {
                emit GateBlocked(txId, 0, "Silence signal - no execution permitted");
                revert CoherenceGateFailed(txId);
            }
        }
        _;
    }

    constructor(address _oracle) {
        oracle = ITRIONGuardOracle(_oracle);
        owner = msg.sender;
    }

    /// @notice Set the TRION oracle address.
    function setOracle(address _oracle) external onlyOwner {
        emit OracleUpdated(address(oracle), _oracle);
        oracle = ITRIONGuardOracle(_oracle);
    }

    /// @notice Toggle the emergency bypass. Only callable by owner (governance).
    ///         Bypass is meant for catastrophic oracle failure only — every
    ///         bypass-enabled transaction emits an event for after-action review.
    /// @dev    SECURITY: enabling the bypass is bounded to a 24h maximum window
    ///         after which it auto-expires (enforced in onlyWhenCoherent), and
    ///         cannot be re-armed until a 1h cool-down after the previous
    ///         expiry has elapsed. SECURITY FIX (P1): re-arming is additionally
    ///         capped at BYPASS_MAX_RE_ARMS (3) uses for the contract's entire
    ///         lifetime — worst case 72h of firewall-off EVER, after which the
    ///         owner cannot keep the coherence firewall disabled at all
    ///         (previously ~96% off-time was achievable by daily re-arming).
    function _toggleTrionBypass(bool _status) internal {
        if (_status) {
            // SECURITY FIX (P1): lifetime budget — fail-closed once exhausted.
            if (bypassReArmsUsed >= BYPASS_MAX_RE_ARMS) {
                revert BypassBudgetExhausted(bypassReArmsUsed, BYPASS_MAX_RE_ARMS);
            }
            // Cool-down: 1h after the previous bypass window expired
            if (lastBypassExpiry != 0 && block.timestamp < lastBypassExpiry + 1 hours) {
                revert Unauthorized();
            }
            bypassReArmsUsed += 1;
            bypassExpiresAt = block.timestamp + BYPASS_MAX_WINDOW;
        } else {
            if (trionBypassActive) {
                lastBypassExpiry = block.timestamp;
            }
            bypassExpiresAt = 0;
        }
        trionBypassActive = _status;
        emit TrionBypassToggled(_status);
    }

    function toggleFirewall(bool _status) external onlyOwner {
        _toggleTrionBypass(_status);
    }
}
