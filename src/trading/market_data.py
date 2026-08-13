"""Compatibility shim — re-exports from core.trading.market_data."""
# This file exists so `from src.trading.market_data import X` still works
# after the restructuring to core/. The canonical location is core.trading.market_data.
from core.trading.market_data import *  # noqa: F401,F403
