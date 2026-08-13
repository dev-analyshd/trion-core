"""Compatibility shim — re-exports from core.spiritual.living_security.pqc_layer."""
# This file exists so `from src.security.pqc_layer import X` still works
# after the restructuring to core/. The canonical location is core.spiritual.living_security.pqc_layer.
from core.spiritual.living_security.pqc_layer import *  # noqa: F401,F403


# Private-symbol re-exports — `import *` skips underscore-prefixed
# names by Python convention, so expose the helpers that tests and
# external callers depend on explicitly.
from core.spiritual.living_security.pqc_layer import (  # noqa: F401
    _ML_KEM_BY_LEVEL,
    _ML_DSA_BY_LEVEL,
    _SPHINCS_BY_LEVEL,
    _real_kyber_roundtrip,
    _real_dilithium_roundtrip,
    _real_sphincs_roundtrip,
)
