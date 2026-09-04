#!/usr/bin/env node
/**
 * TRION Multi-Chain Relayer
 * =========================
 * Polls the Akashic Oracle for the latest signal on each monitored entity,
 * packs it into the bit layout expected by TRIONOracleV3.publishSignal, and
 * either signs+sends to every configured chain or runs in DRY_RUN mode.
 *
 * Bit layout (publishSignal packedData, uint256):
 *   bits   0..7    : status   (uint8 — 1 = SAFE, 0 = COLLAPSE_INTERCEPTED)
 *   bits   8..39   : coherence (uint32 — coherence × 1e6, capped at 2^32-1)
 *   bits  40..71   : threshold (uint32 — threshold × 1e6, capped at 2^32-1)
 *   bits  72..135  : block_num (uint64)
 *   bits 136..199  : timestamp (uint64 — unix seconds)
 *
 * Quorum: publishSignal requires `quorumRequired` signatures over
 *   keccak256(abi.encodePacked(chainId, oracleAddr, txId, packedData))
 * each prefixed with the EIP-191 "\x19Ethereum Signed Message:\n32" header.
 * For a single-validator setup this relayer signs with RELAYER_PRIVATE_KEY
 * (which must also be the registered validator). For multi-validator quorum,
 * collect signatures from peers via SIGNER_KEYS_JSON (comma separated).
 *
 * Required env (live mode):
 *   RELAYER_PRIVATE_KEY      hex private key (0x… or 64 hex chars) for a registered validator
 *                            (dev only — KMS_PROVIDER=env)
 *   … or KMS_PROVIDER=aws|gcp|yubihsm|pkcs11 + the provider-specific env
 *     vars (see relayer/kms_provider.js) for HSM/KMS-backed signing
 *   ORACLE_API_URL           http://127.0.0.1:5000          (default)
 *   MONITORED_ENTITIES       comma-separated list (default: TRION oracle contract)
 *   POLL_INTERVAL_MS         default 30000
 *   ARBITRUM_ORACLE_ADDR     contract addr on Arbitrum One
 *   ETH_MAINNET_ORACLE_ADDR  contract addr on Ethereum
 *   POLYGON_ORACLE_ADDR      contract addr on Polygon
 *   OPTIMISM_ORACLE_ADDR     ...
 *   BASE_ORACLE_ADDR         ...
 *   BNB_ORACLE_ADDR          ...
 *   AVALANCHE_ORACLE_ADDR    ...
 *   LINEA_ORACLE_ADDR        ...
 *   SCROLL_ORACLE_ADDR       ...
 *   ZKSYNC_ORACLE_ADDR       ...
 *
 * If RELAYER_PRIVATE_KEY is missing AND no KMS/HSM provider is configured
 * (KMS_PROVIDER unset or "env"), the relayer runs in DRY_RUN mode and
 * logs the would-be transaction for every chain. If a per-chain *_ORACLE_ADDR
 * is missing, that chain is skipped.
 */

import { ethers } from "ethers";
import axios from "axios";
import { createHash } from "node:crypto";
import fs from "node:fs";

const ORACLE_API_URL  = process.env.ORACLE_API_URL  || "http://127.0.0.1:5000";
const POLL_INTERVAL_MS = parseInt(process.env.POLL_INTERVAL_MS || "30000", 10);
const MONITORED       = (process.env.MONITORED_ENTITIES ||
  "0xb819c63c02Ed5aB49017C0f3f2568A14624658b3,uniswap,aave,compound"
).split(",").map(s => s.trim()).filter(Boolean);

const PRIVATE_KEY = process.env.RELAYER_PRIVATE_KEY || null;
const KMS_PROVIDER = (process.env.KMS_PROVIDER || "env").toLowerCase();
// Live mode when a plaintext key (env provider) OR an external KMS/HSM
// provider is configured. Default — neither set — stays DRY_RUN.
const DRY_RUN     = !PRIVATE_KEY && KMS_PROVIDER === "env";

// Multi-chain registry — points at the testnets/mainnets where TRION oracle
// contracts are actually deployed (see proof-ledger/deploy_*.json). Each entry
// has a baked-in default contract address from the upstream deployment
// manifests; override via *_ORACLE_ADDR secrets if you redeploy. Override
// *_RPC_URL to use a private endpoint.
const CHAINS = [
  // ── Mainnet oracle targets (TRIONOracleV3 deployed) ──────────────────────
  { key: "hashkey",  name: "HashKey Mainnet",  chainId: 177,    rpcEnv: "HSK_RPC_URL",     rpcDefault: "https://mainnet.hsk.xyz",         addrEnv: "HSK_ORACLE_ADDR",     addrDefault: "0x708193f93Fb897fbeA72e7e7D19237770F19E969" },
  // ── Mainnet oracle targets (contract deploy pending — logs "no ADDR") ───
  { key: "eth-mainnet",  name: "Ethereum Mainnet",  chainId: 1,      rpcEnv: "ETH_MAINNET_RPC_URL",  rpcDefault: "https://ethereum.publicnode.com",    addrEnv: "ETH_MAINNET_ORACLE_ADDR",  addrDefault: null },
  { key: "arb-mainnet",  name: "Arbitrum One",       chainId: 42161,  rpcEnv: "ARB_MAINNET_RPC_URL",  rpcDefault: "https://arb1.arbitrum.io/rpc",        addrEnv: "ARB_MAINNET_ORACLE_ADDR",  addrDefault: null },
  { key: "base-mainnet", name: "Base Mainnet",        chainId: 8453,   rpcEnv: "BASE_MAINNET_RPC_URL", rpcDefault: "https://mainnet.base.org",            addrEnv: "BASE_MAINNET_ORACLE_ADDR", addrDefault: null },
  { key: "op-mainnet",   name: "Optimism Mainnet",    chainId: 10,     rpcEnv: "OP_MAINNET_RPC_URL",   rpcDefault: "https://mainnet.optimism.io",         addrEnv: "OP_MAINNET_ORACLE_ADDR",   addrDefault: null },
  { key: "bnb-mainnet",  name: "BNB Smart Chain",     chainId: 56,     rpcEnv: "BNB_MAINNET_RPC_URL",  rpcDefault: "https://bsc-dataseed.binance.org",    addrEnv: "BNB_MAINNET_ORACLE_ADDR",  addrDefault: null },
  { key: "polygon",      name: "Polygon Mainnet",     chainId: 137,    rpcEnv: "POLYGON_RPC_URL",      rpcDefault: "https://polygon-rpc.com",             addrEnv: "POLYGON_ORACLE_ADDR",      addrDefault: null },
  { key: "mantle",       name: "Mantle Mainnet",      chainId: 5000,   rpcEnv: "MANTLE_RPC_URL",       rpcDefault: "https://rpc.mantle.xyz",              addrEnv: "MANTLE_ORACLE_ADDR",       addrDefault: null },
  { key: "linea",        name: "Linea Mainnet",       chainId: 59144,  rpcEnv: "LINEA_RPC_URL",        rpcDefault: "https://rpc.linea.build",             addrEnv: "LINEA_ORACLE_ADDR",        addrDefault: null },
  { key: "scroll",       name: "Scroll Mainnet",      chainId: 534352, rpcEnv: "SCROLL_RPC_URL",       rpcDefault: "https://rpc.scroll.io",               addrEnv: "SCROLL_ORACLE_ADDR",       addrDefault: null },
  // ── 0G Networks ──────────────────────────────────────────────────────────
  { key: "0g-mainnet",   name: "0G Mainnet",          chainId: 16661,  rpcEnv: "ZERO_G_RPC",           rpcDefault: "https://evmrpc.0g.ai",                addrEnv: "ZG_MAINNET_ORACLE_ADDR",   addrDefault: null },

  // ── Avalanche ────────────────────────────────────────────────────────────
  { key: "avalanche",    name: "Avalanche C-Chain",   chainId: 43114,  rpcEnv: "AVAX_RPC_URL",         rpcDefault: "https://api.avax.network/ext/bc/C/rpc", addrEnv: "AVAX_ORACLE_ADDR",       addrDefault: null },

  // ── Fantom / Sonic ────────────────────────────────────────────────────────
  { key: "fantom",       name: "Fantom Opera",        chainId: 250,    rpcEnv: "FTM_RPC_URL",          rpcDefault: "https://rpcapi.fantom.network",       addrEnv: "FTM_ORACLE_ADDR",          addrDefault: null },
  { key: "sonic",        name: "Sonic Mainnet",       chainId: 146,    rpcEnv: "SONIC_RPC_URL",        rpcDefault: "https://rpc.soniclabs.com",           addrEnv: "SONIC_ORACLE_ADDR",        addrDefault: null },

  // ── zkSync Era ────────────────────────────────────────────────────────────
  { key: "zksync-era",   name: "zkSync Era",          chainId: 324,    rpcEnv: "ZKSYNC_RPC_URL",       rpcDefault: "https://mainnet.era.zksync.io",       addrEnv: "ZKSYNC_ORACLE_ADDR",       addrDefault: null },

  // ── Berachain ─────────────────────────────────────────────────────────────
  { key: "berachain",    name: "Berachain",           chainId: 80094,  rpcEnv: "BERA_RPC_URL",         rpcDefault: "https://rpc.berachain.com",           addrEnv: "BERA_ORACLE_ADDR",         addrDefault: null },

  // ── X Layer (OKX L2) ─────────────────────────────────────────────────────
  { key: "xlayer",       name: "X Layer",             chainId: 196,    rpcEnv: "XLAYER_RPC_URL",       rpcDefault: "https://rpc.xlayer.tech",             addrEnv: "XLAYER_ORACLE_ADDR",       addrDefault: null },

  // ── XDC Network ──────────────────────────────────────────────────────────
  { key: "xdc",          name: "XDC Network",         chainId: 50,     rpcEnv: "XDC_RPC_URL",          rpcDefault: "https://rpc.xinfin.network",          addrEnv: "XDC_ORACLE_ADDR",          addrDefault: null },

  // ── Story Protocol (IP) ───────────────────────────────────────────────────
  { key: "story-ip",     name: "Story Protocol IP",   chainId: 1514,   rpcEnv: "STORY_RPC_URL",        rpcDefault: "https://mainnet.storyrpc.io",         addrEnv: "STORY_ORACLE_ADDR",        addrDefault: null },

  // ── Blast ─────────────────────────────────────────────────────────────────
  { key: "blast",        name: "Blast Mainnet",       chainId: 81457,  rpcEnv: "BLAST_RPC_URL",        rpcDefault: "https://rpc.blast.io",                addrEnv: "BLAST_ORACLE_ADDR",        addrDefault: null },

  // ── Manta Pacific ─────────────────────────────────────────────────────────
  { key: "manta",        name: "Manta Pacific",       chainId: 169,    rpcEnv: "MANTA_RPC_URL",        rpcDefault: "https://pacific-rpc.manta.network/http", addrEnv: "MANTA_ORACLE_ADDR",     addrDefault: null },

  // ── Mode Network ──────────────────────────────────────────────────────────
  { key: "mode",         name: "Mode Network",        chainId: 34443,  rpcEnv: "MODE_RPC_URL",         rpcDefault: "https://mainnet.mode.network",        addrEnv: "MODE_ORACLE_ADDR",         addrDefault: null },

  // ── Taiko ─────────────────────────────────────────────────────────────────
  { key: "taiko",        name: "Taiko Mainnet",       chainId: 167000, rpcEnv: "TAIKO_RPC_URL",        rpcDefault: "https://rpc.mainnet.taiko.xyz",       addrEnv: "TAIKO_ORACLE_ADDR",        addrDefault: null },

  // ── Fraxtal ───────────────────────────────────────────────────────────────
  { key: "fraxtal",      name: "Fraxtal Mainnet",     chainId: 252,    rpcEnv: "FRAXTAL_RPC_URL",      rpcDefault: "https://rpc.frax.com",                addrEnv: "FRAXTAL_ORACLE_ADDR",      addrDefault: null },

  // ── Metis ─────────────────────────────────────────────────────────────────
  { key: "metis",        name: "Metis Andromeda",     chainId: 1088,   rpcEnv: "METIS_RPC_URL",        rpcDefault: "https://andromeda.metis.io/?owner=1088", addrEnv: "METIS_ORACLE_ADDR",     addrDefault: null },

  // ── Celo ──────────────────────────────────────────────────────────────────
  { key: "celo",         name: "Celo Mainnet",        chainId: 42220,  rpcEnv: "CELO_RPC_URL",         rpcDefault: "https://forno.celo.org",              addrEnv: "CELO_ORACLE_ADDR",         addrDefault: null },

  // ── Gnosis Chain ──────────────────────────────────────────────────────────
  { key: "gnosis",       name: "Gnosis Chain",        chainId: 100,    rpcEnv: "GNOSIS_RPC_URL",       rpcDefault: "https://rpc.gnosischain.com",         addrEnv: "GNOSIS_ORACLE_ADDR",       addrDefault: null },

  // ── Moonbeam ──────────────────────────────────────────────────────────────
  { key: "moonbeam",     name: "Moonbeam",            chainId: 1284,   rpcEnv: "MOONBEAM_RPC_URL",     rpcDefault: "https://rpc.api.moonbeam.network",    addrEnv: "MOONBEAM_ORACLE_ADDR",     addrDefault: null },

  // ── Kaia (formerly Klaytn) ────────────────────────────────────────────────
  { key: "kaia",         name: "Kaia Mainnet",        chainId: 8217,   rpcEnv: "KAIA_RPC_URL",         rpcDefault: "https://public-en.node.kaia.io",      addrEnv: "KAIA_ORACLE_ADDR",         addrDefault: null },

  // ── CORE Chain ────────────────────────────────────────────────────────────
  { key: "core",         name: "CORE Chain",          chainId: 1116,   rpcEnv: "CORE_RPC_URL",         rpcDefault: "https://rpc.coredao.org",             addrEnv: "CORE_ORACLE_ADDR",         addrDefault: null },

  // ── Bitlayer (BTC L2) ─────────────────────────────────────────────────────
  { key: "bitlayer",     name: "Bitlayer Mainnet",    chainId: 200901, rpcEnv: "BITLAYER_RPC_URL",     rpcDefault: "https://rpc.bitlayer.org",            addrEnv: "BITLAYER_ORACLE_ADDR",     addrDefault: null },

  // ── BOB Network (BTC L2) ─────────────────────────────────────────────────
  { key: "bob",          name: "BOB Network",         chainId: 60808,  rpcEnv: "BOB_RPC_URL",          rpcDefault: "https://rpc.gobob.xyz",               addrEnv: "BOB_ORACLE_ADDR",          addrDefault: null },

  // ── Rootstock (RSK) ──────────────────────────────────────────────────────
  { key: "rootstock",    name: "Rootstock RSK",       chainId: 30,     rpcEnv: "RSK_RPC_URL",          rpcDefault: "https://public-node.rsk.co",          addrEnv: "RSK_ORACLE_ADDR",          addrDefault: null },

  // ── Cronos ───────────────────────────────────────────────────────────────
  { key: "cronos",       name: "Cronos Mainnet",      chainId: 25,     rpcEnv: "CRO_RPC_URL",          rpcDefault: "https://evm.cronos.org",              addrEnv: "CRO_ORACLE_ADDR",          addrDefault: null },

  // ── Aurora (NEAR EVM) ────────────────────────────────────────────────────
  { key: "aurora",       name: "Aurora Mainnet",      chainId: 1313161554, rpcEnv: "AURORA_RPC_URL",   rpcDefault: "https://mainnet.aurora.dev",          addrEnv: "AURORA_ORACLE_ADDR",       addrDefault: null },

  // ── Harmony ONE ──────────────────────────────────────────────────────────
  { key: "harmony",      name: "Harmony ONE",         chainId: 1666600000, rpcEnv: "ONE_RPC_URL",      rpcDefault: "https://api.harmony.one",             addrEnv: "ONE_ORACLE_ADDR",          addrDefault: null },

  // ── IoTeX ─────────────────────────────────────────────────────────────────
  { key: "iotex",        name: "IoTeX Mainnet",       chainId: 4689,   rpcEnv: "IOTEX_RPC_URL",        rpcDefault: "https://babel-api.mainnet.iotex.io",  addrEnv: "IOTEX_ORACLE_ADDR",        addrDefault: null },

  // ── Conflux eSpace ───────────────────────────────────────────────────────
  { key: "conflux",      name: "Conflux eSpace",      chainId: 1030,   rpcEnv: "CFX_RPC_URL",          rpcDefault: "https://evm.confluxrpc.com",          addrEnv: "CFX_ORACLE_ADDR",          addrDefault: null },

  // ── Expansion batch 3: Monad · Filecoin · HyperLiquid · Abstract · Zora ─
  //    WEMIX · OKT · Sapphire · Telos · Kroma · Cyber · Sei EVM · Canto ────
  //    Neon EVM · IOTA EVM ─────────────────────────────────────────────────
  { key: "monad-mainnet",  name: "Monad Mainnet",        chainId: 10143,     rpcEnv: "MONAD_RPC_URL",        rpcDefault: "https://rpc.monad.xyz",                      addrEnv: "MONAD_ORACLE_ADDR",        addrDefault: null },
  { key: "filecoin",       name: "Filecoin FEVM",         chainId: 314,       rpcEnv: "FIL_RPC_URL",          rpcDefault: "https://api.node.glif.io/rpc/v1",            addrEnv: "FIL_ORACLE_ADDR",          addrDefault: null },
  // hyperliquid: OFF-REGISTRY (documented decision, Task 21-c) — 999 is
  // HyperEVM's own native chain id and collides with no canonical registry
  // chain; ingested here and by the bh_streamer worker (testnet RPC), with
  // no Rust indexer. Adding a 130th registry chain would ripple every
  // count/bindings/api surface for that coverage level — kept off-registry,
  // pinned by tests/unit/test_backfill_chain_ids.py.
  { key: "hyperliquid",    name: "HyperLiquid EVM",       chainId: 999,       rpcEnv: "HYPERLIQ_RPC_URL",     rpcDefault: "https://rpc.hyperliquid.xyz/evm",    addrEnv: "HYPERLIQ_ORACLE_ADDR",     addrDefault: null },
  { key: "abstract",       name: "Abstract Mainnet",      chainId: 2741,      rpcEnv: "ABSTRACT_RPC_URL",     rpcDefault: "https://api.mainnet.abs.xyz",                addrEnv: "ABSTRACT_ORACLE_ADDR",     addrDefault: null },
  { key: "zora",           name: "Zora Network",          chainId: 7777777,   rpcEnv: "ZORA_RPC_URL",         rpcDefault: "https://rpc.zora.energy",                    addrEnv: "ZORA_ORACLE_ADDR",         addrDefault: null },
  { key: "wemix",          name: "WEMIX 3.0",             chainId: 1111,      rpcEnv: "WEMIX_RPC_URL",        rpcDefault: "https://api.wemix.com",                      addrEnv: "WEMIX_ORACLE_ADDR",        addrDefault: null },
  { key: "okt-chain",      name: "OKX Chain (OKT)",       chainId: 66,        rpcEnv: "OKT_RPC_URL",          rpcDefault: "https://exchainrpc.okex.org",                addrEnv: "OKT_ORACLE_ADDR",          addrDefault: null },
  { key: "oasis-sapphire", name: "Oasis Sapphire",        chainId: 23294,     rpcEnv: "SAPPHIRE_RPC_URL",     rpcDefault: "https://sapphire.oasis.io",                  addrEnv: "SAPPHIRE_ORACLE_ADDR",     addrDefault: null },
  { key: "telos",          name: "Telos EVM",             chainId: 40,        rpcEnv: "TELOS_RPC_URL",        rpcDefault: "https://mainnet.telos.net/evm",              addrEnv: "TELOS_ORACLE_ADDR",        addrDefault: null },
  { key: "kroma",          name: "Kroma Mainnet",         chainId: 255,       rpcEnv: "KROMA_RPC_URL",        rpcDefault: "https://api.kroma.network",                  addrEnv: "KROMA_ORACLE_ADDR",        addrDefault: null },
  { key: "cyber",          name: "Cyber L3",              chainId: 7560,      rpcEnv: "CYBER_RPC_URL",        rpcDefault: "https://rpc.cyber.co",                       addrEnv: "CYBER_ORACLE_ADDR",        addrDefault: null },
  { key: "sei-evm",        name: "Sei EVM",               chainId: 1329,      rpcEnv: "SEI_EVM_RPC_URL",      rpcDefault: "https://evm-rpc.sei-apis.com",               addrEnv: "SEI_EVM_ORACLE_ADDR",      addrDefault: null },
  { key: "canto",          name: "Canto Mainnet",         chainId: 7700,      rpcEnv: "CANTO_RPC_URL",        rpcDefault: "https://canto.gravitychain.io",              addrEnv: "CANTO_ORACLE_ADDR",        addrDefault: null },
  { key: "neon-evm",       name: "Neon EVM (Solana)",     chainId: 245022934, rpcEnv: "NEON_RPC_URL",         rpcDefault: "https://neon-proxy-mainnet.solana.p2p.org",  addrEnv: "NEON_ORACLE_ADDR",         addrDefault: null },
  { key: "iota-evm",       name: "IOTA EVM",              chainId: 8822,      rpcEnv: "IOTA_RPC_URL",         rpcDefault: "https://json-rpc.evm.iotaledger.net",        addrEnv: "IOTA_ORACLE_ADDR",         addrDefault: null },

  // ── BOT Chain (AI-agent EVM L1) ──────────────────────────────────────────
  { key: "bot-chain",      name: "BOT Chain",             chainId: 677,       rpcEnv: "BOT_CHAIN_RPC_URL",    rpcDefault: "https://rpc.botchain.ai",                    addrEnv: "BOT_CHAIN_ORACLE_ADDR",    addrDefault: null },

  // ── Testnets (deployed oracle contracts — active for testing) ────────────
  { key: "arb-sepolia",  name: "Arbitrum Sepolia",    chainId: 421614, rpcEnv: "ARB_SEPOLIA_RPC_URL",  rpcDefault: "https://sepolia-rollup.arbitrum.io/rpc", addrEnv: "ARB_SEPOLIA_ORACLE_ADDR",  addrDefault: "0xb819c63c02Ed5aB49017C0f3f2568A14624658b3" },
  { key: "eth-sepolia",  name: "Ethereum Sepolia",    chainId: 11155111, rpcEnv: "ETH_SEPOLIA_RPC_URL", rpcDefault: "https://ethereum-sepolia.publicnode.com", addrEnv: "ETH_SEPOLIA_ORACLE_ADDR",  addrDefault: "0xB07AD89a10f94B6D3bF2ab0B3a37988b1F37Db39" },
  { key: "base-sepolia", name: "Base Sepolia",        chainId: 84532,  rpcEnv: "BASE_SEPOLIA_RPC_URL", rpcDefault: "https://sepolia.base.org",              addrEnv: "BASE_SEPOLIA_ORACLE_ADDR", addrDefault: "0x7ADF5B7273883C50EFc005BA7EdD3F379Af9680C" },
  { key: "op-sepolia",   name: "Optimism Sepolia",    chainId: 11155420, rpcEnv: "OP_SEPOLIA_RPC_URL", rpcDefault: "https://sepolia.optimism.io",           addrEnv: "OP_SEPOLIA_ORACLE_ADDR",   addrDefault: "0x708193f93Fb897fbeA72e7e7D19237770F19E969" },
  { key: "bnb-testnet",  name: "BNB Testnet",         chainId: 97,     rpcEnv: "BNB_TESTNET_RPC_URL",  rpcDefault: "https://bsc-testnet-rpc.publicnode.com", addrEnv: "BNB_TESTNET_ORACLE_ADDR",  addrDefault: "0xf0e20F48D4c2c63DCAf4bad01471d29DEb921721" },
  { key: "0g-galileo",   name: "0G Galileo Testnet",  chainId: 16602,  rpcEnv: "ZG_GALILEO_RPC",       rpcDefault: "https://evmrpc-testnet.0g.ai",          addrEnv: "ZG_GALILEO_ORACLE_ADDR",   addrDefault: "0x0471B2BE25c2eBbAe7FAc17383F1692979F0A87C" },
];

// ── Canonical-registry validation (config/chain_registry.json) ───────────────
// The CHAINS table above is operator deployment config (env names, oracle
// addresses, RPC defaults) whose chainId values MUST equal the canonical
// registry ids — config/chain_registry.json is the single source of truth
// (P3-CONSOLIDATE matrix #17). Instead of trusting the literals, every entry
// is cross-checked against the registry at boot and the process refuses to
// start on drift (wrong id, unknown id, or an id belonging to a DIFFERENT
// chain than the entry's name claims).
const _OFF_REGISTRY_CHAINS = new Map([
  // Documented off-registry decisions (see tests/unit/test_backfill_chain_ids.py):
  ["hyperliquid", 999],   // HyperEVM's own native chain id (Task 21-c)
  ["0g-galileo",  16602], // 0G Galileo testnet (registry carries only 0G Mainnet)
]);
// Display-name aliases for entries whose relayer label shares no token with
// the registry display name of the same chain.
const _NAME_ALIASES = {
  "okt-chain": "OKB Chain (OKTC)",
  "bot-chain": "BotChain",
};
function _registryTokens(s) {
  const GENERIC = new Set(["mainnet", "testnet", "chain", "network", "evm", "l2", "one"]);
  return new Set(
    s.toLowerCase().split(/[^a-z0-9]+/).filter(t => t.length >= 2 && !GENERIC.has(t))
  );
}
(function validateChainsAgainstRegistry() {
  const regPath = new URL("../config/chain_registry.json", import.meta.url);
  let registry;
  try {
    registry = JSON.parse(fs.readFileSync(regPath, "utf-8"));
  } catch (e) {
    throw new Error(`relayer: canonical registry unreadable (${regPath}): ${e.message}`);
  }
  const idToName = new Map(registry.chains.map(c => [c.chainId, c.name]));
  for (const c of CHAINS) {
    const documented = _OFF_REGISTRY_CHAINS.get(c.key);
    if (documented !== undefined) {
      if (c.chainId !== documented) {
        throw new Error(
          `relayer: off-registry chain "${c.key}" changed id ${c.chainId} ` +
          `≠ documented ${documented} — update the decision + tests together`
        );
      }
      continue;
    }
    const regName = idToName.get(c.chainId);
    if (regName === undefined) {
      throw new Error(
        `relayer: chain "${c.key}" (chainId ${c.chainId}) is not in the canonical ` +
        `registry and not a documented off-registry chain — add it to the ` +
        `registry or record the off-registry decision`
      );
    }
    const entryName = _NAME_ALIASES[c.key] ?? c.name;
    const shared = _registryTokens(entryName).size > 0
      ? [..._registryTokens(entryName)].some(t => _registryTokens(regName).has(t))
      : false;
    if (!shared && entryName.toLowerCase().replace(/[^a-z0-9]/g, "") !== regName.toLowerCase().replace(/[^a-z0-9]/g, "")) {
      throw new Error(
        `relayer: chain "${c.key}" (chainId ${c.chainId}) claims name ` +
        `"${c.name}" but the registry says that id is "${regName}" — ` +
        `cross-chain id swap? Fix the entry or the alias map.`
      );
    }
  }
})();

const ABI = [
  "function publishSignal(bytes32 txId, uint256 packedData, bytes[] calldata signatures) external",
  "function quorumRequired() external view returns (uint256)",
  "function isValidator(address) external view returns (bool)",
];

// ── 0G ExecutionGate integration ─────────────────────────────────────────────
// When the relayer processes 0G Galileo, it ALSO pushes to the TRIONExecutionGate
// contract (separate from TRIONOracleV3) which implements the full 0G integration:
//   - beoHash: keccak256 of entity's behavioral DNA fingerprint
//   - daProofHash: deterministic 0G DA content hash for anomaly proof
//   - storageRoot: 0G Storage merkle root for FAISS behavioral index
const ZG_GATE_ADDR = process.env.ZG_EXECUTION_GATE_ADDR
  || "0xA85B49C73B5710d9ddB1CB5a94c52D0F33c4199b"; // 0G Mainnet
const ZG_GATE_RPC  = process.env.ZERO_G_RPC || "https://evmrpc.0g.ai";
const ZG_GATE_CHAIN = 16661; // 0G Mainnet (was 16602 Galileo testnet)
const ZG_GATE_EXPLORER = "https://chainscan.0g.ai";

const ZG_GATE_ABI = [
  "function publishSignal(bytes32 entityId, uint256 packedData, bytes32 beoHash, bytes32 daProofHash, string calldata storageRoot, bytes[] calldata signatures) external",
  "function isValidator(address) external view returns (bool)",
  "function beoVectorStorageRoot() external view returns (string memory)",
  "function quorumRequired() external view returns (uint256)",
];

// Persistent 0G gate relayer state
const ZG_STATE_FILE = "/tmp/trion_zg_gate_relayer.json";
const zgState = (() => {
  try { return JSON.parse(fs.readFileSync(ZG_STATE_FILE, "utf-8")); }
  catch { return { generated_at: null, contract: ZG_GATE_ADDR, entities: {} }; }
})();
function persistZGState() {
  try {
    const blob = JSON.stringify({ ...zgState, generated_at: new Date().toISOString() }, null, 2);
    fs.writeFileSync(ZG_STATE_FILE, blob);
    const pub = process.env.ORACLE_PUBLIC_DIR || "./akashic-oracle/public";
    fs.writeFileSync(`${pub}/zg_gate_state.json`, blob);
  } catch { /* non-fatal */ }
}

function classifyGateStatus(coherence, threshold) {
  const ratio = coherence / (threshold || 0.55);
  if (ratio >= 1.05) return 1n; // SAFE
  if (ratio >= 0.90) return 2n; // ELEVATED
  if (ratio >= 0.70) return 3n; // COLLAPSE
  return 4n;                    // HOSTILE
}

function packGateSignal(signal, blockNum) {
  const phi_t   = signal.coherence || signal.signal_value || 0.5;
  const theta   = signal.threshold || 0.55;
  const status  = classifyGateStatus(phi_t, theta);
  const drop    = BigInt(Math.max(0, Math.floor((theta - phi_t) / theta * 100 * 10000)));
  const phi_t32 = clampU32(phi_t * 1_000_000);
  const theta32 = clampU32(theta * 1_000_000);
  const block64 = clampU64(blockNum);
  const ts64    = clampU64(Math.floor(Date.now() / 1000));

  return {
    packed: (ts64 << 168n) | (block64 << 104n) | (drop << 72n)
          | (theta32 << 40n) | (phi_t32 << 8n) | status,
    status: Number(status),
    phi_t, theta,
    statusLabel: ["","SAFE","ELEVATED","COLLAPSE","HOSTILE"][Number(status)] || "UNKNOWN",
  };
}

function deriveBeoHash(entity, signal) {
  const coh = signal.coherence_score ?? signal.coherence ?? 0.5;
  const dna = [entity, coh.toFixed(6), signal.signal_id || ""].join(":");
  return ethers.keccak256(ethers.toUtf8Bytes(dna));
}

function deriveDAProofHash(entity, signal, status) {
  const proof = JSON.stringify({ entity, phi_t: signal.coherence || 0.5,
    theta: signal.threshold || 0.55, status, ts: Date.now(), chain: "0G-Galileo" });
  return "0x" + createHash("sha256").update(proof).digest("hex");
}

let zgStorageRoot = "0g-storage:galileo:f2500e57d9c8864c5e0c527b25600cf5";
let zgProvider    = null;
let zgWallet      = null;
let zgGate        = null;

async function initZGGate(wallet) {
  try {
    zgProvider = new ethers.JsonRpcProvider(ZG_GATE_RPC, ZG_GATE_CHAIN);
    zgWallet   = wallet ? wallet.connect(zgProvider) : null;
    zgGate     = new ethers.Contract(ZG_GATE_ADDR, ZG_GATE_ABI, zgWallet || zgProvider);

    // Read storage root from chain
    const root = await zgGate.beoVectorStorageRoot().catch(() => null);
    if (root && root.length > 4) zgStorageRoot = root;
    console.log(` 0G Gate     : ${ZG_GATE_ADDR}`);
    console.log(` 0G Explorer : ${ZG_GATE_EXPLORER}/address/${ZG_GATE_ADDR}`);
    console.log(` 0G Storage  : ${zgStorageRoot}`);
  } catch (e) {
    console.warn(` 0G Gate init failed: ${e.message?.slice(0, 60)} — gate push disabled`);
    zgGate = null;
  }
}

async function pushToZGGate(entity, signal) {
  if (!zgGate || !zgWallet) return; // skip in DRY_RUN or if init failed

  try {
    const blockNum = await zgProvider.getBlockNumber();
    const { packed, statusLabel, phi_t, theta } = packGateSignal(signal, blockNum);
    const entityId    = ethers.keccak256(ethers.toUtf8Bytes(entity));
    const beoHash     = deriveBeoHash(entity, signal);
    const daProofHash = deriveDAProofHash(entity, signal, statusLabel);

    // Build EIP-191 quorum signature for TRIONExecutionGate.publishSignal.
    // Contract reconstructs: keccak256(abi.encodePacked(block.chainid, address(this), entityId, packedData))
    const zgInner = ethers.solidityPackedKeccak256(
      ["uint256", "address", "bytes32", "uint256"],
      [ZG_GATE_CHAIN, ZG_GATE_ADDR, entityId, packed]
    );
    const zgSig = await zgWallet.signMessage(ethers.getBytes(zgInner));

    const feeData = await zgProvider.getFeeData();
    const tx = await zgGate.publishSignal(
      entityId, packed, beoHash, daProofHash, zgStorageRoot, [zgSig],
      { gasLimit: 300_000, gasPrice: feeData.gasPrice }
    );
    const receipt = await tx.wait(1);
    console.log(`  [0G-GATE   ] ${entity.slice(0,12)}… → ${statusLabel}  Φ=${phi_t.toFixed(4)}  block=${receipt.blockNumber}  hash=${receipt.hash.slice(0,18)}…`);

    zgState.entities[entity] = {
      entity_id: entityId, status: statusLabel, phi_t, theta,
      mode: "REAL", tx_hash: receipt.hash, block: receipt.blockNumber,
      tx_url: `${ZG_GATE_EXPLORER}/tx/${receipt.hash}`,
      updated_at: new Date().toISOString(),
    };
    persistZGState();
  } catch (e) {
    const msg = e?.shortMessage || e?.message || String(e);
    // Log only first 80 chars to avoid noise
    if (!msg.includes("duplicate")) {
      console.warn(`  [0G-GATE   ] ${entity.slice(0,12)}… gate push failed: ${msg.slice(0,80)}`);
    }
    zgState.entities[entity] = {
      ...zgState.entities[entity],
      mode: "ERROR", last_error: msg.slice(0, 120),
      updated_at: new Date().toISOString(),
    };
    persistZGState();
  }
}

// ── Active chain set ─────────────────────────────────────────────────────────
const activeChains = [];
for (const c of CHAINS) {
  const rpc  = process.env[c.rpcEnv] || c.rpcDefault;
  const addr = process.env[c.addrEnv] || c.addrDefault || null;
  activeChains.push({ ...c, rpc, addr });
}

// ── Signal packing ───────────────────────────────────────────────────────────
function clampU32(x) {
  if (x < 0) return 0n;
  const v = BigInt(Math.floor(x));
  const max = (1n << 32n) - 1n;
  return v > max ? max : v;
}

function clampU64(x) {
  if (x < 0) return 0n;
  const v = BigInt(Math.floor(x));
  const max = (1n << 64n) - 1n;
  return v > max ? max : v;
}

/**
 * Pack a TRION signal into the uint256 layout expected by TRIONOracleV3.
 *  status[8] | coherence[32] | threshold[32] | blockNum[64] | timestamp[64]
 *
 * Oracle v2 response uses `coherence_score` (not `coherence` / `signal_value`).
 * We support both field names for forward/backward compatibility.
 */
function packSignal(signal) {
  const coh = signal.coherence_score ?? signal.coherence ?? signal.signal_value ?? 0.5;
  const thr = signal.threshold ?? 0.55;
  const isSafe = coh >= thr ? 1n : 0n;
  const coherence = clampU32(coh * 1_000_000);
  const threshold = clampU32(thr * 1_000_000);
  const blockNum  = clampU64(signal.block_num || Date.now() / 1000 | 0);
  const timestamp = clampU64(Math.floor(Date.now() / 1000));

  return (timestamp << 136n)
       | (blockNum  << 72n)
       | (threshold << 40n)
       | (coherence << 8n)
       | isSafe;
}

function deriveTxId(entity, signal) {
  // bytes32 = exactly 64 hex chars. Oracle's signal_id may be a UUID (with
  // dashes) or a hex string. Strip dashes so UUIDs become pure hex.
  const rawSig  = (signal.signal_id || "").replace(/^0x/, "").replace(/-/g, "").toLowerCase();
  // If after stripping dashes the result is pure hex, use it; otherwise hash it.
  const sigHex  = /^[0-9a-f]+$/.test(rawSig)
    ? rawSig
    : ethers.keccak256(ethers.toUtf8Bytes(signal.signal_id || "")).slice(2);
  const sigPart = sigHex.padEnd(32, "0").slice(0, 32); // 16 bytes = 32 hex
  const ts      = Math.floor(Date.now() / 1000).toString(16).padStart(16, "0");
  // Entity may be a hex address (0x…) OR a string like "uniswap"/"aave".
  const raw = (entity || "").replace(/^0x/, "").toLowerCase();
  const isHex = /^[0-9a-f]+$/.test(raw);
  const entHex  = isHex
    ? raw.padStart(40, "0")
    : ethers.keccak256(ethers.toUtf8Bytes(entity || "")).slice(2); // 64 hex
  const entTail = entHex.slice(-16); // last 8 bytes
  const hex     = (sigPart + ts + entTail).padEnd(64, "0").slice(0, 64);
  return "0x" + hex;
}

// Persistent per-chain publish state, surfaced by the Oracle coverage endpoint
const RELAYER_STATE_FILE = "/tmp/trion_evm_relayer_latest.json";
const relayerState = (() => {
  try { return JSON.parse(fs.readFileSync(RELAYER_STATE_FILE, "utf-8")); }
  catch { return { generated_at: null, chains: {} }; }
})();

function persistRelayerState() {
  try {
    fs.writeFileSync(
      RELAYER_STATE_FILE,
      JSON.stringify({ ...relayerState, generated_at: new Date().toISOString() }, null, 2),
    );
  } catch { /* non-fatal */ }
}

// ── On-chain submission ──────────────────────────────────────────────────────
async function pushToChain(chain, entity, signal, wallet) {
  const txId = deriveTxId(entity, signal);
  const packed = packSignal(signal);

  if (DRY_RUN || !chain.addr) {
    const reason = DRY_RUN ? "DRY_RUN (no RELAYER_PRIVATE_KEY and no KMS provider)" : `no ${chain.addrEnv}`;
    console.log(`  [${chain.key.padEnd(10)}] ${reason} — would publishSignal(txId=${txId.slice(0,18)}…, packed=0x${packed.toString(16).slice(0,16)}…)`);
    relayerState.chains[chain.key] = {
      chain_id: chain.chainId, oracle_address: chain.addr || null,
      mode: "DRY_RUN", reason, last_tx_id: txId, updated_at: new Date().toISOString(),
    };
    persistRelayerState();
    return { ok: true, dry: true };
  }

  try {
    const provider = new ethers.JsonRpcProvider(chain.rpc, chain.chainId);
    const signer = wallet.connect(provider);
    const oracle = new ethers.Contract(chain.addr, ABI, signer);

    // Build the digest the contract reconstructs in publishSignal:
    //   ethSignedMessageHash(keccak256(abi.encodePacked(chainId, oracleAddr, txId, packedData)))
    const inner = ethers.solidityPackedKeccak256(
      ["uint256", "address", "bytes32", "uint256"],
      [chain.chainId, chain.addr, txId, packed]
    );
    // ethers v6 signMessage handles the EIP-191 prefix when given raw bytes.
    const sig = await signer.signMessage(ethers.getBytes(inner));

    // Submit to chain with retry on transient errors (network / RPC drops).
    // 4xx contract reverts and quorum failures are NOT retried.
    const receipt = await withRetry(`push:${chain.key}`, async () => {
      const tx = await oracle.publishSignal(txId, packed, [sig]);
      return await tx.wait(1);
    });
    console.log(`  [${chain.key.padEnd(10)}] published txId=${txId.slice(0,18)}… block=${receipt.blockNumber} hash=${receipt.hash}`);
    const prev = relayerState.chains[chain.key] || {};
    relayerState.chains[chain.key] = {
      ...prev,
      chain_id: chain.chainId, oracle_address: chain.addr,
      mode: "REAL", last_status: "ok",
      last_tx_id: txId,
      last_tx_hash: receipt.hash,
      last_block: receipt.blockNumber,
      last_real_tx_hash: receipt.hash,           // preserved across later failures
      last_real_block: receipt.blockNumber,
      last_real_at: new Date().toISOString(),
      last_signal_value: signal.signal_value, last_signal_type: signal.signal_type,
      updated_at: new Date().toISOString(),
      last_error: null,
    };
    persistRelayerState();
    return { ok: true, hash: receipt.hash };
  } catch (e) {
    const msg = e?.shortMessage || e?.message || String(e);
    console.error(`  [${chain.key.padEnd(10)}] FAILED: ${msg}`);
    const prev = relayerState.chains[chain.key] || {};
    // If we had a prior successful publish, mark DEGRADED (latest attempt failed);
    // otherwise REJECTED. Either way, last_real_* fields are preserved.
    const mode = prev.last_real_tx_hash ? "DEGRADED" : "REJECTED";
    relayerState.chains[chain.key] = {
      ...prev,
      chain_id: chain.chainId, oracle_address: chain.addr,
      mode, last_status: "error", last_error: msg,
      last_attempt_at: new Date().toISOString(),
    };
    persistRelayerState();
    return { ok: false, error: msg };
  }
}

// ── Retry helper ─────────────────────────────────────────────────────────────
// Exponential-backoff retry for transient network failures.  Distinguishes
// retryable errors (timeouts, 5xx, network drops) from permanent ones (4xx
// auth / contract revert) so we don't waste cycles hammering a broken endpoint.
const MAX_RETRIES    = parseInt(process.env.RELAYER_MAX_RETRIES    || "3",    10);
const RETRY_BASE_MS = parseInt(process.env.RELAYER_RETRY_BASE_MS || "500", 10);

function isRetryableError(err) {
  if (!err) return false;
  // Network / timeout errors are retryable
  if (err.code === "ECONNABORTED" || err.code === "ETIMEDOUT" ||
      err.code === "ENOTFOUND"   || err.code === "ECONNRESET") return true;
  // 5xx server errors are retryable
  const status = err.response?.status;
  if (status && status >= 500 && status < 600) return true;
  // 429 Too Many Requests is retryable
  if (status === 429) return true;
  // Contract reverts / 4xx are NOT retryable
  return false;
}

async function withRetry(label, fn) {
  let lastErr = null;
  for (let attempt = 0; attempt <= MAX_RETRIES; attempt++) {
    try {
      return await fn(attempt);
    } catch (e) {
      lastErr = e;
      if (!isRetryableError(e) || attempt === MAX_RETRIES) {
        if (attempt > 0) {
          console.warn(`  [${label}] giving up after ${attempt + 1} attempt(s): ${(e?.shortMessage || e?.message || String(e)).slice(0, 100)}`);
        }
        throw e;
      }
      const delay = RETRY_BASE_MS * Math.pow(2, attempt) + Math.floor(Math.random() * 200);
      console.warn(`  [${label}] attempt ${attempt + 1} failed (${(e?.shortMessage || e?.message || String(e)).slice(0, 80)}); retrying in ${delay}ms`);
      await new Promise(r => setTimeout(r, delay));
    }
  }
  throw lastErr;
}

// ── Main loop ────────────────────────────────────────────────────────────────
async function pollOracle(entity) {
  const url = `${ORACLE_API_URL}/api/v1/signal/${encodeURIComponent(entity)}`;
  return withRetry(`poll:${entity.slice(0, 12)}`, () =>
    axios.get(url, { timeout: 45000 }).then(r => r.data)
  );
}

// ── Reflexive self-halt ────────────────────────────────────────────────────
// Before publishing anything, check TRION's own self-verification status.
// If TRION's own coherence has dropped below the SILENCE threshold, the
// protocol does not trust its own signal generation right now — so the
// relayer must not broadcast anything on-chain this cycle.
async function checkSelfHalt() {
  try {
    const r = await axios.get(`${ORACLE_API_URL}/api/v1/self`, { timeout: 8000 });
    const status = r.data?.status;
    if (status === "SILENCED") {
      console.warn(`[SELF-HALT] TRION self-coherence=${r.data.coherence} < threshold=${r.data.threshold} (limiting=${r.data.limiting_plane}) — skipping this cycle, no signals will be published`);
      return true;
    }
    return false;
  } catch (e) {
    // If self-status is unreachable the relayer cannot confirm its own oracle
    // is healthy — HALT this cycle (fail-closed).  Publishing signals from an
    // oracle whose health is unknown risks propagating incorrect data on-chain.
    console.warn(`[SELF-HALT] could not reach /api/v1/self (${e.message}) — HALTING this cycle (fail-closed)`);
    return true;
  }
}

async function tick(wallet) {
  const stamp = new Date().toISOString();
  console.log(`\n[${stamp}] tick — entities=${MONITORED.length}, active_chains=${activeChains.length}, mode=${DRY_RUN ? "DRY_RUN" : "LIVE"}`);

  if (await checkSelfHalt()) {
    return;
  }

  for (const entity of MONITORED) {
    let signal;
    try {
      signal = await pollOracle(entity);
    } catch (e) {
      console.error(` [${entity}] oracle fetch failed: ${e.message}`);
      continue;
    }
    const coh  = signal.coherence_score ?? signal.coherence ?? signal.signal_value ?? 0.5;
    const thr  = signal.threshold ?? 0.55;
    const safe = coh >= thr;
    console.log(` [${entity}] φ=${coh.toFixed(4)} θ=${thr.toFixed(4)} → ${safe ? "SAFE" : "INTERCEPT"}  arch=${signal.archetype ?? signal.signal_type ?? "?"}`);

    for (const chain of activeChains) {
      // eslint-disable-next-line no-await-in-loop
      await pushToChain(chain, entity, signal, wallet);
    }

    // Also push to 0G ExecutionGate (live mode only — no-op in DRY_RUN)
    // eslint-disable-next-line no-await-in-loop
    await pushToZGGate(entity, signal);
  }
}

async function main() {
  console.log("===============================================================");
  console.log(" TRION MULTI-CHAIN RELAYER");
  console.log("===============================================================");
  console.log(` Oracle API     : ${ORACLE_API_URL}`);
  console.log(` Monitored      : ${MONITORED.join(", ")}`);
  console.log(` Poll interval  : ${POLL_INTERVAL_MS}ms`);
  console.log(` Mode           : ${DRY_RUN ? "DRY_RUN (set RELAYER_PRIVATE_KEY or KMS_PROVIDER to push on-chain)" : "LIVE"}`);
  console.log(` KMS provider   : ${KMS_PROVIDER}`);
  console.log("");
  console.log(" Chain registry:");
  for (const c of activeChains) {
    const status = c.addr ? `→ ${c.addr}` : `[no ${c.addrEnv} — would skip in LIVE mode]`;
    console.log(`   ${c.name.padEnd(22)} chain_id=${String(c.chainId).padEnd(8)} ${status}`);
  }
  console.log("");

  // ── Wallet / signer creation ──────────────────────────────────────────────
  // Whitepaper Finding #10: "HSM (Thales Luna 7 / YubiHSM 2) — NON-NEGOTIABLE"
  // The relayer now uses the KMS abstraction layer to support:
  //   KMS_PROVIDER=env (dev)        — RELAYER_PRIVATE_KEY plaintext
  //   KMS_PROVIDER=aws (production) — AWS KMS
  //   KMS_PROVIDER=gcp (production) — Google Cloud KMS
  //   KMS_PROVIDER=yubihsm (prod)   — YubiHSM 2 hardware
  //   KMS_PROVIDER=pkcs11 (prod)    — Thales Luna 7 / generic PKCS#11 HSM
  //
  // The KMS abstraction layer (relayer/kms_provider.js) returns a signer
  // with signMessage (EIP-191 quorum signatures) AND signDigest (raw 32-byte
  // digest). KmsEthersSigner wraps it in an ethers-compatible AbstractSigner
  // so the SAME KMS/HSM key signs BOTH the quorum signatures AND the actual
  // transactions (EIP-155/EIP-1559) — the private key never leaves the
  // KMS/HSM boundary. Only the env provider materializes a plaintext key.
  let wallet = null;
  if (!DRY_RUN) {
    if (KMS_PROVIDER === "env") {
      // Backward-compatible path: use ethers.Wallet directly
      wallet = new ethers.Wallet(PRIVATE_KEY.startsWith("0x") ? PRIVATE_KEY : "0x" + PRIVATE_KEY);
      console.log(` Validator addr : ${wallet.address}`);
      console.log(` KMS provider   : env (plaintext — dev only)`);
    } else {
      // HSM/KMS path: ONE signer for quorum signatures AND transaction signing
      try {
        const { createSigner, KmsEthersSigner } = await import("./kms_provider.js");
        const kmsSigner = await createSigner();
        wallet = new KmsEthersSigner(kmsSigner);
        console.log(` Validator addr : ${kmsSigner.address}`);
        console.log(` KMS provider   : ${kmsSigner.provider}`);
        console.log(` KMS tx signing : ACTIVE — HSM/KMS-backed transaction signing (signDigest over keccak256(unsigned tx))`);
        if (PRIVATE_KEY) {
          console.warn(` KMS note       : RELAYER_PRIVATE_KEY is set but IGNORED — KMS_PROVIDER=${kmsSigner.provider} takes precedence for all signing`);
        }
      } catch (e) {
        console.error(`FATAL: KMS signer creation failed: ${e.message}`);
        console.error("Set RELAYER_PRIVATE_KEY for dev or KMS_PROVIDER + provider-specific env for production.");
        process.exit(1);
      }
    }
  }
  console.log("");

  // Initialise 0G ExecutionGate connection (reads storageRoot from chain)
  await initZGGate(wallet);
  console.log("");

  // Run once immediately, then every POLL_INTERVAL_MS forever.
  while (true) {
    try {
      // eslint-disable-next-line no-await-in-loop
      await tick(wallet);
    } catch (e) {
      console.error(`tick error: ${e?.message || e}`);
    }
    // eslint-disable-next-line no-await-in-loop
    await new Promise(r => setTimeout(r, POLL_INTERVAL_MS));
  }
}

main().catch(e => {
  console.error("relayer fatal:", e);
  process.exit(1);
});
