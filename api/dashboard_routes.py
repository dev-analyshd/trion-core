"""
TRION Institutional-Grade Dashboard Routes
==========================================

Blueprint serving the comprehensive multi-section dashboard. Each section
maps to a whitepaper concept and pulls live data from the existing Oracle
API and FAISS ANIMA engine.

Sections:
  /app                    — Main dashboard (overview)
  /app/akashic            — Akashic Index (behavioral memory)
  /app/bh-explorer        — Behavioral Hash live stream
  /app/anima              — ANIMA Intelligence (54 languages, 4 streams)
  /app/beo                — Behavioral Entity Object resolution
  /app/living-security    — 8-component DNA-mimetic security
  /app/validators         — Diversity-Weighted BFT validator mesh
  /app/annotators         — Conscious plane K(t) annotation network
  /app/evolutionary       — Evolutionary Fitness + Love Protocol
  /app/continuum          — CONTINUUM DEX (Hyperliquid-style)
  /app/btcp               — BTCP routing & escrow
  /app/marketplace        — Behavioral Data Marketplace
  /app/agent-id           — AI Agent Identity
  /app/timescale          — TimescaleDB live data
  /app/chains             — registry chain coverage matrix
  /app/settings           — Configuration & deployment
"""

from flask import Blueprint, render_template, jsonify, request, Response
import requests
import os
import json
import time

# ── TimescaleDB store (P0 fix: was referenced but never imported) ─────────────
# core/akashic/timescale_store.py provides get_timescale_store(); it degrades
# gracefully to None when psycopg2 is not installed or TIMESCALEDB_URL is unset.
try:
    from core.akashic.timescale_store import get_timescale_store, PSYCOPG2_OK as TIMESCALE_AVAILABLE
except ImportError:
    get_timescale_store = None
    TIMESCALE_AVAILABLE = False

dashboard_bp = Blueprint("dashboard_bp", __name__, url_prefix="/app")

def _redirect_to_react():
    """Redirect to the React frontend origin.

    The frontend is its own process (scripts/start_trion.sh runs it on port
    3000), so an absolute URL is needed — pointing back at "/" here bounced
    to the app root, which redirects to /app/, which redirected back to "/":
    a closed loop every browser rejects as too many redirects. FRONTEND_URL
    overrides the origin for non-default deployments.
    """
    from flask import redirect
    frontend = os.environ.get("FRONTEND_URL", "http://localhost:3000").rstrip("/")
    return redirect(frontend + "/")

FAISS_URL = os.environ.get("FAISS_SERVICE_URL", "http://127.0.0.1:8000")
ORACLE_URL = os.environ.get("ORACLE_INTERNAL_URL", "http://127.0.0.1:5000")


def _proxy(url, timeout=10):
    """Proxy a GET request to an internal service with graceful fallback."""
    try:
        r = requests.get(url, timeout=timeout)
        if r.status_code == 200:
            return r.json()
    except Exception:
        pass
    return None


@dashboard_bp.route("/")
def main_dashboard():
    """Main institutional dashboard — overview."""
    return _redirect_to_react()


@dashboard_bp.route("/akashic")
def akashic_page():
    """Akashic Index — behavioral memory, depth, archetypes."""
    return _redirect_to_react()


@dashboard_bp.route("/bh-explorer")
def bh_explorer_page():
    """Behavioral Hash live stream explorer."""
    return _redirect_to_react()


@dashboard_bp.route("/anima")
def anima_page():
    """ANIMA Intelligence — 4 data streams, 54 languages."""
    return _redirect_to_react()


@dashboard_bp.route("/beo")
def beo_page():
    """Behavioral Entity Object resolution."""
    return _redirect_to_react()


@dashboard_bp.route("/living-security")
def living_security_page():
    """8-component DNA-mimetic Living Security."""
    return _redirect_to_react()


@dashboard_bp.route("/validators")
def validators_page():
    """Diversity-Weighted BFT validator mesh."""
    return _redirect_to_react()


@dashboard_bp.route("/annotators")
def annotators_page():
    """Conscious plane K(t) annotation network."""
    return _redirect_to_react()


@dashboard_bp.route("/evolutionary")
def evolutionary_page():
    """Evolutionary Fitness + Love Protocol."""
    return _redirect_to_react()


@dashboard_bp.route("/continuum")
def continuum_page():
    """CONTINUUM DEX — behavioral clearing network."""
    return _redirect_to_react()


@dashboard_bp.route("/btcp")
def btcp_page():
    """BTCP routing & escrow."""
    return _redirect_to_react()


@dashboard_bp.route("/marketplace")
def marketplace_page():
    """Behavioral Data Marketplace."""
    return _redirect_to_react()


@dashboard_bp.route("/agent-id")
def agent_id_page():
    """AI Agent Identity."""
    return _redirect_to_react()


@dashboard_bp.route("/timescale")
def timescale_page():
    """TimescaleDB live data."""
    return _redirect_to_react()


@dashboard_bp.route("/chains")
def chains_page():
    """Registry chain coverage matrix (live count from chain_registry.json)."""
    return _redirect_to_react()


@dashboard_bp.route("/settings")
def settings_page():
    """Configuration & deployment settings."""
    return _redirect_to_react()


@dashboard_bp.route("/architecture")
def architecture_page():
    """System architecture — all 12+ programming languages live status."""
    return _redirect_to_react()


# ── Live data endpoints (aggregated for dashboard) ────────────────────────────

@dashboard_bp.route("/api/overview")
def api_overview():
    """Aggregated overview data — single call for main dashboard."""
    health = _proxy(f"{ORACLE_URL}/api/v1/health") or {}
    faiss = _proxy(f"{FAISS_URL}/health") or {}
    stats = _proxy(f"{ORACLE_URL}/api/v1/stats") or {}
    chains = _proxy(f"{ORACLE_URL}/api/v1/explorer/chains") or {}
    return jsonify({
        "oracle_health": health,
        "faiss_health": faiss,
        "stats": stats,
        "chains": chains,
        "timestamp": int(time.time()),
    })


@dashboard_bp.route("/api/bh-stream")
def api_bh_stream():
    """Server-Sent Events stream of recent BHs."""
    def generate():
        last_id = 0
        while True:
            try:
                r = requests.get(
                    f"{FAISS_URL}/bh/stats",
                    timeout=5,
                )
                if r.status_code == 200:
                    data = r.json()
                    yield f"data: {json.dumps(data)}\n\n"
            except Exception:
                pass
            time.sleep(2)
    return Response(generate(), mimetype="text/event-stream")


@dashboard_bp.route("/api/living-security-live")
def api_living_security_live():
    """Live GK evolution stream + 8-component status."""
    entity = request.args.get("entity", "TRION_PROTOCOL")
    data = _proxy(f"{FAISS_URL}/api/v1/living_security/{entity}") or {}
    gk = _proxy(f"{FAISS_URL}/api/v1/living_security/gk/{entity}") or {}
    immune = _proxy(f"{FAISS_URL}/api/v1/living_security/immune/{entity}") or {}
    epi = _proxy(f"{FAISS_URL}/api/v1/living_security/epigenetic") or {}
    mito = _proxy(f"{FAISS_URL}/api/v1/living_security/mitochondrial") or {}
    crispr = _proxy(f"{FAISS_URL}/api/v1/crispr/signatures") or {}
    return jsonify({
        "composite": data,
        "genomic_key": gk,
        "immune": immune,
        "epigenetic": epi,
        "mitochondrial": mito,
        "crispr_library": crispr,
        "entity": entity,
        "timestamp": int(time.time()),
    })


@dashboard_bp.route("/api/validators-live")
def api_validators_live():
    """Live validator mesh data."""
    spiritual = _proxy(f"{FAISS_URL}/api/v1/spiritual/validators") or {}
    hhi = _proxy(f"{FAISS_URL}/api/v1/hhi_enforcement") or {}
    diversity = _proxy(f"{FAISS_URL}/api/v1/spiritual/diversity_report") or {}
    geo = _proxy(f"{ORACLE_URL}/api/v1/governance/geo") or {}
    return jsonify({
        "validators": spiritual,
        "hhi": hhi,
        "diversity": diversity,
        "geographic": geo,
        "timestamp": int(time.time()),
    })


@dashboard_bp.route("/api/annotators-live")
def api_annotators_live():
    """Live annotator registry."""
    annotators = _proxy(f"{FAISS_URL}/api/v1/conscious/annotators") or {}
    knowledge = _proxy(f"{FAISS_URL}/api/v1/conscious/knowledge_systems") or {}
    elders = _proxy(f"{FAISS_URL}/api/v1/conscious/elders") or {}
    return jsonify({
        "annotators": annotators,
        "knowledge_systems": knowledge,
        "elders": elders,
        "timestamp": int(time.time()),
    })


@dashboard_bp.route("/api/evolutionary-live")
def api_evolutionary_live():
    """Live evolutionary fitness + love protocol data."""
    fitness = _proxy(f"{FAISS_URL}/fitness") or {}
    awa = _proxy(f"{ORACLE_URL}/api/v1/governance/awa") or {}
    gratitude = _proxy(f"{ORACLE_URL}/api/v1/governance/gratitude") or {}
    bootstrap = _proxy(f"{ORACLE_URL}/api/v1/bootstrap/status") or {}
    return jsonify({
        "fitness": fitness,
        "awa": awa,
        "gratitude": gratitude,
        "bootstrap": bootstrap,
        "timestamp": int(time.time()),
    })


@dashboard_bp.route("/api/anima-live")
def api_anima_live():
    """Live ANIMA intelligence data."""
    im = _proxy(f"{ORACLE_URL}/api/v1/anima/intelligence") or {}
    sources = _proxy(f"{FAISS_URL}/api/v1/anima/system/sources") or {}
    mg = _proxy(f"{FAISS_URL}/api/v1/anima/system/manifestation_gap") or {}
    crawl = _proxy(f"{FAISS_URL}/api/v1/anima/crawl/TRION_PROTOCOL") or {}
    return jsonify({
        "intelligence_maintenance": im,
        "sources": sources,
        "manifestation_gap": mg,
        "crawl": crawl,
        "timestamp": int(time.time()),
    })


@dashboard_bp.route("/api/beo-live")
def api_beo_live():
    """Live BEO entity resolution data."""
    archetypes = _proxy(f"{FAISS_URL}/api/v1/akashic/archetypes") or {}
    audit = _proxy(f"{FAISS_URL}/api/v1/audit/patterns/library") or {}
    return jsonify({
        "archetypes": archetypes,
        "audit_patterns": audit,
        "timestamp": int(time.time()),
    })


@dashboard_bp.route("/api/continuum-live")
def api_continuum_live():
    """Live CONTINUUM DEX data."""
    btcp = _proxy(f"{FAISS_URL}/api/v1/btcp/score") or {}
    pairs = _proxy(f"{ORACLE_URL}/api/v1/price/pairs") or {}
    liquidity = _proxy(f"{ORACLE_URL}/api/v1/liquidity/ETH") or {}
    return jsonify({
        "btcp": btcp,
        "pairs": pairs,
        "liquidity": liquidity,
        "timestamp": int(time.time()),
    })


@dashboard_bp.route("/api/timescale-live")
def api_timescale_live():
    """Live TimescaleDB statistics from the Akashic Index."""
    # FAISS proxy data (backward compatible)
    bh_stats = _proxy(f"{FAISS_URL}/bh/stats") or {}
    conservation = _proxy(f"{FAISS_URL}/conservation/status") or {}
    
    # TimescaleDB live data
    timescale_data = {"available": False}
    if TIMESCALE_AVAILABLE and get_timescale_store:
        store = get_timescale_store()
        if store and store.available:
            timescale_data = store.get_stats()
    
    return jsonify({
        "bh_stats": bh_stats,
        "conservation": conservation,
        "timescale": timescale_data,
        "timestamp": int(time.time()),
    })


@dashboard_bp.route("/api/timescale/health")
def api_timescale_health():
    """TimescaleDB connection health check."""
    if not TIMESCALE_AVAILABLE or not get_timescale_store:
        return jsonify({"status": "unavailable", "reason": "psycopg2 not installed"}), 503
    store = get_timescale_store()
    health = store.health_check()
    status_code = 200 if health.get("status") == "healthy" else 503
    return jsonify(health), status_code


@dashboard_bp.route("/api/timescale/stats")
def api_timescale_stats():
    """Comprehensive Akashic Index statistics from TimescaleDB."""
    if not TIMESCALE_AVAILABLE or not get_timescale_store:
        return jsonify({"available": False, "error": "timescale_unavailable"}), 503
    store = get_timescale_store()
    if not store.available:
        return jsonify({"available": False, "error": "not_configured"}), 503
    return jsonify(store.get_stats())


@dashboard_bp.route("/api/timescale/activity")
@dashboard_bp.route("/api/timescale/activity/<int:hours>")
def api_timescale_activity(hours: int = 24):
    """Recent activity across all entities in the Akashic Index."""
    if not TIMESCALE_AVAILABLE or not get_timescale_store:
        return jsonify({"available": False, "error": "timescale_unavailable"}), 503
    store = get_timescale_store()
    if not store.available:
        return jsonify({"available": False, "error": "not_configured"}), 503
    hours = max(1, min(hours, 168))  # clamp to 1-168 hours
    activity = store.get_recent_activity(hours)
    return jsonify({
        "hours": hours,
        "activity_count": len(activity),
        "activity": activity,
        "timestamp": int(time.time()),
    })


@dashboard_bp.route("/api/timescale/entity/<path:entity_id>/depth")
def api_timescale_entity_depth(entity_id: str):
    """Get Akashic depth statistics for a specific entity."""
    if not TIMESCALE_AVAILABLE or not get_timescale_store:
        return jsonify({"available": False, "error": "timescale_unavailable"}), 503
    store = get_timescale_store()
    if not store.available:
        return jsonify({"available": False, "error": "not_configured"}), 503
    
    # Convert entity_id to bytes (handle hex strings)
    try:
        if entity_id.startswith("0x"):
            entity_bytes = bytes.fromhex(entity_id[2:])
        elif len(entity_id) == 64:
            entity_bytes = bytes.fromhex(entity_id)
        else:
            entity_bytes = entity_id.encode()
    except ValueError:
        entity_bytes = entity_id.encode()
    
    depth = store.get_akashic_depth(entity_bytes)
    return jsonify({
        "entity_id": entity_id,
        "depth": depth,
        "timestamp": int(time.time()),
    })


@dashboard_bp.route("/api/timescale/entity/<path:entity_id>/bhs")
@dashboard_bp.route("/api/timescale/entity/<path:entity_id>/bhs/<int:limit>")
def api_timescale_entity_bhs(entity_id: str, limit: int = 100):
    """Get recent behavioral hashes for a specific entity."""
    if not TIMESCALE_AVAILABLE or not get_timescale_store:
        return jsonify({"available": False, "error": "timescale_unavailable"}), 503
    store = get_timescale_store()
    if not store.available:
        return jsonify({"available": False, "error": "not_configured"}), 503
    
    try:
        if entity_id.startswith("0x"):
            entity_bytes = bytes.fromhex(entity_id[2:])
        elif len(entity_id) == 64:
            entity_bytes = bytes.fromhex(entity_id)
        else:
            entity_bytes = entity_id.encode()
    except ValueError:
        entity_bytes = entity_id.encode()
    
    limit = max(1, min(limit, 1000))
    bhs = store.get_entity_bh(entity_bytes, limit)
    return jsonify({
        "entity_id": entity_id,
        "bh_count": len(bhs),
        "behavioral_hashes": bhs,
        "timestamp": int(time.time()),
    })


@dashboard_bp.route("/api/chains-live")
def api_chains_live():
    """Live chain coverage matrix."""
    chains = _proxy(f"{ORACLE_URL}/api/v1/explorer/chains") or {}
    return jsonify({
        "chains": chains,
        "timestamp": int(time.time()),
    })


@dashboard_bp.route("/api/architecture-live")
def api_architecture_live():
    """Live status of all 12+ programming languages."""
    import sys
    sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))
    from core.native_bridge import native_stack_report, run_formal_verification, run_go_crawler_coordinator_selftest, run_go_validator_mesh_selftest, compute_fft_features
    import math
    demo_signal = [round(0.5 + 0.4 * math.sin(i * 0.6), 4) for i in range(32)]
    return jsonify({
        "languages": native_stack_report(),
        "haskell_verification": run_formal_verification(),
        "go_crawler_selftest": run_go_crawler_coordinator_selftest(),
        "go_validator_selftest": run_go_validator_mesh_selftest(),
        "cpp_fft_live_sample": compute_fft_features(demo_signal),
        "timestamp": int(time.time()),
    })
