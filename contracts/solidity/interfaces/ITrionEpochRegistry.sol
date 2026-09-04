// SPDX-License-Identifier: MIT
pragma solidity ^0.8.24;

/// @title ITrionEpochRegistry — the per-epoch canonical validator state
/// @notice Wave 2 (Agent G) — on-chain epoch registry per
///         docs/protocol/CANONICAL_CERTIFICATE.md §10.2 ("validator entries
///         (id, family pubkeys, s_j, d_j), total_effective_power, D_consensus,
///         hhi" + the registered Θ(t)) and §7 (EVM row: "per-epoch
///         validatorId → (addr, w_j), total_power, D_consensus, registered
///         via epoch-boundary tx").
///
///         VERIFIERS (TRIONOracleV3, BTCPEscrow) consult THIS interface for:
///         epoch activity (§6 step 2 — grace-bounded), signer membership and
///         w_j = s_j·d_j weights (§6 step 5), the registered epoch threshold
///         Θ(t) (H-03 threshold provenance), the set totals (§6 step 6
///         cross-check) and D_consensus for the L4.2 tier quorum.
///
///         The registrar (a TRION-controlled relayer role, auditable, one tx
///         per epoch per chain — §7 bridging rule) is the single writer;
///         validator-set changes take effect ONLY at epoch boundaries.
interface ITrionEpochRegistry {
    /// @notice Latest registered epoch (the current pointer). 0 = nothing
    ///         registered yet (epoch 0 is never a valid epoch).
    function latestEpoch() external view returns (uint32);

    /// @notice Verifier epoch grace (§10.2, ED-G — default 2): certificates
    ///         from epochs older than latest − grace are rejected even within
    ///         their ttl (bounds the slashed-validator residual window, R-1).
    function epochGrace() external view returns (uint32);

    /// @notice True iff the epoch has a registered set.
    function epochRegistered(uint32 epoch) external view returns (bool);

    /// @notice True iff `epoch` is registered AND within the verifier grace
    ///         window: latest − epoch ≤ grace. Unknown, future (never
    ///         registered) and stale (beyond grace) epochs are all INACTIVE
    ///         — verification fails closed (§6 step 2).
    function epochActive(uint32 epoch) external view returns (bool);

    /// @notice Effective power w_j = s_j·d_j (×1e6) of `validator` in `epoch`.
    ///         0 = not a member (or zero-weight member).
    function validatorWeight(uint32 epoch, address validator) external view returns (uint256);

    /// @notice Registered stake s_j (×1e6) — the §6 step 5c cross-check value.
    function validatorStake(uint32 epoch, address validator) external view returns (uint256);

    /// @notice Registered diversity d_j (×1e6, 0..1e6) — the §6 step 5c
    ///         cross-check value.
    function validatorDiversity(uint32 epoch, address validator) external view returns (uint256);

    /// @notice Σ_j s_j·d_j over the epoch set (×1e6) — must equal the
    ///         certificate's total_effective_power (§6 step 6).
    function epochTotalPower(uint32 epoch) external view returns (uint256);

    /// @notice N of the epoch set — must equal the certificate's
    ///         validator_count (§6 step 4).
    function epochValidatorCount(uint32 epoch) external view returns (uint256);

    /// @notice D_consensus = mean(d_j) over the epoch set (×1e6) — selects the
    ///         L4.2 quorum tier (§5.2).
    function epochDConsensus(uint32 epoch) external view returns (uint256);

    /// @notice Registered coherence threshold Θ(t) for the epoch (×1e6) —
    ///         H-03: the certificate's `threshold` field must EQUAL this
    ///         value; the bar is never provenance from the caller.
    function epochThreshold(uint32 epoch) external view returns (uint256);

    /// @notice L4.2 quorum check over a signer list against the registered
    ///         epoch weights. Returns (met, signedPower, totalPower, tier).
    ///         tier: 1 (2/3 strict), 2 (0.75), 3 (0.85).
    function epochQuorum(uint32 epoch, address[] calldata signers)
        external
        view
        returns (bool met, uint256 signedPower, uint256 totalPower, uint256 tier);
}
