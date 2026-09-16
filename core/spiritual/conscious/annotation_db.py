"""
TRION Protocol — L8 Conscious Plane annotation database

Initialises the SQLite schema that backs the human-annotation network
(K(t) plane). Until this module existed, the annotation interface had
no persistence layer: submissions could not be stored, retrieved, or
audited. The four tables created here mirror the specification:

  annotations            — commit-reveal annotation reveals with stake
  annotators             — pseudonymous annotator registry + tenure
  annotation_challenges  — dispute bonds and resolution state
  indigenous_consent      — verified-consent records for indigenous
                            knowledge systems (revocable at any time)

The DB path defaults to ``annotations.db`` next to the other TRION
state DBs (``bh_ledger.db``, ``indigenous_knowledge.db``) and can be
overridden via the ``ANNOTATION_DB_PATH`` environment variable.

HONEST DISCLOSURE:
  Tables are created on startup with NO seeded rows. Annotation
  records must come from real commit-reveal submissions by registered
  annotators. Bootstrap K(t)=0.10 remains in effect until the live
  annotation network is onboarded at mainnet.
"""

from __future__ import annotations

import logging
import os
import sqlite3
import threading
import time
from typing import Optional

logger = logging.getLogger(__name__)

_DB_PATH = os.environ.get(
    "ANNOTATION_DB_PATH",
    os.path.join(os.path.dirname(os.path.abspath(__file__)),
                 "../../../annotations.db"),
)
_DB_PATH = os.path.normpath(_DB_PATH)

_lock = threading.Lock()


def annotation_db_path() -> str:
    """Return the resolved annotation-DB filesystem path."""
    return _DB_PATH


def annotation_conn() -> sqlite3.Connection:
    """Open a WAL-mode SQLite connection for annotation tables."""
    conn = sqlite3.connect(_DB_PATH, check_same_thread=False, timeout=60.0)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA journal_mode=WAL")
    conn.execute("PRAGMA synchronous=NORMAL")
    conn.execute("PRAGMA busy_timeout=60000")
    conn.execute("PRAGMA wal_autocheckpoint=2000")
    conn.execute("PRAGMA foreign_keys=ON")
    return conn


_SCHEMA = """
-- ── annotations: commit-reveal annotation reveals ───────────────────────────
CREATE TABLE IF NOT EXISTS annotations (
    annotation_id   TEXT PRIMARY KEY,        -- UUID v4 / SHA3-256 of commit_hash + reveal salt
    entity_id       TEXT NOT NULL,           -- BEO / EVM / alias identifier being annotated
    type            INTEGER NOT NULL,        -- AnnotationType enum (0..4)
    language        TEXT NOT NULL DEFAULT 'en',
    content         TEXT NOT NULL DEFAULT '',
    confidence      REAL NOT NULL DEFAULT 0.0,  -- k_score ∈ [0, 1]
    stake           REAL NOT NULL DEFAULT 0.0,  -- stake_weight committed
    annotator_id    TEXT NOT NULL,           -- pseudonymous annotator hash
    timestamp       REAL NOT NULL,           -- reveal timestamp
    ttl             REAL NOT NULL DEFAULT 0  -- seconds (0 = no expiry)
);
CREATE INDEX IF NOT EXISTS ann_entity    ON annotations(entity_id);
CREATE INDEX IF NOT EXISTS ann_annotator ON annotations(annotator_id);
CREATE INDEX IF NOT EXISTS ann_type     ON annotations(type);
CREATE INDEX IF NOT EXISTS ann_ts       ON annotations(timestamp);

-- ── annotators: pseudonymous annotator registry ────────────────────────────
CREATE TABLE IF NOT EXISTS annotators (
    annotator_id              TEXT PRIMARY KEY,    -- SHA3-256 commitment hash
    type                      INTEGER NOT NULL,    -- AnnotationType.INDIGENOUS_KNW, EXPERT_JUDGMENT, ...
    tenure_days               INTEGER NOT NULL DEFAULT 0,
    accuracy_history          TEXT NOT NULL DEFAULT '[]',   -- JSON array of recent accuracy ratios
    jurisdictions             TEXT NOT NULL DEFAULT '[]',    -- JSON array of jurisdiction codes (ACP5)
    languages                 TEXT NOT NULL DEFAULT '[]',    -- JSON array of ISO-639-1 codes
    stake_weight_multiplier   REAL NOT NULL DEFAULT 1.0,     -- elder/knowledge-holder multiplier
    term_start                REAL NOT NULL,
    term_end                  REAL NOT NULL                  -- term_start + 24mo max (ACP2)
);
CREATE INDEX IF NOT EXISTS ann_type_idx ON annotators(type);
CREATE INDEX IF NOT EXISTS ann_active   ON annotators(term_end);

-- ── annotation_challenges: dispute bonds and resolution state ───────────────
CREATE TABLE IF NOT EXISTS annotation_challenges (
    challenge_id    TEXT PRIMARY KEY,
    annotation_id   TEXT NOT NULL REFERENCES annotations(annotation_id),
    challenger_id   TEXT NOT NULL,
    bond            REAL NOT NULL,           -- staked bond (slashed on frivolous challenge)
    reason          TEXT NOT NULL DEFAULT '',
    status          TEXT NOT NULL DEFAULT 'OPEN',  -- OPEN, RESOLVED_VALID, RESOLVED_INVALID, SLASHED
    timestamp       REAL NOT NULL,
    resolved_at     REAL,
    resolver_id     TEXT
);
CREATE INDEX IF NOT EXISTS chal_annotation ON annotation_challenges(annotation_id);
CREATE INDEX IF NOT EXISTS chal_status     ON annotation_challenges(status);

-- ── indigenous_consent: verified-consent records (revocable) ───────────────
CREATE TABLE IF NOT EXISTS indigenous_consent (
    consent_id      TEXT PRIMARY KEY,
    community       TEXT NOT NULL,           -- pseudonymous community identifier
    verified_by     TEXT NOT NULL,           -- independent verifier identity
    revocable       INTEGER NOT NULL DEFAULT 1,
    consent_scope   TEXT NOT NULL DEFAULT 'annotation_only',
    timestamp       REAL NOT NULL,
    revoked         INTEGER NOT NULL DEFAULT 0,
    revoked_at      REAL,
    revoked_by      TEXT
);
CREATE INDEX IF NOT EXISTS ic_community ON indigenous_consent(community);
CREATE INDEX IF NOT EXISTS ic_active    ON indigenous_consent(revoked, community);
"""


def init_annotation_db() -> bool:
    """Create the annotation tables if they do not exist.

    Returns True on success, False on failure (logged at WARNING).
    Idempotent: safe to call on every API startup.
    """
    with _lock:
        try:
            os.makedirs(os.path.dirname(_DB_PATH) or ".", exist_ok=True)
        except Exception:
            # dirname may be empty for relative paths; ignore.
            pass
        try:
            conn = annotation_conn()
            conn.executescript(_SCHEMA)
            # Record an init marker so operators can verify the schema was applied
            conn.execute(
                """
                CREATE TABLE IF NOT EXISTS annotation_schema_meta (
                    key   TEXT PRIMARY KEY,
                    value TEXT NOT NULL
                )
                """
            )
            conn.execute(
                "INSERT OR REPLACE INTO annotation_schema_meta(key, value) "
                "VALUES ('schema_version', '1'), ('last_init', ?)",
                (str(int(time.time())),),
            )
            conn.commit()
            conn.close()
            logger.info(
                "[annotation_db] schema initialised at %s (annotations, "
                "annotators, annotation_challenges, indigenous_consent)",
                _DB_PATH,
            )
            return True
        except Exception as exc:  # pragma: no cover — exercised via init_annotation_db()
            logger.warning("[annotation_db] schema init failed: %s", exc)
            return False


def annotation_db_health() -> dict:
    """Best-effort health snapshot — table row counts and schema version."""
    try:
        conn = annotation_conn()
        counts = {}
        for t in ("annotations", "annotators", "annotation_challenges",
                  "indigenous_consent"):
            try:
                counts[t] = conn.execute(f"SELECT COUNT(*) FROM {t}").fetchone()[0]
            except sqlite3.OperationalError:
                counts[t] = None
        meta = {}
        try:
            for row in conn.execute(
                "SELECT key, value FROM annotation_schema_meta"
            ):
                meta[row["key"]] = row["value"]
        except sqlite3.OperationalError:
            pass
        conn.close()
        return {
            "ok":            True,
            "db_path":       _DB_PATH,
            "row_counts":    counts,
            "schema_meta":   meta,
        }
    except Exception as exc:
        return {"ok": False, "error": str(exc), "db_path": _DB_PATH}


# Initialise on import — non-fatal so unit tests can import this module
# without a writable DB path.
try:
    init_annotation_db()
except Exception as _e:  # pragma: no cover
    logger.warning("[annotation_db] init on import failed: %s", _e)
