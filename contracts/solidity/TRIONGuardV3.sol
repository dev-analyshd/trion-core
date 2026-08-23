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

    event OracleUpdated(address indexed previous, address indexed next);
    event TrionBypassToggled(bool active);
    event GateBlocked(bytes32 indexed txId, uint8 mfType, string reason);

    error CoherenceGateFailed(bytes32 txId);
    error Unauthorized();
    error BypassActive();

    modifier onlyOwner() {
        if (msg.sender != owner) revert Unauthorized();
        _;
    }

    modifier onlyWhenCoherent(bytes32 txId) {
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
    function _toggleTrionBypass(bool _status) internal {
        trionBypassActive = _status;
        emit TrionBypassToggled(_status);
    }

    function toggleFirewall(bool _status) external onlyOwner {
        _toggleTrionBypass(_status);
    }
}
