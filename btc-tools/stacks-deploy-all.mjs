/**
 * stacks-deploy-all.mjs — Deploy all 6 Clarity contracts to Stacks testnet.
 * Uses the current nonce, deploys sequentially with confirmation waiting.
 */
import txPkg from '@stacks/transactions';
const { makeContractDeploy, broadcastTransaction, getAddressFromPrivateKey } = txPkg;
import netPkg from '@stacks/network';
const { STACKS_TESTNET, createNetwork } = netPkg;
import * as fs from 'fs';
import * as path from 'path';

const API = 'https://api.testnet.hiro.so';
const DEPLOYER_KEY = process.env.DEPLOYER_KEY || '940806a0a98e86df44835d7fb5d58a79d6259f413550ba11a858880a72e2e71901';
const CONTRACTS_DIR = path.join(process.cwd(), 'contracts', 'clarity');
const network = createNetwork(STACKS_TESTNET);
const DEPLOYER_ADDR = getAddressFromPrivateKey(DEPLOYER_KEY, 'testnet');

async function getNonce(addr) {
  const r = await fetch(`${API}/v2/accounts/${addr}?proof=0`);
  const data = await r.json();
  return parseInt(data.nonce);
}

function sleep(ms) { return new Promise(r => setTimeout(r, ms)); }

async function waitForTx(txId, maxWaitMs = 180000) {
  const start = Date.now();
  while (Date.now() - start < maxWaitMs) {
    await sleep(8000);
    try {
      const r = await fetch(`${API}/extended/v1/tx/${txId}`);
      const info = await r.json();
      if (info.tx_status === 'success') return { ok: true, info };
      if (info.tx_status === 'abort_by_response' || info.tx_status === 'abort_by_post_condition') {
        return { ok: false, info, error: info.raw_result || info.tx_status };
      }
    } catch {}
  }
  return { ok: false, error: 'timeout' };
}

async function deployContract(name, source, nonce) {
  console.log(`  deploying ${name} (${source.length} bytes, nonce ${nonce})...`);
  try {
    const tx = await makeContractDeploy({
      contractName: name,
      codeBody: source,
      senderKey: DEPLOYER_KEY,
      network,
      fee: 500000,
      nonce: BigInt(nonce),
    });
    const resp = await broadcastTransaction({ transaction: tx, network });
    if (resp.txid) {
      console.log(`    broadcast: 0x${resp.txid}`);
      const result = await waitForTx(`0x${resp.txid}`);
      if (result.ok) {
        console.log(`    ✓ SUCCESS at block ${result.info.block_height}`);
        return { name, contractId: `${DEPLOYER_ADDR}.${name}`, txId: `0x${resp.txid}`, status: 'deployed', blockHeight: result.info.block_height };
      } else {
        console.log(`    ✗ FAILED: ${result.error || 'unknown'}`);
        // Try to get more detail from the tx
        if (result.info && result.info.raw_result) {
          console.log(`    raw_result: ${result.info.raw_result.slice(0, 300)}`);
        }
        return { name, status: 'failed', error: result.error, txId: `0x${resp.txid}` };
      }
    }
    return { name, status: 'broadcast_failed', error: JSON.stringify(resp).slice(0, 200) };
  } catch (e) {
    console.log(`    ERR: ${e.message.slice(0, 200)}`);
    return { name, status: 'error', error: e.message.slice(0, 200) };
  }
}

async function main() {
  console.log('=== Deploying 6 Clarity contracts to Stacks testnet ===');
  console.log('Deployer:', DEPLOYER_ADDR);
  let nonce = await getNonce(DEPLOYER_ADDR);
  console.log('Starting nonce:', nonce);

  const contracts = [
    { name: 'btcspvverifier', file: 'BTCSPVVerifier.clar' },
    { name: 'btcpescrow', file: 'BTCPEscrow.clar' },
    { name: 'btcpintent', file: 'BTCPIntent.clar' },
    { name: 'btcproute', file: 'BTCPRoute.clar' },
    { name: 'liquidityocean', file: 'LiquidityOcean.clar' },
    { name: 'behaviorallimitorder', file: 'BehavioralLimitOrder.clar' },
  ];

  const deployments = [];
  for (const c of contracts) {
    const source = fs.readFileSync(path.join(CONTRACTS_DIR, c.file), 'utf-8');
    const result = await deployContract(c.name, source, nonce);
    deployments.push(result);
    nonce++;
    if (result.status !== 'deployed') {
      console.log(`  STOPPING: ${c.name} failed to deploy`);
      break;
    }
    await sleep(2000);
  }

  // Save deployment record
  fs.mkdirSync('docs/deployments', { recursive: true });
  const record = {
    network: 'stacks-testnet',
    chainId: 2147483648,
    api: API,
    deployedAt: new Date().toISOString(),
    deployer: DEPLOYER_ADDR,
    contracts: deployments,
  };
  fs.writeFileSync('docs/deployments/stacks_testnet.json', JSON.stringify(record, null, 2));
  console.log('\n=== Deployment record saved ===');
  console.log(JSON.stringify(deployments, null, 2));
}

main().catch(e => { console.error('FATAL:', e); process.exit(1); });
