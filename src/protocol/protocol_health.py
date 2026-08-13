"""Compatibility shim — re-exports from core.protocol.protocol_health."""
# This file exists so `from src.protocol.protocol_health import X` still works
# after the restructuring to core/. The canonical location is core.protocol.protocol_health.
from core.protocol.protocol_health import *  # noqa: F401,F403
