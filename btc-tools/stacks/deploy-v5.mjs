import { fileURLToPath } from 'url';
import * as fs from 'fs';
import * as path from 'path';
import txPkg from '@stacks/transactions';
const { makeContractDeploy, broadcastTransaction } = txPkg;
import { API, network, getNonce, waitForTx, sleep, getAddressFromPrivateKey } from './lib/helpers.mjs';

const DEPLOYER_KEY = '940806a0a98e86df44835d7fb5d58a79d6259f413550ba11a858880a72e2e71901';
const DEPLOYER_ADDR = getAddressFromPrivateKey(DEPLOYER_KEY, 'testnet');
const REPO_ROOT = path.resolve(path.dirname(fileURLToPath(import.meta.url)), '..', '..');

async function deploy(name, source) {
  const nonce = await getNonce(DEPLOYER_ADDR);
  console.log(`  [nonce=${nonce}] deploying ${name} (${source.length} bytes)...`);
  try {
    const tx = await makeContractDeploy({ contractName: name, codeBody: source, senderKey: DEPLOYER_KEY, network, fee: 100000, nonce: BigInt(nonce) });
    const resp = await broadcastTransaction({ transaction: tx, network });
    if (!resp || !resp.txid) { console.log(`    ✗ broadcast_failed: ${JSON.stringify(resp).slice(0,200)}`); return { name, status: 'failed', error: 'broadcast_failed' }; }
    const txId = `0x${resp.txid}`;
    console.log(`    broadcast: ${txId}`);
    const r = await waitForTx(txId, 180000);
    if (r.ok) { console.log(`    ✓ SUCCESS at block ${r.info?.block_height}`); return { name, txId, status: 'deployed', blockHeight: r.info?.block_height }; }
    console.log(`    ✗ FAILED: ${r.error || r.info?.tx_result?.repr || 'unknown'}`);
    if (r.info?.vm_error) console.log(`    vm_error: ${r.info.vm_error.slice(0,200)}`);
    return { name, txId, status: 'failed', error: r.error || r.info?.tx_result?.repr };
  } catch (e) { console.log(`    ERR: ${e.message.slice(0,300)}`); return { name, status: 'failed', error: e.message.slice(0,300) }; }
}

async function main() {
  console.log(`=== Deploying TRIONCoherenceVaultV5 ===`);
  console.log(`Deployer: ${DEPLOYER_ADDR}`);
  const source = fs.readFileSync(path.resolve(REPO_ROOT, 'contracts', 'clarity', 'TRIONCoherenceVaultV5.clar'), 'utf-8');
  const clean = source.replace(/[^\x00-\x7F]/g, '');
  const r = await deploy('trioncoherencevault-v5', clean);
  console.log('\n=== Summary ===');
  console.log(JSON.stringify(r, null, 2));
}
main().catch(e => { console.error('FATAL:', e); process.exit(1); });
