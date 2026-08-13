"""Compatibility shim — re-exports from core.master.btcp_score."""
# This file exists so `from src.core.btcp_score import X` still works
# after the restructuring to core/. The canonical location is core.master.btcp_score.
from core.master.btcp_score import *  # noqa: F401,F403
