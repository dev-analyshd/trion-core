// SPDX-License-Identifier: MIT
pragma solidity ^0.8.24;

/// @title ITRIONConsumer — Consumer-side interface for TRION behavioral signals.
/// @notice The minimal read-side interface that any contract consuming TRION
///         behavioral signals should implement. Complementary to
///         ITRIONOracleV3 (which is the producer-side interface implemented
///         by the oracle contract itself).
///
///         The oracle pushes typed signals to consumers via
///         ITRIONOracleV3.publishBehavioralSignal, which then calls the
///         consumer's onTRIONSignal handler. Consumers SHOULD implement
///         this interface so they can be registered as signal recipients
///         and so the type-checker enforces that the handler signature
///         matches what the oracle emits.
///
/// @dev The interface is intentionally minimal — consumers only need to
///      handle one callback. Read-only access to historical signals is
///      via ITRIONOracleV3.getBehavioralSignal / getBehavioralSignalPlanes
///      (which the consumer calls as a caller, not via a callback).
///
///      The `signalTypeId` field carries the 24-type canonical taxonomy
///      (M-073): VALUATION=0, SILENCE=1, MANIPULATION_ALERT=2, GENESIS=3,
///      RESURRECTION=4, FORK_DIVERGENCE=5, TRAJECTORY=6, NEGATIVE_SPACE=7,
///      PHASE_TRANSITION=8, SYSTEMIC_RISK=9, LIQUIDITY_HEALTH=10,
///      GOVERNANCE_SIGNAL=11, CROSS_CHAIN_COHERENCE=12, STABLECOIN_HEALTH=13,
///      MEV_EXPOSURE=14, INSTITUTIONAL_BHV=15, REGULATORY_BHV=16,
///      ECOSYSTEM_HEALTH=17, BOOTSTRAP=18, SOVEREIGN_BEHAVIORAL=19,
///      ENERGY_PARTICIPATION=20, BIOLOGICAL_CAPITAL=21,
///      CONSENSUS_ADAPTATION=22, BTCP_ROUTE=23.
interface ITRIONConsumer {
    /// @notice Callback invoked by the oracle when a new behavioral signal
    ///         is published for an entity this contract is registered to
    ///         consume.
    ///
    /// @param  entityId        The 32-byte entity identifier the signal
    ///                         pertains to (typically keccak256 of the
    ///                         contract address / token symbol).
    /// @param  signalTypeId    The 24-type canonical taxonomy ID (see above).
    /// @param  coherenceScore  Coherence C(t) × 1e6 ∈ [0, 1e6].
    /// @param  threshold       Dynamic threshold Θ(t) × 1e6.
    /// @param  moatFactor      Moat M_moat(t) × 1e6 ∈ [0, 1e6].
    /// @param  limitingPlane   Index of the plane that limited emission:
    ///                         0=Physical, 1=Mental, 2=Spiritual,
    ///                         3=Conscious, 4=ANIMA, 5=Bootstrap.
    /// @param  planesPacked    Five plane scores packed into one uint256
    ///                         (×1e6, 32 bits each):
    ///                         bits[0..32)=phi, [32..64)=mental,
    ///                         [64..96)=sigma, [96..128)=conscious,
    ///                         [128..160)=anima.
    /// @param  timestamp       Unix timestamp (seconds) of signal emission.
    /// @return ack             Consumer MUST return bytes4(keccak256(
    ///                         "onTRIONSignal(bytes32,uint8,uint32,uint32,
    ///                          uint32,uint8,uint256,uint256)")) = 0x... on
    ///                         successful receipt. Any other return value
    ///                         causes the oracle to flag the consumer as
    ///                         unresponsive (AWA anti-centralization
    ///                         condition: signal delivery confirmed).
    function onTRIONSignal(
        bytes32 entityId,
        uint8   signalTypeId,
        uint32  coherenceScore,
        uint32  threshold,
        uint32  moatFactor,
        uint8   limitingPlane,
        uint256 planesPacked,
        uint256 timestamp
    ) external returns (bytes4 ack);

    /// @notice Consumer-declared interest in a specific entity. The oracle
    ///         calls this to register the consumer for callbacks on the
    ///         given entity. Returns true if the consumer accepts the
    ///         subscription.
    /// @dev    This is the consumer-side of the opt-in subscription model:
    ///         the oracle cannot push signals to contracts that have not
    ///         opted in (prevents spam / gas-grief vectors).
    function subscribeToEntity(bytes32 entityId) external returns (bool accepted);

    /// @notice Consumer-declared disinterest. The oracle stops pushing
    ///         callbacks for the given entity.
    function unsubscribeFromEntity(bytes32 entityId) external returns (bool accepted);

    /// @notice Returns true if this consumer is currently subscribed to
    ///         signals for the given entity.
    function isSubscribedTo(bytes32 entityId) external view returns (bool subscribed);

    /// @notice Returns the list of entities this consumer is currently
    ///         subscribed to. Used by the oracle to compute the consumer
    ///         set per-entity for efficient fan-out.
    function subscribedEntities() external view returns (bytes32[] memory entities);
}
