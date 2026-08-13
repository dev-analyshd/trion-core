"""Compatibility shim — re-exports from core.master.homomorphic_mapping."""
# This file exists so `from src.core.homomorphic_mapping import X` still works
# after the restructuring to core/. The canonical location is core.master.homomorphic_mapping.
from core.master.homomorphic_mapping import *  # noqa: F401,F403
