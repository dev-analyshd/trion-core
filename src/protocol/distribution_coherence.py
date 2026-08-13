"""Compatibility shim — re-exports from core.protocol.distribution_coherence."""
# This file exists so `from src.protocol.distribution_coherence import X` still works
# after the restructuring to core/. The canonical location is core.protocol.distribution_coherence.
from core.protocol.distribution_coherence import *  # noqa: F401,F403


# Private-symbol re-exports — `import *` skips underscore-prefixed
# names by Python convention, so expose the helpers that tests and
# external callers depend on explicitly.
from core.protocol.distribution_coherence import (  # noqa: F401
    _normalise,
    _smooth,
    _entropy,
)
