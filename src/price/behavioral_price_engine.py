"""Compatibility shim — re-exports from core.price.behavioral_price_engine."""
# This file exists so `from src.price.behavioral_price_engine import X` still works
# after the restructuring to core/. The canonical location is core.price.behavioral_price_engine.
from core.price.behavioral_price_engine import *  # noqa: F401,F403
