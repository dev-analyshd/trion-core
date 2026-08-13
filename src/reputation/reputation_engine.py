"""Compatibility shim — re-exports from core.reputation.reputation_engine."""
# This file exists so `from src.reputation.reputation_engine import X` still works
# after the restructuring to core/. The canonical location is core.reputation.reputation_engine.
from core.reputation.reputation_engine import *  # noqa: F401,F403
