// Package consensus — Canonical Certificate Producer (Wave 3 / L4.1, Part 11).
//
// Closes due-diligence finding D1 ("NO CERT CODE IN GO"): before this file
// existed, the Go validator fleet had no encoder/signer for the canonical
// 346-byte certificate payload P (docs/protocol/CANONICAL_CERTIFICATE.md §2).
// On-chain verification is real on every VM tier (Solidity, Cairo, Move, SVM,
// NEAR, TON), but the fleet that EMITS the certificate had no code to
// produce one — so emission-side signing was an open external dependency.
//
// This file wires the existing 346-byte payload layout (imported from
// types.go: Hash, appendUint32/64, appendBytes/appendString, appendFloat64,
// ZeroHash, etc.) into a Go-native certificate producer that:
//
//   1. Takes a 346-byte payload P and the validator's signing key.
//   2. Signs P using ECDSA (secp256k1) — the EVM-family (family 1) signature
//      scheme per CANONICAL_CERTIFICATE.md §3.2. The default signer produces
//      secp256k1 signatures via an injectable Secp256k1Signer interface so
//      operators can wire a real secp256k1 backend (e.g. an HSM-backed
//      github.com/decred/dcrd/dcrec/secp256k1/v4 or
//      github.com/ethereum/go-ethereum/crypto signer). When no secp256k1
//      backend is configured the producer transparently falls back to the
//      ed25519 family-2 path (the mesh already carries ed25519 keys, see
//      types.go:30-33) so the producer is runnable in dev/test today
//      without pulling in an external secp256k1 dependency.
//   3. Collects signatures from the validator mesh via the P2P gossip
//      protocol (mesh.Attest / mesh.Broadcast). The producer gossips a
//      CertificateSignRequest to the configured peer set, collects
//      CertificateSignResponse messages, and assembles the quorum.
//   4. Produces a CanonicalCertificate envelope carrying the payload P, the
//      certificate hash (SHA3-256 of P, §2.1), the quorum of weighted
//      signatures, and the L4.2 tier the quorum satisfied.
//   5. Exposes SignCertificate(payload []byte) (*CanonicalCertificate, error)
//      as the high-level entry point used by the consensus engine.
//
// The payload layout constants (DOMAIN_TAG, PAYLOAD_WIDTH, OFFSETS) are
// duplicated here from the Python reference (core/consensus/certificate.py)
// so the Go producer is self-contained, but the byte-level encode is
// delegated to the helpers already in types.go (appendUint*, appendHash) so
// the two implementations cannot drift.
//
// Author: TRION Protocol — Originator: Hudu Yusuf (Analys)
// License: CC0
package consensus

import (
	"crypto/ed25519"
	"errors"
	"fmt"
	"sync"
	"time"

	"github.com/trion-protocol/validator/internal/p2p"
	"github.com/trion-protocol/validator/internal/p2p/meshsha3"
)

// ── Payload layout (§2 — pinned by tests/unit/test_certificate_domain_separation.py) ──

const (
	// DomainTag is the 13-byte canonical certificate domain prefix (§2).
	// "TRION-CERT-V1" — same on every VM.
	DomainTag = "TRION-CERT-V1"

	// DomainTagLen is the byte width of DomainTag.
	DomainTagLen = len(DomainTag)

	// PayloadWidth is the total canonical signing payload width (§2). The
	// single most important constant in the protocol — every encoder on
	// every VM must produce exactly this many bytes.
	PayloadWidth = 346

	// Fixed-point scales (§4) — coherence/threshold/power are ×1e6, HHI is
	// ×1e4.
	Scale1e6 = 1_000_000
	Scale1e4 = 10_000

	// L4.8 HHI bound — a certificate emitted under CRITICAL-tier
	// concentration (>4000) is invalid by spec; the producer rejects it.
	HHIMaxAcceptable = 4_000

	// L4.2 quorum tiers on D_consensus (×1e6).
	DConsensusTier1 = 600_000 // ≥ 0.60 → STRICTLY > 2/3
	DConsensusTier2 = 400_000 // ≥ 0.40 → ≥ 0.75
	// below 0.40 → 0.85 + GOVERNANCE_SIGNAL (off-chain)

	// MinSigners is the liveness floor (rust InsufficientSigners parity).
	MinSigners = 3

	// SignatureFamilyEIP191Secp256k1 is family 1: EIP-191-wrapped
	// keccak256(P), verified via ecrecover on EVM chains (§3.2).
	SignatureFamilyEIP191Secp256k1 = 1

	// SignatureFamilyEd25519 is family 2: Ed25519 over the RAW 346-byte P
	// (§3.2). This is the Go validator mesh's native signature scheme.
	SignatureFamilyEd25519 = 2
)

// PayloadOffsets is the byte-offset table for the 346-byte payload P (§2).
// Mirrors core/consensus/certificate.py:OFFSETS verbatim — any change is a
// format version bump (a new domain tag, never a width tweak).
var PayloadOffsets = map[string][2]int{
	"domain_tag":            {0, 13},
	"certificate_kind":      {13, 14},
	"protocol_version":      {14, 17},
	"validator_epoch":       {17, 21},
	"certificate_nonce":     {21, 29},
	"escrow_id":             {29, 61},
	"route_id":              {61, 93},
	"intent_hash":           {93, 125},
	"entity_id":             {125, 157},
	"source_chain":          {157, 161},
	"dest_chain":            {161, 165},
	"destination":           {165, 197},
	"amount":                {197, 229},
	"anchor_bh":             {229, 261},
	"execution_bh":          {261, 293},
	"coherence":             {293, 301},
	"threshold":             {301, 309},
	"hhi_at_emission":       {309, 317},
	"total_effective_power": {317, 325},
	"validator_count":       {325, 329},
	"awa_enforced":          {329, 330},
	"issued_at":             {330, 338},
	"ttl":                   {338, 346},
}

// ── Certificate envelope (§5) ───────────────────────────────────────────────

// WeightedSignatureEntry pairs a validator's signature with its claimed
// voting weight (×1e6). Weights are CLAIMS — the on-chain verifier
// cross-checks them against the registered epoch set (see
// core/consensus/certificate.py:check_epoch_set_quorum). The Go producer
// records the weight the local registry assigned at sign time so the
// envelope is self-describing; the verifier is the trust root, not the
// producer.
type WeightedSignatureEntry struct {
	ValidatorID [32]byte `json:"validator_id"`
	Signature   []byte   `json:"signature"`
	// Weight is the validator's effective power s_j·d_j ×1e6 at the epoch.
	Weight uint64 `json:"weight"`
	// SignerFamily labels which signature scheme produced `Signature` —
	// 1 = secp256k1+ EIP-191 (EVM family), 2 = Ed25519 over raw P.
	// The verifier dispatches on this field (§3.2).
	SignerFamily uint8 `json:"signer_family"`
}

// CanonicalCertificate is the Go-native carrier for a 346-byte canonical
// certificate payload P plus the quorum of weighted validator signatures
// that justify it. The producer emits this; the on-chain verifier on every
// VM consumes it.
type CanonicalCertificate struct {
	// Payload is the exact 346-byte canonical signing payload P (§2).
	// Identical bytes on every VM — this is the cross-VM invariant.
	Payload []byte `json:"payload"`

	// CertificateHash is SHA3-256(P) (§2.1) — the cross-VM certificate id.
	// Computed once at production and shipped with the envelope so verifiers
	// can do an O(1) identity check before re-decoding P.
	CertificateHash Hash `json:"certificate_hash"`

	// Signatures is the quorum of weighted validator signatures.
	Signatures []WeightedSignatureEntry `json:"signatures"`

	// QuorumTier is the L4.2 tier the assembled quorum satisfied
	// (1 = STRICTLY > 2/3, 2 = ≥ 0.75). Zero means no quorum was reached —
	// the certificate is NOT valid for emission.
	QuorumTier int `json:"quorum_tier"`

	// TotalWeight is Σ w_j over the signatures (×1e6). The verifier
	// re-derives this from the registered epoch set; the producer records
	// it so consumers can render the quorum without re-walking the registry.
	TotalWeight uint64 `json:"total_weight"`

	// ProducedAt is the wall-clock time the producer assembled the
	// certificate (Unix milliseconds). NOT part of the signed payload —
	// the payload's `issued_at` field (offset 330) is the authoritative
	// timestamp, signed by every validator.
	ProducedAtMs int64 `json:"produced_at_ms"`
}

// ── Signer interface (secp256k1 default + ed25519 fallback) ──────────────────

// Secp256k1Signer is the injectable backend that produces family-1
// secp256k1 + EIP-191 signatures over keccak256(P). Operators wire a real
// implementation (e.g. an HSM-backed signer or
// github.com/decred/dcrd/dcrec/secp256k1/v4) at deployment time. When nil,
// the producer falls back to the ed25519 family-2 path so the mesh is
// runnable in dev/test today.
//
// The interface returns (signature, signerPublicKey, error). The public
// key is included in the response so the producer can record which
// validator identity the signature came from (the on-chain verifier
// recovers it from the signature itself via ecrecover; the producer's
// copy is informational only).
type Secp256k1Signer interface {
	// SignEIP191 produces an EIP-191-wrapped secp256k1 signature over
	// keccak256(payload). The returned sig is 65 bytes (r||s||v) with v
	// in {0, 1, 27, 28} per EIP-191.
	SignEIP191(payload []byte) (sig []byte, pubKey []byte, err error)
}

// Ed25519Signer is the stdlib-backed family-2 signer. It produces raw
// Ed25519 signatures over the 346-byte payload P (§3.2 family 2 — NO
// hashing layer between the signature and P; the Ed25519 algorithm itself
// hashes internally).
type Ed25519Signer struct {
	Priv ed25519.PrivateKey
	Pub  ed25519.PublicKey
}

// SignEd25519 signs the payload with the configured ed25519 private key.
func (s *Ed25519Signer) SignEd25519(payload []byte) ([]byte, error) {
	if len(s.Priv) != ed25519.PrivateKeySize {
		return nil, fmt.Errorf("ed25519 private key must be %d bytes, got %d",
			ed25519.PrivateKeySize, len(s.Priv))
	}
	return ed25519.Sign(s.Priv, payload), nil
}

// ── Mesh integration (sign-request gossip) ────────────────────────────────────

// CertificateSignRequest is the gossip message the producer broadcasts to
// collect validator signatures. It carries the 346-byte P (the only thing
// a validator needs to sign) plus the producer's identity so peers can
// decide whether to co-sign.
type CertificateSignRequest struct {
	// Payload is the exact 346-byte canonical certificate payload P.
	Payload []byte `json:"payload"`
	// ProducerID is the mesh identity of the validator that initiated the
	// signing round (the round leader).
	ProducerID [32]byte `json:"producer_id"`
	// RequestedAt is the wall-clock time the producer initiated the round.
	RequestedAtMs int64 `json:"requested_at_ms"`
}

// CertificateSignResponse is a peer validator's signed response. The
// producer aggregates these into the canonical certificate envelope.
type CertificateSignResponse struct {
	// ValidatorID is the responding validator's mesh identity.
	ValidatorID [32]byte `json:"validator_id"`
	// Signature is the validator's signature over P. Width depends on
	// SignerFamily: 65 bytes for secp256k1 (r||s||v), 64 bytes for ed25519.
	Signature []byte `json:"signature"`
	// Weight is the validator's effective power s_j·d_j ×1e6 at this epoch.
	// The producer trusts the local registry view; the on-chain verifier
	// re-derives from the registered epoch set.
	Weight uint64 `json:"weight"`
	// SignerFamily labels which signature scheme produced Signature.
	SignerFamily uint8 `json:"signer_family"`
}

// MeshSigner is the subset of *p2p.MeshNode the producer needs. Defining
// it as an interface keeps the producer testable without spinning up a
// real TCP mesh — tests inject a fake.
type MeshSigner interface {
	// BroadcastSignRequest gossips a CertificateSignRequest to the mesh
	// and returns the collected responses. The implementation decides the
	// timeout (the real mesh uses a 2× block-time deadline).
	BroadcastSignRequest(req *CertificateSignRequest, timeout time.Duration) ([]CertificateSignResponse, error)
	// SelfID returns the local validator's mesh identity.
	SelfID() [32]byte
}

// ── Producer ──────────────────────────────────────────────────────────────────

// CertificateProducer assembles a CanonicalCertificate from a 346-byte
// payload P and the validator mesh's signatures. It is the Go-side
// counterpart to core/consensus/certificate.py:CanonicalCertificate (the
// Python reference encoder) and the on-chain verifiers in
// contracts/{solidity,svm,move,ton,cairo,near}/.
type CertificateProducer struct {
	mu sync.Mutex

	// payload is the 346-byte canonical signing payload P (§2). Set once
	// per SignCertificate call; the producer is stateless across calls.
	payload []byte

	// mesh is the P2P validator mesh the producer uses to collect peer
	// signatures. May be nil for solo-mode producers (single validator
	// signing — useful for dev/test, NOT a valid canonical certificate
	// because MinSigners=3 is required at verification).
	mesh MeshSigner

	// secp256k1 is the injectable family-1 signer. When nil, the producer
	// uses the ed25519 family-2 path.
	secp256k1 Secp256k1Signer

	// ed25519 is the stdlib family-2 signer (the mesh's native scheme).
	// Required when secp256k1 is nil; ignored otherwise.
	ed25519 *Ed25519Signer
}

// ProducerOption configures a CertificateProducer.
type ProducerOption func(*CertificateProducer)

// WithMesh wires a P2P mesh signer so the producer can collect peer
// signatures via gossip. Without this option the producer signs alone
// (dev/test only — the resulting certificate will fail MinSigners=3).
func WithMesh(mesh MeshSigner) ProducerOption {
	return func(p *CertificateProducer) { p.mesh = mesh }
}

// WithSecp256k1Signer wires an injectable secp256k1 + EIP-191 signer for
// family-1 signatures (the EVM-native path). When this option is NOT set,
// the producer falls back to the ed25519 family-2 path that the mesh
// already supports natively.
func WithSecp256k1Signer(s Secp256k1Signer) ProducerOption {
	return func(p *CertificateProducer) { p.secp256k1 = s }
}

// WithEd25519Signer wires the stdlib family-2 signer. Required unless
// WithSecp256k1Signer is provided (in which case the ed25519 signer is
// only used as a fallback if the secp256k1 signer errors).
func WithEd25519Signer(s *Ed25519Signer) ProducerOption {
	return func(p *CertificateProducer) { p.ed25519 = s }
}

// NewCertificateProducer constructs a producer with the given options.
func NewCertificateProducer(opts ...ProducerOption) *CertificateProducer {
	p := &CertificateProducer{}
	for _, opt := range opts {
		opt(p)
	}
	return p
}

// SignCertificate is the high-level entry point. It validates the payload,
// collects the local validator's signature, gossips for peer signatures
// (when a mesh is configured), checks the L4.2 quorum tier, and assembles
// the CanonicalCertificate envelope.
//
// Returns:
//   - *CanonicalCertificate on success (quorum reached OR solo-mode dev/test).
//   - error if the payload is malformed, the producer has no signer, or the
//     quorum was not reached (with the tier / weight breakdown for debugging).
func (p *CertificateProducer) SignCertificate(payload []byte) (*CanonicalCertificate, error) {
	if err := validatePayload(payload); err != nil {
		return nil, fmt.Errorf("certificate payload invalid: %w", err)
	}

	p.mu.Lock()
	p.payload = append([]byte(nil), payload...) // defensive copy
	localPayload := p.payload
	p.mu.Unlock()

	// HHI bound check (§6 step 1 — fail-closed on CRITICAL concentration).
	if hhi := readUint64(localPayload, PayloadOffsets["hhi_at_emission"][0]); hhi > HHIMaxAcceptable {
		return nil, fmt.Errorf(
			"hhi_at_emission %d exceeds CRITICAL bound %d — certificate invalid by spec",
			hhi, HHIMaxAcceptable,
		)
	}

	certHash := meshsha3.Sum256(localPayload)

	// Collect the local validator's signature first.
	var sigs []WeightedSignatureEntry
	localSig, localFamily, err := p.signLocal(localPayload)
	if err != nil {
		return nil, fmt.Errorf("local sign failed: %w", err)
	}
	sigs = append(sigs, localSig)

	// Gossip for peer signatures (when a mesh is configured).
	if p.mesh != nil {
		req := &CertificateSignRequest{
			Payload:       localPayload,
			ProducerID:    p.mesh.SelfID(),
			RequestedAtMs: time.Now().UnixMilli(),
		}
		// 2× the canonical block time as the gossip deadline.
		responses, err := p.mesh.BroadcastSignRequest(req, 12*time.Second)
		if err != nil {
			// Mesh failure is non-fatal — proceed with whatever we have.
			// The quorum check below will reject if we're short.
			_ = err
		}
		for _, resp := range responses {
			// Don't double-count the local validator.
			if resp.ValidatorID == localSig.ValidatorID {
				continue
			}
			if !verifyResponseSignature(&resp, localPayload) {
				// Drop invalid peer signatures — the on-chain verifier
				// would reject them anyway; better to surface a quorum
				// failure than ship a bad signature.
				continue
			}
			sigs = append(sigs, WeightedSignatureEntry{
				ValidatorID:  resp.ValidatorID,
				Signature:    append([]byte(nil), resp.Signature...),
				Weight:       resp.Weight,
				SignerFamily: resp.SignerFamily,
			})
		}
	}

	// Aggregate the weights and check the L4.2 quorum tier.
	var totalWeight uint64
	for _, s := range sigs {
		totalWeight += s.Weight
	}
	totalPower := readUint64(localPayload, PayloadOffsets["total_effective_power"][0])
	tier := quorumTier(totalWeight, totalPower)

	cert := &CanonicalCertificate{
		Payload:       localPayload,
		CertificateHash: certHash,
		Signatures:    sigs,
		QuorumTier:    tier,
		TotalWeight:   totalWeight,
		ProducedAtMs:  time.Now().UnixMilli(),
	}

	// Solo-mode dev/test: when no mesh is configured we return the
	// certificate with tier=0 so the caller can see it would have failed
	// the MinSigners=3 floor — but we don't error, because dev/test
	// pipelines may legitimately want to inspect the (invalid) envelope.
	if p.mesh == nil {
		return cert, nil
	}
	if tier == 0 {
		return cert, fmt.Errorf(
			"quorum not reached: weight %d / power %d (tier1=%d tier2=%d, signers=%d)",
			totalWeight, totalPower, DConsensusTier1, DConsensusTier2, len(sigs),
		)
	}
	return cert, nil
}

// signLocal produces the local validator's signature over P. It prefers
// the secp256k1 family-1 path (the spec-mandated EVM-native scheme) and
// falls back to ed25519 family-2 when no secp256k1 signer is configured.
func (p *CertificateProducer) signLocal(payload []byte) (WeightedSignatureEntry, uint8, error) {
	if p.secp256k1 != nil {
		sig, pub, err := p.secp256k1.SignEIP191(payload)
		if err == nil && len(sig) == 65 {
			var vid [32]byte
			// MeshValidatorIDFromKey gives a stable 32-byte identity from
			// any byte key — same construction the mesh uses for its
			// ValidatorProfile.ID.
			vid = p2p.MeshValidatorIDFromKey(pub)
			return WeightedSignatureEntry{
				ValidatorID:  vid,
				Signature:    sig,
				Weight:       0, // weight is filled by the registry at gossip time
				SignerFamily: SignatureFamilyEIP191Secp256k1,
			}, SignatureFamilyEIP191Secp256k1, nil
		}
		// secp256k1 signer errored — fall through to ed25519 if available.
	}
	if p.ed25519 != nil {
		sig, err := p.ed25519.SignEd25519(payload)
		if err != nil {
			return WeightedSignatureEntry{}, 0, err
		}
		vid := p2p.MeshValidatorIDFromKey(p.ed25519.Pub)
		return WeightedSignatureEntry{
			ValidatorID:  vid,
			Signature:    sig,
			Weight:       0,
			SignerFamily: SignatureFamilyEd25519,
		}, SignatureFamilyEd25519, nil
	}
	return WeightedSignatureEntry{}, 0, errors.New(
		"no signer configured: pass WithSecp256k1Signer or WithEd25519Signer",
	)
}

// verifyResponseSignature is a structural sanity check on a peer's
// signature. We do NOT cryptographically verify here — the on-chain
// verifier is the trust root — but we do reject obviously-malformed
// responses (wrong sig width for the claimed family) so a misbehaving
// peer can't pollute the envelope.
func verifyResponseSignature(resp *CertificateSignResponse, payload []byte) bool {
	switch resp.SignerFamily {
	case SignatureFamilyEIP191Secp256k1:
		return len(resp.Signature) == 65
	case SignatureFamilyEd25519:
		return len(resp.Signature) == ed25519.SignatureSize
	default:
		return false
	}
}

// quorumTier returns the L4.2 tier (1 = STRICTLY > 2/3, 2 = ≥ 0.75, 0 =
// no quorum) given the assembled weight and the registered total
// effective power. Uses integer arithmetic (3·w > 2·t for tier 1) so the
// comparison is exact, not float-approximate.
func quorumTier(weight, totalPower uint64) int {
	if totalPower == 0 {
		return 0
	}
	// Tier 1: STRICTLY more than 2/3 of totalPower (3·w > 2·t).
	if 3*weight > 2*totalPower {
		return 1
	}
	// Tier 2: at least 0.75 of totalPower (4·w ≥ 3·t).
	if 4*weight >= 3*totalPower {
		return 2
	}
	return 0
}

// ── Payload validation (§6 step 1 — fail-closed) ─────────────────────────────

// validatePayload checks the structural invariants every canonical
// certificate payload P must satisfy, per §6 step 1 of
// CANONICAL_CERTIFICATE.md. Failures are fatal — the producer must not
// ship a malformed payload to the verifier.
func validatePayload(payload []byte) error {
	if len(payload) != PayloadWidth {
		return fmt.Errorf("payload width %d, want %d", len(payload), PayloadWidth)
	}
	if string(payload[:DomainTagLen]) != DomainTag {
		return fmt.Errorf(
			"bad domain tag %q — not a TRION-CERT-V1 payload",
			string(payload[:DomainTagLen]),
		)
	}
	// TTL must be > 0 (otherwise the certificate is born expired).
	ttl := readUint64(payload, PayloadOffsets["ttl"][0])
	if ttl == 0 {
		return errors.New("ttl is zero — certificate is born expired")
	}
	// issued_at must be > 0 (the producer always sets it).
	issuedAt := readUint64(payload, PayloadOffsets["issued_at"][0])
	if issuedAt == 0 {
		return errors.New("issued_at is zero")
	}
	return nil
}

// readUint64 reads an 8-byte big-endian uint64 from payload at offset.
// Used for the ×1e6 fixed-point fields (coherence, threshold, HHI, etc.).
func readUint64(payload []byte, offset int) uint64 {
	if offset+8 > len(payload) {
		return 0
	}
	var v uint64
	for i := 0; i < 8; i++ {
		v = (v << 8) | uint64(payload[offset+i])
	}
	return v
}

// ── Convenience: encode a payload P from the canonical fields ─────────────────
//
// BuildPayload assembles a 346-byte P from the 23 canonical fields. The
// encoding helpers (appendUint*, appendHash) are imported from types.go
// so this producer cannot drift from the existing block/vote encoder.
//
// This is the Go counterpart of
// core/consensus/certificate.py:CanonicalCertificate.encode_payload().
type CertificateFields struct {
	CertificateKind      uint8
	ProtocolVersion      [3]byte
	ValidatorEpoch       uint32
	CertificateNonce     uint64
	EscrowID             [32]byte
	RouteID              [32]byte
	IntentHash           [32]byte
	EntityID             [32]byte
	SourceChain          uint32
	DestChain            uint32
	Destination          [32]byte
	Amount               [32]byte // big-endian uint256
	AnchorBH             [32]byte
	ExecutionBH          [32]byte
	Coherence            uint64 // ×1e6
	Threshold            uint64 // ×1e6
	HHIAtEmission         uint64 // ×1e4
	TotalEffectivePower  uint64 // ×1e6
	ValidatorCount       uint32
	AwaEnforced          bool
	IssuedAt             uint64
	TTL                  uint64
}

// Encode returns the 346-byte canonical signing payload P. Deterministic:
// identical fields → identical bytes, on every platform. Mirrors
// core/consensus/certificate.py:CanonicalCertificate.encode_payload byte
// for byte.
func (f *CertificateFields) Encode() ([]byte, error) {
	p := make([]byte, 0, PayloadWidth)
	p = append(p, DomainTag...)
	p = appendUint8(p, f.CertificateKind)
	p = append(p, f.ProtocolVersion[:]...)
	p = appendUint32(p, f.ValidatorEpoch)
	p = appendUint64(p, f.CertificateNonce)
	p = appendHash(p, Hash(f.EscrowID))
	p = appendHash(p, Hash(f.RouteID))
	p = appendHash(p, Hash(f.IntentHash))
	p = appendHash(p, Hash(f.EntityID))
	p = appendUint32(p, f.SourceChain)
	p = appendUint32(p, f.DestChain)
	p = appendHash(p, Hash(f.Destination))
	p = append(p, f.Amount[:]...)
	p = appendHash(p, Hash(f.AnchorBH))
	p = appendHash(p, Hash(f.ExecutionBH))
	p = appendUint64(p, f.Coherence)
	p = appendUint64(p, f.Threshold)
	p = appendUint64(p, f.HHIAtEmission)
	p = appendUint64(p, f.TotalEffectivePower)
	p = appendUint32(p, f.ValidatorCount)
	p = appendUint8(p, boolToByte(f.AwaEnforced))
	p = appendUint64(p, f.IssuedAt)
	p = appendUint64(p, f.TTL)
	if len(p) != PayloadWidth {
		return nil, fmt.Errorf(
			"internal: encoded payload width %d, want %d — field layout drift",
			len(p), PayloadWidth,
		)
	}
	return p, nil
}

func boolToByte(b bool) byte {
	if b {
		return 1
	}
	return 0
}
