"""Compatibility shim — re-exports from core.protocol.segmentation."""
# This file exists so `from src.protocol.segmentation import X` still works
# after the restructuring to core/. The canonical location is core.protocol.segmentation.
from core.protocol.segmentation import *  # noqa: F401,F403
