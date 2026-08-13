"""Compatibility shim — re-exports from core.thermodynamics.entropy_engine."""
# This file exists so `from src.thermodynamics.entropy_engine import X` still works
# after the restructuring to core/. The canonical location is core.thermodynamics.entropy_engine.
from core.thermodynamics.entropy_engine import *  # noqa: F401,F403
