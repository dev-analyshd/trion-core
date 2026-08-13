"""Compatibility shim — re-exports from core.trading.agent_interface."""
# This file exists so `from src.trading.agent_interface import X` still works
# after the restructuring to core/. The canonical location is core.trading.agent_interface.
from core.trading.agent_interface import *  # noqa: F401,F403
