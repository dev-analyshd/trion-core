"""Compatibility shim — re-exports from core.protocol.protocol_health."""
# This file exists so `from src.protocol.protocol_health import X` still works
# after the restructuring to core/. The canonical location is core.protocol.protocol_health.
from core.protocol.protocol_health import *  # noqa: F401,F403

# `import *` skips underscore-prefixed names by Python convention; re-export the
# private helpers that the test-suite and external callers depend on explicitly.
from core.protocol.protocol_health import (  # noqa: F401
    _grade,
    _role_coherence,
    _user_quality_proxy,
    _recommendations,
)


# Private-symbol re-exports — `import *` skips underscore-prefixed
# names by Python convention, so expose the helpers that tests and
# external callers depend on explicitly.
from core.protocol.protocol_health import (  # noqa: F401
    _W_DC,
    _W_ROLE_COH,
    _W_USER_QUALITY,
    _W_ATTACK_SURF,
    _role_coherence,
    _user_quality_proxy,
    _grade,
    _recommendations,
)
