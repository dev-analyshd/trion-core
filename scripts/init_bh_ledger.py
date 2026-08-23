#!/usr/bin/env python3
"""Initialize bh_ledger.db with the correct schema."""
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
    ts REAL
)""")
c.execute("CREATE INDEX IF NOT EXISTS bh_ledger_entity ON bh_ledger(entity_id)")
c.execute("CREATE INDEX IF NOT EXISTS bh_ledger_chain ON bh_ledger(chain_id)")
c.execute("CREATE INDEX IF NOT EXISTS bh_ledger_ts ON bh_ledger(ts DESC)")
c.commit()
c.close()
print(f"bh_ledger.db initialized at {DB_PATH}")
