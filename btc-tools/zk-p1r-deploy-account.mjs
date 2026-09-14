// Deploy new v3-compatible account via deployAccount v3
import { ec, hash, CallData, RpcProvider, Account } from 'starknet';

const RPC = 'https://starknet-sepolia.g.alchemy.com/starknet/version/rpc/v0_10/alch_REDACTED_API_KEY';
const NEW_ADDR = '0x06d58c2aa17312d090c27ac52b9f9e4a5d267675afee9dedf424b61655cc1854';
const NEW_PRIV = '0x_REDACTED_NEW_PRIV';
// v3-compatible account class hash (the one widely used on Sepolia)
const V3_CLASS_HASH = '0xd632f69c8e02ea43f1d8a7c3eb441c67eb935f460c02e3860f7c410115d10f';

const provider = new RpcProvider({ nodeUrl: RPC });
const account = new Account({ provider, address: NEW_ADDR, signer: NEW_PRIV });

async function rpc(method, params) {
  const r = await fetch(RPC, { method:'POST', headers:{'Content-Type':'application/json'},
    body: JSON.stringify({jsonrpc:'2.0',id:1,method, params}) });
  return await r.json();
}

const chainId = BigInt((await rpc('starknet_chainId', [])).result);
console.log('chain:', '0x' + chainId.toString(16));
console.log('Deploying to:', NEW_ADDR);

// Get the v3 class hash's ABI to find constructor signature
const cls = await rpc('starknet_getClassAt', ['latest', '0x15569a4dae53e13da0b0f9332d88539c96db79858b14fb15e571a9f46b6c1be']);
if (!cls.result?.abi) {
  console.log('Class hash not found or no ABI');
  process.exit(1);
}
const abi = JSON.parse(cls.result.abi);
const ctor = abi.find(e => e.type === 'constructor');
console.log('Constructor:', JSON.stringify(ctor));

// Pubkey from priv key
const fullPub = ec.starkCurve.getPublicKey(NEW_PRIV);
const pubXFelt = '0x' + Buffer.from(fullPub.slice(1,33)).toString('hex');
console.log('pubkey:', pubXFelt);

// Constructor calldata
const constructorCalldata = CallData.compile([pubXFelt]);
console.log('compiled constructor calldata:', constructorCalldata);

// Resource bounds for deployAccount (small bounds to fit in 50 STRK balance)
// Use the EXACT same values in both hash computation and JSON-RPC to avoid mismatch
const L2_MAX_AMOUNT = 0x4c4b40n; // 5,000,000
const L2_MAX_PRICE = 0xba43b7400n; // 50,000,000,000
const L1_MAX_AMOUNT = 0x64n; // 100
const L1_MAX_PRICE = 0x8d79883d20000n; // 40,114,397,261,824,000 (market price)
const L1D_MAX_AMOUNT = 0x400n; // 1024 (deployAccount needs ~256 L1_data_gas)
const L1D_MAX_PRICE = 0x6b19e4f9a6c000n; // 30,032,754,953,121,792 (market price)

const resourceBounds = {
  l2_gas: { max_amount: L2_MAX_AMOUNT, max_price_per_unit: L2_MAX_PRICE },
  l1_gas: { max_amount: L1_MAX_AMOUNT, max_price_per_unit: L1_MAX_PRICE },
  l1_data_gas: { max_amount: L1D_MAX_AMOUNT, max_price_per_unit: L1D_MAX_PRICE },
};

// Use starknet.js's account.signer.signDeployAccountTransaction to compute the sig
const details = {
  version: '0x3',
  classHash: V3_CLASS_HASH,
  addressSalt: pubXFelt, // salt = pubkey (matches our derivation)
  constructorCalldata,
  contractAddress: NEW_ADDR,
  nonce: 0n,
  maxFee: 0n,
  chainId,
  resourceBounds,
  tip: 0n,
  paymasterData: [],
  nonceDataAvailabilityMode: 'L1',
  feeDataAvailabilityMode: 'L1',
  cairoVersion: '1',
};

let sig;
try {
  sig = await account.signer.signDeployAccountTransaction(details);
  console.log('sig r:', '0x' + sig.r.toString(16));
  console.log('sig s:', '0x' + sig.s.toString(16));
} catch (e) {
  console.log('sig err:', String(e.message).slice(0, 500));
  process.exit(1);
}

// Submit deployAccount v3 via raw JSON-RPC
console.log('\n=== Submit deployAccount v3 ===');
const deployReq = {
  type: 'DEPLOY_ACCOUNT',
  class_hash: V3_CLASS_HASH,
  contract_address_salt: pubXFelt,
  constructor_calldata: constructorCalldata.map(c => '0x' + BigInt(c).toString(16)),
  version: '0x3',
  signature: ['0x' + sig.r.toString(16), '0x' + sig.s.toString(16)],
  nonce: '0x0',
  resource_bounds: {
    l2_gas: { max_amount: '0x' + L2_MAX_AMOUNT.toString(16), max_price_per_unit: '0x' + L2_MAX_PRICE.toString(16) },
    l1_gas: { max_amount: '0x' + L1_MAX_AMOUNT.toString(16), max_price_per_unit: '0x' + L1_MAX_PRICE.toString(16) },
    l1_data_gas: { max_amount: '0x' + L1D_MAX_AMOUNT.toString(16), max_price_per_unit: '0x' + L1D_MAX_PRICE.toString(16) },
  },
  tip: '0x0',
  paymaster_data: [],
  nonce_data_availability_mode: 'L1',
  fee_data_availability_mode: 'L1',
};
const r = await rpc('starknet_addDeployAccountTransaction', [deployReq]);
console.log('Result:', JSON.stringify(r).slice(0, 600));

if (r.result?.transaction_hash) {
  console.log('\n✓ deployAccount v3 tx submitted:', r.result.transaction_hash);
  console.log('  contract_address:', r.result.contract_address);
  for (let i = 0; i < 60; i++) {
    const rcpt = await rpc('starknet_getTransactionReceipt', [r.result.transaction_hash]);
    if (rcpt.result) {
      console.log('Receipt:');
      console.log('  status:', rcpt.result.execution_status);
      console.log('  actual_fee:', rcpt.result.actual_fee);
      if (rcpt.result.execution_status !== 'SUCCEEDED') {
        console.log('  revert_reason:', (rcpt.result.revert_reason || '').slice(0, 600));
      } else {
        console.log('  ✓ Account deployed!');
        // Verify by getting class hash at the new address
        const ch = await rpc('starknet_getClassHashAt', ['latest', NEW_ADDR]);
        console.log('  class hash:', ch.result);
        // Check balance
        const balSel = hash.getSelectorFromName('balanceOf');
        const FRI = '0x04718f5a0fc34cc1af16a1cdee98ffb20c31f5cd61d6ab07201858f4287c938d';
        const balR = await rpc('starknet_call', [{contract_address: FRI, entry_point_selector: balSel, calldata: [NEW_ADDR]}, 'latest']);
        if (balR.result) {
          const bal = BigInt(balR.result[0]) + (BigInt(balR.result[1]) << 128n);
          console.log('  STRK balance:', (Number(bal) / 1e18).toFixed(6));
        }
      }
      break;
    }
    await new Promise(r => setTimeout(r, 2000));
  }
} else if (r.error) {
  console.log('deployAccount failed:', r.error.message);
  console.log('  data:', JSON.stringify(r.error.data).slice(0, 500));
}
