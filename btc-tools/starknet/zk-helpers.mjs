// Helper module: reusable functions for v3 invokes via raw JSON-RPC
import { ec, hash, CallData, RpcProvider, Account } from 'starknet';

export const RPC = 'https://starknet-sepolia.g.alchemy.com/starknet/version/rpc/v0_10/alch_REDACTED_API_KEY';
export const NEW_ADDR = '0x06d58c2aa17312d090c27ac52b9f9e4a5d267675afee9dedf424b61655cc1854';
export const NEW_PRIV = '0x_REDACTED_NEW_PRIV';
export const ZK_CLASS_HASH = '0x05613dd22cb2c57584477da06fec45af657a82b487d1f475526d3eaf9b62b2c0';
export const FRI = '0x04718f5a0fc34cc1af16a1cdee98ffb20c31f5cd61d6ab07201858f4287c938d';

// Resource bounds constants (must match between hash and JSON-RPC)
// Use small bounds — fits in ~45 STRK balance
// Max potential fee: 10M*5e10 + 200*4e16 + 1000*2.77e16 = 5e17 + 8e18 + 2.77e19 = ~3.7e19 wei = ~37 STRK max
export const L2_MAX_AMOUNT = 0x989680n;     // 10,000,000
export const L2_MAX_PRICE = 0xba43b7400n;   // 50,000,000,000
export const L1_MAX_AMOUNT = 0xc8n;         // 200 (small — L1_gas is rarely used)
export const L1_MAX_PRICE = 0x8d79883d20000n; // market price
export const L1D_MAX_AMOUNT = 0x3e8n;       // 1000 (L1_data_gas actual use is ~128-256)
export const L1D_MAX_PRICE = 0x62448724953354n; // market price

export async function rpc(method, params) {
  const r = await fetch(RPC, { method:'POST', headers:{'Content-Type':'application/json'},
    body: JSON.stringify({jsonrpc:'2.0',id:1,method, params}) });
  return await r.json();
}

// Local nonce counter (initialized lazily, incremented after each successful submit)
let _localNonce = null;

export async function getNonce(addr) {
  if (_localNonce !== null) return _localNonce;
  const r = await rpc('starknet_getNonce', ['latest', addr]);
  _localNonce = BigInt(r.result);
  return _localNonce;
}

function incrementNonce() {
  if (_localNonce !== null) _localNonce += 1n;
}

export async function getChainId() {
  const r = await rpc('starknet_chainId', []);
  return BigInt(r.result);
}

// Submit v3 invoke from NEW_ADDR. calls = [{contractAddress, entrypoint, calldata: [...]}]
export async function submitV3Invoke(calls, expectedRevert = false) {
  const provider = new RpcProvider({ nodeUrl: RPC });
  const account = new Account({ provider, address: NEW_ADDR, signer: NEW_PRIV });
  const chainId = await getChainId();
  const nonce = await getNonce(NEW_ADDR);

  const orderCalls = calls.map(c => ({
    contractAddress: c.contractAddress,
    entrypoint: c.entrypoint,
    calldata: CallData.compile(c.calldata || []),
  }));
  const compiledCalldata = CallData.compile({ orderCalls });

  const resourceBounds = {
    l2_gas: { max_amount: L2_MAX_AMOUNT, max_price_per_unit: L2_MAX_PRICE },
    l1_gas: { max_amount: L1_MAX_AMOUNT, max_price_per_unit: L1_MAX_PRICE },
    l1_data_gas: { max_amount: L1D_MAX_AMOUNT, max_price_per_unit: L1D_MAX_PRICE },
  };

  const details = {
    version: '0x3',
    walletAddress: NEW_ADDR,
    nonce,
    maxFee: 0n,
    chainId,
    cairoVersion: '1',
    resourceBounds,
    tip: 0n,
    paymasterData: [],
    accountDeploymentData: [],
    nonceDataAvailabilityMode: 'L1',
    feeDataAvailabilityMode: 'L1',
    proofFacts: undefined,
  };
  const sig = await account.signer.signTransaction(calls, details);

  const invokeReq = {
    type: 'INVOKE',
    sender_address: NEW_ADDR,
    calldata: compiledCalldata.map(c => '0x' + BigInt(c).toString(16)),
    version: '0x3',
    signature: ['0x' + sig.r.toString(16), '0x' + sig.s.toString(16)],
    nonce: '0x' + nonce.toString(16),
    resource_bounds: {
      l2_gas: { max_amount: '0x' + L2_MAX_AMOUNT.toString(16), max_price_per_unit: '0x' + L2_MAX_PRICE.toString(16) },
      l1_gas: { max_amount: '0x' + L1_MAX_AMOUNT.toString(16), max_price_per_unit: '0x' + L1_MAX_PRICE.toString(16) },
      l1_data_gas: { max_amount: '0x' + L1D_MAX_AMOUNT.toString(16), max_price_per_unit: '0x' + L1D_MAX_PRICE.toString(16) },
    },
    tip: '0x0',
    paymaster_data: [],
    nonce_data_availability_mode: 'L1',
    fee_data_availability_mode: 'L1',
    account_deployment_data: [],
  };

  const r = await rpc('starknet_addInvokeTransaction', [invokeReq]);
  if (r.error) {
    return { success: false, error: r.error, txHash: null, status: null };
  }
  const txHash = r.result.transaction_hash;
  // Increment local nonce immediately after submit (the sequencer has accepted it)
  incrementNonce();
  // Wait for receipt (shorter timeout — 30 attempts × 2s = 60s max)
  let receipt = null;
  for (let i = 0; i < 30; i++) {
    try {
      const rcpt = await rpc('starknet_getTransactionReceipt', [txHash]);
      if (rcpt.result) { receipt = rcpt.result; break; }
    } catch (e) {}
    await new Promise(r => setTimeout(r, 2000));
  }
  if (!receipt) {
    // Even if receipt times out, the tx was submitted. Return as "submitted but not confirmed"
    return { success: false, error: 'receipt_timeout', txHash, status: 'PENDING' };
  }
  const succeeded = receipt.execution_status === 'SUCCEEDED';
  return {
    success: succeeded,
    expectedRevert,
    txHash,
    status: receipt.execution_status,
    actual_fee: receipt.actual_fee,
    revert_reason: receipt.revert_reason || null,
    events: receipt.events || [],
  };
}

export async function callView(contract, selector, calldata = []) {
  const r = await rpc('starknet_call', [{
    contract_address: contract,
    entry_point_selector: typeof selector === 'string' ? hash.getSelectorFromName(selector) : selector,
    calldata,
  }, 'latest']);
  return r.result || r.error;
}
