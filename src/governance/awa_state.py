"""Compatibility shim — re-exports from core.governance.awa."""
# This file exists so `from src.governance.awa_state import X` still works
# after the restructuring to core/. The canonical location is core.governance.awa.
from core.governance.awa import *  # noqa: F401,F403
