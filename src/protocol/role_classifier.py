"""Compatibility shim — re-exports from core.protocol.role_classifier."""
# This file exists so `from src.protocol.role_classifier import X` still works
# after the restructuring to core/. The canonical location is core.protocol.role_classifier.
from core.protocol.role_classifier import *  # noqa: F401,F403


# Private-symbol re-exports — `import *` skips underscore-prefixed
# names by Python convention, so expose the helpers that tests and
# external callers depend on explicitly.
from core.protocol.role_classifier import (  # noqa: F401
    _ROLE_TO_ARCHETYPE,
    _ROLE_RISK,
    _ROLE_DESC,
)
