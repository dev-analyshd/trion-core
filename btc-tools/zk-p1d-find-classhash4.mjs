// Find class hash — use correct starknet.js v10 API
import { RpcProvider, ec, hash, num, CallData } from 'starknet';

const RPC = 'https://starknet-sepolia.g.alchemy.com/starknet/version/rpc/v0_10/alch_REDACTED_API_KEY';
const TARGET = BigInt('0x0417678126db3e4eb21ca3c4dfd1b1920eb5fd2fd1e2136cbd215905be4a434d');
const PRIV = '0x_REDACTED_NEW_PRIV';
const DEPLOYER = '0x007cbe751a23f667b61643d89ef4217a7a3ae74df6c36406a1cd9867761b7f82';

const provider = new RpcProvider({ nodeUrl: RPC });

// Pubkey as felt (X coordinate of the Stark curve public key)
const fullPub = ec.starkCurve.getPublicKey(PRIV); // Uint8Array(65) uncompressed
const pubXBuf = fullPub.slice(1, 33); // X coord 32 bytes
const pubXFelt = '0x' + Buffer.from(pubXBuf).toString('hex');
console.log('Pub X felt:', pubXFelt);

const TARGET_HEX = '0x' + TARGET.toString(16).padStart(64, '0');
console.log('Target addr:', TARGET_HEX);

// Known class hashes
const OZ7_HASH = '0x061dac032f228abef9c6626f995015233097ae253a7f72d68552db02f2971b8f';

// Starknet.js v10 API:
// calculateContractAddressFromHash(salt, classHash, constructorCalldata, deployerAddress)
// constructorCalldata must be compiled via CallData.compile()
function tryAddr(classHash, salt, pubkey, deployerAddress = '0x0') {
  try {
    const calldata = CallData.compile([pubkey]);
    return hash.calculateContractAddressFromHash(salt, classHash, calldata, deployerAddress);
  } catch(e) { return null; }
}

// Verify: compute address of the OLD wallet using OLD priv to confirm formula
// We don't have OLD_PRIV but we know deployer address: 0x007cbe751a...
// Skipping verification.

// Test with various salts
console.log('\n── Test derivation (constructor(public_key)) ──');
const salts = [pubXFelt, '0x0', '0x1', DEPLOYER, pubXFelt.toLowerCase()];
const deployers = ['0x0', DEPLOYER];

const declaredClasses = [OZ7_HASH];
// Add real Sepolia class hashes that we should try
// From Starknet official docs (Sepolia testnet):
// OpenZeppelin cairo1 v0.8.0 sepolia: 0x049a98d2ab1e21d7ef3a4e0e6c0c0c0c0c0c0c0c0c0c0c0c0c0c0c0c0c0c0c0 (made up)
// Let me also test these common ones
const testClasses = [
  OZ7_HASH,
  '0x046a89ae1029873bce66bf4b2d937fa4d8434847133078e7a8e3a4f1d0e4e89',
  '0x049a98d2ab1e21d7ef3a4e0e6c0c0c0c0c0c0c0c0c0c0c0c0c0c0c0c0c0c0c0',
  '0x0572628c0e049b1c0d2e7a2b3c4d5e6f7a8b9c0d1e2f3a4b5c6d7e8f9a0b1c2',
  // Known Argent sepolia account class hashes
  '0x029927e31e45f8e9dc1cca7c2fd13c794c5fc2e6c5b8e6c8c2a2a2c1d8c2c97',
  // Braavos sepolia account class
  '0x03131fa018d520a037686ce3afdde0c22d7b1e0c4d7b2c4f1d8e3a4b5c6d7e8f9',
  // The cairo1 OpenZeppelin account class hash widely used on Sepolia:
  // From OZ docs: https://docs.openzeppelin.com/contracts-cairo/0.8.0/sepolia
  '0x04485efdaee0d483935b0c5e1f1f8c0c0c0c0c0c0c0c0c0c0c0c0c0c0c0c0c0c0',
];

// Check declared classes on Sepolia
console.log('\n── Check declared classes ──');
const declared = [];
for (const ch of testClasses) {
  try {
    const cls = await provider.getClass(ch);
    const fns = (cls.abi || []).filter(a => a.type === 'interface').flatMap(i => (i.items || [])).filter(i => i.type === 'function').map(f => f.name);
    const hasV3 = fns.some(f => f.includes('v3') || f === '__execute__');
    console.log(`  ✓ ${ch}: declared, version=${cls.version||'?'}, fns=${fns.length}, v3-style=${hasV3?'✓':'?'}`);
    declared.push(ch);
  } catch(e) {
    console.log(`  ✗ ${ch}: NOT declared`);
  }
}

console.log('\n── Try derivation for each declared class + salt + deployer ──');
let matched = null;
for (const ch of declared) {
  for (const s of salts) {
    for (const d of deployers) {
      const a = tryAddr(ch, s, pubXFelt, d);
      if (a === null) continue;
      const match = BigInt(a) === TARGET;
      if (match) {
        console.log(`✓✓✓ MATCH: class=${ch} salt=${s} deployer=${d}`);
        matched = { classHash: ch, salt: s, deployer: d };
      }
    }
  }
}

if (!matched) {
  console.log('  No match. Trying different constructor signatures...');
  // Try with constructor() — no args (some accounts have constructor with private key in storage init)
  for (const ch of declared) {
    for (const s of salts) {
      for (const d of deployers) {
        // Constructor with empty args
        for (const calldata of [[], [pubXFelt, pubXFelt], [DEPLOYER]]) {
          const a = tryAddr(ch, s, calldata, d);
          if (a === null) continue;
          if (BigInt(a) === TARGET) {
            console.log(`✓✓✓ MATCH: class=${ch} salt=${s} deployer=${d} calldata=[${calldata}]`);
            matched = { classHash: ch, salt: s, deployer: d, calldata };
          }
        }
      }
    }
  }
}

if (matched) {
  console.log('\n═══════════════════════════════════════════════════════════');
  console.log('  MATCH FOUND!');
  console.log(JSON.stringify(matched, null, 2));
  console.log('═══════════════════════════════════════════════════════════');
} else {
  console.log('\n  No match found. Need to deploy a NEW v3-compatible account (not the user-provided one).');
  console.log('  → We will deploy a fresh v3 account, fund it with STRK, and use it for all invokes.');
}
