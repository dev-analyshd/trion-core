"""Compatibility shim — re-exports from core.master.signal_factory."""
# This file exists so `from src.signals.signal_factory import X` still works
# after the restructuring to core/. The canonical location is core.master.signal_factory.
from core.master.signal_factory import *  # noqa: F401,F403
