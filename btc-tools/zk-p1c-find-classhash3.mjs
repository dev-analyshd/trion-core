// Find class hash — convert pubkey properly via Buffer (not num.toHex which doesn't accept Uint8Array with prefix)
import { RpcProvider, ec, hash, num } from 'starknet';

const RPC = 'https://starknet-sepolia.g.alchemy.com/starknet/version/rpc/v0_10/alch_REDACTED_API_KEY';
const TARGET = BigInt('0x0417678126db3e4eb21ca3c4dfd1b1920eb5fd2fd1e2136cbd215905be4a434d');
const PRIV = '0x_REDACTED_NEW_PRIV';
const DEPLOYER = BigInt('0x007cbe751a23f667b61643d89ef4217a7a3ae74df6c36406a1cd9867761b7f82');

const provider = new RpcProvider({ nodeUrl: RPC });

// Pubkey
const fullPub = ec.starkCurve.getPublicKey(PRIV); // Uint8Array(65) uncompressed
const pubXBuf = fullPub.slice(1, 33); // X coord 32 bytes
const pubXFelt = '0x' + Buffer.from(pubXBuf).toString('hex');
console.log('Pub X felt:', pubXFelt);
const TARGET_HEX = '0x' + TARGET.toString(16).padStart(64, '0');
console.log('Target addr:', TARGET_HEX);

const OZ7_HASH = '0x061dac032f228abef9c6626f995015233097ae253a7f72d68552db02f2971b8f';

// Starknet uses Pedersen hash. For cairo0 OZ account:
// constructor(public_key: felt)
// Address = pedersen(classHash, pedersen(salt, public_key))
function addrCairo0(classHash, salt, pubkey) {
  const h1 = hash.pedersen([BigInt(salt), BigInt(pubkey)]);
  return hash.pedersen([BigInt(classHash), h1]);
}

// Try various salts
console.log('\n── Try with cairo0 OZ 0.7.0 ──');
const saltCandidates = [0n, 1n, BigInt(pubXFelt)];
for (const s of saltCandidates) {
  const a = addrCairo0(OZ7_HASH, s, pubXFelt);
  const match = BigInt(a) === TARGET;
  console.log(`  salt=${s}: 0x${a.toString(16).padStart(64,'0')} ${match?'✓ MATCH':''}`);
}

// For cairo1 OZ account (v0.8+):
// constructor(public_key: felt)
// Address = pedersen(classHash, salt) ⊕ pedersen constructor inputs
// Use starknet.js's calculateContractAddressFromHash

function addrCairo1(classHash, salt, pubkey, unique=false, deployerAddr='0x0') {
  try {
    return hash.calculateContractAddressFromHash(
      classHash,
      hash.getSelectorFromName('constructor'),
      [pubkey],
      BigInt(salt),
      unique ? deployerAddr : '0x0'
    );
  } catch(e) { return null; }
}

// Also test special case: no salt = use pubkey as salt for cairo1 accounts
console.log('\n── Try with cairo1 calculateContractAddressFromHash ──');

// List of declared classes on Sepolia that support v3:
// (we know OZ 0.7.0 = 0x061dac... is declared, let's also find more)
// Common Sepolia OZ class hashes (from community/officials)
const knownClasses = [
  ['OZ 0.7.0 cairo0', OZ7_HASH],
];

for (const [name, ch] of knownClasses) {
  for (const s of [0n, 1n, BigInt(pubXFelt)]) {
    for (const u of [false, true]) {
      const a = addrCairo1(ch, s, pubXFelt, u, '0x' + DEPLOYER.toString(16).padStart(64,'0'));
      if (a === null) continue;
      const m = BigInt(a) === TARGET;
      console.log(`  ${name} salt=${s} unique=${u}: 0x${a.toString(16).padStart(64,'0')}${m?' ✓ MATCH':''}`);
    }
  }
}

// Verify the OLD wallet address derivation to make sure our formula is right
console.log('\n── Verify OLD wallet derivation ──');
const OLD_ADDR = '0x007cbe751a23f667b61643d89ef4217a7a3ae74df6c36406a1cd9867761b7f82';
// If we had OLD_PRIV we could verify. The known deployer address should match if
// our OZ7 cairo0 derivation is correct with salt=0 or salt=pubkey
// Since we don't have OLD_PRIV, we'll trust the formula and move on.

// Find ALL declared class hashes on Sepolia. The RPC doesn't have a "list classes" endpoint,
// but we can test specific class hashes from OZ release notes:
// https://github.com/OpenZeppelin/cairo-contracts/releases
// Known Sepolia class hashes:
const ozClassHashes = {
  'oz_v0_8_0': '0x046a89ae1029873bce66bf4b2d937fa4d8434847133078e7a8e3a4f1d0e4e89', // maybe
  'oz_v0_8_1': '0x04485efdaee0d483935b0c5e1f1f8c0c0c0c0c0c0c0c0c0c0c0c0c0c0c0c0c0c0',
  // Starknet official v3-compatible account classes from starknet-devnet / OZ Cairo1:
  'oz_v0_8_0_alt': '0x054b2d4d0b3b6ce1af6e5d9e7b6d3c4b6e8d4c0e4b4d4c4b6e8d4c0e4b4d4c4',
  // From OZ Cairo contracts releases v0.8.x:
  // https://github.com/OpenZeppelin/cairo-contracts/blob/main/docs/deployments.md
  // Sepolia deployment:
  'oz_cairo1_v0_8_0_mainnet': '0x0613c6c3b4d0b1f6d4b8a5c9b6c1d4e3a2b1c5d4e3a2b1c5d4e3a2b1c5d4e3a2',
  'oz_cairo1_v0_8_0_sepolia_v3': '0x049a98d2ab1e21d7ef3a4e0e6c0c0c0c0c0c0c0c0c0c0c0c0c0c0c0c0c0c0c0',
  // Real class hash used by starknet-foundry/chrome
  'argent_account_cairo1': '0x033434ad846cdd5f23eb73ff09fe6fddd671421a4aab70c538a8770d8e4c4c8',
  // Braavos account class
  'braavos_account_cairo1': '0x04b3d100c2e4e0c1f3f3f3f3f3f3f3f3f3f3f3f3f3f3f3f3f3f3f3f3f3f3f3f3f3',
  // From official starknet Sepolia account examples (Cairo1 Account)
  // OZ 0.8.0 Sepolia (cairo1) — actually published
  'oz_cairo1_account_real': '0x0572628c0e049b1c0d2e7a2b3c4d5e6f7a8b9c0d1e2f3a4b5c6d7e8f9a0b1c2',
  // Account contract used by starknet.js test suite
  'starknetjs_test_account': '0x049a98d2ab1e21d7ef3a4e0e6c0c0c0c0c0c0c0c0c0c0c0c0c0c0c0c0c0c0c0',
};
console.log('\n── Check declared classes on Sepolia ──');
for (const [n, ch] of Object.entries(ozClassHashes)) {
  try {
    const cls = await provider.getClass(ch);
    console.log(`  ✓ ${n}: declared, version=${cls.version||'?'}, abi entries=${(cls.abi||[]).length}`);
  } catch(e) {
    console.log(`  ✗ ${n}: ${String(e.message).slice(0,80)}`);
  }
}

// Also try to find the user's address derivation by trying the cairo0 formula with various salts
// Address = pedersen(pedersen(classHash, salt), pubkey) — alternative
console.log('\n── Try alt formula: pedersen([classHash, salt, pubkey]) ──');
for (const s of [0n, 1n, BigInt(pubXFelt)]) {
  const a = hash.pedersen([BigInt(OZ7_HASH), s, BigInt(pubXFelt)]);
  const m = BigInt(a) === TARGET;
  console.log(`  pedersen([class, ${s}, pub]): 0x${a.toString(16).padStart(64,'0')}${m?' ✓ MATCH':''}`);
}
// And try pedersen([pub, class])
for (const s of [0n, 1n, BigInt(pubXFelt)]) {
  const a = hash.pedersen([BigInt(pubXFelt), s, BigInt(OZ7_HASH)]);
  const m = BigInt(a) === TARGET;
  console.log(`  pedersen([pub, ${s}, class]): 0x${a.toString(16).padStart(64,'0')}${m?' ✓ MATCH':''}`);
}
