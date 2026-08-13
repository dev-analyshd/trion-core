"""Compatibility shim — re-exports from core.protocol.segmentation."""
# This file exists so `from src.protocol.segmentation import X` still works
# after the restructuring to core/. The canonical location is core.protocol.segmentation.
from core.protocol.segmentation import *  # noqa: F401,F403


# Private-symbol re-exports — `import *` skips underscore-prefixed
# names by Python convention, so expose the helpers that tests and
# external callers depend on explicitly.
from core.protocol.segmentation import (  # noqa: F401
    _get_conn,
    _DB_PATH,
    _CACHE_TTL,
)
