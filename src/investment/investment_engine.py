"""Compatibility shim — re-exports from core.investment.investment_engine."""
# This file exists so `from src.investment.investment_engine import X` still works
# after the restructuring to core/. The canonical location is core.investment.investment_engine.
from core.investment.investment_engine import *  # noqa: F401,F403
