// SPDX-License-Identifier: MIT
pragma solidity ^0.8.20;


// ── Minimal ECDSA (inlined — replaces @openzeppelin ECDSA dependency) ────────
// EIP-2 compliant: rejects s > secp256k1n/2 and v not in {27, 28}.
library ECDSA {
    function recover(bytes32 hash, bytes memory signature) internal pure returns (address) {
        if (signature.length != 65) return address(0);
        bytes32 r; bytes32 s; uint8 v;
        assembly {
            r := mload(add(signature, 0x20))
            s := mload(add(signature, 0x40))
            v := byte(0, mload(add(signature, 0x60)))
        }
        if (uint256(s) > 0x7FFFFFFFFFFFFFFFFFFFFFFFFFFFFFFF5D576E7357A4501DDFE92F46681B20A0) {
            return address(0); // EIP-2: reject high-s
        }
        if (v != 27 && v != 28) return address(0);
        return ecrecover(hash, v, r, s);
    }
}


// ── Minimal MessageHashUtils (inlined — replaces OZ dependency) ─────────────
library MessageHashUtils {
    function toEthSignedMessageHash(bytes32 hash) internal pure returns (bytes32) {
        return keccak256(abi.encodePacked("\x19Ethereum Signed Message:\n32", hash));
    }
}


// ── Minimal Ownable (inlined — replaces OZ dependency) ──────────────────────
abstract contract Ownable {
    address private _owner;
    event OwnershipTransferred(address indexed previousOwner, address indexed newOwner);
    constructor() { _transferOwnership(msg.sender); }
    modifier onlyOwner() { require(msg.sender == owner(), "Ownable: caller is not the owner"); _; }
    function owner() public view returns (address) { return _owner; }
    function transferOwnership(address newOwner) public virtual onlyOwner {
        require(newOwner != address(0), "Ownable: new owner is the zero address");
        _transferOwnership(newOwner);
    }
    function _transferOwnership(address newOwner) internal virtual {
        address oldOwner = _owner;
        _owner = newOwner;
        emit OwnershipTransferred(oldOwner, newOwner);
    }
}

import "./interfaces/ITRIONOracleV3.sol";
import "./interfaces/ITrionEpochRegistry.sol";
import "./libraries/CanonicalCertificate.sol";

contract TRIONOracleV3 is ITRIONOracleV3, Ownable {
    using ECDSA for bytes32;

    // Signal struct inherited from ITRIONOracleV3

    // BehavioralSignal struct inherited from ITRIONOracleV3

    mapping(bytes32 => BehavioralSignal) public behavioralSignals;
    mapping(bytes32 => uint256) public signalCountByEntity;
    uint256 public totalBehavioralSignals;

    mapping(bytes32 => Signal) public signals;
    mapping(address => bool) public isValidator;
    uint256 public quorumRequired = 2;

    /// @notice Number of registered validators (deployer included).
    /// @dev Feeds minRouteAttestations() — the route-verdict quorum is a
    ///      function of the LIVE validator set, not a static config value.
    uint256 public validatorCount;

    /// @notice Emitted when the owner registers a new validator (set is
    ///         owner-administered — every change is on-chain auditable).
    event ValidatorRegistered(address indexed validator, uint256 validatorCount);

    // ── VALIDATOR EPOCH REGISTRY (Wave 2, audit H-01) ────────────────────────
    // The per-epoch canonical validator state (docs/protocol/
    // CANONICAL_CERTIFICATE.md §10.2): at each epoch boundary the TRION
    // registrar publishes the validator set (addresses, s_j, d_j weights,
    // totals, D_consensus, Θ(t)) to TrionEpochRegistry, and THIS oracle
    // consults it for every canonical-certificate verification: epoch
    // activity (grace-bounded), signer membership, weight quorum, threshold
    // provenance (H-03) and set-total cross-checks. Unbound (address 0) =
    // legacy-only mode — the canonical entrypoint fails closed until the
    // registry is bound.
    ITrionEpochRegistry public epochRegistry;

    event EpochRegistryBound(address indexed registry);

    /// @notice Bind/rotate the epoch registry (owner-gated, auditable).
    ///         Unbinding is impossible (zero address rejected).
    function setEpochRegistry(address registry) external onlyOwner {
        require(registry != address(0), "TRION: zero registry");
        epochRegistry = ITrionEpochRegistry(registry);
        emit EpochRegistryBound(registry);
    }

    // BTCPRoute struct inherited from ITRIONOracleV3

    mapping(bytes32 => BTCPRoute) public btcpRoutes;
    // BTCPRoutePublished event inherited from ITRIONOracleV3

    /// @notice Emitted when a full behavioral signal is published on-chain.
    // BehavioralSignalPublished event inherited from ITRIONOracleV3

    /// @notice Emitted when SILENCE is formally recorded (C(t) < Θ(t)).
    // SilenceRecorded event inherited from ITRIONOracleV3

    /// @notice Emitted when SILENCE is formally recorded — V2 with the full
    ///         structured-null payload (coherence gap + eta). Both V1 and V2
    ///         are emitted on silence (V1 topic0 kept stable for existing
    ///         indexers).
    // SilenceRecordedV2 event inherited from ITRIONOracleV3

    constructor() {
        isValidator[msg.sender] = true;
        validatorCount = 1; // deployer is the bootstrap validator (relayer)
    }

    /// @notice Freshness window for BTCP route safety verdicts (seconds).
    ///         Matches the legacy 300s signal freshness bound.
    uint256 public constant BTCP_ROUTE_FRESHNESS_SECONDS = 300;

    // ── BTCP route quorum attestations (S3/C2 fix: signature-verified) ────────
    // SECURITY (whitepaper: "TRION consensus is the only oracle") — S3/C2 fix:
    // a route verdict must be backed by ECDSA SIGNATURES from a supermajority
    // of the registered validator set, the same discipline publishSignal()
    // already enforces for thermodynamic signals.
    //
    // Previously ANY single validator (or the owner) could call
    // publishBTCPRoute() and mark any route safe: the attestation accounting
    // was keyed on msg.sender, so two owner-controlled EOAs constituted a
    // "quorum" and no signature was ever verified. publishBTCPRoute() is now
    // a METADATA-ONLY etch (it no longer records attestations — see its
    // natspec); attestations are recorded exclusively by
    // submitRouteAttestation(), which recovers each attestor from an EIP-191
    // signature over the route verdict hash. The aggregate batch may be
    // submitted by ANYONE — authority lives in the signatures, not in
    // msg.sender, so the relayer identity is irrelevant to consensus.
    //
    // Quorum to finalize a verdict: N = max(2, ⌈2/3 · validatorCount⌉)
    // DISTINCT registered validators (mirrors the AWA quorum rule in
    // TRIONExecutionGate.sol: (count*2 + 2) / 3 — i.e. ⌈2n/3⌉ — floored at 2).
    // Route values are etched by the first attestation and immutable
    // thereafter: a batch carrying mismatched values reverts (dispute — the
    // route simply never reaches quorum, fail-closed). A route only becomes
    // releasable once at least N distinct validators have signed.
    mapping(bytes32 => mapping(address => bool)) public routeAttested;
    mapping(bytes32 => uint256) public routeAttestationCount;
    mapping(bytes32 => bool) private _routeQuorumEmitted;

    /// @notice Emitted for each NEW distinct validator attestation on a route.
    event RouteAttestationSubmitted(
        bytes32 indexed routeId,
        address indexed validator,
        uint256 attestationCount
    );

    /// @notice Emitted once, when a route verdict first reaches signature quorum.
    event RouteVerdictFinalized(
        bytes32 indexed routeId,
        uint256 attestationCount,
        uint256 requiredQuorum,
        bool isSafe
    );

    /// @notice Minimum distinct signature-verified validators required to
    ///         finalize a route verdict: max(2, ⌈2/3 · validatorCount⌉).
    /// @dev Examples: 1→2, 2→2, 3→2, 4→3, 5→4, 6→4, 7→5, 9→6, 12→8.
    ///      The floor of 2 means a single key can never finalize a verdict,
    ///      regardless of validator-set size.
    function minRouteAttestations() public view returns (uint256) {
        uint256 required = (validatorCount * 2 + 2) / 3; // ⌈2n/3⌉
        return required < 2 ? 2 : required;
    }

    /// @notice True iff a verdict exists for `routeId` AND is backed by at
    ///         least minRouteAttestations() distinct signature-verified
    ///         validators (routeVerdictFinalized == the releasable state).
    function routeVerdictFinalized(bytes32 routeId) external view returns (bool) {
        return btcpRoutes[routeId].timestamp != 0 &&
               routeAttestationCount[routeId] >= minRouteAttestations();
    }

    /// @notice The route-verdict digest validators sign: keccak256 over
    ///         (chainid, this contract, routeId, anchorBH, executionBH,
    ///         coherenceScore, thresholdScore), EIP-191 wrapped by the signer.
    /// @dev Same binding discipline as publishSignal(): replay across chains
    ///      and across oracle deployments is impossible because chainid and
    ///      address(this) are inside the digest.
    function routeVerdictHash(
        bytes32 routeId,
        bytes32 anchorBH,
        bytes32 executionBH,
        uint256 coherenceScore,
        uint256 thresholdScore
    ) public view returns (bytes32) {
        return keccak256(
            abi.encodePacked(
                block.chainid,
                address(this),
                routeId,
                anchorBH,
                executionBH,
                coherenceScore,
                thresholdScore
            )
        );
    }

    // ── Publish/attest BTCP Route signal ──────────────────────────────────────
    /// @notice Etch BTCP route metadata (anchor/execution linkage, coherence,
    ///         threshold). Legacy entrypoint — DEPRECATED as a verdict path.
    /// @dev    Called by relayers/validators BEFORE the escrow release attempt
    ///         to pre-register route data. SECURITY (S3/C2 fix): this function
    ///         NO LONGER records attestations or pushes a route toward quorum
    ///         — a caller here (even the owner or a registered validator,
    ///         twice, from two keys) can never make a verdict releasable.
    ///         Releasability comes exclusively from the signature-verified
    ///         attestation quorum in submitRouteAttestation() below. Values
    ///         written here stay immutable and must be matched exactly by any
    ///         subsequent attestation batch (a mismatch is a dispute and
    ///         reverts, fail-closed). Composability: etch-then-attest with
    ///         identical values is the intended pre-registration flow.
    function publishBTCPRoute(
        bytes32 routeId,
        bytes32 anchorBH,
        bytes32 executionBH,
        uint256 coherenceScore,
        uint256 thresholdScore
    ) external {
        require(
            msg.sender == owner() || isValidator[msg.sender],
            "TRION: not authorized"
        );

        BTCPRoute storage route = btcpRoutes[routeId];
        if (route.timestamp == 0) {
            // First write — values become immutable for this routeId.
            route.anchorBH    = anchorBH;
            route.executionBH = executionBH;
            route.coherence   = coherenceScore;
            route.threshold   = thresholdScore;
            route.isSafe      = coherenceScore >= thresholdScore;
            route.timestamp   = block.timestamp;
        } else {
            require(
                route.anchorBH == anchorBH &&
                route.executionBH == executionBH &&
                route.coherence == coherenceScore &&
                route.threshold == thresholdScore,
                "TRION: route values mismatch - disputed"
            );
        }

        emit BTCPRoutePublished(routeId, coherenceScore >= thresholdScore);
    }

    // ── Aggregated signature-verified route attestations (S3/C2 fix) ─────────
    /// @notice Submit a batch of validator attestations for a route verdict.
    ///         Each attestor is RECOVERED from an EIP-191 signature over
    ///         routeVerdictHash(...) — msg.sender carries no authority here.
    /// @param routeId         Route being attested (must match the escrow's).
    /// @param anchorBH        Escrow id the verdict is bound to (H1: an
    ///                        unrelated escrow's fresh verdict cannot release
    ///                        this route's escrow and vice versa).
    /// @param executionBH     Execution behavioral hash linkage.
    /// @param coherenceScore  Verdict coherence (×1e6).
    /// @param thresholdScore  Verdict threshold (×1e6); isSafe = coherence ≥ threshold.
    /// @param signatures      65-byte (r,s,v) signatures, SORTED ascending by
    ///                        recovered signer address (distinct within the
    ///                        batch — same discipline as publishSignal()).
    ///                        Signers who already attested this route in an
    ///                        earlier batch are accepted but not re-counted.
    /// @dev Reverts on: empty batch, undecodable/non-validator signer,
    ///      unsorted or duplicate signers, values conflicting with the etched
    ///      route (dispute). Emits RouteAttestationSubmitted per NEW distinct
    ///      attestor and RouteVerdictFinalized once when the count first
    ///      reaches minRouteAttestations(). Freshness (M2): only NEW distinct
    ///      attestors refresh btcpRoutes[routeId].timestamp.
    function submitRouteAttestation(
        bytes32 routeId,
        bytes32 anchorBH,
        bytes32 executionBH,
        uint256 coherenceScore,
        uint256 thresholdScore,
        bytes[] calldata signatures
    ) external {
        require(signatures.length > 0, "TRION: empty attestation batch");

        bytes32 ethSignedHash = MessageHashUtils.toEthSignedMessageHash(
            routeVerdictHash(routeId, anchorBH, executionBH, coherenceScore, thresholdScore)
        );

        // Pass 1 — recover and validate every attestor up front (fail-closed:
        // a single bad signature invalidates the whole batch).
        address[] memory signers = new address[](signatures.length);
        address lastSigner = address(0);
        for (uint256 i = 0; i < signatures.length; i++) {
            address signer = ethSignedHash.recover(signatures[i]);
            require(signer != address(0), "TRION: invalid attestation signature");
            require(isValidator[signer], "TRION: attester not validator");
            require(signer > lastSigner, "TRION: signer ordering required");
            lastSigner = signer;
            signers[i] = signer;
        }

        // Etch-or-match the route values. This runs even when the batch adds
        // no NEW attestor: a signature over conflicting values for the same
        // routeId is a dispute and must fail closed.
        BTCPRoute storage route = btcpRoutes[routeId];
        if (route.timestamp == 0) {
            // First attestation — values become immutable for this routeId.
            route.anchorBH    = anchorBH;
            route.executionBH = executionBH;
            route.coherence   = coherenceScore;
            route.threshold   = thresholdScore;
            route.isSafe      = coherenceScore >= thresholdScore;
            route.timestamp   = block.timestamp;
        } else {
            require(
                route.anchorBH == anchorBH &&
                route.executionBH == executionBH &&
                route.coherence == coherenceScore &&
                route.threshold == thresholdScore,
                "TRION: route values mismatch - disputed"
            );
        }

        // Pass 2 — count NEW distinct attestors (idempotent across batches).
        uint256 newAttestations = 0;
        for (uint256 i = 0; i < signers.length; i++) {
            if (!routeAttested[routeId][signers[i]]) {
                routeAttested[routeId][signers[i]] = true;
                routeAttestationCount[routeId]++;
                newAttestations++;
                emit RouteAttestationSubmitted(routeId, signers[i], routeAttestationCount[routeId]);
            }
        }

        if (newAttestations > 0) {
            // SECURITY (M2 fix): freshness is refreshed ONLY by a NEW distinct
            // attestor — re-submitting an overlapping batch cannot keep a
            // stale verdict alive.
            if (route.timestamp < block.timestamp) {
                route.timestamp = block.timestamp;
            }

            // One-time finalization event when the signature quorum is first met.
            uint256 required = minRouteAttestations();
            if (routeAttestationCount[routeId] >= required && !_routeQuorumEmitted[routeId]) {
                _routeQuorumEmitted[routeId] = true;
                emit RouteVerdictFinalized(
                    routeId,
                    routeAttestationCount[routeId],
                    required,
                    route.isSafe
                );
            }
            emit BTCPRoutePublished(routeId, route.isSafe);
        }
    }

    // ── Route binding view (H1 fix support) ────────────────────────────────────
    /// @notice Flat, Vyper-friendly view of a route verdict INCLUDING the
    ///         binding fields escrows need. Escrows settle only via a route
    ///         whose anchorBH equals the escrowId — a quorum-safe verdict
    ///         for an UNRELATED route/escrow can then never release funds
    ///         (the route-spoof attack).
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
        )
    {
        BTCPRoute memory r = btcpRoutes[routeId];
        return (
            r.anchorBH,
            routeAttestationCount[routeId],
            r.isSafe,
            r.coherence,
            r.threshold,
            r.timestamp
        );
    }

    // ══ CANONICAL CERTIFICATE ATTESTATION (Wave 2, H-01/H-03/H-04/M-04) ═════
    // The V4 entrypoint of docs/protocol/CANONICAL_CERTIFICATE.md §11: the
    // validator batch discipline of submitRouteAttestation() (sorted distinct
    // signers, one bad signature fails the batch) applied to the full
    // canonical 346-byte payload P — same P on every VM, EVM-family digest
    // EIP-191(keccak256(P)) (§3.2 family 1). Authority lives in the
    // signatures; msg.sender (the relayer) carries none.
    //
    // CANONICAL-PATTERN DECISION (template for the other VM custodians): this
    // entrypoint is the OBSERVABILITY/INDEX surface — it runs the full §6
    // verification (structure → epoch → freshness → consensus preconditions →
    // signatures+claims → weight quorum → nonce ordering) and records the
    // verdict, but consumers (BTCPEscrow.releaseEscrowCanonical) re-verify
    // the certificate THEMSELVES against the epoch registry at the point of
    // value movement. The oracle store is never a trust dependency — that is
    // what structurally closes the weak-oracle-fallback class (M-05).

    /// @notice The latest canonical certificate accepted per escrow id.
    struct CanonicalVerdict {
        bytes32 routeId;
        bytes32 destination;     // canonical (left-padded address on EVM)
        uint256 amount;
        uint256 coherence;       // ×1e6
        uint256 threshold;       // ×1e6 — == registry Θ(t) (H-03)
        uint32  validatorEpoch;
        uint64  certificateNonce;
        uint256 timestamp;       // block.timestamp at acceptance
        bytes32 payloadDigest;   // keccak256(P) — the EVM consumed-key (§7)
        uint256 signedPower;     // Σ registered w_j over verified signers
        uint256 totalPower;      // registry Σ w_j of the epoch set
        bool    recorded;
    }

    mapping(bytes32 => CanonicalVerdict) public canonicalAttestations;          // escrowId → latest
    mapping(uint32 => mapping(bytes32 => uint64)) public canonicalHighestNonce; // (epoch, escrow) → highest accepted nonce
    mapping(uint32 => mapping(bytes32 => bytes32)) private _canonicalDigestAtNonce; // idempotency key
    mapping(uint32 => mapping(bytes32 => bytes32)) private _canonicalConflictDigest; // second conflicting digest (evidence)

    /// @notice A canonical certificate was accepted and recorded (observability).
    event CertificateAttested(
        bytes32 indexed escrowId,
        bytes32 indexed routeId,
        uint32  indexed validatorEpoch,
        uint64  certificateNonce,
        uint256 signedPower,
        uint256 totalPower,
        uint256 timestamp
    );

    /// @notice Same (epoch, escrow, nonce) with a DIFFERENT payload digest —
    ///         on-chain equivocation evidence (§8.2) feeding L4.9 S1 slashing
    ///         (both conflicting certificate digests are self-authenticating
    ///         off-chain via their quorums of signatures). The conflicting
    ///         certificate itself is REJECTED (not recorded); the evidence
    ///         persists in state + events.
    event CertificateEquivocation(
        bytes32 indexed escrowId,
        uint32  indexed validatorEpoch,
        uint64  certificateNonce,
        bytes32 digestA,
        bytes32 digestB
    );

    /// @notice True once an equivocation conflict was recorded for
    ///         (epoch, escrow) — the slashing-evidence flag.
    mapping(uint32 => mapping(bytes32 => bool)) public certificateConflictRecorded;

    /// @notice Submit a canonical-certificate attestation batch (permissionless
    ///         — authority is in the validator signatures).
    /// @param payload          The canonical 346-byte certificate payload P
    ///                         (§2 — the cross-VM wire format). Strictly
    ///                         decoded field-by-field straight from calldata:
    ///                         exact width, exact domain tag, fixed field
    ///                         order (a mismatched layout fails closed at
    ///                         §6 step 1). escrowId is the BINDING key;
    ///                         anchorBh/executionBh are canonical BH values
    ///                         (FIPS SHA3-256, computed OFF-chain per
    ///                         CANONICAL_BH.md — H-07: opaque inputs, never
    ///                         recomputed with keccak).
    /// @param envelopeWeights The CANONICAL ENVELOPE (§4) weight CLAIMS,
    ///                        interleaved ×1e6: [s_0, d_0, s_1, d_1, ...]
    ///                        index-aligned with the signature batch — must
    ///                        equal the registered epoch values exactly
    ///                        (§6 step 5c; self-reported weights are never
    ///                        authority — the Go-mesh C-06 class).
    /// @param signatures      Concatenated 65-byte (r,s,v) EIP-191 signatures
    ///                        over keccak256(P), SORTED ascending by recovered
    ///                        signer address, distinct within the batch
    ///                        (length must be an exact multiple of 65).
    /// @dev Runs the §6 sequence fail-closed. Registry must be bound. Idempotent
    ///      resubmission of the same certificate (same nonce AND same digest)
    ///      is a silent no-op (§8.2 observability). A CONFLICT (same nonce,
    ///      different digest) is rejected — the verdict is NOT updated — but
    ///      the equivocation evidence is recorded and the call returns
    ///      normally so the evidence (event + state) persists.
    function submitCertificateAttestation(
        bytes calldata payload,
        uint256[] calldata envelopeWeights,
        bytes calldata signatures
    ) external {
        // §6 step 1 — STRUCTURE (fail-closed; registry bound is a hard
        // precondition). certificate_nonce starts at 1: the consumed-nonce
        // pointer initializes to 0, so nonce 0 could otherwise masquerade as
        // an "idempotent resubmission" of the never-submitted nonce slot.
        // Envelope shape: exactly 2 weight claims per 65-byte signature.
        require(address(epochRegistry) != address(0), "TRION: epoch registry unbound");
        require(signatures.length % 65 == 0, "TRION: signature width");
        uint256 batch = signatures.length / 65;
        require(batch >= CanonicalCertificate.MIN_SIGNERS, "TRION: below min signers");
        require(envelopeWeights.length == 2 * batch, "TRION: envelope shape mismatch");
        CanonicalCertificate.checkPayload(payload, block.timestamp);

        // §6 steps 2, 4, 6-pre — EPOCH + registry conformance (H-01/H-03)
        uint32 epoch = CanonicalCertificate.epochOf(payload);
        // P-EVM-01 defense-in-depth: this oracle indexes certificates for
        // THIS chain only — foreign-dest-chain certificates are rejected at
        // the observability surface too (escrows re-verify independently).
        require(
            uint256(CanonicalCertificate.destChainOf(payload)) == block.chainid,
            "TRION: dest chain not this chain"
        );
        _checkEpochAndRegistry(epoch, payload);

        // §6 steps 5-6 — SIGNATURES + weight quorum (H-04)
        bytes32 ethDigest = CanonicalCertificate.ethSignedDigestOf(payload);
        uint256 signedPower = _verifyCertificateSignatures(
            ethDigest, epoch, signatures, envelopeWeights
        );
        uint256 totalPower = _requireCanonicalQuorum(epoch, signedPower);

        // §6 step 8 — nonce ordering, conflict evidence, record (M-04)
        _recordCanonicalVerdict(payload, signedPower, totalPower);
    }

    /// @dev §6 steps 2, 4 and 6-pre: epoch activity (registered + within
    ///      verifier grace; unknown, future and retired epochs all fail
    ///      closed — H-01), registry conformance (the certificate may not
    ///      lie about the set: validator_count and total_effective_power must
    ///      equal the registered values) and H-03 threshold provenance (Θ(t)
    ///      is registry state, never a certificate claim).
    function _checkEpochAndRegistry(uint32 epoch, bytes calldata payload)
        internal
        view
    {
        require(epochRegistry.epochActive(epoch), "TRION: validator epoch inactive");
        require(
            CanonicalCertificate.validatorCountOf(payload) == epochRegistry.epochValidatorCount(epoch),
            "TRION: validator count mismatch"
        );
        require(
            CanonicalCertificate.totalPowerOf(payload) == epochRegistry.epochTotalPower(epoch),
            "TRION: total power mismatch"
        );
        require(
            CanonicalCertificate.thresholdOf(payload) == epochRegistry.epochThreshold(epoch),
            "TRION: threshold not from registry"
        );
    }

    /// @dev §6 step 6 — QUORUM: the L4.2 tier check over REGISTERED weights
    ///      (H-04). Returns the epoch total power (the §6 step 6 cross-check
    ///      value: the certificate's total_effective_power was already
    ///      required to equal it in _checkEpochAndRegistry).
    function _requireCanonicalQuorum(uint32 epoch, uint256 signedPower)
        internal
        view
        returns (uint256 totalPower)
    {
        totalPower = epochRegistry.epochTotalPower(epoch);
        require(
            CanonicalCertificate.quorumMet(signedPower, totalPower, epochRegistry.epochDConsensus(epoch)),
            "TRION: weight quorum unmet"
        );
    }

    /// @dev §6 step 5 — batch fail-closed signature verification: recover each
    ///      signer (one bad signature rejects the whole certificate), enforce
    ///      the sorted-distinct batch discipline, epoch-set membership (step
    ///      5b) and the envelope weight-claim cross-check (step 5c — the
    ///      self-reported-weights hole of audit C-06). Returns the signed
    ///      power recomputed from REGISTERED weights (§5.1), never from the
    ///      envelope.
    function _verifyCertificateSignatures(
        bytes32 ethDigest,
        uint32 epoch,
        bytes calldata signatures,
        uint256[] calldata envelopeWeights
    ) internal view returns (uint256 signedPower) {
        // Pass 1 — recover and order every signer.
        address[] memory signers = _recoverCertificateSigners(ethDigest, signatures);
        // Pass 2 — membership + envelope weight claims + registered power
        // (claims are interleaved [s_j, d_j] — one entry pair per signature).
        for (uint256 i = 0; i < signers.length; i++) {
            signedPower += _checkSignerAndWeight(
                epoch, signers[i], envelopeWeights[2 * i], envelopeWeights[2 * i + 1]
            );
        }
    }

    /// @dev §6 step 5a — recover and order the signers; reverts on any bad
    ///      signature, unsorted or duplicate signer. Returns the recovered
    ///      addresses (index-aligned with the 65-byte signature stride).
    function _recoverCertificateSigners(bytes32 ethDigest, bytes calldata signatures)
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
            require(signer != address(0), "TRION: bad certificate signature");
            require(signer > lastSigner, "TRION: signer ordering required");
            lastSigner = signer;
            signers[i] = signer;
        }
    }

    /// @dev §6 step 5b/5c per signer: epoch-set membership (weight > 0) and
    ///      the exact envelope weight-claim cross-check. Returns the
    ///      REGISTERED w_j (the only power that is ever summed — §5.1).
    function _checkSignerAndWeight(
        uint32 epoch,
        address signer,
        uint256 stakeClaim,
        uint256 diversityClaim
    ) internal view returns (uint256 weight) {
        weight = epochRegistry.validatorWeight(epoch, signer);
        require(weight > 0, "TRION: signer not in epoch set");
        require(
            stakeClaim == epochRegistry.validatorStake(epoch, signer) &&
            diversityClaim == epochRegistry.validatorDiversity(epoch, signer),
            "TRION: envelope weight claim mismatch"
        );
    }

    /// @dev §6 step 8 — nonce ordering, conflict evidence (M-04) and verdict
    ///      recording. Fields are read one-by-one from calldata (no Cert
    ///      struct is materialized on the verification path).
    ///      CANONICAL-PATTERN NOTE: a conflicting certificate (same epoch +
    ///      escrow + nonce, different payload) is REJECTED — nothing of it is
    ///      recorded — but the CONFLICT itself is recorded and the evidence
    ///      event is emitted WITHOUT reverting, because EVM revert semantics
    ///      discard logs: evidence must persist. A conflict report requires a
    ///      fresh validator signature quorum over a different payload for the
    ///      same (epoch, escrow, nonce) — i.e. real equivocation, which is
    ///      itself the L4.9 S1 slashing evidence against those validators.
    function _recordCanonicalVerdict(
        bytes calldata payload,
        uint256 signedPower,
        uint256 totalPower
    ) internal {
        bytes32 digest = CanonicalCertificate.payloadDigestOf(payload);
        uint32 epoch = CanonicalCertificate.epochOf(payload);
        bytes32 escrowId = CanonicalCertificate.escrowIdOf(payload);
        uint64 nonce = CanonicalCertificate.nonceOf(payload);
        uint64 highest = canonicalHighestNonce[epoch][escrowId];
        if (nonce == highest) {
            if (digest == _canonicalDigestAtNonce[epoch][escrowId]) {
                return; // idempotent resubmission — observability only (§8.2)
            }
            if (!certificateConflictRecorded[epoch][escrowId]) {
                certificateConflictRecorded[epoch][escrowId] = true;
                _canonicalConflictDigest[epoch][escrowId] = digest;
                emit CertificateEquivocation(
                    escrowId, epoch, nonce,
                    _canonicalDigestAtNonce[epoch][escrowId], digest
                );
            }
            return; // the conflicting certificate is rejected (not recorded)
        }
        require(nonce > highest, "TRION: stale certificate nonce");

        // Record (overwrite the escrow's latest accepted verdict).
        CanonicalVerdict storage v = canonicalAttestations[escrowId];
        v.routeId          = CanonicalCertificate.routeIdOf(payload);
        v.destination      = CanonicalCertificate.destinationOf(payload);
        v.amount           = CanonicalCertificate.amountOf(payload);
        v.coherence        = CanonicalCertificate.coherenceOf(payload);
        v.threshold        = CanonicalCertificate.thresholdOf(payload);
        v.validatorEpoch   = epoch;
        v.certificateNonce = nonce;
        v.timestamp        = block.timestamp;
        v.payloadDigest    = digest;
        v.signedPower      = signedPower;
        v.totalPower       = totalPower;
        v.recorded         = true;
        canonicalHighestNonce[epoch][escrowId] = nonce;
        _canonicalDigestAtNonce[epoch][escrowId] = digest;
        emit CertificateAttested(
            escrowId, v.routeId, epoch, nonce, signedPower, totalPower, block.timestamp
        );
    }

    /// @notice Flat view of the escrow's latest accepted canonical verdict
    ///         (observability/index surface — consumers re-verify against the
    ///         registry; this view is never verification authority).
    function canonicalBinding(bytes32 escrowId)
        external
        view
        returns (
            bool    recorded,
            bytes32 routeId,
            bytes32 destination,
            uint256 amount,
            uint256 coherence,
            uint256 threshold,
            uint32  validatorEpoch,
            uint64  certificateNonce,
            uint256 timestamp,
            bytes32 payloadDigest
        )
    {
        CanonicalVerdict storage v = canonicalAttestations[escrowId];
        return (
            v.recorded, v.routeId, v.destination, v.amount, v.coherence,
            v.threshold, v.validatorEpoch, v.certificateNonce, v.timestamp,
            v.payloadDigest
        );
    }

    /// @notice Slashing-evidence accessor: the two conflicting digests for an
    ///         (epoch, escrow) equivocation, if any (§8.2 / L4.9 S1).
    function certificateConflict(uint32 epoch, bytes32 escrowId)
        external
        view
        returns (bool recorded, bytes32 digestA, bytes32 digestB)
    {
        return (
            certificateConflictRecorded[epoch][escrowId],
            _canonicalDigestAtNonce[epoch][escrowId],
            _canonicalConflictDigest[epoch][escrowId]
        );
    }

    // ── Publish rich behavioral signal (V3 enhancement) ─────────────────────
    /// @notice Publish a full behavioral signal with entity context and plane data.
    /// @dev Only callable by owner or authorized validator.
    function publishBehavioralSignal(BehavioralSignal calldata s) external {
        require(
            msg.sender == owner() || isValidator[msg.sender],
            "TRION: not authorized"
        );
        require(s.limitingPlane <= 4, "TRION: invalid plane index");

        BehavioralSignal memory sig = s;
        sig.timingPacked = (uint256(uint64(block.number)) << 64) | uint256(uint64(block.timestamp));
        sig.initialized  = true;

        behavioralSignals[s.entityId] = sig;

        signalCountByEntity[s.entityId]++;
        totalBehavioralSignals++;

        uint64 blk = uint64(sig.timingPacked >> 64);
        emit BehavioralSignalPublished(
            sig.entityId, sig.publicCommitment, sig.coherenceScore, sig.threshold,
            sig.moatFactor, sig.coherent, sig.limitingPlane, sig.planesPacked,
            blk, uint64(sig.timingPacked)
        );

        // Also emit SilenceRecorded when not coherent
        if (!sig.coherent) {
            uint256 gap = sig.threshold > sig.coherenceScore ? sig.threshold - sig.coherenceScore : 0;
            emit SilenceRecorded(sig.entityId, sig.coherenceScore, sig.threshold, sig.limitingPlane, gap, blk);
            // SECURITY FIX (P1, verification matrix #20): SILENCE emission must
            // carry coherence_gap AND eta. eta_blocks = int(gap × 1000) per
            // core/master/coherence.py, with the on-chain gap in ×1e6 fixed
            // point → etaBlocks = gap / 1000. V2 event adds the eta field while
            // V1 keeps its original topic0 for backward compatibility.
            uint256 etaBlocks = gap / 1000;
            emit SilenceRecordedV2(sig.entityId, sig.coherenceScore, sig.threshold, sig.limitingPlane, gap, etaBlocks, blk);
        }
    }

    /// @notice Unpack a plane score from planesPacked. planeIndex 0=phi 1=mental 2=sigma 3=conscious 4=anima.
    function unpackPlane(uint256 planesPacked, uint8 planeIndex) external pure returns (uint64) {
        return uint64(planesPacked >> (uint256(planeIndex) * 32));
    }

    /// @notice Pack five plane scores (×1e6) into one uint256.
    function packPlanes(uint64 phi, uint64 mental, uint64 sigma, uint64 conscious, uint64 anima)
        external pure returns (uint256)
    {
        return uint256(uint32(phi))
            | (uint256(uint32(mental)) << 32)
            | (uint256(uint32(sigma)) << 64)
            | (uint256(uint32(conscious)) << 96)
            | (uint256(uint32(anima)) << 128);
    }

    /// @notice Get the core behavioral signal fields for an entity.
    function getBehavioralSignal(bytes32 entityId)
        external view
        returns (
            bytes32 publicCommitment,
            uint256 coherenceScore,
            uint256 threshold,
            uint256 moatFactor,
            bool coherent,
            uint8 limitingPlane,
            bool initialized
        )
    {
        BehavioralSignal memory s = behavioralSignals[entityId];
        return (
            s.publicCommitment, s.coherenceScore, s.threshold, s.moatFactor,
            s.coherent, s.limitingPlane, s.initialized
        );
    }

    /// @notice Get the five-plane breakdown (unpacked) + block/timestamp.
    function getBehavioralSignalPlanes(bytes32 entityId)
        external view
        returns (
            uint64 phiPlane,
            uint64 mentalPlane,
            uint64 sigmaPlane,
            uint64 consciousPlane,
            uint64 animaPlane,
            uint64 signalBlock,
            uint64 signalTimestamp
        )
    {
        uint256 p = behavioralSignals[entityId].planesPacked;
        uint256 t = behavioralSignals[entityId].timingPacked;
        return (
            uint64(uint32(p)),
            uint64(uint32(p >> 32)),
            uint64(uint32(p >> 64)),
            uint64(uint32(p >> 96)),
            uint64(uint32(p >> 128)),
            uint64(t >> 64),
            uint64(t)
        );
    }

    // ── Legacy publishSignal ─────────────────────────────────────────────────
    function publishSignal(bytes32 txId, uint256 packedData, bytes[] calldata signatures) external {
        require(!signals[txId].initialized, "TRION: Signal already etched");
        // M-01 (audit): the legacy thermodynamic quorum is DERIVED from the
        // live validator set — max(static quorumRequired, max(2, ⌈2/3·validatorCount⌉))
        // — so the DD "owner lowers quorum to 2" class can no longer drop the
        // bar below the live-set supermajority. setQuorum() may only TIGHTEN.
        uint256 required = minRouteAttestations();
        if (quorumRequired > required) {
            required = quorumRequired;
        }
        require(signatures.length >= required, "TRION: Insufficient quorum");

        bytes32 messageHash = MessageHashUtils.toEthSignedMessageHash(keccak256(abi.encodePacked(block.chainid, address(this), txId, packedData)));
        
        address lastSigner = address(0);
        for (uint256 i = 0; i < signatures.length; i++) {
            address signer = messageHash.recover(signatures[i]);
            require(isValidator[signer], "TRION: Invalid validator");
            require(signer > lastSigner, "TRION: Signer ordering required");
            lastSigner = signer;
        }

        signals[txId] = Signal(packedData, true);
        
        uint8 status = uint8(packedData & 0xFF);
        uint32 coherence = uint32((packedData >> 8) & 0xFFFFFFFF);
        uint32 threshold = uint32((packedData >> 40) & 0xFFFFFFFF);
        uint64 blockNum = uint64((packedData >> 72) & 0xFFFFFFFFFFFFFFFF);

        emit ThermodynamicSignalEtched(txId, status, coherence, threshold);
        if (status == 1) emit EntropyNominal(txId, coherence, threshold, blockNum);
        if (status != 1) emit ThermodynamicCollapseIntercepted(txId, msg.sender, coherence, threshold, packedData);
    }

    // ── verifyExecution — checks BTCP routes first, then legacy signals ──────
    // Fix 1: BTCP routes are checked before legacy signals. This ensures that
    // publishBTCPRoute() → verifyExecution() returns isSafe = true and the
    // escrow releases via TRION consensus rather than falling back to timeout.
    function verifyExecution(bytes32 txId)
        external view returns (bool isSafe, uint32 coherence, uint32 threshold)
    {
        // Check BTCP route registry first.
        // SECURITY: BTCP routes are subject to the same freshness window as
        // legacy signals — a stale "safe" verdict must not be replayable
        // forever (previously routes never expired).
        // SECURITY: a route verdict additionally requires
        // routeAttestationCount >= quorumRequired distinct attestations —
        // a single-attested route is NOT verifiable (fail-closed).
        BTCPRoute memory r = btcpRoutes[txId];
        if (r.timestamp > 0) {
            bool routeFresh = (block.timestamp - r.timestamp) < BTCP_ROUTE_FRESHNESS_SECONDS;
            // S3/C2: releasable iff the verdict is backed by the dynamic
            // signature quorum (≥ minRouteAttestations() distinct ECDSA-
            // verified validators), not the static quorumRequired setting.
            bool routeQuorum = routeAttestationCount[txId] >= minRouteAttestations();
            return (
                r.isSafe && routeFresh && routeQuorum,
                uint32(r.coherence > type(uint32).max ? type(uint32).max : r.coherence),
                uint32(r.threshold > type(uint32).max ? type(uint32).max : r.threshold)
            );
        }

        // Fallback: check legacy signal storage
        Signal memory s = signals[txId];
        if (!s.initialized) {
            return (false, 0, 0);
        }

        uint8 sigStatus = uint8(s.packedData & 0xFF);
        uint32 c = uint32((s.packedData >> 8) & 0xFFFFFFFF);
        uint32 t = uint32((s.packedData >> 40) & 0xFFFFFFFF);
        uint64 blockNum = uint64((s.packedData >> 72) & 0xFFFFFFFFFFFFFFFF);
        uint64 timestamp = uint64((s.packedData >> 136) & 0xFFFFFFFFFFFFFFFF);

        bool safe    = (sigStatus == 1);
        bool recent  = (block.timestamp - timestamp < 300);
        bool bounded = (block.number - blockNum < 50);

        return (safe && recent && bounded, c, t);
    }

    function getSignalInfo(bytes32 txId) external view returns (uint8, uint32, uint32, uint64, uint64) {
        uint256 p = signals[txId].packedData;
        return (uint8(p & 0xFF), uint32((p >> 8) & 0xFFFFFFFF), uint32((p >> 40) & 0xFFFFFFFF), uint64((p >> 72) & 0xFFFFFFFFFFFFFFFF), uint64((p >> 136) & 0xFFFFFFFFFFFFFFFF));
    }

    /// @notice Register a validator. Owner-gated (validator-set changes are
    ///         an auditable owner action — a ValidatorRegistered event is
    ///         emitted for every change).
    /// @dev GOVERNANCE TRUST ASSUMPTION (documented, not enforced on-chain):
    ///      the owner can add validators and therefore influence quorum
    ///      composition. Mitigations: (1) the route quorum
    ///      minRouteAttestations() = max(2, ⌈2/3·validatorCount⌉) grows with
    ///      the set, and attestations are ECDSA-verified, so the owner must
    ///      control ⌈2/3⌉ of a growing set to forge a verdict — the audited
    ///      "two owner EOAs = quorum" failure mode is closed because quorum
    ///      power no longer derives from msg.sender; (2) route values are
    ///      etched by the FIRST attestation and disputes fail closed;
    ///      (3) the honest long-term path per the whitepaper is a validator
    ///      set with on-chain stake-and-slash (see docs: trust model). A
    ///      malicious owner controlling a supermajority of keys remains a
    ///      governance trust root until then.
    function addValidator(address _v) external onlyOwner {
        // PHASE-1-SECURITY: prevent registering the zero address as a validator.
        require(_v != address(0), "TRION: zero address");
        // Keep validatorCount honest: re-registering an existing validator is
        // rejected instead of silently inflating the count (which would lower
        // nobody's quorum but corrupt the ⌈2/3·count⌉ accounting).
        require(!isValidator[_v], "TRION: already validator");
        isValidator[_v] = true;
        validatorCount++;
        emit ValidatorRegistered(_v, validatorCount);
    }
    function setQuorum(uint256 _q) external onlyOwner {
        // PHASE-1-SECURITY: enforce a hard minimum quorum of 2 — a single
        // attestor must never be able to mark a route safe (the original
        // audit finding). Quorum 1 would let the owner self-attest and
        // release via one signature; 2 keeps the consensus bar meaningful.
        require(_q >= 2, "TRION: quorum < 2");
        quorumRequired = _q;
        // M-01 (audit): the static setting is a TIGHTEN-ONLY ceiling now —
        // publishSignal() floors its requirement at minRouteAttestations()
        // (max(2, ⌈2/3·validatorCount⌉)), so a low static quorum can never
        // drop the effective bar below the live-set supermajority.
    }
}
