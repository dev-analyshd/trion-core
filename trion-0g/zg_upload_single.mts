
import { ZgFile, Indexer } from '@0glabs/0g-ts-sdk';
import { ethers } from 'ethers';

const privateKey = process.env.ZG_UPLOAD_PRIVATE_KEY;
if (!privateKey) { console.error('CONFIG_ERR: ZG_UPLOAD_PRIVATE_KEY not set'); process.exit(1); }

// Accept an explicit path via CLI arg or env var; fall back to the latest snapshot in the exports dir.
import { readdirSync, statSync } from 'fs';
import { join } from 'path';

function latestSnapshot(dir: string): string {
  let files: string[];
  try { files = readdirSync(dir).filter(f => f.endsWith('.json')); }
  catch { throw new Error(`CONFIG_ERR: snapshot dir not found: ${dir}`); }
  if (!files.length) throw new Error(`CONFIG_ERR: no JSON snapshots in ${dir}`);
  files.sort((a, b) => statSync(join(dir, b)).mtimeMs - statSync(join(dir, a)).mtimeMs);
  return join(dir, files[0]);
}

const snapshotDir  = process.env.ZG_SNAPSHOT_DIR  || '/home/runner/workspace/0g-state/exports';
const snapshotPath = process.env.ZG_SNAPSHOT_FILE  || process.argv[2] || latestSnapshot(snapshotDir);
const file         = await ZgFile.fromFilePath(snapshotPath);
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
