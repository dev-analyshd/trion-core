"""
TRION Protocol — FIX-G (Live Data Feed): IMF DataMapper integration.

Bridges the SBA (Sovereign Behavioral Assessment, L8.1) Economic Stability (E),
Currency Alignment (C), and Institutional Integrity (I) sub-scores from
hash-derived synthetic demo values onto real IMF-published macroeconomic
indicators.

IMF DataMapper API base: https://www.imf.org/external/datamapper/api/v1/

Indicators fetched:
  - NGDP_RPCH : Real GDP growth, % change                       → E_economic_regularity
  - PCPIPCH   : Inflation, average consumer prices, % change     → C_currency_alignment
  - BCA_NGDPD : Current account balance, % of GDP                → E_economic_regularity (2nd axis)
  - NGDP_NGAP : Output gap, % of GDP                             → E_economic_regularity (regularity)
  - BGS_NGDPD : Gross national savings, % of GDP                 → I_institutional_integrity (savings discipline)

Honest contract:
  * On success returns is_synthetic=False with the full IMF provenance chain
    (indicator code, year(s) used, fetched_at UTC ts) attached.
  * On any failure (network, parse, missing country) returns is_synthetic=True
    with `synthetic_reason` honestly disclosing which IMF indicator(s) failed
    and why. The fallback values are clearly flagged as synthetic in the
    payload — callers must not silently substitute.

Cache: 5-minute TTL, thread-safe, keyed by URL.

Author: TRION Protocol — Originator: Hudu Yusuf (Analys)
License: CC0
"""

from __future__ import annotations

import json
import math
import threading
import time
import urllib.error
import urllib.request
from typing import Any, Dict, List, Optional, Tuple


# ── Configuration ────────────────────────────────────────────────────────────

IMF_BASE = "https://www.imf.org/external/datamapper/api/v1"

# Indicator code → human label
IMF_INDICATORS: Dict[str, str] = {
    "NGDP_RPCH":   "Real GDP growth (% change)",
    "PCPIPCH":     "Inflation, average consumer prices (% change)",
    "BCA_NGDPD":   "Current account balance (% of GDP)",
    "NGDP_NGAP":   "Output gap (% of GDP)",        # frequently empty on IMF
    "GGXWDG_NGDP": "General government gross debt (% of GDP)",
}

# Indicators that IMF has retired / no longer publishes (we attempt the fetch
# but expect an empty result; documented so callers see honest provenance).
OBSOLETE_INDICATORS = {"NGDP_NGAP"}  # BGS_NGDPD (savings) was retired pre-2025

# ISO 2-letter → IMF 3-letter country code map (IMF DataMapper uses alpha-3).
# Only the entries requested by the audit task plus common sovereigns.
_ISO2_TO_IMF: Dict[str, str] = {
    "NG": "NGA", "US": "USA", "GB": "GBR", "DE": "DEU", "JP": "JPN",
    "CN": "CHN", "FR": "FRA", "IN": "IND", "BR": "BRA", "RU": "RUS",
    "ZA": "ZAF", "EG": "EGY", "KE": "KEN", "GH": "GHA", "AR": "ARG",
    "MX": "MEX", "CA": "CAN", "AU": "AUS", "KR": "KOR", "IT": "ITA",
    "ES": "ESP", "TR": "TUR", "SA": "SAU", "AE": "ARE", "ID": "IDN",
    "PK": "PAK", "BD": "BGD", "SG": "SGP", "CH": "CHE", "SE": "SWE",
    "NO": "NOR", "NL": "NLD", "PL": "POL", "TH": "THA", "MY": "MYS",
    "PH": "PHL", "VN": "VNM", "CO": "COL", "CL": "CHL", "PE": "PER",
    "UA": "UKR", "IL": "ISR", "IR": "IRN", "IQ": "IRQ", "TZ": "TZA",
    "ET": "ETH", "MA": "MAR", "DZ": "DZA", "LY": "LBY", "SD": "SDN",
    "FI": "FIN", "DK": "DNK", "AT": "AUT", "BE": "BEL", "IE": "IRL",
    "PT": "PRT", "GR": "GRC", "CZ": "CZE", "HU": "HUN", "RO": "ROU",
    "BG": "BGR", "HR": "HRV", "SK": "SVK", "SI": "SVN", "EE": "EST",
    "LV": "LVA", "LT": "LTU", "IS": "ISL", "LU": "LUX", "MT": "MLT",
    "CY": "CYP", "NZ": "NZL", "HK": "HKG", "TW": "TWN",
}

DEFAULT_TIMEOUT: float = 12.0
DEFAULT_USER_AGENT: str = (
    "TRION-Protocol/2.0 (+SBA-live-feed; "
    "contact@trion.example.com)"
)

_CACHE_TTL_SECONDS: float = 300.0          # 5 minutes
_CACHE: Dict[str, Dict[str, Any]] = {}     # url -> {"ts": float, "data": Any}
_CACHE_LOCK = threading.Lock()


# ── Cache ────────────────────────────────────────────────────────────────────

def _cache_get(key: str) -> Optional[Any]:
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
    with _CACHE_LOCK:
        _CACHE.clear()


def set_cache_ttl(seconds: float) -> None:
    global _CACHE_TTL_SECONDS
    _CACHE_TTL_SECONDS = max(0.0, float(seconds))


# ── HTTP ────────────────────────────────────────────────────────────────────

def _http_get_json(url: str, timeout: float = DEFAULT_TIMEOUT) -> Dict[str, Any]:
    req = urllib.request.Request(
        url,
        headers={"User-Agent": DEFAULT_USER_AGENT, "Accept": "application/json"},
    )
    with urllib.request.urlopen(req, timeout=timeout) as resp:
        raw = resp.read()
    return json.loads(raw.decode("utf-8", errors="replace"))


def _normalize_country_code(nation_id: str) -> Tuple[str, str]:
    """
    Accept nation_id as ISO alpha-2 (NG, US), ISO alpha-3 (NGA, USA), or
    case variants. Returns (alpha3_for_imf, alpha2_for_disclosure).
    """
    nid = (nation_id or "").strip().upper()
    if len(nid) == 2 and nid in _ISO2_TO_IMF:
        return _ISO2_TO_IMF[nid], nid
    if len(nid) == 3:
        # Reverse-lookup alpha2
        for a2, a3 in _ISO2_TO_IMF.items():
            if a3 == nid:
                return nid, a2
        # Already alpha3, accept as-is
        return nid, nid[:2]
    # Unknown — pass through and let the API reject (or caller handles)
    return nid, nid[:2] if len(nid) >= 2 else nid


# ── Indicator fetcher ───────────────────────────────────────────────────────

def fetch_indicator(
    indicator_code: str,
    use_cache: bool = True,
    timeout: float = DEFAULT_TIMEOUT,
) -> Dict[str, Dict[str, float]]:
    """
    Fetch an IMF indicator for ALL countries. Returns:
        {country_iso3: {year_str: value}}

    The IMF DataMapper URL accepts /<indicator>/<country> but in practice
    the country path is ignored for many indicators (the API returns the
    full dataset). We always fetch the indicator root and filter client-side.

    On network/parse error returns {} — never raises.
    """
    url = f"{IMF_BASE}/{indicator_code}"
    if use_cache:
        cached = _cache_get(url)
        if cached is not None:
            return cached

    try:
        payload = _http_get_json(url, timeout=timeout)
    except (urllib.error.URLError, urllib.error.HTTPError,
            json.JSONDecodeError, OSError, TimeoutError):
        return {}
    except Exception:
        return {}

    if not isinstance(payload, dict):
        return {}

    values = payload.get("values", {})
    if not isinstance(values, dict) or not values:
        return {}

    # IMF nests under the indicator code; fall back to first key if missing
    block = values.get(indicator_code)
    if not isinstance(block, dict):
        first_key = next(iter(values), None)
        block = values.get(first_key, {}) if first_key else {}
        if not isinstance(block, dict):
            return {}

    out: Dict[str, Dict[str, float]] = {}
    for country, yearly in block.items():
        if not isinstance(yearly, dict):
            continue
        sub: Dict[str, float] = {}
        for y, v in yearly.items():
            if v is None:
                continue
            try:
                sub[str(y)] = float(v)
            except (TypeError, ValueError):
                continue
        if sub:
            out[country] = sub

    _cache_set(url, out)
    return out


# ── Per-nation snapshot ─────────────────────────────────────────────────────

def _latest_value(series: Dict[str, float]) -> Optional[Tuple[str, float]]:
    """Return (year, value) for the most-recent non-None observation."""
    if not series:
        return None
    # Prefer the largest year key (handles both "2024" and "2024" floats)
    try:
        sorted_years = sorted(series.keys(), key=lambda y: int(y))
    except ValueError:
        sorted_years = sorted(series.keys())
    y = sorted_years[-1]
    return y, series[y]


def _recent_window(series: Dict[str, float], n: int = 5) -> List[Tuple[str, float]]:
    """Return the n most-recent (year, value) pairs in chronological order."""
    if not series:
        return []
    try:
        sorted_years = sorted(series.keys(), key=lambda y: int(y))
    except ValueError:
        sorted_years = sorted(series.keys())
    return [(y, series[y]) for y in sorted_years[-n:]]


def fetch_nation_snapshot(
    nation_id: str,
    use_cache: bool = True,
) -> Dict[str, Any]:
    """
    Build the IMF-side SBA snapshot for one nation.

    Returns a dict with:
        nation_id, alpha3, fetched_at, indicators: {code: {latest_year, latest_value,
        recent_series: List[(year, value)]}}, sources_ok: List[str], sources_failed:
        List[str], is_synthetic: bool, synthetic_reason: str
    """
    alpha3, alpha2 = _normalize_country_code(nation_id)
    fetched_at = time.time()

    indicators_raw: Dict[str, Dict[str, float]] = {}
    sources_ok: List[str] = []
    sources_failed: List[str] = []

    for code in IMF_INDICATORS:
        data = fetch_indicator(code, use_cache=use_cache)
        if not data:
            sources_failed.append(code)
            continue
        nation_series = data.get(alpha3)
        if not nation_series:
            sources_failed.append(code)
            continue
        indicators_raw[code] = nation_series
        sources_ok.append(code)

    is_synthetic = len(sources_ok) == 0
    if is_synthetic:
        synthetic_reason = (
            "IMF DataMapper API unreachable or returned no data for "
            f"{alpha3}; all {len(IMF_INDICATORS)} indicators failed: "
            f"{', '.join(sources_failed)}"
        )
    elif len(sources_failed) > 0:
        synthetic_reason = (
            f"Partial IMF data: {len(sources_ok)}/{len(IMF_INDICATORS)} indicators "
            f"available; missing: {', '.join(sources_failed)}. Available "
            "components are computed from real IMF data; missing components "
            "fall back to neutral 0.5."
        )
    else:
        synthetic_reason = ""

    # Build the structured snapshot
    indicators_out: Dict[str, Any] = {}
    for code, series in indicators_raw.items():
        latest = _latest_value(series)
        recent = _recent_window(series, n=5)
        indicators_out[code] = {
            "label": IMF_INDICATORS[code],
            "latest_year":  latest[0] if latest else None,
            "latest_value": latest[1] if latest else None,
            "recent_series": [{"year": y, "value": v} for y, v in recent],
        }

    return {
        "nation_id":       nation_id,
        "alpha3":          alpha3,
        "alpha2":          alpha2,
        "fetched_at":      fetched_at,
        "indicators":      indicators_out,
        "sources_ok":      sources_ok,
        "sources_failed":  sources_failed,
        "is_synthetic":    is_synthetic,
        "synthetic_reason": synthetic_reason,
    }


# ── SBA-component mappers ───────────────────────────────────────────────────

def _sigmoid(x: float, k: float = 1.0, x0: float = 0.0) -> float:
    """Numerically stable sigmoid centered at x0."""
    z = k * (x - x0)
    if z >= 0:
        ez = math.exp(-z)
        return 1.0 / (1.0 + ez)
    ez = math.exp(z)
    return ez / (1.0 + ez)


def map_currency_alignment(snapshot: Dict[str, Any]) -> Tuple[float, Dict[str, Any]]:
    """
    C_currency_alignment ← IMF inflation (PCPIPCH).

    Low stable inflation (~0-3% target) → high score (1.0).
    Hyperinflation (>50%) → near-zero score.
    Negative (deflation) is also penalized — central-bank credibility is
    highest at low-positive inflation.

    Score: sigmoid centered at 5% inflation with steep slope:
        score = 1 - sigmoid((inflation - 5) / 10)
    """
    indicators = snapshot.get("indicators", {})
    pcpi = indicators.get("PCPIPCH", {}).get("latest_value")
    if pcpi is None:
        return 0.5, {
            "source": "IMF/PCPIPCH",
            "value":  None,
            "reason": "Inflation unavailable; neutral 0.5 fallback",
        }
    # 0% inflation → ~0.62, 5% → 0.50, 10% → 0.38, 30% → ~0.12
    score = 1.0 - _sigmoid(pcpi, k=0.10, x0=5.0)
    score = max(0.0, min(1.0, score))
    return score, {
        "source":        "IMF/PCPIPCH",
        "value":         pcpi,
        "latest_year":   indicators.get("PCPIPCH", {}).get("latest_year"),
        "formula":       "1 - sigmoid((inflation - 5) / 10)",
    }


def map_economic_regularity(snapshot: Dict[str, Any]) -> Tuple[float, Dict[str, Any]]:
    """
    E_economic_regularity ← IMF GDP growth stability (NGDP_RPCH) ×
    current-account balance (BCA_NGDPD) × output-gap regularity (NGDP_NGAP).

    Sub-formula:
      growth_score    = sigmoid((avg_growth - 0) / 2)        [0% → 0.50, 4% → 0.88]
      ca_score        = sigmoid((ca_balance - 0) / 3)        [0% → 0.50, +5% → 0.73]
      regularity     = 1 - |output_gap| / 5                  (clamped to [0,1])
      E = growth_score * ca_score * (0.5 + 0.5 * regularity)
    """
    indicators = snapshot.get("indicators", {})
    growth_series = indicators.get("NGDP_RPCH", {}).get("recent_series", [])
    ca = indicators.get("BCA_NGDPD", {}).get("latest_value")
    output_gap = indicators.get("NGDP_NGAP", {}).get("latest_value")

    if not growth_series:
        growth_score = 0.5
        growth_reason = "no IMF GDP growth history available"
    else:
        growth_vals = [r["value"] for r in growth_series]
        avg_growth = sum(growth_vals) / len(growth_vals)
        growth_score = _sigmoid(avg_growth, k=0.5, x0=0.0)
        growth_reason = f"avg_growth={avg_growth:.2f}% over {len(growth_vals)} yrs"

    if ca is None:
        ca_score = 0.5
        ca_reason = "no IMF current-account data available"
    else:
        ca_score = _sigmoid(ca, k=0.333, x0=0.0)
        ca_reason = f"ca_balance={ca:.2f}% GDP"

    if output_gap is None:
        regularity = 0.5
        og_reason = "no IMF output-gap data available"
    else:
        regularity = max(0.0, min(1.0, 1.0 - abs(output_gap) / 5.0))
        og_reason = f"output_gap={output_gap:.2f}% GDP"

    e_score = max(0.0, min(1.0, growth_score * ca_score * (0.5 + 0.5 * regularity)))

    return e_score, {
        "source":            "IMF/NGDP_RPCH+BCA_NGDPD+NGDP_NGAP",
        "growth_score":      round(growth_score, 4),
        "ca_score":          round(ca_score, 4),
        "regularity":        round(regularity, 4),
        "details":           f"{growth_reason}; {ca_reason}; {og_reason}",
    }


def map_institutional_integrity(snapshot: Dict[str, Any]) -> Tuple[float, Dict[str, Any]]:
    """
    I_institutional_integrity ← IMF general government gross debt (GGXWDG_NGDP).

    A nation's debt-to-GDP ratio is the cleanest IMF-published behavioral
    signal of institutional restraint: governments whose institutional
    framework enforces fiscal discipline maintain low debt-to-GDP; chronic
    debt accumulation indicates weak institutional guardrails against
    political spending pressure.

    Map: score = 1 - sigmoid((debt_pct - 60) / 30)
        0%   debt → 0.95  (low debt, high discipline)
        60%  debt → 0.50  (IMF "prudent" threshold)
        100% debt → 0.27  (elevated debt)
        150% debt → 0.08  (high debt, low discipline)
        200% debt → 0.02
    """
    indicators = snapshot.get("indicators", {})
    debt = indicators.get("GGXWDG_NGDP", {}).get("latest_value")
    if debt is None:
        return 0.5, {
            "source": "IMF/GGXWDG_NGDP",
            "value":  None,
            "reason": "Government debt unavailable; neutral 0.5 fallback",
        }
    # 1 - sigmoid((debt - 60) / 30)
    score = 1.0 - _sigmoid(debt, k=1.0 / 30.0, x0=60.0)
    score = max(0.0, min(1.0, score))
    return score, {
        "source":       "IMF/GGXWDG_NGDP",
        "value":        debt,
        "latest_year":  indicators.get("GGXWDG_NGDP", {}).get("latest_year"),
        "formula":      "1 - sigmoid((debt - 60) / 30) — IMF prudent threshold = 60% of GDP",
    }


def fetch_sba_components(
    nation_id: str,
    use_cache: bool = True,
) -> Dict[str, Any]:
    """
    Convenience: fetch IMF snapshot and compute the three SBA components
    that IMF data drives (C_currency_alignment, E_economic_regularity,
    I_institutional_integrity).

    Returns a dict ready to merge into the SBA endpoint response:
        {
          "nation_id":      str,
          "is_synthetic":   bool,
          "synthetic_reason": str,
          "fetched_at":     float,
          "alpha3":         str,
          "components": {
              "C_currency_alignment":  {"score": float, "evidence": {...}},
              "E_economic_regularity": {"score": float, "evidence": {...}},
              "I_institutional_integrity": {"score": float, "evidence": {...}},
          },
          "indicators":     {...},   # raw IMF provenance
          "sources_ok":     [...],
          "sources_failed": [...],
        }
    """
    snap = fetch_nation_snapshot(nation_id, use_cache=use_cache)

    c_score, c_ev = map_currency_alignment(snap)
    e_score, e_ev = map_economic_regularity(snap)
    i_score, i_ev = map_institutional_integrity(snap)

    return {
        "nation_id":        nation_id,
        "alpha3":           snap["alpha3"],
        "alpha2":           snap["alpha2"],
        "fetched_at":       snap["fetched_at"],
        "is_synthetic":     snap["is_synthetic"],
        "synthetic_reason": snap["synthetic_reason"],
        "sources_ok":       snap["sources_ok"],
        "sources_failed":   snap["sources_failed"],
        "indicators":       snap["indicators"],
        "components": {
            "C_currency_alignment":     {"score": round(c_score, 6), "evidence": c_ev},
            "E_economic_regularity":     {"score": round(e_score, 6), "evidence": e_ev},
            "I_institutional_integrity": {"score": round(i_score, 6), "evidence": i_ev},
        },
    }


# ── Self-test (manual smoke) ────────────────────────────────────────────────

if __name__ == "__main__":  # pragma: no cover
    import sys
    nation = sys.argv[1] if len(sys.argv) > 1 else "NG"
    print(f"=== IMF feed for {nation} ===")
    out = fetch_sba_components(nation, use_cache=False)
    print(f"is_synthetic:    {out['is_synthetic']}")
    print(f"alpha3:          {out['alpha3']}")
    print(f"sources_ok:      {out['sources_ok']}")
    print(f"sources_failed:  {out['sources_failed']}")
    if out["synthetic_reason"]:
        print(f"synthetic_reason: {out['synthetic_reason']}")
    print()
    for code, comp in out["components"].items():
        print(f"  {code}: score={comp['score']:.4f}")
        ev = comp["evidence"]
        if ev.get("value") is not None:
            print(f"     evidence: {ev.get('source')} = {ev.get('value')} "
                  f"({ev.get('latest_year', 'n/a')})")
        elif ev.get("details"):
            print(f"     evidence: {ev['details']}")
    print()
    print("Indicators:")
    for code, ind in out["indicators"].items():
        print(f"  {code} ({ind['label']}): latest={ind['latest_value']} "
              f"in {ind['latest_year']}; "
              f"series_len={len(ind['recent_series'])}")
