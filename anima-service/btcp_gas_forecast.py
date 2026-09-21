"""
btcp_gas_forecast.py — BTCP Gas Forecasting Module
Predicts gas costs across chains for BTCP_score computation.
Uses EWMA + ARIMA-lite for short-horizon forecasting.
normalize_gas = 1 - forecast_mean_usd / 99th_percentile_gas
Spec: BTCP Master Implementation Spec §4.2 Step 1 (BIBL), §4.2 Step 5
      (Gas Sharing Protocol), §5 BRT Scheduler (line 1566) — gas forecast
      formula. §11 Gap J (TRION token gas utility).
"""

import math
import os
import sqlite3
import statistics
import threading
import time
from typing import Optional, Tuple

# ─── Configuration ────────────────────────────────────────────────────────────
# Gap D8 fix: GAS_99TH_PERCENTILE is no longer a hardcoded 200.0 constant.
# It is computed as the empirical 99th percentile of recent gas costs over a
# rolling 30-day window, cached with a 1-hour TTL. The 200.0 below is the
# LAST-RESORT FALLBACK used only when the bh_ledger has no usable data — see
# compute_gas_99th_percentile(). Spec ref: §4.2 Step 5 / §5 BRT Scheduler.
GAS_99TH_PERCENTILE_FALLBACK = 200.0   # USD — last-resort fallback only
EWMA_ALPHA          = 0.2     # smoothing factor for EWMA
VOLATILITY_WINDOW   = 24      # hours
GAS_99TH_TTL_SECONDS = 3600   # 1-hour cache TTL (spec §5: rolling 30-day sample)
GAS_99TH_WINDOW_DAYS = 30     # spec: "rolling 30-day empirical sample"

# ─── Gas-unit → USD conversion (Gap D8 honest disclosure) ────────────────────
# bh_ledger.gas_used is in raw EVM gas units (e.g. 21 000 for a simple
# transfer, ~3 000 000 for a DEX swap). To express the 99th percentile in
# USD per the spec formula (normalize_gas = 1 - mean_usd / p99_usd), we
# multiply gas_used by an assumed gas price in USD per gas unit.
#
# The default assumes Ethereum mainnet at ~30 gwei × ~$3 000/ETH ≈ 9e-5
# USD per gas unit. This is a CONSERVATIVE FIXED ASSUMPTION, NOT a live
# oracle feed — there is no gas-price oracle in the current stack. When
# a proper gas-price feed is wired in, this factor should be replaced
# with the chain's live gas-price oracle × the chain's native-token USD
# price (per spec §4.2 Step 5 Gas Sharing Protocol).
ASSUMED_GAS_PRICE_USD_PER_UNIT = 9e-5

# ─── Per-chain gas profiles (baseline fallback) ───────────────────────────────
CHAIN_GAS_PROFILES = {
    42161:  {"mean": 0.08, "std": 0.04, "min": 0.02, "p99": 0.80},   # Arbitrum
    8453:   {"mean": 0.06, "std": 0.03, "min": 0.01, "p99": 0.60},   # Base
    10:     {"mean": 0.06, "std": 0.03, "min": 0.01, "p99": 0.60},   # Optimism
    137:    {"mean": 0.02, "std": 0.01, "min": 0.005,"p99": 0.20},   # Polygon
    1:      {"mean": 8.50, "std": 5.00, "min": 2.00, "p99": 45.0},   # Ethereum
    56:     {"mean": 0.15, "std": 0.08, "min": 0.05, "p99": 1.50},   # BNB Chain
    43114:  {"mean": 0.10, "std": 0.05, "min": 0.03, "p99": 1.00},   # Avalanche
    421614: {"mean": 0.01, "std": 0.005,"min": 0.001,"p99": 0.05},   # Arb Sepolia
}


# ─── Rolling 30-day 99th-percentile computation (Gap D8) ─────────────────────
_GAS_99TH_CACHE_LOCK = threading.Lock()
_GAS_99TH_CACHE: Optional[dict] = None  # {"value": float, "source": str,
                                         #  "sample_count": int, "computed_at": float,
                                         #  "window_seconds": int, "ts_span_seconds": float}


def _default_bh_ledger_path() -> str:
    """Locate bh_ledger.db (the L0 Akashic behavioral-hash ledger).

    Search order:
      1. $TRION_BH_LEDGER_DB (explicit override)
      2. <repo_root>/bh_ledger.db
      3. <repo_root>/anima-service/bh_ledger.db
    Returns the first path that exists, or the repo-root path as a default
    (the caller will then fall back gracefully when the file is absent).
    """
    env = os.environ.get("TRION_BH_LEDGER_DB")
    if env and os.path.exists(env):
        return env
    here = os.path.dirname(os.path.abspath(__file__))
    repo_root = os.path.dirname(here)  # anima-service/.. = repo root
    candidates = [
        os.path.join(repo_root, "bh_ledger.db"),
        os.path.join(here, "bh_ledger.db"),  # anima-service/bh_ledger.db
    ]
    for c in candidates:
        if os.path.exists(c):
            return c
    return candidates[0]  # default path; query will fail and fall back


def _query_gas_used_last_30d(db_path: str) -> Tuple[list, float, float]:
    """Return (gas_used_values, min_ts, max_ts) for the last 30 days.

    The bh_ledger table has columns gas_used (int) and ts (float Unix seconds).
    Returns empty list on any DB error.
    """
    window_start = time.time() - GAS_99TH_WINDOW_DAYS * 86400
    try:
        conn = sqlite3.connect(f"file:{db_path}?mode=ro", uri=True, timeout=2.0)
        cur = conn.cursor()
        rows = cur.execute(
            "SELECT gas_used, ts FROM bh_ledger "
            "WHERE gas_used IS NOT NULL AND gas_used > 0 AND ts >= ? "
            "ORDER BY ts ASC",
            (window_start,),
        ).fetchall()
        if not rows:
            conn.close()
            return [], 0.0, 0.0
        gas_used = [r[0] for r in rows]
        ts_values = [r[1] for r in rows]
        conn.close()
        return gas_used, float(min(ts_values)), float(max(ts_values))
    except Exception:
        return [], 0.0, 0.0


def _query_gas_ts_last_30d(db_path: str) -> list[float]:
    """Return the list of `ts` values for gas-bearing bh_ledger rows over the
    last 30 days (BTCP-FIX2-INT Fix 2 — feeds ``derive_brt_phase`` so the gas
    forecast can carry BRT/circadian correlation info)."""
    window_start = time.time() - GAS_99TH_WINDOW_DAYS * 86400
    try:
        conn = sqlite3.connect(f"file:{db_path}?mode=ro", uri=True, timeout=2.0)
        cur = conn.cursor()
        rows = cur.execute(
            "SELECT ts FROM bh_ledger "
            "WHERE gas_used IS NOT NULL AND gas_used > 0 AND ts IS NOT NULL AND ts >= ? "
            "ORDER BY ts ASC",
            (window_start,),
        ).fetchall()
        conn.close()
        return [float(r[0]) for r in rows if r[0] is not None]
    except Exception:
        return []


def compute_gas_99th_percentile(force_refresh: bool = False) -> dict:
    """Compute the rolling 30-day empirical 99th percentile of gas costs.

    Returns a dict with:
      value            — float, the 99th percentile in USD
      source           — str: "empirical_30d" | "fallback_hardcoded"
      sample_count     — int, number of bh_ledger rows used
      computed_at      — float, Unix timestamp of cache fill
      window_seconds   — int, 30 days = 2 592 000
      ts_span_seconds  — float, actual span of the source data
      conversion_note  — str, disclosure of gas_used → USD conversion

    Spec ref: §4.2 Step 5 (Gas Sharing Protocol), §5 BRT Scheduler (the
    gas correlation formula's normalization denominator). The spec says
    GAS_99TH_PERCENTILE = "rolling 30-day 99th percentile" — that is exactly
    what this computes. Cache TTL is 1 hour (GAS_99TH_TTL_SECONDS).

    Fallback: if the bh_ledger has no usable rows for the last 30 days
    (e.g. cold start, DB unavailable), returns 200.0 USD with
    source="fallback_hardcoded" and a clear disclosure note.
    """
    global _GAS_99TH_CACHE
    now = time.time()
    with _GAS_99TH_CACHE_LOCK:
        if (_GAS_99TH_CACHE is not None
                and not force_refresh
                and (now - _GAS_99TH_CACHE["computed_at"]) < GAS_99TH_TTL_SECONDS):
            return dict(_GAS_99TH_CACHE)

    db_path = _default_bh_ledger_path()
    gas_used, ts_min, ts_max = _query_gas_used_last_30d(db_path)
    if len(gas_used) >= 2:
        gas_usd = sorted(g * ASSUMED_GAS_PRICE_USD_PER_UNIT for g in gas_used)
        # 99th percentile via nearest-rank method (inclusive)
        idx = max(0, min(len(gas_usd) - 1,
                         int(math.ceil(0.99 * len(gas_usd))) - 1))
        p99 = float(gas_usd[idx])
        result = {
            "value": p99,
            "source": "empirical_30d",
            "sample_count": len(gas_usd),
            "computed_at": now,
            "window_seconds": GAS_99TH_WINDOW_DAYS * 86400,
            "ts_span_seconds": max(0.0, ts_max - ts_min),
            "conversion_note": (
                "gas_used (raw EVM units) × ASSUMED_GAS_PRICE_USD_PER_UNIT="
                f"{ASSUMED_GAS_PRICE_USD_PER_UNIT:.2e} USD/unit (Ethereum "
                "mainnet ~30 gwei × ~$3000/ETH). NOT a live oracle feed — "
                "replace with chain gas-price oracle × native-token USD price "
                "when available (spec §4.2 Step 5 Gas Sharing Protocol)."
            ),
        }
    else:
        # Honest fallback: no usable bh_ledger data
        result = {
            "value": GAS_99TH_PERCENTILE_FALLBACK,
            "source": "fallback_hardcoded",
            "sample_count": 0,
            "computed_at": now,
            "window_seconds": GAS_99TH_WINDOW_DAYS * 86400,
            "ts_span_seconds": 0.0,
            "conversion_note": (
                f"FALLBACK: GAS_99TH_PERCENTILE={GAS_99TH_PERCENTILE_FALLBACK} "
                "USD used because bh_ledger has no usable rows in the last 30 "
                "days. This is the legacy hardcoded value — kept only as a "
                "cold-start fallback (Gap D8)."
            ),
        }
    with _GAS_99TH_CACHE_LOCK:
        _GAS_99TH_CACHE = dict(result)
    return dict(result)


def get_gas_99th_percentile() -> float:
    """Convenience accessor returning just the 99th-percentile value."""
    return compute_gas_99th_percentile()["value"]


# ─── EWMA gas estimate ────────────────────────────────────────────────────────
def ewma_forecast(
    history:    list[float],
    alpha:      float = EWMA_ALPHA,
) -> float:
    """Exponentially Weighted Moving Average for gas price forecasting."""
    if not history:
        return 1.0
    ewma = history[0]
    for obs in history[1:]:
        ewma = alpha * obs + (1 - alpha) * ewma
    return ewma


# ─── Volatility estimate ──────────────────────────────────────────────────────
def gas_volatility(history: list[float]) -> float:
    """Realized gas price volatility (coefficient of variation)."""
    if len(history) < 2:
        return 0.5
    mean = statistics.mean(history)
    if mean == 0:
        return 1.0
    std = statistics.stdev(history)
    return std / mean


# ─── CI95 bounds ─────────────────────────────────────────────────────────────
def ci95(mean: float, vol: float) -> tuple[float, float]:
    """95% confidence interval: mean ± 1.96 × (vol × mean)."""
    margin = 1.96 * vol * mean
    return (max(0.0, mean - margin), mean + margin)


# ─── Full gas forecast ────────────────────────────────────────────────────────
def forecast_gas(
    chain_id: int,
    history:  list[float] = None,  # recent gas costs in USD
) -> dict:
    """
    Forecast gas for a specific chain.
    Returns mean_usd, ci95_low, ci95_high, normalize_gas component.

    Gap D8 fix: GAS_99TH_PERCENTILE is computed at runtime from the rolling
    30-day empirical sample (compute_gas_99th_percentile). The response now
    discloses the source ("empirical_30d" | "fallback_hardcoded"), the
    sample count, and the conversion note so callers can distinguish a
    real empirical denominator from the legacy 200.0 fallback.

    BTCP-FIX2-INT Fix 2 — wire BRT into the gas forecast. The response now
    carries `brt_phase` (circadian/ultradian/peak_hour/quiet_hour/strength/
    data_source) and `deferred_recommendation` (None|"DEFERRED"|"NOW"). When
    BRT detects a circadian trough near the current hour (quiet_hour within
    ±2h of now) AND circadian_strength ≥ 0.15 (CONJECTURE floor for the
    gas-circadian correlation per spec §5), the forecast marks the route as
    DEFERRED so the router can route it via the spec §4.2 Step 2 DEFERRED
    RouteType (priority 6) instead of executing immediately at suboptimal
    gas. Spec ref: §5 BRT Scheduler, §5.8 Water Following the Gradient.
    """
    profile = CHAIN_GAS_PROFILES.get(chain_id, {"mean": 5.0, "std": 3.0, "min": 0.5, "p99": 30.0})

    if history and len(history) >= 2:
        mean_usd = ewma_forecast(history)
        vol      = gas_volatility(history[-VOLATILITY_WINDOW:])
    else:
        # Fallback to baseline profile
        mean_usd = profile["mean"]
        vol      = profile["std"] / max(profile["mean"], 1e-6)

    low, high     = ci95(mean_usd, vol)
    p99_meta      = compute_gas_99th_percentile()
    p99_usd       = p99_meta["value"]
    normalize_gas = max(0.0, 1.0 - mean_usd / max(p99_usd, 1e-9))

    # ── BTCP-FIX2-INT Fix 2: derive BRT phase from observed tx timestamps ──
    # Spec §5.8 "Water Following the Gradient": non-urgent intents should
    # defer to a predicted optimal window when BRT detects a circadian
    # trough. The BRT scheduler is the gas-circadian correlation primitive
    # (spec §5 line 1566 — `derive_brt_phase`); prior to this fix
    # `btcp_gas_forecast.py` ignored BRT entirely (BTCP-DEEP-5 #6).
    brt_phase_info = None
    deferred_recommendation = "NOW"
    defer_reason = "no BRT data yet (cold start)"
    try:
        from brt_scheduler import derive_brt_phase  # local import for isolation
        db_path = _default_bh_ledger_path()
        tx_ts = _query_gas_ts_last_30d(db_path)
        brt = derive_brt_phase(tx_ts)
        brt_phase_info = {
            "circadian_phase":    round(brt.circadian_phase, 4),
            "ultradian_phase":    round(brt.ultradian_phase, 4),
            "circadian_strength": round(brt.circadian_strength, 4),
            "ultradian_strength": round(brt.ultradian_strength, 4),
            "lunar_phase":        round(brt.lunar_phase, 4),
            "seasonal_phase":     round(brt.seasonal_phase, 4),
            "data_source":        brt.data_source,  # OBSERVED | CLOCK_FALLBACK
            "observation_count":  brt.observation_count,
            "peak_hour_utc":      brt.peak_hour,
            "quiet_hour_utc":     brt.quiet_hour,
        }
        # BRT gas-circadian correlation is a CONJECTURE (spec §1, F14
        # falsifiability). Deploy-time we use a conservative trigger:
        # only recommend DEFERRED when the observed signal is strong
        # enough to plausibly predict a cheaper upcoming window, AND the
        # current hour is within ±2h of the BRT-detected quiet hour.
        now_hour = int((time.time() % 86400) // 3600) % 24
        quiet_hour = brt.quiet_hour
        hours_to_quiet = (quiet_hour - now_hour) % 24
        # Window of ±2h around the quiet_hour (closest quiet window).
        near_quiet_window = (
            hours_to_quiet <= 2 or hours_to_quiet >= 22
        )
        # Circadian strength floor: 0.15 == brt_scheduler's own threshold
        # for "OBSERVED" vs CLOCK_FALLBACK confidence.
        strong_enough = (
            brt.data_source == "OBSERVED"
            and brt.circadian_strength >= 0.15
        )
        if strong_enough and near_quiet_window:
            deferred_recommendation = "DEFERRED"
            defer_reason = (
                f"BRT circadian trough near now_hour={now_hour} UTC "
                f"(quiet_hour={quiet_hour}, strength={brt.circadian_strength:.3f}); "
                f"spec §5.8 predicts cheaper gas in the next window."
            )
        elif strong_enough:
            deferred_recommendation = "NOW"
            defer_reason = (
                f"BRT strong (strength={brt.circadian_strength:.3f}) "
                f"but next quiet hour {hours_to_quiet}h away — execute now."
            )
        else:
            deferred_recommendation = "NOW"
            defer_reason = (
                f"BRT signal weak (data_source={brt.data_source}, "
                f"strength={brt.circadian_strength:.3f}) — spec §5 marks "
                f"gas-circadian correlation as CONJECTURE (F14); executing now."
            )
    except Exception as e:
        defer_reason = f"BRT derivation unavailable: {type(e).__name__}: {str(e)[:60]}"
        deferred_recommendation = "NOW"

    return {
        "chain_id":       chain_id,
        "mean_usd":       round(mean_usd, 6),
        "ci95_low":       round(low, 6),
        "ci95_high":      round(high, 6),
        "volatility":     round(vol, 4),
        "normalize_gas":  round(normalize_gas, 6),  # ← used in BTCP_score formula
        "above_threshold": normalize_gas > 0.5,    # chains with very high gas penalized
        # Gap D8 disclosures:
        "gas_99th_percentile":   round(p99_usd, 6),
        "gas_99th_source":       p99_meta["source"],
        "gas_99th_sample_count": p99_meta["sample_count"],
        "gas_99th_window_seconds": p99_meta["window_seconds"],
        "gas_99th_ts_span_seconds": round(p99_meta["ts_span_seconds"], 3),
        "gas_99th_conversion_note": p99_meta["conversion_note"],
        "gas_99th_cached_at":   round(p99_meta["computed_at"], 3),
        "gas_99th_ttl_seconds": GAS_99TH_TTL_SECONDS,
        # BTCP-FIX2-INT Fix 2 — BRT phase + deferred route recommendation
        # (spec §5 BRT Scheduler + §5.8 Water Following the Gradient).
        "brt_phase":                 brt_phase_info,
        "deferred_recommendation":   deferred_recommendation,  # "NOW" | "DEFERRED"
        "defer_reason":              defer_reason,
        "brt_correlation_status":    "CONJECTURE (F14 — validate over 90-day sample)",
    }


# ─── Multi-chain gas comparison ───────────────────────────────────────────────
def compare_chains_gas(
    chain_histories: dict[int, list[float]],
) -> list[dict]:
    """
    Rank chains by gas efficiency for BTCP routing.
    Returns sorted list (cheapest first).
    """
    forecasts = [
        forecast_gas(cid, history)
        for cid, history in chain_histories.items()
    ]
    return sorted(forecasts, key=lambda x: x["mean_usd"])


# ─── Gas savings vs bridge ────────────────────────────────────────────────────
BRIDGE_GAS_BASELINE = {
    "wormhole":  15.0,    # USD gas cost for Wormhole bridge
    "layerzero": 12.0,    # LayerZero
    "axelar":    18.0,    # Axelar
    "hop":       10.0,    # Hop Protocol
    "across":    8.0,     # Across Protocol
    "mean":      12.6,    # weighted mean
}

def compute_gas_savings(
    btcp_gas_usd:  float,
    bridge_name:   str = "mean",
) -> dict:
    """
    Compute gas saved by using BTCP vs traditional bridge.
    """
    bridge_cost = BRIDGE_GAS_BASELINE.get(bridge_name, BRIDGE_GAS_BASELINE["mean"])
    saved       = max(0.0, bridge_cost - btcp_gas_usd)
    pct_saved   = saved / bridge_cost if bridge_cost > 0 else 0.0

    return {
        "bridge_gas_usd":   bridge_cost,
        "btcp_gas_usd":     round(btcp_gas_usd, 6),
        "saved_usd":        round(saved, 6),
        "pct_saved":        round(pct_saved * 100, 2),
        "is_cheaper":       btcp_gas_usd < bridge_cost,
    }


if __name__ == "__main__":
    import json

    print("=== Gap D8: rolling 30-day empirical 99th-percentile ===")
    p99 = compute_gas_99th_percentile()
    print(json.dumps(p99, indent=2))
    print()

    # Test with simulated Arbitrum gas history
    arb_history = [0.07, 0.09, 0.06, 0.08, 0.10, 0.07, 0.08]
    result = forecast_gas(42161, arb_history)
    print(f"Arbitrum gas forecast: {json.dumps(result, indent=2)}")

    savings = compute_gas_savings(result["mean_usd"])
    print(f"Gas savings vs bridge: {json.dumps(savings, indent=2)}")

    # Cache check: second call must hit the 1h cache (same computed_at)
    p99_2 = compute_gas_99th_percentile()
    assert p99_2["computed_at"] == p99["computed_at"], "cache must hit on 2nd call"
    print("\n✓ 1-hour TTL cache verified (computed_at unchanged on 2nd call)")
    print(f"✓ source={p99['source']} value={p99['value']:.6f} sample_count={p99['sample_count']}")
