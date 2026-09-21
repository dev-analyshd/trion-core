"""
TRION Protocol — World Bank + IMF Live Data Feed
================================================
Fetches real economic indicators from the World Bank API (api.worldbank.org)
and maps them to SBA (Sovereign Behavioral Assessment) components.

Whitepaper L8.1 SBA components:
  S_signaling_credibility    ← Regulatory Quality + Voice & Accountability
  C_currency_alignment       ← Inflation rate + Currency stability
  E_economic_regularity      ← GDP growth stability
  G_geopolitical_coherence   ← Rule of Law + Political Stability
  I_institutional_integrity  ← Government Effectiveness + Control of Corruption

Falls back to honestly-disclosed synthetic data if the API is unreachable.
Caches results for 5 minutes (300s) to avoid rate-limiting.
"""
import os, time, json, math, logging
from typing import Dict, Optional, Tuple
from urllib.request import urlopen, Request
from urllib.parse import urlencode

_log = logging.getLogger("worldbank_feed")
_cache: Dict[str, Tuple[float, dict]] = {}
_CACHE_TTL = 300  # 5 minutes

WB_BASE = "https://api.worldbank.org/v2"

# World Bank indicator codes → TRION SBA component mapping
WB_INDICATORS = {
    "NY.GDP.MKTP.KD.ZG":  "gdp_growth",        # GDP growth (annual %)
    "FP.CPI.TOTL.ZG":      "inflation",          # Inflation, consumer prices (annual %)
    "FI.RES.TOTL.CD":      "reserves",           # Total reserves (includes gold, current US$)
    "NY.GDP.MKTP.CD":      "gdp_usd",            # GDP (current US$)
    "FR.BNK.CBRW.RNGD":    "current_account",    # Current account balance (current US$)
    "RL.EST":              "rule_of_law",        # Rule of Law (WGI estimate, -2.5 to +2.5)
    "CC.EST":              "control_corruption", # Control of Corruption (WGI estimate)
    "GE.EST":              "govt_effectiveness", # Government Effectiveness (WGI estimate)
    "RQ.EST":              "regulatory_quality", # Regulatory Quality (WGI estimate)
    "VA.EST":              "voice_accountability", # Voice & Accountability (WGI estimate)
    "PS.EST":              "political_stability",  # Political Stability (WGI estimate)
}

# IMF DataMapper API (fallback for some indicators)
IMF_BASE = "https://www.imf.org/external/datamapper/api/v1"
IMF_INDICATORS = {
    "NGDP_RPCH": "imf_gdp_growth",    # Real GDP growth
    "PCPIPCH":   "imf_inflation",      # Inflation
    "NGSD_NGDP": "imf_gdp_savings",   # Gross national savings
    "BCA_NGDPD": "imf_current_account", # Current account % GDP
}


def _fetch_json(url: str, timeout: int = 15) -> Optional[dict]:
    """Fetch JSON from URL with timeout."""
    try:
        req = Request(url, headers={"User-Agent": "TRION-Protocol/2.0"})
        with urlopen(req, timeout=timeout) as resp:
            body = resp.read().decode("utf-8", errors="replace")
            return json.loads(body)
    except Exception as e:
        _log.debug("fetch failed for %s: %s", url, str(e)[:100])
        return None


def fetch_worldbank_indicator(nation_code: str, indicator: str, date_range: str = "2020:2023") -> Optional[float]:
    """Fetch a single World Bank indicator for a nation.
    
    Args:
        nation_code: ISO 2-letter country code (NG, US, GB, etc.)
        indicator: World Bank indicator code (e.g. NY.GDP.MKTP.KD.ZG)
        date_range: Year range (e.g. "2020:2023")
    
    Returns:
        Most recent non-null value, or None if unavailable.
    """
    cache_key = f"wb:{nation_code}:{indicator}:{date_range}"
    if cache_key in _cache:
        ts, val = _cache[cache_key]
        if time.time() - ts < _CACHE_TTL:
            return val

    params = urlencode({"format": "json", "date": date_range, "per_page": 20})
    url = f"{WB_BASE}/country/{nation_code}/indicator/{indicator}?{params}"
    data = _fetch_json(url)
    if not data or len(data) < 2 or not data[1]:
        return None

    # Find most recent non-null value
    for obs in data[1]:
        if obs.get("value") is not None:
            val = float(obs["value"])
            _cache[cache_key] = (time.time(), val)
            return val
    return None


def fetch_imf_indicator(nation_code: str, indicator: str) -> Optional[float]:
    """Fetch a single IMF DataMapper indicator for a nation."""
    cache_key = f"imf:{nation_code}:{indicator}"
    if cache_key in _cache:
        ts, val = _cache[cache_key]
        if time.time() - ts < _CACHE_TTL:
            return val

    url = f"{IMF_BASE}/{indicator}/{nation_code}"
    data = _fetch_json(url, timeout=10)
    if not data or "values" not in data:
        return None

    values = data.get("values", {}).get(nation_code, {})
    if not values:
        return None

    # Get most recent year's value
    latest_year = max(values.keys()) if values else None
    if latest_year:
        val = float(values[latest_year])
        _cache[cache_key] = (time.time(), val)
        return val
    return None


def compute_sba_components(nation_code: str) -> Dict:
    """Fetch real economic data and compute SBA components.
    
    Returns dict with:
      - S_signaling_credibility
      - C_currency_alignment
      - E_economic_regularity
      - G_geopolitical_coherence
      - I_institutional_integrity
      - is_synthetic: bool (false if real data was used)
      - data_sources: list of indicator descriptions used
      - raw_values: dict of fetched indicators
    """
    raw = {}
    sources = []
    is_synthetic = False

    # Fetch World Bank indicators
    for wb_code, trion_name in WB_INDICATORS.items():
        val = fetch_worldbank_indicator(nation_code, wb_code)
        if val is not None:
            raw[trion_name] = val
            sources.append(f"WB:{wb_code}={val:.4f}")
        # Try IMF as fallback for economic indicators
        if val is None and wb_code in ("NY.GDP.MKTP.KD.ZG", "FP.CPI.TOTL.ZG"):
            imf_code = {"NY.GDP.MKTP.KD.ZG": "NGDP_RPCH", "FP.CPI.TOTL.ZG": "PCPIPCH"}[wb_code]
            imf_val = fetch_imf_indicator(nation_code, imf_code)
            if imf_val is not None:
                raw[trion_name] = imf_val
                sources.append(f"IMF:{imf_code}={imf_val:.4f}")

    # Compute SBA components from real data
    # S_signaling_credibility: from regulatory_quality (WGI -2.5 to +2.5 → 0 to 1)
    rq = raw.get("regulatory_quality")
    va = raw.get("voice_accountability")
    if rq is not None:
        S = max(0.0, min(1.0, (rq + 2.5) / 5.0))  # normalize -2.5..+2.5 → 0..1
        if va is not None:
            S = (S + max(0.0, min(1.0, (va + 2.5) / 5.0))) / 2.0
    else:
        S = 0.5  # neutral fallback
        is_synthetic = True

    # C_currency_alignment: from inflation (low inflation = high alignment)
    inflation = raw.get("inflation") or raw.get("imf_inflation")
    if inflation is not None:
        # Map: 0% inflation → 1.0, 50% inflation → 0.0
        C = max(0.0, min(1.0, 1.0 - (inflation / 50.0)))
    else:
        C = 0.5
        is_synthetic = True

    # E_economic_regularity: from GDP growth (stable positive growth = high regularity)
    gdp_growth = raw.get("gdp_growth") or raw.get("imf_gdp_growth")
    if gdp_growth is not None:
        # Map: 5-10% growth → 1.0, negative growth → 0.0, >15% (volatile) → 0.5
        if 0 <= gdp_growth <= 10:
            E = 0.5 + (gdp_growth / 20.0)  # 0.5 to 1.0
        elif gdp_growth < 0:
            E = max(0.0, 0.5 + gdp_growth / 10.0)  # 0.0 to 0.5
        else:
            E = max(0.3, 1.0 - (gdp_growth - 10) / 20.0)  # declining above 10%
    else:
        E = 0.5
        is_synthetic = True

    # G_geopolitical_coherence: from rule_of_law + political_stability
    rl = raw.get("rule_of_law")
    ps = raw.get("political_stability")
    if rl is not None:
        G = max(0.0, min(1.0, (rl + 2.5) / 5.0))
        if ps is not None:
            G = (G + max(0.0, min(1.0, (ps + 2.5) / 5.0))) / 2.0
    else:
        G = 0.5
        is_synthetic = True

    # I_institutional_integrity: from govt_effectiveness + control_corruption
    ge = raw.get("govt_effectiveness")
    cc = raw.get("control_corruption")
    if ge is not None:
        I = max(0.0, min(1.0, (ge + 2.5) / 5.0))
        if cc is not None:
            I = (I + max(0.0, min(1.0, (cc + 2.5) / 5.0))) / 2.0
    else:
        I = 0.5
        is_synthetic = True

    # SBA composite: weighted per whitepaper L8.1
    # SBA = w_S·S + w_C·C + w_E·E + w_G·G + w_I·I
    weights = {"S": 0.30, "C": 0.25, "E": 0.20, "G": 0.15, "I": 0.10}
    sba_score = (weights["S"] * S + weights["C"] * C + weights["E"] * E +
                 weights["G"] * G + weights["I"] * I)

    return {
        "S_signaling_credibility":    round(S, 4),
        "C_currency_alignment":       round(C, 4),
        "E_economic_regularity":      round(E, 4),
        "G_geopolitical_coherence":   round(G, 4),
        "I_institutional_integrity":  round(I, 4),
        "sba_score":                  round(sba_score, 4),
        "is_synthetic":               is_synthetic,
        "data_sources":               sources,
        "raw_values":                 {k: round(v, 4) for k, v in raw.items()},
        "nation_code":                nation_code,
    }


if __name__ == "__main__":
    # Test: fetch real data for Nigeria, US, UK
    for nation in ["NG", "US", "GB"]:
        result = compute_sba_components(nation)
        print(f"\n=== {nation} ===")
        print(f"  SBA score: {result['sba_score']:.4f}")
        print(f"  Synthetic: {result['is_synthetic']}")
        print(f"  Sources: {len(result['data_sources'])} indicators")
        for s in result["data_sources"][:5]:
            print(f"    {s}")
        print(f"  Components: S={result['S_signaling_credibility']:.3f} C={result['C_currency_alignment']:.3f} E={result['E_economic_regularity']:.3f} G={result['G_geopolitical_coherence']:.3f} I={result['I_institutional_integrity']:.3f}")
