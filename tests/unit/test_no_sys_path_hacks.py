"""Sys.path hygiene guard — RESTRUCTURE_PLAN Phase 0 (P3-CONSOLIDATE).

The repo currently carries 68 files that bootstrap imports with
``sys.path.insert`` — the fragility the docs/architecture/RESTRUCTURE_PLAN.md
migration must eliminate (the `anima-service` hyphen is the root cause).

This test pins the snapshot: NO NEW file may introduce a sys.path.insert
hack. Migrations that REMOVE or MOVE files only shrink the live set —
moves require the allow-list below to be updated in the same commit
(which is exactly the point: import rewires must be conscious).
"""
import os

from core import generated_chain_bindings  # noqa: F401  (canonical-import sanity)

ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", ".."))

# Searched via concatenation so this file does not match its own scan.
_TOKEN = "sys.path" + ".insert"

# Runtime/build dirs (mirror .gitignore) — never scanned.
_SKIP_DIRS = {
    ".git", "__pycache__", "node_modules", "venv", ".venv",
    ".pytest_cache", ".pythonlibs", ".uv", "target", "build", "dist",
    "bin", "data", "tmp", "0g-state", "faiss_index",
}

_THIS_FILE = os.path.relpath(os.path.abspath(__file__), ROOT)

# Snapshot at P3-CONSOLIDATE time (68 files). Order irrelevant.
_ALLOWLIST = frozenset({
    "anima-service/batch_contract_audit.py",
    "anima-service/faiss_service.py",
    "anima-service/nl_score_engine.py",
    "api/app.py",
    "api/dashboard_routes.py",
    "api/price_feed_routes.py",
    "api/protocol_routes.py",
    "api/self_verification_routes.py",
    "api/socket_push.py",
    "core/agent/safety_pipeline.py",
    "core/akashic/bibl.py",
    "core/akashic/epigenetics.py",
    "core/auditor/contract_auditor.py",
    "core/btcp/integration.py",
    "core/btcp/orchestrator.py",
    "core/master/signal_factory.py",
    "core/master/trion_primitives.py",
    "core/mental/anima/data_streams.py",
    "core/mental/anima/engine.py",
    "core/trading/agent_interface.py",
    "core/trading/signal_engine.py",
    "main.py",
    "scripts/cross_lang_bh_check.py",
    "scripts/deep_resonance_test.py",
    "scripts/deploy_and_activate.py",
    "scripts/generate_beo_report.py",
    "scripts/init_trion.py",
    "scripts/live_beo_proof.py",
    "scripts/run_bh_streamer.py",
    "scripts/simulate_attacks.py",
    "scripts/tests/integration_test.py",
    "serve.py",
    "tests/adversarial/test_adversarial_matrix.py",
    "tests/adversarial/test_adversarial_suite.py",
    "tests/adversarial/test_protocol_distribution_coherence.py",
    "tests/adversarial/test_protocol_health.py",
    "tests/adversarial/test_protocol_role_classifier.py",
    "tests/adversarial/test_protocol_segmentation.py",
    "tests/bh_pipeline_test.py",
    "tests/chain_coverage_audit.py",
    "tests/conftest.py",
    "tests/golden_test.py",
    "tests/integration/test_akashic_category4.py",
    "tests/integration/test_anima_full.py",
    "tests/integration/test_anima_live_ingestion.py",
    "tests/integration/test_beo_cross_chain_vm.py",
    "tests/integration/test_btcp_cross_chain_e2e.py",
    "tests/integration/test_deep_vm_and_zg.py",
    "tests/integration/test_e2e_full.py",
    "tests/integration/test_vision_expansion.py",
    "tests/invention_verification.py",
    "tests/master_formula_verification.py",
    "tests/per_vm_e2e_test.py",
    "tests/test_anima_stress_1000.py",
    "tests/test_btcp_bitp_sba_bibl.py",
    "tests/test_gk_living_security.py",
    "tests/unit/test_all_planes.py",
    "tests/unit/test_stress.py",
    "tests/unit/test_trading_signals.py",
    "tests/unit/trion_protocol/test_archetype_engine.py",
    "tests/unit/trion_protocol/test_bh_collision_resistance.py",
    "tests/unit/trion_protocol/test_conformal_predictor.py",
    "tests/unit/trion_protocol/test_consensus_bft.py",
    "tests/unit/trion_protocol/test_feature_extractor.py",
    "tests/unit/trion_protocol/test_five_plane_c.py",
    "zg/zg_api_routes.py",
    "zg/zg_da_streamer.py",
    "zg/zg_sync_daemon.py",
})


def _files_with_path_hack():
    found = set()
    for dirpath, dirnames, filenames in os.walk(ROOT):
        dirnames[:] = [d for d in dirnames
                       if d not in _SKIP_DIRS and not d.startswith(".")]
        for fn in filenames:
            if not fn.endswith(".py"):
                continue
            full = os.path.join(dirpath, fn)
            rel = os.path.relpath(full, ROOT)
            if rel == _THIS_FILE:
                continue
            try:
                with open(full, encoding="utf-8", errors="replace") as f:
                    src = f.read()
            except OSError:
                continue
            if _TOKEN in src:
                found.add(rel)
    return found


def test_no_new_sys_path_hacks():
    """A NEW sys.path.insert is a defect: fix the import instead.

    Migrations per docs/architecture/RESTRUCTURE_PLAN.md only shrink this
    set (files moved/deleted drop out; the allow-list is updated in the
    same commit as the move).
    """
    live = _files_with_path_hack()
    new_hacks = sorted(live - _ALLOWLIST)
    assert not new_hacks, (
        "New sys.path.insert hacks introduced (RESTRUCTURE_PLAN Phase 0 "
        "violated — rewire the import to a package path instead):\n  "
        + "\n  ".join(new_hacks)
    )


def test_hack_count_is_shrinking_not_growing():
    """Even within the allow-listed files, the live hack count must not
    exceed the P3-CONSOLIDATE snapshot of 68."""
    live = _files_with_path_hack()
    assert len(live) <= len(_ALLOWLIST), (
        f"sys.path.insert file count grew: {len(live)} > "
        f"{len(_ALLOWLIST)} (snapshot at P3-CONSOLIDATE)"
    )
