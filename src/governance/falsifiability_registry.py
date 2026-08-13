"""Compatibility shim — re-exports from core.governance.falsifiability_registry."""
# This file exists so `from src.governance.falsifiability_registry import X` still works
# after the restructuring to core/. The canonical location is core.governance.falsifiability_registry.
from core.governance.falsifiability_registry import *  # noqa: F401,F403
