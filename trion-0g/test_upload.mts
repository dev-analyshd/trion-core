import { ZgFile, Indexer } from '@0glabs/0g-ts-sdk';
import { ethers } from 'ethers';
import * as fs from 'fs';
import * as os from 'os';
import * as path from 'path';

// Create a tiny test file
const tmpFile = path.join(os.tmpdir(), 'trion_test_upload.bin');
fs.writeFileSync(tmpFile, Buffer.alloc(256 * 1024, 0xab)); // 256 KB

console.log('Test file:', tmpFile, fs.statSync(tmpFile).size, 'bytes');

const provider = new ethers.JsonRpcProvider('https://evmrpc-testnet.0g.ai');
const signer = new ethers.Wallet(process.env.ZG_PRIVATE_KEY!, provider);

const bal = await provider.getBalance(signer.address);
console.log('Balance:', ethers.formatEther(bal), 'OG');

const file = await ZgFile.fromFilePath(tmpFile);
const [tree, e1] = await file.merkleTree();
if (e1) { console.error('TREE_ERR:', e1); process.exit(1); }
console.log('Merkle root:', tree.rootHash());
console.log('File size:', file.size());

const indexer = new Indexer('https://indexer-storage-testnet-standard.0g.ai');
console.log('Uploading...');
const [tx, e2] = await indexer.upload(file, 'https://evmrpc-testnet.0g.ai', signer);
if (e2) { console.error('UPLOAD_ERR:', e2); process.exit(1); }
await file.close();
console.log('SUCCESS! tx:', JSON.stringify(tx));
