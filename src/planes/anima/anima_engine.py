"""Compatibility shim — re-exports from core.mental.anima.engine."""
# This file exists so `from src.planes.anima.anima_engine import X` still works
# after the restructuring to core/. The canonical location is core.mental.anima.engine.
from core.mental.anima.engine import *  # noqa: F401,F403
