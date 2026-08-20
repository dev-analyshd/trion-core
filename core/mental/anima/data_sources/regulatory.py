"""Regulatory Data Source for ANIMA Engine.

Fetches regulatory filings from the SEC EDGAR full-text search (EFTS)
public API (``efts.sec.gov``) — no API key required.

Used for Sovereign Behavioral Assessment (SBA) and institutional signals.

Phase 3 fix: the prior implementation called the right host but parsed the
wrong JSON fields (`form_type`, `entity_name`, `entity_id`) — the real EFTS
payload uses `form`, `display_names[]`, and `ciks[]`. Fixed to match the
actual response schema returned by the live SEC endpoint.
"""
import json, time, urllib.parse, urllib.request
from typing import Dict, Any, List

_CACHE: Dict[str, Any] = {}
_CACHE_TTL = 600   # 10 minutes


def fetch_sec_filings(query: str = "blockchain cryptocurrency", limit: int = 10) -> List[Dict]:
    """Fetch SEC EDGAR full-text search results (public, no API key needed).

    Uses the official EFTS endpoint at https://efts.sec.gov/LATEST/search-index
    which returns an Elasticsearch-style payload:
        {"hits": {"total": ..., "hits": [{"_id": ..., "_source": {
            "form": "10-K", "file_date": "2024-...", "display_names": ["Apple Inc."],
            "ciks": ["0000320193"], "adsh": "0000320193-24-...", ...
        }}]}}
    """
    cache_key = f"sec:{query}"
    cached = _CACHE.get(cache_key)
    if cached and time.time() - cached["ts"] < _CACHE_TTL:
        return cached["data"][:limit]

    params = urllib.parse.urlencode({
        "q":          query,
        "dateRange":  "custom",
        "startdt":    "2024-01-01",
        "forms":      "10-K,10-Q,8-K",
    })
    url = f"https://efts.sec.gov/LATEST/search-index?{params}"

    try:
        req = urllib.request.Request(url, headers={
            # SEC requires a UA with a contact email — otherwise 403.
            "User-Agent": "TRION-ANIMA/2.0 research@example.com",
            "Accept":     "application/json",
        })
        with urllib.request.urlopen(req, timeout=15) as resp:
            data = json.loads(resp.read().decode("utf-8", errors="replace"))
            raw_hits = data.get("hits", {}).get("hits", [])
            results: List[Dict] = []
            for hit in raw_hits[:limit]:
                src = hit.get("_source", {})
                display_names = src.get("display_names") or []
                ciks           = src.get("ciks") or []
                accession      = src.get("adsh", "")
                # SEC accession numbers use dashes in URLs but no dashes in CIK paths.
                acc_no_dash   = accession.replace("-", "")
                cik            = ciks[0] if ciks else ""
                results.append({
                    "filing_type": src.get("form", src.get("root_forms", [""])[0]
                                              if src.get("root_forms") else ""),
                    "filed_date":  src.get("file_date", ""),
                    "company":     display_names[0] if display_names else "",
                    "cik":         cik,
                    "accession":   accession,
                    "url": (
                        f"https://www.sec.gov/cgi-bin/browse-edgar?action=getcompany&CIK={cik}"
                        f"&type=&dateb=&owner=include&count=40"
                    ) if cik else "",
                    "doc_url": (
                        f"https://www.sec.gov/Archives/edgar/data/{int(cik)}/{acc_no_dash}/"
                        f"{src.get('_source_file', accession + '-index.htm')}"
                    ) if cik and accession else "",
                    "excerpt":     display_names[0] if display_names else "",
                })
            _CACHE[cache_key] = {"ts": time.time(), "data": results}
            return results
    except (urllib.error.URLError, urllib.error.HTTPError, json.JSONDecodeError, OSError):
        return []


def compute_regulatory_signal(query: str = "blockchain cryptocurrency") -> Dict[str, Any]:
    """Compute structured regulatory signal for ANIMA SBA plane."""
    filings = fetch_sec_filings(query, 10)
    if not filings:
        return {
            "source":        "regulatory",
            "query":         query,
            "filing_count":  0,
            "sba_score":     0.0,
            "filings":       [],
        }

    # SBA proxy: more regulatory filings mentioning crypto = higher institutional engagement
    sba_score = min(1.0, len(filings) / 10.0)

    # Group by filing type
    type_counts: Dict[str, int] = {}
    for f in filings:
        ft = f["filing_type"] or "UNKNOWN"
        type_counts[ft] = type_counts.get(ft, 0) + 1

    return {
        "source":        "regulatory",
        "query":         query,
        "filing_count":  len(filings),
        "sba_score":     sba_score,
        "filing_types":  type_counts,
        "filings":       filings[:5],
    }


if __name__ == "__main__":
    import pprint
    pprint.pprint(compute_regulatory_signal())
