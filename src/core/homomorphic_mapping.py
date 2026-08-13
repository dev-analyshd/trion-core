"""Compatibility shim — re-exports from core.master.homomorphic_mapping."""
# This file exists so `from src.core.homomorphic_mapping import X` still works
# after the restructuring to core/. The canonical location is core.master.homomorphic_mapping.
from core.master.homomorphic_mapping import *  # noqa: F401,F403


# Private-symbol re-exports — `import *` skips underscore-prefixed
# names by Python convention, so expose the helpers that tests and
# external callers depend on explicitly.
from core.master.homomorphic_mapping import (  # noqa: F401
    _resolve_arch,
    _map_evm,
    _map_btc,
    _map_solana,
    _map_cosmos,
    _map_generic,
    _default_stats,
)
