"""Compatibility shim — re-exports from core.extended.cross_species."""
# This file exists so `from src.planes.extended.xsl import X` still works
# after the restructuring to core/. The canonical location is core.extended.cross_species.
from core.extended.cross_species import *  # noqa: F401,F403
