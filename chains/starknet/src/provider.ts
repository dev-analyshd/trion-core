import { RpcProvider, Account, ec, hash, CallData } from 'starknet';
import { STARKNET_CONFIG } from './config.js';

// All known Starknet Sepolia account class hashes
const KNOWN_CLASS_HASHES: Record<string, { ch: string; buildCalldata: (pub: string) => string[]; salt: (pub: string) => string }> = {
  'Argent X V3': {
    ch: '0x036078334509b514626504edc9fb252328d1a240e4e948bef8d0c08dff45927f',
    buildCalldata: (pub) => CallData.compile({ owner: pub, guardian: '0x0' }),
    salt: (pub) => pub,
  },
  'Argent X V4': {
    ch: '0x029927c8af6bccf3f6fda035981e765a7bdbf18a2dc0d630494f8758aa908e2b',
    buildCalldata: (pub) => CallData.compile({ owner: pub, guardian: '0x0' }),
    salt: (pub) => pub,
  },
  'Argent X V3 (salt=0)': {
    ch: '0x036078334509b514626504edc9fb252328d1a240e4e948bef8d0c08dff45927f',
    buildCalldata: (pub) => CallData.compile({ owner: pub, guardian: '0x0' }),
    salt: () => '0x0',
  },
  'OpenZeppelin 0.6': {
    ch: '0x061dac032f228abef9c6626f995015233097ae253a7f72d68552db02f2971b8f',
    buildCalldata: (pub) => CallData.compile({ publicKey: pub }),
    salt: (pub) => pub,
  },
  'OpenZeppelin 0.7': {
    ch: '0x04ad3c1dc8413453db314497945b6903e1c766495a1e60492d44d33b5a1f3c0',
    buildCalldata: (pub) => CallData.compile({ publicKey: pub }),
    salt: (pub) => pub,
  },
  'OpenZeppelin 0.6 (salt=0)': {
    ch: '0x061dac032f228abef9c6626f995015233097ae253a7f72d68552db02f2971b8f',
    buildCalldata: (pub) => CallData.compile({ publicKey: pub }),
    salt: () => '0x0',
  },
};

export async function getWorkingProvider(): Promise<RpcProvider> {
  // Probe each endpoint with BOTH a chainId check AND a real getBlockWithTxs call.
  // Some providers (e.g. drpc.org) advertise the right chainId but return
  // -32601 "method does not exist" for starknet_getBlockWithTxs — that breaks
  // the indexer hot loop. We must reject those endpoints up-front.
  for (const url of STARKNET_CONFIG.rpcEndpoints) {
    try {
      const provider = new RpcProvider({ nodeUrl: url });
      const chainId = await provider.getChainId();
      if (chainId !== STARKNET_CONFIG.chainIdHex) continue;
      // Probe getBlockWithTxs against latest block — must succeed.
      const latest = await provider.getBlockNumber();
      await provider.getBlockWithTxs(latest);
      console.log(`✓ Connected to Starknet Sepolia via ${url}`);
      console.log(`  Chain ID: ${chainId} (SN_SEPOLIA), latest block: ${latest}`);
      return provider;
    } catch (e: any) {
      const msg = e?.message ?? String(e);
      console.log(`  · RPC ${url} rejected: ${msg.slice(0, 120)}`);
    }
  }
  throw new Error('All Starknet Sepolia RPC endpoints failed (none support getBlockWithTxs)');
}

// starknet.js v9 Account constructor requires an options object
export function getAccount(provider: RpcProvider): Account {
  const privateKey = process.env.STARKNET_PRIVATE_KEY;
  const address    = process.env.STARKNET_ACCOUNT_ADDRESS;

  if (!privateKey || !address) {
    throw new Error('Missing STARKNET_PRIVATE_KEY or STARKNET_ACCOUNT_ADDRESS');
  }

  return new Account({ provider, address, signer: privateKey } as any);
}

export async function printAccountInfo(account: Account, provider: RpcProvider): Promise<{ ethFloat: number; strkFloat: number; deployed: boolean }> {
  const ETH  = '0x049d36570d4e46f48e99674bd3fcc84644ddd6b96f7c741b1562b82f9e004dc7';
  const STRK = '0x04718f5a0fc34cc1af16a1cdee98ffb20c31f5cd61d6ab07201858f4287c938d';

  let ethFloat = 0, strkFloat = 0;
  try {
    const b = await provider.callContract({ contractAddress: ETH, entrypoint: 'balanceOf', calldata: [account.address] });
    ethFloat = Number(BigInt(b[0]) + BigInt(b[1]) * (2n ** 128n)) / 1e18;
  } catch {}
  try {
    const b = await provider.callContract({ contractAddress: STRK, entrypoint: 'balanceOf', calldata: [account.address] });
    strkFloat = Number(BigInt(b[0]) + BigInt(b[1]) * (2n ** 128n)) / 1e18;
  } catch {}

  let deployed = false;
  try { await account.getNonce(); deployed = true; } catch {}

  console.log(`\n  Address  : ${account.address}`);
  console.log(`  ETH Bal  : ${ethFloat.toFixed(6)} ETH`);
  console.log(`  STRK Bal : ${strkFloat.toFixed(2)} STRK`);
  console.log(`  Deployed : ${deployed}`);

  return { ethFloat, strkFloat, deployed };
}

export async function ensureAccountDeployed(account: Account, provider: RpcProvider): Promise<void> {
  console.log('\n── Account Deployment Check ──────────────────────────────');

  try {
    await account.getNonce();
    console.log('  ✓ Account already deployed on-chain');
    return;
  } catch {}

  const pk = process.env.STARKNET_PRIVATE_KEY!;
  const pubKey = ec.starkCurve.getStarkKey(pk);
  const targetBig = BigInt(account.address);

  console.log(`  Derived public key: ${pubKey}`);

  // Search all known class hashes for a match
  for (const [name, { ch, buildCalldata, salt }] of Object.entries(KNOWN_CLASS_HASHES)) {
    const cd   = buildCalldata(pubKey);
    const s    = salt(pubKey);
    const addr = hash.calculateContractAddressFromHash(s, ch, cd, 0);
    if (BigInt(addr) === targetBig) {
      console.log(`  ✓ Address matches: ${name}`);
      console.log('  Deploying account using STRK fees...');
      const { transaction_hash } = await account.deployAccount(
        { classHash: ch, constructorCalldata: cd, addressSalt: s },
      );
      console.log(`  Deploy tx: ${transaction_hash}`);
      console.log(`  Waiting for confirmation...`);
      await provider.waitForTransaction(transaction_hash);
      console.log('  ✓ Account deployed successfully!');
      return;
    }
  }

  // No match found — list what we computed for diagnostics
  console.warn('\n  ⚠ Private key does not derive to the target address.');
  console.warn('  This means the STARKNET_PRIVATE_KEY secret is still wrong.');
  console.warn('\n  Target address:', account.address);
  console.warn('  Derived pubkey:', pubKey);
  console.warn('\n  Computed addresses:');
  for (const [name, { ch, buildCalldata, salt }] of Object.entries(KNOWN_CLASS_HASHES)) {
    const cd   = buildCalldata(pubKey);
    const s    = salt(pubKey);
    const addr = hash.calculateContractAddressFromHash(s, ch, cd, 0);
    console.warn(`    ${name}: ${addr}`);
  }
  console.warn('\n  Please export the private key from the wallet that controls the target address.');
  throw new Error('Private key does not match the target Starknet address.');
}
