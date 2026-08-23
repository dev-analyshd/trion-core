"""Ecological Data Source for ANIMA Engine.

Fetches species/ecosystem data from IUCN Red List and GBIF public APIs.
Used for Biological Capital (BC) and Cross-Species Liquidity (XSL) signals.
"""
import json, time, urllib.request, urllib.parse
from typing import Dict, Any, List

_CACHE: Dict[str, Any] = {}
_CACHE_TTL = 3600  # 1 hour

def fetch_gbif_species(query: str = "coral", limit: int = 10) -> List[Dict]:
    """Fetch species occurrence data from GBIF public API."""
    cache_key = f"gbif:{query}"
    if cache_key in _CACHE and time.time() - _CACHE[cache_key]["ts"] < _CACHE_TTL:
        return _CACHE[cache_key]["data"]
    
    params = urllib.parse.urlencode({"q": query, "limit": limit, "hasCoordinate": "true"})
    url = f"https://api.gbif.org/v1/occurrence/search?{params}"
    try:
        req = urllib.request.Request(url, headers={"User-Agent": "TRION-ANIMA/2.0"})
        with urllib.request.urlopen(req, timeout=15) as resp:
            data = json.loads(resp.read().decode())
            results = data.get("results", [])
            _CACHE[cache_key] = {"ts": time.time(), "data": results}
            return results
    except Exception:
        return []

def compute_ecological_signal(species_query: str = "coral reef") -> Dict[str, Any]:
    """Compute structured ecological signal for ANIMA BC/XSL planes."""
    occurrences = fetch_gbif_species(species_query, 20)
    if not occurrences:
        return {"source": "ecological", "query": species_query, "occurrence_count": 0, "bc_score": 0.0}
    
    # Species diversity
    species_set = set()
    threat_statuses = {}
    for occ in occurrences:
        sp = occ.get("species", occ.get("scientificName", "unknown"))
        species_set.add(sp)
        threat = occ.get("iucnRedListCategory", "UNKNOWN")
        threat_statuses[threat] = threat_statuses.get(threat, 0) + 1
    
    # BC score: more diverse species = healthier ecosystem = higher BC
    diversity = min(1.0, len(species_set) / 15.0)
    threatened_count = sum(v for k, v in threat_statuses.items() if k in ("CRITICALLY_ENDANGERED", "ENDANGERED", "VULNERABLE"))
    threat_ratio = threatened_count / max(1, len(occurrences))
    bc_score = diversity * (1 - threat_ratio * 0.5)
    
    return {
        "source": "ecological",
        "query": species_query,
        "occurrence_count": len(occurrences),
        "species_count": len(species_set),
        "diversity_score": diversity,
        "threat_ratio": threat_ratio,
        "threat_statuses": threat_statuses,
        "bc_score": bc_score,
    }

if __name__ == "__main__":
    import pprint
    pprint.pprint(compute_ecological_signal())
