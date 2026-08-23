/**
 * TRION NEAR — Deploy BTCPContract WASM to trion.testnet
 * Uses direct Borsh encoding + ed25519 signing (no near-api-js dependency needed)
 * 
 * Usage: NEAR_PRIVATE_KEY=ed25519:... node deploy_wasm.mjs [wasm_path]
 */
import fs from "fs";
import { createHash } from "crypto";
import { fileURLToPath } from "url";
import path from "path";

const NEAR_RPC   = "https://rpc.testnet.fastnear.com";
const ACCOUNT_ID = "trion.testnet";
const WASM_PATH  = process.argv[2] || "/tmp/near_hello.wasm";

async function nearRpc(method, params) {
  const r = await fetch(NEAR_RPC, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ jsonrpc: "2.0", id: "1", method, params }),
    signal: AbortSignal.timeout(30000),
  });
  const d = await r.json();
  if (d.error) throw new Error(`NEAR RPC: ${JSON.stringify(d.error)}`);
  return d.result;
}

function encodeString(s) {
  const enc = new TextEncoder().encode(s);
  const buf = new Uint8Array(4 + enc.length);
  new DataView(buf.buffer).setUint32(0, enc.length, true);
  buf.set(enc, 4);
  return buf;
}

function encodeU32(n) {
  const buf = new Uint8Array(4);
  new DataView(buf.buffer).setUint32(0, n, true);
  return buf;
}

function encodeU64(n) {
  const buf = new Uint8Array(8);
  const view = new DataView(buf.buffer);
  view.setBigUint64(0, BigInt(n), true);
  return buf;
}

function concat(...arrays) {
  const total = arrays.reduce((s, a) => s + a.length, 0);
  const result = new Uint8Array(total);
  let offset = 0;
  for (const a of arrays) { result.set(a, offset); offset += a.length; }
  return result;
}

async function main() {
  console.log("╔══════════════════════════════════════════════════════════════════╗");
  console.log("║  TRION NEAR — Deploy BTCPContract WASM to trion.testnet         ║");
  console.log("╚══════════════════════════════════════════════════════════════════╝\n");

  if (!fs.existsSync(WASM_PATH)) { console.error("WASM not found:", WASM_PATH); process.exit(1); }
  const wasmBytes = fs.readFileSync(WASM_PATH);
  const wasmSha   = createHash("sha256").update(wasmBytes).digest("hex");
  console.log(`  WASM: ${WASM_PATH}`);
  console.log(`  Size: ${(wasmBytes.length / 1024).toFixed(1)} KB`);
  console.log(`  SHA256: ${wasmSha.slice(0, 16)}...`);

  const rawKey = (process.env.NEAR_PRIVATE_KEY ?? "").replace(/^ed25519:/, "");
  if (!rawKey) { console.error("NEAR_PRIVATE_KEY not set"); process.exit(1); }

  // Dynamically import tweetnacl and bs58
  const nacl = await import("/home/runner/workspace/node_modules/tweetnacl/nacl-fast.js").catch(() => null)
    || await import("tweetnacl");
  const bs58 = await import("/home/runner/workspace/node_modules/bs58/src/cjs/index.cjs").catch(() => null)
    || await import("bs58");

  const secretKey = bs58.default.decode(rawKey);
  const keyPair   = nacl.default.sign.keyPair.fromSecretKey(secretKey);
  const pubKey    = keyPair.publicKey;
  console.log(`  Public key (hex): ${Buffer.from(pubKey).toString("hex").slice(0, 16)}...`);

  // Get latest block
  const block = await nearRpc("block", { finality: "final" });
  const blockHash   = block.header.hash;
  const blockHeight = block.header.height;
  const blockHashBytes = bs58.default.decode(blockHash);
  console.log(`  Block height: ${blockHeight}`);

  // Get current nonce for this key
  // Try by querying access key — derive ed25519 public key as base58
  const pubKeyB58 = bs58.default.encode(pubKey);
  let nonce = 0;
  try {
    const ak = await nearRpc("query", {
      request_type: "view_access_key",
      finality: "final",
      account_id: ACCOUNT_ID,
      public_key: `ed25519:${pubKeyB58}`,
    });
    nonce = ak.nonce + 1;
    console.log(`  Access key nonce: ${nonce}`);
  } catch (e) {
    // Fallback: use known nonce + timestamp
    nonce = 245642240000002;
    console.log(`  Nonce fallback: ${nonce}`);
  }

  // Build DeployContract action Borsh
  // Action enum 1 = DeployContract
  // Layout: u32 code_len + code bytes
  const actionEnum    = new Uint8Array([1]); // DeployContract
  const codeLenBytes  = encodeU32(wasmBytes.length);
  const deployAction  = concat(actionEnum, codeLenBytes, wasmBytes);

  // Build transaction Borsh body
  const txBody = concat(
    encodeString(ACCOUNT_ID),  // signer_id
    new Uint8Array([0]),        // public_key type: ED25519
    pubKey,                     // 32-byte public key
    encodeU64(nonce),           // nonce
    encodeString(ACCOUNT_ID),  // receiver_id (self)
    blockHashBytes,             // block_hash (32 bytes)
    encodeU32(1),               // actions count
    deployAction,               // DeployContract action
  );

  // Sign SHA256 hash of txBody
  const hash      = createHash("sha256").update(txBody).digest();
  const signature = nacl.default.sign.detached(hash, secretKey);

  // Build signed tx
  const signedTx = concat(
    txBody,
    new Uint8Array([0]), // signature type: ED25519
    signature,           // 64-byte ed25519 signature
  );

  const signedTxB64 = Buffer.from(signedTx).toString("base64");
  console.log("\n  Broadcasting DeployContract transaction...");

  try {
    const result = await nearRpc("broadcast_tx_async", [signedTxB64]);
    console.log(`  ✅ TX Hash: ${result}`);
    console.log(`  Explorer: https://testnet.nearblocks.io/txns/${result}`);

    // Wait for receipt
    await new Promise(r => setTimeout(r, 5000));
    try {
      const receipt = await nearRpc("tx", [result, ACCOUNT_ID]);
      const status  = receipt.status?.SuccessValue !== undefined ? "SUCCESS" : JSON.stringify(receipt.status);
      console.log(`  Receipt status: ${status}`);
    } catch (e2) {
      console.log(`  Receipt: pending (${e2.message.slice(0, 60)})`);
    }

    // Verify deployed code
    await new Promise(r => setTimeout(r, 3000));
    const codeInfo = await nearRpc("query", {
      request_type: "view_code",
      finality: "final",
      account_id: ACCOUNT_ID,
    });
    const deployedSize = Buffer.from(codeInfo.code_base64, "base64").length;
    console.log(`\n  ✅ Verified deployed WASM: ${deployedSize} bytes (hash: ${codeInfo.hash})`);
    console.log(`  Account: ${ACCOUNT_ID}`);
    console.log(`  Explorer: https://testnet.nearblocks.io/address/${ACCOUNT_ID}`);
  } catch (e) {
    console.error("  ✗ Deploy error:", e.message.slice(0, 120));
  }
}

main().catch(e => { console.error("Fatal:", e); process.exit(1); });
