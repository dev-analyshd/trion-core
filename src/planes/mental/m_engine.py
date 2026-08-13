"""Compatibility shim — re-exports from core.mental.confidence."""
# This file exists so `from src.planes.mental.m_engine import X` still works
# after the restructuring to core/. The canonical location is core.mental.confidence.
from core.mental.confidence import *  # noqa: F401,F403
