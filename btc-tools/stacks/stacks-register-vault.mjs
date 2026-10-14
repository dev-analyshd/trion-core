import { sendContractCall, buffCV, hashStr, getAddressFromPrivateKey } from './lib/helpers.mjs';
import txPkg from '@stacks/transactions';
import * as crypto from 'crypto';
import * as fs from 'fs';
const { uintCV } = txPkg;

const DEPLOYER_KEY = '940806a0a98e86df44835d7fb5d58a79d6259f413550ba11a858880a72e2e71901';
const DEPLOYER_ADDR = getAddressFromPrivateKey(DEPLOYER_KEY, 'testnet');
const CONTRACT = { contractAddress: DEPLOYER_ADDR, contractName: 'trioncoherencevault-v4' };

const vault = JSON.parse(fs.readFileSync('/tmp/vault-state-v2.json', 'utf-8'));

const vaultId = '0x' + crypto.createHash('sha256').update(vault.vaultAddress + Date.now()).digest('hex');
const entityIdHex = vault.payloadHex.slice(0, 40); // first 20 bytes
const anchorBH = vault.committedAnchorBH;

console.log('=== Stacks: Register vault ===');
console.log(`  vault-id: ${vaultId}`);
console.log(`  anchor-bh: ${anchorBH}`);

const regResult = await sendContractCall({
  ...CONTRACT,
  functionName: 'register-vault',
  functionArgs: [
    buffCV(vaultId),
    buffCV('0x' + entityIdHex),
    buffCV('0x' + anchorBH),
    buffCV(hashStr(vault.lenderAddress)),
    uintCV(BigInt(183933)),
    uintCV(6),
  ],
  senderKey: DEPLOYER_KEY,
  fee: 100000,
});
console.log(`  register-vault: ${regResult.ok ? 'PASS' : 'FAIL'} tx=${regResult.txId || regResult.error}`);

console.log('\n=== Stacks: Publish preimage ===');
const pubResult = await sendContractCall({
  ...CONTRACT,
  functionName: 'publish-preimage',
  functionArgs: [
    buffCV(vaultId),
    buffCV('0x' + vault.payloadHex),
  ],
  senderKey: DEPLOYER_KEY,
  fee: 100000,
});
console.log(`  publish-preimage: ${pubResult.ok ? 'PASS' : 'FAIL'} tx=${pubResult.txId || pubResult.error}`);

// Save combined results
const btcResults = JSON.parse(fs.readFileSync('/home/z/my-project/trion-core/proofs/btcp-zero-bridge/stacks/btc-testnet-preimage-results.json', 'utf-8'));
const combined = {
  ...btcResults,
  stacks: {
    registerVaultTx: regResult.txId,
    publishPreimageTx: pubResult.txId,
    contract: 'ST969AZNDX2P7N1YJ0DNVGC8QEKT388DBMXGHR9Z.trioncoherencevault-v4',
  },
  endToEnd: {
    btcFundingTx: '18959005d213716354037e2d38394ba132aef581ea766a77423026645508820b',
    btcSpendTx: 'a2c26048d477243b094798a29d405eadf27567ff3c0e77585fb6e986df58bcdc',
    btcSpendBlock: 5158940,
    btcSpendType: 'preimage-reveal (NO SIGNATURE — 80-byte HashDNA payload is the SOLE authorization)',
    stacksRegisterTx: regResult.txId,
    stacksPublishTx: pubResult.txId,
    vaultAddress: vault.vaultAddress,
    committedAnchorBH: vault.committedAnchorBH,
    payloadLength: 80,
    assetsBridged: false,
  },
};
fs.writeFileSync(
  '/home/z/my-project/trion-core/proofs/btcp-zero-bridge/stacks/btc-testnet-e2e-results.json',
  JSON.stringify(combined, null, 2)
);
console.log('\n=== Combined results saved ===');
console.log(JSON.stringify(combined.endToEnd, null, 2));
