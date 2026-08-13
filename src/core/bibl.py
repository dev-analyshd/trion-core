"""Compatibility shim — re-exports from core.akashic.bibl."""
# This file exists so `from src.core.bibl import X` still works
# after the restructuring to core/. The canonical location is core.akashic.bibl.
from core.akashic.bibl import *  # noqa: F401,F403
