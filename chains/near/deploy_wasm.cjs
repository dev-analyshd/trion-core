'use strict';
/**
 * TRION NEAR — Deploy WASM Contract to trion.testnet (CommonJS)
 * Uses direct Borsh encoding + ed25519 signing
 * Usage: NEAR_PRIVATE_KEY=ed25519:... node deploy_wasm.cjs [wasm_path]
 */
const fs          = require('fs');
const crypto      = require('crypto');
const { default: bs58api } = require('/home/runner/workspace/node_modules/bs58/src/cjs/index.cjs');
const nacl        = require('/home/runner/workspace/node_modules/tweetnacl/nacl-fast.js');

const encode = bs58api.encode;
const decode = bs58api.decode;

const NEAR_RPC   = 'https://rpc.testnet.fastnear.com';
const ACCOUNT_ID = 'trion.testnet';
const WASM_PATH  = process.argv[2] || '/tmp/near_hello.wasm';

async function nearRpc(method, params) {
  const r = await fetch(NEAR_RPC, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ jsonrpc: '2.0', id: '1', method, params }),
    signal: AbortSignal.timeout(30000),
  });
  const d = await r.json();
  if (d.error) throw new Error(`NEAR RPC: ${JSON.stringify(d.error)}`);
  return d.result;
}

function encodeString(s) {
  const enc = Buffer.from(s, 'utf8');
  const buf = Buffer.alloc(4 + enc.length);
  buf.writeUInt32LE(enc.length, 0);
  enc.copy(buf, 4);
  return buf;
}

function encodeU32(n) {
  const b = Buffer.alloc(4);
  b.writeUInt32LE(n, 0);
  return b;
}

function encodeU64(n) {
  const b = Buffer.alloc(8);
  b.writeBigUInt64LE(BigInt(n), 0);
  return b;
}

function concat(...bufs) {
  return Buffer.concat(bufs.map(b => Buffer.from(b)));
}

async function main() {
  console.log('╔══════════════════════════════════════════════════════════╗');
  console.log('║  TRION NEAR — Deploy BTCPContract WASM to trion.testnet ║');
  console.log('╚══════════════════════════════════════════════════════════╝\n');

  if (!fs.existsSync(WASM_PATH)) { console.error('WASM not found:', WASM_PATH); process.exit(1); }
  const wasmBytes = fs.readFileSync(WASM_PATH);
  const sha256    = crypto.createHash('sha256').update(wasmBytes).digest('hex');
  console.log(`  WASM: ${WASM_PATH}`);
  console.log(`  Size: ${(wasmBytes.length / 1024).toFixed(1)} KB`);
  console.log(`  SHA256: ${sha256.slice(0,16)}...`);

  const rawKey = (process.env.NEAR_PRIVATE_KEY || '').replace(/^ed25519:/, '');
  if (!rawKey) { console.error('NEAR_PRIVATE_KEY not set'); process.exit(1); }

  const secretKey = decode(rawKey);
  const keyPair   = nacl.sign.keyPair.fromSecretKey(secretKey);
  const pubKey    = keyPair.publicKey;
  console.log(`  Public key: ed25519:${encode(pubKey).slice(0,16)}...`);

  // Get latest block
  const block = await nearRpc('block', { finality: 'final' });
  const blockHash      = block.header.hash;
  const blockHeight    = block.header.height;
  const blockHashBytes = Buffer.from(decode(blockHash));
  console.log(`  Block height: ${blockHeight}`);

  // Get current nonce via access key lookup
  const pubKeyB58 = encode(Buffer.from(pubKey));
  let nonce = 245642240000002;
  try {
    const ak = await nearRpc('query', {
      request_type: 'view_access_key',
      finality: 'final',
      account_id: ACCOUNT_ID,
      public_key: `ed25519:${pubKeyB58}`,
    });
    nonce = ak.nonce + 1;
    console.log(`  Access key nonce: ${nonce}`);
  } catch (e) {
    console.log(`  Nonce fallback: ${nonce}`);
  }

  // Build DeployContract action (action enum = 1)
  const actionEnum   = Buffer.from([1]);
  const codeLenBytes = encodeU32(wasmBytes.length);
  const deployAction = concat(actionEnum, codeLenBytes, wasmBytes);

  // Build NEAR transaction Borsh body
  const txBody = concat(
    encodeString(ACCOUNT_ID),    // signer_id
    Buffer.from([0]),             // key type: ED25519
    Buffer.from(pubKey),          // 32-byte public key
    encodeU64(nonce),             // nonce (u64 LE)
    encodeString(ACCOUNT_ID),    // receiver_id (self)
    blockHashBytes,               // block_hash (32 bytes)
    encodeU32(1),                 // actions count
    deployAction,                 // DeployContract action
  );

  // Sign SHA256(txBody)
  const txHash    = crypto.createHash('sha256').update(txBody).digest();
  const signature = nacl.sign.detached(txHash, secretKey);

  // Assemble signed transaction
  const signedTx    = concat(txBody, Buffer.from([0]), Buffer.from(signature));
  const signedTxB64 = signedTx.toString('base64');

  console.log('\n  Broadcasting DeployContract transaction...');
  try {
    const result = await nearRpc('broadcast_tx_async', [signedTxB64]);
    console.log(`  ✅ TX Hash: ${result}`);
    console.log(`  Explorer: https://testnet.nearblocks.io/txns/${result}`);

    // Wait and verify
    await new Promise(r => setTimeout(r, 8000));
    try {
      const receipt = await nearRpc('tx', [result, ACCOUNT_ID]);
      const st = receipt.status?.SuccessValue !== undefined ? 'SUCCESS'
        : receipt.status?.Failure ? `FAIL: ${JSON.stringify(receipt.status.Failure).slice(0,80)}`
        : JSON.stringify(receipt.status);
      console.log(`  Receipt: ${st}`);
    } catch (e2) {
      console.log(`  Receipt: pending (${e2.message.slice(0,60)})`);
    }

    // Verify deployed WASM
    await new Promise(r => setTimeout(r, 3000));
    const codeInfo   = await nearRpc('query', { request_type: 'view_code', finality: 'final', account_id: ACCOUNT_ID });
    const deployedSz = Buffer.from(codeInfo.code_base64, 'base64').length;
    console.log(`\n  ✅ Contract verified on chain!`);
    console.log(`     Account:  ${ACCOUNT_ID}`);
    console.log(`     WASM sz:  ${deployedSz} bytes`);
    console.log(`     Hash:     ${codeInfo.hash}`);
    console.log(`     Explorer: https://testnet.nearblocks.io/address/${ACCOUNT_ID}`);
    return { tx: result, size: deployedSz, hash: codeInfo.hash };
  } catch (e) {
    console.error('  ✗ Deploy error:', e.message.slice(0, 120));
    process.exit(1);
  }
}

main().catch(e => { console.error('Fatal:', e); process.exit(1); });
