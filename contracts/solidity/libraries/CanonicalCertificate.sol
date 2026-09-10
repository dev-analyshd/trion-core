// SPDX-License-Identifier: MIT
pragma solidity ^0.8.24;

/// @title CanonicalCertificate — the ONE cross-VM TRION consensus certificate
/// @notice Wave 2 (Agent G) — EVM/Solidity reference implementation of the
///         canonical certificate payload defined by
///         `docs/protocol/CANONICAL_CERTIFICATE.md` §2 and pinned byte-for-byte
///         by the Python reference encoder `core/consensus/certificate.py`.
///
///         Every function here is part of the cross-VM TEMPLATE: the other VM
///         custodians (Solana, Move, TON, Cairo, NEAR, PVM) implement the SAME
///         payload, the SAME family-1 digest rule and the SAME L4.2 tier
///         quorum arithmetic, per §3.2 / §5.2 / §6 of the canonical doc.
///
///         Pinned conformance evidence:
///         `tests/contracts/test_canonical_certificate_sol.py` reproduces the
///         346-byte GOLDEN PAYLOAD and the EVM-family inner digest of the
///         golden vector in `tests/unit/test_certificate_domain_separation.py`
///         on a real EVM (eth_tester / py-evm).
///
/// @dev DIGEST POLICY (§3.2, family 1 — deliberate, documented):
///      - The canonical payload P (below) is identical on every VM.
///      - The EVM family inner digest is keccak256(P) and the signed message
///        is its EIP-191 wrap — EXACTLY what this library computes.
///      - The canonical cross-VM certificate id is SHA3-256(P) (FIPS 202),
///        computed OFF-chain by the emitter (the EVM has no FIPS-SHA3
///        precompile and EVM keccak is the pre-standard Keccak — padding
///        0x01, NOT interchangeable). EVM contracts therefore never claim to
///        compute `certificate_hash`; the EVM consumed-key of §7 is
///        keccak256(P), which IS recomputable on-chain (see payloadDigest).
///      - anchorBh / executionBh inside the payload are CANONICAL BH values
///        (FIPS SHA3-256 dual-strand sense, per docs/protocol/CANONICAL_BH.md)
///        computed off-chain. They are opaque bytes32 INPUTS on EVM — never
///        recomputed with keccak (audit H-07; see libraries/HashDNA.sol).
library CanonicalCertificate {
    // ── §2 constants ────────────────────────────────────────────────────────

    /// @notice Total signed payload width — the single most important constant.
    uint256 public constant PAYLOAD_WIDTH = 346;

    /// @notice Minimum distinct signers (§4 invariant 4 — liveness floor; the
    ///         real bar is the L4.2 weight quorum).
    uint256 public constant MIN_SIGNERS = 3;

    /// @notice L4.8 concentration bound (0-10000 HHI scale) — above it the
    ///         consensus is CRITICAL/frozen and no valid emission exists.
    uint256 public constant HHI_MAX_ACCEPTABLE = 4000;

    /// @notice §9 clock drift tolerance — widens the freshness LOWER bound
    ///         only (consensus-time skew tolerated, expiry never).
    uint256 public constant CLOCK_DRIFT_TOLERANCE = 60;

    /// @notice ×1e6 fixed-point scale of the weight/coherence fields.
    uint256 public constant SCALE_1E6 = 1_000_000;

    /// @notice L4.2 D_consensus tier boundaries (×1e6).
    uint256 public constant D_CONSENSUS_TIER1 = 600_000; // ≥ 0.60 → 2/3 (strict >)
    uint256 public constant D_CONSENSUS_TIER2 = 400_000; // ≥ 0.40 → 0.75

    /// @notice Highest protocol_version (packed semver) this verifier accepts
    ///         (§6 step 1: protocol_version ≤ supported max). pack(1,2,3).
    uint24 public constant SUPPORTED_PROTOCOL_VERSION = 66051;

    /// @notice certificate_kind 1 = ESCROW_RELEASE (ED-K1). Unknown kinds fail
    ///         closed.
    uint8 public constant CERT_KIND_ESCROW_RELEASE = 1;

    // ── §2 canonical payload (v1 — 346 bytes) ───────────────────────────────

    /// @notice The 23 canonical certificate fields, in §2 order.
    /// @dev  All integers unsigned big-endian on the wire; fixed-point fields
    ///       carry their scale in the name. anchorBh/executionBh are canonical
    ///       (FIPS SHA3-256) BH values — opaque inputs on EVM (H-07).
    struct Cert {
        // header
        uint8   certificateKind;     // 1 = ESCROW_RELEASE
        uint24  protocolVersion;     // semver packed major<<16|minor<<8|patch
        uint32  validatorEpoch;      // epoch whose set/weights signed this
        uint64  certificateNonce;    // per (epoch, escrow_id) monotonic
        // binding — what the certificate authorizes
        bytes32 escrowId;            // destination escrow identifier
        bytes32 routeId;             // BTCP route identifier
        bytes32 intentHash;          // hash of the full §4.1 intent
        bytes32 entityId;            // BEO identifier
        uint32  sourceChain;         // TRION registry chain id (anchor)
        uint32  destChain;           // TRION registry chain id (execution)
        bytes32 destination;         // canonical destination account (EVM: 12 zero bytes ‖ address)
        uint256 amount;              // raw destination-native units
        bytes32 anchorBh;            // canonical BH (off-chain FIPS SHA3-256)
        bytes32 executionBh;         // canonical BH (off-chain FIPS SHA3-256)
        // consensus state at emission
        uint64  coherence;           // C(t) ×1e6
        uint64  threshold;           // Θ(t) ×1e6 — must equal registry Θ(t) (H-03)
        uint64  hhiAtEmission;       // ×1e4, 0-10000
        uint64  totalEffectivePower; // Σ_j s_j·d_j over the epoch set ×1e6
        uint32  validatorCount;      // N of the epoch set
        bool    awaEnforced;         // 1 iff AWA held at emission (MD §17)
        // validity
        uint64  issuedAt;            // unix seconds, consensus clock
        uint64  ttl;                 // seconds until expiry
    }

    /// @notice The canonical signing payload P (§2) — 346 bytes, big-endian,
    ///         fixed widths, no dynamic fields. MUST equal
    ///         core/consensus/certificate.py CanonicalCertificate.encode_payload()
    ///         byte-for-byte (pinned by the golden-vector test).
    function encodePayload(Cert memory cert) internal pure returns (bytes memory) {
        return abi.encodePacked(
            "TRION-CERT-V1",              // 13  domain_tag (ED-DS1)
            cert.certificateKind,          // 1   uint8
            cert.protocolVersion,          // 3   uint24
            cert.validatorEpoch,           // 4   uint32
            cert.certificateNonce,         // 8   uint64
            cert.escrowId,                 // 32
            cert.routeId,                  // 32
            cert.intentHash,               // 32
            cert.entityId,                 // 32
            cert.sourceChain,              // 4   uint32
            cert.destChain,               // 4   uint32
            cert.destination,              // 32
            cert.amount,                   // 32  uint256
            cert.anchorBh,                 // 32
            cert.executionBh,              // 32
            cert.coherence,                // 8   uint64 ×1e6
            cert.threshold,                // 8   uint64 ×1e6
            cert.hhiAtEmission,            // 8   uint64 ×1e4
            cert.totalEffectivePower,      // 8   uint64 ×1e6
            cert.validatorCount,           // 4   uint32
            cert.awaEnforced,              // 1   bool → 0/1
            cert.issuedAt,                 // 8   uint64
            cert.ttl                       // 8   uint64
        );
        // 13+1+3+4+8+32*7+4+4+32+32+32+8*4+4+1+8+8 = 346
    }

    /// @notice EVM family inner digest: keccak256(P) (§3.2 — intentional and
    ///         documented; this is NOT the FIPS-SHA3 certificate_hash, which
    ///         is computed off-chain by the emitter).
    function payloadDigest(Cert memory cert) internal pure returns (bytes32) {
        return keccak256(encodePayload(cert));
    }

    /// @notice FAMILY 1 signed message: EIP-191 wrap of the inner digest —
    ///         keccak256("\x19Ethereum Signed Message:\n32" ‖ keccak256(P)).
    ///         Validators sign THIS value with secp256k1 (65-byte r‖s‖v).
    function ethSignedDigest(Cert memory cert) internal pure returns (bytes32) {
        return keccak256(
            abi.encodePacked("\x19Ethereum Signed Message:\n32", payloadDigest(cert))
        );
    }

    /// @notice EVM-family canonical destination encoding (§7): the 20-byte
    ///         address left-padded to 32 bytes (12 zero bytes ‖ address) —
    ///         the same encoding as the Python reference
    ///         (destination=bytes(12) ‖ address).
    function destinationToBytes32(address dest) internal pure returns (bytes32) {
        return bytes32(uint256(uint160(dest)));
    }

    // ── §2 strict payload decode (the wire format IS the 346-byte P) ───────

    /// @notice The 13-byte domain tag as an integer: "TRION-CERT-V1".
    uint256 private constant DOMAIN_TAG_INT = 0x5452494f4e2d434552542d5631;

    /// @notice Strict decode of the canonical 346-byte payload P into a Cert
    ///         (the Solidity twin of the py reference `decode_payload`):
    ///         exact width, exact domain tag, fixed field order. Verifiers
    ///         that receive the certificate as raw bytes (the cross-VM wire
    ///         format of §7 — e.g. TRIONOracleV3.submitCertificateAttestation)
    ///         never trust an ABI-decoded struct: they decode P itself, so a
    ///         mismatched field layout fails closed at step 1.
    function decode(bytes calldata payload) internal pure returns (Cert memory cert) {
        require(payload.length == PAYLOAD_WIDTH, "CERT: bad width");
        require(_load(payload, 0, 13) == DOMAIN_TAG_INT, "CERT: bad domain tag");
        cert.certificateKind     = uint8(_load(payload, 13, 1));
        cert.protocolVersion     = uint24(_load(payload, 14, 3));
        cert.validatorEpoch      = uint32(_load(payload, 17, 4));
        cert.certificateNonce    = uint64(_load(payload, 21, 8));
        cert.escrowId            = bytes32(_load(payload, 29, 32));
        cert.routeId             = bytes32(_load(payload, 61, 32));
        cert.intentHash          = bytes32(_load(payload, 93, 32));
        cert.entityId            = bytes32(_load(payload, 125, 32));
        cert.sourceChain         = uint32(_load(payload, 157, 4));
        cert.destChain           = uint32(_load(payload, 161, 4));
        cert.destination         = bytes32(_load(payload, 165, 32));
        cert.amount              = _load(payload, 197, 32);
        cert.anchorBh            = bytes32(_load(payload, 229, 32));
        cert.executionBh         = bytes32(_load(payload, 261, 32));
        cert.coherence           = uint64(_load(payload, 293, 8));
        cert.threshold           = uint64(_load(payload, 301, 8));
        cert.hhiAtEmission       = uint64(_load(payload, 309, 8));
        cert.totalEffectivePower = uint64(_load(payload, 317, 8));
        cert.validatorCount      = uint32(_load(payload, 325, 4));
        cert.awaEnforced         = _load(payload, 329, 1) == 1;
        cert.issuedAt            = uint64(_load(payload, 330, 8));
        cert.ttl                 = uint64(_load(payload, 338, 8));
    }

    /// @dev Big-endian scalar read of `width` bytes at `offset` — calldataload
    ///      returns a 32-byte BE word, so shifting right by (256 − 8·width)
    ///      leaves exactly the field. memory-safe (reads only).
    function _load(bytes calldata payload, uint256 offset, uint256 width)
        private
        pure
        returns (uint256 v)
    {
        assembly ("memory-safe") {
            v := shr(sub(256, mul(width, 8)), calldataload(add(payload.offset, offset)))
        }
    }

    // ── §6 byte-level verification primitives (raw payload P) ───────────────
    // The hot verification path (TRIONOracleV3.submitCertificateAttestation,
    // BTCPEscrow.releaseEscrowCanonical) consumes the certificate as the raw
    // 346-byte P and NEVER materializes a Cert struct: every field is read
    // straight from calldata (short-lived stack values only — this is what
    // keeps the via-ir stack layout within budget on solc 0.8.24).

    /// @notice §6 steps 1, 3 and 4 on the RAW payload: exact width, exact
    ///         domain tag, known kind, supported version, non-zero nonce,
    ///         bound dest_chain, HHI below the CRITICAL tier, AWA enforced,
    ///         the isSafe verdict (coherence ≥ threshold), non-zero ttl and
    ///         the §9 freshness window (drift widens the LOWER bound only).
    ///         Byte-level twin of checkStructureAndConsensus() +
    ///         checkFreshness() — both paths are adversarially pinned by the
    ///         tests (probe struct path, oracle/escrow byte path).
    function checkPayload(bytes calldata payload, uint256 now) internal pure {
        require(payload.length == PAYLOAD_WIDTH, "CERT: bad width");
        require(_load(payload, 0, 13) == DOMAIN_TAG_INT, "CERT: bad domain tag");
        require(_load(payload, 13, 1) == CERT_KIND_ESCROW_RELEASE, "CERT: unknown kind");
        require(_load(payload, 14, 3) <= SUPPORTED_PROTOCOL_VERSION, "CERT: version too new");
        require(_load(payload, 21, 8) > 0, "CERT: zero nonce");
        require(_load(payload, 161, 4) != 0, "CERT: dest chain unbound");
        require(_load(payload, 309, 8) <= HHI_MAX_ACCEPTABLE, "CERT: hhi critical");
        require(_load(payload, 329, 1) == 1, "CERT: awa not enforced");
        require(_load(payload, 293, 8) >= _load(payload, 301, 8), "CERT: not safe");
        require(_load(payload, 338, 8) > 0, "CERT: zero ttl");
        // §6 step 3 — freshness (§9.1: issued_at ≤ now ≤ issued_at + ttl with
        // the drift tolerance on the lower bound ONLY).
        require(_load(payload, 330, 8) <= now + CLOCK_DRIFT_TOLERANCE, "CERT: future-dated");
        require(now <= _load(payload, 330, 8) + _load(payload, 338, 8), "CERT: expired");
    }

    /// @notice keccak256(P) computed on the raw payload — identical to
    ///         payloadDigest(Cert) by construction (P IS the payload bytes).
    function payloadDigestOf(bytes calldata payload) internal pure returns (bytes32) {
        return keccak256(payload);
    }

    /// @notice FAMILY 1 signed message over the raw payload: the EIP-191 wrap
    ///         of keccak256(P) — identical to ethSignedDigest(Cert). NOTE the
    ///         double hash: the EIP-191 prefix wraps the 32-byte INNER digest
    ///         keccak256(P), never the raw 346-byte P (§3.2 family 1).
    function ethSignedDigestOf(bytes calldata payload) internal pure returns (bytes32) {
        return keccak256(abi.encodePacked("\x19Ethereum Signed Message:\n32", keccak256(payload)));
    }

    /// @notice Domain tag of the escrow-deployment binding: keccak256(
    ///         "TRION-ESCROW-BOUND-V1"). The escrow VALUE path folds the
    ///         payload digest with the consuming deployment's address under
    ///         this tag — one quorum certificate authorizes ONE escrow.
    bytes32 private constant ESCROW_BINDING_DOMAIN =
        0x7d2abb7b662e58696a052610824542b32fbde263c9b6ca3af2b9ec1d9e64be1f;

    /// @notice SEC-21 (P-EVM-01 amplifier): the ESCROW-RELEASE family 1
    ///         signed message — the EIP-191 wrap of
    ///         keccak256(ESCROW_BINDING_DOMAIN ‖ escrowDeployment ‖
    ///         keccak256(P)). The quorum's signatures bind to exactly ONE
    ///         escrow deployment: the same 346-byte P replayed at a second
    ///         deployment (a same-chain clone, or a redeployed upgrade)
    ///         recovers non-signer addresses and fails §6 step 5. The
    ///         oracle's ethSignedDigestOf (observability path, no value
    ///         movement) stays deployment-agnostic — only the value path
    ///         binds.
    function escrowBoundEthDigestOf(bytes calldata payload, address escrowDeployment)
        internal
        pure
        returns (bytes32)
    {
        return keccak256(
            abi.encodePacked(
                "\x19Ethereum Signed Message:\n32",
                keccak256(
                    abi.encodePacked(ESCROW_BINDING_DOMAIN, escrowDeployment, keccak256(payload))
                )
            )
        );
    }

    /// @notice validator_epoch (§2 offset 17) — the §6 step 2 registry key.
    function epochOf(bytes calldata payload) internal pure returns (uint32) {
        return uint32(_load(payload, 17, 4));
    }

    /// @notice certificate_nonce (§2 offset 21).
    function nonceOf(bytes calldata payload) internal pure returns (uint64) {
        return uint64(_load(payload, 21, 8));
    }

    /// @notice escrow_id (§2 offset 29) — the binding key.
    function escrowIdOf(bytes calldata payload) internal pure returns (bytes32) {
        return bytes32(_load(payload, 29, 32));
    }

    /// @notice route_id (§2 offset 61).
    function routeIdOf(bytes calldata payload) internal pure returns (bytes32) {
        return bytes32(_load(payload, 61, 32));
    }

    /// @notice entity_id (§2 offset 125).
    function entityIdOf(bytes calldata payload) internal pure returns (bytes32) {
        return bytes32(_load(payload, 125, 32));
    }

    /// @notice dest_chain (§2 offset 161) — the chain this certificate
    ///         settles on. A deployment must reject certificates whose
    ///         dest_chain is not its own chain id (P-EVM-01: cross-chain
    ///         certificate confusion — same quorum cert settling escrows on
    ///         a foreign deployment).
    function destChainOf(bytes calldata payload) internal pure returns (uint32) {
        return uint32(_load(payload, 161, 4));
    }

    /// @notice destination (§2 offset 165) — settlement-tuple half A.
    function destinationOf(bytes calldata payload) internal pure returns (bytes32) {
        return bytes32(_load(payload, 165, 32));
    }

    /// @notice amount (§2 offset 197) — settlement-tuple half B.
    function amountOf(bytes calldata payload) internal pure returns (uint256) {
        return _load(payload, 197, 32);
    }

    /// @notice coherence (§2 offset 293, ×1e6).
    function coherenceOf(bytes calldata payload) internal pure returns (uint64) {
        return uint64(_load(payload, 293, 8));
    }

    /// @notice threshold (§2 offset 301, ×1e6) — must equal registry Θ(t) (H-03).
    function thresholdOf(bytes calldata payload) internal pure returns (uint64) {
        return uint64(_load(payload, 301, 8));
    }

    /// @notice total_effective_power (§2 offset 317, ×1e6) — §6 step 6 cross-check.
    function totalPowerOf(bytes calldata payload) internal pure returns (uint64) {
        return uint64(_load(payload, 317, 8));
    }

    /// @notice validator_count (§2 offset 325) — §6 step 4 cross-check.
    function validatorCountOf(bytes calldata payload) internal pure returns (uint32) {
        return uint32(_load(payload, 325, 4));
    }

    // ── §5.2 quorum (L4.2 tier table — normative, exact integers) ───────────

    /// @notice L4.2 tier quorum over REGISTERED weights (never envelope
    ///         claims): tier 1 (D ≥ 0.60) requires STRICT 3·signed > 2·total
    ///         (exactly-2/3 is NOT a quorum); tier 2 (0.40 ≤ D < 0.60)
    ///         requires 4·signed ≥ 3·total; tier 3 (D < 0.40) requires
    ///         20·signed ≥ 17·total. All arithmetic exact (no division).
    function quorumMet(
        uint256 signedPower,
        uint256 totalPower,
        uint256 dConsensus
    ) internal pure returns (bool) {
        if (totalPower == 0) return false;
        if (dConsensus >= D_CONSENSUS_TIER1) return 3 * signedPower > 2 * totalPower;
        if (dConsensus >= D_CONSENSUS_TIER2) return 4 * signedPower >= 3 * totalPower;
        return 20 * signedPower >= 17 * totalPower;
    }

    // ── §6 step 1 / step 4 — structure + consensus preconditions ───────────

    /// @notice Fail-closed payload-side checks: known kind, supported version,
    ///         positive ttl, bound dest_chain, HHI below the CRITICAL tier,
    ///         AWA enforced at emission, and the isSafe verdict
    ///         (coherence ≥ threshold). Registry/clock checks are the
    ///         caller's job (steps 2-3, 5-6).
    function checkStructureAndConsensus(Cert memory cert) internal pure {
        require(cert.certificateKind == CERT_KIND_ESCROW_RELEASE, "CERT: unknown kind");
        require(cert.protocolVersion <= SUPPORTED_PROTOCOL_VERSION, "CERT: version too new");
        require(cert.ttl > 0, "CERT: zero ttl");
        require(cert.destChain != 0, "CERT: dest chain unbound");
        require(cert.hhiAtEmission <= HHI_MAX_ACCEPTABLE, "CERT: hhi critical");
        require(cert.awaEnforced, "CERT: awa not enforced");
        require(cert.coherence >= cert.threshold, "CERT: not safe");
    }

    // ── §6 step 3 / §9 — freshness ──────────────────────────────────────────

    /// @notice issued_at ≤ now ≤ issued_at + ttl, with the drift tolerance
    ///         (60 s) widening the LOWER bound only: a slightly future-dated
    ///         certificate from consensus-time skew is tolerated; an expired
    ///         one never is.
    function checkFreshness(Cert memory cert, uint256 now) internal pure {
        require(cert.issuedAt <= now + CLOCK_DRIFT_TOLERANCE, "CERT: future-dated");
        require(now <= cert.issuedAt + cert.ttl, "CERT: expired");
    }

    // ── §6 step 5a — signature recovery (V3 batch discipline) ──────────────

    /// @notice Minimal EIP-191 ECDSA recovery with the EIP-2 s-malleability
    ///         guard — the same discipline as TRIONOracleV3's inlined ECDSA.
    ///         Returns address(0) on any malformed signature (the caller
    ///         fails the whole batch — one bad signature rejects the
    ///         certificate, §6 step 5a).
    function recoverSigner(bytes32 ethHash, bytes memory signature)
        internal
        pure
        returns (address)
    {
        if (signature.length != 65) return address(0);
        bytes32 r;
        bytes32 s;
        uint8 v;
        assembly {
            r := mload(add(signature, 0x20))
            s := mload(add(signature, 0x40))
            v := byte(0, mload(add(signature, 0x60)))
        }
        if (uint256(s) > 0x7FFFFFFFFFFFFFFFFFFFFFFFFFFFFFFF5D576E7357A4501DDFE92F46681B20A0) {
            return address(0); // EIP-2: reject high-s malleable twins
        }
        if (v != 27 && v != 28) return address(0);
        return ecrecover(ethHash, v, r, s);
    }
}
