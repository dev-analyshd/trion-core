// SPDX-License-Identifier: MIT
pragma solidity ^0.8.24;

import {IERC20} from "@openzeppelin/contracts/interfaces/IERC20.sol";
import {SafeERC20} from "@openzeppelin/contracts/token/ERC20/utils/SafeERC20.sol";
import {Ownable} from "@openzeppelin/contracts/access/Ownable.sol";
import {ITRIONSensingOracle} from "./ITRIONSensingOracle.sol";

/**
 * @title ConfidentialCoherenceVault
 * @notice ERC-20 vault gated by TRION behavioral coherence.
 *
 * Architecture:
 *   ERC-20 token  ──coherenceWrap()──▶  vault shares (locked)
 *   vault shares  ──coherenceUnwrap()──▶  ERC-20 token
 *
 * Coherence gate: TRION C(t) formula must return isCoherent(entityId) == true
 * before any wrap or unwrap is allowed.
 *
 * This unlocks behavioral trust-gated DeFi:
 *   - Capital enters only via behavioral coherence checks
 *   - TRION provides the coherence signal on-chain
 *
 * Author: Hudu Yusuf (Analys) | CC0
 */
contract ConfidentialCoherenceVault is Ownable {
    using SafeERC20 for IERC20;

    IERC20 public immutable underlying;
    ITRIONSensingOracle public trionOracle;

    mapping(address => uint256) public balanceOf;
    uint256 public totalDeposited;

    event CoherenceGatedWrap(bytes32 indexed entityId, address indexed user, uint256 amount);
    event CoherenceGatedUnwrap(bytes32 indexed entityId, address indexed user, uint256 amount);
    event OracleUpdated(address indexed newOracle);

    error CoherenceGateFailed(bytes32 entityId);
    error ZeroAddress();
    error InsufficientBalance();

    constructor(
        IERC20 underlying_,
        address trionOracle_,
        address initialOwner
    ) Ownable(initialOwner) {
        if (address(underlying_) == address(0) || trionOracle_ == address(0)) revert ZeroAddress();
        underlying = underlying_;
        trionOracle = ITRIONSensingOracle(trionOracle_);
    }

    // ─────────────────────────────────────────────────────────────────────
    // Coherence-gated wrap / unwrap
    // ─────────────────────────────────────────────────────────────────────

    /**
     * @notice Wrap ERC-20 tokens into the vault.
     * @dev TRION coherence gate: entity must be behaviorally coherent before wrapping.
     *      Raw behavioral data is never stored on-chain — only the coherence signal.
     * @param amount    Amount of underlying ERC-20 to wrap.
     * @param entityId  TRION entity identifier — must pass isCoherent() gate.
     */
    function coherenceWrap(uint256 amount, bytes32 entityId) external {
        if (!trionOracle.isCoherent(entityId)) revert CoherenceGateFailed(entityId);
        underlying.safeTransferFrom(msg.sender, address(this), amount);
        balanceOf[msg.sender] += amount;
        totalDeposited += amount;
        emit CoherenceGatedWrap(entityId, msg.sender, amount);
    }

    /**
     * @notice Unwrap vault tokens back to ERC-20.
     * @dev TRION coherence gate: entity must be behaviorally coherent.
     * @param amount    Amount to unwrap.
     * @param entityId  TRION entity identifier — must pass isCoherent() gate.
     */
    function coherenceUnwrap(uint256 amount, bytes32 entityId) external {
        if (!trionOracle.isCoherent(entityId)) revert CoherenceGateFailed(entityId);
        if (balanceOf[msg.sender] < amount) revert InsufficientBalance();
        balanceOf[msg.sender] -= amount;
        totalDeposited -= amount;
        underlying.safeTransfer(msg.sender, amount);
        emit CoherenceGatedUnwrap(entityId, msg.sender, amount);
    }

    // ─────────────────────────────────────────────────────────────────────
    // Admin
    // ─────────────────────────────────────────────────────────────────────

    /// @notice Update the TRION oracle address (owner only).
    function setOracle(address newOracle) external onlyOwner {
        if (newOracle == address(0)) revert ZeroAddress();
        trionOracle = ITRIONSensingOracle(newOracle);
        emit OracleUpdated(newOracle);
    }
}
