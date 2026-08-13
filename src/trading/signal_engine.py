"""Compatibility shim — re-exports from core.trading.signal_engine."""
# This file exists so `from src.trading.signal_engine import X` still works
# after the restructuring to core/. The canonical location is core.trading.signal_engine.
from core.trading.signal_engine import *  # noqa: F401,F403
