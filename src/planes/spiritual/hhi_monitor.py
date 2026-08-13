"""Compatibility shim — re-exports from core.spiritual.hhi_monitor."""
# This file exists so `from src.planes.spiritual.hhi_monitor import X` still works
# after the restructuring to core/. The canonical location is core.spiritual.hhi_monitor.
from core.spiritual.hhi_monitor import *  # noqa: F401,F403
