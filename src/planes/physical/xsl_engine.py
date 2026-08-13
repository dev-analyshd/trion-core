"""Compatibility shim — re-exports from core.extended.xsl_engine."""
# This file exists so `from src.planes.physical.xsl_engine import X` still works
# after the restructuring to core/. The canonical location is core.extended.xsl_engine.
from core.extended.xsl_engine import *  # noqa: F401,F403
