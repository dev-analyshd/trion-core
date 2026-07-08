
import { ZgFile, Indexer } from '@0glabs/0g-ts-sdk';
import { ethers } from 'ethers';

const filePath = process.env.ZG_UPLOAD_FILE || process.argv[2];
if (!filePath) {
  console.error('ERROR: provide a file path via ZG_UPLOAD_FILE env or first CLI argument');
  process.exit(1);
}

const rawKey = process.env.DEPLOY_0G_PRIVATE || process.env.ZG_PRIVATE_KEY;
if (!rawKey) {
  console.error('ERROR: set DEPLOY_0G_PRIVATE or ZG_PRIVATE_KEY to upload to 0G Storage');
  process.exit(1);
}

const file     = await ZgFile.fromFilePath(filePath);
const [tree, e1] = await file.merkleTree();
if (e1) { console.error('TREE_ERR:' + e1); process.exit(1); }

const rootHash = tree.rootHash();
const provider = new ethers.JsonRpcProvider('https://evmrpc.0g.ai');
const signer   = new ethers.Wallet(rawKey, provider);
const indexer  = new Indexer('https://indexer-storage.0g.ai');

const [tx, e2] = await indexer.upload(file, 'https://evmrpc.0g.ai', signer);
if (e2) { console.error('UPLOAD_ERR:' + e2); process.exit(1); }
await file.close();

console.log('ROOT:' + rootHash);
console.log('TX:' + (tx?.txHash || tx?.txHashes?.[0] || ''));
