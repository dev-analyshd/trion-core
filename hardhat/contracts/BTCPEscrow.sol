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
///      • ORACLE-GATED RELEASE — bind a TRION oracle (one-way) and releases
///        additionally require its quorum+freshness route verdict, bound to
///        the escrow via the route's anchorBH (route-spoof prevention).
///      • SIGNATURE-QUORUM CONSENSUS (S3/C2 fix) — when the oracle is bound,
///        the verdict itself must have been finalized by ≥ max(2,
///        ⌈2/3 · validatorCount⌉) DISTINCT registered validators whose ECDSA
///        attestations the oracle recovered on-chain (TRIONOracleV3.
///        submitRouteAttestation). The relayer's caller-supplied coherence
///        can never release funds in that mode.
interface ITRIONOracleEscrowView {
    /// @notice verifyExecution — legacy route/signal safety verdict.
    function verifyExecution(bytes32 txId)
        external
        view
        returns (bool isSafe, uint32 coherence, uint32 threshold);

    /// @notice routeBinding — flat verdict view with binding + quorum fields.
    function routeBinding(bytes32 routeId)
        external
        view
        returns (
            bytes32 anchorBH,
            uint256 attestationCount,
            bool isSafe,
            uint256 coherence,
            uint256 threshold,
            uint256 timestamp
        );

    /// @notice Dynamic route-verdict quorum the bound oracle enforces:
    ///         max(2, ⌈2/3 · validatorCount⌉) distinct signature-verified
    ///         validators. The escrow treats this as a hard floor on the
    ///         attestationCount reported by routeBinding().
    function minRouteAttestations() external view returns (uint256);
}

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

    // ── ORACLE-GATED RELEASE (whitepaper: "TRION consensus is the only
    // oracle") ─────────────────────────────────────────────────────────────
    // When set, releaseEscrow()/releaseFromPendingAkashic() additionally
    // require the TRION oracle's route verdict for THIS escrow to have been
    // FINALIZED BY SIGNATURE QUORUM: the oracle only counts attestations it
    // recovered itself from EIP-191 ECDSA signatures of DISTINCT registered
    // validators (TRIONOracleV3.submitRouteAttestation), and this gate
    // additionally demands attestationCount ≥ the oracle's dynamic quorum
    // max(2, ⌈2/3 · validatorCount⌉). The relayer's caller-supplied
    // coherence alone can then never release funds.
    //
    // TRUSTED-RELAYER MODE (oracle == address(0)) is the bootstrap/local-dev
    // mode: releases take the relayer's word for coherence. It is an
    // EXPLICIT OPT-OUT by the deployer — production deployments MUST call
    // setTRIONOracle() (the evm-tools deploy scripts bind the oracle
    // atomically at deploy time; TRUSTED_RELAYER_MODE=1 skips it for local
    // dev only). Binding is a ONE-WAY upgrade (immutable once set) — the
    // contract fails toward verification, never back toward trust.
    address public trionOracle;
    event TRIONOracleBound(address indexed oracle, uint64 at);

    /// @notice Bind the TRION oracle for consensus-gated releases. One-way:
    /// once set it cannot be changed or cleared — fails toward verification.
    /// Production deploy flows (evm-tools/deploy-evm.mjs & friends) call this
    /// by default; leaving it unset is the documented dev-only
    /// trusted-relayer opt-out.
    function setTRIONOracle(address oracle) external onlyOwner {
        require(oracle != address(0), "ZERO_ORACLE");
        require(trionOracle == address(0), "ORACLE_ALREADY_BOUND");
        trionOracle = oracle;
        emit TRIONOracleBound(oracle, uint64(block.timestamp));
    }

    /// @dev Internal consensus gate (H1 fix: verdict is BOUND to this escrow;
    ///      S3/C2 fix: verdict is finalized by SIGNATURE QUORUM).
    ///      Loads the route verdict via the oracle's routeBinding() view and
    ///      requires: anchorBH == escrowId (the binding — a quorum-safe
    ///      verdict for an UNRELATED route can never release this escrow),
    ///      isSafe, attestationCount ≥ max(2, oracle's dynamic quorum
    ///      max(2, ⌈2/3 · validatorCount⌉)), freshness ≤ 300s, and both
    ///      coherence ≥ minCoherence and ≥ oracle threshold. Because the
    ///      oracle only records attestations recovered from validator ECDSA
    ///      signatures, the quorum requirement here is a SIGNATURE quorum —
    ///      the relayer identity and the caller-supplied coherence value are
    ///      irrelevant to the gate. Reverts when the bound oracle fails any
    ///      check. No-op in trusted-relayer mode (oracle unbound) — that
    ///      mode remains documented above and is dev-only.
    function _consensusGate(
        bytes32 escrowId,
        bytes32 routeId,
        uint256 minCoherence
    ) internal view {
        if (trionOracle == address(0)) {
            return; // trusted-relayer mode (documented dev-only opt-out)
        }
        (
            bytes32 anchorBH,
            uint256 attestationCount,
            bool isSafe,
            uint256 oracleCoherence,
            uint256 oracleThreshold,
            uint256 ts
        ) = ITRIONOracleEscrowView(trionOracle).routeBinding(routeId);
        // H1: the verdict must be bound to THIS escrow — anchorBH carries the
        // escrowId the route was attested for. Route substitution (pointing
        // the escrow at an unrelated fresh quorum-safe route) fails here.
        require(anchorBH == escrowId, "ORACLE_ROUTE_NOT_BOUND_TO_ESCROW");
        require(isSafe, "ORACLE_CONSENSUS_UNSAFE");
        // S3/C2 STRENGTHENING: the verdict must be FINALIZED BY SIGNATURE
        // QUORUM. The oracle's attestationCount only grows via ECDSA-
        // verified attestations from DISTINCT registered validators; the
        // required quorum is the oracle's dynamic max(2, ⌈2/3 · validatorCount⌉)
        // — never below the hard floor of 2, so one relayer key (or two keys
        // controlled by it without validator signatures) cannot release.
        uint256 requiredQuorum = 2; // hard floor — see require below
        try ITRIONOracleEscrowView(trionOracle).minRouteAttestations() returns (
            uint256 dynamicQuorum
        ) {
            if (dynamicQuorum > requiredQuorum) {
                requiredQuorum = dynamicQuorum;
            }
        } catch {
            // Legacy/mock oracles without the dynamic route-quorum view:
            // fall back to the hard floor of 2. The bound oracle is already
            // the fully trusted verdict source (one-way, owner-gated
            // binding), so this fallback introduces no additional trust
            // assumption — only TRIONOracleV3 with its live validator set
            // enforces the ⌈2/3⌉ supermajority.
        }
        require(attestationCount >= requiredQuorum, "ORACLE_QUORUM_UNMET");
        require(block.timestamp - ts <= 300, "ORACLE_VERDICT_STALE");
        require(oracleCoherence >= minCoherence, "ORACLE_COHERENCE_INSUFFICIENT");
        require(oracleCoherence >= oracleThreshold, "ORACLE_BELOW_THRESHOLD");
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
    /// ═══════════════════════════════════════════════════════════════════════════
    /// SECURITY MODEL — TRUST ASSUMPTIONS (per DD report §7.2, S3/C2 resolved)
    /// ═══════════════════════════════════════════════════════════════════════════
    ///
    /// PRODUCTION (oracle bound — the default in the deploy scripts): the
    /// release is gated by _consensusGate(), which requires a route verdict
    /// that the oracle finalized from ECDSA attestations of ≥ max(2,
    /// ⌈2/3 · validatorCount⌉) DISTINCT registered validators, bound to this
    /// escrow (anchorBH) and fresh within 300s. The relayer remains the tx
    /// SUBMITTER (it pays gas and sequences settlement) but holds no
    /// release authority of its own: without the validator signature quorum
    /// the call reverts (ORACLE_QUORUM_UNMET / ORACLE_ROUTE_NOT_BOUND_TO_ESCROW /
    /// ORACLE_CONSENSUS_UNSAFE / ...). This is the on-chain counterpart of the
    /// DW-BFT quorum that produces the coherence score off-chain — the
    /// previously-planned BLS/Schnorr aggregate check is realized here with
    /// per-validator ECDSA attestations (publishSignal's existing discipline).
    ///
    /// BOOTSTRAP / LOCAL DEV (oracle unbound — explicit opt-out): the release
    /// accepts a coherence value from the caller (relayer/owner). This
    /// trusted-relayer mode exists for local development only; production
    /// deployments bind the oracle atomically (see setTRIONOracle natspec and
    /// evm-tools/deploy-evm.mjs — TRUSTED_RELAYER_MODE=1 skips binding).
    ///
    /// Remaining documented trust anchors (no single point can release funds
    /// alone, but jointly they administer the system):
    /// 1. The oracle's validator set is owner-administered (addValidator) —
    ///    forging a verdict requires controlling a ⌈2/3⌉ supermajority of the
    ///    registered keys; on-chain stake-and-slash remains future work.
    /// 2. The G1 Two-Phase Settlement Check (verifySettlementCheck) as a second gate
    /// 3. The 7-day emergency escape hatch (revertEmergency) as a fallback
    /// 4. The PENDING_AKASHIC 24h recovery window
    /// ═══════════════════════════════════════════════════════════════════════════

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
        // ORACLE-GATED (H1 + S3/C2 fixes): when a TRION oracle is bound, its
        // signature-quorum + freshness verdict — bound to THIS escrow via
        // anchorBH — gates the release independently of the caller-supplied
        // coherence. A route attested for a different escrow cannot release
        // this one, and no amount of relayer authority substitutes for the
        // validator attestation quorum.
        _consensusGate(escrowId, esc.routeId, esc.minCoherence);

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
        // ORACLE-GATED (H1 + S3/C2 fixes): same escrow-bound
        // signature-quorum consensus gate as releaseEscrow().
        _consensusGate(escrowId, esc.routeId, esc.minCoherence);

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
