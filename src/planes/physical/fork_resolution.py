"""Compatibility shim — re-exports from core.akashic.fork_resolution."""
# This file exists so `from src.planes.physical.fork_resolution import X` still works
# after the restructuring to core/. The canonical location is core.akashic.fork_resolution.
from core.akashic.fork_resolution import *  # noqa: F401,F403
