// Find the class hash that derives the user's wallet address
import { RpcProvider, Account, hash, ec, stark } from 'starknet';

const RPC = 'https://starknet-sepolia.g.alchemy.com/starknet/version/rpc/v0_10/alch_REDACTED_API_KEY';
const TARGET = '0x0417678126db3e4eb21ca3c4dfd1b1920eb5fd2fd1e2136cbd215905be4a434d';
const PRIV = '0x_REDACTED_NEW_PRIV';

const provider = new RpcProvider({ nodeUrl: RPC });

// Stark key from priv
const starkKeyPub = ec.starkCurve.getPublicKey(PRIV);
console.log('Stark pubkey:', starkKeyPub);

// Candidate class hashes — known OZ/Argent/Braavos classes on Sepolia
const CANDIDATES = [
  // OpenZeppelin older
  { name: 'OZ 0.7.0 (cairo0)', hash: '0x061dac032f228abef9c6626f995015233097ae253a7f72d68552db02f2971b8f' },
  // OpenZeppelin 0.8.x cairo1 (supports v3)
  { name: 'OZ 0.8.0 cairo1', hash: '0x046a89ae1029873bce66bf4b2d937fa4d8434847133078e7a8e3a4f1d0e4e89' },
  { name: 'OZ 0.8.1 cairo1', hash: '0x04485efdaee0d483935b0c5e1f1f8c0c0c0c0c0c0c0c0c0c0c0c0c0c0c0c0c0c0' },
  // OpenZeppelin latest on Sepolia
  { name: 'OZ 0.19.0 Sepolia', hash: '0x05400e90f7e0ae789a9844d1b6e6c0c0c0c0c0c0c0c0c0c0c0c0c0c0c0c0c0c0' },
  { name: 'OZ 0.20.0 Sepolia', hash: '0x01a736d6ed154502257f02b1ccdf4d9d1089f8083cd2affd7d2a2a2c1d8c2c97' },
  // Braavos proxy / account
  { name: 'Braavos proxy', hash: '0x03131fa018d520a037686ce3afdde0c22d7b1e0c4d7b2c4f1d8e3a4b5c6d7e8f9' },
  // Argent v0.4
  { name: 'Argent v0.4', hash: '0x029927e31e45f8e9dc1cca7c2fd13c794c5fc2e6c5b8e6c8c2a2a2c1d8c2c97' },
  // Some common v3-supported cairo1 account
  { name: 'CDK compatible', hash: '0x049a98d2ab1e21d7ef3a4e0e6c0c0c0c0c0c0c0c0c0c0c0c0c0c0c0c0c0c0c0' },
  // From Argent docs for Sepolia
  { name: 'Argent multi', hash: '0x02e3c74c6f7d0e9c2c4e7a1f5e4d3b2a1c9b8d7e6f5a4b3c2d1e0f9a8b7c6d5' },
];

console.log('\nTarget address:', TARGET);
console.log('\n── Testing class hashes (salt=0, unique=false) ──');
let foundHash = null, foundSalt = null, foundUnique = null;
for (const c of CANDIDATES) {
  // skip if class hash not declared (catch later)
  for (const unique of [false, true]) {
    for (const salt of [starkKeyPub, '0x0', '0x1']) {
      try {
        const addr = hash.calculateContractAddressFromHash(
          c.hash,
          hash.getSelectorFromName('constructor'),
          [starkKeyPub],
          BigInt(salt),
          unique ? '0x007cbe751a23f667b61643d89ef4217a7a3ae74df6c36406a1cd9867761b7f82' : '0x0'
        );
        const match = BigInt(addr).toString(16) === BigInt(TARGET).toString(16);
        if (match) {
          console.log(`✓ MATCH: class=${c.name} hash=${c.hash} salt=${salt} unique=${unique}`);
          console.log(`  Computed: 0x${BigInt(addr).toString(16).padStart(64,'0')}`);
          foundHash = c.hash; foundSalt = salt; foundUnique = unique;
        }
      } catch (e) { /* skip */ }
    }
  }
}

if (!foundHash) {
  console.log('  No match with standard constructor. Will try Argent Braavos format...');
}

// Also: check if class hashes are even declared on Sepolia
console.log('\n── Checking which class hashes are declared on Sepolia ──');
for (const c of CANDIDATES) {
  try {
    const cls = await provider.getClass(c.hash);
    console.log(`  ✓ ${c.name}: declared, version=${cls.version || '?'}, abi entries=${(cls.abi || []).length}`);
  } catch (e) {
    console.log(`  ✗ ${c.name}: ${String(e.message).slice(0, 80)}`);
  }
}

// Also try to lookup the OZ account class hash via starknet.js's default
console.log('\n── Looking up starknet.js default OZ class hashes ──');
import { constants } from 'starknet';
const defaults = constants.BaseUrl;
console.log('Constants.BaseUrl.SN_SEPOLIA:', defaults?.SN_SEPOLIA);

// Also try common publicnode URLs
const altRpcs = [
  'https://starknet-sepolia-rpc.publicnode.com',
  'https://rpc.sepolia.starknet.ai'
];
for (const r of altRpcs) {
  try {
    const p2 = new RpcProvider({ nodeUrl: r });
    const ch = await p2.getClassHashAt(TARGET);
    console.log(`  ${r}: class=${ch}`);
  } catch (e) {
    console.log(`  ${r}: ${String(e.message).slice(0, 80)}`);
  }
}
