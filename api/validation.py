"""
TRION API — Input validation module.

Phase 2.1: Centralised regex-based validation for entity IDs, addresses, and
transaction hashes. The `require_entity_id` decorator wraps any Flask route
that accepts an `entity_id` path parameter, returning 400 on invalid input.

Usage:
    from api.validation import require_entity_id

    @app.route("/api/v1/signal/<entity_id>")
    @require_entity_id()
    def signal(entity_id):
        ...
"""
import re
from functools import wraps
from typing import Callable, Optional
from flask import request, jsonify

# ── Regex patterns ──────────────────────────────────────────────────────────
# Entity ID: 64-char hex string (SHA3-256 output, no 0x prefix typically,
# but we accept both forms for ergonomics)
ENTITY_ID_RE = re.compile(r'^(0x)?[a-fA-F0-9]{64}$')

# EVM address: 0x + 40 hex chars
ADDRESS_RE = re.compile(r'^0x[a-fA-F0-9]{40}$')

# Transaction hash: 0x + 64 hex chars (EVM) or 64-char hex (Solana signature
# is 88 base58 but we accept the EVM form here for cross-chain BH ledger keys)
TX_HASH_RE = re.compile(r'^(0x)?[a-fA-F0-9]{64}$')

# Block number: positive integer up to 2^53 (JS-safe)
BLOCK_NUM_RE = re.compile(r'^\d{1,16}$')

# Chain ID: positive integer 1-100000
CHAIN_ID_RE = re.compile(r'^\d{1,6}$')


def validate_entity_id(eid: Optional[str]) -> bool:
    """Return True if `eid` is a valid 64-char hex entity ID (with or without 0x)."""
    return bool(eid and ENTITY_ID_RE.match(eid.strip()))


def validate_address(addr: Optional[str]) -> bool:
    """Return True if `addr` is a valid 0x-prefixed 40-hex EVM address."""
    return bool(addr and ADDRESS_RE.match(addr.strip()))


def validate_tx_hash(h: Optional[str]) -> bool:
    """Return True if `h` is a valid 64-hex transaction hash (with or without 0x)."""
    return bool(h and TX_HASH_RE.match(h.strip()))


def validate_block_num(n: Optional[str | int]) -> bool:
    """Return True if `n` is a plausible block number."""
    if n is None:
        return False
    s = str(n)
    return bool(BLOCK_NUM_RE.match(s) and 0 <= int(s) <= 2**53)


def validate_chain_id(cid: Optional[str | int]) -> bool:
    """Return True if `cid` is a plausible chain ID (1-100000)."""
    if cid is None:
        return False
    s = str(cid)
    return bool(CHAIN_ID_RE.match(s) and 1 <= int(s) <= 100000)


def normalise_entity_id(eid: str) -> str:
    """Strip whitespace; preserve 0x prefix if present."""
    return eid.strip()


def require_entity_id(param_name: str = 'entity_id') -> Callable:
    """
    Decorator that validates an entity_id path parameter.

    Usage:
        @app.route("/api/v1/signal/<entity_id>")
        @require_entity_id()
        def signal(entity_id):
            ...

    Returns 400 JSON on invalid input:
        {"error": "invalid_entity_id", "message": "entity_id must be a 64-character hex string"}
    """
    def decorator(f: Callable) -> Callable:
        @wraps(f)
        def wrapper(*args, **kwargs):
            eid = kwargs.get(param_name, '')
            if not validate_entity_id(eid):
                return jsonify({
                    "error": "invalid_entity_id",
                    "message": f"{param_name} must be a 64-character hex string (with or without 0x prefix)",
                    "received": (eid[:80] + '…') if eid and len(eid) > 80 else eid,
                }), 400
            # Normalise before passing through
            kwargs[param_name] = normalise_entity_id(eid)
            return f(*args, **kwargs)
        return wrapper
    return decorator


def require_address(param_name: str = 'address') -> Callable:
    """
    Decorator that validates an EVM address path parameter.
    Returns 400 JSON on invalid input.
    """
    def decorator(f: Callable) -> Callable:
        @wraps(f)
        def wrapper(*args, **kwargs):
            addr = kwargs.get(param_name, '')
            if not validate_address(addr):
                return jsonify({
                    "error": "invalid_address",
                    "message": f"{param_name} must be a 0x-prefixed 40-character hex address",
                    "received": (addr[:80] + '…') if addr and len(addr) > 80 else addr,
                }), 400
            kwargs[param_name] = addr.strip()
            return f(*args, **kwargs)
        return wrapper
    return decorator


def require_tx_hash(param_name: str = 'tx_hash') -> Callable:
    """
    Decorator that validates a transaction hash path parameter.
    Returns 400 JSON on invalid input.
    """
    def decorator(f: Callable) -> Callable:
        @wraps(f)
        def wrapper(*args, **kwargs):
            h = kwargs.get(param_name, '')
            if not validate_tx_hash(h):
                return jsonify({
                    "error": "invalid_tx_hash",
                    "message": f"{param_name} must be a 64-character hex string (with or without 0x prefix)",
                    "received": (h[:80] + '…') if h and len(h) > 80 else h,
                }), 400
            kwargs[param_name] = h.strip()
            return f(*args, **kwargs)
        return wrapper
    return decorator


# ── Self-test ───────────────────────────────────────────────────────────────
if __name__ == '__main__':
    assert validate_entity_id('a' * 64)
    assert validate_entity_id('0x' + 'a' * 64)
    assert validate_entity_id('F9769049' + 'b' * 56)
    assert not validate_entity_id('short')
    assert not validate_entity_id('z' * 64)  # non-hex
    assert not validate_entity_id(None)
    assert not validate_entity_id('')

    assert validate_address('0x' + 'a' * 40)
    assert not validate_address('a' * 40)  # missing 0x
    assert not validate_address('0x' + 'z' * 40)

    assert validate_tx_hash('0x' + 'a' * 64)
    assert validate_tx_hash('a' * 64)
    assert not validate_tx_hash('short')

    assert validate_block_num(18000000)
    assert validate_block_num('18000000')
    assert not validate_block_num(-1)
    assert not validate_block_num('abc')

    assert validate_chain_id(1)
    assert validate_chain_id('42161')
    assert not validate_chain_id(0)
    assert not validate_chain_id('abc')

    print("✓ All validation self-tests passed")
