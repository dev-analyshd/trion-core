"""Compatibility shim — re-exports from core.thermodynamics.thermo_engine."""
# This file exists so `from src.thermodynamics.thermo_engine import X` still works
# after the restructuring to core/. The canonical location is core.thermodynamics.thermo_engine.
from core.thermodynamics.thermo_engine import *  # noqa: F401,F403
