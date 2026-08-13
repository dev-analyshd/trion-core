"""Compatibility shim — re-exports from core.physical.transduction_integrity."""
# This file exists so `from src.core.self_verification import X` still works
# after the restructuring to core/. The canonical location is core.physical.transduction_integrity.
from core.physical.transduction_integrity import *  # noqa: F401,F403
