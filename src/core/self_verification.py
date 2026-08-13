"""Compatibility shim — re-exports from core.physical.transduction_integrity."""
# This file exists so `from src.core.self_verification import X` still works
# after the restructuring to core/. The canonical location is core.physical.transduction_integrity.
from core.physical.transduction_integrity import *  # noqa: F401,F403


# Private-symbol re-exports — `import *` skips underscore-prefixed
# names by Python convention, so expose the helpers that tests and
# external callers depend on explicitly.
from core.physical.transduction_integrity import (  # noqa: F401
    _conn,
    _latest_key,
    _append_key,
    _verify_gk_chain,
    _evolve_gk,
    _get_json,
    _score_transduction_integrity,
    _score_component_fitness,
    _register_self_component_fitness,
    _iter_deployment_records,
    _score_validator_diversity,
    _score_feed_temporal_spacing,
)
