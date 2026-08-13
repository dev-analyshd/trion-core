"""Compatibility shim — re-exports from core.primitives.behavioral_hash."""
# This file exists so `from src.core.behavioral_hash import X` still works
# after the restructuring to core/. The canonical location is core.primitives.behavioral_hash.
from core.primitives.behavioral_hash import *  # noqa: F401,F403
