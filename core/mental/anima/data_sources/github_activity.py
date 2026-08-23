"""GitHub Activity Data Source for ANIMA Engine.

Fetches repository activity from GitHub public API (60 req/hr without token).
Used to measure developer engagement and protocol health.
"""
import json, time, urllib.request, urllib.error
from typing import List, Dict, Any

_CACHE: Dict[str, Any] = {}
_CACHE_TTL = 300  # 5 minutes

def fetch_github_activity(owner: str = "dev-analyshd", repo: str = "trion-core") -> List[Dict]:
    """Fetch recent GitHub repo events (push, pull_request, issues, releases)."""
    cache_key = f"github:{owner}/{repo}"
    if cache_key in _CACHE and time.time() - _CACHE[cache_key]["ts"] < _CACHE_TTL:
        return _CACHE[cache_key]["data"]
    
    url = f"https://api.github.com/repos/{owner}/{repo}/events?per_page=30"
    req = urllib.request.Request(url, headers={
        "Accept": "application/vnd.github+json",
        "User-Agent": "TRION-ANIMA/2.0",
    })
    try:
        with urllib.request.urlopen(req, timeout=10) as resp:
            events = json.loads(resp.read().decode())
            _CACHE[cache_key] = {"ts": time.time(), "data": events}
            return events
    except (urllib.error.URLError, urllib.error.HTTPError, json.JSONDecodeError):
        return []

def compute_github_signal(owner: str = "dev-analyshd", repo: str = "trion-core") -> Dict[str, Any]:
    """Compute structured GitHub activity signal for ANIMA."""
    events = fetch_github_activity(owner, repo)
    if not events:
        return {"source": "github", "repo": f"{owner}/{repo}", "activity_score": 0.0, "events": []}
    
    event_types = {}
    for evt in events:
        etype = evt.get("type", "unknown")
        event_types[etype] = event_types.get(etype, 0) + 1
    
    # Activity score: more events + more diverse types = higher score
    activity_score = min(1.0, len(events) / 30.0)
    diversity_score = min(1.0, len(event_types) / 8.0)
    
    return {
        "source": "github",
        "repo": f"{owner}/{repo}",
        "activity_score": activity_score,
        "diversity_score": diversity_score,
        "event_count": len(events),
        "event_types": event_types,
        "events": [{"type": e.get("type"), "created_at": e.get("created_at"), "actor": e.get("actor", {}).get("login")} for e in events[:10]],
    }

if __name__ == "__main__":
    import pprint
    pprint.pprint(compute_github_signal())
