"""SEC EDGAR data source — delegates to the real fetcher.

Bridges the L3.4a ANIMA plane SEC EDGAR fetcher (``sec_edgar_fetcher.py``)
into the ``core.mental.anima.data_sources`` namespace so it can be
discovered alongside the other live connectors (github_activity, news,
ecological, academic, regulatory).

The real network + parsing logic lives in
``core.mental.anima.sec_edgar_fetcher.SECEdgarFetcher`` — this module is a
thin facade that instantiates the fetcher once (cached) and exposes the
two functions the rest of the ANIMA stack expects:

    fetch_sec_edgar(cik, form_type)        -> List[dict]
    compute_sec_edgar_signal(cik)         -> dict
"""

from __future__ import annotations

import threading
from typing import List

from core.mental.anima.sec_edgar_fetcher import SECEdgarFetcher


# ── Module-level singleton fetcher (thread-safe lazy init) ─────────────────────
# The SEC fair-use policy is 10 req/sec per IP — a single shared fetcher
# enforces the rate-limit across all callers and keeps the in-process
# credibility registry consistent.
_FETCHER: SECEdgarFetcher | None = None
_FETCHER_LOCK = threading.Lock()


def _get_fetcher() -> SECEdgarFetcher:
    global _FETCHER
    if _FETCHER is None:
        with _FETCHER_LOCK:
            if _FETCHER is None:
                _FETCHER = SECEdgarFetcher()
    return _FETCHER


def fetch_sec_edgar(cik: str = "0000789019", form_type: str = "10-K") -> List[dict]:
    """Fetch recent SEC filings for a given CIK (10-digit zero-padded).

    Returns a list of plain dicts (the dataclass SECFiling serialised via
    ``to_dict()``) so the result is JSON-serialisable for ANIMA signal
    consumers. Returns ``[]`` on network failure or unknown CIK.
    """
    fetcher = _get_fetcher()
    try:
        filings = fetcher.get_recent_filings(cik=cik, form_type=form_type, limit=20)
    except Exception:
        # SEC EDGAR is occasionally unavailable; degrade gracefully.
        return []
    return [f.to_dict() if hasattr(f, "to_dict") else dict(f) for f in filings]


def compute_sec_edgar_signal(cik: str = "0000789019") -> dict:
    """Compute structured SEC EDGAR signal for ANIMA.

    Combines the raw filing list with a credibility snapshot for the source
    so downstream CA (cross-source agreement) weighting has the L3.4
    baseline CRED=0.65 to work with.
    """
    fetcher = _get_fetcher()
    filings = fetch_sec_edgar(cik)
    try:
        cred = fetcher.credibility_for_source(cik)
    except Exception:
        cred = {
            "source_id":   f"sec_edgar_{cik}",
            "source_type": "SEC_EDGAR",
            "cred":        0.65,
            "disclosure":  "credibility_for_source unavailable — baseline CRED=0.65 used.",
        }
    return {
        "source":        "sec_edgar",
        "cik":           cik,
        "filing_count":  len(filings),
        "filings":       filings[:5],
        "credibility":   cred,
    }


if __name__ == "__main__":
    import pprint
    pprint.pprint(compute_sec_edgar_signal("0000320193"))  # Apple Inc.
