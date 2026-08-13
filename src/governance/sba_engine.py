"""Compatibility shim — re-exports from core.governance.sba_engine."""
# This file exists so `from src.governance.sba_engine import X` still works
# after the restructuring to core/. The canonical location is core.governance.sba_engine.
from core.governance.sba_engine import *  # noqa: F401,F403


# Private-symbol re-exports — `import *` skips underscore-prefixed
# names by Python convention, so expose the helpers that tests and
# external callers depend on explicitly.
from core.governance.sba_engine import (  # noqa: F401
    _corr_to_score,
)
