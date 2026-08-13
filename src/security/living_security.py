"""Compatibility shim — re-exports from core.spiritual.living_security."""
# This file exists so `from src.security.living_security import X` still works
# after the restructuring to core/. The canonical location is core.spiritual.living_security.
from core.spiritual.living_security import *  # noqa: F401,F403
