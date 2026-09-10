import { ethers } from 'ethers';
import fs from 'fs';
import crypto from 'crypto';

const RPC = 'https://sepolia-rollup.arbitrum.io/rpc';
const PK = '0x293b2a244a82c8b3639895c4a9ad8f3d548fd1793bb9d26698b3cfd0bc90cc6d';
const BTC_RPC = 'https://bitcoin-testnet.g.alchemy.com/v2/alch_s5FpWzSEKTzISMWu761j2';
const TXID = '62bfe73fab5ac18c64794493d3713c5eb3e92b839df401befecd68162ee1fcf7';
const BTC_ADDR = 'tb1q5d69fyxxxwdkr7pecmxyr245w5jqchm9zptkks';
const BTC_CID = 100;
const TARGET = 5128449;
const GEN = TARGET - 6;
const TIP = TARGET + 6; // submit up to 5128455 for depth=6

const provider = new ethers.JsonRpcProvider(RPC);
const wallet = new ethers.Wallet(PK, provider);

const SPV_ABI = JSON.parse(fs.readFileSync('contracts/solidity/compiled/BTCSPVVerifierArb.abi', 'utf8'));
const SPV_BIN = '0x' + fs.readFileSync('contracts/solidity/compiled/BTCSPVVerifierArb.bin', 'utf8').trim();
const REG_ABI = JSON.parse(fs.readFileSync('contracts/solidity/compiled/OOAAnchorRegistry.abi', 'utf8'));
const REG_BIN = '0x' + fs.readFileSync('contracts/solidity/compiled/OOAAnchorRegistry.bin', 'utf8').trim();

let nextNonce = await provider.getTransactionCount(wallet.address, 'latest');
console.log('Account:', wallet.address, 'nonce:', nextNonce);

async function stx(label, fn) {
  for (let a = 1; a <= 15; a++) {
    try {
      const t = await fn(nextNonce);
      nextNonce++;
      const r = await t.wait();
      console.log('  ' + label + ': ' + (r.status === 1 ? 'OK' : 'FAIL') + ' ' + t.hash.slice(0, 14));
      return r;
    } catch (e) {
      if (/nonce/i.test(String(e.message)) && a < 15) {
        nextNonce = await provider.getTransactionCount(wallet.address, 'latest');
        await new Promise(r => setTimeout(r, 2000));
        continue;
      }
      console.log('  ' + label + ': ERR ' + String(e.message).slice(0, 120));
      return null;
    }
  }
  return null;
}

async function btc(m, p = []) {
  const r = await fetch(BTC_RPC, { method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify({ jsonrpc: '2.0', method: m, params: p, id: 1 }) });
  const j = await r.json(); if (j.error) throw new Error(j.error.message); return j.result;
}
function ds(b) { const a = crypto.createHash('sha256').update(b).digest(); return crypto.createHash('sha256').update(a).digest(); }

// BTC data
const tx = await btc('getrawtransaction', [TXID, true]);
const bh = await btc('getblockheader', [tx.blockhash, false]);
const hb = Buffer.from(bh, 'hex');
const bt = hb.readUInt32LE(68);
const bH = tx.blockhash;
const bHb = Buffer.from(bH, 'hex');
const v0 = tx.vout.find(v => v.n === 0);
const amt = Math.round(v0.value * 1e8);
const eB = crypto.createHash('sha256').update(BTC_ADDR.toLowerCase()).digest();
const mag = BigInt(amt) * 1_000_000_000n;
const b = Buffer.alloc(93);
eB.copy(b, 0, 0, 32); b.writeUInt8(0, 32); b.writeBigUInt64BE(mag, 33);
b.writeBigUInt64BE(BigInt(bt), 49); b.writeUInt32BE(BTC_CID, 57); bHb.copy(b, 61, 0, 32);
const sen = crypto.createHash('sha256').update(Buffer.concat([b, Buffer.from([0x00])])).digest();
const aBH = '0x' + sen.toString('hex');
const bHU = '0x' + bH.padStart(64, '0');
const txH = '0x' + TXID;
const eH = '0x' + eB.toString('hex');
const b2 = await btc('getblock', [tx.blockhash, 2]);
const txids = b2.tx.map(t => t.txid);
let lv = txids.map(t => Buffer.from(t, 'hex').reverse());
let ix = txids.indexOf(TXID);
const mp = [];
while (lv.length > 1) {
  const si = (ix % 2 === 0) ? ix + 1 : ix - 1;
  const sb = (si < lv.length) ? lv[si] : lv[ix];
  mp.push('0x' + Buffer.from(sb).reverse().toString('hex'));
  const nx = [];
  for (let i = 0; i < lv.length; i += 2) { const l = lv[i]; const r = (i + 1 < lv.length) ? lv[i + 1] : l; nx.push(ds(Buffer.concat([l, r]))); }
  lv = nx; ix = Math.floor(ix / 2);
}
console.log('BTC:', b2.height, 'aBH:', aBH.slice(0, 16) + '...');

// Deploy SPV
console.log('\nDeploy SPV...');
const sf = new ethers.ContractFactory(SPV_ABI, SPV_BIN, wallet);
const spvC = await sf.deploy(wallet.address, false, { nonce: nextNonce });
nextNonce++;
await spvC.waitForDeployment();
const spvAddr = await spvC.getAddress();
console.log('SPV:', spvAddr);
const spv = new ethers.Contract(spvAddr, SPV_ABI, wallet);

// Genesis
console.log('Genesis at', GEN);
const gH = await btc('getblockhash', [GEN]);
const gHd = await btc('getblockheader', [gH, true]);
const gB = Buffer.from(await btc('getblockheader', [gH, false]), 'hex');
const gT = gB.readUInt32LE(68); const gBits = gB.readUInt32LE(72);
const gMr = '0x' + gHd.merkleroot.padStart(64, '0'); // BE display order
const gHU = '0x' + gH.padStart(64, '0');
await stx('genesis', (nn) => spv.submitBlockHeaderTrusted(gHU, BigInt(GEN), gMr, BigInt(gT), gBits, { nonce: nn }));

// Submit blocks
for (let h = GEN + 1; h <= TIP; h++) {
  const bh2 = await btc('getblockhash', [h]);
  const hd = await btc('getblockheader', [bh2, true]);
  const hB = Buffer.from(await btc('getblockheader', [bh2, false]), 'hex');
  const hT = hB.readUInt32LE(68); const hBits = hB.readUInt32LE(72);
  const hMr = '0x' + hd.merkleroot.padStart(64, '0'); // BE display order
  const hU = '0x' + bh2.padStart(64, '0');
  await stx('block-' + h, (nn) => spv.submitBlockHeaderTrusted(hU, BigInt(h), hMr, BigInt(hT), hBits, { nonce: nn }));
}

// Check tip
const tip = await spv.getChainTip();
console.log('Tip:', tip[1].toString(), '(expect', TARGET, ')');

// Verify anchor
console.log('\nVerify anchor...');
const rid = '0x' + crypto.createHash('sha256').update('arb-final-' + Date.now()).digest('hex').slice(0, 64);
const vr = await stx('verify', (nn) => spv.verifyAnchor(aBH, bHU, txH, txids.indexOf(TXID), mp, eH, 0, mag, BigInt(bt), BTC_CID, 0n, { nonce: nn }));

// Deploy registry
console.log('\nDeploy registry...');
const rf = new ethers.ContractFactory(REG_ABI, REG_BIN, wallet);
const regC = await rf.deploy(wallet.address, spvAddr, { nonce: nextNonce });
nextNonce++;
await regC.waitForDeployment();
const regAddr = await regC.getAddress();
console.log('Registry:', regAddr);
const reg = new ethers.Contract(regAddr, REG_ABI, wallet);

// Anchor
console.log('\nAnchor...');
await stx('anchor', (nn) => reg.anchor(rid, aBH, bHU, txH, txids.indexOf(TXID), mp, eH, 0, mag, BigInt(bt), BTC_CID, 0n, { nonce: nn }));

// Read back
try {
  const a = await reg.getAnchor(rid);
  console.log('depth:', a.depth.toString(), 'confidence:', (Number(a.confidence) / 1e9).toFixed(6), 'active:', a.active);
} catch (e) { console.log('read:', String(e.message).slice(0, 80)); }

// Renounce
await stx('renounce', (nn) => spv.renounceGenesisAbility({ nonce: nn }));

// Adversarial
console.log('\nAdversarial:');
const mBuf = Buffer.from(b); mBuf[0] ^= 0x01;
const mSen = crypto.createHash('sha256').update(Buffer.concat([mBuf, Buffer.from([0x00])])).digest();
const mBH = '0x' + mSen.toString('hex');
try { await spv.verifyAnchor.staticCall(mBH, bHU, txH, txids.indexOf(TXID), mp, eH, 0, mag, BigInt(bt), BTC_CID, 0n); console.log('  A6: FAIL'); } catch { console.log('  A6: REVERTED OK'); }
try { await spv.verifyAnchor.staticCall(aBH, bHU, '0x' + crypto.createHash('sha256').update('fake').digest('hex'), txids.indexOf(TXID), mp, eH, 0, mag, BigInt(bt), BTC_CID, 0n); console.log('  A5: FAIL'); } catch { console.log('  A5: REVERTED OK'); }
try { await spv.verifyAnchor.staticCall(aBH, bHU, txH, txids.indexOf(TXID), mp, eH, 0, mag, BigInt(bt), BTC_CID, 2000000n); console.log('  A7: FAIL'); } catch { console.log('  A7: REVERTED OK'); }
try { await spv.verifyAnchor.staticCall(aBH, '0x' + 'ab'.repeat(32), txH, 0, mp, eH, 0, mag, BigInt(bt), BTC_CID, 0n); console.log('  A1: FAIL'); } catch { console.log('  A1: REVERTED OK'); }

// Save
fs.writeFileSync('docs/proofs/arbitrum_ooa_proof.json', JSON.stringify({
  spvVerifier: spvAddr, registry: regAddr, routeId: rid,
  btc: { txid: TXID, blockHash: bH, anchorBh: aBH, blockHeight: TARGET },
  timestamp: new Date().toISOString()
}, null, 2));
console.log('\nDONE: SPV=' + spvAddr + ' Reg=' + regAddr);
