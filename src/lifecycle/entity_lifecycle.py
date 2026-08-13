"""Compatibility shim — re-exports from core.lifecycle.entity_lifecycle."""
# This file exists so `from src.lifecycle.entity_lifecycle import X` still works
# after the restructuring to core/. The canonical location is core.lifecycle.entity_lifecycle.
from core.lifecycle.entity_lifecycle import *  # noqa: F401,F403
