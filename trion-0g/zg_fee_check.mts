import { ZgFile, getFlowContract } from '@0glabs/0g-ts-sdk';
import { ethers } from 'ethers';
import * as fs from 'fs';
import * as os from 'os';
import * as path from 'path';

const RPC = 'https://evmrpc-testnet.0g.ai';
const KEY = process.env.ZG_PRIVATE_KEY!;

const provider = new ethers.JsonRpcProvider(RPC);
const signer   = new ethers.Wallet(KEY, provider);

const bal = await provider.getBalance(signer.address);
console.log('Balance:', ethers.formatEther(bal), 'OG (', bal.toString(), 'wei)');

// Try the storage node status to get flow address
const resp = await fetch('http://34.19.125.196:5678', {
  method: 'POST',
  headers: { 'Content-Type': 'application/json' },
  body: JSON.stringify({ jsonrpc: '2.0', method: 'zgs_getStatus', id: 1 })
});
const status = await resp.json() as any;
console.log('Storage node status keys:', Object.keys(status?.result || {}));
const flowAddr = status?.result?.networkIdentity?.flowAddress;
console.log('Flow contract:', flowAddr);

if (!flowAddr) { console.log('No flow address'); process.exit(1); }

// Check flow contract pricePerSector
const flowAbi = [
  { name: 'pricePerSector', type: 'function', inputs: [], outputs: [{ name: '', type: 'uint256' }], stateMutability: 'view' },
  { name: 'numEntries', type: 'function', inputs: [], outputs: [{ name: '', type: 'uint256' }], stateMutability: 'view' },
];
const flow = new ethers.Contract(flowAddr, flowAbi, provider);
try {
  const price = await flow.pricePerSector();
  const num   = await flow.numEntries();
  console.log('pricePerSector:', price.toString(), '=', ethers.formatEther(price), 'OG');
  console.log('numEntries:', num.toString());
  
  // 1.36MB file → ceil(1.36MB / 256KB) = 6 sectors
  const sectors = 6n;
  const fee = price * sectors;
  console.log('Fee for 6 sectors:', ethers.formatEther(fee), 'OG');
  console.log('Can afford upload:', bal >= fee);
} catch(e) {
  console.log('Flow contract call error:', e.message);
}
