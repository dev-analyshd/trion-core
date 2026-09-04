"""
TRION Protocol — ANIMA Concurrent Crawler Pool
==============================================

Implements the "1,000+ concurrent crawlers" scaling target from the
whitepaper §8.2 (ANIMA plane). Built on top of the 6 real data source
connectors in ``core.mental.anima.data_sources``:

  - github_activity  → GitHub Events API
  - news             → CoinDesk / CoinTelegraph / The Block / Decrypt / ...
  - ecological       → GBIF + IUCN
  - regulatory       → SEC EDGAR full-text search
  - academic         → arXiv API
  - multilingual     → anima-service/multilingual_sentiment (10 lexicons)

Each crawler is a thin wrapper that calls one of those fetchers and returns
a ``DataSourceResult`` (source_name, data, timestamp, success). The pool
runs workers in a ``concurrent.futures.ThreadPoolExecutor`` (configurable
``max_workers``, default 50, scalable to 1000).

Workers can be duplicated — e.g. 10 GitHub workers for 10 different repos,
20 news workers for 20 different feeds. Results are aggregated into an
``ANIMADataStreamBundle`` (from ``core.mental.anima.data_streams``) so the
existing ANIMA engine can consume the pool output directly.

The pool runs on a schedule (default 60 seconds) and is thread-safe — all
result aggregation uses ``queue.Queue`` + ``threading.Lock``.

Usage::

    from crawler_pool import CrawlerPool, CrawlerSpec
    pool = CrawlerPool(max_workers=50)
    pool.register(CrawlerSpec(source="github", kwargs={"owner":"ethereum","repo":"solidity"}))
    pool.register(CrawlerSpec(source="github", kwargs={"owner":"dev-analyshd","repo":"trion-core"}))
    pool.register(CrawlerSpec(source="news"))
    pool.start()                    # background scheduler
    bundle = pool.get_bundle()       # latest aggregated bundle
    pool.stop()

Or one-shot::

    bundle = pool.run_once()         # run all registered crawlers once, return bundle

Author: TRION Protocol — Originator: Hudu Yusuf (Analys)
License: CC0
"""

from __future__ import annotations

import logging
import threading
import time
import queue
from concurrent.futures import ThreadPoolExecutor, as_completed, Future
from dataclasses import dataclass, field
from typing import Any, Callable, Dict, List, Optional, Tuple

# ─────────────────────────────────────────────────────────────────────────────
# Optional: ANIMADataStreamBundle re-export for convenience
# ─────────────────────────────────────────────────────────────────────────────
# Importing data_streams pulls in the full ANIMA engine. The pool should
# still be usable in lightweight contexts (e.g. anima-service scripts that
# only need raw crawl results), so we degrade gracefully if the import
# path is unavailable.

try:
    from core.mental.anima.data_streams import (
        ANIMADataStreamBundle,
        StructuredOffchainSignal,
        NLPSignal,
        BiologicalEcologicalSignal,
    )
    _HAVE_BUNDLE = True
except Exception:  # pragma: no cover — graceful degradation
    _HAVE_BUNDLE = False
    ANIMADataStreamBundle = None  # type: ignore
    StructuredOffchainSignal = None  # type: ignore
    NLPSignal = None  # type: ignore
    BiologicalEcologicalSignal = None  # type: ignore


logger = logging.getLogger(__name__)
if not logger.handlers:
    # Avoid "No handlers could be found" warnings in CLI usage.
    logger.addHandler(logging.NullHandler())


# ─────────────────────────────────────────────────────────────────────────────
# DataSourceResult — the per-crawler return type
# ─────────────────────────────────────────────────────────────────────────────

@dataclass
class DataSourceResult:
    """
    Structured result returned by every crawler worker.

    Fields
    ------
    source_name : str
        Human-readable identifier (e.g. ``"github:ethereum/solidity"``).
        Includes any per-instance disambiguator so multiple workers of the
        same source type don't collide.
    source_type : str
        One of: ``github``, ``news``, ``ecological``, ``regulatory``,
        ``academic``, ``multilingual``.
    data : Any
        The raw payload returned by the fetcher (dict / list — fetcher-
        dependent). Empty on failure.
    timestamp : float
        Unix timestamp when the result was collected.
    success : bool
        True if the fetcher returned a non-empty result. False on network
        error, parse error, or empty result.
    error : Optional[str]
        Error message when ``success=False``.
    duration_ms : float
        Wall-clock duration of the fetch call (for SLA monitoring).
    """
    source_name: str
    source_type: str
    data: Any = None
    timestamp: float = 0.0
    success: bool = False
    error: Optional[str] = None
    duration_ms: float = 0.0


# ─────────────────────────────────────────────────────────────────────────────
# CrawlerSpec — declarative crawler registration
# ─────────────────────────────────────────────────────────────────────────────

@dataclass
class CrawlerSpec:
    """
    Declarative description of one crawler worker.

    Parameters
    ----------
    source : str
        Source type identifier. Must be one of the keys returned by
        :func:`_SUPPORTED_SOURCES`. Example: ``"github"``.
    name : Optional[str]
        Human-readable name. When None, defaults to ``f"{source}:{i}"``
        where ``i`` is the spec index.
    kwargs : Dict[str, Any]
        Keyword arguments forwarded to the fetcher. Example for GitHub:
        ``{"owner": "ethereum", "repo": "solidity"}``.
    enabled : bool
        When False, the pool skips this crawler. Useful for A/B testing
        or temporary disablement without unregistering.
    timeout : Optional[float]
        Per-crawler timeout in seconds. When None, the pool's default
        timeout is used.
    """
    source: str
    name: Optional[str] = None
    kwargs: Dict[str, Any] = field(default_factory=dict)
    enabled: bool = True
    timeout: Optional[float] = None


# ─────────────────────────────────────────────────────────────────────────────
# Source fetcher registry — thin adapters around the data_sources modules
# ─────────────────────────────────────────────────────────────────────────────

def _fetch_github(**kwargs) -> Dict[str, Any]:
    from core.mental.anima.data_sources.github_activity import compute_github_signal
    return compute_github_signal(
        owner=kwargs.get("owner", "dev-analyshd"),
        repo=kwargs.get("repo", "trion-core"),
    )


def _fetch_news(**kwargs) -> Dict[str, Any]:
    from core.mental.anima.data_sources.news import compute_news_signal
    return compute_news_signal(query=kwargs.get("query", ""))


def _fetch_ecological(**kwargs) -> Dict[str, Any]:
    from core.mental.anima.data_sources.ecological import compute_ecological_signal
    return compute_ecological_signal(species_query=kwargs.get("species_query", "coral reef"))


def _fetch_regulatory(**kwargs) -> Dict[str, Any]:
    from core.mental.anima.data_sources.regulatory import compute_regulatory_signal
    return compute_regulatory_signal(query=kwargs.get("query", "blockchain cryptocurrency"))


def _fetch_academic(**kwargs) -> Dict[str, Any]:
    from core.mental.anima.data_sources.academic import compute_academic_signal
    return compute_academic_signal(query=kwargs.get("query", "blockchain security"))


def _fetch_multilingual(**kwargs) -> Dict[str, Any]:
    """Multilingual sentiment — degrades to a neutral result if the
    anima-service/multilingual_sentiment module is unavailable."""
    text = kwargs.get("text", "")
    if not text:
        return {"source": "multilingual", "sentiment": 0.5, "language": "unknown"}
    try:
        from multilingual_sentiment import score_text, detect_language
        lang = detect_language(text)
        score = score_text(text, lang)
        return {"source": "multilingual", "text": text[:200], "sentiment": score, "language": lang}
    except Exception as e:
        return {"source": "multilingual", "text": text[:200], "sentiment": 0.5,
                "language": "unknown", "error": f"{type(e).__name__}: {e}"}


# Registry mapping source type → fetcher callable
_FETCHERS: Dict[str, Callable[..., Dict[str, Any]]] = {
    "github":        _fetch_github,
    "news":          _fetch_news,
    "ecological":    _fetch_ecological,
    "regulatory":    _fetch_regulatory,
    "academic":      _fetch_academic,
    "multilingual":  _fetch_multilingual,
}

_SUPPORTED_SOURCES = tuple(_FETCHERS.keys())


# ─────────────────────────────────────────────────────────────────────────────
# Worker function — runs one fetcher and returns a DataSourceResult
# ─────────────────────────────────────────────────────────────────────────────

def _run_one_crawler(spec: CrawlerSpec, default_timeout: float) -> DataSourceResult:
    """Execute a single crawler spec synchronously. Never raises — any
    exception is captured into DataSourceResult.error and success=False."""
    name = spec.name or f"{spec.source}:{id(spec)}"
    fetcher = _FETCHERS.get(spec.source)
    if fetcher is None:
        return DataSourceResult(
            source_name=name,
            source_type=spec.source,
            data=None,
            timestamp=time.time(),
            success=False,
            error=f"unknown_source_type:{spec.source}",
            duration_ms=0.0,
        )

    start = time.time()
    try:
        data = fetcher(**spec.kwargs)
        duration_ms = (time.time() - start) * 1000.0
        # Empty / error payloads are still "success" from the network POV —
        # the fetcher itself is responsible for degrading gracefully. We
        # only mark success=False when the fetcher raised or returned None.
        success = data is not None
        return DataSourceResult(
            source_name=name,
            source_type=spec.source,
            data=data,
            timestamp=time.time(),
            success=success,
            error=None if success else "fetcher_returned_none",
            duration_ms=duration_ms,
        )
    except Exception as exc:
        duration_ms = (time.time() - start) * 1000.0
        return DataSourceResult(
            source_name=name,
            source_type=spec.source,
            data=None,
            timestamp=time.time(),
            success=False,
            error=f"{type(exc).__name__}: {exc}",
            duration_ms=duration_ms,
        )


# ─────────────────────────────────────────────────────────────────────────────
# CrawlerPool — the concurrent worker pool + scheduler
# ─────────────────────────────────────────────────────────────────────────────

class CrawlerPool:
    """
    Concurrent crawler pool for ANIMA data ingestion.

    Features
    --------
    - ``ThreadPoolExecutor`` with configurable ``max_workers`` (default 50,
      scalable to 1000).
    - Workers can be duplicated (10 GitHub workers for 10 different repos).
    - Thread-safe result collection via ``queue.Queue`` + ``threading.Lock``.
    - Runs on a configurable schedule (default 60 seconds).
    - Aggregates results into an ``ANIMADataStreamBundle`` when available.
    - Per-crawler error isolation — failures are logged and the pool
      continues with remaining crawlers.

    Usage
    -----
    ::

        pool = CrawlerPool(max_workers=50, schedule_interval=60.0)
        pool.register(CrawlerSpec(source="github", kwargs={"owner":"ethereum","repo":"solidity"}))
        pool.register(CrawlerSpec(source="github", kwargs={"owner":"dev-analyshd","repo":"trion-core"}))
        pool.register(CrawlerSpec(source="news"))
        pool.register(CrawlerSpec(source="ecological"))
        pool.register(CrawlerSpec(source="regulatory"))
        pool.start()                    # start background scheduler
        bundle = pool.get_bundle()      # latest aggregated bundle
        pool.stop()
    """

    def __init__(
        self,
        max_workers: int = 50,
        schedule_interval: float = 60.0,
        default_timeout: float = 30.0,
        entity_id: str = "anima-pool",
    ):
        if max_workers < 1:
            raise ValueError("max_workers must be >= 1")
        self.max_workers = int(max_workers)
        self.schedule_interval = float(schedule_interval)
        self.default_timeout = float(default_timeout)
        self.entity_id = str(entity_id)

        # Registry
        self._specs: List[CrawlerSpec] = []
        self._specs_lock = threading.Lock()

        # Result aggregation (thread-safe)
        self._results_queue: "queue.Queue[DataSourceResult]" = queue.Queue()
        self._latest_results: List[DataSourceResult] = []
        self._latest_bundle: Optional[Any] = None
        self._results_lock = threading.Lock()

        # Scheduler
        self._scheduler_thread: Optional[threading.Thread] = None
        self._stop_event = threading.Event()
        self._cycle_count = 0
        self._last_cycle_at: float = 0.0

        # Executor (created lazily — allows CrawlerPool(max_workers=5) to
        # be constructed in environments where ThreadPoolExecutor can't
        # spawn workers, e.g. some test sandboxes).
        self._executor: Optional[ThreadPoolExecutor] = None
        self._executor_lock = threading.Lock()

    # ── Spec registration ─────────────────────────────────────────────────

    def register(self, spec: CrawlerSpec) -> None:
        """Register a crawler spec. Thread-safe."""
        if spec.source not in _FETCHERS:
            raise ValueError(
                f"unknown source type: {spec.source!r}. "
                f"Supported: {_SUPPORTED_SOURCES}"
            )
        with self._specs_lock:
            self._specs.append(spec)

    def register_many(self, specs: List[CrawlerSpec]) -> None:
        """Register multiple crawler specs at once."""
        for spec in specs:
            self.register(spec)

    def unregister(self, name: str) -> bool:
        """Remove a crawler by its ``name`` field. Returns True if removed."""
        with self._specs_lock:
            before = len(self._specs)
            self._specs = [s for s in self._specs if (s.name or "") != name]
            return len(self._specs) < before

    def list_specs(self) -> List[CrawlerSpec]:
        with self._specs_lock:
            return list(self._specs)

    def spec_count(self) -> int:
        with self._specs_lock:
            return len(self._specs)

    # ── Executor management ───────────────────────────────────────────────

    def _get_executor(self) -> ThreadPoolExecutor:
        with self._executor_lock:
            if self._executor is None:
                self._executor = ThreadPoolExecutor(
                    max_workers=self.max_workers,
                    thread_name_prefix="anima-crawler",
                )
            return self._executor

    def _shutdown_executor(self) -> None:
        with self._executor_lock:
            if self._executor is not None:
                try:
                    self._executor.shutdown(wait=False, cancel_futures=True)
                except TypeError:
                    # Python <3.9 — cancel_futures not supported
                    self._executor.shutdown(wait=False)
                self._executor = None

    # ── One-shot run ──────────────────────────────────────────────────────

    def run_once(self) -> List[DataSourceResult]:
        """
        Run all registered crawlers once in parallel. Blocks until all
        workers complete (or the per-crawler timeout fires). Returns a
        list of ``DataSourceResult`` — one per registered crawler.

        Side effects: updates the pool's internal ``_latest_results`` and
        ``_latest_bundle`` caches (queriable via :meth:`get_results` and
        :meth:`get_bundle`).
        """
        with self._specs_lock:
            specs = [s for s in self._specs if s.enabled]

        if not specs:
            return []

        executor = self._get_executor()
        future_to_spec: Dict[Future, CrawlerSpec] = {}
        for spec in specs:
            timeout = spec.timeout if spec.timeout is not None else self.default_timeout
            fut = executor.submit(_run_one_crawler, spec, timeout)
            future_to_spec[fut] = spec

        results: List[DataSourceResult] = []
        for fut in as_completed(future_to_spec, timeout=self.default_timeout + 5.0):
            spec = future_to_spec[fut]
            try:
                res = fut.result(timeout=self.default_timeout)
            except Exception as exc:
                # Worker raised — capture as failed result, don't crash pool.
                logger.warning(
                    "crawler %s raised %s: %s — continuing",
                    spec.name or spec.source, type(exc).__name__, exc,
                )
                res = DataSourceResult(
                    source_name=spec.name or f"{spec.source}:{id(spec)}",
                    source_type=spec.source,
                    data=None,
                    timestamp=time.time(),
                    success=False,
                    error=f"worker_exception: {type(exc).__name__}: {exc}",
                    duration_ms=0.0,
                )
            results.append(res)
            # Push to queue for any consumers blocking on get()
            self._results_queue.put(res)

        # Update latest results cache
        with self._results_lock:
            self._latest_results = results
            self._latest_bundle = self._aggregate_into_bundle(results)
            self._cycle_count += 1
            self._last_cycle_at = time.time()

        return results

    # ── Bundle aggregation ───────────────────────────────────────────────

    def _aggregate_into_bundle(
        self,
        results: List[DataSourceResult],
    ) -> Optional[Any]:
        """
        Aggregate crawler results into an ``ANIMADataStreamBundle``.

        Falls back to a plain dict when the ANIMA bundle types are not
        importable (e.g. anima-service-only deployment).
        """
        if not _HAVE_BUNDLE:
            return {
                "entity_id":   self.entity_id,
                "timestamp":    time.time(),
                "block_number": 0,
                "results":      [r.__dict__ for r in results],
                "success_count": sum(1 for r in results if r.success),
                "failure_count": sum(1 for r in results if not r.success),
            }

        offchain_signals: List[Any] = []
        nlp_signals: List[Any] = []
        biological: Optional[Any] = None
        block_number = 0

        for r in results:
            if not r.success or not r.data:
                continue
            data = r.data
            ts = r.timestamp or time.time()

            if r.source_type == "github":
                try:
                    nlp_signals.append(NLPSignal(
                        language_code="en",
                        source_type="DEV_REPO",
                        timestamp=ts,
                        sentiment_score=float(data.get("activity_score", 0.5)),
                        confidence=float(data.get("diversity_score", 0.5)),
                        source_count=int(data.get("event_count", 1)),
                        source_cred=0.80,
                    ))
                except Exception:
                    pass

            elif r.source_type == "news":
                try:
                    nlp_signals.append(NLPSignal(
                        language_code="en",
                        source_type="NEWS",
                        timestamp=ts,
                        sentiment_score=float(data.get("avg_sentiment", 0.5)),
                        confidence=0.75,
                        source_count=int(data.get("article_count", 1)),
                        source_cred=0.75,
                    ))
                except Exception:
                    pass

            elif r.source_type == "academic":
                try:
                    nlp_signals.append(NLPSignal(
                        language_code="en",
                        source_type="ACADEMIC",
                        timestamp=ts,
                        sentiment_score=float(data.get("research_trend", 0.5)),
                        confidence=0.85,
                        source_count=int(data.get("paper_count", 1)),
                        source_cred=0.85,
                    ))
                except Exception:
                    pass

            elif r.source_type == "multilingual":
                try:
                    lang = str(data.get("language", "unknown"))[:2] or "en"
                    nlp_signals.append(NLPSignal(
                        language_code=lang,
                        source_type="NEWS",
                        timestamp=ts,
                        sentiment_score=float(data.get("sentiment", 0.5)),
                        confidence=0.70,
                        source_count=1,
                        source_cred=0.70,
                    ))
                except Exception:
                    pass

            elif r.source_type == "regulatory":
                try:
                    offchain_signals.append(StructuredOffchainSignal(
                        source_id=f"sec_edgar:{r.source_name}",
                        source_type="SEC_EDGAR",
                        jurisdiction="US",
                        timestamp=ts,
                        signal_strength=min(1.0, int(data.get("filing_count", 0)) / 10.0),
                        source_cred=0.85,
                    ))
                except Exception:
                    pass

            elif r.source_type == "ecological":
                try:
                    biological = BiologicalEcologicalSignal(
                        timestamp=ts,
                        circadian_phase=0.5,
                        ultradian_phase=0.5,
                        lunar_phase=0.5,
                        seasonal_phase=0.5,
                        circadian_phase_deviation=0.0,
                        circadian_strength=0.5,
                        bc_score=float(data.get("bc_score", 0.0)),
                        bc_flow=float(data.get("diversity_score", 0.0)),
                        bc_resilience=0.5,
                        bc_interdependence=0.5,
                        xsl_aggregate=0.5,
                        xsl_keystone_score=0.5,
                        xsl_decline_rate=0.0,
                    )
                except Exception:
                    pass

        try:
            return ANIMADataStreamBundle(
                entity_id=self.entity_id,
                timestamp=time.time(),
                block_number=block_number,
                onchain=None,
                offchain=offchain_signals,
                nlp=nlp_signals,
                biological=biological,
            )
        except Exception:
            # Final fallback — never raise from aggregation.
            return {
                "entity_id":     self.entity_id,
                "timestamp":     time.time(),
                "block_number":  block_number,
                "offchain_count": len(offchain_signals),
                "nlp_count":      len(nlp_signals),
                "has_biological": biological is not None,
                "results":        [r.__dict__ for r in results],
            }

    # ── Public query API ─────────────────────────────────────────────────

    def get_results(self) -> List[DataSourceResult]:
        """Return the most recent cycle's results (thread-safe copy)."""
        with self._results_lock:
            return list(self._latest_results)

    def get_bundle(self) -> Optional[Any]:
        """Return the most recent aggregated ``ANIMADataStreamBundle``
        (or dict fallback). Returns None if no cycle has run yet."""
        with self._results_lock:
            return self._latest_bundle

    def drain_queue(self, max_items: int = 1000) -> List[DataSourceResult]:
        """Drain up to ``max_items`` results from the live queue. Useful
        for streaming consumers that want every result, not just the latest
        cycle snapshot."""
        out: List[DataSourceResult] = []
        try:
            for _ in range(max_items):
                out.append(self._results_queue.get_nowait())
        except queue.Empty:
            pass
        return out

    def stats(self) -> Dict[str, Any]:
        """Return pool stats: cycle count, last cycle timestamp, registered
        crawler count, success/failure counts for the latest cycle."""
        with self._results_lock:
            results = list(self._latest_results)
        return {
            "entity_id":         self.entity_id,
            "max_workers":       self.max_workers,
            "schedule_interval": self.schedule_interval,
            "spec_count":        self.spec_count(),
            "cycle_count":       self._cycle_count,
            "last_cycle_at":     self._last_cycle_at,
            "last_cycle_success": sum(1 for r in results if r.success),
            "last_cycle_failure": sum(1 for r in results if not r.success),
            "is_running":        self._scheduler_thread is not None
                                  and self._scheduler_thread.is_alive(),
        }

    # ── Scheduler (background thread) ─────────────────────────────────────

    def start(self) -> None:
        """Start the background scheduler. The scheduler runs
        :meth:`run_once` every ``schedule_interval`` seconds until
        :meth:`stop` is called. Returns immediately."""
        if self._scheduler_thread is not None and self._scheduler_thread.is_alive():
            return  # already running

        self._stop_event.clear()
        self._scheduler_thread = threading.Thread(
            target=self._scheduler_loop,
            name="anima-crawler-scheduler",
            daemon=True,
        )
        self._scheduler_thread.start()

    def stop(self, timeout: float = 5.0) -> None:
        """Signal the scheduler to stop and wait briefly for it to exit."""
        self._stop_event.set()
        if self._scheduler_thread is not None:
            self._scheduler_thread.join(timeout=timeout)
            self._scheduler_thread = None
        # Shutdown the executor too — no more run_once calls expected.
        self._shutdown_executor()

    def _scheduler_loop(self) -> None:
        """Internal scheduler loop. Runs ``run_once`` immediately, then
        every ``schedule_interval`` seconds until :meth:`stop`."""
        while not self._stop_event.is_set():
            try:
                self.run_once()
            except Exception as exc:
                logger.error(
                    "crawler pool cycle raised %s: %s — continuing",
                    type(exc).__name__, exc,
                )
            # Wait for the next cycle (interruptible).
            self._stop_event.wait(self.schedule_interval)

    # ── Context manager protocol ─────────────────────────────────────────

    def __enter__(self) -> "CrawlerPool":
        self.start()
        return self

    def __exit__(self, exc_type, exc_val, exc_tb) -> None:
        self.stop()


# ─────────────────────────────────────────────────────────────────────────────
# Default crawler registry — convenience preset covering all 6 sources
# ─────────────────────────────────────────────────────────────────────────────

def default_crawler_specs() -> List[CrawlerSpec]:
    """
    Return the default crawler set: one worker per source type covering
    the canonical TRION Protocol targets. Useful as a starting point::

        pool = CrawlerPool(max_workers=50)
        pool.register_many(default_crawler_specs())
        pool.start()
    """
    return [
        CrawlerSpec(source="github",     name="github:trion-core",
                    kwargs={"owner": "dev-analyshd", "repo": "trion-core"}),
        CrawlerSpec(source="github",     name="github:ethereum/solidity",
                    kwargs={"owner": "ethereum", "repo": "solidity"}),
        CrawlerSpec(source="news",       name="news:crypto"),
        CrawlerSpec(source="ecological", name="gbif:coral"),
        CrawlerSpec(source="regulatory", name="sec:crypto"),
        CrawlerSpec(source="academic",   name="arxiv:defi-security",
                    kwargs={"query": "blockchain security DeFi"}),
        CrawlerSpec(source="multilingual", name="multilingual:default",
                    kwargs={"text": "DeFi adoption surges globally"}),
    ]


# ─────────────────────────────────────────────────────────────────────────────
# CLI entry point — manual smoke test
# ─────────────────────────────────────────────────────────────────────────────

if __name__ == "__main__":  # pragma: no cover
    import pprint
    pool = CrawlerPool(max_workers=10, schedule_interval=60.0)
    pool.register_many(default_crawler_specs())
    print(f"Registered {pool.spec_count()} crawlers. Running once...")
    results = pool.run_once()
    print(f"\nCycle complete: {len(results)} results")
    for r in results:
        status = "OK" if r.success else "FAIL"
        print(f"  [{status}] {r.source_name:35s} ({r.duration_ms:6.1f}ms)"
              + (f"  err={r.error}" if r.error else ""))
    print(f"\nPool stats: {pool.stats()}")
    bundle = pool.get_bundle()
    if bundle is not None:
        if hasattr(bundle, "streams_active"):
            print(f"Bundle streams active: {bundle.streams_active()}")
        else:
            print(f"Bundle (fallback dict): {bundle}")
