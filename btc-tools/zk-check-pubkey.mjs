const RPC = 'https://starknet-sepolia.g.alchemy.com/starknet/version/rpc/v0_10/alch_REDACTED_API_KEY';
const OLD_ADDR = '0x007cbe751a23f667b61643d89ef4217a7a3ae74df6c36406a1cd9867761b7f82';
const OLD_PRIV = '0x_REDACTED_OLD_PRIV';
const NEW_ADDR = '0x0417678126db3e4eb21ca3c4dfd1b1920eb5fd2fd1e2136cbd215905be4a434d';
const NEW_PRIV = '0x_REDACTED_NEW_PRIV';

async function rpc(method, params) {
  const r = await fetch(RPC, { method:'POST', headers:{'Content-Type':'application/json'},
    body: JSON.stringify({jsonrpc:'2.0',id:1,method, params}) });
  return await r.json();
}

import { ec, hash, num } from 'starknet';

// Get stored pubkey from OLD account
const pkSel = hash.getSelectorFromName('getPublicKey');
let r = await rpc('starknet_call', [{contract_address: OLD_ADDR, entry_point_selector: pkSel, calldata: []}, 'latest']);
console.log('OLD account getPublicKey():', r.result);

// Compute pubkey from OLD priv
const oldFullPub = ec.starkCurve.getPublicKey(OLD_PRIV);
const oldPubX = '0x' + Buffer.from(oldFullPub.slice(1,33)).toString('hex');
console.log('OLD priv → pubkey X:', oldPubX);

// Compute pubkey from NEW priv
const newFullPub = ec.starkCurve.getPublicKey(NEW_PRIV);
const newPubX = '0x' + Buffer.from(newFullPub.slice(1,33)).toString('hex');
console.log('NEW priv → pubkey X:', newPubX);

// Compute pubkey from NEW priv using starknet.js's starkKeyPub
console.log('\nNEW priv starkKeyPub:', newPubX);
console.log('OLD priv starkKeyPub:', oldPubX);

// Also: try to find what class hash was used to derive NEW_ADDR
// Brute force: try OZ 0.1.0 with various salt candidates
const OZ_HASH = '0x061dac032f228abef9c6626f995015233097ae253a7f72d68552db02f2971b8f';
const TARGET = BigInt('0x0417678126db3e4eb21ca3c4dfd1b1920eb5fd2fd1e2136cbd215905be4a434d');

console.log('\n=== Brute force class hash + salt for NEW address ===');
// Try salts: 0, 1, pubkey, hash(pubkey), sha256(pubkey), deployer addr
const saltCandidates = [
  ['0', BigInt(0)],
  ['1', BigInt(1)],
  ['pubkey', BigInt(newPubX)],
  ['pubkey-low-16', BigInt(newPubX) & ((1n << 128n) - 1n)],
  ['pubkey-high-16', BigInt(newPubX) >> 128n],
];

const deployerCandidates = [
  ['no-deployer', '0x0'],
  ['old-deployer', OLD_ADDR],
];

for (const [sName, s] of saltCandidates) {
  for (const [dName, d] of deployerCandidates) {
    const calldata = CallData_compile([newPubX]);
    const a = hash.calculateContractAddressFromHash(s, OZ_HASH, calldata, d);
    const match = BigInt(a) === TARGET;
    console.log(`  salt=${sName} deployer=${dName}: ${match?'✓✓✓ MATCH':'no'} → 0x${BigInt(a).toString(16).padStart(64,'0').slice(0,16)}...`);
  }
}

function CallData_compile(arr) {
  // For cairo1 account constructor(public_key: felt252), calldata = [pubkey]
  return arr;
}
