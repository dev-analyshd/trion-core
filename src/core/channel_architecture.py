"""Compatibility shim — re-exports from core.master.channel_architecture."""
# This file exists so `from src.core.channel_architecture import X` still works
# after the restructuring to core/. The canonical location is core.master.channel_architecture.
from core.master.channel_architecture import *  # noqa: F401,F403
