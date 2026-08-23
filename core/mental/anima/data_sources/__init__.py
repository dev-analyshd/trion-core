"""TRION Protocol — core.mental.anima.data_sources

Real external data source fetchers for the ANIMA intelligence engine.

Each module implements one fetcher backed by a real public API:
  - github_activity.py  → GitHub Events API (api.github.com)
  - academic.py         → arXiv API (export.arxiv.org)
  - regulatory.py       → SEC EDGAR full-text search + CFTC/ESMA RSS
  - ecological.py       → IUCN Red List API + GBIF Occurrence API
  - sec_edgar.py        → thin wrapper around core/mental/anima/sec_edgar_fetcher.py
  - news.py             → 20+ crypto news RSS feeds (CoinDesk, CoinTelegraph, ...)

Shared infrastructure (caching, rate limiting, HTTP helpers) lives in the
``_base`` module so each fetcher can stay focused on its domain logic.

Whitepaper §8.2 (ANIMA plane) calls for "1,000+ concurrent crawlers" backed
by real data sources. The fetchers here are the single-source building blocks;
an :class:`~core.mental.anima.data_streams.ANIMADataAggregator` orchestrates
them into the unified :class:`~core.mental.anima.data_streams.ANIMADataStreamBundle`.
"""

from ._base import (  # noqa: F401
    BaseFetcher,
    TTLCache,
    RateLimiter,
    http_get,
    http_get_json,
    parse_xml,
    safe_float,
    safe_int,
    now_ts,
    DEFAULT_TIMEOUT,
    DEFAULT_TTL,
    DEFAULT_USER_AGENT,
)
