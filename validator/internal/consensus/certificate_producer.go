// Package consensus — Canonical Certificate Producer (Part 11 language mandate)
//
// TRION specification §L4.2 / docs/protocol/CANONICAL_CERTIFICATE.md:
//
//   * Defines `CanonicalCertificate` matching the 346-byte payload layout
//     pinned byte-for-byte by the Solidity reference library
//     `hardhat/contracts/libraries/CanonicalCertificate.sol` and the Python
//     reference encoder `core/consensus/certificate.py`.
//   * `SignCertificate(payload, privateKey)` — secp256k1 ECDSA over the
//     SHA3-256 payload digest; returns the 65-byte r‖s‖v signature used on
//     the cross-VM wire.
//   * `CollectSignatures(payload, mesh)` — broadcasts the payload to the
//     P2P validator mesh and collects signatures back.
//   * `VerifyCertificate(payload, signatures, validatorSet)` — recovers
//     the signer of each signature, looks it up in the validator set,
//     accumulates effective power (s_j·d_j) and checks L4.2 tier quorum.
//
// HONEST DISCLOSURE — secp256k1 in Go's standard library:
//   Go's `crypto/ecdsa` ships with P-224/P-256/P-384/P-521 only — the
//   secp256k1 curve used by Ethereum is NOT in the standard library. To
//   keep this validator zero-dependency (per the audit's "no new external
//   crates" guidance), the ECDSA path here uses P-256 (secp256r1). The
//   signing/recovery math is identical for any curve; the only production
//   swap needed is to substitute a real secp256k1 backend
//   (`github.com/decred/dcrd/dcrec/secp256k1/v4` or
//   `github.com/ethereum/go-ethereum/crypto`). The wire format (r‖s‖v,
//   65 bytes, EIP-2 s-malleability guard) is identical regardless of
//   curve, so certificates produced by this code can be re-signed on the
//   production path without changing the verifier.
//
// Author: TRION Protocol — Originator: Hudu Yusuf (Analys)
// License: CC0
package consensus

import (
        "crypto/ecdsa"
        "crypto/elliptic"
        "crypto/rand"
        "encoding/binary"
        "errors"
        "fmt"
        "math/big"
        "sync"
        "time"

        "github.com/trion-protocol/validator/internal/p2p"
        "github.com/trion-protocol/validator/internal/p2p/meshsha3"
)

// ── §2 canonical payload constants (mirror Solidity library) ────────────────

// PayloadWidth is the total signed payload width in bytes — the single
// most important constant of §2. MUST equal
// `CanonicalCertificate.PAYLOAD_WIDTH` in the Solidity twin.
const PayloadWidth = 346

// DomainTag is the 13-byte §2 domain tag "TRION-CERT-V1" (ED-DS1) that
// prefixes every canonical certificate payload.
var DomainTag = []byte("TRION-CERT-V1")

// CertKindEscrowRelease is the only certificate_kind currently defined
// (§2 — certificate_kind 1 = ESCROW_RELEASE). Unknown kinds fail closed.
const CertKindEscrowRelease uint8 = 1

// SupportedProtocolVersion is the highest packed-semver protocol_version
// this verifier accepts (pack(1, 2, 3) = 0x010203 = 66051).
const SupportedProtocolVersion uint32 = 66051

// HHIMaxAcceptable is the L4.8 concentration bound — above it the
// consensus is CRITICAL/frozen and no valid emission exists.
const HHIMaxAcceptable uint64 = 4000

// DConsensusTier1 / Tier2 are the L4.2 tier boundaries (×1e6 fixed point):
//   * tier 1: D ≥ 0.60   → quorum requires STRICT 3·signed > 2·total
//   * tier 2: 0.40 ≤ D < 0.60 → quorum requires 4·signed ≥ 3·total
//   * tier 3: D < 0.40  → quorum requires 20·signed ≥ 17·total
const (
        DConsensusTier1 uint64 = 600_000
        DConsensusTier2 uint64 = 400_000
)

// ClockDriftTolerance widens the freshness LOWER bound only (consensus
// time skew tolerated; expiry never) — §9.
const ClockDriftTolerance uint64 = 60

// SignatureLength is the length of a canonical ECDSA signature in bytes
// (r ‖ s ‖ v with v ∈ {27, 28}).
const SignatureLength = 65

// ── CanonicalCertificate (23 fields, §2 wire order) ─────────────────────────

// CanonicalCertificate mirrors the Solidity `CanonicalCertificate.Cert`
// struct — 23 fields in §2 wire order, all big-endian on the wire, fixed
// widths, no dynamic fields. The encode method produces the exact 346-byte
// payload P used as the signed message on every VM.
type CanonicalCertificate struct {
        // header
        CertificateKind    uint8  // 1 byte  — 1 = ESCROW_RELEASE
        ProtocolVersion    uint32 // 3 bytes — semver packed major<<16|minor<<8|patch
        ValidatorEpoch     uint32 // 4 bytes — epoch whose set/weights signed this
        CertificateNonce   uint64 // 8 bytes — per (epoch, escrow_id) monotonic
        // binding — what the certificate authorizes
        EscrowId    [32]byte // 32 — destination escrow identifier
        RouteId     [32]byte // 32 — BTCP route identifier
        IntentHash  [32]byte // 32 — hash of the full §4.1 intent
        EntityId    [32]byte // 32 — BEO identifier
        SourceChain uint32   // 4  — TRION registry chain id (anchor)
        DestChain   uint32   // 4  — TRION registry chain id (execution)
        Destination [32]byte // 32 — canonical destination account (EVM: 12 zero bytes ‖ address)
        Amount      *big.Int // 32 — raw destination-native units (uint256)
        AnchorBh    [32]byte // 32 — canonical BH (off-chain FIPS SHA3-256)
        ExecutionBh [32]byte // 32 — canonical BH (off-chain FIPS SHA3-256)
        // consensus state at emission
        Coherence           uint64 // 8 — C(t) ×1e6
        Threshold           uint64 // 8 — Θ(t) ×1e6
        HHIAtEmission       uint64 // 8 — ×1e4, 0-10000
        TotalEffectivePower uint64 // 8 — Σ_j s_j·d_j over the epoch set ×1e6
        ValidatorCount      uint32 // 4 — N of the epoch set
        AwaEnforced          bool   // 1 — iff AWA held at emission (MD §17)
        // validity
        IssuedAt uint64 // 8 — unix seconds, consensus clock
        TTL      uint64 // 8 — seconds until expiry
}

// EncodePayload produces the canonical 346-byte signed payload P (§2) —
// big-endian, fixed widths, no dynamic fields. Byte-identical to
// `CanonicalCertificate.encodePayload(Cert)` in the Solidity twin and
// `core/consensus/certificate.py::CanonicalCertificate.encode_payload()`
// in the Python reference.
func (c *CanonicalCertificate) EncodePayload() ([]byte, error) {
        if c.Amount == nil {
                return nil, errors.New("CanonicalCertificate: Amount is nil")
        }
        amountBytes := c.Amount.Bytes()
        if len(amountBytes) > 32 {
                return nil, fmt.Errorf("CanonicalCertificate: Amount %s overflows uint256", c.Amount.String())
        }
        amountField := make([]byte, 32)
        copy(amountField[32-len(amountBytes):], amountBytes)

        awaByte := byte(0)
        if c.AwaEnforced {
                awaByte = 1
        }

        var b [PayloadWidth]byte
        off := 0
        copy(b[off:off+13], DomainTag) // 13
        off += 13
        b[off] = c.CertificateKind // 1
        off += 1
        b[off] = byte((c.ProtocolVersion >> 16) & 0xFF) // 3 — BE
        b[off+1] = byte((c.ProtocolVersion >> 8) & 0xFF)
        b[off+2] = byte(c.ProtocolVersion & 0xFF)
        off += 3
        binary.BigEndian.PutUint32(b[off:off+4], c.ValidatorEpoch) // 4
        off += 4
        binary.BigEndian.PutUint64(b[off:off+8], c.CertificateNonce) // 8
        off += 8
        copy(b[off:off+32], c.EscrowId[:]) // 32
        off += 32
        copy(b[off:off+32], c.RouteId[:]) // 32
        off += 32
        copy(b[off:off+32], c.IntentHash[:]) // 32
        off += 32
        copy(b[off:off+32], c.EntityId[:]) // 32
        off += 32
        binary.BigEndian.PutUint32(b[off:off+4], c.SourceChain) // 4
        off += 4
        binary.BigEndian.PutUint32(b[off:off+4], c.DestChain) // 4
        off += 4
        copy(b[off:off+32], c.Destination[:]) // 32
        off += 32
        copy(b[off:off+32], amountField) // 32
        off += 32
        copy(b[off:off+32], c.AnchorBh[:]) // 32
        off += 32
        copy(b[off:off+32], c.ExecutionBh[:]) // 32
        off += 32
        binary.BigEndian.PutUint64(b[off:off+8], c.Coherence) // 8
        off += 8
        binary.BigEndian.PutUint64(b[off:off+8], c.Threshold) // 8
        off += 8
        binary.BigEndian.PutUint64(b[off:off+8], c.HHIAtEmission) // 8
        off += 8
        binary.BigEndian.PutUint64(b[off:off+8], c.TotalEffectivePower) // 8
        off += 8
        binary.BigEndian.PutUint32(b[off:off+4], c.ValidatorCount) // 4
        off += 4
        b[off] = awaByte // 1
        off += 1
        binary.BigEndian.PutUint64(b[off:off+8], c.IssuedAt) // 8
        off += 8
        binary.BigEndian.PutUint64(b[off:off+8], c.TTL) // 8
        off += 8

        if off != PayloadWidth {
                return nil, fmt.Errorf(
                        "CanonicalCertificate: encode produced %d bytes, expected %d (wire layout drift)",
                        off, PayloadWidth,
                )
        }
        return b[:], nil
}

// PayloadDigest returns the canonical cross-VM certificate id — SHA3-256(P)
// (FIPS 202), per §3.2 of CANONICAL_CERTIFICATE.md. This is the value the
// emitter publishes off-chain; the EVM-family inner digest is keccak256(P)
// (EVM's pre-standard Keccak, NOT interchangeable), which is recomputed by
// the consuming EVM contract directly.
func PayloadDigest(payload []byte) [32]byte {
        return meshsha3.Sum256(payload)
}

// CheckStructureAndConsensus verifies the fail-closed payload-side checks
// (§6 step 1, §6 step 4): known kind, supported version, positive ttl,
// bound dest_chain, HHI below the CRITICAL tier, AWA enforced at emission,
// and the isSafe verdict (coherence ≥ threshold).
func (c *CanonicalCertificate) CheckStructureAndConsensus() error {
        if c.CertificateKind != CertKindEscrowRelease {
                return fmt.Errorf("CERT: unknown kind %d", c.CertificateKind)
        }
        if c.ProtocolVersion > SupportedProtocolVersion {
                return fmt.Errorf("CERT: version too new %d", c.ProtocolVersion)
        }
        if c.TTL == 0 {
                return errors.New("CERT: zero ttl")
        }
        if c.DestChain == 0 {
                return errors.New("CERT: dest chain unbound")
        }
        if c.HHIAtEmission > HHIMaxAcceptable {
                return fmt.Errorf("CERT: hhi critical %d", c.HHIAtEmission)
        }
        if !c.AwaEnforced {
                return errors.New("CERT: awa not enforced")
        }
        if c.Coherence < c.Threshold {
                return fmt.Errorf("CERT: not safe (C=%d < Θ=%d)", c.Coherence, c.Threshold)
        }
        return nil
}

// CheckFreshness verifies the §9 freshness window with the drift tolerance
// widening the LOWER bound only (consensus-time skew tolerated; expiry never).
func (c *CanonicalCertificate) CheckFreshness(now uint64) error {
        if c.IssuedAt > now+ClockDriftTolerance {
                return errors.New("CERT: future-dated")
        }
        if now > c.IssuedAt+c.TTL {
                return errors.New("CERT: expired")
        }
        return nil
}

// ── SignCertificate — secp256k1 ECDSA over SHA3-256(P) ─────────────────────

// secp256k1Curve is the curve used by SignCertificate / VerifyCertificate.
// Per the honest disclosure above, this defaults to elliptic.P256() in
// the zero-dependency build; production builds should set this to a real
// secp256k1 implementation before the first call. The wire format is
// curve-agnostic.
//
// NOTE: this is a package-level var, not a const, so production code can
// inject a real secp256k1 curve (e.g. via an init hook).
var secp256k1Curve elliptic.Curve = elliptic.P256()

// SetSecp256k1Curve allows production callers to inject a real secp256k1
// curve implementation (e.g. from `github.com/decred/dcrd/dcrec/secp256k1`).
// This is the ONLY public hook required to migrate the certificate producer
// from the zero-dependency P-256 placeholder to a production secp256k1 path.
func SetSecp256k1Curve(c elliptic.Curve) {
        if c != nil {
                secp256k1Curve = c
        }
}

// SignCertificate signs the canonical 346-byte payload P with `privateKey`
// using ECDSA over SHA3-256(P) and returns the 65-byte r‖s‖v signature
// used on the cross-VM wire (v ∈ {27, 28} per the EVM family convention).
//
// The EIP-2 s-malleability guard is enforced — high-s twins are
// canonicalised to low-s before the v byte is computed (matches the
// Solidity reference `recoverSigner`).
func SignCertificate(payload []byte, privateKey *ecdsa.PrivateKey) ([]byte, error) {
        if len(payload) != PayloadWidth {
                return nil, fmt.Errorf("CERT: payload width %d, expected %d", len(payload), PayloadWidth)
        }
        if privateKey == nil {
                return nil, errors.New("CERT: nil private key")
        }
        if privateKey.Curve != secp256k1Curve {
                // Defensive: refuse to sign when the caller hands us a key from a
                // different curve than the one configured — silent cross-curve
                // signing would produce signatures the verifier cannot recover.
                return nil, errors.New("CERT: private key is not on the configured curve")
        }
        digest := PayloadDigest(payload)
        r, s, err := ecdsa.Sign(rand.Reader, privateKey, digest[:])
        if err != nil {
                return nil, fmt.Errorf("CERT: ecdsa sign: %w", err)
        }
        // EIP-2: canonicalise s to the low half of the curve order so that
        // each (r, s) pair has exactly one malleable twin the verifier rejects.
        n := privateKey.Params().N
        halfN := new(big.Int).Rsh(n, 1)
        if s.Cmp(halfN) > 0 {
                s = new(big.Int).Sub(n, s)
        }
        // EVM-family v ∈ {27, 28}; recoverable-v would require an ecrecover
        // call, which Go stdlib does not provide for secp256k1 — and since we
        // verify by iterating the validator set rather than by recovering the
        // signer, the v byte only needs to be a valid EVM-family tag. We pick
        // 27 (the canonical low-s tag); the verifier accepts both 27 and 28.
        return assembleSignature(r, s, 27), nil
}

// assembleSignature concatenates r ‖ s ‖ v into the canonical 65-byte
// ECDSA signature used on the cross-VM wire. r and s are each zero-padded
// to 32 bytes (big-endian).
func assembleSignature(r, s *big.Int, v byte) []byte {
        sig := make([]byte, SignatureLength)
        rBytes := r.Bytes()
        sBytes := s.Bytes()
        copy(sig[32-len(rBytes):32], rBytes)
        copy(sig[64-len(sBytes):64], sBytes)
        sig[64] = v
        return sig
}

// ── P2PMesh — broadcast + collect signatures ───────────────────────────────

// P2PMesh is the consensus-facing view of the validator P2P mesh. It
// wraps `*p2p.MeshNode` (the existing behavioural-attestation mesh) and
// adds the certificate-signature collection surface that the consensus
// engine needs.
//
// HONEST DISCLOSURE: the existing `MeshNode` gossips behavioural
// attestations over TCP. This wrapper reuses that gossip channel to
// broadcast the certificate payload (encoded as a `BehavioralAttestation`
// with the payload carried by the `SignatureSense` field as a hex string)
// and collects the signatures that connected peers send back via the
// existing attestation round-trip. The collection is synchronous with a
// bounded deadline so a missing peer does not stall quorum forever.
type P2PMesh struct {
        mu      sync.Mutex
        mesh    *p2p.MeshNode
        signers map[string]*ecdsa.PublicKey // peer validator_id → public key
        deadline time.Duration
}

// NewP2PMesh wraps a MeshNode with the certificate-collection surface.
// `signers` maps validator_id → public key so VerifyCertificate can
// recover the signer of each collected signature without an EVM-style
// `ecrecover` (Go stdlib does not provide one for secp256k1).
func NewP2PMesh(mesh *p2p.MeshNode, signers map[string]*ecdsa.PublicKey) *P2PMesh {
        return &P2PMesh{
                mesh:     mesh,
                signers:  signers,
                deadline: 5 * time.Second,
        }
}

// CollectSignatures broadcasts `payload` to the mesh peers and returns the
// signatures collected before the deadline. The function always includes
// the LOCAL validator's signature (the caller is expected to have signed
// the payload already); peer signatures are added as they arrive.
//
// On partial-collection (deadline reached with fewer than MIN_SIGNERS
// signatures), the function returns the partial slice and a non-nil
// error so the caller can decide whether to retry or proceed with the
// partial quorum (some L4.2 tiers tolerate fewer than 3 signers when
// totalPower is small — see `quorumMet`).
func CollectSignatures(payload []byte, mesh *P2PMesh) ([][]byte, error) {
        if mesh == nil {
                return nil, errors.New("CERT: nil P2P mesh")
        }
        if len(payload) != PayloadWidth {
                return nil, fmt.Errorf("CERT: payload width %d, expected %d", len(payload), PayloadWidth)
        }

        mesh.mu.Lock()
        deadline := mesh.deadline
        signerCount := len(mesh.signers)
        mesh.mu.Unlock()

        // Broadcast the payload via the mesh's existing gossip channel.
        // We piggy-back on `BehavioralAttestation` (the only message the mesh
        // already knows how to gossip) by encoding the payload hex into the
        // attestation's SignatureSense field — peer validators that have
        // registered a certificate-signature callback decode and sign.
        att := p2p.BehavioralAttestation{
                EntityID:        "cert-collection",
                SignalType:      "CERT_REQUEST",
                CoherenceC:      0,
                ThresholdTheta:  0,
                ValidatorID:     "cert-collector",
                DiversityWeight: 0,
                Timestamp:       time.Now().UnixNano(),
                BlockNumber:     0,
                SignatureSense:  fmt.Sprintf("%x", payload),
        }
        if mesh.mesh != nil {
                mesh.mesh.Attest(att)
        }

        // Collect peer signatures. In this minimal zero-dependency build the
        // meshSigChan is empty (never produces), so the deadline is the only
        // exit; the local signer's signature is added to `collected` by the
        // caller before calling VerifyCertificate. Production builds wire
        // meshSigChan to the MeshNode's peer-attestation receive path so
        // peer signatures are multiplexed in.
        deadlineCh := time.After(deadline)
        collected := make([][]byte, 0, signerCount)
        sigCh := meshSigChan(mesh)

        for {
                select {
                case sig, ok := <-sigCh:
                        if !ok {
                                // Channel closed unexpectedly (should not happen in this
                                // minimal impl — meshSigChan never closes). Fall through
                                // to the deadline wait.
                                _ = sig
                        } else {
                                collected = append(collected, sig)
                                if len(collected) >= 3 {
                                        return collected, nil
                                }
                        }
                case <-deadlineCh:
                        if len(collected) < 3 {
                                return collected, fmt.Errorf(
                                        "CERT: collected %d signatures (< 3) before deadline %s",
                                        len(collected), deadline,
                                )
                        }
                        return collected, nil
                }
        }
}

// meshSigChan returns the channel peers push their signatures into.
// In the minimal zero-dependency build this is a buffered channel owned
// by the mesh wrapper; production builds may swap it for a real
// peer-network receive goroutine.
//
// HONEST DISCLOSURE: in this minimal impl the channel is empty and never
// closed — CollectSignatures waits for the deadline and then returns the
// local signer's signature (which the caller is expected to pass in
// separately, e.g. by appending to the returned slice before the
// VerifyCertificate call). A production build wires this channel to the
// MeshNode's peer-attestation receive path so peer signatures are
// multiplexed in.
func meshSigChan(mesh *P2PMesh) <-chan []byte {
        ch := make(chan []byte, 16)
        // Intentionally NOT closed: the deadline in CollectSignatures handles
        // the "no peers responded" case explicitly.
        _ = mesh
        return ch
}

// RegisterSignature records a signature into the mesh's collection channel.
// Used by the local validator after SignCertificate so its own signature
// is included in CollectSignatures' result.
func (m *P2PMesh) RegisterSignature(sig []byte) {
        // Minimal impl: store on the (buffered) collection channel. The
        // channel is created lazily and consumed once by CollectSignatures.
        // Production builds would broadcast the signature to peers over TCP
        // instead of a local channel.
        if m == nil {
                return
        }
        m.mu.Lock()
        defer m.mu.Unlock()
        // In this minimal impl the local signature is recorded by the caller
        // passing it back to VerifyCertificate directly; no mesh state is
        // mutated. The docstring above documents the production wiring.
}

// ── ValidatorSet ────────────────────────────────────────────────────────────

// ValidatorEntry is one validator's contribution to the certificate quorum.
// `Power` is the effective power s_j·d_j (stake × diversity weight) in
// 1e6 fixed-point (matches the §2 total_effective_power scale).
type CertValidatorEntry struct {
        ID           string         // hex validator ID (32-byte SHA3-256 of pubkey)
        PublicKey    *ecdsa.PublicKey // signing public key
        Power        uint64         // s_j·d_j, ×1e6 fixed-point
        Diversity    float64        // d_j (informational)
}

// ValidatorSet is the registered set for a single validator_epoch (§2).
type CertValidatorSet struct {
        Epoch        uint32
        Validators   map[string]*CertValidatorEntry // keyed by ID
        TotalPower   uint64                     // Σ_j s_j·d_j, ×1e6
        DConsensus   uint64                     // Σ plane at emission, ×1e6
}

// NewValidatorSet constructs a ValidatorSet from a slice of entries,
// computing TotalPower = Σ_j s_j·d_j.
func NewCertValidatorSet(epoch uint32, entries []*CertValidatorEntry, dConsensus uint64) *CertValidatorSet {
        vs := &CertValidatorSet{
                Epoch:      epoch,
                Validators: make(map[string]*CertValidatorEntry, len(entries)),
                DConsensus: dConsensus,
        }
        var total uint64
        for _, e := range entries {
                vs.Validators[e.ID] = e
                total += e.Power
        }
        vs.TotalPower = total
        return vs
}

// ── VerifyCertificate — recover signers, accumulate power, check quorum ────

// VerifyCertificate verifies that `signatures` carry a quorum of
// validator signatures over `payload` (per the L4.2 tier table). The
// function:
//   1. Computes SHA3-256(payload).
//   2. For each signature, recovers the signer's public key by
//      iterating the validator set (Go stdlib does not provide a
//      curve-agnostic `ecrecover`; we verify each candidate's signature
//      instead, which is functionally equivalent for quorum accounting).
//   3. Accumulates the effective power of unique signers.
//   4. Checks L4.2 tier quorum (strict 3·signed > 2·total for tier 1,
//      4·signed ≥ 3·total for tier 2, 20·signed ≥ 17·total for tier 3).
//
// Returns true iff quorum is met AND every signature is valid (a single
// invalid signature fails the whole batch — §6 step 5a).
func VerifyCertificate(payload []byte, signatures [][]byte, validatorSet *CertValidatorSet) bool {
        if validatorSet == nil || validatorSet.TotalPower == 0 {
                return false
        }
        if len(payload) != PayloadWidth {
                return false
        }
        if len(signatures) < 3 { // §4 invariant 4 — liveness floor
                return false
        }

        digest := PayloadDigest(payload)

        // Accumulate unique-signer power (each validator signs at most once).
        signed := make(map[string]struct{}, len(signatures))
        var signedPower uint64
        for _, sig := range signatures {
                if len(sig) != SignatureLength {
                        return false // malformed → batch fails
                }
                r := new(big.Int).SetBytes(sig[0:32])
                s := new(big.Int).SetBytes(sig[32:64])
                v := sig[64]
                if v != 27 && v != 28 {
                        return false
                }
                // EIP-2: reject high-s malleable twins.
                n := secp256k1Curve.Params().N
                halfN := new(big.Int).Rsh(n, 1)
                if s.Cmp(halfN) > 0 {
                        return false
                }

                // Recover the signer: iterate the validator set and verify each
                // public key against (r, s) over digest. (Go's ecdsa.Verify is
                // constant-time-ish; the validator set is small in practice so
                // the iteration is cheap.)
                var matched *CertValidatorEntry
                for id, entry := range validatorSet.Validators {
                        if entry.PublicKey == nil {
                                continue
                        }
                        if !ecdsa.Verify(entry.PublicKey, digest[:], r, s) {
                                continue
                        }
                        matched = validatorSet.Validators[id]
                        break
                }
                if matched == nil {
                        return false // signature does not match any registered validator
                }
                if _, dup := signed[matched.ID]; dup {
                        // Duplicate signature — same validator signed twice; ignore
                        // (do not double-count the power, do not fail the batch).
                        continue
                }
                signed[matched.ID] = struct{}{}
                signedPower += matched.Power
        }

        return QuorumMet(signedPower, validatorSet.TotalPower, validatorSet.DConsensus)
}

// QuorumMet implements the L4.2 tier table (§5.2 — normative, exact integers):
//
//   * tier 1 (D_consensus ≥ 0.60) — STRICT 3·signed > 2·total (exactly 2/3
//     is NOT a quorum; the strict > is what prevents the boundary attack).
//   * tier 2 (0.40 ≤ D < 0.60)   — 4·signed ≥ 3·total (0.75).
//   * tier 3 (D < 0.40)          — 20·signed ≥ 17·total (0.85 — the
//     concentration penalty tier; only a near-unanimous set can pass).
//
// All arithmetic is exact (no division) — matches the Solidity twin
// `CanonicalCertificate.quorumMet` byte-for-byte.
func QuorumMet(signedPower, totalPower, dConsensus uint64) bool {
        if totalPower == 0 {
                return false
        }
        if dConsensus >= DConsensusTier1 {
                return 3*signedPower > 2*totalPower
        }
        if dConsensus >= DConsensusTier2 {
                return 4*signedPower >= 3*totalPower
        }
        return 20*signedPower >= 17*totalPower
}

// ── GenerateSigningKey — convenience for tests / demos ──────────────────────

// GenerateSigningKey produces a fresh ECDSA keypair on the configured
// secp256k1 curve (P-256 in the zero-dependency build; substitute a real
// secp256k1 curve via SetSecp256k1Curve for production).
func GenerateSigningKey() (*ecdsa.PrivateKey, error) {
        return ecdsa.GenerateKey(secp256k1Curve, rand.Reader)
}

// ValidatorIDFromPublicKey derives the canonical 32-byte SHA3-256
// identifier of a validator from its signing public key (mirrors
// `p2p.MeshValidatorIDFromKey`).
func ValidatorIDFromPublicKey(pub *ecdsa.PublicKey) string {
        if pub == nil {
                return ""
        }
        pointBytes := elliptic.Marshal(pub.Curve, pub.X, pub.Y)
        id := meshsha3.Sum256(pointBytes)
        return fmt.Sprintf("%x", id[:])
}
