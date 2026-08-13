"""Compatibility shim — re-exports from core.master.moat."""
# This file exists so `from src.core.moat_engine import X` still works
# after the restructuring to core/. The canonical location is core.master.moat.
from core.master.moat import *  # noqa: F401,F403
