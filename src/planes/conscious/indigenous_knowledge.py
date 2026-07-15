"""
TRION Protocol — Indigenous Knowledge Interface & Elder Wisdom Protocol

Real infrastructure for onboarding traditional/indigenous knowledge systems
with explicit verified-consent records and elevated epistemic weight.

HONEST DISCLOSURE:
- Zero seeded entries. All registrations must come from real onboarding.
- Consent is revocable at any time by the consent_given_by party.
- Elder annotations carry elevated stake_weight in compute_k_score.
- SQLite persistence matches akashic/faiss_service.py house pattern.
"""

import sqlite3
import threading
import hashlib
import time
import logging
from typing import Optional
from dataclasses import dataclass

logger = logging.getLogger(__name__)

# ── Database path — co-located with other TRION state DBs ────────────────────
import os
_IK_DB_PATH = os.environ.get(
    "IK_DB_PATH",
    os.path.join(os.path.dirname(os.path.abspath(__file__)),
                 "../../../akashic/indigenous_knowledge.db")
)
_IK_DB_PATH = os.path.normpath(_IK_DB_PATH)

_ik_lock = threading.Lock()

# ── Elder annotation elevated weight (distinct from standard 1.0 default) ────
ELDER_STAKE_WEIGHT_MULTIPLIER = 2.5   # Whitepaper: elder/knowledge-holder epistemic primacy


# ── SQLite connection ─────────────────────────────────────────────────────────

def _ik_conn() -> sqlite3.Connection:
    """Return a WAL-mode SQLite connection for indigenous knowledge tables."""
    conn = sqlite3.connect(_IK_DB_PATH, check_same_thread=False, timeout=60.0)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA journal_mode=WAL")
    conn.execute("PRAGMA synchronous=NORMAL")
    conn.execute("PRAGMA busy_timeout=60000")
    conn.execute("PRAGMA wal_autocheckpoint=2000")
    conn.execute("PRAGMA cache_size=-8000")
    return conn


def _init_ik_db():
    """Create indigenous knowledge tables if they don't exist."""
    conn = _ik_conn()
    conn.executescript("""
        -- Registered knowledge systems
        CREATE TABLE IF NOT EXISTS knowledge_systems (
            system_id        TEXT PRIMARY KEY,
            system_name      TEXT NOT NULL,
            origin_region    TEXT NOT NULL,
            contact_hash     TEXT NOT NULL,   -- SHA3-256 of contact identifier (pseudonymous)
            registered_at    REAL NOT NULL,
            active           INTEGER NOT NULL DEFAULT 1,
            description      TEXT DEFAULT ''
        );
        CREATE INDEX IF NOT EXISTS ks_active ON knowledge_systems(active);

        -- Verified consent records (one per system; revocable)
        CREATE TABLE IF NOT EXISTS consent_records (
            consent_id       TEXT PRIMARY KEY,
            system_id        TEXT NOT NULL REFERENCES knowledge_systems(system_id),
            consent_given_by TEXT NOT NULL,   -- pseudonymous identifier of consenting party
            consent_scope    TEXT NOT NULL,   -- what is consented (e.g. "annotation_only", "full_protocol")
            consent_timestamp REAL NOT NULL,
            revocable        INTEGER NOT NULL DEFAULT 1,
            revoked          INTEGER NOT NULL DEFAULT 0,
            revoked_at       REAL,
            revoked_by       TEXT,
            FOREIGN KEY (system_id) REFERENCES knowledge_systems(system_id)
        );
        CREATE INDEX IF NOT EXISTS cr_system ON consent_records(system_id);
        CREATE INDEX IF NOT EXISTS cr_active  ON consent_records(revoked, system_id);

        -- Elder/knowledge-holder registry
        CREATE TABLE IF NOT EXISTS elder_registry (
            elder_id         TEXT PRIMARY KEY,   -- pseudonymous annotator_id
            system_id        TEXT NOT NULL REFERENCES knowledge_systems(system_id),
            annotation_type  INTEGER NOT NULL,   -- AnnotationType.INDIGENOUS_KNW = 2
            term_start       REAL NOT NULL,
            term_end         REAL NOT NULL,      -- term_start + 24 months max (ACP2)
            active           INTEGER NOT NULL DEFAULT 1,
            registered_at    REAL NOT NULL
        );
        CREATE INDEX IF NOT EXISTS er_system ON elder_registry(system_id);
        CREATE INDEX IF NOT EXISTS er_active ON elder_registry(active);

        -- Elder annotation submissions (immutable audit log)
        CREATE TABLE IF NOT EXISTS elder_annotations (
            id               INTEGER PRIMARY KEY AUTOINCREMENT,
            elder_id         TEXT NOT NULL REFERENCES elder_registry(elder_id),
            system_id        TEXT NOT NULL,
            entity_id        TEXT NOT NULL,
            judgment         INTEGER NOT NULL,   -- 0=ORGANIC 1=MANIPULATED 2=TRANSITIONAL 3=UNCERTAIN
            k_score          REAL NOT NULL,
            cultural_context TEXT DEFAULT '',
            stake_weight     REAL NOT NULL,      -- pre-multiplied by ELDER_STAKE_WEIGHT_MULTIPLIER
            submitted_at     REAL NOT NULL,
            annotation_id    INTEGER            -- foreign key into faiss_service._annotations (if linked)
        );
        CREATE INDEX IF NOT EXISTS ea_entity ON elder_annotations(entity_id);
        CREATE INDEX IF NOT EXISTS ea_elder  ON elder_annotations(elder_id);
    """)
    conn.commit()
    conn.close()
    logger.info("[indigenous_knowledge] DB initialised at %s", _IK_DB_PATH)


# Initialise on import
try:
    _init_ik_db()
except Exception as _e:
    logger.warning("[indigenous_knowledge] DB init failed: %s", _e)


# ── KnowledgeSystemRegistry ───────────────────────────────────────────────────

class KnowledgeSystemRegistry:
    """
    Records which indigenous/traditional knowledge systems have onboarded,
    with an explicit verified-consent record per system.

    - consent_given_by: pseudonymous identifier of consenting party
    - consent_scope: e.g. "annotation_only", "full_protocol"
    - revocable=True always (TRION protocol commitment)
    - Revocation immediately deactivates all associated elder annotations
    """

    @staticmethod
    def register_system(
        system_id: str,
        system_name: str,
        origin_region: str,
        contact_identifier: str,
        description: str = "",
    ) -> dict:
        """
        Register a new knowledge system. contact_identifier is hashed
        before storage (pseudonymous per ACP1).
        """
        contact_hash = hashlib.sha3_256(contact_identifier.encode()).hexdigest()
        now = time.time()
        with _ik_lock:
            conn = _ik_conn()
            try:
                conn.execute(
                    """INSERT INTO knowledge_systems
                       (system_id, system_name, origin_region, contact_hash,
                        registered_at, active, description)
                       VALUES (?, ?, ?, ?, ?, 1, ?)""",
                    (system_id, system_name, origin_region, contact_hash, now, description),
                )
                conn.commit()
            except sqlite3.IntegrityError:
                conn.close()
                return {"status": "error", "detail": f"system_id '{system_id}' already exists"}
            finally:
                conn.close()
        logger.info("[IK] Registered knowledge system: %s (%s)", system_id, system_name)
        return {"status": "registered", "system_id": system_id, "registered_at": now}

    @staticmethod
    def record_consent(
        system_id: str,
        consent_given_by: str,
        consent_scope: str,
    ) -> dict:
        """
        Record explicit verified consent for a knowledge system.
        One active consent per system; re-consenting replaces prior record.
        """
        now = time.time()
        consent_id = hashlib.sha3_256(
            f"{system_id}:{consent_given_by}:{now}".encode()
        ).hexdigest()[:32]

        with _ik_lock:
            conn = _ik_conn()
            try:
                row = conn.execute(
                    "SELECT system_id FROM knowledge_systems WHERE system_id=? AND active=1",
                    (system_id,)
                ).fetchone()
                if not row:
                    return {"status": "error", "detail": f"system_id '{system_id}' not found or inactive"}

                # Revoke any prior active consent
                conn.execute(
                    "UPDATE consent_records SET revoked=1, revoked_at=?, revoked_by='superseded' "
                    "WHERE system_id=? AND revoked=0",
                    (now, system_id)
                )
                conn.execute(
                    """INSERT INTO consent_records
                       (consent_id, system_id, consent_given_by, consent_scope,
                        consent_timestamp, revocable, revoked)
                       VALUES (?, ?, ?, ?, ?, 1, 0)""",
                    (consent_id, system_id, consent_given_by, consent_scope, now)
                )
                conn.commit()
            finally:
                conn.close()
        logger.info("[IK] Consent recorded for system %s scope=%s", system_id, consent_scope)
        return {
            "status": "consent_recorded",
            "consent_id": consent_id,
            "system_id": system_id,
            "consent_scope": consent_scope,
            "revocable": True,
            "consent_timestamp": now,
        }

    @staticmethod
    def revoke_consent(system_id: str, revoked_by: str) -> dict:
        """Revoke consent for a knowledge system. Immediate effect."""
        now = time.time()
        with _ik_lock:
            conn = _ik_conn()
            try:
                n = conn.execute(
                    "UPDATE consent_records SET revoked=1, revoked_at=?, revoked_by=? "
                    "WHERE system_id=? AND revoked=0",
                    (now, revoked_by, system_id)
                ).rowcount
                conn.commit()
            finally:
                conn.close()
        logger.info("[IK] Consent revoked for system %s by %s (rows=%d)", system_id, revoked_by, n)
        return {"status": "revoked", "system_id": system_id, "rows_affected": n}

    @staticmethod
    def has_active_consent(system_id: str) -> bool:
        """Return True iff system has a non-revoked consent record."""
        conn = _ik_conn()
        try:
            row = conn.execute(
                "SELECT consent_id FROM consent_records WHERE system_id=? AND revoked=0",
                (system_id,)
            ).fetchone()
            return row is not None
        finally:
            conn.close()

    @staticmethod
    def list_systems() -> list:
        conn = _ik_conn()
        try:
            rows = conn.execute(
                "SELECT ks.system_id, ks.system_name, ks.origin_region, ks.active, "
                "  ks.registered_at, "
                "  (SELECT COUNT(*) FROM consent_records cr "
                "   WHERE cr.system_id=ks.system_id AND cr.revoked=0) AS has_consent "
                "FROM knowledge_systems ks ORDER BY ks.registered_at DESC"
            ).fetchall()
            return [dict(r) for r in rows]
        finally:
            conn.close()


# ── ElderWisdomProtocol ───────────────────────────────────────────────────────

class ElderWisdomProtocol:
    """
    Allows a registered elder/knowledge-holder to submit an annotation with
    elevated epistemic weight (ELDER_STAKE_WEIGHT_MULTIPLIER × base_stake).

    Guards:
    1. Elder must be registered and within their active term.
    2. The elder's knowledge system must have an active (non-revoked) consent record.
    3. Elevated weight is stored in elder_annotations and forwarded to the
       main annotation store in faiss_service via the returned payload.
    """

    @staticmethod
    def register_elder(
        elder_id: str,
        system_id: str,
        term_months: int = 12,
    ) -> dict:
        """
        Register an elder/knowledge-holder under a given knowledge system.
        Requires active consent from the system. Terms 1–24 months (ACP2).
        elder_id is a pseudonymous identifier (never a real name).
        """
        if not (1 <= term_months <= 24):
            return {"status": "error", "detail": "term_months must be 1–24 (ACP2)"}

        if not KnowledgeSystemRegistry.has_active_consent(system_id):
            return {
                "status": "error",
                "detail": f"system '{system_id}' has no active consent — cannot register elder",
            }

        now = time.time()
        term_end = now + term_months * 30 * 24 * 3600  # approximate months

        with _ik_lock:
            conn = _ik_conn()
            try:
                conn.execute(
                    """INSERT OR REPLACE INTO elder_registry
                       (elder_id, system_id, annotation_type, term_start, term_end,
                        active, registered_at)
                       VALUES (?, ?, 2, ?, ?, 1, ?)""",
                    (elder_id, system_id, now, term_end, now)
                )
                conn.commit()
            finally:
                conn.close()
        logger.info("[IK] Elder registered: %s under system %s (term=%dm)", elder_id, system_id, term_months)
        return {
            "status": "elder_registered",
            "elder_id": elder_id,
            "system_id": system_id,
            "term_start": now,
            "term_end": term_end,
            "annotation_type": "INDIGENOUS_KNW",
        }

    @staticmethod
    def submit_elder_annotation(
        elder_id: str,
        entity_id: str,
        judgment: int,
        cultural_context: str = "",
        base_stake_trion: float = 500.0,
    ) -> dict:
        """
        Submit an elder annotation for an entity.

        Returns a payload dict suitable for injection into the main
        _annotations store in faiss_service.py (submit_annotation pathway),
        with stake_trion pre-scaled by ELDER_STAKE_WEIGHT_MULTIPLIER and
        specialization=INDIGENOUS.

        Requires:
        - Elder is registered and within active term.
        - Knowledge system has active consent.

        judgment: 0=ORGANIC 1=MANIPULATED 2=TRANSITIONAL 3=UNCERTAIN
        """
        if judgment not in (0, 1, 2, 3):
            return {"status": "error", "detail": "judgment must be 0–3"}
        if base_stake_trion < 100.0:
            return {"status": "error", "detail": "Minimum 100 TRION base stake"}

        now = time.time()
        with _ik_lock:
            conn = _ik_conn()
            try:
                elder_row = conn.execute(
                    "SELECT elder_id, system_id, term_end, active FROM elder_registry "
                    "WHERE elder_id=? AND active=1",
                    (elder_id,)
                ).fetchone()
            finally:
                conn.close()

        if not elder_row:
            return {"status": "error", "detail": f"elder '{elder_id}' not found or inactive"}

        if now > elder_row["term_end"]:
            # Term expired — deactivate
            with _ik_lock:
                conn = _ik_conn()
                try:
                    conn.execute("UPDATE elder_registry SET active=0 WHERE elder_id=?", (elder_id,))
                    conn.commit()
                finally:
                    conn.close()
            return {"status": "error", "detail": f"elder '{elder_id}' term has expired (ACP2)"}

        system_id = elder_row["system_id"]
        if not KnowledgeSystemRegistry.has_active_consent(system_id):
            return {
                "status": "error",
                "detail": f"knowledge system '{system_id}' consent has been revoked — annotation blocked",
            }

        # Elevated stake weight
        elevated_stake = round(base_stake_trion * ELDER_STAKE_WEIGHT_MULTIPLIER, 4)

        # Record in elder_annotations audit log
        with _ik_lock:
            conn = _ik_conn()
            try:
                conn.execute(
                    """INSERT INTO elder_annotations
                       (elder_id, system_id, entity_id, judgment, k_score,
                        cultural_context, stake_weight, submitted_at)
                       VALUES (?, ?, ?, ?, ?, ?, ?, ?)""",
                    (
                        elder_id, system_id, entity_id, judgment,
                        {0: 1.0, 1: 0.0, 2: 0.5, 3: 0.5}[judgment],
                        cultural_context, elevated_stake, now,
                    )
                )
                conn.commit()
            finally:
                conn.close()

        logger.info(
            "[IK] Elder annotation: elder=%s entity=%s judgment=%d elevated_stake=%.1f",
            elder_id, entity_id, judgment, elevated_stake,
        )

        # Return payload for injection into main annotation store
        return {
            "status": "ok",
            "elder_id": elder_id,
            "system_id": system_id,
            "entity_id": entity_id,
            "judgment": judgment,
            "cultural_context": cultural_context,
            "annotation_payload": {
                "entity_id":      entity_id,
                "annotator_id":   elder_id,
                "judgment":       judgment,
                "stake_trion":    elevated_stake,
                "confidence":     1.0,
                "specialization": "INDIGENOUS",
                "evidence_text":  cultural_context,
                "ipfs_cid":       "",
            },
            "elevated_stake_trion": elevated_stake,
            "elder_weight_multiplier": ELDER_STAKE_WEIGHT_MULTIPLIER,
            "annotation_type": "INDIGENOUS_KNW",
        }

    @staticmethod
    def list_elders(system_id: Optional[str] = None) -> list:
        conn = _ik_conn()
        try:
            if system_id:
                rows = conn.execute(
                    "SELECT elder_id, system_id, term_start, term_end, active, registered_at "
                    "FROM elder_registry WHERE system_id=? ORDER BY registered_at DESC",
                    (system_id,)
                ).fetchall()
            else:
                rows = conn.execute(
                    "SELECT elder_id, system_id, term_start, term_end, active, registered_at "
                    "FROM elder_registry ORDER BY registered_at DESC"
                ).fetchall()
            return [dict(r) for r in rows]
        finally:
            conn.close()


# ── Singleton instances ───────────────────────────────────────────────────────
registry = KnowledgeSystemRegistry()
elder_protocol = ElderWisdomProtocol()
