"""
TRION Protocol — core.mental.anima.data_sources._base
======================================================

Shared infrastructure for the ANIMA external data source fetchers.

Provides:
  - TTLCache        : thread-safe in-memory cache with per-key TTL
  - RateLimiter     : simple token-bucket / min-interval rate limiter
  - http_get        : GET a URL, returns bytes (with UA + timeout)
  - http_get_json   : GET a URL and decode JSON
  - parse_xml       : GET a URL and return ElementTree root
  - BaseFetcher     : base class wiring cache + rate limiter together

Design goals:
  - Pure stdlib + `requests` only — no feedparser / vaderSentiment dependency
    so the fetchers can be imported from environments that only have the
    core/mental Python package (not anima-service).
  - Network failures degrade gracefully — every fetcher returns a structured
    "unavailable" result rather than raising.
  - Caching is opt-in per fetcher via a TTLCache instance.
"""

from __future__ import annotations

import json
import threading
import time
import urllib.error
import urllib.request
import xml.etree.ElementTree as ET
from typing import Any, Dict, Optional, Tuple

DEFAULT_TIMEOUT = 12.0           # seconds
DEFAULT_TTL = 300.0              # 5-minute default cache TTL
DEFAULT_MIN_INTERVAL = 0.5       # 2 req/sec default rate
DEFAULT_USER_AGENT = "TRION-Protocol/2.0 (+research; contact@trion.example.com)"


# ─────────────────────────────────────────────────────────────────────────────
# TTL Cache
# ─────────────────────────────────────────────────────────────────────────────

class TTLCache:
    """
    Thread-safe in-memory cache mapping key → (expires_at, value).

    Usage:
        cache = TTLCache(default_ttl=300.0)
        if cache.has("foo"):
            return cache.get("foo")
        val = compute(...)
        cache.set("foo", val, ttl=120.0)
        return val
    """

    def __init__(self, default_ttl: float = DEFAULT_TTL):
        self._store: Dict[Any, Tuple[float, Any]] = {}
        self._lock = threading.Lock()
        self._default_ttl = default_ttl

    def get(self, key: Any) -> Optional[Any]:
        with self._lock:
            entry = self._store.get(key)
            if entry is None:
                return None
            expires_at, value = entry
            if time.time() > expires_at:
                # Lazy expiry
                self._store.pop(key, None)
                return None
            return value

    def set(self, key: Any, value: Any, ttl: Optional[float] = None) -> None:
        ttl_val = self._default_ttl if ttl is None else ttl
        expires_at = time.time() + ttl_val
        with self._lock:
            self._store[key] = (expires_at, value)

    def has(self, key: Any) -> bool:
        return self.get(key) is not None

    def invalidate(self, key: Any) -> None:
        with self._lock:
            self._store.pop(key, None)

    def clear(self) -> None:
        with self._lock:
            self._store.clear()


# ─────────────────────────────────────────────────────────────────────────────
# Rate Limiter  (simple minimum-interval throttle)
# ─────────────────────────────────────────────────────────────────────────────

class RateLimiter:
    """
    Enforces a minimum interval between consecutive network calls per host.
    Thread-safe.
    """

    def __init__(self, min_interval: float = DEFAULT_MIN_INTERVAL):
        self._min_interval = max(0.0, float(min_interval))
        self._last_at: Dict[str, float] = {}
        self._lock = threading.Lock()

    def wait(self, host: str = "_default") -> None:
        """Block until enough time has passed since the last call to `host`."""
        if self._min_interval <= 0:
            return
        with self._lock:
            now = time.time()
            last = self._last_at.get(host, 0.0)
            elapsed = now - last
            if elapsed < self._min_interval:
                time.sleep(self._min_interval - elapsed)
            self._last_at[host] = time.time()


# ─────────────────────────────────────────────────────────────────────────────
# HTTP helpers
# ─────────────────────────────────────────────────────────────────────────────

def http_get(
    url: str,
    headers: Optional[Dict[str, str]] = None,
    timeout: float = DEFAULT_TIMEOUT,
    user_agent: str = DEFAULT_USER_AGENT,
) -> bytes:
    """
    GET a URL, returning raw bytes. Raises urllib.error.URLError on failure.

    Always sends a User-Agent (SEC EDGAR and GitHub both reject default
    urllib UA strings).
    """
    h = {"User-Agent": user_agent}
    if headers:
        h.update(headers)
    req = urllib.request.Request(url, headers=h)
    with urllib.request.urlopen(req, timeout=timeout) as resp:
        return resp.read()


def http_get_json(
    url: str,
    headers: Optional[Dict[str, str]] = None,
    timeout: float = DEFAULT_TIMEOUT,
    user_agent: str = DEFAULT_USER_AGENT,
) -> Dict[str, Any]:
    """GET a URL and decode JSON. Raises on JSON parse failure."""
    raw = http_get(url, headers=headers, timeout=timeout, user_agent=user_agent)
    return json.loads(raw.decode("utf-8", errors="replace"))


def parse_xml(
    url: str,
    headers: Optional[Dict[str, str]] = None,
    timeout: float = DEFAULT_TIMEOUT,
    user_agent: str = DEFAULT_USER_AGENT,
) -> ET.Element:
    """GET a URL and parse the response as XML, returning the root Element."""
    raw = http_get(url, headers=headers, timeout=timeout, user_agent=user_agent)
    return ET.fromstring(raw.decode("utf-8", errors="replace"))


# ─────────────────────────────────────────────────────────────────────────────
# Numeric coercion
# ─────────────────────────────────────────────────────────────────────────────

def safe_float(value: Any, default: float = 0.0) -> float:
    try:
        if value is None:
            return default
        return float(value)
    except (TypeError, ValueError):
        return default


def safe_int(value: Any, default: int = 0) -> int:
    try:
        if value is None:
            return default
        return int(value)
    except (TypeError, ValueError):
        return default


def now_ts() -> float:
    return time.time()


# ─────────────────────────────────────────────────────────────────────────────
# Base fetcher
# ─────────────────────────────────────────────────────────────────────────────

class BaseFetcher:
    """
    Base class for all ANIMA external data source fetchers.

    Subclasses get:
      - self._cache (TTLCache)
      - self._limiter (RateLimiter)
      - self._user_agent
      - self._http_get / _http_get_json / _parse_xml helpers that
        automatically apply rate limiting.
    """

    def __init__(
        self,
        user_agent: str = DEFAULT_USER_AGENT,
        cache_ttl: float = DEFAULT_TTL,
        min_interval: float = DEFAULT_MIN_INTERVAL,
    ):
        self._user_agent = user_agent
        self._cache = TTLCache(default_ttl=cache_ttl)
        self._limiter = RateLimiter(min_interval=min_interval)

    # ── HTTP helpers (apply rate limiting + UA) ──────────────────────────────

    def _host_for(self, url: str) -> str:
        # cheap host extraction (no urllib.parse to keep this method tiny)
        try:
            after_scheme = url.split("://", 1)[1] if "://" in url else url
            return after_scheme.split("/", 1)[0]
        except Exception:
            return "_default"

    def _http_get(
        self,
        url: str,
        headers: Optional[Dict[str, str]] = None,
        timeout: float = DEFAULT_TIMEOUT,
    ) -> bytes:
        self._limiter.wait(self._host_for(url))
        return http_get(url, headers=headers, timeout=timeout,
                        user_agent=self._user_agent)

    def _http_get_json(
        self,
        url: str,
        headers: Optional[Dict[str, str]] = None,
        timeout: float = DEFAULT_TIMEOUT,
    ) -> Dict[str, Any]:
        self._limiter.wait(self._host_for(url))
        return http_get_json(url, headers=headers, timeout=timeout,
                             user_agent=self._user_agent)

    def _parse_xml(
        self,
        url: str,
        headers: Optional[Dict[str, str]] = None,
        timeout: float = DEFAULT_TIMEOUT,
    ) -> ET.Element:
        self._limiter.wait(self._host_for(url))
        return parse_xml(url, headers=headers, timeout=timeout,
                         user_agent=self._user_agent)

    # ── Convenience ──────────────────────────────────────────────────────────

    @staticmethod
    def _unavailable(source: str, err: Exception) -> Dict[str, Any]:
        """Build a structured 'unavailable' result."""
        return {
            "source":  source,
            "status":  "unavailable",
            "error":   f"{type(err).__name__}: {err}",
            "score":   0.50,   # neutral prior — never zero out ANIMA from a single fetch failure
            "retrieved_at": now_ts(),
        }
