"""Compatibility shim — re-exports from core.novel.behavioral_identity_recovery."""
# This file exists so `from src.signals.behavioral_identity_recovery import X` still works
# after the restructuring to core/. The canonical location is core.novel.behavioral_identity_recovery.
from core.novel.behavioral_identity_recovery import *  # noqa: F401,F403
