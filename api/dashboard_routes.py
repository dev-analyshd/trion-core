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
  /app/chains             — 100-chain coverage matrix
  /app/settings           — Configuration & deployment
"""

from flask import Blueprint, render_template, jsonify, request, Response
import requests
import os
import json
import time

dashboard_bp = Blueprint("dashboard_bp", __name__, url_prefix="/app")

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
    return render_template("pages/main.html", active_page="main")


@dashboard_bp.route("/akashic")
def akashic_page():
    """Akashic Index — behavioral memory, depth, archetypes."""
    return render_template("pages/akashic.html", active_page="akashic")


@dashboard_bp.route("/bh-explorer")
def bh_explorer_page():
    """Behavioral Hash live stream explorer."""
    return render_template("pages/bh_explorer.html", active_page="bh")


@dashboard_bp.route("/anima")
def anima_page():
    """ANIMA Intelligence — 4 data streams, 54 languages."""
    return render_template("pages/anima.html", active_page="anima")


@dashboard_bp.route("/beo")
def beo_page():
    """Behavioral Entity Object resolution."""
    return render_template("pages/beo.html", active_page="beo")


@dashboard_bp.route("/living-security")
def living_security_page():
    """8-component DNA-mimetic Living Security."""
    return render_template("pages/living_security.html", active_page="security")


@dashboard_bp.route("/validators")
def validators_page():
    """Diversity-Weighted BFT validator mesh."""
    return render_template("pages/validators.html", active_page="validators")


@dashboard_bp.route("/annotators")
def annotators_page():
    """Conscious plane K(t) annotation network."""
    return render_template("pages/annotators.html", active_page="annotators")


@dashboard_bp.route("/evolutionary")
def evolutionary_page():
    """Evolutionary Fitness + Love Protocol."""
    return render_template("pages/evolutionary.html", active_page="evolutionary")


@dashboard_bp.route("/continuum")
def continuum_page():
    """CONTINUUM DEX — behavioral clearing network."""
    return render_template("pages/continuum.html", active_page="continuum")


@dashboard_bp.route("/btcp")
def btcp_page():
    """BTCP routing & escrow."""
    return render_template("pages/btcp.html", active_page="btcp")


@dashboard_bp.route("/marketplace")
def marketplace_page():
    """Behavioral Data Marketplace."""
    return render_template("pages/marketplace.html", active_page="marketplace")


@dashboard_bp.route("/agent-id")
def agent_id_page():
    """AI Agent Identity."""
    return render_template("pages/agent_id.html", active_page="agent_id")


@dashboard_bp.route("/timescale")
def timescale_page():
    """TimescaleDB live data."""
    return render_template("pages/timescale.html", active_page="timescale")


@dashboard_bp.route("/chains")
def chains_page():
    """100-chain coverage matrix."""
    return render_template("pages/chains.html", active_page="chains")


@dashboard_bp.route("/settings")
def settings_page():
    """Configuration & deployment settings."""
    return render_template("pages/settings.html", active_page="settings")


@dashboard_bp.route("/architecture")
def architecture_page():
    """System architecture — all 12+ programming languages live status."""
    return render_template("pages/architecture.html", active_page="architecture")


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
    """Live TimescaleDB statistics."""
    bh_stats = _proxy(f"{FAISS_URL}/bh/stats") or {}
    conservation = _proxy(f"{FAISS_URL}/conservation/status") or {}
    return jsonify({
        "bh_stats": bh_stats,
        "conservation": conservation,
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
    from src.native_bridge import native_stack_report, run_formal_verification, run_go_crawler_coordinator_selftest, run_go_validator_mesh_selftest, compute_fft_features
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
