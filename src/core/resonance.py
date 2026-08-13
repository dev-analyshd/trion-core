"""Compatibility shim — re-exports from core.primitives.resonance."""
# This file exists so `from src.core.resonance import X` still works
# after the restructuring to core/. The canonical location is core.primitives.resonance.
from core.primitives.resonance import *  # noqa: F401,F403
