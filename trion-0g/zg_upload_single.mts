
import { ZgFile, Indexer } from '@0glabs/0g-ts-sdk';
import { ethers } from 'ethers';

const privateKey = process.env.ZG_UPLOAD_PRIVATE_KEY;
if (!privateKey) { console.error('CONFIG_ERR: ZG_UPLOAD_PRIVATE_KEY not set'); process.exit(1); }

// File path from CLI arg or env var — no hardcoded paths
const filePath = process.argv[2] || process.env.ZG_UPLOAD_FILE;
if (!filePath) {
  console.error('USAGE: ZG_UPLOAD_PRIVATE_KEY=<key> npx tsx zg_upload_single.mts <path-to-file>');
  console.error('   or: ZG_UPLOAD_FILE=<path> ZG_UPLOAD_PRIVATE_KEY=<key> npx tsx zg_upload_single.mts');
  process.exit(1);
}

const file     = await ZgFile.fromFilePath(filePath);
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
