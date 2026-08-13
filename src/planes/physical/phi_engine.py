"""Compatibility shim — re-exports from core.physical.phi_engine."""
# This file exists so `from src.planes.physical.phi_engine import X` still works
# after the restructuring to core/. The canonical location is core.physical.phi_engine.
from core.physical.phi_engine import *  # noqa: F401,F403
