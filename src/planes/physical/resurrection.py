"""Compatibility shim — re-exports from core.akashic.resurrection."""
# This file exists so `from src.planes.physical.resurrection import X` still works
# after the restructuring to core/. The canonical location is core.akashic.resurrection.
from core.akashic.resurrection import *  # noqa: F401,F403
