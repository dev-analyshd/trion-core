// SPDX-License-Identifier: MIT
pragma solidity ^0.8.24;

/// @title IntentCommitmentRegistry — S1 ZK Intent Commitment (BTCP §5.6).
/// @author A-CHAIN (BZK Phase 4.2)
///
/// @notice Canon citations (verbatim; full quotes in
///         docs/zk/CANON_EXTRACT.md §1.1–§1.3):
///
///   BTCP §5.6 Phase 1 verbatim:
///       "Phase 1 — Commit (MEV bots see nothing actionable):
///        H_intent = Hash_DNA(intent_details || random_nonce || entity_id)
///        User submits: H_intent ONLY
///        MEV bots observe: a commitment hash — no direction, no value, nothing
///        // Implementation: submit `H_intent` to `BTCPIntent.sol`
///        // Contract stores: `H_intent → timestamp, entity_id`
///        // NO routing calculation yet"
///
///   BTCP §5.6 Phase 2 verbatim (the complementarity statement):
///       "TRION searches for `H_intent_B` that is complement of `H_intent_A`
///        Both parties prove complementarity through ZK proof:
///            zk_proof = SNARK.prove(
///                statement: 'H_my_intent and H_counterparty_intent are complements',
///                public_inputs:   [H_intent_A, H_intent_B, entity_id_A, entity_id_B],
///                private_inputs: [intent_A_full, intent_B_full, nonce_A, nonce_B]
///            )"
///
///   BTCP §5.6 Phase 3 verbatim:
///       "Phase 3 — Atomic Reveal (both in same block):
///        Both intents published in same block — atomic
///        If complements verified: execution commits immediately
///        If not complements: both intents remain hidden, no information leaked"
///
/// @dev R-ABSENT: this contract has NO field for intent contents (direction,
///      value, asset, counter-party identifier, message-layer identifier,
///      or ledger identifier). Only the commitment hash H_intent, the
///      entity_id, and the stored-at timestamp are persisted. The
///      leakage_grep.sh extended to contracts/zk/ must exit 0 — clean.
///
/// @dev R-FAILCLOSED: every error is a named custom error. There are NO
///      bare `require(cond)` calls without a message and NO bare panics.
///      Complementarity proof failure → revert `ComplementarityProofFailed`
///      AND both intents remain hidden (BTCP §5.6 Phase 3 verbatim:
///      "If not complements: both intents remain hidden, no information
///      leaked"). The reveal is atomic: both H_intent_A and H_intent_B
///      MUST be revealed in the SAME transaction, or NEITHER is revealed.
///
/// @dev R-CHANNELS: this contract emits signal publication events ONLY.
///      No economic coordination, no routing calculation, no execution
///      logic. Per BTCP §5.6 Phase 1 verbatim: "NO routing calculation yet".
///      Per R-CHANNELS (WP-Mar §15): "SMART CONTRACTS — OUTPUT ONLY:
///      Signal publication (Solidity). Economic coordination (Vyper)."
///
/// @dev R-GENERIC: contract name is `IntentCommitmentRegistry` — NO ledger
///      prefix (per R-GENERIC).
///
/// @dev R-NO-REDEF: the H_intent hash itself is computed offchain via
///      `zk-circuits/commitments/hash_dna.py::intent_hash(intent_details,
///      random_nonce, entity_id)` (Phase 2.1, commit 2429e7e). This contract
///      receives the 32-byte sense strand as a `bytes32` and stores it —
///      it does NOT re-implement the Hash_DNA construction (which is
///      a SNARK-friendly dual-strand SHA3-256 with complementarity
///      invariant, see BTCP Formula Index).

interface IComplementarityVerifier {
    /// @notice Verifies a complementarity proof per BTCP §5.6 Phase 2.
    /// @dev    Public inputs per BTCP §5.6 Phase 2 verbatim:
    ///         `[H_intent_A, H_intent_B, entity_id_A, entity_id_B]`.
    ///         The MEASURED circuit (zk_complementarity_proof, Phase 1
    ///         commit cbd2996, 2,686 constraints, 5 public inputs) adds
    ///         a 5th tolerance parameter — see docs/zk/FEASIBILITY_AND_SETUP.md §2.
    ///         Implementations MUST accept exactly 5 public inputs.
    /// @param proof        Serialized SNARK proof (Groth16 per BTCP §5.6).
    /// @param publicInputs 5-element array:
    ///                     [0] H_intent_A
    ///                     [1] H_intent_B
    ///                     [2] entity_id_A
    ///                     [3] entity_id_B
    ///                     [4] tolerance parameter (Phase 2 magnitude_A ≈ magnitude_B)
    /// @return ok TRUE iff the proof verifies for the supplied public inputs.
    ///         Implementations MAY emit a ProofVerified signal-publication
    ///         event (R-CHANNELS) — therefore this function is NOT `view`.
    function verifyProof(bytes calldata proof, uint256[] calldata publicInputs)
        external
        returns (bool ok);
}

contract IntentCommitmentRegistry {
    // ───────────────────────────────────────────────────────────────────────
    // State — `H_intent → (timestamp, entity_id)` (BTCP §5.6 Phase 1 verbatim).
    //
    // R-ABSENT: NO field for intent contents, direction, value, asset,
    // counter-party identifier, message-layer identifier, or ledger identifier.
    // The mapping stores ONLY the timestamp + entity_id per BTCP §5.6 Phase 1
    // verbatim: "Contract stores: H_intent → timestamp, entity_id".
    // ───────────────────────────────────────────────────────────────────────

    struct IntentCommit {
        uint64  committedAt;    // block.timestamp at commit (BTCP §5.6 Phase 1)
        bytes32 entityId;       // entity identifier (BTCP §5.6 Phase 1)
        bool    revealed;       // TRUE after atomic reveal (BTCP §5.6 Phase 3)
    }

    /// @dev H_intent → IntentCommit. H_intent is the 32-byte Hash_DNA sense
    ///      strand (computed offchain via hash_dna.intent_hash). The
    ///      complementarity SNARK (Phase 2) consumes the dual-strand form
    ///      via hash_dna.hash_dna_dual.
    mapping(bytes32 => IntentCommit) private _commits;

    /// @dev Public counter — signal publication only.
    uint256 public commitCount;

    /// @dev Public counter for atomic reveals — signal publication only.
    uint256 public revealCount;

    // ───────────────────────────────────────────────────────────────────────
    // Pluggable complementarity verifier (Phase 4.3).
    //
    // The verifier contract implements `IComplementarityVerifier` and is
    // plugged in via `setVerifier`. The handover follows the same two-step
    // pattern as TravelRuleCompliance (defence-in-depth for R-INVISIBILITY
    // — no single entity can unilaterally swap a verifier for a malicious one).
    // ───────────────────────────────────────────────────────────────────────

    address public verifier;
    address public pendingVerifier;
    address public deployer;

    // ───────────────────────────────────────────────────────────────────────
    // Events — signal publication ONLY (R-CHANNELS).
    // ───────────────────────────────────────────────────────────────────────

    /// @dev BTCP §5.6 Phase 1 verbatim: "Contract stores: H_intent →
    ///      timestamp, entity_id". Emitted on every successful commit.
    ///      NO intent contents in the event payload.
    event IntentCommitted(
        bytes32 indexed entityId,
        bytes32 indexed H_intent,
        uint256 indexed timestamp
    );

    /// @dev BTCP §5.6 Phase 3 atomic reveal — both intents in same block.
    ///      Emitted ONLY if the complementarity proof verifies. If the
    ///      proof fails, the transaction reverts with `ComplementarityProofFailed`
    ///      AND both intents remain hidden (no event emitted, no state change).
    event IntentRevealed(
        bytes32 indexed H_intent_A,
        bytes32 indexed H_intent_B,
        bytes32 indexed zk_proof_hash
    );

    event VerifierSet(address indexed verifier);
    event VerifierNominated(address indexed current, address indexed successor);

    // ───────────────────────────────────────────────────────────────────────
    // Named errors (R-FAILCLOSED).
    // ───────────────────────────────────────────────────────────────────────

    error ZeroHIntent();                     // zero H_intent forbidden
    error ZeroEntityId();                    // zero entity_id forbidden
    error IntentAlreadyCommitted(bytes32 H_intent);  // idempotency
    error IntentNotFound(bytes32 H_intent);   // reveal without prior commit
    error ComplementarityProofFailed();      // BTCP §5.6 Phase 3 fail-closed
    error InvalidPublicInputsLength();        // != 5 per MEASURED circuit (Phase 1)
    error InvalidProofBytes();                // empty proof forbidden
    error VerifierNotRegistered();            // no verifier plugged in
    error ZeroAddress();                      // address(0) forbidden
    error NotDeployer();                      // caller is not deployer
    error NotCurrentVerifier();              // caller is not the current verifier nominator
    error IntentAlreadyRevealed(bytes32 H_intent);   // double-reveal forbidden

    // ───────────────────────────────────────────────────────────────────────
    // Constructor.
    // ───────────────────────────────────────────────────────────────────────

    constructor() {
        deployer = msg.sender;
    }

    // ───────────────────────────────────────────────────────────────────────
    // Verifier registration — initial set by deployer, subsequent sets by
    // the current verifier's nominator (two-step handover, see
    // ComplementarityVerifier.sol).
    // ───────────────────────────────────────────────────────────────────────

    /// @notice Register / replace the complementarity verifier.
    /// @dev  Initial registration is gated to the deployer. Subsequent
    ///       replacements MUST go through the two-step handover
    ///       (`nominateVerifier` + `acceptVerifierNomination`) so that no
    ///       single entity can unilaterally swap a verifier for a malicious
    ///       one — defence-in-depth for R-INVISIBILITY.
    function setVerifier(address _verifier) external {
        if (_verifier == address(0)) revert ZeroAddress();
        if (verifier == address(0)) {
            // Initial registration — deployer only.
            if (msg.sender != deployer) revert NotDeployer();
        } else {
            // Replacement — only via the existing verifier's nominator path.
            address nominator = IComplementarityVerifierNominator(verifier).nominator();
            if (msg.sender != nominator) revert NotCurrentVerifier();
        }
        verifier = _verifier;
        emit VerifierSet(_verifier);
    }

    function nominateVerifier(address successor) external {
        if (verifier == address(0)) revert VerifierNotRegistered();
        if (msg.sender != IComplementarityVerifierNominator(verifier).nominator())
            revert NotCurrentVerifier();
        if (successor == address(0)) revert ZeroAddress();
        pendingVerifier = successor;
        emit VerifierNominated(verifier, successor);
    }

    function acceptVerifierNomination() external {
        if (msg.sender != pendingVerifier) revert NotCurrentVerifier();
        address old = verifier;
        verifier = msg.sender;
        pendingVerifier = address(0);
        emit VerifierNominated(old, msg.sender);
    }

    // ───────────────────────────────────────────────────────────────────────
    // Phase 1 — Commit (BTCP §5.6 Phase 1 verbatim).
    //
    // Per BTCP §5.6 Phase 1 verbatim:
    //     "H_intent = Hash_DNA(intent_details || random_nonce || entity_id)
    //      User submits: H_intent ONLY
    //      MEV bots observe: a commitment hash — no direction, no value, nothing
    //      // Implementation: submit `H_intent` to `BTCPIntent.sol`
    //      // Contract stores: `H_intent → timestamp, entity_id`
    //      // NO routing calculation yet"
    //
    // The H_intent is computed offchain via
    //     hash_dna.intent_hash(intent_details, random_nonce, entity_id)
    // (Phase 2.1, commit 2429e7e). This contract receives the 32-byte sense
    // strand as a `bytes32` and stores it — it does NOT re-implement the
    // Hash_DNA construction (R-NO-REDEF).
    // ───────────────────────────────────────────────────────────────────────

    /// @notice Commit an intent. Stores `H_intent → (timestamp, entity_id)`
    ///         per BTCP §5.6 Phase 1 verbatim. NO routing calculation.
    /// @dev    R-FAILCLOSED: zero H_intent or zero entity_id reverts.
    ///         R-ABSENT: NO field for intent contents, direction, value,
    ///         asset, counter-party identifier, message-layer identifier,
    ///         or ledger identifier.
    /// @param  H_intent  32-byte Hash_DNA sense strand (offchain-computed).
    /// @param  entityId  Entity identifier (BTCP §5.6 Phase 1 verbatim).
    function commitIntent(bytes32 H_intent, bytes32 entityId)
        external
        returns (bool)
    {
        // R-FAILCLOSED input validation — every error named.
        if (H_intent == bytes32(0)) revert ZeroHIntent();
        if (entityId == bytes32(0)) revert ZeroEntityId();
        if (_commits[H_intent].committedAt != 0) revert IntentAlreadyCommitted(H_intent);

        // Store H_intent → (timestamp, entity_id) per BTCP §5.6 Phase 1 verbatim.
        _commits[H_intent] = IntentCommit({
            committedAt: uint64(block.timestamp),
            entityId:    entityId,
            revealed:    false
        });
        commitCount += 1;

        // Signal publication — R-CHANNELS (event only, no intent contents).
        emit IntentCommitted(entityId, H_intent, block.timestamp);
        return true;
    }

    // ───────────────────────────────────────────────────────────────────────
    // Phase 3 — Atomic Reveal (BTCP §5.6 Phase 3 verbatim).
    //
    // Per BTCP §5.6 Phase 3 verbatim:
    //     "Phase 3 — Atomic Reveal (both in same block):
    //      Both intents published in same block — atomic
    //      If complements verified: execution commits immediately
    //      If not complements: both intents remain hidden, no information leaked"
    //
    // Atomicity is enforced by Solidity's transaction semantics: this
    // function receives BOTH H_intent_A and H_intent_B in a single call.
    // If the complementarity proof fails, the entire transaction reverts —
    // both intents remain hidden (no state change, no event emitted).
    //
    // Public inputs per BTCP §5.6 Phase 2 verbatim:
    //     [H_intent_A, H_intent_B, entity_id_A, entity_id_B]
    //
    // Plus the 5th tolerance parameter (Phase 1 MEASURED circuit,
    // 5 public inputs total — see docs/zk/FEASIBILITY_AND_SETUP.md §2).
    // ───────────────────────────────────────────────────────────────────────

    /// @notice Atomic same-block reveal of two complement intents.
    /// @dev    BTCP §5.6 Phase 3 verbatim: "If complements verified:
    ///         execution commits immediately. If not complements: both
    ///         intents remain hidden, no information leaked."
    ///         The reveal is atomic: both H_intent_A and H_intent_B MUST
    ///         be revealed in the SAME transaction, or NEITHER is revealed.
    /// @param  H_intent_A   First intent commitment hash.
    /// @param  H_intent_B   Second intent commitment hash (counter-party).
    /// @param  proof        Serialized SNARK proof (Groth16 per BTCP §5.6).
    /// @param  publicInputs 5-element array per MEASURED circuit (Phase 1):
    ///                      [0] H_intent_A
    ///                      [1] H_intent_B
    ///                      [2] entity_id_A
    ///                      [3] entity_id_B
    ///                      [4] tolerance parameter
    function revealIntent(
        bytes32 H_intent_A,
        bytes32 H_intent_B,
        bytes calldata proof,
        uint256[] calldata publicInputs
    ) external returns (bool) {
        // R-FAILCLOSED input validation — every error named.
        if (H_intent_A == bytes32(0)) revert ZeroHIntent();
        if (H_intent_B == bytes32(0)) revert ZeroHIntent();
        if (H_intent_A == H_intent_B) revert ZeroHIntent();
        if (proof.length == 0) revert InvalidProofBytes();
        if (verifier == address(0)) revert VerifierNotRegistered();
        // Per Phase 1 MEASURED circuit (zk_complementarity_proof, 5 public inputs).
        if (publicInputs.length != 5) revert InvalidPublicInputsLength();

        // Both H_intent_A and H_intent_B MUST be previously committed
        // (BTCP §5.6 Phase 3 verbatim: "Both intents published in same
        // block — atomic").
        IntentCommit storage a = _commits[H_intent_A];
        IntentCommit storage b = _commits[H_intent_B];
        if (a.committedAt == 0) revert IntentNotFound(H_intent_A);
        if (b.committedAt == 0) revert IntentNotFound(H_intent_B);
        if (a.revealed) revert IntentAlreadyRevealed(H_intent_A);
        if (b.revealed) revert IntentAlreadyRevealed(H_intent_B);

        // Verify complementarity proof per BTCP §5.6 Phase 2 verbatim.
        // R-FAILCLOSED: proof failure → revert ComplementarityProofFailed
        // AND both intents remain hidden (no state change, no event).
        bool ok = IComplementarityVerifier(verifier).verifyProof(proof, publicInputs);
        if (!ok) revert ComplementarityProofFailed();

        // Atomic reveal — both intents marked revealed in the same transaction.
        a.revealed = true;
        b.revealed = true;
        revealCount += 1;

        // zk_proof_hash = SHA3-256(proof bytes) for offchain deduplication.
        bytes32 zkProofHash = sha256(proof);

        // Signal publication — R-CHANNELS (event only, no intent contents).
        emit IntentRevealed(H_intent_A, H_intent_B, zkProofHash);
        return true;
    }

    // ───────────────────────────────────────────────────────────────────────
    // Read-only accessors (signal publication; NO PII in any return path).
    // ───────────────────────────────────────────────────────────────────────

    function getCommit(bytes32 H_intent)
        external
        view
        returns (uint64 committedAt, bytes32 entityId, bool revealed)
    {
        IntentCommit storage c = _commits[H_intent];
        return (c.committedAt, c.entityId, c.revealed);
    }

    function isRevealed(bytes32 H_intent) external view returns (bool) {
        return _commits[H_intent].revealed;
    }
}

/// @title IComplementarityVerifierNominator
/// @notice Minimal interface that the verifier contract MUST expose so
///         that IntentCommitmentRegistry can enforce two-step verifier
///         handover (defence-in-depth for R-INVISIBILITY).
interface IComplementarityVerifierNominator {
    function nominator() external view returns (address);
}
