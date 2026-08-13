"""Compatibility shim — re-exports from core.mental.intelligence_maintenance."""
# This file exists so `from src.planes.mental.intelligence_maintenance import X` still works
# after the restructuring to core/. The canonical location is core.mental.intelligence_maintenance.
from core.mental.intelligence_maintenance import *  # noqa: F401,F403
