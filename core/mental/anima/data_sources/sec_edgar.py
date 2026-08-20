"""SEC EDGAR data source — delegates to the real fetcher."""

from core.mental.anima.sec_edgar_fetcher import (
    get_recent_filings,
    credibility_for_source,
    SECEdgarFetcher,
)

def fetch_sec_edgar(cik: str = "0000789019", form_type: str = "10-K") -> list:
    """Fetch recent SEC filings for a given CIK."""
    return get_recent_filings(cik, form_type)

def compute_sec_edgar_signal(cik: str = "0000789019") -> dict:
    """Compute structured SEC EDGAR signal for ANIMA."""
    filings = fetch_sec_edgar(cik)
    return {
        "source": "sec_edgar",
        "cik": cik,
        "filing_count": len(filings),
        "filings": filings[:5],
        "credibility": credibility_for_source(),
    }
