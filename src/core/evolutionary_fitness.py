"""Compatibility shim — re-exports from core.primitives.evolutionary_fitness."""
# This file exists so `from src.core.evolutionary_fitness import X` still works
# after the restructuring to core/. The canonical location is core.primitives.evolutionary_fitness.
from core.primitives.evolutionary_fitness import *  # noqa: F401,F403
