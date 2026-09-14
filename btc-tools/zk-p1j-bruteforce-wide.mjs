// Wider brute force: iterate salt 0-1000 with each candidate class hash
import { hash, ec } from 'starknet';

const NEW_ADDR = BigInt('0x0417678126db3e4eb21ca3c4dfd1b1920eb5fd2fd1e2136cbd215905be4a434d');
const NEW_PRIV = '0x_REDACTED_NEW_PRIV';
const OLD_ADDR = '0x007cbe751a23f667b61643d89ef4217a7a3ae74df6c36406a1cd9867761b7f82';
const FRI = '0x04718f5a0fc34cc1af16a1cdee98ffb20c31f5cd61d6ab07201858f4287c938d';

const RPC = 'https://starknet-sepolia.g.alchemy.com/starknet/version/rpc/v0_10/alch_REDACTED_API_KEY';
async function rpc(method, params) {
  const r = await fetch(RPC, { method:'POST', headers:{'Content-Type':'application/json'},
    body: JSON.stringify({jsonrpc:'2.0',id:1,method, params}) });
  return await r.json();
}

const fullPub = ec.starkCurve.getPublicKey(NEW_PRIV);
const pubXFelt = '0x' + Buffer.from(fullPub.slice(1,33)).toString('hex');
const balSel = hash.getSelectorFromName('balanceOf');

async function checkBalance(addrHex) {
  const r = await rpc('starknet_call', [{contract_address: FRI, entry_point_selector: balSel, calldata: [addrHex]}, 'latest']);
  if (r.error || !r.result || r.result.length < 2) return null;
  return BigInt(r.result[0]) + (BigInt(r.result[1]) << 128n);
}

const classes = [
  '0xd632f69c8e02ea43f1d8a7c3eb441c67eb935f460c02e3860f7c410115d10f',
  '0x5b4b537eaa2399e3aa99c4e2e0208ebd6c71bc1467938cd52c798c601e43564',
  '0x36078334509b514626504edc9fb252328d1a240e4e948bef8d0c08dff45927f',
  '0x3957f9f5a1cbfe918cedc2015c85200ca51a5f7506ecb6de98a5207b759bf8a',
  '0x261c293c8084cd79086214176b33e5911677cec55104fddc8d25b0b736dcad',
  '0xe2eb8f5672af4e6a4e8a8f1b44989685e668489b0a25437733756c5a34a1d6',
  '0x73414441639dcd11d1846f287650a00c60c416b9d3ba45d31c651672125b2c2',
  '0x061dac032f228abef9c6626f995015233097ae253a7f72d68552db02f2971b8f',
];

const deployers = [0n, BigInt(OLD_ADDR)];

let found = null;
const totalCombos = classes.length * 1001 * deployers.length;
console.log(`Checking ${totalCombos} combinations...`);

let checked = 0;
for (const ch of classes) {
  if (found) break;
  for (let s = 0n; s <= 1000n; s++) {
    if (found) break;
    for (const d of deployers) {
      checked++;
      try {
        const a = hash.calculateContractAddressFromHash(s, ch, [pubXFelt], d);
        if (BigInt(a) === NEW_ADDR) {
          console.log(`✓✓✓ EXACT ADDRESS MATCH: ch=${ch} salt=${s} deployer=${d}`);
          found = { ch, salt: s.toString(), deployer: d.toString(16), args: 1 };
          break;
        }
        // Check balance (batch every 50 to avoid rate limit)
        if (checked % 50 === 0) {
          const addrHex = '0x' + BigInt(a).toString(16).padStart(64, '0');
          const bal = await checkBalance(addrHex);
          if (bal && bal > 0n) {
            console.log(`  addr=${addrHex.slice(0,16)}... bal=${(Number(bal)/1e18).toFixed(2)} ch=${ch.slice(0,16)}... salt=${s} deployer=0x${d.toString(16).slice(0,16)}...`);
            if (bal === 100n * 10n**18n) {
              console.log(`✓✓✓ BALANCE MATCH (100 STRK)! ch=${ch} salt=${s} deployer=${d}`);
              found = { ch, salt: s.toString(), deployer: d.toString(16), addr: addrHex };
              break;
            }
          }
        }
      } catch(e) {}
    }
  }
  console.log(`Done with class ${ch.slice(0,16)}... checked=${checked}`);
}

if (found) {
  console.log('\n═══════════════════════════════════════════════════════════');
  console.log('  FOUND');
  console.log(JSON.stringify(found, null, 2));
  console.log('═══════════════════════════════════════════════════════════');
} else {
  console.log(`\nNo match after ${checked} combinations. Wider search needed.`);
}
