// P1 — Verify new v3-compatible wallet and unfreeze AWA via set_awa_state(false)
// Uses STRK as gas fee (v3 invoke) on the new funded account
import { RpcProvider, Account, Contract, stark, ec, hash, cairo, CallData } from 'starknet';

const RPC = 'https://starknet-sepolia.g.alchemy.com/starknet/version/rpc/v0_10/alch_REDACTED_API_KEY';
const NEW_ADDR = '0x0417678126db3e4eb21ca3c4dfd1b1920eb5fd2fd1e2136cbd215905be4a434d';
const NEW_PRIV = '0x_REDACTED_NEW_PRIV';
const ZK_VERIFIER = '0x0222c170d97af28d9cb964e81b9394be3bf9a4e1d96a85df1084a7667ef40029';

const provider = new RpcProvider({ nodeUrl: RPC });
console.log('═══════════════════════════════════════════════════════════');
console.log('  P1 — VERIFY NEW V3 WALLET + UNFREEZE AWA');
console.log('═══════════════════════════════════════════════════════════\n');

// 1) Class hash at the new address (must be deployed)
let classHash = null;
try {
  classHash = await provider.getClassHashAt(NEW_ADDR);
  console.log('✓ Wallet deployed at', NEW_ADDR);
  console.log('  Class hash:', classHash);
} catch (e) {
  console.log('✗ Wallet NOT deployed:', String(e.message).slice(0, 200));
  console.log('  → must use deploy_account v3 first');
  process.exit(1);
}

// 2) Class ABI / version
try {
  const cls = await provider.getClass(classHash);
  console.log('  Contract class ABI entries:', (cls.abi || []).length);
  console.log('  Class version:', cls.version);
  // Look for v3 invoke entrypoint
  const hasV3 = (cls.abi || []).some(a =>
    a.type === 'interface' && (a.items || []).some(i =>
      i.name && i.name.includes('invoke') && (i.name.includes('v3') || i.name === '__execute__')
    )
  );
  console.log('  Has v3-style entrypoint:', hasV3 ? '✓' : '✗ (need to check)');
} catch (e) {
  console.log('  Class fetch err:', String(e.message).slice(0, 200));
}

// 3) ETH + STRK balance (use raw RPC for STRK)
async function getBalance(token, addr) {
  try {
    const r = await fetch(RPC, {
      method: 'POST',
      headers: {'Content-Type':'application/json'},
      body: JSON.stringify({ jsonrpc:'2.0', id:1, method:'starknet_call',
        params: [{ contract_address: token, entry_point_selector: '0x2e4263afad30923c891518314c3aae71e0f5b0170f6e21b84d97f4f0c4b3543', calldata: [addr] }, 'pending'] })
    });
    const j = await r.json();
    if (j.error) return null;
    return BigInt(j.result[0]);
  } catch (e) { return null; }
}
const ETH = '0x049d36570eeef7d7a8d3b8b2e6c3079efe6b7c2e93c0d5c4b0e7d9c2b20c4f';
const STRK = '0x04718f5a0fc34cc1af16a1cdee98ffb20c31f5cd61d6ab0720188d6c1a4b6f';
const ethBal = await getBalance(ETH, NEW_ADDR);
const strkBal = await getBalance(STRK, NEW_ADDR);
console.log('  ETH balance:', ethBal ? (Number(ethBal) / 1e18).toFixed(4) : 'n/a');
console.log('  STRK balance:', strkBal ? (Number(strkBal) / 1e18).toFixed(4) : 'n/a');

// 4) Account instance
const account = new Account({ provider, address: NEW_ADDR, signer: NEW_PRIV });

// 5) Get nonce for v3
const nonce = await provider.getNonceForAddress(NEW_ADDR, 'pending');
console.log('  Account nonce:', nonce.toString());

// 6) Read current AWA state from ZKVerifier
const { abi: zkAbi } = await provider.getClassAt(ZK_VERIFIER);
const zkContract = new Contract(zkAbi, ZK_VERIFIER, provider);

// Read functions
const reads = ['is_awa_frozen', 'awa_frozen', 'get_awa_state', 'owner', 'total_proofs', 'proof_count'];
for (const fn of reads) {
  if (!zkContract[fn]) continue;
  try {
    const v = await zkContract[fn]();
    console.log(`  ${fn}():`, JSON.stringify(v).slice(0, 120));
  } catch (e) {
    console.log(`  ${fn}(): err`, String(e.message).slice(0, 120));
  }
}

// List all entrypoints in the ZKVerifier
console.log('\n  ZKVerifier entrypoints:');
const fns = (zkAbi || []).filter(a => a.type === 'interface').flatMap(i => (i.items || [])).filter(i => i.type === 'function').map(f => f.name);
console.log(' ', fns.join(', '));

// 7) Try set_awa_state(false) using v3 invoke with STRK gas
console.log('\n── Attempting set_awa_state(false) via v3 invoke (STRK gas) ──');
const candidates = ['set_awa_state', 'set_awa_frozen', 'set_awafrozen', 'unfreeze_awa'];
let usedFn = null;
for (const fn of candidates) {
  if (zkContract[fn]) { usedFn = fn; break; }
}
if (!usedFn) {
  console.log('  No set_awa_* function found. Inspecting all write fns...');
  const writes = (zkAbi || []).filter(a => a.type === 'interface').flatMap(i => (i.items || [])).filter(i => i.type === 'function' && (i.inputs || []).length > 0).map(f => f.name + '/' + f.inputs.length);
  console.log(' ', writes.join(', '));
} else {
  console.log('  Using:', usedFn);
  try {
    const call = zkContract.populate(usedFn, [false]);
    const { suggestedMaxFee: fee } = await account.estimateInvokeFee(call, { version: 3 });
    console.log('  Estimated fee (STRK):', fee.toString());
    const { transaction_hash } = await account.execute(call, { version: 3, maxFee: (fee * 3n) });
    console.log('  ✓ Tx submitted:', transaction_hash);
    console.log('  Waiting for receipt...');
    const receipt = await provider.waitForTransaction(transaction_hash);
    console.log('  Status:', receipt.execution_status);
    if (receipt.execution_status === 'SUCCEEDED') {
      console.log('  ✓ AWA UNFROZEN');
    } else {
      console.log('  Revert reason:', JSON.stringify(receipt.revert_reason || '').slice(0, 300));
    }
  } catch (e) {
    console.log('  ✗ v3 invoke failed:', String(e.message).slice(0, 400));
  }
}

// 8) Re-read AWA state
try {
  const v = await zkContract.is_awa_frozen();
  console.log('  is_awa_frozen() after:', JSON.stringify(v));
} catch (e) {
  console.log('  is_awa_frozen() after err:', String(e.message).slice(0, 200));
}

console.log('\n═══════════════════════════════════════════════════════════');
console.log('  P1 VERIFICATION COMPLETE');
console.log('═══════════════════════════════════════════════════════════');
