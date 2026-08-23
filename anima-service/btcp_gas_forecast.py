"""
btcp_gas_forecast.py — BTCP Gas Forecasting Module
Predicts gas costs across chains for BTCP_score computation.
Uses EWMA + ARIMA-lite for short-horizon forecasting.
normalize_gas = 1 - forecast_mean_usd / 99th_percentile_gas
Spec: BTCP Master Implementation Spec §4.2 Step 1 (BIBL), §Gap J
"""

import math
import statistics
from typing import Optional

# ─── Configuration ────────────────────────────────────────────────────────────
GAS_99TH_PERCENTILE = 200.0   # USD — calibrate from 90-day empirical sample
EWMA_ALPHA          = 0.2     # smoothing factor for EWMA
VOLATILITY_WINDOW   = 24      # hours

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
    normalize_gas = max(0.0, 1.0 - mean_usd / GAS_99TH_PERCENTILE)

    return {
        "chain_id":       chain_id,
        "mean_usd":       round(mean_usd, 6),
        "ci95_low":       round(low, 6),
        "ci95_high":      round(high, 6),
        "volatility":     round(vol, 4),
        "normalize_gas":  round(normalize_gas, 6),  # ← used in BTCP_score formula
        "above_threshold": normalize_gas > 0.5,     # chains with very high gas penalized
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

    # Test with simulated Arbitrum gas history
    arb_history = [0.07, 0.09, 0.06, 0.08, 0.10, 0.07, 0.08]
    result = forecast_gas(42161, arb_history)
    print(f"Arbitrum gas forecast: {json.dumps(result, indent=2)}")

    savings = compute_gas_savings(result["mean_usd"])
    print(f"Gas savings vs bridge: {json.dumps(savings, indent=2)}")
