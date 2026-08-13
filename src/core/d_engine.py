"""Compatibility shim — re-exports from core.master.d_engine."""
# This file exists so `from src.core.d_engine import X` still works
# after the restructuring to core/. The canonical location is core.master.d_engine.
from core.master.d_engine import *  # noqa: F401,F403
