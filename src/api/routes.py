"""Compatibility shim — re-exports from core.api.routes."""
# This file exists so `from src.api.routes import X` still works
# after the restructuring to core/. The canonical location is core.api.routes.
from core.api.routes import *  # noqa: F401,F403
