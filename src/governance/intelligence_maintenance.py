"""Compatibility shim — re-exports from core.governance.intelligence_maintenance."""
# This file exists so `from src.governance.intelligence_maintenance import X` still works
# after the restructuring to core/. The canonical location is core.governance.intelligence_maintenance.
from core.governance.intelligence_maintenance import *  # noqa: F401,F403
