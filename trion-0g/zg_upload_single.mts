
import { ZgFile, Indexer } from '@0glabs/0g-ts-sdk';
import { ethers } from 'ethers';

const privateKey = process.env.ZG_UPLOAD_PRIVATE_KEY;
if (!privateKey) { console.error('CONFIG_ERR: ZG_UPLOAD_PRIVATE_KEY not set'); process.exit(1); }

const file     = await ZgFile.fromFilePath('/home/runner/workspace/0g-state/exports/kv_snapshot_1783619141.json');
const [tree, e1] = await file.merkleTree();
if (e1) { console.error('TREE_ERR:' + e1); process.exit(1); }

const rootHash = tree.rootHash();
const provider = new ethers.JsonRpcProvider('https://evmrpc.0g.ai');
const signer   = new ethers.Wallet(privateKey, provider);
const indexer  = new Indexer('https://indexer-storage.0g.ai');

const [tx, e2] = await indexer.upload(file, 'https://evmrpc.0g.ai', signer);
if (e2) { console.error('UPLOAD_ERR:' + e2); process.exit(1); }
await file.close();

console.log('ROOT:' + rootHash);
console.log('TX:' + (tx?.txHash || tx?.txHashes?.[0] || ''));
