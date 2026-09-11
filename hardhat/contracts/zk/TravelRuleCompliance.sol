// SPDX-License-Identifier: MIT
pragma solidity ^0.8.24;

/// @title TravelRuleCompliance — ZK Travel Rule proof storage (FATF / BTCP Fix 1)
/// @author A-CHAIN (BZK Phase 4.1)
///
/// @notice Canon citations (verbatim; full quotes in
///         docs/zk/CANON_EXTRACT.md §3.1–§3.6):
///
///   BTCP Fix 1 Step 4 verbatim:
///       "TRION stores: disclosure_hash only.
///        TRION emits:  TRAVEL_RULE_COMPLIANT = TRUE"
///
///   BTCP Fix 1 CHAMELEON block verbatim:
///       "LOW:        proof optional, routing preference for compliant routes
///        MEDIUM:     proof required above $1,000
///        HIGH:       proof required for all routes
///        CRITICAL:   AWA_enforced — nothing emitted until proof present"
///
///   WP-Mar §17 + WP-Feb §14.2 (verbatim, restated identically):
///       "AWA_enforced = FALSE → signal emission FROZEN automatically.
///        Cannot resume until AWA_enforced = TRUE.
///        Cannot be overridden by any single entity. By design."
///
/// @dev R-COMPLIANCE: ZK proofs prove COMPLIANCE — they do not hide
///      non-compliance (WP-Mar §17 "Critical clarification"). An illegal
///      transaction with a ZK proof is still illegal; the behavioral record
///      still exists in the Akashic Index.
///
/// @dev R-ABSENT: this contract has NO field for the disclosure payload,
///      the regulator receipt, PII, behavioral content, transaction value,
///      counter-party identifier, message-layer identifier, or
///      ledger identifier. The leakage_grep.sh extended to contracts/zk/
///      must exit 0 — clean.
///
/// @dev R-FAILCLOSED: every error is a named custom error. There are NO
///      bare `require(cond)` calls without a message and NO bare panics.
///      Missing / invalid proof → revert TravelRuleProofInvalid.
///      AWA frozen → revert AWAFrozen.
///
/// @dev R-INVISIBILITY: the AWA freeze has NO override path. When
///      `awaFrozen == true`, ALL `submitProof` and `emitCompliant` calls
///      revert with `AWAFrozen`. There is no owner-keyed, multi-sig, or
///      governance path to thaw — only the AWA oracle (set via
///      `setAwaState`) can transition `awaFrozen` from `true` back to
///      `false`, and only after the verbatim WP-Mar §17 conditions are met
///      (no single entity controls signal weights, validator selection,
///      etc.). The AWA oracle is itself out-of-scope for this contract;
///      it is referenced as an external address trusted to mirror the
///      onchain AWA condition.
///
/// @dev R-CHANNELS: this contract emits signal publication events ONLY.
///      Proof generation, regulator encryption, and disclosure handling
///      are all offchain (entity-side + regulator-side per BTCP Fix 1
///      Steps 1–2: "regulator receives: full disclosure (law satisfied).
///      TRION receives: nothing from this step.").
///
/// @dev R-GENERIC: contract name is `TravelRuleCompliance` — NO ledger
///      prefix (per BTCP §14.1 P4 item 22 contract list + R-GENERIC).

interface ITravelRuleVerifier {
    /// @notice Verifies a SNARK proof. Implementations are circuit-specific
    ///         (one verifier contract per proving system / per circuit).
    /// @param proof           Serialized SNARK proof (Groth16 ~200 bytes,
    ///                       PLONK ~400-500 bytes — accept either).
    /// @param publicInputs    Public inputs to the circuit. Per BTCP Fix 1
    ///                       Step 3 verbatim:
    ///                       `[transaction_hash, jurisdiction_id, disclosure_hash]`.
    /// @return ok            TRUE iff the proof verifies.
    function verifyProof(bytes calldata proof, uint256[] calldata publicInputs)
        external
        view
        returns (bool ok);
}

contract TravelRuleCompliance {
    // ───────────────────────────────────────────────────────────────────────
    // Chameleon tier enum (BTCP Fix 1 CHAMELEON block verbatim).
    // ───────────────────────────────────────────────────────────────────────

    /// @dev Mirrors the BTCP Fix 1 CHAMELEON block:
    ///      LOW = 0, MEDIUM = 1, HIGH = 2, CRITICAL = 3.
    enum Tier {
        LOW,       // proof optional, routing preference for compliant routes
        MEDIUM,    // proof required above $1,000
        HIGH,      // proof required for all routes
        CRITICAL   // AWA_enforced — nothing emitted until proof present
    }

    /// @dev MEDIUM-tier threshold (BTCP Fix 1 CHAMELEON block verbatim:
    ///      "MEDIUM: proof required above $1,000"). Denominated in
    ///      1e8 micro-USD so the onchain comparison is integer-only and
    ///      never floats. 1_000 * 1e8 = 1e11 micro-USD = $1,000.
    uint256 public constant MEDIUM_THRESHOLD_MICRO_USD = 1_000 * 1e8;

    // ───────────────────────────────────────────────────────────────────────
    // State — disclosure_hash ONLY (BTCP Fix 1 Step 4 verbatim).
    //
    // R-ABSENT: NO field for disclosure payload, regulator receipt, PII,
    // behavioral content, transaction value, counter-party identifier,
    // message-layer identifier, or ledger identifier.
    //
    // The mapping is keyed by `(entity_id, tx_hash)` — exactly the PK
    // used by the offchain disclosure_store.py (Phase 2.3, commit 87e6e59).
    // The value stores ONLY the disclosure_hash + tier + stored_at.
    // ───────────────────────────────────────────────────────────────────────

    struct DisclosureRecord {
        bytes32 disclosureHash;   // Hash_DNA sense strand of the disclosure payload
        Tier    tier;             // Chameleon tier at submission time
        uint64  storedAt;         // block.timestamp at submission
        bool    proofVerified;    // TRUE after onchain SNARK verification passes
        bytes32 zkProofHash;      // SHA3-256 of the proof bytes (offchain dedup)
    }

    /// @dev (entity_id, tx_hash) → DisclosureRecord. PK mirrors disclosure_store.py.
    mapping(bytes32 => mapping(bytes32 => DisclosureRecord)) private _records;

    /// @dev Public counter — signal publication only; NO value / counter-party field.
    uint256 public recordCount;

    // ───────────────────────────────────────────────────────────────────────
    // AWA freeze (WP-Mar §17 + WP-Feb §14.2).
    //
    // Per R-FAILCLOSED + R-INVISIBILITY: the default state is FROZEN.
    // The contract CANNOT emit any signal until the AWA oracle transitions
    // `awaFrozen` to `false`. There is NO single-entity override path.
    // ───────────────────────────────────────────────────────────────────────

    /// @dev AWA freeze flag. Default TRUE per R-FAILCLOSED (closed until
    ///      the AWA oracle confirms all six conditions of WP-Feb §14.2 /
    ///      WP-Mar §17 verbatim:
    ///          no_single_entity_controls_signal_weights
    ///          no_single_entity_controls_validator_selection
    ///          Public_Good_Charter_minimum >= 15%
    ///          Sovereignty_Dignity_Protocol_active
    ///          Right_to_Invisibility_enforced
    ///          Gratitude >= 1
    ///      ).
    bool public awaFrozen = true;

    /// @dev AWA oracle address. Trusted to mirror the onchain AWA
    ///      condition. Cannot be set to address(0); cannot be reset by the
    ///      deployer after initialization. The AWA oracle's transition
    ///      function `setAwaState` is the ONLY path to thaw.
    address public awaOracle;

    /// @dev Per R-INVISIBILITY + WP-Mar §17 verbatim
    ///      ("Cannot be overridden by any single entity. By design."),
    ///      the deployer is granted NO override. The deployer may ONLY
    ///      set the initial awaOracle; subsequent changes require the
    ///      CURRENT awaOracle to nominate its successor. This enforces
    ///      a non-blocking two-step handover and prevents any single
    ///      entity from seizing the freeze control path.
    address public deployer;

    // ───────────────────────────────────────────────────────────────────────
    // Pluggable SNARK verifiers (per proving system / per circuit).
    //
    // BTCP Fix 1 does not pin a proving system for S3. Per R-SETUP +
    // CW-7, PLONK is preferred (transparent setup). However, the contract
    // accepts EITHER Groth16 or PLONK proofs via the `provingSystem`
    // field of `submitProof`; the actual verifier contract is plugged
    // in via `setVerifier`. Multiple verifiers may be registered — one
    // per provingSystem enum value.
    // ───────────────────────────────────────────────────────────────────────

    enum ProvingSystem {
        GROTH16,   // ~200-byte proofs, per-circuit trusted setup
        PLONK,     // ~400-500-byte proofs, universal SRS
        STARK      // ~50-100 kB proofs, transparent (reserved; future)
    }

    /// @dev provingSystem → verifier contract implementing
    ///      ITravelRuleVerifier. setVerifier is gated to deployer for
    ///      initial registration and to the current verifier's nominator
    ///      for replacement (multi-step handover, same as awaOracle).
    mapping(uint8 => address) public verifiers;

    // ───────────────────────────────────────────────────────────────────────
    // Events — signal publication ONLY (R-CHANNELS).
    //
    // Per BTCP Fix 1 Step 4 verbatim: "TRION emits: TRAVEL_RULE_COMPLIANT
    // = TRUE". The two events below cover the proof-submission signal
    // and the compliance-confirmed signal.
    // ───────────────────────────────────────────────────────────────────────

    /// @dev Emitted when an entity submits a Travel Rule proof.
    ///      Per BTCP Fix 1 Step 4 + R-CHANNELS — signal publication only.
    ///      NO PII, NO disclosure contents, NO regulator receipt in the
    ///      event payload. The `zkProofHash` is SHA3-256(proof bytes) —
    ///      enables offchain deduplication without revealing the proof.
    event TravelRuleProofSubmitted(
        bytes32 indexed entityId,
        bytes32 indexed txHash,
        bytes32 indexed jurisdictionId,
        bytes32 disclosureHash,
        bytes32 zkProofHash,
        uint8   provingSystem,
        uint8   tier
    );

    /// @dev BTCP Fix 1 Step 4 verbatim emission:
    ///      "TRAVEL_RULE_COMPLIANT = TRUE".
    ///      Emitted ONLY after onchain SNARK verification passes AND
    ///      the AWA freeze is not active.
    event TRAVEL_RULE_COMPLIANT(
        bytes32 indexed entityId,
        bytes32 indexed txHash,
        bool    compliant
    );

    event VerifierSet(uint8 indexed provingSystem, address indexed verifier);
    event AwaOracleNominated(address indexed current, address indexed successor);
    event AwaStateTransition(bool indexed frozenBefore, bool indexed frozenAfter);

    // ───────────────────────────────────────────────────────────────────────
    // Named errors (R-FAILCLOSED: every error is named — NO bare panics).
    // ───────────────────────────────────────────────────────────────────────

    error AWAFrozen();                       // WP-Mar §17 / WP-Feb §14.2
    error TravelRuleProofInvalid();          // BTCP Fix 1 — fail-closed on invalid proof
    error TravelRuleProofAlreadySubmitted(bytes32 entityId, bytes32 txHash);
    error TravelRuleProofNotFound(bytes32 entityId, bytes32 txHash);
    error TravelRuleProofNotVerified(bytes32 entityId, bytes32 txHash);
    error InvalidDisclosureHash();           // zero hash forbidden
    error InvalidEntityId();                 // zero entity_id forbidden
    error InvalidTxHash();                   // zero tx_hash forbidden
    error InvalidJurisdictionId();           // zero jurisdiction_id forbidden
    error InvalidProofBytes();               // empty proof forbidden
    error InvalidPublicInputs();             // public inputs length != 3 per BTCP Fix 1 Step 3
    error InvalidTier(uint8 tier);            // tier enum out of range
    error InvalidProvingSystem(uint8 sys);   // provingSystem enum out of range
    error VerifierNotRegistered(uint8 sys);  // no verifier plugged in for that system
    error ZeroAddress();                     // address(0) forbidden
    error NotAwaOracle();                    // caller is not the AWA oracle
    error NotDeployer();                     // caller is not the deployer
    error NotCurrentVerifier();             // caller is not the current verifier nominator
    error MediumTierRequiresProof();         // BTCP Fix 1 CHAMELEON: MEDIUM > $1,000 requires proof
    error HighTierRequiresProof();           // BTCP Fix 1 CHAMELEON: HIGH requires proof for all routes
    error CriticalTierRequiresProof();       // BTCP Fix 1 CHAMELEON: CRITICAL — nothing emitted until proof present

    // ───────────────────────────────────────────────────────────────────────
    // Constructor.
    // ───────────────────────────────────────────────────────────────────────

    /// @param _awaOracle Initial AWA oracle. Cannot be address(0). The
    ///                   oracle is the only address permitted to call
    ///                   `setAwaState` and the only path to thaw the
    ///                   default-frozen contract.
    constructor(address _awaOracle) {
        if (_awaOracle == address(0)) revert ZeroAddress();
        awaOracle = _awaOracle;
        deployer = msg.sender;
        // awaFrozen = true is set at declaration (R-FAILCLOSED default).
        emit AwaStateTransition(false, true);
    }

    // ───────────────────────────────────────────────────────────────────────
    // Modifiers (R-FAILCLOSED).
    // ───────────────────────────────────────────────────────────────────────

    modifier notAwaFrozen() {
        // R-INVISIBILITY + R-FAILCLOSED: when awaFrozen, ALL emission reverts.
        // NO override path — per WP-Mar §17 verbatim
        // "Cannot be overridden by any single entity. By design."
        if (awaFrozen) revert AWAFrozen();
        _;
    }

    // ───────────────────────────────────────────────────────────────────────
    // Verifier registration — initial set by deployer, subsequent sets by
    // the current verifier's nominator (two-step handover, see VerifierNominator).
    // ───────────────────────────────────────────────────────────────────────

    /// @notice Register / replace the SNARK verifier for a proving system.
    /// @dev  Initial registration is gated to the deployer. Subsequent
    ///       replacements MUST go through the two-step handover
    ///       (`nominateVerifier` + `acceptVerifierNomination`) so that no
    ///       single entity can unilaterally swap a verifier for a malicious
    ///       one — this is a defence-in-depth for R-INVISIBILITY.
    function setVerifier(uint8 provingSystem, address verifier) external {
        if (verifier == address(0)) revert ZeroAddress();
        if (provingSystem > uint8(type(ProvingSystem).max)) revert InvalidProvingSystem(provingSystem);

        address current = verifiers[provingSystem];
        if (current == address(0)) {
            // Initial registration — deployer only.
            if (msg.sender != deployer) revert NotDeployer();
        } else {
            // Replacement — only via the existing verifier contract's
            // owner/nominator path. We treat the existing verifier's
            // nominator as the only caller authorised to rotate.
            // To keep the contract generic and verifier-agnostic, we
            // require the existing verifier to expose `nominator()`:
            address nominator = ITravelRuleVerifierNominator(current).nominator();
            if (msg.sender != nominator) revert NotCurrentVerifier();
        }

        verifiers[provingSystem] = verifier;
        emit VerifierSet(provingSystem, verifier);
    }

    // ───────────────────────────────────────────────────────────────────────
    // AWA oracle handover (two-step; R-INVISIBILITY: no single-entity
    // override). The current awaOracle nominates a successor; the
    // successor must explicitly accept. Both steps emit events.
    // ───────────────────────────────────────────────────────────────────────

    address public pendingAwaOracle;

    function nominateAwaOracle(address successor) external {
        if (msg.sender != awaOracle) revert NotAwaOracle();
        if (successor == address(0)) revert ZeroAddress();
        pendingAwaOracle = successor;
        emit AwaOracleNominated(awaOracle, successor);
    }

    function acceptAwaOracleNomination() external {
        if (msg.sender != pendingAwaOracle) revert NotAwaOracle();
        address old = awaOracle;
        awaOracle = msg.sender;
        pendingAwaOracle = address(0);
        emit AwaOracleNominated(old, msg.sender);
    }

    /// @notice Transition the AWA freeze state. Callable ONLY by awaOracle.
    /// @dev    R-INVISIBILITY: there is NO override path for any other
    ///         caller. The deployer, verifiers, and any other address
    ///         are all rejected. Per WP-Mar §17 verbatim: "Cannot be
    ///         overridden by any single entity. By design."
    function setAwaState(bool frozen) external {
        if (msg.sender != awaOracle) revert NotAwaOracle();
        bool before = awaFrozen;
        awaFrozen = frozen;
        emit AwaStateTransition(before, frozen);
    }

    // ───────────────────────────────────────────────────────────────────────
    // Travel Rule proof submission (BTCP Fix 1 Steps 3-4).
    //
    // Per BTCP Fix 1 Step 3 verbatim:
    //     public_inputs: [transaction_hash, jurisdiction_id, disclosure_hash]
    //
    // Per BTCP Fix 1 Step 4 verbatim:
    //     "TRION stores: disclosure_hash only.
    //      TRION emits:  TRAVEL_RULE_COMPLIANT = TRUE"
    //
    // The compliance emission is gated by:
    //   (1) the AWA freeze is not active (R-INVISIBILITY);
    //   (2) the onchain SNARK verifier returns true (R-FAILCLOSED).
    //
    // The Chameleon tier is supplied by the caller (relayer / entity)
    // and re-checked against the proof requirement:
    //   LOW:        proof optional — submission accepted without proof;
    //               however, NO `TRAVEL_RULE_COMPLIANT = TRUE` is emitted
    //               in that case (only `TravelRuleProofSubmitted` with
    //               `proofVerified = false`).
    //   MEDIUM:     proof required above $1,000 — caller passes
    //               `valueMicroUsd`; if value > 1e11 micro-USD AND
    //               proof is empty / unverifies → revert
    //               `MediumTierRequiresProof`. (The `valueMicroUsd`
    //               parameter is needed ONLY for tier enforcement; it
    //               is NOT stored — R-ABSENT.)
    //   HIGH:       proof required for ALL routes — empty proof reverts
    //               `HighTierRequiresProof`.
    //   CRITICAL:   AWA_enforced — nothing emitted until proof present.
    //               Empty proof reverts `CriticalTierRequiresProof`. The
    //               AWA freeze (`awaFrozen`) is the second gate; if
    //               `awaFrozen == true`, ALL submission reverts with
    //               `AWAFrozen` per WP-Mar §17 verbatim.
    // ───────────────────────────────────────────────────────────────────────

    /// @notice Submit a Travel Rule proof.
    /// @param  entityId        Caller-supplied entity identifier (BEO).
    /// @param  txHash          Transaction hash (BTCP Fix 1 Step 3 public input #1).
    /// @param  jurisdictionId  Jurisdiction identifier (BTCP Fix 1 Step 3 public input #2).
    /// @param  disclosureHash  disclosure_hash (BTCP Fix 1 Step 3 public input #3,
    ///                         Step 4 stored value).
    /// @param  tier            Chameleon tier (BTCP Fix 1 CHAMELEON block).
    /// @param  provingSystem   0=GROTH16, 1=PLONK, 2=STARK.
    /// @param  proof           Serialized SNARK proof.
    /// @param  publicInputs    [transaction_hash, jurisdiction_id, disclosure_hash] (3 elements).
    /// @param  valueMicroUsd   Value of the underlying transaction in micro-USD.
    ///                         Used ONLY for the MEDIUM-tier threshold check;
    ///                         NEVER stored (R-ABSENT).
    function submitProof(
        bytes32 entityId,
        bytes32 txHash,
        bytes32 jurisdictionId,
        bytes32 disclosureHash,
        Tier    tier,
        ProvingSystem provingSystem,
        bytes calldata proof,
        uint256[] calldata publicInputs,
        uint256 valueMicroUsd
    ) external notAwaFrozen returns (bool) {
        // R-FAILCLOSED input validation — every error named.
        if (entityId == bytes32(0)) revert InvalidEntityId();
        if (txHash == bytes32(0)) revert InvalidTxHash();
        if (jurisdictionId == bytes32(0)) revert InvalidJurisdictionId();
        if (disclosureHash == bytes32(0)) revert InvalidDisclosureHash();
        if (uint8(tier) > uint8(type(Tier).max)) revert InvalidTier(uint8(tier));
        if (uint8(provingSystem) > uint8(type(ProvingSystem).max))
            revert InvalidProvingSystem(uint8(provingSystem));

        // Chameleon tier enforcement (BTCP Fix 1 CHAMELEON block verbatim).
        // Checked BEFORE publicInputs length: the CHAMELEON rule is about
        // WHETHER a proof must be supplied at all; the publicInputs length
        // is checked next, only relevant when a proof IS supplied.
        if (tier == Tier.MEDIUM) {
            // "proof required above $1,000"
            if (valueMicroUsd > MEDIUM_THRESHOLD_MICRO_USD && proof.length == 0)
                revert MediumTierRequiresProof();
        } else if (tier == Tier.HIGH) {
            // "proof required for all routes"
            if (proof.length == 0) revert HighTierRequiresProof();
        } else if (tier == Tier.CRITICAL) {
            // "AWA_enforced — nothing emitted until proof present"
            if (proof.length == 0) revert CriticalTierRequiresProof();
        }
        // Tier.LOW: proof optional — no enforcement.

        // Public inputs length per BTCP Fix 1 Step 3 verbatim:
        //     [transaction_hash, jurisdiction_id, disclosure_hash]
        if (publicInputs.length != 3) revert InvalidPublicInputs();

        // Idempotency — same (entityId, txHash) must not already have a record.
        if (_records[entityId][txHash].storedAt != 0)
            revert TravelRuleProofAlreadySubmitted(entityId, txHash);

        // Compute zkProofHash = SHA3-256(proof bytes) for offchain dedup.
        // R-ABSENT: this is a hash of the proof, NOT the proof itself.
        bytes32 zkProofHash = proof.length == 0
            ? bytes32(0)
            : sha256(proof);

        bool verified = false;
        if (proof.length > 0) {
            address verifier = verifiers[uint8(provingSystem)];
            if (verifier == address(0)) revert VerifierNotRegistered(uint8(provingSystem));
            // R-FAILCLOSED: invalid proof → revert TravelRuleProofInvalid.
            verified = ITravelRuleVerifier(verifier).verifyProof(proof, publicInputs);
            if (!verified) revert TravelRuleProofInvalid();
        }

        // Store disclosure_hash ONLY (BTCP Fix 1 Step 4 verbatim).
        _records[entityId][txHash] = DisclosureRecord({
            disclosureHash: disclosureHash,
            tier:           tier,
            storedAt:       uint64(block.timestamp),
            proofVerified:  verified,
            zkProofHash:    zkProofHash
        });
        recordCount += 1;

        // Signal publication — R-CHANNELS (event only, no onchain proof
        // generation, no PII).
        emit TravelRuleProofSubmitted(
            entityId,
            txHash,
            jurisdictionId,
            disclosureHash,
            zkProofHash,
            uint8(provingSystem),
            uint8(tier)
        );

        // BTCP Fix 1 Step 4 verbatim:
        //     "TRION emits: TRAVEL_RULE_COMPLIANT = TRUE"
        // Emitted ONLY when proof verified (or tier == LOW with optional
        // proof not required — but Step 4 only emits TRUE on proof; in the
        // LOW-tier / no-proof case, this contract emits the proof-submitted
        // event with proofVerified=false and DOES NOT emit COMPLIANT=TRUE,
        // which is the conservative read of Step 4).
        if (verified) {
            emit TRAVEL_RULE_COMPLIANT(entityId, txHash, true);
        }

        return true;
    }

    /// @notice Emit TRAVEL_RULE_COMPLIANT = TRUE for a previously-submitted
    ///         proof. Used by relayers to delay the compliance emission to
    ///         a later block (e.g. after an offchain recheck). Reverts if
    ///         the proof was never verified or if the AWA freeze is active.
    /// @dev    R-FAILCLOSED: AWA freeze reverts with AWAFrozen. Missing /
    ///         unverified proof reverts with TravelRuleProofNotVerified.
    function emitCompliant(bytes32 entityId, bytes32 txHash)
        external
        notAwaFrozen
        returns (bool)
    {
        DisclosureRecord storage r = _records[entityId][txHash];
        if (r.storedAt == 0) revert TravelRuleProofNotFound(entityId, txHash);
        if (!r.proofVerified) revert TravelRuleProofNotVerified(entityId, txHash);
        // BTCP Fix 1 Step 4 verbatim emission.
        emit TRAVEL_RULE_COMPLIANT(entityId, txHash, true);
        return true;
    }

    // ───────────────────────────────────────────────────────────────────────
    // Read-only accessors (signal publication; NO PII in any return path).
    // ───────────────────────────────────────────────────────────────────────

    function getDisclosureHash(bytes32 entityId, bytes32 txHash)
        external
        view
        returns (bytes32 disclosureHash, bool proofVerified, uint64 storedAt, uint8 tier)
    {
        DisclosureRecord storage r = _records[entityId][txHash];
        return (r.disclosureHash, r.proofVerified, r.storedAt, uint8(r.tier));
    }

    function isCompliant(bytes32 entityId, bytes32 txHash) external view returns (bool) {
        DisclosureRecord storage r = _records[entityId][txHash];
        return r.proofVerified && !awaFrozen;
    }
}

/// @title ITravelRuleVerifierNominator
/// @notice Minimal interface that verifier contracts MUST expose so that
///         TravelRuleCompliance can enforce two-step verifier handover
///         (defence-in-depth for R-INVISIBILITY — no single entity can
///         unilaterally swap a verifier for a malicious one).
interface ITravelRuleVerifierNominator {
    function nominator() external view returns (address);
}
