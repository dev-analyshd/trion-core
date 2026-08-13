"""Compatibility shim — re-exports from core.auditor.contract_auditor."""
# This file exists so `from src.auditor.contract_auditor import X` still works
# after the restructuring to core/. The canonical location is core.auditor.contract_auditor.
from core.auditor.contract_auditor import *  # noqa: F401,F403
