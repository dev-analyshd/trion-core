
import { ZgFile, Indexer } from '@0glabs/0g-ts-sdk';
import { ethers } from 'ethers';

const privateKey = process.env.ZG_UPLOAD_PRIVATE_KEY;
if (!privateKey) { console.error('CONFIG_ERR: ZG_UPLOAD_PRIVATE_KEY not set'); process.exit(1); }

// File path is passed as the first CLI argument (process.argv[2]).
// When called by zg_sync_daemon.py, the daemon rewrites this file with the
// absolute snapshot path before invoking it — process.argv[2] is the fallback
// for standalone invocations.
const filePath = process.argv[2];
if (!filePath) { console.error('USAGE: npx tsx zg_upload_single.mts <snapshot_path>'); process.exit(1); }

const file     = await ZgFile.fromFilePath(filePath);
const [tree, e1] = await file.merkleTree();
if (e1) { console.error('TREE_ERR:' + e1); process.exit(1); }

const rootHash = tree.rootHash();
const provider = new ethers.JsonRpcProvider(process.env.ZG_RPC ?? 'https://evmrpc.0g.ai');
const signer   = new ethers.Wallet(privateKey, provider);
const indexer  = new Indexer(process.env.ZG_INDEXER ?? 'https://indexer-storage.0g.ai');

const [tx, e2] = await indexer.upload(file, process.env.ZG_RPC ?? 'https://evmrpc.0g.ai', signer);
if (e2) { console.error('UPLOAD_ERR:' + e2); process.exit(1); }
await file.close();

console.log('ROOT:' + rootHash);
console.log('TX:' + (tx?.txHash || tx?.txHashes?.[0] || ''));
