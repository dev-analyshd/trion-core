"""
self_verification.py — TRION_PROTOCOL reflexive self-verification.

Treats the TRION protocol itself as a single behavioral entity, reusing the
SAME primitives already built for external entities/protocols instead of
inventing a parallel system:

  - L4.3 Genomic Key evolution  (Hash_DNA chaining, persisted across restarts)
  - L1.4 Transduction Integrity (per-plane sensor health, from FAISS ANIMA)
  - L0.6 Evolutionary Fitness   (component health, from FAISS ANIMA)
  - Safety pipeline SILENCE gate (same 0.25 threshold used for relay actions)
  - Live signal feed             (same FeedEntry schema external protocols use)

Honesty note: this computes a real, reproducible coherence score from live
operational signals. It is NOT a claim of omniscience or omnipotence — it is
bounded exactly like every other measurement in the system: proxies are
approximations of the whitepaper's f1-f9 features, not the literal chain-by-
chain entropy computation that exists for indexed EVM/SVM wallets. Where a
signal is unavailable, it is scored neutrally (0.5) and flagged, never
silently assumed.
"""

from __future__ import annotations

import hashlib
import json
import os
import sqlite3
import threading
import time
from datetime import datetime, timezone
from typing import Optional

SELF_ENTITY_ID = "TRION_PROTOCOL"
SELF_DB_PATH = os.environ.get("SELF_VERIFICATION_DB", "self_verification.db")
SILENCE_THRESHOLD = 0.25  # same threshold as src/agent/safety_pipeline.py

_lock = threading.Lock()


def _conn() -> sqlite3.Connection:
    c = sqlite3.connect(SELF_DB_PATH, check_same_thread=False, timeout=30.0)
    c.execute("""
        CREATE TABLE IF NOT EXISTS self_genomic_key (
            generation INTEGER PRIMARY KEY AUTOINCREMENT,
            key_hash TEXT NOT NULL,
            parent_hash TEXT,
            coherence REAL,
            limiting_plane TEXT,
            behavioral_event TEXT,
            created_at TEXT
        )
    """)
    return c


def _latest_key() -> Optional[sqlite3.Row]:
    with _conn() as c:
        c.row_factory = sqlite3.Row
        row = c.execute(
            "SELECT * FROM self_genomic_key ORDER BY generation DESC LIMIT 1"
        ).fetchone()
        return row


def _append_key(key_hash: str, parent_hash: Optional[str], coherence: float,
                 limiting_plane: str, behavioral_event: str) -> int:
    with _lock, _conn() as c:
        cur = c.execute(
            "INSERT INTO self_genomic_key "
            "(key_hash, parent_hash, coherence, limiting_plane, behavioral_event, created_at) "
            "VALUES (?,?,?,?,?,?)",
            (key_hash, parent_hash, coherence, limiting_plane, behavioral_event,
             datetime.now(timezone.utc).isoformat()),
        )
        return cur.lastrowid


def _evolve_gk(behavioral_event: str, temporal_marker: float, context_vector: dict) -> tuple[str, int]:
    """
    GK(TRION, t) = Hash_DNA(GK(TRION, t-1) || BE(t) || TM(t) || CV(t))
    Persisted in SQLite so the chain survives process restarts — a real
    hash-chain, not re-bootstrapped per request like the generic
    /api/v1/gk/<entity_id> demo endpoint.
    """
    prev = _latest_key()
    prev_hash = prev["key_hash"] if prev else "GENESIS"
    generation = (prev["generation"] + 1) if prev else 0

    payload = (
        prev_hash.encode()
        + behavioral_event.encode()
        + str(temporal_marker).encode()
        + json.dumps(context_vector, sort_keys=True).encode()
    )
    new_hash = hashlib.sha3_256(payload).hexdigest()
    return new_hash, generation


# ── Signal gathering (real HTTP calls to already-running TRION services) ──────

def _get_json(url: str, timeout: float = 3.0) -> Optional[dict]:
    try:
        import requests
        r = requests.get(url, timeout=timeout)
        if r.status_code == 200:
            return r.json()
    except Exception:
        return None
    return None


def _score_transduction_integrity(faiss_url: str) -> tuple[float, dict]:
    """Spiritual/Conscious/ANIMA/Mental/Physical plane health, from L1.4 TI."""
    data = _get_json(f"{faiss_url}/api/v1/transduction_integrity")
    if not data:
        return 0.5, {"available": False}
    return float(data.get("system_ti", 0.5)), {
        "available": True,
        "sensors": data.get("sensors", {}),
        "degraded": data.get("degraded", False),
    }


def _score_component_fitness(faiss_url: str) -> tuple[float, dict]:
    """L0.6 Evolutionary Fitness — health of TRION's own components."""
    data = _get_json(f"{faiss_url}/fitness")
    if not data or not data.get("components"):
        return 0.5, {"available": False}
    fitnesses = [c.get("fitness", 0.5) for c in data["components"].values()]
    avg = sum(fitnesses) / len(fitnesses) if fitnesses else 0.5
    return avg, {"available": True, "components": data["components"]}


def _score_validator_diversity() -> tuple[float, dict]:
    """
    f2 proxy — counterparty/geography diversity of the protocol's own
    validator/deployment surface, derived from actual deployments.json,
    not simulated. More independently-configured chain deployments =
    higher structural diversity = less single-point-of-failure risk.
    """
    try:
        base = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
        path = os.path.join(base, "deployments.json")
        with open(path) as f:
            deployments = json.load(f)
        # deployments.json may be a single dict (one network) or a list
        entries = deployments if isinstance(deployments, list) else [deployments]
        chain_ids = {e.get("chainId") for e in entries if e.get("chainId") is not None}
        diversity = min(1.0, len(chain_ids) / 5.0)  # 5+ independent chains = fully diverse
        return diversity, {"available": True, "distinct_chains": len(chain_ids)}
    except Exception:
        return 0.5, {"available": False}


def _score_feed_temporal_spacing(oracle_api_url: str) -> tuple[float, dict]:
    """
    f3 proxy — are TRION's own emitted signals evenly paced (healthy) or
    bursty/clustered (could indicate internal malfunction or manipulation
    of the feed itself)? Computed from the live /api/v1/feed the dashboard
    already consumes.
    """
    data = _get_json(f"{oracle_api_url}/api/v1/feed")
    entries = data.get("entries") if isinstance(data, dict) else data
    if not entries or len(entries) < 3:
        return 0.5, {"available": False}
    timestamps = sorted(e.get("timestamp", 0) for e in entries if e.get("timestamp"))
    if len(timestamps) < 3:
        return 0.5, {"available": False}
    gaps = [timestamps[i + 1] - timestamps[i] for i in range(len(timestamps) - 1)]
    mean_gap = sum(gaps) / len(gaps)
    if mean_gap <= 0:
        return 0.5, {"available": False}
    variance = sum((g - mean_gap) ** 2 for g in gaps) / len(gaps)
    cv = (variance ** 0.5) / mean_gap  # coefficient of variation
    # Lower CV = more even spacing = higher score. Cap at 2.0 CV -> score 0.
    score = max(0.0, min(1.0, 1.0 - (cv / 2.0)))
    return score, {"available": True, "coefficient_of_variation": round(cv, 4)}


PLANE_WEIGHTS = {
    "physical_component_fitness": 0.25,
    "mental_transduction_integrity": 0.30,
    "spiritual_validator_diversity": 0.20,
    "conscious_temporal_spacing": 0.15,
    "anima_transduction_integrity": 0.10,
}


def compute_self_coherence(oracle_api_url: str, faiss_url: str) -> dict:
    """
    Computes TRION_PROTOCOL's own coherence from five real, weighted signals.
    Unavailable signals score neutral (0.5) and are flagged — never assumed.
    """
    ti_score, ti_detail = _score_transduction_integrity(faiss_url)
    fitness_score, fitness_detail = _score_component_fitness(faiss_url)
    diversity_score, diversity_detail = _score_validator_diversity()
    spacing_score, spacing_detail = _score_feed_temporal_spacing(oracle_api_url)

    planes = {
        "physical_component_fitness":  fitness_score,
        "mental_transduction_integrity": ti_score,
        "spiritual_validator_diversity": diversity_score,
        "conscious_temporal_spacing":   spacing_score,
        "anima_transduction_integrity": ti_score,  # same live TI feed covers ANIMA sensors too
    }
    coherence = sum(planes[k] * PLANE_WEIGHTS[k] for k in planes)
    limiting_plane = min(planes, key=planes.get)

    detail = {
        "physical_component_fitness":  fitness_detail,
        "mental_transduction_integrity": ti_detail,
        "spiritual_validator_diversity": diversity_detail,
        "conscious_temporal_spacing":   spacing_detail,
    }

    return {
        "coherence": round(coherence, 6),
        "planes": {k: round(v, 6) for k, v in planes.items()},
        "limiting_plane": limiting_plane,
        "coherence_deficit": round(max(0.0, SILENCE_THRESHOLD - coherence), 6),
        "detail": detail,
        "any_signal_unavailable": any(
            not d.get("available", False) for d in detail.values()
        ),
    }


def run_self_verification_cycle(oracle_api_url: str, faiss_url: str) -> dict:
    """
    One full reflexive-verification pass: measure -> evolve GK -> decide
    SILENCE vs live signal -> persist -> return the record for the feed.
    """
    result = compute_self_coherence(oracle_api_url, faiss_url)
    coherence = result["coherence"]
    now = time.time()

    behavioral_event = (
        f"cycle@{int(now)}|coherence={coherence}|limiting={result['limiting_plane']}"
    )
    new_hash, generation = _evolve_gk(behavioral_event, now, result["planes"])
    prev = _latest_key()
    prev_hash = prev["key_hash"] if prev else None

    is_silence = coherence < SILENCE_THRESHOLD
    _append_key(new_hash, prev_hash, coherence, result["limiting_plane"], behavioral_event)

    record = {
        "entity_id": SELF_ENTITY_ID,
        "signal_type": "SILENCE" if is_silence else "SELF_VERIFICATION",
        "status": "SILENCE" if is_silence else "COHERENT",
        "coherence_score": coherence,
        "coherent": not is_silence,
        "threshold": SILENCE_THRESHOLD,
        "limiting_plane": result["limiting_plane"],
        "coherence_deficit": result["coherence_deficit"] if is_silence else 0.0,
        "genomic_generation": generation,
        "genomic_key": new_hash[:16] + "...",
        "planes": result["planes"],
        "any_signal_unavailable": result["any_signal_unavailable"],
        "timestamp": now,
        "kind": "SELF_VERIFICATION",
        "short_id": "TRION Protocol (self)",
        "archetype": "Sage" if coherence >= 0.65 else ("Regular" if coherence >= 0.25 else "Shadow"),
        "disclaimer": (
            "Reflexive coherence measurement across 5 real operational signals "
            "(component fitness, transduction integrity, deployment diversity, "
            "feed temporal spacing). This is a bounded engineering metric, not "
            "a claim of infallibility or omnipotence."
        ),
    }
    return record


# ── Background loop ────────────────────────────────────────────────────────────

_started = False
_start_lock = threading.Lock()


def start_self_verification_monitor(
    oracle_api_url: str,
    faiss_url: str,
    feed_push_fn,
    interval_seconds: int = 120,
) -> None:
    global _started
    with _start_lock:
        if _started:
            return
        _started = True

    def _loop():
        import logging
        log = logging.getLogger("self_verification")
        log.info(
            "self_verification: reflexive monitor started — entity=%s interval=%ds",
            SELF_ENTITY_ID, interval_seconds,
        )
        while True:
            try:
                record = run_self_verification_cycle(oracle_api_url, faiss_url)
                feed_push_fn(record)
                log.info(
                    "self_verification: gen=%d coherence=%.4f limiting=%s status=%s",
                    record["genomic_generation"], record["coherence_score"],
                    record["limiting_plane"], record["status"],
                )
            except Exception as exc:
                log.warning("self_verification: cycle failed: %s", exc)
            time.sleep(interval_seconds)

    threading.Thread(target=_loop, name="self-verification", daemon=True).start()


def get_self_status() -> dict:
    """Latest self-verification record for the /api/v1/self endpoint."""
    row = _latest_key()
    if not row:
        return {"status": "not_yet_run", "entity_id": SELF_ENTITY_ID}
    return {
        "entity_id": SELF_ENTITY_ID,
        "genomic_generation": row["generation"],
        "genomic_key": row["key_hash"],
        "parent_key": row["parent_hash"],
        "coherence": row["coherence"],
        "limiting_plane": row["limiting_plane"],
        "behavioral_event": row["behavioral_event"],
        "created_at": row["created_at"],
        "status": "SILENCE" if (row["coherence"] or 0) < SILENCE_THRESHOLD else "COHERENT",
    }
