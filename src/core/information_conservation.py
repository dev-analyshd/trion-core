"""Compatibility shim — re-exports from core.primitives.thermodynamics."""
# This file exists so `from src.core.information_conservation import X` still works
# after the restructuring to core/. The canonical location is core.primitives.thermodynamics.
from core.primitives.thermodynamics import *  # noqa: F401,F403
