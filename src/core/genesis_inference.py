"""Compatibility shim — re-exports from core.akashic.genesis."""
# This file exists so `from src.core.genesis_inference import X` still works
# after the restructuring to core/. The canonical location is core.akashic.genesis.
from core.akashic.genesis import *  # noqa: F401,F403


# Private-symbol re-exports — `import *` skips underscore-prefixed
# names by Python convention, so expose the helpers that tests and
# external callers depend on explicitly.
from core.akashic.genesis import (  # noqa: F401
    _get_requests,
    _ARCHETYPE_MATCH_ENDPOINT,
)
