"""Compatibility shim — re-exports from core.extended.energy_participation."""
# This file exists so `from src.planes.extended.energy_participation import X` still works
# after the restructuring to core/. The canonical location is core.extended.energy_participation.
from core.extended.energy_participation import *  # noqa: F401,F403
