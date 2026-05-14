"""
TRION Sensing Oracle — unified server (frontend + Oracle API on port 5000).
The Flask app in oracle_api/app.py serves both the static frontend and all /api/v1/* routes.
"""
import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "oracle_api"))
from app import app

if __name__ == "__main__":
    port = int(os.environ.get("PORT", 5000))
    print(f"TRION Oracle + Frontend serving on http://0.0.0.0:{port}", flush=True)
    app.run(host="0.0.0.0", port=port, debug=False)
