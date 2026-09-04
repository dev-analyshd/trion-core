// SPDX-License-Identifier: MIT
pragma solidity ^0.8.24;

import "./interfaces/ITrionEpochRegistry.sol";
import "./libraries/CanonicalCertificate.sol";

/// @title TrionEpochRegistry — the per-epoch canonical validator state
/// @notice Wave 2 (Agent G) — the EVM epoch registry of
///         docs/protocol/CANONICAL_CERTIFICATE.md §10.2: at each epoch
///         boundary the registrar publishes the validator set (addresses =
///         family-1 public keys, stake s_j ×1e6, diversity d_j ×1e6), the set
///         totals (total_effective_power, D_consensus, HHI) and the epoch's
///         coherence threshold Θ(t). Validator-set changes (join/leave/slash/
///         rotate) take effect ONLY at epoch boundaries — a retired or slashed
///         validator is simply absent from later epochs, which is what closes
///         the historical-set vulnerability (audit H-01).
///
///         TEMPLATE NOTE for the other VM custodians (H/I/J/K/L): the
///         registry layout per VM is CANONICAL_CERTIFICATE §7 — the EVM
///         identity of a validator is its address (family-1 pubkey); the
///         weights are s_j and d_j stored separately so verifiers can
///         cross-check the ENVELOPE claims (§6 step 5c) exactly; w_j = s_j·d_j
///         is stored precomputed for cheap quorum recomputation.
///
/// @dev TRUST MODEL (documented governance root, mirrors TRIONOracleV3
///      addValidator): the owner administers the registrar role; the registrar
///      is a single TRION-controlled relayer key, auditable, bounded to one
///      epoch per write (sequential registration, R-4: a registrar compromise
///      is bounded to one epoch by the TRION-side epoch-set root). Registration
///      is SEQUENTIAL (epoch == latest + 1) so `latestEpoch` is a single
///      monotonic pointer and stale/future epoch rejection is total-ordering
///      based, never time-based (§10.1: verifiers never compute epochs from
///      time).
contract TrionEpochRegistry is ITrionEpochRegistry {

    address public owner;
    address public registrar;

    /// @notice Latest registered epoch. 0 = nothing registered; the first
    ///         registration is epoch 1 (epoch 0 is never valid).
    uint32 public latestEpoch;

    /// @notice Verifier epoch grace (§10.2, ED-G). Default 2.
    uint32 public epochGrace = 2;

    /// @notice Minimum epoch-set size at registration (liveness floor — the
    ///         MIN_SIGNERS discipline of §4 invariant 4; a 1-validator epoch
    ///         would make the weight quorum trivial).
    uint256 public constant MIN_EPOCH_SET_SIZE = 3;

    struct ValidatorEntry {
        uint256 stake;      // s_j ×1e6 (claim cross-check value, §6 step 5c)
        uint256 diversity;  // d_j ×1e6, 0..1e6 (claim cross-check value)
        uint256 weight;     // w_j = s_j·d_j / 1e6 (quorum power, §5.1)
    }

    struct EpochData {
        uint256 totalPower;    // Σ w_j — == certificate.total_effective_power
        uint256 count;         // N — == certificate.validator_count
        uint256 dConsensus;    // mean(d_j) ×1e6 — selects the L4.2 tier
        uint256 threshold;     // Θ(t) ×1e6 — H-03 provenance
        uint256 hhi;           // registered HHI ×1e4 (audit; must be ≤ 4000)
        bool    registered;
    }

    mapping(uint32 => EpochData) private _epochs;
    mapping(uint32 => mapping(address => ValidatorEntry)) private _validators;

    event EpochRegistered(
        uint32 indexed epoch,
        uint256 validatorCount,
        uint256 totalEffectivePower,
        uint256 dConsensus,
        uint256 threshold,
        uint256 hhi
    );
    event RegistrarUpdated(address indexed previous, address indexed next);
    event EpochGraceUpdated(uint32 grace);

    modifier onlyOwner() { require(msg.sender == owner, "REG: not owner"); _; }
    modifier onlyRegistrar() { require(msg.sender == registrar, "REG: not registrar"); _; }

    constructor() {
        owner = msg.sender;
        registrar = msg.sender; // bootstrap: deployer is the registrar until rotated
    }

    // ── Registrar administration ───────────────────────────────────────────

    /// @notice Rotate the registrar role (owner-gated, auditable).
    function setRegistrar(address newRegistrar) external onlyOwner {
        require(newRegistrar != address(0), "REG: zero registrar");
        emit RegistrarUpdated(registrar, newRegistrar);
        registrar = newRegistrar;
    }

    /// @notice Adjust the verifier grace window (owner-gated; bounded 0..10 —
    ///         large grace windows would defeat epoch rotation).
    function setGrace(uint32 grace) external onlyOwner {
        require(grace <= 10, "REG: grace too wide");
        epochGrace = grace;
        emit EpochGraceUpdated(grace);
    }

    // ── Epoch registration (§10.2 — one tx per epoch boundary) ─────────────

    /// @notice Register the validator set for `epoch` (registrar only).
    ///         MUST be exactly latest + 1 (sequential rotation).
    /// @param validators        Strictly ascending, distinct, non-zero
    ///                          validator addresses (family-1 pubkeys).
    /// @param stakeWeights      s_j ×1e6 per validator (≥ 1).
    /// @param diversityWeights  d_j ×1e6 per validator (≤ 1e6 — d ∈ [0,1]).
    /// @param dConsensus        mean(d_j) ×1e6 of THIS set (tier selector).
    /// @param threshold         Θ(t) ×1e6 registered for this epoch (H-03).
    /// @param hhi               Set HHI ×1e4 — CRITICAL (>4000) sets are
    ///                          rejected: a frozen consensus cannot register
    ///                          an emitting set (§5.3).
    function registerEpoch(
        uint32 epoch,
        address[] calldata validators,
        uint256[] calldata stakeWeights,
        uint256[] calldata diversityWeights,
        uint256 dConsensus,
        uint256 threshold,
        uint256 hhi
    ) external onlyRegistrar {
        require(epoch == latestEpoch + 1, "REG: epoch not sequential");
        uint256 n = validators.length;
        require(n >= MIN_EPOCH_SET_SIZE, "REG: epoch set too small");
        require(stakeWeights.length == n && diversityWeights.length == n, "REG: shape");
        require(dConsensus <= CanonicalCertificate.SCALE_1E6, "REG: d range");
        require(threshold <= CanonicalCertificate.SCALE_1E6, "REG: theta range");
        require(hhi <= CanonicalCertificate.HHI_MAX_ACCEPTABLE, "REG: hhi critical");

        uint256 totalPower;
        address last = address(0);
        for (uint256 i = 0; i < n; i++) {
            address v = validators[i];
            // dup + order in one check: strictly ascending numeric order of
            // the uint160 addresses (caught live by the adversarial test —
            // `last` MUST be updated every iteration or the check degrades
            // to a v > 0 tautology).
            require(v > last, "REG: validators must be ascending & distinct");
            last = v;
            uint256 s = stakeWeights[i];
            uint256 d = diversityWeights[i];
            require(s >= 1 && s <= type(uint64).max, "REG: stake range");
            require(d <= CanonicalCertificate.SCALE_1E6, "REG: diversity range");
            // w_j = s_j·d_j, carried ×1e6 (§5.1) — exact integer division like
            // the py reference EpochSetEntry.effective_power().
            uint256 w = (s * d) / CanonicalCertificate.SCALE_1E6;
            require(w <= type(uint64).max, "REG: weight range");
            _validators[epoch][v] = ValidatorEntry({stake: s, diversity: d, weight: w});
            totalPower += w;
        }
        require(totalPower > 0, "REG: zero total power");
        require(totalPower <= type(uint64).max, "REG: power range"); // cert field is uint64

        _epochs[epoch] = EpochData({
            totalPower: totalPower,
            count: n,
            dConsensus: dConsensus,
            threshold: threshold,
            hhi: hhi,
            registered: true
        });
        latestEpoch = epoch;
        emit EpochRegistered(epoch, n, totalPower, dConsensus, threshold, hhi);
    }

    // ── Views (ITrionEpochRegistry) ────────────────────────────────────────

    function epochRegistered(uint32 epoch) external view returns (bool) {
        return _epochs[epoch].registered;
    }

    function epochActive(uint32 epoch) external view returns (bool) {
        EpochData storage e = _epochs[epoch];
        if (!e.registered) return false;          // unknown / future epoch
        // latest >= epoch always holds for a registered epoch; grace bounds age.
        return (latestEpoch - epoch) <= epochGrace;
    }

    function validatorWeight(uint32 epoch, address validator) external view returns (uint256) {
        return _validators[epoch][validator].weight;
    }

    function validatorStake(uint32 epoch, address validator) external view returns (uint256) {
        return _validators[epoch][validator].stake;
    }

    function validatorDiversity(uint32 epoch, address validator) external view returns (uint256) {
        return _validators[epoch][validator].diversity;
    }

    function epochTotalPower(uint32 epoch) external view returns (uint256) {
        return _epochs[epoch].totalPower;
    }

    function epochValidatorCount(uint32 epoch) external view returns (uint256) {
        return _epochs[epoch].count;
    }

    function epochDConsensus(uint32 epoch) external view returns (uint256) {
        return _epochs[epoch].dConsensus;
    }

    function epochThreshold(uint32 epoch) external view returns (uint256) {
        return _epochs[epoch].threshold;
    }

    /// @notice Registered set HHI (×1e4) — emission-side audit value.
    function epochHHI(uint32 epoch) external view returns (uint256) {
        return _epochs[epoch].hhi;
    }

    function epochQuorum(uint32 epoch, address[] calldata signers)
        external
        view
        returns (bool met, uint256 signedPower, uint256 totalPower, uint256 tier)
    {
        EpochData storage e = _epochs[epoch];
        totalPower = e.totalPower;
        for (uint256 i = 0; i < signers.length; i++) {
            signedPower += _validators[epoch][signers[i]].weight;
        }
        uint256 d = e.dConsensus;
        if (d >= CanonicalCertificate.D_CONSENSUS_TIER1) {
            tier = 1;
            met = 3 * signedPower > 2 * totalPower;
        } else if (d >= CanonicalCertificate.D_CONSENSUS_TIER2) {
            tier = 2;
            met = 4 * signedPower >= 3 * totalPower;
        } else {
            tier = 3;
            met = 20 * signedPower >= 17 * totalPower;
        }
    }
}
