#!/usr/bin/env python3
"""Initialize bh_ledger.db with the correct schema.

Schema kept in sync with core/realtime/bh_streamer.py::_init_db so the
container's pre-start init script does not create a stale table that the
streamer then has to migrate at runtime. Earlier the init script emitted
the pre-`valid` schema; the streamer would silently migrate it on first
write, but if the streamer was disabled (the default on Railway) the
table stayed stale and any operator `INSERT INTO bh_ledger ... valid ...`
from a backfill script would raise `table has no column named valid`.
"""
import sqlite3
import os

DB_PATH = os.environ.get("BH_LEDGER_DB", "/app/bh_ledger.db")

c = sqlite3.connect(DB_PATH)
c.execute("""CREATE TABLE IF NOT EXISTS bh_ledger (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    tx_hash TEXT UNIQUE,
    entity_id TEXT,
    from_addr TEXT,
    to_addr TEXT,
    event_type INTEGER,
    event_type_name TEXT,
    magnitude_norm REAL,
    value_wei TEXT,
    selector TEXT,
    sense_hex TEXT,
    antisense_hex TEXT,
    block_num INTEGER,
    block_hash TEXT,
    chain_id INTEGER,
    chain_label TEXT,
    ts REAL,
    valid INTEGER DEFAULT 1
)""")

# Schema migration: CREATE TABLE IF NOT EXISTS does NOT upgrade an existing
# table. If a pre-`valid` schema ledger exists, ALTER it to add the column.
cols = {row[1] for row in c.execute("PRAGMA table_info(bh_ledger)").fetchall()}
if "valid" not in cols:
    c.execute("ALTER TABLE bh_ledger ADD COLUMN valid INTEGER DEFAULT 1")

c.execute("CREATE INDEX IF NOT EXISTS bh_ledger_entity ON bh_ledger(entity_id)")
c.execute("CREATE INDEX IF NOT EXISTS bh_ledger_chain ON bh_ledger(chain_id)")
c.execute("CREATE INDEX IF NOT EXISTS bh_ledger_ts ON bh_ledger(ts DESC)")
c.execute("CREATE INDEX IF NOT EXISTS bh_ledger_chain_label ON bh_ledger(chain_label)")
c.commit()
c.close()
print(f"bh_ledger.db initialized at {DB_PATH} (schema=valid)")
