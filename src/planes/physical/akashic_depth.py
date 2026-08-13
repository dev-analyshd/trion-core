"""Compatibility shim — re-exports from core.akashic.depth."""
# This file exists so `from src.planes.physical.akashic_depth import X` still works
# after the restructuring to core/. The canonical location is core.akashic.depth.
from core.akashic.depth import *  # noqa: F401,F403
