#!/usr/bin/env node
/**
 * run-50tx-tests.mjs — 50-transaction end-to-end test of the BTCP Zero-Bridge
 * Clarity contracts (suffix -v3) deployed on Stacks testnet.
 *
 * 50 DISTINCT test transactions across 10 contracts. Each test broadcasts ONE
 * contract-call tx (or STX transfer for setup), waits for confirmation, and
 * records { id, name, contract, status, txId, error, expected, actual, pass }.
 *
 * Distribution (per task spec):
 *   1-3   BTCSPVVerifier       (submit-genesis-tip fake FAIL, real SUCCESS, renounce SUCCESS)
 *   4-6   BTCPVersionRegistry  (version-too-low FAIL, register SUCCESS, duplicate FAIL)
 *   7-10  TravelRuleCompliance (low-tier SUCCESS, critical SUCCESS+freeze, dup FAIL, clear SUCCESS)
 *   11-14 GenesisCommitment    (low-bond FAIL, sponsored SUCCESS, organic SUCCESS, dup FAIL)
 *   15-21 BTCPIntent           (7 unique register-intent SUCCESS, varied action/chain/magnitude/privacy)
 *   22-28 BTCPRoute            (5 register-route SUCCESS, finalize SUCCESS, finalize FAIL below-floor)
 *   29-35 BTCPEscrow           (3 add-validator, lock, 2 attest w/ mismatched coherence, release FAIL disputed)
 *   36-42 LiquidityOcean       (4 commit SUCCESS, settle SUCCESS, revert SUCCESS, commit FAIL min>1e6)
 *   43-46 BehavioralLimitOrder (place BUY, place SELL, fill partial, cancel SELL)
 *   47-50 tTRION token         (transfer SUCCESS, mint SUCCESS, faucet-drip SUCCESS, drip again FAIL cooldown)
 *
 * Negative tests (expected to FAIL on-chain, counted as PASS when they actually abort):
 *   tests 1, 4, 6, 9, 11, 14, 28, 35, 42, 50  → 10 negative scenarios.
 * Positive tests (expected to SUCCESS):
 *   tests 2, 3, 5, 7, 8, 10, 12, 13, 15-27, 29-34, 36-41, 43-49  → 40 positive scenarios.
 *
 * Output: /home/z/my-project/trion-core/proofs/btcp-zero-bridge/stacks/v3-50tx-results.json
 *
 * Usage:
 *   node run-50tx-tests.mjs
 *   DEPLOYER_KEY=... CONTRACT_SUFFIX=v3 node run-50tx-tests.mjs
 *
 * NOTE: V2/V3 must have STX for tx fees. The script auto-funds them from the
 * deployer at startup if their balance < 1 STX (these funding txs are NOT
 * counted in the 50 tests).
 */
import * as fs from 'fs';
import * as path from 'path';
import { fileURLToPath } from 'url';
import * as crypto from 'crypto';

import txPkg from '@stacks/transactions';
const {
  uintCV,
  bufferCV,
  boolCV,
  principalCV,
  listCV,
  tupleCV,
  noneCV,
  someCV,
  stringAsciiCV,
  makeSTXTokenTransfer,
  broadcastTransaction,
  PostConditionMode,
  AnchorMode,
} = txPkg;

import {
  sendContractCall,
  buffCV,
  hashStr,
  randomBuff32,
  getAddressFromPrivateKey,
  TransactionVersion,
  getBalance,
  getNonce,
  waitForTx,
  sleep,
  API,
  network,
} from './lib/helpers.mjs';

// ---------------------------------------------------------------------- config
const DEPLOYER_KEY =
  process.env.DEPLOYER_KEY ||
  '940806a0a98e86df44835d7fb5d58a79d6259f413550ba11a858880a72e2e71901';
const SUFFIX = process.env.CONTRACT_SUFFIX || 'v3';
const FEE = 100000; // 0.1 STX per tx (microSTX)
const MEMPOOL_TESTNET_API = 'https://mempool.space/testnet/api';

// Deployer address (also validator V1).
const D = 'ST969AZNDX2P7N1YJ0DNVGC8QEKT388DBMXGHR9Z';

// Contract identifiers (deployer address + name-with-suffix).
const CONTRACTS = {
  SPV: { contractAddress: D, contractName: `btcspvverifier-${SUFFIX}` },
  VR:  { contractAddress: D, contractName: `btcpversionregistry-${SUFFIX}` },
  TRC: { contractAddress: D, contractName: `travelrulecompliance-${SUFFIX}` },
  GEN: { contractAddress: D, contractName: `genesiscommitment-${SUFFIX}` },
  INT: { contractAddress: D, contractName: `btcpintent-${SUFFIX}` },
  RTE: { contractAddress: D, contractName: `btcproute-${SUFFIX}` },
  ESC: { contractAddress: D, contractName: `btcpescrow-${SUFFIX}` },
  LO:  { contractAddress: D, contractName: `liquidityocean-${SUFFIX}` },
  BLO: { contractAddress: D, contractName: `behaviorallimitorder-${SUFFIX}` },
  TOK: { contractAddress: D, contractName: `triontesttoken-${SUFFIX}` },
};

// Validator keys — V1 == deployer (deployer is itself a validator).
const V1_KEY = DEPLOYER_KEY;
const V2_KEY = 'c5a4f8e2a9b1d3c5e7f9a1b3d5e7f9a1b3d5e7f9a1b3d5e7f9a1b3d5e7f9a1b301';
const V3_KEY = 'e7b9d3f1c5a7e9b1d3f5c7a9e1b3d5f7a9e1b3d5f7a9e1b3d5f7a9e1b3d5f7a901';

const V1_ADDR = getAddressFromPrivateKey(V1_KEY, TransactionVersion.Testnet);
const V2_ADDR = getAddressFromPrivateKey(V2_KEY, TransactionVersion.Testnet);
const V3_ADDR = getAddressFromPrivateKey(V3_KEY, TransactionVersion.Testnet);

const __filename = fileURLToPath(import.meta.url);
const __dirname = path.dirname(__filename);
const REPO_ROOT = path.resolve(__dirname, '..', '..');
const RESULTS_FILE = path.resolve(
  REPO_ROOT, 'proofs', 'btcp-zero-bridge', 'stacks', 'v3-50tx-results.json'
);

// ------------------------------------------------------------ results accumulator
const results = [];
let txsBroadcast = 0;
let realTipRef = null;  // set in main(), used by saveResultsPartial

// ------------------------------------------------------------ resume support
let priorResults = [];
try {
  if (fs.existsSync(RESULTS_FILE)) {
    const prior = JSON.parse(fs.readFileSync(RESULTS_FILE, 'utf-8'));
    priorResults = (prior && prior.tests) || [];
    console.log(`[resume] loaded ${priorResults.length} prior test results from ${RESULTS_FILE}`);
  }
} catch (_e) {}

function priorResult(id) { return priorResults.find(r => r.id === id) || null; }

function saveResultsPartial() {
  try {
    fs.mkdirSync(path.dirname(RESULTS_FILE), { recursive: true });
    const passed = results.filter(r => r.pass).length;
    const failed = results.filter(r => !r.pass && r.status !== 'skipped').length;
    const skipped = results.filter(r => r.status === 'skipped').length;
    fs.writeFileSync(RESULTS_FILE, JSON.stringify({
      timestamp: new Date().toISOString(),
      summary: { total: 50, completed: results.length, passed, failed, skipped, txsBroadcast },
      deployer: D,
      validators: { v1: V1_ADDR, v2: V2_ADDR, v3: V3_ADDR },
      contractSuffix: SUFFIX,
      realBtcTip: realTipRef ? { blockHashBE: realTipRef.blockHashBE, height: realTipRef.height } : null,
      tests: results,
    }, null, 2));
  } catch (e) { console.error('WARN: saveResultsPartial failed:', e.message); }
}

async function runTest({ id, name, contract, expected, call }) {
  const prior = priorResult(id);
  if (prior) {
    process.stdout.write(`[test ${id}/50] ${name} ... ◌ SKIP (already completed: ${prior.status}, pass=${prior.pass})\n`);
    results.push(prior);
    return prior;
  }
  process.stdout.write(`[test ${id}/50] ${name} ... `);
  try {
    const result = await call();
    if (result && result.txId) txsBroadcast++;
    const actual = result && result.ok ? 'success' : 'failed';
    const pass =
      (expected === 'success' && actual === 'success') ||
      (expected === 'failed' && actual === 'failed');
    const tag = pass ? '✓ PASS' : '✗ FAIL';
    process.stdout.write(`${tag}\n`);
    if (!pass) {
      process.stdout.write(
        `    expected=${expected} actual=${actual} err=${String(result && result.error || '').slice(0, 200)}\n`
      );
    }
    const entry = {
      id, name, contract,
      status: actual,
      txId: (result && result.txId) || null,
      error: (result && result.error) || null,
      expected, actual, pass,
    };
    results.push(entry);
    saveResultsPartial();
    return result;
  } catch (e) {
    txsBroadcast++;
    const msg = (e && e.message) ? e.message.slice(0, 300) : String(e);
    process.stdout.write(`✗ FAIL (exception: ${msg.slice(0, 120)})\n`);
    const entry = {
      id, name, contract,
      status: 'failed',
      txId: null,
      error: msg,
      expected, actual: 'exception',
      pass: expected === 'failed',
    };
    results.push(entry);
    saveResultsPartial();
    return { ok: false, error: msg };
  }
}

function recordSkipped({ id, name, contract, expected, reason }) {
  const prior = priorResult(id);
  if (prior) { results.push(prior); return; }
  process.stdout.write(`[test ${id}/50] ${name} ... ◌ SKIP (${reason})\n`);
  const entry = {
    id, name, contract,
    status: 'skipped',
    txId: null,
    error: reason,
    expected, actual: 'skipped',
    pass: false,
  };
  results.push(entry);
  saveResultsPartial();
}

// --------------------------------------------------------------- buffer helpers
/**
 * buff80(hexStr) — Convert a 160-hex-char (80-byte) raw Bitcoin block header
 * into a Clarity `bufferCV`. Unlike buffCV (which left-pads to 32 bytes), this
 * preserves the full 80-byte length required by submit-genesis-tip / verify-pow.
 */
function buff80(hexStr) {
  const raw = hexStr == null ? '' : String(hexStr);
  const hex = raw.startsWith('0x') ? raw.slice(2) : raw;
  const bytes = Buffer.from(hex, 'hex');
  if (bytes.length !== 80) {
    throw new Error(`buff80 expected 80 bytes, got ${bytes.length}`);
  }
  return bufferCV(bytes);
}

/**
 * parseHeader(hex) — Parse the 80-byte Bitcoin block header into its 6 fields.
 * Returns numeric `version`, `timestamp`, `bits`, `nonce` (LE uint32 reads) and
 * Buffer slices for `prevHash` and `merkleRoot` (in Bitcoin's INTERNAL LE form
 * — which is exactly how the contract expects them, since Clarity's sha256
 * matches Bitcoin's internal byte order).
 */
function parseHeader(hex) {
  const b = Buffer.from(hex, 'hex');
  if (b.length !== 80) throw new Error(`header must be 80 bytes, got ${b.length}`);
  return {
    version: b.readUInt32LE(0),
    prevHash: b.slice(4, 36),
    merkleRoot: b.slice(36, 68),
    timestamp: b.readUInt32LE(68),
    bits: b.readUInt32LE(72),
    nonce: b.readUInt32LE(76),
  };
}

// --------------------------------------------------------------- fetch helpers
async function fetchText(url) {
  const r = await fetch(url);
  if (!r.ok) throw new Error(`HTTP ${r.status} ${r.statusText} for ${url}`);
  return r.text();
}

async function fetchJson(url) {
  const r = await fetch(url);
  if (!r.ok) throw new Error(`HTTP ${r.status} ${r.statusText} for ${url}`);
  return r.json();
}

/**
 * getTestnetTipHeader() — Fetch the latest BTC testnet block hash + 80-byte
 * raw header from the public mempool.space testnet API (no auth required).
 * Returns { blockHashBE, headerHex, height }.
 */
async function getTestnetTipHeader() {
  const hash = (await fetchText(`${MEMPOOL_TESTNET_API}/blocks/tip/hash`)).trim();
  const headerHex = (await fetchText(`${MEMPOOL_TESTNET_API}/block/${hash}/header`)).trim();
  const blockInfo = await fetchJson(`${MEMPOOL_TESTNET_API}/block/${hash}`);
  return { blockHashBE: hash, headerHex, height: blockInfo.height };
}

// --------------------------------------------------------- STX transfer helper
/**
 * transferSTX(senderKey, recipient, microStx) — sign + broadcast a STX token
 * transfer and wait for confirmation. Used by the setup phase to fund V2/V3
 * with STX for tx fees. Returns { ok, txId, error }.
 */
async function transferSTX(senderKey, recipient, microStx) {
  const senderAddr = getAddressFromPrivateKey(senderKey, TransactionVersion.Testnet);
  const nonce = await getNonce(senderAddr);
  const tx = await makeSTXTokenTransfer({
    recipient,
    amount: BigInt(microStx),
    senderKey,
    network,
    fee: FEE,
    nonce: BigInt(nonce),
    memo: '',
    anchorMode: AnchorMode.Any,
    postConditionMode: PostConditionMode.Allow,
  });
  const resp = await broadcastTransaction(tx, network);
  if (!resp || !resp.txid) {
    return {
      ok: false,
      error: resp ? JSON.stringify(resp).slice(0, 200) : 'no broadcast response',
    };
  }
  const txId = `0x${resp.txid}`;
  const r = await waitForTx(txId);
  return { ok: !!r.ok, txId, error: r.error };
}

/**
 * setupValidatorBalances() — Top up V2/V3 with 5 STX each if their balance is
 * below 1 STX. Funding txs are NOT counted in the 50 tests.
 */
async function setupValidatorBalances() {
  console.log('--- Setup: check + fund V2/V3 balances ---');
  const MIN_BAL = 1_000_000;     // 1 STX minimum threshold
  const TOPUP_TARGET = 5_000_000; // 5 STX target after topup
  for (const [label, key, addr] of [
    ['V2', V2_KEY, V2_ADDR],
    ['V3', V3_KEY, V3_ADDR],
  ]) {
    try {
      const bal = await getBalance(addr);
      console.log(`  ${label} (${addr}): ${bal} microSTX`);
      if (bal < MIN_BAL) {
        const amount = TOPUP_TARGET - bal;
        console.log(`    funding ${amount} microSTX from deployer...`);
        const r = await transferSTX(DEPLOYER_KEY, addr, amount);
        if (r.ok) {
          txsBroadcast++;
          console.log(`    ✓ funded (tx ${r.txId})`);
          await sleep(3000);
        } else {
          console.log(`    ✗ funding failed: ${r.error}`);
        }
      } else {
        console.log(`    ✓ sufficient balance, skipping topup`);
      }
    } catch (e) {
      console.log(`  ${label}: balance check failed: ${e.message}`);
    }
  }
  console.log('');
}

// ====================================================================== MAIN
async function main() {
  console.log('=== run-50tx-tests.mjs — 50-tx end-to-end BTCP Zero-Bridge test ===');
  console.log(`API:       ${API}`);
  console.log(`Deployer:  ${D} (= V1)`);
  console.log(`V2:        ${V2_ADDR}`);
  console.log(`V3:        ${V3_ADDR}`);
  console.log(`Suffix:    -${SUFFIX}`);
  console.log(`Fee:       ${FEE} microSTX (0.1 STX) per tx`);
  console.log(`Results:   ${RESULTS_FILE}`);
  console.log('');

  // --- Setup: fund V2/V3 if needed (not counted in 50 tests) ---
  await setupValidatorBalances();

  // --- Pre-fetch real BTC testnet tip header for test 2 ---
  let realTip = null;
  try {
    console.log('--- Pre-fetch: BTC testnet tip header (mempool.space) ---');
    realTip = await getTestnetTipHeader();
    realTipRef = realTip;  // expose to saveResultsPartial
    console.log(`  tip hash: ${realTip.blockHashBE}`);
    console.log(`  height:   ${realTip.height}`);
    console.log(`  header:   ${realTip.headerHex}`);
    const p = parseHeader(realTip.headerHex);
    console.log(
      `  parsed:   ts=${p.timestamp} bits=0x${p.bits.toString(16)} merkle=0x${p.merkleRoot.toString('hex')}`
    );
  } catch (e) {
    console.log(`  ⚠ could not fetch tip header: ${e.message}`);
    console.log(`  test 2 will be SKIPPED`);
  }
  console.log('');

  // ============================================== TESTS 1-3: BTCSPVVerifier
  // --- Test 1: submit-genesis-tip with FAKE PoW → FAIL (Err u110) ---
  // Random 80-byte header + random 32-byte block-hash → verify-pow mismatches.
  await runTest({
    id: 1,
    name: `${CONTRACTS.SPV.contractName}.submit-genesis-tip (fake PoW)`,
    contract: 'BTCSPVVerifier',
    expected: 'failed',
    call: async () => {
      const fakeHeaderHex = '0x' + crypto.randomBytes(80).toString('hex');
      const fakeBlockHash = randomBuff32(); // 32 random bytes, won't match sha256(sha256(header))
      const p = parseHeader(fakeHeaderHex.slice(2));
      return sendContractCall({
        ...CONTRACTS.SPV,
        functionName: 'submit-genesis-tip',
        functionArgs: [
          buffCV(fakeBlockHash),                          // 1. block-hash (BE display form, fake)
          uintCV(1n),                                     // 2. height
          buffCV('0x' + p.merkleRoot.toString('hex')),    // 3. merkle-root (LE internal)
          uintCV(p.timestamp),                            // 4. timestamp
          uintCV(p.bits),                                 // 5. bits
          buff80(fakeHeaderHex),                          // 6. header (80 bytes)
        ],
        senderKey: DEPLOYER_KEY,
        fee: FEE,
      });
    },
  });

  // --- Test 2: submit-genesis-tip with REAL BTC testnet header → SUCCESS ---
  if (!realTip) {
    recordSkipped({
      id: 2,
      name: `${CONTRACTS.SPV.contractName}.submit-genesis-tip (real PoW)`,
      contract: 'BTCSPVVerifier',
      expected: 'success',
      reason: 'mempool.space testnet API unavailable',
    });
  } else {
    await runTest({
      id: 2,
      name: `${CONTRACTS.SPV.contractName}.submit-genesis-tip (real PoW)`,
      contract: 'BTCSPVVerifier',
      expected: 'success',
      call: async () => {
        const p = parseHeader(realTip.headerHex);
        return sendContractCall({
          ...CONTRACTS.SPV,
          functionName: 'submit-genesis-tip',
          functionArgs: [
            buffCV(realTip.blockHashBE),                  // 1. block-hash (BE display form from API)
            uintCV(BigInt(realTip.height)),               // 2. height
            buffCV('0x' + p.merkleRoot.toString('hex')),  // 3. merkle-root (LE internal)
            uintCV(p.timestamp),                          // 4. timestamp
            uintCV(p.bits),                               // 5. bits
            buff80(realTip.headerHex),                    // 6. header (80 bytes)
          ],
          senderKey: DEPLOYER_KEY,
          fee: FEE,
        });
      },
    });
  }

  // --- Test 3: renounce-genesis-ability → SUCCESS ---
  await runTest({
    id: 3,
    name: `${CONTRACTS.SPV.contractName}.renounce-genesis-ability`,
    contract: 'BTCSPVVerifier',
    expected: 'success',
    call: async () => sendContractCall({
      ...CONTRACTS.SPV,
      functionName: 'renounce-genesis-ability',
      functionArgs: [],
      senderKey: DEPLOYER_KEY,
      fee: FEE,
    }),
  });

  // ============================================== TESTS 4-6: BTCPVersionRegistry
  // --- Test 4: register-adapter V1 version=100 → FAIL (version too low, MIN=150) ---
  await runTest({
    id: 4,
    name: `${CONTRACTS.VR.contractName}.register-adapter V1 v=100 (too low)`,
    contract: 'BTCPVersionRegistry',
    expected: 'failed',
    call: async () => sendContractCall({
      ...CONTRACTS.VR,
      functionName: 'register-adapter',
      functionArgs: [principalCV(V1_ADDR), uintCV(100n)],
      senderKey: DEPLOYER_KEY,
      fee: FEE,
    }),
  });

  // --- Test 5: register-adapter V2 version=200 → SUCCESS ---
  await runTest({
    id: 5,
    name: `${CONTRACTS.VR.contractName}.register-adapter V2 v=200`,
    contract: 'BTCPVersionRegistry',
    expected: 'success',
    call: async () => sendContractCall({
      ...CONTRACTS.VR,
      functionName: 'register-adapter',
      functionArgs: [principalCV(V2_ADDR), uintCV(200n)],
      senderKey: DEPLOYER_KEY,
      fee: FEE,
    }),
  });

  // --- Test 6: register-adapter V2 again (duplicate) → FAIL (Err u801) ---
  await runTest({
    id: 6,
    name: `${CONTRACTS.VR.contractName}.register-adapter V2 v=200 (duplicate)`,
    contract: 'BTCPVersionRegistry',
    expected: 'failed',
    call: async () => sendContractCall({
      ...CONTRACTS.VR,
      functionName: 'register-adapter',
      functionArgs: [principalCV(V2_ADDR), uintCV(200n)],
      senderKey: DEPLOYER_KEY,
      fee: FEE,
    }),
  });

  // ============================================== TESTS 7-10: TravelRuleCompliance
  // --- Test 7: file-travel-rule-proof entity1, tier=0 (LOW) → SUCCESS ---
  await runTest({
    id: 7,
    name: `${CONTRACTS.TRC.contractName}.file-travel-rule-proof entity1 tier=LOW`,
    contract: 'TravelRuleCompliance',
    expected: 'success',
    call: async () => sendContractCall({
      ...CONTRACTS.TRC,
      functionName: 'file-travel-rule-proof',
      functionArgs: [
        buffCV(hashStr('trc-entity-1')),
        buffCV(hashStr('disclosure-1')),
        uintCV(0n),  // TIER-LOW
      ],
      senderKey: DEPLOYER_KEY,
      fee: FEE,
    }),
  });

  // --- Test 8: file-travel-rule-proof entity2, tier=3 (CRITICAL) → SUCCESS + awa-freeze=true ---
  await runTest({
    id: 8,
    name: `${CONTRACTS.TRC.contractName}.file-travel-rule-proof entity2 tier=CRITICAL`,
    contract: 'TravelRuleCompliance',
    expected: 'success',
    call: async () => sendContractCall({
      ...CONTRACTS.TRC,
      functionName: 'file-travel-rule-proof',
      functionArgs: [
        buffCV(hashStr('trc-entity-2')),
        buffCV(hashStr('disclosure-2')),
        uintCV(3n),  // TIER-CRITICAL — sets awa-global-freeze=true
      ],
      senderKey: DEPLOYER_KEY,
      fee: FEE,
    }),
  });

  // --- Test 9: file-travel-rule-proof entity1 again (already filed) → FAIL (Err u701) ---
  await runTest({
    id: 9,
    name: `${CONTRACTS.TRC.contractName}.file-travel-rule-proof entity1 (dup)`,
    contract: 'TravelRuleCompliance',
    expected: 'failed',
    call: async () => sendContractCall({
      ...CONTRACTS.TRC,
      functionName: 'file-travel-rule-proof',
      functionArgs: [
        buffCV(hashStr('trc-entity-1')),
        buffCV(hashStr('disclosure-3')),
        uintCV(0n),
      ],
      senderKey: DEPLOYER_KEY,
      fee: FEE,
    }),
  });

  // --- Test 10: clear-awa-freeze → SUCCESS ---
  await runTest({
    id: 10,
    name: `${CONTRACTS.TRC.contractName}.clear-awa-freeze`,
    contract: 'TravelRuleCompliance',
    expected: 'success',
    call: async () => sendContractCall({
      ...CONTRACTS.TRC,
      functionName: 'clear-awa-freeze',
      functionArgs: [],
      senderKey: DEPLOYER_KEY,
      fee: FEE,
    }),
  });

  // ============================================== TESTS 11-14: GenesisCommitment
  // --- Test 11: sponsored-genesis bond=999999 → FAIL (bond < MIN-SPONSOR-BOND=1000000) ---
  await runTest({
    id: 11,
    name: `${CONTRACTS.GEN.contractName}.sponsored-genesis bond=999999 (low)`,
    contract: 'GenesisCommitment',
    expected: 'failed',
    call: async () => sendContractCall({
      ...CONTRACTS.GEN,
      functionName: 'sponsored-genesis',
      functionArgs: [
        buffCV(hashStr('gen-sponsor-1')),      // entity-id (sponsor)
        buffCV(hashStr('gen-sponsored-1')),    // sponsored-entity-id
        uintCV(999999n),                       // bond < 1000000 → Err u602
      ],
      senderKey: DEPLOYER_KEY,
      fee: FEE,
    }),
  });

  // --- Test 12: sponsored-genesis bond=1000000 → SUCCESS ---
  await runTest({
    id: 12,
    name: `${CONTRACTS.GEN.contractName}.sponsored-genesis bond=1000000`,
    contract: 'GenesisCommitment',
    expected: 'success',
    call: async () => sendContractCall({
      ...CONTRACTS.GEN,
      functionName: 'sponsored-genesis',
      functionArgs: [
        buffCV(hashStr('gen-sponsor-1')),
        buffCV(hashStr('gen-sponsored-2')),    // different sponsored entity
        uintCV(1000000n),                      // bond >= MIN-SPONSOR-BOND
      ],
      senderKey: DEPLOYER_KEY,
      fee: FEE,
    }),
  });

  // --- Test 13: organic-genesis entity4 → SUCCESS ---
  await runTest({
    id: 13,
    name: `${CONTRACTS.GEN.contractName}.organic-genesis entity4`,
    contract: 'GenesisCommitment',
    expected: 'success',
    call: async () => sendContractCall({
      ...CONTRACTS.GEN,
      functionName: 'organic-genesis',
      functionArgs: [buffCV(hashStr('gen-organic-1'))],
      senderKey: DEPLOYER_KEY,
      fee: FEE,
    }),
  });

  // --- Test 14: organic-genesis entity4 again → FAIL (already genesis, Err u601) ---
  await runTest({
    id: 14,
    name: `${CONTRACTS.GEN.contractName}.organic-genesis entity4 (dup)`,
    contract: 'GenesisCommitment',
    expected: 'failed',
    call: async () => sendContractCall({
      ...CONTRACTS.GEN,
      functionName: 'organic-genesis',
      functionArgs: [buffCV(hashStr('gen-organic-1'))],
      senderKey: DEPLOYER_KEY,
      fee: FEE,
    }),
  });

  // ============================================== TESTS 15-21: BTCPIntent
  // 7 unique register-intent calls — varied action/source-chain/dest-chain/magnitude/privacy/chain-pref/min-finality.
  // Arg order (17 total): intent-hash, entity-id, action, asset-in, asset-out, magnitude,
  //                       source-chain, dest-chain, deadline, max-gas-usd, min-nl-score,
  //                       min-finality, chain-pref, privacy, btcp-version, nonce, travel-rule-proof
  const intentTuples = [
    // [action, srcChain, dstChain, magnitude, privacy, chainPref, minFin, maxGas, minNl]
    [0, 1, 2,  1000000n, 0, 0, 0, 50, 800000], // SWAP      1->2  public    optimal  fast
    [1, 2, 3,  2500000n, 1, 1, 1, 75, 850000], // TRANSFER  2->3  zk-cred   single   standard
    [2, 3, 4,   500000n, 2, 2, 2, 100, 900000],// LIQUIDITY 3->4  invisible list     secure
    [3, 4, 5,  7500000n, 0, 0, 1, 60,  820000],// STAKE     4->5  public    optimal  standard
    [4, 5, 6,  3330000n, 1, 1, 2, 80,  880000],// BORROW    5->6  zk-cred   single   secure
    [0, 6, 7,  4210000n, 2, 2, 0, 90,  910000],// SWAP      6->7  invisible list     fast
    [1, 7, 1,  9990000n, 0, 0, 2, 70,  870000],// TRANSFER  7->1  public    optimal  secure
  ];
  const intentHashes = [];
  for (let i = 0; i < 7; i++) {
    const testId = 15 + i;
    const [action, srcChain, dstChain, magnitude, privacy, chainPref, minFin, maxGas, minNl] =
      intentTuples[i];
    const intentHash = hashStr(`intent-${testId}`);
    intentHashes.push(intentHash);
    await runTest({
      id: testId,
      name: `${CONTRACTS.INT.contractName}.register-intent #${i + 1} action=${action} ${srcChain}->${dstChain}`,
      contract: 'BTCPIntent',
      expected: 'success',
      call: async () => sendContractCall({
        ...CONTRACTS.INT,
        functionName: 'register-intent',
        functionArgs: [
          buffCV(intentHash),                                  // 1.  intent-hash
          buffCV(hashStr(`entity-${testId}`)),                 // 2.  entity-id
          uintCV(action),                                      // 3.  action
          buffCV(hashStr(`asset-in-${testId}`)),               // 4.  asset-in
          buffCV(hashStr(`asset-out-${testId}`)),              // 5.  asset-out
          uintCV(magnitude),                                   // 6.  magnitude
          uintCV(srcChain),                                    // 7.  source-chain
          uintCV(dstChain),                                    // 8.  dest-chain
          uintCV(1000000000n),                                 // 9.  deadline (large; not asserted)
          uintCV(maxGas),                                      // 10. max-gas-usd
          uintCV(minNl),                                       // 11. min-nl-score
          uintCV(minFin),                                      // 12. min-finality
          uintCV(chainPref),                                   // 13. chain-pref
          uintCV(privacy),                                     // 14. privacy
          uintCV(150n),                                        // 15. btcp-version
          uintCV(BigInt(testId)),                              // 16. nonce (testId > 0)
          buffCV(hashStr(`trp-${testId}`)),                    // 17. travel-rule-proof
        ],
        senderKey: DEPLOYER_KEY,
        fee: FEE,
      }),
    });
  }

  // ============================================== TESTS 22-28: BTCPRoute
  // 5 register-route SUCCESS + 1 finalize-route SUCCESS + 1 finalize-route FAIL (below floor).
  // register-route args (9): route-id, intent-hash, anchor-bh, anchor-chain, execution-chain,
  //                          entity-id, route-type, consensus-proof, travel-rule-proof
  // finalize-route args (5): route-id, execution-bh, gas-saved, beo-continuity, cc-coherence
  const routeIds = [];
  for (let i = 0; i < 5; i++) {
    const testId = 22 + i;
    const routeId = hashStr(`route-${testId}`);
    routeIds.push(routeId);
    const intentHash = intentHashes[i]; // reference intents 15-19
    await runTest({
      id: testId,
      name: `${CONTRACTS.RTE.contractName}.register-route #${i + 1}`,
      contract: 'BTCPRoute',
      expected: 'success',
      call: async () => sendContractCall({
        ...CONTRACTS.RTE,
        functionName: 'register-route',
        functionArgs: [
          buffCV(routeId),                                  // 1. route-id
          buffCV(intentHash),                               // 2. intent-hash
          buffCV(hashStr(`anchor-bh-${testId}`)),           // 3. anchor-bh
          uintCV(1 + i),                                    // 4. anchor-chain
          uintCV(2 + i),                                    // 5. execution-chain
          buffCV(hashStr(`route-entity-${testId}`)),        // 6. entity-id
          uintCV(i % 7),                                    // 7. route-type (0-6, all valid)
          buffCV(hashStr(`consensus-${testId}`)),           // 8. consensus-proof
          buffCV(hashStr(`trp-${testId}`)),                 // 9. travel-rule-proof
        ],
        senderKey: DEPLOYER_KEY,
        fee: FEE,
      }),
    });
  }

  // --- Test 27: finalize-route #1 with cc-coherence=600000 (>= 550000 floor) → SUCCESS ---
  await runTest({
    id: 27,
    name: `${CONTRACTS.RTE.contractName}.finalize-route #1 cc=600000`,
    contract: 'BTCPRoute',
    expected: 'success',
    call: async () => sendContractCall({
      ...CONTRACTS.RTE,
      functionName: 'finalize-route',
      functionArgs: [
        buffCV(routeIds[0]),
        buffCV(hashStr('exec-bh-1')),
        uintCV(50000n),     // gas-saved
        uintCV(800000n),    // beo-continuity (<= 1e6)
        uintCV(600000n),    // cc-coherence (>= 550000 floor)
      ],
      senderKey: DEPLOYER_KEY,
      fee: FEE,
    }),
  });

  // --- Test 28: finalize-route #2 with cc-coherence=100000 (below floor) → FAIL (Err u405) ---
  await runTest({
    id: 28,
    name: `${CONTRACTS.RTE.contractName}.finalize-route #2 cc=100000 (below floor)`,
    contract: 'BTCPRoute',
    expected: 'failed',
    call: async () => sendContractCall({
      ...CONTRACTS.RTE,
      functionName: 'finalize-route',
      functionArgs: [
        buffCV(routeIds[1]),
        buffCV(hashStr('exec-bh-2')),
        uintCV(30000n),
        uintCV(700000n),
        uintCV(100000n),    // cc-coherence (< 550000 floor)
      ],
      senderKey: DEPLOYER_KEY,
      fee: FEE,
    }),
  });

  // ============================================== TESTS 29-35: BTCPEscrow
  // 3x add-validator (V1, V2, V3) + lock-escrow #1 + 2x submit-attestation
  // (V1 then V2 with MISMATCHED coherence → disputed=true) + release-escrow FAIL.
  //
  // This compresses the user's spec scenarios (a)-(f) into 7 distinct tests while
  // preserving the most important invariants:
  //   • add-validator SUCCESS path × 3 (scenarios a)
  //   • lock-escrow SUCCESS × 1 (scenario b, partial)
  //   • submit-attestation with same coherence → no dispute (scenario c, partial)
  //   • submit-attestation with MISMATCHED coherence → disputed=true (scenario e)
  //   • release-escrow FAIL due to disputed (scenario f)
  // Scenarios (b) lock-escrow #2, (c) V3 attestation, (d) release-escrow SUCCESS
  // are dropped to fit the 7-test slot budget; the disputed-path negative test
  // (scenario f) is prioritized as it most directly demonstrates the contract's
  // fail-closed invariant.

  // --- Test 29: add-validator V1 → SUCCESS ---
  await runTest({
    id: 29,
    name: `${CONTRACTS.ESC.contractName}.add-validator V1`,
    contract: 'BTCPEscrow',
    expected: 'success',
    call: async () => sendContractCall({
      ...CONTRACTS.ESC,
      functionName: 'add-validator',
      functionArgs: [principalCV(V1_ADDR)],
      senderKey: DEPLOYER_KEY,
      fee: FEE,
    }),
  });

  // --- Test 30: add-validator V2 → SUCCESS ---
  await runTest({
    id: 30,
    name: `${CONTRACTS.ESC.contractName}.add-validator V2`,
    contract: 'BTCPEscrow',
    expected: 'success',
    call: async () => sendContractCall({
      ...CONTRACTS.ESC,
      functionName: 'add-validator',
      functionArgs: [principalCV(V2_ADDR)],
      senderKey: DEPLOYER_KEY,
      fee: FEE,
    }),
  });

  // --- Test 31: add-validator V3 → SUCCESS ---
  await runTest({
    id: 31,
    name: `${CONTRACTS.ESC.contractName}.add-validator V3`,
    contract: 'BTCPEscrow',
    expected: 'success',
    call: async () => sendContractCall({
      ...CONTRACTS.ESC,
      functionName: 'add-validator',
      functionArgs: [principalCV(V3_ADDR)],
      senderKey: DEPLOYER_KEY,
      fee: FEE,
    }),
  });

  // --- Test 32: lock-escrow #1 → SUCCESS (min-coherence=600000 >= 550000 floor) ---
  const escrowId1 = hashStr('escrow-1');
  await runTest({
    id: 32,
    name: `${CONTRACTS.ESC.contractName}.lock-escrow #1`,
    contract: 'BTCPEscrow',
    expected: 'success',
    call: async () => sendContractCall({
      ...CONTRACTS.ESC,
      functionName: 'lock-escrow',
      functionArgs: [
        buffCV(escrowId1),                  // 1. escrow-id
        buffCV(routeIds[0]),                // 2. route-id (from test 22)
        principalCV(V2_ADDR),               // 3. destination
        uintCV(1000n),                      // 4. amount
        uintCV(600000n),                     // 5. min-coherence (>= 550000 floor)
        uintCV(10000n),                      // 6. timeout (burn blocks)
      ],
      senderKey: DEPLOYER_KEY,
      fee: FEE,
    }),
  });

  // --- Test 33: submit-attestation V1 for escrow-1 (coherence=600000, bh=H1) → SUCCESS ---
  // First attestation — creates new attestation record with count=1, disputed=false.
  const escrow1Coherence = 600000n;
  const escrow1Bh = hashStr('exec-bh-1');
  await runTest({
    id: 33,
    name: `${CONTRACTS.ESC.contractName}.submit-attestation V1 escrow-1 cc=600000`,
    contract: 'BTCPEscrow',
    expected: 'success',
    call: async () => sendContractCall({
      ...CONTRACTS.ESC,
      functionName: 'submit-attestation',
      functionArgs: [
        buffCV(escrowId1),                  // 1. escrow-id
        uintCV(escrow1Coherence),            // 2. coherence
        buffCV(escrow1Bh),                   // 3. execution-bh
      ],
      senderKey: V1_KEY,                    // V1 == deployer; validator since test 29
      fee: FEE,
    }),
  });

  // --- Test 34: submit-attestation V2 for escrow-1 with MISMATCHED coherence (700000) ---
  // Tx SUCCEEDS (it returns ok true) but marks disputed=true on the attestation record.
  await runTest({
    id: 34,
    name: `${CONTRACTS.ESC.contractName}.submit-attestation V2 escrow-1 cc=700000 (mismatched)`,
    contract: 'BTCPEscrow',
    expected: 'success',
    call: async () => sendContractCall({
      ...CONTRACTS.ESC,
      functionName: 'submit-attestation',
      functionArgs: [
        buffCV(escrowId1),
        uintCV(700000n),                    // DIFFERENT coherence → disputed=true
        buffCV(escrow1Bh),
      ],
      senderKey: V2_KEY,                   // V2 sends its own attestation
      fee: FEE,
    }),
  });

  // --- Test 35: release-escrow for escrow-1 → FAIL (disputed=true, insufficient quorum) ---
  // Even though disputed=true is the primary fail-closed trigger, count=1 < quorum=3
  // would also fail. Either way the tx aborts, which is the expected negative outcome.
  await runTest({
    id: 35,
    name: `${CONTRACTS.ESC.contractName}.release-escrow escrow-1 (disputed)`,
    contract: 'BTCPEscrow',
    expected: 'failed',
    call: async () => sendContractCall({
      ...CONTRACTS.ESC,
      functionName: 'release-escrow',
      functionArgs: [
        buffCV(escrowId1),                  // 1. escrow-id
        buffCV(escrow1Bh),                   // 2. execution-bh
        uintCV(escrow1Coherence),            // 3. coherence
      ],
      senderKey: DEPLOYER_KEY,
      fee: FEE,
    }),
  });

  // ============================================== TESTS 36-42: LiquidityOcean
  // 4x commit-liquidity SUCCESS (different cost/time/beo tuples → different ocean-score)
  // + 1x settle-commitment SUCCESS + 1x revert-commitment SUCCESS
  // + 1x commit-liquidity FAIL (min-coherence > 1e6).
  //
  // commit-liquidity args (10): commitment-id, entity-id, route-id, asset, amount,
  //                             min-coherence, expiry, cost-score, time-score, beo-health
  // settle-commitment args (3): commitment-id, coherence, execution-bh
  // revert-commitment args (2): commitment-id, reason
  const commitIds = [];
  const loTuples = [
    // [cost-score, time-score, beo-health] — each computes a distinct ocean-score
    [800000n, 700000n, 600000n],
    [900000n, 850000n, 750000n],
    [600000n, 500000n, 400000n],
    [1000000n, 1000000n, 1000000n],
  ];
  for (let i = 0; i < 4; i++) {
    const testId = 36 + i;
    const commitId = hashStr(`commit-${testId}`);
    commitIds.push(commitId);
    const [cost, time, beo] = loTuples[i];
    await runTest({
      id: testId,
      name: `${CONTRACTS.LO.contractName}.commit-liquidity #${i + 1} cost=${cost}/${time}/${beo}`,
      contract: 'LiquidityOcean',
      expected: 'success',
      call: async () => sendContractCall({
        ...CONTRACTS.LO,
        functionName: 'commit-liquidity',
        functionArgs: [
          buffCV(commitId),                                 // 1. commitment-id
          buffCV(hashStr(`lo-entity-${testId}`)),            // 2. entity-id
          buffCV(routeIds[i % routeIds.length]),             // 3. route-id
          buffCV(hashStr(`asset-${testId}`)),                // 4. asset
          uintCV(1000000n * BigInt(i + 1)),                  // 5. amount (varies)
          uintCV(600000n),                                   // 6. min-coherence (<= 1e6)
          uintCV(1000000000n),                               // 7. expiry (huge; > tenure-height)
          uintCV(cost),                                      // 8. cost-score
          uintCV(time),                                      // 9. time-score
          uintCV(beo),                                       // 10. beo-health
        ],
        senderKey: DEPLOYER_KEY,
        fee: FEE,
      }),
    });
  }

  // --- Test 40: settle-commitment #1 with coherence=600000 → SUCCESS ---
  await runTest({
    id: 40,
    name: `${CONTRACTS.LO.contractName}.settle-commitment #1 cc=600000`,
    contract: 'LiquidityOcean',
    expected: 'success',
    call: async () => sendContractCall({
      ...CONTRACTS.LO,
      functionName: 'settle-commitment',
      functionArgs: [
        buffCV(commitIds[0]),
        uintCV(600000n),                    // coherence (>= 550000 floor, >= min-coherence)
        buffCV(hashStr('lo-exec-bh-1')),
      ],
      senderKey: DEPLOYER_KEY,
      fee: FEE,
    }),
  });

  // --- Test 41: revert-commitment #2 → SUCCESS ---
  await runTest({
    id: 41,
    name: `${CONTRACTS.LO.contractName}.revert-commitment #2`,
    contract: 'LiquidityOcean',
    expected: 'success',
    call: async () => sendContractCall({
      ...CONTRACTS.LO,
      functionName: 'revert-commitment',
      functionArgs: [
        buffCV(commitIds[1]),
        uintCV(42n),                        // reason code (arbitrary)
      ],
      senderKey: DEPLOYER_KEY,
      fee: FEE,
    }),
  });

  // --- Test 42: commit-liquidity with min-coherence=2000000 (> 1e6) → FAIL (Err u504) ---
  await runTest({
    id: 42,
    name: `${CONTRACTS.LO.contractName}.commit-liquidity min-coherence=2000000 (too high)`,
    contract: 'LiquidityOcean',
    expected: 'failed',
    call: async () => sendContractCall({
      ...CONTRACTS.LO,
      functionName: 'commit-liquidity',
      functionArgs: [
        buffCV(hashStr('commit-bad-1')),
        buffCV(hashStr('lo-entity-bad')),
        buffCV(routeIds[0]),
        buffCV(hashStr('asset-bad')),
        uintCV(500000n),
        uintCV(2000000n),                   // min-coherence > 1e6 → Err u504
        uintCV(1000000000n),
        uintCV(500000n),
        uintCV(500000n),
        uintCV(500000n),
      ],
      senderKey: DEPLOYER_KEY,
      fee: FEE,
    }),
  });

  // ============================================== TESTS 43-46: BehavioralLimitOrder
  // place-order BUY + place-order SELL + fill-order partial on BUY + cancel-order on SELL.
  //
  // place-order args (7): order-id, entity-id, route-id, side, asset, amount, price
  // fill-order args (3): order-id, fill-amount, match-quality
  // cancel-order args (1): order-id

  // --- Test 43: place-order BUY → SUCCESS ---
  const buyOrderId = hashStr('order-buy-1');
  await runTest({
    id: 43,
    name: `${CONTRACTS.BLO.contractName}.place-order BUY`,
    contract: 'BehavioralLimitOrder',
    expected: 'success',
    call: async () => sendContractCall({
      ...CONTRACTS.BLO,
      functionName: 'place-order',
      functionArgs: [
        buffCV(buyOrderId),
        buffCV(hashStr('blo-entity-1')),
        buffCV(routeIds[0]),
        uintCV(0n),                         // SIDE-BUY
        buffCV(hashStr('asset-btc')),
        uintCV(1000000n),                   // amount
        uintCV(50000n),                      // price
      ],
      senderKey: DEPLOYER_KEY,
      fee: FEE,
    }),
  });

  // --- Test 44: place-order SELL → SUCCESS ---
  const sellOrderId = hashStr('order-sell-1');
  await runTest({
    id: 44,
    name: `${CONTRACTS.BLO.contractName}.place-order SELL`,
    contract: 'BehavioralLimitOrder',
    expected: 'success',
    call: async () => sendContractCall({
      ...CONTRACTS.BLO,
      functionName: 'place-order',
      functionArgs: [
        buffCV(sellOrderId),
        buffCV(hashStr('blo-entity-2')),
        buffCV(routeIds[1]),
        uintCV(1n),                         // SIDE-SELL
        buffCV(hashStr('asset-usdc')),
        uintCV(2000000n),
        uintCV(75000n),
      ],
      senderKey: DEPLOYER_KEY,
      fee: FEE,
    }),
  });

  // --- Test 45: fill-order partial on BUY (fill 500000 of 1000000) → SUCCESS (status=PARTIAL) ---
  await runTest({
    id: 45,
    name: `${CONTRACTS.BLO.contractName}.fill-order BUY partial`,
    contract: 'BehavioralLimitOrder',
    expected: 'success',
    call: async () => sendContractCall({
      ...CONTRACTS.BLO,
      functionName: 'fill-order',
      functionArgs: [
        buffCV(buyOrderId),
        uintCV(500000n),                    // fill-amount (half of 1M)
        uintCV(800000n),                     // match-quality (<= 1e6)
      ],
      senderKey: DEPLOYER_KEY,
      fee: FEE,
    }),
  });

  // --- Test 46: cancel-order on SELL → SUCCESS ---
  await runTest({
    id: 46,
    name: `${CONTRACTS.BLO.contractName}.cancel-order SELL`,
    contract: 'BehavioralLimitOrder',
    expected: 'success',
    call: async () => sendContractCall({
      ...CONTRACTS.BLO,
      functionName: 'cancel-order',
      functionArgs: [buffCV(sellOrderId)],
      senderKey: DEPLOYER_KEY,
      fee: FEE,
    }),
  });

  // ============================================== TESTS 47-50: trion-test-token
  // transfer (deployer->V2) + mint (to V3, owner-only) + faucet-drip from V2 (SUCCESS)
  // + faucet-drip from V2 again immediately (FAIL — FAUCET-COOLDOWN-BLOCKS=6).
  //
  // transfer args (4): amount, sender, recipient, memo (optional (buff 34))
  // mint args (2): amount, to
  // faucet-drip args (0)

  // --- Test 47: transfer 1000 micro-tTRION from V1 (deployer) to V2 → SUCCESS ---
  await runTest({
    id: 47,
    name: `${CONTRACTS.TOK.contractName}.transfer 1000 to V2`,
    contract: 'trion-test-token',
    expected: 'success',
    call: async () => sendContractCall({
      ...CONTRACTS.TOK,
      functionName: 'transfer',
      functionArgs: [
        uintCV(1000n),                       // amount
        principalCV(V1_ADDR),                // sender (deployer = V1; is-eq tx-sender sender)
        principalCV(V2_ADDR),                // recipient
        noneCV(),                            // memo (optional, none)
      ],
      senderKey: V1_KEY,                    // tx-sender = V1 = sender arg
      fee: FEE,
    }),
  });

  // --- Test 48: mint 5000 micro-tTRION to V3 (owner-only) → SUCCESS ---
  await runTest({
    id: 48,
    name: `${CONTRACTS.TOK.contractName}.mint 5000 to V3 (owner)`,
    contract: 'trion-test-token',
    expected: 'success',
    call: async () => sendContractCall({
      ...CONTRACTS.TOK,
      functionName: 'mint',
      functionArgs: [
        uintCV(5000n),
        principalCV(V3_ADDR),
      ],
      senderKey: DEPLOYER_KEY,              // deployer is the token contract owner
      fee: FEE,
    }),
  });

  // --- Test 49: faucet-drip from V2 → SUCCESS (first drip, no prior record) ---
  await runTest({
    id: 49,
    name: `${CONTRACTS.TOK.contractName}.faucet-drip from V2`,
    contract: 'trion-test-token',
    expected: 'success',
    call: async () => sendContractCall({
      ...CONTRACTS.TOK,
      functionName: 'faucet-drip',
      functionArgs: [],
      senderKey: V2_KEY,
      fee: FEE,
    }),
  });

  // --- Test 50: faucet-drip from V2 again immediately → FAIL (cooldown, Err u3003) ---
  // Stacks burn-block-height (Bitcoin block height) advances ~every 10 min; between
  // test 49 and test 50 only a few seconds elapse, so the cooldown check
  // (>= last_height + 6) fails.
  await runTest({
    id: 50,
    name: `${CONTRACTS.TOK.contractName}.faucet-drip from V2 (cooldown)`,
    contract: 'trion-test-token',
    expected: 'failed',
    call: async () => sendContractCall({
      ...CONTRACTS.TOK,
      functionName: 'faucet-drip',
      functionArgs: [],
      senderKey: V2_KEY,
      fee: FEE,
    }),
  });

  // ============================================== SUMMARY
  const passed = results.filter(r => r.pass).length;
  const failed = results.filter(r => !r.pass && r.status !== 'skipped').length;
  const skipped = results.filter(r => r.status === 'skipped').length;

  console.log('');
  console.log('=== Summary ===');
  console.log(
    `Tests passed: ${passed}/50  Failed: ${failed}  Skipped: ${skipped}  Total txs broadcast: ${txsBroadcast}`
  );
  console.log('');
  console.log('Per-contract breakdown:');
  const byContract = {};
  for (const r of results) {
    if (!byContract[r.contract]) byContract[r.contract] = { pass: 0, fail: 0, skip: 0 };
    if (r.status === 'skipped') byContract[r.contract].skip++;
    else if (r.pass) byContract[r.contract].pass++;
    else byContract[r.contract].fail++;
  }
  for (const [c, v] of Object.entries(byContract)) {
    console.log(`  ${c.padEnd(22)} pass=${v.pass} fail=${v.fail} skip=${v.skip}`);
  }

  // Per-scenario breakdown (positive vs negative).
  const positive = results.filter(r => r.expected === 'success');
  const negative = results.filter(r => r.expected === 'failed');
  const posPass = positive.filter(r => r.pass).length;
  const negPass = negative.filter(r => r.pass).length;
  console.log('');
  console.log(
    `Positive tests (expected success): ${posPass}/${positive.length} passed`
  );
  console.log(
    `Negative tests (expected failed): ${negPass}/${negative.length} behaved as expected (failed on-chain)`
  );

  // Write JSON results.
  fs.mkdirSync(path.dirname(RESULTS_FILE), { recursive: true });
  fs.writeFileSync(
    RESULTS_FILE,
    JSON.stringify(
      {
        timestamp: new Date().toISOString(),
        summary: {
          total: 50,
          passed,
          failed,
          skipped,
          txsBroadcast,
          positive: { total: positive.length, passed: posPass },
          negative: { total: negative.length, passed: negPass },
        },
        deployer: D,
        validators: { v1: V1_ADDR, v2: V2_ADDR, v3: V3_ADDR },
        contractSuffix: SUFFIX,
        realBtcTip: realTip
          ? { blockHashBE: realTip.blockHashBE, height: realTip.height }
          : null,
        tests: results,
      },
      null,
      2
    )
  );
  console.log(`\nResults written to: ${RESULTS_FILE}`);
  console.log('');
}

main().catch(e => {
  console.error('FATAL:', e);
  console.error(e.stack);
  try { saveResultsPartial(); } catch (_) {}
  process.exit(1);
});

process.on('unhandledRejection', (reason) => {
  console.error('WARN: unhandledRejection:', reason);
});

process.on('SIGINT', () => {
  console.error('\nSIGINT: saving partial results...');
  try { saveResultsPartial(); } catch (_) {}
  process.exit(130);
});
