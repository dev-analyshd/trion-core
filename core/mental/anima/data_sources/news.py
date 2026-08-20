"""News Data Source for ANIMA Engine.

Fetches crypto/blockchain news from public RSS feeds using feedparser patterns.
Computes VADER-like sentiment for English text.
"""
import time, urllib.request, xml.etree.ElementTree as ET
from typing import List, Dict, Any

_FEEDS = [
    ("CoinDesk", "https://www.coindesk.com/arc/outboundfeeds/rss/"),
    ("CoinTelegraph", "https://cointelegraph.com/rss"),
    ("The Block", "https://www.theblock.co/rss.xml"),
    ("Decrypt", "https://decrypt.co/feed"),
    ("CryptoSlate", "https://cryptoslate.com/feed/"),
    ("Bitcoin Magazine", "https://bitcoinmagazine.com/.rss/full/"),
]

_POSITIVE_WORDS = {"bullish", "surge", "rally", "gain", "growth", "adoption", "breakthrough", "partnership", "launch", "upgrade", "secure", "innovation", "bull", "support", "approve"}
_NEGATIVE_WORDS = {"bearish", "crash", "hack", "exploit", "breach", "loss", "decline", "drop", "fraud", "scam", "rug", "dump", "bear", "ban", "reject", "fail"}

_CACHE: Dict[str, Any] = {}
_CACHE_TTL = 600  # 10 minutes

def _compute_sentiment(text: str) -> float:
    """Simple lexicon-based sentiment, returns 0-1 (0.5 = neutral)."""
    words = set(text.lower().split())
    pos = len(words & _POSITIVE_WORDS)
    neg = len(words & _NEGATIVE_WORDS)
    if pos + neg == 0:
        return 0.5
    return pos / (pos + neg)

def fetch_news(limit: int = 20) -> List[Dict[str, Any]]:
    """Fetch recent crypto news from RSS feeds."""
    cache_key = "news:all"
    if cache_key in _CACHE and time.time() - _CACHE[cache_key]["ts"] < _CACHE_TTL:
        return _CACHE[cache_key]["data"][:limit]
    
    all_items = []
    for source, url in _FEEDS:
        try:
            req = urllib.request.Request(url, headers={"User-Agent": "TRION-ANIMA/2.0"})
            with urllib.request.urlopen(req, timeout=10) as resp:
                root = ET.fromstring(resp.read())
                for item in root.findall(".//item")[:5]:
                    title = item.findtext("title", "")
                    desc = item.findtext("description", "")
                    pub = item.findtext("pubDate", "")
                    link = item.findtext("link", "")
                    text = f"{title} {desc}"
                    all_items.append({
                        "source": source,
                        "title": title,
                        "description": desc[:200],
                        "pubDate": pub,
                        "link": link,
                        "sentiment": _compute_sentiment(text),
                    })
        except Exception:
            continue
    
    _CACHE[cache_key] = {"ts": time.time(), "data": all_items}
    return all_items[:limit]

def compute_news_signal(query: str = "") -> Dict[str, Any]:
    """Compute structured news signal for ANIMA."""
    items = fetch_news(20)
    if not items:
        return {"source": "news", "article_count": 0, "avg_sentiment": 0.5, "items": []}
    
    sentiments = [i["sentiment"] for i in items]
    avg = sum(sentiments) / len(sentiments)
    
    return {
        "source": "news",
        "article_count": len(items),
        "avg_sentiment": avg,
        "sentiment_label": "positive" if avg > 0.6 else "negative" if avg < 0.4 else "neutral",
        "items": items[:10],
    }

if __name__ == "__main__":
    import pprint
    pprint.pprint(compute_news_signal())
