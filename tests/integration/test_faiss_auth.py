"""
SEC-01 / SEC-24 regression — FAISS service API-key authentication
=================================================================

Boots the FAISS service twice (once with FAISS_API_KEY set, once without)
and asserts the enforcement matrix:

  key SET   — health/stats probes stay open; everything else requires
              X-API-Key (401 on missing/invalid key, constant-time compare).
  key UNSET — fail closed: POSTs and the privileged families
              (/index/*, /api/v1/slash*, /api/v1/pqc/sign) return 503;
              health + read-only GETs stay open for local inspection.
              The PQC signing oracle never answers without a key (SEC-24).

Run: pytest tests/integration/test_faiss_auth.py -v
"""
from __future__ import annotations

import json
import math
import os
import random
import socket
import subprocess
import sys
import tempfile
import time
import urllib.error
import urllib.request
from pathlib import Path
from typing import Any, Dict, Optional

import pytest

ROOT = Path(__file__).resolve().parents[2]
# The service under test is booted as a plain subprocess running
# anima-service/faiss_service.py — its own __main__ entry point — so this
# file needs no sys.path surgery (tests/unit/test_no_sys_path_hacks.py
# pins that no new file may introduce any).

_TEST_KEY = "trion-auth-test-key"

# Every env var the service can resolve a key from — stripped for the
# fail-closed boot so an ambient TRION_API_KEY cannot re-enable writes.
_KEY_ENV_VARS = ("FAISS_API_KEY", "FAISS_SERVICE_API_KEY", "TRION_API_KEY")


def _free_port() -> int:
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
        s.bind(("127.0.0.1", 0))
        return s.getsockname()[1]


def _request(url: str, *, method: str = "GET", body: Optional[dict] = None,
              key: Optional[str] = None, timeout: float = 20.0):
    """Fire one HTTP request; returns (status_code, json_or_text)."""
    headers = {"Content-Type": "application/json"}
    if key is not None:
        headers["X-API-Key"] = key
    data = json.dumps(body).encode("utf-8") if body is not None else None
    req = urllib.request.Request(url, data=data, headers=headers, method=method)
    try:
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            raw = resp.read().decode("utf-8", errors="replace")
            return resp.status, _maybe_json(raw)
    except urllib.error.HTTPError as exc:
        raw = exc.read().decode("utf-8", errors="replace")
        return exc.code, _maybe_json(raw)


def _maybe_json(raw: str) -> Any:
    try:
        return json.loads(raw)
    except (ValueError, TypeError):
        return raw


def _rnd_vec(dim: int = 128) -> list:
    v = [random.gauss(0, 1) for _ in range(dim)]
    norm = math.sqrt(sum(x * x for x in v)) or 1.0
    return [x / norm for x in v]


def _add_payload() -> dict:
    return {
        "entity_id": "auth-test-entity",
        "vector": _rnd_vec(),
        "magnitude": 0.5,
        "entropy": 0.7,
        "chain_id": 1,
        "chain_label": "ethereum",
        "vm_type": "EVM",
    }


def _boot(with_key: bool):
    """Boot an isolated FAISS subprocess; returns (base_url, proc, workdir).

    Runs anima-service/faiss_service.py through its own __main__ entry
    point (uvicorn binds 127.0.0.1:$FAISS_PORT). Invoking the script by
    path puts the anima-service directory on the interpreter path for its
    intra-package imports, so the boot needs no sys.path manipulation.
    """
    port = _free_port()
    base_url = f"http://127.0.0.1:{port}"
    workdir = tempfile.mkdtemp(prefix=f"trion_faiss_auth_{'key' if with_key else 'nokey'}_")
    env = os.environ.copy()
    for var in _KEY_ENV_VARS:          # start from a clean auth slate
        env.pop(var, None)
    env.update({
        "FAISS_PORT": str(port),
        "PORT": str(port),
        "FAISS_HOST": "127.0.0.1",     # deterministic loopback bind
        "FAISS_INDEX_PATH": os.path.join(workdir, "akashic_faiss.index"),
        "FAISS_CENTROIDS_PATH": os.path.join(workdir, "trion_archetype_centroids.npy"),
        "FAISS_STATE_DB": os.path.join(workdir, "akashic_state.db"),
        "BH_LEDGER_DB": os.path.join(workdir, "bh_ledger.db"),
    })
    if with_key:
        env["FAISS_API_KEY"] = _TEST_KEY
    proc = subprocess.Popen(
        [sys.executable, str(ROOT / "anima-service" / "faiss_service.py")],
        env=env, cwd=str(ROOT),
        stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True,
    )
    deadline = time.time() + 30.0
    while time.time() < deadline:
        try:
            with urllib.request.urlopen(f"{base_url}/healthz", timeout=3) as resp:
                if resp.status == 200:
                    return base_url, proc, workdir
        except Exception:
            time.sleep(0.5)
    proc.terminate()
    try:
        out = proc.stdout.read(4000) if proc.stdout else ""
    except Exception:
        out = ""
    proc.wait(timeout=10)
    raise RuntimeError(f"FAISS auth-test service did not boot:\n{out}")


def _shutdown(proc, workdir):
    proc.terminate()
    try:
        proc.wait(timeout=10)
    except subprocess.TimeoutExpired:
        proc.kill()
        proc.wait(timeout=5)
    import shutil
    shutil.rmtree(workdir, ignore_errors=True)


# ── Mode 1: FAISS_API_KEY is set ──────────────────────────────────────────────

@pytest.fixture(scope="module")
def keyed_service():
    base_url, proc, workdir = _boot(with_key=True)
    try:
        yield base_url
    finally:
        _shutdown(proc, workdir)


class TestKeyEnabled:

    def test_health_probes_open(self, keyed_service):
        # health/readiness/stats stay public so monitors keep working
        for path in ("/healthz", "/health", "/readyz", "/stats", "/api/v1/health"):
            status, _ = _request(f"{keyed_service}{path}")
            assert status == 200, f"{path} expected 200, got {status}"

    def test_write_without_key_401(self, keyed_service):
        status, body = _request(f"{keyed_service}/index/add",
                                method="POST", body=_add_payload())
        assert status == 401, f"expected 401, got {status}: {body}"

    def test_write_with_wrong_key_401(self, keyed_service):
        status, body = _request(f"{keyed_service}/index/add",
                                method="POST", body=_add_payload(), key="wrong-key")
        assert status == 401, f"expected 401, got {status}: {body}"

    def test_write_with_valid_key_200(self, keyed_service):
        status, body = _request(f"{keyed_service}/index/add",
                                method="POST", body=_add_payload(), key=_TEST_KEY)
        assert status == 200, f"expected 200, got {status}: {body}"

    def test_read_route_requires_key(self, keyed_service):
        # non-public GETs are locked too when a key is configured
        status, _ = _request(f"{keyed_service}/vm-status")
        assert status == 401
        status, body = _request(f"{keyed_service}/vm-status", key=_TEST_KEY)
        assert status == 200, f"expected 200, got {status}: {body}"

    def test_pqc_sign_oracle_requires_key(self, keyed_service):
        # SEC-24: the ML-DSA signing oracle must not answer unauthenticated
        url = f"{keyed_service}/api/v1/pqc/sign?message_hex=deadbeef"
        status, body = _request(url, method="POST")
        assert status == 401, f"expected 401, got {status}: {body}"
        status, body = _request(url, method="POST", key="wrong-key")
        assert status == 401
        status, body = _request(url, method="POST", key=_TEST_KEY)
        assert status == 200, f"expected 200, got {status}: {body}"
        assert "public_key_hex" in body


# ── Mode 2: FAISS_API_KEY unset (fail-closed) ─────────────────────────────────

@pytest.fixture(scope="module")
def unkeyed_service():
    base_url, proc, workdir = _boot(with_key=False)
    try:
        yield base_url
    finally:
        _shutdown(proc, workdir)


class TestKeyUnsetFailClosed:

    def test_health_and_reads_still_work(self, unkeyed_service):
        for path in ("/healthz", "/health", "/stats"):
            status, _ = _request(f"{unkeyed_service}{path}")
            assert status == 200, f"{path} expected 200, got {status}"
        # read-only GETs stay open for local inspection
        for path in ("/vm-status", "/bh/stats"):
            status, body = _request(f"{unkeyed_service}{path}")
            assert status == 200, f"{path} expected 200, got {status}: {body}"

    def test_write_refused_503(self, unkeyed_service):
        status, body = _request(f"{unkeyed_service}/index/add",
                                method="POST", body=_add_payload())
        assert status == 503, f"expected 503, got {status}: {body}"
        assert "FAISS_API_KEY" in json.dumps(body)

    def test_pqc_sign_disabled(self, unkeyed_service):
        # SEC-24: never an unauthenticated signing oracle
        status, body = _request(
            f"{unkeyed_service}/api/v1/pqc/sign?message_hex=deadbeef", method="POST")
        assert status == 503, f"expected 503, got {status}: {body}"

    def test_slash_family_blocked_even_on_get(self, unkeyed_service):
        status, _ = _request(f"{unkeyed_service}/api/v1/slash")
        assert status == 503

    def test_beo_write_refused(self, unkeyed_service):
        status, body = _request(f"{unkeyed_service}/beo/resolve_batch",
                                method="POST", body={"addresses": ["0xabc"]})
        assert status == 503, f"expected 503, got {status}: {body}"
