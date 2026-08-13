"""Compatibility shim — re-exports from core.mental.anima.source_credibility."""
# This file exists so `from src.planes.anima.source_credibility import X` still works
# after the restructuring to core/. The canonical location is core.mental.anima.source_credibility.
from core.mental.anima.source_credibility import *  # noqa: F401,F403
