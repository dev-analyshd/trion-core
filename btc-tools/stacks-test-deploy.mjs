import txPkg from '@stacks/transactions';
const { makeContractDeploy, broadcastTransaction } = txPkg;
import netPkg from '@stacks/network';
const { STACKS_TESTNET, createNetwork } = netPkg;
import fs from 'fs';

const DEPLOYER_KEY = '940806a0a98e86df44835d7fb5d58a79d6259f413550ba11a858880a72e2e71901';
const network = createNetwork(STACKS_TESTNET);

async function getNonce() {
  const r = await fetch('https://api.testnet.hiro.so/v2/accounts/ST969AZNDX2P7N1YJ0DNVGC8QEKT388DBMXGHR9Z?proof=0');
  const data = await r.json();
  return parseInt(data.nonce);
}

async function tryDeploy(name, source) {
  const nonce = await getNonce();
  console.log(`deploying ${name} (nonce ${nonce})...`);
  try {
    const tx = await makeContractDeploy({
      contractName: name,
      codeBody: source,
      senderKey: DEPLOYER_KEY,
      network,
      fee: 100000,
      nonce: BigInt(nonce),
    });
    const resp = await broadcastTransaction({ transaction: tx, network });
    if (resp.txid) {
      console.log(`  broadcast: 0x${resp.txid}`);
      await new Promise(r => setTimeout(r, 20000));
      const info = await fetch(`https://api.testnet.hiro.so/extended/v1/tx/0x${resp.txid}`).then(r => r.json());
      console.log(`  status: ${info.tx_status}`);
      if (info.tx_status !== 'success' && info.raw_result) {
        console.log(`  raw_result: ${info.raw_result.slice(0, 300)}`);
      }
      return info.tx_status === 'success';
    } else {
      console.log(`  error: ${JSON.stringify(resp).slice(0, 300)}`);
      return false;
    }
  } catch (e) {
    console.log(`  exception: ${e.message.slice(0, 200)}`);
    return false;
  }
}

// Test 1: full BTCSPVVerifier
const fullSource = fs.readFileSync('contracts/clarity/BTCSPVVerifier.clar', 'utf-8');
await tryDeploy('btcspvverifier', fullSource);
