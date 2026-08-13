"""Compatibility shim — re-exports from core.akashic.bibl."""
# This file exists so `from src.core.bibl import X` still works
# after the restructuring to core/. The canonical location is core.akashic.bibl.
from core.akashic.bibl import *  # noqa: F401,F403


# Private-symbol re-exports — `import *` skips underscore-prefixed
# names by Python convention, so expose the helpers that tests and
# external callers depend on explicitly.
from core.akashic.bibl import (  # noqa: F401
    _circular_mean_and_strength,
)
