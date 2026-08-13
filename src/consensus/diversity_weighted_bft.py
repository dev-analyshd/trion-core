"""Compatibility shim — re-exports from core.spiritual.consensus."""
# This file exists so `from src.consensus.diversity_weighted_bft import X` still works
# after the restructuring to core/. The canonical location is core.spiritual.consensus.
from core.spiritual.consensus import *  # noqa: F401,F403
