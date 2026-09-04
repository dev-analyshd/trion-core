"""core/akashic/beo_lookup.py — read-only BEO ledger binding (W3-D, INV-016).

The Akashic BEO ledger (produced by the ANIMA/FAISS service plane,
``anima-service/faiss_service.py``) persists:

    beo_clusters  (address → canonical BEO id)          — address resolution
    entity_meta   (beo_id → last_active, archetype_id)  — BEO state
    entity_records(beo_id, ts, magnitude, entropy, arch_sim, vector)
                                                          — behavioral record

This module gives core-side consumers (the BTCP privacy router's witness
provenance, W2-F's INV-016 handoff) a READ-ONLY lookup so a witness can be
BOUND to the Akashic BEO ledger: the entity claiming a behavioral
credential is verified to be a BEO the Akashic Index actually tracks, and
the binding records the ledger's own facts (last active, record count,
entropy, archetype). Scores remain caller-supplied claims — the binding is
identity-level (entity known to the ledger), never a fabricated
score-level attestation.

HONEST LIMITATION: the ledger DB is written by the ANIMA service (SQLite,
WAL). In sandboxes without a live ledger the lookup returns ``None`` and
callers keep the unbound label — never a synthetic binding.

Author: TRION Protocol — Wave 3 Agent D
License: CC0
"""

from __future__ import annotations

import os
import sqlite3
from typing import Optional


def resolve_beo_db_path(db_path: Optional[str] = None) -> Optional[str]:
    """Resolve the Akashic BEO ledger DB path (read-only resolution).

    Order: explicit ``db_path`` → env ``TRION_BEO_DB`` → env
    ``FAISS_STATE_DB`` → ``akashic_state.db`` / ``akashic/akashic_state.db``
    (mirrors anima-service/faiss_service.py's STATE_DB_PATH resolution).
    Returns None when no candidate file exists (no ledger → unbound).
    """
    if db_path:
        return db_path if os.path.exists(db_path) else None
    candidates = []
    env = os.environ.get("TRION_BEO_DB")
    if env:
        candidates.append(env)
    env_faiss = os.environ.get("FAISS_STATE_DB")
    if env_faiss:
        candidates.append(env_faiss)
        candidates.append(os.path.join(os.path.dirname(env_faiss) or ".", "akashic_state.db"))
    candidates.extend(["akashic_state.db", "akashic/akashic_state.db"])
    for c in candidates:
        if c and os.path.exists(c):
            return c
    return None


def lookup_beo_binding(
    address_or_beo_id: str,
    db_path: Optional[str] = None,
) -> Optional[dict]:
    """Bind an address / BEO id to the Akashic BEO ledger (read-only).

    Lookup order:
      1. ``beo_clusters`` by lowercased address → canonical BEO id.
      2. ``entity_meta`` / ``entity_records`` by the canonical id (or the
         input itself when it is already a BEO id).

    Returns None when the ledger is absent or the entity is unknown
    (unbound — the caller must keep the self-attested label). Never raises
    on lookup failure: an unreadable ledger is "unbound", not an error the
    proof path should crash on.
    """
    if not address_or_beo_id:
        return None
    path = resolve_beo_db_path(db_path)
    if not path:
        return None

    key = str(address_or_beo_id).lower()
    try:
        conn = sqlite3.connect(f"file:{path}?mode=ro", uri=True, timeout=10.0)
    except sqlite3.Error:
        return None
    try:
        beo_id: Optional[str] = None
        try:
            row = conn.execute(
                "SELECT canonical FROM beo_clusters WHERE address = ?", (key,)
            ).fetchone()
            if row and row[0]:
                beo_id = str(row[0])
        except sqlite3.Error:
            beo_id = None  # table absent in older ledgers

        if beo_id is None:
            # The input may itself be a BEO id (entity_records is keyed by it).
            probe = conn.execute(
                "SELECT 1 FROM entity_meta WHERE beo_id = ? LIMIT 1",
                (str(address_or_beo_id),),
            ).fetchone()
            if probe:
                beo_id = str(address_or_beo_id)
        if beo_id is None:
            return None  # entity unknown to the Akashic BEO ledger

        meta = conn.execute(
            "SELECT last_active, archetype_id FROM entity_meta WHERE beo_id = ?",
            (beo_id,),
        ).fetchone()
        rec = conn.execute(
            "SELECT ts, magnitude, entropy, arch_sim FROM entity_records "
            "WHERE beo_id = ? ORDER BY ts DESC LIMIT 1",
            (beo_id,),
        ).fetchone()
        count = conn.execute(
            "SELECT COUNT(*) FROM entity_records WHERE beo_id = ?", (beo_id,)
        ).fetchone()

        return {
            "beo_id":        beo_id,
            "address":       str(address_or_beo_id),
            "last_active":   (float(meta[0]) if meta and meta[0] is not None else None),
            "archetype_id":  (int(meta[1]) if meta and meta[1] is not None else None),
            "ledger_records": int(count[0]) if count else 0,
            "latest_record": (
                {
                    "ts":        float(rec[0]),
                    "magnitude": float(rec[1]) if rec[1] is not None else None,
                    "entropy":   float(rec[2]) if rec[2] is not None else None,
                    "arch_sim":  float(rec[3]) if rec[3] is not None else None,
                }
                if rec else None
            ),
            "ledger_db":     path,
        }
    except sqlite3.Error:
        return None
    finally:
        try:
            conn.close()
        except sqlite3.Error:
            pass


if __name__ == "__main__":
    import json
    import tempfile

    # Self-test against a synthetic in-memory ledger file.
    tmp = tempfile.mktemp(suffix=".db")
    conn = sqlite3.connect(tmp)
    conn.executescript("""
        CREATE TABLE beo_clusters (address TEXT PRIMARY KEY, canonical TEXT, funding TEXT);
        CREATE TABLE entity_meta (beo_id TEXT PRIMARY KEY, last_active REAL, archetype_id INTEGER);
        CREATE TABLE entity_records (beo_id TEXT, ts REAL, magnitude REAL, entropy REAL, arch_sim REAL, vector BLOB, PRIMARY KEY (beo_id, ts));
        INSERT INTO beo_clusters VALUES ('0xabc', 'beo_001', '0xfund');
        INSERT INTO entity_meta VALUES ('beo_001', 1700000000.0, 7);
        INSERT INTO entity_records VALUES ('beo_001', 1700000100.0, 12.5, 0.71, 0.83, NULL);
    """)
    conn.commit()
    conn.close()

    bound = lookup_beo_binding("0xABC", db_path=tmp)
    assert bound and bound["beo_id"] == "beo_001", bound
    assert bound["ledger_records"] == 1 and bound["latest_record"]["entropy"] == 0.71
    print("bound:", json.dumps({k: v for k, v in bound.items() if k != "latest_record"}))

    unbound = lookup_beo_binding("0xunknown", db_path=tmp)
    assert unbound is None
    no_db = lookup_beo_binding("0xabc", db_path="/nonexistent/ledger.db")
    assert no_db is None
    print("unbound / no-ledger: OK (None, honest)")
    os.unlink(tmp)
    print("beo_lookup: PASS")
