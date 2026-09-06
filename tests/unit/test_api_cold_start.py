"""Cold-start regression battery — signal routes on FAISS-empty entities.

An entity with no behavioral sediment in FAISS must never crash the API:
_compute_signal returns a typed SILENCE/COLD_START dict that deliberately
omits plane_breakdown (no planes were observed), and the per-type signal
route builds its coherence_result dict from that base.  Two pre-existing
500s lived on this path (verified at HEAD c0ccb14):

  * signal_by_type read base["plane_breakdown"] directly — KeyError for
    every COLD_START entity on every /api/v1/signal/type/* request.
  * the GOVERNANCE_SIGNAL branch indexed h[32]/h[33]/h[34] of a 32-byte
    sha3-256 digest — IndexError on every governance signal request.

Both are now pinned: all 19 whitepaper §11 signal types must answer 200
with a parseable JSON body for a cold entity, and the governance payload
fields the digest-overflow bytes feed must be well-formed.

Run: pytest tests/unit/test_api_cold_start.py -q
"""
import os

os.environ.setdefault("TRION_STREAMER_INPROCESS", "0")

import pytest  # noqa: E402 — env must be set before the api.app import

import api.app as api_app  # noqa: E402 — import side effects match sibling tests
from api.app import app  # noqa: E402

COLD_ENTITY = "0x" + "9a" * 20

# The 19 whitepaper §11 signal types accepted by /api/v1/signal/type/*
# (the route's documented type list — Section 11).
SECTION_11_TYPES = (
    "VALUATION", "SILENCE", "MANIPULATION_ALERT", "GENESIS", "RESURRECTION",
    "FORK_DIVERGENCE", "TRAJECTORY", "NEGATIVE_SPACE", "PHASE_TRANSITION",
    "SYSTEMIC_RISK", "LIQUIDITY_HEALTH", "GOVERNANCE_SIGNAL",
    "CROSS_CHAIN_COHERENCE", "STABLECOIN_HEALTH", "MEV_EXPOSURE",
    "INSTITUTIONAL_BHV", "REGULATORY_BHV", "ECOSYSTEM_HEALTH", "BOOTSTRAP",
)


@pytest.fixture(autouse=True)
def _fresh_rate_limit():
    """Start every request from a clean rate-limit slate."""
    with api_app._rl_lock:
        api_app._rl_buckets.clear()


@pytest.fixture()
def cold_client(monkeypatch):
    """Test client with the entity guaranteed COLD_START (no FAISS sediment).

    _query_faiss_planes returning None is the documented cold-start
    sentinel — this pins the trigger itself, so the battery stays valid
    even when a live FAISS service happens to be running next to the
    test process.
    """
    monkeypatch.setattr(api_app, "_query_faiss_planes", lambda eid: None)
    return app.test_client()


class TestColdStartSignalRoutes:

    def test_plain_signal_route_emits_cold_start_silence(self, cold_client):
        """Guards the battery's own premise: the entity IS cold."""
        r = cold_client.get(f"/api/v1/signal/{COLD_ENTITY}")
        assert r.status_code == 200, r.status_code
        j = r.get_json()
        assert j["signal_type"] == "SILENCE"
        assert j["signal_subtype"] == "COLD_START"
        assert j["coherence_score"] == 0.0

    def test_full_signal_route_survives_cold_start(self, cold_client):
        r = cold_client.get(f"/api/v1/signal/{COLD_ENTITY}/full")
        assert r.status_code == 200, r.status_code
        assert r.get_json()["signal_subtype"] == "COLD_START"

    def test_all_section11_types_answer_200_on_cold_start(self, cold_client):
        """Bug pin 1: base["plane_breakdown"] KeyError → every type 500'd."""
        for tn in SECTION_11_TYPES:
            r = cold_client.get(f"/api/v1/signal/type/{tn}/{COLD_ENTITY}")
            assert r.status_code == 200, (tn, r.status_code)
            assert r.get_json(silent=True) is not None, (tn, "no JSON body")

    def test_silence_cold_start_carries_bootstrap_flags(self, cold_client):
        """The derived bootstrap planes must stay truthful (all unobserved)."""
        r = cold_client.get(f"/api/v1/signal/type/SILENCE/{COLD_ENTITY}")
        assert r.status_code == 200
        j = r.get_json()
        # signal_factory emits plane-level bootstrap disclosure via the
        # coherence_result we built — the cold entity never fabricates values.
        assert j["signal_type"] == "SILENCE"
        assert "limiting_plane" in j

    def test_bootstrap_type_reports_no_planes_bootstrapped(self, cold_client):
        """A cold entity has bootstrapped NOTHING — 0.0 defaults keep that honest."""
        r = cold_client.get(f"/api/v1/signal/type/BOOTSTRAP/{COLD_ENTITY}")
        assert r.status_code == 200
        planes = r.get_json()["planes_bootstrapped"]
        assert planes == {"sigma": False, "k": False, "anima": False}

    def test_negative_space_absence_significance_finite(self, cold_client):
        """absence_significance = |expected − physical| with physical 0.0."""
        r = cold_client.get(f"/api/v1/signal/type/NEGATIVE_SPACE/{COLD_ENTITY}")
        assert r.status_code == 200
        j = r.get_json()
        assert isinstance(j["absence_significance"], float)
        assert 0.0 <= j["absence_significance"] <= 1.0

    def test_governance_signal_cold_start_fields(self, cold_client):
        """Bug pin 2: h[33]/h[34] IndexError → GOVERNANCE_SIGNAL 500'd."""
        r = cold_client.get(f"/api/v1/signal/type/GOVERNANCE_SIGNAL/{COLD_ENTITY}")
        assert r.status_code == 200, r.status_code
        j = r.get_json()
        assert isinstance(j["validator_count"], int)
        assert 5 <= j["validator_count"] <= 24
        assert j["active_proposal"].startswith("PROP-")
        assert len(j["active_proposal"]) == len("PROP-") + 4
        assert isinstance(j["awa_enforced"], bool)
        assert isinstance(j["signals_frozen"], bool)
        assert j["signals_frozen"] == (not j["awa_enforced"])

    def test_unknown_type_is_400_not_500(self, cold_client):
        r = cold_client.get(f"/api/v1/signal/type/NOT_A_TYPE/{COLD_ENTITY}")
        assert r.status_code == 400
        assert "valid_types" in r.get_json()
