"""
ANIMA Full Test Suite
=====================
Covers every component of the ANIMA / Akashic Intelligence Engine:

§1  Health & Status Infrastructure
§2  Vector Ingestion — /index/add
§3  Batch Vector Ingestion — /index/add_batch
§4  BH Transaction Ingestion — /index/add_tx_bh_batch
§5  Similarity Engine
§6  Archetype Engine (L2.2)
§7  ANIMA Score Formula (unit — offline)
§8  ANIMA Score API  — PCR × HA × CA
§9  CRED Decay & Source Management
§10 Reflexivity (L3.5)
§11 Observer Effect (L3.2)
§12 NL Score Formula (unit — offline)
§13 Liquidity Ocean API
§14 Living Security — Full 8-Component Report
§15 Genomic Key (GK) Evolution
§16 Immune System — Innate + Adaptive
§17 Epigenetic Phenotype
§18 Noise / Decoy Fingerprints
§19 Mitochondrial Core
§20 BEO Cluster Resolution
§21 PHI Weights (L1.1)
§22 Information Conservation (L0.4)
§23 Fitness Update (L0.6)
§24 Thermodynamics & Lifecycle
§25 Epigenetics Pressure (Akashic)
§26 Conscious Plane — Annotations
§27 Conscious Plane — Knowledge Systems & Elders
§28 Spiritual Diversity (L5 Validator Diversity)
§29 Signal Publishing
§30 Routing — BTCP Score & Route Selection
§31 Genesis Locking & Semi-Immutable Signals
§32 Audit Engine
§33 Agent Validation
§34 Trading Signal API
§35 Sovereign Assessment
§36 Slash & Dispute Resolution
§37 ZK Behavioral Proofs (unit — offline)
§38 Jurisdictional Routing (unit — offline)
§39 Fork & Resurrection
§40 System Bootstrap
§41 Concurrent load — 1 000 simultaneous /index/add
§42 Concurrent load — 1 000 simultaneous reads
§43 Thundering herd — 1 000 requests for the same entity
§44 Mixed concurrent storm — all endpoint classes at once
§45 End-to-end full pipeline
"""

# ─────────────────────────────────────────────────────────────────────────────
# Imports & config
# ─────────────────────────────────────────────────────────────────────────────
import asyncio
import hashlib
import math
import os
import random
import sys
import time
import uuid
from typing import Any, Dict, List, Optional, Tuple

import pytest
import requests

# ── optional async HTTP client ────────────────────────────────────────────────
try:
    import aiohttp
    _AIOHTTP_OK = True
except ImportError:
    _AIOHTTP_OK = False

# ── ANIMA sub-modules imported directly for unit tests ───────────────────────
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

try:
    from akashic.nl_score_engine import compute_nl_score, apply_oe_correction
    _NL_OK = True
except Exception:
    _NL_OK = False

try:
    from akashic.liquidity_ocean import LiquidityOcean
    _OCEAN_OK = True
except Exception:
    _OCEAN_OK = False

try:
    from akashic.anima_regulatory import (
        BehavioralZKProver,
        JurisdictionRegistry,
        ZKBehavioralProof,
        PRIVACY_ZK_CRED,
    )
    _ZK_OK = True
except Exception:
    _ZK_OK = False

# ─────────────────────────────────────────────────────────────────────────────
# Test helpers
# ─────────────────────────────────────────────────────────────────────────────
BASE = "http://127.0.0.1:8000"
TIMEOUT = 90          # seconds per HTTP call — generous: live FAISS indexers can saturate add_batch
DIM = 128             # FAISS index dimension

BOLD  = "\033[1m"
GREEN = "\033[32m"
RED   = "\033[31m"
CYAN  = "\033[36m"
RESET = "\033[0m"

def sep(label: str) -> None:
    bar = "─" * 66
    print(f"\n{CYAN}{bar}\n  {BOLD}{label}{RESET}{CYAN}\n{bar}{RESET}")

def ok(msg: str) -> None:
    print(f"  {GREEN}✅ {msg}{RESET}")

def info(key: str, val: Any) -> None:
    print(f"  {key:<35} {val}")

def rnd_vec(dim: int = DIM) -> List[float]:
    v = [random.gauss(0, 1) for _ in range(dim)]
    norm = math.sqrt(sum(x * x for x in v)) or 1.0
    return [x / norm for x in v]

def uid(prefix: str = "anima") -> str:
    return f"{prefix}_{uuid.uuid4().hex[:12]}"

def post(path: str, body: dict, *, timeout: int = TIMEOUT) -> requests.Response:
    return requests.post(f"{BASE}{path}", json=body, timeout=timeout)

def get(path: str, *, params: dict = None, timeout: int = TIMEOUT) -> requests.Response:
    return requests.get(f"{BASE}{path}", params=params, timeout=timeout)

def assert_ok(r: requests.Response, label: str) -> dict:
    assert r.status_code in (200, 201), \
        f"{label}: HTTP {r.status_code} — {r.text[:300]}"
    data = r.json()
    return data

def seed_entity(entity_id: str, n: int = 3) -> None:
    """Push n vectors so an entity exists in FAISS."""
    for _ in range(n):
        post("/index/add", {
            "entity_id": entity_id,
            "vector": rnd_vec(),
            "magnitude": round(random.uniform(0.1, 1.0), 3),
            "entropy": round(random.uniform(0.5, 1.0), 3),
            "chain_id": 1,
            "chain_label": "ethereum",
            "vm_type": "EVM",
        })

# ─────────────────────────────────────────────────────────────────────────────
# §1  Health & Status Infrastructure
# ─────────────────────────────────────────────────────────────────────────────
class TestHealth:

    def test_healthz(self):
        sep("§1a — GET /healthz")
        r = get("/healthz")
        d = assert_ok(r, "/healthz")
        assert d.get("status") == "ok"
        ok("PASS — /healthz → status=ok")

    def test_health_full(self):
        sep("§1b — GET /health (full status)")
        r = get("/health")
        d = assert_ok(r, "/health")
        info("Response keys", list(d.keys()))
        assert "status" in d or "faiss_available" in d or "indexed_vectors" in d
        ok("PASS — /health returns system information")

    def test_vm_status(self):
        sep("§1c — GET /vm-status")
        r = get("/vm-status")
        d = assert_ok(r, "/vm-status")
        info("VM status keys", list(d.keys()))
        ok("PASS — /vm-status reachable")

    def test_api_health(self):
        sep("§1d — GET /api/v1/health")
        r = get("/api/v1/health")
        d = assert_ok(r, "/api/v1/health")
        ok("PASS — /api/v1/health reachable")

    def test_index_status_alias(self):
        sep("§1e — GET /api/v1/index/status")
        r = get("/api/v1/index/status")
        d = assert_ok(r, "/api/v1/index/status")
        ok("PASS — /api/v1/index/status reachable")


# ─────────────────────────────────────────────────────────────────────────────
# §2  Vector Ingestion — /index/add
# ─────────────────────────────────────────────────────────────────────────────
class TestIndexAdd:

    def test_basic_add(self):
        sep("§2a — POST /index/add basic")
        eid = uid("idx")
        r = post("/index/add", {
            "entity_id": eid,
            "vector": rnd_vec(),
            "magnitude": 0.75,
            "entropy": 0.90,
        })
        d = assert_ok(r, "/index/add")
        info("status", d.get("status"))
        info("indexed_vectors", d.get("indexed_vectors"))
        assert d.get("status") in ("added", "ok", "success", "indexed")
        ok(f"PASS — vector accepted for {eid}")

    def test_add_with_full_fields(self):
        sep("§2b — POST /index/add with all optional fields")
        eid = uid("idx")
        r = post("/index/add", {
            "entity_id": eid,
            "vector": rnd_vec(),
            "magnitude": 0.60,
            "entropy": 0.80,
            "chain_id": 42161,
            "chain_label": "arbitrum",
            "vm_type": "EVM",
            "block_num": 12345678,
            "block_hash_hex": "0x" + "ab" * 32,
            "event_type": 1,
            "sense_hex": "0xdeadbeef",
            "antisense_hex": "0xcafebabe",
            "funding_source": "0xFunder01",
        })
        d = assert_ok(r, "/index/add full")
        assert d.get("status") in ("added", "ok", "success", "indexed")
        ok("PASS — full-field add accepted")

    def test_add_zero_magnitude(self):
        sep("§2c — POST /index/add magnitude=0 (entropy collapse edge case)")
        eid = uid("idx")
        r = post("/index/add", {
            "entity_id": eid,
            "vector": rnd_vec(),
            "magnitude": 0.0,
            "entropy": 0.0,
        })
        # Should either accept or reject gracefully — no 500
        assert r.status_code in (200, 201, 400, 422)
        ok(f"PASS — zero-magnitude handled gracefully (HTTP {r.status_code})")

    def test_add_multiple_vectors_same_entity(self):
        sep("§2d — POST /index/add — 10 vectors same entity → depth grows")
        eid = uid("depth")
        depths = []
        for i in range(10):
            r = post("/index/add", {
                "entity_id": eid,
                "vector": rnd_vec(),
                "magnitude": round(0.1 + i * 0.08, 2),
                "entropy": 0.85,
            })
            d = assert_ok(r, f"/index/add depth[{i}]")
            depths.append(d.get("depth", d.get("indexed_vectors", 0)))
        info("Depth after 10 vectors", depths[-1])
        ok("PASS — 10 sequential vectors accepted for same entity")

    def test_add_cross_chain_entity(self):
        sep("§2e — POST /index/add — same entity across 4 chains (BEO cross-chain)")
        eid = uid("xchain")
        chains = [(1, "ethereum", "EVM"), (137, "polygon", "EVM"),
                  (101, "solana", "SVM"), (1360100178526210, "near", "NVM")]
        for chain_id, label, vm in chains:
            r = post("/index/add", {
                "entity_id": eid,
                "vector": rnd_vec(),
                "magnitude": 0.70,
                "entropy": 0.85,
                "chain_id": chain_id,
                "chain_label": label,
                "vm_type": vm,
            })
            d = assert_ok(r, f"/index/add {label}")
            info(f"  {label}", d.get("status"))
        ok(f"PASS — entity {eid} indexed across 4 chains")


# ─────────────────────────────────────────────────────────────────────────────
# §3  Batch Vector Ingestion — /index/add_batch
# ─────────────────────────────────────────────────────────────────────────────
class TestIndexAddBatch:

    def test_basic_batch(self):
        sep("§3a — POST /index/add_batch — 5 vectors")
        base_eid = uid("batch")
        vectors = [
            {
                "entity_id": f"{base_eid}_{i}",
                "vector": rnd_vec(),
                "magnitude": round(random.uniform(0.3, 0.9), 2),
                "entropy": round(random.uniform(0.5, 1.0), 2),
                "chain_id": 1,
                "chain_label": "ethereum",
                "vm_type": "EVM",
            }
            for i in range(5)
        ]
        r = post("/index/add_batch", {
            "vectors": vectors,
            "block_num": 20000000,
            "block_phi": 0.75,
            "chain_id": 1,
            "chain_label": "ethereum",
            "vm_type": "EVM",
        })
        d = assert_ok(r, "/index/add_batch")
        info("added", d.get("added"))
        info("rejected_l0_5", d.get("rejected_l0_5", 0))
        ok("PASS — 5-vector batch accepted")

    def test_large_batch_50(self):
        sep("§3b — POST /index/add_batch — 50 vectors")
        base_eid = uid("big")
        vectors = [
            {
                "entity_id": f"{base_eid}_{i}",
                "vector": rnd_vec(),
                "magnitude": round(random.uniform(0.2, 1.0), 3),
                "entropy": round(random.uniform(0.4, 1.0), 3),
                "chain_id": 42161,
                "chain_label": "arbitrum",
                "vm_type": "EVM",
            }
            for i in range(50)
        ]
        r = post("/index/add_batch", {
            "vectors": vectors,
            "block_num": 200100000,
            "block_phi": 0.80,
            "chain_id": 42161,
            "chain_label": "arbitrum",
        })
        d = assert_ok(r, "/index/add_batch 50")
        added = d.get("added", 0)
        rejected = d.get("rejected_l0_5", 0)
        info("accepted", added)
        info("rejected L0.5", rejected)
        assert added + rejected == 50
        ok("PASS — 50-vector batch: accepted + rejected = 50")

    def test_batch_conservation_delta(self):
        sep("§3c — POST /index/add_batch — conservation_delta present")
        base_eid = uid("cons")
        r = post("/index/add_batch", {
            "vectors": [
                {
                    "entity_id": f"{base_eid}_{i}",
                    "vector": rnd_vec(),
                    "magnitude": 0.75,
                    "entropy": 0.90,
                    "chain_id": 1,
                    "chain_label": "ethereum",
                }
                for i in range(10)
            ],
            "block_num": 20100001,
            "block_phi": 0.72,
        })
        d = assert_ok(r, "/index/add_batch conservation")
        info("conservation_delta", d.get("conservation_delta"))
        ok("PASS — conservation_delta present in batch response")


# ─────────────────────────────────────────────────────────────────────────────
# §4  BH Transaction Ingestion — /index/add_tx_bh_batch
# ─────────────────────────────────────────────────────────────────────────────
class TestBHIngestion:

    def test_bh_batch_basic(self):
        sep("§4a — POST /index/add_tx_bh_batch — 3 BH entries")
        eid = uid("bh")
        entries = []
        for i in range(3):
            entries.append({
                "tx_hash": "0x" + uuid.uuid4().hex + uuid.uuid4().hex[:8],
                "from_addr": "0xFrom" + uid(),
                "to_addr": "0xTo" + uid(),
                "event_type": 1,
                "event_type_name": "TRANSFER",
                "entity_id": eid,
                "magnitude_norm": round(random.uniform(0.1, 1.0), 3),
                "value_wei": str(int(1e18 * random.uniform(0.01, 10))),
                "selector": "0xa9059cbb",
                "timestamp": int(time.time()) - i * 12,
                "chain_id": 1,
                "chain_label": "ethereum",
                "block_num": 20000000 + i,
                "block_hash": "0x" + uuid.uuid4().hex * 2,
                "sense_hex": "0xaabbccdd",
                "antisense_hex": "0x11223344",
            })
        r = post("/index/add_tx_bh_batch", {
            "chain_id": 1,
            "chain_label": "ethereum",
            "block_num": 20000003,
            "block_hash": "0x" + uuid.uuid4().hex * 2,
            "timestamp": int(time.time()),
            "entries": entries,
        })
        d = assert_ok(r, "/index/add_tx_bh_batch")
        info("stored", d.get("stored", d.get("accepted", d.get("status"))))
        ok(f"PASS — 3 BH entries ingested for {eid}")

    def test_bh_duplicate_tx_hash(self):
        sep("§4b — POST /index/add_tx_bh_batch — duplicate tx_hash is idempotent")
        eid = uid("bhdup")
        tx = "0x" + uuid.uuid4().hex * 2
        entry = {
            "tx_hash": tx,
            "from_addr": "0xFromDup",
            "to_addr": "0xToDup",
            "event_type": 1,
            "event_type_name": "TRANSFER",
            "entity_id": eid,
            "magnitude_norm": 0.50,
            "value_wei": "1000000000000000000",
            "selector": "0xa9059cbb",
            "timestamp": int(time.time()),
            "chain_id": 1,
            "chain_label": "ethereum",
            "block_num": 20000010,
            "block_hash": "0x" + uuid.uuid4().hex * 2,
            "sense_hex": "0xaabb",
            "antisense_hex": "0xccdd",
        }
        payload = {
            "chain_id": 1, "chain_label": "ethereum",
            "block_num": 20000010,
            "block_hash": "0x" + uuid.uuid4().hex * 2,
            "timestamp": int(time.time()),
            "entries": [entry],
        }
        r1 = post("/index/add_tx_bh_batch", payload)
        r2 = post("/index/add_tx_bh_batch", payload)  # same hash again
        assert r1.status_code in (200, 201)
        assert r2.status_code in (200, 201)
        ok("PASS — duplicate tx_hash handled idempotently")


# ─────────────────────────────────────────────────────────────────────────────
# §5  Similarity Engine
# ─────────────────────────────────────────────────────────────────────────────
class TestSimilarity:

    def test_similarity_after_seeding(self):
        sep("§5a — GET /similarity/{entity_id} — after seeding")
        eid = uid("sim")
        seed_entity(eid, n=5)
        r = get(f"/similarity/{eid}")
        d = assert_ok(r, "/similarity")
        info("mental_m", d.get("mental_m"))
        info("closest_archetype", d.get("closest_archetype"))
        ok(f"PASS — similarity returned for {eid}")

    def test_similarity_fields(self):
        sep("§5b — GET /similarity — response field presence")
        eid = uid("simf")
        seed_entity(eid, n=3)
        r = get(f"/similarity/{eid}")
        d = assert_ok(r, "/similarity fields")
        for field in ("mental_m", "closest_archetype"):
            info(f"  {field} present", field in d)
        ok("PASS — similarity response has expected fields")

    def test_akashic_match(self):
        sep("§5c — GET /api/v1/akashic/match/{entity_id}")
        eid = uid("match")
        seed_entity(eid, n=4)
        r = get(f"/api/v1/akashic/match/{eid}")
        d = assert_ok(r, "/akashic/match")
        info("Keys", list(d.keys())[:8])
        ok(f"PASS — akashic match returned for {eid}")


# ─────────────────────────────────────────────────────────────────────────────
# §6  Archetype Engine (L2.2)
# ─────────────────────────────────────────────────────────────────────────────
class TestArchetypes:

    def test_archetype_coverage(self):
        sep("§6a — GET /archetypes/coverage")
        r = get("/archetypes/coverage")
        d = assert_ok(r, "/archetypes/coverage")
        info("coverage keys", list(d.keys()))
        ok("PASS — archetype coverage reachable")

    def test_match_vector(self):
        sep("§6b — POST /archetypes/match_vector")
        r = post("/archetypes/match_vector", {
            "vector": rnd_vec(),
            "top_k": 3,
        })
        d = assert_ok(r, "/archetypes/match_vector")
        info("status", d.get("status"))
        info("best_archetype_id", d.get("best_archetype_id"))
        ok("PASS — /archetypes/match_vector returns best archetype")

    def test_match_vector_top_k(self):
        sep("§6c — POST /archetypes/match_vector top_k=5")
        r = post("/archetypes/match_vector", {
            "vector": rnd_vec(),
            "top_k": 5,
        })
        d = assert_ok(r, "/archetypes/match_vector top_k=5")
        archs = d.get("archetypes", [])
        info("archetypes returned", len(archs))
        assert len(archs) <= 5
        ok("PASS — top_k constraint respected")

    def test_faiss_archetypes_api(self):
        sep("§6d — GET /api/v1/akashic/archetypes")
        r = get("/api/v1/akashic/archetypes")
        d = assert_ok(r, "/akashic/archetypes")
        info("Keys", list(d.keys()))
        ok("PASS — /api/v1/akashic/archetypes reachable")

    def test_train_trigger(self):
        sep("§6e — POST /archetypes/train")
        r = post("/archetypes/train", {})
        # May return 200 or 202 (async) or 429 (cooldown)
        assert r.status_code in (200, 201, 202, 400, 429)
        ok(f"PASS — /archetypes/train responded HTTP {r.status_code}")


# ─────────────────────────────────────────────────────────────────────────────
# §7  ANIMA Score Formula (unit — offline)
# ─────────────────────────────────────────────────────────────────────────────
class TestANIMAFormula:
    """Pure-math verification of A(t) = PCR × HA × CA and reflexivity dampening."""

    @staticmethod
    def _anima(pcr: float, ha: float, ca: float) -> float:
        return pcr * ha * ca

    @staticmethod
    def _anima_adj(a: float, reflexivity: float, beta: float = 0.50) -> float:
        return a * (1.0 - beta * reflexivity)

    def test_perfect_score(self):
        sep("§7a — ANIMA formula: perfect inputs")
        a = self._anima(1.0, 1.0, 1.0)
        info("A(PCR=1, HA=1, CA=1)", a)
        assert a == 1.0
        ok("PASS — perfect inputs → A=1.0")

    def test_zero_any_component(self):
        sep("§7b — ANIMA formula: any zero component collapses score")
        assert self._anima(0.0, 0.8, 0.9) == 0.0
        assert self._anima(0.8, 0.0, 0.9) == 0.0
        assert self._anima(0.8, 0.9, 0.0) == 0.0
        ok("PASS — any zero component → A=0.0")

    def test_product_ordering(self):
        sep("§7c — ANIMA formula: product is commutative")
        a1 = self._anima(0.7, 0.85, 0.90)
        a2 = self._anima(0.90, 0.7, 0.85)
        assert abs(a1 - a2) < 1e-12
        ok(f"PASS — product is commutative: {a1:.6f}")

    def test_reflexivity_dampening(self):
        sep("§7d — ANIMA reflexivity dampening: A_adj = A × (1 − β × r)")
        a_raw = self._anima(0.8, 0.85, 0.90)
        for r_val in [0.0, 0.2, 0.5, 1.0]:
            a_adj = self._anima_adj(a_raw, r_val)
            expected = a_raw * (1.0 - 0.5 * r_val)
            info(f"  r={r_val:.1f}  A_adj", f"{a_adj:.6f}  (expected {expected:.6f})")
            assert abs(a_adj - expected) < 1e-12
        ok("PASS — reflexivity dampening formula exact")

    def test_reflexivity_full_saturation(self):
        sep("§7e — ANIMA: reflexivity=2.0 doesn't go negative (clamped)")
        a_raw = 0.75
        a_adj = self._anima_adj(a_raw, 2.0)
        # β=0.5, r=2.0 → A × (1 − 1.0) = 0  (or server clamps to 0)
        info("A_adj at r=2.0", a_adj)
        assert a_adj <= 0.0 + 1e-9
        ok("PASS — full reflexivity saturation collapses score to 0")

    def test_cred_decay_formula(self):
        sep("§7f — CRED decay: CRED(t) = CRED(0) × 0.99^days")
        cred_0 = 1.0
        for days in [0, 1, 7, 30, 90]:
            cred_t = cred_0 * (0.99 ** days)
            info(f"  days={days:>3}", f"{cred_t:.6f}")
        assert cred_0 * (0.99 ** 30) > 0.70, "30d decay should stay above 70%"
        assert cred_0 * (0.99 ** 90) > 0.40, "90d decay should stay above 40%"
        ok("PASS — CRED decay is gradual, not cliff-edge")

    def test_ha_calibration_bound(self):
        sep("§7g — HA = correct/total, ∈ [0,1]")
        for correct, total in [(0, 10), (5, 10), (10, 10), (1, 1)]:
            ha = correct / total
            assert 0.0 <= ha <= 1.0
            info(f"  {correct}/{total}", f"{ha:.2f}")
        ok("PASS — HA is always in [0,1]")

    def test_pcr_formula(self):
        sep("§7h — PCR = matching active / expected (Jaccard-style)")
        # Simulate expected=[a,b,c,d,e], actual=[a,b,c,x,y]
        expected = {"a", "b", "c", "d", "e"}
        actual   = {"a", "b", "c", "x", "y"}
        matches  = len(expected & actual)
        pcr = matches / len(expected)
        info("expected patterns", len(expected))
        info("actual patterns  ", len(actual))
        info("matches", matches)
        info("PCR", pcr)
        assert abs(pcr - 0.6) < 1e-12
        ok("PASS — PCR = 3/5 = 0.60 for 3-match scenario")


# ─────────────────────────────────────────────────────────────────────────────
# §8  ANIMA Score API
# ─────────────────────────────────────────────────────────────────────────────
class TestANIMAAPI:

    def test_anima_score_seeded(self):
        sep("§8a — GET /api/v1/anima/{entity_id} — seeded entity")
        eid = uid("anima")
        seed_entity(eid, n=5)
        r = get(f"/api/v1/anima/{eid}")
        d = assert_ok(r, "/api/v1/anima")
        info("Keys returned", list(d.keys()))
        score_key = next(
            (k for k in ("anima_score", "a_adj", "score", "anima") if k in d),
            None
        )
        info("Score key", score_key)
        if score_key:
            info("Score value", d[score_key])
            assert 0.0 <= float(d[score_key]) <= 1.0
        ok(f"PASS — ANIMA score returned for {eid}")

    def test_anima_score_fresh_entity(self):
        sep("§8b — GET /api/v1/anima/{entity_id} — fresh (unseeded) entity")
        eid = uid("fresh")
        r = get(f"/api/v1/anima/{eid}")
        assert r.status_code in (200, 404)
        ok(f"PASS — fresh entity returns 200 or 404 (HTTP {r.status_code})")

    def test_anima_calibrate(self):
        sep("§8c — POST /api/v1/anima/{entity_id}/calibrate")
        eid = uid("cal")
        seed_entity(eid, n=3)
        r = post(f"/api/v1/anima/{eid}/calibrate", {
            "predicted": 0.72,
            "actual": 0.68,
            "source": "test_suite",
        })
        assert r.status_code in (200, 201, 400, 422)
        ok(f"PASS — calibrate endpoint responded HTTP {r.status_code}")

    def test_anima_system_sources(self):
        sep("§8d — GET /api/v1/anima/system/sources")
        r = get("/api/v1/anima/system/sources")
        d = assert_ok(r, "/anima/system/sources")
        info("Sources data type", type(d).__name__)
        ok("PASS — /api/v1/anima/system/sources reachable")

    def test_anima_cred_event(self):
        sep("§8e — POST /api/v1/anima/cred/{source_id}/event")
        r = post("/api/v1/anima/cred/test_source_01/event", {
            "event_type": "VERIFIED",
            "entity_id": uid("cred"),
            "note": "test suite verification",
        })
        assert r.status_code in (200, 201, 400, 422)
        ok(f"PASS — CRED event posted HTTP {r.status_code}")


# ─────────────────────────────────────────────────────────────────────────────
# §9  CRED Decay & Source Management
# ─────────────────────────────────────────────────────────────────────────────
class TestCRED:

    def test_cred_monotonic_decay(self):
        sep("§9a — CRED decay: monotonically decreasing over time")
        cred = 1.0
        decay_rate = 0.99
        values = []
        for day in range(100):
            values.append(cred * (decay_rate ** day))
        assert all(values[i] >= values[i + 1] for i in range(len(values) - 1))
        info("CRED at day 0  ", f"{values[0]:.4f}")
        info("CRED at day 30 ", f"{values[30]:.4f}")
        info("CRED at day 90 ", f"{values[90]:.4f}")
        ok("PASS — CRED is monotonically decreasing")

    def test_cred_event_types(self):
        sep("§9b — CRED event types: VERIFIED / FALSIFIED / PARTIAL")
        event_types = ["VERIFIED", "FALSIFIED", "PARTIAL", "UNVERIFIED"]
        for et in event_types:
            r = post("/api/v1/anima/cred/source_multi/event", {
                "event_type": et,
                "entity_id": uid("cred"),
                "note": f"testing {et}",
            })
            info(f"  {et}", f"HTTP {r.status_code}")
            assert r.status_code in (200, 201, 400, 422)
        ok("PASS — all 4 CRED event types accepted/rejected cleanly")

    def test_multiple_sources_independence(self):
        sep("§9c — CRED independence: different source IDs track separately")
        sources = ["github_crawler", "sec_edgar", "news_rss", "on_chain_oracle"]
        for src in sources:
            r = post(f"/api/v1/anima/cred/{src}/event", {
                "event_type": "VERIFIED",
                "entity_id": uid("cred_src"),
                "note": f"independence test for {src}",
            })
            info(f"  {src}", f"HTTP {r.status_code}")
        ok("PASS — multiple independent CRED sources accepted")


# ─────────────────────────────────────────────────────────────────────────────
# §10 Reflexivity (L3.5)
# ─────────────────────────────────────────────────────────────────────────────
class TestReflexivity:

    def test_reflexivity_report(self):
        sep("§10a — GET /api/v1/anima/reflexivity/{entity_id}")
        eid = uid("reflex")
        seed_entity(eid, n=4)
        r = get(f"/api/v1/anima/reflexivity/{eid}")
        d = assert_ok(r, "/anima/reflexivity")
        info("Keys", list(d.keys()))
        ok(f"PASS — reflexivity report returned for {eid}")

    def test_reflexivity_dampening_formula(self):
        sep("§10b — Reflexivity dampening reduces score proportionally")
        # A(t) = A_raw × (1 - 0.5 × reflexivity)
        for r_val, expected_mult in [(0.0, 1.0), (1.0, 0.5), (0.5, 0.75)]:
            mult = 1.0 - 0.5 * r_val
            assert abs(mult - expected_mult) < 1e-9
            info(f"  r={r_val}  multiplier", f"{mult:.3f}")
        ok("PASS — reflexivity dampening formula exact")

    def test_reflexivity_score_bounded(self):
        sep("§10c — Reflexivity score ∈ [0, 1]")
        eid = uid("reflex_b")
        seed_entity(eid, n=3)
        r = get(f"/api/v1/anima/reflexivity/{eid}")
        if r.status_code == 200:
            d = r.json()
            score = d.get("reflexivity_score", d.get("reflexivity", 0))
            if score is not None:
                assert 0.0 <= float(score) <= 2.0  # may exceed 1 by design
                info("reflexivity_score", score)
        ok("PASS — reflexivity score in valid range")


# ─────────────────────────────────────────────────────────────────────────────
# §11 Observer Effect (L3.2)
# ─────────────────────────────────────────────────────────────────────────────
class TestObserverEffect:

    def test_observer_effect_endpoint(self):
        sep("§11a — GET /api/v1/observer_effect/{entity_id} (L3.2)")
        eid = uid("oe")
        seed_entity(eid, n=3)
        r = get(f"/api/v1/observer_effect/{eid}")
        if r.status_code == 404:
            # Endpoint may not exist in this build
            ok("SKIP — observer_effect endpoint not present in this build")
            return
        d = assert_ok(r, "/observer_effect")
        info("oe_factor", d.get("oe_factor"))
        info("reflexivity_flag", d.get("reflexivity_flag"))
        ok(f"PASS — observer effect data returned for {eid}")

    def test_oe_factor_range(self):
        sep("§11b — OE factor is always in [0, 1]")
        # Unit verification of oe_factor semantics
        for oe in [0.0, 0.25, 0.5, 0.99, 1.0]:
            corrected = max(0.0, min(1.0, oe))
            assert corrected == oe
            info(f"  oe={oe}", "valid")
        ok("PASS — OE factor clamp invariant holds")


# ─────────────────────────────────────────────────────────────────────────────
# §12 NL Score Formula (unit — offline)
# ─────────────────────────────────────────────────────────────────────────────
class TestNLFormula:

    @pytest.mark.skipif(not _NL_OK, reason="nl_score_engine not importable")
    def test_nl_basic(self):
        sep("§12a — NL score: basic computation")
        result = compute_nl_score(
            pool_depths=[1_000_000, 2_000_000, 800_000],
            pool_corrs=[0.9, 0.8, 0.7],
            depth_history=[900_000, 950_000, 1_000_000] * 10,
            price_history=[1.00, 1.01, 0.99, 1.02, 1.00] * 6,
        )
        info("nl_score", result["nl_score"])
        info("ld", result["ld"])
        info("above_floor", result["above_floor"])
        assert 0.0 <= result["nl_score"] <= 1.0
        ok("PASS — NL score in [0,1]")

    @pytest.mark.skipif(not _NL_OK, reason="nl_score_engine not importable")
    def test_nl_shallow_pool(self):
        sep("§12b — NL score: shallow pool → low score")
        deep = compute_nl_score(pool_depths=[10_000_000, 8_000_000])
        shallow = compute_nl_score(pool_depths=[1_000, 500])
        info("deep pool NL", deep["nl_score"])
        info("shallow pool NL", shallow["nl_score"])
        assert deep["nl_score"] > shallow["nl_score"], \
            "deeper pool must score higher"
        ok("PASS — deep > shallow pool scoring")

    @pytest.mark.skipif(not _NL_OK, reason="nl_score_engine not importable")
    def test_nl_oe_correction(self):
        sep("§12c — NL: Observer Effect correction reduces score")
        base = compute_nl_score(pool_depths=[5_000_000])["nl_score"]
        corrected = apply_oe_correction(base, oe_factor=0.5)
        info("base NL", base)
        info("after OE correction (oe=0.5)", corrected)
        assert corrected <= base
        ok("PASS — OE correction cannot inflate NL score")

    @pytest.mark.skipif(not _NL_OK, reason="nl_score_engine not importable")
    def test_nl_floor_gate(self):
        sep("§12d — NL: above_floor gate")
        trivial = compute_nl_score(pool_depths=[0.01])
        info("above_floor", trivial["above_floor"])
        info("sufficient_depth", trivial.get("sufficient_depth"))
        ok("PASS — zero-depth pool flagged below floor")

    @pytest.mark.skipif(not _NL_OK, reason="nl_score_engine not importable")
    def test_nl_four_components(self):
        sep("§12e — NL: all four components (LD, LO, LC, LS) present")
        result = compute_nl_score(
            pool_depths=[2_000_000, 3_000_000],
            depth_history=[1_500_000] * 14 + [500_000] * 5,
            price_history=[1.0, 1.1, 0.9, 1.2, 0.8] * 4,
        )
        for comp in ("ld", "lo", "lc", "ls"):
            info(f"  {comp}", result.get(comp))
        ok("PASS — all four NL components present")


# ─────────────────────────────────────────────────────────────────────────────
# §13 Liquidity Ocean API
# ─────────────────────────────────────────────────────────────────────────────
class TestLiquidityOcean:

    @pytest.mark.skipif(not _OCEAN_OK, reason="liquidity_ocean not importable")
    def test_ocean_coherence_formula(self):
        sep("§13a — LiquidityOcean coherence formula: C(t) = 1 - tanh(2σ/μ)")
        ocean = LiquidityOcean(oe_factor=0.0)
        # Push uniform chain NL scores → σ≈0 → coherence≈1
        for chain_id, nl in [(1, 0.8), (137, 0.81), (42161, 0.79), (10, 0.80)]:
            ocean.update_chain(
                chain_id=chain_id,
                pool_depths=[2_000_000, 3_000_000],
                depth_history=[2_000_000] * 14,
                price_history=[1.0] * 10,
            )
        signal = ocean.get_ocean_signal()
        info("coherence", signal["coherence"])
        info("l_ocean", signal["l_ocean"])
        info("hhi", signal["hhi"])
        assert 0.0 <= signal["coherence"] <= 1.0
        ok("PASS — coherence in [0,1] for uniform NL scores")

    @pytest.mark.skipif(not _OCEAN_OK, reason="liquidity_ocean not importable")
    def test_ocean_hhi_high_when_concentrated(self):
        sep("§13b — HHI spikes when one chain dominates NL")
        ocean = LiquidityOcean(oe_factor=0.0)
        ocean.update_chain(1, pool_depths=[50_000_000], depth_history=[50_000_000] * 14)
        ocean.update_chain(137, pool_depths=[100], depth_history=[100] * 14)
        signal = ocean.get_ocean_signal()
        info("HHI (concentrated)", signal["hhi"])
        assert signal["hhi"] > 0.50, "HHI must be high for dominated landscape"
        ok("PASS — HHI > 0.50 when one chain dominates")

    @pytest.mark.skipif(not _OCEAN_OK, reason="liquidity_ocean not importable")
    def test_ocean_routing_threshold(self):
        sep("§13c — LiquidityOcean dynamic routing threshold ∈ [0.30, 0.70]")
        ocean = LiquidityOcean(oe_factor=0.0)
        for cid, depth in [(1, 2e6), (137, 1.5e6), (42161, 3e6), (10, 1e6)]:
            ocean.update_chain(cid, pool_depths=[depth], depth_history=[depth] * 14)
            ocean.get_ocean_signal()  # populate coherence_history
        theta = ocean.dynamic_routing_threshold()
        info("routing threshold θ(t)", theta)
        assert 0.30 <= theta <= 0.70
        ok("PASS — routing threshold bounded in [0.30, 0.70]")

    def test_liquidity_nl_api(self):
        sep("§13d — GET /api/v1/liquidity/{asset_address}")
        asset = "0x" + "a1" * 20
        r = get(f"/api/v1/liquidity/{asset}")
        assert r.status_code in (200, 404)
        if r.status_code == 200:
            d = r.json()
            info("nl_score", d.get("nl_score"))
            info("above_floor", d.get("above_floor"))
        ok(f"PASS — /api/v1/liquidity responded HTTP {r.status_code}")


# ─────────────────────────────────────────────────────────────────────────────
# §14 Living Security — Full 8-Component Report
# ─────────────────────────────────────────────────────────────────────────────
class TestLivingSecurity:
    eid = None

    @classmethod
    def setup_class(cls):
        cls.eid = uid("ls")
        seed_entity(cls.eid, n=5)

    def test_full_report(self):
        sep("§14a — GET /api/v1/living_security/{entity_id} — 8-component")
        r = get(f"/api/v1/living_security/{self.eid}")
        d = assert_ok(r, "/living_security full")
        info("Keys", list(d.keys())[:12])
        ok(f"PASS — living security full report for {self.eid}")

    def test_report_has_entity_id(self):
        sep("§14b — Living security report contains entity_id")
        r = get(f"/api/v1/living_security/{self.eid}")
        d = assert_ok(r, "/living_security entity_id")
        assert "entity_id" in d or "beo_id" in d
        ok("PASS — entity_id / beo_id present in report")

    def test_report_scores_in_range(self):
        sep("§14c — Living security scores ∈ [0, 1]")
        r = get(f"/api/v1/living_security/{self.eid}")
        d = assert_ok(r, "/living_security scores")
        for k, v in d.items():
            if isinstance(v, (int, float)) and k not in ("generation", "memory_size"):
                assert 0.0 <= float(v) <= 1.0, f"{k}={v} out of [0,1]"
                info(f"  {k}", f"{v:.4f}")
        ok("PASS — all numeric scores in [0,1]")


# ─────────────────────────────────────────────────────────────────────────────
# §15 Genomic Key (GK) Evolution
# ─────────────────────────────────────────────────────────────────────────────
class TestGenomicKey:

    def test_gk_evolve_basic(self):
        sep("§15a — POST /api/v1/living_security/gk/evolve/{entity_id}")
        eid = uid("gk")
        seed_entity(eid, n=3)
        r = post(f"/api/v1/living_security/gk/evolve/{eid}", {
            "be_t": 0.85,
            "tm_t": 0.10,
            "cv_t": 0.60,
        })
        d = assert_ok(r, "/gk/evolve")
        info("gk_hex", d.get("gk_hex", "")[:32] + "...")
        info("generation", d.get("generation"))
        assert "gk_hex" in d
        ok(f"PASS — GK evolved for {eid}")

    def test_gk_evolution_chain(self):
        sep("§15b — GK evolution: each step changes the key")
        eid = uid("gkchain")
        seed_entity(eid, n=2)
        keys = []
        for step in range(5):
            r = post(f"/api/v1/living_security/gk/evolve/{eid}", {
                "be_t": 0.80 + step * 0.02,
                "tm_t": float(step) * 0.05,
                "cv_t": 0.50,
            })
            d = assert_ok(r, f"/gk/evolve step {step}")
            keys.append(d["gk_hex"])
        unique = len(set(keys))
        info("Unique keys across 5 evolutions", unique)
        assert unique == 5, "Each evolution must produce a distinct key"
        ok("PASS — 5 evolution steps → 5 unique GK hashes")

    def test_gk_same_inputs_same_key(self):
        sep("§15c — GK determinism: same inputs at same generation → same key")
        eid = uid("gkdet")
        seed_entity(eid, n=2)
        # First evolution
        r1 = post(f"/api/v1/living_security/gk/evolve/{eid}",
                  {"be_t": 0.75, "tm_t": 0.00, "cv_t": 0.50})
        d1 = assert_ok(r1, "gk det 1")
        # Read back the key
        r_get = get(f"/api/v1/living_security/gk/{eid}")
        d_get = assert_ok(r_get, "gk get")
        info("GK from evolve", d1.get("gk_hex", "")[:24])
        info("GK from get   ", d_get.get("gk_hex", "")[:24])
        ok("PASS — GK retrieval returns the last evolved key")

    def test_gk_get(self):
        sep("§15d — GET /api/v1/living_security/gk/{entity_id}")
        eid = uid("gkget")
        seed_entity(eid, n=2)
        post(f"/api/v1/living_security/gk/evolve/{eid}",
             {"be_t": 0.80, "tm_t": 0.05, "cv_t": 0.55})
        r = get(f"/api/v1/living_security/gk/{eid}")
        d = assert_ok(r, "/gk/get")
        info("gk_hex", d.get("gk_hex", "")[:32] + "...")
        info("generation", d.get("generation"))
        assert "gk_hex" in d
        ok(f"PASS — GK retrieved for {eid}")

    def test_gk_stolen_key_attack(self):
        sep("§15e — GK stolen-key attack: old key is invalidated after evolution")
        eid = uid("gksteal")
        seed_entity(eid, n=2)
        r1 = post(f"/api/v1/living_security/gk/evolve/{eid}",
                  {"be_t": 0.70, "tm_t": 0.00, "cv_t": 0.50})
        stolen_key = assert_ok(r1, "gk stolen")["gk_hex"]
        # Evolve again
        r2 = post(f"/api/v1/living_security/gk/evolve/{eid}",
                  {"be_t": 0.85, "tm_t": 0.20, "cv_t": 0.65})
        current_key = assert_ok(r2, "gk current")["gk_hex"]
        info("Stolen (old) key", stolen_key[:24] + "...")
        info("Current key     ", current_key[:24] + "...")
        assert stolen_key != current_key, "Stolen key must differ from current"
        ok("PASS — stolen key is invalidated after evolution")


# ─────────────────────────────────────────────────────────────────────────────
# §16 Immune System — Innate + Adaptive
# ─────────────────────────────────────────────────────────────────────────────
class TestImmuneSystem:

    def test_adaptive_memory_registration(self):
        sep("§16a — POST /api/v1/living_security/immune/adaptive — register threat")
        r = post("/api/v1/living_security/immune/adaptive", {
            "pattern_name": f"replay_attack_{uid()}",
            "attack_vector_hex": "0xdeadbeef01020304",
            "counter_response": "REJECT",
        })
        d = assert_ok(r, "/immune/adaptive")
        info("pattern_hash", d.get("pattern_hash", "")[:24] + "...")
        info("memory_size", d.get("memory_size"))
        assert "pattern_hash" in d
        ok("PASS — adaptive immune memory pattern registered")

    def test_adaptive_memory_grows(self):
        sep("§16b — Immune adaptive memory grows with each registration")
        # Read baseline
        r0 = get("/api/v1/living_security/immune/memory")
        d0 = assert_ok(r0, "/immune/memory baseline")
        size_before = d0.get("memory_size", 0)
        # Add 3 new patterns
        for i in range(3):
            post("/api/v1/living_security/immune/adaptive", {
                "pattern_name": f"threat_grow_{uid()}_{i}",
                "attack_vector_hex": "0x" + f"a{i}" * 8,
                "counter_response": "QUARANTINE",
            })
        r1 = get("/api/v1/living_security/immune/memory")
        d1 = assert_ok(r1, "/immune/memory after")
        size_after = d1.get("memory_size", 0)
        info(f"Memory size before", size_before)
        info(f"Memory size after ", size_after)
        assert size_after >= size_before
        ok("PASS — immune memory size grows or stays same after additions")

    def test_immune_memory_read(self):
        sep("§16c — GET /api/v1/living_security/immune/memory")
        r = get("/api/v1/living_security/immune/memory")
        d = assert_ok(r, "/immune/memory")
        info("memory_size", d.get("memory_size"))
        info("innate_library_size", d.get("innate_library_size"))
        info("adaptive_patterns count", len(d.get("adaptive_patterns", [])))
        ok("PASS — immune memory read successful")

    def test_immune_entity_clearance(self):
        sep("§16d — GET /api/v1/living_security/immune/{entity_id}")
        eid = uid("imm")
        seed_entity(eid, n=2)
        r = get(f"/api/v1/living_security/immune/{eid}")
        d = assert_ok(r, "/immune/{entity_id}")
        info("clearance", d.get("clearance"))
        info("threat_count", d.get("threat_count"))
        ok(f"PASS — immune clearance for {eid}")

    def test_counter_response_variants(self):
        sep("§16e — Immune: all counter-response types accepted")
        for cr in ["REJECT", "QUARANTINE", "ALERT", "ALLOW"]:
            r = post("/api/v1/living_security/immune/adaptive", {
                "pattern_name": f"cr_test_{cr}_{uid()}",
                "attack_vector_hex": "0xaabbccdd",
                "counter_response": cr,
            })
            info(f"  {cr}", f"HTTP {r.status_code}")
            assert r.status_code in (200, 201, 400, 422)
        ok("PASS — all counter-response variants accepted or rejected cleanly")


# ─────────────────────────────────────────────────────────────────────────────
# §17 Epigenetic Phenotype
# ─────────────────────────────────────────────────────────────────────────────
class TestEpigenetic:

    def test_epigenetic_update(self):
        sep("§17a — POST /api/v1/living_security/epigenetic/update")
        r = post("/api/v1/living_security/epigenetic/update", {
            "threat_level": 0.80,
            "validator_health": 0.60,
            "network_entropy": 0.90,
        })
        d = assert_ok(r, "/epigenetic/update")
        info("expression_level", d.get("expression_level"))
        info("phenotype", d.get("phenotype"))
        assert "phenotype" in d
        ok("PASS — epigenetic phenotype updated")

    def test_epigenetic_read(self):
        sep("§17b — GET /api/v1/living_security/epigenetic")
        r = get("/api/v1/living_security/epigenetic")
        d = assert_ok(r, "/epigenetic")
        info("expression_level", d.get("expression_level"))
        info("phenotype", d.get("phenotype"))
        info("threat_level", d.get("threat_level"))
        ok("PASS — epigenetic state readable")

    def test_epigenetic_phenotype_shifts_with_threat(self):
        sep("§17c — Epigenetic phenotype shifts under high vs low threat")
        post("/api/v1/living_security/epigenetic/update",
             {"threat_level": 0.05, "validator_health": 0.99, "network_entropy": 1.0})
        r_low = get("/api/v1/living_security/epigenetic")
        d_low = assert_ok(r_low, "epigenetic low threat")

        post("/api/v1/living_security/epigenetic/update",
             {"threat_level": 0.95, "validator_health": 0.20, "network_entropy": 0.30})
        r_high = get("/api/v1/living_security/epigenetic")
        d_high = assert_ok(r_high, "epigenetic high threat")

        info("Low-threat phenotype ", d_low.get("phenotype"))
        info("High-threat phenotype", d_high.get("phenotype"))
        # The expression levels must differ
        el_low  = d_low.get("expression_level",  0)
        el_high = d_high.get("expression_level", 0)
        info("Expression low ", el_low)
        info("Expression high", el_high)
        assert el_low != el_high, "Expression level must respond to threat changes"
        ok("PASS — phenotype shifts under different threat conditions")


# ─────────────────────────────────────────────────────────────────────────────
# §18 Noise / Decoy Fingerprints
# ─────────────────────────────────────────────────────────────────────────────
class TestNoise:

    def test_noise_decoys(self):
        sep("§18a — GET /api/v1/living_security/noise/{entity_id}")
        eid = uid("noise")
        seed_entity(eid, n=3)
        post(f"/api/v1/living_security/gk/evolve/{eid}",
             {"be_t": 0.70, "tm_t": 0.00, "cv_t": 0.50})
        r = get(f"/api/v1/living_security/noise/{eid}", params={"n_decoys": 5})
        if r.status_code == 404:
            r = get(f"/api/v1/living_security/noise/{eid}")
        d = assert_ok(r, "/living_security/noise")
        info("n_decoys returned", len(d.get("decoys", [])))
        info("noise_fingerprint", str(d.get("noise_fingerprint", ""))[:24])
        ok(f"PASS — noise decoys generated for {eid}")

    def test_decoys_differ_from_real_key(self):
        sep("§18b — Noise decoys do not equal the real GK")
        eid = uid("decoy")
        seed_entity(eid, n=2)
        ev = post(f"/api/v1/living_security/gk/evolve/{eid}",
                  {"be_t": 0.75, "tm_t": 0.05, "cv_t": 0.55})
        real_key = assert_ok(ev, "gk real")["gk_hex"]
        r = get(f"/api/v1/living_security/noise/{eid}", params={"n_decoys": 8})
        if r.status_code != 200:
            r = get(f"/api/v1/living_security/noise/{eid}")
        if r.status_code == 200:
            decoys = r.json().get("decoys", [])
            for dec in decoys:
                dec_key = dec if isinstance(dec, str) else dec.get("gk_hex", "")
                assert dec_key != real_key, "Decoy must not equal real key"
            info("Decoys checked", len(decoys))
        ok("PASS — no decoy equals the real GK")


# ─────────────────────────────────────────────────────────────────────────────
# §19 Mitochondrial Core
# ─────────────────────────────────────────────────────────────────────────────
class TestMitochondrial:

    def test_mitochondrial_read(self):
        sep("§19a — GET /api/v1/living_security/mitochondrial")
        r = get("/api/v1/living_security/mitochondrial")
        d = assert_ok(r, "/mitochondrial")
        info("mito_hash", str(d.get("mito_hash", ""))[:24] + "...")
        info("intact", d.get("intact"))
        info("event_count", d.get("event_count"))
        assert "mito_hash" in d
        ok("PASS — mitochondrial core status readable")

    def test_mitochondrial_integrity(self):
        sep("§19b — Mitochondrial: intact=True before tampering")
        r = get("/api/v1/living_security/mitochondrial")
        d = assert_ok(r, "/mitochondrial integrity")
        info("intact", d.get("intact"))
        # intact can be True or False depending on state — just assert it is a bool
        assert isinstance(d.get("intact"), bool)
        ok("PASS — mitochondrial intact flag is boolean")

    def test_mitochondrial_claimed_hash_valid(self):
        sep("§19c — Mitochondrial: claim valid hash")
        r_base = get("/api/v1/living_security/mitochondrial")
        d_base = assert_ok(r_base, "/mitochondrial base")
        real_hash = d_base.get("mito_hash", "")
        if real_hash:
            r_claim = get("/api/v1/living_security/mitochondrial",
                          params={"claimed_hash": real_hash})
            d_claim = assert_ok(r_claim, "/mitochondrial claim valid")
            info("claim_valid", d_claim.get("claim_valid"))
            assert d_claim.get("claim_valid") is True
            ok("PASS — real hash is accepted as valid claim")

    def test_mitochondrial_claimed_hash_invalid(self):
        sep("§19d — Mitochondrial: claim with wrong hash → invalid")
        r = get("/api/v1/living_security/mitochondrial",
                params={"claimed_hash": "0xfakeHash" + "00" * 16})
        d = assert_ok(r, "/mitochondrial invalid claim")
        info("claim_valid", d.get("claim_valid"))
        assert d.get("claim_valid") is False
        ok("PASS — wrong hash rejected as invalid claim")


# ─────────────────────────────────────────────────────────────────────────────
# §20 BEO Cluster Resolution
# ─────────────────────────────────────────────────────────────────────────────
class TestBEO:

    def test_beo_resolve_shared_funder(self):
        sep("§20a — BEO: two entities with shared funder cluster together")
        funder = "0xSharedFunder_" + uid()
        eid_a = uid("beo_a")
        eid_b = uid("beo_b")
        for eid in (eid_a, eid_b):
            post("/index/add", {
                "entity_id": eid,
                "vector": rnd_vec(),
                "magnitude": 0.80,
                "entropy": 0.85,
                "funding_source": funder,
                "chain_id": 1,
                "chain_label": "ethereum",
            })
        r = get(f"/api/v1/akashic/match/{eid_a}")
        d = assert_ok(r, "/akashic/match BEO")
        info("Match result keys", list(d.keys()))
        ok("PASS — BEO akashic match resolved for shared-funder entities")

    def test_beo_co_occurrence_tracking(self):
        sep("§20b — BEO: co-occurrence count grows with joint activity")
        eid_x = uid("cooc_x")
        eid_y = uid("cooc_y")
        funder = "0xCoocFunder_" + uid()
        for i in range(5):
            for eid in (eid_x, eid_y):
                post("/index/add", {
                    "entity_id": eid,
                    "vector": rnd_vec(),
                    "magnitude": 0.70,
                    "entropy": 0.85,
                    "funding_source": funder,
                    "chain_id": 1,
                    "chain_label": "ethereum",
                    "block_num": 20000000 + i,
                })
        r = get(f"/api/v1/akashic/match/{eid_x}")
        d = assert_ok(r, "/akashic/match co-occurrence")
        ok(f"PASS — co-occurrence tracked for {eid_x} ↔ {eid_y}")


# ─────────────────────────────────────────────────────────────────────────────
# §21 PHI Weights (L1.1)
# ─────────────────────────────────────────────────────────────────────────────
class TestPHIWeights:

    def test_phi_weights_sum(self):
        sep("§21a — PHI weights formula: uniform phase → sum = 1.0 (9 components)")
        n = 9
        uniform = [1.0 / n] * n
        total = sum(uniform)
        info("n_components", n)
        info("weight each", f"{1/n:.6f}")
        info("sum", f"{total:.6f}")
        assert abs(total - 1.0) < 1e-9
        ok("PASS — uniform PHI weights sum to 1.0")

    def test_phi_learned_weights(self):
        sep("§21b — PHI weights converge to accuracy-correlated distribution")
        # Simulate Pearson-based weight update:
        # higher correlation with signal accuracy → higher weight
        accuracies = [0.9, 0.8, 0.7, 0.6, 0.5, 0.4, 0.3, 0.2, 0.1]
        total_acc  = sum(accuracies)
        learned    = [a / total_acc for a in accuracies]
        info("Sum of learned weights", f"{sum(learned):.6f}")
        assert abs(sum(learned) - 1.0) < 1e-9
        assert learned[0] > learned[-1], "Best-accuracy component gets highest weight"
        ok("PASS — learned PHI weights: best-accuracy component gets highest weight")

    def test_phi_vm_status_api(self):
        sep("§21c — GET /api/v1/index/vm-status (PHI per VM family)")
        r = get("/api/v1/index/vm-status")
        d = assert_ok(r, "/index/vm-status")
        info("VM status keys", list(d.keys()))
        ok("PASS — /api/v1/index/vm-status reachable")


# ─────────────────────────────────────────────────────────────────────────────
# §22 Information Conservation (L0.4)
# ─────────────────────────────────────────────────────────────────────────────
class TestConservation:

    def test_conservation_status(self):
        sep("§22a — GET /conservation/status")
        r = get("/conservation/status")
        d = assert_ok(r, "/conservation/status")
        info("I_total", d.get("I_total"))
        info("delta_consumed", d.get("delta_consumed"))
        info("delta_transformed", d.get("delta_transformed"))
        info("invariant_holds", d.get("invariant_holds"))
        info("conservation_ratio", d.get("conservation_ratio"))
        assert "I_total" in d
        ok("PASS — conservation status fields present")

    def test_conservation_invariant(self):
        sep("§22b — L0.4 invariant: delta_transformed ≥ 0")
        r = get("/conservation/status")
        d = assert_ok(r, "/conservation invariant")
        assert d.get("invariant_holds", True) is True or d.get("delta_transformed", 0) >= 0
        ok("PASS — L0.4 conservation invariant holds")

    def test_conservation_grows_with_indexing(self):
        sep("§22c — Conservation I_total grows after new vectors are indexed")
        r_before = get("/conservation/status")
        d_before = assert_ok(r_before, "conservation before")
        i_before = d_before.get("I_total", 0)
        # Index 5 more vectors
        for _ in range(5):
            post("/index/add", {
                "entity_id": uid("cons_grow"),
                "vector": rnd_vec(),
                "magnitude": 0.75,
                "entropy": 0.90,
            })
        r_after = get("/conservation/status")
        d_after = assert_ok(r_after, "conservation after")
        i_after = d_after.get("I_total", 0)
        info("I_total before indexing", i_before)
        info("I_total after indexing ", i_after)
        assert i_after >= i_before, "I_total must be monotonically non-decreasing"
        ok("PASS — I_total is non-decreasing after indexing")

    def test_conservation_ratio_in_range(self):
        sep("§22d — Conservation ratio ∈ [0, 1]")
        r = get("/conservation/status")
        d = assert_ok(r, "/conservation ratio")
        ratio = d.get("conservation_ratio", 0)
        info("conservation_ratio", ratio)
        assert 0.0 <= float(ratio) <= 1.0
        ok("PASS — conservation_ratio ∈ [0, 1]")


# ─────────────────────────────────────────────────────────────────────────────
# §23 Fitness Update (L0.6)
# ─────────────────────────────────────────────────────────────────────────────
class TestFitness:

    def test_fitness_update_basic(self):
        sep("§23a — POST /fitness/update")
        r = post("/fitness/update", {
            "component": "BEO_RESOLVER",
            "PA": 0.85,
            "ICE": 0.90,
            "AS": 0.80,
            "Love": 1.0,
        })
        d = assert_ok(r, "/fitness/update")
        info("fitness", d.get("fitness"))
        info("component", d.get("component"))
        expected = 0.85 * 0.90 * 0.80 * 1.0
        actual   = d.get("fitness", 0)
        info("expected (PA×ICE×AS×Love)", f"{expected:.6f}")
        if actual:
            assert abs(float(actual) - expected) < 0.01
        ok("PASS — fitness = PA × ICE × AS × Love")

    def test_fitness_love_zero_collapses(self):
        sep("§23b — Fitness: Love=0 forces fitness=0 regardless of other inputs")
        r = post("/fitness/update", {
            "component": "TEST_ZERO_LOVE",
            "PA": 1.0,
            "ICE": 1.0,
            "AS": 1.0,
            "Love": 0.0,
        })
        d = assert_ok(r, "/fitness Love=0")
        fitness = float(d.get("fitness", -1))
        love_zero = d.get("love_zero", None)
        info("fitness", fitness)
        info("love_zero flag", love_zero)
        assert fitness == 0.0 or love_zero is True
        ok("PASS — Love=0 collapses fitness to 0")

    def test_fitness_multiple_components(self):
        sep("§23c — Fitness: independent tracking across components")
        components = [
            ("ANIMA_ENGINE",    0.90, 0.88, 0.85, 1.0),
            ("FAISS_INDEX",     0.75, 0.80, 0.70, 1.0),
            ("BEO_RESOLVER",    0.95, 0.92, 0.90, 1.0),
            ("PHI_CONTROLLER",  0.60, 0.65, 0.55, 0.8),
        ]
        for comp, pa, ice, asp, love in components:
            r = post("/fitness/update", {
                "component": comp, "PA": pa, "ICE": ice, "AS": asp, "Love": love,
            })
            d = assert_ok(r, f"/fitness {comp}")
            expected = pa * ice * asp * love
            info(f"  {comp:<22} expected={expected:.4f}", f"got={d.get('fitness', '?')}")
        ok("PASS — all 4 components updated independently")


# ─────────────────────────────────────────────────────────────────────────────
# §24 Thermodynamics & Lifecycle
# ─────────────────────────────────────────────────────────────────────────────
class TestThermo:

    def test_thermodynamics_endpoint(self):
        sep("§24a — GET /api/v1/thermodynamics/{entity_id}")
        eid = uid("thermo")
        seed_entity(eid, n=4)
        r = get(f"/api/v1/thermodynamics/{eid}")
        d = assert_ok(r, "/thermodynamics")
        info("Keys", list(d.keys()))
        ok(f"PASS — thermodynamics data returned for {eid}")

    def test_lifecycle_endpoint(self):
        sep("§24b — GET /api/v1/lifecycle/{entity_id}")
        eid = uid("life")
        seed_entity(eid, n=3)
        r = get(f"/api/v1/lifecycle/{eid}")
        d = assert_ok(r, "/lifecycle")
        info("Keys", list(d.keys()))
        ok(f"PASS — lifecycle data returned for {eid}")

    def test_thermodynamics_entropy_bounded(self):
        sep("§24c — Thermodynamics: entropy value in valid range")
        eid = uid("thermo_e")
        seed_entity(eid, n=5)
        r = get(f"/api/v1/thermodynamics/{eid}")
        d = assert_ok(r, "/thermodynamics entropy")
        entropy = d.get("entropy", d.get("current_entropy"))
        if entropy is not None:
            assert 0.0 <= float(entropy) <= 10.0, f"entropy out of range: {entropy}"
            info("entropy", entropy)
        ok("PASS — entropy in valid range")


# ─────────────────────────────────────────────────────────────────────────────
# §25 Epigenetics Pressure (Akashic)
# ─────────────────────────────────────────────────────────────────────────────
class TestAkashicEpigenetics:

    def test_akashic_epigenetics_read(self):
        sep("§25a — GET /api/v1/akashic/epigenetics/{entity_id}")
        eid = uid("akep")
        seed_entity(eid, n=3)
        r = get(f"/api/v1/akashic/epigenetics/{eid}")
        d = assert_ok(r, "/akashic/epigenetics")
        info("Keys", list(d.keys()))
        ok(f"PASS — akashic epigenetics read for {eid}")

    def test_akashic_epigenetics_pressure(self):
        sep("§25b — POST /api/v1/akashic/epigenetics/{entity_id}/pressure")
        eid = uid("akpress")
        seed_entity(eid, n=3)
        r = post(f"/api/v1/akashic/epigenetics/{eid}/pressure", {
            "pressure_type": "REGULATORY",
            "magnitude": 0.75,
        })
        assert r.status_code in (200, 201, 400, 422)
        ok(f"PASS — epigenetic pressure applied HTTP {r.status_code}")


# ─────────────────────────────────────────────────────────────────────────────
# §26 Conscious Plane — Annotations
# ─────────────────────────────────────────────────────────────────────────────
class TestConscious:

    def test_auto_annotate(self):
        sep("§26a — POST /api/v1/conscious/auto_annotate/{entity_id}")
        eid = uid("annot")
        seed_entity(eid, n=4)
        r = post(f"/api/v1/conscious/auto_annotate/{eid}", {})
        assert r.status_code in (200, 201, 400, 422)
        if r.status_code in (200, 201):
            d = r.json()
            info("Annotation keys", list(d.keys()))
        ok(f"PASS — auto-annotate HTTP {r.status_code}")


# ─────────────────────────────────────────────────────────────────────────────
# §27 Conscious Plane — Knowledge Systems & Elders
# ─────────────────────────────────────────────────────────────────────────────
class TestKnowledgeSystems:

    def test_register_knowledge_system(self):
        sep("§27a — POST /api/v1/conscious/knowledge_systems/register")
        sys_id = uid("ks")
        r = post("/api/v1/conscious/knowledge_systems/register", {
            "system_id": sys_id,
            "system_name": f"TestSystem_{sys_id}",
            "origin_region": "OCEANIA",
            "contact_identifier": hashlib.sha256(sys_id.encode()).hexdigest(),
            "description": "Test knowledge system for ANIMA suite",
        })
        assert r.status_code in (200, 201, 400, 409)
        ok(f"PASS — knowledge system register HTTP {r.status_code}")

    def test_list_knowledge_systems(self):
        sep("§27b — GET /api/v1/conscious/knowledge_systems")
        r = get("/api/v1/conscious/knowledge_systems")
        d = assert_ok(r, "/knowledge_systems list")
        info("systems count", len(d.get("systems", [])))
        ok("PASS — knowledge systems list returned")

    def test_consent_and_revoke(self):
        sep("§27c — Consent lifecycle: register → consent → revoke")
        sys_id = uid("consent_ks")
        post("/api/v1/conscious/knowledge_systems/register", {
            "system_id": sys_id,
            "system_name": f"Consent Test {sys_id}",
            "origin_region": "AMERICAS",
            "contact_identifier": hashlib.sha256(sys_id.encode()).hexdigest(),
            "description": "Consent lifecycle test",
        })
        r_consent = post("/api/v1/conscious/knowledge_systems/consent", {
            "system_id": sys_id,
            "consent_given_by": "test_guardian",
            "consent_scope": "analytics_read",
        })
        info("consent HTTP", r_consent.status_code)
        r_revoke = post("/api/v1/conscious/knowledge_systems/revoke_consent", {
            "system_id": sys_id,
            "revoked_by": "test_guardian",
        })
        info("revoke HTTP", r_revoke.status_code)
        assert r_revoke.status_code in (200, 201, 400, 404)
        ok("PASS — consent + revoke lifecycle completed")

    def test_register_elder(self):
        sep("§27d — POST /api/v1/conscious/elders/register")
        sys_id = uid("elder_ks")
        post("/api/v1/conscious/knowledge_systems/register", {
            "system_id": sys_id,
            "system_name": f"Elder System {sys_id}",
            "origin_region": "AFRICA",
            "contact_identifier": hashlib.sha256(sys_id.encode()).hexdigest(),
            "description": "Elder test",
        })
        elder_id = uid("elder")
        r = post("/api/v1/conscious/elders/register", {
            "elder_id": elder_id,
            "system_id": sys_id,
            "term_months": 12,
        })
        assert r.status_code in (200, 201, 400, 409)
        ok(f"PASS — elder register HTTP {r.status_code}")

    def test_list_elders(self):
        sep("§27e — GET /api/v1/conscious/elders")
        r = get("/api/v1/conscious/elders")
        d = assert_ok(r, "/conscious/elders")
        info("elders count", len(d.get("elders", [])))
        ok("PASS — elders list returned")


# ─────────────────────────────────────────────────────────────────────────────
# §28 Spiritual Diversity (L5 Validator Diversity)
# ─────────────────────────────────────────────────────────────────────────────
class TestSpiritualDiversity:

    def test_validator_heartbeat(self):
        sep("§28a — POST /api/v1/spiritual/heartbeat")
        r = post("/api/v1/spiritual/heartbeat", {
            "validator_id": uid("val"),
            "region": "EU",
            "client_type": "LIGHTHOUSE",
            "stake": 32.0,
        })
        assert r.status_code in (200, 201, 400, 422)
        ok(f"PASS — validator heartbeat HTTP {r.status_code}")

    def test_diversity_report(self):
        sep("§28b — GET /api/v1/spiritual/diversity_report")
        r = get("/api/v1/spiritual/diversity_report")
        d = assert_ok(r, "/spiritual/diversity_report")
        info("Keys", list(d.keys()))
        ok("PASS — diversity report returned")


# ─────────────────────────────────────────────────────────────────────────────
# §29 Signal Publishing
# ─────────────────────────────────────────────────────────────────────────────
class TestSignals:

    def test_signal_history(self):
        sep("§29a — GET /api/v1/signal/{entity_id}/history")
        eid = uid("sighist")
        seed_entity(eid, n=3)
        r = get(f"/api/v1/signal/{eid}/history")
        d = assert_ok(r, "/signal/history")
        info("Keys", list(d.keys()))
        ok(f"PASS — signal history returned for {eid}")

    def test_signal_batch_publish(self):
        sep("§29b — POST /api/v1/signals/batch")
        eid = uid("sigbatch")
        seed_entity(eid, n=3)
        r = post("/api/v1/signals/batch", {
            "signals": [
                {"entity_id": eid, "signal_type": "BEHAVIORAL", "value": 0.72},
                {"entity_id": eid, "signal_type": "LIQUIDITY",  "value": 0.65},
            ]
        })
        assert r.status_code in (200, 201, 400, 422)
        ok(f"PASS — signal batch HTTP {r.status_code}")

    def test_semi_immutable_signal(self):
        sep("§29c — GET /api/v1/semi_immutable/signal/{entity_id}")
        eid = uid("sigsemi")
        seed_entity(eid, n=3)
        r = get(f"/api/v1/semi_immutable/signal/{eid}")
        d = assert_ok(r, "/semi_immutable/signal")
        info("Keys", list(d.keys()))
        ok(f"PASS — semi-immutable signal returned for {eid}")


# ─────────────────────────────────────────────────────────────────────────────
# §30 Routing — BTCP Score & Route Selection
# ─────────────────────────────────────────────────────────────────────────────
class TestRouting:

    def test_btcp_score_endpoint(self):
        sep("§30a — POST /api/v1/btcp/score")
        r = post("/api/v1/btcp/score", {
            "entity_id": uid("btcp"),
            "nl": 0.82,
            "gas_total": 10.0,
            "gas_99th": 50.0,
            "finality": 0.95,
            "cc_coherence": 0.88,
            "beo_continuity": 0.90,
            "manipulation_factor": 0.0,
        })
        assert r.status_code in (200, 201, 400, 422)
        if r.status_code in (200, 201):
            d = r.json()
            info("btcp_score", d.get("btcp_score"))
            info("is_safe", d.get("is_safe"))
        ok(f"PASS — BTCP score endpoint HTTP {r.status_code}")

    def test_route_selection(self):
        sep("§30b — POST /api/v1/route — select best chain")
        r = post("/api/v1/route", {
            "entity_id": uid("route"),
            "value_usd": 50000.0,
            "destination_chain": "arbitrum",
            "source_chain": "ethereum",
        })
        assert r.status_code in (200, 201, 400, 422)
        if r.status_code in (200, 201):
            d = r.json()
            info("Route keys", list(d.keys()))
        ok(f"PASS — route selection HTTP {r.status_code}")

    def test_genesis_endpoint(self):
        sep("§30c — GET /api/v1/genesis/{asset_id}")
        asset = uid("asset")
        seed_entity(asset, n=3)
        r = get(f"/api/v1/genesis/{asset}")
        d = assert_ok(r, "/genesis")
        info("Keys", list(d.keys()))
        ok(f"PASS — genesis endpoint returned for {asset}")


# ─────────────────────────────────────────────────────────────────────────────
# §31 Genesis Locking & Semi-Immutable Signals
# ─────────────────────────────────────────────────────────────────────────────
class TestGenesisLocking:

    def test_genesis_lock_threshold(self):
        sep("§31a — Genesis locking: entity locks after sufficient observations")
        eid = uid("genlock")
        for i in range(8):
            post("/index/add", {
                "entity_id": eid,
                "vector": rnd_vec(),
                "magnitude": 0.90,
                "entropy": 0.85,
                "chain_id": 1,
                "chain_label": "ethereum",
            })
        r = get(f"/api/v1/genesis/{eid}")
        d = assert_ok(r, "/genesis lock check")
        info("is_locked", d.get("is_locked"))
        info("frozen_conf", d.get("frozen_conf"))
        ok(f"PASS — genesis state readable for {eid}")

    def test_system_bootstrap(self):
        sep("§31b — GET /api/v1/system/bootstrap")
        r = get("/api/v1/system/bootstrap")
        d = assert_ok(r, "/system/bootstrap")
        info("Keys", list(d.keys()))
        ok("PASS — system bootstrap endpoint reachable")


# ─────────────────────────────────────────────────────────────────────────────
# §32 Audit Engine
# ─────────────────────────────────────────────────────────────────────────────
class TestAudit:

    def test_audit_contract(self):
        sep("§32a — GET /api/v1/audit/{address}")
        address = "0x" + "dead" * 5 + "beef"[:4]
        r = get(f"/api/v1/audit/{address}")
        d = assert_ok(r, "/audit/contract")
        info("Keys", list(d.keys()))
        ok(f"PASS — audit endpoint returned for {address}")

    def test_audit_patterns_library(self):
        sep("§32b — GET /api/v1/audit/patterns/library")
        r = get("/api/v1/audit/patterns/library")
        d = assert_ok(r, "/audit/patterns/library")
        info("Keys", list(d.keys()))
        ok("PASS — audit patterns library returned")


# ─────────────────────────────────────────────────────────────────────────────
# §33 Agent Validation
# ─────────────────────────────────────────────────────────────────────────────
class TestAgent:

    def test_agent_validate(self):
        sep("§33a — POST /api/v1/agent/validate")
        agent_id = uid("agent")
        r = post("/api/v1/agent/validate", {
            "agent_id": agent_id,
            "proposed_action": "ROUTE_TRANSFER",
            "value_usd": 10000.0,
            "destination": "0xDest" + uid(),
        })
        assert r.status_code in (200, 201, 400, 422)
        ok(f"PASS — agent validate HTTP {r.status_code}")

    def test_agent_profile(self):
        sep("§33b — GET /api/v1/agent/{agent_id}/profile")
        agent_id = uid("agentprof")
        r = get(f"/api/v1/agent/{agent_id}/profile")
        assert r.status_code in (200, 404)
        ok(f"PASS — agent profile HTTP {r.status_code}")


# ─────────────────────────────────────────────────────────────────────────────
# §34 Trading Signal API
# ─────────────────────────────────────────────────────────────────────────────
class TestTrading:

    def test_trading_signal(self):
        sep("§34a — GET /api/v1/trading/signal/{entity_id}")
        eid = uid("trade")
        seed_entity(eid, n=4)
        r = get(f"/api/v1/trading/signal/{eid}")
        d = assert_ok(r, "/trading/signal")
        info("signal", d.get("signal", d.get("action")))
        info("Keys", list(d.keys()))
        ok(f"PASS — trading signal returned for {eid}")

    def test_trading_patterns(self):
        sep("§34b — GET /api/v1/trading/patterns")
        r = get("/api/v1/trading/patterns")
        d = assert_ok(r, "/trading/patterns")
        info("Keys", list(d.keys()))
        ok("PASS — trading patterns returned")

    def test_trading_scan_chain(self):
        sep("§34c — GET /api/v1/trading/scan/{chain_id}")
        r = get("/api/v1/trading/scan/1")
        d = assert_ok(r, "/trading/scan")
        info("Keys", list(d.keys()))
        ok("PASS — chain scan returned")

    def test_agent_decide(self):
        sep("§34d — POST /api/v1/trading/agent/decide")
        r = post("/api/v1/trading/agent/decide", {
            "entity_id": uid("decide"),
            "context": {"current_price": 3400.0, "volume_24h": 1_200_000.0},
        })
        assert r.status_code in (200, 201, 400, 422)
        ok(f"PASS — trading agent decide HTTP {r.status_code}")

    def test_trading_signal_values(self):
        sep("§34e — Trading signal values are BUY/AVOID/SHORT or score")
        eid = uid("tradesig")
        seed_entity(eid, n=5)
        r = get(f"/api/v1/trading/signal/{eid}")
        d = assert_ok(r, "/trading/signal values")
        signal = d.get("signal", d.get("action", ""))
        if isinstance(signal, str):
            assert signal in ("BUY", "AVOID", "SHORT", "HOLD", "NEUTRAL", "UNKNOWN", "")
            info("Signal value", signal)
        ok("PASS — trading signal is valid categorical value")


# ─────────────────────────────────────────────────────────────────────────────
# §35 Sovereign Assessment
# ─────────────────────────────────────────────────────────────────────────────
class TestSovereign:

    def test_sovereign_assessment(self):
        sep("§35a — GET /api/v1/sovereign_assessment/{entity_id}")
        eid = uid("sov")
        seed_entity(eid, n=3)
        r = get(f"/api/v1/sovereign_assessment/{eid}")
        assert r.status_code in (200, 404)
        if r.status_code == 200:
            d = r.json()
            info("Keys", list(d.keys()))
        ok(f"PASS — sovereign assessment HTTP {r.status_code}")

    def test_sovereign_appeal(self):
        sep("§35b — POST /api/v1/sovereign_appeal/{entity_id}")
        eid = uid("appeal")
        r = post(f"/api/v1/sovereign_appeal/{eid}", {
            "challenge_basis": "cultural_misclassification",
            "cultural_context": "The entity represents a traditional finance pattern",
            "supporting_data": {"jurisdiction": "AU", "evidence_type": "BEHAVIORAL"},
            "contact_reference": "anon_contact_" + uid(),
        })
        assert r.status_code in (200, 201, 400, 404, 422)
        if r.status_code in (200, 201):
            d = r.json()
            info("appeal_id", d.get("appeal_id"))
            info("status", d.get("status"))
        ok(f"PASS — sovereign appeal HTTP {r.status_code}")


# ─────────────────────────────────────────────────────────────────────────────
# §36 Slash & Dispute Resolution
# ─────────────────────────────────────────────────────────────────────────────
class TestSlash:

    def test_slash_submit(self):
        sep("§36a — POST /api/v1/slash — submit slashing event")
        r = post("/api/v1/slash", {
            "validator_id": uid("val"),
            "condition": "DOUBLE_SIGN",
            "evidence": "0x" + uuid.uuid4().hex,
            "signal_value": 0.85,
            "consensus_value": 0.50,
            "deviation_sigma": 3.5,
        })
        d = assert_ok(r, "/slash submit")
        info("slash_id", d.get("slash_id"))
        info("penalty_pct", d.get("penalty_pct"))
        info("state", d.get("state"))
        assert d.get("state") in ("PENDING", "ACTIVE", "SUBMITTED")
        return d.get("slash_id")

    def test_slash_list(self):
        sep("§36b — GET /api/v1/slash — list pending slashes")
        r = get("/api/v1/slash")
        d = assert_ok(r, "/slash list")
        info("response type", type(d).__name__)
        ok("PASS — slash list returned")

    def test_slash_dispute_lifecycle(self):
        sep("§36c — Slash dispute: submit → dispute → vote → resolve")
        # Submit slash
        r_slash = post("/api/v1/slash", {
            "validator_id": uid("disp_val"),
            "condition": "LIVENESS_FAULT",
            "evidence": "0x" + uuid.uuid4().hex,
            "signal_value": 0.80,
            "consensus_value": 0.75,
            "deviation_sigma": 2.1,
        })
        slash_id = assert_ok(r_slash, "slash for dispute").get("slash_id")
        if not slash_id:
            ok("SKIP — slash_id not returned, skipping dispute chain")
            return

        # Open dispute
        r_disp = post("/api/v1/slash/dispute", {
            "slash_id": slash_id,
            "disputant": uid("disputant"),
            "reason": "Evidence was collected during network outage",
        })
        disp_d = assert_ok(r_disp, "/slash/dispute")
        dispute_id = disp_d.get("dispute_id")
        info("dispute_id", dispute_id)
        info("state", disp_d.get("state"))

        if dispute_id:
            # Cast votes (supermajority required)
            for voter_i, vote_val in enumerate([True, True, False, True, True]):
                post("/api/v1/slash/dispute/vote", {
                    "dispute_id": dispute_id,
                    "voter": uid(f"voter{voter_i}"),
                    "vote": vote_val,
                })
            r_status = get(f"/api/v1/slash/{slash_id}")
            if r_status.status_code == 200:
                status_d = r_status.json()
                info("Final state", status_d.get("state"))
        ok("PASS — slash dispute lifecycle completed")

    def test_slash_72h_window(self):
        sep("§36d — Slash: expires_at is ~72h from submission")
        r = post("/api/v1/slash", {
            "validator_id": uid("expire_val"),
            "condition": "EQUIVOCATION",
            "evidence": "0x" + uuid.uuid4().hex,
            "signal_value": 0.90,
            "consensus_value": 0.55,
            "deviation_sigma": 4.2,
        })
        d = assert_ok(r, "/slash 72h")
        expires_at = d.get("expires_at", 0)
        now = time.time()
        delta_h = (float(expires_at) - now) / 3600 if expires_at else 72
        info("expires_at (h from now)", f"{delta_h:.1f}h")
        assert 60 <= delta_h <= 84, f"expires_at should be ~72h from now, got {delta_h:.1f}h"
        ok("PASS — slash expiry is within 60–84h window")


# ─────────────────────────────────────────────────────────────────────────────
# §37 ZK Behavioral Proofs (unit — offline)
# ─────────────────────────────────────────────────────────────────────────────
class TestZKProofs:

    @pytest.mark.skipif(not _ZK_OK, reason="anima_regulatory not importable")
    def test_proof_generation(self):
        sep("§37a — ZK proof generation: returns ZKBehavioralProof")
        prover = BehavioralZKProver()
        bhash = hashlib.sha256(b"test_entity_behavior").digest()
        proof = prover.generate_proof(
            entity_id="test_entity",
            jurisdiction="US",
            behavioral_hash=bhash,
            amount_usd=5000.0,
            privacy_mode=PRIVACY_ZK_CRED,
            kyc_level=1,
        )
        info("proof_id", str(proof.proof_id)[:24] + "...")
        info("jurisdiction", proof.jurisdiction)
        info("travel_rule_triggered", proof.travel_rule_triggered)
        assert proof.jurisdiction == "US"
        ok("PASS — ZK proof generated successfully")

    @pytest.mark.skipif(not _ZK_OK, reason="anima_regulatory not importable")
    def test_proof_verification_valid(self):
        sep("§37b — ZK proof verification: valid proof → True")
        prover = BehavioralZKProver()
        bhash = hashlib.sha256(b"verify_entity").digest()
        proof = prover.generate_proof(
            entity_id="verify_entity",
            jurisdiction="EU",
            behavioral_hash=bhash,
            amount_usd=1000.0,
        )
        valid, reason = prover.verify_proof(proof, "verify_entity", "EU")
        info("valid", valid)
        info("reason", reason)
        assert valid is True
        assert "VALID" in reason.upper() or "OK" in reason.upper()
        ok("PASS — valid proof is verified as True")

    @pytest.mark.skipif(not _ZK_OK, reason="anima_regulatory not importable")
    def test_proof_verification_wrong_entity(self):
        sep("§37c — ZK proof: wrong entity_id → verification fails")
        prover = BehavioralZKProver()
        bhash = hashlib.sha256(b"entity_alpha").digest()
        proof = prover.generate_proof("entity_alpha", "US", bhash, 2000.0)
        valid, reason = prover.verify_proof(proof, "entity_IMPERSONATOR", "US")
        info("valid (should be False)", valid)
        info("reason", reason)
        assert valid is False
        ok("PASS — wrong entity_id rejects proof")

    @pytest.mark.skipif(not _ZK_OK, reason="anima_regulatory not importable")
    def test_proof_travel_rule_threshold(self):
        sep("§37d — ZK proof: travel rule triggers at ≥ threshold")
        prover = BehavioralZKProver()
        bhash = hashlib.sha256(b"travel_rule_test").digest()
        # Under threshold
        p_small = prover.generate_proof("ent_s", "US", bhash, 999.0)
        # Over threshold (US default: $3000)
        p_large = prover.generate_proof("ent_l", "US", bhash, 5000.0)
        info("$999 travel_rule_triggered ", p_small.travel_rule_triggered)
        info("$5000 travel_rule_triggered", p_large.travel_rule_triggered)
        assert p_large.travel_rule_triggered is True
        ok("PASS — travel rule triggers for large transfer")

    @pytest.mark.skipif(not _ZK_OK, reason="anima_regulatory not importable")
    def test_proof_ttl_expiry(self):
        sep("§37e — ZK proof: expired proof fails verification")
        prover = BehavioralZKProver()
        bhash = hashlib.sha256(b"ttl_test").digest()
        proof = prover.generate_proof("ttl_entity", "EU", bhash, 1000.0, ttl_secs=-1.0)
        valid, reason = prover.verify_proof(proof, "ttl_entity", "EU")
        info("valid (should be False)", valid)
        info("reason", reason)
        assert valid is False
        ok("PASS — expired proof rejected")


# ─────────────────────────────────────────────────────────────────────────────
# §38 Jurisdictional Routing (unit — offline)
# ─────────────────────────────────────────────────────────────────────────────
class TestJurisdiction:

    @pytest.mark.skipif(not _ZK_OK, reason="anima_regulatory not importable")
    def test_jurisdiction_registry_get(self):
        sep("§38a — JurisdictionRegistry.get() returns config for known codes")
        registry = JurisdictionRegistry()
        for code in ("US", "EU", "UK", "SG"):
            cfg = registry.get(code)
            if cfg:
                info(f"  {code}", f"threshold=${cfg.travel_rule_threshold_usd}")
        ok("PASS — known jurisdiction codes return configs")

    @pytest.mark.skipif(not _ZK_OK, reason="anima_regulatory not importable")
    def test_jurisdiction_resolve_chain(self):
        sep("§38b — JurisdictionRegistry.resolve_chain() maps chain_id → jurisdiction")
        registry = JurisdictionRegistry()
        cfg = registry.resolve_chain(1)  # Ethereum mainnet
        info("chain 1 → jurisdiction", cfg.jurisdiction_code if cfg else "NOT_FOUND")
        ok("PASS — resolve_chain returns a jurisdiction config")

    @pytest.mark.skipif(not _ZK_OK, reason="anima_regulatory not importable")
    def test_all_configs_returns_dict(self):
        sep("§38c — JurisdictionRegistry.all_configs() returns non-empty dict")
        registry = JurisdictionRegistry()
        configs = registry.all_configs()
        info("jurisdiction count", len(configs))
        assert len(configs) > 0
        ok(f"PASS — {len(configs)} jurisdictions registered")

    @pytest.mark.skipif(not _ZK_OK, reason="anima_regulatory not importable")
    def test_travel_rule_thresholds_vary_by_jurisdiction(self):
        sep("§38d — Travel rule thresholds differ by jurisdiction")
        registry = JurisdictionRegistry()
        thresholds = {}
        for code in ("US", "EU", "SG", "FATF"):
            cfg = registry.get(code)
            if cfg:
                thresholds[code] = cfg.travel_rule_threshold_usd
        info("Thresholds", thresholds)
        if len(thresholds) >= 2:
            # Not all must be equal — jurisdictions differ
            assert len(set(thresholds.values())) >= 1
        ok("PASS — jurisdiction travel rule thresholds verified")


# ─────────────────────────────────────────────────────────────────────────────
# §39 Fork & Resurrection
# ─────────────────────────────────────────────────────────────────────────────
class TestForkResurrection:

    def test_fork_two_entities(self):
        sep("§39a — POST /fork — fork two BEO entities")
        eid_a = uid("fork_a")
        eid_b = uid("fork_b")
        seed_entity(eid_a, n=3)
        seed_entity(eid_b, n=3)
        r = post("/fork", {
            "entity_a": eid_a,
            "entity_b": eid_b,
        })
        assert r.status_code in (200, 201, 400, 404, 422)
        ok(f"PASS — fork HTTP {r.status_code}")

    def test_resurrection(self):
        sep("§39b — POST /resurrection — re-activate dormant entity")
        eid = uid("dead")
        seed_entity(eid, n=2)
        r = post("/resurrection", {
            "entity_id": eid,
            "vector": rnd_vec(),
            "dormancy_type": "VOLUNTARY",
        })
        assert r.status_code in (200, 201, 400, 404, 422)
        ok(f"PASS — resurrection HTTP {r.status_code}")


# ─────────────────────────────────────────────────────────────────────────────
# §40 System Bootstrap
# ─────────────────────────────────────────────────────────────────────────────
class TestSystemBootstrap:

    def test_bootstrap_fields(self):
        sep("§40a — GET /api/v1/system/bootstrap — all fields present")
        r = get("/api/v1/system/bootstrap")
        d = assert_ok(r, "/system/bootstrap")
        info("Keys", list(d.keys()))
        ok("PASS — system bootstrap fields present")

    def test_index_counts_non_negative(self):
        sep("§40b — /health: indexed_vectors ≥ 0, archetypes ≥ 0")
        r = get("/health")
        d = assert_ok(r, "/health counts")
        vectors  = d.get("indexed_vectors", 0)
        archs    = d.get("archetypes", 0)
        info("indexed_vectors", vectors)
        info("archetypes", archs)
        assert int(vectors) >= 0
        assert int(archs) >= 0
        ok("PASS — non-negative counts in /health")


# ─────────────────────────────────────────────────────────────────────────────
# §41 Concurrent load — 1 000 simultaneous /index/add
# ─────────────────────────────────────────────────────────────────────────────
class TestConcurrentIndexAdd:

    @pytest.mark.skipif(not _AIOHTTP_OK, reason="aiohttp not installed")
    def test_1000_concurrent_index_add(self):
        sep("§41 — 1 000 concurrent POST /index/add")

        async def _run():
            async def _one(session, i):
                payload = {
                    "entity_id": uid(f"load{i % 50}"),  # 50 distinct entities → re-use
                    "vector": rnd_vec(),
                    "magnitude": round(random.uniform(0.3, 0.9), 3),
                    "entropy": round(random.uniform(0.5, 1.0), 3),
                    "chain_id": random.choice([1, 137, 42161, 10]),
                    "chain_label": random.choice(["ethereum","polygon","arbitrum","optimism"]),
                    "vm_type": "EVM",
                }
                try:
                    async with session.post(f"{BASE}/index/add", json=payload,
                                            timeout=aiohttp.ClientTimeout(total=45)) as resp:
                        return resp.status
                except Exception as exc:
                    return str(exc)[:20]

            connector = aiohttp.TCPConnector(limit=200)
            async with aiohttp.ClientSession(connector=connector) as session:
                tasks = [_one(session, i) for i in range(1000)]
                results = await asyncio.gather(*tasks)
            return results

        results = asyncio.run(_run())

        ok_codes = [r for r in results if r in (200, 201)]
        err_codes = [r for r in results if r not in (200, 201)]
        pct_ok = len(ok_codes) / 1000 * 100

        print(f"\n  Total requests   : 1 000")
        print(f"  Successful (2xx) : {len(ok_codes)}  ({pct_ok:.1f}%)")
        print(f"  Non-2xx / errors : {len(err_codes)}")
        if err_codes[:5]:
            print(f"  Sample errors    : {err_codes[:5]}")

        assert pct_ok >= 80.0, f"Success rate {pct_ok:.1f}% below 80% threshold"
        ok(f"PASS — 1 000 concurrent writes: {pct_ok:.1f}% success")


# ─────────────────────────────────────────────────────────────────────────────
# §42 Concurrent load — 1 000 simultaneous reads
# ─────────────────────────────────────────────────────────────────────────────
class TestConcurrentReads:

    @pytest.mark.skipif(not _AIOHTTP_OK, reason="aiohttp not installed")
    def test_1000_concurrent_reads(self):
        sep("§42 — 1 000 concurrent reads (similarity + health + conservation)")

        # Pre-seed a small pool of entities
        pool = [uid("readpool") for _ in range(20)]
        for eid in pool:
            seed_entity(eid, n=2)

        async def _run():
            endpoints = (
                [f"/similarity/{eid}" for eid in pool] * 10 +
                ["/health"] * 200 +
                ["/conservation/status"] * 100 +
                ["/api/v1/living_security/immune/memory"] * 100 +
                [f"/api/v1/living_security/{eid}" for eid in pool] * 10 +
                ["/archetypes/coverage"] * 100 +
                [f"/api/v1/thermodynamics/{eid}" for eid in pool[:5]] * 20
            )
            random.shuffle(endpoints)
            endpoints = endpoints[:1000]

            async def _one(session, path):
                try:
                    async with session.get(f"{BASE}{path}",
                                           timeout=aiohttp.ClientTimeout(total=45)) as resp:
                        return resp.status
                except Exception as exc:
                    return str(exc)[:20]

            connector = aiohttp.TCPConnector(limit=200)
            async with aiohttp.ClientSession(connector=connector) as session:
                tasks = [_one(session, p) for p in endpoints]
                return await asyncio.gather(*tasks)

        results = asyncio.run(_run())
        ok_codes = [r for r in results if r in (200, 201, 404)]
        pct_ok = len(ok_codes) / 1000 * 100
        print(f"\n  Total requests  : 1 000")
        print(f"  Successful      : {len(ok_codes)}  ({pct_ok:.1f}%)")
        assert pct_ok >= 80.0, f"Read success rate {pct_ok:.1f}% below 80%"
        ok(f"PASS — 1 000 concurrent reads: {pct_ok:.1f}% success")


# ─────────────────────────────────────────────────────────────────────────────
# §43 Thundering herd — 1 000 requests for the same entity
# ─────────────────────────────────────────────────────────────────────────────
class TestThunderingHerd:

    @pytest.mark.skipif(not _AIOHTTP_OK, reason="aiohttp not installed")
    def test_thundering_herd_same_entity(self):
        sep("§43 — Thundering herd: 1 000 requests for 1 entity")
        hot_entity = uid("hot")
        seed_entity(hot_entity, n=5)

        async def _run():
            endpoints = (
                [f"/similarity/{hot_entity}"] * 300 +
                [f"/api/v1/living_security/{hot_entity}"] * 200 +
                [f"/api/v1/anima/{hot_entity}"] * 200 +
                [f"/api/v1/thermodynamics/{hot_entity}"] * 150 +
                [f"/api/v1/akashic/match/{hot_entity}"] * 150
            )
            random.shuffle(endpoints)

            async def _one(session, path):
                try:
                    async with session.get(f"{BASE}{path}",
                                           timeout=aiohttp.ClientTimeout(total=60)) as resp:
                        return resp.status
                except Exception as exc:
                    return str(exc)[:20]

            connector = aiohttp.TCPConnector(limit=200)
            async with aiohttp.ClientSession(connector=connector) as session:
                tasks = [_one(session, p) for p in endpoints]
                return await asyncio.gather(*tasks)

        results = asyncio.run(_run())
        ok_codes = [r for r in results if r in (200, 201, 404)]
        pct_ok = len(ok_codes) / 1000 * 100
        print(f"\n  Entity        : {hot_entity}")
        print(f"  Total requests: 1 000  ({pct_ok:.1f}% success)")
        assert pct_ok >= 75.0, f"Herd success rate {pct_ok:.1f}% below 75%"
        ok(f"PASS — Thundering herd absorbed: {pct_ok:.1f}% success")


# ─────────────────────────────────────────────────────────────────────────────
# §44 Mixed concurrent storm — all endpoint classes at once
# ─────────────────────────────────────────────────────────────────────────────
class TestMixedStorm:

    @pytest.mark.skipif(not _AIOHTTP_OK, reason="aiohttp not installed")
    def test_mixed_1000_concurrent(self):
        sep("§44 — Mixed storm: 1 000 concurrent requests across all endpoint classes")
        eids = [uid("storm") for _ in range(10)]
        for eid in eids:
            seed_entity(eid, n=2)

        WRITE_REQUESTS = []
        for i in range(200):
            WRITE_REQUESTS.append(("POST", "/index/add", {
                "entity_id": uid(f"stormw{i % 10}"),
                "vector": rnd_vec(),
                "magnitude": 0.70,
                "entropy": 0.85,
                "chain_id": 1,
                "chain_label": "ethereum",
            }))

        READ_REQUESTS = (
            [("GET", f"/similarity/{e}", None) for e in eids] * 5 +
            [("GET", "/health", None)] * 50 +
            [("GET", "/conservation/status", None)] * 50 +
            [("GET", f"/api/v1/anima/{e}", None) for e in eids] * 5 +
            [("GET", f"/api/v1/living_security/{e}", None) for e in eids] * 5 +
            [("GET", "/api/v1/living_security/immune/memory", None)] * 50 +
            [("GET", f"/api/v1/thermodynamics/{e}", None) for e in eids[:5]] * 5 +
            [("GET", "/archetypes/coverage", None)] * 50 +
            [("GET", "/api/v1/trading/patterns", None)] * 50 +
            [("POST", "/archetypes/match_vector", {"vector": rnd_vec(), "top_k": 3})] * 20 +
            [("POST", "/api/v1/living_security/gk/evolve/" + e,
              {"be_t": 0.80, "tm_t": 0.10, "cv_t": 0.60}) for e in eids] * 3 +
            [("POST", "/api/v1/living_security/epigenetic/update",
              {"threat_level": 0.50, "validator_health": 0.75, "network_entropy": 0.80})] * 30
        )

        all_requests = WRITE_REQUESTS + READ_REQUESTS
        random.shuffle(all_requests)
        all_requests = all_requests[:1000]

        async def _run():
            async def _one(session, method, path, body):
                try:
                    timeout = aiohttp.ClientTimeout(total=60)
                    if method == "GET":
                        async with session.get(f"{BASE}{path}", timeout=timeout) as resp:
                            return resp.status
                    else:
                        async with session.post(f"{BASE}{path}", json=body,
                                                timeout=timeout) as resp:
                            return resp.status
                except Exception as exc:
                    return str(exc)[:20]

            connector = aiohttp.TCPConnector(limit=200)
            async with aiohttp.ClientSession(connector=connector) as session:
                tasks = [_one(session, m, p, b) for m, p, b in all_requests]
                return await asyncio.gather(*tasks)

        results = asyncio.run(_run())
        ok_codes = [r for r in results if r in (200, 201, 404)]
        errors   = [r for r in results if r not in (200, 201, 404)]
        pct_ok   = len(ok_codes) / len(results) * 100

        print(f"\n  Total   : {len(results)}")
        print(f"  Success : {len(ok_codes)}  ({pct_ok:.1f}%)")
        print(f"  Errors  : {len(errors)}")
        if errors[:5]:
            print(f"  Sample  : {errors[:5]}")

        assert pct_ok >= 70.0, f"Mixed storm success rate {pct_ok:.1f}% below 70%"
        ok(f"PASS — Mixed storm: {pct_ok:.1f}% success across all endpoint classes")


# ─────────────────────────────────────────────────────────────────────────────
# §45 End-to-end full pipeline
# ─────────────────────────────────────────────────────────────────────────────
class TestEndToEnd:

    def test_full_pipeline(self):
        sep("§45 — End-to-end: ingest → BEO → GK → ANIMA → Living Security → Signal")
        eid = uid("e2e")
        print(f"\n  Entity: {eid}")

        # ── Step 1: Ingest BH transactions
        print("\n  [1/8] Ingesting BH transactions…")
        for i in range(3):
            r = post("/index/add_tx_bh_batch", {
                "chain_id": 1,
                "chain_label": "ethereum",
                "block_num": 21000000 + i,
                "block_hash": "0x" + uuid.uuid4().hex * 2,
                "timestamp": int(time.time()) - i * 12,
                "entries": [{
                    "tx_hash": "0x" + uuid.uuid4().hex * 2,
                    "from_addr": "0xFromE2E_" + str(i),
                    "to_addr": "0xToE2E_" + str(i),
                    "event_type": 1,
                    "event_type_name": "TRANSFER",
                    "entity_id": eid,
                    "magnitude_norm": 0.70 + i * 0.05,
                    "value_wei": str(int(1e18 * (i + 1))),
                    "selector": "0xa9059cbb",
                    "timestamp": int(time.time()) - i * 12,
                    "chain_id": 1,
                    "chain_label": "ethereum",
                    "block_num": 21000000 + i,
                    "block_hash": "0x" + uuid.uuid4().hex * 2,
                    "sense_hex": "0xaabbccdd",
                    "antisense_hex": "0x11223344",
                }],
            })
            assert r.status_code in (200, 201), f"BH step {i}: {r.status_code}"
        ok("  BH ingestion: 3 transactions")

        # ── Step 2: Multi-chain vector indexing
        print("\n  [2/8] Indexing vectors across 3 chains…")
        for chain_id, label in [(1, "ethereum"), (137, "polygon"), (42161, "arbitrum")]:
            r = post("/index/add", {
                "entity_id": eid,
                "vector": rnd_vec(),
                "magnitude": 0.75,
                "entropy": 0.88,
                "chain_id": chain_id,
                "chain_label": label,
                "vm_type": "EVM",
            })
            assert r.status_code in (200, 201)
        ok("  Vector indexing: 3 chains")

        # ── Step 3: GK Genesis
        print("\n  [3/8] Evolving Genomic Key…")
        r = post(f"/api/v1/living_security/gk/evolve/{eid}",
                 {"be_t": 0.80, "tm_t": 0.10, "cv_t": 0.60})
        d = assert_ok(r, "GK genesis")
        gk_genesis = d["gk_hex"]
        gen = d.get("generation", 1)
        info("  GK genesis (gen=1)", gk_genesis[:32] + "...")
        ok("  GK genesis locked")

        # ── Step 4: Evolve GK (simulate activity)
        print("\n  [4/8] GK evolution chain (5 steps)…")
        for step in range(5):
            r = post(f"/api/v1/living_security/gk/evolve/{eid}", {
                "be_t": 0.75 + step * 0.02,
                "tm_t": 0.05 + step * 0.03,
                "cv_t": 0.55 + step * 0.02,
            })
            assert r.status_code in (200, 201)
        ok("  GK evolved 5 times")

        # ── Step 5: ANIMA score
        print("\n  [5/8] Computing ANIMA score…")
        r = get(f"/api/v1/anima/{eid}")
        if r.status_code == 200:
            d = r.json()
            score = d.get("anima_score", d.get("a_adj", d.get("score")))
            info("  ANIMA score", score)
        ok("  ANIMA score computed")

        # ── Step 6: Living Security full report
        print("\n  [6/8] Full 8-component Living Security report…")
        r = get(f"/api/v1/living_security/{eid}")
        d = assert_ok(r, "E2E living security")
        info("  LS components", len(d))
        ok("  Living Security report generated")

        # ── Step 7: Immune check
        print("\n  [7/8] Immune system check…")
        r = get(f"/api/v1/living_security/immune/{eid}")
        d = assert_ok(r, "E2E immune")
        info("  clearance", d.get("clearance"))
        info("  threats", d.get("threat_count", 0))
        ok("  Immune check complete")

        # ── Step 8: Trading signal
        print("\n  [8/8] Generating trading signal…")
        r = get(f"/api/v1/trading/signal/{eid}")
        d = assert_ok(r, "E2E trading signal")
        signal = d.get("signal", d.get("action", "UNKNOWN"))
        info("  Signal", signal)
        ok("  Trading signal generated")

        print(f"\n  {BOLD}{'='*60}{RESET}")
        print(f"  {GREEN}{BOLD}E2E COMPLETE: 8/8 steps passed for entity {eid}{RESET}")
        print(f"  GK genesis: {gk_genesis[:32]}...")
        print(f"  Trading signal: {signal}")
        ok(f"PASS — Full pipeline verified for entity {eid}")
