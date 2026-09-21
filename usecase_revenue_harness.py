#!/usr/bin/env python3
"""
TRION Use-Case + Revenue Model Test Harness
==========================================
Tests the TRION whitepaper use cases ("100 Use Cases of TRION Nobody Imagined")
against the live system (Oracle API :5000, ANIMA FAISS :8000, TimescaleDB
Akashic Index) AND the whitepaper §15.2 Revenue Model (6 streams × 20 iterations).

Part A — 20 representative use cases (2 per domain × 10 domains):
  Finance, Governance, Healthcare, Environment, Education, Humanitarian,
  AI, Science, Culture, Infrastructure

Part B — 6 revenue streams × 20 iterations = 120 revenue-model tests:
  1. Signal consumption fees
  2. Genesis Inference premium
  3. ANIMA intelligence subscriptions
  4. Regulatory API
  5. Behavioral data market
  6. Developer ecosystem

Output: JSON + Markdown report.
"""
import os, sys, json, time, statistics, hashlib, urllib.parse, urllib.request, urllib.error
from datetime import datetime, timezone

ORACLE = "http://127.0.0.1:5000"
ANIMA  = "http://127.0.0.1:8000"
REV    = "http://127.0.0.1:5001"
ORACLE_KEY = "test-audit-key"
ANIMA_KEY  = "trion-audit-key"
REV_KEY    = "test-audit-key"

# Sample entities (realistic EVM addresses + nation codes)
ENTITIES = [
    "0xd8dA6BF26964aF9D7eEd9e03E53415D37aA96045",  # vitalik.eth
    "0x28C6c06298d514Db089934071355E5743bf21d60",  # Binance 14
    "0xA0b86991c6218b36c1d19D4a2e9Eb0cE3606eB48",  # USDC
    "0x5B14a5b0f7b1d3d2c5a8f9e1b4c7d0a3f6e9b2c5",  # synthetic
    "0x6B175474E89094C44Da98b954EedeAC495271d0F",  # DAI
]
NATIONS = ["NG","US","GB","JP","BR","DE","KE","IN","AU","CA"]

results = {"start_ts": time.time(), "use_cases": [], "revenue_streams": [], "summary": {}}

def get(url, key=None, timeout=20):
    headers = {}
    if key:
        headers["X-API-Key"] = key
    req = urllib.request.Request(url, headers=headers)
    t0 = time.time()
    try:
        with urllib.request.urlopen(req, timeout=timeout) as r:
            body = r.read().decode("utf-8", errors="replace")
            try: data = json.loads(body)
            except: data = {"_raw": body[:500]}
            return {"ok": True, "status": r.status, "data": data, "ms": int((time.time()-t0)*1000)}
    except urllib.error.HTTPError as e:
        body = e.read().decode("utf-8", errors="replace")[:300]
        return {"ok": False, "status": e.code, "error": body, "ms": int((time.time()-t0)*1000)}
    except Exception as e:
        return {"ok": False, "status": 0, "error": str(e)[:200], "ms": int((time.time()-t0)*1000)}

# ────────────────────────────────────────────────────────────────────────────
# PART A — USE CASE TESTS (20 representative, 2 per domain × 10 domains)
# ────────────────────────────────────────────────────────────────────────────
USE_CASES = [
    # FINANCE & ECONOMICS (1-15)
    {"id":1,"domain":"Finance","title":"Behavioral Flash Crash Predictor",
     "endpoints":[("/api/v1/signal/{}","ORACLE"),("/api/v1/audit/patterns","ORACLE")],
     "entity":0,"verify": lambda r: r[0]["ok"] and "manipulation_fingerprint" in str(r[0]["data"])},
    {"id":3,"domain":"Finance","title":"Insurance Premium Behavioral Engine",
     "endpoints":[("/api/v1/signal/{}","ORACLE"),("/api/v1/akashic/match/{}","ORACLE")],
     "entity":0,"verify": lambda r: r[0]["ok"] and "coherence_score" in r[0]["data"]},
    # GOVERNANCE & DEMOCRACY (16-25)
    {"id":16,"domain":"Governance","title":"On-Chain Voter Behavioral Verification",
     "endpoints":[("/api/v1/planes/{}/all","ORACLE"),("/api/v1/reputation/{}","ORACLE")],
     "entity":1,"verify": lambda r: r[0]["ok"] and "planes" in r[0]["data"]},
    {"id":21,"domain":"Governance","title":"UN Sanctions Behavioral Monitoring",
     "endpoints":[("/api/v1/audit/{}","ORACLE"),("/api/v1/akashic/match/{}","ORACLE")],
     "entity":1,"verify": lambda r: r[0]["ok"]},
    # HEALTHCARE & LIFE SCIENCES (26-35)
    {"id":29,"domain":"Healthcare","title":"Clinical Trial Behavioral Integrity",
     "endpoints":[("/api/v1/thermodynamics/{}","ORACLE"),("/api/v1/akashic/epigenetics/{}","ORACLE")],
     "entity":0,"verify": lambda r: r[1]["ok"] and "methylation_pattern" in r[1]["data"]},
    {"id":26,"domain":"Healthcare","title":"Pharma Supply Chain Behavioral Auth",
     "endpoints":[("/api/v1/signal/{}","ORACLE"),("/api/v1/akashic/epigenetics/{}","ORACLE")],
     "entity":2,"verify": lambda r: r[0]["ok"]},
    # ENVIRONMENT & CLIMATE (36-44)
    {"id":36,"domain":"Environment","title":"Carbon Credit Behavioral Verification",
     "endpoints":[("/api/v1/xsl/{}","ORACLE"),("/api/v1/akashic/match/{}","ORACLE")],
     "entity":2,"verify": lambda r: r[0]["ok"]},
    {"id":37,"domain":"Environment","title":"Behavioral Deforestation Financial Tracking",
     "endpoints":[("/api/v1/audit/{}","ORACLE"),("/api/v1/thermodynamics/{}","ORACLE")],
     "entity":3,"verify": lambda r: r[0]["ok"]},
    # EDUCATION & RESEARCH (45-52)
    {"id":45,"domain":"Education","title":"Behavioral Academic Credential Verification",
     "endpoints":[("/api/v1/ubl/{}","ORACLE"),("/api/v1/reputation/{}","ORACLE")],
     "entity":4,"verify": lambda r: r[0]["ok"]},
    {"id":46,"domain":"Education","title":"Research Data Behavioral Integrity",
     "endpoints":[("/api/v1/thermodynamics/{}","ORACLE"),("/api/v1/akashic/epigenetics/{}","ORACLE")],
     "entity":4,"verify": lambda r: r[0]["ok"]},
    # HUMANITARIAN & HUMAN RIGHTS (53-61)
    {"id":60,"domain":"Humanitarian","title":"Stateless Person Behavioral Passport",
     "endpoints":[("/api/v1/ubl/{}","ORACLE"),("/api/v1/planes/{}/all","ORACLE")],
     "entity":0,"verify": lambda r: r[0]["ok"] and "ubl" in str(r[0]["data"]).lower()},
    {"id":55,"domain":"Humanitarian","title":"Behavioral Refugee Integration Assessment",
     "endpoints":[("/api/v1/sba/{}","ORACLE"),("/api/v1/akashic/match/{}","ORACLE")],
     "entity":None,"nation":0,"verify": lambda r: r[0]["ok"] and "SBA" in str(r[0]["data"])},
    # ARTIFICIAL INTELLIGENCE (62-70)
    {"id":62,"domain":"AI","title":"AI Agent Behavioral Certification",
     "endpoints":[("/api/v1/agent/validate","ORACLE")],
     "entity":None,"method":"POST","post":{"agent_id":"agent-001","coherence":0.85,"actions":100},
     "verify": lambda r: r[0]["ok"]},
    {"id":68,"domain":"AI","title":"Behavioral Turing Test for Financial Actors",
     "endpoints":[("/api/v1/signal/{}","ORACLE"),("/api/v1/manipulation/fingerprint/{}","ANIMA")],
     "entity":0,"verify": lambda r: r[0]["ok"]},
    # SCIENCE & RESEARCH FRONTIERS (71-78)
    {"id":74,"domain":"Science","title":"Behavioral Archaeology Digital Culture",
     "endpoints":[("/api/v1/lifecycle/{}","ORACLE"),("/api/v1/akashic/match/{}","ORACLE")],
     "entity":0,"verify": lambda r: r[0]["ok"]},
    {"id":77,"domain":"Science","title":"Behavioral Quantum Computing Verification",
     "endpoints":[("/api/v1/thermodynamics/{}","ORACLE"),("/api/v1/security/complexity/{}","ORACLE")],
     "entity":1,"verify": lambda r: r[0]["ok"]},
    # CULTURE, MEDIA & IDENTITY (79-87)
    {"id":80,"domain":"Culture","title":"Behavioral Art Provenance",
     "endpoints":[("/api/v1/akashic/match/{}","ORACLE"),("/api/v1/akashic/epigenetics/{}","ORACLE")],
     "entity":2,"verify": lambda r: r[0]["ok"] and "archetype" in str(r[0]["data"])},
    {"id":82,"domain":"Culture","title":"Behavioral Sports Betting Integrity",
     "endpoints":[("/api/v1/signal/{}","ORACLE"),("/api/v1/audit/{}","ORACLE")],
     "entity":3,"verify": lambda r: r[0]["ok"]},
    # INFRASTRUCTURE & PHYSICAL WORLD (88-94)
    {"id":88,"domain":"Infrastructure","title":"Smart City Behavioral Resource Allocation",
     "endpoints":[("/api/v1/sba/{}","ORACLE"),("/api/v1/reputation/{}","ORACLE")],
     "entity":None,"nation":1,"verify": lambda r: r[0]["ok"]},
    {"id":94,"domain":"Infrastructure","title":"Behavioral Critical Infrastructure Protection",
     "endpoints":[("/api/v1/security/sec","ORACLE"),("/api/v1/planes/{}/all","ORACLE")],
     "entity":4,"verify": lambda r: r[0]["ok"]},
]

def run_use_case(uc):
    eid = ENTITIES[uc["entity"]] if uc.get("entity") is not None else None
    nation = NATIONS[uc["nation"]] if uc.get("nation") is not None else None
    responses = []
    for path, svc in uc["endpoints"]:
        if "{}" in path:
            arg = nation if nation is not None else eid
            if arg is None: continue
            url = path.format(arg)
        else:
            url = path
        base = {"ORACLE":ORACLE,"ANIMA":ANIMA}[svc]
        key = ORACLE_KEY if svc=="ORACLE" else ANIMA_KEY
        if uc.get("method") == "POST":
            # simple POST
            t0=time.time()
            import urllib.request as ur
            data = json.dumps(uc["post"]).encode()
            req = ur.Request(base+url, data=data, headers={"X-API-Key":key,"Content-Type":"application/json"}, method="POST")
            try:
                with ur.urlopen(req, timeout=20) as r:
                    body=r.read().decode()
                    try: d=json.loads(body)
                    except: d={"_raw":body[:300]}
                    responses.append({"ok":True,"status":r.status,"data":d,"ms":int((time.time()-t0)*1000)})
            except Exception as e:
                responses.append({"ok":False,"error":str(e)[:200],"ms":int((time.time()-t0)*1000)})
        else:
            responses.append(get(base+url, key=key))
    passed = False
    err = ""
    try:
        passed = uc["verify"](responses) if responses else False
    except Exception as e:
        err = str(e)[:200]
    return {
        "id": uc["id"], "domain": uc["domain"], "title": uc["title"],
        "passed": passed, "error": err,
        "endpoints_hit": len(responses),
        "latencies_ms": [r.get("ms",0) for r in responses],
        "response_snippets": [
            {"status": r.get("status"), "ok": r.get("ok"),
             "snippet": (json.dumps(r.get("data",{}))[:200] if r.get("data") else r.get("error",""))[:200]}
            for r in responses
        ],
    }

# ────────────────────────────────────────────────────────────────────────────
# PART B — REVENUE MODEL TESTS (6 streams × 20 iterations)
# ────────────────────────────────────────────────────────────────────────────
REVENUE_STREAMS = [
    {"name":"Signal consumption fees","endpoint":"/api/v1/revenue/signal-consumption",
     "params_gen": lambda i: {"tvl_usd": [100_000, 5_000_000, 50_000_000, 500_000_000, 5_000_000_000][i%5],
                              "calls_per_month": [1000, 10_000, 100_000, 1_000_000][i%4]},
     "verify": lambda d: "tier" in d and "monthly_total_usd" in d},
    {"name":"Genesis Inference premium","endpoint":"/api/v1/revenue/genesis-inference",
     "params_gen": lambda i: {"asset": f"TOKEN_{i}", "block_age": [1, 10, 100, 1000, 5000, 10000, 50000][i%7]},
     "verify": lambda d: "premium_price_usd" in d and "premium_factor" in d},
    {"name":"ANIMA intelligence subscriptions","endpoint":"/api/v1/revenue/anima-subscription",
     "params_gen": lambda i: {"plan": ["RESEARCH","PRO","INSTITUTIONAL"][i%3], "seats": (i%20)+1},
     "verify": lambda d: "monthly_total_usd" in d and "signals_included" in d},
    {"name":"Regulatory API","endpoint":"/api/v1/revenue/regulatory-api",
     "params_gen": lambda i: {"customer_type": ["GOV_TRANSPARENT","GOV_OPAQUE","COMMERCIAL","RESEARCH"][i%4],
                              "nations_monitored": (i%50)+1},
     "verify": lambda d: "tier" in d and "monthly_total_usd" in d},
    {"name":"Behavioral data market","endpoint":"/api/v1/revenue/data-market",
     "params_gen": lambda i: {"buyer_type": ["ACADEMIC","COMMERCIAL","GOV"][i%3],
                              "rows_requested": [10_000, 100_000, 1_000_000, 10_000_000][i%4]},
     "verify": lambda d: "monthly_total_usd" in d and "price_per_million_usd" in d},
    {"name":"Developer ecosystem","endpoint":"/api/v1/revenue/developer-ecosystem",
     "params_gen": lambda i: {"product": ["SDK_LICENSE","INTEGRATION_CERT","VALIDATOR_TOOLING","ENTERPRISE_SDK"][i%4],
                              "quantity": (i%10)+1},
     "verify": lambda d: "total_usd" in d and "unit_price_usd" in d},
]

def run_revenue_stream(stream, n=20):
    iters = []
    for i in range(n):
        params = stream["params_gen"](i)
        qs = urllib.parse.urlencode(params)
        url = REV + stream["endpoint"] + "?" + qs
        r = get(url, key=REV_KEY)
        passed = False
        pricing = None
        if r["ok"]:
            try:
                passed = stream["verify"](r["data"])
                pricing = {
                    "monthly_total_usd": r["data"].get("monthly_total_usd") or r["data"].get("total_usd"),
                    "tier": r["data"].get("tier"),
                    "burn_usd": r["data"].get("burn_usd"),
                }
            except Exception as e:
                passed = False
        iters.append({
            "i": i, "params": params, "ok": r["ok"], "passed": passed,
            "ms": r["ms"], "status": r.get("status"),
            "pricing": pricing,
            "error": r.get("error",""),
        })
    passed_count = sum(1 for x in iters if x["passed"])
    revenues = [x["pricing"]["monthly_total_usd"] for x in iters if x["pricing"] and x["pricing"]["monthly_total_usd"] is not None]
    return {
        "stream": stream["name"], "endpoint": stream["endpoint"],
        "iterations": n, "passed": passed_count, "failed": n - passed_count,
        "pass_rate": round(passed_count/n*100, 1),
        "latency_ms_avg": round(statistics.mean(x["ms"] for x in iters), 1),
        "latency_ms_max": max(x["ms"] for x in iters),
        "revenue_min_usd": round(min(revenues),2) if revenues else 0,
        "revenue_max_usd": round(max(revenues),2) if revenues else 0,
        "revenue_avg_usd": round(statistics.mean(revenues),2) if revenues else 0,
        "iterations_detail": iters,
    }

def main():
    print("="*70)
    print("TRION USE-CASE + REVENUE MODEL TEST HARNESS")
    print("="*70)

    # Preflight checks
    print("\n[0] Preflight service checks...")
    for name, url, key in [("Oracle",ORACLE+"/api/v1/health",ORACLE_KEY),
                           ("ANIMA",ANIMA+"/health",None),
                           ("Revenue",REV+"/health",None)]:
        r = get(url, key=key)
        print(f"  {name:8s} status={r.get('status')} ok={r['ok']} ms={r['ms']}")
        if not r["ok"]:
            print(f"  !! {name} not reachable: {r.get('error')}")
            print("  Aborting. Start services first: bash dev_services.sh && python3 revenue_model_service.py &")
            return

    # PART A — Use cases
    print(f"\n[1] Running {len(USE_CASES)} use-case tests (2 per domain × 10 domains)...")
    uc_results = []
    for uc in USE_CASES:
        res = run_use_case(uc)
        uc_results.append(res)
        mark = "✓" if res["passed"] else "✗"
        print(f"  {mark} UC#{res['id']:>3} [{res['domain']:<14}] {res['title'][:48]:<48} ({sum(res['latencies_ms'])}ms)")
    results["use_cases"] = uc_results
    uc_pass = sum(1 for r in uc_results if r["passed"])
    print(f"  Use cases passed: {uc_pass}/{len(uc_results)} ({round(uc_pass/len(uc_results)*100,1)}%)")

    # PART B — Revenue model
    print(f"\n[2] Running revenue-model tests: 6 streams × 20 iterations = 120 tests...")
    rev_results = []
    for s in REVENUE_STREAMS:
        res = run_revenue_stream(s, n=20)
        rev_results.append(res)
        mark = "✓" if res["passed"]==res["iterations"] else "○"
        print(f"  {mark} {res['stream']:<36} {res['passed']:>2}/{res['iterations']} pass "
              f"avg={res['latency_ms_avg']}ms rev_avg=${res['revenue_avg_usd']}")
    results["revenue_streams"] = rev_results
    rev_total_tests = sum(r["iterations"] for r in rev_results)
    rev_total_pass = sum(r["passed"] for r in rev_results)
    print(f"  Revenue tests passed: {rev_total_pass}/{rev_total_tests} ({round(rev_total_pass/rev_total_tests*100,1)}%)")

    # Aggregate revenue projection
    print("\n[3] Fetching aggregate revenue projection...")
    agg = get(REV+"/api/v1/revenue/aggregate", key=REV_KEY)
    results["aggregate_revenue"] = agg.get("data",{}) if agg["ok"] else {"error":agg.get("error")}
    if agg["ok"]:
        d = agg["data"]
        print(f"  Projected MRR: ${d.get('total_mrr_usd',0):,.2f}")
        print(f"  Projected ARR: ${d.get('arr_usd',0):,.2f}")
        print(f"  Burn/month:    ${d.get('burn_per_month_usd',0):,.2f}")
        print(f"  Public good:   ${d.get('public_good_pool_monthly_usd',0):,.2f}")

    # Summary
    results["summary"] = {
        "use_cases_total": len(uc_results),
        "use_cases_passed": uc_pass,
        "use_cases_pass_rate": round(uc_pass/len(uc_results)*100,1),
        "revenue_tests_total": rev_total_tests,
        "revenue_tests_passed": rev_total_pass,
        "revenue_tests_pass_rate": round(rev_total_pass/rev_total_tests*100,1),
        "revenue_streams_operational": sum(1 for r in rev_results if r["passed"]==r["iterations"]),
        "revenue_streams_partial": sum(1 for r in rev_results if 0<r["passed"]<r["iterations"]),
        "revenue_streams_failed": sum(1 for r in rev_results if r["passed"]==0),
        "end_ts": time.time(),
        "duration_s": round(time.time()-results["start_ts"],1),
    }
    print("\n" + "="*70)
    print(f"DONE in {results['summary']['duration_s']}s")
    print(f"  Use cases:    {uc_pass}/{len(uc_results)} passed")
    print(f"  Revenue tests:{rev_total_pass}/{rev_total_tests} passed")
    print(f"  Streams fully operational: {results['summary']['revenue_streams_operational']}/6")
    print("="*70)

    # Write reports
    with open("usecase_revenue_report.json","w") as f:
        json.dump(results, f, indent=2, default=str)
    print("  Wrote usecase_revenue_report.json")

if __name__ == "__main__":
    main()
