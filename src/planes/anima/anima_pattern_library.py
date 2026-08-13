"""Compatibility shim — re-exports from core.mental.anima.pattern_library."""
# This file exists so `from src.planes.anima.anima_pattern_library import X` still works
# after the restructuring to core/. The canonical location is core.mental.anima.pattern_library.
from core.mental.anima.pattern_library import *  # noqa: F401,F403
