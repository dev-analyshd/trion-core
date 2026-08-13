"""Compatibility shim — re-exports from core.novel.birp."""
# This file exists so `from src.signals.birp import X` still works
# after the restructuring to core/. The canonical location is core.novel.birp.
from core.novel.birp import *  # noqa: F401,F403


# Private-symbol re-exports — `import *` skips underscore-prefixed
# names by Python convention, so expose the helpers that tests and
# external callers depend on explicitly.
from core.novel.birp import (  # noqa: F401
    _complement,
    _hash_dna,
    _verify_xor_invariant,
    _merkle_root,
)
