import { hash, ec } from 'starknet';

const NEW_ADDR = BigInt('0x0417678126db3e4eb21ca3c4dfd1b1920eb5fd2fd1e2136cbd215905be4a434d');
const NEW_PRIV = '0x_REDACTED_NEW_PRIV';
const OLD_ADDR = '0x007cbe751a23f667b61643d89ef4217a7a3ae74df6c36406a1cd9867761b7f82';

const fullPub = ec.starkCurve.getPublicKey(NEW_PRIV);
const pubXFelt = '0x' + Buffer.from(fullPub.slice(1,33)).toString('hex');
console.log('Pubkey X:', pubXFelt);
console.log('Target  :', '0x' + NEW_ADDR.toString(16).padStart(64, '0'));

// All v3 class hashes found on Sepolia
const classes = [
  '0xd632f69c8e02ea43f1d8a7c3eb441c67eb935f460c02e3860f7c410115d10f',
  '0x5b4b537eaa2399e3aa99c4e2e0208ebd6c71bc1467938cd52c798c601e43564',
  '0x36078334509b514626504edc9fb252328d1a240e4e948bef8d0c08dff45927f',
  '0x3957f9f5a1cbfe918cedc2015c85200ca51a5f7506ecb6de98a5207b759bf8a',
  '0x261c293c8084cd79086214176b33e5911677cec55104fddc8d25b0b736dcad',
  '0xe2eb8f5672af4e6a4e8a8f1b44989685e668489b0a25437733756c5a34a1d6',
  '0x73414441639dcd11d1846f287650a00c60c416b9d3ba45d31c651672125b2c2',
  // Also old OZ
  '0x061dac032f228abef9c6626f995015233097ae253a7f72d68552db02f2971b8f',
];

// Brute force salt candidates
const saltCandidates = [
  pubXFelt,
  '0x0',
  '0x1',
  OLD_ADDR,
  // hash of pubkey via various functions
  hash.starknetKeccak(pubXFelt).toString(16),
  // pedersen hash
  hash.computePedersenHash(BigInt(pubXFelt), 0n).toString(16),
  hash.computePedersenHash(BigInt(pubXFelt), BigInt(pubXFelt)).toString(16),
  // poseidon hash
  hash.computePoseidonHashOnElements([BigInt(pubXFelt)]).toString(16),
  // Various smart contract salt values
  '0x42',
  '0xdeadbeef',
];

const deployers = ['0x0', OLD_ADDR];

let found = null;
for (const ch of classes) {
  for (const s of saltCandidates) {
    for (const d of deployers) {
      try {
        // Try with 1-arg constructor (public_key)
        const a1 = hash.calculateContractAddressFromHash(
          BigInt(s), ch, [pubXFelt], d === '0x0' ? 0n : BigInt(d)
        );
        if (BigInt(a1) === NEW_ADDR) {
          console.log(`✓✓✓ MATCH (1-arg): ch=${ch} salt=${s.slice(0,20)}... deployer=${d}`);
          found = { ch, salt: s, deployer: d, args: 1 };
        }
        // Try with 2-arg constructor (public_key, owner)
        const a2 = hash.calculateContractAddressFromHash(
          BigInt(s), ch, [pubXFelt, pubXFelt], d === '0x0' ? 0n : BigInt(d)
        );
        if (BigInt(a2) === NEW_ADDR) {
          console.log(`✓✓✓ MATCH (2-arg): ch=${ch} salt=${s.slice(0,20)}... deployer=${d}`);
          found = { ch, salt: s, deployer: d, args: 2 };
        }
      } catch (e) {}
    }
  }
}

if (!found) {
  console.log('\nNo match found with simple salt candidates.');
  console.log('Need to either:');
  console.log('1. Try MORE salt candidates (random values)');
  console.log('2. Deploy a fresh v3 account at a NEW address (give up on user-provided address)');
}
