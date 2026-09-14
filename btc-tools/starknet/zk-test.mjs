const RPC = 'https://starknet-sepolia.g.alchemy.com/starknet/version/rpc/v0_10/alch_REDACTED_API_KEY';
const OLD_ADDR = '0x007cbe751a23f667b61643d89ef4217a7a3ae74df6c36406a1cd9867761b7f82';
const ETH = '0x049d36570d4e46f48e99674bd3fcc84644ddd6b96f7c741b1562b82f9e004dc7';
const STRK = '0x04718f5a0fc34cc1af16a1cdee98ffb20c31f5cd61d6ab0720188d6c1a4b6f';
const ZK = '0x0222c170d97af28d9cb964e81b9394be3bf9a4e1d96a85df1084a7667ef40029';

async function call(c, ep, calldata) {
  const r = await fetch(RPC, { method:'POST', headers:{'Content-Type':'application/json'},
    body: JSON.stringify({jsonrpc:'2.0',id:1,method:'starknet_call',
      params:[{contract_address:c, entry_point_selector: ep, calldata}, 'pending']}) });
  const j = await r.json();
  if (j.error) return {error: j.error};
  return j.result;
}

// balanceOf selector: starknet_keccak("balanceOf") mod Stark prime
import { hash } from 'starknet';
const balSel = hash.getSelectorFromName('balanceOf');
console.log('balanceOf selector:', balSel);

const ethBal = await call(ETH, balSel, [OLD_ADDR]);
console.log('ETH balance:', ethBal);
const strkBal = await call(STRK, balSel, [OLD_ADDR]);
console.log('STRK balance:', strkBal);

// Check ZK verifier class hash
const ch = await (async () => {
  const r = await fetch(RPC, { method:'POST', headers:{'Content-Type':'application/json'},
    body: JSON.stringify({jsonrpc:'2.0',id:1,method:'starknet_getClassHashAt',
      params:['pending', ZK]}) });
  return (await r.json()).result;
})();
console.log('ZKVerifier class hash:', ch);

// Try calling is_awa_frozen
const isFrozenSel = hash.getSelectorFromName('is_awa_frozen');
const fr = await call(ZK, isFrozenSel, []);
console.log('is_awa_frozen():', fr);
