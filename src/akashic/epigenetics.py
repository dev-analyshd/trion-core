"""Compatibility shim — re-exports from core.akashic.epigenetics."""
# This file exists so `from src.akashic.epigenetics import X` still works
# after the restructuring to core/. The canonical location is core.akashic.epigenetics.
from core.akashic.epigenetics import *  # noqa: F401,F403
