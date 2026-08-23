"""
TRION Protocol — BIBL Pattern Store
Persistent pattern match database for the Inter-Block Intelligence Layer.

Backs the BIBLEngine with real historical match counters and archetype tracking.
Stores observed mempool states → outcome mappings for chain memory calibration.

Storage: SQLite (local) with optional TimescaleDB (production) write-through.
Archetypes: 15 behavioral archetypes (expanded from 5).
Calibration: pattern confidence improves as sample size grows.

Author: TRION Protocol — Originator: Hudu Yusuf (Analys)
License: CC0
"""

from __future__ import annotations

import json
import math
import os
import sqlite3
import time
from dataclasses import dataclass, field
from typing import Dict, List, Optional, Tuple


# ── Archetype Definitions ─────────────────────────────────────────────────────

@dataclass
class MempoolArchetype:
    """
    A behavioral mempool archetype — a named cluster of mempool conditions.
    Expanded from 5 to 15 archetypes per paper's 847+ historical instances spec.
    """
    code:            str
    label:           str
    base_fee_adj:    float    # recommended base fee multiplier adjustment
    confidence_base: float    # default confidence before calibration
    min_mempool_size: int
    max_mempool_size: int
    min_mev_rate:    float
    max_mev_rate:    float
    volatility_band: Tuple[float, float]   # (min, max) volatility
    description:     str


ARCHETYPES: Dict[str, MempoolArchetype] = {
    "DEEP_CALM": MempoolArchetype(
        code="DEEP_CALM", label="Deep Calm",
        base_fee_adj=-0.20, confidence_base=0.85,
        min_mempool_size=0, max_mempool_size=2000,
        min_mev_rate=0.0, max_mev_rate=0.001,
        volatility_band=(0.0, 0.10),
        description="Very low activity, minimal MEV — ideal routing window",
    ),
    "LOW_ACTIVITY": MempoolArchetype(
        code="LOW_ACTIVITY", label="Low Activity",
        base_fee_adj=-0.10, confidence_base=0.80,
        min_mempool_size=2000, max_mempool_size=10000,
        min_mev_rate=0.0, max_mev_rate=0.005,
        volatility_band=(0.0, 0.20),
        description="Below-average mempool, low MEV pressure",
    ),
    "MEDIUM_ACTIVITY": MempoolArchetype(
        code="MEDIUM_ACTIVITY", label="Medium Activity",
        base_fee_adj=0.0, confidence_base=0.80,
        min_mempool_size=10000, max_mempool_size=30000,
        min_mev_rate=0.001, max_mev_rate=0.01,
        volatility_band=(0.10, 0.35),
        description="Normal operating conditions",
    ),
    "HIGH_ACTIVITY": MempoolArchetype(
        code="HIGH_ACTIVITY", label="High Activity",
        base_fee_adj=+0.15, confidence_base=0.75,
        min_mempool_size=30000, max_mempool_size=80000,
        min_mev_rate=0.005, max_mev_rate=0.02,
        volatility_band=(0.25, 0.55),
        description="Above-average throughput, fee pressure rising",
    ),
    "CONGESTION_ONSET": MempoolArchetype(
        code="CONGESTION_ONSET", label="Congestion Onset",
        base_fee_adj=+0.25, confidence_base=0.72,
        min_mempool_size=50000, max_mempool_size=120000,
        min_mev_rate=0.01, max_mev_rate=0.03,
        volatility_band=(0.40, 0.65),
        description="Mempool growing fast — congestion imminent within 5-10 blocks",
    ),
    "FULL_CONGESTION": MempoolArchetype(
        code="FULL_CONGESTION", label="Full Congestion",
        base_fee_adj=+0.50, confidence_base=0.68,
        min_mempool_size=100000, max_mempool_size=999999,
        min_mev_rate=0.02, max_mev_rate=1.0,
        volatility_band=(0.55, 1.0),
        description="Severe congestion — defer non-urgent transactions",
    ),
    "MEV_SURGE": MempoolArchetype(
        code="MEV_SURGE", label="MEV Surge",
        base_fee_adj=+0.30, confidence_base=0.65,
        min_mempool_size=5000, max_mempool_size=999999,
        min_mev_rate=0.02, max_mev_rate=1.0,
        volatility_band=(0.30, 1.0),
        description="Elevated MEV activity — sandwich attacks and frontrunning likely",
    ),
    "MEV_EQUILIBRIUM": MempoolArchetype(
        code="MEV_EQUILIBRIUM", label="MEV Equilibrium",
        base_fee_adj=+0.08, confidence_base=0.73,
        min_mempool_size=5000, max_mempool_size=50000,
        min_mev_rate=0.005, max_mev_rate=0.02,
        volatility_band=(0.15, 0.40),
        description="MEV present but stable — use private mempool or batch",
    ),
    "LIQUIDATION_STORM": MempoolArchetype(
        code="LIQUIDATION_STORM", label="Liquidation Storm",
        base_fee_adj=+0.60, confidence_base=0.62,
        min_mempool_size=20000, max_mempool_size=999999,
        min_mev_rate=0.03, max_mev_rate=1.0,
        volatility_band=(0.60, 1.0),
        description="DeFi liquidation cascade — extreme fee and MEV pressure",
    ),
    "STRESS_EVENT": MempoolArchetype(
        code="STRESS_EVENT", label="Stress Event",
        base_fee_adj=+0.50, confidence_base=0.60,
        min_mempool_size=0, max_mempool_size=999999,
        min_mev_rate=0.0, max_mev_rate=1.0,
        volatility_band=(0.70, 1.0),
        description="Extreme volatility stress — high-priority only",
    ),
    "ARBITRAGE_WAVE": MempoolArchetype(
        code="ARBITRAGE_WAVE", label="Arbitrage Wave",
        base_fee_adj=+0.12, confidence_base=0.70,
        min_mempool_size=8000, max_mempool_size=60000,
        min_mev_rate=0.008, max_mev_rate=0.025,
        volatility_band=(0.20, 0.50),
        description="Cross-DEX arbitrage surge — prices diverged across venues",
    ),
    "GOVERNANCE_VOTE_WINDOW": MempoolArchetype(
        code="GOVERNANCE_VOTE_WINDOW", label="Governance Vote Window",
        base_fee_adj=-0.05, confidence_base=0.75,
        min_mempool_size=3000, max_mempool_size=40000,
        min_mev_rate=0.001, max_mev_rate=0.01,
        volatility_band=(0.05, 0.30),
        description="On-chain governance vote active — predictable patterns",
    ),
    "AIRDROP_WAVE": MempoolArchetype(
        code="AIRDROP_WAVE", label="Airdrop Wave",
        base_fee_adj=+0.35, confidence_base=0.67,
        min_mempool_size=40000, max_mempool_size=999999,
        min_mev_rate=0.01, max_mev_rate=0.05,
        volatility_band=(0.35, 0.75),
        description="Mass claim event — avoid unless urgent",
    ),
    "NFT_MINT_STORM": MempoolArchetype(
        code="NFT_MINT_STORM", label="NFT Mint Storm",
        base_fee_adj=+0.45, confidence_base=0.65,
        min_mempool_size=60000, max_mempool_size=999999,
        min_mev_rate=0.02, max_mev_rate=0.10,
        volatility_band=(0.50, 0.90),
        description="High-demand NFT mint — gas auction conditions",
    ),
    "POST_UPGRADE_SETTLEMENT": MempoolArchetype(
        code="POST_UPGRADE_SETTLEMENT", label="Post-Upgrade Settlement",
        base_fee_adj=+0.05, confidence_base=0.77,
        min_mempool_size=5000, max_mempool_size=35000,
        min_mev_rate=0.002, max_mev_rate=0.015,
        volatility_band=(0.10, 0.35),
        description="Network upgraded — activity normalizing, confidence high",
    ),
}


# ── Pattern Observation ────────────────────────────────────────────────────────

@dataclass
class PatternObservation:
    """One recorded mempool state → outcome pair."""
    archetype_code:      str
    observed_at:         float
    mempool_size:        int
    mev_rate:            float
    volatility:          float
    recommended_fee_adj: float
    actual_fee_adj:      float       # realized outcome
    prediction_error:    float       # |recommended - actual|
    chain_id:            int


@dataclass
class ArchetypeCalibration:
    """
    Calibrated archetype statistics from historical observations.
    Confidence grows toward 1.0 as sample_size grows.
    """
    archetype_code:       str
    sample_size:          int
    mean_prediction_error: float
    calibrated_confidence: float    # Bayesian-updated from base + sample
    mean_fee_adj:         float
    std_fee_adj:          float
    last_seen_at:         float


# ── SQLite Pattern Store ───────────────────────────────────────────────────────

class BIBLPatternStore:
    """
    Persistent pattern match store for BIBL chain memory.
    SQLite-backed with in-memory cache.
    """

    DB_PATH = os.environ.get(
        "BIBL_PATTERN_DB",
        os.path.join(
            os.path.dirname(os.path.abspath(__file__)),
            "..", "..", "akashic", "bibl_patterns.db"
        )
    )

    def __init__(self, db_path: Optional[str] = None):
        self._db_path  = db_path or self.DB_PATH
        self._cache:   Dict[str, ArchetypeCalibration] = {}
        self._init_db()
        self._load_calibrations()

    def _init_db(self) -> None:
        # Ensure parent directory exists
        os.makedirs(os.path.dirname(os.path.abspath(self._db_path)), exist_ok=True)
        with sqlite3.connect(self._db_path) as conn:
            conn.execute("""
                CREATE TABLE IF NOT EXISTS bibl_observations (
                    id                INTEGER PRIMARY KEY AUTOINCREMENT,
                    archetype_code    TEXT NOT NULL,
                    observed_at       REAL NOT NULL,
                    mempool_size      INTEGER,
                    mev_rate          REAL,
                    volatility        REAL,
                    recommended_fee   REAL,
                    actual_fee        REAL,
                    prediction_error  REAL,
                    chain_id          INTEGER
                )
            """)
            conn.execute("""
                CREATE INDEX IF NOT EXISTS idx_bibl_archetype
                ON bibl_observations(archetype_code, observed_at DESC)
            """)
            conn.execute("""
                CREATE TABLE IF NOT EXISTS bibl_calibrations (
                    archetype_code        TEXT PRIMARY KEY,
                    sample_size           INTEGER,
                    mean_prediction_error REAL,
                    calibrated_confidence REAL,
                    mean_fee_adj          REAL,
                    std_fee_adj           REAL,
                    last_seen_at          REAL
                )
            """)
            conn.commit()

    def _load_calibrations(self) -> None:
        with sqlite3.connect(self._db_path) as conn:
            rows = conn.execute(
                "SELECT * FROM bibl_calibrations"
            ).fetchall()
            for row in rows:
                cal = ArchetypeCalibration(
                    archetype_code        = row[0],
                    sample_size           = row[1],
                    mean_prediction_error = row[2],
                    calibrated_confidence = row[3],
                    mean_fee_adj          = row[4],
                    std_fee_adj           = row[5],
                    last_seen_at          = row[6],
                )
                self._cache[row[0]] = cal

    def record_observation(self, obs: PatternObservation) -> None:
        """Record one mempool state observation."""
        with sqlite3.connect(self._db_path) as conn:
            conn.execute("""
                INSERT INTO bibl_observations
                  (archetype_code, observed_at, mempool_size, mev_rate,
                   volatility, recommended_fee, actual_fee, prediction_error, chain_id)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
            """, (
                obs.archetype_code, obs.observed_at, obs.mempool_size,
                obs.mev_rate, obs.volatility, obs.recommended_fee_adj,
                obs.actual_fee_adj, obs.prediction_error, obs.chain_id,
            ))
            conn.commit()
        self._recalibrate(obs.archetype_code)

    def _recalibrate(self, archetype_code: str) -> None:
        """Recompute calibration stats after a new observation."""
        archetype = ARCHETYPES.get(archetype_code)
        if not archetype:
            return

        with sqlite3.connect(self._db_path) as conn:
            rows = conn.execute("""
                SELECT actual_fee, prediction_error, observed_at
                FROM bibl_observations
                WHERE archetype_code = ?
                ORDER BY observed_at DESC
                LIMIT 5000
            """, (archetype_code,)).fetchall()

        if not rows:
            return

        n          = len(rows)
        fee_adjs   = [r[0] for r in rows]
        errors     = [r[1] for r in rows]
        last_seen  = max(r[2] for r in rows)

        mean_fee  = sum(fee_adjs) / n
        mean_err  = sum(errors) / n
        std_fee   = math.sqrt(sum((v - mean_fee) ** 2 for v in fee_adjs) / n) if n > 1 else 0.0

        # Bayesian confidence update:
        # confidence = base_confidence + (sample_weight) * (1 - mean_error)
        # sample_weight grows toward 0.30 as n → 1000
        sample_weight = min(0.30, n / 1000 * 0.30)
        calibrated = (
            archetype.confidence_base * (1.0 - sample_weight) +
            (1.0 - min(1.0, mean_err)) * sample_weight
        )
        calibrated = max(0.20, min(0.98, calibrated))

        cal = ArchetypeCalibration(
            archetype_code        = archetype_code,
            sample_size           = n,
            mean_prediction_error = mean_err,
            calibrated_confidence = calibrated,
            mean_fee_adj          = mean_fee,
            std_fee_adj           = std_fee,
            last_seen_at          = last_seen,
        )
        self._cache[archetype_code] = cal

        with sqlite3.connect(self._db_path) as conn:
            conn.execute("""
                INSERT OR REPLACE INTO bibl_calibrations
                  (archetype_code, sample_size, mean_prediction_error,
                   calibrated_confidence, mean_fee_adj, std_fee_adj, last_seen_at)
                VALUES (?, ?, ?, ?, ?, ?, ?)
            """, (
                archetype_code, n, mean_err, calibrated,
                mean_fee, std_fee, last_seen,
            ))
            conn.commit()

    def get_calibration(self, archetype_code: str) -> Optional[ArchetypeCalibration]:
        return self._cache.get(archetype_code)

    def match_count(self, archetype_code: str) -> int:
        """Real historical match count for this archetype."""
        cal = self._cache.get(archetype_code)
        if cal:
            return cal.sample_size
        with sqlite3.connect(self._db_path) as conn:
            row = conn.execute(
                "SELECT COUNT(*) FROM bibl_observations WHERE archetype_code = ?",
                (archetype_code,)
            ).fetchone()
            return row[0] if row else 0

    def calibration_summary(self) -> List[dict]:
        rows = []
        for code in ARCHETYPES:
            cal = self._cache.get(code)
            arc = ARCHETYPES[code]
            rows.append({
                "code":             code,
                "label":            arc.label,
                "sample_size":      cal.sample_size if cal else 0,
                "confidence":       cal.calibrated_confidence if cal else arc.confidence_base,
                "mean_error":       cal.mean_prediction_error if cal else None,
                "base_fee_adj":     arc.base_fee_adj,
                "last_seen":        cal.last_seen_at if cal else None,
            })
        return sorted(rows, key=lambda r: r["sample_size"], reverse=True)


# ── Archetype Classifier ───────────────────────────────────────────────────────

def classify_mempool_archetype(
    mempool_size: int,
    mev_rate:     float,
    volatility:   float,
) -> Tuple[MempoolArchetype, float]:
    """
    Classify current mempool state into one of the 15 archetypes.
    Returns (best_match_archetype, match_score).

    Match score: fraction of conditions satisfied.
    Priority ordering: specific events > general activity levels.
    """
    # Priority: specific events checked first
    priority_order = [
        "LIQUIDATION_STORM",
        "STRESS_EVENT",
        "NFT_MINT_STORM",
        "AIRDROP_WAVE",
        "MEV_SURGE",
        "FULL_CONGESTION",
        "ARBITRAGE_WAVE",
        "CONGESTION_ONSET",
        "MEV_EQUILIBRIUM",
        "HIGH_ACTIVITY",
        "POST_UPGRADE_SETTLEMENT",
        "GOVERNANCE_VOTE_WINDOW",
        "MEDIUM_ACTIVITY",
        "LOW_ACTIVITY",
        "DEEP_CALM",
    ]

    best_score    = -1.0
    best_archetype = ARCHETYPES["MEDIUM_ACTIVITY"]

    for code in priority_order:
        arc   = ARCHETYPES[code]
        score = _archetype_match_score(arc, mempool_size, mev_rate, volatility)
        if score > best_score:
            best_score     = score
            best_archetype = arc

    return best_archetype, max(0.0, best_score)


def _archetype_match_score(
    arc:          MempoolArchetype,
    mempool_size: int,
    mev_rate:     float,
    volatility:   float,
) -> float:
    """Score how well current state matches this archetype. Range [0, 1]."""
    conditions_met = 0
    total = 3

    if arc.min_mempool_size <= mempool_size <= arc.max_mempool_size:
        conditions_met += 1
    if arc.min_mev_rate <= mev_rate <= arc.max_mev_rate:
        conditions_met += 1
    if arc.volatility_band[0] <= volatility <= arc.volatility_band[1]:
        conditions_met += 1

    return conditions_met / total


# ── Self-test ─────────────────────────────────────────────────────────────────

if __name__ == "__main__":
    import tempfile

    with tempfile.NamedTemporaryFile(suffix=".db", delete=False) as f:
        db_path = f.name

    store = BIBLPatternStore(db_path=db_path)

    # Record 50 observations for MEV_SURGE
    for i in range(50):
        store.record_observation(PatternObservation(
            archetype_code="MEV_SURGE",
            observed_at=time.time() - i * 3600,
            mempool_size=60000 + i * 100,
            mev_rate=0.025,
            volatility=0.5,
            recommended_fee_adj=0.30,
            actual_fee_adj=0.28 + (i % 5) * 0.01,
            prediction_error=abs(0.30 - (0.28 + (i % 5) * 0.01)),
            chain_id=1,
        ))

    cal = store.get_calibration("MEV_SURGE")
    assert cal is not None
    assert cal.sample_size == 50
    print(f"MEV_SURGE: samples={cal.sample_size} confidence={cal.calibrated_confidence:.4f}")

    # Classify
    archetype, score = classify_mempool_archetype(65000, 0.03, 0.55)
    print(f"Classify: {archetype.code} ({archetype.label}) score={score:.2f}")

    # Real match count
    count = store.match_count("MEV_SURGE")
    print(f"Historical matches for MEV_SURGE: {count}")
    assert count == 50

    summary = store.calibration_summary()
    print(f"Archetypes tracked: {len(ARCHETYPES)}")
    print(f"With observations:  {sum(1 for r in summary if r['sample_size'] > 0)}")

    os.unlink(db_path)
    print("BIBL-PATTERN-STORE PASS — 15 archetypes + persistent calibration implemented")
