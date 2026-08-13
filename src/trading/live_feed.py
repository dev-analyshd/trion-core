"""Compatibility shim — re-exports from core.trading.live_feed."""
# This file exists so `from src.trading.live_feed import X` still works
# after the restructuring to core/. The canonical location is core.trading.live_feed.
from core.trading.live_feed import *  # noqa: F401,F403
