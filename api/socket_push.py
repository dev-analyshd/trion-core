"""
TRION WebSocket Push Layer
Wraps the existing Flask app with SocketIO and runs a background broadcaster
that detects new feed entries (every 3 s) and pushes them to all connected
clients instantly — no client polling needed.

Architecture:
  Background thread → polls /api/v1/feed internally → diffs against seen set
  → socketio.emit('signal', entry) for each new entry → browser receives instantly.
"""
import os
import sys
import time
import threading
import logging

import requests
from flask_socketio import SocketIO

sys.path.insert(0, os.path.dirname(__file__))
from app import app  # noqa: E402 — the 9,043-line Flask app, untouched

log = logging.getLogger("trion.ws")

socketio = SocketIO(
    app,
    cors_allowed_origins="*",
    async_mode="threading",
    logger=False,
    engineio_logger=False,
    ping_timeout=60,
    ping_interval=25,
)

# ── broadcaster state ──────────────────────────────────────────────
_POLL_INTERVAL = 3            # seconds between internal feed checks
_PORT          = int(os.environ.get("PORT", 5000))
_FEED_URL      = f"http://127.0.0.1:{_PORT}/api/v1/feed"
_STATS_URL     = f"http://127.0.0.1:{_PORT}/api/v1/health"
_seen_keys: set = set()       # (entity_id, timestamp) already broadcast
_connected: int = 0           # rough connected-client counter (for logging)


def _feed_key(entry: dict) -> tuple:
    return (entry.get("entity_id", ""), int(entry.get("timestamp", 0)))


def _broadcaster():
    """Daemon thread: poll feed, emit new entries via WebSocket."""
    time.sleep(5)                       # let Flask finish starting up
    log.info("[WS-broadcaster] started — polling %s every %ss", _FEED_URL, _POLL_INTERVAL)
    while True:
        try:
            resp = requests.get(_FEED_URL, timeout=4)
            if resp.ok:
                entries = resp.json().get("feed", [])
                new_entries = []
                for e in entries:
                    k = _feed_key(e)
                    if k not in _seen_keys:
                        _seen_keys.add(k)
                        new_entries.append(e)

                if new_entries:
                    for e in new_entries:
                        socketio.emit("signal", e, namespace="/feed")
                    log.debug("[WS-broadcaster] pushed %d new signal(s)", len(new_entries))

                # Cap seen set to avoid unbounded growth (keep last 500)
                if len(_seen_keys) > 500:
                    excess = len(_seen_keys) - 400
                    to_remove = list(_seen_keys)[:excess]
                    for k in to_remove:
                        _seen_keys.discard(k)

        except Exception as exc:
            log.debug("[WS-broadcaster] feed poll error: %s", exc)

        time.sleep(_POLL_INTERVAL)


def _health_broadcaster():
    """Emit a condensed health/stats packet every 10 s for the topbar counters."""
    time.sleep(8)
    while True:
        try:
            resp = requests.get(_STATS_URL, timeout=4)
            if resp.ok:
                socketio.emit("health", resp.json(), namespace="/feed")
        except Exception:
            pass
        time.sleep(10)


# ── Socket.IO events ───────────────────────────────────────────────
@socketio.on("connect", namespace="/feed")
def on_connect():
    global _connected
    _connected += 1
    log.info("[WS] client connected  (total ~%d)", _connected)


@socketio.on("disconnect", namespace="/feed")
def on_disconnect():
    global _connected
    _connected = max(0, _connected - 1)
    log.debug("[WS] client disconnected (total ~%d)", _connected)


# ── start background threads ───────────────────────────────────────
threading.Thread(target=_broadcaster,       daemon=True, name="trion-ws-feed").start()
threading.Thread(target=_health_broadcaster, daemon=True, name="trion-ws-health").start()
