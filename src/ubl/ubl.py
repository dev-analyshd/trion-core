"""Compatibility shim — re-exports from core.ubl.ubl."""
# This file exists so `from src.ubl.ubl import X` still works
# after the restructuring to core/. The canonical location is core.ubl.ubl.
from core.ubl.ubl import *  # noqa: F401,F403
