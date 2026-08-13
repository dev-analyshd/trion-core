"""Compatibility shim — re-exports from core.extended.biological_capital."""
# This file exists so `from src.planes.extended.biological_capital import X` still works
# after the restructuring to core/. The canonical location is core.extended.biological_capital.
from core.extended.biological_capital import *  # noqa: F401,F403
