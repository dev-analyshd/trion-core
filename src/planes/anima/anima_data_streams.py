"""Compatibility shim — re-exports from core.mental.anima.data_streams."""
# This file exists so `from src.planes.anima.anima_data_streams import X` still works
# after the restructuring to core/. The canonical location is core.mental.anima.data_streams.
from core.mental.anima.data_streams import *  # noqa: F401,F403
