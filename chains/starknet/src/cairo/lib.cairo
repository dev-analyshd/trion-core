// ═══════════════════════════════════════════════════════════
//   TRION Protocol — Starknet BTCP Contract Suite
//   All modules compile via `pub mod cairo;` in src/lib.cairo
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
