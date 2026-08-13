"""Compatibility shim — re-exports from core.master.coherence."""
# This file exists so `from src.core.coherence_engine import X` still works
# after the restructuring to core/. The canonical location is core.master.coherence.
from core.master.coherence import *  # noqa: F401,F403
