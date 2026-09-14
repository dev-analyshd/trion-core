// Focused BTC testnet lock transaction (behavioral self-transfer anchor)
import 'dotenv/config';
import fs from 'fs';
import path from 'path';
import { fileURLToPath } from 'url';
import { Psbt, payments, networks } from 'bitcoinjs-lib';
import { ECPairFactory } from 'ecpair';
import * as bslEcc from '@bitcoinerlab/secp256k1';

const __dirname = path.dirname(fileURLToPath(import.meta.url));
const ECPair = ECPairFactory(bslEcc);
const BTC_ADDRESS = 'tb1q5d69fyxxxwdkr7pecmxyr245w5jqchm9zptkks';
const NETWORK = networks.testnet;

const pk = process.env.EVM_PRIVATE_KEY.replace(/^0x/, '');
const utxoData = JSON.parse(fs.readFileSync(path.join(__dirname, 'btc_utxos.json'), 'utf-8'));
const utxo = utxoData.utxos[0];
console.log('UTXO:', utxo.txid.slice(0,16) + '...', 'vout', utxo.vout, '=', utxo.value, 'sats (confirmed:', utxo.status.confirmed + ')');

const keyPair = ECPair.fromPrivateKey(Buffer.from(pk, 'hex'), { network: NETWORK });
const p2wpkh = payments.p2wpkh({ pubkey: keyPair.publicKey, network: NETWORK });
console.log('Signing addr:', p2wpkh.address, '| match:', p2wpkh.address === BTC_ADDRESS);

const fee = 1000;
const sendValue = utxo.value - fee;

const psbt = new Psbt({ network: NETWORK });
psbt.addInput({
  hash: utxo.txid,
  index: utxo.vout,
  witnessUtxo: { script: p2wpkh.output, value: BigInt(utxo.value) },
});
psbt.addOutput({ address: BTC_ADDRESS, value: BigInt(sendValue) });
psbt.signInput(0, keyPair);
psbt.finalizeAllInputs();

const rawTx = psbt.extractTransaction();
const rawHex = Buffer.from(rawTx.toBuffer()).toString('hex');
const txid = rawTx.getId();
console.log('\nSigned BTC lock tx:');
console.log('  TXID:', txid);
console.log('  Send value:', sendValue, 'sats  |  Fee:', fee, 'sats');

// Broadcast
console.log('\nBroadcasting to Bitcoin testnet via Esplora...');
const res = await fetch('https://blockstream.info/testnet/api/tx', { method: 'POST', body: rawHex });
const txt = await res.text();
console.log('  HTTP', res.status, '| Response:', txt.slice(0,80));
const resultPath = path.join(__dirname, '..', 'docs', 'proofs', 'btc_lock_tx_result.json');
if (res.ok && txt.length < 80) {
  console.log('\n✅ BTC LOCK TX BROADCAST SUCCESS');
  console.log('  Explorer: https://blockstream.info/testnet/tx/' + txt.trim());
  const result = { step: 'btc_lock_tx', pass: true, txid: txt.trim(), sendValue, fee,
    explorer: 'https://blockstream.info/testnet/tx/' + txt.trim(), broadcastAt: new Date().toISOString() };
  fs.writeFileSync(resultPath, JSON.stringify(result, null, 2));
} else {
  console.log('\n✗ Broadcast failed');
  fs.writeFileSync(resultPath, JSON.stringify({ step: 'btc_lock_tx', pass: false, error: txt.slice(0,300), httpStatus: res.status, preTxid: txid }, null, 2));
}
