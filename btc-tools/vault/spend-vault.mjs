/**
 * spend-vault.mjs — Build + broadcast the preimage-reveal spend tx.
 *
 * Reads /tmp/vault-state-live.json, fetches the vault UTXO from mempool.space,
 * builds the Taproot script-path spend (witness = [payload, releaseScript,
 * releaseControlBlock]), and broadcasts to Bitcoin testnet.
 *
 * No signature — the preimage IS the authorization. See:
 *   docs/architecture/trion-coherence-vault.md §3
 *
 * Usage:
 *   node spend-vault.mjs            # build + broadcast
 *   node spend-vault.mjs --dry-run  # build + print raw hex, do NOT broadcast
 */
import * as fs from 'fs';
import * as bitcoin from 'bitcoinjs-lib';
import { ECPairFactory } from 'ecpair';
import * as ecc from 'tiny-secp256k1';

bitcoin.initEccLib(ecc);
const ECPair = ECPairFactory(ecc);
const network = bitcoin.networks.testnet;

const STATE_FILE = '/tmp/vault-state-live.json';
const MEMPOOL_API = 'https://mempool.space/testnet/api';
const FEE_SATS = 1000; // ~1 sat/vB for the ~150-vbyte reveal tx

function log(m) { console.log(`[spend-vault] ${m}`); }

async function fetchJson(url, opts = {}) {
  const r = await fetch(url, opts);
  if (!r.ok) throw new Error(`HTTP ${r.status} for ${url}: ${await r.text()}`);
  return r.json();
}

function buildSpendTx(vault, utxo, payload) {
  const releaseScript = Buffer.from(vault.releaseScript.split(',').map(b => parseInt(b, 10)));
  const controlBlock = Buffer.from(vault.releaseControlBlock, 'hex');
  const vaultOutputScript = Buffer.from(vault.vaultOutputScript, 'hex');

  const psbt = new bitcoin.Psbt({ network });
  psbt.addInput({
    hash: utxo.txid,
    index: utxo.vout,
    witnessUtxo: {
      script: vaultOutputScript,
      value: BigInt(utxo.value),
    },
    tapLeafScript: {
      leafVersion: 0xc0,
      script: releaseScript,
      controlBlock,
    },
  });

  const sendAmount = utxo.value - FEE_SATS;
  psbt.addOutput({ address: vault.lenderAddress, value: sendAmount });

  // Finalize: witness = [payload, releaseScript, controlBlock]
  psbt.finalizeInput(0, () => ({
    finalScriptWitness: bitcoin.script.witnessStackToWitness([payload, releaseScript, controlBlock]),
  }));

  const tx = psbt.extractTransaction();
  return { tx, sendAmount, rawHex: tx.toHex(), txid: tx.getId() };
}

async function main() {
  const dryRun = process.argv.includes('--dry-run');
  const vault = JSON.parse(fs.readFileSync(STATE_FILE, 'utf-8'));
  log(`Vault address: ${vault.vaultAddress}`);

  // Fetch UTXOs
  const utxos = await fetchJson(`${MEMPOOL_API}/address/${vault.vaultAddress}/utxo`);
  if (!utxos || utxos.length === 0) {
    log('ERROR: Vault has no UTXOs. Fund it first.');
    process.exit(1);
  }
  const utxo = utxos[0];
  log(`Using UTXO: txid=${utxo.txid} vout=${utxo.vout} value=${utxo.value} sats`);

  const payload = Buffer.from(vault.payloadHex, 'hex');
  log(`Payload (93 bytes): ${payload.toString('hex').slice(0, 40)}...`);
  log(`committed_anchor_bh: ${vault.committedAnchorBH}`);

  // Sanity: SHA-256(payload || 0x00) must equal committedAnchorBH
  const sense = require('crypto').createHash('sha256')
    .update(Buffer.concat([payload, Buffer.from([0x00])])).digest('hex');
  if (sense !== vault.committedAnchorBH) {
    log(`ERROR: sense mismatch — payload does not commit to anchor_bh`);
    log(`  computed: ${sense}`);
    log(`  expected: ${vault.committedAnchorBH}`);
    process.exit(1);
  }
  log(`✓ sense check passed: SHA-256(payload||0x00) == committed_anchor_bh`);

  const { tx, sendAmount, rawHex, txid } = buildSpendTx(vault, utxo, payload);
  log(`Built spend tx:`);
  log(`  Input:  ${utxo.value} sats (vault UTXO)`);
  log(`  Output: ${sendAmount} sats → ${vault.lenderAddress} (lender)`);
  log(`  Fee:    ${FEE_SATS} sats`);
  log(`  Txid:   ${txid}`);
  log(`  Raw hex (${rawHex.length} chars): ${rawHex.slice(0, 80)}...${rawHex.slice(-40)}`);

  if (dryRun) {
    log('DRY RUN — not broadcasting.');
    fs.writeFileSync('/tmp/vault-spend-unsigned.hex', rawHex);
    log('Raw hex saved to /tmp/vault-spend-unsigned.hex');
    return;
  }

  // Broadcast
  log('Broadcasting to Bitcoin testnet...');
  const r = await fetch(`${MEMPOOL_API}/tx`, {
    method: 'POST',
    headers: { 'Content-Type': 'text/plain' },
    body: rawHex,
  });
  const text = await r.text();
  if (r.ok) {
    const broadcastTxid = text.replace(/"/g, '').trim();
    log(`✓ BROADCAST SUCCESS! txid: ${broadcastTxid}`);
    log(`  Explorer: https://mempool.space/testnet/tx/${broadcastTxid}`);
    console.log(broadcastTxid); // final stdout = txid
  } else {
    log(`✗ BROADCAST FAILED: HTTP ${r.status}`);
    log(`  Response: ${text}`);
    process.exit(2);
  }
}

// tiny require shim for `crypto` in ESM
import { createHash } from 'crypto';
globalThis.require = (mod) => mod === 'crypto' ? { createHash } : null;

main().catch(e => { console.error('FATAL:', e); process.exit(1); });
