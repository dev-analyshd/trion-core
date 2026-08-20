"""
Phase 3 — ANIMA Live Connectors + FAISS Concurrent-Write Ingestion Test
=======================================================================

End-to-end test that:
  1. Boots the FAISS service (FastAPI/uvicorn) on a free port.
  2. Starts the BH streamer (real EVM RPC polling, 7 chains).
  3. Waits 30 seconds for BHs to land in the index.
  4. Queries FAISS /stats for the live vector count.
  5. Queries /api/v1/health for system stats.
  6. Verifies BHs are being produced (count > 0).
  7. Exercises every ANIMA data source connector with REAL HTTP calls
     (no mocks) — GitHub, news RSS, GBIF, SEC EDGAR EFTS, arXiv,
     SEC EDGAR per-CIK.
  8. Verifies non-empty responses from every connector.
  9. Prints timing for every step (must complete within 60 s total).

The test is a pytest test (`pytest tests/integration/test_anima_live_ingestion.py`)
but also runnable directly (`python3 tests/integration/test_anima_live_ingestion.py`)
for ad-hoc smoke checks.
"""

from __future__ import annotations

import json
import os
import socket
import sqlite3
import subprocess
import sys
import tempfile
import threading
import time
import urllib.error
import urllib.request
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

import pytest

# ── Path setup ─────────────────────────────────────────────────────────────────
ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "anima-service"))
sys.path.insert(0, str(ROOT / "api"))

# ── Helpers ────────────────────────────────────────────────────────────────────

def _free_port() -> int:
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
        s.bind(("127.0.0.1", 0))
        return s.getsockname()[1]


def _http_get_json(url: str, timeout: float = 15.0) -> Dict[str, Any]:
    req = urllib.request.Request(url, headers={"User-Agent": "trion-phase3-test/1.0"})
    with urllib.request.urlopen(req, timeout=timeout) as resp:
        return json.loads(resp.read().decode("utf-8", errors="replace"))


def _http_post_json(url: str, body: Dict[str, Any], timeout: float = 30.0) -> Dict[str, Any]:
    payload = json.dumps(body).encode("utf-8")
    req = urllib.request.Request(
        url, data=payload, headers={"Content-Type": "application/json",
                                    "User-Agent": "trion-phase3-test/1.0"},
        method="POST",
    )
    with urllib.request.urlopen(req, timeout=timeout) as resp:
        return json.loads(resp.read().decode("utf-8", errors="replace"))


def _wait_for_healthz(base_url: str, deadline_s: float = 30.0) -> bool:
    """Poll /healthz until 200 OK or deadline."""
    deadline = time.time() + deadline_s
    last_err: Optional[str] = None
    while time.time() < deadline:
        try:
            _http_get_json(f"{base_url}/healthz", timeout=3.0)
            return True
        except Exception as exc:  # noqa: BLE001 — broad on purpose during boot
            last_err = f"{type(exc).__name__}: {exc}"
            time.sleep(0.5)
    print(f"  [boot] /healthz never came up — last error: {last_err}", file=sys.stderr)
    return False


# ── Test fixture: FAISS service subprocess ────────────────────────────────────

def _boot_faiss_service(scope: str):
    """Shared boot logic — spawns uvicorn + waits for /healthz.

    Returns the fixture dict (base_url, proc, workdir, env). Caller is
    responsible for terminating `proc` on teardown.
    """
    port = _free_port()
    base_url = f"http://127.0.0.1:{port}"
    workdir = tempfile.mkdtemp(prefix=f"trion_phase3_{scope}_")
    env = os.environ.copy()
    env.update({
        "FAISS_PORT": str(port),
        "PORT":       str(port),
        "FAISS_INDEX_PATH":     os.path.join(workdir, "akashic_faiss.index"),
        "FAISS_CENTROIDS_PATH": os.path.join(workdir, "trion_archetype_centroids.npy"),
        "FAISS_STATE_DB":       os.path.join(workdir, "akashic_state.db"),
        "BH_LEDGER_DB":         os.path.join(workdir, "bh_ledger.db"),
    })
    launcher = (
        "import sys, os; "
        f"sys.path.insert(0, {str(ROOT)!r}); "
        f"sys.path.insert(0, {str(ROOT / 'anima-service')!r}); "
        f"sys.path.insert(0, {str(ROOT / 'api')!r}); "
        "os.chdir(sys.path[1]); "
        "import faiss_service; "
        "import uvicorn; "
        f"uvicorn.run(faiss_service.app, host='127.0.0.1', port={port}, "
        "access_log=False, log_level='warning')"
    )
    proc = subprocess.Popen(
        [sys.executable, "-c", launcher],
        env=env,
        cwd=str(ROOT / "anima-service"),
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        text=True,
    )
    try:
        if not _wait_for_healthz(base_url, deadline_s=30.0):
            out = ""
            try:
                out = proc.stdout.read(4000) if proc.stdout else ""
            except Exception:
                pass
            raise RuntimeError(
                f"FAISS service did not become healthy on port {port}. "
                f"Process alive={proc.poll() is None}. Output:\n{out}"
            )
        return {"base_url": base_url, "proc": proc, "workdir": workdir, "env": env}
    except Exception:
        proc.terminate()
        try: proc.wait(timeout=10)
        except subprocess.TimeoutExpired:
            proc.kill(); proc.wait(timeout=5)
        raise


def _teardown_faiss_service(svc):
    proc = svc["proc"]
    proc.terminate()
    try:
        proc.wait(timeout=10)
    except subprocess.TimeoutExpired:
        proc.kill()
        proc.wait(timeout=5)


@pytest.fixture(scope="module")
def faiss_service():
    """Module-scoped FAISS service for the live-ingestion test (+ BH streamer)."""
    svc = _boot_faiss_service("module")
    try:
        yield svc
    finally:
        _teardown_faiss_service(svc)


@pytest.fixture(scope="function")
def faiss_service_clean():
    """Function-scoped, *isolated* FAISS service for the concurrent-write test.

    A fresh process per test so the BH streamer (running in the module-scoped
    `faiss_service`/`bh_streamer` fixtures) does NOT compete for the index
    write lock during the concurrent stress test.
    """
    svc = _boot_faiss_service("clean")
    try:
        yield svc
    finally:
        _teardown_faiss_service(svc)


# ── Test fixture: BH streamer (in-process) ────────────────────────────────────

@pytest.fixture(scope="module")
def bh_streamer(faiss_service):
    """Start the BH streamer in-process and point it at the running FAISS service."""
    # Override FAISS_SERVICE_URL so the streamer POSTs to our test instance.
    os.environ["FAISS_SERVICE_URL"] = faiss_service["base_url"]
    faiss_service["env"]["FAISS_SERVICE_URL"] = faiss_service["base_url"]

    # Streamer writes to bh_ledger.db in CWD by default. Override via param.
    # NOTE: we use a SEPARATE file from the FAISS service's bh_ledger.db
    # because the streamer's CREATE TABLE schema has an extra `valid` column
    # that the FAISS service's _init_bh_ledger_db() doesn't include. If both
    # write to the same file, the first schema wins and the second's INSERTs
    # silently fail with "table bh_ledger has no column named valid".
    bh_db = os.path.join(faiss_service["workdir"], "bh_streamer_ledger.db")
    from core.realtime.bh_streamer import start_streamer, get_streamer, get_faiss_accumulator
    streamer = start_streamer(db_path=bh_db)
    faiss_service["bh_db"] = bh_db
    faiss_service["streamer"] = streamer
    faiss_service["accumulator"] = get_faiss_accumulator()
    try:
        yield streamer
    finally:
        try:
            streamer.stop()
        except Exception:
            pass


# ═══════════════════════════════════════════════════════════════════════════════
# TEST 1 — Live ingestion within 60 seconds
# ═══════════════════════════════════════════════════════════════════════════════

class TestAnimaLiveIngestion:
    """Verifies the ANIMA live-data pipeline runs end-to-end in <60s."""

    #: Overall test budget (seconds). Asserted at the end.
    BUDGET_S = 60.0

    def test_live_ingestion_within_60s(self, faiss_service, bh_streamer):
        base_url = faiss_service["base_url"]
        bh_db = faiss_service["bh_db"]
        timings: List[Tuple[str, float]] = []
        t_global_start = time.time()

        def step(label: str, fn):
            t0 = time.time()
            try:
                result = fn()
            except Exception as exc:
                dt = time.time() - t0
                timings.append((label, dt))
                print(f"  [step] {label:<40s}  FAIL  ({dt:.2f}s)  {exc}", file=sys.stderr)
                raise
            dt = time.time() - t0
            timings.append((label, dt))
            print(f"  [step] {label:<40s}  ok    ({dt:.2f}s)")
            return result

        # ── Step 1: FAISS service is up (already true from fixture, but recorded) ──
        def _s1():
            d = _http_get_json(f"{base_url}/healthz", timeout=5.0)
            assert d.get("status") == "ok"
            return d
        step("1. FAISS /healthz", _s1)

        # ── Step 2: BH streamer is running ─────────────────────────────────────
        def _s2():
            assert bh_streamer.is_running(), "streamer not running"
            return bh_streamer.get_stats()
        step("2. BH streamer running", _s2)

        # ── Step 3: Wait 30 seconds for BHs to accumulate ───────────────────────
        def _s3():
            time.sleep(30.0)
            return None
        step("3. Wait 30s for BHs", _s3)

        # ── Step 4: Query FAISS /stats for vector count ─────────────────────────
        def _s4():
            d = _http_get_json(f"{base_url}/stats", timeout=10.0)
            assert "indexed_vectors" in d, f"/stats missing indexed_vectors: {d}"
            return d
        stats = step("4. FAISS /stats", _s4)

        # ── Step 5: Query /api/v1/health for system stats ───────────────────────
        def _s5():
            d = _http_get_json(f"{base_url}/api/v1/health", timeout=10.0)
            assert "status" in d and "faiss_available" in d, f"/api/v1/health bad payload: {d}"
            return d
        health = step("5. /api/v1/health", _s5)

        # ── Step 6: Verify BHs are being produced (bh_ledger row count > 0) ────
        def _s6():
            # Use the dedicated bh_ledger DB path the streamer is writing to.
            conn = sqlite3.connect(bh_db, timeout=5.0)
            try:
                row = conn.execute("SELECT COUNT(*) FROM bh_ledger").fetchone()
                count = row[0] if row else 0
            finally:
                conn.close()
            assert count > 0, (
                f"bh_ledger is empty after 30s — streamer may be failing to "
                f"reach public RPCs. Stats: {bh_streamer.get_stats()}"
            )
            return count
        bh_count = step("6. BH ledger count > 0", _s6)

        # ── Step 7: Test each ANIMA data source connector (REAL HTTP) ──────────
        from core.mental.anima.data_sources.github_activity import fetch_github_activity
        from core.mental.anima.data_sources.news import fetch_news
        from core.mental.anima.data_sources.ecological import fetch_gbif_species
        from core.mental.anima.data_sources.regulatory import fetch_sec_filings
        from core.mental.anima.data_sources.academic import fetch_arxiv_papers
        from core.mental.anima.data_sources.sec_edgar import fetch_sec_edgar

        github_events = step("7a. GitHub events", lambda: fetch_github_activity())
        news_items    = step("7b. News RSS",      lambda: fetch_news(limit=10))
        gbif_occs     = step("7c. GBIF ecology",  lambda: fetch_gbif_species("coral", 5))
        sec_filings   = step("7d. SEC EDGAR EFTS", lambda: fetch_sec_filings("blockchain", 5))
        arxiv_papers  = step("7e. arXiv papers",  lambda: fetch_arxiv_papers("blockchain", 5))
        apple_filings = step("7f. SEC EDGAR Apple 10-K", lambda: fetch_sec_edgar("0000320193", "10-K"))

        # ── Step 8: Assert every connector returned non-empty data ──────────────
        def _s8():
            assert len(github_events) > 0,  f"GitHub returned 0 events: {github_events}"
            assert len(news_items) > 0,     f"News returned 0 articles: {news_items}"
            assert len(gbif_occs) > 0,      f"GBIF returned 0 occurrences: {gbif_occs}"
            assert len(sec_filings) > 0,    f"SEC EFTS returned 0 filings: {sec_filings}"
            assert len(arxiv_papers) > 0,   f"arXiv returned 0 papers: {arxiv_papers}"
            assert len(apple_filings) > 0,  f"SEC EDGAR Apple 10-K returned 0: {apple_filings}"
            return {
                "github":   len(github_events),
                "news":     len(news_items),
                "gbif":     len(gbif_occs),
                "sec_efts": len(sec_filings),
                "arxiv":    len(arxiv_papers),
                "apple":    len(apple_filings),
            }
        counts = step("8. Assert non-empty", _s8)

        # ── Step 9: Sanity-check the data shapes (event type, paper title, etc.) ──
        def _s9():
            # GitHub event has 'type' and 'actor' fields
            assert github_events[0].get("type"), "GitHub event missing 'type'"
            assert github_events[0].get("actor", {}).get("login"), "GitHub event missing actor.login"
            # News item has 'source' and 'title'
            assert news_items[0].get("source"), "News item missing 'source'"
            assert news_items[0].get("title"),   "News item missing 'title'"
            # GBIF occurrence has 'scientificName' or 'species'
            assert (gbif_occs[0].get("scientificName") or gbif_occs[0].get("species")), \
                "GBIF occurrence missing scientificName/species"
            # SEC EFTS filing has 'filing_type' and 'filed_date'
            assert sec_filings[0].get("filing_type"), "SEC EFTS filing missing filing_type"
            assert sec_filings[0].get("filed_date"),  "SEC EFTS filing missing filed_date"
            # arXiv paper has 'title' and 'published'
            assert arxiv_papers[0].get("title"),      "arXiv paper missing title"
            assert arxiv_papers[0].get("published"),  "arXiv paper missing published"
            # SEC EDGAR Apple has 'form_type' and 'filing_date'
            assert apple_filings[0].get("form_type"), "SEC EDGAR filing missing form_type"
            assert apple_filings[0].get("filing_date"), "SEC EDGAR filing missing filing_date"
            return True
        step("9. Sanity-check data shapes", _s9)

        # ── Step 10: Multilingual sentiment covers 10 languages ─────────────────
        def _s10():
            from multilingual_sentiment import LEXICONS, compute_sentiment
            assert len(LEXICONS) >= 10, f"only {len(LEXICONS)} languages supported"
            # Quick round-trip on a few scripts to verify Unicode detection.
            for text, expected_lang in [
                ("Bitcoin surges to new high", "en"),
                ("比特币突破历史新高",          "zh"),
                ("ビットコインが史上最高値",     "ja"),
                ("비트코인 상승",                "ko"),
                ("البيتكوين يرتفع",              "ar"),
                ("Биткоин растет",               "ru"),
            ]:
                _, lang = compute_sentiment(text)
                assert lang == expected_lang, f"lang detection: {text!r} → {lang}, expected {expected_lang}"
            return list(LEXICONS.keys())
        langs = step("10. Multilingual sentiment (10 langs)", _s10)

        # ── Timing summary + budget assertion ─────────────────────────────────
        t_total = time.time() - t_global_start
        print("\n  ─── Phase 3 live ingestion timing ───")
        for label, dt in timings:
            print(f"    {label:<40s}  {dt:>6.2f}s")
        print(f"    {'TOTAL':<40s}  {t_total:>6.2f}s  (budget {self.BUDGET_S:.0f}s)")

        print("\n  ─── Live counts ───")
        print(f"    BHs in ledger:        {bh_count}")
        print(f"    FAISS indexed_vectors: {stats.get('indexed_vectors')}")
        print(f"    Streamer total_bhs:    {bh_streamer.get_stats().get('total_bhs')}")
        print(f"    Multilingual langs:    {langs}")
        print(f"    Connector counts:      {counts}")

        assert t_total <= self.BUDGET_S, (
            f"Phase 3 live ingestion took {t_total:.2f}s > {self.BUDGET_S}s budget"
        )


# ═══════════════════════════════════════════════════════════════════════════════
# TEST 2 — FAISS /stats endpoint + concurrent writes
# ═══════════════════════════════════════════════════════════════════════════════

class TestFaissConcurrent:
    """Verifies /stats endpoint shape + concurrent /index/add safety.

    Uses an isolated function-scoped FAISS service so the BH streamer (still
    running from the module-scoped fixtures above) does not compete for the
    index write lock and skew the concurrent-write timing.
    """

    def test_stats_endpoint(self, faiss_service_clean):
        d = _http_get_json(f"{faiss_service_clean['base_url']}/stats", timeout=10.0)
        for key in ("status", "faiss_available", "indexed_vectors",
                    "index_type", "entities_tracked", "timestamp"):
            assert key in d, f"/stats missing '{key}': {d}"

    def test_concurrent_add_batch_thread_safety(self, faiss_service_clean):
        """10 threads × 50 vectors → all 500 must land in the index."""
        base = faiss_service_clean["base_url"]
        import math, random
        def rnd_vec():
            v = [random.gauss(0, 1) for _ in range(128)]
            n = math.sqrt(sum(x*x for x in v)) or 1.0
            return [x/n for x in v]

        results: List[Tuple[int, int]] = []
        results_lock = threading.Lock()

        def worker(idx: int):
            payload = {
                "vectors": [
                    {"entity_id": f"phase3-conc-{idx}-{i}",
                     "vector":    rnd_vec(),
                     "magnitude": 0.7, "entropy": 0.85,
                     "chain_id": 1, "chain_label": "ethereum", "vm_type": "EVM"}
                    for i in range(50)
                ],
                "source": "phase3-concurrent-test",
            }
            try:
                d = _http_post_json(f"{base}/index/add_batch", payload, timeout=30.0)
                with results_lock:
                    results.append((idx, int(d.get("added", 0))))
            except Exception as exc:
                with results_lock:
                    results.append((idx, -1))
                print(f"  [worker {idx}] FAIL: {exc}", file=sys.stderr)

        threads = [threading.Thread(target=worker, args=(i,)) for i in range(10)]
        for t in threads: t.start()
        for t in threads: t.join(timeout=60.0)

        total_added = sum(c for _, c in results if c > 0)
        failures = [i for i, c in results if c < 0]
        assert not failures, f"{len(failures)} workers failed: {failures}"
        assert total_added == 500, f"expected 500 concurrent adds, got {total_added}"

        # Confirm /stats reflects the new count (clean instance → exactly 500).
        d = _http_get_json(f"{base}/stats", timeout=10.0)
        assert d["indexed_vectors"] >= 500, (
            f"/stats indexed_vectors ({d['indexed_vectors']}) < 500 after concurrent writes"
        )


# ═══════════════════════════════════════════════════════════════════════════════
# Allow `python3 tests/integration/test_anima_live_ingestion.py` smoke run
# ═══════════════════════════════════════════════════════════════════════════════

if __name__ == "__main__":
    # Manual smoke runner — boots the FAISS service + streamer, then runs
    # TestAnimaLiveIngestion.test_live_ingestion_within_60s.
    import tempfile, shutil

    port = _free_port()
    base_url = f"http://127.0.0.1:{port}"
    workdir = tempfile.mkdtemp(prefix="trion_phase3_smoke_")
    env = os.environ.copy()
    env.update({
        "FAISS_PORT": str(port), "PORT": str(port),
        "FAISS_INDEX_PATH":     os.path.join(workdir, "akashic_faiss.index"),
        "FAISS_CENTROIDS_PATH": os.path.join(workdir, "trion_archetype_centroids.npy"),
        "FAISS_STATE_DB":       os.path.join(workdir, "akashic_state.db"),
        "BH_LEDGER_DB":         os.path.join(workdir, "bh_ledger.db"),
    })
    launcher = (
        "import sys, os; "
        f"sys.path.insert(0, {str(ROOT)!r}); "
        f"sys.path.insert(0, {str(ROOT / 'anima-service')!r}); "
        f"sys.path.insert(0, {str(ROOT / 'api')!r}); "
        "os.chdir(sys.path[1]); "
        "import faiss_service; "
        "import uvicorn; "
        f"uvicorn.run(faiss_service.app, host='127.0.0.1', port={port}, "
        "access_log=False, log_level='warning')"
    )
    proc = subprocess.Popen(
        [sys.executable, "-c", launcher], env=env,
        cwd=str(ROOT / "anima-service"),
        stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True,
    )
    try:
        if not _wait_for_healthz(base_url, 30.0):
            out = proc.stdout.read(4000) if proc.stdout else ""
            print(f"FAISS did not boot:\n{out}", file=sys.stderr)
            sys.exit(1)

        os.environ["FAISS_SERVICE_URL"] = base_url
        bh_db = os.path.join(workdir, "bh_streamer_ledger.db")
        from core.realtime.bh_streamer import start_streamer
        streamer = start_streamer(db_path=bh_db)
        try:
            # Reuse the test class with a fake module fixture
            class _Ctx:
                base_url = base_url
                bh_db    = bh_db
            inst = TestAnimaLiveIngestion()
            # Build the fixture dicts the test expects
            faiss_fixture = {"base_url": base_url, "bh_db": bh_db}
            # Manually run the steps
            inst.test_live_ingestion_within_60s(faiss_fixture, streamer)
            print("\nSMOKE PASS")
        finally:
            streamer.stop()
    finally:
        proc.terminate()
        try: proc.wait(timeout=10)
        except subprocess.TimeoutExpired:
            proc.kill(); proc.wait(timeout=5)
        shutil.rmtree(workdir, ignore_errors=True)
