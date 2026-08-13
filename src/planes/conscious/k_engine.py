"""Compatibility shim — re-exports from core.spiritual.conscious.engine."""
# This file exists so `from src.planes.conscious.k_engine import X` still works
# after the restructuring to core/. The canonical location is core.spiritual.conscious.engine.
from core.spiritual.conscious.engine import *  # noqa: F401,F403
