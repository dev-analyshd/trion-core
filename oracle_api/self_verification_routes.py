"""
self_verification_routes.py — exposes TRION's reflexive self-verification.

GET /api/v1/self             Latest self-coherence record (persisted GK chain tip)
POST /api/v1/self/cycle      Force an immediate verification cycle (debug/manual)
"""

import os
import sys
import logging
from flask import Blueprint, jsonify

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

log = logging.getLogger(__name__)
self_verification_bp = Blueprint("self_verification", __name__)

ORACLE_API_URL = os.environ.get("ORACLE_API_URL", "http://127.0.0.1:5000")
FAISS_URL = os.environ.get("FAISS_URL", "http://127.0.0.1:8000")

try:
    from src.core.self_verification import (
        start_self_verification_monitor,
        get_self_status,
        run_self_verification_cycle,
    )
    _available = True
except Exception as _err:
    _available = False
    log.warning("Self-verification module unavailable: %s", _err)


def _lazy_feed_push(entry: dict) -> None:
    """
    Lazy lookup of app._feed_push, same pattern as protocol_monitor.py.
    Registration happens before app.py finishes defining _feed_push, so we
    must resolve it at push-time, not at blueprint-registration time.
    """
    try:
        app_mod = sys.modules.get("app") or sys.modules.get("oracle_api.app")
        if app_mod and hasattr(app_mod, "_feed_push"):
            app_mod._feed_push(entry)
            return
        import importlib
        mod = importlib.import_module("app")
        if hasattr(mod, "_feed_push"):
            mod._feed_push(entry)
    except Exception as exc:
        log.debug("self_verification: feed push failed: %s", exc)


@self_verification_bp.record_once
def _start_self_verification_monitor(state):
    if not _available:
        return
    try:
        start_self_verification_monitor(ORACLE_API_URL, FAISS_URL, _lazy_feed_push, interval_seconds=120)
        log.info("Self-verification monitor started via blueprint.record_once")
    except Exception as exc:
        log.warning("Self-verification monitor could not start: %s", exc)


@self_verification_bp.route("/api/v1/self")
def self_status():
    if not _available:
        return jsonify({"error": "self-verification module unavailable"}), 503
    return jsonify(get_self_status())


@self_verification_bp.route("/api/v1/self/cycle", methods=["POST"])
def self_cycle():
    if not _available:
        return jsonify({"error": "self-verification module unavailable"}), 503
    record = run_self_verification_cycle(ORACLE_API_URL, FAISS_URL)
    try:
        app_mod = sys.modules.get("app") or sys.modules.get("oracle_api.app")
        if app_mod and hasattr(app_mod, "_feed_push"):
            app_mod._feed_push(record)
    except Exception:
        pass
    return jsonify(record)
