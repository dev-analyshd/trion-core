"""
TRION Protocol — Sovereign Data Fetcher (SBA economic indicators)
================================================================

Real fetchers for the macroeconomic / governance data sources that feed the
Economic Stability (E) and Institutional Integrity (I) components of the
Sovereign Behavioral Assessment (SBA) — see ``sovereign_behavioral.py``.

Wires the public APIs used in the whitepaper's F11 falsification condition:

  - IMF DataMapper API        → GDP real growth (NGDP_RPCH)
  - World Bank API            → GDP current USD (NY.GDP.MKTP.CD)
  - World Bank API            → Ease of Doing Business (IC.BUS.EASE.XQ)

All fetchers:
  - use only ``urllib.request`` (no external deps)
  - keep a 5-minute in-memory TTL cache (thread-safe)
  - degrade gracefully on any network / parse error → return an empty dict
    (so callers can fall back to defaults without try/except gymnastics)

Author: TRION Protocol — Originator: Hudu Yusuf (Analys)
License: CC0
"""

from __future__ import annotations

import json
import threading
import time
import urllib.error
import urllib.parse
import urllib.request
from typing import Any, Dict, List, Optional


# ─────────────────────────────────────────────────────────────────────────────
# Cache (5-minute TTL, thread-safe)
# ─────────────────────────────────────────────────────────────────────────────

_CACHE_TTL_SECONDS: float = 300.0     # 5 minutes
_CACHE: Dict[str, Dict[str, Any]] = {}  # key -> {"ts": float, "data": Any}
_CACHE_LOCK = threading.Lock()

DEFAULT_TIMEOUT: float = 12.0
DEFAULT_USER_AGENT: str = (
    "TRION-Protocol/2.0 (+sovereign-behavioral; "
    "contact@trion.example.com)"
)


def _cache_get(key: str) -> Optional[Any]:
    """Return cached payload if it exists and has not expired, else None."""
    with _CACHE_LOCK:
        entry = _CACHE.get(key)
        if entry is None:
            return None
        if time.time() - entry["ts"] > _CACHE_TTL_SECONDS:
            _CACHE.pop(key, None)
            return None
        return entry["data"]


def _cache_set(key: str, data: Any) -> None:
    with _CACHE_LOCK:
        _CACHE[key] = {"ts": time.time(), "data": data}


def clear_cache() -> None:
    """Clear the sovereign-data cache. Used by tests / refresh on demand."""
    with _CACHE_LOCK:
        _CACHE.clear()


def set_cache_ttl(seconds: float) -> None:
    """Override the global cache TTL (mainly for tests)."""
    global _CACHE_TTL_SECONDS
    _CACHE_TTL_SECONDS = max(0.0, float(seconds))


# ─────────────────────────────────────────────────────────────────────────────
# Low-level HTTP fetch
# ─────────────────────────────────────────────────────────────────────────────

def _http_get_json(
    url: str,
    timeout: float = DEFAULT_TIMEOUT,
    user_agent: str = DEFAULT_USER_AGENT,
) -> Dict[str, Any]:
    """GET a URL and decode JSON. Raises on any HTTP / parse error."""
    req = urllib.request.Request(url, headers={"User-Agent": user_agent,
                                               "Accept": "application/json"})
    with urllib.request.urlopen(req, timeout=timeout) as resp:
        raw = resp.read()
    return json.loads(raw.decode("utf-8", errors="replace"))


# ─────────────────────────────────────────────────────────────────────────────
# IMF DataMapper  (NGDP_RPCH — real GDP growth, %)
# ─────────────────────────────────────────────────────────────────────────────

IMF_NGDP_RPCH_URL = (
    "https://www.imf.org/external/datamapper/api/v1/NGDP_RPCH"
)


def fetch_imf_data(
    url: str = IMF_NGDP_RPCH_URL,
    use_cache: bool = True,
) -> Dict[str, Any]:
    """
    Fetch IMF DataMapper data for the given indicator.

    Returns the parsed JSON response, which is structured as::

        {
          "values": {"NGDP_RPCH": {"USA": {"2024": 2.6, "2023": 2.5, ...}, ...}},
          "dates":  ["2023", "2024", ...]
        }

    On any network/parse error returns an empty dict (``{}``) so callers
    can use ``.get(...)`` chains without try/except.
    """
    if use_cache:
        cached = _cache_get(url)
        if cached is not None:
            return cached

    try:
        data = _http_get_json(url)
    except (urllib.error.URLError, urllib.error.HTTPError,
            json.JSONDecodeError, OSError, TimeoutError):
        return {}

    if not isinstance(data, dict):
        return {}

    _cache_set(url, data)
    return data


def fetch_imf_gdp_growth(use_cache: bool = True) -> Dict[str, Dict[str, float]]:
    """
    Convenience wrapper returning just the country → {year: growth_pct} mapping
    from IMF NGDP_RPCH. Empty dict on failure.
    """
    payload = fetch_imf_data(use_cache=use_cache)
    if not payload:
        return {}
    values = payload.get("values", {})
    if not isinstance(values, dict) or not values:
        return {}
    indicator_block = values.get("NGDP_RPCH")
    if not isinstance(indicator_block, dict):
        # fall back: maybe the indicator name is the only key
        first_key = next(iter(values))
        indicator_block = values.get(first_key, {})
    if not isinstance(indicator_block, dict):
        return {}
    return {
        country: {year: float(v) for year, v in yearly.items()
                  if v is not None}
        for country, yearly in indicator_block.items()
        if isinstance(yearly, dict)
    }


# ─────────────────────────────────────────────────────────────────────────────
# World Bank API
# ─────────────────────────────────────────────────────────────────────────────

WORLDBANK_GDP_URL = (
    "https://api.worldbank.org/v2/country/all/indicator/"
    "NY.GDP.MKTP.CD?format=json&per_page=400"
)
WORLDBANK_EASE_URL = (
    "https://api.worldbank.org/v2/country/all/indicator/"
    "IC.BUS.EASE.XQ?format=json&per_page=400"
)


def _worldbank_fetch(
    url: str,
    use_cache: bool = True,
) -> Dict[str, Dict[str, float]]:
    """
    Generic World Bank fetcher.

    World Bank returns a 2-element JSON list:
      [0] = pagination metadata
      [1] = list of {country, countryiso3code, date, value, indicator, ...}

    We reshape it to ``{countryiso3code: {year: value}}`` for ease of use
    in the SBA economic-stability component. Returns ``{}`` on failure.
    """
    if use_cache:
        cached = _cache_get(url)
        if cached is not None:
            return cached

    try:
        raw = _http_get_json(url)
    except (urllib.error.URLError, urllib.error.HTTPError,
            json.JSONDecodeError, OSError, TimeoutError):
        return {}

    if not isinstance(raw, list) or len(raw) < 2:
        return {}

    records = raw[1]
    if not isinstance(records, list):
        return {}

    out: Dict[str, Dict[str, float]] = {}
    for rec in records:
        if not isinstance(rec, dict):
            continue
        iso = rec.get("countryiso3code") or ""
        if not iso:
            continue
        year = str(rec.get("date", ""))
        value = rec.get("value")
        if value is None:
            continue
        try:
            value_f = float(value)
        except (TypeError, ValueError):
            continue
        out.setdefault(iso, {})[year] = value_f

    _cache_set(url, out)
    return out


def fetch_worldbank_gdp(use_cache: bool = True) -> Dict[str, Dict[str, float]]:
    """
    Fetch GDP (current USD, NY.GDP.MKTP.CD) for all countries from World Bank.

    Returns ``{iso3: {year: gdp_usd}}``. Empty dict on failure.
    """
    return _worldbank_fetch(WORLDBANK_GDP_URL, use_cache=use_cache)


def fetch_worldbank_ease_of_doing_business(
    use_cache: bool = True,
) -> Dict[str, Dict[str, float]]:
    """
    Fetch Ease of Doing Business index (IC.BUS.EASE.XQ, 1=best, 190=worst)
    for all countries from World Bank.

    Returns ``{iso3: {year: ease_score}}``. Empty dict on failure.
    """
    return _worldbank_fetch(WORLDBANK_EASE_URL, use_cache=use_cache)


# ─────────────────────────────────────────────────────────────────────────────
# Unified sovereign economic snapshot
# ─────────────────────────────────────────────────────────────────────────────

def fetch_sovereign_economic_snapshot(
    use_cache: bool = True,
) -> Dict[str, Any]:
    """
    Aggregate IMF + World Bank data into a single snapshot dict suitable for
    SBA's Economic Stability (E) component and the "stated policy" proxy.

    Returned shape::

        {
          "imf_gdp_growth":   {country: {year: growth_pct}},
          "wb_gdp_usd":       {iso3: {year: gdp_usd}},
          "wb_ease_of_doing": {iso3: {year: ease_score}},
          "fetched_at":       float,        # unix ts
          "sources_ok":       List[str],    # which fetchers succeeded
          "sources_failed":   List[str],
        }

    Never raises. Empty dict fields remain ``{}`` on per-source failure.
    """
    snapshot: Dict[str, Any] = {
        "imf_gdp_growth":   {},
        "wb_gdp_usd":       {},
        "wb_ease_of_doing": {},
        "fetched_at":       time.time(),
        "sources_ok":       [],
        "sources_failed":   [],
    }

    try:
        imf = fetch_imf_gdp_growth(use_cache=use_cache)
        if imf:
            snapshot["imf_gdp_growth"] = imf
            snapshot["sources_ok"].append("imf")
        else:
            snapshot["sources_failed"].append("imf")
    except Exception:                          # pragma: no cover — defensive
        snapshot["sources_failed"].append("imf")

    try:
        wb_gdp = fetch_worldbank_gdp(use_cache=use_cache)
        if wb_gdp:
            snapshot["wb_gdp_usd"] = wb_gdp
            snapshot["sources_ok"].append("worldbank_gdp")
        else:
            snapshot["sources_failed"].append("worldbank_gdp")
    except Exception:                          # pragma: no cover — defensive
        snapshot["sources_failed"].append("worldbank_gdp")

    try:
        wb_ease = fetch_worldbank_ease_of_doing_business(use_cache=use_cache)
        if wb_ease:
            snapshot["wb_ease_of_doing"] = wb_ease
            snapshot["sources_ok"].append("worldbank_ease")
        else:
            snapshot["sources_failed"].append("worldbank_ease")
    except Exception:                          # pragma: no cover — defensive
        snapshot["sources_failed"].append("worldbank_ease")

    return snapshot


def stated_policy_proxy_from_snapshot(
    snapshot: Dict[str, Any],
    country_code: str,
) -> List[float]:
    """
    Build the "stated policy" proxy series used by SBA's I-component
    (``corr(stated_policy, onchain_enforcement)``).

    The proxy uses GDP growth (stated economic policy outcome) over the most
    recent 6 years — governments that publish optimistic GDP targets should
    see real GDP growth aligned with their stated targets. Low or negative
    growth after public commitments → low correlation → low I.

    Returns a list of recent growth percentages (oldest → newest).
    On any data-missing path returns an empty list (the SBA corr function
    falls back to a neutral 0.5 when n<3).
    """
    if not isinstance(snapshot, dict):
        return []
    imf = snapshot.get("imf_gdp_growth", {})
    if not imf:
        return []

    # IMF keys are country names or ISO codes depending on the dataset.
    # Try exact match first, then case-insensitive match.
    if country_code in imf:
        yearly = imf[country_code]
    else:
        lc = country_code.lower()
        yearly = None
        for k, v in imf.items():
            if k.lower() == lc:
                yearly = v
                break
        if yearly is None:
            return []

    if not isinstance(yearly, dict) or not yearly:
        return []

    sorted_years = sorted(yearly.keys())
    # Take most recent 6 years — keep chronological order (oldest → newest)
    recent = sorted_years[-6:]
    return [float(yearly[y]) for y in recent if yearly.get(y) is not None]


if __name__ == "__main__":  # pragma: no cover — manual smoke test
    snap = fetch_sovereign_economic_snapshot(use_cache=False)
    print("Sovereign economic snapshot fetched:")
    print(f"  IMF growth countries:    {len(snap['imf_gdp_growth'])}")
    print(f"  WorldBank GDP countries: {len(snap['wb_gdp_usd'])}")
    print(f"  WorldBank ease countries:{len(snap['wb_ease_of_doing'])}")
    print(f"  Sources OK:   {snap['sources_ok']}")
    print(f"  Sources fail: {snap['sources_failed']}")
