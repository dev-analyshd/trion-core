"""Compatibility shim — re-exports from core.trading.pattern_archetypes."""
# This file exists so `from src.trading.pattern_archetypes import X` still works
# after the restructuring to core/. The canonical location is core.trading.pattern_archetypes.
from core.trading.pattern_archetypes import *  # noqa: F401,F403
