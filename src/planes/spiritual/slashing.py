"""Compatibility shim — re-exports from core.spiritual.slashing."""
# This file exists so `from src.planes.spiritual.slashing import X` still works
# after the restructuring to core/. The canonical location is core.spiritual.slashing.
from core.spiritual.slashing import *  # noqa: F401,F403
