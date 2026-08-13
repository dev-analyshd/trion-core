"""Compatibility shim — re-exports from core.agent.safety_pipeline."""
# This file exists so `from src.agent.safety_pipeline import X` still works
# after the restructuring to core/. The canonical location is core.agent.safety_pipeline.
from core.agent.safety_pipeline import *  # noqa: F401,F403


# Private-symbol re-exports — `import *` skips underscore-prefixed
# names by Python convention, so expose the helpers that tests and
# external callers depend on explicitly.
from core.agent.safety_pipeline import (  # noqa: F401
    _AGENT_REGISTRY,
)
