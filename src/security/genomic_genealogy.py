"""Compatibility shim — re-exports from core.spiritual.living_security.genomic_genealogy."""
# This file exists so `from src.security.genomic_genealogy import X` still works
# after the restructuring to core/. The canonical location is core.spiritual.living_security.genomic_genealogy.
from core.spiritual.living_security.genomic_genealogy import *  # noqa: F401,F403
