"""Compatibility shim — re-exports from core.akashic.mental_transformer."""
# This file exists so `from src.core.mental_transformer import X` still works
# after the restructuring to core/. The canonical location is core.akashic.mental_transformer.
from core.akashic.mental_transformer import *  # noqa: F401,F403
