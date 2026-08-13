"""Compatibility shim — re-exports from core.governance.open_research_questions."""
# This file exists so `from src.governance.open_research_questions import X` still works
# after the restructuring to core/. The canonical location is core.governance.open_research_questions.
from core.governance.open_research_questions import *  # noqa: F401,F403
