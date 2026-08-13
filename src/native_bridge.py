"""Compatibility shim — re-exports from core.native_bridge."""
# This file exists so `from src.native_bridge import X` still works
# after the restructuring to core/. The canonical location is core.native_bridge.
from core.native_bridge import *  # noqa: F401,F403


# Private-symbol re-exports — `import *` skips underscore-prefixed
# names by Python convention, so expose the helpers that tests and
# external callers depend on explicitly.
from core.native_bridge import (  # noqa: F401
    _ROOT,
    _BIN_DIR,
    _GO_BIN,
    _GHC_RUNGHC,
    _GHC_CANDIDATES,
    _GO_CANDIDATES,
    _find_tool,
)
