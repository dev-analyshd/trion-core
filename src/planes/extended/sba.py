"""Compatibility shim — re-exports from core.extended.sovereign_behavioral."""
# This file exists so `from src.planes.extended.sba import X` still works
# after the restructuring to core/. The canonical location is core.extended.sovereign_behavioral.
from core.extended.sovereign_behavioral import *  # noqa: F401,F403
