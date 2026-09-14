// Fast local brute force: compute all addresses, check for match with user address
import { hash, ec } from 'starknet';

const NEW_ADDR = BigInt('0x0417678126db3e4eb21ca3c4dfd1b1920eb5fd2fd1e2136cbd215905be4a434d');
const NEW_PRIV = '0x_REDACTED_NEW_PRIV';
const OLD_ADDR = '0x007cbe751a23f667b61643d89ef4217a7a3ae74df6c36406a1cd9867761b7f82';

const fullPub = ec.starkCurve.getPublicKey(NEW_PRIV);
const pubXFelt = '0x' + Buffer.from(fullPub.slice(1,33)).toString('hex');
const priv = BigInt(NEW_PRIV);
console.log('Pubkey:', pubXFelt);
console.log('Target:', '0x' + NEW_ADDR.toString(16).padStart(64, '0'));

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

// Salt candidates including priv-based and hash-based
const salts = [
  pubXFelt, '0x0', '0x1', OLD_ADDR,
  NEW_PRIV,
  '0x' + (priv + 1n).toString(16),
  '0x' + (priv - 1n).toString(16),
  '0x' + (BigInt(pubXFelt) ^ priv).toString(16),
  '0x' + (BigInt(pubXFelt) + priv).toString(16),
  '0x' + (BigInt(pubXFelt) - priv).toString(16),
  // Hashes
  '0x' + hash.starknetKeccak(pubXFelt).toString(16),
  '0x' + hash.starknetKeccak(NEW_PRIV).toString(16),
  '0x' + hash.computePedersenHashOnElements([BigInt(pubXFelt)]).toString(16),
  '0x' + hash.computePedersenHashOnElements([priv]).toString(16),
  '0x' + hash.computePedersenHashOnElements([priv, BigInt(pubXFelt)]).toString(16),
  '0x' + hash.computePedersenHashOnElements([BigInt(pubXFelt), priv]).toString(16),
  '0x' + hash.computePoseidonHashOnElements([BigInt(pubXFelt)]).toString(16),
  '0x' + hash.computePoseidonHashOnElements([priv]).toString(16),
  '0x' + hash.computePoseidonHashOnElements([priv, BigInt(pubXFelt)]).toString(16),
  // SHA256 of pubkey
  '0x' + (await import('crypto')).createHash('sha256').update(Buffer.from(pubXFelt.replace('0x',''), 'hex')).digest('hex').slice(0, 64).padStart(64, '0'),
  // Keccak256 of pubkey (EVM style)
  // Truncated pedersen
  '0x' + (BigInt(pubXFelt) & ((1n << 128n) - 1n)).toString(16),
  '0x' + (BigInt(pubXFelt) >> 128n).toString(16),
];

const deployers = [0n, BigInt(OLD_ADDR), BigInt(NEW_ADDR)];

let found = null;
let totalChecked = 0;
for (const ch of classes) {
  for (const s of salts) {
    for (const d of deployers) {
      // Try 0, 1, 2 args
      for (const nArgs of [1, 2, 0]) {
        const args = nArgs === 0 ? [] : nArgs === 1 ? [pubXFelt] : [pubXFelt, pubXFelt];
        try {
          const a = hash.calculateContractAddressFromHash(BigInt(s), ch, args, d);
          totalChecked++;
          if (BigInt(a) === NEW_ADDR) {
            console.log(`✓✓✓ MATCH: ch=${ch} salt=${s.slice(0,20)}... deployer=${'0x'+d.toString(16).slice(0,16)}... args=${nArgs}`);
            found = { ch, salt: s, deployer: d.toString(16), args: nArgs };
          }
        } catch(e) {}
      }
    }
  }
}

console.log(`\nTotal combinations checked: ${totalChecked}`);
if (found) {
  console.log('\n═══════════════════════════════════════════════════════════');
  console.log('  FOUND!');
  console.log(JSON.stringify(found, null, 2));
  console.log('═══════════════════════════════════════════════════════════');
} else {
  console.log('No match. Will deploy a fresh v3 account at a NEW address.');
}
