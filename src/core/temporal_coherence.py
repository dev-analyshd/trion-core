"""Compatibility shim — re-exports from core.physical.temporal_coherence."""
# This file exists so `from src.core.temporal_coherence import X` still works
# after the restructuring to core/. The canonical location is core.physical.temporal_coherence.
from core.physical.temporal_coherence import *  # noqa: F401,F403
