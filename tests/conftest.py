"""TRION Protocol — pytest configuration"""
import sys
import os

# Add root to sys.path so `from core.*` imports work.
# (The legacy `src/` shim layer was removed in FIX-4 — all Python imports
# now point directly at `core/*` canonical locations per the v2 restructuring.)
ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)
sys.path.insert(0, os.path.join(ROOT, "api"))
sys.path.insert(0, os.path.join(ROOT, "anima-service"))
sys.path.insert(0, os.path.join(ROOT, "zg"))

# Exclude live-service tests from default collection
collect_ignore = [
    "integration/test_e2e_full.py",
    "integration/test_chain_integrations.py",
    "integration/test_vision_expansion.py",
]
