"""Compatibility shim — re-exports from core.spiritual.conscious.indigenous_knowledge."""
# This file exists so `from src.planes.conscious.indigenous_knowledge import X` still works
# after the restructuring to core/. The canonical location is core.spiritual.conscious.indigenous_knowledge.
from core.spiritual.conscious.indigenous_knowledge import *  # noqa: F401,F403
