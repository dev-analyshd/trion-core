#!/usr/bin/env node
/**
 * stacks-transfer.mjs — Transfer STX from deployer to the 3 validators.
 * Each validator needs ~2 STX for gas to submit attestations.
 */
import txPkg from '@stacks/transactions';
const { makeSTXTokenTransfer, broadcastTransaction, getAddressFromPrivateKey, TransactionVersion, privateKeyToHex } = txPkg;
import netPkg from '@stacks/network';
const { STACKS_TESTNET, createNetwork } = netPkg;

const API = 'https://api.testnet.hiro.so';
const DEPLOYER_KEY = process.env.DEPLOYER_KEY || '940806a0a98e86df44835d7fb5d58a79d6259f413550ba11a858880a72e2e71901';
const VALIDATORS = [
  { addr: 'ST2HTG5KX41N69DTSF49QGNP4W1XDGWKPP46ZMV67', amount: 2000000 },  // 2 STX
  { addr: 'ST227WJ8TFQZFWWP914FXF3GYXSETCRCJRF3N7NJA', amount: 2000000 },
  { addr: 'ST2SXN6HP9EBYN8RJSP9N4WKK6XM007A7R3YSXYA', amount: 2000000 },
];

async function getNonce(addr) {
  const r = await fetch(`${API}/v2/accounts/${addr}?proof=0`);
  const data = await r.json();
  return parseInt(data.balance, 16) > 0 ? parseInt(data.nonce) : 0;
}

async function transfer(toAddr, amount, nonce) {
  const network = createNetwork(STACKS_TESTNET);
  const tx = await makeSTXTokenTransfer({
    recipient: toAddr,
    amount: BigInt(amount),
    senderKey: DEPLOYER_KEY,
    network,
    fee: 1000,
    nonce: BigInt(nonce),
  });
  // broadcastTransaction expects { transaction, network }
  const resp = await broadcastTransaction({ transaction: tx, network });
  return { txId: resp.txid, status: resp.status || 200 };
}

async function waitForTx(txId, maxWaitMs = 60000) {
  const start = Date.now();
  while (Date.now() - start < maxWaitMs) {
    await new Promise(r => setTimeout(r, 5000));
    try {
      const r = await fetch(`${API}/extended/v1/tx/${txId}`);
      const info = await r.json();
      if (info.tx_status === 'success') return info;
      if (info.tx_status === 'abort_by_response' || info.tx_status === 'abort_by_post_condition') {
        throw new Error(`tx ${txId} ${info.tx_status}`);
      }
    } catch (e) {
      // tx not found yet
    }
  }
  throw new Error(`tx ${txId} timeout`);
}

async function main() {
  const deployerAddr = getAddressFromPrivateKey(DEPLOYER_KEY, 'testnet');
  console.log('Deployer:', deployerAddr);
  let nonce = await getNonce(deployerAddr);
  console.log('Starting nonce:', nonce);

  for (const v of VALIDATORS) {
    console.log(`\nTransferring ${v.amount} microSTX to ${v.addr} (nonce ${nonce})...`);
    const { txId, status } = await transfer(v.addr, v.amount, nonce);
    console.log(`  broadcast status=${status} txId=${txId}`);
    nonce++;
    if (txId.startsWith('0x')) {
      try {
        const info = await waitForTx(txId);
        console.log(`  confirmed at block ${info.block_height}`);
      } catch (e) {
        console.log(`  confirmation: ${e.message}`);
      }
    }
  }
  console.log('\n=== Done. Validator balances: ===');
  for (const v of VALIDATORS) {
    const r = await fetch(`${API}/extended/v1/address/${v.addr}/balances`);
    const bal = await r.json();
    console.log(`  ${v.addr}: ${bal.stx.balance} microSTX`);
  }
}

main().catch(e => { console.error('FATAL:', e); process.exit(1); });
