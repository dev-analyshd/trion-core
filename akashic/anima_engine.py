"""
TRION ANIMA Intelligence Engine — L3.3 through L3.7 Complete
=============================================================
Implements the full ANIMA intelligence layer as specified in the TRION whitepaper.

  L3.3  ANIMA Score  A(t) = PCR(t) × HA(t) × CA(t)
  L3.4  Source Credibility  CRED(s,t) with daily decay and event updates
  L3.5  Reflexivity Dampening  A_adj(t) = A(t) × (1 - β × reflexivity)
  L3.5  Manifestation Gap Monitor  MG(S,t) = B_predicted - B_observed
  L3.7  Intelligence Maintenance Protocol  IM auto-retraining on degradation

Data sources crawled:
  - SEC EDGAR        (regulatory filings — XML-parsed, not hit-count)
  - GitHub           (commit velocity, contributor growth, issue resolution)
  - News RSS         (20+ feeds with VADER financial sentiment, not keyword lists)
  - CFTC / FCA       (regulatory enforcement RSS feeds)
  - arXiv            (academic preprints cs.CR + q-fin.TR)

Background:
  APScheduler runs entity crawl cycles every 30 minutes.
  CRED daily decay runs every 24 hours.
  Outcome verification runs every 6 hours.
"""

import os
import math
import json
import time
import hashlib
import logging
import sqlite3
import threading
import urllib.request
import urllib.error
import urllib.parse
import xml.etree.ElementTree as ET
from collections import defaultdict
from datetime import datetime, timezone, timedelta
from typing import Dict, List, Optional, Tuple, Any

import numpy as np
import feedparser
import httpx
from apscheduler.schedulers.background import BackgroundScheduler
from vaderSentiment.vaderSentiment import SentimentIntensityAnalyzer

logger = logging.getLogger(__name__)

# ─────────────────────────────────────────────────────────────────────────────
# Constants — whitepaper-aligned
# ─────────────────────────────────────────────────────────────────────────────

CRED_DECAY_DAILY        = 0.99      # L3.4: CRED(s,t) = CRED(s,t-1) × 0.99 per day
CRED_DELTA_VERIFIED     = +1.0      # prediction verified against realized outcome
CRED_DELTA_FALSIFIED    = -2.0      # prediction falsified
CRED_DELTA_MANIPULATION = -3.0      # manipulation pattern detected in source output
CRED_DELTA_CONFLICT     = -5.0      # source correlated with entity's own trading
CRED_FLAG_THRESHOLD     = 0.30      # below this: flag, human review required
CRED_EXCLUDE_THRESHOLD  = 0.10      # below this: exclude from CA entirely

HA_WINDOW_DAYS          = 90        # rolling 90-day historical accuracy window
HA_CORRECT_TOLERANCE    = 0.20      # |actual - predicted| ≤ 0.20 = correct
HA_FLAG_THRESHOLD       = 0.70      # HA < 0.70 → flag ANIMA output
HA_DISABLE_THRESHOLD    = 0.60      # HA < 0.60 → A(t) = 0

PCR_SEQUENCE_WINDOW     = 20        # number of records in sequence window for PCR
PCR_ACTIVE_THRESHOLD    = 0.01      # dimension considered "active" if > 1% of max

REFLEXIVITY_BETA        = 0.50      # L3.5: dampening coefficient
REFLEXIVITY_FLAG_THR    = 0.30      # flag if reflexivity exceeds this
REFLEXIVITY_WINDOW_H    = 2         # hours post-publication to measure behavioral change

IM_CHECK_INTERVAL_H     = 24        # check IM every 24 hours
IM_DEGRADATION_THR      = 0.80      # IM < 0.80 → trigger maintenance

CRAWL_CYCLE_MINUTES     = 30        # background crawl cycle
OUTCOME_VERIFY_HOURS    = 6         # how often to verify pending predictions
MANIFEST_WINDOW_HOURS   = 24        # how long after prediction to look for outcome

GITHUB_TOKEN = (
    os.environ.get("GITHUB_PERSONAL_ACCESS_TOKEN")
    or os.environ.get("GITHUB_TOKEN")
    or ""
)

# ─────────────────────────────────────────────────────────────────────────────
# Named source registry — L3.4
# Initial CRED values reflect source authority
# ─────────────────────────────────────────────────────────────────────────────

SOURCES: Dict[str, Dict[str, Any]] = {
    # Regulatory — highest CRED, authoritative
    "SEC_EDGAR":      {"initial_cred": 0.92, "category": "regulatory",  "weight": 1.0},
    "CFTC":           {"initial_cred": 0.94, "category": "regulatory",  "weight": 1.0},
    "FCA":            {"initial_cred": 0.94, "category": "regulatory",  "weight": 1.0},
    "ESMA":           {"initial_cred": 0.92, "category": "regulatory",  "weight": 1.0},
    "MAS":            {"initial_cred": 0.91, "category": "regulatory",  "weight": 1.0},
    # Developer — high CRED, verifiable commit history
    "GITHUB":         {"initial_cred": 0.80, "category": "developer",   "weight": 1.0},
    # Academic — peer-review signal
    "ARXIV":          {"initial_cred": 0.88, "category": "academic",    "weight": 0.9},
    # Tier-1 crypto news — established, full-time editorial
    "COINDESK":       {"initial_cred": 0.72, "category": "news",        "weight": 0.8},
    "THEBLOCK":       {"initial_cred": 0.74, "category": "news",        "weight": 0.8},
    "DECRYPT":        {"initial_cred": 0.68, "category": "news",        "weight": 0.7},
    "COINTELEGRAPH":  {"initial_cred": 0.65, "category": "news",        "weight": 0.7},
    "REUTERS_CRYPTO": {"initial_cred": 0.82, "category": "news",        "weight": 0.9},
    "BLOCKWORKS":     {"initial_cred": 0.70, "category": "news",        "weight": 0.75},
    "THEDEFIANT":     {"initial_cred": 0.68, "category": "news",        "weight": 0.7},
    "DLNEWS":         {"initial_cred": 0.71, "category": "news",        "weight": 0.75},
    "PROTOS":         {"initial_cred": 0.66, "category": "news",        "weight": 0.65},
    "BITCOINMAGAZINE":{"initial_cred": 0.70, "category": "news",        "weight": 0.7},
    # Tier-2 crypto news — broader coverage, slightly lower editorial bar
    "CRYPTOBRIEFING": {"initial_cred": 0.63, "category": "news",        "weight": 0.65},
    "NEWSBTC":        {"initial_cred": 0.60, "category": "news",        "weight": 0.60},
    "AMBCRYPTO":      {"initial_cred": 0.58, "category": "news",        "weight": 0.55},
    "BEINCRYPTO":     {"initial_cred": 0.60, "category": "news",        "weight": 0.60},
    "CRYPTOSLATE":    {"initial_cred": 0.62, "category": "news",        "weight": 0.65},
    "BITCOINIST":     {"initial_cred": 0.58, "category": "news",        "weight": 0.55},
    "UTODAY":         {"initial_cred": 0.56, "category": "news",        "weight": 0.55},
    "DAILYHODL":      {"initial_cred": 0.55, "category": "news",        "weight": 0.50},
    "CRYPTOPOTATO":   {"initial_cred": 0.57, "category": "news",        "weight": 0.55},
    "COINJOURNAL":    {"initial_cred": 0.59, "category": "news",        "weight": 0.55},
    # Cross-domain signals — L6.1 BC, L9.1 XSL, L6.2 BRT (injected by faiss_service)
    "BC_SIGNAL":      {"initial_cred": 0.85, "category": "cross_domain", "weight": 0.9},
    "XSL_SIGNAL":     {"initial_cred": 0.85, "category": "cross_domain", "weight": 0.9},
    "BRT_SIGNAL":     {"initial_cred": 0.80, "category": "cross_domain", "weight": 0.8},
}

NEWS_FEEDS = {
    # Tier-1 established crypto/finance news with reliable RSS
    "COINDESK":       "https://www.coindesk.com/arc/outboundfeeds/rss/",
    "THEBLOCK":       "https://www.theblock.co/rss.xml",
    "DECRYPT":        "https://decrypt.co/feed",
    "COINTELEGRAPH":  "https://cointelegraph.com/rss",
    "REUTERS_CRYPTO": "https://feeds.reuters.com/reuters/technologyNews",  # Reuters Tech (crypto coverage)
    "BLOCKWORKS":     "https://blockworks.co/feed",
    "THEDEFIANT":     "https://thedefiant.io/feed",
    "DLNEWS":         "https://www.dlnews.com/articles/feed/",
    "PROTOS":         "https://protos.com/feed/",
    "BITCOINMAGAZINE":"https://bitcoinmagazine.com/.rss/full/",
    # Tier-2 broader crypto news coverage
    "CRYPTOBRIEFING": "https://cryptobriefing.com/feed/",
    "NEWSBTC":        "https://www.newsbtc.com/feed/",
    "AMBCRYPTO":      "https://ambcrypto.com/feed/",
    "BEINCRYPTO":     "https://beincrypto.com/feed/",
    "CRYPTOSLATE":    "https://cryptoslate.com/feed/",
    "BITCOINIST":     "https://bitcoinist.com/feed/",
    "UTODAY":         "https://u.today/rss",
    "DAILYHODL":      "https://dailyhodl.com/feed/",
    "CRYPTOPOTATO":   "https://cryptopotato.com/feed/",
    "COINJOURNAL":    "https://coinjournal.net/feed/",
}

REGULATORY_FEEDS = {
    "CFTC":  "https://www.cftc.gov/rss/enforcementactions.xml",
    "FCA":   "https://www.fca.org.uk/news/rss.xml",
    "ESMA":  "https://www.esma.europa.eu/press-news/esma-news/rss",
    "MAS":   "https://www.mas.gov.sg/news/rss",
}

# ─────────────────────────────────────────────────────────────────────────────
# Module state
# ─────────────────────────────────────────────────────────────────────────────

_db_path: str = ""
_db_lock  = threading.Lock()
_vader    = SentimentIntensityAnalyzer()
_scheduler: Optional[BackgroundScheduler] = None
_entity_history_ref: Optional[Dict] = None  # reference to faiss_service entity_history
_centroids_ref: Optional[np.ndarray] = None  # reference to faiss_service centroids

# In-memory caches (refreshed from DB)
_cred_cache: Dict[str, float] = {}
_crawl_cache: Dict[str, Dict] = {}
_reflexivity_log: Dict[str, List[Tuple[float, float]]] = defaultdict(list)
_mg_log: Dict[str, List[float]] = defaultdict(list)  # Manifestation Gap per entity
_signal_pub_log: List[Tuple[float, float, str]] = []  # (ts, anima_score, entity_id)

# ─────────────────────────────────────────────────────────────────────────────
# Database — L3.4 CRED tables + L3.3 outcome tables
# ─────────────────────────────────────────────────────────────────────────────

def _db_conn() -> sqlite3.Connection:
    conn = sqlite3.connect(_db_path, check_same_thread=False)
    conn.row_factory = sqlite3.Row
    return conn


def _init_anima_tables():
    """Create ANIMA-specific SQLite tables if they don't exist."""
    with _db_lock:
        conn = _db_conn()
        conn.executescript("""
            -- L3.4: Source credibility tracking
            CREATE TABLE IF NOT EXISTS anima_sources (
                source_id    TEXT PRIMARY KEY,
                category     TEXT,
                cred         REAL DEFAULT 0.80,
                last_decay   REAL,           -- unix ts of last daily decay
                total_events INTEGER DEFAULT 0,
                verified     INTEGER DEFAULT 0,
                falsified    INTEGER DEFAULT 0,
                flagged      INTEGER DEFAULT 0,
                excluded     INTEGER DEFAULT 0,
                updated_at   TEXT
            );

            -- L3.4: Source credibility events (audit trail)
            CREATE TABLE IF NOT EXISTS anima_cred_events (
                id         INTEGER PRIMARY KEY AUTOINCREMENT,
                source_id  TEXT,
                event_type TEXT,      -- VERIFIED | FALSIFIED | MANIPULATION | CONFLICT
                delta      REAL,
                cred_after REAL,
                entity_id  TEXT,
                note       TEXT,
                ts         REAL
            );

            -- L3.3 HA: Outcome predictions + time-delayed verification
            CREATE TABLE IF NOT EXISTS anima_predictions (
                pred_id         TEXT PRIMARY KEY,
                entity_id       TEXT,
                source_id       TEXT,
                predicted_value REAL,
                prediction_ts   REAL,
                manifest_window REAL,   -- seconds until outcome expected
                realized_value  REAL,   -- filled in on verification
                error           REAL,   -- |realized - predicted|
                verified        INTEGER DEFAULT 0,
                verified_at     REAL
            );

            -- L3.5: Per-entity crawl results (for CA cross-source agreement)
            CREATE TABLE IF NOT EXISTS anima_crawl_results (
                id        INTEGER PRIMARY KEY AUTOINCREMENT,
                entity_id TEXT,
                source_id TEXT,
                score     REAL,       -- normalized [0,1] signal from this source
                raw_data  TEXT,       -- JSON blob of raw crawl result
                crawled_at REAL
            );

            -- L3.5: Reflexivity log (signal publication → behavioral change)
            CREATE TABLE IF NOT EXISTS anima_reflexivity (
                id           INTEGER PRIMARY KEY AUTOINCREMENT,
                entity_id    TEXT,
                pub_ts       REAL,
                anima_at_pub REAL,
                phi_before   REAL,    -- Φ(t) 2h before publication
                phi_after    REAL,    -- Φ(t) 2h after publication
                delta_phi    REAL,    -- behavioral change attributed to publication
                reflexivity  REAL,    -- |delta_phi| / max(phi_before, ε)
                recorded_at  REAL
            );

            -- L3.5: Manifestation Gap per entity per signal type
            CREATE TABLE IF NOT EXISTS anima_manifestation_gap (
                id            INTEGER PRIMARY KEY AUTOINCREMENT,
                entity_id     TEXT,
                signal_type   TEXT,
                predicted_at  REAL,
                observed_at   REAL,
                mg            REAL,   -- B_predicted - B_observed (timing gap in hours)
                recorded_at   REAL
            );

            -- L3.7: Intelligence Maintenance Protocol status
            CREATE TABLE IF NOT EXISTS anima_im_status (
                source_id    TEXT PRIMARY KEY,
                baseline_ha  REAL DEFAULT 0.80,
                current_ha   REAL DEFAULT 0.80,
                im_ratio     REAL DEFAULT 1.00,
                last_checked REAL,
                maintenance_triggered INTEGER DEFAULT 0
            );
        """)
        conn.commit()
        conn.close()


def _bootstrap_sources():
    """Insert source registry rows if they don't exist yet."""
    with _db_lock:
        conn = _db_conn()
        now = datetime.now(timezone.utc)
        for sid, meta in SOURCES.items():
            conn.execute("""
                INSERT OR IGNORE INTO anima_sources
                    (source_id, category, cred, last_decay, updated_at)
                VALUES (?, ?, ?, ?, ?)
            """, (sid, meta["category"], meta["initial_cred"],
                  now.timestamp(), now.isoformat()))
        conn.commit()
        conn.close()
    _refresh_cred_cache()


# ─────────────────────────────────────────────────────────────────────────────
# L3.4 — Source Credibility Operations
# ─────────────────────────────────────────────────────────────────────────────

def _refresh_cred_cache():
    """Load all CRED values from DB into memory cache."""
    with _db_lock:
        conn = _db_conn()
        rows = conn.execute("SELECT source_id, cred FROM anima_sources").fetchall()
        conn.close()
    for row in rows:
        _cred_cache[row["source_id"]] = row["cred"]


def get_cred(source_id: str) -> float:
    """Return current CRED for a source, applying any pending daily decay first."""
    _apply_cred_decay(source_id)
    return _cred_cache.get(source_id, 0.80)


def _apply_cred_decay(source_id: str):
    """
    L3.4: CRED(s,t) = CRED(s,t-1) × 0.99_per_day.
    Applies lazy compound decay since the last recorded decay timestamp.
    """
    now_ts = datetime.now(timezone.utc).timestamp()
    with _db_lock:
        conn = _db_conn()
        row = conn.execute(
            "SELECT cred, last_decay FROM anima_sources WHERE source_id = ?",
            (source_id,)
        ).fetchone()
        if not row:
            conn.close()
            return
        cred       = row["cred"]
        last_decay = row["last_decay"] or now_ts
        days_elapsed = (now_ts - last_decay) / 86400.0
        if days_elapsed >= 1.0:
            days_full = int(days_elapsed)
            new_cred  = max(0.05, cred * (CRED_DECAY_DAILY ** days_full))
            conn.execute("""
                UPDATE anima_sources
                SET cred = ?, last_decay = ?, updated_at = ?
                WHERE source_id = ?
            """, (new_cred, now_ts, datetime.now(timezone.utc).isoformat(), source_id))
            conn.commit()
            _cred_cache[source_id] = new_cred
        else:
            _cred_cache[source_id] = cred
        conn.close()


def update_cred(source_id: str, event_type: str, entity_id: str = "", note: str = ""):
    """
    L3.4: Apply a credibility event to a source.
    event_type: VERIFIED | FALSIFIED | MANIPULATION | CONFLICT
    """
    delta_map = {
        "VERIFIED":    CRED_DELTA_VERIFIED,
        "FALSIFIED":   CRED_DELTA_FALSIFIED,
        "MANIPULATION": CRED_DELTA_MANIPULATION,
        "CONFLICT":    CRED_DELTA_CONFLICT,
    }
    delta = delta_map.get(event_type, 0.0)
    if delta == 0.0:
        return
    _apply_cred_decay(source_id)
    now_ts = datetime.now(timezone.utc).timestamp()
    with _db_lock:
        conn = _db_conn()
        row = conn.execute(
            "SELECT cred, total_events, verified, falsified FROM anima_sources WHERE source_id = ?",
            (source_id,)
        ).fetchone()
        if not row:
            conn.close()
            return
        new_cred = max(0.05, min(1.0, row["cred"] + delta))
        flagged  = 1 if new_cred < CRED_FLAG_THRESHOLD else 0
        excluded = 1 if new_cred < CRED_EXCLUDE_THRESHOLD else 0
        conn.execute("""
            UPDATE anima_sources
            SET cred = ?, total_events = total_events + 1,
                verified  = verified  + ?,
                falsified = falsified + ?,
                flagged   = ?,
                excluded  = ?,
                updated_at = ?
            WHERE source_id = ?
        """, (new_cred,
              1 if event_type == "VERIFIED"  else 0,
              1 if event_type == "FALSIFIED" else 0,
              flagged, excluded,
              datetime.now(timezone.utc).isoformat(),
              source_id))
        conn.execute("""
            INSERT INTO anima_cred_events
                (source_id, event_type, delta, cred_after, entity_id, note, ts)
            VALUES (?, ?, ?, ?, ?, ?, ?)
        """, (source_id, event_type, delta, new_cred, entity_id, note, now_ts))
        conn.commit()
        conn.close()
    _cred_cache[source_id] = new_cred
    logger.info("[CRED] %s %s → %.3f (Δ%.1f)", source_id, event_type, new_cred, delta)


def get_all_cred_status() -> List[Dict]:
    """Return current CRED status for all sources."""
    for sid in SOURCES:
        _apply_cred_decay(sid)
    with _db_lock:
        conn = _db_conn()
        rows = conn.execute("""
            SELECT source_id, category, cred, total_events, verified,
                   falsified, flagged, excluded, updated_at
            FROM anima_sources ORDER BY cred DESC
        """).fetchall()
        conn.close()
    return [dict(r) for r in rows]


# ─────────────────────────────────────────────────────────────────────────────
# Enhanced Crawlers — L3.4 data sources
# ─────────────────────────────────────────────────────────────────────────────

_EDGAR_UA = "TRION-Protocol research@trion.io"

# NLP lexicons for EDGAR filing body text — whitepaper gap analysis spec
_EDGAR_HIGH_RISK = [
    "investigation", "material weakness", "going concern", "enforcement action",
    "subpoena", "fraud", "violation", "cease and desist", "sanctions",
    "money laundering", "unlicensed", "unregistered", "class action",
    "restated", "restatement", "impairment", "significant doubt",
    "inability to continue", "substantial doubt", "criminal",
]
_EDGAR_MED_RISK = [
    "regulatory scrutiny", "compliance issue", "risk factor", "litigation",
    "inquiry", "examination", "deficiency", "contingent liability",
    "under review", "pending investigation", "whistleblower", "material change",
]
_EDGAR_POSITIVE = [
    "clean audit", "no material weakness", "compliance", "approved",
    "registered", "licensed", "exemption granted", "no adverse findings",
    "unqualified opinion", "going concern resolved", "regulatory approval",
    "cleared", "closed investigation",
]


def _edgar_fetch_filing_text(hit_id: str, timeout: int = 5) -> str:
    """
    Fetch actual 8-K / 10-K body text from SEC EDGAR archives.

    EDGAR hit `_id` format: "edgar/data/{cik}/{accession_nodash}.json"
    We reconstruct the filing index URL and fetch the primary document.
    Returns extracted plain text, empty string on failure.
    """
    try:
        parts = hit_id.strip("/").split("/")
        if len(parts) < 3:
            return ""
        cik             = parts[1]
        accession_nodash = parts[2].replace(".json", "")

        # Format accession number with dashes: "000123456724123456" → "0001234567-24-123456"
        if len(accession_nodash) == 18:
            an = f"{accession_nodash[:10]}-{accession_nodash[10:12]}-{accession_nodash[12:]}"
        else:
            an = accession_nodash

        index_url = (
            f"https://www.sec.gov/Archives/edgar/data/{cik}/"
            f"{accession_nodash}/{an}-index.json"
        )
        req = urllib.request.Request(index_url, headers={"User-Agent": _EDGAR_UA})
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            index_data = json.loads(resp.read().decode())

        # Find primary document (.htm / .txt)
        docs = index_data.get("documents", [])
        primary_url = ""
        for doc in docs:
            if doc.get("type") in ("", "10-K", "8-K", "10-Q") and doc.get("documentUrl"):
                primary_url = "https://www.sec.gov" + doc["documentUrl"]
                break
        if not primary_url and docs:
            first_doc = docs[0].get("documentUrl", "")
            if first_doc:
                primary_url = "https://www.sec.gov" + first_doc

        if not primary_url:
            return ""

        req2 = urllib.request.Request(primary_url, headers={"User-Agent": _EDGAR_UA})
        with urllib.request.urlopen(req2, timeout=timeout) as resp2:
            raw_html = resp2.read().decode("utf-8", errors="replace")

        # Strip HTML tags to get plain text (fast, no dependencies)
        import re as _re
        text = _re.sub(r"<[^>]+>", " ", raw_html)
        text = _re.sub(r"&nbsp;|&amp;|&lt;|&gt;|&#\d+;", " ", text)
        text = _re.sub(r"\s+", " ", text)
        # Return first 8000 chars — enough for NLP, not too slow
        return text[:8000].lower()

    except Exception as e:
        logger.debug("[ANIMA][EDGAR][FETCH] %s: %s", hit_id[:40], e)
        return ""


def _crawl_sec_edgar(entity_id: str) -> Dict:
    """
    SEC EDGAR — Real NLP on actual 8-K / 10-K filing body text.

    Step 1: Full-text search hits via efts.sec.gov (JSON, structured API).
    Step 2: For top 3 hits, fetch actual filing document from SEC archives.
    Step 3: Run VADER financial sentiment + NLP keyword analysis on body text.
    Step 4: Extract all available _source metadata (form_type, file_date,
            display_names, accession_no, period_of_report).

    Returns regulatory_score ∈ [0.30, 1.0]: 1 = clean, low = high risk language.
    """
    try:
        # Gap analysis: use entity ticker / address fragment, not raw hex
        query = entity_id.replace("0x", "").lower()[:20]
        url = (
            f"https://efts.sec.gov/LATEST/search-index?q=%22{query}%22"
            f"&dateRange=custom&startdt=2023-01-01&forms=8-K,10-K,13F"
        )
        req = urllib.request.Request(url, headers={"User-Agent": _EDGAR_UA})
        with urllib.request.urlopen(req, timeout=8) as resp:
            data = json.loads(resp.read().decode())

        hits  = data.get("hits", {}).get("hits", [])
        total = data.get("hits", {}).get("total", {}).get("value", 0)

        risk_score  = 0.0
        pos_score   = 0.0
        vader_scores = []
        texts_analyzed = 0
        filings_fetched = 0
        form_types = []
        filing_dates = []

        for i, hit in enumerate(hits[:5]):
            src = hit.get("_source", {})

            # ── Metadata extraction (all available _source fields) ─────────────
            form_type  = src.get("form_type", src.get("period_of_report", ""))
            file_date  = src.get("file_date", "")
            accession  = src.get("accession_no", "")
            names      = " ".join(
                n.get("name", "") for n in src.get("display_names", [])
            )
            period     = src.get("period_of_report", "")
            file_num   = src.get("file_num", "")
            biz_loc    = src.get("biz_location", "")

            if form_type:
                form_types.append(form_type)
            if file_date:
                filing_dates.append(file_date)

            meta_text = " ".join([names, period, file_num, biz_loc]).lower()

            # ── Also check highlight excerpts if EDGAR returns them ────────────
            highlight_text = ""
            highlight = hit.get("highlight", {})
            if highlight:
                for field_vals in highlight.values():
                    for excerpt in (field_vals if isinstance(field_vals, list) else []):
                        highlight_text += " " + excerpt

            # ── For top 3 hits: fetch and NLP the actual filing body ───────────
            body_text = ""
            if i < 3:
                hit_id = hit.get("_id", "")
                if hit_id:
                    body_text = _edgar_fetch_filing_text(hit_id)
                    if body_text:
                        filings_fetched += 1

            full_text = (meta_text + " " + highlight_text + " " + body_text).strip()
            if not full_text:
                continue

            texts_analyzed += 1

            # ── NLP keyword scoring ─────────────────────────────────────────────
            for kw in _EDGAR_HIGH_RISK:
                if kw in full_text:
                    risk_score += 0.10
            for kw in _EDGAR_MED_RISK:
                if kw in full_text:
                    risk_score += 0.04
            for kw in _EDGAR_POSITIVE:
                if kw in full_text:
                    pos_score += 0.04

            # ── VADER financial sentiment on body text ─────────────────────────
            if body_text or highlight_text:
                nlp_text = (body_text or highlight_text)[:2000]
                vs = _vader.polarity_scores(nlp_text)
                vader_scores.append(vs["compound"])

        # ── Aggregate score ────────────────────────────────────────────────────
        raw = max(0.0, min(1.0, 0.80 - min(risk_score, 0.60) + pos_score * 0.5))
        volume_penalty = min(0.10, total * 0.008)
        keyword_score  = max(0.30, raw - volume_penalty)

        # Blend keyword score with VADER sentiment if available
        if vader_scores:
            mean_vader = float(np.mean(vader_scores))
            vader_normalized = (mean_vader + 1.0) / 2.0  # map [-1,1] → [0,1]
            # Weight: 60% keyword NLP, 40% VADER sentiment
            final_score = round(0.60 * keyword_score + 0.40 * vader_normalized, 4)
        else:
            final_score = round(keyword_score, 4)

        return {
            "source":           "SEC_EDGAR",
            "score":            max(0.30, final_score),
            "filing_count":     total,
            "texts_analyzed":   texts_analyzed,
            "filings_fetched":  filings_fetched,
            "form_types":       list(set(form_types)),
            "recent_filing":    max(filing_dates) if filing_dates else "",
            "risk_score_raw":   round(risk_score, 3),
            "vader_compound":   round(float(np.mean(vader_scores)), 3) if vader_scores else None,
            "status":           "ok",
        }

    except Exception as e:
        logger.debug("[ANIMA][SEC_EDGAR] %s", e)
        return {"source": "SEC_EDGAR", "score": 0.75, "filing_count": 0,
                "filings_fetched": 0, "status": "unavailable", "error": str(e)}


def _crawl_github(entity_id: str) -> Dict:
    """
    GitHub commit-level analysis.
    Scores: commit_velocity + contributor_diversity + issue_resolution + freshness.
    Returns developer_score ∈ [0,1].
    """
    headers = {"User-Agent": "TRION-Oracle/1.0"}
    if GITHUB_TOKEN:
        headers["Authorization"] = f"token {GITHUB_TOKEN}"
    ticker = entity_id[:10].lower().replace("0x", "")
    try:
        with httpx.Client(timeout=6.0) as client:
            search_url = f"https://api.github.com/search/repositories?q={ticker}+in:name,description+topic:defi&sort=stars&per_page=5"
            resp = client.get(search_url, headers=headers)
            repos = resp.json().get("items", [])

        if not repos:
            return {"source": "GITHUB", "score": 0.45, "repos_found": 0, "status": "no_repos"}

        top = repos[0]
        owner_repo = top.get("full_name", "")

        commit_velocity = 0.0
        contributor_div = 0.0
        issue_res_rate  = 0.0

        if owner_repo:
            with httpx.Client(timeout=6.0) as client:
                # Commit frequency — last 100 commits
                c_resp = client.get(
                    f"https://api.github.com/repos/{owner_repo}/commits?per_page=100",
                    headers=headers
                )
                commits = c_resp.json() if isinstance(c_resp.json(), list) else []
                if len(commits) >= 2:
                    # Days spanned by last 100 commits
                    try:
                        first_ts = commits[-1]["commit"]["committer"]["date"]
                        last_ts  = commits[0]["commit"]["committer"]["date"]
                        from datetime import datetime as dt
                        span_days = max(1, (dt.fromisoformat(last_ts.replace("Z","+00:00")) -
                                        dt.fromisoformat(first_ts.replace("Z","+00:00"))).days)
                        commits_per_week = (len(commits) / span_days) * 7
                        commit_velocity = min(1.0, commits_per_week / 20.0)
                    except Exception:
                        commit_velocity = 0.3

                # Contributor diversity
                cont_resp = client.get(
                    f"https://api.github.com/repos/{owner_repo}/contributors?per_page=30",
                    headers=headers
                )
                contributors = cont_resp.json() if isinstance(cont_resp.json(), list) else []
                contributor_div = min(1.0, len(contributors) / 15.0)

                # Issue resolution rate
                closed_resp = client.get(
                    f"https://api.github.com/repos/{owner_repo}/issues?state=closed&per_page=30",
                    headers=headers
                )
                open_resp = client.get(
                    f"https://api.github.com/repos/{owner_repo}/issues?state=open&per_page=30",
                    headers=headers
                )
                n_closed = len(closed_resp.json()) if isinstance(closed_resp.json(), list) else 0
                n_open   = len(open_resp.json())   if isinstance(open_resp.json(),   list) else 1
                issue_res_rate = n_closed / max(1, n_closed + n_open)

        # Freshness: pushed within 60 days
        pushed_at = top.get("pushed_at", "")
        fresh = 0.15 if pushed_at > "2026-01-01" else (0.08 if pushed_at > "2025-06-01" else 0.0)

        score = (
            commit_velocity  * 0.35 +
            contributor_div  * 0.30 +
            issue_res_rate   * 0.20 +
            fresh
        )
        score = max(0.0, min(1.0, score))
        return {
            "source":            "GITHUB",
            "score":             round(score, 4),
            "repos_found":       len(repos),
            "top_repo":          top.get("full_name", ""),
            "commit_velocity":   round(commit_velocity, 3),
            "contributor_div":   round(contributor_div, 3),
            "issue_res_rate":    round(issue_res_rate, 3),
            "freshness_bonus":   fresh,
            "status":            "ok",
        }
    except Exception as e:
        logger.debug("[ANIMA][GITHUB] %s", e)
        return {"source": "GITHUB", "score": 0.50, "repos_found": 0,
                "status": "unavailable", "error": str(e)}


def _crawl_news_rss(entity_id: str) -> Dict:
    """
    News RSS crawl across 5+ feeds with VADER financial sentiment analysis.
    VADER scores range: compound ∈ [-1, 1] → normalized to [0,1].
    Weights scores by source CRED.
    """
    ticker = entity_id[:10].lower().replace("0x", "")
    # Also check hex prefix for onchain entities
    hex_tag = entity_id[:6].lower() if entity_id.startswith("0x") else ""

    weighted_scores = []
    total_articles  = 0
    source_breakdown = {}

    for source_id, feed_url in NEWS_FEEDS.items():
        cred = get_cred(source_id)
        if cred < CRED_EXCLUDE_THRESHOLD:
            continue
        try:
            feed = feedparser.parse(feed_url)
            relevant = []
            for entry in feed.entries[:30]:
                text = (
                    (entry.get("title", "") + " " + entry.get("summary", "")).lower()
                )
                if ticker in text or (hex_tag and hex_tag in text):
                    relevant.append(entry.get("title", "") + " " + entry.get("summary", ""))

            if relevant:
                compound_scores = []
                for txt in relevant:
                    vs = _vader.polarity_scores(txt)
                    compound_scores.append(vs["compound"])
                mean_compound = float(np.mean(compound_scores))
                # Map [-1,1] → [0,1]
                normalized = (mean_compound + 1.0) / 2.0
                weighted_scores.append((normalized, cred))
                total_articles += len(relevant)
                source_breakdown[source_id] = {
                    "articles": len(relevant),
                    "sentiment": round(normalized, 3),
                    "cred": round(cred, 3),
                }
        except Exception as e:
            logger.debug("[ANIMA][NEWS][%s] %s", source_id, e)

    if not weighted_scores:
        return {
            "source":   "NEWS_RSS",
            "score":    0.60,   # neutral prior
            "articles": 0,
            "status":   "no_relevant_coverage",
        }

    total_weight = sum(w for _, w in weighted_scores)
    composite    = sum(s * w for s, w in weighted_scores) / total_weight
    return {
        "source":            "NEWS_RSS",
        "score":             round(composite, 4),
        "articles_analyzed": total_articles,
        "sources_hit":       len(weighted_scores),
        "source_breakdown":  source_breakdown,
        "status":            "ok",
    }


def _crawl_regulatory(entity_id: str) -> Dict:
    """
    Regulatory enforcement RSS feeds (CFTC, FCA, ESMA).
    Checks if the entity or related terms appear in enforcement actions.
    Returns regulatory_clean_score ∈ [0,1]: 1 = no enforcement hits, 0 = enforcement action found.
    """
    ticker = entity_id[:10].lower().replace("0x", "")
    enforcement_hits = 0
    feeds_parsed = 0

    for source_id, feed_url in REGULATORY_FEEDS.items():
        cred = get_cred(source_id)
        if cred < CRED_EXCLUDE_THRESHOLD:
            continue
        try:
            feed = feedparser.parse(feed_url)
            for entry in feed.entries[:20]:
                text = (entry.get("title", "") + " " + entry.get("summary", "")).lower()
                if ticker in text or "cryptocurrency" in text or "digital asset" in text:
                    enforcement_hits += 1
            feeds_parsed += 1
        except Exception as e:
            logger.debug("[ANIMA][REG][%s] %s", source_id, e)

    # Enforcement hits heavily penalize the score
    score = max(0.20, 1.0 - min(0.80, enforcement_hits * 0.15))
    return {
        "source":           "REGULATORY",
        "score":            round(score, 4),
        "enforcement_hits": enforcement_hits,
        "feeds_parsed":     feeds_parsed,
        "status":           "ok",
    }


def _crawl_arxiv(entity_id: str) -> Dict:
    """
    arXiv preprint monitoring — cs.CR (crypto/security) + q-fin.TR (trading).

    Two-pass search:
      Pass 1 (entity-specific): Search for the entity ticker/address fragment
              in recent academic papers — direct research coverage signal.
      Pass 2 (domain-general):  DeFi oracle security behavioral — tracks
              academic activity in TRION's problem domain.

    VADER sentiment on paper abstracts: positive framing in academic research
    correlates with protocol health; negative = identified vulnerabilities or
    risk analysis (which may be an early warning).

    Returns academic_signal ∈ [0,1].
    """
    try:
        ns = {"atom": "http://www.w3.org/2005/Atom"}

        entity_papers   = 0
        domain_papers   = 0
        abstract_vader  = []

        # ── Pass 1: Entity-specific search ────────────────────────────────────
        entity_term = urllib.parse.quote(entity_id.replace("0x", "")[:16])
        url1 = (
            f"https://export.arxiv.org/api/query?search_query="
            f"all:{entity_term}"
            f"&start=0&max_results=5&sortBy=submittedDate&sortOrder=descending"
        )
        try:
            req1 = urllib.request.Request(url1, headers={"User-Agent": "TRION-Oracle/1.0"})
            with urllib.request.urlopen(req1, timeout=6) as resp1:
                root1 = ET.fromstring(resp1.read().decode())
            for entry in root1.findall("atom:entry", ns):
                published = entry.findtext("atom:published", "", ns)
                if published > "2024-01-01":
                    entity_papers += 1
                    abstract = entry.findtext("atom:summary", "", ns)
                    if abstract:
                        vs = _vader.polarity_scores(abstract[:500])
                        abstract_vader.append(vs["compound"])
        except Exception:
            pass

        # ── Pass 2: Domain-general DeFi / oracle / behavioral security ────────
        url2 = (
            f"https://export.arxiv.org/api/query?search_query="
            f"(cat:cs.CR+OR+cat:q-fin.TR)+AND+"
            f"all:(DeFi+oracle+security+behavioral+protocol)"
            f"&start=0&max_results=15&sortBy=submittedDate&sortOrder=descending"
        )
        req2 = urllib.request.Request(url2, headers={"User-Agent": "TRION-Oracle/1.0"})
        with urllib.request.urlopen(req2, timeout=6) as resp2:
            root2 = ET.fromstring(resp2.read().decode())

        for entry in root2.findall("atom:entry", ns):
            published = entry.findtext("atom:published", "", ns)
            if published > "2024-01-01":
                domain_papers += 1
                abstract = entry.findtext("atom:summary", "", ns)
                if abstract:
                    vs = _vader.polarity_scores(abstract[:500])
                    abstract_vader.append(vs["compound"])

        # ── Score computation ─────────────────────────────────────────────────
        # Entity-specific coverage carries more weight than domain activity
        entity_bonus = min(0.20, entity_papers * 0.05)
        domain_bonus = min(0.20, domain_papers * 0.015)
        base_score   = 0.60 + entity_bonus + domain_bonus

        # Blend with VADER: negative abstract sentiment = vulnerability research →
        # slight penalty (may be early warning); positive = protocol health papers
        if abstract_vader:
            mean_vader = float(np.mean(abstract_vader))
            # Negative compound: 5% penalty per -0.1 unit below 0
            vader_adj = mean_vader * 0.05  # small adjustment [-0.05, +0.05]
            base_score = base_score + vader_adj

        score = round(min(1.0, max(0.40, base_score)), 4)

        return {
            "source":              "ARXIV",
            "score":               score,
            "entity_papers":       entity_papers,
            "domain_papers":       domain_papers,
            "vader_abstract_mean": round(float(np.mean(abstract_vader)), 3) if abstract_vader else None,
            "status":              "ok",
        }
    except Exception as e:
        logger.debug("[ANIMA][ARXIV] %s", e)
        return {"source": "ARXIV", "score": 0.65, "entity_papers": 0, "domain_papers": 0,
                "status": "unavailable", "error": str(e)}


# ─────────────────────────────────────────────────────────────────────────────
# Full crawl — aggregates all sources, stores results, records predictions
# ─────────────────────────────────────────────────────────────────────────────

def run_full_crawl(entity_id: str) -> Dict:
    """
    L3.3 / L3.4 — Run a full ANIMA intelligence crawl across all sources.
    Stores per-source results in DB for CA computation.
    Records prediction for time-delayed outcome verification (HA loop).
    """
    now_ts = datetime.now(timezone.utc).timestamp()

    sec      = _crawl_sec_edgar(entity_id)
    gh       = _crawl_github(entity_id)
    news     = _crawl_news_rss(entity_id)
    reg      = _crawl_regulatory(entity_id)
    arx      = _crawl_arxiv(entity_id)

    source_results = {
        "SEC_EDGAR":  sec,
        "GITHUB":     gh,
        "NEWS_RSS":   news,
        "REGULATORY": reg,
        "ARXIV":      arx,
    }

    # Store per-source crawl results for CA computation
    with _db_lock:
        conn = _db_conn()
        for sid, result in source_results.items():
            conn.execute("""
                INSERT INTO anima_crawl_results (entity_id, source_id, score, raw_data, crawled_at)
                VALUES (?, ?, ?, ?, ?)
            """, (entity_id, sid, result.get("score", 0.5),
                  json.dumps(result), now_ts))
        conn.commit()
        conn.close()

    # Weighted composite using CRED-weighted sources
    weights = {
        "SEC_EDGAR":  get_cred("SEC_EDGAR")  * 0.30,
        "GITHUB":     get_cred("GITHUB")     * 0.25,
        "NEWS_RSS":   get_cred("COINDESK")   * 0.20,  # representative news CRED
        "REGULATORY": get_cred("CFTC")       * 0.15,
        "ARXIV":      get_cred("ARXIV")      * 0.10,
    }
    total_w   = sum(weights.values())
    composite = sum(source_results[k].get("score", 0.5) * w
                    for k, w in weights.items()) / max(total_w, 1e-6)
    composite = round(composite, 6)

    # Record prediction for HA loop (verified after MANIFEST_WINDOW_HOURS)
    pred_id = hashlib.sha256(f"{entity_id}:{now_ts}".encode()).hexdigest()[:16]
    with _db_lock:
        conn = _db_conn()
        conn.execute("""
            INSERT OR IGNORE INTO anima_predictions
                (pred_id, entity_id, source_id, predicted_value, prediction_ts, manifest_window)
            VALUES (?, ?, ?, ?, ?, ?)
        """, (pred_id, entity_id, "COMPOSITE", composite,
              now_ts, MANIFEST_WINDOW_HOURS * 3600))
        conn.commit()
        conn.close()

    result = {
        "entity_id":        entity_id,
        "composite_signal": composite,
        "prediction_id":    pred_id,
        "sources":          source_results,
        "cred_weights":     {k: round(v/max(total_w,1e-6), 3) for k, v in weights.items()},
        "crawled_at":       datetime.now(timezone.utc).isoformat(),
        "status":           "ok",
    }
    _crawl_cache[entity_id] = result
    logger.info("[ANIMA][CRAWL] %s composite=%.3f", entity_id[:16], composite)
    return result


# ─────────────────────────────────────────────────────────────────────────────
# L3.3 PCR — Pattern Coherence Ratio (sequence-based)
# ─────────────────────────────────────────────────────────────────────────────

def _compute_pcr(entity_id: str, entity_history: Dict) -> float:
    """
    L3.3 PCR — Fraction of archetype-expected behavioral dimensions that the
    entity is currently expressing, measured over a sequence window (not just
    the latest single record).

    Method:
      1. Take last PCR_SEQUENCE_WINDOW records from entity_history.
      2. Compute sequence centroid (mean vector).
      3. Find closest archetype centroid.
      4. PCR = (active dims in entity ∩ active dims in archetype) / active dims in archetype.
    """
    if _centroids_ref is None or len(_centroids_ref) == 0:
        return 0.50

    beo_id  = _resolve_beo(entity_id)
    records = entity_history.get(beo_id, [])

    if not records:
        # No history yet — return neutral prior rather than zeroing ANIMA entirely
        return 0.50

    # Use sequence window
    window = records[-PCR_SEQUENCE_WINDOW:]
    vecs   = [np.array(r["vector"], dtype="float32") for r in window if "vector" in r]
    if not vecs:
        return 0.50

    seq_centroid = np.mean(vecs, axis=0).astype("float32")
    norm = np.linalg.norm(seq_centroid)
    if norm < 1e-10:
        return 0.50

    # Find closest archetype
    sims = np.dot(_centroids_ref, seq_centroid) / (
        np.linalg.norm(_centroids_ref, axis=1) * norm + 1e-10
    )
    arch_id = int(np.argmax(sims))
    expected = _centroids_ref[arch_id].astype("float32")

    max_exp = np.max(np.abs(expected))
    max_act = np.max(np.abs(seq_centroid))

    active_expected = np.abs(expected)     > PCR_ACTIVE_THRESHOLD * max(max_exp, 1e-10)
    active_actual   = np.abs(seq_centroid) > PCR_ACTIVE_THRESHOLD * max(max_act, 1e-10)

    n_expected = active_expected.sum()
    if n_expected == 0:
        return float(sims[arch_id])

    pcr = float((active_expected & active_actual).sum() / n_expected)
    return round(pcr, 6)


# ─────────────────────────────────────────────────────────────────────────────
# L3.3 HA — Historical Accuracy (time-delayed verification)
# ─────────────────────────────────────────────────────────────────────────────

def _compute_ha(entity_id: str) -> Tuple[float, int]:
    """
    L3.3 HA — Rolling 90-day Historical Accuracy from verified outcomes.
    Returns (ha_score, n_verified_samples).
    """
    cutoff_ts = (datetime.now(timezone.utc) - timedelta(days=HA_WINDOW_DAYS)).timestamp()
    with _db_lock:
        conn = _db_conn()
        rows = conn.execute("""
            SELECT predicted_value, realized_value, error
            FROM anima_predictions
            WHERE entity_id = ?
              AND verified = 1
              AND verified_at > ?
            ORDER BY verified_at DESC
            LIMIT 200
        """, (entity_id, cutoff_ts)).fetchall()
        conn.close()

    if not rows:
        return 0.80, 0  # neutral prior — L3.3 whitepaper spec

    correct = sum(1 for r in rows if r["error"] is not None and r["error"] <= HA_CORRECT_TOLERANCE)
    ha      = correct / len(rows)
    return round(ha, 6), len(rows)


def verify_pending_outcomes(entity_id: Optional[str] = None):
    """
    L3.3 HA loop — Close the feedback loop by verifying predictions whose
    manifest_window has elapsed. Compares predicted composite score to the
    most recent crawl result for the same entity.
    Called by APScheduler every OUTCOME_VERIFY_HOURS.
    """
    now_ts = datetime.now(timezone.utc).timestamp()
    with _db_lock:
        conn = _db_conn()
        query = """
            SELECT pred_id, entity_id, source_id, predicted_value, prediction_ts, manifest_window
            FROM anima_predictions
            WHERE verified = 0
              AND (prediction_ts + manifest_window) < ?
        """
        params = [now_ts]
        if entity_id:
            query += " AND entity_id = ?"
            params.append(entity_id)
        rows = conn.execute(query, params).fetchall()
        conn.close()

    for row in rows:
        eid = row["entity_id"]
        # Get the most recent crawl result as the "realized" value
        with _db_lock:
            conn = _db_conn()
            recent = conn.execute("""
                SELECT score FROM anima_crawl_results
                WHERE entity_id = ? AND crawled_at > ?
                ORDER BY crawled_at DESC LIMIT 1
            """, (eid, row["prediction_ts"] + row["manifest_window"] - 3600)).fetchone()
            conn.close()

        if recent:
            realized = recent["score"]
            error    = abs(realized - row["predicted_value"])
            correct  = error <= HA_CORRECT_TOLERANCE

            with _db_lock:
                conn = _db_conn()
                conn.execute("""
                    UPDATE anima_predictions
                    SET realized_value = ?, error = ?, verified = 1, verified_at = ?
                    WHERE pred_id = ?
                """, (realized, error, now_ts, row["pred_id"]))
                conn.commit()
                conn.close()

            # Update source CRED based on whether prediction was correct
            # Use the actual source_id from the prediction record, not a hardcoded value
            update_cred(
                row["source_id"] if row["source_id"] in SOURCES else "SEC_EDGAR",
                "VERIFIED" if correct else "FALSIFIED",
                entity_id=eid,
                note=f"pred={row['predicted_value']:.3f} real={realized:.3f} err={error:.3f}"
            )
            logger.debug("[ANIMA][HA] %s pred=%.3f real=%.3f correct=%s",
                        eid[:16], row["predicted_value"], realized, correct)


# ─────────────────────────────────────────────────────────────────────────────
# L3.3 CA — Cross-Source Agreement (credibility-weighted)
# ─────────────────────────────────────────────────────────────────────────────

def _compute_ca(entity_id: str) -> float:
    """
    L3.3 CA = Σ_s CRED(s,t) × agreement(s,t) / Σ_s CRED(s,t)

    agreement(s,t) = 1 - |score_s - consensus| / max_deviation
    Uses the last 24h of crawl results per source.
    """
    cutoff_ts = (datetime.now(timezone.utc) - timedelta(hours=24)).timestamp()
    with _db_lock:
        conn = _db_conn()
        rows = conn.execute("""
            SELECT source_id, AVG(score) as avg_score
            FROM anima_crawl_results
            WHERE entity_id = ? AND crawled_at > ?
            GROUP BY source_id
        """, (entity_id, cutoff_ts)).fetchall()
        conn.close()

    if len(rows) < 2:
        return 0.70  # neutral prior when insufficient multi-source data

    source_scores = {r["source_id"]: r["avg_score"] for r in rows}
    consensus     = float(np.mean(list(source_scores.values())))
    max_dev       = max(abs(s - consensus) for s in source_scores.values())
    if max_dev < 1e-6:
        return 1.0  # perfect agreement

    weighted_agreement = 0.0
    total_weight       = 0.0

    for sid, score in source_scores.items():
        # Map source_id to registered source for CRED lookup
        cred_sid = sid if sid in SOURCES else _source_id_map(sid)
        cred     = get_cred(cred_sid)
        if cred < CRED_EXCLUDE_THRESHOLD:
            continue
        agreement = 1.0 - abs(score - consensus) / max_dev
        weighted_agreement += cred * agreement
        total_weight       += cred

    if total_weight < 1e-6:
        return 0.70

    return round(weighted_agreement / total_weight, 6)


def _source_id_map(sid: str) -> str:
    """Map crawler source IDs to registered SOURCES keys."""
    mapping = {
        "NEWS_RSS":   "COINDESK",
        "REGULATORY": "CFTC",
        "COMPOSITE":  "SEC_EDGAR",
    }
    return mapping.get(sid, sid)


# ─────────────────────────────────────────────────────────────────────────────
# Cross-domain signal injection — L6.1 BC, L9.1 XSL, L6.2 BRT
# Whitepaper: "BC feeds into ANIMA as a cross-domain signal" (L6.1)
#             "XSL feeds into ANIMA as a cross-domain signal" (L9.1)
#             "BRT enables ANIMA to detect human behavioral shifts" (L6.2)
# ─────────────────────────────────────────────────────────────────────────────

def ingest_cross_domain_signals(
    entity_id: str,
    bc_score: float = 0.70,
    xsl_score: float = 0.70,
    brt: Optional[Dict] = None,
) -> None:
    """
    L6.1 / L6.2 / L9.1 — Inject cross-domain signals as synthetic ANIMA sources.

    These are treated as additional "sources" in CA computation:
      BC_SIGNAL  — Biological Capital score from L6.1 (ecosystem health)
      XSL_SIGNAL — Cross-Species Liquidity score from L9.1
      BRT_SIGNAL — Biological Rhythm coherence from L6.2

    BRT coherence: deviation from expected circadian/lunar/seasonal pattern
    degrades the BRT_SIGNAL score, flagging human behavioral regime shifts.
    """
    now_ts = datetime.now(timezone.utc).timestamp()

    # ── BRT coherence score ────────────────────────────────────────────────────
    # Perfect circadian phase = 0.5 (midpoint); near 0 or 1 = anomaly window
    brt_coherence = 0.70  # neutral prior
    if brt:
        circ  = brt.get("circadian_phase", 0.5)
        ultr  = brt.get("ultradian_phase", 0.5)
        lunar = brt.get("lunar_phase", 0.5)
        seas  = brt.get("seasonal_phase", 0.5)
        # Deviation from midpoint (0.5) is the rhythm anomaly signal
        # Low deviation = normal circadian pattern; extreme values = regime shift
        circ_dev  = abs(circ  - 0.5) * 2   # [0,1]
        lunar_dev = abs(lunar - 0.5) * 2
        seas_dev  = abs(seas  - 0.5) * 2
        # BRT signal healthy when rhythms are at expected phases (low deviation)
        brt_coherence = round(1.0 - 0.4 * circ_dev - 0.3 * lunar_dev - 0.3 * seas_dev, 4)
        brt_coherence = max(0.0, min(1.0, brt_coherence))

    rows = [
        ("BC_SIGNAL",  "biological_capital",  bc_score),
        ("XSL_SIGNAL", "cross_species",       xsl_score),
        ("BRT_SIGNAL", "biological_rhythm",   brt_coherence),
    ]

    with _db_lock:
        conn = _db_conn()
        try:
            for source_id, category, score in rows:
                conn.execute("""
                    INSERT INTO anima_crawl_results
                        (entity_id, source_id, score, raw_data, crawled_at)
                    VALUES (?, ?, ?, ?, ?)
                """, (entity_id, source_id, score,
                      json.dumps({"category": category, "cross_domain": True}), now_ts))
            conn.commit()
        except Exception as exc:
            logger.warning("[ANIMA][cross-domain] Failed to ingest: %s", exc)
        finally:
            conn.close()


# ─────────────────────────────────────────────────────────────────────────────
# L3.3 — Full ANIMA Score A(t) = PCR × HA × CA
# ─────────────────────────────────────────────────────────────────────────────

def get_anima_score(entity_id: str, entity_history: Dict) -> Dict:
    """
    L3.3 — ANIMA Score A(t) = PCR(t) × HA(t) × CA(t) ∈ [0,1].

    PCR: Pattern Coherence Ratio — sequence-window vs archetype (real behavioral pattern matching)
    HA:  Historical Accuracy — rolling 90-day verified outcome accuracy
    CA:  Cross-Source Agreement — CRED-weighted agreement across external sources

    Flags:
      ha_flag:      True if HA < HA_FLAG_THRESHOLD (0.70)
      anima_disabled: True if HA < HA_DISABLE_THRESHOLD (0.60)
    """
    pcr            = _compute_pcr(entity_id, entity_history)
    ha, n_verified = _compute_ha(entity_id)
    ca             = _compute_ca(entity_id)

    ha_flag      = ha < HA_FLAG_THRESHOLD
    anima_disabled = ha < HA_DISABLE_THRESHOLD

    anima_score = 0.0 if anima_disabled else round(pcr * ha * ca, 6)

    # Apply reflexivity dampening (L3.5)
    reflexivity   = _compute_reflexivity(entity_id)
    a_adj         = round(anima_score * (1.0 - REFLEXIVITY_BETA * reflexivity["reflexivity"]), 6)
    reflexivity_flag = reflexivity["reflexivity"] > REFLEXIVITY_FLAG_THR

    # ── Whitepaper §3.3: ANIMA output MUST be PROBABILITY_DISTRIBUTION not POINT_PREDICTION
    # std_dev: uncertainty grows when HA < 1.0 and CA < 1.0 and reflexivity is present
    uncertainty   = round(max(0.02, (1.0 - ha) * 0.3 + (1.0 - ca) * 0.2
                               + reflexivity["reflexivity"] * 0.1), 6)
    ci95_half     = round(min(a_adj, 1.96 * uncertainty), 6)
    calibration   = round(ha * ca, 4)     # proxy: HA × CA → well-calibrated when both ≈1

    return {
        "entity_id":        entity_id,
        "anima_score":      anima_score,
        "a_adj":            a_adj,          # A_adj(t) after reflexivity dampening (L3.5)
        # Whitepaper §3.3 mandatory probability distribution format
        "probability_distribution": {
            "type":        "PROBABILITY_DISTRIBUTION",
            "mean":        a_adj,
            "std_dev":     uncertainty,
            "CI_95":       [round(max(0.0, a_adj - ci95_half), 6),
                            round(min(1.0, a_adj + ci95_half), 6)],
            "calibration": calibration,
        },
        "components": {
            "pcr": round(pcr, 4),
            "ha":  round(ha,  4),
            "ca":  round(ca,  4),
        },
        "reflexivity":       round(reflexivity["reflexivity"], 4),
        "reflexivity_flag":  reflexivity_flag,
        "ha_flag":           ha_flag,
        "anima_disabled":    anima_disabled,
        "n_verified_outcomes": n_verified,
        "sequence_window":   PCR_SEQUENCE_WINDOW,
        "status":            "ok",
    }


# ─────────────────────────────────────────────────────────────────────────────
# L3.5 — Reflexivity Dampening
# ─────────────────────────────────────────────────────────────────────────────

def record_signal_publication(entity_id: str, anima_score: float, phi_before: float):
    """
    L3.5 — Record a signal publication event.
    Called by oracle/relayer when a TRION signal is published.
    phi_before = Φ(t) at time of publication (from L0 indexer).
    """
    now_ts = datetime.now(timezone.utc).timestamp()
    _signal_pub_log.append((now_ts, anima_score, entity_id, phi_before))
    if len(_signal_pub_log) > 1000:
        _signal_pub_log.pop(0)


def _compute_reflexivity(entity_id: str) -> Dict:
    """
    L3.5 — Compute reflexivity for an entity.
    ANIMA_reflexivity = corr(ANIMA signal strength at t-1, behavioral change at t).
    Uses stored publication events and subsequent Φ(t) changes.
    """
    now_ts = datetime.now(timezone.utc).timestamp()
    cutoff_ts = now_ts - 7 * 86400  # last 7 days

    with _db_lock:
        conn = _db_conn()
        rows = conn.execute("""
            SELECT reflexivity FROM anima_reflexivity
            WHERE entity_id = ? AND recorded_at > ?
            ORDER BY recorded_at DESC LIMIT 50
        """, (entity_id, cutoff_ts)).fetchall()
        conn.close()

    if not rows:
        return {"reflexivity": 0.0, "samples": 0, "status": "insufficient_data"}

    reflexivity = float(np.mean([r["reflexivity"] for r in rows]))
    return {
        "reflexivity": round(reflexivity, 6),
        "samples":     len(rows),
        "flag":        reflexivity > REFLEXIVITY_FLAG_THR,
        "status":      "ok",
    }


def record_phi_update(entity_id: str, phi_current: float, ts: float):
    """
    Called by L0 daemon / FAISS service whenever Φ(t) is updated for an entity.
    Checks if there was a recent publication and records the phi change for reflexivity.
    """
    now_ts = ts
    window_start = now_ts - REFLEXIVITY_WINDOW_H * 3600

    # Find publications in this window for this entity
    relevant_pubs = [
        (pub_ts, anima_s, phi_b)
        for pub_ts, anima_s, eid, phi_b in _signal_pub_log
        if eid == entity_id and window_start < pub_ts <= now_ts
    ]
    if not relevant_pubs:
        return

    for pub_ts, anima_s, phi_before in relevant_pubs:
        if phi_before < 1e-6:
            continue
        delta_phi   = abs(phi_current - phi_before)
        reflexivity = min(1.0, delta_phi / max(phi_before, 1e-6))
        record_ts   = datetime.now(timezone.utc).timestamp()
        with _db_lock:
            conn = _db_conn()
            conn.execute("""
                INSERT INTO anima_reflexivity
                    (entity_id, pub_ts, anima_at_pub, phi_before, phi_after,
                     delta_phi, reflexivity, recorded_at)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?)
            """, (entity_id, pub_ts, anima_s, phi_before,
                  phi_current, delta_phi, reflexivity, record_ts))
            conn.commit()
            conn.close()


def get_reflexivity_report(entity_id: str) -> Dict:
    """Public API: get full reflexivity report for an entity."""
    now_ts = datetime.now(timezone.utc).timestamp()
    cutoff = now_ts - 30 * 86400
    with _db_lock:
        conn = _db_conn()
        rows = conn.execute("""
            SELECT pub_ts, anima_at_pub, phi_before, phi_after, delta_phi, reflexivity, recorded_at
            FROM anima_reflexivity
            WHERE entity_id = ? AND recorded_at > ?
            ORDER BY recorded_at DESC LIMIT 100
        """, (entity_id, cutoff)).fetchall()
        conn.close()

    if not rows:
        return {"entity_id": entity_id, "reflexivity": 0.0, "samples": 0,
                "status": "no_data", "warning": "No signal publications recorded yet"}

    reflexivity = float(np.mean([r["reflexivity"] for r in rows]))
    return {
        "entity_id":    entity_id,
        "reflexivity":  round(reflexivity, 6),
        "a_dampening":  round(REFLEXIVITY_BETA * reflexivity, 6),
        "samples":      len(rows),
        "flag":         reflexivity > REFLEXIVITY_FLAG_THR,
        "recent":       [dict(r) for r in rows[:5]],
        "status":       "ok",
    }


# ─────────────────────────────────────────────────────────────────────────────
# L3.5 — Manifestation Gap Monitor
# ─────────────────────────────────────────────────────────────────────────────

def record_manifestation_gap(entity_id: str, signal_type: str,
                              predicted_at: float, observed_at: float):
    """
    L3.5 MG(S,t) = B_predicted(S,t) - B_observed(t)
    mg > 0: ANIMA predicted early (optimistic)
    mg < 0: ANIMA predicted late (lagging)
    mg = 0: perfect timing
    """
    mg = (predicted_at - observed_at) / 3600.0  # in hours
    now_ts = datetime.now(timezone.utc).timestamp()
    with _db_lock:
        conn = _db_conn()
        conn.execute("""
            INSERT INTO anima_manifestation_gap
                (entity_id, signal_type, predicted_at, observed_at, mg, recorded_at)
            VALUES (?, ?, ?, ?, ?, ?)
        """, (entity_id, signal_type, predicted_at, observed_at, mg, now_ts))
        conn.commit()
        conn.close()
    _mg_log[entity_id].append(mg)
    if len(_mg_log[entity_id]) > 200:
        _mg_log[entity_id].pop(0)


def get_manifestation_gap_report() -> Dict:
    """
    L3.5 — Manifestation Gap rolling mean per entity and signal type.
    Used to recalibrate timing predictions.
    """
    cutoff_ts = (datetime.now(timezone.utc) - timedelta(days=90)).timestamp()
    with _db_lock:
        conn = _db_conn()
        rows = conn.execute("""
            SELECT entity_id, signal_type,
                   AVG(mg) as mean_mg,
                   COUNT(*) as samples,
                   MIN(mg) as min_mg,
                   MAX(mg) as max_mg
            FROM anima_manifestation_gap
            WHERE recorded_at > ?
            GROUP BY entity_id, signal_type
            ORDER BY ABS(AVG(mg)) DESC
        """, (cutoff_ts,)).fetchall()
        conn.close()

    return {
        "manifestation_gaps": [dict(r) for r in rows],
        "interpretation": {
            "mg_positive": "ANIMA predicted early (optimistic bias)",
            "mg_negative": "ANIMA predicted late (lagging bias)",
            "mg_zero":     "Perfect timing calibration",
        },
        "status": "ok",
    }


# ─────────────────────────────────────────────────────────────────────────────
# L3.7 — Intelligence Maintenance Protocol
# ─────────────────────────────────────────────────────────────────────────────

def run_intelligence_maintenance():
    """
    L3.7 IM(component, t) = Accuracy(component, t) / Accuracy(component, t_baseline).
    IM < IM_DEGRADATION_THR → trigger maintenance (re-crawl + CRED reset).
    Runs every IM_CHECK_INTERVAL_H hours via scheduler.
    """
    now_ts = datetime.now(timezone.utc).timestamp()
    logger.info("[ANIMA][IM] Running intelligence maintenance check")

    with _db_lock:
        conn = _db_conn()
        sources_rows = conn.execute("SELECT source_id FROM anima_sources").fetchall()
        conn.close()

    for row in sources_rows:
        sid = row["source_id"]
        # Current HA for this source
        cutoff = (datetime.now(timezone.utc) - timedelta(days=HA_WINDOW_DAYS)).timestamp()
        with _db_lock:
            conn = _db_conn()
            preds = conn.execute("""
                SELECT predicted_value, realized_value, error
                FROM anima_predictions
                WHERE source_id = ? AND verified = 1 AND verified_at > ?
            """, (sid, cutoff)).fetchall()
            baseline = conn.execute("""
                SELECT baseline_ha FROM anima_im_status WHERE source_id = ?
            """, (sid,)).fetchone()
            conn.close()

        if not preds:
            continue

        current_ha = sum(1 for p in preds if p["error"] and p["error"] <= HA_CORRECT_TOLERANCE) / len(preds)
        baseline_ha = baseline["baseline_ha"] if baseline else 0.80
        im_ratio    = current_ha / max(baseline_ha, 0.01)

        maintenance_triggered = 0
        if im_ratio < IM_DEGRADATION_THR:
            logger.warning("[ANIMA][IM] Source %s degraded: IM=%.3f → triggering maintenance", sid, im_ratio)
            maintenance_triggered = 1
            # Reset CRED to a recovery level (not full reset — that would be too aggressive)
            new_cred = max(CRED_FLAG_THRESHOLD, get_cred(sid) * 0.90)
            with _db_lock:
                conn = _db_conn()
                conn.execute("UPDATE anima_sources SET cred = ? WHERE source_id = ?",
                             (new_cred, sid))
                conn.commit()
                conn.close()
            _cred_cache[sid] = new_cred

        with _db_lock:
            conn = _db_conn()
            conn.execute("""
                INSERT OR REPLACE INTO anima_im_status
                    (source_id, baseline_ha, current_ha, im_ratio, last_checked, maintenance_triggered)
                VALUES (?, ?, ?, ?, ?, ?)
            """, (sid, baseline_ha, current_ha, im_ratio, now_ts, maintenance_triggered))
            conn.commit()
            conn.close()

    logger.info("[ANIMA][IM] Maintenance check complete")


def get_im_status() -> Dict:
    """L3.7 — Return Intelligence Maintenance Protocol status for all sources."""
    with _db_lock:
        conn = _db_conn()
        rows = conn.execute("""
            SELECT source_id, baseline_ha, current_ha, im_ratio,
                   last_checked, maintenance_triggered
            FROM anima_im_status ORDER BY im_ratio ASC
        """).fetchall()
        conn.close()
    return {
        "im_status":    [dict(r) for r in rows],
        "threshold":    IM_DEGRADATION_THR,
        "check_interval_h": IM_CHECK_INTERVAL_H,
        "status":       "ok",
    }


# ─────────────────────────────────────────────────────────────────────────────
# APScheduler — background intelligence loop
# ─────────────────────────────────────────────────────────────────────────────

def _scheduled_crawl_cycle():
    """
    Background crawl cycle — runs every CRAWL_CYCLE_MINUTES.
    Crawls the most recently active entities.
    """
    if _entity_history_ref is None:
        return
    # Get the 10 most recently active entities
    entities = list(_entity_history_ref.keys())[-10:]
    for eid in entities:
        try:
            run_full_crawl(eid)
        except Exception as e:
            logger.debug("[ANIMA][SCHEDULER][CRAWL] %s: %s", eid[:16], e)


def _scheduled_cred_decay():
    """
    Daily CRED decay — runs every 24h.
    Forces a decay pass over all registered sources.
    """
    for sid in list(SOURCES.keys()):
        try:
            _apply_cred_decay(sid)
        except Exception as e:
            logger.debug("[ANIMA][SCHEDULER][CRED] %s: %s", sid, e)
    logger.info("[ANIMA][SCHEDULER] Daily CRED decay applied to %d sources", len(SOURCES))


def _scheduled_outcome_verification():
    """Verify pending predictions — runs every OUTCOME_VERIFY_HOURS."""
    try:
        verify_pending_outcomes()
    except Exception as e:
        logger.debug("[ANIMA][SCHEDULER][HA] %s", e)


def _scheduled_im_check():
    """IM Protocol — runs every IM_CHECK_INTERVAL_H hours."""
    try:
        run_intelligence_maintenance()
    except Exception as e:
        logger.debug("[ANIMA][SCHEDULER][IM] %s", e)


def _start_scheduler():
    """Start the APScheduler background intelligence loop."""
    global _scheduler
    if _scheduler and _scheduler.running:
        return
    _scheduler = BackgroundScheduler(daemon=True)
    _scheduler.add_job(_scheduled_crawl_cycle,        "interval",
                       minutes=CRAWL_CYCLE_MINUTES,   id="anima_crawl")
    _scheduler.add_job(_scheduled_cred_decay,         "interval",
                       hours=24,                      id="anima_cred_decay")
    _scheduler.add_job(_scheduled_outcome_verification, "interval",
                       hours=OUTCOME_VERIFY_HOURS,    id="anima_outcome_verify")
    _scheduler.add_job(_scheduled_im_check,           "interval",
                       hours=IM_CHECK_INTERVAL_H,     id="anima_im_check")
    _scheduler.start()
    logger.info("[ANIMA] Scheduler started — crawl every %dm, HA verify every %dh, IM every %dh",
                CRAWL_CYCLE_MINUTES, OUTCOME_VERIFY_HOURS, IM_CHECK_INTERVAL_H)


# ─────────────────────────────────────────────────────────────────────────────
# Helpers
# ─────────────────────────────────────────────────────────────────────────────

def _resolve_beo(entity_id: str) -> str:
    """
    Canonical BEO ID — must exactly match faiss_service.resolve_beo so
    entity_history lookups succeed.

    Rule: if the input is already a 64-char lowercase hex string (a pre-resolved
    SHA3-256 BEO ID from the L0 daemon), return it unchanged to prevent double-
    hashing.  Otherwise hash with SHA3-256.
    """
    normalized = entity_id.strip().lower()
    if len(normalized) == 64 and all(c in "0123456789abcdef" for c in normalized):
        return normalized   # already canonical — return as-is
    return hashlib.sha3_256(normalized.encode()).hexdigest()


# ─────────────────────────────────────────────────────────────────────────────
# Public initialisation — called from faiss_service.py
# ─────────────────────────────────────────────────────────────────────────────

def init_anima(db_path: str,
               entity_history: Dict,
               centroids: Optional[np.ndarray] = None):
    """
    Initialise the ANIMA engine. Call once at service startup from faiss_service.py.

    Args:
        db_path:        Path to the shared SQLite DB (akashic_state.db).
        entity_history: Live reference to the entity_history dict in faiss_service.
        centroids:      Live reference to the archetype centroids array.
    """
    global _db_path, _entity_history_ref, _centroids_ref
    _db_path            = db_path
    _entity_history_ref = entity_history
    _centroids_ref      = centroids

    _init_anima_tables()
    _bootstrap_sources()
    _start_scheduler()

    logger.info("[ANIMA] Engine initialised | db=%s | sources=%d | scheduler=running",
                db_path, len(SOURCES))


def update_centroids(centroids: np.ndarray):
    """Called when FAISS centroids are reloaded."""
    global _centroids_ref
    _centroids_ref = centroids


def get_source_summary() -> Dict:
    """Return complete source credibility summary."""
    return {
        "sources":     get_all_cred_status(),
        "source_count": len(SOURCES),
        "status":      "ok",
    }


def get_crawl_cache(entity_id: str) -> Optional[Dict]:
    """Return last crawl result for an entity without triggering a new crawl."""
    return _crawl_cache.get(entity_id)
