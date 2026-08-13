"""Compatibility shim — re-exports from core.novel.chameleon."""
# This file exists so `from src.security.chameleon_protocol import X` still works
# after the restructuring to core/. The canonical location is core.novel.chameleon.
from core.novel.chameleon import *  # noqa: F401,F403
