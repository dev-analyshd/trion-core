"""Compatibility shim — re-exports from core.akashic.epigenetics."""
# This file exists so `from src.akashic.epigenetics import X` still works
# after the restructuring to core/. The canonical location is core.akashic.epigenetics.
from core.akashic.epigenetics import *  # noqa: F401,F403


# Private-symbol re-exports — `import *` skips underscore-prefixed
# names by Python convention, so expose the helpers that tests and
# external callers depend on explicitly.
from core.akashic.epigenetics import (  # noqa: F401
    _resolve_epigenetic_store_path,
)
