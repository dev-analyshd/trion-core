#!/usr/bin/env python3
"""
TRION Revenue Model Service — LOCAL ONLY (not committed to git).

Implements the 6 whitepaper §15.2 revenue streams as live, testable endpoints.
Each stream is priced per the whitepaper specification and queries the live
Akashic Index (TimescaleDB) for grounding.

Streams (whitepaper §15.2):
  1. Signal consumption fees       — tiered by protocol TVL
  2. Genesis Inference premium      — new-asset behavioral pricing from block 1
  3. ANIMA intelligence subscriptions — Pre-Manifestation / Trajectory / Institutional
  4. Regulatory API                 — SBA + Regulatory Behavioral; public-good vs commercial
  5. Behavioral data market         — anonymized Akashic Index access; academic vs commercial
  6. Developer ecosystem            — SDK licensing, integration certification, validator tooling

Port: 5001 (standalone; never touches api/app.py)
"""
import os, math, time, hashlib, json, logging
from datetime import datetime, timezone
import psycopg2
from flask import Flask, jsonify, request

logging.basicConfig(level=logging.INFO, format="%(levelname)s [rev] %(message)s")
log = logging.getLogger("revenue")
app = Flask(__name__)

TS_URL = os.environ.get(
    "TIMESCALEDB_URL",
    "postgres://tsdbadmin:baemjc9icol13pb5@mo7c8ietup.tv8aa8cnsj.tsdb.cloud.timescale.com:34783/tsdb?sslmode=require",
)
API_KEY = os.environ.get("TRION_API_KEY", "test-audit-key")

# Whitepaper §15.3 token economics constants
TOTAL_SUPPLY = 1_000_000_000       # fixed at genesis, no inflation
BURN_FRACTION = 0.001              # 0.1% burned per consumption bonding
PUBLIC_GOOD_FRACTION = 0.15        # 15% of fee revenue → public good pool
UNKNOWN_BUDGET_FRACTION = 0.10     # 10% reserved for unknown unknowns

# ── Akashic Index connection (live) ───────────────────────────────────────────
def tsdb():
    return psycopg2.connect(TS_URL)

def akashic_stats():
    """Return live Akashic Index row counts for grounding revenue calcs."""
    out = {"ts": time.time()}
    try:
        c = tsdb(); cur = c.cursor()
        for t in ("akashic_bh","akashic_depth","akashic_vectors","beo_registry",
                  "archetype_library","validator_coverage","genesis_confidence_log"):
            try:
                cur.execute(f"SELECT count(*) FROM {t}"); out[t] = cur.fetchone()[0]
            except Exception: out[t] = 0
        cur.close(); c.close()
    except Exception as e:
        out["error"] = str(e)
    return out

_STATS_CACHE = {"t": 0, "v": None}
def cached_stats():
    now = time.time()
    if _STATS_CACHE["v"] is None or now - _STATS_CACHE["t"] > 60:
        _STATS_CACHE["v"] = akashic_stats(); _STATS_CACHE["t"] = now
    return _STATS_CACHE["v"]

def require_key():
    k = request.headers.get("X-API-Key","")
    if k != API_KEY:
        return False
    return True

def auth_or_403():
    if not require_key():
        return jsonify({"error":"unauthorized","hint":"X-API-Key required"}), 403
    return None

# ══════════════════════════════════════════════════════════════════════════════
# STREAM 1 — Signal consumption fees (tiered by protocol TVL)
# Whitepaper: "Tiered by protocol TVL. Small protocols pay minimal. Large TVL pays scaled."
# ══════════════════════════════════════════════════════════════════════════════
@app.route("/api/v1/revenue/signal-consumption")
def stream_signal_consumption():
    if (e := auth_or_403()): return e
    tvl = float(request.args.get("tvl_usd", 1_000_000))
    calls = int(request.args.get("calls_per_month", 10000))
    # Tiered: 4 bands by TVL
    if tvl < 1_000_000:           tier, base, per_call = "MICRO",     0,     0.0
    elif tvl < 10_000_000:        tier, base, per_call = "SMALL",     99,    0.002
    elif tvl < 100_000_000:       tier, base, per_call = "MID",       999,    0.001
    elif tvl < 1_000_000_000:     tier, base, per_call = "LARGE",   4999,    0.0005
    else:                         tier, base, per_call = "WHALE",  19999,    0.0002
    usage_fee = calls * per_call
    monthly = base + usage_fee
    burn = monthly * BURN_FRACTION
    public_good = monthly * PUBLIC_GOOD_FRACTION
    unknown_reserve = monthly * UNKNOWN_BUDGET_FRACTION
    # Quality bond (whitepaper §15.3 item 3): stake scales with TVL
    quality_bond = max(tvl * 0.001, 1000)
    return jsonify({
        "stream": "signal_consumption_fees",
        "whitepaper_section": "15.2",
        "tvl_usd": tvl, "calls_per_month": calls,
        "tier": tier,
        "base_subscription_usd": base,
        "per_call_usd": per_call,
        "usage_fee_usd": round(usage_fee, 4),
        "monthly_total_usd": round(monthly, 2),
        "burn_usd": round(burn, 4),
        "public_good_pool_usd": round(public_good, 4),
        "unknown_unknown_reserve_usd": round(unknown_reserve, 4),
        "quality_bond_required_usd": round(quality_bond, 2),
        "akashic_grounding": cached_stats(),
    })

# ══════════════════════════════════════════════════════════════════════════════
# STREAM 2 — Genesis Inference premium
# Whitepaper: "No alternative exists for new asset behavioral pricing from block 1. Premium tier."
# ══════════════════════════════════════════════════════════════════════════════
@app.route("/api/v1/revenue/genesis-inference")
def stream_genesis_inference():
    if (e := auth_or_403()): return e
    asset = request.args.get("asset", "NEW_TOKEN")
    block_age = int(request.args.get("block_age", 100))   # blocks since genesis
    # Premium: highest at block 1, decays as behavioral sediment accumulates
    # Premium factor: e^(-block_age / 5000) — at block 1, ~1.0; at block 5000, ~0.37
    premium_factor = math.exp(-block_age / 5000.0)
    base_price = 25000   # USD one-time genesis inference
    premium_price = base_price * (1 + 2.0 * premium_factor)  # up to 3x at block 1
    # Query genesis_confidence_log to see how many assets are in genesis phase
    genesis_active = 0
    try:
        c = tsdb(); cur = c.cursor()
        # schema: (time, entity_id, confidence, state, inactivity_days)
        # BOOTSTRAP state = entity in genesis/bootstrap phase (per whitepaper §7)
        cur.execute("SELECT count(*) FROM genesis_confidence_log WHERE state = 'BOOTSTRAP' OR confidence < 0.30")
        genesis_active = cur.fetchone()[0]
        cur.close(); c.close()
    except Exception as ex:
        log.warning("genesis query failed: %s", ex)
    return jsonify({
        "stream": "genesis_inference_premium",
        "whitepaper_section": "15.2",
        "asset": asset,
        "block_age": block_age,
        "premium_factor": round(premium_factor, 4),
        "base_price_usd": base_price,
        "premium_price_usd": round(premium_price, 2),
        "premium_multiplier": round(premium_price / base_price, 3),
        "justification": "No alternative exists for new-asset behavioral pricing from block 1.",
        "genesis_phase_assets_active": genesis_active,
        "akashic_grounding": cached_stats(),
    })

# ══════════════════════════════════════════════════════════════════════════════
# STREAM 3 — ANIMA intelligence subscriptions
# Whitepaper: "Institutional access to Pre-Manifestation Signals, Trajectory, Institutional Behavioral signals."
# ══════════════════════════════════════════════════════════════════════════════
@app.route("/api/v1/revenue/anima-subscription")
def stream_anima_subscription():
    if (e := auth_or_403()): return e
    plan = request.args.get("plan", "INSTITUTIONAL").upper()
    seats = int(request.args.get("seats", 5))
    plans = {
        "RESEARCH":   {"price": 2_000,    "signals": ["Pre-Manifestation"], "sla": "best-effort"},
        "PRO":         {"price": 12_000,   "signals": ["Pre-Manifestation","Trajectory"], "sla": "99.5%"},
        "INSTITUTIONAL":{"price": 60_000, "signals": ["Pre-Manifestation","Trajectory","Institutional Behavioral"], "sla": "99.95%"},
    }
    if plan not in plans:
        return jsonify({"error":"unknown plan","plans":list(plans.keys())}), 400
    p = plans[plan]
    monthly = p["price"] * seats
    burn = monthly * BURN_FRACTION
    public_good = monthly * PUBLIC_GOOD_FRACTION
    # ANIMA vector count grounds the subscription value
    stats = cached_stats()
    return jsonify({
        "stream": "anima_intelligence_subscriptions",
        "whitepaper_section": "15.2",
        "plan": plan,
        "seats": seats,
        "signals_included": p["signals"],
        "sla": p["sla"],
        "monthly_per_seat_usd": p["price"],
        "monthly_total_usd": monthly,
        "annual_total_usd": monthly * 12,
        "burn_usd": round(burn, 4),
        "public_good_pool_usd": round(public_good, 4),
        "anima_vectors_indexed": stats.get("akashic_vectors", 0),
        "akashic_grounding": stats,
    })

# ══════════════════════════════════════════════════════════════════════════════
# STREAM 4 — Regulatory API
# Whitepaper: "SBA and Regulatory Behavioral signals. Public good pricing for transparent governments. Premium for commercial use."
# ══════════════════════════════════════════════════════════════════════════════
@app.route("/api/v1/revenue/regulatory-api")
def stream_regulatory_api():
    if (e := auth_or_403()): return e
    customer = request.args.get("customer_type", "COMMERCIAL").upper()  # GOV_TRANSPARENT | GOV_OPAQUE | COMMERCIAL | RESEARCH
    nations = int(request.args.get("nations_monitored", 10))
    # Public good pricing for transparent governments; premium for commercial
    base_per_nation = 5000
    if customer == "GOV_TRANSPARENT":
        discount = 0.85   # public-good pricing — 85% off
        tier = "PUBLIC_GOOD"
    elif customer == "GOV_OPAQUE":
        discount = 0.0
        tier = "STANDARD_GOV"
    elif customer == "RESEARCH":
        discount = 0.50
        tier = "ACADEMIC"
    else:  # COMMERCIAL
        discount = 0.0
        tier = "COMMERCIAL_PREMIUM"
        base_per_nation = 12000   # premium for commercial use
    monthly = base_per_nation * nations * (1 - discount)
    burn = monthly * BURN_FRACTION
    public_good = monthly * PUBLIC_GOOD_FRACTION
    return jsonify({
        "stream": "regulatory_api",
        "whitepaper_section": "15.2",
        "customer_type": customer,
        "tier": tier,
        "nations_monitored": nations,
        "base_per_nation_usd": base_per_nation,
        "public_good_discount": discount,
        "monthly_total_usd": round(monthly, 2),
        "annual_total_usd": round(monthly * 12, 2),
        "burn_usd": round(burn, 4),
        "public_good_pool_usd": round(public_good, 4),
        "signals": ["SBA", "Regulatory Behavioral"],
        "akashic_grounding": cached_stats(),
    })

# ══════════════════════════════════════════════════════════════════════════════
# STREAM 5 — Behavioral data market
# Whitepaper: "Anonymized Akashic Index access for researchers. Tiered academic vs commercial pricing."
# ══════════════════════════════════════════════════════════════════════════════
@app.route("/api/v1/revenue/data-market")
def stream_data_market():
    if (e := auth_or_403()): return e
    buyer = request.args.get("buyer_type", "ACADEMIC").upper()  # ACADEMIC | COMMERCIAL | GOV
    rows = int(request.args.get("rows_requested", 100000))
    stats = cached_stats()
    total_rows = sum(v for k, v in stats.items() if isinstance(v, int) and k != "ts")
    # Tiered: academic gets heavy discount; commercial pays full
    per_million = {"ACADEMIC": 50, "COMMERCIAL": 2500, "GOV": 500}
    if buyer not in per_million:
        return jsonify({"error":"unknown buyer_type","types":list(per_million.keys())}), 400
    price_per_m = per_million[buyer]
    cost = (rows / 1_000_000) * price_per_m
    # Anonymization fee (flat)
    anon_fee = 100 if buyer == "ACADEMIC" else 1000
    monthly = max(cost + anon_fee, 200 if buyer == "ACADEMIC" else 2000)
    burn = monthly * BURN_FRACTION
    return jsonify({
        "stream": "behavioral_data_market",
        "whitepaper_section": "15.2",
        "buyer_type": buyer,
        "rows_requested": rows,
        "akashic_total_rows": total_rows,
        "price_per_million_usd": price_per_m,
        "data_cost_usd": round(cost, 4),
        "anonymization_fee_usd": anon_fee,
        "monthly_total_usd": round(monthly, 2),
        "burn_usd": round(burn, 4),
        "public_good_pool_usd": round(monthly * PUBLIC_GOOD_FRACTION, 4),
        "akashic_grounding": stats,
    })

# ══════════════════════════════════════════════════════════════════════════════
# STREAM 6 — Developer ecosystem
# Whitepaper: "SDK licensing, integration certification, validator tooling."
# ══════════════════════════════════════════════════════════════════════════════
@app.route("/api/v1/revenue/developer-ecosystem")
def stream_developer_ecosystem():
    if (e := auth_or_403()): return e
    product = request.args.get("product", "SDK_LICENSE").upper()
    # SDK_LICENSE | INTEGRATION_CERT | VALIDATOR_TOOLING
    products = {
        "SDK_LICENSE":        {"price": 499,   "unit": "per year",       "desc": "TypeScript/Rust/Python SDK license"},
        "INTEGRATION_CERT":   {"price": 15000, "unit": "per integration", "desc": "Integration certification (per protocol)"},
        "VALIDATOR_TOOLING": {"price": 25000, "unit": "per year",       "desc": "Validator tooling + dashboard"},
        "ENTERPRISE_SDK":    {"price": 75000, "unit": "per year",       "desc": "White-label SDK + support"},
    }
    if product not in products:
        return jsonify({"error":"unknown product","products":list(products.keys())}), 400
    p = products[product]
    quantity = int(request.args.get("quantity", 1))
    total = p["price"] * quantity
    burn = total * BURN_FRACTION
    return jsonify({
        "stream": "developer_ecosystem",
        "whitepaper_section": "15.2",
        "product": product,
        "description": p["desc"],
        "unit_price_usd": p["price"],
        "unit": p["unit"],
        "quantity": quantity,
        "total_usd": round(total, 2),
        "burn_usd": round(burn, 4),
        "public_good_pool_usd": round(total * PUBLIC_GOOD_FRACTION, 4),
        "akashic_grounding": cached_stats(),
    })

# ══════════════════════════════════════════════════════════════════════════════
# Aggregate revenue projection (all 6 streams) — for the report
# ══════════════════════════════════════════════════════════════════════════════
@app.route("/api/v1/revenue/aggregate")
def revenue_aggregate():
    if (e := auth_or_403()): return e
    stats = cached_stats()
    # Hypothetical customer mix
    mix = {
        "signal_consumption": {"stream": 1, "monthly_usd": 4999 * 5 + 999 * 20 + 99 * 100},
        "genesis_inference":  {"stream": 2, "monthly_usd": 75000 * 1},   # 3 premium genesis / month
        "anima_subscription": {"stream": 3, "monthly_usd": 60000 * 2 + 12000 * 10 + 2000 * 50},
        "regulatory_api":     {"stream": 4, "monthly_usd": 5000 * 50 * 0.15 + 12000 * 50 * 0.5},
        "data_market":        {"stream": 5, "monthly_usd": 2500 * 10 + 50 * 100},
        "developer_ecosystem":{"stream": 6, "monthly_usd": 499 * 500 + 15000 * 5 + 25000 * 20},
    }
    total_mrr = sum(v["monthly_usd"] for v in mix.values())
    arr = total_mrr * 12
    burn = total_mrr * BURN_FRACTION
    public_good = total_mrr * PUBLIC_GOOD_FRACTION
    unknown_reserve = total_mrr * UNKNOWN_BUDGET_FRACTION
    return jsonify({
        "whitepaper_section": "15.2",
        "streams": mix,
        "total_mrr_usd": round(total_mrr, 2),
        "arr_usd": round(arr, 2),
        "burn_per_month_usd": round(burn, 2),
        "public_good_pool_monthly_usd": round(public_good, 2),
        "unknown_unknown_reserve_monthly_usd": round(unknown_reserve, 2),
        "token_economics": {
            "total_supply": TOTAL_SUPPLY,
            "burn_fraction_per_use": BURN_FRACTION,
            "public_good_fraction": PUBLIC_GOOD_FRACTION,
            "unknown_budget_fraction": UNKNOWN_BUDGET_FRACTION,
            "deflationary": True,
            "inflation_mechanism": "NONE",
        },
        "akashic_grounding": stats,
        "timestamp": datetime.now(timezone.utc).isoformat(),
    })

@app.route("/healthz")
@app.route("/health")
def health():
    return jsonify({"status": "ok", "service": "trion-revenue-model", "port": 5001,
                    "streams": 6, "akashic_connected": bool(cached_stats().get("akashic_bh"))})

if __name__ == "__main__":
    log.info("TRION Revenue Model Service starting on port 5001 (LOCAL ONLY — not in git)")
    app.run(host="127.0.0.1", port=5001, debug=False)
