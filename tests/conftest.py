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
    # Script-style E2E harnesses: require a live Oracle/FAISS stack and call
    # sys.exit() at module level. Run them explicitly via `python tests/<file>.py`
    # after starting services (see scripts/ and docs/DEPLOYMENT.md).
    "live_rpc_test.py",
    "per_vm_e2e_test.py",
    # Golden Test: boots in-process services and executes the full Phase-9
    # workflow. Run explicitly: `python tests/golden_test.py`
    "golden_test.py",
]
