// Derive Bitcoin testnet address from EVM private key
// Using @noble/secp256k1 directly for key derivation + manual address encoding
import * as ecc from '@noble/secp256k1';
import crypto from 'crypto';

const evmPrivateKey = '***REDACTED-EVM-DEPLOYER-KEY***';
const privateKeyHex = evmPrivateKey.slice(2);
const privateKeyBuffer = Buffer.from(privateKeyHex, 'hex');

// Step 1: Get public key (compressed, 33 bytes)
const publicKey = ecc.getPublicKey(privateKeyBuffer, true);
const pubKeyBuffer = Buffer.from(publicKey);

// Step 2: SHA256 then RIPEMD160 of the public key
const sha256Hash = crypto.createHash('sha256').update(pubKeyBuffer).digest();
// Node.js doesn't have ripemd160 built-in, let's use a manual implementation
const ripemd160 = (data) => {
  // Use crypto.createHash('ripemd160') if available
  try {
    return crypto.createHash('ripemd160').update(data).digest();
  } catch (e) {
    // Fallback: use a pure JS implementation
    throw new Error('RIPEMD160 not available');
  }
};

const pubkeyHash = ripemd160(sha256Hash);

// Step 3: P2PKH address (legacy, testnet)
// Testnet prefix: 0x6f
const testnetP2PKH = Buffer.concat([
  Buffer.from([0x6f]),
  pubkeyHash,
]);
// Double SHA256 checksum
const checksum1 = crypto.createHash('sha256').update(testnetP2PKH).digest();
const checksum2 = crypto.createHash('sha256').update(checksum1).digest();
const p2pkhBinary = Buffer.concat([testnetP2PKH, checksum2.slice(0, 4)]);
const p2pkhAddress = base58Encode(p2pkhBinary);

// Step 4: P2WPKH address (Bech32, testnet)
// Testnet HRP (Human Readable Part): "tb"
const bech32Address = bech32Encode('tb', 0, pubkeyHash);

// Step 5: WIF (Wallet Import Format)
const testnetWIF = Buffer.concat([
  Buffer.from([0xef]),  // testnet prefix
  privateKeyBuffer,
  Buffer.from([0x01]),   // compressed flag
]);
const wifChecksum1 = crypto.createHash('sha256').update(testnetWIF).digest();
const wifChecksum2 = crypto.createHash('sha256').update(wifChecksum1).digest();
const wifBinary = Buffer.concat([testnetWIF, wifChecksum2.slice(0, 4)]);
const wif = base58Encode(wifBinary);

// ── Helper: Base58 encoding ──
function base58Encode(buffer) {
  const alphabet = '123456789ABCDEFGHJKLMNPQRSTUVWXYZabcdefghijkmnopqrstuvwxyz';
  let num = BigInt('0x' + buffer.toString('hex'));
  let encoded = '';
  while (num > 0n) {
    const remainder = num % 58n;
    num = num / 58n;
    encoded = alphabet[Number(remainder)] + encoded;
  }
  for (let i = 0; i < buffer.length && buffer[i] === 0; i++) {
    encoded = alphabet[0] + encoded;
  }
  return encoded;
}

// ── Helper: Bech32 encoding (BIP173) ──
function bech32Encode(hrp, witver, witprog) {
  const charset = 'qpzry9x8gf2tvdw0s3jn54khce6mua7l';
  
  function bech32Polymod(values) {
    const GEN = [0x3b6a57b2, 0x26508e6d, 0x1ea119fa, 0x3d4233dd, 0x2a1462b3];
    let chk = 1;
    for (const v of values) {
      const b = chk >> 25;
      chk = ((chk & 0x1ffffff) << 5) ^ v;
      for (let i = 0; i < 5; i++) {
        if (((b >> i) & 1) === 1) chk ^= GEN[i];
      }
    }
    return chk;
  }
  
  function bech32HrpExpand(hrp) {
    return hrp.split('').map(c => c.charCodeAt(0) >> 5).concat([0]).concat(hrp.split('').map(c => c.charCodeAt(0) & 31));
  }
  
  function bech32CreateChecksum(hrp, data) {
    const values = bech32HrpExpand(hrp).concat(data).concat([0, 0, 0, 0, 0, 0]);
    const polymod = bech32Polymod(values) ^ 1;
    const ret = [];
    for (let i = 0; i < 6; i++) {
      ret.push((polymod >> 5 * (5 - i)) & 31);
    }
    return ret;
  }
  
  function convertbits(data, frombits, tobits, pad) {
    let acc = 0;
    let bits = 0;
    const ret = [];
    const maxv = (1 << tobits) - 1;
    for (const value of data) {
      if (value < 0 || (value >> frombits) !== 0) return null;
      acc = (acc << frombits) | value;
      bits += frombits;
      while (bits >= tobits) {
        bits -= tobits;
        ret.push((acc >> bits) & maxv);
      }
    }
    if (pad) {
      if (bits > 0) ret.push((acc << (tobits - bits)) & maxv);
    } else if (bits >= frombits || ((acc << (tobits - bits)) & maxv)) {
      return null;
    }
    return ret;
  }
  
  const data = [witver].concat(convertbits(Array.from(witprog), 8, 5, true));
  const checksum = bech32CreateChecksum(hrp, data);
  const combined = data.concat(checksum);
  return hrp + '1' + combined.map(v => charset[v]).join('');
}

console.log('═══════════════════════════════════════════════════════════');
console.log('  Bitcoin Testnet Address Derivation                       ');
console.log('═══════════════════════════════════════════════════════════');
console.log(`  EVM Private Key:  ${evmPrivateKey}`);
console.log(`  Bitcoin WIF:      ${wif}`);
console.log(`  Public Key:       ${pubKeyBuffer.toString('hex')}`);
console.log(`  Pubkey Hash:     ${pubkeyHash.toString('hex')}`);
console.log(`  P2WPKH (Bech32):  ${bech32Address}`);
console.log(`  P2PKH (Legacy):   ${p2pkhAddress}`);
console.log('═══════════════════════════════════════════════════════════');

export { bech32Address as p2wpkhAddress, p2pkhAddress, wif, privateKeyBuffer, pubKeyBuffer, pubkeyHash };
