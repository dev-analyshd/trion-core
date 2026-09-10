/**
 * stacks-deploy.mjs — Deploy the 6 Clarity contracts to Stacks testnet.
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

async function getNonce(addr) {
  const r = await fetch(`${API}/v2/accounts/${addr}?proof=0`);
  const data = await r.json();
  return parseInt(data.nonce);
}

async function waitForTx(txId, maxWaitMs = 120000) {
  const start = Date.now();
  while (Date.now() - start < maxWaitMs) {
    await new Promise(r => setTimeout(r, 5000));
    try {
      const r = await fetch(`${API}/extended/v1/tx/${txId}`);
      const info = await r.json();
      if (info.tx_status === 'success') return info;
      if (info.tx_status && info.tx_status !== 'pending') {
        return info;
      }
    } catch {}
  }
  return { tx_status: 'timeout' };
}

async function deployContract(name, source, nonce) {
  console.log(`  deploying ${name} (${source.length} bytes, nonce ${nonce})...`);
  try {
    const tx = await makeContractDeploy({
      contractName: name,
      codeBody: source,
      senderKey: DEPLOYER_KEY,
      network,
      fee: 100000,  // 0.1 STX
      nonce: BigInt(nonce),
    });
    const resp = await broadcastTransaction({ transaction: tx, network });
    if (resp.txid) {
      console.log(`    broadcast: 0x${resp.txid}`);
      const info = await waitForTx(`0x${resp.txid}`);
      console.log(`    status: ${info.tx_status} block: ${info.block_height || 'n/a'}`);
      if (info.tx_status === 'success') {
        // Check for contract deployment result
        if (info.contract_abi) {
          console.log(`    contract deployed: ABI available`);
        }
        const contractId = `${info.sender_address || 'ST969AZNDX2P7N1YJ0DNVGC8QEKT388DBMXGHR9Z'}.${name}`;
        return { name, contractId, txId: `0x${resp.txid}`, status: 'deployed', blockHeight: info.block_height };
      } else {
        return { name, txId: `0x${resp.txid}`, status: info.tx_status, error: info.raw_result };
      }
    } else {
      console.log(`    broadcast failed: ${JSON.stringify(resp).slice(0, 200)}`);
      return { name, status: 'broadcast_failed', error: resp };
    }
  } catch (e) {
    console.log(`    ERR: ${e.message.slice(0, 200)}`);
    return { name, status: 'error', error: e.message };
  }
}

async function main() {
  const deployerAddr = getAddressFromPrivateKey(DEPLOYER_KEY, 'testnet');
  console.log('Deployer:', deployerAddr);
  let nonce = await getNonce(deployerAddr);
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
  }

  // Save deployment record
  const record = {
    network: 'stacks-testnet',
    chainId: 2147483648,
    api: API,
    deployedAt: new Date().toISOString(),
    deployer: deployerAddr,
    contracts: deployments,
  };
  fs.mkdirSync(path.join(process.cwd(), 'docs', 'deployments'), { recursive: true });
  fs.writeFileSync(path.join(process.cwd(), 'docs', 'deployments', 'stacks_testnet.json'), JSON.stringify(record, null, 2));
  console.log('\n=== Deployment record saved ===');
  console.log(JSON.stringify(deployments, null, 2));
}

main().catch(e => { console.error('FATAL:', e); process.exit(1); });
