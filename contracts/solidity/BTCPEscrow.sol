// SPDX-License-Identifier: MIT
pragma solidity ^0.8.24;

/// @title BTCPEscrow — Two-State Atomic Escrow for BTCP Cross-Chain Settlement
/// @notice Holds value in HOLDING state until TRION consensus verifies both
///         parties' behavioral coherence, then releases or reverts atomically.
/// @dev Implements whitepaper BTCP §4.3 (Six-Step Execution) and §11 (Five Final Fixes).
///      Release requires: status==HOLDING AND not expired AND coherence >= threshold.
///      Revert requires: status==HOLDING AND (expired OR relayer triggers failure).
///
///      ── Audit upgrades (Phase 1.1) per BTCP Master Implementation Spec ──
///      • States extended: IDLE | HOLDING | PENDING_AKASHIC | RELEASED | REVERTED | EMERGENCY_REVERTED
///      • revert_emergency() — anyone can call after 7 days (Gap 8 Resolution)
///      • cascade_revert() — multi-hop nested escrow support (Gap 9 Resolution)
///      • PENDING_AKASHIC state — 24h window for Akashic recovery (E1 Resolution)
///      • Force Majeure — funds held on SOURCE chain, not affected by target chain (Gap 11)
///      • Two-Phase Confirmation — SETTLEMENT_CHECK before release (G1 Resolution)
///
///      ── PHASE-1-SECURITY Hardening ──
///      • ReentrancyGuard on all value-transferring functions (releaseEscrow,
///        releaseFromPendingAkashic, revertEscrow, revertEmergency, _cascadeRevert).
///      • Pausable circuit breaker — owner can freeze new locks during emergencies
///        (existing escrows still settle/revert per their lifecycle).
///      • Zero-address checks on every address parameter and admin setter.
///      • All ETH transfers use `.call{value:}()` with explicit return-value check.
contract BTCPEscrow {
    // ── PHASE-1-SECURITY: Reentrancy guard (custom, no OZ dependency) ────────
    uint256 private constant _NOT_ENTERED = 1;
    uint256 private constant _ENTERED     = 2;
    uint256 private _reentrancyStatus = _NOT_ENTERED;

    modifier nonReentrant() {
        require(_reentrancyStatus != _ENTERED, "REENTRANT");
        _reentrancyStatus = _ENTERED;
        _;
        _reentrancyStatus = _NOT_ENTERED;
    }

    // ── PHASE-1-SECURITY: Pause circuit breaker ────────────────────────────
    // When `paused` is true, no NEW escrows can be locked. Existing escrows
    // continue to settle or revert per their normal lifecycle — pausing only
    // blocks value ingress, not egress (so funds are never frozen).
    bool public paused;

    // ── SECURITY: Aggregate locked balance ──────────────────────────────────
    // Sum of esc.amount over all escrows in HOLDING or PENDING_AKASHIC.
    // sweepETH() can only withdraw the EXCESS above this figure, so the owner
    // can never drain in-flight escrow funds ("no governance override").
    uint256 private _lockedBalance;

    /// @notice Total value currently locked in active (HOLDING/PENDING_AKASHIC) escrows.
    function totalLockedBalance() external view returns (uint256) {
        return _lockedBalance;
    }

    /// @notice Sweepable excess — ETH in the contract beyond active escrow value
    /// (e.g. force-sent via selfdestruct/coinbase). This is the ONLY portion
    /// sweepETH() may move.
    function sweepableExcess() external view returns (uint256) {
        return address(this).balance > _lockedBalance
            ? address(this).balance - _lockedBalance
            : 0;
    }

    // ── States (extended per spec Phase 1.1) ─────────────────────────────────
    enum State {
        IDLE,                // 0 — initial, no escrow
        HOLDING,             // 1 — locked, awaiting settlement
        PENDING_AKASHIC,     // 2 — Akashic unavailable, 24h recovery window
        RELEASED,            // 3 — successfully settled
        REVERTED,            // 4 — timed out or coherence failure
        EMERGENCY_REVERTED   // 5 — 7-day absolute escape hatch (Gap 8)
    }

    /// @notice Revert reasons (whitepaper BTCP §11)
    enum RevertReason {
        TIMEOUT,                 // 0
        COHERENCE_FAILURE,       // 1
        ROUTE_INVALID,           // 2
        MANUAL,                  // 3
        AKASHIC_OUTAGE_24H,      // 4 — E1 Resolution
        CASCADE_REVERT,          // 5 — Gap 9 multi-hop
        EMERGENCY_ESCAPE         // 6 — Gap 8
    }

    struct Escrow {
        bytes32 escrowId;          // unique escrow identifier
        bytes32 routeId;           // linked BTCP route
        bytes32 entityId;          // BEO identifier
        address payable destination;
        uint256 amount;            // native token amount locked
        uint256 minCoherence;      // ×1e6 — release threshold
        uint256 lockBlock;         // block at which escrow was locked
        uint256 lockTimestamp;     // timestamp at lock (for 7-day emergency)
        uint256 timeoutBlocks;     // max blocks before auto-revert
        State state;
        RevertReason revertReason;
        uint256 settledAt;
        uint256 revertedAt;
        address lockedBy;
        bytes32 parentEscrowId;    // for cascade revert (multi-hop) — 0 if no parent
        bytes32 settlementCheckHash; // G1: two-phase confirmation hash
    }

    // ── Constants (Phase 1.1 audit) ──────────────────────────────────────────
    uint256 public constant EMERGENCY_ESCAPE_SECONDS = 7 days;   // Gap 8: 7-day absolute max
    uint256 public constant AKASHIC_RECOVERY_SECONDS = 24 hours; // E1: 24h PENDING_AKASHIC window

    mapping(bytes32 => Escrow) public escrows;
    bytes32[] public escrowList;
    uint256 public escrowCount;

    address public owner;
    address public relayer;

    // ── Events (extended per spec) ───────────────────────────────────────────
    event EscrowLocked(bytes32 indexed escrowId, bytes32 indexed routeId, bytes32 indexed entityId, address destination, uint256 amount, uint256 minCoherence, uint256 timeoutBlocks);
    event EscrowReleased(bytes32 indexed escrowId, bytes32 indexed routeId, bytes32 executionBH, uint256 coherence, uint256 settledAt);
    event EscrowReverted(bytes32 indexed escrowId, RevertReason reason, uint256 revertedAt);
    event EmergencyRevert(bytes32 indexed escrowId, address indexed caller, uint256 revertedAt);
    event PendingAkashicEntered(bytes32 indexed escrowId, uint256 recoveryDeadline);
    event CascadeRevert(bytes32 indexed childEscrowId, bytes32 indexed parentEscrowId, uint256 revertedAt);
    event RelayerUpdated(address indexed oldRelayer, address indexed newRelayer);
    event SettlementCheckVerified(bytes32 indexed escrowId, bytes32 settlementCheckHash);

    // ── PHASE-1-SECURITY: Pause events ─────────────────────────────────────
    event Paused(address indexed by, uint256 at);
    event Unpaused(address indexed by, uint256 at);

    modifier onlyOwner() { require(msg.sender == owner, "NOT_OWNER"); _; }
    modifier onlyRelayer() { require(msg.sender == relayer || msg.sender == owner, "NOT_RELAYER"); _; }
    modifier whenNotPaused() { require(!paused, "PAUSED"); _; }

    constructor() {
        owner = msg.sender;
        relayer = msg.sender;
    }

    /// @notice Lock native tokens in escrow. Caller must send value with tx.
    /// @dev Called by the BTCP router after both parties confirm the PMO.
    /// @param parentEscrowId  0 if single-hop; non-zero for multi-hop nested escrow (Gap 9).
    function lockEscrow(
        bytes32 escrowId,
        bytes32 routeId,
        bytes32 entityId,
        address payable destination,
        uint256 minCoherence,
        uint256 timeoutBlocks,
        bytes32 parentEscrowId   // NEW: for cascade revert support
    ) external payable onlyRelayer whenNotPaused nonReentrant returns (bool) {
        // PHASE-1-SECURITY: zero-address & sanity checks
        require(msg.sender != address(0), "ZERO_SENDER");
        require(escrows[escrowId].escrowId == bytes32(0), "ESCROW_EXISTS");
        require(msg.value > 0, "ZERO_AMOUNT");
        require(destination != address(0), "ZERO_DESTINATION");
        require(minCoherence <= 1_000_000, "INVALID_COHERENCE");
        require(timeoutBlocks > 0, "ZERO_TIMEOUT");

        escrows[escrowId] = Escrow({
            escrowId:       escrowId,
            routeId:        routeId,
            entityId:       entityId,
            destination:    destination,
            amount:         msg.value,
            minCoherence:   minCoherence,
            lockBlock:      block.number,
            lockTimestamp:  block.timestamp,
            timeoutBlocks:  timeoutBlocks,
            state:          State.HOLDING,
            revertReason:   RevertReason.TIMEOUT,
            settledAt:      0,
            revertedAt:     0,
            lockedBy:       msg.sender,
            parentEscrowId: parentEscrowId,
            settlementCheckHash: bytes32(0)
        });

        escrowList.push(escrowId);
        escrowCount++;
        _lockedBalance += msg.value;  // SECURITY: track aggregate locked value
        emit EscrowLocked(escrowId, routeId, entityId, destination, msg.value, minCoherence, timeoutBlocks);
        return true;
    }

    /// @notice Backward-compatible lockEscrow without parent (single-hop).
    function lockEscrow(
        bytes32 escrowId,
        bytes32 routeId,
        bytes32 entityId,
        address payable destination,
        uint256 minCoherence,
        uint256 timeoutBlocks
    ) external payable onlyRelayer whenNotPaused nonReentrant returns (bool) {
        return _lockEscrowInternal(escrowId, routeId, entityId, destination, minCoherence, timeoutBlocks, bytes32(0));
    }

    function _lockEscrowInternal(
        bytes32 escrowId,
        bytes32 routeId,
        bytes32 entityId,
        address payable destination,
        uint256 minCoherence,
        uint256 timeoutBlocks,
        bytes32 parentEscrowId
    ) internal returns (bool) {
        require(msg.sender != address(0), "ZERO_SENDER");
        require(escrows[escrowId].escrowId == bytes32(0), "ESCROW_EXISTS");
        require(msg.value > 0, "ZERO_AMOUNT");
        require(destination != address(0), "ZERO_DESTINATION");
        require(minCoherence <= 1_000_000, "INVALID_COHERENCE");
        require(timeoutBlocks > 0, "ZERO_TIMEOUT");

        escrows[escrowId] = Escrow({
            escrowId:       escrowId,
            routeId:        routeId,
            entityId:       entityId,
            destination:    destination,
            amount:         msg.value,
            minCoherence:   minCoherence,
            lockBlock:      block.number,
            lockTimestamp:  block.timestamp,
            timeoutBlocks:  timeoutBlocks,
            state:          State.HOLDING,
            revertReason:   RevertReason.TIMEOUT,
            settledAt:      0,
            revertedAt:     0,
            lockedBy:       msg.sender,
            parentEscrowId: parentEscrowId,
            settlementCheckHash: bytes32(0)
        });

        escrowList.push(escrowId);
        escrowCount++;
        _lockedBalance += msg.value;  // SECURITY: track aggregate locked value
        emit EscrowLocked(escrowId, routeId, entityId, destination, msg.value, minCoherence, timeoutBlocks);
        return true;
    }

    /// @notice Two-Phase Confirmation (G1 Resolution) — verify settlement check
    ///         before release. The settlementCheckHash proves the execution
    ///         conditions were verified at the anchor block.
    function verifySettlementCheck(
        bytes32 escrowId,
        bytes32 settlementCheckHash
    ) external onlyRelayer whenNotPaused returns (bool) {
        Escrow storage esc = escrows[escrowId];
        require(esc.escrowId != bytes32(0), "ESCROW_NOT_FOUND");
        require(esc.state == State.HOLDING, "NOT_HOLDING");
        require(esc.settlementCheckHash == bytes32(0), "ALREADY_VERIFIED");

        esc.settlementCheckHash = settlementCheckHash;
        emit SettlementCheckVerified(escrowId, settlementCheckHash);
        return true;
    }

    /// @notice Release escrow to destination. Requires TRION consensus verification
    ///         AND settlement check verified (G1 Resolution).
    /// @param executionBH The execution behavioral hash linking anchor → execution.
    /// @param coherence   The coherence score (×1e6) at settlement time.
    function releaseEscrow(
        bytes32 escrowId,
        bytes32 executionBH,
        uint256 coherence
    ) external onlyRelayer nonReentrant returns (bool) {
        Escrow storage esc = escrows[escrowId];
        require(esc.escrowId != bytes32(0), "ESCROW_NOT_FOUND");
        require(esc.state == State.HOLDING, "NOT_HOLDING");
        require(block.number <= esc.lockBlock + esc.timeoutBlocks, "EXPIRED");
        require(coherence >= esc.minCoherence, "COHERENCE_INSUFFICIENT");
        // G1: Two-Phase Confirmation — settlement check must be verified
        require(esc.settlementCheckHash != bytes32(0), "SETTLEMENT_NOT_VERIFIED");

        // ── PHASE-1-SECURITY: state update BEFORE external call (CEI pattern) ──
        // Mark as RELEASED and clear the amount before transferring value,
        // so a malicious destination cannot re-enter releaseEscrow.
        uint256 amountToTransfer = esc.amount;
        address payable destinationToPay = esc.destination;
        esc.state = State.RELEASED;
        esc.settledAt = block.timestamp;
        esc.amount = 0;  // PHASE-1-SECURITY: clear balance before external call
        _lockedBalance -= amountToTransfer;  // SECURITY: value leaves the locked pool

        // Transfer native tokens to destination — .call{value:}() with return check.
        (bool ok, ) = destinationToPay.call{value: amountToTransfer}("");
        require(ok, "TRANSFER_FAILED");

        emit EscrowReleased(escrowId, esc.routeId, executionBH, coherence, esc.settledAt);
        return true;
    }

    /// @notice Enter PENDING_AKASHIC state when Akashic Index is unavailable
    ///         at execution time (E1 Resolution). 24h recovery window.
    function enterPendingAkashic(bytes32 escrowId) external onlyRelayer whenNotPaused {
        Escrow storage esc = escrows[escrowId];
        require(esc.escrowId != bytes32(0), "ESCROW_NOT_FOUND");
        require(esc.state == State.HOLDING, "NOT_HOLDING");

        esc.state = State.PENDING_AKASHIC;
        uint256 deadline = block.timestamp + AKASHIC_RECOVERY_SECONDS;
        emit PendingAkashicEntered(escrowId, deadline);
    }

    /// @notice Release from PENDING_AKASHIC after Akashic recovery (within 24h).
    function releaseFromPendingAkashic(
        bytes32 escrowId,
        bytes32 executionBH,
        uint256 coherence
    ) external onlyRelayer nonReentrant returns (bool) {
        Escrow storage esc = escrows[escrowId];
        require(esc.escrowId != bytes32(0), "ESCROW_NOT_FOUND");
        require(esc.state == State.PENDING_AKASHIC, "NOT_PENDING");
        require(block.timestamp <= esc.lockTimestamp + AKASHIC_RECOVERY_SECONDS, "AKASHIC_WINDOW_EXPIRED");
        require(coherence >= esc.minCoherence, "COHERENCE_INSUFFICIENT");
        require(esc.settlementCheckHash != bytes32(0), "SETTLEMENT_NOT_VERIFIED");

        // ── PHASE-1-SECURITY: CEI pattern — clear state BEFORE external call ──
        uint256 amountToTransfer = esc.amount;
        address payable destinationToPay = esc.destination;
        esc.state = State.RELEASED;
        esc.settledAt = block.timestamp;
        esc.amount = 0;
        _lockedBalance -= amountToTransfer;  // SECURITY: value leaves the locked pool

        (bool ok, ) = destinationToPay.call{value: amountToTransfer}("");
        require(ok, "TRANSFER_FAILED");

        emit EscrowReleased(escrowId, esc.routeId, executionBH, coherence, esc.settledAt);
        return true;
    }

    /// @notice Revert escrow back to the original locker.
    /// @dev Auto-reverts on timeout; relayer can trigger on coherence failure or route invalidity.
    ///      Also handles PENDING_AKASHIC → REVERTED after 24h (E1 Resolution).
    function revertEscrow(bytes32 escrowId, RevertReason reason) external nonReentrant returns (bool) {
        Escrow storage esc = escrows[escrowId];
        require(esc.escrowId != bytes32(0), "ESCROW_NOT_FOUND");
        require(esc.state == State.HOLDING || esc.state == State.PENDING_AKASHIC, "NOT_REVERTABLE");

        bool isTimeout = block.number > esc.lockBlock + esc.timeoutBlocks;
        bool isAkashicExpired = esc.state == State.PENDING_AKASHIC &&
                                block.timestamp > esc.lockTimestamp + AKASHIC_RECOVERY_SECONDS;

        if (isAkashicExpired) {
            reason = RevertReason.AKASHIC_OUTAGE_24H;
        } else if (!isTimeout) {
            require(msg.sender == relayer || msg.sender == owner, "NOT_RELAYER");
            require(reason != RevertReason.TIMEOUT, "NOT_TIMEOUT");
        }

        // ── PHASE-1-SECURITY: CEI pattern — clear state BEFORE external call ──
        uint256 amountToRefund = esc.amount;
        address payable refundTo = payable(esc.lockedBy);
        esc.state = State.REVERTED;
        esc.revertReason = reason;
        esc.revertedAt = block.timestamp;
        esc.amount = 0;
        _lockedBalance -= amountToRefund;  // SECURITY: value leaves the locked pool

        // Return funds to locker (Force Majeure — funds on source chain, Gap 11)
        (bool ok, ) = refundTo.call{value: amountToRefund}("");
        require(ok, "REFUND_FAILED");

        emit EscrowReverted(escrowId, reason, esc.revertedAt);

        // If this escrow has a parent (multi-hop), trigger cascade revert
        if (esc.parentEscrowId != bytes32(0)) {
            _cascadeRevert(esc.parentEscrowId, escrowId);
        }

        return true;
    }

    /// @notice Emergency Escape Hatch (Gap 8 Resolution).
    ///         After 7 days, ANY caller can trigger revert — no TRION signal needed.
    ///         This is the absolute maximum lockup period.
    function revertEmergency(bytes32 escrowId) external nonReentrant returns (bool) {
        Escrow storage esc = escrows[escrowId];
        require(esc.escrowId != bytes32(0), "ESCROW_NOT_FOUND");
        require(esc.state == State.HOLDING || esc.state == State.PENDING_AKASHIC, "NOT_HOLDING");
        require(
            block.timestamp >= esc.lockTimestamp + EMERGENCY_ESCAPE_SECONDS,
            "EMERGENCY_NOT_YET"
        );

        // ── PHASE-1-SECURITY: CEI pattern — clear state BEFORE external call ──
        uint256 amountToRefund = esc.amount;
        address payable refundTo = payable(esc.lockedBy);
        esc.state = State.EMERGENCY_REVERTED;
        esc.revertReason = RevertReason.EMERGENCY_ESCAPE;
        esc.revertedAt = block.timestamp;
        esc.amount = 0;
        _lockedBalance -= amountToRefund;  // SECURITY: value leaves the locked pool

        (bool ok, ) = refundTo.call{value: amountToRefund}("");
        require(ok, "REFUND_FAILED");

        emit EmergencyRevert(escrowId, msg.sender, esc.revertedAt);

        // Cascade to parent if multi-hop
        if (esc.parentEscrowId != bytes32(0)) {
            _cascadeRevert(esc.parentEscrowId, escrowId);
        }

        return true;
    }

    /// @notice Internal cascade revert for multi-hop nested escrows (Gap 9).
    ///         Called when a child escrow reverts — triggers revert on parent.
    function _cascadeRevert(bytes32 parentEscrowId, bytes32 childEscrowId) internal {
        Escrow storage parent = escrows[parentEscrowId];
        if (parent.escrowId == bytes32(0)) return;
        if (parent.state != State.HOLDING && parent.state != State.PENDING_AKASHIC) return;

        // ── PHASE-1-SECURITY: CEI pattern — clear state BEFORE external call ──
        uint256 amountToRefund = parent.amount;
        address payable refundTo = payable(parent.lockedBy);
        parent.state = State.REVERTED;
        parent.revertReason = RevertReason.CASCADE_REVERT;
        parent.revertedAt = block.timestamp;
        parent.amount = 0;
        _lockedBalance -= amountToRefund;  // SECURITY: value leaves the locked pool

        (bool ok, ) = refundTo.call{value: amountToRefund}("");
        require(ok, "CASCADE_REFUND_FAILED");

        emit CascadeRevert(childEscrowId, parentEscrowId, parent.revertedAt);
        emit EscrowReverted(parentEscrowId, RevertReason.CASCADE_REVERT, parent.revertedAt);

        // Recursively cascade to grandparent
        if (parent.parentEscrowId != bytes32(0)) {
            _cascadeRevert(parent.parentEscrowId, parentEscrowId);
        }
    }

    /// @notice Get escrow state.
    function getEscrow(bytes32 escrowId) external view returns (Escrow memory) {
        return escrows[escrowId];
    }

    /// @notice Check if escrow is expired (can be auto-reverted).
    function isExpired(bytes32 escrowId) external view returns (bool) {
        Escrow storage esc = escrows[escrowId];
        return esc.state == State.HOLDING && block.number > esc.lockBlock + esc.timeoutBlocks;
    }

    /// @notice Check if emergency escape is available (Gap 8).
    function emergencyEscapeAvailable(bytes32 escrowId) external view returns (bool) {
        Escrow storage esc = escrows[escrowId];
        return (esc.state == State.HOLDING || esc.state == State.PENDING_AKASHIC) &&
               block.timestamp >= esc.lockTimestamp + EMERGENCY_ESCAPE_SECONDS;
    }

    /// @notice Check if Akashic recovery window has expired (E1).
    function akashicWindowExpired(bytes32 escrowId) external view returns (bool) {
        Escrow storage esc = escrows[escrowId];
        return esc.state == State.PENDING_AKASHIC &&
               block.timestamp > esc.lockTimestamp + AKASHIC_RECOVERY_SECONDS;
    }

    function setRelayer(address newRelayer) external onlyOwner {
        // PHASE-1-SECURITY: prevent bricking the contract by setting relayer to address(0).
        require(newRelayer != address(0), "ZERO_RELAYER");
        emit RelayerUpdated(relayer, newRelayer);
        relayer = newRelayer;
    }

    // ── PHASE-1-SECURITY: Circuit breaker ──────────────────────────────────
    // Pause blocks NEW escrow locks only — existing escrows still settle or
    // revert per their normal lifecycle so no funds are frozen.
    function pause() external onlyOwner {
        require(!paused, "ALREADY_PAUSED");
        paused = true;
        emit Paused(msg.sender, block.timestamp);
    }

    function unpause() external onlyOwner {
        require(paused, "NOT_PAUSED");
        paused = false;
        emit Unpaused(msg.sender, block.timestamp);
    }

    // ── PHASE-1-SECURITY: Sweep stuck ETH (e.g. from failed refund) ────────
    // Owner-only escape hatch for ETH sent to the contract outside an escrow
    // (force-send via selfdestruct/coinbase). NEVER used for escrow funds.
    event ETHSwept(address indexed to, uint256 amount);

    function sweepETH(address payable to) external onlyOwner nonReentrant {
        require(to != address(0), "ZERO_DESTINATION");
        // SECURITY: never touch in-flight escrow funds — sweep only the excess
        // (force-sent ETH from selfdestruct/coinbase) above the aggregate
        // locked balance. Prevents owner from draining HOLDING escrows.
        uint256 excess = address(this).balance - _lockedBalance;
        require(excess > 0, "ZERO_SWEEPABLE_EXCESS");
        (bool ok, ) = to.call{value: excess}("");
        require(ok, "SWEEP_FAILED");
        emit ETHSwept(to, excess);
    }
}
