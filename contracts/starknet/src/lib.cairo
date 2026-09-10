// ═══════════════════════════════════════════════════════════
//   TRION Protocol — Starknet (Cairo) Contract Suite
//   Unified workspace: BTCP + oracle + behavioral infrastructure
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
pub mod btc_spv_verifier;
pub mod btc_spend_verifier;
pub mod sha256_test;
pub mod btcp_escrow_v2;
pub mod btcp_escrow_v3;
pub mod btcp_defi_pool;
pub mod attestor_proxy;
pub mod forwarder;

// ─── Behavioral infrastructure (merged from contracts/cairo) ──
pub mod trion_oracle_v3;
pub mod trion_sensing_oracle;
pub mod trion_execution_gate;
pub mod trion_price_feed;
pub mod trion_firewall;
pub mod trion_liquidity_guard;
pub mod trion_protected_vault;
pub mod trion_certificate;
pub mod trion_epoch_registry;
pub mod akashic_proof;
pub mod confidential_coherence_vault;
pub mod liquidity_ocean;
pub mod module_root;

// ─── Test helpers ────────────────────────────────────────────
pub mod mock_oracle;
pub mod mock_trion_token;
pub mod attack_simulator;
pub mod reentrant_attacker;

// ─── Sepolia deployed structs ───────────────────────────────
pub mod starknet_sepolia_structs;
