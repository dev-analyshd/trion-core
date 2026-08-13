"""Compatibility shim — re-exports from core.lifecycle.entity_lifecycle."""
# This file exists so `from src.lifecycle.entity_lifecycle import X` still works
# after the restructuring to core/. The canonical location is core.lifecycle.entity_lifecycle.
from core.lifecycle.entity_lifecycle import *  # noqa: F401,F403


# Private-symbol re-exports — `import *` skips underscore-prefixed
# names by Python convention, so expose the helpers that tests and
# external callers depend on explicitly.
from core.lifecycle.entity_lifecycle import (  # noqa: F401
    _DATA_DIR,
)
