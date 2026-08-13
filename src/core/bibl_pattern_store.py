"""Compatibility shim — re-exports from core.akashic.bibl_pattern_store."""
# This file exists so `from src.core.bibl_pattern_store import X` still works
# after the restructuring to core/. The canonical location is core.akashic.bibl_pattern_store.
from core.akashic.bibl_pattern_store import *  # noqa: F401,F403
