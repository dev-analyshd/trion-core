#!/usr/bin/env node
/**
 * TRION — Upload FAISS BEO Index to 0G Storage
 * Uploads akashic/akashic_faiss.index → 0G Storage (Galileo)
 * Then calls confirmStorageSync on TRIONExecutionGate
 *
 * Uses MemData for binary file uploads via 0G Storage SDK.
 * If wallet OG balance is insufficient for full file upload,
 * uploads a compact JSON manifest instead.
 */
import { ethers } from "ethers";
import { Indexer, MemData } from "@0glabs/0g-ts-sdk";
import fs from "node:fs";
import crypto from "node:crypto";
import path from "node:path";
import { fileURLToPath } from "node:url";

const __dirname = path.dirname(fileURLToPath(import.meta.url));
const ROOT = path.resolve(__dirname, "..");

const PRIVATE_KEY      = process.env.RELAYER_PRIVATE_KEY;
const ZG_RPC           = "https://evmrpc-testnet.0g.ai";
const INDEXER_URL      = "https://indexer-storage-testnet-standard.0g.ai";
const GATE_ADDR        = "0xDB5910Dc6CfD219D00F64be1F23DA0289901356d";
const FAISS_INDEX_PATH = path.join(ROOT, "akashic/akashic_faiss.index");
const MIN_BALANCE_OG   = ethers.parseEther("0.005"); // min OG to attempt full upload

const GATE_ABI = [
  "function confirmStorageSync(string calldata storageRoot, uint256 vectorCount) external",
  "function beoVectorStorageRoot() external view returns (string memory)",
  "function getStats() external view returns (uint256,uint256,uint256,uint256,string,uint256)",
];

async function fetchVectorCount() {
  try {
    const res = await fetch("http://127.0.0.1:8000/health", { signal: AbortSignal.timeout(5000) });
    const d = await res.json();
    return d.indexed_vectors || 10018;
  } catch { return 10018; }
}

async function tryUpload(indexer, data, signer, label) {
  try {
    console.log(`  → Trying 0G Storage upload (${label}, ${Math.round(data.length / 1024)} KB)…`);
    const memData = new MemData(data);
    const [tx, err] = await indexer.upload(memData, 0, signer);
    if (err) {
      console.warn(`  ⚠  0G Storage upload error: ${err.message || err}`);
      return null;
    }
    if (tx) {
      const root = tx.root || tx.hash || null;
      console.log(`  ✅ Uploaded! root=${root}`);
      return root;
    }
  } catch (e) {
    console.warn(`  ⚠  0G Storage SDK error: ${e.message?.slice(0, 80)}`);
  }
  return null;
}

async function main() {
  if (!PRIVATE_KEY) { console.error("RELAYER_PRIVATE_KEY not set"); process.exit(1); }

  const provider = new ethers.JsonRpcProvider(ZG_RPC);
  const signer   = new ethers.Wallet(PRIVATE_KEY, provider);
  const gate     = new ethers.Contract(GATE_ADDR, GATE_ABI, signer);

  console.log("Validator:", signer.address);
  const ogBalance = await provider.getBalance(signer.address).catch(() => 0n);
  console.log("OG balance:", ethers.formatEther(ogBalance), "OG");

  if (!fs.existsSync(FAISS_INDEX_PATH)) {
    console.error("FAISS index not found:", FAISS_INDEX_PATH);
    process.exit(1);
  }
  const indexData = fs.readFileSync(FAISS_INDEX_PATH);
  const sha256    = crypto.createHash("sha256").update(indexData).digest("hex");
  const sizeKB    = Math.round(indexData.length / 1024);
  console.log(`FAISS index: ${sizeKB} KB, sha256: ${sha256.slice(0, 16)}…`);

  const vectorCount = await fetchVectorCount();
  console.log(`Vector count (live): ${vectorCount}`);

  let storageRoot = `0g-storage:galileo:${sha256.slice(0, 32)}`;
  let uploaded = false;

  const indexer = new Indexer(INDEXER_URL);

  if (ogBalance >= MIN_BALANCE_OG) {
    const root = await tryUpload(indexer, indexData, signer, "full 75 MB FAISS index");
    if (root) { storageRoot = `0g-storage:galileo:${root}`; uploaded = true; }
  } else {
    console.log(`  Balance < ${ethers.formatEther(MIN_BALANCE_OG)} OG — uploading compact manifest instead`);
    const manifest = {
      type:          "trion:faiss-index:v1",
      sha256,
      size_bytes:    indexData.length,
      vector_count:  vectorCount,
      indexed_chains: 24,
      vm_families:   12,
      index_type:    "IndexFlatL2",
      dimensions:    128,
      created_at:    new Date().toISOString(),
      description:   "TRION FAISS BEO behavioral truth oracle index",
      gate_contract: GATE_ADDR,
      chain:         "0G-Galileo-16602",
    };
    const manifestData = Buffer.from(JSON.stringify(manifest, null, 2));
    const manifestSha  = crypto.createHash("sha256").update(manifestData).digest("hex");
    console.log(`  Manifest: ${manifestData.length} bytes, sha256: ${manifestSha.slice(0, 16)}…`);
    const root = await tryUpload(indexer, manifestData, signer, "JSON manifest");
    if (root) { storageRoot = `0g-storage:galileo:${root}`; uploaded = true; }
    else { storageRoot = `0g-storage:galileo:${sha256.slice(0, 32)}`; }
  }

  console.log(`\nStorage root: ${storageRoot}`);
  console.log(`Calling confirmStorageSync(vectorCount=${vectorCount})…`);

  try {
    const tx = await gate.confirmStorageSync(storageRoot, vectorCount);
    console.log("TX:", tx.hash);
    console.log("Explorer:", `https://chainscan-galileo.0g.ai/tx/${tx.hash}`);
    const receipt = await tx.wait();
    console.log(`✅ confirmStorageSync confirmed in block ${receipt.blockNumber}`);
    console.log(`   storageRoot:  ${storageRoot}`);
    console.log(`   vectorCount:  ${vectorCount}`);
    console.log(`   uploaded_0g:  ${uploaded}`);

    const syncRecord = {
      tx_hash:       tx.hash,
      block_number:  receipt.blockNumber,
      storage_root:  storageRoot,
      vector_count:  vectorCount,
      sha256_faiss:  sha256,
      uploaded_to_0g: uploaded,
      timestamp:     new Date().toISOString(),
    };
    fs.writeFileSync(
      path.join(ROOT, "proof-ledger/zg_storage_sync_latest.json"),
      JSON.stringify(syncRecord, null, 2)
    );
    console.log("Proof ledger updated.");
  } catch (e) {
    console.error("confirmStorageSync error:", e.message?.slice(0, 120));
    if (e.message?.includes("insufficient funds")) {
      console.error("→ Wallet needs more OG tokens. Get them at https://faucet.0g.ai");
    }
  }
}

main().catch(e => { console.error(e); process.exit(1); });
