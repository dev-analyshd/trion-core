"""Academic Data Source for ANIMA Engine.

Fetches crypto/security research papers from arXiv public API.
Used for cross-domain intelligence and trend detection.
"""
import time, urllib.request, urllib.parse, xml.etree.ElementTree as ET
from typing import Dict, Any, List

_CACHE: Dict[str, Any] = {}
_CACHE_TTL = 3600

_ARXIV_NS = {"atom": "http://www.w3.org/2005/Atom"}

def fetch_arxiv_papers(query: str = "blockchain security DeFi", limit: int = 10) -> List[Dict]:
    """Fetch papers from arXiv API (public, no API key needed)."""
    cache_key = f"arxiv:{query}"
    if cache_key in _CACHE and time.time() - _CACHE[cache_key]["ts"] < _CACHE_TTL:
        return _CACHE[cache_key]["data"]
    
    params = urllib.parse.urlencode({
        "search_query": f"all:{query}",
        "start": 0,
        "max_results": limit,
        "sortBy": "submittedDate",
        "sortOrder": "descending",
    })
    url = f"http://export.arxiv.org/api/query?{params}"
    
    try:
        req = urllib.request.Request(url, headers={"User-Agent": "TRION-ANIMA/2.0"})
        with urllib.request.urlopen(req, timeout=15) as resp:
            root = ET.fromstring(resp.read())
            entries = root.findall("atom:entry", _ARXIV_NS)
            papers = []
            for entry in entries:
                papers.append({
                    "title": entry.findtext("atom:title", "", _ARXIV_NS).strip().replace("\n", " "),
                    "summary": entry.findtext("atom:summary", "", _ARXIV_NS).strip()[:200],
                    "published": entry.findtext("atom:published", "", _ARXIV_NS),
                    "url": entry.findtext("atom:id", "", _ARXIV_NS),
                    "authors": [a.findtext("atom:name", "", _ARXIV_NS) for a in entry.findall("atom:author", _ARXIV_NS)],
                })
            _CACHE[cache_key] = {"ts": time.time(), "data": papers}
            return papers
    except Exception:
        return []

def compute_academic_signal(query: str = "blockchain security") -> Dict[str, Any]:
    """Compute structured academic signal for ANIMA."""
    papers = fetch_arxiv_papers(query, 10)
    if not papers:
        return {"source": "academic", "query": query, "paper_count": 0, "research_trend": 0.0}
    
    # Research trend: more recent papers = higher trend score
    import datetime
    now = datetime.datetime.now(datetime.timezone.utc)
    recent_count = 0
    for p in papers:
        pub = p.get("published", "")
        if pub:
            try:
                pub_date = datetime.datetime.fromisoformat(pub.replace("Z", "+00:00"))
                if (now - pub_date).days < 90:
                    recent_count += 1
            except:
                pass
    
    research_trend = min(1.0, recent_count / 10.0)
    
    return {
        "source": "academic",
        "query": query,
        "paper_count": len(papers),
        "recent_count": recent_count,
        "research_trend": research_trend,
        "papers": papers[:5],
    }

if __name__ == "__main__":
    import pprint
    pprint.pprint(compute_academic_signal())
