const RPC = 'https://starknet-sepolia.g.alchemy.com/starknet/version/rpc/v0_10/alch_REDACTED_API_KEY';
async function rpc(method, params) {
  const r = await fetch(RPC, { method:'POST', headers:{'Content-Type':'application/json'},
    body: JSON.stringify({jsonrpc:'2.0',id:1,method, params}) });
  return await r.json();
}

// Pad to 64 hex digits
function pad(h) {
  if (typeof h !== 'string') h = '0x' + BigInt(h).toString(16);
  if (!h.startsWith('0x')) h = '0x' + h;
  return '0x' + h.replace('0x', '').padStart(64, '0');
}

// Two v3-compatible classes found
const classes = [
  '0x0d632f69c8e02ea43f1d8a7c3eb441c67eb935f460c02e3860f7c410115d10f',
  '0x5b4b537eaa2399e3aa99c4e2e0208ebd6c71bc1467938cd52c798c601e43564',
];

import { hash, CallData } from 'starknet';
const NEW_ADDR = BigInt('0x0417678126db3e4eb21ca3c4dfd1b1920eb5fd2fd1e2136cbd215905be4a434d');
const NEW_PRIV = '0x_REDACTED_NEW_PRIV';
const OLD_ADDR = '0x007cbe751a23f667b61643d89ef4217a7a3ae74df6c36406a1cd9867761b7f82';

// Get NEW priv pubkey
const fullPub = (await import('starknet')).ec.starkCurve.getPublicKey(NEW_PRIV);
const pubXFelt = '0x' + Buffer.from(fullPub.slice(1,33)).toString('hex');
console.log('NEW priv → pubkey:', pubXFelt);
console.log('NEW target addr:', '0x' + NEW_ADDR.toString(16).padStart(64, '0'));

for (const chRaw of classes) {
  const ch = pad(chRaw);
  console.log('\n=== Class:', ch, '===');
  const r = await rpc('starknet_getClass', [ch]);
  if (r.error) { console.log('  err:', r.error.message); continue; }
  if (!r.result?.abi) { console.log('  no abi'); continue; }
  const abi = JSON.parse(r.result.abi);
  console.log('  version:', r.result.contract_class_version, ' abi entries:', abi.length);

  // Print function names
  const allNames = [];
  function walk(items, prefix='') {
    if (!Array.isArray(items)) return;
    for (const e of items) {
      if (e.type === 'function') {
        allNames.push(prefix + e.name + '/' + (e.inputs||[]).length);
      }
      if (e.items) walk(e.items, prefix + (e.name||'') + '::');
    }
  }
  walk(abi);
  const v3Fns = allNames.filter(f => f.includes('v3') || f.includes('V3') || f.includes('__validate'));
  console.log('  v3/validate fns:', v3Fns.slice(0,10).join(', '));
  console.log('  constructor inputs:', abi.find(e => e.type === 'constructor')?.inputs?.map(i => i.name+':'+i.type).join(', '));

  // Brute force salt for the user's address
  console.log('  Trying to derive NEW address...');
  const saltCandidates = [pubXFelt, '0x0', '0x1', OLD_ADDR, '0x' + BigInt(pubXFelt).toString(16).padStart(64, '0')];
  let found = null;
  for (const s of saltCandidates) {
    for (const d of ['0x0', OLD_ADDR]) {
      try {
        const a = hash.calculateContractAddressFromHash(
          BigInt(s), ch, [pubXFelt], d === '0x0' ? 0n : BigInt(d)
        );
        if (BigInt(a) === NEW_ADDR) {
          console.log(`  ✓✓✓ MATCH: salt=${s}, deployer=${d}`);
          found = { salt: s, deployer: d };
        }
      } catch (e) {}
    }
  }
  if (!found) console.log('  no match with simple salts');

  // Also try with constructor(public_key, owner) — 2 args
  if (!found) {
    for (const s of saltCandidates) {
      for (const d of ['0x0', OLD_ADDR]) {
        try {
          const a = hash.calculateContractAddressFromHash(
            BigInt(s), ch, [pubXFelt, pubXFelt], d === '0x0' ? 0n : BigInt(d)
          );
          if (BigInt(a) === NEW_ADDR) {
            console.log(`  ✓✓✓ MATCH (2 args): salt=${s}, deployer=${d}`);
            found = { salt: s, deployer: d, args: 2 };
          }
        } catch (e) {}
      }
    }
  }
}
