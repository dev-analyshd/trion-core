// SPDX-License-Identifier: MIT
pragma solidity ^0.8.24;

import "./interfaces/ITrionEpochRegistry.sol";
import "./libraries/CanonicalCertificate.sol";

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
    /// INV-003 (follow-on 2 ruling): the protocol coherence floor Θ_min
    /// 0.55 (BTCP_SPEC §17 dynamic threshold; the same number as
    /// core/btcp/escrow_monitor.py::MIN_COHERENCE_FLOOR and the Move
    /// twin's MIN_COHERENCE_FLOOR). A locker may TIGHTEN their gate
    /// above the floor, never loosen below it — sub-floor values are
    /// rejected AT LOCK (fail-fast, Move/Cairo parity), so a lock can
    /// never encode a sub-floor expectation. Release remains certificate-
    /// gated (cert coherence ≥ registry threshold ≥ floor) regardless.
    uint256 public constant MIN_COHERENCE_FLOOR = 550_000; // ×1e6

    mapping(bytes32 => Escrow) private _escrows;
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
    /// @dev M-05 (audit): the minimum oracle interface is PINNED AT BIND TIME —
    ///      the bound oracle must expose the dynamic route-quorum view
    ///      minRouteAttestations() (and return ≥ 2). A weak/mock oracle
    ///      without the view can never be bound: the binding call itself
    ///      reverts, so the runtime gate never needs a fallback and the
    ///      DD "silent quorum degradation" class is closed fail-closed.
    function setTRIONOracle(address oracle) external onlyOwner {
        require(oracle != address(0), "ZERO_ORACLE");
        require(trionOracle == address(0), "ORACLE_ALREADY_BOUND");
        uint256 bindTimeQuorum = ITRIONOracleEscrowView(oracle).minRouteAttestations();
        require(bindTimeQuorum >= 2, "ORACLE_QUORUM_VIEW_WEAK");
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
        // S3/C2 STRENGTHENING + M-05: the verdict must be FINALIZED BY
        // SIGNATURE QUORUM of at least the oracle's dynamic
        // max(2, ⌈2/3 · validatorCount⌉) distinct ECDSA-verified validators.
        // setTRIONOracle() pins the minRouteAttestations() view at BIND time
        // (a mock/weak oracle cannot be bound at all), so the call below is
        // REQUIRED, never fallen back from: an oracle that lacks the view
        // fails the release closed.
        uint256 requiredQuorum = ITRIONOracleEscrowView(trionOracle).minRouteAttestations();
        require(requiredQuorum >= 2, "ORACLE_QUORUM_VIEW_WEAK");
        require(attestationCount >= requiredQuorum, "ORACLE_QUORUM_UNMET");
        require(block.timestamp - ts <= 300, "ORACLE_VERDICT_STALE");
        require(oracleCoherence >= minCoherence, "ORACLE_COHERENCE_INSUFFICIENT");
        require(oracleCoherence >= oracleThreshold, "ORACLE_BELOW_THRESHOLD");
    }

    // ══ CANONICAL CERTIFICATE RELEASE (Wave 2 — H-01/H-03/H-04/H-05/M-04) ═══
    // The V4 consumption path of docs/protocol/CANONICAL_CERTIFICATE.md §6-§8:
    // the escrow verifies the FULL canonical certificate at the point of
    // value movement, directly against the per-epoch TrionEpochRegistry —
    // NEVER against the TRIONOracleV3 verdict store (the oracle's
    // submitCertificateAttestation is the observability/index surface only;
    // re-verifying here is what structurally closes the weak-oracle-fallback
    // class, M-05). Fail-closed everywhere; no weaker fallback exists.
    //
    // Authority = the validator signature quorum (sorted, distinct, batch
    // fail-closed) over keccak256(P) EIP-191-wrapped, with weights recomputed
    // from REGISTERED epoch state (H-04), epoch activity + grace (H-01),
    // registry Θ(t) provenance (H-03) and the settlement tuple (destination,
    // amount) checked against THIS escrow's own state (H-05 — ED-B2).
    ITrionEpochRegistry public epochRegistry;
    event EpochRegistryBound(address indexed registry);

    /// @notice Bind the epoch registry for canonical-certificate releases.
    ///         One-way: once set it cannot be changed or cleared — the escrow
    ///         fails toward verification, never back toward trust. The
    ///         registry itself rotates validator sets per epoch internally
    ///         (one registrar tx per epoch boundary), so rebinding is never
    ///         needed for set rotation.
    function setEpochRegistry(address registry) external onlyOwner {
        require(registry != address(0), "ZERO_REGISTRY");
        require(address(epochRegistry) == address(0), "REGISTRY_ALREADY_BOUND");
        // Fail closed at bind time on a registry without the active-epoch
        // view (a mismatched interface can never gate value).
        require(ITrionEpochRegistry(registry).epochGrace() <= 10, "REGISTRY_INTERFACE_MISMATCH");
        epochRegistry = ITrionEpochRegistry(registry);
        emit EpochRegistryBound(registry);
    }

    /// @notice Consumed-nonce tracking (§8.1/§8.2, M-04) —
    ///         (validator_epoch, escrow_id) → highest consumed nonce.
    mapping(uint32 => mapping(bytes32 => uint64)) public canonicalHighestNonce;
    mapping(uint32 => mapping(bytes32 => bytes32)) private _canonicalDigestAtNonce;
    mapping(uint32 => mapping(bytes32 => bytes32)) private _canonicalConflictDigest;
    mapping(uint32 => mapping(bytes32 => bool)) public canonicalConflictRecorded;

    /// @notice Same (epoch, escrow, nonce) with a DIFFERENT payload digest —
    ///         on-chain equivocation evidence (§8.2) feeding L4.9 S1
    ///         slashing. The conflicting certificate does NOT settle; the
    ///         call returns false so the evidence (event + state) persists.
    event CanonicalCertificateConflict(
        bytes32 indexed escrowId,
        uint32  indexed validatorEpoch,
        uint64  certificateNonce,
        bytes32 digestA,
        bytes32 digestB
    );

    /// @notice A canonical-certificate release settled the escrow (the V4
    ///         counterpart of EscrowReleased — carries the certificate's
    ///         identity for the Akashic Index; signedPower/totalPower/coherence
    ///         are re-derivable from the certificate by indexers, and the
    ///         CertificateAttested event on the oracle carries the quorum
    ///         figures).
    event EscrowReleasedCanonical(
        bytes32 indexed escrowId,
        bytes32 indexed routeId,
        uint32  indexed validatorEpoch,
        uint64  certificateNonce,
        bytes32 payloadDigest,
        uint256 settledAt
    );

    /// @notice Release an escrow against a CANONICAL certificate (§6-§8) —
    ///         PERMISSIONLESS: the release authority is the validator
    ///         signature quorum, not msg.sender (the relayer is a mere
    ///         submitter; front-running it changes nothing — the settlement
    ///         tuple is fixed by the certificate and escrow state).
    ///         Covers both HOLDING (within timeout) and PENDING_AKASHIC
    ///         (within the 24h recovery window).
    /// @param payload         The canonical 346-byte certificate payload P.
    /// @param envelopeWeights The CANONICAL ENVELOPE (§4) weight CLAIMS,
    ///                        interleaved ×1e6: [s_0, d_0, s_1, d_1, ...]
    ///                        index-aligned with the signature batch (must
    ///                        equal the registered epoch values exactly).
    /// @param signatures      Concatenated 65-byte (r,s,v) EIP-191
    ///                        signatures over the ESCROW-BOUND digest
    ///                        (keccak256(ESCROW_BINDING_DOMAIN ‖
    ///                        address(this) ‖ keccak256(P)) — SEC-21: the
    ///                        quorum signs for THIS deployment), sorted
    ///                        ascending by recovered signer, distinct within
    ///                        the batch (length must be an exact multiple
    ///                        of 65).
    /// @return true iff the escrow was settled. false = a nonce CONFLICT was
    ///         recorded instead (equivocation evidence, no settlement).
    /// @dev Reverts (fail-closed) on every §6 violation; also requires the
    ///      G1 two-phase settlement check like the legacy path.
    function releaseEscrowCanonical(
        bytes calldata payload,
        uint256[] calldata envelopeWeights,
        bytes calldata signatures
    ) external nonReentrant returns (bool) {
        // §6 step 7 prelude — the escrow lookup is keyed by the certificate's
        // escrow_id (the binding key): a certificate for another escrow can
        // never even address this escrow's state.
        Escrow storage esc = _escrows[CanonicalCertificate.escrowIdOf(payload)];
        require(esc.escrowId != bytes32(0), "ESCROW_NOT_FOUND");
        require(
            esc.state == State.HOLDING || esc.state == State.PENDING_AKASHIC,
            "NOT_RELEASABLE"
        );
        if (esc.state == State.HOLDING) {
            require(block.number <= esc.lockBlock + esc.timeoutBlocks, "EXPIRED");
        } else {
            require(
                block.timestamp <= esc.lockTimestamp + AKASHIC_RECOVERY_SECONDS,
                "AKASHIC_WINDOW_EXPIRED"
            );
        }
        // G1: Two-Phase Confirmation — same discipline as releaseEscrow().
        require(esc.settlementCheckHash != bytes32(0), "SETTLEMENT_NOT_VERIFIED");

        // §6 steps 1-6 — structure, epoch, registry conformance, freshness,
        // signatures + weight claims, weight quorum (fail-closed, no
        // fallbacks; registry must be bound).
        _verifyCanonicalCertificate(payload, envelopeWeights, signatures);

        // §6 step 7 — BINDING against the escrow's own state (incl. the H-05
        // settlement tuple and the escrow-local min_coherence tightening).
        _checkCanonicalBinding(esc, payload);

        // §6 step 8 — nonce ordering / conflict evidence / consumption.
        // (No early return: the branch-return shape tips the via-ir stack
        // layout over budget on solc 0.8.24 — same class as the oracle fix.)
        bool consumed = _recordCanonicalConsumption(payload);
        if (consumed) {
            _settleCanonical(esc, payload);
        }
        return consumed; // false = conflict recorded, nothing settled
    }

    /// @dev Settlement effects (CEI: state BEFORE external call) + the
    ///      canonical release event. Split from the verifier body to keep the
    ///      via-ir stack layout within budget (same discipline as the oracle).
    function _settleCanonical(Escrow storage esc, bytes calldata payload) private {
        uint256 amountToTransfer = esc.amount;
        address payable destinationToPay = esc.destination;
        esc.state = State.RELEASED;
        esc.settledAt = block.timestamp;
        esc.amount = 0;
        _lockedBalance -= amountToTransfer;

        (bool ok, ) = destinationToPay.call{value: amountToTransfer}("");
        require(ok, "TRANSFER_FAILED");

        emit EscrowReleasedCanonical(
            esc.escrowId,
            CanonicalCertificate.routeIdOf(payload),
            CanonicalCertificate.epochOf(payload),
            CanonicalCertificate.nonceOf(payload),
            CanonicalCertificate.payloadDigestOf(payload),
            esc.settledAt
        );
    }

    /// @dev §6 steps 1-6 on the raw payload, mirroring the oracle's
    ///      discipline: structure/consensus preconditions (library), epoch
    ///      activity + registry conformance (H-01/H-03), freshness, batch
    ///      signature verification with envelope weight-claim cross-checks,
    ///      L4.2 weight quorum (H-04). Registry binding is a hard
    ///      precondition — the canonical path does not exist in
    ///      trusted-relayer mode. Signature verification uses the
    ///      escrow-deployment-bound digest (SEC-21), not the oracle's plain
    ///      payload digest — the value path is stricter than the
    ///      observability path by design.
    function _verifyCanonicalCertificate(
        bytes calldata payload,
        uint256[] calldata envelopeWeights,
        bytes calldata signatures
    ) internal view {
        require(address(epochRegistry) != address(0), "EPOCH_REGISTRY_UNBOUND");
        require(signatures.length % 65 == 0, "SIGNATURE_WIDTH");
        uint256 batch = signatures.length / 65;
        require(batch >= CanonicalCertificate.MIN_SIGNERS, "BELOW_MIN_SIGNERS");
        require(envelopeWeights.length == 2 * batch, "ENVELOPE_SHAPE_MISMATCH");
        CanonicalCertificate.checkPayload(payload, block.timestamp);

        uint32 epoch = CanonicalCertificate.epochOf(payload);
        require(epochRegistry.epochActive(epoch), "VALIDATOR_EPOCH_INACTIVE");
        require(
            CanonicalCertificate.validatorCountOf(payload) == epochRegistry.epochValidatorCount(epoch),
            "VALIDATOR_COUNT_MISMATCH"
        );
        require(
            CanonicalCertificate.totalPowerOf(payload) == epochRegistry.epochTotalPower(epoch),
            "TOTAL_POWER_MISMATCH"
        );
        require(
            CanonicalCertificate.thresholdOf(payload) == epochRegistry.epochThreshold(epoch),
            "THRESHOLD_NOT_FROM_REGISTRY"
        );

        // SEC-21 (P-EVM-01 amplifier, Wave 5): the VALUE path verifies the
        // quorum over the ESCROW-BOUND digest — the certificate's
        // signatures are only valid for THIS deployment, so a quorum-signed
        // release for one escrow contract can never settle a second one.
        bytes32 ethDigest = CanonicalCertificate.escrowBoundEthDigestOf(payload, address(this));
        uint256 signedPower = _verifyCanonicalSignatures(
            ethDigest, epoch, signatures, envelopeWeights
        );
        require(
            CanonicalCertificate.quorumMet(
                signedPower, epochRegistry.epochTotalPower(epoch), epochRegistry.epochDConsensus(epoch)
            ),
            "WEIGHT_QUORUM_UNMET"
        );
    }

    /// @dev §6 step 7 — the certificate must match THIS escrow's state:
    ///      escrow_id (binding key), route_id, entity_id, the SETTLEMENT TUPLE
    ///      (destination == escrow.destination left-padded, amount ==
    ///      escrow.amount — H-05/ED-B2, closes escrow-substitution) and
    ///      coherence ≥ the escrow's min_coherence (the §5.4 escrow-local
    ///      tightening; the isSafe verdict itself was checked in
    ///      checkPayload). intent_hash/anchor_bh/execution_bh are not stored
    ///      by the EVM escrow — §6 step 7 checks them "where the VM escrow
    ///      stores it".
    function _checkCanonicalBinding(Escrow storage esc, bytes calldata payload) internal view {
        require(esc.escrowId == CanonicalCertificate.escrowIdOf(payload), "CERT_NOT_BOUND_TO_ESCROW");
        require(esc.routeId == CanonicalCertificate.routeIdOf(payload), "CERT_ROUTE_MISMATCH");
        require(esc.entityId == CanonicalCertificate.entityIdOf(payload), "CERT_ENTITY_MISMATCH");
        bytes32 dest32 = CanonicalCertificate.destinationOf(payload);
        require(
            bytes12(dest32) == bytes12(0) &&
            esc.destination == address(uint160(uint256(dest32))),
            "CERT_DESTINATION_MISMATCH"
        );
        require(esc.amount == CanonicalCertificate.amountOf(payload), "CERT_AMOUNT_MISMATCH");
        require(esc.minCoherence <= CanonicalCertificate.coherenceOf(payload), "CERT_COHERENCE_INSUFFICIENT");
        // P-EVM-01 (Wave 4 red team): the certificate must settle on THIS
        // deployment's chain — a quorum-signed certificate destined for a
        // foreign chain (even an otherwise-valid one) can never pay here.
        require(
            uint256(CanonicalCertificate.destChainOf(payload)) == block.chainid,
            "CERT_DEST_CHAIN_NOT_THIS_CHAIN"
        );
    }

    /// @dev §6 step 5 — recover + order the signers, then membership, weight
    ///      claims and registered-power accumulation (pass split keeps the
    ///      via-ir stack shallow; same shape as the oracle's verifier).
    function _verifyCanonicalSignatures(
        bytes32 ethDigest,
        uint32 epoch,
        bytes calldata signatures,
        uint256[] calldata envelopeWeights
    ) internal view returns (uint256 signedPower) {
        address[] memory signers = _recoverCanonicalSigners(ethDigest, signatures);
        for (uint256 i = 0; i < signers.length; i++) {
            signedPower += _checkCanonicalSignerWeight(
                epoch, signers[i], envelopeWeights[2 * i], envelopeWeights[2 * i + 1]
            );
        }
    }

    function _recoverCanonicalSigners(bytes32 ethDigest, bytes calldata signatures)
        internal
        pure
        returns (address[] memory signers)
    {
        uint256 batch = signatures.length / 65;
        signers = new address[](batch);
        address lastSigner = address(0);
        for (uint256 i = 0; i < batch; i++) {
            address signer = CanonicalCertificate.recoverSigner(
                ethDigest, signatures[65 * i:65 * (i + 1)]
            );
            require(signer != address(0), "BAD_CERTIFICATE_SIGNATURE");
            require(signer > lastSigner, "SIGNER_ORDERING_REQUIRED");
            lastSigner = signer;
            signers[i] = signer;
        }
    }

    function _checkCanonicalSignerWeight(
        uint32 epoch,
        address signer,
        uint256 stakeClaim,
        uint256 diversityClaim
    ) internal view returns (uint256 weight) {
        weight = epochRegistry.validatorWeight(epoch, signer);
        require(weight > 0, "SIGNER_NOT_IN_EPOCH_SET");
        require(
            stakeClaim == epochRegistry.validatorStake(epoch, signer) &&
            diversityClaim == epochRegistry.validatorDiversity(epoch, signer),
            "ENVELOPE_WEIGHT_CLAIM_MISMATCH"
        );
    }

    /// @dev §6 step 8 — certificate_nonce strictly increasing per (epoch,
    ///      escrow_id); consumption records the nonce + digest. Same-nonce +
    ///      same-digest → no settlement (idempotent observability; the state
    ///      machine is the exactly-once guard). Same-nonce + different digest
    ///      → conflict evidence (event + state, emitted WITHOUT reverting so
    ///      it persists) and NO settlement.
    function _recordCanonicalConsumption(bytes calldata payload) internal returns (bool) {
        bytes32 digest = CanonicalCertificate.payloadDigestOf(payload);
        uint32 epoch = CanonicalCertificate.epochOf(payload);
        bytes32 escrowId = CanonicalCertificate.escrowIdOf(payload);
        uint64 nonce = CanonicalCertificate.nonceOf(payload);
        uint64 highest = canonicalHighestNonce[epoch][escrowId];
        if (nonce == highest) {
            if (digest != _canonicalDigestAtNonce[epoch][escrowId]) {
                if (!canonicalConflictRecorded[epoch][escrowId]) {
                    canonicalConflictRecorded[epoch][escrowId] = true;
                    _canonicalConflictDigest[epoch][escrowId] = digest;
                    emit CanonicalCertificateConflict(
                        escrowId, epoch, nonce,
                        _canonicalDigestAtNonce[epoch][escrowId], digest
                    );
                }
            }
            return false; // idempotent resubmission or conflict — no settlement
        }
        require(nonce > highest, "STALE_CERTIFICATE_NONCE");
        canonicalHighestNonce[epoch][escrowId] = nonce;
        _canonicalDigestAtNonce[epoch][escrowId] = digest;
        return true;
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
        require(_escrows[escrowId].escrowId == bytes32(0), "ESCROW_EXISTS");
        require(msg.value > 0, "ZERO_AMOUNT");
        require(destination != address(0), "ZERO_DESTINATION");
        require(minCoherence <= 1_000_000, "INVALID_COHERENCE");
        // INV-003 (follow-on 2): tightening-only — sub-floor min_coherence
        // is rejected at lock (fail-fast; Move/Cairo parity)
        require(minCoherence >= MIN_COHERENCE_FLOOR, "COHERENCE_BELOW_FLOOR");
        require(timeoutBlocks > 0, "ZERO_TIMEOUT");

        _escrows[escrowId] = Escrow({
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
        require(_escrows[escrowId].escrowId == bytes32(0), "ESCROW_EXISTS");
        require(msg.value > 0, "ZERO_AMOUNT");
        require(destination != address(0), "ZERO_DESTINATION");
        require(minCoherence <= 1_000_000, "INVALID_COHERENCE");
        // INV-003 (follow-on 2): tightening-only — sub-floor min_coherence
        // is rejected at lock (fail-fast; Move/Cairo parity)
        require(minCoherence >= MIN_COHERENCE_FLOOR, "COHERENCE_BELOW_FLOOR");
        require(timeoutBlocks > 0, "ZERO_TIMEOUT");

        _escrows[escrowId] = Escrow({
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
        Escrow storage esc = _escrows[escrowId];
        require(esc.escrowId != bytes32(0), "ESCROW_NOT_FOUND");
        require(esc.state == State.HOLDING, "NOT_HOLDING");
        // P-EVM-02 (Wave 4 red team): a block-expired escrow must go down
        // the expiry path (revert/refund), never be flipped into the
        // Akashic recovery window to extend its release lifetime.
        require(block.number <= esc.lockBlock + esc.timeoutBlocks, "ESCROW_EXPIRED");
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
        Escrow storage esc = _escrows[escrowId];
        require(esc.escrowId != bytes32(0), "ESCROW_NOT_FOUND");
        require(esc.state == State.HOLDING, "NOT_HOLDING");
        // P-EVM-02 (Wave 4 red team): a block-expired escrow must go down
        // the expiry path (revert/refund), never be flipped into the
        // Akashic recovery window to extend its release lifetime.
        require(block.number <= esc.lockBlock + esc.timeoutBlocks, "ESCROW_EXPIRED");
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
        Escrow storage esc = _escrows[escrowId];
        require(esc.escrowId != bytes32(0), "ESCROW_NOT_FOUND");
        require(esc.state == State.HOLDING, "NOT_HOLDING");
        // P-EVM-02 (Wave 4 red team): a block-expired escrow must go down
        // the expiry path (revert/refund), never be flipped into the
        // Akashic recovery window to extend its release lifetime.
        require(block.number <= esc.lockBlock + esc.timeoutBlocks, "ESCROW_EXPIRED");

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
        Escrow storage esc = _escrows[escrowId];
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
        Escrow storage esc = _escrows[escrowId];
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
        Escrow storage esc = _escrows[escrowId];
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
        Escrow storage parent = _escrows[parentEscrowId];
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
    /// @dev Split accessors: the 16-field struct return trips the solc
    ///      via-ir stack budget (value0..value15 + headStart), so the public
    ///      mapping auto-getter was removed (private _escrows) and the view
    ///      is served in two halves.
    function getEscrowCore(bytes32 escrowId)
        external
        view
        returns (
            bytes32 id,
            bytes32 route,
            bytes32 entity,
            address payable dest,
            uint256 amount,
            uint256 minCoherence,
            State state,
            bytes32 settlementCheckHash
        )
    {
        Escrow storage e = _escrows[escrowId];
        return (e.escrowId, e.routeId, e.entityId, e.destination, e.amount,
                e.minCoherence, e.state, e.settlementCheckHash);
    }

    function getEscrowMeta(bytes32 escrowId)
        external
        view
        returns (
            uint256 lockBlock,
            uint256 lockTimestamp,
            uint256 timeoutBlocks,
            RevertReason revertReason,
            uint256 settledAt,
            uint256 revertedAt,
            address lockedBy,
            bytes32 parentEscrowId
        )
    {
        Escrow storage e = _escrows[escrowId];
        return (e.lockBlock, e.lockTimestamp, e.timeoutBlocks, e.revertReason,
                e.settledAt, e.revertedAt, e.lockedBy, e.parentEscrowId);
    }

    /// @notice Check if escrow is expired (can be auto-reverted).
    function isExpired(bytes32 escrowId) external view returns (bool) {
        Escrow storage esc = _escrows[escrowId];
        return esc.state == State.HOLDING && block.number > esc.lockBlock + esc.timeoutBlocks;
    }

    /// @notice Check if emergency escape is available (Gap 8).
    function emergencyEscapeAvailable(bytes32 escrowId) external view returns (bool) {
        Escrow storage esc = _escrows[escrowId];
        return (esc.state == State.HOLDING || esc.state == State.PENDING_AKASHIC) &&
               block.timestamp >= esc.lockTimestamp + EMERGENCY_ESCAPE_SECONDS;
    }

    /// @notice Check if Akashic recovery window has expired (E1).
    function akashicWindowExpired(bytes32 escrowId) external view returns (bool) {
        Escrow storage esc = _escrows[escrowId];
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
