"""
protocol_monitor.py — Background monitor for protocol H(t) score streaming.

Watches a set of DeFi protocol contracts, computes H(t) on a configurable
interval, and pushes notable events into TRION's live signal feed ring buffer
via a lazy reference to app._feed_push — no circular imports at load time.

Events are pushed when:
  - Grade changes (e.g. B → C, or C → B recovery)
  - Threat level changes (LOW → HIGH, etc.)
  - H(t) score drifts more than SCORE_DRIFT_THRESHOLD since last push
  - Attack probability exceeds ATTACK_ALERT_THRESHOLD

The pushed dicts are FeedEntry-compatible so the existing SSE infrastructure
(/api/v1/feed → /api/live-feed → useLiveFeed) carries them transparently.
"""

from __future__ import annotations

import sys
import time
import threading
import logging
from dataclasses import dataclass, field

log = logging.getLogger(__name__)

# ── Constants ─────────────────────────────────────────────────────────────────

POLL_INTERVAL_SECONDS  = 60
SCORE_DRIFT_THRESHOLD  = 0.05
ATTACK_ALERT_THRESHOLD = 0.35

WATCHED_PROTOCOLS: list[dict] = [
    {"address": "uniswap",                                    "name": "Uniswap V3"},
    {"address": "aave",                                       "name": "Aave V3"},
    {"address": "compound",                                   "name": "Compound III"},
    {"address": "0xa85b49c73b5710d9ddb1cb5a94c52d0f33c4199b", "name": "0G ExGate"},
]

# Limiting-plane display names keyed on H(t) component with lowest value
_COMPONENT_LABELS = {
    "distribution_coherence": "DC(t) — Dist. Coherence",
    "role_coherence":         "Role Coherence",
    "user_quality":           "User Quality",
    "attack_surface":         "Attack Surface",
}

_GRADE_ARCHETYPE = {
    "A": "Innocent",
    "B": "Hero",
    "C": "Sage",
    "D": "Jester",
    "F": "Outlaw",
}

_THREAT_ARCHETYPE = {
    "LOW":      "Innocent",
    "MEDIUM":   "Sage",
    "HIGH":     "Outlaw",
    "CRITICAL": "Outlaw",
}

# ── State ─────────────────────────────────────────────────────────────────────

@dataclass
class ProtocolState:
    address: str
    name: str
    last_score: float = -1.0
    last_grade: str = ""
    last_threat: str = ""
    last_attack_prob: float = 0.0
    last_push_ts: float = field(default_factory=time.time)
    push_count: int = 0


_states: dict[str, ProtocolState] = {
    p["address"]: ProtocolState(p["address"], p["name"])
    for p in WATCHED_PROTOCOLS
}

_started = False
_lock = threading.Lock()


# ── Lazy feed push ────────────────────────────────────────────────────────────

def _push_to_feed(entry: dict) -> None:
    """
    Lazy import of app._feed_push to avoid circular imports at module load.
    By the time the monitor thread fires, api/app.py is fully loaded
    and accessible via sys.modules.
    """
    try:
        app_mod = sys.modules.get("app") or sys.modules.get("api.app")
        if app_mod and hasattr(app_mod, "_feed_push"):
            app_mod._feed_push(entry)
            return
        # Fallback: try direct import
        import importlib
        mod = importlib.import_module("app")
        if hasattr(mod, "_feed_push"):
            mod._feed_push(entry)
    except Exception as exc:
        log.debug("protocol_monitor: feed push failed: %s", exc)


# ── Event builder ─────────────────────────────────────────────────────────────

def _build_feed_entry(
    state: ProtocolState,
    result,
    attack_surface_data: dict,
    change_reason: str,
) -> dict:
    components = result.components
    # Find the lowest-scoring component as the "limiting plane"
    comp_scores = {
        k: components.get(k, 0.5)
        for k in ("distribution_coherence", "role_coherence", "user_quality", "attack_surface")
    }
    limiting_key = min(comp_scores, key=comp_scores.get)
    limiting_label = _COMPONENT_LABELS.get(limiting_key, limiting_key)

    grade = result.grade
    threat = attack_surface_data.get("threat_level", "UNKNOWN")
    attack_prob = result.dc_result.get("attack_probability", 0.0)

    archetype = _GRADE_ARCHETYPE.get(grade, "Regular")

    short_id = state.name

    return {
        # Required FeedEntry fields
        "entity_id":        state.address,
        "short_id":         short_id,
        "archetype":        archetype,
        "coherence_score":  round(result.health_score, 4),
        "coherent":         result.health_score >= 0.55,
        "threshold":        0.55,
        "limiting_plane":   limiting_label,
        "timestamp":        time.time(),
        # Extended protocol fields
        "kind":             "PROTOCOL_HEALTH",
        "grade":            grade,
        "threat_level":     threat,
        "attack_probability": round(attack_prob, 4),
        "protocol_name":    state.name,
        "change_reason":    change_reason,
        "prev_score":       round(state.last_score, 4) if state.last_score >= 0 else None,
        "sub_entity_count": result.sub_entity_count,
        "role_distribution": result.role_distribution,
        "recommendations":  result.recommendations[:2],
        "dc_score":         round(result.components.get("distribution_coherence", 0.5), 4),
    }


# ── Change detection ──────────────────────────────────────────────────────────

def _detect_changes(state: ProtocolState, result, attack_surface_data: dict) -> str | None:
    """
    Returns a change_reason string if an event should be pushed, else None.
    """
    new_score   = result.health_score
    new_grade   = result.grade
    new_threat  = attack_surface_data.get("threat_level", "UNKNOWN")
    new_attack  = result.dc_result.get("attack_probability", 0.0)

    # First observation for this protocol
    if state.last_score < 0:
        return "initial"

    # Grade changed
    if new_grade != state.last_grade:
        direction = "degraded" if new_grade > state.last_grade else "recovered"
        return f"grade_{direction}:{state.last_grade}→{new_grade}"

    # Threat level changed
    if new_threat != state.last_threat and state.last_threat:
        return f"threat_change:{state.last_threat}→{new_threat}"

    # Score drift beyond threshold
    if abs(new_score - state.last_score) >= SCORE_DRIFT_THRESHOLD:
        direction = "drop" if new_score < state.last_score else "rise"
        return f"score_{direction}:{state.last_score:.3f}→{new_score:.3f}"

    # Attack probability crossed alert threshold
    if new_attack >= ATTACK_ALERT_THRESHOLD and state.last_attack_prob < ATTACK_ALERT_THRESHOLD:
        return f"attack_alert:{new_attack:.3f}"

    # Attack probability recovered
    if new_attack < ATTACK_ALERT_THRESHOLD * 0.5 and state.last_attack_prob >= ATTACK_ALERT_THRESHOLD:
        return f"attack_resolved:{new_attack:.3f}"

    return None


def _update_state(state: ProtocolState, result, attack_surface_data: dict) -> None:
    state.last_score       = result.health_score
    state.last_grade       = result.grade
    state.last_threat      = attack_surface_data.get("threat_level", "UNKNOWN")
    state.last_attack_prob = result.dc_result.get("attack_probability", 0.0)
    state.last_push_ts     = time.time()
    state.push_count      += 1


# ── Monitor thread ────────────────────────────────────────────────────────────

def _monitor_loop(engine) -> None:
    from src.protocol.protocol_health import ProtocolHealthEngine
    from src.protocol.segmentation import ProtocolSegmenter
    from src.protocol.distribution_coherence import DistributionCoherenceEngine

    _segmenter = ProtocolSegmenter()
    _dc_engine = DistributionCoherenceEngine()

    log.info("protocol_monitor: started — watching %d protocols every %ds",
             len(WATCHED_PROTOCOLS), POLL_INTERVAL_SECONDS)

    while True:
        for p in WATCHED_PROTOCOLS:
            addr = p["address"]
            state = _states[addr]
            try:
                result = engine.compute(addr, top_n=30, window_seconds=3600)

                cur_dist = _segmenter.get_protocol_activity(addr, window_seconds=3600)
                global_dist = _segmenter.get_global_activity(window_seconds=86400)
                _dc_engine.update_baseline(addr, global_dist or cur_dist)
                attack_surface = _dc_engine.compute(addr, cur_dist)
                attack_surface["threat_level"] = _infer_threat(
                    attack_surface.get("attack_probability", 0),
                    attack_surface.get("distribution_coherence", 1),
                )

                change_reason = _detect_changes(state, result, attack_surface)

                if change_reason:
                    entry = _build_feed_entry(state, result, attack_surface, change_reason)
                    _push_to_feed(entry)
                    log.info(
                        "protocol_monitor: pushed %s H(t)=%.3f grade=%s reason=%s",
                        state.name, result.health_score, result.grade, change_reason,
                    )

                _update_state(state, result, attack_surface)

            except Exception as exc:
                log.warning("protocol_monitor: error for %s: %s", addr, exc)

        time.sleep(POLL_INTERVAL_SECONDS)


def _infer_threat(attack_prob: float, dc: float) -> str:
    score = attack_prob * 0.6 + (1 - dc) * 0.4
    if score >= 0.6:   return "CRITICAL"
    if score >= 0.40:  return "HIGH"
    if score >= 0.20:  return "MEDIUM"
    return "LOW"


# ── Public API ────────────────────────────────────────────────────────────────

def start_monitor(engine=None) -> None:
    """
    Start the background protocol monitor. Safe to call multiple times —
    only one thread is ever started.
    """
    global _started
    with _lock:
        if _started:
            return
        _started = True

    if engine is None:
        try:
            from src.protocol.protocol_health import ProtocolHealthEngine
            engine = ProtocolHealthEngine()
        except Exception as exc:
            log.warning("protocol_monitor: engine unavailable, monitor not started: %s", exc)
            return

    t = threading.Thread(
        target=_monitor_loop,
        args=(engine,),
        name="protocol-monitor",
        daemon=True,
    )
    t.start()
    log.info("protocol_monitor: daemon thread started")


def get_monitor_status() -> dict:
    """Return current state of all watched protocols (for debug endpoint)."""
    return {
        addr: {
            "name":           s.name,
            "last_score":     round(s.last_score, 4),
            "last_grade":     s.last_grade,
            "last_threat":    s.last_threat,
            "last_attack_prob": round(s.last_attack_prob, 4),
            "last_push_ts":   s.last_push_ts,
            "push_count":     s.push_count,
        }
        for addr, s in _states.items()
    }
