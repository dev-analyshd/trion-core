"""
TRION Sensing Oracle — unified server (frontend + Oracle API on port 5000).
WebSocket push is handled by flask-socketio (threading mode, /feed namespace).
The Flask app in oracle_api/app.py is untouched; socket_push.py wraps it.
"""
import os
import sys
import logging

logging.basicConfig(level=logging.INFO)

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
