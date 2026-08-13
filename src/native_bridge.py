"""Compatibility shim — re-exports from core.native_bridge."""
# This file exists so `from src.native_bridge import X` still works
# after the restructuring to core/. The canonical location is core.native_bridge.
from core.native_bridge import *  # noqa: F401,F403
