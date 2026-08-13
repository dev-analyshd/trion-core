"""Compatibility shim — re-exports from core.price.behavioral_price_engine."""
# This file exists so `from src.price.behavioral_price_engine import X` still works
# after the restructuring to core/. The canonical location is core.price.behavioral_price_engine.
from core.price.behavioral_price_engine import *  # noqa: F401,F403


# Private-symbol re-exports — `import *` skips underscore-prefixed
# names by Python convention, so expose the helpers that tests and
# external callers depend on explicitly.
from core.price.behavioral_price_engine import (  # noqa: F401
    _fetch_cg_batch,
    _prefetch_cg_prices,
    _fetch_cex_reference,
    _fetch_bh_stats,
    _SIGNAL_TIMEOUT,
    _fetch_coherence_for_asset,
    _fetch_nl_score,
    _compute_source_diversity,
    _get_hardcoded_reference,
)
