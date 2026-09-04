"""
TRION Sensing Oracle — unified server (frontend + Oracle API on port 5000).
WebSocket push is handled by flask-socketio (threading mode, /feed namespace).
The Flask app in api/app.py is untouched; socket_push.py wraps it.
"""
import os
import sys
import shutil
import logging

logging.basicConfig(level=logging.INFO)

# ── bh_ledger.db guard ────────────────────────────────────────────────────────
# Ensure bh_ledger.db is accessible at the repo root. In Docker/Render the
# anima-service/ directory contains the canonical copy. We copy it to root
# (symlinks are forbidden in some environments).
_root     = os.path.dirname(os.path.abspath(__file__))
_link     = os.path.join(_root, "bh_ledger.db")
_abs_tgt  = os.path.join(_root, "anima-service", "bh_ledger.db")
if os.path.exists(_abs_tgt) and not os.path.exists(_link):
    try:
        shutil.copy2(_abs_tgt, _link)
        logging.info("serve.py: copied bh_ledger.db from anima-service/ to root")
    except Exception as _e:
        logging.warning("serve.py: could not copy bh_ledger.db: %s", _e)
elif not os.path.exists(_abs_tgt) and not os.path.exists(_link):
    # Create an empty bh_ledger.db so SQLite connections don't fail
    try:
        import sqlite3
        conn = sqlite3.connect(_link)
        conn.execute("""CREATE TABLE IF NOT EXISTS bh_ledger (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            tx_hash TEXT UNIQUE,
            entity_id TEXT, from_addr TEXT, to_addr TEXT,
            event_type INTEGER, event_type_name TEXT,
            magnitude_norm REAL, value_wei TEXT, selector TEXT,
            sense_hex TEXT, antisense_hex TEXT,
            block_num INTEGER, block_hash TEXT,
            chain_id INTEGER, chain_label TEXT, ts REAL,
            valid INTEGER DEFAULT 1
        )""")
        conn.execute("CREATE INDEX IF NOT EXISTS bh_ledger_entity ON bh_ledger(entity_id)")
        conn.execute("CREATE INDEX IF NOT EXISTS bh_ledger_chain ON bh_ledger(chain_id)")
        conn.execute("CREATE INDEX IF NOT EXISTS bh_ledger_ts ON bh_ledger(ts DESC)")
        conn.commit()
        conn.close()
        logging.info("serve.py: created empty bh_ledger.db at root")
    except Exception as _e:
        logging.warning("serve.py: could not create bh_ledger.db: %s", _e)
# ─────────────────────────────────────────────────────────────────────────────

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "api"))
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
