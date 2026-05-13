"""
TRION Sensing Oracle — entry point for gunicorn / deployment.
Serves the Oracle API + static frontend on port 5000.
"""
import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "oracle_api"))
from app import app  # noqa: F401 — imported for gunicorn

if __name__ == "__main__":
    port = int(os.environ.get("PORT", 5000))
    print(f"TRION Oracle + Frontend serving on http://0.0.0.0:{port}", flush=True)
    app.run(host="0.0.0.0", port=port, debug=False)
