/**
 * TRION EVM Family Relayer
 * ========================
 *
 * This is the **DEFAULT** relayer for the EVM VM family. It supersedes the
 * EVM-half of relayer/relayer.js: the same W3-M fail-closed signal
 * validation, the same EIP-191 single-signature quorum submission, and the
 * same 0G ExecutionGate integration — but constrained to EVM chains and
 * invokable either standalone or via the unified relayer/index.js.
 *
 * Bit layout (publishSignal packedData, uint256):
 *   bits   0..7    : status   (uint8 — 1 = SAFE, 0 = COLLAPSE_INTERCEPTED)
 *   bits   8..39   : coherence (uint32 — coherence × 1e6, capped at 2^32-1)
 *   bits  40..71   : threshold (uint32 — threshold × 1e6, capped at 2^32-1)
 *   bits  72..135  : block_num (uint64)
 *   bits 136..199  : timestamp (uint64 — unix seconds)
 *
 * Truth-in-advertising (W3-M): this relayer submits exactly ONE signature
 * — its own. Multi-sig aggregation is NOT implemented; the contract is
 * the authorizer.
 *
 * Usage:
 *   node relayer/families/evm.js --dry-run         # default — no on-chain submit
 *   node relayer/families/evm.js --live            # LIVE: requires RELAYER_PRIVATE_KEY / KMS
 *   RELAYER_PRIVATE_KEY=0x... node relayer/families/evm.js --live
 *
 * Required env (live mode):
 *   RELAYER_PRIVATE_KEY      hex private key (0x… or 64 hex chars) for a registered validator
 *                            (dev only — KMS_PROVIDER=env)
 *   … or KMS_PROVIDER=aws|gcp|yubihsm|pkcs11 + the provider-specific env
 *     vars (see relayer/kms_provider.js) for HSM/KMS-backed signing
 *   ORACLE_API_URL           http://127.0.0.1:5000          (default)
 *   MONITORED_ENTITIES       comma-separated list (default: TRION oracle contract)
 *   POLL_INTERVAL_MS         default 30000
 *   ETH_MAINNET_ORACLE_ADDR, ARB_MAINNET_ORACLE_ADDR, ...   per-chain overrides
 *
 * If RELAYER_PRIVATE_KEY is missing AND no KMS/HSM provider is configured,
 * the relayer runs in DRY_RUN mode and logs the would-be transaction for
 * every chain.
 */

import { ethers } from "ethers";
import axios from "axios";
import { createHash } from "node:crypto";
import fs from "node:fs";

import {
  ORACLE_API_URL, POLL_INTERVAL_MS,
  log, parseArgs, validateSignal, signalFields,
  fetchSignal, checkSelfHalt, withRetry, persistState,
} from "./common.js";

export const FAMILY = "EVM";

// ── EVM chain deployment config ──────────────────────────────────────────────
// Each entry pairs a canonical registry chainId with operator deployment
// config (env names for RPC + oracle address override, RPC default, optional
// baked-in oracle address from the deploy manifests). This is the same table
// that powered relayer/relayer.js — preserved here so the per-VM-family
// architecture is a strict superset of the legacy EVM relayer.
export const CHAINS = [
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

  // ── BOT Chain (AI-agent EVM L1) — also handled by botchain.js family
  //    module (chains/botchain/execute.ts); leaving the entry here so the
  //    EVM relayer's per-chain preflight can still see its RPC + chainId.
  { key: "bot-chain",      name: "BOT Chain",             chainId: 677,       rpcEnv: "BOT_CHAIN_RPC_URL",    rpcDefault: "https://rpc.botchain.ai",                    addrEnv: "BOT_CHAIN_ORACLE_ADDR",    addrDefault: null },

  // ── Testnets (deployed oracle contracts — active for testing) ────────────
  { key: "arb-sepolia",  name: "Arbitrum Sepolia",    chainId: 421614, rpcEnv: "ARB_SEPOLIA_RPC_URL",  rpcDefault: "https://sepolia-rollup.arbitrum.io/rpc", addrEnv: "ARB_SEPOLIA_ORACLE_ADDR",  addrDefault: "0xb819c63c02Ed5aB49017C0f3f2568A14624658b3" },
  { key: "eth-sepolia",  name: "Ethereum Sepolia",    chainId: 11155111, rpcEnv: "ETH_SEPOLIA_RPC_URL", rpcDefault: "https://ethereum-sepolia.publicnode.com", addrEnv: "ETH_SEPOLIA_ORACLE_ADDR",  addrDefault: "0x590CD9B5ad34b735d8c262a462d9bc82E57C4DA5" },
  { key: "base-sepolia", name: "Base Sepolia",        chainId: 84532,  rpcEnv: "BASE_SEPOLIA_RPC_URL", rpcDefault: "https://sepolia.base.org",              addrEnv: "BASE_SEPOLIA_ORACLE_ADDR", addrDefault: "0x7ADF5B7273883C50EFc005BA7EdD3F379Af9680C" },
  { key: "op-sepolia",   name: "Optimism Sepolia",    chainId: 11155420, rpcEnv: "OP_SEPOLIA_RPC_URL", rpcDefault: "https://sepolia.optimism.io",           addrEnv: "OP_SEPOLIA_ORACLE_ADDR",   addrDefault: "0x708193f93Fb897fbeA72e7e7D19237770F19E969" },
  { key: "bnb-testnet",  name: "BNB Testnet",         chainId: 97,     rpcEnv: "BNB_TESTNET_RPC_URL",  rpcDefault: "https://bsc-testnet-rpc.publicnode.com", addrEnv: "BNB_TESTNET_ORACLE_ADDR",  addrDefault: "0xf0e20F48D4c2c63DCAf4bad01471d29DEb921721" },
  { key: "0g-galileo",   name: "0G Galileo Testnet",  chainId: 16602,  rpcEnv: "ZG_GALILEO_RPC",       rpcDefault: "https://evmrpc-testnet.0g.ai",          addrEnv: "ZG_GALILEO_ORACLE_ADDR",   addrDefault: "0x0471B2BE25c2eBbAe7FAc17383F1692979F0A87C" },
];

// ── Canonical-registry validation (config/chain_registry.json) ───────────────
// Cross-check every entry's chainId against the canonical registry at boot.
// The process refuses to start on drift (wrong id, unknown id, or an id
// belonging to a DIFFERENT chain than the entry's name claims).
const _OFF_REGISTRY_CHAINS = new Map([
  ["hyperliquid", 999],
  ["0g-galileo",  16602],
]);
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
export function _validateChainsAgainstRegistry() {
  const regPath = new URL("../../config/chain_registry.json", import.meta.url);
  const registry = JSON.parse(fs.readFileSync(regPath, "utf-8"));
  const idToName = new Map(registry.chains.map(c => [c.chainId, c.name]));
  for (const c of CHAINS) {
    const documented = _OFF_REGISTRY_CHAINS.get(c.key);
    if (documented !== undefined) {
      if (c.chainId !== documented) {
        throw new Error(
          `evm: off-registry chain "${c.key}" changed id ${c.chainId} ` +
          `≠ documented ${documented} — update the decision + tests together`
        );
      }
      continue;
    }
    const regName = idToName.get(c.chainId);
    if (regName === undefined) {
      throw new Error(
        `evm: chain "${c.key}" (chainId ${c.chainId}) is not in the canonical ` +
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
        `evm: chain "${c.key}" (chainId ${c.chainId}) claims name ` +
        `"${c.name}" but the registry says that id is "${regName}" — ` +
        `cross-chain id swap? Fix the entry or the alias map.`
      );
    }
  }
}

const ABI = [
  "function publishSignal(bytes32 txId, uint256 packedData, bytes[] calldata signatures) external",
  "function quorumRequired() external view returns (uint256)",
  "function isValidator(address) external view returns (bool)",
];

// ── 0G ExecutionGate integration ─────────────────────────────────────────────
const ZG_GATE_ADDR = process.env.ZG_EXECUTION_GATE_ADDR
  || "0xA85B49C73B5710d9ddB1CB5a94c52D0F33c4199b";
const ZG_GATE_RPC  = process.env.ZERO_G_RPC || "https://evmrpc.0g.ai";
const ZG_GATE_CHAIN = 16661;
const ZG_GATE_EXPLORER = "https://chainscan.0g.ai";

const ZG_GATE_ABI = [
  "function publishSignal(bytes32 entityId, uint256 packedData, bytes32 beoHash, bytes32 daProofHash, string calldata storageRoot, bytes[] calldata signatures) external",
  "function isValidator(address) external view returns (bool)",
  "function beoVectorStorageRoot() external view returns (string memory)",
  "function quorumRequired() external view returns (uint256)",
];

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
  if (ratio >= 1.05) return 1n;
  if (ratio >= 0.90) return 2n;
  if (ratio >= 0.70) return 3n;
  return 4n;
}

function packGateSignal(signal, blockNum) {
  const err = validateSignal(signal);
  if (err) throw new Error(`refusing to pack invalid gate signal: ${err}`);
  const { coh: phi_t, thr: theta } = signalFields(signal);
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
  const { coh } = signalFields(signal);
  const dna = [entity, coh.toFixed(6), signal.signal_id || ""].join(":");
  return ethers.keccak256(ethers.toUtf8Bytes(dna));
}

function deriveDAProofHash(entity, signal, status) {
  const { coh: phi_t, thr: theta } = signalFields(signal);
  const proof = JSON.stringify({ entity, phi_t, theta, status, ts: Date.now(), chain: "0G-Galileo" });
  return "0x" + createHash("sha256").update(proof).digest("hex");
}

let zgStorageRoot = "0g-storage:galileo:f2500e57d9c8864c5e0c527b25600cf5";
let zgProvider = null, zgWallet = null, zgGate = null;

async function initZGGate(wallet) {
  try {
    zgProvider = new ethers.JsonRpcProvider(ZG_GATE_RPC, ZG_GATE_CHAIN);
    zgWallet   = wallet ? wallet.connect(zgProvider) : null;
    zgGate     = new ethers.Contract(ZG_GATE_ADDR, ZG_GATE_ABI, zgWallet || zgProvider);
    const root = await zgGate.beoVectorStorageRoot().catch(() => null);
    if (root && root.length > 4) zgStorageRoot = root;
    log(FAMILY, `0G Gate: ${ZG_GATE_ADDR}`);
    log(FAMILY, `0G Explorer: ${ZG_GATE_EXPLORER}/address/${ZG_GATE_ADDR}`);
    log(FAMILY, `0G Storage root: ${zgStorageRoot}`);
  } catch (e) {
    log(FAMILY, `0G Gate init failed: ${e.message?.slice(0, 60)} — gate push disabled`);
    zgGate = null;
  }
}

async function pushToZGGate(entity, signal) {
  if (!zgGate || !zgWallet) return;
  const verr = validateSignal(signal);
  if (verr) {
    console.warn(`  [0G-GATE   ] ${entity.slice(0,12)}… SKIPPED — invalid oracle signal: ${verr}`);
    return;
  }
  try {
    const blockNum = await zgProvider.getBlockNumber();
    const { packed, statusLabel, phi_t, theta } = packGateSignal(signal, blockNum);
    const entityId    = ethers.keccak256(ethers.toUtf8Bytes(entity));
    const beoHash     = deriveBeoHash(entity, signal);
    const daProofHash = deriveDAProofHash(entity, signal, statusLabel);
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

export function packSignal(signal) {
  const err = validateSignal(signal);
  if (err) throw new Error(`refusing to pack invalid signal: ${err}`);
  const { coh, thr } = signalFields(signal);
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

export function deriveTxId(entity, signal) {
  const rawSig  = (signal.signal_id || "").replace(/^0x/, "").replace(/-/g, "").toLowerCase();
  const sigHex  = /^[0-9a-f]+$/.test(rawSig)
    ? rawSig
    : ethers.keccak256(ethers.toUtf8Bytes(signal.signal_id || "")).slice(2);
  const sigPart = sigHex.padEnd(32, "0").slice(0, 32);
  const ts      = Math.floor(Date.now() / 1000).toString(16).padStart(16, "0");
  const raw = (entity || "").replace(/^0x/, "").toLowerCase();
  const isHex = /^[0-9a-f]+$/.test(raw);
  const entHex  = isHex
    ? raw.padStart(40, "0")
    : ethers.keccak256(ethers.toUtf8Bytes(entity || "")).slice(2);
  const entTail = entHex.slice(-16);
  const hex     = (sigPart + ts + entTail).padEnd(64, "0").slice(0, 64);
  return "0x" + hex;
}

const RELAYER_STATE_FILE = "/tmp/trion_evm_relayer_latest.json";
const relayerState = (() => {
  try { return JSON.parse(fs.readFileSync(RELAYER_STATE_FILE, "utf-8")); }
  catch { return { generated_at: null, chains: {} }; }
})();
function persistRelayerState() {
  persistState(FAMILY, relayerState);
}

// ── On-chain submission ──────────────────────────────────────────────────────
async function pushToChain(chain, entity, signal, wallet, dryRun) {
  const verr = validateSignal(signal);
  if (verr) {
    console.warn(`  [${chain.key.padEnd(10)}] SKIPPED — invalid oracle signal for ${entity.slice(0,12)}…: ${verr}`);
    return { ok: false, skipped: true, error: `invalid signal: ${verr}` };
  }
  const txId = deriveTxId(entity, signal);
  const packed = packSignal(signal);

  if (dryRun || !chain.addr) {
    const reason = dryRun ? "DRY_RUN (no RELAYER_PRIVATE_KEY and no KMS provider)" : `no ${chain.addrEnv}`;
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
    const inner = ethers.solidityPackedKeccak256(
      ["uint256", "address", "bytes32", "uint256"],
      [chain.chainId, chain.addr, txId, packed]
    );
    const sig = await signer.signMessage(ethers.getBytes(inner));
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
      last_tx_id: txId, last_tx_hash: receipt.hash,
      last_block: receipt.blockNumber,
      last_real_tx_hash: receipt.hash,
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

// ── Wallet / signer ──────────────────────────────────────────────────────────
async function buildWallet(dryRun, privateKey, kmsProvider) {
  if (dryRun) return null;
  if (kmsProvider === "env") {
    const pk = privateKey?.startsWith("0x") ? privateKey : "0x" + privateKey;
    const w = new ethers.Wallet(pk);
    log(FAMILY, `Validator addr: ${w.address}`);
    log(FAMILY, `KMS provider: env (plaintext — dev only)`);
    return w;
  }
  try {
    const { createSigner, KmsEthersSigner } = await import("../kms_provider.js");
    const kmsSigner = await createSigner();
    const w = new KmsEthersSigner(kmsSigner);
    log(FAMILY, `Validator addr: ${kmsSigner.address}`);
    log(FAMILY, `KMS provider: ${kmsSigner.provider}`);
    return w;
  } catch (e) {
    console.error(`FATAL: KMS signer creation failed: ${e.message}`);
    console.error("Set RELAYER_PRIVATE_KEY for dev or KMS_PROVIDER + provider-specific env for production.");
    process.exit(1);
  }
}

async function preflightChainAccess(wallet, activeChains, dryRun) {
  if (!wallet) return;
  for (const chain of activeChains) {
    if (dryRun || !chain.addr) continue;
    try {
      const provider = new ethers.JsonRpcProvider(chain.rpc, chain.chainId, { staticNetwork: true });
      const oracle = new ethers.Contract(chain.addr, ABI, provider);
      const [isValidator, quorumRequired] = await Promise.all([
        oracle.isValidator(wallet.address).catch(() => null),
        oracle.quorumRequired().catch(() => null),
      ]);
      if (isValidator === false) {
        console.warn(
          `  [preflight ] ${chain.key}: signer ${wallet.address} is NOT a registered validator on this oracle — publishSignal will revert until the validator registry is updated`
        );
      }
      if (quorumRequired !== null && Number(quorumRequired) > 1) {
        console.warn(
          `  [preflight ] ${chain.key}: quorumRequired=${Number(quorumRequired)} but this relayer submits ONE signature — submission will be rejected until peer validator signatures are aggregated (multi-sig collection is NOT implemented; see header)`
        );
      }
    } catch (e) {
      console.warn(`  [preflight ] ${chain.key}: preflight unreachable (${(e?.message || e).slice(0, 60)}) — continuing, the contract remains the authority`);
    }
  }
}

// ── Main loop ────────────────────────────────────────────────────────────────
async function pollOracle(entity) {
  const url = `${ORACLE_API_URL}/api/v1/signal/${encodeURIComponent(entity)}`;
  return withRetry(`poll:${entity.slice(0, 12)}`, () =>
    axios.get(url, { timeout: 45000 }).then(r => r.data)
  );
}

async function tick(wallet, monitored, activeChains, dryRun) {
  const stamp = new Date().toISOString();
  log(FAMILY, `tick — entities=${monitored.length}, active_chains=${activeChains.length}, mode=${dryRun ? "DRY_RUN" : "LIVE"}`);
  if (await checkSelfHalt(FAMILY)) return;
  for (const entity of monitored) {
    let signal;
    try {
      signal = await pollOracle(entity);
    } catch (e) {
      console.error(` [${entity}] oracle fetch failed: ${e.message}`);
      continue;
    }
    const verr = validateSignal(signal);
    if (verr) {
      console.warn(` [${entity}] SKIPPED — invalid oracle response: ${verr} (refusing to sign/publish defaults)`);
      continue;
    }
    const { coh, thr } = signalFields(signal);
    const safe = coh >= thr;
    console.log(` [${entity}] φ=${coh.toFixed(4)} θ=${thr.toFixed(4)} → ${safe ? "SAFE" : "INTERCEPT"}  arch=${signal.archetype ?? signal.signal_type ?? "?"}`);
    for (const chain of activeChains) {
      await pushToChain(chain, entity, signal, wallet, dryRun);
    }
    await pushToZGGate(entity, signal);
  }
}

/**
 * Public entry point — invoked by relayer/index.js or by direct execution.
 * `opts` accepts the parsed CLI shape from common.parseArgs.
 */
export async function start(opts = { dryRun: true }) {
  _validateChainsAgainstRegistry();

  const MONITORED = (process.env.MONITORED_ENTITIES ||
    "0xb819c63c02Ed5aB49017C0f3f2568A14624658b3,uniswap,aave,compound"
  ).split(",").map(s => s.trim()).filter(Boolean);

  const PRIVATE_KEY  = process.env.RELAYER_PRIVATE_KEY || null;
  const KMS_PROVIDER = (process.env.KMS_PROVIDER || "env").toLowerCase();
  // Honour explicit --live flag; fall back to legacy env-detection when
  // invoked without a flag (backwards compat with relayer.js).
  const dryRun = opts.dryRun ?? (!PRIVATE_KEY && KMS_PROVIDER === "env");

  const activeChains = CHAINS.map(c => ({
    ...c,
    rpc: process.env[c.rpcEnv] || c.rpcDefault,
    addr: process.env[c.addrEnv] || c.addrDefault || null,
  }));

  log(FAMILY, "═══════════════════════════════════════════════════════════════");
  log(FAMILY, "TRION EVM FAMILY RELAYER (default — Node.js)");
  log(FAMILY, `Oracle API: ${ORACLE_API_URL}`);
  log(FAMILY, `Monitored: ${MONITORED.join(", ")}`);
  log(FAMILY, `Poll interval: ${POLL_INTERVAL_MS}ms`);
  log(FAMILY, `Mode: ${dryRun ? "DRY_RUN (set RELAYER_PRIVATE_KEY or KMS_PROVIDER to push on-chain)" : "LIVE"}`);
  log(FAMILY, `KMS provider: ${KMS_PROVIDER}`);
  log(FAMILY, `Chains: ${activeChains.length} (${activeChains.filter(c => c.addr).length} with oracle address)`);
  log(FAMILY, "═══════════════════════════════════════════════════════════════");

  const wallet = await buildWallet(dryRun, PRIVATE_KEY, KMS_PROVIDER);
  await preflightChainAccess(wallet, activeChains, dryRun);
  await initZGGate(wallet);

  while (true) {
    try {
      await tick(wallet, MONITORED, activeChains, dryRun);
    } catch (e) {
      console.error(`tick error: ${e?.message || e}`);
    }
    await new Promise(r => setTimeout(r, POLL_INTERVAL_MS));
  }
}

// ── Standalone execution ─────────────────────────────────────────────────────
const isMain = import.meta.url === `file://${process.argv[1]}`;
if (isMain) {
  const opts = parseArgs();
  if (opts.help) {
    console.log(`Usage: node relayer/families/evm.js [--dry-run|--live] [--help]`);
    console.log(`\nEnv: RELAYER_PRIVATE_KEY, KMS_PROVIDER, ORACLE_API_URL, MONITORED_ENTITIES, *_ORACLE_ADDR`);
    process.exit(0);
  }
  start(opts).catch(e => {
    console.error("evm relayer fatal:", e);
    process.exit(1);
  });
}
