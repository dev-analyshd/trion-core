// Brute force class hash + salt for the user's address by checking on-chain STRK balance
import { hash, ec } from 'starknet';

const NEW_ADDR = BigInt('0x0417678126db3e4eb21ca3c4dfd1b1920eb5fd2fd1e2136cbd215905be4a434d');
const NEW_PRIV = '0x_REDACTED_NEW_PRIV';
const OLD_ADDR = '0x007cbe751a23f667b61643d89ef4217a7a3ae74df6c36406a1cd9867761b7f82';
const FRI = '0x04718f5a0fc34cc1af16a1cdee98ffb20c31f5cd61d6ab07201858f4287c938d';  // Sepolia STRK
const TARGET_BAL = 100n * 10n**18n;  // 100 STRK

const RPC = 'https://starknet-sepolia.g.alchemy.com/starknet/version/rpc/v0_10/alch_REDACTED_API_KEY';
async function rpc(method, params) {
  const r = await fetch(RPC, { method:'POST', headers:{'Content-Type':'application/json'},
    body: JSON.stringify({jsonrpc:'2.0',id:1,method, params}) });
  return await r.json();
}

const fullPub = ec.starkCurve.getPublicKey(NEW_PRIV);
const pubXFelt = '0x' + Buffer.from(fullPub.slice(1,33)).toString('hex');
const priv = BigInt(NEW_PRIV);

const balSel = hash.getSelectorFromName('balanceOf');

async function checkBalance(addr) {
  const r = await rpc('starknet_call', [{contract_address: FRI, entry_point_selector: balSel, calldata: [addr]}, 'latest']);
  if (r.error) return null;
  if (!r.result || r.result.length < 2) return null;
  const low = BigInt(r.result[0]);
  const high = BigInt(r.result[1]);
  return low + (high << 128n);
}

// Verify target balance
console.log('=== Verify user-provided address balance ===');
const bal = await checkBalance('0x' + NEW_ADDR.toString(16).padStart(64, '0'));
console.log(`User address STRK balance: ${bal ? (Number(bal) / 1e18).toFixed(4) : 'n/a'} (target: 100)`);

// Now compute candidate addresses with various class hashes + salts, check each balance
const classes = [
  '0xd632f69c8e02ea43f1d8a7c3eb441c67eb935f460c02e3860f7c410115d10f',  // common v3
  '0x5b4b537eaa2399e3aa99c4e2e0208ebd6c71bc1467938cd52c798c601e43564',
  '0x36078334509b514626504edc9fb252328d1a240e4e948bef8d0c08dff45927f',
  '0x3957f9f5a1cbfe918cedc2015c85200ca51a5f7506ecb6de98a5207b759bf8a',
  '0x261c293c8084cd79086214176b33e5911677cec55104fddc8d25b0b736dcad',
  '0xe2eb8f5672af4e6a4e8a8f1b44989685e668489b0a25437733756c5a34a1d6',
  '0x73414441639dcd11d1846f287650a00c60c416b9d3ba45d31c651672125b2c2',
  '0x061dac032f228abef9c6626f995015233097ae253a7f72d68552db02f2971b8f',  // OZ 0.1.0 (broken)
];

const salts = [
  pubXFelt, '0x0', '0x1', OLD_ADDR,
  // priv-based
  NEW_PRIV,
  // hashes
  '0x' + hash.starknetKeccak(pubXFelt).toString(16),
  '0x' + hash.computePedersenHashOnElements([BigInt(pubXFelt)]).toString(16),
  '0x' + hash.computePedersenHashOnElements([priv]).toString(16),
  '0x' + hash.computePedersenHashOnElements([priv, BigInt(pubXFelt)]).toString(16),
  '0x' + hash.computePoseidonHashOnElements([BigInt(pubXFelt)]).toString(16),
  '0x' + hash.computePoseidonHashOnElements([priv]).toString(16),
];

const deployers = ['0x0', OLD_ADDR];

let found = null;
let candidatesWithBalance = [];
for (const ch of classes) {
  for (const s of salts) {
    for (const d of deployers) {
      // Try 1-arg constructor (pubkey)
      try {
        const a = hash.calculateContractAddressFromHash(
          BigInt(s), ch, [pubXFelt], d === '0x0' ? 0n : BigInt(d)
        );
        const addrHex = '0x' + BigInt(a).toString(16).padStart(64, '0');
        if (BigInt(a) === NEW_ADDR) {
          console.log(`✓✓✓ EXACT MATCH: ch=${ch} salt=${s.slice(0,30)}... deployer=${d}`);
          found = { ch, salt: s, deployer: d, args: 1 };
        }
        // Check balance
        const bal = await checkBalance(addrHex);
        if (bal && bal > 0n) {
          candidatesWithBalance.push({ addr: addrHex, bal: bal, ch, salt: s, deployer: d, args: 1 });
          if (bal === TARGET_BAL) {
            console.log(`✓✓✓ BALANCE MATCH (100 STRK): addr=${addrHex.slice(0,16)}... ch=${ch.slice(0,20)}...`);
            if (!found) found = { ch, salt: s, deployer: d, args: 1, addr: addrHex };
          }
        }
      } catch(e) {}
    }
  }
}

console.log('\n=== Addresses with non-zero STRK balance ===');
for (const c of candidatesWithBalance) {
  console.log(`  addr=${c.addr.slice(0,20)}... bal=${(Number(c.bal)/1e18).toFixed(4)} STRK ch=${c.ch.slice(0,16)}... salt=${c.salt.slice(0,16)}... deployer=${c.deployer.slice(0,16)}...`);
}

if (found) {
  console.log('\n═══════════════════════════════════════════════════════════');
  console.log('  FOUND! Class hash + salt that produces the user address');
  console.log(JSON.stringify(found, null, 2));
  console.log('═══════════════════════════════════════════════════════════');
} else {
  console.log('\nNo match found yet. Try more combinations...');
}
