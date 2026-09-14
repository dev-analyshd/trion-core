import { hash, ec } from 'starknet';

const NEW_ADDR = BigInt('0x0417678126db3e4eb21ca3c4dfd1b1920eb5fd2fd1e2136cbd215905be4a434d');
const NEW_PRIV = '0x_REDACTED_NEW_PRIV';
const OLD_ADDR = '0x007cbe751a23f667b61643d89ef4217a7a3ae74df6c36406a1cd9867761b7f82';

const fullPub = ec.starkCurve.getPublicKey(NEW_PRIV);
const pubXFelt = '0x' + Buffer.from(fullPub.slice(1,33)).toString('hex');
const priv = BigInt(NEW_PRIV);

console.log('Pubkey X:', pubXFelt);
console.log('Priv   :', NEW_PRIV);
console.log('Target :', '0x' + NEW_ADDR.toString(16).padStart(64, '0'));

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

const salts = [
  pubXFelt,
  '0x0', '0x1',
  OLD_ADDR,
  // priv-based
  NEW_PRIV,
  // priv+1
  '0x' + (priv + 1n).toString(16),
  // pub^priv
  '0x' + (BigInt(pubXFelt) ^ priv).toString(16),
  // various hashes
  '0x' + hash.starknetKeccak(pubXFelt).toString(16),
  '0x' + hash.starknetKeccak(NEW_PRIV).toString(16),
  // pedersen variants
  '0x' + hash.computePedersenHashOnElements([BigInt(pubXFelt)]).toString(16),
  '0x' + hash.computePedersenHashOnElements([priv]).toString(16),
  '0x' + hash.computePedersenHashOnElements([priv, BigInt(pubXFelt)]).toString(16),
  '0x' + hash.computePedersenHashOnElements([BigInt(pubXFelt), priv]).toString(16),
  // poseidon variants
  '0x' + hash.computePoseidonHashOnElements([BigInt(pubXFelt)]).toString(16),
  '0x' + hash.computePoseidonHashOnElements([priv]).toString(16),
  '0x' + hash.computePoseidonHashOnElements([priv, BigInt(pubXFelt)]).toString(16),
  // random small values
  '0x42', '0xdeadbeef', '0xff',
];

const deployers = ['0x0', OLD_ADDR];
let found = null;
for (const ch of classes) {
  for (const s of salts) {
    for (const d of deployers) {
      try {
        const args1 = [pubXFelt];
        const args2 = [pubXFelt, pubXFelt];
        const args0 = [];
        for (const args of [args1, args2, args0]) {
          const a = hash.calculateContractAddressFromHash(
            BigInt(s), ch, args, d === '0x0' ? 0n : BigInt(d)
          );
          if (BigInt(a) === NEW_ADDR) {
            console.log(`✓✓✓ MATCH: ch=${ch} salt=${s.slice(0,30)} deployer=${d} args=${args.length}`);
            found = { ch, salt: s, deployer: d, args: args.length };
          }
        }
      } catch (e) {}
    }
  }
}

if (!found) {
  console.log('\nNo match. Will need to deploy a fresh v3 account at a new address.');
  // Compute the address that the new priv key would derive if we used:
  // - Class hash 0xd632f69c8e02ea43f1d8a7c3eb441c67eb935f460c02e3860f7c410115d10f
  // - Salt = pubkey
  // - Deployer = 0
  const ch = '0xd632f69c8e02ea43f1d8a7c3eb441c67eb935f460c02e3860f7c410115d10f';
  const a1 = hash.calculateContractAddressFromHash(BigInt(pubXFelt), ch, [pubXFelt], 0n);
  console.log('\nFresh address (v3-class, salt=pubkey):', '0x' + BigInt(a1).toString(16).padStart(64, '0'));
  // Same with salt=0
  const a2 = hash.calculateContractAddressFromHash(0n, ch, [pubXFelt], 0n);
  console.log('Fresh address (v3-class, salt=0):', '0x' + BigInt(a2).toString(16).padStart(64, '0'));
}
