"""
TRION Protocol — TimescaleDB Akashic Store

Provides persistent storage and query access to the Akashic Index via TimescaleDB.
This module enables:
  - Connection management with auto-reconnect
  - Writing behavioral hashes (BH) to akashic_bh hypertable
  - Querying Akashic depth, entity history, archetype data
  - Three-tier storage: HOT (akashic_bh) → WARM (akashic_warm) → COLD (akashic_cold)
  - BEO registry operations
  - Genesis confidence and trajectory anomaly logging

Schema defined in schema.sql. Connection configured via TIMESCALEDB_URL env var.
"""

import os
import time
import logging
import threading
from typing import Dict, List, Optional, Any
from contextlib import contextmanager

logger = logging.getLogger(__name__)

try:
    import psycopg2
    from psycopg2.extras import RealDictCursor, execute_values, Json
    PSYCOPG2_OK = True
except ImportError:
    PSYCOPG2_OK = False
    logger.warning("psycopg2 not installed — TimescaleDB features disabled")


class TimescaleStore:
    """
    Connection-managed TimescaleDB store for the Akashic Index.
    
    Thread-safe connection pool of 1 (reconnect on failure).
    """

    def __init__(self, db_url: Optional[str] = None):
        self.db_url = db_url or os.environ.get(
            "TIMESCALEDB_URL",
            os.environ.get("TIMESCALE_DB_URL", "")
        )
        self._conn = None
        self._lock = threading.Lock()
        self._last_reconnect = 0
        self._reconnect_cooldown = 5  # seconds

    @property
    def available(self) -> bool:
        """Check if TimescaleDB is configured and psycopg2 is available."""
        return PSYCOPG2_OK and bool(self.db_url)

    def _connect(self) -> bool:
        """Establish a new connection. Returns True on success."""
        if not self.available:
            return False
        
        now = time.time()
        if now - self._last_reconnect < self._reconnect_cooldown:
            return False
        
        try:
            self._conn = psycopg2.connect(
                self.db_url,
                connect_timeout=10,
                application_name="trion-akashic",
            )
            self._conn.autocommit = True
            self._last_reconnect = now
            logger.info("✅ TimescaleDB connected")
            return True
        except Exception as e:
            logger.error("TimescaleDB connection failed: %s", e)
            self._last_reconnect = now
            self._conn = None
            return False

    def _get_conn(self):
        """Get a valid connection, reconnecting if needed."""
        if self._conn is None or self._conn.closed:
            with self._lock:
                if self._conn is None or self._conn.closed:
                    self._connect()
        return self._conn

    @contextmanager
    def cursor(self, cursor_factory=RealDictCursor):
        """Context manager for a database cursor."""
        conn = self._get_conn()
        if conn is None:
            raise ConnectionError("TimescaleDB not available")
        cur = conn.cursor(cursor_factory=cursor_factory)
        try:
            yield cur
        except psycopg2.InterfaceError:
            # Connection lost, try to reconnect
            self._conn = None
            conn = self._get_conn()
            if conn is None:
                raise
            cur = conn.cursor(cursor_factory=cursor_factory)
            yield cur
        finally:
            cur.close()

    def execute(self, query: str, params: tuple = ()) -> List[Dict]:
        """Execute a query and return results as list of dicts."""
        if not self.available:
            return []
        try:
            with self.cursor() as cur:
                cur.execute(query, params)
                if cur.description:
                    return [dict(row) for row in cur.fetchall()]
                return []
        except Exception as e:
            logger.error("Query failed: %s", e)
            return []

    def execute_one(self, query: str, params: tuple = ()) -> Optional[Dict]:
        """Execute a query and return the first row as dict."""
        results = self.execute(query, params)
        return results[0] if results else None

    # ── Akashic BH Operations (HOT tier) ─────────────────────────────

    def insert_bh(self, bh_data: Dict) -> bool:
        """Insert a single behavioral hash into akashic_bh hypertable."""
        if not self.available:
            return False
        try:
            with self.cursor() as cur:
                cur.execute("""
                    INSERT INTO akashic_bh (
                        time, gk_hash, prev_gk_hash, bh_id, antisense,
                        entity_id, event_type, magnitude_norm, entropy_delta,
                        chain_id, block_hash, block_num, context
                    ) VALUES (
                        %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s
                    ) ON CONFLICT (time, bh_id) DO NOTHING;
                """, (
                    bh_data.get("time") or time.strftime("%Y-%m-%dT%H:%M:%S%z"),
                    bh_data.get("gk_hash", b"\x00"),
                    bh_data.get("prev_gk_hash", b"\x00"),
                    bh_data.get("bh_id", b"\x00"),
                    bh_data.get("antisense", b"\x00"),
                    bh_data.get("entity_id", b"\x00"),
                    bh_data.get("event_type", "TRANSFER"),
                    bh_data.get("magnitude_norm", 0.0),
                    bh_data.get("entropy_delta", 0.0),
                    bh_data.get("chain_id", 1),
                    bh_data.get("block_hash", b"\x00"),
                    bh_data.get("block_num", 0),
                    Json(bh_data.get("context", {})),
                ))
                return True
        except Exception as e:
            logger.error("Insert BH failed: %s", e)
            return False

    def insert_bh_batch(self, bh_list: List[Dict]) -> int:
        """Batch insert behavioral hashes. Returns count inserted."""
        if not self.available or not bh_list:
            return 0
        try:
            with self.cursor() as cur:
                values = []
                for bh in bh_list:
                    values.append((
                        bh.get("time") or time.strftime("%Y-%m-%dT%H:%M:%S%z"),
                        bh.get("gk_hash", b"\x00"),
                        bh.get("prev_gk_hash", b"\x00"),
                        bh.get("bh_id", b"\x00"),
                        bh.get("antisense", b"\x00"),
                        bh.get("entity_id", b"\x00"),
                        bh.get("event_type", "TRANSFER"),
                        bh.get("magnitude_norm", 0.0),
                        bh.get("entropy_delta", 0.0),
                        bh.get("chain_id", 1),
                        bh.get("block_hash", b"\x00"),
                        bh.get("block_num", 0),
                        Json(bh.get("context", {})),
                    ))
                execute_values(cur, """
                    INSERT INTO akashic_bh (
                        time, gk_hash, prev_gk_hash, bh_id, antisense,
                        entity_id, event_type, magnitude_norm, entropy_delta,
                        chain_id, block_hash, block_num, context
                    ) VALUES %s ON CONFLICT (time, bh_id) DO NOTHING;
                """, values)
                return len(bh_list)
        except Exception as e:
            logger.error("Batch insert BH failed: %s", e)
            return 0

    def get_entity_bh(self, entity_id: bytes, limit: int = 100) -> List[Dict]:
        """Get recent behavioral hashes for an entity."""
        return self.execute("""
            SELECT time, encode(bh_id, 'hex') as bh_id, event_type,
                   magnitude_norm, entropy_delta, chain_id, block_num, context
            FROM akashic_bh
            WHERE entity_id = %s
            ORDER BY time DESC
            LIMIT %s;
        """, (entity_id, limit))

    # ── Akashic Vectors ──────────────────────────────────────────────

    def insert_vector(self, entity_id: str, vector: List[float],
                      magnitude: float = 0.0, entropy: float = 0.0,
                      arch_sim: float = 0.0) -> bool:
        """Insert a FAISS vector snapshot into akashic_vectors."""
        if not self.available:
            return False
        try:
            with self.cursor() as cur:
                cur.execute("""
                    INSERT INTO akashic_vectors (
                        entity_id, ts, vector, magnitude, entropy, arch_sim
                    ) VALUES (%s, now(), %s, %s, %s, %s);
                """, (entity_id, vector, magnitude, entropy, arch_sim))
                return True
        except Exception as e:
            logger.error("Insert vector failed: %s", e)
            return False

    def get_entity_vectors(self, entity_id: str, limit: int = 10) -> List[Dict]:
        """Get recent vector snapshots for an entity."""
        return self.execute("""
            SELECT ts, vector, magnitude, entropy, arch_sim
            FROM akashic_vectors
            WHERE entity_id = %s
            ORDER BY ts DESC
            LIMIT %s;
        """, (entity_id, limit))

    # ── BEO Registry ─────────────────────────────────────────────────

    def upsert_beo(self, entity_id: bytes, raw_addresses: List[str],
                   cluster_confidence: float = 1.0,
                   akashic_depth: float = 0.0) -> bool:
        """Upsert a BEO entity into the registry."""
        if not self.available:
            return False
        try:
            with self.cursor() as cur:
                cur.execute("""
                    INSERT INTO beo_registry (
                        entity_id, raw_addresses, first_seen, last_seen,
                        cluster_confidence, akashic_depth
                    ) VALUES (%s, %s, now(), now(), %s, %s)
                    ON CONFLICT (entity_id) DO UPDATE SET
                        last_seen = now(),
                        cluster_confidence = EXCLUDED.cluster_confidence,
                        akashic_depth = EXCLUDED.akashic_depth,
                        raw_addresses = array_cat(
                            beo_registry.raw_addresses, EXCLUDED.raw_addresses
                        );
                """, (entity_id, raw_addresses, cluster_confidence, akashic_depth))
                return True
        except Exception as e:
            logger.error("Upsert BEO failed: %s", e)
            return False

    def get_beo(self, entity_id: bytes) -> Optional[Dict]:
        """Get BEO registry entry."""
        return self.execute_one("""
            SELECT encode(entity_id, 'hex') as entity_id_hex,
                   raw_addresses, first_seen, last_seen,
                   cluster_confidence, akashic_depth, archetype_id
            FROM beo_registry WHERE entity_id = %s;
        """, (entity_id,))

    # ── Statistics & Aggregations ────────────────────────────────────

    def get_stats(self) -> Dict:
        """Get overall Akashic Index statistics."""
        if not self.available:
            return {"available": False}
        
        bh_count = self.execute_one("SELECT COUNT(*) as cnt FROM akashic_bh;")
        vec_count = self.execute_one("SELECT COUNT(*) as cnt FROM akashic_vectors;")
        beo_count = self.execute_one("SELECT COUNT(*) as cnt FROM beo_registry;")
        arch_count = self.execute_one("SELECT COUNT(*) as cnt FROM archetype_library;")
        
        # Time range of BH data
        time_range = self.execute_one("""
            SELECT MIN(time) as earliest, MAX(time) as latest
            FROM akashic_bh;
        """)
        
        # Chain distribution
        chain_dist = self.execute("""
            SELECT chain_id, COUNT(*) as count
            FROM akashic_bh
            GROUP BY chain_id
            ORDER BY count DESC
            LIMIT 10;
        """)
        
        # Event type distribution
        event_dist = self.execute("""
            SELECT event_type, COUNT(*) as count
            FROM akashic_bh
            GROUP BY event_type
            ORDER BY count DESC
            LIMIT 10;
        """)
        
        return {
            "available": True,
            "bh_count": bh_count["cnt"] if bh_count else 0,
            "vector_count": vec_count["cnt"] if vec_count else 0,
            "beo_count": beo_count["cnt"] if beo_count else 0,
            "archetype_count": arch_count["cnt"] if arch_count else 0,
            "earliest_bh": str(time_range["earliest"]) if time_range and time_range["earliest"] else None,
            "latest_bh": str(time_range["latest"]) if time_range and time_range["latest"] else None,
            "chain_distribution": [dict(r) for r in chain_dist],
            "event_distribution": [dict(r) for r in event_dist],
        }

    def get_akashic_depth(self, entity_id: bytes) -> Optional[Dict]:
        """Compute Akashic depth statistics for an entity."""
        return self.execute_one("""
            SELECT
                COUNT(*) as event_count,
                AVG(magnitude_norm) as avg_magnitude,
                AVG(entropy_delta) as avg_entropy_delta,
                SUM(entropy_delta) as total_entropy,
                MIN(time) as first_seen,
                MAX(time) as last_seen,
                EXTRACT(EPOCH FROM (MAX(time) - MIN(time))) as lifespan_seconds
            FROM akashic_bh
            WHERE entity_id = %s;
        """, (entity_id,))

    def get_recent_activity(self, hours: int = 24) -> List[Dict]:
        """Get recent activity across all entities."""
        return self.execute("""
            SELECT
                encode(entity_id, 'hex') as entity_id_hex,
                event_type,
                COUNT(*) as event_count,
                AVG(magnitude_norm) as avg_magnitude,
                MAX(time) as last_seen
            FROM akashic_bh
            WHERE time > NOW() - INTERVAL '%s hours'
            GROUP BY entity_id, event_type
            ORDER BY event_count DESC
            LIMIT 50;
        """, (hours,))

    # ── Genesis & Trajectory Logs ────────────────────────────────────

    def log_genesis_confidence(self, entity_id: bytes, confidence: float,
                                state: str, inactivity_days: float) -> bool:
        """Log genesis confidence assessment."""
        if not self.available:
            return False
        try:
            with self.cursor() as cur:
                cur.execute("""
                    INSERT INTO genesis_confidence_log (
                        entity_id, confidence, state, inactivity_days
                    ) VALUES (%s, %s, %s, %s);
                """, (entity_id, confidence, state, inactivity_days))
                return True
        except Exception as e:
            logger.error("Log genesis confidence failed: %s", e)
            return False

    def log_trajectory_anomaly(self, entity_id: bytes, alert: str,
                                kl_divergence: float,
                                archetype_id: Optional[int] = None,
                                genesis_locked: bool = False) -> bool:
        """Log a trajectory anomaly detection."""
        if not self.available:
            return False
        try:
            with self.cursor() as cur:
                cur.execute("""
                    INSERT INTO trajectory_anomaly_log (
                        entity_id, alert, kl_divergence, archetype_id, genesis_locked
                    ) VALUES (%s, %s, %s, %s, %s);
                """, (entity_id, alert, kl_divergence, archetype_id, genesis_locked))
                return True
        except Exception as e:
            logger.error("Log trajectory anomaly failed: %s", e)
            return False

    # ── Health Check ─────────────────────────────────────────────────

    def health_check(self) -> Dict:
        """Check TimescaleDB connection and basic health."""
        if not PSYCOPG2_OK:
            return {"status": "unavailable", "reason": "psycopg2 not installed"}
        if not self.db_url:
            return {"status": "unconfigured", "reason": "TIMESCALEDB_URL not set"}
        
        try:
            result = self.execute_one("""
                SELECT 
                    version(),
                    (SELECT extversion FROM pg_extension WHERE extname = 'timescaledb') as tsdb_version,
                    (SELECT COUNT(*) FROM akashic_bh) as bh_count,
                    (SELECT COUNT(*) FROM timescaledb_information.hypertables) as hypertable_count;
            """)
            if result:
                return {
                    "status": "healthy",
                    "postgres_version": result["version"].split(",")[0],
                    "timescaledb_version": result["tsdb_version"],
                    "bh_count": result["bh_count"],
                    "hypertable_count": result["hypertable_count"],
                }
            return {"status": "error", "reason": "no result"}
        except Exception as e:
            return {"status": "error", "reason": str(e)}


# Singleton instance
_store: Optional[TimescaleStore] = None
_store_lock = threading.Lock()


def get_timescale_store() -> Optional[TimescaleStore]:
    """Get or create the singleton TimescaleStore instance."""
    global _store
    if _store is None:
        with _store_lock:
            if _store is None:
                _store = TimescaleStore()
    return _store


def init_timescale_store(db_url: Optional[str] = None) -> TimescaleStore:
    """Initialize and return the TimescaleStore singleton."""
    global _store
    with _store_lock:
        _store = TimescaleStore(db_url)
    return _store
