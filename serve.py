"""
TRION Sensing Oracle — unified server (frontend + Oracle API on port 5000).
WebSocket push is handled by flask-socketio (threading mode, /feed namespace).
The Flask app in oracle_api/app.py is untouched; socket_push.py wraps it.
"""
import os
import sys
import logging

logging.basicConfig(level=logging.INFO)

# ── bh_ledger.db symlink guard ────────────────────────────────────────────────
# The root-level symlink bh_ledger.db → akashic/bh_ledger.db is destroyed on
# container reset. Recreate it at every startup so oracle_api can always find
# the ledger via the canonical relative path "../bh_ledger.db".
_root     = os.path.dirname(os.path.abspath(__file__))
_link     = os.path.join(_root, "bh_ledger.db")
_target   = os.path.join("akashic", "bh_ledger.db")   # relative → survives moves
_abs_tgt  = os.path.join(_root, "akashic", "bh_ledger.db")
if os.path.exists(_abs_tgt) and not os.path.exists(_link):
    try:
        os.symlink(_target, _link)
        logging.info("serve.py: recreated bh_ledger.db → %s", _target)
    except OSError as _e:
        logging.warning("serve.py: could not recreate bh_ledger.db symlink: %s", _e)
# ─────────────────────────────────────────────────────────────────────────────

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "oracle_api"))
from socket_push import socketio, app  # noqa: E402

if __name__ == "__main__":
    port = int(os.environ.get("PORT", 5000))
    print(f"TRION Oracle + Frontend (WebSocket) serving on http://0.0.0.0:{port}", flush=True)
    socketio.run(
        app,
        host="0.0.0.0",
        port=port,
        debug=False,
        allow_unsafe_werkzeug=True,
    )
