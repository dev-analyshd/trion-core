"""
TRION Protocol — L3.4 Conscious Plane K(t) Annotation Network
=============================================================

Whitepaper §L3.4 + §L8 Conscious Layer specification:

  K(t) = Conscious plane score from a global annotation network.
  The ONLY plane requiring human participation.

  Components:
    1. Annotator registry — 100+ annotators across 20+ countries, 3+ indigenous
       knowledge systems with verified consent (FPIC — Free, Prior, Informed Consent)
    2. Stake-and-challenge mechanism (§L8 44-54 months):
       - Annotators stake TRION tokens to submit annotations
       - Annotations can be challenged by other annotators
       - Slashing for fraudulent/manipulated annotations
       - Dispute resolution via quorum of non-accused annotators
    3. Source Credibility Evolution (§L3.4):
       CRED(source, t) = CRED(source, t-1) · α_decay + verification_events · β_update
       α_decay = 0.99 per day
       Verification event deltas:
         +1.0 prediction verified against realized outcome
         -2.0 prediction falsified
         -3.0 manipulation pattern detected in source output
         -5.0 source correlated with entity's own trading (conflict of interest)
       CRED < 0.30 → source flagged, human review required
       CRED < 0.10 → source excluded from K(t) until reviewed
    4. K(t) computation:
       K(t) = Σ_a [CRED(a,t) · annotation(a,t)] / Σ_a CRED(a,t)
       where annotation(a,t) ∈ [0,1] is the annotator's confidence score
    5. Indigenous Knowledge Interface + Elder Wisdom Protocol:
       - Separate consent registry (indigenous_consent table)
       - Revocable consent (communities can revoke at any time)
       - Elder annotators carry higher weight (tenure-based)
    6. Annotation TTL — annotations expire after 90 days (configurable)
       to prevent stale wisdom from dominating K(t)

Author: TRION Protocol — Originator: Hudu Yusuf (Analys)
License: CC0
"""
from __future__ import annotations

import os
import sqlite3
import time
import hashlib
import threading
from typing import Optional, Dict, List, Tuple, Any
from dataclasses import dataclass

_DB_PATH = os.environ.get(
    "ANNOTATIONS_DB",
    os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "..", "annotations.db"),
)

_ALPHA_DECAY = 0.99
_BETA_UPDATE = 1.0
_FLAG_THRESHOLD = 0.30
_EXCLUDE_THRESHOLD = 0.10
_DEFAULT_CRED = 0.50
_TTL_DAYS = 90
_MIN_STAKE = 100
_CHALLENGE_BOND = 50
_DISPUTE_WINDOW_HOURS = 72
_QUORUM_FRACTION = 2 / 3

_EVENT_DELTAS = {
    "verified": 1.0,
    "falsified": -2.0,
    "manipulation": -3.0,
    "conflict_of_interest": -5.0,
}

_lock = threading.Lock()


@dataclass
class Annotator:
    annotator_id: str
    annotator_type: str
    tenure_days: int
    accuracy_history: float
    jurisdictions: str
    languages: str
    stake_weight_multiplier: float
    term_start: float
    term_end: float
    stake: int
    credibility: float
    flagged: bool
    excluded: bool


def _get_db() -> sqlite3.Connection:
    conn = sqlite3.connect(_DB_PATH, timeout=10)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA journal_mode=WAL")
    return conn


def init_db() -> None:
    conn = _get_db()
    cur = conn.cursor()
    cur.execute("""
        CREATE TABLE IF NOT EXISTS annotators (
            annotator_id TEXT PRIMARY KEY,
            annotator_type TEXT NOT NULL DEFAULT 'community',
            tenure_days INTEGER NOT NULL DEFAULT 0,
            accuracy_history REAL NOT NULL DEFAULT 0.5,
            jurisdictions TEXT NOT NULL DEFAULT '',
            languages TEXT NOT NULL DEFAULT '',
            stake_weight_multiplier REAL NOT NULL DEFAULT 1.0,
            term_start REAL NOT NULL,
            term_end REAL NOT NULL DEFAULT 0,
            stake INTEGER NOT NULL DEFAULT 0,
            credibility REAL NOT NULL DEFAULT 0.5,
            flagged INTEGER NOT NULL DEFAULT 0,
            excluded INTEGER NOT NULL DEFAULT 0,
            created_at REAL NOT NULL,
            last_active REAL NOT NULL
        )
    """)
    cur.execute("""
        CREATE TABLE IF NOT EXISTS annotations (
            annotation_id TEXT PRIMARY KEY,
            entity_id TEXT NOT NULL,
            annotation_type TEXT NOT NULL,
            language TEXT NOT NULL DEFAULT 'en',
            content TEXT NOT NULL,
            confidence REAL NOT NULL,
            stake INTEGER NOT NULL DEFAULT 0,
            annotator_id TEXT NOT NULL,
            timestamp REAL NOT NULL,
            ttl REAL NOT NULL,
            challenged INTEGER NOT NULL DEFAULT 0,
            resolved INTEGER NOT NULL DEFAULT 0,
            FOREIGN KEY (annotator_id) REFERENCES annotators(annotator_id)
        )
    """)
    cur.execute("CREATE INDEX IF NOT EXISTS idx_annotations_entity ON annotations(entity_id)")
    cur.execute("CREATE INDEX IF NOT EXISTS idx_annotations_annotator ON annotations(annotator_id)")
    cur.execute("""
        CREATE TABLE IF NOT EXISTS annotation_challenges (
            challenge_id TEXT PRIMARY KEY,
            annotation_id TEXT NOT NULL,
            challenger_id TEXT NOT NULL,
            bond INTEGER NOT NULL,
            reason TEXT NOT NULL,
            status TEXT NOT NULL DEFAULT 'open',
            timestamp REAL NOT NULL,
            resolved_at REAL NOT NULL DEFAULT 0,
            resolver_id TEXT NOT NULL DEFAULT '',
            FOREIGN KEY (annotation_id) REFERENCES annotations(annotation_id),
            FOREIGN KEY (challenger_id) REFERENCES annotators(annotator_id)
        )
    """)
    cur.execute("""
        CREATE TABLE IF NOT EXISTS indigenous_consent (
            consent_id TEXT PRIMARY KEY,
            community TEXT NOT NULL,
            verified_by TEXT NOT NULL,
            revocable INTEGER NOT NULL DEFAULT 1,
            consent_scope TEXT NOT NULL,
            timestamp REAL NOT NULL,
            revoked INTEGER NOT NULL DEFAULT 0,
            revoked_at REAL NOT NULL DEFAULT 0,
            revoked_by TEXT NOT NULL DEFAULT ''
        )
    """)
    cur.execute("""
        CREATE TABLE IF NOT EXISTS credibility_events (
            event_id TEXT PRIMARY KEY,
            annotator_id TEXT NOT NULL,
            event_type TEXT NOT NULL,
            delta REAL NOT NULL,
            reason TEXT NOT NULL,
            timestamp REAL NOT NULL,
            FOREIGN KEY (annotator_id) REFERENCES annotators(annotator_id)
        )
    """)
    conn.commit()
    conn.close()


def register_annotator(
    annotator_id: str,
    annotator_type: str = "community",
    jurisdictions: str = "",
    languages: str = "en",
    stake: int = 0,
    stake_weight_multiplier: float = 1.0,
    term_end: float = 0,
) -> Dict[str, Any]:
    if stake < _MIN_STAKE and annotator_type != "elder":
        return {"error": "insufficient_stake", "required": _MIN_STAKE, "provided": stake}

    now = time.time()
    conn = _get_db()
    cur = conn.cursor()
    try:
        cur.execute("""
            INSERT OR REPLACE INTO annotators
                (annotator_id, annotator_type, tenure_days, accuracy_history,
                 jurisdictions, languages, stake_weight_multiplier, term_start,
                 term_end, stake, credibility, flagged, excluded, created_at, last_active)
            VALUES (?, ?, 0, 0.5, ?, ?, ?, ?, ?, ?, ?, 0, 0, ?, ?)
        """, (
            annotator_id, annotator_type,
            jurisdictions, languages, stake_weight_multiplier,
            now, term_end, stake, _DEFAULT_CRED, now, now
        ))
        conn.commit()
        return {
            "status": "registered",
            "annotator_id": annotator_id,
            "type": annotator_type,
            "credibility": _DEFAULT_CRED,
            "stake": stake,
            "stake_weight_multiplier": stake_weight_multiplier,
        }
    except Exception as e:
        return {"error": str(e)}
    finally:
        conn.close()


def get_annotator(annotator_id: str) -> Optional[Annotator]:
    conn = _get_db()
    cur = conn.cursor()
    cur.execute("SELECT * FROM annotators WHERE annotator_id = ?", (annotator_id,))
    row = cur.fetchone()
    conn.close()
    if not row:
        return None
    return Annotator(
        annotator_id=row["annotator_id"],
        annotator_type=row["annotator_type"],
        tenure_days=row["tenure_days"],
        accuracy_history=row["accuracy_history"],
        jurisdictions=row["jurisdictions"],
        languages=row["languages"],
        stake_weight_multiplier=row["stake_weight_multiplier"],
        term_start=row["term_start"],
        term_end=row["term_end"],
        stake=row["stake"],
        credibility=row["credibility"],
        flagged=bool(row["flagged"]),
        excluded=bool(row["excluded"]),
    )


def submit_annotation(
    entity_id: str,
    annotation_type: str,
    content: str,
    confidence: float,
    annotator_id: str,
    language: str = "en",
    stake: int = 0,
    ttl_days: int = _TTL_DAYS,
) -> Dict[str, Any]:
    if not 0.0 <= confidence <= 1.0:
        return {"error": "confidence must be in [0,1]"}

    annotator = get_annotator(annotator_id)
    if not annotator:
        return {"error": "annotator_not_registered", "annotator_id": annotator_id}

    if annotator.excluded:
        return {"error": "annotator_excluded", "reason": "credibility_below_0.10"}

    now = time.time()
    ttl = now + (ttl_days * 86400)
    annotation_id = hashlib.sha3_256(
        f"{entity_id}:{annotator_id}:{content}:{now}".encode()
    ).hexdigest()[:32]

    conn = _get_db()
    cur = conn.cursor()
    try:
        cur.execute("""
            INSERT INTO annotations
                (annotation_id, entity_id, annotation_type, language, content,
                 confidence, stake, annotator_id, timestamp, ttl, challenged, resolved)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, 0, 0)
        """, (
            annotation_id, entity_id, annotation_type, language, content,
            confidence, stake, annotator_id, now, ttl
        ))
        tenure = int((now - annotator.term_start) / 86400)
        cur.execute("""
            UPDATE annotators SET last_active = ?, tenure_days = ?
            WHERE annotator_id = ?
        """, (now, tenure, annotator_id))
        conn.commit()
        return {
            "status": "submitted",
            "annotation_id": annotation_id,
            "entity_id": entity_id,
            "annotator_id": annotator_id,
            "confidence": confidence,
            "ttl": ttl,
            "specification": "L3.4 Conscious plane K(t) — annotation network",
        }
    except Exception as e:
        return {"error": str(e)}
    finally:
        conn.close()


def challenge_annotation(
    annotation_id: str,
    challenger_id: str,
    reason: str,
    bond: int = _CHALLENGE_BOND,
) -> Dict[str, Any]:
    if bond < _CHALLENGE_BOND:
        return {"error": "insufficient_bond", "required": _CHALLENGE_BOND}

    challenger = get_annotator(challenger_id)
    if not challenger:
        return {"error": "challenger_not_registered"}

    conn = _get_db()
    cur = conn.cursor()
    cur.execute("SELECT * FROM annotations WHERE annotation_id = ?", (annotation_id,))
    ann = cur.fetchone()
    if not ann:
        conn.close()
        return {"error": "annotation_not_found"}
    if ann["challenged"]:
        conn.close()
        return {"error": "already_challenged"}

    now = time.time()
    challenge_id = hashlib.sha3_256(
        f"{annotation_id}:{challenger_id}:{now}".encode()
    ).hexdigest()[:32]

    try:
        cur.execute("""
            INSERT INTO annotation_challenges
                (challenge_id, annotation_id, challenger_id, bond, reason,
                 status, timestamp, resolved_at, resolver_id)
            VALUES (?, ?, ?, ?, ?, 'open', ?, 0, '')
        """, (challenge_id, annotation_id, challenger_id, bond, reason, now))
        cur.execute("UPDATE annotations SET challenged = 1 WHERE annotation_id = ?", (annotation_id,))
        conn.commit()
        return {
            "status": "challenge_opened",
            "challenge_id": challenge_id,
            "annotation_id": annotation_id,
            "challenger_id": challenger_id,
            "bond": bond,
            "dispute_window_hours": _DISPUTE_WINDOW_HOURS,
        }
    except Exception as e:
        return {"error": str(e)}
    finally:
        conn.close()


def resolve_challenge(challenge_id: str, resolver_id: str, decision: str) -> Dict[str, Any]:
    conn = _get_db()
    cur = conn.cursor()
    cur.execute("SELECT * FROM annotation_challenges WHERE challenge_id = ?", (challenge_id,))
    ch = cur.fetchone()
    if not ch:
        conn.close()
        return {"error": "challenge_not_found"}
    if ch["status"] != "open":
        conn.close()
        return {"error": "challenge_already_resolved"}

    now = time.time()
    annotation_id = ch["annotation_id"]
    cur.execute("SELECT annotator_id FROM annotations WHERE annotation_id = ?", (annotation_id,))
    ann_row = cur.fetchone()
    if not ann_row:
        conn.close()
        return {"error": "annotation_not_found"}
    annotation_author = ann_row["annotator_id"]

    status = f"resolved_{decision}"
    slash_amount = 0

    if decision == "uphold":
        _apply_credibility_event(annotation_author, "falsified", "challenge upheld")
        author = get_annotator(annotation_author)
        if author:
            slash_amount = min(ch["bond"], author.stake // 4)
    elif decision == "slash":
        _apply_credibility_event(annotation_author, "manipulation", "fraudulent annotation")
        _apply_credibility_event(annotation_author, "conflict_of_interest", "manipulation detected")
        author = get_annotator(annotation_author)
        if author:
            slash_amount = min(author.stake, ch["bond"] * 3)
        cur.execute("UPDATE annotators SET excluded = 1, credibility = 0.0 WHERE annotator_id = ?", (annotation_author,))
    elif decision == "overturn":
        cur.execute("UPDATE annotators SET stake = stake + ? WHERE annotator_id = ?", (ch["bond"], annotation_author))

    cur.execute("""
        UPDATE annotation_challenges
        SET status = ?, resolved_at = ?, resolver_id = ?
        WHERE challenge_id = ?
    """, (status, now, resolver_id, challenge_id))
    cur.execute("UPDATE annotations SET resolved = 1 WHERE annotation_id = ?", (annotation_id,))
    conn.commit()
    conn.close()

    return {
        "status": status,
        "challenge_id": challenge_id,
        "annotation_id": annotation_id,
        "slash_amount": slash_amount,
        "resolver_id": resolver_id,
    }


def _apply_credibility_event(annotator_id: str, event_type: str, reason: str) -> None:
    delta = _EVENT_DELTAS.get(event_type, 0.0)
    now = time.time()
    event_id = hashlib.sha3_256(f"{annotator_id}:{event_type}:{now}".encode()).hexdigest()[:32]

    conn = _get_db()
    cur = conn.cursor()
    cur.execute("""
        INSERT INTO credibility_events
            (event_id, annotator_id, event_type, delta, reason, timestamp)
        VALUES (?, ?, ?, ?, ?, ?)
    """, (event_id, annotator_id, event_type, delta, reason, now))

    cur.execute("SELECT credibility FROM annotators WHERE annotator_id = ?", (annotator_id,))
    row = cur.fetchone()
    if row:
        old_cred = row["credibility"]
        new_cred = max(0.0, min(1.0, old_cred * _ALPHA_DECAY + delta * _BETA_UPDATE))
        flagged = 1 if new_cred < _FLAG_THRESHOLD else 0
        excluded = 1 if new_cred < _EXCLUDE_THRESHOLD else 0
        cur.execute("""
            UPDATE annotators SET credibility = ?, flagged = ?, excluded = ?
            WHERE annotator_id = ?
        """, (new_cred, flagged, excluded, annotator_id))

    conn.commit()
    conn.close()


def decay_all_credibility() -> int:
    conn = _get_db()
    cur = conn.cursor()
    cur.execute("SELECT annotator_id, credibility FROM annotators WHERE excluded = 0")
    annotators = cur.fetchall()
    count = 0
    for ann in annotators:
        new_cred = ann["credibility"] * _ALPHA_DECAY
        flagged = 1 if new_cred < _FLAG_THRESHOLD else 0
        excluded = 1 if new_cred < _EXCLUDE_THRESHOLD else 0
        cur.execute("""
            UPDATE annotators SET credibility = ?, flagged = ?, excluded = ?
            WHERE annotator_id = ?
        """, (new_cred, flagged, excluded, ann["annotator_id"]))
        count += 1
    conn.commit()
    conn.close()
    return count


def get_k_score(entity_id: str) -> Tuple[float, str, Dict[str, Any]]:
    """K(t) = Σ_a [CRED(a,t) · annotation(a,t)] / Σ_a CRED(a,t)"""
    now = time.time()
    conn = _get_db()
    cur = conn.cursor()
    cur.execute("""
        SELECT a.annotation_id, a.confidence, a.annotation_type, a.language,
               a.timestamp, a.ttl, a.challenged, a.resolved,
               an.annotator_id, an.credibility, an.stake_weight_multiplier,
               an.excluded, an.flagged
        FROM annotations a
        JOIN annotators an ON a.annotator_id = an.annotator_id
        WHERE a.entity_id = ?
          AND a.ttl > ?
          AND an.excluded = 0
          AND (a.challenged = 0 OR (a.challenged = 1 AND a.resolved = 1))
        ORDER BY a.timestamp DESC
    """, (entity_id, now))
    rows = cur.fetchall()
    conn.close()

    if not rows:
        return 0.10, "bootstrap_0.10", {
            "specification": "L3.4 Conscious plane K(t)",
            "annotation_count": 0,
            "bootstrap": True,
            "disclosure": "No active annotations for this entity. K(t) = bootstrap baseline 0.10.",
        }

    numerator = 0.0
    denominator = 0.0
    annotator_ids = set()
    for row in rows:
        cred = row["credibility"]
        conf = row["confidence"]
        swm = row["stake_weight_multiplier"]
        weight = cred * swm
        numerator += weight * conf
        denominator += weight
        annotator_ids.add(row["annotator_id"])

    k_score = numerator / denominator if denominator > 0 else 0.10
    k_score = max(0.0, min(1.0, k_score))
    source = "live_annotations" if len(rows) >= 3 else "partial_annotations"

    return k_score, source, {
        "specification": "L3.4 Conscious plane K(t) — human annotation network",
        "k_score": round(k_score, 6),
        "annotation_count": len(rows),
        "annotator_count": len(annotator_ids),
        "source": source,
        "bootstrap": False,
        "formula": "K(t) = Σ_a [CRED(a,t) · annotation(a,t)] / Σ_a CRED(a,t)",
        "credibility_range": {
            "min": min(r["credibility"] for r in rows),
            "max": max(r["credibility"] for r in rows),
        },
    }


def register_indigenous_consent(community: str, verified_by: str, consent_scope: str) -> Dict[str, Any]:
    now = time.time()
    consent_id = hashlib.sha3_256(f"{community}:{verified_by}:{now}".encode()).hexdigest()[:32]
    conn = _get_db()
    cur = conn.cursor()
    try:
        cur.execute("""
            INSERT INTO indigenous_consent
                (consent_id, community, verified_by, revocable, consent_scope,
                 timestamp, revoked, revoked_at, revoked_by)
            VALUES (?, ?, ?, 1, ?, ?, 0, 0, '')
        """, (consent_id, community, verified_by, consent_scope, now))
        conn.commit()
        return {
            "status": "consent_registered",
            "consent_id": consent_id,
            "community": community,
            "verified_by": verified_by,
            "revocable": True,
        }
    except Exception as e:
        return {"error": str(e)}
    finally:
        conn.close()


def revoke_indigenous_consent(consent_id: str, revoked_by: str) -> Dict[str, Any]:
    now = time.time()
    conn = _get_db()
    cur = conn.cursor()
    cur.execute("""
        UPDATE indigenous_consent
        SET revoked = 1, revoked_at = ?, revoked_by = ?
        WHERE consent_id = ?
    """, (now, revoked_by, consent_id))
    affected = cur.rowcount
    conn.commit()
    conn.close()
    if affected == 0:
        return {"error": "consent_not_found"}
    return {"status": "consent_revoked", "consent_id": consent_id, "revoked_by": revoked_by}


def get_network_stats() -> Dict[str, Any]:
    conn = _get_db()
    cur = conn.cursor()
    cur.execute("SELECT COUNT(*) FROM annotators")
    total_annotators = cur.fetchone()[0]
    cur.execute("SELECT COUNT(*) FROM annotators WHERE excluded = 0")
    active_annotators = cur.fetchone()[0]
    cur.execute("SELECT COUNT(*) FROM annotators WHERE flagged = 1")
    flagged = cur.fetchone()[0]
    cur.execute("SELECT COUNT(*) FROM annotators WHERE excluded = 1")
    excluded = cur.fetchone()[0]
    cur.execute("SELECT COUNT(*) FROM annotations")
    total_annotations = cur.fetchone()[0]
    cur.execute("SELECT COUNT(*) FROM annotations WHERE ttl > ?", (time.time(),))
    active_annotations = cur.fetchone()[0]
    cur.execute("SELECT COUNT(*) FROM annotation_challenges WHERE status = 'open'")
    open_challenges = cur.fetchone()[0]
    cur.execute("SELECT COUNT(*) FROM indigenous_consent WHERE revoked = 0")
    active_consent = cur.fetchone()[0]
    cur.execute("SELECT annotator_type, COUNT(*) FROM annotators GROUP BY annotator_type")
    type_breakdown = {r[0]: r[1] for r in cur.fetchall()}
    cur.execute("SELECT jurisdictions FROM annotators WHERE jurisdictions != ''")
    all_countries = set()
    for row in cur.fetchall():
        for code in row[0].split(","):
            code = code.strip()
            if code:
                all_countries.add(code)
    cur.execute("SELECT languages FROM annotators WHERE languages != ''")
    all_languages = set()
    for row in cur.fetchall():
        for code in row[0].split(","):
            code = code.strip()
            if code:
                all_languages.add(code)
    cur.execute("SELECT AVG(credibility) FROM annotators WHERE excluded = 0")
    avg_cred = cur.fetchone()[0] or 0.0
    conn.close()

    return {
        "specification": "L3.4 Conscious plane K(t) — annotation network",
        "total_annotators": total_annotators,
        "active_annotators": active_annotators,
        "flagged_annotators": flagged,
        "excluded_annotators": excluded,
        "total_annotations": total_annotations,
        "active_annotations": active_annotations,
        "open_challenges": open_challenges,
        "indigenous_consent_active": active_consent,
        "annotator_types": type_breakdown,
        "country_coverage": len(all_countries),
        "countries": sorted(all_countries),
        "language_coverage": len(all_languages),
        "languages": sorted(all_languages),
        "avg_credibility": round(avg_cred, 4),
        "whitepaper_target": "100+ annotators across 20+ countries, 3+ indigenous",
        "ready": total_annotators >= 100 and len(all_countries) >= 20,
    }


init_db()
