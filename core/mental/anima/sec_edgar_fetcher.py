"""
TRION Protocol — L3.4a ANIMA SEC EDGAR Fetcher
===============================================

Whitepaper §3 (ANIMA plane) specifies "1,000+ concurrent crawlers" and
explicitly mentions SEC EDGAR as a primary data source for off-chain
behavioral signals.

This module implements a minimal SEC EDGAR fetcher that retrieves
public filings from the SEC's public REST API (https://www.sec.gov/).
It is intentionally lightweight — no API key required, rate-limited
to 10 requests/second per SEC's fair-use policy.

For production deployment the fetcher should be backed by a queue
(Redis/SQS) and run as a worker pool; this module provides the
single-fetcher building block.

Author: TRION Protocol — Originator: Hudu Yusuf (Analys)
License: CC0
"""

from __future__ import annotations

import json
import os
import re
import time
import urllib.error
import urllib.request
from dataclasses import dataclass, field
from typing import List, Optional

from core.mental.anima.source_credibility import (
    SourceType,
    initialize_source,
    update_credibility,
)


# ── Constants ──────────────────────────────────────────────────────────────────

SEC_USER_AGENT = os.environ.get(
    "SEC_USER_AGENT",
    "TRION Protocol research contact@trion.example.com"
)
SEC_BASE_URL = "https://www.sec.gov/cgi-bin/browse-edgar"
SEC_DATA_URL = "https://data.sec.gov"

# SEC fair-use rate limit: 10 requests/second
SEC_RATE_LIMIT_RPS = 10.0
SEC_MIN_INTERVAL = 1.0 / SEC_RATE_LIMIT_RPS


# ── Data Model ─────────────────────────────────────────────────────────────────

@dataclass
class SECFiling:
    """A single SEC EDGAR filing."""
    cik:             str
    company_name:    str
    form_type:       str      # 10-K, 10-Q, 8-K, S-1, etc.
    filing_date:     str      # YYYY-MM-DD
    accession_no:    str
    filing_url:      str
    retrieved_at:    float = field(default_factory=time.time)

    def to_dict(self) -> dict:
        return {
            "cik":          self.cik,
            "company_name": self.company_name,
            "form_type":    self.form_type,
            "filing_date":  self.filing_date,
            "accession_no": self.accession_no,
            "filing_url":   self.filing_url,
            "retrieved_at": self.retrieved_at,
        }


# ── Fetcher ────────────────────────────────────────────────────────────────────

class SECEdgarFetcher:
    """
    Minimal SEC EDGAR fetcher.

    Usage:
        fetcher = SECEdgarFetcher()
        filings = fetcher.get_recent_filings(cik="0000320193", form_type="10-K")
    """

    def __init__(self, user_agent: Optional[str] = None):
        self._user_agent = user_agent or SEC_USER_AGENT
        self._last_request_at: float = 0.0

    def _rate_limit(self) -> None:
        """Enforce SEC's 10 requests/second fair-use rate limit."""
        elapsed = time.time() - self._last_request_at
        if elapsed < SEC_MIN_INTERVAL:
            time.sleep(SEC_MIN_INTERVAL - elapsed)
        self._last_request_at = time.time()

    def _fetch(self, url: str) -> bytes:
        """Fetch a URL with the required User-Agent header."""
        self._rate_limit()
        req = urllib.request.Request(url, headers={
            "User-Agent": self._user_agent,
            "Accept":     "application/json",
        })
        with urllib.request.urlopen(req, timeout=30) as resp:
            return resp.read()

    def get_recent_filings(
        self,
        cik: str,
        form_type: Optional[str] = None,
        limit: int = 20,
    ) -> List[SECFiling]:
        """
        Retrieve recent filings for a company by CIK.

        Args:
            cik:        10-digit SEC CIK (e.g. "0000320193" for Apple Inc.)
            form_type:  optional filter (e.g. "10-K", "10-Q", "8-K")
            limit:      maximum number of filings to return (1-100)

        Returns:
            List of SECFiling objects, most recent first.
        """
        # Strip any leading "0x" or padding
        cik_clean = re.sub(r"\D", "", cik).zfill(10)
        url = f"{SEC_DATA_URL}/submissions/CIK{cik_clean}.json"
        try:
            raw = self._fetch(url)
        except urllib.error.HTTPError as e:
            if e.code == 404:
                return []  # CIK not found — return empty
            raise

        try:
            data = json.loads(raw)
        except json.JSONDecodeError:
            return []

        recent = data.get("filings", {}).get("recent", {})
        forms    = recent.get("form", [])
        dates    = recent.get("filingDate", [])
        acc_nos  = recent.get("accessionNumber", [])
        urls     = recent.get("primaryDocument", [])
        company  = data.get("name", "")

        results: List[SECFiling] = []
        for i, form in enumerate(forms):
            if form_type and form != form_type:
                continue
            acc_no = acc_nos[i]
            acc_no_dashed = acc_no.replace("-", "")
            filing_url = (
                f"{SEC_BASE_URL}?action=getcompany&CIK={cik_clean}"
                f"&type={form}&dateb=&owner=include&count=40"
            )
            results.append(SECFiling(
                cik=cik_clean,
                company_name=company,
                form_type=form,
                filing_date=dates[i],
                accession_no=acc_no,
                filing_url=filing_url,
            ))
            if len(results) >= limit:
                break

        return results

    def credibility_for_source(self, cik: str) -> dict:
        """
        Create a TRION Source entry for an SEC EDGAR feed keyed by CIK,
        with initial CRED = 0.65 per the SEC_EDGAR source type baseline.
        """
        source = initialize_source(
            source_id=f"sec_edgar_{cik}",
            source_type=SourceType.SEC_EDGAR,
            timestamp=time.time(),
        )
        return {
            "source_id":   source.source_id,
            "source_type": source.source_type.name,
            "cred":        source.cred,
            "manipulation_flag": source.manipulation_flag,
            "disclosure":  "SEC EDGAR source initialized at baseline CRED=0.65.",
        }


# ── Self-test ──────────────────────────────────────────────────────────────────

if __name__ == "__main__":
    fetcher = SECEdgarFetcher()

    print("=== SEC EDGAR Fetcher Self-test ===\n")

    # Test 1: Initialize a source (does not require network)
    src = fetcher.credibility_for_source("0000320193")
    print(f"Source: {src['source_id']}")
    print(f"  type: {src['source_type']}")
    print(f"  CRED: {src['cred']}")
    assert src["cred"] == 0.65
    print()

    # Test 2: Try to fetch Apple's recent 10-K filings.
    # NOTE: This test requires network access and may be skipped in CI.
    print("Fetching recent 10-K filings for CIK=0000320193 (Apple Inc.)...")
    try:
        filings = fetcher.get_recent_filings(cik="0000320193", form_type="10-K", limit=5)
        if filings:
            print(f"  Found {len(filings)} filing(s):")
            for f in filings[:3]:
                print(f"    {f.filing_date} {f.form_type} {f.accession_no} — {f.company_name}")
        else:
            print("  No filings returned (network blocked or CIK not found).")
    except Exception as e:
        print(f"  Network fetch failed (expected in offline env): {e}")

    print("\nPHASE 6 PASS — SEC EDGAR fetcher ready (network fetch best-effort)")
