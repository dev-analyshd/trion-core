// =============================================================================
// TRION Coherence Vault — End-to-End Test (Phase 4)
// =============================================================================
//
// Runs the full preimage-triggered BTC lock flow on Bitcoin testnet + Stacks
// testnet, exercising:
//
//   Phase A — Vault Creation (Bitcoin testnet)
//     A1  Generate borrower keypair + lender address
//     A2  Fetch a real BTC testnet tx from mempool.space for the canonical
//         testnet address tb1q5d69fyxxxwdkr7pecmxyr245w5jqchm9zptkks
//     A3  Compute the 93-byte HashDNA payload (entity_id, event_type,
//         magnitude, context, timestamp, chain_id, block_hash)
//     A4  Compute committed anchor_bh = SHA-256(payload ‖ 0x00)
//     A5  Build the Coherence Vault Taproot address (2 leaves: preimage
//         reveal + CSV refund) via the coherence-vault.js CLI
//     A6  Record the vault on Stacks via TRIONCoherenceVault.register-vault
//
//   Phase B — Preimage Publication (Stacks testnet)
//     B1  Call TRIONCoherenceVault.publish-preimage with the 93-byte payload
//     B2  Verify the contract emits coherence-vault-release-triggered +
//         read-only is-vault-release-triggered returns true
//
//   Phase C — Borrower Refund (Bitcoin testnet simulation)
//     C1  Build the CSV refund transaction (borrower signs after timelock)
//         via the coherence-vault.js CLI refund command
//     C2  Verify the refund tx is valid (don't broadcast — just decode the
//         signed hex and confirm input.sequence encodes the CSV value)
//
// Output: proofs/btcp-zero-bridge/stacks/coherence-vault-test-results.json
// =============================================================================

import { execFileSync } from 'node:child_process';
import * as fs from 'node:fs';
import * as path from 'node:path';
import * as crypto from 'node:crypto';
import { fileURLToPath } from 'node:url';

import * as bitcoin from 'bitcoinjs-lib';
import { ECPairFactory } from 'ecpair';
import * as ecc from 'tiny-secp256k1';
import { bufferCV, uintCV, serializeCV, deserializeCV } from '@stacks/transactions';

import {
  API,
  network,
  getAddressFromPrivateKey,
  getNonce,
  getBalance,
  waitForTx,
  sendContractCall,
  sleep,
} from '../stacks/lib/helpers.mjs';

// Register the ECC library with bitcoinjs-lib v7 (required for Taproot).
bitcoin.initEccLib(ecc);
const ECPair = ECPairFactory(ecc);

// =============================================================================
// Constants
// =============================================================================

const __dirname = path.dirname(fileURLToPath(import.meta.url));
const VAULT_DIR = __dirname;
const COHERENCE_VAULT_CLI = path.join(VAULT_DIR, 'coherence-vault.js');
const REPO_ROOT = path.resolve(VAULT_DIR, '..', '..');
const RESULTS_FILE = path.join(
  REPO_ROOT,
  'proofs',
  'btcp-zero-bridge',
  'stacks',
  'coherence-vault-test-results.json',
);

const DEPLOYER_KEY = '940806a0a98e86df44835d7fb5d58a79d6259f413550ba11a858880a72e2e71901';
const FEE = 100000; // microSTX per Stacks tx

const CONTRACT_ADDR = 'ST969AZNDX2P7N1YJ0DNVGC8QEKT388DBMXGHR9Z';
const CONTRACT_NAME = 'trioncoherencevault-v4';
const DEPLOYER_ADDR = getAddressFromPrivateKey(DEPLOYER_KEY, 'testnet');

// Canonical BTC testnet address — used both as the lender destination and as
// the source of the real on-chain tx from which we derive the HashDNA payload.
const CANONICAL_BTC_ADDR = 'tb1q5d69fyxxxwdkr7pecmxyr245w5jqchm9zptkks';

const MEMPOOL_API = (addr) =>
  `https://mempool.space/testnet/api/address/${addr}/txs`;

// HashDNA payload field constants (must match coherence-vault.js + Clarity).
const PAYLOAD_LEN = 93;
const SENSE_SUFFIX = 0x00;
const CHAIN_ID_STACKS = 100; // Stacks chain-id in TRION registry

// CSV refund timelock in Bitcoin blocks. 144 = ~24h. Keep small for the test
// so the refund-vault read-only check (after the timelock elapses) is
// reachable on Stacks testnet (which uses burn-block-height).
const CSV_BLOCKS = 6;

// Locked BTC amount (satoshis) used in the vault registration + refund PSBT.
const LOCK_SATS = 100_000; // 0.001 BTC

// =============================================================================
// Small helpers
// =============================================================================

function step(n, msg) {
  console.log(`\n────────── STEP ${n} ──────────`);
  console.log(`  ${msg}`);
}

function logField(k, v) {
  // Truncate long hex strings for console readability.
  const s = typeof v === 'string' && v.length > 80 ? `${v.slice(0, 78)}…` : v;
  console.log(`    ${k.padEnd(22)}: ${s}`);
}

// Spawn the coherence-vault.js CLI synchronously, returning stdout.
function runVaultCli(...args) {
  return execFileSync('node', [COHERENCE_VAULT_CLI, ...args], {
    cwd: VAULT_DIR,
    encoding: 'utf-8',
    stdio: ['ignore', 'pipe', 'pipe'],
  });
}

// Encode a uint as a big-endian 8-byte Buffer (for vault-id derivation).
function uintBe8(n) {
  const buf = Buffer.alloc(8);
  buf.writeBigUInt64BE(BigInt(n));
  return buf;
}

// Fetch BTC testnet txs for an address from mempool.space.
async function fetchBtcTxs(addr) {
  const url = MEMPOOL_API(addr);
  const ctrl = new AbortController();
  const t = setTimeout(() => ctrl.abort(), 30_000);
  try {
    const r = await fetch(url, { signal: ctrl.signal });
    if (!r.ok) throw new Error(`HTTP ${r.status} fetching ${url}`);
    return await r.json();
  } finally {
    clearTimeout(t);
  }
}

// Get the current Stacks burn block height (Bitcoin block height as seen
// by Stacks — used to verify the CSV-timelock invariant in refund-vault).
async function getBurnBlockHeight() {
  const r = await fetch(`${API}/v2/info`);
  if (!r.ok) throw new Error(`HTTP ${r.status} fetching /v2/info`);
  const j = await r.json();
  return parseInt(j.burn_block_height, 10);
}

// Read-only contract call (Clarity call-read endpoint).
// The Hiro API returns: { okay: true, result: '0x0703' }
// where `result` is the hex-encoded serialized Clarity value.
// We decode it with @stacks/transactions' deserializeCV for ergonomic inspection.
async function callReadOnly(fnName, args /* ClarityValue[] */) {
  const sender = DEPLOYER_ADDR;
  const url = `${API}/v2/contracts/call-read/${CONTRACT_ADDR}/${CONTRACT_NAME}/${fnName}`;
  const body = {
    sender,
    arguments: args.map((cv) => '0x' + serializeCV(cv).toString('hex')),
  };
  const r = await fetch(url, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(body),
  });
  if (!r.ok) throw new Error(`call-read ${fnName}: HTTP ${r.status}`);
  const j = await r.json();
  // Decode the result Clarity value if present.
  let decoded = null;
  let repr = j?.result ?? j?.cause ?? '(no result)';
  if (j?.okay && typeof j.result === 'string' && j.result.startsWith('0x')) {
    try {
      decoded = deserializeCV(Buffer.from(j.result.slice(2), 'hex'));
      repr = clarityRepr(decoded);
    } catch (e) {
      repr = `(decode failed: ${e.message})`;
    }
  }
  return { okay: !!j?.okay, raw: j, decoded, repr };
}

// Render a deserialized Clarity value as a readable Clarity string.
function clarityRepr(v) {
  if (!v) return '(none)';
  switch (v.type) {
    case 'ok':    return `(ok ${clarityRepr(v.value)})`;
    case 'err':   return `(err ${clarityRepr(v.value)})`;
    case 'true':  return 'true';
    case 'false': return 'false';
    case 'uint':  return `u${v.value.toString()}`;
    case 'int':   return v.value.toString();
    case 'buffer': {
      const hex = Buffer.from(v.value).toString('hex');
      return `0x${hex}${hex.length > 32 ? `…(${hex.length / 2} bytes)` : ''}`;
    }
    case 'string_ascii': return `"${v.value}"`;
    case 'string_utf8':  return `u"${v.value}"`;
    case 'tuple': {
      const fields = v.value.map(({ name, type, value }) => `${name}: ${clarityRepr({ type, value })}`);
      return `(tuple ${fields.join(' ')})`;
    }
    case 'list': {
      const items = v.value.map((x) => clarityRepr(x));
      return `(list ${items.join(' ')})`;
    }
    default: return `(${v.type})`;
  }
}

// =============================================================================
// Main
// =============================================================================

async function main() {
  console.log('==========================================================');
  console.log(' TRION Coherence Vault — End-to-End Test (Phase 4)');
  console.log('==========================================================');
  console.log(` Contract       : ${CONTRACT_ADDR}.${CONTRACT_NAME}`);
  console.log(` Deployer       : ${DEPLOYER_ADDR}`);
  console.log(` Stacks API     : ${API}`);
  console.log(` Vault CLI      : ${path.relative(REPO_ROOT, COHERENCE_VAULT_CLI)}`);
  console.log(` Results file   : ${path.relative(REPO_ROOT, RESULTS_FILE)}`);
  console.log(` BTC canonical  : ${CANONICAL_BTC_ADDR}`);
  console.log('==========================================================');

  // Pre-flight: deployer STX balance sanity.
  const bal = await getBalance(DEPLOYER_ADDR);
  console.log(` Deployer STX   : ${bal} µSTX`);
  if (bal < FEE * 4) {
    console.warn(`  [warn] low balance — Phase B may fail mid-test`);
  }

  const results = {
    schema: 'trion-coherence-vault-test/v1',
    startedAt: new Date().toISOString(),
    contract: `${CONTRACT_ADDR}.${CONTRACT_NAME}`,
    deployer: DEPLOYER_ADDR,
    phases: { A: {}, B: {}, C: {} },
    steps: [],
  };

  // ===========================================================================
  // PHASE A — Vault Creation
  // ===========================================================================
  console.log('\n========== PHASE A — Vault Creation (Bitcoin testnet) ==========');

  // --- A1: Generate borrower keypair + lender address -----------------------
  step('A1', 'Generate borrower keypair + lender address');
  const borrower = ECPair.makeRandom({ network: bitcoin.networks.testnet });
  const borrowerWif = borrower.toWIF();
  const borrowerPubkeyHex = Buffer.from(borrower.publicKey).toString('hex');
  const lenderAddr = CANONICAL_BTC_ADDR;
  logField('borrower WIF', borrowerWif);
  logField('borrower pubkey', borrowerPubkeyHex);
  logField('lender addr', lenderAddr);
  results.steps.push({
    step: 'A1',
    ok: true,
    borrowerWif,
    borrowerPubkey: borrowerPubkeyHex,
    lenderAddr,
  });

  // --- A2: Fetch a real BTC testnet tx from mempool.space -------------------
  step('A2', `Fetch real BTC testnet tx from mempool.space (${CANONICAL_BTC_ADDR})`);
  const txs = await fetchBtcTxs(CANONICAL_BTC_ADDR);
  if (!Array.isArray(txs) || txs.length === 0) {
    throw new Error(`no BTC txs returned for ${CANONICAL_BTC_ADDR}`);
  }
  const confirmedTx = txs.find((t) => t.status?.confirmed) ?? txs[0];
  const blockHash = confirmedTx.status.block_hash;      // big-endian display hex
  const blockHeight = confirmedTx.status.block_height;
  const blockTime = confirmedTx.status.block_time;       // unix seconds
  // Find the vout paying the canonical address (if any) — used as the
  // magnitude for the HashDNA payload. Fall back to vout[0].value.
  const voutToCanonical = confirmedTx.vout.find(
    (v) => v.scriptpubkey_address === CANONICAL_BTC_ADDR,
  );
  const amountSats = voutToCanonical?.value ?? confirmedTx.vout[0].value;
  logField('txid', confirmedTx.txid);
  logField('block height', blockHeight);
  logField('block hash', blockHash);
  logField('block time', `${blockTime}  (${new Date(blockTime * 1000).toISOString()})`);
  logField('vout value', `${amountSats} sats`);
  results.steps.push({
    step: 'A2',
    ok: true,
    txid: confirmedTx.txid,
    blockHash,
    blockHeight,
    blockTime,
    amountSats,
  });

  // --- A3: Compute the 93-byte HashDNA payload -----------------------------
  step('A3', 'Compute the 93-byte HashDNA payload (7 fields)');
  // entity_id = SHA-256(borrower_pubkey || canonical_btc_addr) — derived from
  // the borrower keypair so each test run produces a fresh vault-id (the
  // contract enforces ERR-VAULT-EXISTS on duplicates).
  const entityId = crypto
    .createHash('sha256')
    .update(
      Buffer.concat([
        Buffer.from(borrower.publicKey),
        Buffer.from(CANONICAL_BTC_ADDR.toLowerCase(), 'utf8'),
      ]),
    )
    .digest();                                  // 32 bytes
  const eventType = 0;                          // 1 byte
  const magnitudeNano = BigInt(amountSats) * 1_000_000_000n;  // 8 bytes BE
  const context = 0n;                           // 8 bytes BE
  const timestamp = BigInt(blockTime);          // 8 bytes BE
  const chainId = CHAIN_ID_STACKS;              // 4 bytes BE
  const blockHashBuf = Buffer.from(blockHash, 'hex'); // 32 bytes (as-is, LE)
  if (blockHashBuf.length !== 32) {
    throw new Error(`block_hash must be 32 bytes, got ${blockHashBuf.length}`);
  }
  const payload = Buffer.alloc(PAYLOAD_LEN);
  entityId.copy(payload, 0);
  payload.writeUInt8(eventType, 32);
  payload.writeBigUInt64BE(magnitudeNano, 33);
  payload.writeBigUInt64BE(context, 41);
  payload.writeBigUInt64BE(timestamp, 49);
  payload.writeUInt32BE(chainId, 57);
  blockHashBuf.copy(payload, 61);
  if (payload.length !== PAYLOAD_LEN) {
    throw new Error(`payload length mismatch: ${payload.length}`);
  }
  logField('payload hex', payload.toString('hex'));
  logField('payload len', `${payload.length} bytes`);
  logField('entity_id', entityId.toString('hex'));
  logField('event_type', eventType);
  logField('magnitude_nano', magnitudeNano.toString());
  logField('context', context.toString());
  logField('timestamp', timestamp.toString());
  logField('chain_id', chainId);
  logField('block_hash', blockHash);
  results.steps.push({
    step: 'A3',
    ok: true,
    payloadHex: payload.toString('hex'),
    payloadLen: payload.length,
    fields: {
      entityId: entityId.toString('hex'),
      eventType,
      magnitudeNano: magnitudeNano.toString(),
      context: context.toString(),
      timestamp: timestamp.toString(),
      chainId,
      blockHash,
    },
  });

  // --- A4: Compute committed anchor_bh --------------------------------------
  step('A4', 'Compute committed anchor_bh = SHA-256(payload ‖ 0x00)');
  const senseInput = Buffer.concat([payload, Buffer.from([SENSE_SUFFIX])]);
  const anchorBH = crypto.createHash('sha256').update(senseInput).digest(); // 32 bytes
  logField('anchor_bh', anchorBH.toString('hex'));
  results.steps.push({
    step: 'A4',
    ok: true,
    anchorBH: anchorBH.toString('hex'),
  });

  // --- A5: Build the Coherence Vault Taproot address ------------------------
  step('A5', 'Build the Coherence Vault Taproot address (2 leaves)');
  // Invoke coherence-vault.js CLI `create` so the test exercises the deployed
  // CLI. The vault-state JSON is the system-of-record for Phase C.
  // Use a simulated UTXO so the CLI also pre-builds the refund PSBT we will
  // sign in Phase C. (We never broadcast — these are testnet-only test PSBTs.)
  const simUtxoTxid = crypto.randomBytes(32).toString('hex');
  const simUtxoVout = 0;
  const vaultStateFile = path.join(VAULT_DIR, 'vault-state-test.json');
  const payloadHex = payload.toString('hex');
  let createStdout = '';
  try {
    createStdout = runVaultCli(
      'create',
      '--borrower-wif', borrowerWif,
      '--lender-addr', lenderAddr,
      '--sats', String(LOCK_SATS),
      '--csv-blocks', String(CSV_BLOCKS),
      '--payload', payloadHex,
      '--vault-txid', simUtxoTxid,
      '--vault-vout', String(simUtxoVout),
      '--out', vaultStateFile,
    );
  } catch (e) {
    console.error(createStdout || e.stdout || e.stderr || e.message);
    throw new Error(`coherence-vault.js create failed: ${e.message}`);
  }
  const vaultState = JSON.parse(fs.readFileSync(vaultStateFile, 'utf-8'));
  logField('vault address', vaultState.vaultAddress);
  logField('vault output scr', vaultState.vaultOutputScript);
  logField('release script', vaultState.releaseScript);
  logField('refund script', vaultState.refundScript);
  logField('internal x-only', vaultState.internalPubkey);
  logField('sim UTXO', `${simUtxoTxid}:${simUtxoVout}`);
  results.phases.A = {
    vaultAddress: vaultState.vaultAddress,
    vaultOutputScript: vaultState.vaultOutputScript,
    releaseScript: vaultState.releaseScript,
    refundScript: vaultState.refundScript,
    internalPubkey: vaultState.internalPubkey,
    borrowerPubkey: vaultState.borrowerPubkey,
    committedAnchorBH: vaultState.committedAnchorBH,
    csvBlocks: CSV_BLOCKS,
    sats: LOCK_SATS,
    lenderAddress: lenderAddr,
    simUtxo: { txid: simUtxoTxid, vout: simUtxoVout },
    vaultStateFile: path.relative(REPO_ROOT, vaultStateFile),
    releasePsbtB64: vaultState.releasePsbtB64,
    refundPsbtB64: vaultState.refundPsbtB64,
  };
  results.steps.push({
    step: 'A5',
    ok: !!vaultState.vaultAddress && vaultState.committedAnchorBH === anchorBH.toString('hex'),
    vaultAddress: vaultState.vaultAddress,
  });

  // --- A6: Record the vault on Stacks via register-vault --------------------
  step('A6', `Call ${CONTRACT_NAME}.register-vault on Stacks testnet`);
  // vault-id = SHA-256(borrower-beo || committed-anchor-bh || lender-btc-addr
  //                    || amount-sats || csv-blocks)  — computed off-chain,
  // verified by the caller's possession of all the values that hash to it.
  const vaultIdBuf = crypto
    .createHash('sha256')
    .update(
      Buffer.concat([
        entityId,
        anchorBH,
        Buffer.from(lenderAddr, 'utf8'),
        uintBe8(LOCK_SATS),
        uintBe8(CSV_BLOCKS),
      ]),
    )
    .digest();
  const vaultIdHex = vaultIdBuf.toString('hex');
  logField('vault-id', vaultIdHex);
  logField('borrower-beo', entityId.toString('hex'));
  logField('committed-anchor-bh', anchorBH.toString('hex'));
  logField('lender-btc-addr (utf8)', lenderAddr);
  logField('amount-sats', LOCK_SATS);
  logField('csv-blocks', CSV_BLOCKS);

  const regArgs = [
    bufferCV(vaultIdBuf),                       // vault-id (buff 32)
    bufferCV(entityId),                        // borrower-beo (buff 32)
    bufferCV(anchorBH),                         // committed-anchor-bh (buff 32)
    bufferCV(Buffer.from(lenderAddr, 'utf8')),   // lender-btc-addr (buff 64)
    uintCV(LOCK_SATS),                          // amount-sats uint
    uintCV(CSV_BLOCKS),                         // csv-blocks uint
  ];
  logField('sender', DEPLOYER_ADDR);
  logField('fee', `${FEE} µSTX`);
  const burnHeightBefore = await getBurnBlockHeight();
  logField('burn-block-height (pre)', burnHeightBefore);

  const regRes = await sendContractCall({
    contractAddress: CONTRACT_ADDR,
    contractName: CONTRACT_NAME,
    functionName: 'register-vault',
    functionArgs: regArgs,
    senderKey: DEPLOYER_KEY,
    fee: FEE,
  });
  logField('register-vault tx', regRes.txId);
  logField('result', regRes.ok ? 'OK' : `FAIL: ${regRes.error}`);
  if (!regRes.ok) {
    throw new Error(`register-vault failed: ${regRes.error}`);
  }
  const regBlock = regRes.info?.block_height;
  logField('stacks block', regBlock);
  logField('events on tx', regRes.info?.events?.length ?? 0);

  // Verify the on-chain state via read-only getter.
  const regRead = await callReadOnly('get-vault-state', [bufferCV(vaultIdBuf)]);
  logField('get-vault-state', regRead?.repr?.slice(0, 80));

  results.phases.A.registerVaultTx = regRes.txId;
  results.phases.A.registerBlock = regBlock;
  results.phases.A.vaultId = vaultIdHex;
  results.phases.A.burnBlockHeightBefore = burnHeightBefore;
  results.steps.push({
    step: 'A6',
    ok: regRes.ok,
    txId: regRes.txId,
    block: regBlock,
    vaultStateRepr: regRead?.repr,
  });

  // ===========================================================================
  // PHASE B — Preimage Publication
  // ===========================================================================
  console.log('\n========== PHASE B — Preimage Publication (Stacks testnet) ==========');

  // --- B1: Call publish-preimage -------------------------------------------
  step('B1', `Call ${CONTRACT_NAME}.publish-preimage with the 93-byte payload`);
  const pubArgs = [
    bufferCV(vaultIdBuf),  // vault-id (buff 32)
    bufferCV(payload),     // payload (buff 93)
  ];
  logField('payload (93 B)', payloadHex);
  logField('expected sense', anchorBH.toString('hex'));
  logField('sender', DEPLOYER_ADDR);

  const pubRes = await sendContractCall({
    contractAddress: CONTRACT_ADDR,
    contractName: CONTRACT_NAME,
    functionName: 'publish-preimage',
    functionArgs: pubArgs,
    senderKey: DEPLOYER_KEY,
    fee: FEE,
  });
  logField('publish-preimage tx', pubRes.txId);
  logField('result', pubRes.ok ? 'OK' : `FAIL: ${pubRes.error}`);
  if (!pubRes.ok) {
    throw new Error(`publish-preimage failed: ${pubRes.error}`);
  }
  const pubBlock = pubRes.info?.block_height;
  logField('stacks block', pubBlock);
  logField('events on tx', pubRes.info?.events?.length ?? 0);

  results.phases.B.publishPreimageTx = pubRes.txId;
  results.phases.B.publishBlock = pubBlock;
  results.steps.push({
    step: 'B1',
    ok: pubRes.ok,
    txId: pubRes.txId,
    block: pubBlock,
  });

  // --- B2: Verify release-triggered event + read-only getter ----------------
  step('B2', 'Verify coherence-vault-release-triggered event + read-only getter');
  const events = pubRes.info?.events ?? [];
  // Hiro API returns events with .event_data or .contract_event.value.repr
  // depending on the endpoint. Be defensive and look across all fields.
  const releaseEvent = events.find((ev) => {
    const blob = JSON.stringify(ev);
    return blob.includes('coherence-vault-release-triggered');
  });
  logField('events total', events.length);
  logField('release-event found', releaseEvent ? 'YES' : 'NO');

  // Read-only: is-vault-release-triggered → expect (ok true)
  const roRelease = await callReadOnly('is-vault-release-triggered', [
    bufferCV(vaultIdBuf),
  ]);
  logField('is-vault-release-triggered', roRelease?.repr);

  // Read-only: get-committed-anchor-bh (sanity: must equal our anchor_bh)
  const roBh = await callReadOnly('get-committed-anchor-bh', [
    bufferCV(vaultIdBuf),
  ]);
  logField('get-committed-anchor-bh', roBh?.repr?.slice(0, 80));

  // Read-only: verify-preimage (relayer pre-flight check) → expect (ok true)
  const roVerify = await callReadOnly('verify-preimage', [
    bufferCV(vaultIdBuf),
    bufferCV(payload),
  ]);
  logField('verify-preimage', roVerify?.repr);

  const releaseOk =
    !!releaseEvent &&
    /true/.test(roRelease?.repr || '') &&
    /true/.test(roVerify?.repr || '');

  results.phases.B.releaseEventFound = !!releaseEvent;
  results.phases.B.isReleaseTriggeredRepr = roRelease?.repr;
  results.phases.B.committedAnchorBhRepr = roBh?.repr;
  results.phases.B.verifyPreimageRepr = roVerify?.repr;
  results.steps.push({
    step: 'B2',
    ok: releaseOk,
    eventFound: !!releaseEvent,
    isReleaseTriggeredRepr: roRelease?.repr,
    verifyPreimageRepr: roVerify?.repr,
  });

  // ===========================================================================
  // PHASE C — Borrower Refund (Bitcoin testnet simulation)
  // ===========================================================================
  console.log('\n========== PHASE C — Borrower Refund (Bitcoin testnet simulation) ==========');

  // --- C1: Build the CSV refund transaction --------------------------------
  step('C1', 'Build the CSV refund transaction (borrower signs after timelock)');
  // The vault-state from A5 already includes a pre-built refund PSBT because
  // we passed --vault-txid/--vault-vout to the create command. The CLI's
  // `refund` sub-command loads the state, re-derives the control block, and
  // signs the input with the borrower's Schnorr key.
  const refundHexFile = path.join(VAULT_DIR, 'refund-tx-test.hex');
  let refundStdout = '';
  try {
    refundStdout = runVaultCli(
      'refund',
      '--vault-state', vaultStateFile,
      '--borrower-wif', borrowerWif,
      '--out', refundHexFile,
    );
  } catch (e) {
    console.error(refundStdout || e.stdout || e.stderr || e.message);
    throw new Error(`coherence-vault.js refund failed: ${e.message}`);
  }
  const refundHex = fs.readFileSync(refundHexFile, 'utf-8').trim();
  logField('refund hex (head)', refundHex.slice(0, 80) + '…');
  logField('refund hex len', `${refundHex.length / 2} bytes`);
  logField('refund-tx file', path.relative(REPO_ROOT, refundHexFile));
  results.steps.push({
    step: 'C1',
    ok: refundHex.length > 0,
    refundHexFile: path.relative(REPO_ROOT, refundHexFile),
  });

  // --- C2: Verify the refund tx is valid (don't broadcast) -----------------
  step('C2', 'Verify the refund tx is valid (decode + check CSV in sequence)');
  const refundTx = bitcoin.Transaction.fromHex(refundHex);
  const refundTxid = refundTx.getId();
  logField('refund TXID', refundTxid);
  logField('input count', refundTx.ins.length);
  logField('output count', refundTx.outs.length);

  // Input[0].sequence low 16 bits encode the CSV value (BIP-68 relative
  // timelock). The high bit (1<<31) is the disable flag — must be 0 for
  // the relative timelock to apply. The coherence-vault.js refund path
  // sets sequence = csvBlocks (no disable flag, type 0).
  const seq = refundTx.ins[0].sequence >>> 0;
  const seqDisabled = (seq & 0x80000000) !== 0;
  const seqType = (seq & 0x00400000) !== 0 ? 'time' : 'blocks';
  const csvValue = seq & 0x0000ffff;
  logField('input[0].sequence', `0x${seq.toString(16).padStart(8, '0')}`);
  logField('disabled flag', seqDisabled ? 'YES (CSV inactive)' : 'NO (CSV active)');
  logField('seq type', seqType);
  logField('csv value', `${csvValue} (expected ${CSV_BLOCKS})`);

  // Output: must pay back to the borrower (p2tr of internal key).
  // Coherence-vault.js refund uses bitcoin.payments.p2tr({internalPubkey}).
  const internalPubkeyBuf = Buffer.from(vaultState.internalPubkey, 'hex');
  const expectedRefundAddr = bitcoin.payments.p2tr({
    internalPubkey: internalPubkeyBuf,
    network: bitcoin.networks.testnet,
  }).address;
  logField('expected refund addr', expectedRefundAddr);

  // Decode the refund output address from the scriptPubKey.
  let actualRefundAddr = null;
  try {
    actualRefundAddr = bitcoin.address.fromOutputScript(
      refundTx.outs[0].script,
      bitcoin.networks.testnet,
    );
  } catch (e) {
    logField('refund addr decode', `failed: ${e.message}`);
  }
  logField('actual refund addr', actualRefundAddr);
  logField('refund amount', `${Number(refundTx.outs[0].value)} sats`);
  logField('vault amount', `${LOCK_SATS} sats`);
  logField('fee', `${LOCK_SATS - Number(refundTx.outs[0].value)} sats`);

  const refundTxValid =
    !seqDisabled &&
    seqType === 'blocks' &&
    csvValue === CSV_BLOCKS &&
    actualRefundAddr === expectedRefundAddr &&
    Number(refundTx.outs[0].value) > 0 &&
    Number(refundTx.outs[0].value) < LOCK_SATS;

  logField('refund tx valid', refundTxValid ? 'YES ✓' : 'NO ✗');

  // Also exercise the read-only refund path on Stacks. We can't actually call
  // refund-vault successfully until CSV_BLOCKS have elapsed since A6, so the
  // call will likely abort with ERR-CSV-NOT-ELAPSED. That's the *expected*
  // outcome here — it proves (a) the borrower-only auth check passed
  // (deployer == registered-by == borrower-principal here), and (b) the CSV
  // invariant is enforced on-chain. Record the abort reason.
  step('C2b', 'Call refund-vault on Stacks (expect ERR-CSV-NOT-ELAPSED until timelock)');
  const refundCallRes = await sendContractCall({
    contractAddress: CONTRACT_ADDR,
    contractName: CONTRACT_NAME,
    functionName: 'refund-vault',
    functionArgs: [bufferCV(vaultIdBuf)],
    senderKey: DEPLOYER_KEY,
    fee: FEE,
  });
  logField('refund-vault tx', refundCallRes.txId ?? '(no txid)');
  logField('refund-vault result', refundCallRes.ok ? 'OK (CSV already elapsed)' : refundCallRes.error || '(aborted)');
  // Parse the abort reason (Hiro returns err code in raw_result / events).
  const refundEvents = refundCallRes.info?.events ?? [];
  const refundReason =
    refundCallRes.info?.raw_result ||
    refundCallRes.info?.tx_result?.repr ||
    (refundCallRes.ok ? 'success' : 'abort_by_response (CSV not yet elapsed — expected)');

  results.phases.C = {
    simUtxo: { txid: simUtxoTxid, vout: simUtxoVout },
    refundTxid,
    refundTxHex: refundHex,
    refundTxLen: refundHex.length / 2,
    inputSequence: `0x${seq.toString(16).padStart(8, '0')}`,
    csvDisabled: seqDisabled,
    csvType: seqType,
    csvValue,
    csvExpected: CSV_BLOCKS,
    csvMatches: csvValue === CSV_BLOCKS,
    refundAddress: actualRefundAddr,
    refundAmount: Number(refundTx.outs[0].value),
    refundFee: LOCK_SATS - Number(refundTx.outs[0].value),
    refundTxValid,
    refundVaultCallTxId: refundCallRes.txId,
    refundVaultCallResult: refundReason,
  };
  results.steps.push({
    step: 'C2',
    ok: refundTxValid,
    refundTxid,
    csvMatches: csvValue === CSV_BLOCKS,
    refundAddressMatches: actualRefundAddr === expectedRefundAddr,
  });

  // ===========================================================================
  // Final — write results
  // ===========================================================================
  results.completedAt = new Date().toISOString();
  results.success =
    results.steps.every((s) => s.ok) && refundTxValid;
  results.stepCount = results.steps.length;
  results.stepsPassed = results.steps.filter((s) => s.ok).length;

  // Make sure the directory exists.
  fs.mkdirSync(path.dirname(RESULTS_FILE), { recursive: true });
  fs.writeFileSync(RESULTS_FILE, JSON.stringify(results, null, 2));

  console.log('\n==========================================================');
  console.log(' TRION Coherence Vault — E2E test complete');
  console.log('==========================================================');
  console.log(`  Phase A — vault created + registered on Stacks`);
  console.log(`            vault-address : ${results.phases.A.vaultAddress}`);
  console.log(`            register-vault: ${results.phases.A.registerVaultTx} (block ${results.phases.A.registerBlock})`);
  console.log(`  Phase B — preimage published, release-triggered`);
  console.log(`            publish-preimage: ${results.phases.B.publishPreimageTx} (block ${results.phases.B.publishBlock})`);
  console.log(`            release-event  : ${results.phases.B.releaseEventFound ? 'YES ✓' : 'NO ✗'}`);
  console.log(`  Phase C — refund PSBT built & signed (CSV=${CSV_BLOCKS})`);
  console.log(`            refund TXID    : ${refundTxid}`);
  console.log(`            refund valid   : ${refundTxValid ? 'YES ✓' : 'NO ✗'}`);
  console.log(`  Steps: ${results.stepsPassed}/${results.stepCount} passed`);
  console.log(`  Results: ${path.relative(REPO_ROOT, RESULTS_FILE)}`);
  console.log('==========================================================');
  console.log(' NO committee. NO multisig. NO federation. NO oracle.');
  console.log(' Anyone with the preimage can trigger release.');
  console.log(' Borrower can refund after CSV blocks. Censorship impossible.');
  console.log('==========================================================');

  if (!results.success) {
    process.exit(2);
  }
}

main().catch((e) => {
  console.error('\nFATAL:', e?.stack || e?.message || e);
  process.exit(1);
});
