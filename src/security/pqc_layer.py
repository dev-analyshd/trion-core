"""Compatibility shim — re-exports from core.spiritual.living_security.pqc_layer."""
# This file exists so `from src.security.pqc_layer import X` still works
# after the restructuring to core/. The canonical location is core.spiritual.living_security.pqc_layer.
from core.spiritual.living_security.pqc_layer import *  # noqa: F401,F403
