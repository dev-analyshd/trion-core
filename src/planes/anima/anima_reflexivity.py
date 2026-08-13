"""Compatibility shim — re-exports from core.mental.anima.reflexivity."""
# This file exists so `from src.planes.anima.anima_reflexivity import X` still works
# after the restructuring to core/. The canonical location is core.mental.anima.reflexivity.
from core.mental.anima.reflexivity import *  # noqa: F401,F403
