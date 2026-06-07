"""
protocol_routes.py — TRION Protocol-Contract Intelligence API

Solves the many-to-one identity aggregation problem for DeFi protocol
contracts. Instead of scoring the contract address as a single entity
(which produces incoherent Mental-plane scores), this module decomposes
protocol activity into (contract, caller) sub-entities, each with a
meaningful behavioral identity.

ENDPOINTS
---------
GET  /api/v1/protocol/<address>/health             Aggregate H(t) score
GET  /api/v1/protocol/<address>/users              Top caller sub-entities
GET  /api/v1/protocol/<address>/roles              Role distribution breakdown
GET  /api/v1/protocol/<address>/attack-surface     Anomaly + attack detection
GET  /api/v1/protocol/<address>/distribution       Jensen-Shannon coherence
GET  /api/v1/protocol/<address>/sub-entities       Raw (contract, caller) pairs
GET  /api/v1/protocol/supported-roles              Role taxonomy reference
"""

import os
import sys
import time
import logging
from flask import Blueprint, jsonify, request

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

log = logging.getLogger(__name__)
protocol_bp = Blueprint("protocol", __name__)

try:
    from src.protocol.protocol_health import ProtocolHealthEngine
    from src.protocol.segmentation import ProtocolSegmenter
    from src.protocol.role_classifier import RoleClassifier, DeFiRole
    from src.protocol.distribution_coherence import DistributionCoherenceEngine
    _engine = ProtocolHealthEngine()
    _segmenter = ProtocolSegmenter()
    _classifier = RoleClassifier()
    _dc_engine = DistributionCoherenceEngine()
    _available = True
    log.info("Protocol intelligence engine loaded")
except Exception as _err:
    _available = False
    _engine = None
    log.warning("Protocol engine unavailable: %s", _err)

# ── Start background protocol monitor when blueprint is registered ────────────
@protocol_bp.record_once
def _start_protocol_monitor(state):
    if not _available:
        return
    try:
        from protocol_monitor import start_monitor
        start_monitor(_engine)
        log.info("Protocol monitor started via blueprint.record_once")
    except Exception as _mon_err:
        log.warning("Protocol monitor could not start: %s", _mon_err)


def _unavailable():
    return jsonify({"error": "Protocol intelligence engine not available", "status": 503}), 503


def _validate_address(address: str) -> str:
    return address.lower().strip()


# ── /api/v1/protocol/<address>/health ────────────────────────────────────────

@protocol_bp.route("/api/v1/protocol/<address>/health", methods=["GET"])
def protocol_health(address: str):
    """
    Aggregate protocol health score H(t) decomposed into 4 components:
      - Distribution Coherence (35%): JSD-based Mental-plane substitute
      - Role Coherence (20%): Diversity + stability of user role mix
      - User Quality (30%): Behavioural confidence of top callers
      - Attack Surface (15%): 1 - attack_probability
    """
    if not _available:
        return _unavailable()

    addr = _validate_address(address)
    top_n = min(int(request.args.get("top_n", 50)), 200)
    window = int(request.args.get("window_seconds", 3600))

    t0 = time.time()
    result = _engine.compute(addr, top_n=top_n, window_seconds=window)
    elapsed = round(time.time() - t0, 3)

    return jsonify({
        "status": "ok",
        "address": addr,
        "health_score": result.health_score,
        "grade": result.grade,
        "components": result.components,
        "role_distribution": result.role_distribution,
        "sub_entity_count": result.sub_entity_count,
        "attacker_count": len(result.attacker_wallets),
        "recommendations": result.recommendations,
        "dc_summary": {
            "distribution_coherence": result.dc_result.get("distribution_coherence"),
            "attack_probability": result.dc_result.get("attack_probability"),
            "interpretation": result.dc_result.get("interpretation"),
        },
        "computed_at": result.computed_at,
        "elapsed_ms": elapsed * 1000,
    })


# ── /api/v1/protocol/<address>/users ─────────────────────────────────────────

@protocol_bp.route("/api/v1/protocol/<address>/users", methods=["GET"])
def protocol_users(address: str):
    """
    Returns ranked list of (contract, caller) sub-entities with role
    classification, risk level, and behavioral metrics.
    """
    if not _available:
        return _unavailable()

    addr = _validate_address(address)
    limit = min(int(request.args.get("limit", 50)), 200)
    role_filter = request.args.get("role")
    risk_filter = request.args.get("risk")

    sub_entities = _segmenter.get_sub_entities(addr, limit=limit)
    classified = _classifier.classify_batch(sub_entities)

    users = []
    for se, role_res in classified:
        if role_filter and role_res.role.value != role_filter.upper():
            continue
        if risk_filter and role_res.risk_level != risk_filter.upper():
            continue
        users.append({
            "caller": se.caller,
            "contract": se.contract,
            "role": role_res.role.value,
            "archetype": role_res.archetype,
            "risk_level": role_res.risk_level,
            "confidence": role_res.confidence,
            "tx_count": se.tx_count,
            "dominant_event": se.dominant_event,
            "event_type_counts": se.event_type_counts,
            "magnitude_mean": se.magnitude_stats.get("mean", 0),
            "magnitude_p95": se.magnitude_stats.get("p95", 0),
            "chains": se.chains,
            "first_seen": se.first_seen,
            "last_seen": se.last_seen,
            "evidence": role_res.evidence,
        })

    return jsonify({
        "status": "ok",
        "address": addr,
        "total": len(users),
        "users": users,
        "filters": {"role": role_filter, "risk": risk_filter},
    })


# ── /api/v1/protocol/<address>/roles ─────────────────────────────────────────

@protocol_bp.route("/api/v1/protocol/<address>/roles", methods=["GET"])
def protocol_roles(address: str):
    """
    Role distribution breakdown for the protocol's user base.
    Includes risk concentration analysis and dominant behaviour summary.
    """
    if not _available:
        return _unavailable()

    addr = _validate_address(address)
    limit = min(int(request.args.get("limit", 100)), 500)

    sub_entities = _segmenter.get_sub_entities(addr, limit=limit)
    classified = _classifier.classify_batch(sub_entities)

    role_stats: dict = {}
    for se, role_res in classified:
        r = role_res.role.value
        if r not in role_stats:
            role_stats[r] = {
                "count": 0, "total_tx": 0,
                "archetype": role_res.archetype,
                "risk_level": role_res.risk_level,
                "description": role_res.description,
                "avg_confidence": 0.0,
                "confidences": [],
            }
        role_stats[r]["count"] += 1
        role_stats[r]["total_tx"] += se.tx_count
        role_stats[r]["confidences"].append(role_res.confidence)

    total_users = sum(s["count"] for s in role_stats.values())
    roles_out = []
    for role_name, stats in sorted(role_stats.items(), key=lambda x: -x[1]["count"]):
        confs = stats.pop("confidences")
        stats["share"] = round(stats["count"] / total_users, 4) if total_users > 0 else 0
        stats["avg_confidence"] = round(sum(confs) / len(confs), 4) if confs else 0
        roles_out.append({"role": role_name, **stats})

    high_risk = sum(s["count"] for s in role_stats.values() if s.get("risk_level") == "HIGH")
    risk_concentration = round(high_risk / total_users, 4) if total_users > 0 else 0

    return jsonify({
        "status": "ok",
        "address": addr,
        "total_users_sampled": total_users,
        "role_breakdown": roles_out,
        "risk_concentration": risk_concentration,
        "dominant_role": roles_out[0]["role"] if roles_out else "UNKNOWN",
    })


# ── /api/v1/protocol/<address>/attack-surface ────────────────────────────────

@protocol_bp.route("/api/v1/protocol/<address>/attack-surface", methods=["GET"])
def protocol_attack_surface(address: str):
    """
    Attack surface analysis combining:
      - Anomalous event-type spikes vs baseline
      - Flash loan / liquidation concentration
      - High-risk caller identification
      - Distribution Coherence score
    """
    if not _available:
        return _unavailable()

    addr = _validate_address(address)
    window = int(request.args.get("window_seconds", 3600))

    current_dist = _segmenter.get_protocol_activity(addr, window_seconds=window)
    global_dist = _segmenter.get_global_activity(window_seconds=window * 24)
    _dc_engine.update_baseline(addr, global_dist or current_dist)
    dc_result = _dc_engine.compute(addr, current_dist)

    sub_entities = _segmenter.get_sub_entities(addr, limit=100)
    classified = _classifier.classify_batch(sub_entities)
    attackers = [
        {
            "caller": se.caller,
            "role": role_res.role.value,
            "risk_level": role_res.risk_level,
            "confidence": role_res.confidence,
            "tx_count": se.tx_count,
            "dominant_event": se.dominant_event,
            "magnitude_p95": se.magnitude_stats.get("p95", 0),
        }
        for se, role_res in classified
        if role_res.risk_level == "HIGH" and role_res.confidence > 0.4
    ]

    threat_level = _threat_level(
        dc_result.get("attack_probability", 0),
        dc_result.get("distribution_coherence", 1),
        len(attackers),
        len(sub_entities),
    )

    return jsonify({
        "status": "ok",
        "address": addr,
        "threat_level": threat_level,
        "attack_probability": dc_result.get("attack_probability"),
        "distribution_coherence": dc_result.get("distribution_coherence"),
        "interpretation": dc_result.get("interpretation"),
        "anomalous_events": dc_result.get("anomalous_events", []),
        "high_risk_callers": attackers,
        "high_risk_count": len(attackers),
        "total_sampled": len(sub_entities),
        "window_seconds": window,
    })


def _threat_level(attack_prob: float, dc: float, attacker_count: int, total: int) -> str:
    ratio = attacker_count / max(total, 1)
    score = attack_prob * 0.5 + (1 - dc) * 0.3 + ratio * 0.2
    if score >= 0.6:
        return "CRITICAL"
    if score >= 0.4:
        return "HIGH"
    if score >= 0.2:
        return "MEDIUM"
    return "LOW"


# ── /api/v1/protocol/<address>/distribution ──────────────────────────────────

@protocol_bp.route("/api/v1/protocol/<address>/distribution", methods=["GET"])
def protocol_distribution(address: str):
    """
    Jensen-Shannon divergence between current and baseline event-type
    distribution. Core of the distribution-coherence Mental-plane substitute.
    """
    if not _available:
        return _unavailable()

    addr = _validate_address(address)
    window = int(request.args.get("window_seconds", 3600))

    current_dist = _segmenter.get_protocol_activity(addr, window_seconds=window)
    global_dist = _segmenter.get_global_activity(window_seconds=window * 24)
    _dc_engine.update_baseline(addr, global_dist or current_dist)
    dc_result = _dc_engine.compute(
        addr, current_dist, window_label=f"{window // 3600}h"
    )

    return jsonify({
        "status": "ok",
        "address": addr,
        **dc_result,
        "window_seconds": window,
    })


# ── /api/v1/protocol/<address>/sub-entities ──────────────────────────────────

@protocol_bp.route("/api/v1/protocol/<address>/sub-entities", methods=["GET"])
def protocol_sub_entities(address: str):
    """
    Raw (contract, caller) pair list with event statistics.
    The foundation of protocol-level segmentation.
    """
    if not _available:
        return _unavailable()

    addr = _validate_address(address)
    limit = min(int(request.args.get("limit", 50)), 500)

    sub_entities = _segmenter.get_sub_entities(addr, limit=limit)

    return jsonify({
        "status": "ok",
        "address": addr,
        "count": len(sub_entities),
        "sub_entities": [
            {
                "caller": se.caller,
                "tx_count": se.tx_count,
                "dominant_event": se.dominant_event,
                "event_type_counts": se.event_type_counts,
                "magnitude_mean": se.magnitude_stats.get("mean", 0),
                "magnitude_p95": se.magnitude_stats.get("p95", 0),
                "chains": se.chains,
                "first_seen": se.first_seen,
                "last_seen": se.last_seen,
            }
            for se in sub_entities
        ],
    })


# ── /api/v1/protocol/supported-roles ─────────────────────────────────────────

@protocol_bp.route("/api/v1/protocol/supported-roles", methods=["GET"])
def supported_roles():
    """Reference endpoint: all supported DeFi roles with descriptions."""
    return jsonify({
        "status": "ok",
        "roles": [
            {
                "role": role.value,
                "archetype": role.archetype,
                "risk_level": role.risk_level,
                "description": role.description,
            }
            for role in DeFiRole
            if role != DeFiRole.UNKNOWN
        ],
    })


# ── /api/v1/protocol/monitor/status ──────────────────────────────────────────

@protocol_bp.route("/api/v1/protocol/monitor/status", methods=["GET"])
def monitor_status():
    """
    Returns current state of the background protocol health monitor:
    last H(t) score, grade, threat level, and push count for each watched protocol.
    """
    try:
        from protocol_monitor import get_monitor_status, WATCHED_PROTOCOLS, POLL_INTERVAL_SECONDS
        return jsonify({
            "status": "ok",
            "monitor_active": True,
            "poll_interval_seconds": POLL_INTERVAL_SECONDS,
            "watched_protocols": WATCHED_PROTOCOLS,
            "states": get_monitor_status(),
        })
    except Exception as exc:
        return jsonify({"status": "ok", "monitor_active": False, "error": str(exc)})
