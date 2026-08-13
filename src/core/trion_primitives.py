"""Compatibility shim — re-exports from core.master.trion_primitives."""
# This file exists so `from src.core.trion_primitives import X` still works
# after the restructuring to core/. The canonical location is core.master.trion_primitives.
from core.master.trion_primitives import *  # noqa: F401,F403
