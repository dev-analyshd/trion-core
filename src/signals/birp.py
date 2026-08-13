"""Compatibility shim — re-exports from core.novel.birp."""
# This file exists so `from src.signals.birp import X` still works
# after the restructuring to core/. The canonical location is core.novel.birp.
from core.novel.birp import *  # noqa: F401,F403
