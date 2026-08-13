"""Compatibility shim — re-exports from core.master.degradation."""
# This file exists so `from src.core.consensus_degradation import X` still works
# after the restructuring to core/. The canonical location is core.master.degradation.
from core.master.degradation import *  # noqa: F401,F403
