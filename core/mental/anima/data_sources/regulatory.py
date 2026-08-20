"""Regulatory Data Source for ANIMA Engine.

Fetches regulatory filings from SEC EDGAR full-text search.
Used for Sovereign Behavioral Assessment (SBA) and institutional signals.
"""
import json, time, urllib.request, urllib.parse
from typing import Dict, Any, List

_CACHE: Dict[str, Any] = {}
_CACHE_TTL = 600

def fetch_sec_filings(query: str = "blockchain cryptocurrency", limit: int = 10) -> List[Dict]:
    """Fetch SEC EDGAR full-text search results (public, no API key needed)."""
    cache_key = f"sec:{query}"
    if cache_key in _CACHE and time.time() - _CACHE[cache_key]["ts"] < _CACHE_TTL:
        return _CACHE[cache_key]["data"]
    
    params = urllib.parse.urlencode({"q": query, "dateRange": "custom", "startdt": "2024-01-01", "forms": "10-K,10-Q,8-K"})
    url = f"https://efts.sec.gov/LATEST/search-index?{params}"
    
    # Use the full-text search API endpoint
    url = f"https://efts.sec.gov/LATEST/search-index?q={urllib.parse.quote(query)}&dateRange=custom&startdt=2024-01-01&forms=10-K,10-Q,8-K"
    
    try:
        req = urllib.request.Request(url, headers={
            "User-Agent": "TRION-ANIMA/2.0 research@example.com",
            "Accept": "application/json",
        })
        with urllib.request.urlopen(req, timeout=15) as resp:
            data = json.loads(resp.read().decode())
            hits = data.get("hits", {}).get("hits", [])
            results = []
            for hit in hits[:limit]:
                src = hit.get("_source", {})
                results.append({
                    "filing_type": src.get("form_type", ""),
                    "filed_date": src.get("file_date", ""),
                    "company": src.get("entity_name", ""),
                    "cik": src.get("entity_id", ""),
                    "url": f"https://www.sec.gov/cgi-bin/browse-edgar?action=getcompany&CIK={src.get('entity_id', '')}",
                    "excerpt": hit.get("_source", {}).get("display_names", [""])[0] if hit.get("_source", {}).get("display_names") else "",
                })
            _CACHE[cache_key] = {"ts": time.time(), "data": results}
            return results
    except Exception as e:
        return []

def compute_regulatory_signal(query: str = "blockchain cryptocurrency") -> Dict[str, Any]:
    """Compute structured regulatory signal for ANIMA SBA plane."""
    filings = fetch_sec_filings(query, 10)
    if not filings:
        return {"source": "regulatory", "query": query, "filing_count": 0, "sba_score": 0.0}
    
    # SBA proxy: more regulatory filings mentioning crypto = higher institutional engagement
    sba_score = min(1.0, len(filings) / 10.0)
    
    # Group by filing type
    type_counts = {}
    for f in filings:
        ft = f["filing_type"]
        type_counts[ft] = type_counts.get(ft, 0) + 1
    
    return {
        "source": "regulatory",
        "query": query,
        "filing_count": len(filings),
        "sba_score": sba_score,
        "filing_types": type_counts,
        "filings": filings[:5],
    }

if __name__ == "__main__":
    import pprint
    pprint.pprint(compute_regulatory_signal())
