"""Compatibility shim — re-exports from core.protocol.role_classifier."""
# This file exists so `from src.protocol.role_classifier import X` still works
# after the restructuring to core/. The canonical location is core.protocol.role_classifier.
from core.protocol.role_classifier import *  # noqa: F401,F403
