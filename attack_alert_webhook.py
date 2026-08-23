"""
TRION Attack Alert Webhook Service
===================================
Standalone polling service that monitors the TRION Oracle API for
behavioral threat signals and fires registered webhooks when:

  1. CRISPR intercepts a known attack signature (INTERCEPT status)
  2. C(t) drops below Θ(t) for a tracked entity (COLLAPSE_INTERCEPTED)
  3. A new adaptive attack is characterized by the immune system
  4. The epigenetic layer enters DEFENSIVE or LOCKDOWN state

POST /webhook/register   — register a callback URL
GET  /webhook/list       — list all registered webhooks
DELETE /webhook/<id>     — remove a webhook
POST /webhook/test/<id>  — fire a test alert to a registered URL
GET  /alerts             — last 100 alerts fired
GET  /health             — service health
"""

import os
import json
import uuid
import time
import hmac
import hashlib
import logging
import threading
import traceback
from datetime import datetime, timezone
from collections import deque

import requests
from flask import Flask, request, jsonify

logging.basicConfig(level=logging.INFO,
                    format="%(asctime)s [WEBHOOK] %(levelname)s %(message)s")
log = logging.getLogger("trion.webhook")

# Semaphore: cap concurrent outbound webhook delivery threads to prevent FD exhaustion
_DELIVERY_SEMAPHORE = threading.Semaphore(32)

app = Flask(__name__)

ORACLE_URL    = os.getenv("ORACLE_API_URL", "http://127.0.0.1:5000")
POLL_INTERVAL = int(os.getenv("WEBHOOK_POLL_INTERVAL_MS", "30000")) / 1000.0
PORT          = int(os.getenv("WEBHOOK_PORT", "5001"))

MONITORED_ENTITIES = (os.getenv("MONITORED_ENTITIES") or
    "uniswap,aave,compound,0xb819c63c02Ed5aB49017C0f3f2568A14624658b3"
).split(",")

_webhooks: dict = {}
_alerts: deque  = deque(maxlen=100)
_prev_states: dict = {}
_lock = threading.Lock()


def _sign_payload(secret: str, body: bytes) -> str:
    return "sha256=" + hmac.new(secret.encode(), body, hashlib.sha256).hexdigest()


def _fire(webhook_id: str, hook: dict, alert: dict) -> bool:
    body = json.dumps(alert, default=str).encode()
    headers = {
        "Content-Type":         "application/json",
        "X-TRION-Event":        alert["event"],
        "X-TRION-Delivery":     str(uuid.uuid4()),
        "X-TRION-Timestamp":    str(int(time.time())),
    }
    if hook.get("secret"):
        headers["X-TRION-Signature"] = _sign_payload(hook["secret"], body)
    try:
        r = requests.post(hook["url"], data=body, headers=headers, timeout=10)
        log.info(f"Fired {alert['event']} → {hook['url']} [{r.status_code}]")
        return r.status_code < 400
    except Exception as e:
        log.warning(f"Webhook delivery failed ({hook['url']}): {e}")
        return False


def _dispatch(alert: dict):
    with _lock:
        alert["fired_at"] = datetime.now(timezone.utc).isoformat()
        _alerts.appendleft(alert)
        hooks = list(_webhooks.values())

    event = alert.get("event", "")
    for wh in hooks:
        subscribed = wh.get("events", [])
        if subscribed and event not in subscribed and "all" not in subscribed:
            continue
        def _guarded_fire(webhook_id, hook, alert):
            with _DELIVERY_SEMAPHORE:
                _fire(webhook_id, hook, alert)
        threading.Thread(target=_guarded_fire, args=(wh["id"], wh, alert), daemon=True).start()


def _check_entity(entity: str):
    try:
        r = requests.get(f"{ORACLE_URL}/api/v1/signal/{entity}", timeout=5)
        if r.status_code != 200:
            return
        sig = r.json()
    except Exception:
        return

    coherence  = sig.get("coherence", 0)
    threshold  = sig.get("threshold", 0.55)
    status     = sig.get("status", "")
    archetype  = sig.get("archetype", "")
    entity_id  = sig.get("entity_id", entity)
    planes     = sig.get("planes", {})
    crispr_hit = sig.get("crispr_intercept") or (status in ("COLLAPSE_INTERCEPTED", "HOSTILE"))

    prev = _prev_states.get(entity, {})
    prev_status = prev.get("status", "")

    events_to_fire = []

    if crispr_hit and prev_status not in ("COLLAPSE_INTERCEPTED", "HOSTILE"):
        events_to_fire.append({
            "event":       "crispr.intercept",
            "entity_id":   entity_id,
            "entity_label": entity,
            "coherence":   round(coherence, 6),
            "threshold":   round(threshold, 6),
            "status":      status,
            "archetype":   archetype,
            "planes":      planes,
            "message":     f"CRISPR intercepted known attack pattern on entity '{entity}'",
        })

    if coherence < threshold and prev.get("coherence", 1.0) >= prev.get("threshold", 0.55):
        events_to_fire.append({
            "event":       "signal.collapse",
            "entity_id":   entity_id,
            "entity_label": entity,
            "coherence":   round(coherence, 6),
            "threshold":   round(threshold, 6),
            "status":      status,
            "archetype":   archetype,
            "planes":      planes,
            "message":     f"Entity '{entity}' coherence fell below dynamic threshold (C={coherence:.4f} < Θ={threshold:.4f})",
        })

    limiting = sig.get("limiting_plane", "")
    if limiting and limiting != prev.get("limiting_plane", ""):
        events_to_fire.append({
            "event":        "signal.plane_shift",
            "entity_id":    entity_id,
            "entity_label": entity,
            "coherence":    round(coherence, 6),
            "threshold":    round(threshold, 6),
            "limiting_plane": limiting,
            "prev_limiting":  prev.get("limiting_plane", "none"),
            "message":      f"Limiting plane shifted to '{limiting}' for entity '{entity}'",
        })

    for ev in events_to_fire:
        _dispatch(ev)

    _prev_states[entity] = {
        "status":        status,
        "coherence":     coherence,
        "threshold":     threshold,
        "limiting_plane": limiting,
        "last_check":    time.time(),
    }


def _poll_loop():
    log.info(f"Poll loop started — {len(MONITORED_ENTITIES)} entities, interval={POLL_INTERVAL}s")
    while True:
        for entity in MONITORED_ENTITIES:
            try:
                _check_entity(entity.strip())
            except Exception:
                log.debug(traceback.format_exc())
        time.sleep(POLL_INTERVAL)


# ── API Routes ────────────────────────────────────────────────────────────────

@app.route("/health")
def health():
    return jsonify({
        "service":     "trion-attack-alert-webhook",
        "status":      "ok",
        "webhooks":    len(_webhooks),
        "alerts_fired": len(_alerts),
        "monitored":   MONITORED_ENTITIES,
        "poll_interval_s": POLL_INTERVAL,
        "oracle_url":  ORACLE_URL,
        "timestamp":   datetime.now(timezone.utc).isoformat(),
    })


@app.route("/webhook/register", methods=["POST"])
def register():
    data = request.get_json(force=True, silent=True) or {}
    url = data.get("url", "").strip()
    if not url:
        return jsonify({"error": "url required"}), 400

    wh_id = str(uuid.uuid4())[:8]
    hook = {
        "id":      wh_id,
        "url":     url,
        "events":  data.get("events", ["all"]),
        "secret":  data.get("secret", ""),
        "label":   data.get("label", url),
        "created": datetime.now(timezone.utc).isoformat(),
        "deliveries": 0,
    }
    with _lock:
        _webhooks[wh_id] = hook

    log.info(f"Registered webhook {wh_id} → {url} (events={hook['events']})")
    return jsonify({"id": wh_id, "url": url, "events": hook["events"],
                    "message": "Webhook registered. TRION will POST alerts to this URL."}), 201


@app.route("/webhook/list")
def list_webhooks():
    with _lock:
        hooks = [
            {k: v for k, v in h.items() if k != "secret"}
            for h in _webhooks.values()
        ]
    return jsonify({"webhooks": hooks, "count": len(hooks)})


@app.route("/webhook/<wh_id>", methods=["DELETE"])
def delete_webhook(wh_id):
    with _lock:
        if wh_id not in _webhooks:
            return jsonify({"error": "not found"}), 404
        del _webhooks[wh_id]
    return jsonify({"deleted": wh_id})


@app.route("/webhook/test/<wh_id>", methods=["POST"])
def test_webhook(wh_id):
    with _lock:
        hook = _webhooks.get(wh_id)
    if not hook:
        return jsonify({"error": "not found"}), 404
    test_alert = {
        "event":       "test.ping",
        "entity_id":   "trion.testnet",
        "entity_label": "test",
        "coherence":   0.8123,
        "threshold":   0.7201,
        "status":      "SAFE",
        "message":     "TRION webhook test — system operational",
        "timestamp":   datetime.now(timezone.utc).isoformat(),
    }
    ok = _fire(wh_id, hook, test_alert)
    return jsonify({"delivered": ok, "alert": test_alert})


@app.route("/alerts")
def get_alerts():
    limit = int(request.args.get("limit", 50))
    with _lock:
        alerts = list(_alerts)[:limit]
    return jsonify({"alerts": alerts, "count": len(alerts)})


@app.route("/alerts/stats")
def alert_stats():
    with _lock:
        alerts = list(_alerts)
    by_event: dict = {}
    by_entity: dict = {}
    for a in alerts:
        ev = a.get("event", "unknown")
        en = a.get("entity_label", "unknown")
        by_event[ev]   = by_event.get(ev, 0) + 1
        by_entity[en]  = by_entity.get(en, 0) + 1
    return jsonify({
        "total_alerts": len(alerts),
        "by_event":  by_event,
        "by_entity": by_entity,
        "monitored_entities": MONITORED_ENTITIES,
    })


# ── Events emitted ─────────────────────────────────────────────────────────
#
#  crispr.intercept     — CRISPR matched a known attack pattern
#  signal.collapse      — C(t) dropped below Θ(t) (new threat window)
#  signal.plane_shift   — The limiting behavioral plane changed
#  test.ping            — Manual test delivery
#
# Payload shape (all events):
#  {
#    "event":        "crispr.intercept",
#    "entity_id":    "0x...",
#    "entity_label": "uniswap",
#    "coherence":    0.3791,
#    "threshold":    0.7064,
#    "status":       "COLLAPSE_INTERCEPTED",
#    "archetype":    "Shadow",
#    "planes":       { "phi": 0.38, "mental": 0.41, ... },
#    "message":      "CRISPR intercepted known attack pattern on entity 'uniswap'",
#    "fired_at":     "2026-06-01T16:30:00Z"
#  }
# ─────────────────────────────────────────────────────────────────────────────


if __name__ == "__main__":
    poll_thread = threading.Thread(target=_poll_loop, daemon=True)
    poll_thread.start()
    log.info(f"TRION Attack Alert Webhook Service starting on port {PORT}")
    log.info(f"Oracle API: {ORACLE_URL}")
    log.info(f"Monitoring: {', '.join(MONITORED_ENTITIES)}")
    app.run(host="0.0.0.0", port=PORT, debug=False)
