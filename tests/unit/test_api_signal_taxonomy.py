"""API signal-type alignment — the M-073 29-type canonical taxonomy view.

Wave-6 pins for the 11-a follow-up (the api lane of the taxonomy ruling):

  * /api/v1/signal/types reports the canonical view: 29 taxonomy rows
    (19 base §11 + 10 BTCP-family, the two dual-family rows flagged),
    27 distinct closed-set names, and the full 24-member on-chain id
    mapping (29 rows + registry_v2_extended together cover ids 0-23).
  * /api/v1/signal/type/<t>/<id> accepts every closed-set name (27, in
    their ruling spellings) plus the registry spellings that remain
    emittable (V2 extended + the two internal drift names).
  * Response-shape backward compatibility for the dynamic consumers —
    the frontends read total + signal_types[].{id,name,description}
    dynamically (11-a's survey; no static type maps exist).

The closed-set source of truth is imported read-only from the core
registry (core/master/signal_factory) — same single source the endpoint
itself consumes; nothing is re-declared here.

Run: pytest tests/unit/test_api_signal_taxonomy.py -q
"""
import os

os.environ.setdefault("TRION_STREAMER_INPROCESS", "0")

import pytest  # noqa: E402 — env must be set before the api.app import

import api.app as api_app  # noqa: E402 — import side effects match sibling tests
from api.app import app  # noqa: E402
from core.master.signal_factory import (  # noqa: E402 — read-only source of truth
    BTCP_DOMAIN_SIGNALS, SignalType, RULING_CLOSED_SET_27, RULING_NAME_ALIASES,
    signal_registry,
)

COLD_ENTITY = "0x" + "4c" * 20

# The registry spellings /signal/type still accepts beyond the closed set:
# the V2 Part 5 members outside the taxonomy + the internal drift names.
EXTRA_ACCEPTED = (
    "NEGATIVE_SPACE", "INSTITUTIONAL_BHV", "ECOSYSTEM_HEALTH", "BOOTSTRAP",
    "REGULATORY_BHV", "MEV_EXPOSURE",
)


@pytest.fixture(autouse=True)
def _fresh_rate_limit():
    """Start every request from a clean rate-limit slate."""
    with api_app._rl_lock:
        api_app._rl_buckets.clear()


@pytest.fixture()
def cold_client(monkeypatch):
    """Cold-start client — no FAISS sediment, no live services.

    _query_faiss_planes returning None is the documented cold-start
    sentinel (same premise as test_api_cold_start.py).
    """
    monkeypatch.setattr(api_app, "_query_faiss_planes", lambda eid: None)
    return app.test_client()


class TestSignalTypesCanonicalView:

    def test_reports_the_29_type_taxonomy(self, cold_client):
        r = cold_client.get("/api/v1/signal/types")
        assert r.status_code == 200
        j = r.get_json()
        assert j["total"] == 29
        assert len(j["signal_types"]) == 29
        assert j["canonical_per_whitepaper"] == 19
        assert j["extended_beyond_whitepaper"] == 10
        assert j["closed_set_distinct"] == 27
        assert j["dual_family"] == ["BTCP_ROUTE", "CONSENSUS_ADAPTATION"]
        assert "dual_family_note" in j and "27" in j["dual_family_note"]

    def test_rows_are_19_base_plus_10_family(self, cold_client):
        j = cold_client.get("/api/v1/signal/types").get_json()
        rows = j["signal_types"]
        base = [t for t in rows if t["family"] == "base_19"]
        family = [t for t in rows if t["family"] == "btcp_family_10"]
        assert len(base) == 19 and len(family) == 10
        # Base rows carry the §11 (ruling) spelling as whitepaper_name.
        assert {t["whitepaper_name"] for t in base} == set(signal_registry()["ruling_base_19"])
        # Family rows cite the BTCP master spec — §2's six + §14.2's four.
        assert [t["source"] for t in family[:6]] == ["BTCP master spec §2"] * 6
        assert [t["source"] for t in family[6:]] == ["BTCP master spec §14.2"] * 4

    def test_dual_family_rows_listed_once_per_family(self, cold_client):
        j = cold_client.get("/api/v1/signal/types").get_json()
        dual_rows = [t for t in j["signal_types"] if t["dual_family"]]
        names = sorted(t["name"] for t in dual_rows)
        assert names == ["BTCP_ROUTE", "BTCP_ROUTE",
                         "CONSENSUS_ADAPTATION", "CONSENSUS_ADAPTATION"]
        assert sorted(t["family"] for t in dual_rows if t["name"] == "BTCP_ROUTE") \
            == ["base_19", "btcp_family_10"]
        assert sorted(t["family"] for t in dual_rows if t["name"] == "CONSENSUS_ADAPTATION") \
            == ["base_19", "btcp_family_10"]

    def test_full_24_member_id_mapping_stays_exposed(self, cold_client):
        """29 rows + registry_v2_extended together cover enum ids 0-23 —
        the on-chain id mapping the endpoint has always exposed."""
        j = cold_client.get("/api/v1/signal/types").get_json()
        ids = sorted({t["id"] for t in j["signal_types"] + j["registry_v2_extended"]})
        assert ids == list(range(24))          # dense 0-23 parity
        v2_names = [t["name"] for t in j["registry_v2_extended"]]
        assert v2_names == ["NEGATIVE_SPACE", "INSTITUTIONAL_BHV",
                            "ECOSYSTEM_HEALTH", "BOOTSTRAP"]

    def test_domain_rows_ride_canonical_carriers(self, cold_client):
        j = cold_client.get("/api/v1/signal/types").get_json()
        by_name = {t["name"]: t for t in j["signal_types"]}
        for name, meta in BTCP_DOMAIN_SIGNALS.items():
            row = by_name[name]
            assert row["carrier"] == meta["carrier"], name
            assert row["signal_subtype"] == name
            assert row["id"] == int(SignalType[meta["carrier"]]), name

    def test_backward_compat_response_shape(self, cold_client):
        """The pre-29 keys all survive (dynamic frontend consumers)."""
        j = cold_client.get("/api/v1/signal/types").get_json()
        for key in ("total", "canonical_per_whitepaper", "extended_beyond_whitepaper",
                    "signal_types", "name_drift", "parity_note", "whitepaper",
                    "timestamp"):
            assert key in j, key
        # Every row keeps the fields the Signal Type Catalog table renders.
        for t in j["signal_types"]:
            for key in ("id", "name", "whitepaper_name", "source", "description"):
                assert key in t, (t["name"], key)
        # The §11 ↔ internal drift translation is unchanged.
        assert j["name_drift"] == [
            {"whitepaper_name": "REGULATORY_BEHAVIORAL",
             "internal_name": "REGULATORY_BHV", "id": 16},
            {"whitepaper_name": "MEV_BEHAVIORAL",
             "internal_name": "MEV_EXPOSURE", "id": 14},
        ]


class TestSignalByTypeClosedSet:

    def test_all_27_closed_set_names_answer_200(self, cold_client):
        """The core pin: every M-073 closed-set name is emittable."""
        for tn in RULING_CLOSED_SET_27:
            r = cold_client.get(f"/api/v1/signal/type/{tn}/{COLD_ENTITY}")
            assert r.status_code == 200, (tn, r.status_code)
            assert r.get_json(silent=True) is not None, (tn, "no JSON body")

    def test_registry_spellings_still_accepted(self, cold_client):
        """Backward compatibility: pre-ruling spellings keep answering."""
        for tn in EXTRA_ACCEPTED:
            r = cold_client.get(f"/api/v1/signal/type/{tn}/{COLD_ENTITY}")
            assert r.status_code == 200, (tn, r.status_code)

    def test_ruling_aliases_resolve_to_the_same_emission(self, cold_client):
        for ruling, internal in RULING_NAME_ALIASES.items():
            a = cold_client.get(f"/api/v1/signal/type/{ruling}/{COLD_ENTITY}").get_json()
            b = cold_client.get(f"/api/v1/signal/type/{internal}/{COLD_ENTITY}").get_json()
            assert a["signal_type"] == b["signal_type"] == internal
            assert a["signal_type_id"] == b["signal_type_id"] == int(SignalType[internal])

    def test_btcp_domain_types_ride_carriers(self, cold_client):
        for name, meta in BTCP_DOMAIN_SIGNALS.items():
            j = cold_client.get(f"/api/v1/signal/type/{name}/{COLD_ENTITY}").get_json()
            assert j["signal_subtype"] == name
            assert j["signal_type"] == meta["carrier"]
            assert j["signal_type_id"] == int(SignalType[meta["carrier"]])
            assert j["is_synthetic"] is True

    def test_behavioral_truth_carries_seven_plane_results(self, cold_client):
        j = cold_client.get(f"/api/v1/signal/type/BEHAVIORAL_TRUTH/{COLD_ENTITY}").get_json()
        assert len(j["plane_results"]) == 7
        assert all(isinstance(p, bool) for p in j["plane_results"])
        assert j["planes_checked"] == 7
        assert j["coherent_7_plane"] == all(j["plane_results"])
        # Dark Field: the commitment is a hash, never behavior content.
        assert len(j["public_commitment"]) == 2 + 64

    def test_btcp_timeout_mirrors_revert_on_timeout_guard(self, cold_client):
        """timeout_reached == current > lock + timeout (the .vy assert)."""
        j = cold_client.get(f"/api/v1/signal/type/BTCP_TIMEOUT/{COLD_ENTITY}").get_json()
        assert j["timeout_blocks"] > 0
        assert j["timeout_reached"] == (
            j["current_block"] > j["lock_block"] + j["timeout_blocks"])
        assert j["intent_preserved"] is True

    def test_liquidity_ocean_routability_rule(self, cold_client):
        """Score > 0 → routable; only zero is thermodynamic death (D3-144)."""
        j = cold_client.get(f"/api/v1/signal/type/LIQUIDITY_OCEAN/{COLD_ENTITY}").get_json()
        assert j["routable_liquidity"] == (j["ocean_score"] > 0)
        assert set(j["form_breakdown"]) and isinstance(j["estimated_slippage"], float)

    def test_btcp_escrow_event_state_is_canonical(self, cold_client):
        j = cold_client.get(f"/api/v1/signal/type/BTCP_ESCROW_EVENT/{COLD_ENTITY}").get_json()
        assert j["escrow_state"] in ("HOLDING", "RELEASED", "REVERTED")

    def test_unknown_type_is_400_with_closed_set_listed(self, cold_client):
        r = cold_client.get(f"/api/v1/signal/type/NOT_A_TYPE/{COLD_ENTITY}")
        assert r.status_code == 400
        j = r.get_json()
        assert set(RULING_CLOSED_SET_27) <= set(j["valid_types"])
        assert set(EXTRA_ACCEPTED) <= set(j["valid_types"])
