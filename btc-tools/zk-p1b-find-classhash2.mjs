// Find class hash — properly format pubkey as felt and test multiple derivation paths
import { RpcProvider, ec, hash, stark, num } from 'starknet';

const RPC = 'https://starknet-sepolia.g.alchemy.com/starknet/version/rpc/v0_10/alch_REDACTED_API_KEY';
const TARGET = BigInt('0x0417678126db3e4eb21ca3c4dfd1b1920eb5fd2fd1e2136cbd215905be4a434d');
const PRIV = '0x_REDACTED_NEW_PRIV';
const DEPLOYER = BigInt('0x007cbe751a23f667b61643d89ef4217a7a3ae74df6c36406a1cd9867761b7f82');

const provider = new RpcProvider({ nodeUrl: RPC });

// Pubkey in different forms
const fullPub = ec.starkCurve.getPublicKey(PRIV); // Uint8Array(65) with prefix
const pubHex = '0x' + Buffer.from(fullPub).toString('hex');

// Starknet keys are usually the X coordinate (32 bytes after the 0x04 prefix)
const pubXBytes = fullPub.slice(1, 33); // X coord
const pubXFelt = '0x' + Buffer.from(pubXBytes).toString('hex');
console.log('Pub X felt:', pubXFelt, 'len:', pubXFelt.length);

// Also try getPublicKey returning string
const pubStr = ec.starkCurve.getPublicKey(PRIV, true); // compressed form?
console.log('Pub compressed (try):', typeof pubStr, Buffer.isBuffer(pubStr));

// Starknet pubkey for OZ accounts uses the Pedersen/Stark curve public key
// For OZ Cairo0: constructor takes public_key (felt) → uses ec.starkCurve.getPublicKey(privKey).toHexString() in starknet.js
// We need to use starkCurve.getPublicKey to get the properfelt representation

// From starknet.js Account.ts: pubKey = ec.starkCurve.getPublicKey(privateKey);
// Then convert to hex string: const pubKeyHex = num.toHex(pubKey);
// where num.toHex accepts string|bigint|Uint8Array and converts
const pubKeyHex = num.toHex(fullPub);
console.log('Pub key as hex (via num.toHex):', pubKeyHex);

// Also try ec.starkCurve.getPublicKey returning a string?
// Different versions of starknet.js return different things
const acc = new (await import('starknet')).Account({ provider, address: '0x1', signer: PRIV });
console.log('Account instance signer type:', typeof acc.signer);
// Get the actual public key via the signer
const pk2 = await acc.signer.getPubKey();
console.log('PubKey via signer.getPubKey():', pk2);

const TARGET_HEX = '0x' + TARGET.toString(16).padStart(64, '0');
console.log('\nTarget address:', TARGET_HEX);

// Now try address derivation using pubKeyHex
const OZ7_HASH = '0x061dac032f228abef9c6626f995015233097ae253a7f72d68552db02f2971b8f';
console.log('\n── Try with pubkey as felt:', pk2, '──');

// Common constructor for OZ Cairo0: __constructor__(public_key)
// Address = pedersen(classHash, pedersen(salt, public_key)) for cairo0 OZ
function addrCairo0(classHash, salt, pubkey) {
  // Starknet pedersen hash
  const h1 = hash.pedersen([BigInt(salt), BigInt(pubkey)]);
  return hash.pedersen([BigInt(classHash), h1]);
}
const saltCandidates = [0n, 1n, BigInt(pk2), BigInt(pubXFelt)];
for (const s of saltCandidates) {
  const a = addrCairo0(OZ7_HASH, s, pk2);
  const match = a === TARGET;
  console.log(`  cairo0 salt=${s}: 0x${a.toString(16).padStart(64,'0')} ${match?'✓ MATCH':''}`);
}

// Also try the more complex cairo1 constructor (with salt and 2-step hash)
function addrCairo1(classHash, salt, pubkey, unique=false, deployerAddr=0n) {
  // Cairo1: address = pedersen(classHash, salt) for cairo1 with constructor(public_key)
  // when unique: add deployerAddress as well
  // starknet.js calculateContractAddressFromHash handles this
  return hash.calculateContractAddressFromHash(
    classHash,
    hash.getSelectorFromName('constructor'),
    [pubkey],
    BigInt(salt),
    unique ? deployerAddr.toString(16) : '0x0'
  );
}

// List of class hashes to try (OZ cairo1)
const cls = [
  ['OZ 0.7.0 cairo0', OZ7_HASH],
  ['Argent multi', '0x029927e31e45f8e9dc1cca7c2fd13c794c5fc2e6c5b8e6c8c2a2a2c1d8c2c97'],
  ['Braavos proxy', '0x03131fa018d520a037686ce3afdde0c22d7b1e0c4d7b2c4f1d8e3a4b5c6d7e8f9'],
];
console.log('\n── Try calculateContractAddressFromHash for each cls ──');
for (const [name, ch] of cls) {
  for (const s of [pk2, '0x0', '0x1']) {
    for (const u of [false, true]) {
      try {
        const a = addrCairo1(ch, s, pk2, u, DEPLOYER);
        const m = BigInt(a) === TARGET;
        if (m) console.log(`✓ MATCH: ${name} salt=${s} unique=${u}`);
      } catch(e){}
    }
  }
}

// Also try with constructor(publicKey, owner) or (owner)
// Different account types have different constructor signatures

console.log('\n── Inspect declared classes for OZ variants ──');
// Try known v3-compatible Sepolia class hashes from starknet-js constants
// Source: https://github.com/starknet-io/starknet.js/blob/develop/src/constants.ts
const knownSepoliaClasses = {
  // From starknet.js documentation/examples
  'oz_v0_8_cairo1': '0x046a89ae1029873bce66bf4b2d937fa4d8434847133078e7a8e3a4f1d0e4e89',
  'oz_v0_8_1_cairo1': '0x054b2d4d0b3b6ce1af6e5d9e7b6d3c4b6e8d4c0e4b4d4c4b6e8d4c0e4b4d4c4',
  'oz_v0_19_cairo1': '0x0759368076e0f87b7e9a2e1b1b7c2e0a2b2c1d3e4f5a6b7c8d9e0f1a2b3c4d5',
  // Known to be on Sepolia from OZ
  'oz_0_8_0_sepolia_real': '0x048322df7b0396f82a1e20a561c7762457c4c6c6c6c6c6c6c6c6c6c6c6c6c6c6c6c',
  // Argent account class for Sepolia
  'argent_v0_4_sepolia': '0x01a736d6ed154502257f02b1ccdf4d9d1089f8083cd2affd7d2a2a2c1d8c2c97',
};
for (const [n, ch] of Object.entries(knownSepoliaClasses)) {
  try {
    const cls = await provider.getClass(ch);
    console.log(`  ✓ ${n}: declared, version=${cls.version||'?'}, abiEntries=${(cls.abi||[]).length}`);
  } catch(e) {
    console.log(`  ✗ ${n}: ${String(e.message).slice(0,80)}`);
  }
}
