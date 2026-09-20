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

# ── Cross-VM address patterns (L0 — substrate-independent) ──────────────────
# Solana: base58, 32-44 chars
SOLANA_RE = re.compile(r'^[1-9A-HJ-NP-Za-km-z]{32,44}$')
# Cosmos (bech32): prefix + 1 + 38+ chars
COSMOS_RE = re.compile(r'^(cosmos|osmo|juno|akash|celestia|injective|terra|kava|secret|regen|sentinel|ixo|emoney|stargaze|agoric|sommelier|umee|crescent|noble|dymension|tgrade|archway|neutron|nibiru|stride|aura)1[a-z0-9]{38,}$')
# NEAR: account.near or subaccount.account.near
NEAR_RE = re.compile(r'^[a-z0-9][a-z0-9\-_.]{1,63}\.near$')
# TON: EQ/UQ + base64url (48 chars) or hex
TON_RE = re.compile(r'^(EQ|UQ)[A-Za-z0-9_-]{46}$')
# Sui/Aptos (Move): 0x + 64 hex (32-byte addresses)
MOVE_RE = re.compile(r'^0x[a-fA-F0-9]{64}$')
# Stacks: SP/ST + base58check (41 chars)
STACKS_RE = re.compile(r'^(SP|ST)[A-Z0-9]{39,41}$')
# Stellar: G + base32 (56 chars)
STELLAR_RE = re.compile(r'^G[A-Z2-7]{55}$')
# Bitcoin: bc1, 1, 3 prefixes
BITCOIN_RE = re.compile(r'^(bc1[a-z0-9]{39,59}|[13][a-km-zA-HJ-NP-Z1-9]{25,34})$')

# ── Well-known protocol aliases ─────────────────────────────────────────────
# STRICT ALLOWLIST (lowercase, exact-match) of protocol names accepted as
# entity identifiers. These resolve to stable BEO IDs via SHA3-256 of the
# canonical alias string — preserving the documented demo/dashboard API
# surface (e.g. /api/v1/signal/uniswap) while blocking arbitrary/injected
# entity inputs. Anything not hex, not an address, and not in this set is
# rejected with 400.
PROTOCOL_ALIASES = frozenset({
    "uniswap", "aave", "compound", "curve", "maker", "lido",
    "ethereum", "arbitrum", "base", "optimism", "polygon", "solana",
    "trion", "trion_protocol",
})


def resolve_protocol_alias(eid: str) -> Optional[str]:
    """Return the canonical BEO ID for a protocol alias, or None if `eid` is
    not a listed alias. Aliases map to a deterministic 64-hex BEO ID so every
    component (FAISS, ledger, coherence) sees one stable identity per protocol.
    """
    if not eid:
        return None
    key = eid.strip().lower()
    if key not in PROTOCOL_ALIASES:
        return None
    import hashlib
    return hashlib.sha3_256(f"trion:protocol:{key}".encode()).hexdigest()

# Transaction hash: 0x + 64 hex chars (EVM) or 64-char hex (Solana signature
# is 88 base58 but we accept the EVM form here for cross-chain BH ledger keys)
TX_HASH_RE = re.compile(r'^(0x)?[a-fA-F0-9]{64}$')

# Block number: positive integer up to 2^53 (JS-safe)
BLOCK_NUM_RE = re.compile(r'^\d{1,16}$')

# Chain ID: positive integer 1..2**32-1 (10 digits). The EVM chain-id
# space is uint256 in EIP-155 but every real id fits uint32; the canonical
# TRION registry (api/chains_registry.py) tops out at Harmony 1666600000.
# The old 1-100000 bound rejected VALID canonical ids (Zora 7777777,
# Eth Sepolia 11155111, Neon 245022934, Aurora 1313161554) — reported by
# W3-C; this validator is plausibility-only (no registry membership claim).
CHAIN_ID_RE = re.compile(r'^\d{1,10}$')
CHAIN_ID_MAX = 2**32 - 1


def validate_entity_id(eid: Optional[str]) -> bool:
    """Return True if `eid` is a valid entity identifier.
    
    TRION is substrate-independent (whitepaper §L0) — ANY non-empty string
    that doesn't contain path traversal characters is accepted as an entity
    identifier. The BH computation normalizes it to a canonical hex BEO ID
    via SHA3-256, so every component (FAISS, ledger, coherence) sees one
    stable identity per entity regardless of the source VM.
    
    This accepts ALL VM address formats:
    - EVM: 0x + 40 hex
    - Solana: base58 (32-44 chars)
    - Cosmos: bech32 (cosmos1..., osmo1...)
    - NEAR: account.near
    - TON: EQ.../UQ...
    - Move: 0x + 64 hex (Sui/Aptos)
    - Stacks: SP.../ST...
    - Stellar: G + 55 chars
    - Bitcoin: bc1.../1.../3...
    - Program names, contract names, or any other identifier
    - Protocol aliases (uniswap, aave, etc.)
    """
    if not eid:
        return False
    eid = eid.strip()
    if len(eid) < 2 or len(eid) > 200:
        return False
    # Block path traversal (security)
    if "../" in eid or "..\\" in eid or "\x00" in eid:
        return False
    return True


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
    """Return True if `cid` is a plausible chain ID (1..2**32-1).

    Plausibility only — a True result does NOT mean the id exists in the
    canonical chain registry (see api/chains_registry.py for membership).
    """
    if cid is None:
        return False
    s = str(cid)
    return bool(CHAIN_ID_RE.match(s) and 1 <= int(s) <= CHAIN_ID_MAX)


def normalise_entity_id(eid: str) -> str:
    """Normalise an entity ID to its canonical BEO form via the resolution engine.
    
    This is the CORE of TRION's uniqueness (whitepaper §L0.2):
    TRION does NOT track addresses — it tracks ECONOMIC ACTORS.
    
    Uses core/primitives/entity_resolution.py::resolve_entity() to resolve
    the address to a canonical BEO ID. For linked wallets (same funding
    source, timing, behavioral patterns), they resolve to ONE BEO ID.
    """
    import hashlib
    eid = eid.strip()
    
    alias_resolved = resolve_protocol_alias(eid)
    if alias_resolved:
        return alias_resolved
    
    if ENTITY_ID_RE.match(eid):
        return eid.lower().replace("0x", "", 1) if eid.lower().startswith("0x") else eid.lower()
    
    if ADDRESS_RE.match(eid) or MOVE_RE.match(eid):
        eid = eid.lower()
    
    try:
        from core.primitives.entity_resolution import WalletActivity, resolve_entity
        wallet = WalletActivity(
            address=eid,
            chain_id=_detect_chain_id(eid),
            funding_source=None,
            first_tx_ts=0,
            co_tx_timestamps=[],
        )
        result = resolve_entity([wallet])
        canonical_id = result.get("canonical_id")
        if canonical_id:
            return canonical_id.replace("0x", "", 1) if canonical_id.startswith("0x") else canonical_id
        return hashlib.sha3_256(eid.encode()).hexdigest()
    except Exception:
        return hashlib.sha3_256(eid.encode()).hexdigest()


def _detect_chain_id(eid: str) -> int:
    """Detect the chain ID from an entity ID's address format."""
    eid = eid.strip()
    if ADDRESS_RE.match(eid): return 1
    if MOVE_RE.match(eid): return 1
    if SOLANA_RE.match(eid): return 900
    if COSMOS_RE.match(eid): return 23000
    if NEAR_RE.match(eid): return 23000
    if BITCOIN_RE.match(eid): return 100
    if STACKS_RE.match(eid): return 26000
    if STELLAR_RE.match(eid): return 27000
    return 0


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
                    "message": f"{param_name} must be a 64-character hex BEO ID or a 0x-prefixed 40-character EVM address",
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
                    "message": f"{param_name} must be a 64-character hex BEO ID or a 0x-prefixed 40-character EVM address",
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
    assert validate_entity_id('0x' + 'a' * 40)  # EVM address also valid
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
    # canonical registry ids previously rejected by the 1-100000 bound (W3-C)
    assert validate_chain_id(7777777)          # Zora
    assert validate_chain_id(11155111)         # Eth Sepolia
    assert validate_chain_id(245022934)        # Neon
    assert validate_chain_id(1313161554)       # Aurora
    assert validate_chain_id(1666600000)       # Harmony (registry max)
    assert not validate_chain_id(0)
    assert not validate_chain_id('abc')
    assert not validate_chain_id(2**32)        # past the uint32 id space

    print("✓ All validation self-tests passed")
