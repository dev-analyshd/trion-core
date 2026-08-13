"""Compatibility shim — re-exports from core.akashic.trajectory_anomaly."""
# This file exists so `from src.planes.physical.trajectory_anomaly import X` still works
# after the restructuring to core/. The canonical location is core.akashic.trajectory_anomaly.
from core.akashic.trajectory_anomaly import *  # noqa: F401,F403
