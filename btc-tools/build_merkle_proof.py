#!/usr/bin/env python3
"""
Merkle proof builder pinned to block 5128449 golden proof.
Builds a Bitcoin Merkle proof for a txid in a block, returning the sibling path
and the is-left flags for each level.

Usage: python3 build_merkle_proof.py <block_hash> <txid>
"""
import json, sys, hashlib, urllib.request

def fetch_txids(block_hash):
    """Fetch txids for a block. Try blockstream first, fall back to Alchemy."""
    # blockstream: GET /block/{hash} returns {tx: [txid, ...]} or {txs: [...]}
    try:
        url = f'https://blockstream.info/testnet/api/block/{block_hash}'
        r = urllib.request.urlopen(url, timeout=15)
        data = json.loads(r.read())
        txids = data.get('tx', data.get('txs', []))
        if txids and isinstance(txids[0], str):
            return txids
        if txids and isinstance(txids[0], dict):
            return [t['txid'] for t in txids]
    except Exception as e:
        print(f'  blockstream err: {e}', file=sys.stderr)
    # Alchemy fallback
    body = json.dumps({'jsonrpc': '2.0', 'method': 'getblock', 'params': [block_hash, 2], 'id': 1}).encode()
    req = urllib.request.Request('https://bitcoin-testnet.g.alchemy.com/v2/alch_s5FpWzSEKTzISMWu761j2', data=body, headers={'Content-Type': 'application/json'})
    r = urllib.request.urlopen(req, timeout=15)
    result = json.loads(r.read())['result']
    return [t['txid'] for t in result.get('tx', [])]

def double_sha256(b):
    return hashlib.sha256(hashlib.sha256(b).digest()).digest()

def build_merkle_proof(txids, target_txid):
    """Build a Merkle proof for target_txid. Returns (path, is_left, merkle_root)."""
    # Bitcoin Merkle: hashes are in LE byte order; concatenate as bytes, double-SHA-256
    level = [bytes.fromhex(t)[::-1] for t in txids]  # reverse to internal LE
    idx = txids.index(target_txid)
    path = []
    is_left = []
    while len(level) > 1:
        if idx % 2 == 0:
            # target is left; sibling is right
            sib_idx = idx + 1
            sib = level[sib_idx] if sib_idx < len(level) else level[idx]
            path.append(sib[::-1].hex())  # back to display order
            is_left.append(True)  # sibling is on the right (so "is-left" for the current node)
        else:
            sib_idx = idx - 1
            sib = level[sib_idx]
            path.append(sib[::-1].hex())
            is_left.append(False)  # sibling is on the left
        # Next level
        next_level = []
        for i in range(0, len(level), 2):
            l = level[i]
            r = level[i+1] if i+1 < len(level) else l
            next_level.append(double_sha256(l + r))
        level = next_level
        idx = idx // 2
    merkle_root = level[0][::-1].hex()  # back to display order
    return path, is_left, merkle_root

if __name__ == '__main__':
    if len(sys.argv) < 3:
        print('Usage: build_merkle_proof.py <block_hash> <txid>', file=sys.stderr)
        sys.exit(1)
    block_hash = sys.argv[1]
    target_txid = sys.argv[2]

    txids = fetch_txids(block_hash)
    if target_txid not in txids:
        print(f'ERROR: txid {target_txid} not in block {block_hash}', file=sys.stderr)
        sys.exit(1)

    path, is_left, root = build_merkle_proof(txids, target_txid)
    result = {
        'block_hash': block_hash,
        'target_txid': target_txid,
        'tx_index': txids.index(target_txid),
        'tx_count': len(txids),
        'merkle_depth': len(path),
        'merkle_path': path,
        'is_left': is_left,
        'recomputed_merkle_root': root,
    }
    print(json.dumps(result, indent=2))
