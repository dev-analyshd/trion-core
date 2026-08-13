"""Compatibility shim — re-exports from core.novel.behavioral_identity_recovery."""
# This file exists so `from src.signals.behavioral_identity_recovery import X` still works
# after the restructuring to core/. The canonical location is core.novel.behavioral_identity_recovery.
from core.novel.behavioral_identity_recovery import *  # noqa: F401,F403


# Private-symbol re-exports — `import *` skips underscore-prefixed
# names by Python convention, so expose the helpers that tests and
# external callers depend on explicitly.
from core.novel.behavioral_identity_recovery import (  # noqa: F401
    _activity_autocorrelation,
    _distribution_features,
    _shannon_entropy,
    _phase_peak,
    _burst_features,
    _feature_labels,
)
