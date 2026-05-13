/**
 * TRION × 0G Storage Integration
 * Stores behavioral signals and BEO vectors on 0G's decentralized storage.
 * Uses @0glabs/0g-ts-sdk (v0.3.3)
 *
 * Architecture:
 *   - Behavioral signals (JSON) → MemData → 0G Storage → Merkle root
 *   - FAISS index (binary) → ZgFile → 0G Storage → root stored on-chain
 *   - Root recorded in TRIONExecutionGate.confirmStorageSync()
 */

import { ethers } from "ethers";
import { Indexer, MemData } from "@0glabs/0g-ts-sdk";
import crypto from "node:crypto";

export const ZG_RPC         = "https://evmrpc-testnet.0g.ai";
export const ZG_CHAIN_ID    = 16602;
export const INDEXER_URL    = "https://indexer-storage-testnet-standard.0g.ai";
export const INDEXER_TURBO  = "https://indexer-storage-testnet-turbo.0g.ai";
export const GATE_ADDR      = "0xDB5910Dc6CfD219D00F64be1F23DA0289901356d";
export const ORACLE_ADDR    = "0x0471B2BE25c2eBbAe7FAc17383F1692979F0A87C";

const GATE_ABI = [
  "function confirmStorageSync(string calldata storageRoot, uint256 vectorCount) external",
  "function beoVectorStorageRoot() external view returns (string memory)",
  "function getStats() external view returns (uint256 allowed, uint256 blocked, uint256 published, uint256 anomalies, string memory storageRoot, uint256 storageSyncBlock)",
];

/**
 * computeLocalMerkleRoot — deterministic 256-byte-segment Merkle root.
 * Used as the storage proof even when on-chain submission is unavailable.
 */
export function computeLocalMerkleRoot(data) {
  const SEGMENT = 256;
  const leaves = [];
  for (let i = 0; i < data.length; i += SEGMENT) {
    const chunk = Buffer.alloc(SEGMENT, 0);
    data.copy(chunk, 0, i, Math.min(i + SEGMENT, data.length));
    leaves.push(crypto.createHash("sha256").update(chunk).digest());
  }
  if (leaves.length === 0) {
    return "0x" + crypto.createHash("sha256").update(data).digest("hex");
  }
  let level = leaves;
  while (level.length > 1) {
    const next = [];
    for (let i = 0; i < level.length; i += 2) {
      const left  = level[i];
      const right = level[i + 1] || level[i];
      next.push(crypto.createHash("sha256").update(Buffer.concat([left, right])).digest());
    }
    level = next;
  }
  return "0x" + level[0].toString("hex");
}

/**
 * storeSignal — upload a behavioral signal JSON to 0G Storage.
 * Returns { root, tx_hash, method, bytes_stored }.
 */
export async function storeSignal(signalData, privateKey) {
  const payload  = Buffer.from(JSON.stringify(signalData, null, 2));
  const localRoot = computeLocalMerkleRoot(payload);

  const result = {
    entity_id:       signalData.entity_id || "unknown",
    root:            localRoot,
    bytes_stored:    payload.length,
    method:          "local_merkle",
    sdk_version:     "0g-ts-sdk@0.3.3",
    storage_endpoint: INDEXER_URL,
    chain_id:        ZG_CHAIN_ID,
    timestamp:       Math.floor(Date.now() / 1000),
    payload_preview: JSON.stringify(signalData).slice(0, 120) + "…",
  };

  if (!privateKey) {
    result.note = "Wallet not configured — Merkle root computed locally. Set RELAYER_PRIVATE_KEY for on-chain storage.";
    return result;
  }

  try {
    const provider = new ethers.JsonRpcProvider(ZG_RPC);
    const signer   = new ethers.Wallet(privateKey, provider);
    const indexer  = new Indexer(INDEXER_TURBO);
    const memData  = new MemData(payload);
    const [tx, err] = await indexer.upload(memData, 0, signer);
    if (err) {
      result.note = `0G Storage upload attempted — error: ${err.message || err}`;
    } else if (tx) {
      result.root       = tx.root || tx.hash || localRoot;
      result.tx_hash    = tx.hash || null;
      result.method     = "0g_storage_sdk";
      result.note       = "Stored on 0G decentralized storage network";
    }
  } catch (e) {
    result.note = `SDK attempted: ${e.message?.slice(0, 100)}. Local Merkle root returned.`;
  }

  return result;
}

/**
 * readStorageRoot — read current BEO storage root from TRIONExecutionGate.
 */
export async function readStorageRoot() {
  try {
    const provider = new ethers.JsonRpcProvider(ZG_RPC);
    const gate     = new ethers.Contract(GATE_ADDR, GATE_ABI, provider);
    const [allowed, blocked, published, anomalies, storageRoot, syncBlock] = await gate.getStats();
    return {
      ok:           true,
      storage_root: storageRoot,
      sync_block:   Number(syncBlock),
      published:    Number(published),
      anomalies:    Number(anomalies),
      allowed:      Number(allowed),
      blocked:      Number(blocked),
      gate:         GATE_ADDR,
      explorer:     `https://chainscan-galileo.0g.ai/address/${GATE_ADDR}`,
    };
  } catch (e) {
    return { ok: false, error: e.message?.slice(0, 100) };
  }
}
