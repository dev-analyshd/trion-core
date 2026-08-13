"""Compatibility shim — re-exports from core.spiritual.sigma_engine."""
# This file exists so `from src.planes.spiritual.sigma_engine import X` still works
# after the restructuring to core/. The canonical location is core.spiritual.sigma_engine.
from core.spiritual.sigma_engine import *  # noqa: F401,F403
