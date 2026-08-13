"""Compatibility shim — re-exports from core.spiritual.epigenetic."""
# This file exists so `from src.planes.spiritual.epigenetic import X` still works
# after the restructuring to core/. The canonical location is core.spiritual.epigenetic.
from core.spiritual.epigenetic import *  # noqa: F401,F403
