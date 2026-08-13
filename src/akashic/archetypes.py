"""Compatibility shim — re-exports from core.akashic.archetype."""
# This file exists so `from src.akashic.archetypes import X` still works
# after the restructuring to core/. The canonical location is core.akashic.archetype.
from core.akashic.archetype import *  # noqa: F401,F403
