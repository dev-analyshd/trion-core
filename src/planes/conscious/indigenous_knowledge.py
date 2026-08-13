"""Compatibility shim — re-exports from core.spiritual.conscious.indigenous_knowledge."""
# This file exists so `from src.planes.conscious.indigenous_knowledge import X` still works
# after the restructuring to core/. The canonical location is core.spiritual.conscious.indigenous_knowledge.
from core.spiritual.conscious.indigenous_knowledge import *  # noqa: F401,F403


# Private-symbol re-exports — `import *` skips underscore-prefixed
# names by Python convention, so expose the helpers that tests and
# external callers depend on explicitly.
from core.spiritual.conscious.indigenous_knowledge import (  # noqa: F401
    _IK_DB_PATH,
    _ik_conn,
    _init_ik_db,
)
