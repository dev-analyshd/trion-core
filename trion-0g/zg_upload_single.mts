
import { ZgFile, Indexer } from '@0glabs/0g-ts-sdk';
import { ethers } from 'ethers';
import { existsSync } from 'node:fs';
import { resolve } from 'node:path';

const privateKey = process.env.ZG_UPLOAD_PRIVATE_KEY;
if (!privateKey) { console.error('CONFIG_ERR: ZG_UPLOAD_PRIVATE_KEY not set'); process.exit(1); }

// Accept snapshot path from: CLI arg > ZG_SNAPSHOT_PATH env var
const snapshotArg = process.argv[2] ?? process.env.ZG_SNAPSHOT_PATH;
if (!snapshotArg) {
  console.error('CONFIG_ERR: Provide snapshot path as first CLI argument or set ZG_SNAPSHOT_PATH');
  console.error('  Usage: tsx zg_upload_single.mts <path-to-snapshot.json>');
  process.exit(1);
}
const snapshotPath = resolve(snapshotArg);
if (!existsSync(snapshotPath)) {
  console.error(`CONFIG_ERR: Snapshot file not found: ${snapshotPath}`);
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
