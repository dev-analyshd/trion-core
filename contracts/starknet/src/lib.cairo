// ═══════════════════════════════════════════════════════════
//   TRION Protocol — Starknet BTCP Contract Suite
//   Module root: every contract below compiles from src/lib.cairo
// ═══════════════════════════════════════════════════════════

// ─── Core oracle + identity ─────────────────────────────────
pub mod TRIONOracle;
pub mod BEOAttestation;
pub mod BTCFiGuard;
pub mod BIRPAttestation;

// ─── BTCP suite (BTCP Master Spec §14.3) ────────────────────
pub mod btcp_escrow;
pub mod btcp_intent;
pub mod btcp_route;

// ─── Canonical certificate, family 3 (C-04 fix) ─────────────
// trion_certificate: the CANONICAL_CERTIFICATE §3.2 felt-chunk
// library (Poseidon domain felt + starknet::ecdsa); pure, no
// storage, no authority. trion_epoch_registry: the §10.2
// per-epoch validator-set registrar the escrow consults for
// epoch membership, weights, D_consensus and the quorum tier.
pub mod trion_certificate;
pub mod trion_epoch_registry;
