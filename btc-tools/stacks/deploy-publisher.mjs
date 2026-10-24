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
    if (!resp || !resp.txid) { console.log(`    ERR: ${JSON.stringify(resp).slice(0,200)}`); return null; }
    const txId = `0x${resp.txid}`;
    console.log(`    broadcast: ${txId}`);
    const r = await waitForTx(txId, 180000);
    if (r.ok) { console.log(`    SUCCESS at block ${r.info?.block_height}`); return txId; }
    console.log(`    FAILED: ${r.error || r.info?.tx_result?.repr || 'unknown'}`);
    if (r.info?.vm_error) console.log(`    vm_error: ${r.info.vm_error.slice(0,200)}`);
    return null;
  } catch (e) { console.log(`    ERR: ${e.message.slice(0,300)}`); return null; }
}

const source = fs.readFileSync(path.resolve(REPO_ROOT, 'contracts', 'clarity', 'PublisherRegistry.clar'), 'utf-8');
const clean = source.replace(/[^\x00-\x7F]/g, '');
const txId = await deploy('publisherregistry-v1', clean);
if (txId) {
  console.log(`\nDeployed: ST969AZNDX2P7N1YJ0DNVGC8QEKT388DBMXGHR9Z.publisherregistry-v1`);
  console.log(`Tx: ${txId}`);
} else {
  console.log('\nDeploy failed');
}
