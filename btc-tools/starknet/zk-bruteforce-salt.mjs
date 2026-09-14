import { hash, ec, CallData } from 'starknet';

const NEW_ADDR = BigInt('0x0417678126db3e4eb21ca3c4dfd1b1920eb5fd2fd1e2136cbd215905be4a434d');
const NEW_PRIV = '0x_REDACTED_NEW_PRIV';
const OLD_ADDR = '0x007cbe751a23f667b61643d89ef4217a7a3ae74df6c36406a1cd9867761b7f82';

const fullPub = ec.starkCurve.getPublicKey(NEW_PRIV);
const pubXFelt = '0x' + Buffer.from(fullPub.slice(1,33)).toString('hex');
console.log('Pubkey X:', pubXFelt);
console.log('Target  :', '0x' + NEW_ADDR.toString(16).padStart(64, '0'));

// v3-compatible class hash from real Sepolia txs
const CH = '0xd632f69c8e02ea43f1d8a7c3eb441c67eb935f460c02e3860f7c410115d10f';
const OLD_CH = '0x061dac032f228abef9c6626f995015233097ae253a7f72d68552db02f2971b8f';

// Convert target to BigInt
console.log('\n=== Brute force salt for v3 class hash ===');
const saltCandidates = [
  pubXFelt,
  '0x0',
  '0x1',
  OLD_ADDR,
  // hash of pubkey
  hash.starknetKeccak(pubXFelt).toString(16),
  // pedersen of pubkey
  // sha256 of pubkey
  '0x' + Buffer.from(fullPub.slice(1)).toString('hex'),
];

for (const s of saltCandidates) {
  for (const d of ['0x0', OLD_ADDR]) {
    try {
      const a = hash.calculateContractAddressFromHash(
        BigInt(s), CH, [pubXFelt], d === '0x0' ? 0n : BigInt(d)
      );
      const match = BigInt(a) === NEW_ADDR;
      console.log(`  salt=${s.slice(0,20)}... deployer=${d.slice(0,16)}...: 0x${BigInt(a).toString(16).padStart(64,'0').slice(0,16)}...${match?' ✓✓✓ MATCH':''}`);
    } catch(e) {}
  }
}

// Try OZ 0.1.0 with this pubkey as both pubkey and salt
console.log('\n=== Try with OZ 0.1.0 (for comparison) ===');
for (const s of saltCandidates) {
  for (const d of ['0x0', OLD_ADDR]) {
    try {
      const a = hash.calculateContractAddressFromHash(
        BigInt(s), OLD_CH, [pubXFelt], d === '0x0' ? 0n : BigInt(d)
      );
      const match = BigInt(a) === NEW_ADDR;
      console.log(`  salt=${s.slice(0,20)}... deployer=${d.slice(0,16)}...: 0x${BigInt(a).toString(16).padStart(64,'0').slice(0,16)}...${match?' ✓✓✓ MATCH':''}`);
    } catch(e) {}
  }
}

// Also try the previous known validator address derivations to verify the formula
console.log('\n=== Verify against val2 known address (OZ 0.1.0 salt=pubkey) ===');
const val2Expected = BigInt('0x6a1e0617be069d72ae112ad8e227c5431169a20ae241c47845ab72a608b402d');
const a = hash.calculateContractAddressFromHash(
  BigInt(pubXFelt), OLD_CH, [pubXFelt], 0n
);
console.log('Computed:', '0x' + BigInt(a).toString(16).padStart(64, '0'));
console.log('Expected:', '0x' + val2Expected.toString(16).padStart(64, '0'));
console.log('Match:', BigInt(a) === val2Expected);

// Try the v3 class hash with salt=pubkey for val2's expected address
const a2 = hash.calculateContractAddressFromHash(
  BigInt(pubXFelt), CH, [pubXFelt], 0n
);
console.log('\nv3 CH salt=pubkey:', '0x' + BigInt(a2).toString(16).padStart(64, '0'));
console.log('Match NEW target:', BigInt(a2) === NEW_ADDR);
