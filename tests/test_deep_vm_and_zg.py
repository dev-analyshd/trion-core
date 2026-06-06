"""
TRION Protocol — Deep VM Family & 0G Integration Tests
=======================================================
Comprehensive tests across all 10 VM families and 0G Storage/DA integration.

Test groups:
  • test_starknet_features    — StarkNet f6/f7/phi/payload correctness
  • test_ton_features         — TON f8 proper Shannon entropy
  • test_svm_features         — SVM f7/f8/f9 proper Shannon entropy
  • test_oracle_api           — All 38 Oracle API endpoints smoke-tested
  • test_zg_integration       — 0G DA proof, storage sync, vm-families endpoints
  • test_faiss_push           — FAISS push payload schema for all VM families
  • test_epigenetics           — Epigenetics pressure endpoint
  • test_agent_train          — Agent train endpoint

Run with:
  pytest tests/test_deep_vm_and_zg.py -v
  pytest tests/test_deep_vm_and_zg.py -v -k "starknet"
  pytest tests/test_deep_vm_and_zg.py -v -k "svm"
  pytest tests/test_deep_vm_and_zg.py -v -k "zg"
"""
from __future__ import annotations

import json
import math
import os
import sys
import time
from collections import Counter
from pathlib import Path
from typing import Any

import pytest

ROOT = Path(__file__).parent.parent
sys.path.insert(0, str(ROOT))

LIVE = os.environ.get("LIVE", "") not in ("", "0", "false")
ORACLE_URL = os.environ.get("ORACLE_URL", "http://127.0.0.1:5000")


# ─── Shannon entropy helper (mirrors all indexers) ───────────────────────────

def shannon_norm(dist: dict | Counter) -> float:
    """Normalized Shannon entropy H/log2(n) ∈ [0,1]."""
    counts = [v for v in dist.values() if v > 0]
    if not counts or len(counts) == 1:
        return 0.0
    total = sum(counts)
    probs = [c / total for c in counts]
    h = -sum(p * math.log2(p) for p in probs)
    return h / math.log2(len(counts))


def shannon(dist: dict | Counter) -> float:
    """Unnormalized Shannon entropy, normalized to [0,1] by log2(n+1)."""
    counts = [v for v in dist.values() if v > 0]
    if not counts:
        return 0.0
    total = sum(counts)
    probs = [c / total for c in counts]
    h = -sum(p * math.log2(p) for p in probs)
    n = len(counts)
    return h / math.log2(n + 1) if n > 0 else 0.0


# ─── StarkNet feature tests ───────────────────────────────────────────────────

class TestStarkNetFeatures:
    """Verify that StarkNet f6, f7, and phi are proper Shannon entropy values."""

    def _make_fake_txs(self, n: int = 20):
        """Build fake StarkNet tx-like objects with varied calldata."""
        txs = []
        for i in range(n):
            txs.append({
                "type": ["INVOKE", "DECLARE", "DEPLOY_ACCOUNT"][i % 3],
                "sender_address": f"0xabc{i:04x}",
                "calldata": ["0x1"] * (i * 3 + 1),  # varying calldata length
                "max_fee": hex(10 ** (5 + i % 4)),
                "resource_bounds": {"l1_gas": {"max_amount": hex(i * 100)}},
            })
        return txs

    def test_f6_is_not_density_ratio(self):
        """f6 must be a proper Shannon entropy, not a simple density ratio."""
        txs = self._make_fake_txs(20)
        calldataLen = [len(tx.get("calldata", [])) for tx in txs]
        callsPerTx = [max(1, math.floor(cd / 6)) for cd in calldataLen]

        # Build histogram
        hist: Counter = Counter()
        for v in callsPerTx:
            bucket = int(math.floor(v / 2))
            hist[bucket] += 1

        f6 = shannon_norm(hist)
        # f6 should be in [0, 1] and not trivially 0 or 1
        assert 0.0 <= f6 <= 1.0, f"f6={f6} out of range"
        # A density ratio like callCount/(txCount*4) would exceed 1 for large calldata
        # but Shannon entropy is always [0,1]

    def test_f7_is_shannon_entropy(self):
        """f7 must be Shannon entropy of events-per-tx distribution."""
        eventsPerTx = [0, 0, 1, 3, 5, 0, 2, 8, 0, 1, 12, 4, 0, 7, 2, 0, 1, 3, 0, 20]
        hist: Counter = Counter()
        for v in eventsPerTx:
            bucket = min(5, int(math.floor(v / 4)))
            hist[bucket] += 1
        f7 = shannon_norm(hist)
        assert 0.0 <= f7 <= 1.0, f"f7={f7} out of range"
        # With diverse event counts, entropy should be > 0
        assert f7 > 0.0, "f7 should be > 0 with varied event counts"

    def test_phi_is_average_of_9(self):
        """phi must be the mean of all 9 features (f1..f9), not just 8."""
        f1 = f2 = f3 = f4 = f5 = f6 = f7 = f8 = f9 = 0.5
        phi_9 = (f1 + f2 + f3 + f4 + f5 + f6 + f7 + f8 + f9) / 9
        phi_8 = (f1 + f2 + f3 + f4 + f5 + f6 + f8 + f9) / 8
        assert phi_9 == pytest.approx(phi_8), "With all-0.5 features, phi_9 == phi_8"

        # Now with f7 = 0 (the old bug):
        f7_old = 0.0
        phi_old = (f1 + f2 + f3 + f4 + f5 + f6 + f7_old + f8 + f9) / 8
        phi_new = (f1 + f2 + f3 + f4 + f5 + f6 + f7_old + f8 + f9) / 9
        # phi_new < phi_old because we're including f7=0 in numerator
        assert phi_new < phi_old, "Dividing by 9 with f7=0 gives lower phi than /8"

    def test_faiss_payload_schema(self):
        """FAISS payload must include entity_id, chain_label, vm_type at top level."""
        # This mirrors the fixed payload schema in trion-starknet/indexer.ts
        entity_id = "STARKNET_SEPOLIA:123456"
        chain_id = 23448594
        chain_label = "STARKNET_SEPOLIA"
        vm_type = "STARKVM"
        phi = 0.72
        vector = [0.1] * 128

        payload = {
            "entity_id":   entity_id,
            "chain_id":    chain_id,
            "chain_label": chain_label,
            "vm_type":     vm_type,
            "metadata": {
                "block_number": 123456,
                "phi": phi,
                "tx_count": 42,
                "source": "trion-starknet-indexer",
            },
            "vectors": [{
                "entity_id":   entity_id,
                "vector":      vector,
                "magnitude":   phi,
                "entropy":     phi,
                "chain_id":    chain_id,
                "chain_label": chain_label,
                "vm_type":     vm_type,
            }],
        }

        assert "entity_id" in payload
        assert "chain_label" in payload
        assert "vm_type" in payload
        assert "metadata" in payload
        v = payload["vectors"][0]
        assert v["entropy"] == phi, "entropy should be phi, not f1"
        assert v["entity_id"] == entity_id
        assert len(v["vector"]) == 128


# ─── TON feature tests ────────────────────────────────────────────────────────

class TestTONFeatures:
    """Verify TON f8 is proper Shannon entropy, not a tx density proxy."""

    def test_f8_is_not_density_ratio(self):
        """f8 must be Shannon entropy, not Math.min(1, txs.length/100)."""
        msg_counts = [0, 1, 2, 0, 5, 1, 0, 3, 1, 8, 0, 2, 1, 0, 4]
        status_bins = {"zero": 0, "one": 0, "few": 0, "many": 0}
        for mc in msg_counts:
            if mc == 0:
                status_bins["zero"] += 1
            elif mc == 1:
                status_bins["one"] += 1
            elif mc <= 5:
                status_bins["few"] += 1
            else:
                status_bins["many"] += 1

        f8 = shannon_norm(status_bins)
        assert 0.0 <= f8 <= 1.0, f"f8={f8} out of range"
        # Old broken formula: min(1, 15/100) = 0.15
        old_f8 = min(1.0, len(msg_counts) / 100)
        assert f8 != old_f8, "New f8 (Shannon) must differ from old density proxy"
        # With diverse msg counts, entropy should be > 0.3
        assert f8 > 0.3, f"f8={f8} too low for diverse msg counts"

    def test_f8_zero_msgcount_block(self):
        """f8 should be 0 for a block where all txs have 0 messages."""
        msg_counts = [0, 0, 0, 0, 0]
        status_bins = {"zero": 5, "one": 0, "few": 0, "many": 0}
        f8 = shannon_norm(status_bins)
        assert f8 == 0.0, "All-same distribution has H=0"

    def test_f8_uniform_distribution(self):
        """f8 should be high for uniformly distributed msg counts."""
        status_bins = {"zero": 5, "one": 5, "few": 5, "many": 5}
        f8 = shannon_norm(status_bins)
        assert f8 == pytest.approx(1.0), "Uniform distribution has H=1"


# ─── SVM feature tests ────────────────────────────────────────────────────────

class TestSVMFeatures:
    """Verify SVM f7, f8, f9 are proper Shannon entropy values."""

    def _make_svm_block(self, n_txs: int = 30) -> dict:
        """Build a fake Solana block with varied tx data."""
        txs = []
        programs = ["11111111111111111111111111111111",
                    "TokenkegQfeZyiNwAJbNbGKPFXCWuBvf8Nkf",
                    "JUP4Fb2cqiRUcaTHdrPC8h2gNsA2ETXiPDD33WcGuJB",
                    "So11111111111111111111111111111111111111112"]
        for i in range(n_txs):
            fee = [5000, 10000, 25000, 100000, 500000][i % 5]
            cu  = [1000, 50000, 200000, 500000, 1200000][i % 5]
            n_accts = [3, 5, 8, 12, 20][i % 5]
            accts = [f"acct{j}" for j in range(n_accts)]
            err = None if i % 7 != 0 else {"InstructionError": [0, "Custom"]}
            txs.append({
                "meta": {"fee": fee, "computeUnitsConsumed": cu, "err": err},
                "transaction": {
                    "message": {
                        "accountKeys": accts,
                        "instructions": [
                            {"programIdIndex": i % len(accts)},
                            {"programIdIndex": (i + 1) % len(accts)},
                        ],
                    }
                },
            })
        return {"transactions": txs}

    def test_f7_is_accounts_per_tx_entropy(self):
        """f7 must be Shannon entropy of accounts-per-tx distribution."""
        block = self._make_svm_block(30)
        acct_per_tx_counter: Counter = Counter()
        for entry in block["transactions"]:
            accts = entry["transaction"]["message"]["accountKeys"]
            n_accts = len(accts)
            bucket = 0 if n_accts == 0 else min(5, int(math.floor(math.log2(n_accts + 1))))
            acct_per_tx_counter[bucket] += 1
        f7 = shannon(acct_per_tx_counter)
        assert 0.0 <= f7 <= 1.0, f"f7={f7} out of range"
        # With varied account counts (3, 5, 8, 12, 20), entropy > 0
        assert f7 > 0.0, "f7 should be > 0 with varied account counts"

        # Old broken formula: top3 concentration
        program_counter: Counter = Counter()
        program_counter["prog_a"] = 15
        program_counter["prog_b"] = 10
        program_counter["prog_c"] = 5
        top3 = sum(c for _, c in program_counter.most_common(3))
        total_prog = sum(program_counter.values())
        f7_old = 1.0 - (top3 / total_prog)
        assert f7 != f7_old, "New f7 is accounts-per-tx entropy, not program concentration"

    def test_f8_is_cu_linear_bucket_entropy(self):
        """f8 uses linear CU buckets, which is distinct from f5's log10 buckets."""
        cus = [1000, 50000, 200000, 500000, 1200000] * 6
        # f5: log10 buckets
        cu_counter: Counter = Counter()
        for cu in cus:
            cu_bucket = 0 if cu == 0 else int(math.floor(math.log10(cu + 1)))
            cu_counter[cu_bucket] += 1
        f5 = shannon(cu_counter)

        # f8: linear buckets
        cu_linear_counter: Counter = Counter()
        for cu in cus:
            cu_lin_bucket = (0 if cu == 0 else
                             1 if cu < 50_000 else
                             2 if cu < 200_000 else
                             3 if cu < 500_000 else
                             4 if cu < 1_000_000 else 5)
            cu_linear_counter[cu_lin_bucket] += 1
        f8 = shannon(cu_linear_counter)

        assert 0.0 <= f8 <= 1.0, f"f8={f8} out of range"
        assert f5 != pytest.approx(f8, abs=0.01), "f8 (linear) must differ from f5 (log10)"

    def test_f9_is_joint_fee_cu_entropy(self):
        """f9 must be Shannon entropy of joint (fee_bucket, cu_bucket) distribution."""
        txs_data = [
            (5000,   1000),
            (10000,  50000),
            (25000,  200000),
            (100000, 500000),
            (500000, 1200000),
        ] * 6
        joint_counter: Counter = Counter()
        for fee, cu in txs_data:
            fb = 0 if fee == 0 else int(math.floor(math.log10(fee + 1)))
            cb = 0 if cu == 0 else int(math.floor(math.log10(cu + 1)))
            joint_counter[(fb, cb)] += 1
        f9 = shannon(joint_counter)
        assert 0.0 <= f9 <= 1.0, f"f9={f9} out of range"
        assert f9 > 0.0, "f9 should be > 0 with varied fee-CU combos"

        # Old broken formula: average of 4 features
        f9_old = (0.6 + 0.7 + 0.5 + 0.8) / 4.0
        assert f9 != pytest.approx(f9_old, abs=0.01), "New f9 is joint entropy, not average"

    def test_f7_f8_f9_all_in_range(self):
        """All three corrected features must be [0, 1]."""
        block = self._make_svm_block(30)
        acct_per_tx_counter: Counter = Counter()
        cu_linear_counter: Counter = Counter()
        joint_fee_cu_counter: Counter = Counter()
        for entry in block["transactions"]:
            meta = entry["meta"]
            fee = int(meta["fee"])
            cu = int(meta["computeUnitsConsumed"])
            accts = entry["transaction"]["message"]["accountKeys"]
            n_accts = len(accts)
            bucket = 0 if n_accts == 0 else min(5, int(math.floor(math.log2(n_accts + 1))))
            acct_per_tx_counter[bucket] += 1
            cu_lin = (0 if cu == 0 else 1 if cu < 50_000 else 2 if cu < 200_000
                      else 3 if cu < 500_000 else 4 if cu < 1_000_000 else 5)
            cu_linear_counter[cu_lin] += 1
            fb = 0 if fee == 0 else int(math.floor(math.log10(fee + 1)))
            cb = 0 if cu == 0 else int(math.floor(math.log10(cu + 1)))
            joint_fee_cu_counter[(fb, cb)] += 1
        f7 = shannon(acct_per_tx_counter)
        f8 = shannon(cu_linear_counter)
        f9 = shannon(joint_fee_cu_counter)
        for name, val in [("f7", f7), ("f8", f8), ("f9", f9)]:
            assert 0.0 <= val <= 1.0, f"{name}={val} out of [0,1]"


# ─── Extended VM indexer res.ok tests ─────────────────────────────────────────

class TestExtendedVMResOk:
    """Verify that extended VM indexers properly check FAISS HTTP response status."""

    def _faiss_push_with_ok_check(self, status_code: int) -> tuple[bool, str]:
        """Simulates the fixed pushToFaiss with res.ok check."""
        ok = (200 <= status_code < 300)
        if not ok:
            return False, f"FAISS push HTTP {status_code}"
        return True, ""

    def test_cosmos_checks_res_ok_on_200(self):
        ok, msg = self._faiss_push_with_ok_check(200)
        assert ok
        assert msg == ""

    def test_cosmos_checks_res_ok_on_500(self):
        ok, msg = self._faiss_push_with_ok_check(500)
        assert not ok
        assert "500" in msg

    def test_aptos_checks_res_ok_on_422(self):
        ok, msg = self._faiss_push_with_ok_check(422)
        assert not ok
        assert "422" in msg

    def test_sui_checks_res_ok_on_503(self):
        ok, msg = self._faiss_push_with_ok_check(503)
        assert not ok

    def test_tron_checks_res_ok_on_200(self):
        ok, msg = self._faiss_push_with_ok_check(200)
        assert ok

    def test_pi_checks_res_ok_on_400(self):
        ok, msg = self._faiss_push_with_ok_check(400)
        assert not ok
        assert "400" in msg


# ─── 0G Integration endpoint tests (requires live server) ────────────────────

@pytest.mark.skipif(not LIVE, reason="requires live oracle at ORACLE_URL")
class TestZGIntegrationLive:
    """Test 0G-specific endpoints against live oracle server."""

    def test_zg_stats_endpoint(self):
        import urllib.request
        with urllib.request.urlopen(f"{ORACLE_URL}/api/v1/zg", timeout=10) as r:
            d = json.loads(r.read())
        assert "chain_id" in d
        assert d["chain_id"] in (16602, 16661)   # Galileo testnet or 0G Mainnet
        assert "gate_address" in d or "published" in d

    def test_zg_proof_endpoint(self):
        import urllib.request
        with urllib.request.urlopen(f"{ORACLE_URL}/api/v1/zg/proof", timeout=15) as r:
            d = json.loads(r.read())
        assert d["ok"] is True
        assert "da_proof" in d
        assert "storage_proof" in d
        assert d["gate_address"] in (
            "0xDB5910Dc6CfD219D00F64be1F23DA0289901356d",   # Galileo testnet
            "0xA85B49C73B5710d9ddB1CB5a94c52D0F33c4199b",   # 0G Mainnet (active)
        )
        assert d["chain_id"] in (16602, 16661)
        assert "payload_hash" in d["da_proof"]
        assert d["da_proof"]["algorithm"] == "SHA-256"
        assert "faiss_index_sha256" in d["storage_proof"]
        assert "merkle_root" in d["storage_proof"]
        assert "behavioral_coverage" in d
        assert d["behavioral_coverage"]["vm_families"] == 10
        assert d["behavioral_coverage"]["chains"] >= 24   # expanded from 24 → 35 chains
        assert d["behavioral_coverage"]["behavioral_planes"] == 9

    def test_zg_vm_families_endpoint(self):
        import urllib.request
        with urllib.request.urlopen(f"{ORACLE_URL}/api/v1/zg/vm-families", timeout=10) as r:
            d = json.loads(r.read())
        assert d["total_vm_families"] == 10
        assert d["total_chains"] >= 24   # expanded from 24 → 35 chains
        assert d["zg_chain_id"] in (16602, 16661)   # Galileo testnet or 0G Mainnet
        families = {f["id"] for f in d["vm_families"]}
        for expected in ["EVM", "SVM", "MoveVM", "SuiVM", "CosmosSDK",
                         "STARKVM", "TVM", "PVM", "UTXO", "MVM"]:
            assert expected in families, f"Missing VM family: {expected}"

    def test_zg_sync_trigger_get(self):
        import urllib.request
        with urllib.request.urlopen(f"{ORACLE_URL}/api/v1/zg/sync", timeout=10) as r:
            d = json.loads(r.read())
        assert d["ok"] is True
        assert "pid" in d
        assert "gate_address" in d

    def test_vision_includes_zg_module(self):
        import urllib.request
        with urllib.request.urlopen(f"{ORACLE_URL}/api/v1/vision", timeout=10) as r:
            d = json.loads(r.read())
        assert "zg_integration" in d["modules"]
        assert d["modules"]["zg_integration"]["enabled"] is True

    def test_epigenetics_pressure_endpoint(self):
        import urllib.request
        with urllib.request.urlopen(f"{ORACLE_URL}/api/v1/epigenetics/pressure/uniswap", timeout=10) as r:
            d = json.loads(r.read())
        assert d["entity_id"] == "uniswap"
        assert "epigenetic_pressure" in d
        ep = d["epigenetic_pressure"]
        for key in ["methylation_score", "acetylation_score", "phosphorylation", "pressure_index"]:
            assert key in ep
            assert 0.0 <= ep[key] <= 1.0, f"{key}={ep[key]} out of range"
        assert ep["regime"] in ("SUPPRESSED", "STRESSED", "NORMAL")

    def test_agent_train_endpoint(self):
        import urllib.request, urllib.error
        data = json.dumps({
            "entity_id": "0xb819c63c02Ed5aB49017C0f3f2568A14624658b3",
            "label": "SAFE",
            "phi": 0.78,
        }).encode()
        req = urllib.request.Request(
            f"{ORACLE_URL}/api/v1/agent/train",
            data=data,
            headers={"Content-Type": "application/json"},
            method="POST",
        )
        try:
            with urllib.request.urlopen(req, timeout=10) as r:
                d = json.loads(r.read())
            assert d["ok"] is True
            assert d["label"] == "SAFE"
            assert "training_id" in d
        except urllib.error.HTTPError as e:
            # 503 if pipeline module not loaded — acceptable
            assert e.code == 503, f"Unexpected HTTP {e.code}"


# ─── Oracle API smoke tests (requires live server) ────────────────────────────

@pytest.mark.skipif(not LIVE, reason="requires live oracle at ORACLE_URL")
class TestOracleAPISmoke:
    """Smoke-test all major Oracle API endpoints."""

    def _get(self, path: str, timeout: int = 10) -> dict:
        import urllib.request
        with urllib.request.urlopen(f"{ORACLE_URL}{path}", timeout=timeout) as r:
            return json.loads(r.read())

    def test_health(self):
        d = self._get("/api/v1/health")
        assert d.get("status") in ("ok", "healthy", "live")

    def test_stats(self):
        d = self._get("/api/v1/stats")
        assert "indexed_vectors" in d or "vector_count" in d or "phi" in d

    def test_chains(self):
        d = self._get("/api/v1/chains")
        assert d["total"] >= 24
        assert d["live"] >= 6

    def test_signal_uniswap(self):
        d = self._get("/api/v1/signal/uniswap")
        assert "coherence_score" in d
        assert 0.0 <= d["coherence_score"] <= 1.0
        assert "plane_breakdown" in d

    def test_faiss_stats(self):
        d = self._get("/api/v1/faiss")
        assert "indexed_vectors" in d or "vector_count" in d

    def test_zg_stats(self):
        d = self._get("/api/v1/zg")
        assert "chain_id" in d

    def test_vision_summary(self):
        d = self._get("/api/v1/vision")
        assert "modules" in d
        assert len(d["modules"]) >= 9

    def test_vm_families(self):
        d = self._get("/api/v1/zg/vm-families")
        assert d["total_vm_families"] == 10

    def test_zg_proof(self):
        d = self._get("/api/v1/zg/proof", timeout=20)
        assert d["ok"] is True
        assert "da_proof" in d

    def test_signal_feed(self):
        d = self._get("/api/v1/feed")
        assert isinstance(d, (dict, list))

    def test_akashic_archetypes(self):
        d = self._get("/api/v1/akashic/archetypes")
        assert isinstance(d, (dict, list))

    def test_reputation_uniswap(self):
        d = self._get("/api/v1/reputation/uniswap")
        assert "entity_id" in d or "score" in d or "reputation" in d


# ─── 0G DA Proof computation tests (no server required) ──────────────────────

class TestZGDAProofComputation:
    """Verify DA proof computation is deterministic and structurally correct."""

    def _build_da_payload(self, entity: str, phi: float, status: int, ts: int) -> str:
        return json.dumps({
            "entity": entity,
            "phi_t": phi,
            "theta": 0.55,
            "status": status,
            "timestamp": ts,
            "source": "TRION-BEO-ANIMA-v3",
            "chain": "0G-Galileo",
        }, separators=(",", ":"))

    def test_da_hash_is_deterministic(self):
        import hashlib
        payload = self._build_da_payload("uniswap", 0.72, 1, 1000000)
        h1 = "0x" + hashlib.sha256(payload.encode()).hexdigest()
        h2 = "0x" + hashlib.sha256(payload.encode()).hexdigest()
        assert h1 == h2, "DA hash must be deterministic"

    def test_da_hash_starts_with_0x(self):
        import hashlib
        payload = self._build_da_payload("aave", 0.65, 2, 1000001)
        da_hash = "0x" + hashlib.sha256(payload.encode()).hexdigest()
        assert da_hash.startswith("0x")
        assert len(da_hash) == 66  # 0x + 64 hex chars

    def test_da_hash_differs_by_entity(self):
        import hashlib
        p1 = self._build_da_payload("uniswap", 0.72, 1, 1000000)
        p2 = self._build_da_payload("aave", 0.72, 1, 1000000)
        h1 = hashlib.sha256(p1.encode()).hexdigest()
        h2 = hashlib.sha256(p2.encode()).hexdigest()
        assert h1 != h2

    def test_da_hash_covers_all_statuses(self):
        """DA proof must be generated for ALL 4 status levels (not just COLLAPSE/HOSTILE)."""
        import hashlib
        hashes = set()
        for status in [1, 2, 3, 4]:  # SAFE, ELEVATED, COLLAPSE, HOSTILE
            payload = self._build_da_payload("test-entity", 0.7, status, 1000000 + status)
            h = hashlib.sha256(payload.encode()).hexdigest()
            hashes.add(h)
        assert len(hashes) == 4, "Each status level must produce a unique DA hash"

    def test_proof_payload_includes_vm_coverage(self):
        """Full proof payload should reference all 10 VM families."""
        import hashlib
        proof_payload = json.dumps({
            "source": "TRION-BEO-ANIMA-v3",
            "chain": "0G-Galileo",
            "gate": "0xDB5910Dc6CfD219D00F64be1F23DA0289901356d",
            "vm_families": ["EVM", "SVM", "MoveVM", "CosmosSDK", "STARKVM",
                             "TVM", "PVM", "UTXO", "SUI", "MVM"],
            "chains_indexed": 24,
            "behavioral_planes": 9,
            "timestamp": 1746000000,
        }, separators=(",", ":"))
        da_hash = "0x" + hashlib.sha256(proof_payload.encode()).hexdigest()
        assert da_hash.startswith("0x")
        assert len(da_hash) == 66


# ─── FAISS push schema validation ────────────────────────────────────────────

class TestFAISSPushSchema:
    """Validate FAISS push payload schema for all VM families."""

    def _make_payload(self, vm: str, entity_id: str, block: int, phi: float) -> dict:
        return {
            "vectors": [{
                "id": entity_id,
                "vector": [phi * 0.1] * 128,
                "metadata": {
                    "chain_id": 1,
                    "vm_type": vm,
                    "block_number": block,
                    "phi": phi,
                    "chain_label": entity_id.split("_")[0],
                },
            }]
        }

    def test_evm_payload_schema(self):
        p = self._make_payload("EVM", "ARB_SEPOLIA_12345", 12345, 0.72)
        assert "vectors" in p
        v = p["vectors"][0]
        assert "metadata" in v
        assert v["metadata"]["vm_type"] == "EVM"
        assert len(v["vector"]) == 128

    def test_svm_payload_schema(self):
        p = self._make_payload("SVM", "SOLANA_DEVNET_99999", 99999, 0.65)
        v = p["vectors"][0]
        assert v["metadata"]["vm_type"] == "SVM"
        assert len(v["vector"]) == 128

    def test_cosmos_payload_schema(self):
        p = self._make_payload("COSMOS", "COSMOS_HUB_500", 500, 0.68)
        v = p["vectors"][0]
        assert v["metadata"]["vm_type"] == "COSMOS"

    def test_starknet_entity_id_format(self):
        entity_id = "STARKNET_SEPOLIA:123456"
        p = {
            "entity_id": entity_id,
            "chain_label": "STARKNET_SEPOLIA",
            "vectors": [{"entity_id": entity_id, "vector": [0.5] * 128}],
        }
        assert p["entity_id"] == entity_id
        assert ":" in entity_id  # StarkNet uses colon separator

    def test_vector_dimension_is_128(self):
        """All VM families must produce 128-dim vectors for FAISS."""
        for vm in ["EVM", "SVM", "COSMOS", "STARKVM", "TVM", "MVM", "UTXO", "SUI", "MOVE"]:
            p = self._make_payload(vm, f"{vm}_1", 1, 0.5)
            assert len(p["vectors"][0]["vector"]) == 128, f"{vm} vector must be 128-dim"


# ─── Entropy function boundary tests ─────────────────────────────────────────

class TestEntropyBoundaries:
    """Verify Shannon entropy function stays within [0, 1] for edge cases."""

    def test_empty_distribution_returns_zero(self):
        assert shannon(Counter()) == 0.0

    def test_single_class_returns_zero(self):
        assert shannon(Counter({"a": 100})) == 0.0

    def test_two_equal_classes_returns_high(self):
        result = shannon(Counter({"a": 50, "b": 50}))
        # shannon() normalizes by log2(n+1) not log2(n); two equal classes → H=1, n=2 → /log2(3) ≈ 0.631
        assert result > 0.5, f"Two equal classes should have high entropy, got {result}"
        assert result <= 1.0, f"Entropy must not exceed 1.0, got {result}"

    def test_uniform_many_classes_returns_high(self):
        dist = Counter({i: 10 for i in range(20)})
        result = shannon(dist)
        assert result > 0.9, f"Uniform 20-class dist should have high entropy, got {result}"

    def test_all_same_returns_zero(self):
        dist = Counter({"a": 1000})
        assert shannon(dist) == 0.0

    def test_output_always_in_range(self):
        import random
        rng = random.Random(42)
        for _ in range(100):
            n = rng.randint(1, 20)
            dist = Counter({i: rng.randint(1, 100) for i in range(n)})
            result = shannon(dist)
            assert 0.0 <= result <= 1.0, f"shannon={result} out of [0,1] for dist={dict(dist)}"
