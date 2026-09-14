// Try v1 invoke (ETH gas) via Alchemy RPC — old deployer wallet has 7960 ETH
import { RpcProvider, Account, Contract, CallData, constants } from 'starknet';

const RPC = 'https://starknet-sepolia.g.alchemy.com/starknet/version/rpc/v0_10/alch_REDACTED_API_KEY';
const OLD_ADDR = '0x007cbe751a23f667b61643d89ef4217a7a3ae74df6c36406a1cd9867761b7f82';
const OLD_PRIV = process.env.STARKNET_PRIVATE_KEY || '0x0'; // from env
const ZK_VERIFIER = '0x0222c170d97af28d9cb964e81b9394be3bf9a4e1d96a85df1084a7667ef40029';

if (OLD_PRIV === '0x0') {
  console.log('STARKNET_PRIVATE_KEY env var not set');
  process.exit(1);
}

const provider = new RpcProvider({ nodeUrl: RPC });
console.log('═══════════════════════════════════════════════════════════');
console.log('  P1 — TRY v1 INVOKE VIA ALCHEMY (ETH GAS, OLD DEPLOYER)');
console.log('═══════════════════════════════════════════════════════════\n');

// Verify the OLD account is still deployed + get its STRK balance
async function getBalance(token, addr) {
  const r = await fetch(RPC, { method: 'POST', headers: {'Content-Type':'application/json'},
    body: JSON.stringify({ jsonrpc:'2.0', id:1, method:'starknet_call',
      params: [{ contract_address: token, entry_point_selector: '0x2e4263afad30923c891518314c3aae71e0f5b0170f6e21b84d97f4f0c4b3543', calldata: [addr] }, 'pending'] }) });
  const j = await r.json(); if (j.error) return null; return BigInt(j.result[0]);
}
const ETH = '0x049d36570d4e46f48e99674bd3fcc84644ddd6b96f7c741b1562b82f9e004dc7';
const STRK = '0x04718f5a0fc34cc1af16a1cdee98ffb20c31f5cd61d6ab0720188d6c1a4b6f';
const ethBal = await getBalance(ETH, OLD_ADDR);
const strkBal = await getBalance(STRK, OLD_ADDR);
console.log('Old deployer ETH balance:', ethBal ? (Number(ethBal) / 1e18).toFixed(2) : 'n/a');
console.log('Old deployer STRK balance:', strkBal ? (Number(strkBal) / 1e18).toFixed(4) : 'n/a');

// Account instance
const account = new Account({ provider, address: OLD_ADDR, signer: OLD_PRIV });

// Load ZKVerifier ABI
const { abi: zkAbi } = await provider.getClassAt(ZK_VERIFIER);
const zkContract = new Contract(zkAbi, ZK_VERIFIER, provider);
const zkContractWithAcct = new Contract(zkAbi, ZK_VERIFIER, account);

// Inspect ZKVerifier functions
console.log('\n── ZKVerifier functions ──');
const fns = (zkAbi || []).filter(a => a.type === 'interface').flatMap(i => (i.items || [])).filter(i => i.type === 'function');
console.log('Functions:', fns.map(f => `${f.name}/${(f.inputs||[]).length}`).join(', '));

// Read current AWA state
for (const fn of ['is_awa_frozen', 'awa_frozen', 'get_awa_state', 'owner', 'total_proofs']) {
  if (!zkContract[fn]) continue;
  try {
    const v = await zkContract[fn]();
    console.log(`  ${fn}():`, JSON.stringify(v).slice(0, 100));
  } catch (e) { console.log(`  ${fn}() err:`, String(e.message).slice(0,100)); }
}

// Try set_awa_state(false) with v1 invoke (ETH gas)
console.log('\n── Try v1 invoke set_awa_state(false) ──');
const candidates = ['set_awa_state', 'set_awa_frozen', 'unfreeze_awa', 'set_awafrozen'];
let usedFn = null;
for (const fn of candidates) {
  if (zkContractWithAcct[fn]) { usedFn = fn; break; }
}
if (!usedFn) {
  console.log('  No set_awa_* function found');
  process.exit(1);
}
console.log('  Using:', usedFn);
try {
  const call = zkContractWithAcct.populate(usedFn, [false]);
  // Estimate fee with v1
  let fee;
  try {
    const est = await account.estimateInvokeFee(call, { version: 1 });
    fee = est.suggestedMaxFee;
    console.log('  v1 fee est (ETH):', fee.toString());
  } catch (e) {
    console.log('  v1 fee est err:', String(e.message).slice(0, 200));
    fee = 1000000000000000n; // fallback
  }
  // Submit v1 invoke
  const { transaction_hash } = await account.execute(call, { version: 1, maxFee: fee * 2n });
  console.log('  ✓ v1 tx submitted:', transaction_hash);
  const receipt = await provider.waitForTransaction(transaction_hash);
  console.log('  Status:', receipt.execution_status);
  if (receipt.execution_status !== 'SUCCEEDED') {
    console.log('  Revert reason:', JSON.stringify(receipt.revert_reason || '').slice(0, 500));
  }
} catch (e) {
  console.log('  ✗ v1 invoke err:', String(e.message).slice(0, 400));
}

// Also try with raw JSON-RPC to see if Alchemy accepts v1
console.log('\n── Try raw JSON-RPC v1 invoke (sanity check) ──');
try {
  const nonce = await provider.getNonceForAddress(OLD_ADDR, 'pending');
  console.log('  Nonce:', nonce.toString());
} catch (e) {
  console.log('  Nonce err:', String(e.message).slice(0, 200));
}

console.log('\n═══════════════════════════════════════════════════════════');
