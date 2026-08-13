"""Compatibility shim — re-exports from core.governance.slashing."""
# This file exists so `from src.governance.slashing import X` still works
# after the restructuring to core/. The canonical location is core.governance.slashing.
from core.governance.slashing import *  # noqa: F401,F403
