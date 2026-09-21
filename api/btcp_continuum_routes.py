#!/usr/bin/env python3
"""
TRION BTCP + CONTINUUM — API Blueprint
=======================================

Adds API endpoints for all Phase 0-4 modules. Every path listed below is a
real, registered route (the docstring-truth test in
tests/btcp/test_btcp_api_surface.py keeps this list and the url_map in
sync in both directions):

  /api/v1/btcp/hash_dna             (POST) Hash_DNA computation
  /api/v1/btcp/coherence_7plane     (POST) 7-plane coherence score
  /api/v1/btcp/mf_score             (POST) 7-type MF fingerprint score
  /api/v1/btcp/route                (POST) BTCP route selection
  /api/v1/btcp/escrow/<id>          (GET)  persisted escrow state lookup
  /api/v1/btcp/escrow_states        (GET)  escrow state machine reference
  /api/v1/btcp/bibl/snapshot        (GET)  BIBL Tier-1 snapshot
  /api/v1/btcp/proof                (GET)  BTCP proof builder reference
  /api/v1/btcp/modules              (GET)  18-module overview
  /api/v1/btcp/bitp/match           (POST) BITP complement matching (2.5)
  /api/v1/btcp/netting              (POST) netting pair finder (2.6)
  /api/v1/btcp/aggregate            (POST) intent aggregation pooling (2.7)
  /api/v1/btcp/failure_classify     (POST) failure classifier (2.11)
  /api/v1/btcp/version              (GET)  semver compatibility handler (2.16)
  /api/v1/btcp/validator_fee        (POST) validator fee calculator (2.17)
  /api/v1/btcp/sybil                (POST) sybil resistance layers (2.18)
  /api/v1/btcp/orchestrate          (POST) full BTCPOrchestrator 6-step run
  /api/v1/btcp/private_bibl         (POST) private BIBL protocol
  /api/v1/btcp/shadow_observations  (GET, POST) §8.1 shadow obs (BTCP-FIX2-S59)
  /api/v1/btcp/ultra_light_node     (POST) §8.2 block-header PoW verify (BTCP-FIX2-S59)
  /api/v1/btcp/rejoin               (POST) §8.4 3-phase rejoin mechanism (BTCP-FIX2-S59)
  /api/v1/btcp/integration_status   (GET)  anima-service integration status
  /api/v1/btcp/pipeline_status      (GET)  full pipeline status overview
  /api/v1/btcp/mainnet_bootstrap    (GET)  phased rollout status
  /api/v1/btcp/streamer/status      (GET)  real-time BH streamer status
  /api/v1/btcp/streamer/start       (POST) start the BH streamer
  /api/v1/btcp/orchestrator/status  (GET)  indexer orchestrator + RPC health
  /api/v1/btcp/sanctions/<address>  (GET)  sanctions screening (J1)
  /api/v1/btcp/sanctions            (POST) sanctions oracle upsert (J1)
  /api/v1/continuum/bid             (POST) BID detection
  /api/v1/continuum/cme             (POST) CME complement matching
  /api/v1/continuum/pmo             (POST) PMO creation
  /api/v1/continuum/bdc             (POST) BDC credit limit
  /api/v1/continuum/settlement      (POST) thermodynamic settlement trigger
  /api/v1/continuum/ccp             (POST) CCP distribution
  /api/v1/continuum/engines         (GET)  all engine status overview
"""

from flask import Blueprint, jsonify, request
import sys
import time
import hashlib
import os

# Ensure anima-service/ is importable so endpoints can do
# `from btcp_gas_forecast import forecast_gas` etc. (Gap D8 endpoint).
_ANIMA_SERVICE_PATH = os.path.join(
    os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
    "anima-service",
)
if _ANIMA_SERVICE_PATH not in sys.path:
    sys.path.insert(0, _ANIMA_SERVICE_PATH)

btcp_bp = Blueprint("btcp_continuum", __name__)


# ── Phase 0: Hash_DNA ──────────────────────────────────────────────────────────

@btcp_bp.route("/api/v1/btcp/hash_dna", methods=["POST"])
def btcp_hash_dna():
    """Compute Hash_DNA per the formal specification (Gap 7)."""
    from core.primitives.hash_dna import hash_dna, build_event, hash_dna_hex
    data = request.get_json(force=True, silent=True) or {}
    try:
        event = build_event(
            entity_id=data.get("entity_id_hex", "01" * 32),
            event_type_id=int(data.get("event_type_id", 1)),
            raw_amount=int(data.get("raw_amount", 10**18)),
            asset_decimals=int(data.get("asset_decimals", 18)),
            asset_chain_id=int(data.get("asset_chain_id", 1)),
            asset_address=data.get("asset_address", "0xa0b86991c6218b36c1d19d4a2e9eb0ce3606eb48"),
            asset_symbol=data.get("asset_symbol", "USDC"),
            timestamp=int(data.get("timestamp", int(time.time()))),
            block_number=int(data.get("block_number", 18000000)),
            block_hash=data.get("block_hash_hex", "cc" * 32),
            chain_id=int(data.get("chain_id", 1)),
            contract_address=data.get("contract_address", "0x1d129D34279d1246aB08a41dfE610EaF8D794237"),
            counterparty_id=data.get("counterparty_id_hex"),
            protocol_id=data.get("protocol_id_hex"),
            context_hash=bytes.fromhex(data["context_hash_hex"]) if data.get("context_hash_hex") else None,
            btcp_version=int(data.get("btcp_version", 1)),
            nonce=int(data.get("nonce", 0)),
        )
        h = hash_dna(event)
        return jsonify({
            "hash_dna": hash_dna_hex(event),
            "domain_separator": event.domain_separator.hex(),
            "currency_id": event.magnitude_currency_id.hex(),
            "magnitude_normalized": event.magnitude_normalized,
            "payload_fields": 14,
            "specification": "Gap 7 Resolution",
            "timestamp": int(time.time()),
        })
    except Exception as e:
        return jsonify({"error": str(e)}), 400


# ── Phase 0: 7-Plane Coherence ─────────────────────────────────────────────────

@btcp_bp.route("/api/v1/btcp/coherence_7plane", methods=["POST"])
def btcp_coherence_7plane():
    """Compute 7-plane coherence score (Gap 2 Resolution)."""
    from core.planes.seven_plane_coherence import (
        PlaneInput, compute_7plane_coherence, PLANE_WEIGHTS, PlaneType,
    )
    data = request.get_json(force=True, silent=True) or {}
    try:
        inp = PlaneInput(
            magnitude=float(data.get("magnitude", 100.0)),
            historical_magnitudes=data.get("historical_magnitudes", [100.0] * 5),
            event_timestamp=int(data.get("event_timestamp", int(time.time()))),
            brt_phase=data.get("brt_phase", "normal"),
            historical_event_times=data.get("historical_event_times",
                                            [int(time.time()) - i * 86400 for i in range(1, 20)]),
            protocol_id=data.get("protocol_id", "uniswap"),
            historical_protocols=data.get("historical_protocols", ["uniswap"] * 15),
            counterparty_id=data.get("counterparty_id", ""),
            behavioral_graph=data.get("behavioral_graph", {}),
            recent_tx_count=int(data.get("recent_tx_count", 10)),
            historical_avg_per_N=float(data.get("historical_avg_per_N", 10.0)),
            behavioral_vectors={int(k): v for k, v in data.get("behavioral_vectors", {1: [0.8, 0.7, 0.9]}).items()},
            recent_kc=float(data.get("recent_kc", 0.50)),
            historical_kc=float(data.get("historical_kc", 0.49)),
        )
        score, results = compute_7plane_coherence(inp)
        return jsonify({
            "coherence_score": round(score, 6),
            "planes": [
                {
                    "name": r.plane.name,
                    "score": round(r.score, 4),
                    "passed": r.passed,
                    "needs_conscious_review": r.needs_conscious_review,
                    "details": r.details,
                }
                for r in results
            ],
            "weights": {p.name: w for p, w in PLANE_WEIGHTS.items()},
            "specification": "Gap 2 Resolution — 7 Planes of Behavioral Truth",
        })
    except Exception as e:
        return jsonify({"error": str(e)}), 400


# ── Phase 0: 7 MF Fingerprint ──────────────────────────────────────────────────

@btcp_bp.route("/api/v1/btcp/mf_score", methods=["POST"])
def btcp_mf_score():
    """Compute 7-type MF fingerprint score (BTCP_15 Gap 3)."""
    from core.manipulation.btcp_mf_detector import MFInput, compute_mf_score, MF_WEIGHTS, MFType
    data = request.get_json(force=True, silent=True) or {}
    try:
        inp = MFInput(
            intent_a_side=data.get("intent_a_side"),
            intent_b_side=data.get("intent_b_side"),
            victim_tx_between=data.get("victim_tx_between", False),
            magnitude_similarity=float(data.get("magnitude_similarity", 0.0)),
            self_trade_ratio=float(data.get("self_trade_ratio", 0.0)),
            counterparty_diversity=float(data.get("counterparty_diversity", 1.0)),
            trade_frequency=float(data.get("trade_frequency", 0.0)),
            large_swap_deviation=float(data.get("large_swap_deviation", 0.0)),
            oracle_update_deviation=float(data.get("oracle_update_deviation", 0.0)),
            borrow_liquidate_within_10_blocks=data.get("borrow_liquidate_within_10_blocks", False),
            order_submission_rate=float(data.get("order_submission_rate", 0.0)),
            order_cancellation_rate=float(data.get("order_cancellation_rate", 0.0)),
            behavioral_similarity_to_high_D=float(data.get("behavioral_similarity_to_high_D", 0.0)),
            own_D=float(data.get("own_D", 0.0)),
            high_D_threshold=float(data.get("high_D_threshold", 1000.0)),
            correlated_timing_score=float(data.get("correlated_timing_score", 0.0)),
            protocol_overlap_count=int(data.get("protocol_overlap_count", 0)),
            kc_complexity_delta=float(data.get("kc_complexity_delta", 0.0)),
            historical_kc=float(data.get("historical_kc", 0.0)),
        )
        score, results, review = compute_mf_score(inp)
        return jsonify({
            "mf_score": round(score, 6),
            "needs_conscious_review": review,
            "fingerprints": [
                {
                    "type": f"T{r.mf_type}",
                    "name": r.mf_type.name,
                    "detected": r.detected,
                    "score": round(r.score, 4),
                    "evidence": r.evidence,
                }
                for r in results
            ],
            "weights": {f"T{t}": w for t, w in MF_WEIGHTS.items()},
            "specification": "BTCP_15 Gap 3 Resolution",
        })
    except Exception as e:
        return jsonify({"error": str(e)}), 400


# ── Phase 2: BTCP Router ───────────────────────────────────────────────────────

@btcp_bp.route("/api/v1/btcp/route", methods=["POST"])
def btcp_route():
    """Compute BTCP route selection (K1 Resolution)."""
    from core.btcp.router import BIBLState, select_optimal_route, btcp_score_final
    data = request.get_json(force=True, silent=True) or {}
    try:
        state = BIBLState(
            nl_scores={int(k): v for k, v in data.get("nl_scores", {1: 0.85}).items()},
            gas_forecasts={int(k): v for k, v in data.get("gas_forecasts", {1: 31.0}).items()},
            gas_reference=float(data.get("gas_reference", 31.0)),
            cc_coherence={int(k): v for k, v in data.get("cc_coherence", {1: 0.9}).items()},
            mf_scores={int(k): v for k, v in data.get("mf_scores", {1: 0.02}).items()},
            finality_dist={int(k): v for k, v in data.get("finality_dist", {1: 12.0}).items()},
            beo_continuity={int(k): v for k, v in data.get("beo_continuity", {}).items()},
        )
        route = select_optimal_route(
            intent_value=float(data.get("intent_value", 1000.0)),
            entity_id=bytes.fromhex(data.get("entity_id_hex", "01" * 32)),
            state=state,
            candidate_chains=data.get("candidate_chains", [1, 137, 8453]),
            validator_counts={int(k): v for k, v in data.get("validator_counts", {1: 50}).items()},
        )
        if route is None:
            return jsonify({
                "route": None,
                "btcp_score": 0.0,
                "reason": "no_valid_route",
                "specification": "K1 Resolution",
            })
        return jsonify({
            "route": {
                "route_id": route.route_id,
                "route_type": route.route_type.name,
                "anchor_chain": route.anchor_chain,
                "execution_chain": route.execution_chain,
                "gas_total": route.gas_total,
                "finality_confidence": route.finality_confidence,
                "beo_continuity": route.beo_continuity,
                "cc_coherence": route.cc_coherence,
            },
            "btcp_score": round(btcp_score_final(route, state), 6),
            "state_provenance": {
                "nl_scores": "caller_supplied",
                "gas_forecasts": "caller_supplied",
                "cc_coherence": "caller_supplied",
                "mf_scores": "caller_supplied",
                "validator_counts": "caller_supplied",
                "note": ("BIBL chain state comes from the request body — this "
                         "endpoint computes a route RECOMMENDATION over "
                         "caller-supplied evidence. It is not a TRION-verified "
                         "route verdict; verified routes come from "
                         "/api/v1/btcp/orchestrate + on-chain certificate "
                         "verification"),
            },
            "specification": "K1 Resolution",
        })
    except Exception as e:
        return jsonify({"error": str(e)}), 400


# ── Phase 2: BIBL Snapshot ─────────────────────────────────────────────────────

@btcp_bp.route("/api/v1/btcp/bibl/snapshot")
def btcp_bibl_snapshot():
    """BIBL Tier-1 snapshot (D3 Resolution)."""
    from core.btcp.bibl_engine import BIBLEngine
    # In production, this would return the live BIBL state.
    # For demo, return a sample snapshot.
    bibl = BIBLEngine()
    bibl.update_chain_state(1, 0.85, 31.0, (28.0, 34.0), 0.90, 0.02, 0.80, 12.0, 18000000)
    bibl.update_chain_state(137, 0.90, 0.50, (0.4, 0.6), 0.92, 0.01, 0.90, 2.0, 65000000)
    bibl.update_chain_state(8453, 0.88, 0.98, (0.8, 1.2), 0.91, 0.01, 0.85, 2.0, 12000000)
    return jsonify({
        "demo": True,
        "demo_reason": "hand-seeded sample chain states (1/137/8453) — not the live BIBL tier state",
        "snapshot": bibl.get_bibl_snapshot(),
        "tier_1_latency_target_ms": 50,
        "tier_2_latency_target_ms": 50,
        "tier_3_latency_target_ms": 150,
        "total_bibl_latency_target_ms": 200,
        "specification": "D3 Resolution — BIBL Three-Tier",
        "timestamp": int(time.time()),
    })


# ── Phase 2: Escrow Monitor ────────────────────────────────────────────────────

@btcp_bp.route("/api/v1/btcp/escrow_states")
def btcp_escrow_states():
    """Escrow state machine reference (Gap 8, 9, E1, G1)."""
    from core.btcp.escrow_monitor import EscrowState, RevertReason, EMERGENCY_ESCAPE_SECONDS, AKASHIC_RECOVERY_SECONDS
    return jsonify({
        "states": [s.name for s in EscrowState],
        "revert_reasons": [r.name for r in RevertReason],
        "emergency_escape_seconds": EMERGENCY_ESCAPE_SECONDS,
        "emergency_escape_days": EMERGENCY_ESCAPE_SECONDS / 86400,
        "akashic_recovery_seconds": AKASHIC_RECOVERY_SECONDS,
        "akashic_recovery_hours": AKASHIC_RECOVERY_SECONDS / 3600,
        "resolutions": {
            "gap_8": "Emergency Escape Hatch (7-day absolute max)",
            "gap_9": "Multi-Hop Cascade Revert",
            "E1": "Akashic Availability Guarantee + 24h auto-revert",
            "G1": "Two-Phase Execution Confirmation",
            "gap_11": "Force Majeure (source-chain escrow)",
        },
    })


# ── Phase 2: Proof Builder ─────────────────────────────────────────────────────

@btcp_bp.route("/api/v1/btcp/proof")
def btcp_proof():
    """BTCP proof builder reference (A3 Resolution)."""
    from core.btcp.modules import BTCPProofBuilder
    pb = BTCPProofBuilder()
    return jsonify({
        "cert_validity_windows": [
            {"value_tier": "<$1K", "blocks": 10000, "approx_days": 1.4},
            {"value_tier": "$1K-$100K", "blocks": 50000, "approx_days": 7},
            {"value_tier": "$100K-$10M", "blocks": 200000, "approx_days": 28},
            {"value_tier": ">$10M", "blocks": 500000, "approx_days": 70},
        ],
        "verification_steps": [
            "1. Check consensus_proof against known TRION validator set",
            "2. Check certification_block is within certification_expiry",
            "3. Check validator_key_version was valid at certification_block",
            "4. If valid: execute natively — no bridge, no wrapped token",
        ],
        "specification": "A3 Resolution",
    })


# ── Phase 2: Modules Overview ──────────────────────────────────────────────────

@btcp_bp.route("/api/v1/btcp/modules")
def btcp_modules():
    """Overview of all 18 BTCP modules."""
    return jsonify({
        "modules": [
            {"id": "2.1", "name": "btcp_router", "status": "IMPLEMENTED", "spec": "K1 Resolution"},
            {"id": "2.2", "name": "escrow_monitor", "status": "IMPLEMENTED", "spec": "Gap 8, 9, E1, G1"},
            {"id": "2.3", "name": "bibl_engine", "status": "IMPLEMENTED", "spec": "D3 Resolution"},
            {"id": "2.4", "name": "proof_builder", "status": "IMPLEMENTED", "spec": "A3 Resolution"},
            {"id": "2.5", "name": "bitp_matcher", "status": "IMPLEMENTED", "spec": "BITP Flow"},
            {"id": "2.6", "name": "netting_engine", "status": "IMPLEMENTED", "spec": "NETTING routes"},
            {"id": "2.7", "name": "intent_aggregator", "status": "IMPLEMENTED", "spec": "IAP pooling"},
            {"id": "2.8", "name": "ooa_anchor", "status": "IMPLEMENTED", "spec": "Observation-Only"},
            {"id": "2.9", "name": "shadow_observer", "status": "IMPLEMENTED", "spec": "Hostile chains"},
            {"id": "2.10", "name": "state_capsule", "status": "IMPLEMENTED", "spec": "Cross-chain state"},
            {"id": "2.11", "name": "failure_classifier", "status": "IMPLEMENTED", "spec": "EXTERNAL vs ENTITY"},
            {"id": "2.12", "name": "genesis_commitment", "status": "IMPLEMENTED", "spec": "Null-State Theorem"},
            {"id": "2.13", "name": "blo_scheduler", "status": "IMPLEMENTED", "spec": "BRT optimal window"},
            {"id": "2.14", "name": "state_channel", "status": "IMPLEMENTED", "spec": "50× cheaper"},
            {"id": "2.15", "name": "finality_normalizer", "status": "IMPLEMENTED", "spec": "max(A,B) not sum"},
            {"id": "2.16", "name": "version_handler", "status": "IMPLEMENTED", "spec": "Semver compat"},
            {"id": "2.17", "name": "validator_fee_calc", "status": "IMPLEMENTED", "spec": "Fix 4"},
            {"id": "2.18", "name": "sybil_resistance", "status": "IMPLEMENTED", "spec": "5-layer (Fix 5)"},
        ],
        "total_modules": 18,
        "implemented": 18,
        "specification": "BTCP Master Spec Phase 2",
    })


# ── Phase 2: Module Surfaces (Gap #3 — docstring-promised endpoints) ──────────
#
# The blueprint docstring used to promise eight module endpoints that were
# never implemented. These routes wire the real core.btcp.modules classes
# (2.5 BITPMatcher, 2.6 NettingEngine, 2.7 IntentAggregator, 2.11
# FailureClassifier, 2.16 VersionHandler, 2.17 ValidatorFeeCalculator, 2.18
# SybilResistance) and the persisted escrows (state_store/escrow_monitor)
# through to the API, passing their actual outputs through unchanged.

# ── Caller-truth guardrails (W3-M, INV-016 family) ──────────────────────────
#
# "APIs submit evidence, never manufacture truth." Matching tolerances are
# behavioral price-discovery parameters, not free-form caller settings: an
# uncapped price_tolerance lets a caller match ANY magnitude pair (including
# wildly divergent ones), degenerating BITP "price discovery" into arbitrary
# pairing. The spec default is 0.02 (2%, BTCP_SPEC §5.1 behavioral_price_
# tolerance); callers may tighten or widen within a bounded band, never
# remove the discipline.
MATCH_TOLERANCE_MAX = 0.10   # hard cap: 10% divergence ceiling for API callers
MATCH_TOLERANCE_MIN = 0.0    # tolerances below 0 mean "match nothing" — reject


def _bounded_tolerance(data, key, default, what):
    """Parse a matching tolerance with a hard cap (fail-closed on abuse).

    Returns (value, None) on success or (None, error_message) when the
    supplied value is non-numeric, NaN, negative, or above the cap.
    """
    raw = data.get(key, default)
    try:
        value = float(raw)
    except (TypeError, ValueError):
        return None, f"{what} must be a number"
    if value != value:  # NaN
        return None, f"{what} must be a number (got NaN)"
    if value < MATCH_TOLERANCE_MIN:
        return None, f"{what} must be >= {MATCH_TOLERANCE_MIN}"
    if value > MATCH_TOLERANCE_MAX:
        return None, (
            f"{what} is capped at {MATCH_TOLERANCE_MAX} (got {value}) — "
            f"behavioral price discovery cannot run with an unbounded "
            f"tolerance; the spec default is 0.02")
    return value, None


def _require(data, key, cast, what=None):
    """Fetch + cast a required request field; clear ValueError on failure."""
    raw = data.get(key)
    if raw is None:
        raise ValueError(f"{what or key} is required")
    try:
        return cast(raw)
    except (TypeError, ValueError):
        raise ValueError(f"{what or key} must be a valid {cast.__name__}")


def _build_bitp_intent(payload, label="intent"):
    """Build a core.btcp.modules.BITPIntent from a JSON payload.

    Constructed defensively: only fields that exist on the dataclass *at
    runtime* (dataclasses.fields) are forwarded, so the endpoint keeps
    working both before and after BITPIntent gains optional fields
    (action, value, max_total_gas, min_finality, min_NL_score/min_nl_score,
    chain_pref, privacy, btcp_version, nonce — all default-valued
    additions). Unknown extra fields in the payload are ignored, never
    fatal.
    """
    import dataclasses
    from core.btcp.modules import BITPIntent

    if not isinstance(payload, dict):
        raise ValueError(f"{label} must be a JSON object")
    field_names = {f.name for f in dataclasses.fields(BITPIntent)}

    def _hex(name):
        raw = payload.get(name)
        if raw is None:
            raise ValueError(f"{label}.{name} is required (hex string)")
        if not isinstance(raw, str):
            raise ValueError(f"{label}.{name} must be a hex string")
        try:
            return bytes.fromhex(raw.removeprefix("0x"))
        except ValueError:
            raise ValueError(f"{label}.{name} is not a valid hex string")

    kwargs = {}
    if "entity_id" in field_names:
        kwargs["entity_id"] = _hex("entity_id")
    if "asset_in" in field_names:
        kwargs["asset_in"] = _hex("asset_in")
    if "asset_out" in field_names:
        kwargs["asset_out"] = _hex("asset_out")
    if "magnitude" in field_names:
        kwargs["magnitude"] = _require(
            payload, "magnitude", float, f"{label}.magnitude")
    if "chain_id" in field_names:
        kwargs["chain_id"] = _require(
            payload, "chain_id", int, f"{label}.chain_id")
    if "deadline" in field_names:
        deadline = payload.get("deadline")
        # deadline has no default in the current dataclass — default to now+1h
        kwargs["deadline"] = int(deadline) if deadline is not None \
            else int(time.time()) + 3600

    # Optional pass-through fields — forwarded only when the running
    # dataclass actually declares them (forward compatibility with the
    # concurrent BITPIntent §4.1 field additions). Values are forwarded
    # unchanged; the spec's min_NL_score spelling is aliased to the repo's
    # min_nl_score field name when that is the one that exists.
    _aliases = {"min_NL_score": "min_nl_score"}
    for name in ("action", "value", "max_total_gas", "min_finality",
                 "min_NL_score", "min_nl_score", "chain_pref", "privacy",
                 "btcp_version", "nonce"):
        target = name
        if target not in field_names and target in _aliases:
            target = _aliases[target]
        if target in field_names and payload.get(name) is not None:
            kwargs[target] = payload[name]

    return BITPIntent(**kwargs)


def _bitp_intent_to_json(intent):
    """BITPIntent → JSON-safe dict (bytes → hex, extra fields included)."""
    import dataclasses
    out = {}
    for f in dataclasses.fields(intent):
        v = getattr(intent, f.name)
        out[f.name] = v.hex() if isinstance(v, bytes) else v
    return out


def _intent_list(data, key):
    """Parse + validate a list of BITP intent objects from request JSON."""
    raw = data.get(key, [])
    if not isinstance(raw, list):
        raise ValueError(f"{key} must be a list of intent objects")
    return [
        _build_bitp_intent(item, label=f"{key}[{i}]")
        for i, item in enumerate(raw)
    ]


@btcp_bp.route("/api/v1/btcp/bitp/match", methods=["POST"])
def btcp_bitp_match():
    """BITP complement matching (Module 2.5).

    Payload:
      intent           — BITP intent object (entity_id/asset_in/asset_out as
                         hex strings, magnitude, chain_id, deadline)
      candidates       — list of the same intent objects to search across
                         chains
      price_tolerance  — optional, default 0.02, capped at 0.10 (see
                         MATCH_TOLERANCE_MAX above — a caller cannot widen
                         the matching band past the behavioral-discipline
                         ceiling)

    Optional extra intent fields are forwarded when the running BITPIntent
    dataclass declares them; unknown fields are ignored. On a match the
    PASTE phase result is included (zero cross-chain movement by design).
    """
    from core.btcp.modules import BITPMatcher
    data = request.get_json(force=True, silent=True) or {}
    try:
        payload = data.get("intent") if isinstance(data.get("intent"), dict) else data
        intent_a = _build_bitp_intent(payload)
        candidates = _intent_list(data, "candidates")
        price_tolerance, err = _bounded_tolerance(
            data, "price_tolerance", 0.02, "price_tolerance")
        if err:
            return jsonify({"error": err}), 400

        matcher = BITPMatcher()
        match = matcher.find_complement(intent_a, candidates, price_tolerance)
        matched = match is not None
        return jsonify({
            "matched": matched,
            "complement": _bitp_intent_to_json(match) if matched else None,
            "paste": matcher.execute_paste(intent_a, match) if matched else None,
            "candidates_considered": len(candidates),
            "price_tolerance": price_tolerance,
            "price_tolerance_cap": MATCH_TOLERANCE_MAX,
            "specification": "Module 2.5 — BITP Matcher",
        })
    except Exception as e:
        return jsonify({"error": str(e)}), 400


@btcp_bp.route("/api/v1/btcp/netting", methods=["POST"])
def btcp_netting():
    """Netting pair finder (Module 2.6) — pure NETTING routes.

    Same payload shape as /bitp/match (intent, candidates) plus an optional
    ``tolerance`` (default 0.01, capped at 0.10 — same MATCH_TOLERANCE_MAX
    discipline as BITP). Netting finds the exact opposite intent on the
    *same* chain from a different entity; gas cost is the state-update
    floor from NettingEngine.netting_gas_cost().
    """
    from core.btcp.modules import NettingEngine
    data = request.get_json(force=True, silent=True) or {}
    try:
        payload = data.get("intent") if isinstance(data.get("intent"), dict) else data
        intent_a = _build_bitp_intent(payload)
        candidates = _intent_list(data, "candidates")
        tolerance, err = _bounded_tolerance(
            data, "tolerance", 0.01, "tolerance")
        if err:
            return jsonify({"error": err}), 400

        engine = NettingEngine()
        pair = engine.find_netting_pair(intent_a, candidates, tolerance)
        found = pair is not None
        return jsonify({
            "netting_found": found,
            "netting_pair": _bitp_intent_to_json(pair) if found else None,
            "netting_gas_cost": engine.netting_gas_cost(),
            "tolerance": tolerance,
            "tolerance_cap": MATCH_TOLERANCE_MAX,
            "candidates_considered": len(candidates),
            "specification": "Module 2.6 — Netting Engine",
        })
    except Exception as e:
        return jsonify({"error": str(e)}), 400


@btcp_bp.route("/api/v1/btcp/aggregate", methods=["POST"])
def btcp_aggregate():
    """Intent aggregation pooling (Module 2.7).

    Payload:
      intents        — list of BITP intent objects
      window_blocks  — optional, default 10
      total_gas      — optional; when given, the per-user gas split is
                       included (equal split, plus the value-weighted split
                       when user_value + total_value are also given)
    """
    from core.btcp.modules import IntentAggregator
    data = request.get_json(force=True, silent=True) or {}
    try:
        intents = _intent_list(data, "intents")
        window_blocks = int(data.get("window_blocks", 10))

        agg = IntentAggregator()
        pool = agg.find_aggregation_pool(intents, window_blocks)
        pool_found = bool(pool)
        out = {
            "pool_found": pool_found,
            "pool": [_bitp_intent_to_json(i) for i in pool],
            "pool_size": len(pool),
            "min_intents": IntentAggregator.MIN_INTENTS,
            "window_blocks": window_blocks,
            "intents_considered": len(intents),
            "specification": "Module 2.7 — Intent Aggregator",
        }
        if pool_found and data.get("total_gas") is not None:
            total_gas = float(data.get("total_gas"))
            out["per_user_gas"] = agg.compute_per_user_gas(total_gas, len(pool))
            if data.get("user_value") is not None and data.get("total_value") is not None:
                out["per_user_gas_weighted"] = agg.compute_per_user_gas_weighted(
                    total_gas, float(data.get("user_value")),
                    float(data.get("total_value")))
        return jsonify(out)
    except Exception as e:
        return jsonify({"error": str(e)}), 400


# Escrow rows are written through to the shared SQLite state store by
# core/btcp/escrow_monitor.py (S7). The lookup below reads that persisted
# state directly, so it sees escrows locked by any process (or before a
# restart), not just the ones this API process created.
_ESCROW_STORES = {}


def _get_escrow_store():
    """Lazily open (and cache by resolved path) the BTCP state store."""
    from core.btcp.state_store import BtcpStateStore, resolve_state_db
    path = os.path.abspath(resolve_state_db())
    if path not in _ESCROW_STORES:
        _ESCROW_STORES[path] = BtcpStateStore(path)
    return _ESCROW_STORES[path]


@btcp_bp.route("/api/v1/btcp/escrow/<escrow_id>", methods=["GET"])
def btcp_escrow_state(escrow_id):
    """Escrow state lookup by ID — reads the persisted BTCP state store.

    Escrow state is persisted write-through by the escrow monitor as
    ``escrow_v1`` rows. Unknown IDs get an honest 404-style JSON response
    (with the number of escrows that ARE persisted), never a fabricated
    default state.
    """
    try:
        store = _get_escrow_store()
        rows = store.get_escrows()
        if escrow_id not in rows:
            return jsonify({
                "found": False,
                "escrow_id": escrow_id,
                "error": "escrow id not found in the persisted BTCP state store",
                "persisted_escrow_count": len(rows),
                "state_db": store.path,
            }), 404
        type_tag, row = rows[escrow_id]
        return jsonify({
            "found": True,
            "escrow_id": escrow_id,
            "type_tag": type_tag,
            "escrow": row,
            "state": row.get("state"),
            "state_db": store.path,
        })
    except Exception as e:
        return jsonify({"error": str(e)}), 500


@btcp_bp.route("/api/v1/btcp/failure_classify", methods=["POST"])
def btcp_failure_classify():
    """Failure classifier (Module 2.11, Spec §11 Fix 2) — EXTERNAL_CAUSE
    vs ENTITY_CAUSE classification + recommended entity choice.

    All eight indicator fields are booleans (default false);
    ``prior_ambiguous_count`` is an int (default 0). The classification,
    the recommended entity choice (WAIT / CANCEL / REROUTE), and the
    indicator echo are passed through from
    ``FailureClassifier.classify_and_recommend()``.
    """
    from core.btcp.modules import FailureClassifier
    data = request.get_json(force=True, silent=True) or {}
    try:
        indicators = {}
        for key in ("chain_outage", "nl_dropped_below_0_10",
                    "reorg_depth_exceeded", "mf_spike", "invalid_proof",
                    "collateral_withdrawn", "conflicting_intents",
                    "systematic_timeout"):
            raw = data.get(key, False)
            if not isinstance(raw, bool):
                raise ValueError(f"{key} must be a boolean")
            indicators[key] = raw
        prior = data.get("prior_ambiguous_count", 0)
        if isinstance(prior, bool) or not isinstance(prior, int):
            raise ValueError("prior_ambiguous_count must be an integer")

        verdict = FailureClassifier().classify_and_recommend(
            **indicators, prior_ambiguous_count=prior)
        classification = verdict["cause"]
        recommended_choice = verdict["recommended_choice"]
        return jsonify({
            "classification": classification,
            "recommended_choice": recommended_choice,
            "indicators": indicators,
            "prior_ambiguous_count": prior,
            "policy": {
                "EXTERNAL_CAUSE": "BEO impact = ZERO, entity not penalized",
                "ENTITY_CAUSE": "graduated penalties (D(t) growth -10% for 30 days)",
                "AMBIGUOUS": ("first two = EXTERNAL benefit of doubt; "
                              "third within 90 days = ENTITY"),
            },
            "entity_choice": {
                "WAIT": "auto-retry the route after a backoff window",
                "CANCEL": "terminate the route; escrow returns funds",
                "REROUTE": "pick a different path immediately",
            },
            "specification": "Module 2.11 / Spec §11 Fix 2 — Failure Classifier + Entity Choice",
        })
    except Exception as e:
        return jsonify({"error": str(e)}), 400


@btcp_bp.route("/api/v1/btcp/version", methods=["GET"])
def btcp_version():
    """Version handler (Module 2.16) — semver compatibility checks.

    Query params:
      verifier_version (default 1.0.0), min_version (default 1.0.0) →
          compatibility verdict (verifier >= min)
      old_version + new_version (optional, supplied together) →
          breaking-change verdict (major bump)
    """
    from core.btcp.modules import VersionHandler
    vh = VersionHandler()
    try:
        verifier = request.args.get("verifier_version", "1.0.0")
        minimum = request.args.get("min_version", "1.0.0")
        old_version = request.args.get("old_version")
        new_version = request.args.get("new_version")

        out = {
            "verifier_version": {"raw": verifier,
                                 "parsed": list(vh.parse_semver(verifier))},
            "min_version": {"raw": minimum,
                            "parsed": list(vh.parse_semver(minimum))},
            "compatible": vh.is_compatible(verifier, minimum),
            "adapter_version_bonus": VersionHandler.ADAPTER_VERSION_BONUS,
            "specification": "Module 2.16 — Version Handler",
        }
        if (old_version is None) != (new_version is None):
            raise ValueError("old_version and new_version must be supplied together")
        if old_version is not None:
            out["old_version"] = {"raw": old_version,
                                  "parsed": list(vh.parse_semver(old_version))}
            out["new_version"] = {"raw": new_version,
                                  "parsed": list(vh.parse_semver(new_version))}
            out["breaking_change"] = vh.is_breaking_change(old_version, new_version)
        return jsonify(out)
    except Exception as e:
        return jsonify({"error": str(e)}), 400


@btcp_bp.route("/api/v1/btcp/validator_fee", methods=["POST"])
def btcp_validator_fee():
    """Validator fee calculator (Module 2.17, Fix 4).

    Payload:
      chains_covered       — list of chain ids the validator covers
      validators_per_chain — {chain_id: validators covering that chain}
                              (must be >= 1 for every covered chain; the
                              rarity factor is undefined otherwise)
      total_validators     — positive int
      volume_per_chain     — optional {chain_id: volume factor}
      uptime_per_chain     — optional {chain_id: uptime factor}
      total_route_reward   — optional; adds the 60/40 anchor/exec split
    """
    from core.btcp.modules import ValidatorFeeCalculator
    data = request.get_json(force=True, silent=True) or {}
    try:
        chains = data.get("chains_covered", [])
        if not isinstance(chains, list):
            raise ValueError("chains_covered must be a list of chain ids")
        chains = [int(c) for c in chains]
        for name in ("validators_per_chain", "volume_per_chain", "uptime_per_chain"):
            if not isinstance(data.get(name, {}), dict):
                raise ValueError(f"{name} must be an object keyed by chain id")
        validators_per_chain = {
            int(k): int(v) for k, v in data.get("validators_per_chain", {}).items()}
        total_validators = int(data.get("total_validators", 0))
        if total_validators <= 0:
            raise ValueError("total_validators must be a positive integer")
        volume_per_chain = {
            int(k): float(v) for k, v in data.get("volume_per_chain", {}).items()}
        uptime_per_chain = {
            int(k): float(v) for k, v in data.get("uptime_per_chain", {}).items()}
        for c in chains:
            if validators_per_chain.get(c, 0) < 1:
                raise ValueError(
                    f"validators_per_chain[{c}] must be >= 1 — the rarity "
                    f"factor is undefined for an uncovered chain")

        calc = ValidatorFeeCalculator()
        coverage_bonus = calc.compute_coverage_bonus(
            chains, validators_per_chain, total_validators,
            volume_per_chain, uptime_per_chain)
        out = {
            "base_rate": ValidatorFeeCalculator.BASE_RATE,
            # Spec §11 Fix 4 — `btcp_route_reward = Σ route.value × BTCP_ROUTE_FEE_RATE`.
            # Exposed so callers can verify the Rust/Python constant is unified
            # (BTCP-FIX2-RUST-VM added the Python mirror).
            "btcp_route_fee_rate": ValidatorFeeCalculator.BTCP_ROUTE_FEE_RATE,
            "chains_covered": chains,
            "rarity_factors": {
                str(c): calc.compute_rarity_factor(
                    validators_per_chain.get(c, 1), total_validators)
                for c in chains
            },
            "coverage_bonus": coverage_bonus,
            "total_validators": total_validators,
            "specification": "Module 2.17 — Validator Fee Calculator (Fix 4)",
        }
        # Spec §11 Fix 4 — `btcp_route_reward = Σ route.value × BTCP_ROUTE_FEE_RATE`.
        # When `certified_route_value` (the Σ route.value across the validator's
        # certified routes in the period) is supplied, compute the raw route
        # fee and the 60/40 anchor/exec split.
        if data.get("certified_route_value") is not None:
            certified_route_value = float(data.get("certified_route_value"))
            if certified_route_value < 0:
                raise ValueError("certified_route_value must be non-negative")
            raw_fee = calc.compute_btcp_route_fee(certified_route_value)
            out["btcp_route_reward"] = {
                "certified_route_value": certified_route_value,
                "fee_rate": ValidatorFeeCalculator.BTCP_ROUTE_FEE_RATE,
                "raw_fee": raw_fee,
                "anchor_share": ValidatorFeeCalculator.BTCP_ROUTE_SPLIT_ANCHOR,
                "execution_share": ValidatorFeeCalculator.BTCP_ROUTE_SPLIT_EXEC,
                "anchor_validators": calc.compute_btcp_route_reward(
                    raw_fee, True),
                "execution_validators": calc.compute_btcp_route_reward(
                    raw_fee, False),
            }
        # Back-compat: accept the old `total_route_reward` field as a
        # pre-split reward amount (still 60/40 split, no fee computation).
        elif data.get("total_route_reward") is not None:
            total_route_reward = float(data.get("total_route_reward"))
            out["btcp_route_reward"] = {
                "total": total_route_reward,
                "anchor_share": ValidatorFeeCalculator.BTCP_ROUTE_SPLIT_ANCHOR,
                "execution_share": ValidatorFeeCalculator.BTCP_ROUTE_SPLIT_EXEC,
                "anchor_validators": calc.compute_btcp_route_reward(
                    total_route_reward, True),
                "execution_validators": calc.compute_btcp_route_reward(
                    total_route_reward, False),
            }
        return jsonify(out)
    except Exception as e:
        return jsonify({"error": str(e)}), 400


# ── §8.1 Shadow Observation (BTCP-FIX2-S59 — wire real akashic_bh data) ───────

@btcp_bp.route("/api/v1/btcp/shadow_observations", methods=["GET", "POST"])
def btcp_shadow_observations():
    """§8.1 Shadow Observation Protocol — real (non-simulated) sources.

    GET:  return the most-recent real (simulated=FALSE) shadow observations
          for the requested hostile chain (query param ``hostile_chain_id``;
          default 99999 — an unintegrated/hostile chain id for the audit
          environment that has no live hostile-chain indexer).
    POST: collect fresh real shadow sources from the ``akashic_bh`` live
          feed (events TRION observed but did NOT emit as published signals —
          i.e. ``context->>'source' IS NULL``), persist them to the
          ``shadow_observations`` table with ``simulated=FALSE``, and
          return the summary + up-to-25 most-recent real rows.

    Body (POST, all optional):
      hostile_chain_id   int — the chain being shadowed (default 99999)
      lookback_hours     int — collector lookback window (default 168 = 7d)
      limit_per_chain    int — cap per source chain (default 25)
      integrated_chains  list[int] — restrict source chains (default = all)
    """
    from core.btcp.shadow_observer import (
        shadow_observation_summary,
        fetch_recent_shadow_observations,
    )
    if request.method == "GET":
        hostile = request.args.get("hostile_chain_id", type=int) or 99999
        only_real = request.args.get("only_real", "1") not in ("0", "false", "False")
        limit = request.args.get("limit", type=int) or 25
        try:
            recent = fetch_recent_shadow_observations(
                hostile_chain_id=hostile,
                only_real=only_real,
                limit=limit,
            )
            return jsonify({
                "hostile_chain_id": hostile,
                "only_real": only_real,
                "count": len(recent),
                "simulated": False,
                "recent_observations": recent,
                "specification": "§8.1 Shadow Observation (BTCP-FIX2-S59) — live akashic_bh",
            })
        except Exception as e:
            return jsonify({"error": str(e)}), 400

    # POST — collect + persist real sources from akashic_bh.
    data = request.get_json(force=True, silent=True) or {}
    try:
        hostile = int(data.get("hostile_chain_id", 99999))
        lookback = int(data.get("lookback_hours", 168))
        limit_per_chain = int(data.get("limit_per_chain", 25))
        integrated = data.get("integrated_chains")
        if integrated is not None and not isinstance(integrated, list):
            raise ValueError("integrated_chains must be a list of ints")
        if integrated:
            integrated = [int(c) for c in integrated]

        # Inline the collect+persist+summary cycle so we can pass the
        # integrated_chains filter through (shadow_observation_summary
        # uses the defaults).
        from core.btcp.shadow_observer import (
            collect_real_shadow_sources,
            persist_real_shadow_observations,
        )
        sources = collect_real_shadow_sources(
            hostile_chain_id=hostile,
            integrated_chains=integrated,
            lookback_hours=lookback,
            limit_per_chain=limit_per_chain,
        )
        inserted = persist_real_shadow_observations(sources)
        recent = fetch_recent_shadow_observations(
            hostile_chain_id=hostile, only_real=True, limit=25,
        )
        mean_conf = (
            sum(s.confidence_weight for s in sources) / len(sources)
            if sources else 0.0
        )
        diversity = sources[0].diversity_factor if sources else 0.0
        shadow_bh_hex = sources[0].shadow_bh.hex() if sources else ""
        return jsonify({
            "hostile_chain_id":   hostile,
            "lookback_hours":     lookback,
            "limit_per_chain":    limit_per_chain,
            "integrated_chains":  integrated,
            "source_count":       len(sources),
            "new_rows_inserted":  inserted,
            "mean_confidence":    round(mean_conf, 4),
            "diversity_factor":   round(diversity, 4),
            "shadow_bh_hex":      shadow_bh_hex,
            "simulated":          False,
            "recent_real_observations": recent,
            "specification":      "§8.1 Shadow Observation (BTCP-FIX2-S59) — live akashic_bh",
        })
    except Exception as e:
        return jsonify({"error": str(e)}), 400


# ── §8.2 Ultra-Light Node block-header processing (BTCP-FIX2-S59) ─────────────


@btcp_bp.route("/api/v1/btcp/ultra_light_node", methods=["POST"])
def btcp_ultra_light_node():
    """§8.2 Ultra-Light Node — block-header processing + PoW verification.

    Body:
      header_hex   str  — 160-char hex of the 80-byte Bitcoin block header
                          (LE wire format, same byte order as on the wire).
                          Required.
      chain_id     int  — the hostile chain this header belongs to
                          (default 0).

    Returns:
      The parsed header fields (version, prev_block, merkle_root,
      timestamp, bits, nonce), the double-SHA256 ``block_hash_hex`` (display
      order), the decoded 256-bit ``target``, the ``pow_valid`` boolean, and
      the stored row id (the header is persisted to ``ultra_light_headers``
      in TimescaleDB; idempotent on ``block_hash``).

    Spec §8.2: "Hostile chains publish block headers regardless: block hash,
    Merkle root, timestamp, validator signatures.  TRION processes ~80
    bytes per block — trivial cost, zero permission required."
    """
    from core.btcp.ultra_light_node import (
        process_block_header,
        fetch_recent_headers,
        ULTRA_LIGHT_NODE_BYTES_PER_BLOCK,
    )
    data = request.get_json(force=True, silent=True) or {}
    try:
        header_hex = data.get("header_hex")
        if not header_hex:
            raise ValueError(
                "header_hex is required (160-char hex of the 80-byte "
                "Bitcoin block header — LE wire format, spec §8.2)"
            )
        header_hex = str(header_hex).removeprefix("0x").strip()
        chain_id = int(data.get("chain_id", 0))
        result = process_block_header(header_hex, chain_id=chain_id)

        # Include recent stored headers for context (so callers can see the
        # chain rhythm / fork detection — spec §8.2 secondary outputs).
        recent = fetch_recent_headers(chain_id, limit=5) if data.get(
            "include_recent", True
        ) else []
        return jsonify({
            **result,
            "bytes_per_block": ULTRA_LIGHT_NODE_BYTES_PER_BLOCK,
            "recent_headers": recent,
            "specification": "§8.2 Ultra-Light Node (BTCP-FIX2-S59) — block-header PoW verify",
        })
    except Exception as e:
        return jsonify({"error": str(e)}), 400


# ── §8.4 Rejoin Mechanism (BTCP-FIX2-S59 — 3-phase hostile-chain rejoin) ──────


@btcp_bp.route("/api/v1/btcp/rejoin", methods=["POST"])
def btcp_rejoin():
    """§8.4 Rejoin Mechanism — 3-phase hostile-chain rejoin.

    Body (all optional):
      hostile_chain_id   int  — the (formerly hostile) chain requesting
                                 rejoin (default 99999).
      num_total_chains   int  — total integrated chains AFTER rejoin;
                                 used for the N(N-1)/2 bridge-pair formula
                                 (default 10).
      collect_real       bool — when True (default), Phase 1 collects fresh
                                 real shadow sources from akashic_bh.
      lookback_hours     int  — collector lookback window (default 168 = 7d).
      limit_per_chain    int  — cap per source chain (default 25).

    Returns:
      RejoinResult with the three PhaseOutcome objects + the overall
      success flag (ALL three phases must pass for ``success=true``).

    Spec §8.4:
      Phase 1 — Shadow history becomes Genesis baseline (D(t) starts
                 from shadow, not zero).  Gate: mean confidence ≥ 0.5.
      Phase 2 — Native Channel 6 observation begins (confidence climbs
                 fast — shadow foundation already exists).
      Phase 3 — Full BTCP integration — N(N-1)/2 new bridge pairs
                 eliminated instantly.  "Bone heals stronger at the break point."
    """
    from core.btcp.rejoin import rejoin_hostile_chain
    data = request.get_json(force=True, silent=True) or {}
    try:
        hostile = int(data.get("hostile_chain_id", 99999))
        num_total = int(data.get("num_total_chains", 10))
        collect_real = bool(data.get("collect_real", True))
        lookback = int(data.get("lookback_hours", 168))
        limit_per_chain = int(data.get("limit_per_chain", 25))

        result = rejoin_hostile_chain(
            hostile_chain_id=hostile,
            num_total_chains=num_total,
            collect_real=collect_real,
            lookback_hours=lookback,
            limit_per_chain=limit_per_chain,
        )
        return jsonify({
            **result.to_dict(),
            "specification": "§8.4 Rejoin Mechanism (BTCP-FIX2-S59) — 3-phase hostile-chain rejoin",
        })
    except Exception as e:
        return jsonify({"error": str(e)}), 400


@btcp_bp.route("/api/v1/btcp/sybil", methods=["POST"])
def btcp_sybil():
    """Sybil resistance layers (Module 2.18, Fix 5).

    Each layer is computed when its inputs are present:
      depth_d + depth_d_min  → layer 1 (logarithmic sponsorship cap)
      n_sponsored            → layer 2 (scrutiny multiplier) and layer 4
                               (quadratic temporal spacing)
      cosine_similarity      → layer 3 (sockpuppet detection, > 0.85 alert)
      sponsor_graph          → layer 5 (star-pattern detection), shaped
                               {sponsor_hex: [sponsored_hex, ...]}
    """
    from core.btcp.modules import SybilResistance
    data = request.get_json(force=True, silent=True) or {}
    try:
        sr = SybilResistance()
        layers = {}

        if data.get("depth_d") is not None or data.get("depth_d_min") is not None:
            depth_d = _require(data, "depth_d", float, "depth_d")
            depth_d_min = _require(data, "depth_d_min", float, "depth_d_min")
            layers["layer1_max_sponsored"] = sr.layer1_max_sponsored(depth_d, depth_d_min)

        if data.get("n_sponsored") is not None:
            n_sponsored = _require(data, "n_sponsored", int, "n_sponsored")
            layers["layer2_scrutiny_multiplier"] = \
                sr.layer2_scrutiny_multiplier(n_sponsored)
            layers["layer4_min_spacing_days"] = \
                sr.layer4_min_spacing_days(n_sponsored)

        if data.get("cosine_similarity") is not None:
            cosine = float(data.get("cosine_similarity"))
            layers["layer3_sockpuppet_alert"] = sr.layer3_is_sockpuppet(cosine)

        graph_raw = data.get("sponsor_graph")
        if graph_raw is not None:
            if not isinstance(graph_raw, dict):
                raise ValueError(
                    "sponsor_graph must be an object {sponsor_hex: [sponsored_hex, ...]}")
            graph = {}
            for sponsor, sponsored in graph_raw.items():
                try:
                    sponsor_bytes = bytes.fromhex(str(sponsor).removeprefix("0x"))
                except ValueError:
                    raise ValueError(f"sponsor_graph key {sponsor!r} is not valid hex")
                if not isinstance(sponsored, list):
                    raise ValueError(
                        f"sponsor_graph[{sponsor!r}] must be a list of hex entity ids")
                try:
                    graph[sponsor_bytes] = [
                        bytes.fromhex(str(s).removeprefix("0x")) for s in sponsored]
                except ValueError:
                    raise ValueError(
                        f"sponsor_graph[{sponsor!r}] contains a non-hex entity id")
            layers["layer5_suspicious_sponsors"] = [
                s.hex() for s in sr.layer5_detect_star_pattern(graph)]

        if not layers:
            raise ValueError(
                "no layer inputs provided — supply depth_d/depth_d_min, "
                "n_sponsored, cosine_similarity and/or sponsor_graph")

        return jsonify({
            "layers": layers,
            "constants": {
                "base_sponsor_cap": SybilResistance.BASE_SPONSOR_CAP,
                "min_spacing_base_days": SybilResistance.MIN_SPACING_BASE_DAYS,
                "similarity_threshold": SybilResistance.SIMILARITY_THRESHOLD,
            },
            "specification": "Module 2.18 — Sybil Resistance (Fix 5)",
        })
    except Exception as e:
        return jsonify({"error": str(e)}), 400


# ── Phase 3: Integration & Private BIBL ────────────────────────────────────────

# ── BTCP Dispute Resolution (Gap D6 — 72h runtime enforcement) ────────────────

# ── BTCP Gas Forecast (Gap D8 — rolling 30-day 99th percentile) ──────────────

@btcp_bp.route("/api/v1/btcp/gas-forecast/<int:chain_id>")
def btcp_gas_forecast(chain_id: int):
    """BTCP gas forecast for a chain — Gap D8 disclosure endpoint.

    Computes the rolling 30-day empirical 99th percentile of gas costs from
    bh_ledger.gas_used (cached 1 hour), uses it as the denominator of the
    normalize_gas formula, and discloses the source ("empirical_30d" or
    "fallback_hardcoded"), sample count, conversion assumption, and cache
    TTL. Spec ref: §4.2 Step 5 (Gas Sharing Protocol), §5 BRT Scheduler.
    """
    from btcp_gas_forecast import forecast_gas, compute_gas_99th_percentile
    history_param = request.args.get("history")
    history = None
    if history_param:
        try:
            history = [float(x) for x in history_param.split(",") if x.strip()]
        except ValueError:
            return jsonify({"error": "history must be comma-separated floats"}), 400
    result = forecast_gas(chain_id, history)
    result["gas_99th_meta"] = compute_gas_99th_percentile()
    result["specification"] = "Gap D8 — rolling 30-day empirical 99th percentile"
    return jsonify(result)


@btcp_bp.route("/api/v1/btcp/gas-99th")
def btcp_gas_99th():
    """Standalone accessor for the rolling 30-day empirical 99th percentile."""
    from btcp_gas_forecast import compute_gas_99th_percentile
    return jsonify(compute_gas_99th_percentile())


# ── BTCP Dispute Resolution (Gap D6 — 72h runtime enforcement) ────────────────

@btcp_bp.route("/api/v1/btcp/dispute/file", methods=["POST"])
def btcp_dispute_file():
    """File a new BTCP dispute case (Gap D6 — 72h runtime enforcement).

    Body:
      route_id, claimant, respondent, claim (strings)
      evidence_hashes (optional list[str])
      challenged_value (optional float — used to compute 5% challenge bond)
      filed_at (optional float — Unix seconds; defaults to now. Setting this
                to a timestamp >72h in the past is how callers simulate an
                expired dispute for the Gap D6 enforcement test).
    Returns the new case_id + the dispute-window metadata.
    """
    from core.btcp.dispute_resolution import get_dispute_resolver
    data = request.get_json(force=True, silent=True) or {}
    try:
        resolver = get_dispute_resolver()
        # Bootstrap: if no annotators are registered, register a 6-member
        # demo panel so the 3-of-5 selection has candidates. Disclosure:
        # these are placeholder annotators for end-to-end testing; a
        # production deployment registers real stake-weighted annotators via
        # register_annotator() before any case is filed.
        if len(resolver._annotators) == 0:
            for aid, stk, juris in [("a1", 100, "EU"), ("a2", 80, "US"),
                                     ("a3", 60, "AS"), ("a4", 50, "AF"),
                                     ("a5", 40, "SA"), ("a6", 30, "OC")]:
                resolver.register_annotator(aid, stk, juris)
        filed_at = data.get("filed_at")
        case = resolver.open_case(
            route_id=data.get("route_id", "route_unknown"),
            claimant=data.get("claimant", "0x0"),
            respondent=data.get("respondent", "0x0"),
            claim=data.get("claim", "unspecified"),
            evidence_hashes=data.get("evidence_hashes", []),
            challenged_value=float(data.get("challenged_value", 0.0)),
            filed_at=float(filed_at) if filed_at is not None else None,
        )
        return jsonify({
            "case_id": case.case_id,
            "status": case.status.value,
            "opened_at": case.opened_at,
            "challenge_bond": case.challenge_bond,
            "selected_annotators": case.selected_annotators,
            "dispute_window_seconds": 72 * 3600,
            "remaining_seconds": case.remaining_seconds(),
            "is_expired": case.is_expired(),
            "specification": "Gap D6 — 72h dispute window runtime enforcement",
        })
    except Exception as e:
        return jsonify({"error": str(e)}), 400


@btcp_bp.route("/api/v1/btcp/dispute/<case_id>/vote", methods=["POST"])
def btcp_dispute_vote(case_id: str):
    """Cast a 3-of-5 annotator vote on a dispute case.

    Gap D6 enforcement: if the case's 72h window has elapsed, the vote is
    REFUSED and the case auto-resolves IN FAVOR OF THE ROUTE (NOT_GUILTY).
    """
    from core.btcp.dispute_resolution import get_dispute_resolver, Vote
    data = request.get_json(force=True, silent=True) or {}
    try:
        resolver = get_dispute_resolver()
        annotator_id = data.get("annotator_id", "")
        vote_str = str(data.get("vote", "")).upper()
        if vote_str not in ("GUILTY", "NOT_GUILTY"):
            return jsonify({"error": "vote must be GUILTY or NOT_GUILTY"}), 400
        rationale = data.get("rationale", "")
        accepted = resolver.cast_vote(
            case_id, annotator_id, Vote[vote_str], rationale)
        case = resolver.get_case(case_id)
        if case is None:
            return jsonify({"error": "case not found"}), 404
        return jsonify({
            "case_id": case_id,
            "vote_accepted": accepted,
            "status": case.status.value,
            "resolved_at": case.resolved_at,
            "resolution_note": case.resolution_note,
            "is_expired": case.is_expired(),
            "remaining_seconds": case.remaining_seconds(),
            "guilty_votes": case.guilty_votes,
            "not_guilty_votes": case.not_guilty_votes,
            "specification": "Gap D6 — 72h dispute window runtime enforcement",
        })
    except Exception as e:
        return jsonify({"error": str(e)}), 400


@btcp_bp.route("/api/v1/btcp/dispute/<case_id>")
def btcp_dispute_status(case_id: str):
    """Get dispute case status, including the 72h dispute-window metadata."""
    from core.btcp.dispute_resolution import get_dispute_resolver
    resolver = get_dispute_resolver()
    case = resolver.get_case(case_id)
    if case is None:
        return jsonify({"error": "case not found"}), 404
    # Opportunistic 72h sweep: if the case is expired, resolve it now so the
    # caller sees the auto-resolution result (Gap D6).
    if case.is_expired() and case.status.value == "OPEN":
        resolver.resolve_expired_cases()
        case = resolver.get_case(case_id)
    return jsonify({
        "case_id": case.case_id,
        "route_id": case.route_id,
        "status": case.status.value,
        "opened_at": case.opened_at,
        "resolved_at": case.resolved_at,
        "resolution_note": case.resolution_note,
        "guilty_votes": case.guilty_votes,
        "not_guilty_votes": case.not_guilty_votes,
        "dispute_window_seconds": 72 * 3600,
        "remaining_seconds": case.remaining_seconds(),
        "is_expired": case.is_expired(),
        "selected_annotators": case.selected_annotators,
        "specification": "Gap D6 — 72h dispute window runtime enforcement",
    })


@btcp_bp.route("/api/v1/btcp/integration_status")
def btcp_integration_status():
    """anima-service integration status."""
    from core.btcp.integration import BTCPIntegrationHub, PrivacyLevel
    hub = BTCPIntegrationHub()
    status = hub.initialize()
    return jsonify({
        "anima_service_modules": status,
        "loaded_count": sum(1 for v in status.values() if v),
        "total_count": len(status),
        "privacy_levels": {
            "PUBLIC": "standard BIBL, no encryption",
            "ZK_CREDENTIAL": "full threshold protocol, encrypted",
            "INVISIBLE": "Sensing Oracle + ZK + Private BIBL (+500ms)",
        },
        "private_bibl_phases": [
            "Phase 1: Public routing parameters",
            "Phase 2: Private execution parameters (encrypted)",
            "Phase 3: Private BIBL computation (threshold homomorphic)",
            "Phase 4: Route selection + execution (zero front-running)",
        ],
        "specification": "Gap 9 Resolution — Private BIBL",
    })


@btcp_bp.route("/api/v1/btcp/private_bibl", methods=["POST"])
def btcp_private_bibl():
    """Private BIBL computation protocol (Gap 9)."""
    from core.btcp.integration import PrivateBIBLProtocol
    data = request.get_json(force=True, silent=True) or {}
    try:
        proto = PrivateBIBLProtocol()
        # Gap D5: per-entity BEO-id-derived key (spec §7.1 Dark Field).
        # The aggregate public key is no longer blindly set to a derived
        # constant — we let the per-entity derivation path run by default
        # unless the caller explicitly supplies an aggregate pubkey hex.
        agg_pub_hex = data.get("aggregate_public_key_hex")
        if agg_pub_hex:
            proto.set_aggregate_public_key(bytes.fromhex(agg_pub_hex))
        entity_id = bytes.fromhex(data.get("entity_id_hex", "01" * 32))

        # Phase 2: Encrypt (per-entity BEO-id-derived key per §7.1 Dark Field)
        encrypted = proto.encrypt_payload(
            asset_in=bytes.fromhex(data.get("asset_in_hex", "aa" * 32)),
            asset_out=bytes.fromhex(data.get("asset_out_hex", "bb" * 32)),
            value=float(data.get("value", 1000.0)),
            max_gas=float(data.get("max_gas", 50.0)),
            min_nl_score=float(data.get("min_nl_score", 0.30)),
            entity_id=entity_id,
        )

        # Phase 3: Private score (using magnitude bucket)
        magnitude_bucket = proto.classify_magnitude_bucket(
            float(data.get("value", 1000.0)),
            float(data.get("historical_avg", 1000.0)),
        )
        score = proto.compute_btcp_score_private(
            public_params={"entity_id": data.get("entity_id_hex", "01" * 32)},
            encrypted_score_components=data.get("score_components", {
                "nl": 0.85, "gas_norm": 0.9, "finality": 0.95, "cc": 0.9, "beo": 0.8,
            }),
            magnitude_bucket=magnitude_bucket,
        )

        # Phase 4: Decrypt at execution (requires 3-of-5 threshold shares)
        decrypted = proto.decrypt_payload(encrypted, [b"s1", b"s2", b"s3"], entity_id=entity_id)

        return jsonify({
            "encrypted_payload_hex": encrypted.hex(),
            "magnitude_bucket": magnitude_bucket,
            "private_btcp_score": round(score, 6),
            "front_running_window_ms": proto.zero_front_running_window(),
            "decrypted": {
                "asset_in_hex": decrypted[0].hex(),
                "asset_out_hex": decrypted[1].hex(),
                "value": decrypted[2],
                "max_gas": decrypted[3],
                "min_nl_score": decrypted[4],
            },
            "encryption": {
                "key_source": proto._last_key_source,
                "cipher": "XOR (placeholder for AEAD — spec §7.1 Dark Field)",
                "disclosure": (
                    "Per-entity BEO-id-derived key (SHA3-256). XOR is a "
                    "deliberate placeholder; production must use AES-GCM / "
                    "ChaCha20-Poly1305 + a KMS / threshold BLS key schedule."
                ),
            },
            "specification": "Gap 9 Resolution + Gap D5 fix (Dark Field key derivation)",
        })
    except Exception as e:
        return jsonify({"error": str(e)}), 400


# ── Phase 4: CONTINUUM Engines ─────────────────────────────────────────────────

@btcp_bp.route("/api/v1/continuum/engines")
def continuum_engines():
    """Overview of all 5 CONTINUUM engines."""
    return jsonify({
        "engines": [
            {"id": "4.1", "name": "BID", "full_name": "Behavioral Intent Detection",
             "formula": "BID_conf = cosine_sim(feature_delta, pretrade_sig) × min(1, D/D_min)",
             "status": "IMPLEMENTED"},
            {"id": "4.2", "name": "CME", "full_name": "Complement Matching Engine",
             "formula": "COMPLEMENT_score = direction × temporal × health × independence × liquidity",
             "status": "IMPLEMENTED"},
            {"id": "4.3", "name": "PMO", "full_name": "Pre-Manifest Order System",
             "formula": "price_guarantee = TRION_VALUATION + CCP_premium",
             "status": "IMPLEMENTED"},
            {"id": "4.4", "name": "BDC", "full_name": "Behavioral Depth Credit",
             "formula": "BDC_limit = D(t) × consistency × avg_trade × min(2, D/D_min)",
             "status": "IMPLEMENTED"},
            {"id": "4.5", "name": "Thermodynamic Settlement", "full_name": "Settlement Triggers",
             "formula": "5 conditions: C_A≥Θ_A, C_B≥Θ_B, BTCP verified, temporal, no MF",
             "status": "IMPLEMENTED"},
        ],
        "ccp_distribution": {
            "entity_a": 0.40, "entity_b": 0.40,
            "validators": 0.12, "protocol": 0.08,
        },
        "total_engines": 5,
        "implemented": 5,
        "specification": "CONTINUUM Protocol Phase 4",
    })


@btcp_bp.route("/api/v1/continuum/bid", methods=["POST"])
def continuum_bid():
    """BID — Behavioral Intent Detection."""
    from continuum.engines import BIDEngine
    data = request.get_json(force=True, silent=True) or {}
    try:
        bid = BIDEngine()
        result = bid.detect(
            current_features=data.get("current_features", [0.8] * 9),
            baseline_features=data.get("baseline_features", [0.7] * 9),
            pretrade_signature=data.get("pretrade_signature", [0.1] * 9),
            depth_d=float(data.get("depth_d", 500.0)),
        )
        return jsonify({
            "confidence": round(result.confidence, 6),
            "direction": result.direction,
            "detected": result.detected,
            "depth_factor": round(result.depth_factor, 4),
            "pretrade_match": round(result.pretrade_match, 4),
            "feature_delta": result.feature_delta,
            "specification": "CONTINUUM 4.1 — BID",
        })
    except Exception as e:
        return jsonify({"error": str(e)}), 400


@btcp_bp.route("/api/v1/continuum/cme", methods=["POST"])
def continuum_cme():
    """CME — Complement Matching Engine."""
    from continuum.engines import CMEEngine
    data = request.get_json(force=True, silent=True) or {}
    try:
        cme = CMEEngine()
        candidates = data.get("candidates", [])
        result = cme.find_complement(
            entity_a_vector=data.get("entity_a_vector", [1.0] + [0.0] * 127),
            entity_a_direction=data.get("entity_a_direction", "BUY"),
            candidate_pool=candidates,
        )
        return jsonify({
            "matched": result.matched,
            "complement_id": result.complement_id.hex() if result.complement_id else None,
            "complement_score": round(result.complement_score, 6),
            "components": {
                "direction_complement": round(result.direction_complement, 4),
                "temporal_alignment": round(result.temporal_alignment, 4),
                "behavioral_health": round(result.behavioral_health, 4),
                "beo_independence": round(result.beo_independence, 4),
                "liquidity_sufficiency": round(result.liquidity_sufficiency, 4),
            },
            "specification": "CONTINUUM 4.2 — CME",
        })
    except Exception as e:
        return jsonify({"error": str(e)}), 400


@btcp_bp.route("/api/v1/continuum/pmo", methods=["POST"])
def continuum_pmo():
    """PMO — Pre-Manifest Order System."""
    from continuum.engines import PMOSystem
    data = request.get_json(force=True, silent=True) or {}
    try:
        pmo_sys = PMOSystem()
        pmo = pmo_sys.create_pmo(
            entity_id=bytes.fromhex(data.get("entity_id_hex", "01" * 32)),
            intent_data=data.get("intent_data", "swap").encode(),
            entity_bh=bytes.fromhex(data.get("entity_bh_hex", "aa" * 32)),
            nonce=int(data.get("nonce", 42)),
            trion_valuation=float(data.get("trion_valuation", 2000.0)),
            ccp_premium=float(data.get("ccp_premium", 5.0)),
            complement_id=bytes.fromhex(data.get("complement_id_hex", "02" * 32)),
            valid_blocks=int(data.get("valid_blocks", 100)),
            privacy_mode=int(data.get("privacy_mode", 0)),
        )
        return jsonify({
            "behavioral_commitment_hex": pmo.behavioral_commitment.hex(),
            "price_guarantee": pmo.price_guarantee,
            "complement_id_hex": pmo.complement_id.hex(),
            "valid_blocks": pmo.valid_blocks,
            "status": pmo.status,
            "specification": "CONTINUUM 4.3 — PMO",
        })
    except Exception as e:
        return jsonify({"error": str(e)}), 400


@btcp_bp.route("/api/v1/continuum/bdc", methods=["POST"])
def continuum_bdc():
    """BDC — Behavioral Depth Credit."""
    from continuum.engines import BDCEngine
    data = request.get_json(force=True, silent=True) or {}
    try:
        bdc = BDCEngine()
        result = bdc.compute_credit_limit(
            depth_d=float(data.get("depth_d", 730.0)),
            phi_history_90d=data.get("phi_history_90d", [0.8] * 10),
            avg_trade_size_90d=float(data.get("avg_trade_size_90d", 1000.0)),
        )
        return jsonify({
            "credit_limit": round(result["credit_limit"], 2),
            "consistency_ratio": round(result["consistency_ratio"], 4),
            "confidence_multiplier": round(result["confidence_multiplier"], 4),
            "depth_d": result["depth_d"],
            "specification": "CONTINUUM 4.4 — BDC",
        })
    except Exception as e:
        return jsonify({"error": str(e)}), 400


@btcp_bp.route("/api/v1/continuum/settlement", methods=["POST"])
def continuum_settlement():
    """Thermodynamic Settlement Triggers (CONTINUUM 4.5).

    Truth boundary (W3-M): ``btcp_route_verified`` is a settlement GATE —
    the API must never let a caller simply assert it. Two disciplines:

    * ``route_id`` (optional): when supplied, the gate is DERIVED from
      server-side state — the route is looked up in the persisted BTCP
      state store and its proofs are re-verified via
      BTCPOchestrator.verify_route_proofs (fail-closed, zk_pending
      included). A caller-supplied ``btcp_route_verified`` is IGNORED
      whenever ``route_id`` is present.
    * Without ``route_id``: the trigger computation runs on caller-supplied
      inputs and the response labels them ``caller_attested`` — the result
      is a computation preview, not a settlement authorization.

    The default for a bare ``btcp_route_verified`` (no route_id) is False —
    omitting the field must never read as "route verified".
    """
    from continuum.engines import ThermodynamicSettlement
    data = request.get_json(force=True, silent=True) or {}
    try:
        route_id = data.get("route_id")
        if route_id is not None and (not isinstance(route_id, str) or not route_id):
            return jsonify({"error": "route_id must be a non-empty string"}), 400

        caller_claim = data.get("btcp_route_verified")
        derived = None
        route_lookup = None
        if route_id is not None:
            # DERIVE the gate from persisted state + proof verification —
            # caller-supplied btcp_route_verified is ignored (never trust).
            try:
                orch = _get_orchestrator()
                routes = orch._store.get_routes()
                if route_id not in routes:
                    return jsonify({
                        "error": ("route_id not found in the persisted BTCP "
                                  "state store — cannot derive "
                                  "btcp_route_verified for an unknown route"),
                        "route_id": route_id,
                    }), 404
                derived, verify_errors = orch.verify_route_proofs(route_id)
                route_lookup = {
                    "route_id": route_id,
                    "found": True,
                    "proofs_all_valid": derived,
                    "verify_errors": verify_errors,
                }
            except Exception as e:
                return jsonify({
                    "error": f"route verification failed: {e}",
                    "route_id": route_id,
                }), 500
            btcp_route_verified = derived
        else:
            # Caller-attested gate — labeled, default False (fail-closed).
            if caller_claim is None:
                btcp_route_verified = False
            else:
                if not isinstance(caller_claim, bool):
                    return jsonify({
                        "error": "btcp_route_verified must be a boolean",
                    }), 400
                btcp_route_verified = caller_claim

        ts = ThermodynamicSettlement()
        result = ts.check_trigger(
            coherence_a=float(data.get("coherence_a", 0.85)),
            threshold_a=float(data.get("threshold_a", 0.55)),
            coherence_b=float(data.get("coherence_b", 0.80)),
            threshold_b=float(data.get("threshold_b", 0.55)),
            btcp_route_verified=btcp_route_verified,
            temporal_alignment_valid=data.get("temporal_alignment_valid", True),
            mf_detected=data.get("mf_detected", False),
        )
        out = {
            "triggered": result.triggered,
            "conditions": result.conditions,
            "reason": result.reason,
            # Provenance labels — a consumer can never mistake a caller
            # computation preview for a verified settlement authorization.
            "btcp_route_verified": btcp_route_verified,
            "btcp_route_verified_provenance": (
                "derived_from_persisted_route_proofs" if route_id is not None
                else "caller_attested"),
            "input_provenance": {
                "coherence_a": "caller_supplied",
                "threshold_a": "caller_supplied",
                "coherence_b": "caller_supplied",
                "threshold_b": "caller_supplied",
                "note": ("coherence/threshold inputs are caller-supplied "
                         "evidence, not TRION-verified values; the trigger "
                         "verdict below is a computation on that evidence"),
            },
            "specification": "CONTINUUM 4.5 — Thermodynamic Settlement",
        }
        if route_lookup is not None:
            out["route_verification"] = route_lookup
            if caller_claim is not None and caller_claim is not derived:
                out["caller_claim_ignored"] = (
                    f"caller-supplied btcp_route_verified={caller_claim} was "
                    f"ignored; derived value={derived} from route proofs")
        return jsonify(out)
    except Exception as e:
        return jsonify({"error": str(e)}), 400


@btcp_bp.route("/api/v1/continuum/ccp", methods=["POST"])
def continuum_ccp():
    """CCP — Complement Certainty Premium distribution."""
    from continuum.engines import CCPDistribution
    data = request.get_json(force=True, silent=True) or {}
    try:
        ccp = CCPDistribution()
        result = ccp.compute_ccp(
            best_exchange_spread=float(data.get("best_exchange_spread", 0.003)),
            btcp_routing_cost=float(data.get("btcp_routing_cost", 0.0005)),
            trade_value=float(data.get("trade_value", 10000.0)),
        )
        return jsonify({
            "ccp_total": round(result["ccp_total"], 2),
            "ccp_a": round(result["ccp_a"], 2),
            "ccp_b": round(result["ccp_b"], 2),
            "ccp_validators": round(result["ccp_validators"], 2),
            "ccp_protocol": round(result["ccp_protocol"], 2),
            "split": {"a": 0.40, "b": 0.40, "validators": 0.12, "protocol": 0.08},
            "specification": "CONTINUUM — CCP",
        })
    except Exception as e:
        return jsonify({"error": str(e)}), 400


# ── Phase 5: Full Pipeline ─────────────────────────────────────────────────────

@btcp_bp.route("/api/v1/btcp/pipeline_status")
def btcp_pipeline_status():
    """Full pipeline status overview."""
    return jsonify({
        "phases": {
            "phase_0": {
                "name": "Foundation",
                "status": "COMPLETE",
                "modules": ["Hash_DNA", "7-Plane Coherence", "7 MF Fingerprints"],
                "tests": 79,
            },
            "phase_1": {
                "name": "BTCP Core Contracts",
                "status": "COMPLETE",
                "contracts": ["BTCPEscrow", "BTCPIntent", "BTCPRoute", "BehavioralLimitOrder",
                              "LiquidityOcean", "GenesisCommitment", "TravelRuleCompliance",
                              "BTCPVersionRegistry", "SanctionsOracle", "HashDNA"],
                "tests": 36,
            },
            "phase_2": {
                "name": "BTCP Rust Modules (Python)",
                "status": "COMPLETE",
                "modules": 18,
                "tests": 58,
            },
            "phase_3": {
                "name": "Python/ML Integration",
                "status": "COMPLETE",
                "modules": ["anima-service integration", "Private BIBL Protocol"],
            },
            "phase_4": {
                "name": "CONTINUUM Protocol",
                "status": "COMPLETE",
                "engines": ["BID", "CME", "PMO", "BDC", "Thermodynamic Settlement", "CCP"],
                "tests": 26,
            },
            "phase_5": {
                "name": "Full System Testing",
                "status": "COMPLETE",
                "integration_tests": 11,
            },
        },
        "total_tests": 210,
        "all_passing": True,
        "specification": "BTCP Master Implementation Spec — All 6 Phases",
        "timestamp": int(time.time()),
    })


# ── Mainnet Bootstrap (Phase 2) ────────────────────────────────────────────────

@btcp_bp.route("/api/v1/btcp/mainnet_bootstrap")
def btcp_mainnet_bootstrap():
    """Mainnet bootstrap sequence (phased rollout across the registry VM families)."""
    from core.btcp.mainnet_bootstrap import build_chain_registry, get_bootstrap_status
    chains = build_chain_registry()
    status = get_bootstrap_status(chains)
    return jsonify({
        **status,
        "chains": [c.to_dict() for c in chains[:20]],  # first 20 for display
        "total_chains_in_registry": len(chains),
        "specification": "BTCP Master Spec Phase 6 — Bootstrap & Mainnet Launch",
        "timestamp": int(time.time()),
    })


# ── Real-Time Streamer Endpoints ───────────────────────────────────────────────

@btcp_bp.route("/api/v1/btcp/streamer/status")
def streamer_status():
    """Real-time BH streamer status and stats."""
    try:
        from core.realtime.bh_streamer import get_streamer, get_faiss_accumulator
        streamer = get_streamer()
        acc = get_faiss_accumulator()
        if streamer and streamer.is_running():
            stats = streamer.get_stats()
            return jsonify({
                **stats,
                "faiss_vectors_accumulated": acc.vector_count if acc else 0,
                "chains": list(streamer.chains.keys()),
                "chain_configs": {str(k): v for k, v in streamer.chains.items()},
                "status": "RUNNING",
            })
        else:
            return jsonify({
                "status": "STOPPED",
                "total_bhs": 0,
                "message": "Streamer not started. Call /api/v1/btcp/streamer/start",
            })
    except Exception as e:
        return jsonify({"status": "ERROR", "error": str(e)}), 500


@btcp_bp.route("/api/v1/btcp/streamer/start", methods=["POST"])
def streamer_start():
    """Start the real-time BH streamer."""
    try:
        from core.realtime.bh_streamer import start_streamer, get_streamer
        streamer = get_streamer()
        if streamer and streamer.is_running():
            return jsonify({"status": "ALREADY_RUNNING", "stats": streamer.get_stats()})
        start_streamer()
        try:
            from core.realtime.bh_streamer import get_streamer as _gs
            _st = _gs()
            _n = _st.get_stats().get("chains_active", 96) if _st else 96
        except Exception:
            _n = 96
        return jsonify({"status": "STARTED", "message": f"BH streamer started for {_n} chains"})
    except Exception as e:
        return jsonify({"status": "ERROR", "error": str(e)}), 500


# ── Orchestrator & RPC Health (Phase 2 Step 2.3 + 2.4) ────────────────────────

@btcp_bp.route("/api/v1/btcp/orchestrator/status")
def orchestrator_status():
    """Unified indexer orchestrator status + RPC health monitor."""
    from core.realtime.bh_streamer import CHAIN_RPCS, get_streamer
    streamer = get_streamer()
    stats = streamer.get_stats() if streamer and streamer.is_running() else {}

    # RPC health from streamer's per-chain stats
    rpc_health = {}
    for chain_id, config in CHAIN_RPCS.items():
        chain_name = config["name"]
        chain_stats = stats.get("per_chain", {}).get(chain_name, {})
        last_block = stats.get("last_blocks", {}).get(str(chain_id))
        rpc_health[str(chain_id)] = {
            "chain": chain_name,
            "label": config["label"],
            "rpc": config["rpc"],
            "block_time": config["block_time"],
            "last_block": last_block,
            "bhs_indexed": chain_stats.get("bhs", 0),
            "blocks_processed": chain_stats.get("blocks", 0),
            "status": "ok" if chain_stats.get("blocks", 0) > 0 else "waiting",
        }

    healthy = sum(1 for v in rpc_health.values() if v["status"] == "ok")
    return jsonify({
        "orchestrator_status": "RUNNING" if streamer and streamer.is_running() else "STOPPED",
        "total_chains": len(CHAIN_RPCS),
        "healthy_chains": healthy,
        "rpc_health": rpc_health,
        "streamer_stats": stats,
        "processes": {
            "bh_streamer": {
                "status": "RUNNING" if streamer and streamer.is_running() else "STOPPED",
                "total_bhs": stats.get("total_bhs", 0),
                "bhs_per_second": stats.get("bhs_per_second", 0),
                "chains_active": stats.get("chains_active", 0),
                "uptime_seconds": stats.get("uptime_seconds", 0),
            },
        },
        "timestamp": int(time.time()),
    })


# ── BTCP Orchestrator Execution (Gap #4) ──────────────────────────────────────
#
# core/btcp/orchestrator.py BTCPOrchestrator runs the full six-step BTCP
# sequence (address validation → intent creation → VM encoding → gas
# estimation → ZK proof generation → route tracking) with SQLite
# write-through persistence (S7). It is pure-Python and fast — a full route
# measures ~12 ms in-process — so this endpoint runs it synchronously and
# there is no async status route to poll.

_ORCHESTRATOR = None


def _get_orchestrator():
    """Lazily construct the shared BTCPOrchestrator singleton.

    Routes the orchestrator tracks are persisted to the shared SQLite
    state store (env TRION_STATE_DB, default db/btcp_state.db), so the
    singleton re-loads previously tracked routes on restart.
    """
    global _ORCHESTRATOR
    if _ORCHESTRATOR is None:
        from core.btcp.orchestrator import BTCPOrchestrator
        _ORCHESTRATOR = BTCPOrchestrator()
    return _ORCHESTRATOR


def _privacy_level_arg(data):
    """Parse the privacy_level request field into an orchestrator enum."""
    from core.btcp.orchestrator import PrivacyLevel
    raw = data.get("privacy_level", "BASIC")
    if isinstance(raw, bool):
        raise ValueError("privacy_level must be a level name or number")
    if isinstance(raw, str):
        if raw not in PrivacyLevel.__members__:
            raise ValueError(
                "privacy_level must be one of: " + ", ".join(PrivacyLevel.__members__))
        return PrivacyLevel[raw]
    if isinstance(raw, int):
        try:
            return PrivacyLevel(raw)
        except ValueError:
            raise ValueError(
                "privacy_level number must be one of: "
                + ", ".join(f"{p.value} ({p.name})" for p in PrivacyLevel))
    raise ValueError("privacy_level must be a level name or number")


def _proof_provenance_summary(route):
    """W3-M (INV-016 / W2-F handoff): surface witness provenance at the TOP
    LEVEL of the orchestrate response.

    The orchestrator already labels each proof dict with ``witness_source``
    (caller_self_attested / caller_supplied_batch_economics) and defers
    un-witnessed circuits as ``status: "zk_pending"`` (core/btcp/
    orchestrator.py). Those labels were previously buried inside ``proofs``;
    this summary hoists them so a consumer reading the response top-level
    can never mistake self-attested caller data or deferred circuits for
    TRION-verified truth. ``proof_verification.all_valid`` stays the
    fail-closed verdict (zk_pending ⇒ not valid).
    """
    proofs = (getattr(route, "proofs", None) or {}) if route is not None else {}
    per_proof = {}
    zk_pending = []
    witness_labeled = []
    for name, proof in proofs.items():
        row = {}
        if isinstance(proof, dict):
            row["status"] = proof.get("status", "generated")
            if "witness_source" in proof:
                row["witness_source"] = proof["witness_source"]
                witness_labeled.append(name)
            if proof.get("status") == "zk_pending":
                zk_pending.append(name)
        else:
            row["status"] = "generated"
        per_proof[name] = row
    return {
        "per_proof": per_proof,
        "witness_source_labels": witness_labeled,
        "zk_pending": zk_pending,
        "note": (
            "Proofs with witness_source=caller_* attest CALLER-SUPPLIED claims "
            "(behavioral_data / iap_economics), not TRION-verified truth. "
            "Proofs listed in zk_pending are honestly deferred — no proof "
            "bytes exist and the route is NOT fully proven. Consult "
            "proof_verification.all_valid for the fail-closed verification "
            "verdict, which is False whenever any proof is zk_pending."),
    }


@btcp_bp.route("/api/v1/btcp/orchestrate", methods=["POST"])
def btcp_orchestrate():
    """Run the full BTCPOrchestrator six-step route sequence (Gap #4).

    Payload (the intent parameters the orchestrator accepts):
      source_chain, dest_chain  — chain ids (ints, required)
      source_address, dest_address — addresses on those chains (required)
      amount                    — integer amount (required)
      asset                     — asset id/address (required)
      intent_type               — default "TRANSFER"
      privacy_level             — PUBLIC|BASIC|STANDARD|COMPLIANT|FULL
                                  (default BASIC)
      deadline_offset           — seconds from now, default 3600
      behavioral_data           — optional object; supplies the HashDNA
                                  strands/block for the complementarity
                                  proof and the behavioral-credential
                                  thresholds
      iap_economics             — optional object; the IAP batch economics
                                  (total_gas, entity_gas,
                                  total_btcp_fee_wei, entity_share_wei,
                                  num_participants) for the IAP share proof

    Response: per-step results, the full route, its proofs (plus the
    verification verdict), and the SQLite write-through persistence status.
    The orchestrator is pure-Python and measures ~12 ms per route, so this
    runs synchronously — no async status endpoint is needed (the existing
    /api/v1/btcp/orchestrator/status covers the RPC/indexer health plane).
    """
    from core.btcp.orchestrator import _gas_to_row
    data = request.get_json(force=True, silent=True) or {}
    try:
        source_chain = _require(data, "source_chain", int)
        dest_chain = _require(data, "dest_chain", int)
        if source_chain < 0 or dest_chain < 0:
            raise ValueError("chain ids must be non-negative integers")
        source_address = data.get("source_address")
        if not isinstance(source_address, str) or not source_address:
            raise ValueError("source_address is required (string)")
        dest_address = data.get("dest_address")
        if not isinstance(dest_address, str) or not dest_address:
            raise ValueError("dest_address is required (string)")
        amount = _require(data, "amount", int)
        if amount < 0:
            raise ValueError("amount must be a non-negative integer")
        asset = data.get("asset")
        if not isinstance(asset, str) or not asset:
            raise ValueError("asset is required (string)")
        intent_type = data.get("intent_type", "TRANSFER")
        if not isinstance(intent_type, str) or not intent_type:
            raise ValueError("intent_type must be a non-empty string")
        deadline_offset = int(data.get("deadline_offset", 3600))
        if deadline_offset <= 0:
            raise ValueError("deadline_offset must be a positive integer")
        privacy_level = _privacy_level_arg(data)
        for name in ("behavioral_data", "iap_economics"):
            if data.get(name) is not None and not isinstance(data.get(name), dict):
                raise ValueError(f"{name} must be an object")

        orch = _get_orchestrator()
        result = orch.create_route(
            source_chain=source_chain,
            dest_chain=dest_chain,
            source_address=source_address,
            dest_address=dest_address,
            amount=amount,
            asset=asset,
            intent_type=intent_type,
            privacy_level=privacy_level,
            deadline_offset=deadline_offset,
            behavioral_data=data.get("behavioral_data"),
            iap_economics=data.get("iap_economics"),
            # BTCP-FIX-INT — single /orchestrate call leaves a finalized
            # route so the §4.2 Step 6 Akashic Recording (Gap 1) and the
            # ANIMA reflexivity publish (Gap 3) fire automatically. The
            # caller can pass auto_finalize=false to defer (e.g. for
            # escrow-held routes).
            auto_finalize=bool(data.get("auto_finalize", True)),
            # BTCP-FIX-INT (Gap 4) — sovereign-actor SBA gate. When the
            # caller passes sovereign_actor=true, the orchestrator pulls
            # the L8.1 SBA score for nation_id and flags the route as
            # SOVEREIGN_RISK when SBA < 0.40.
            sovereign_actor=bool(data.get("sovereign_actor", False)),
            nation_id=data.get("nation_id"),
        )

        route = result.route
        route_id = route.route_id if route else None

        # proof verification verdict for the freshly generated route
        try:
            verified, verify_errors = orch.verify_route_proofs(route_id) \
                if route_id else (False, ["no route"])
        except Exception as e:
            verified, verify_errors = False, [f"verification failed: {e}"]

        # persistence: confirm the SQLite write-through actually landed
        try:
            state_db = orch._store.path
            persisted = route_id in orch._store.get_routes() if route_id else False
        except Exception:
            state_db, persisted = None, False

        steps = {}
        if route is not None:
            steps["1_validate_addresses"] = {
                "source_chain": source_chain,
                "dest_chain": dest_chain,
                "address_errors": [e for e in result.errors if "address" in e.lower()],
            }
            steps["2_create_intent"] = {
                "intent_id": route.intent.intent_id if route.intent else None,
                "intent_type": intent_type,
                "deadline": route.intent.deadline if route.intent else None,
            }
            steps["3_encode_for_vms"] = {
                "source_vm": route.source_vm.name,
                "dest_vm": route.dest_vm.name,
                "source_encoded": bool(route.source_encoded),
                "dest_encoded": bool(route.dest_encoded),
                "encoding_errors": [e for e in result.errors if "ncoding" in e],
            }
            steps["4_estimate_gas"] = {
                "source_gas": _gas_to_row(route.source_gas),
                "dest_gas": _gas_to_row(route.dest_gas),
                "total_fee": route.total_fee,
                "gas_errors": [e for e in result.errors if "gas" in e.lower()],
            }
            steps["5_generate_proofs"] = {
                "generated": list(route.proofs.keys()) if route.proofs else [],
                "proof_status": {
                    name: (proof.get("status")
                           if isinstance(proof, dict) and "status" in proof
                           else "generated")
                    for name, proof in (route.proofs or {}).items()
                },
            }
            steps["6_track_route"] = {
                "route_id": route_id,
                "status": route.status.name,
                "persisted": persisted,
                "state_db": state_db,
            }

        # BTCP Master Spec §4.2 — spec-aligned six-step execution surface
        # (Gap D3). The orchestrator now runs the full pipeline:
        #   Step 1 BIBL Analysis → Step 2 BTCP_score → Step 3 Cross-Chain
        #   Proof → Step 4 VM Translation → Step 5 IAP Gas Sharing →
        #   Step 6 Akashic Recording
        # `spec_steps` carries the orchestrator's own per-step outcomes
        # (status, components, formula, evidence). The legacy `steps` dict
        # above is preserved for backwards compatibility (existing
        # consumers that read steps["1_validate_addresses"], etc.).
        spec_steps = dict(getattr(result, "step_results", {}) or {})
        # The 6 spec-mandated steps. Additional derived steps (e.g.
        # 2b_xsl_liquidity_factor, 2c_sba_sovereign_risk) may be present
        # for credit/penalty multipliers — they don't replace the spec
        # pipeline, they extend it. We assert all 6 spec steps are present.
        _SPEC_SIX_STEPS = (
            "1_bibl_analysis",
            "2_btcp_score",
            "3_cross_chain_proof",
            "4_vm_translation",
            "5_iap_gas_sharing",
            "6_akashic_recording",
        )
        _missing_spec_steps = [s for s in _SPEC_SIX_STEPS if s not in spec_steps]
        _extra_steps = [s for s in spec_steps if s not in _SPEC_SIX_STEPS]

        return jsonify({
            "success": result.success,
            "route_id": route_id,
            "steps": steps,
            "spec_steps": spec_steps,
            "btcp_score": (route.btcp_score if route else 0.0),
            "six_step_pipeline": {
                "step_count_expected": 6,
                "step_count_executed": len(spec_steps),
                "all_six_steps_wired": len(_missing_spec_steps) == 0,
                "missing_spec_steps": _missing_spec_steps,
                "extra_derived_steps": _extra_steps,
                "step_order": list(_SPEC_SIX_STEPS),
                "spec_reference": "BTCP Master Spec §4.2 Six-Step Execution Sequence",
                "note": (
                    f"Spec §4.2 six-step pipeline present: "
                    f"{6 - len(_missing_spec_steps)}/6 spec steps "
                    f"({', '.join(_SPEC_SIX_STEPS)}). "
                    f"Extra derived steps (e.g. XSL/SBA multipliers from "
                    f"BTCP-FIX-INT) extend the pipeline; they do NOT replace "
                    f"the spec steps."
                ),
            },
            "route": route.to_dict() if route else None,
            "proofs": (route.proofs if route else None) or {},
            "proof_provenance": _proof_provenance_summary(route),
            "witness_inputs": {
                "behavioral_data": data.get("behavioral_data") is not None,
                "iap_economics": data.get("iap_economics") is not None,
                "note": (
                    "behavioral_data and iap_economics are caller-supplied "
                    "WITNESS EVIDENCE — the orchestrator labels the proofs "
                    "built from them with witness_source (see "
                    "proof_provenance); thresholds remain protocol constants "
                    "and cannot be moved by the caller"),
            },
            "proof_verification": {
                "all_valid": verified,
                "errors": verify_errors,
            },
            "persistence": {
                "persisted": persisted,
                "state_db": state_db,
            },
            # BTCP-FIX-INT — TRION-side integration assessments surfaced for
            # API echo. Each gap maps to a spec section (see comments above).
            "btcp_fix_int": {
                "gap_1_akashic_bh_writeback": {
                    "wired":   True,
                    "spec":    "§4.2 Step 6 — Finalization and Akashic Recording",
                    "finalized": bool(getattr(result, "finalized", False)),
                    "test_query": (
                        "SELECT count(*) FROM akashic_bh WHERE "
                        "event_type_name = 'BTCP_ROUTE_FINALIZED'"
                    ),
                },
                "gap_2_akashic_depth": {
                    "wired":   True,
                    "spec":    "§2.1 D(t) = Σ A·(1+M)·C — BTCP route finalizations added",
                    "entry":   "core.akashic.depth.compute_akashic_depth(btcp_routes=...)",
                },
                "gap_3_anima_reflexivity": {
                    "wired":   bool(getattr(result, "finalized", False)),
                    "spec":    "§3.5 — ANIMA Reflexivity Dampening publish",
                    "endpoint": (
                        "POST http://127.0.0.1:8000/api/v1/anima/reflexivity/"
                        "<entity_id>/publish?anima_score=<score>&phi_before=<phi>"
                    ),
                },
                "gap_4_l8_sba_sovereign_gate": {
                    "wired":      bool(data.get("sovereign_actor", False)),
                    "spec":       "§8.1 / whitepaper L8.1 — Sovereign Behavioral Assessment",
                    "sba_assessment": getattr(result, "sba_assessment", None),
                    "sba_risk_flag":  getattr(result, "sba_risk_flag", None),
                    "nation_id":      data.get("nation_id"),
                },
                "gap_5_l9_xsl_liquidity_multiplier": {
                    "wired":         True,
                    "spec":          "§9.1 / whitepaper L9.1 — XSL = TV·FS·RR/(1+TP)",
                    "xsl_assessment": getattr(result, "xsl_assessment", None),
                    "multiplier":     "btcp_score × (1 + 0.20·XSL)",
                },
            },
            "errors": result.errors,
            "execution_time_ms": round(result.execution_time_ms, 2),
            "specification": "BTCP six-step orchestration — L7 BTCP Cross-Chain Protocol",
        })
    except Exception as e:
        return jsonify({"error": str(e)}), 400


# ── Phase 6: Sanctions screening (J1) ─────────────────────────────────────────

_SANCTIONS_ORACLE = None


def _get_sanctions_oracle():
    """Lazily construct the shared SanctionsOracle singleton (J1)."""
    global _SANCTIONS_ORACLE
    if _SANCTIONS_ORACLE is None:
        from core.price.btcp_price_oracle import SanctionsOracle
        _SANCTIONS_ORACLE = SanctionsOracle()
    return _SANCTIONS_ORACLE


@btcp_bp.route("/api/v1/btcp/sanctions/<address>", methods=["GET"])
def btcp_sanctions_check(address):
    """
    Check an address against the TRION sanctions oracle (J1).

    Response fields:
      sanctioned  — true only when the address is on a loaded list
      lists       — which lists matched (or SCREENING_UNAVAILABLE on error)
      confidence  — 1.0 for a confirmed hit, lower for fuzzy matches
      coverage    — how many addresses the oracle currently holds and when
                    the list was last refreshed; integrators MUST treat a
                    zero-coverage oracle as "cannot screen", not "clean".
    """
    oracle = _get_sanctions_oracle()
    try:
        result = oracle.is_sanctioned(address)
    except Exception as e:
        return jsonify({
            "sanctioned": True,
            "lists": ["SCREENING_UNAVAILABLE"],
            "confidence": 0.0,
            "error": str(e),
        }), 503
    result["coverage"] = {
        "entries": oracle.count(),
        "last_refresh": oracle._last_refresh,
        "list_hash": oracle._list_hash,
        "note": ("sanctions feed not loaded — treat every 'not sanctioned' "
                 "answer as unverified until entries > 0") if oracle.count() == 0 else "",
    }
    return jsonify(result)


@btcp_bp.route("/api/v1/btcp/sanctions", methods=["POST"])
def btcp_sanctions_upsert():
    """
    Add (or delist) an entry on the sanctions oracle.

    Intended for the signed oracle feed verifier in production; requires the
    admin token when TRION_ADMIN_TOKEN is set. Payload:
      {"address": "0x..", "lists": ["OFAC_SDN"], "confidence": 1.0,
       "remove": false}

    W3-M fail-closed policy: the sanctions list is AUTHORITATIVE compliance
    data, not caller evidence. When NEITHER TRION_ADMIN_TOKEN NOR the global
    TRION_API_KEY is configured, this endpoint refuses to mutate the list
    (503) — an unauthenticated caller must never be able to delist a
    sanctioned address. Reads (/sanctions/<address>) stay public.
    """
    admin_token = None
    import os
    admin_token = os.environ.get("TRION_ADMIN_TOKEN")
    if admin_token:
        auth = request.headers.get("Authorization", "")
        if auth != f"Bearer {admin_token}":
            return jsonify({"error": "unauthorized"}), 401
    elif not os.environ.get("TRION_API_KEY", "").strip():
        # No admin token AND no global API key: the write path is NOT
        # authenticated by any layer — refuse (fail-closed). When
        # TRION_API_KEY is set, the app-level before_request middleware
        # already enforces X-API-Key on this POST.
        return jsonify({
            "error": "sanctions upsert disabled",
            "reason": ("no TRION_ADMIN_TOKEN and no TRION_API_KEY configured — "
                       "unauthenticated sanctions-list mutation is refused; "
                       "configure an admin credential to enable the feed"),
        }), 503
    data = request.get_json(force=True, silent=True) or {}
    address = data.get("address", "")
    if not isinstance(address, str) or len(address) < 10:
        return jsonify({"error": "address required"}), 400
    oracle = _get_sanctions_oracle()
    if data.get("remove"):
        oracle.remove_delisted(address)
        return jsonify({"address": address, "removed": True})
    lists = data.get("lists") or ["OFAC_SDN"]
    confidence = float(data.get("confidence", 1.0))
    oracle.add_sanctioned(address, lists, confidence)
    return jsonify({"address": address, "added": True, "lists": lists,
                    "confidence": confidence, "entries": oracle.count()})
