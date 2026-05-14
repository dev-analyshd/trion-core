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
 * If RELAYER_PRIVATE_KEY is missing the relayer runs in DRY_RUN mode and
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
const DRY_RUN     = !PRIVATE_KEY;

// Multi-chain registry — points at the testnets/mainnets where TRION oracle
// contracts are actually deployed (see proof-ledger/deploy_*.json). Each entry
// has a baked-in default contract address from the upstream deployment
// manifests; override via *_ORACLE_ADDR secrets if you redeploy. Override
// *_RPC_URL to use a private endpoint.
const CHAINS = [
  // Arbitrum Sepolia — TRIONOracleV3
  { key: "arb-sepolia",  name: "Arbitrum Sepolia",  chainId: 421614,   rpcEnv: "ARBITRUM_SEPOLIA_RPC_URL", rpcDefault: "https://sepolia-rollup.arbitrum.io/rpc",      addrEnv: "ARBITRUM_ORACLE_ADDR",     addrDefault: "0xb819c63c02Ed5aB49017C0f3f2568A14624658b3" },
  // Ethereum Sepolia — TRIONOracleV3
  { key: "eth-sepolia",  name: "Ethereum Sepolia",  chainId: 11155111, rpcEnv: "ETH_SEPOLIA_RPC_URL",      rpcDefault: "https://ethereum-sepolia.publicnode.com",     addrEnv: "ETH_SEPOLIA_ORACLE_ADDR",  addrDefault: "0xB07AD89a10f94B6D3bF2ab0B3a37988b1F37Db39" },
  // Base Sepolia — TRIONOracleV3
  { key: "base-sepolia", name: "Base Sepolia",      chainId: 84532,    rpcEnv: "BASE_SEPOLIA_RPC_URL",     rpcDefault: "https://sepolia.base.org",                    addrEnv: "BASE_ORACLE_ADDR",         addrDefault: "0x7ADF5B7273883C50EFc005BA7EdD3F379Af9680C" },
  // Optimism Sepolia — TRIONOracleV3
  { key: "op-sepolia",   name: "Optimism Sepolia",  chainId: 11155420, rpcEnv: "OP_SEPOLIA_RPC_URL",       rpcDefault: "https://sepolia.optimism.io",                 addrEnv: "OPTIMISM_ORACLE_ADDR",     addrDefault: "0x708193f93Fb897fbeA72e7e7D19237770F19E969" },
  // BNB Smart Chain Testnet — TRIONOracleV3
  { key: "bnb-testnet",  name: "BNB Testnet",       chainId: 97,       rpcEnv: "BNB_TESTNET_RPC_URL",      rpcDefault: "https://bsc-testnet-rpc.publicnode.com",      addrEnv: "BNB_ORACLE_ADDR",          addrDefault: "0xf0e20F48D4c2c63DCAf4bad01471d29DEb921721" },
  // 0G Newton Mainnet — TRIONOracleV3 (primary hackathon target)
  { key: "0g-newton",    name: "0G Newton Mainnet", chainId: 16600,    rpcEnv: "ZG_NEWTON_RPC",            rpcDefault: "https://evmrpc-mainnet.0g.ai",                addrEnv: "ZG_NEWTON_ORACLE_ADDR",    addrDefault: null },
  // 0G Galileo testnet — TRIONOracleV3
  { key: "0g-galileo",   name: "0G Galileo",        chainId: 16602,    rpcEnv: "ZERO_G_RPC",               rpcDefault: "https://evmrpc-testnet.0g.ai",                addrEnv: "ZG_ORACLE_ADDR",           addrDefault: "0x0471B2BE25c2eBbAe7FAc17383F1692979F0A87C" },
  // HashKey Chain Mainnet — TRIONOracleV3
  { key: "hashkey",      name: "HashKey Mainnet",   chainId: 177,      rpcEnv: "HSK_RPC_URL",              rpcDefault: "https://mainnet.hsk.xyz",                     addrEnv: "HSK_ORACLE_ADDR",          addrDefault: "0x708193f93Fb897fbeA72e7e7D19237770F19E969" },
  // Mantle Mainnet — TRIONOracleV3 (deploy pending)
  { key: "mantle",       name: "Mantle Mainnet",    chainId: 5000,     rpcEnv: "MANTLE_RPC_URL",           rpcDefault: "https://rpc.mantle.xyz",                      addrEnv: "MANTLE_ORACLE_ADDR",       addrDefault: null },
  // Linea Mainnet — TRIONOracleV3 (deploy pending)
  { key: "linea",        name: "Linea Mainnet",     chainId: 59144,    rpcEnv: "LINEA_RPC_URL",            rpcDefault: "https://rpc.linea.build",                     addrEnv: "LINEA_ORACLE_ADDR",        addrDefault: null },
  // Scroll Mainnet — TRIONOracleV3 (deploy pending)
  { key: "scroll",       name: "Scroll Mainnet",    chainId: 534352,   rpcEnv: "SCROLL_RPC_URL",           rpcDefault: "https://rpc.scroll.io",                       addrEnv: "SCROLL_ORACLE_ADDR",       addrDefault: null },
  // Polygon Mainnet — TRIONOracleV3 (deploy pending)
  { key: "polygon",      name: "Polygon Mainnet",   chainId: 137,      rpcEnv: "POLYGON_RPC_URL",          rpcDefault: "https://polygon-rpc.com",                     addrEnv: "POLYGON_ORACLE_ADDR",      addrDefault: null },
];

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
  || "0xDB5910Dc6CfD219D00F64be1F23DA0289901356d";
const ZG_GATE_RPC  = process.env.ZERO_G_RPC || "https://evmrpc-testnet.0g.ai";
const ZG_GATE_CHAIN = 16602;
const ZG_GATE_EXPLORER = "https://chainscan-galileo.0g.ai";

const ZG_GATE_ABI = [
  "function publishSignal(bytes32 entityId, uint256 packedData, bytes32 beoHash, bytes32 daProofHash, string calldata storageRoot) external",
  "function isValidator(address) external view returns (bool)",
  "function beoVectorStorageRoot() external view returns (string memory)",
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

    const feeData = await zgProvider.getFeeData();
    const tx = await zgGate.publishSignal(
      entityId, packed, beoHash, daProofHash, zgStorageRoot,
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
    const reason = DRY_RUN ? "DRY_RUN (no RELAYER_PRIVATE_KEY)" : `no ${chain.addrEnv}`;
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

    const tx = await oracle.publishSignal(txId, packed, [sig]);
    const receipt = await tx.wait(1);
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

// ── Main loop ────────────────────────────────────────────────────────────────
async function pollOracle(entity) {
  const url = `${ORACLE_API_URL}/api/v1/signal/${encodeURIComponent(entity)}`;
  const r = await axios.get(url, { timeout: 45000 });
  return r.data;
}

async function tick(wallet) {
  const stamp = new Date().toISOString();
  console.log(`\n[${stamp}] tick — entities=${MONITORED.length}, active_chains=${activeChains.length}, mode=${DRY_RUN ? "DRY_RUN" : "LIVE"}`);

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
  console.log(` Mode           : ${DRY_RUN ? "DRY_RUN (set RELAYER_PRIVATE_KEY to push on-chain)" : "LIVE"}`);
  console.log("");
  console.log(" Chain registry:");
  for (const c of activeChains) {
    const status = c.addr ? `→ ${c.addr}` : `[no ${c.addrEnv} — would skip in LIVE mode]`;
    console.log(`   ${c.name.padEnd(22)} chain_id=${String(c.chainId).padEnd(8)} ${status}`);
  }
  console.log("");

  const wallet = DRY_RUN ? null : new ethers.Wallet(PRIVATE_KEY.startsWith("0x") ? PRIVATE_KEY : "0x" + PRIVATE_KEY);
  if (wallet) console.log(` Validator addr : ${wallet.address}\n`);

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
