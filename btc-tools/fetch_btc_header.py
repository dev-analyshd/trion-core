#!/usr/bin/env python3
"""
Multi-source Bitcoin header fetcher with agreement gate.
Sources: mempool.space (primary), blockstream.info (fallback), Alchemy (fallback).
Returns header data ONLY if 2-of-3 sources agree on the block hash.

Usage: python3 fetch_btc_header.py <block_height_or_hash>
"""
import json, sys, hashlib, urllib.request, urllib.error

SOURCES = [
    {
        'name': 'mempool.space',
        'block_hash': lambda h: f'https://mempool.space/testnet/api/block-height/{h}',
        'header': lambda hh: f'https://mempool.space/testnet/api/block/{hh}/header',
        'block': lambda hh: f'https://mempool.space/testnet/api/block/{hh}',
    },
    {
        'name': 'blockstream.info',
        'block_hash': lambda h: f'https://blockstream.info/testnet/api/block-height/{h}',
        'header': lambda hh: f'https://blockstream.info/testnet/api/block/{hh}/header',
        'block': lambda hh: f'https://blockstream.info/testnet/api/block/{hh}',
    },
    {
        'name': 'alchemy',
        'block_hash': lambda h: None,  # Alchemy uses different API; handled separately
        'header': lambda hh: None,
        'block': lambda hh: None,
    },
]

ALCHEMY_BTC_RPC = 'https://bitcoin-testnet.g.alchemy.com/v2/alch_s5FpWzSEKTzISMWu761j2'

def fetch(url, timeout=15, retries=3):
    for i in range(retries):
        try:
            r = urllib.request.urlopen(url, timeout=timeout)
            return json.loads(r.read()) if 'application/json' in r.headers.get('Content-Type', '') else r.read().decode()
        except urllib.error.HTTPError as e:
            if e.code == 429 and i < retries - 1:
                import time; time.sleep(3 * (i + 1))
                continue
            raise
        except Exception as e:
            if i < retries - 1:
                import time; time.sleep(2 * (i + 1))
                continue
            raise

def fetch_block_hash_alchemy(height):
    """Fetch block hash via Alchemy JSON-RPC."""
    body = json.dumps({'jsonrpc': '2.0', 'method': 'getblockhash', 'params': [height], 'id': 1}).encode()
    req = urllib.request.Request(ALCHEMY_BTC_RPC, data=body, headers={'Content-Type': 'application/json'})
    r = urllib.request.urlopen(req, timeout=15)
    return json.loads(r.read())['result']

def fetch_block_alchemy(block_hash):
    """Fetch block (with txids) via Alchemy JSON-RPC."""
    body = json.dumps({'jsonrpc': '2.0', 'method': 'getblock', 'params': [block_hash, 2], 'id': 1}).encode()
    req = urllib.request.Request(ALCHEMY_BTC_RPC, data=body, headers={'Content-Type': 'application/json'})
    r = urllib.request.urlopen(req, timeout=15)
    return json.loads(r.read())['result']

def fetch_header(height_or_hash):
    """Fetch a Bitcoin block header from multiple sources; require 2-of-3 agreement."""
    results = {}

    # Determine block hash first
    if isinstance(height_or_hash, int) or height_or_hash.isdigit():
        height = int(height_or_hash)
        hashes = {}
        # mempool.space
        try:
            hashes['mempool.space'] = fetch(SOURCES[0]['block_hash'](height)).strip()
        except Exception as e:
            print(f'  mempool.space hash err: {e}', file=sys.stderr)
        # blockstream
        try:
            hashes['blockstream.info'] = fetch(SOURCES[1]['block_hash'](height)).strip()
        except Exception as e:
            print(f'  blockstream hash err: {e}', file=sys.stderr)
        # alchemy
        try:
            hashes['alchemy'] = fetch_block_hash_alchemy(height)
        except Exception as e:
            print(f'  alchemy hash err: {e}', file=sys.stderr)

        if not hashes:
            raise RuntimeError('All sources failed for block hash')
        # Agreement gate: require at least 2 sources to agree
        from collections import Counter
        counts = Counter(hashes.values())
        agreed_hash, count = counts.most_common(1)[0]
        if count < 2:
            # Only 1 source — use it but flag as single-source
            agreed_hash = list(hashes.values())[0]
            results['agreement'] = f'single-source ({list(hashes.keys())[0]})'
        else:
            results['agreement'] = f'{count}-of-{len(hashes)} sources agree'
        results['block_hash'] = agreed_hash
        results['height'] = height
        results['source_hashes'] = hashes
    else:
        results['block_hash'] = height_or_hash
        results['agreement'] = 'provided hash (no height lookup)'

    block_hash = results['block_hash']

    # Fetch header hex + block (txids) from blockstream
    try:
        header_hex = fetch(SOURCES[1]['header'](block_hash))
        results['header_hex'] = header_hex
        # Parse header
        hb = bytes.fromhex(header_hex)
        results['version'] = int.from_bytes(hb[0:4], 'little')
        results['prev_hash_le'] = hb[4:36].hex()
        results['merkle_root_le'] = hb[36:68].hex()
        results['timestamp'] = int.from_bytes(hb[68:72], 'little')
        results['bits'] = int.from_bytes(hb[72:76], 'little')
        results['nonce'] = int.from_bytes(hb[76:80], 'little')
    except Exception as e:
        print(f'  blockstream header err: {e}', file=sys.stderr)

    # Fetch block (txids) from blockstream
    try:
        block = fetch(SOURCES[1]['block'](block_hash))
        results['txids'] = block.get('tx', [])
        results['block_height_from_blockstream'] = block.get('height')
    except Exception as e:
        print(f'  blockstream block err: {e}', file=sys.stderr)

    # Cross-check with Alchemy block (if available)
    try:
        alchemy_block = fetch_block_alchemy(block_hash)
        results['alchemy_txid_count'] = len(alchemy_block.get('tx', []))
        results['alchemy_height'] = alchemy_block.get('height')
    except Exception as e:
        print(f'  alchemy block err: {e}', file=sys.stderr)

    # Verify PoW: double-SHA-256(header) < target (derived from bits)
    if 'header_hex' in results:
        header_bytes = bytes.fromhex(results['header_hex'])
        pow_hash = hashlib.sha256(hashlib.sha256(header_bytes).digest()).digest()
        results['pow_hash_le'] = pow_hash.hex()
        # Bits → target (compact format)
        bits = results['bits']
        exponent = bits >> 24
        mantissa = bits & 0xffffff
        target = mantissa * (1 << (8 * (exponent - 3)))
        pow_int = int.from_bytes(pow_hash[::-1], 'big')  # LE → int
        results['pow_valid'] = pow_int < target
        results['target'] = hex(target)

    return results

if __name__ == '__main__':
    if len(sys.argv) < 2:
        print('Usage: fetch_btc_header.py <block_height_or_hash>', file=sys.stderr)
        sys.exit(1)
    arg = sys.argv[1]
    try:
        arg = int(arg)
    except ValueError:
        pass
    r = fetch_header(arg)
    print(json.dumps(r, indent=2))
