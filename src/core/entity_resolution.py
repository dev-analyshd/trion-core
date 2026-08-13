"""Compatibility shim — re-exports from core.primitives.entity_resolution."""
# This file exists so `from src.core.entity_resolution import X` still works
# after the restructuring to core/. The canonical location is core.primitives.entity_resolution.
from core.primitives.entity_resolution import *  # noqa: F401,F403
