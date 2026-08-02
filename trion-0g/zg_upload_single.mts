
import { ZgFile, Indexer } from '@0glabs/0g-ts-sdk';
import { ethers } from 'ethers';

const privateKey = process.env.ZG_UPLOAD_PRIVATE_KEY;
if (!privateKey) { console.error('CONFIG_ERR: ZG_UPLOAD_PRIVATE_KEY not set'); process.exit(1); }

// Accept snapshot path from env var or first CLI argument
const snapshotPath = process.env.ZG_SNAPSHOT_PATH || process.argv[2];
if (!snapshotPath) {
  console.error('CONFIG_ERR: snapshot path required — set ZG_SNAPSHOT_PATH or pass as first argument');
  process.exit(1);
}

const file     = await ZgFile.fromFilePath(snapshotPath);
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
