"""
Shared FAISS ANIMA-service client auth (SEC-01 companion)
=========================================================

One resolution point for the X-API-Key secret every internal FAISS client
(Flask API, dashboard proxy, CEX forwarder, BH streamer) must send now that
anima-service/faiss_service.py enforces API-key authentication.

Resolution order MUST stay in lockstep with the service itself:

    FAISS_API_KEY → FAISS_SERVICE_API_KEY → TRION_API_KEY

(the last hop mirrors the Flask Oracle's TRION_API_KEY so a single shared
secret secures both services).  Unset or empty values resolve to None —
callers then send no header, which is correct for public read-only GETs
against a fail-closed service and produces 401/503 on protected routes,
exactly the enforcement matrix the service pins.
"""

from __future__ import annotations

import os
import urllib.request
from typing import Optional


def faiss_api_key() -> Optional[str]:
    """Resolve the FAISS service API key; None when not configured."""
    for var in ("FAISS_API_KEY", "FAISS_SERVICE_API_KEY", "TRION_API_KEY"):
        key = (os.environ.get(var) or "").strip()
        if key:
            return key
    return None


def faiss_headers() -> dict:
    """Header dict for a FAISS request; empty when no key is configured."""
    key = faiss_api_key()
    return {"X-API-Key": key} if key else {}


def faiss_urlopen(url: str, timeout: float = 3.0, data: Optional[bytes] = None,
                  headers: Optional[dict] = None):
    """urlopen() against the FAISS service with X-API-Key attached.

    Drop-in replacement for the bare ``urllib.request.urlopen(url)`` call
    sites used throughout the API layer: builds the Request so the key
    header travels on every call (public GET endpoints simply ignore it),
    merges any caller-supplied headers on top (e.g. Content-Type on POSTs).
    """
    hdrs = faiss_headers()
    if headers:
        hdrs.update(headers)
    req = urllib.request.Request(url, data=data, headers=hdrs or None)
    return urllib.request.urlopen(req, timeout=timeout)
