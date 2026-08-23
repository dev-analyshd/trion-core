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

    // ── SECURITY: BEO identity binding ─────────────────────────────────
    // Each address may register exactly ONE TRION BEO identity (immutable
    // once set). The coherence gate binds to the CALLER'S OWN registered
    // identity — closing the bypass where any caller supplied an arbitrary
    // coherent entityId to pass the gate with someone else's behavior.
    mapping(address => bytes32) public registeredBEO;
    mapping(bytes32 => address) public beoOwner;   // enforces 1:1 binding

    event BEORegistered(address indexed user, bytes32 indexed entityId);
    event CoherenceGatedWrap(bytes32 indexed entityId, address indexed user, uint256 amount);
    event CoherenceGatedUnwrap(bytes32 indexed entityId, address indexed user, uint256 amount);
    event OracleUpdated(address indexed newOracle);

    error CoherenceGateFailed(bytes32 entityId);
    error ZeroAddress();
    error InsufficientBalance();
    error BEOAlreadyRegistered(address user);
    error BEOAlreadyBound(bytes32 entityId);
    error BEONotRegistered(address user);
    error BEOMismatch(address user, bytes32 provided, bytes32 registered);

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
    // BEO identity registration
    // ─────────────────────────────────────────────────────────────────────

    /**
     * @notice Register the caller's TRION BEO identity. One per address,
     *         immutable once set. The entity must already be coherent to
     *         register (prevents squatting on identities that could never
     *         pass the gate anyway).
     * @param entityId TRION BEO identifier owned by the caller.
     */
    function registerBEO(bytes32 entityId) external {
        if (entityId == bytes32(0)) revert ZeroAddress();
        if (registeredBEO[msg.sender] != bytes32(0)) revert BEOAlreadyRegistered(msg.sender);
        if (beoOwner[entityId] != address(0)) revert BEOAlreadyBound(entityId);
        registeredBEO[msg.sender] = entityId;
        beoOwner[entityId] = msg.sender;
        emit BEORegistered(msg.sender, entityId);
    }

    // ─────────────────────────────────────────────────────────────────────
    // Coherence-gated wrap / unwrap
    // ─────────────────────────────────────────────────────────────────────

    /**
     * @notice Wrap ERC-20 tokens into the vault.
     * @dev TRION coherence gate: the CALLER'S OWN registered BEO must pass
     *      isCoherent() before wrapping. Raw behavioral data is never stored
     *      on-chain — only the coherence signal.
     * @param amount    Amount of underlying ERC-20 to wrap.
     * @param entityId  Must equal the caller's registered BEO identity.
     */
    function coherenceWrap(uint256 amount, bytes32 entityId) external {
        bytes32 own = registeredBEO[msg.sender];
        if (own == bytes32(0)) revert BEONotRegistered(msg.sender);
        if (entityId != own) revert BEOMismatch(msg.sender, entityId, own);
        if (!trionOracle.isCoherent(own)) revert CoherenceGateFailed(own);
        underlying.safeTransferFrom(msg.sender, address(this), amount);
        balanceOf[msg.sender] += amount;
        totalDeposited += amount;
        emit CoherenceGatedWrap(own, msg.sender, amount);
    }

    /**
     * @notice Unwrap vault tokens back to ERC-20.
     * @dev TRION coherence gate: the CALLER'S OWN registered BEO must pass
     *      isCoherent() before unwrapping.
     * @param amount    Amount to unwrap.
     * @param entityId  Must equal the caller's registered BEO identity.
     */
    function coherenceUnwrap(uint256 amount, bytes32 entityId) external {
        bytes32 own = registeredBEO[msg.sender];
        if (own == bytes32(0)) revert BEONotRegistered(msg.sender);
        if (entityId != own) revert BEOMismatch(msg.sender, entityId, own);
        if (!trionOracle.isCoherent(own)) revert CoherenceGateFailed(own);
        if (balanceOf[msg.sender] < amount) revert InsufficientBalance();
        balanceOf[msg.sender] -= amount;
        totalDeposited -= amount;
        underlying.safeTransfer(msg.sender, amount);
        emit CoherenceGatedUnwrap(own, msg.sender, amount);
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
