"""Compatibility shim — re-exports from core.extended.natural_liquidity."""
# This file exists so `from src.planes.physical.nl_engine import X` still works
# after the restructuring to core/. The canonical location is core.extended.natural_liquidity.
from core.extended.natural_liquidity import *  # noqa: F401,F403
