"""Compatibility shim — re-exports from core.spiritual.consensus_degradation."""
# This file exists so `from src.planes.spiritual.consensus_degradation import X` still works
# after the restructuring to core/. The canonical location is core.spiritual.consensus_degradation.
from core.spiritual.consensus_degradation import *  # noqa: F401,F403
