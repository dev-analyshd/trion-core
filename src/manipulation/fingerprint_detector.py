"""Compatibility shim — re-exports from core.physical.manipulation_detector."""
# This file exists so `from src.manipulation.fingerprint_detector import X` still works
# after the restructuring to core/. The canonical location is core.physical.manipulation_detector.
from core.physical.manipulation_detector import *  # noqa: F401,F403
