"""
TRION Protocol — Complete Signal System
24 signal types: 19 canonical (whitepaper Section 11) + 5 extended (L6–L9 planes).

Canonical 19 (whitepaper Section 11):
  VALUATION, SILENCE, LIQUIDITY_HEALTH, MANIPULATION_ALERT, TRAJECTORY,
  SYSTEMIC_RISK, GOVERNANCE_SIGNAL, CROSS_CHAIN_COHERENCE, STABLECOIN_HEALTH,
  PHASE_TRANSITION, FORK_DIVERGENCE, GENESIS, REGULATORY_BHV,
  SOVEREIGN_BEHAVIORAL, MEV_BEHAVIORAL (alias: MEV_EXPOSURE),
  ENERGY_PARTICIPATION, BIOLOGICAL_CAPITAL, BTCP_ROUTE, CONSENSUS_ADAPTATION.

Extended 5 (beyond canonical 19, retained for coverage breadth):
  RESURRECTION, NEGATIVE_SPACE, INSTITUTIONAL_BHV, ECOSYSTEM_HEALTH, BOOTSTRAP.

Every signal includes: CI_95 always, biological_time,
full provenance chain, coherence breakdown.

Provenance (whitepaper Section 11 — previously always empty, fixed):
  Every signal carries a non-empty `provenance` list recording the actual
  computation sources: caller-supplied source records (e.g. behavioral-hash
  ids backing the signal) plus auto-recorded entries for the coherence
  evaluation, the BRT phase derivation (OBSERVED vs CLOCK_FALLBACK), and
  the genomic signature generation. Entries are factual records of what
  produced the signal value — never fabricated hashes.

BRT observed-timestamp path (fixed import):
  compute_brt() derives circadian/ultradian phases from observed timestamps
  via core.akashic.bibl.derive_brt_from_observations (real circular
  statistics). The previous import target `akashic.brt_scheduler` never
  existed in the akashic/ package (the real BRT scheduler lives in
  anima-service/brt_scheduler.py, which is not importable as a Python
  package — hyphenated directory, no __init__.py), so the observed path
  silently degraded to wall-clock. The biological_time dict now carries
  an honest `brt_source` label.

SILENCE signal carries:
  coherence_gap, limiting_plane, coherence_trend, eta

Author: TRION Protocol — Originator: Hudu Yusuf (Analys)
License: CC0
"""

from __future__ import annotations

import time
import uuid
from typing import Optional
from enum import IntEnum


class SignalType(IntEnum):
    VALUATION             = 0
    SILENCE               = 1
    MANIPULATION_ALERT    = 2
    GENESIS               = 3
    RESURRECTION          = 4
    FORK_DIVERGENCE       = 5
    TRAJECTORY            = 6
    NEGATIVE_SPACE        = 7
    PHASE_TRANSITION      = 8
    SYSTEMIC_RISK         = 9
    LIQUIDITY_HEALTH      = 10
    GOVERNANCE_SIGNAL     = 11
    CROSS_CHAIN_COHERENCE = 12
    STABLECOIN_HEALTH     = 13
    MEV_EXPOSURE          = 14
    INSTITUTIONAL_BHV     = 15
    REGULATORY_BHV        = 16
    ECOSYSTEM_HEALTH      = 17
    BOOTSTRAP             = 18
    # ── Extended signals (whitepaper original Section 11 — L6–L9 planes) ─────
    SOVEREIGN_BEHAVIORAL  = 19   # L8.1 SBA — sovereign entity behavioral divergence
    ENERGY_PARTICIPATION  = 20   # L7.2 EP  — energy participation index signal
    BIOLOGICAL_CAPITAL    = 21   # L6.1 BC  — biological capital ecosystem health
    BTCP_ROUTE            = 22   # BIBL     — behavioral transaction continuity routing
    CONSENSUS_ADAPTATION  = 23   # L4.1     — adaptive consensus mechanism state change


# ─── BTCP §14.2 domain signal registry (Wave 3 D, R-SG-03 remediation) ────────
#
# BTCP Master Implementation Spec §14.2 "New Signal Types to Add" lists ten
# BTCP-domain names. Three already exist in the canonical 24-type registry
# above (BTCP_ROUTE=22, CONSENSUS_ADAPTATION=23, RESURRECTION=4). The
# remaining seven are registered here as an EXPLICIT BTCP-domain extension:
#
#   * The canonical 24-type registry stays EXACTLY 24 (signal_types.md
#     invariant "Exactly 24 signal types are defined; new types require a
#     protocol fork"; wasm signal_type_count()==24; rust
#     SIGNAL_TYPE_COUNT==24; on-chain ids 0–23 — cross-language parity).
#   * BTCP §14.2 types are emitted as TYPED SUB-PAYLOADS (signal_subtype)
#     on their closest canonical carrier — the same pattern the repo
#     already established for LIQUIDITY_OCEAN (core/extended/
#     natural_liquidity.py: "emitted as an EXTENDED PAYLOAD on
#     LIQUIDITY_HEALTH (id 10)").
#   * classify_signal() makes every one of the 31 names classifiable at
#     emission (domain / carrier / severity / emitter layer / TTL class).
BTCP_DOMAIN_SIGNALS = {
    # name                  carrier (canonical 24)         severity      emitter_layer
    "BEHAVIORAL_TRUTH":   {"carrier": "VALUATION",             "severity": "info",     "layer": "L1",  "ttl_class": "critical"},
    "SHADOW_CHAIN":       {"carrier": "SYSTEMIC_RISK",         "severity": "warning",  "layer": "L9",  "ttl_class": "critical"},
    "LIQUIDITY_OCEAN":    {"carrier": "LIQUIDITY_HEALTH",      "severity": "info",     "layer": "L7",  "ttl_class": "non_critical"},
    "CHAIN_RELIABILITY":  {"carrier": "CROSS_CHAIN_COHERENCE", "severity": "warning",  "layer": "L9",  "ttl_class": "non_critical"},
    "BTCP_ESCROW_EVENT":  {"carrier": "BTCP_ROUTE",            "severity": "info",     "layer": "L9",  "ttl_class": "non_critical"},
    "BTCP_TIMEOUT":       {"carrier": "BTCP_ROUTE",            "severity": "warning",  "layer": "L9",  "ttl_class": "critical"},
    "GENESIS_COMMITMENT": {"carrier": "GENESIS",               "severity": "info",     "layer": "L2",  "ttl_class": "non_critical"},
}

# Canonical MD §11 19-type list (exact names, MD wins semantics) — used by
# the registry-completeness classification and tests.
CANONICAL_19_TYPES = [
    "VALUATION", "SILENCE", "LIQUIDITY_HEALTH", "MANIPULATION_ALERT",
    "TRAJECTORY", "SYSTEMIC_RISK", "GOVERNANCE_SIGNAL",
    "CROSS_CHAIN_COHERENCE", "STABLECOIN_HEALTH", "PHASE_TRANSITION",
    "FORK_DIVERGENCE", "GENESIS", "REGULATORY_BHV", "SOVEREIGN_BEHAVIORAL",
    "MEV_EXPOSURE", "ENERGY_PARTICIPATION", "BIOLOGICAL_CAPITAL",
    "BTCP_ROUTE", "CONSENSUS_ADAPTATION",
]

# V2 Part 5 five extended types (authoritative where MD is silent).
V2_EXTENDED_5_TYPES = [
    "RESURRECTION", "NEGATIVE_SPACE", "INSTITUTIONAL_BHV",
    "ECOSYSTEM_HEALTH", "BOOTSTRAP",
]


def signal_registry() -> dict:
    """Complete registry view: canonical 24 + BTCP §14.2 domain extension."""
    return {
        "canonical_24": [t.name for t in SignalType],
        "canonical_19": CANONICAL_19_TYPES,
        "v2_extended_5": V2_EXTENDED_5_TYPES,
        "btcp_domain_7": sorted(BTCP_DOMAIN_SIGNALS.keys()),
        "total_classifiable": len(SignalType) + len(BTCP_DOMAIN_SIGNALS),
    }


def classify_signal(name_or_type) -> dict:
    """Emission classification for any canonical or BTCP-domain signal name.

    Returns {type_name, signal_type_id, domain, carrier, severity,
    emitter_layer, ttl_class}. Unknown names raise KeyError (fail-closed:
    an unclassifiable type must not be emitted — signal_types.md envelope
    rule "A signal without a valid emitter_layer MUST be rejected").
    """
    if isinstance(name_or_type, SignalType):
        st = name_or_type
    else:
        try:
            st = SignalType[str(name_or_type).upper()]
        except KeyError:
            name = str(name_or_type).upper()
            if name in BTCP_DOMAIN_SIGNALS:
                meta = BTCP_DOMAIN_SIGNALS[name]
                carrier = SignalType[meta["carrier"]]
                domain = "btcp_14_2"
                return {
                    "type_name":       name,
                    "signal_type_id":  int(carrier),   # carried on the carrier id
                    "domain":          domain,
                    "carrier":         meta["carrier"],
                    "signal_subtype":  name,
                    "severity":        meta["severity"],
                    "emitter_layer":   meta["layer"],
                    "ttl_class":       meta["ttl_class"],
                }
            raise KeyError(
                f"unclassifiable signal type {name_or_type!r} — not in the "
                f"canonical 24 (MD §11 ∪ V2 Part 5) nor the BTCP §14.2 "
                f"domain registry"
            )
    name = st.name
    if name in CANONICAL_19_TYPES:
        domain = "canonical_19"
    elif name in V2_EXTENDED_5_TYPES:
        domain = "v2_extended_5"
    else:  # pragma: no cover — enum is exactly 19 + 5
        raise KeyError(f"signal type {name} not in the canonical lists")
    return {
        "type_name":      name,
        "signal_type_id": int(st),
        "domain":         domain,
        "carrier":        name,
        "signal_subtype": None,
        "severity":       "critical" if name in ("MANIPULATION_ALERT", "SYSTEMIC_RISK") else "info",
        "emitter_layer":  "L1",
        "ttl_class":      "critical" if name in ("MANIPULATION_ALERT", "SYSTEMIC_RISK") else "non_critical",
    }


def compute_brt(unix_ts: float, observed_timestamps: Optional[list] = None) -> dict:
    """
    Biological Rhythm Timer — four phases.
    Uses observed timestamps for circadian/ultradian if available.

    Observed-timestamp derivation delegates to
    core.akashic.bibl.derive_brt_from_observations (circular mean +
    resultant strength; CLOCK_FALLBACK below 48 observations or strength
    ≤ 0.20). The dict additionally carries an honest `brt_source` label
    ("OBSERVED" | "CLOCK_FALLBACK") and the observed circadian strength.
    """
    circ  = (unix_ts % 86400)    / 86400
    ultr  = (unix_ts % 5400)     / 5400
    lunar = (unix_ts % 2551442)  / 2551442
    seas  = (unix_ts % 31557600) / 31557600

    brt_source         = "CLOCK_FALLBACK"
    circadian_strength = 0.0

    if observed_timestamps and len(observed_timestamps) >= 24:
        try:
            # Real observed-timestamp BRT via circular statistics.
            # (The historical import `akashic.brt_scheduler` pointed at a
            # module that never existed in akashic/ — the live scheduler is
            # anima-service/brt_scheduler.py, not importable as a package.
            # core.akashic.bibl implements the same derivation and is the
            # canonical importable location — see deep-read finding #1.)
            from core.akashic.bibl import derive_brt_from_observations
            brt_obs = derive_brt_from_observations(observed_timestamps)
            if brt_obs.brt_data_source == "OBSERVED":
                circ = brt_obs.circadian_phase
                ultr = brt_obs.ultradian_phase
            brt_source         = brt_obs.brt_data_source
            circadian_strength = brt_obs.circadian_strength
        except ImportError as _brt_import_err:
            # Direct-script execution: repo root not yet on sys.path —
            # add it (mirrors core.akashic.bibl's own fallback) and retry.
            import sys as _sys, os as _os
            _sys.path.insert(0, _os.path.join(_os.path.dirname(__file__), "..", ".."))
            try:
                from core.akashic.bibl import derive_brt_from_observations
                brt_obs = derive_brt_from_observations(observed_timestamps)
                if brt_obs.brt_data_source == "OBSERVED":
                    circ = brt_obs.circadian_phase
                    ultr = brt_obs.ultradian_phase
                brt_source         = brt_obs.brt_data_source
                circadian_strength = brt_obs.circadian_strength
            except Exception:
                import logging as _logging
                _logging.getLogger(__name__).warning(
                    "BRT observed phase derivation failed after path fixup: %s",
                    _brt_import_err, exc_info=True
                )
        except Exception as _brt_err:
            import logging as _logging
            _logging.getLogger(__name__).warning(
                "BRT observed phase derivation failed: %s", _brt_err, exc_info=True
            )

    return {
        "circadian_phase":    circ,
        "ultradian_phase":    ultr,
        "lunar_phase":        lunar,
        "seasonal_phase":     seas,
        "brt_source":         brt_source,
        "circadian_strength": round(circadian_strength, 6),
    }


import hashlib as _hashlib


def _genomic_signature(entity_id_str: str, generation: int = 0) -> str:
    """
    Compute genomic_signature: bytes64 (128 hex chars) from sense+antisense strands.
    Whitepaper L0.1 dual-strand DNA schema:
      sense     = SHA3-256(payload || 0x00)
      antisense = SHA3-256(payload || 0xFF) XOR complement(sense)

    The XOR-complement construction binds antisense to sense cryptographically:
    any tampering with either strand breaks the invariant, enabling tamper detection.
    Two independent hashes would NOT provide this property.
    """
    payload     = (entity_id_str + str(generation)).encode()
    sense_b     = _hashlib.sha3_256(payload + b'\x00').digest()
    sha3ff_b    = _hashlib.sha3_256(payload + b'\xFF').digest()
    # antisense = SHA3(payload||0xFF) XOR NOT(sense)
    antisense_b = bytes(s ^ (f ^ 0xFF) for s, f in zip(sha3ff_b, sense_b))
    return sense_b.hex() + antisense_b.hex()   # 128 hex chars = 64 bytes


def _build_provenance(
    caller_provenance: Optional[list],
    coherence_result:  dict,
    brt:               dict,
    observed_timestamps: Optional[list],
    entity_id_str:     str,
    genomic_generation: int,
    now:               float,
) -> list:
    """
    Build the actual provenance chain for a TRIONSignal.

    Layers (in order):
      1. Caller-supplied source records — e.g. behavioral-hash ids or upstream
         source dicts backing this signal (`provenance=[...]` argument).
         Strings are normalized to {"source": "behavioral_hash", "bh_id": s}.
      2. Coherence-engine evaluation record — the C(t)/Θ(t) computation that
         gated the signal, with the contributing planes.
      3. BRT derivation record — wall-clock vs OBSERVED circular statistics,
         with the observation count.
      4. Genomic-signature record — the dual-strand SHA3-256 generation.

    All entries are factual descriptions of the computation performed;
    no hashes or sources are fabricated.
    """
    prov: list = []

    for entry in (caller_provenance or []):
        if isinstance(entry, str):
            prov.append({"source": "behavioral_hash", "bh_id": entry, "ts": int(now)})
        elif isinstance(entry, dict):
            prov.append(dict(entry))

    planes = coherence_result.get("plane_breakdown", {}) or {}
    prov.append({
        "source":   "coherence_engine",
        "stage":    "C(t)/Θ(t) evaluation",
        "C":        coherence_result.get("C", 0.0),
        "theta":    coherence_result.get("theta", 0.55),
        "emits":    coherence_result.get("emits", False),
        "planes":   sorted(planes.keys()) if planes else [],
        "ts":       int(now),
    })

    prov.append({
        "source":       "brt",
        "stage":        "biological_time derivation",
        "data_source":  brt.get("brt_source", "CLOCK_FALLBACK"),
        "observations": len(observed_timestamps) if observed_timestamps else 0,
        "ts":           int(now),
    })

    prov.append({
        "source":     "genomic_signature",
        "stage":      "dual-strand SHA3-256 (L0.1)",
        "entity":     entity_id_str[:16] + ("…" if len(entity_id_str) > 16 else ""),
        "generation": genomic_generation,
        "ts":         int(now),
    })

    return prov


def _awa_gate_state():
    """Consult the MD §17 emission-freeze gate (governance singleton).

    Returns (frozen: bool, gate_dict: dict). Import is lazy so the signal
    factory stays importable in minimal runtimes (governance layer absent
    → no freeze state recorded → gate open; honest default documented in
    core/governance/awa.py).
    """
    try:
        from core.governance.awa import is_emission_frozen, get_emission_gate
        return is_emission_frozen(), get_emission_gate().to_dict()
    except Exception:
        return False, {"emission_frozen": False, "freeze_reason": "governance layer unavailable"}


def build_signal(
    entity_id:            object,
    signal_type:          SignalType,
    coherence_result:     dict,
    signal_value:         Optional[float] = None,
    ci_95_lower:          float = 0.0,
    ci_95_upper:          float = 1.0,
    extra:                Optional[dict] = None,
    observed_timestamps:  Optional[list] = None,
    provenance:           Optional[list] = None,
    genomic_generation:   int = 0,
    immune_clearance:     bool = True,
    validator_count:      int = 0,
    validator_hhi:        float = 0.0,
    reflexivity_flag:     bool = False,
    oe_factor:            float = 0.0,
    temporal_coherence:   float = 1.0,
    conf_genesis:         Optional[float] = None,
    akashic_depth:        Optional[float] = None,
    # ── L0.5 Signal Selection Principle (entropy-budget gate, Wave 3 D) ──
    # Optional caller-supplied information-gain / entropy-cost figures.
    # When BOTH are provided, the L0.5 gate applies: a signal whose
    # dI_gained/dS_entropy_cost <= theta_selection is SUPPRESSED (emitted
    # as SILENCE with the selection record). Values are NEVER fabricated —
    # omitting them means the budget is unmeasured for this emission.
    i_gained:             Optional[float] = None,
    s_entropy_cost:       Optional[float] = None,
    theta_selection:      float = 1.0,
) -> dict:
    """
    Build a complete TRIONSignal object with all whitepaper-mandated fields.

    Whitepaper-specified mandatory fields (Section 11):
      signal_id, signal_type, entity_id, signal_value, ci_95 (always present),
      coherence, threshold, biological_time (BRT 4 phases), genomic_signature,
      immune_clearance, security_generation, provenance, validator_count,
      validator_hhi, reflexivity_flag, OE_factor, temporal_coherence,
      conf_genesis, silence_gap, limiting_plane, coherence_trend, eta_blocks,
      akashic_depth, timestamp, ttl_seconds.

    EMISSION GATES (fail-closed, in order — Wave 3 D):
      1. MD §17 AWA freeze: while the governance AWA emission gate is frozen
         (AWA_enforced = FALSE — any of the six canonical conditions failed
         or a WEAPONIZATION_ATTEMPT fired), every non-SILENCE request is
         converted into a structured SILENCE signal (T(t) = 0) carrying the
         awa_freeze record. SILENCE itself is always emittable — "the
         silence is not absence. It is information" (MD §2).
      2. L0.5 Signal Selection: when the caller supplies BOTH i_gained and
         s_entropy_cost, the thermodynamic selection principle applies
         (dI/dS > theta_selection) — a below-threshold signal is emitted as
         SILENCE with the selection record (never fabricated inputs).

    Args:
        provenance: optional caller-supplied source records (behavioral-hash
            ids as strings, or source dicts) that back this signal. They are
            placed first in the signal's provenance chain, followed by the
            auto-recorded coherence/BRT/genomic entries. When omitted, the
            chain still records the actual computation sources (it is never
            an empty list).
        i_gained / s_entropy_cost / theta_selection: optional L0.5 entropy-
            budget inputs (see above). Omitted = budget unmeasured (no
            fabrication).
    """
    now = time.time()
    brt = compute_brt(now, observed_timestamps)

    C     = coherence_result.get("C", 0.0)
    theta = coherence_result.get("theta", 0.55)
    emits = coherence_result.get("emits", False)

    entity_id_str = entity_id.hex() if isinstance(entity_id, bytes) else str(entity_id)

    # ── Emission gate 1: MD §17 AWA freeze (T(t) silence) ──────────────────
    # AWA_enforced = FALSE → signal emission FROZEN (cannot be overridden by
    # any single entity). Truth requests become structured SILENCE carrying
    # the freeze record; SILENCE requests pass through unchanged.
    awa_frozen, awa_gate_dict = _awa_gate_state()
    if awa_frozen and signal_type != SignalType.SILENCE:
        frozen_coh = dict(coherence_result)
        frozen_coh.update({
            "emits": False, "silence": True,
            "coherence_gap": max(0.0, theta - C),
        })
        frozen_sig = build_signal(
            entity_id, SignalType.SILENCE, frozen_coh,
            signal_value=None, ci_95_lower=0.0, ci_95_upper=0.0,
            observed_timestamps=observed_timestamps,
            provenance=provenance,
            genomic_generation=genomic_generation,
            immune_clearance=immune_clearance,
            validator_count=validator_count,
            validator_hhi=validator_hhi,
            reflexivity_flag=reflexivity_flag,
            oe_factor=oe_factor,
            temporal_coherence=temporal_coherence,
            conf_genesis=conf_genesis,
            akashic_depth=akashic_depth,
        )
        frozen_sig.update({
            "requested_signal_type": signal_type.name,
            "requested_signal_type_id": int(signal_type),
            "awa_freeze": awa_gate_dict,
            "silence_explanation": (
                "TRUTH EMISSION FROZEN (AWA, MD §17): "
                + (awa_gate_dict.get("freeze_reason") or "AWA not enforced")
                + ". T(t) = 0 — silence is information."
            ),
            **(extra or {}),
        })
        return frozen_sig

    # ── Emission gate 2: L0.5 Signal Selection Principle ────────────────
    # dI_gained/dS_entropy_cost > theta_selection — applied only when the
    # caller supplies real figures (no fabricated budget inputs).
    selection_record = None
    if i_gained is not None and s_entropy_cost is not None:
        from core.primitives.thermodynamics import apply_signal_selection
        selection_record = apply_signal_selection(
            signal_id="(pending)",
            i_gained=float(i_gained),
            s_entropy_cost=float(s_entropy_cost),
            theta=float(theta_selection),
        )
        if not selection_record.selected:
            sel_coh = dict(coherence_result)
            sel_coh.update({
                "emits": False, "silence": True,
                "coherence_gap": max(0.0, theta - C),
            })
            sel_sig = build_signal(
                entity_id, SignalType.SILENCE, sel_coh,
                signal_value=None, ci_95_lower=0.0, ci_95_upper=0.0,
                observed_timestamps=observed_timestamps,
                provenance=provenance,
                genomic_generation=genomic_generation,
                immune_clearance=immune_clearance,
                validator_count=validator_count,
                validator_hhi=validator_hhi,
                reflexivity_flag=reflexivity_flag,
                oe_factor=oe_factor,
                temporal_coherence=temporal_coherence,
                conf_genesis=conf_genesis,
                akashic_depth=akashic_depth,
            )
            sel_sig.update({
                "requested_signal_type": signal_type.name,
                "signal_selection": {
                    "i_gained": selection_record.i_gained,
                    "s_entropy_cost": selection_record.s_entropy_cost,
                    "ratio": selection_record.ratio,
                    "theta": selection_record.theta,
                    "selected": False,
                    "reason": selection_record.reason,
                },
                "silence_explanation": (
                    "L0.5 SIGNAL SELECTION SUPPRESSED: " + selection_record.reason
                ),
                **(extra or {}),
            })
            return sel_sig

    depth = akashic_depth if akashic_depth is not None else coherence_result.get("akashic_depth", 0)

    if conf_genesis is None and depth is not None and depth >= 0:
        import math as _math
        conf_genesis = round(1.0 - _math.exp(-0.001 * float(depth)), 6)

    gen_sig = _genomic_signature(entity_id_str, genomic_generation)

    prov = _build_provenance(
        caller_provenance=provenance,
        coherence_result=coherence_result,
        brt=brt,
        observed_timestamps=observed_timestamps,
        entity_id_str=entity_id_str,
        genomic_generation=genomic_generation,
        now=now,
    )

    signal = {
        "signal_id":          str(uuid.uuid4()),
        "signal_type":        signal_type.name,
        "signal_type_id":     int(signal_type),
        "entity_id":          entity_id_str,
        "signal_value":       signal_value,
        "ci_95":              [ci_95_lower, ci_95_upper],
        "coherence":          C,
        "threshold":          theta,
        "margin":             coherence_result.get("margin", C - theta),
        "plane_breakdown":    coherence_result.get("plane_breakdown", {}),
        "limiting_plane":     coherence_result.get("limiting_plane"),
        "weights":            coherence_result.get("weights", {}),
        "silence":            not emits,
        "silence_gap":        coherence_result.get("coherence_gap", 0),
        "coherence_trend":    coherence_result.get("trend", "STABLE"),
        "eta_blocks":         coherence_result.get("eta_blocks", 0),
        "akashic_depth":      depth,
        "observer_effect":    round(oe_factor, 6),
        "OE_factor":          round(oe_factor, 6),
        "bootstrap_phase":    any(
            coherence_result.get("bootstrap_planes", {}).values()
        ),
        "conf_genesis":       conf_genesis,
        "timestamp":          int(now),
        "ttl_seconds":        3600,
        "biological_time":    brt,
        "genomic_signature":  gen_sig,
        "immune_clearance":   immune_clearance,
        "security_generation": genomic_generation,
        "validator_count":    validator_count,
        "validator_hhi":      round(validator_hhi, 2),
        "reflexivity_flag":   reflexivity_flag,
        "temporal_coherence": round(temporal_coherence, 6),
        "provenance":         prov,
        **(extra or {}),
    }
    if selection_record is not None and selection_record.selected:
        signal["signal_selection"] = {
            "i_gained": selection_record.i_gained,
            "s_entropy_cost": selection_record.s_entropy_cost,
            "ratio": selection_record.ratio,
            "theta": selection_record.theta,
            "selected": True,
            "reason": selection_record.reason,
        }
    return signal


# ─── Signal Type 0: VALUATION ─────────────────────────────────────────────────

def build_valuation(
    entity_id, coherence_result: dict,
    signal_value: float,
    ci_95_lower: float,
    ci_95_upper: float,
    moat_factor: float = 1.0,
) -> dict:
    return build_signal(
        entity_id=entity_id,
        signal_type=SignalType.VALUATION,
        coherence_result=coherence_result,
        signal_value=signal_value,
        ci_95_lower=ci_95_lower,
        ci_95_upper=ci_95_upper,
        extra={"moat_factor": moat_factor},
    )


# ─── Signal Type 1: SILENCE ───────────────────────────────────────────────────

def build_silence(entity_id, coherence_result: dict) -> dict:
    return build_signal(
        entity_id=entity_id,
        signal_type=SignalType.SILENCE,
        coherence_result=coherence_result,
        signal_value=None,
        ci_95_lower=0.0,
        ci_95_upper=0.0,
        extra={
            "silence_explanation": (
                f"Coherence C(t)={coherence_result.get('C', 0):.4f} "
                f"below threshold Θ(t)={coherence_result.get('theta', 0):.4f}. "
                f"Limiting plane: {coherence_result.get('limiting_plane', 'unknown')}. "
                f"Trend: {coherence_result.get('trend', 'STABLE')}. "
                f"ETA: ~{coherence_result.get('eta_blocks', 0)} blocks."
            ),
        }
    )


# ─── Signal Type 2: MANIPULATION_ALERT ────────────────────────────────────────

def build_manipulation_alert(entity_id, coherence_result: dict, mf_result: dict) -> dict:
    return build_signal(
        entity_id=entity_id,
        signal_type=SignalType.MANIPULATION_ALERT,
        coherence_result=coherence_result,
        signal_value=mf_result.get("mf_score", 0),
        ci_95_lower=mf_result.get("mf_score", 0) * 0.9,
        ci_95_upper=min(1.0, mf_result.get("mf_score", 0) * 1.1),
        extra={
            "mf_score":       mf_result.get("mf_score", 0),
            "primary_type":   mf_result.get("primary_type"),
            "detected_types": mf_result.get("detected_types", []),
            "components":     mf_result.get("components", {}),
            "recommendation": "BLOCK_IMMEDIATELY",
        }
    )


# ─── Signal Type 3: GENESIS ───────────────────────────────────────────────────

def build_genesis(
    entity_id, coherence_result: dict,
    genesis_block: int,
    deployer_address: str,
    genesis_confidence: float,
    behavioral_age_days: float = 0.0,
    genomic_generation: int = 0,
) -> dict:
    return build_signal(
        entity_id=entity_id,
        signal_type=SignalType.GENESIS,
        coherence_result=coherence_result,
        signal_value=genesis_confidence,
        ci_95_lower=max(0.0, genesis_confidence - 0.10),
        ci_95_upper=min(1.0, genesis_confidence + 0.10),
        extra={
            "genesis_block":       genesis_block,
            "deployer_address":    deployer_address,
            "genesis_confidence":  genesis_confidence,
            "behavioral_age_days": behavioral_age_days,
            "genomic_generation":  genomic_generation,
            "bootstrap_note": (
                "Genesis entity — bootstrap phase active. "
                "Σ(t) will use bootstrap prior until 21+ validators observed."
            ),
        }
    )


# ─── Signal Type 4: RESURRECTION ──────────────────────────────────────────────

def build_resurrection(
    entity_id, coherence_result: dict,
    dormancy_days: float,
    resurrection_confidence: float,
    behavioral_continuity: float,
    last_seen_block: int,
    epigenetic_expression: str = "NORMAL",
) -> dict:
    return build_signal(
        entity_id=entity_id,
        signal_type=SignalType.RESURRECTION,
        coherence_result=coherence_result,
        signal_value=resurrection_confidence,
        ci_95_lower=max(0.0, resurrection_confidence - 0.15),
        ci_95_upper=min(1.0, resurrection_confidence + 0.15),
        extra={
            "dormancy_days":            dormancy_days,
            "resurrection_confidence":  resurrection_confidence,
            "behavioral_continuity":    behavioral_continuity,
            "last_seen_block":          last_seen_block,
            "epigenetic_expression":    epigenetic_expression,
            "caution": (
                "Resurrection after extended dormancy — "
                "behavioral continuity check required before full trust restoration."
                if dormancy_days > 90 else None
            ),
        }
    )


# ─── Signal Type 5: FORK_DIVERGENCE ───────────────────────────────────────────

def build_fork_divergence(
    entity_id, coherence_result: dict,
    fork_score: float,
    entity_a: str,
    entity_b: str,
    divergence_blocks: int,
    kl_divergence: float,
    recommended_action: str = "MONITOR",
) -> dict:
    return build_signal(
        entity_id=entity_id,
        signal_type=SignalType.FORK_DIVERGENCE,
        coherence_result=coherence_result,
        signal_value=fork_score,
        ci_95_lower=max(0.0, fork_score - 0.08),
        ci_95_upper=min(1.0, fork_score + 0.08),
        extra={
            "fork_score":          fork_score,
            "entity_a":            entity_a,
            "entity_b":            entity_b,
            "divergence_blocks":   divergence_blocks,
            "kl_divergence":       kl_divergence,
            "recommended_action":  recommended_action,
            "interpretation": (
                "HIGH divergence — entities have separated into distinct behavioral identities."
                if fork_score > 0.70 else
                "MODERATE divergence — entities share partial behavioral history."
                if fork_score > 0.40 else
                "LOW divergence — entities may be same actor on multiple wallets."
            ),
        }
    )


# ─── Signal Type 6: TRAJECTORY ────────────────────────────────────────────────

def build_trajectory(
    entity_id, coherence_result: dict,
    trajectory_score: float,
    direction: str,
    momentum: float,
    eta_blocks: int,
    archetype_matched: Optional[str] = None,
    manifestation_gap_mean: float = 0.0,
    reflexivity_score: float = 0.0,
) -> dict:
    return build_signal(
        entity_id=entity_id,
        signal_type=SignalType.TRAJECTORY,
        coherence_result=coherence_result,
        signal_value=trajectory_score,
        ci_95_lower=max(0.0, trajectory_score - 0.10),
        ci_95_upper=min(1.0, trajectory_score + 0.10),
        extra={
            "trajectory_score":      trajectory_score,
            "direction":             direction,         # "RISING", "FALLING", "SIDEWAYS"
            "momentum":              momentum,
            "eta_blocks":            eta_blocks,
            "archetype_matched":     archetype_matched,
            "manifestation_gap_mean": manifestation_gap_mean,
            "reflexivity_score":     reflexivity_score,
            "reflexivity_warning": (
                "SELF-FULFILLING RISK: trajectory signal may be influencing behavior "
                f"it predicts (reflexivity={reflexivity_score:.3f})"
                if reflexivity_score > 0.40 else None
            ),
            "conjecture_label": "CONJECTURE",
        }
    )


# ─── Signal Type 7: NEGATIVE_SPACE ────────────────────────────────────────────

def build_negative_space(
    entity_id, coherence_result: dict,
    absence_duration_blocks: int,
    expected_activity_score: float,
    absence_significance: float,
    pattern_context: str = "",
) -> dict:
    return build_signal(
        entity_id=entity_id,
        signal_type=SignalType.NEGATIVE_SPACE,
        coherence_result=coherence_result,
        signal_value=absence_significance,
        ci_95_lower=max(0.0, absence_significance - 0.10),
        ci_95_upper=min(1.0, absence_significance + 0.10),
        extra={
            "absence_duration_blocks": absence_duration_blocks,
            "expected_activity_score": expected_activity_score,
            "absence_significance":    absence_significance,
            "pattern_context":         pattern_context,
            "interpretation": (
                "Significant behavioral absence — entity is conspicuously NOT acting "
                "when historical pattern predicts activity. Negative space is signal."
            ),
        }
    )


# ─── Signal Type 8: PHASE_TRANSITION ──────────────────────────────────────────

def build_phase_transition(
    entity_id, coherence_result: dict,
    from_phase: str,
    to_phase: str,
    transition_confidence: float,
    epigenetic_trigger: str,
    threat_level: str,
    el_expression: str,
) -> dict:
    return build_signal(
        entity_id=entity_id,
        signal_type=SignalType.PHASE_TRANSITION,
        coherence_result=coherence_result,
        signal_value=transition_confidence,
        ci_95_lower=max(0.0, transition_confidence - 0.12),
        ci_95_upper=min(1.0, transition_confidence + 0.12),
        extra={
            "from_phase":             from_phase,
            "to_phase":               to_phase,
            "transition_confidence":  transition_confidence,
            "epigenetic_trigger":     epigenetic_trigger,
            "threat_level":           threat_level,
            "el_expression":          el_expression,
            "semi_immutability_note": (
                "Phase transition recorded in epigenetic layer — "
                "behavioral history is semi-immutable. "
                f"EL expression: {el_expression}"
            ),
        }
    )


# ─── Signal Type 9: SYSTEMIC_RISK ─────────────────────────────────────────────

def build_systemic_risk(
    entity_id, coherence_result: dict,
    risk_score: float,
    risk_factors: list,
    hhi: float,
    cross_chain_correlation: float,
    contagion_radius: int,
) -> dict:
    tier = (
        "CRITICAL" if risk_score > 0.80 else
        "HIGH"     if risk_score > 0.60 else
        "MODERATE" if risk_score > 0.40 else
        "LOW"
    )
    return build_signal(
        entity_id=entity_id,
        signal_type=SignalType.SYSTEMIC_RISK,
        coherence_result=coherence_result,
        signal_value=risk_score,
        ci_95_lower=max(0.0, risk_score - 0.08),
        ci_95_upper=min(1.0, risk_score + 0.08),
        extra={
            "risk_score":               risk_score,
            "risk_tier":                tier,
            "risk_factors":             risk_factors,
            "hhi":                      hhi,
            "cross_chain_correlation":  cross_chain_correlation,
            "contagion_radius":         contagion_radius,
            "awa_triggered":            hhi > 4000,
            "governance_emergency":     risk_score > 0.80 and hhi > 4000,
        }
    )


# ─── Signal Type 10: LIQUIDITY_HEALTH ────────────────────────────────────────

def build_liquidity_health(
    entity_id, coherence_result: dict,
    nl_score: float, ld: float, lo: float, lc: float, ls: float,
    asset_address: str,
) -> dict:
    return build_signal(
        entity_id=entity_id,
        signal_type=SignalType.LIQUIDITY_HEALTH,
        coherence_result=coherence_result,
        signal_value=nl_score,
        ci_95_lower=max(0, nl_score - 0.05),
        ci_95_upper=min(1, nl_score + 0.05),
        extra={
            "nl_score":      nl_score,
            "nl_components": {"LD": ld, "LO": lo, "LC": lc, "LS": ls},
            "asset_address": asset_address,
            "recommendation": "DO_NOT_ROUTE" if nl_score < 0.30 else "CAUTION" if nl_score < 0.50 else "ROUTE_OK",
            "explanation": (
                f"NL={nl_score:.2f} below safe threshold 0.30. "
                f"LD={ld:.2f} LO={lo:.2f} LC={lc:.2f} LS={ls:.2f}. "
                "Pool cannot safely absorb this transaction."
                if nl_score < 0.30 else f"NL={nl_score:.2f} — liquidity healthy."
            ),
        }
    )


# ─── Signal Type 11: GOVERNANCE_SIGNAL ───────────────────────────────────────

def build_governance_signal(
    entity_id, coherence_result: dict,
    governance_score: float,
    quorum_reached: bool,
    hhi: float,
    validator_count: int,
    awa_enforced: bool,
    signals_frozen: bool,
    active_proposal: Optional[str] = None,
) -> dict:
    health = (
        "CRITICAL" if hhi > 4000 else
        "DANGER"   if hhi > 2500 else
        "WARNING"  if hhi > 1500 else
        "HEALTHY"
    )
    return build_signal(
        entity_id=entity_id,
        signal_type=SignalType.GOVERNANCE_SIGNAL,
        coherence_result=coherence_result,
        signal_value=governance_score,
        ci_95_lower=max(0.0, governance_score - 0.05),
        ci_95_upper=min(1.0, governance_score + 0.05),
        extra={
            "governance_score":  governance_score,
            "quorum_reached":    quorum_reached,
            "hhi":               hhi,
            "hhi_health":        health,
            "validator_count":   validator_count,
            "awa_enforced":      awa_enforced,
            "signals_frozen":    signals_frozen,
            "active_proposal":   active_proposal,
            "diversity_note": (
                f"HHI={hhi:.0f} [{health}] — "
                f"{'EMERGENCY: consensus paused' if signals_frozen else 'consensus active'}"
            ),
        }
    )


# ─── Signal Type 12: CROSS_CHAIN_COHERENCE ───────────────────────────────────

def build_cross_chain_coherence(
    entity_id, coherence_result: dict,
    cross_chain_score: float,
    chains_analyzed: list,
    highest_chain: str,
    lowest_chain: str,
    coherence_spread: float,
    btcp_scores: Optional[dict] = None,
) -> dict:
    return build_signal(
        entity_id=entity_id,
        signal_type=SignalType.CROSS_CHAIN_COHERENCE,
        coherence_result=coherence_result,
        signal_value=cross_chain_score,
        ci_95_lower=max(0.0, cross_chain_score - 0.06),
        ci_95_upper=min(1.0, cross_chain_score + 0.06),
        extra={
            "cross_chain_score": cross_chain_score,
            "chains_analyzed":   chains_analyzed,
            "highest_chain":     highest_chain,
            "lowest_chain":      lowest_chain,
            "coherence_spread":  coherence_spread,
            "btcp_scores":       btcp_scores or {},
            "routing_recommendation": (
                f"Route via {highest_chain} — highest cross-chain coherence."
                if cross_chain_score > 0.55 else
                "CAUTION: Low cross-chain coherence. Use BTCP safety gates."
            ),
        }
    )


# ─── Signal Type 13: STABLECOIN_HEALTH ───────────────────────────────────────

def build_stablecoin_health(
    entity_id, coherence_result: dict,
    peg_stability_score: float,
    peg_deviation_pct: float,
    collateral_ratio: float,
    depeg_risk_score: float,
    asset_address: str,
) -> dict:
    return build_signal(
        entity_id=entity_id,
        signal_type=SignalType.STABLECOIN_HEALTH,
        coherence_result=coherence_result,
        signal_value=peg_stability_score,
        ci_95_lower=max(0.0, peg_stability_score - 0.04),
        ci_95_upper=min(1.0, peg_stability_score + 0.04),
        extra={
            "peg_stability_score": peg_stability_score,
            "peg_deviation_pct":   peg_deviation_pct,
            "collateral_ratio":    collateral_ratio,
            "depeg_risk_score":    depeg_risk_score,
            "asset_address":       asset_address,
            "alert": (
                "CRITICAL DEPEG RISK — do not use as settlement asset"
                if depeg_risk_score > 0.70 else
                "ELEVATED DEPEG RISK — monitor closely"
                if depeg_risk_score > 0.40 else None
            ),
        }
    )


# ─── Signal Type 14: MEV_EXPOSURE ─────────────────────────────────────────────

def build_mev_exposure(
    entity_id, coherence_result: dict,
    mev_score: float,
    mev_rate_30d: float,
    attack_types_detected: list,
    estimated_loss_pct: float,
    protection_available: bool,
    batch_size_recommendation: int = 1,
) -> dict:
    return build_signal(
        entity_id=entity_id,
        signal_type=SignalType.MEV_EXPOSURE,
        coherence_result=coherence_result,
        signal_value=mev_score,
        ci_95_lower=max(0.0, mev_score - 0.08),
        ci_95_upper=min(1.0, mev_score + 0.08),
        extra={
            "mev_score":                mev_score,
            "mev_rate_30d":             mev_rate_30d,
            "attack_types_detected":    attack_types_detected,
            "estimated_loss_pct":       estimated_loss_pct,
            "protection_available":     protection_available,
            "batch_size_recommendation": batch_size_recommendation,
            "recommendation": (
                f"BATCH {batch_size_recommendation}+ transactions "
                "to amortize MEV cost across bundle."
                if mev_score > 0.30 else "MEV risk acceptable"
            ),
        }
    )


# ─── Signal Type 15: INSTITUTIONAL_BHV ───────────────────────────────────────

def build_institutional_bhv(
    entity_id, coherence_result: dict,
    institutional_score: float,
    whale_activity_score: float,
    accumulation_signal: bool,
    distribution_signal: bool,
    smart_money_alignment: float,
) -> dict:
    regime = (
        "ACCUMULATION"  if accumulation_signal and not distribution_signal else
        "DISTRIBUTION"  if distribution_signal and not accumulation_signal else
        "MIXED"         if accumulation_signal and distribution_signal else
        "NEUTRAL"
    )
    return build_signal(
        entity_id=entity_id,
        signal_type=SignalType.INSTITUTIONAL_BHV,
        coherence_result=coherence_result,
        signal_value=institutional_score,
        ci_95_lower=max(0.0, institutional_score - 0.08),
        ci_95_upper=min(1.0, institutional_score + 0.08),
        extra={
            "institutional_score":  institutional_score,
            "whale_activity_score": whale_activity_score,
            "regime":               regime,
            "smart_money_alignment": smart_money_alignment,
            "behavioral_alpha": (
                f"Smart money {regime.lower()} phase detected. "
                f"Alignment={smart_money_alignment:.2f}"
            ),
        }
    )


# ─── Signal Type 16: REGULATORY_BHV ───────────────────────────────────────────

def build_regulatory_bhv(
    entity_id, coherence_result: dict,
    regulatory_score: float,
    jurisdiction: str,
    aml_score: float,
    jrs: float,
    compliance_tier: str,
    travel_rule_required: bool,
    action: str,
    zk_proof_id: Optional[str] = None,
) -> dict:
    return build_signal(
        entity_id=entity_id,
        signal_type=SignalType.REGULATORY_BHV,
        coherence_result=coherence_result,
        signal_value=regulatory_score,
        ci_95_lower=max(0.0, regulatory_score - 0.05),
        ci_95_upper=min(1.0, regulatory_score + 0.05),
        extra={
            "regulatory_score":     regulatory_score,
            "jurisdiction":         jurisdiction,
            "aml_score":            aml_score,
            "jrs":                  jrs,
            "compliance_tier":      compliance_tier,
            "travel_rule_required": travel_rule_required,
            "action":               action,
            "zk_proof_id":          zk_proof_id,
            "primitive_7_note": (
                "Regulatory Adaptation (Primitive 7): "
                f"R(t)={regulatory_score:.3f} [{compliance_tier}] "
                f"JRS={jrs:.3f} AML={aml_score:.3f}"
            ),
        }
    )


# ─── Signal Type 17: ECOSYSTEM_HEALTH ────────────────────────────────────────

def build_ecosystem_health(
    entity_id, coherence_result: dict,
    ecosystem_score: float,
    protocol_count: int,
    active_entities: int,
    tvl_behavioral_score: float,
    network_effect_score: float,
    ecosystem_id: str,
) -> dict:
    return build_signal(
        entity_id=entity_id,
        signal_type=SignalType.ECOSYSTEM_HEALTH,
        coherence_result=coherence_result,
        signal_value=ecosystem_score,
        ci_95_lower=max(0.0, ecosystem_score - 0.06),
        ci_95_upper=min(1.0, ecosystem_score + 0.06),
        extra={
            "ecosystem_score":        ecosystem_score,
            "ecosystem_id":           ecosystem_id,
            "protocol_count":         protocol_count,
            "active_entities":        active_entities,
            "tvl_behavioral_score":   tvl_behavioral_score,
            "network_effect_score":   network_effect_score,
            "health_tier": (
                "THRIVING" if ecosystem_score >= 0.75 else
                "HEALTHY"  if ecosystem_score >= 0.55 else
                "STRESSED" if ecosystem_score >= 0.35 else
                "CRITICAL"
            ),
        }
    )


# ─── Signal Type 18: BOOTSTRAP ────────────────────────────────────────────────

def build_bootstrap(
    entity_id, coherence_result: dict,
    bootstrap_progress: float,
    observations_needed: int,
    observations_current: int,
    planes_bootstrapped: dict,
    estimated_blocks_to_full: int,
) -> dict:
    return build_signal(
        entity_id=entity_id,
        signal_type=SignalType.BOOTSTRAP,
        coherence_result=coherence_result,
        signal_value=bootstrap_progress,
        ci_95_lower=0.0,
        ci_95_upper=0.0,
        extra={
            "bootstrap_progress":       bootstrap_progress,
            "observations_needed":      observations_needed,
            "observations_current":     observations_current,
            "planes_bootstrapped":      planes_bootstrapped,
            "estimated_blocks_to_full": estimated_blocks_to_full,
            "bootstrap_note": (
                f"Entity in bootstrap phase: {observations_current}/{observations_needed} "
                f"observations. Σ(t) using prior until full observation window complete. "
                f"ETA: ~{estimated_blocks_to_full} blocks."
            ),
        }
    )


# ─── Signal Type 19: SOVEREIGN_BEHAVIORAL ────────────────────────────────────

def build_sovereign_behavioral(
    entity_id, coherence_result: dict,
    sba_score: float,
    jurisdiction: str,
    policy_stated: float,
    policy_observed: float,
    divergence_index: float,
    capital_flow_entropy: float,
    threat_level: str = "LOW",
) -> dict:
    """
    L8.1 — Sovereign Behavioral Assessment (SBA) signal.
    Emits when sovereign/state-level behavioral patterns diverge from stated policy.
    SBA(s,t) = ΔP(s,t) · CF(s,t) · I(s,t)
    """
    return build_signal(
        entity_id=entity_id,
        signal_type=SignalType.SOVEREIGN_BEHAVIORAL,
        coherence_result=coherence_result,
        signal_value=sba_score,
        ci_95_lower=max(0.0, sba_score - 0.08),
        ci_95_upper=min(1.0, sba_score + 0.08),
        extra={
            "sba_score":             sba_score,
            "jurisdiction":          jurisdiction,
            "policy_stated":         policy_stated,
            "policy_observed":       policy_observed,
            "divergence_index":      divergence_index,
            "capital_flow_entropy":  capital_flow_entropy,
            "threat_level":          threat_level,
            "primitive_8_note": (
                f"Sovereign Behavioral Assessment (L8.1): "
                f"SBA={sba_score:.3f} jurisdiction={jurisdiction} "
                f"divergence={divergence_index:.3f} threat={threat_level}"
            ),
        }
    )


# ─── Signal Type 20: ENERGY_PARTICIPATION ────────────────────────────────────

def build_energy_participation(
    entity_id, coherence_result: dict,
    ep_score: float,
    validator_count: int,
    participation_ratio: float,
    decentralization_coefficient: float,
    energy_source_diversity: float,
    carbon_intensity: float = 0.0,
) -> dict:
    """
    L7.2 — Energy Participation Index (EP) signal.
    EP(asset,t) = VC(a,t) · PA(a,t) · DC(a,t)
    Measures validator energy participation quality and decentralization.
    """
    return build_signal(
        entity_id=entity_id,
        signal_type=SignalType.ENERGY_PARTICIPATION,
        coherence_result=coherence_result,
        signal_value=ep_score,
        ci_95_lower=max(0.0, ep_score - 0.05),
        ci_95_upper=min(1.0, ep_score + 0.05),
        extra={
            "ep_score":                    ep_score,
            "validator_count":             validator_count,
            "participation_ratio":         participation_ratio,
            "decentralization_coefficient": decentralization_coefficient,
            "energy_source_diversity":     energy_source_diversity,
            "carbon_intensity":            carbon_intensity,
            "participation_tier": (
                "OPTIMAL"   if ep_score >= 0.80 else
                "HEALTHY"   if ep_score >= 0.60 else
                "DEGRADED"  if ep_score >= 0.40 else
                "CRITICAL"
            ),
        }
    )


# ─── Signal Type 21: BIOLOGICAL_CAPITAL ──────────────────────────────────────

def build_biological_capital(
    entity_id, coherence_result: dict,
    bc_score: float,
    ecosystem_id: str,
    species_at_risk: int,
    keystone_health: float,
    resilience_index: float,
    interdependence_score: float,
    xsl_aggregate: float,
) -> dict:
    """
    L6.1 — Biological Capital (BC) signal.
    BC(e,t) = H(e,t) · R(e,t) · I(e,t)
    Cross-domain ecological health invisible to finance-only oracles.
    """
    return build_signal(
        entity_id=entity_id,
        signal_type=SignalType.BIOLOGICAL_CAPITAL,
        coherence_result=coherence_result,
        signal_value=bc_score,
        ci_95_lower=max(0.0, bc_score - 0.07),
        ci_95_upper=min(1.0, bc_score + 0.07),
        extra={
            "bc_score":             bc_score,
            "ecosystem_id":         ecosystem_id,
            "species_at_risk":      species_at_risk,
            "keystone_health":      keystone_health,
            "resilience_index":     resilience_index,
            "interdependence_score": interdependence_score,
            "xsl_aggregate":        xsl_aggregate,
            "ecological_tier": (
                "THRIVING"  if bc_score >= 0.75 else
                "STABLE"    if bc_score >= 0.55 else
                "STRESSED"  if bc_score >= 0.35 else
                "COLLAPSE_RISK"
            ),
            "novel_primitive_note": (
                "Stream 4 Biological+Ecological signal — "
                "cross-domain intelligence invisible to finance-only oracles."
            ),
        }
    )


# ─── Signal Type 22: BTCP_ROUTE ───────────────────────────────────────────────

def build_btcp_route(
    entity_id, coherence_result: dict,
    btcp_score: float,
    continuity_score: float,
    route_chain_ids: list,
    optimal_route: str,
    mev_exposure_on_route: float,
    batch_opportunity: bool,
    estimated_gas_saved: float,
    mempool_archetype: str = "NORMAL",
) -> dict:
    """
    BIBL — Behavioral Transaction Continuity Protocol (BTCP_ROUTE) signal.
    Emitted during the inter-block window with routing and MEV protection.
    Carries: optimal route, batch opportunity, gas savings, MEV warnings.
    """
    return build_signal(
        entity_id=entity_id,
        signal_type=SignalType.BTCP_ROUTE,
        coherence_result=coherence_result,
        signal_value=btcp_score,
        ci_95_lower=max(0.0, btcp_score - 0.04),
        ci_95_upper=min(1.0, btcp_score + 0.04),
        extra={
            "btcp_score":             btcp_score,
            "continuity_score":       continuity_score,
            "route_chain_ids":        route_chain_ids,
            "optimal_route":          optimal_route,
            "mev_exposure_on_route":  mev_exposure_on_route,
            "batch_opportunity":      batch_opportunity,
            "estimated_gas_saved":    estimated_gas_saved,
            "mempool_archetype":      mempool_archetype,
            "bibl_note": (
                f"BIBL inter-block routing: route={optimal_route} "
                f"MEV_exposure={mev_exposure_on_route:.3f} "
                f"archetype={mempool_archetype} "
                f"batch={'YES' if batch_opportunity else 'NO'}"
            ),
        }
    )


# ─── Signal Type 23: CONSENSUS_ADAPTATION ────────────────────────────────────

def build_consensus_adaptation(
    entity_id, coherence_result: dict,
    adaptation_score: float,
    previous_consensus_mode: str,
    new_consensus_mode: str,
    trigger_event: str,
    validator_diversity_index: float,
    hhi_pre: float,
    hhi_post: float,
    degradation_tier: int = 0,
) -> dict:
    """
    L4.1 DW-BFT — Consensus Adaptation signal.
    Emitted when the adaptive consensus mechanism changes state.
    Covers: validator composition change, HHI threshold crossing,
    Coordination Collapse detection, degradation tier transitions.
    """
    return build_signal(
        entity_id=entity_id,
        signal_type=SignalType.CONSENSUS_ADAPTATION,
        coherence_result=coherence_result,
        signal_value=adaptation_score,
        ci_95_lower=max(0.0, adaptation_score - 0.06),
        ci_95_upper=min(1.0, adaptation_score + 0.06),
        extra={
            "adaptation_score":        adaptation_score,
            "previous_consensus_mode": previous_consensus_mode,
            "new_consensus_mode":      new_consensus_mode,
            "trigger_event":           trigger_event,
            "validator_diversity_index": validator_diversity_index,
            "hhi_pre":                 hhi_pre,
            "hhi_post":                hhi_post,
            "degradation_tier":        degradation_tier,
            "dw_bft_note": (
                f"DW-BFT L4.1: {previous_consensus_mode} → {new_consensus_mode} "
                f"trigger={trigger_event} "
                f"HHI: {hhi_pre:.1f} → {hhi_post:.1f} "
                f"tier={degradation_tier}"
            ),
        }
    )


# ─── BTCP §14.2 domain signal builder (typed sub-payload emission) ──────────

def build_btcp_domain_signal(
    subtype: str,
    entity_id,
    coherence_result: dict,
    signal_value: float,
    detail: Optional[dict] = None,
) -> dict:
    """Emit a BTCP §14.2 domain signal (R-SG-03, Wave 3 D).

    The BTCP-domain type (BEHAVIORAL_TRUTH, SHADOW_CHAIN, LIQUIDITY_OCEAN,
    CHAIN_RELIABILITY, BTCP_ESCROW_EVENT, BTCP_TIMEOUT, GENESIS_COMMITMENT)
    is carried as a TYPED SUB-PAYLOAD (``signal_subtype``) on its closest
    canonical-24 carrier — the registry-parity pattern this repo already
    uses for LIQUIDITY_OCEAN (core/extended/natural_liquidity.py). The
    canonical 24-type registry itself stays exactly 24.

    Route-failure signaling (top-10 remediation #8): CHAIN_RELIABILITY and
    BTCP_TIMEOUT now have a concrete, classifiable emission path.

    Fails closed on unknown subtypes (KeyError from classify_signal).
    """
    meta = classify_signal(subtype)
    carrier = SignalType[meta["carrier"]]
    return build_signal(
        entity_id=entity_id,
        signal_type=carrier,
        coherence_result=coherence_result,
        signal_value=signal_value,
        ci_95_lower=max(0.0, signal_value - 0.10),
        ci_95_upper=min(1.0, signal_value + 0.10),
        extra={
            "signal_subtype":  meta["type_name"],
            "btcp_domain":     True,
            "domain":          meta["domain"],
            "severity":        meta["severity"],
            "emitter_layer":   meta["emitter_layer"],
            **(detail or {}),
        },
    )


# ─── Self-test ────────────────────────────────────────────────────────────────

if __name__ == "__main__":
    entity   = b'\xab' * 32
    coherence = {
        "C": 0.72, "theta": 0.62, "margin": 0.10,
        "emits": True, "silence": False,
        "coherence_gap": 0, "limiting_plane": "anima",
        "trend": "RISING", "eta_blocks": 0,
        "plane_breakdown": {"phi_adj": 0.72, "m_adj": 0.68, "sigma": 0.25, "k_plane": 0.10, "anima": 0.10},
        "bootstrap_planes": {"sigma_bootstrap": True, "k_bootstrap": True, "anima_bootstrap": True},
        "weights": {"alpha": 0.20, "beta": 0.30, "gamma": 0.20, "delta": 0.15, "epsilon": 0.15},
    }
    silence_coh = {**coherence, "C": 0.40, "emits": False, "silence": True,
                   "coherence_gap": 0.22, "margin": -0.22}

    # Test all 19 signal types
    sigs = [
        build_valuation(entity, coherence, 0.72, 0.65, 0.79),
        build_silence(entity, silence_coh),
        build_manipulation_alert(entity, coherence, {"mf_score": 0.55, "primary_type": "WASH_TRADING", "detected_types": [], "components": {}}),
        build_genesis(entity, coherence, 1000, "0xDEPLOYER", 0.80, 0.0, 0),
        build_resurrection(entity, coherence, 90.0, 0.75, 0.82, 1234567),
        build_fork_divergence(entity, coherence, 0.65, "0xA", "0xB", 500, 0.45),
        build_trajectory(entity, coherence, 0.80, "RISING", 0.65, 300, "growth_archetype", 50.0, 0.12),
        build_negative_space(entity, coherence, 1000, 0.70, 0.65, "Unexpectedly quiet before governance vote"),
        build_phase_transition(entity, coherence, "NORMAL", "ELEVATED", 0.78, "VALIDATOR_SLASH", "ELEVATED", "STRESS_EXPRESSION"),
        build_systemic_risk(entity, coherence, 0.62, ["HIGH_CORRELATION", "HHI_ELEVATED"], 2800.0, 0.72, 3),
        build_liquidity_health(entity, coherence, 0.09, 0.3, 0.4, 0.2, 0.09, "0xAAVE"),
        build_governance_signal(entity, coherence, 0.73, True, 1800.0, 12, True, False, "PROP-42"),
        build_cross_chain_coherence(entity, coherence, 0.68, [1, 137, 42161], "arbitrum", "ethereum", 0.15, {"arb": 0.75, "eth": 0.60}),
        build_stablecoin_health(entity, coherence, 0.92, 0.05, 1.35, 0.08, "0xUSDC"),
        build_mev_exposure(entity, coherence, 0.42, 0.025, ["SANDWICH"], 0.08, True, 5),
        build_institutional_bhv(entity, coherence, 0.78, 0.65, True, False, 0.82),
        build_regulatory_bhv(entity, coherence, 0.71, "EU", 0.05, 0.22, "COMPLIANT", False, "ALLOW", "proof-001"),
        build_ecosystem_health(entity, coherence, 0.74, 48, 15200, 0.68, 0.72, "ARBITRUM_ECOSYSTEM"),
        build_bootstrap(entity, coherence, 0.34, 100, 34, {"sigma": False, "k": False, "anima": False}, 660),
    ]

    # Extended signals (types 19–23 from whitepaper original Section 11)
    sigs += [
        build_sovereign_behavioral(entity, coherence, 0.62, "EU", 0.70, 0.45, 0.38, 1.22, "MEDIUM"),
        build_energy_participation(entity, coherence, 0.75, 512, 0.82, 0.71, 0.60, 0.12),
        build_biological_capital(entity, coherence, 0.68, "AMAZON_BASIN", 12, 0.72, 0.65, 0.70, 0.67),
        build_btcp_route(entity, coherence, 0.88, 0.92, [1, 137, 42161], "ethereum→arbitrum", 0.08, True, 0.0035, "PRE_VOLATILITY"),
        build_consensus_adaptation(entity, coherence, 0.79, "STANDARD_BFT", "DIVERSITY_WEIGHTED_BFT", "HHI_THRESHOLD_CROSSED", 0.85, 3200.0, 1800.0, 1),
    ]

    assert len(sigs) == 24, f"Expected 24 signals, got {len(sigs)}"

    for sig in sigs:
        assert "signal_id"       in sig, f"Missing signal_id in {sig['signal_type']}"
        assert "ci_95"           in sig, f"Missing CI_95 in {sig['signal_type']}"
        assert "biological_time" in sig, f"Missing BRT in {sig['signal_type']}"
        assert "coherence"       in sig, f"Missing coherence in {sig['signal_type']}"
        # Provenance chain must be non-empty and carry factual source records
        assert isinstance(sig["provenance"], list) and sig["provenance"], \
            f"Empty provenance in {sig['signal_type']}"
        sources = {p["source"] for p in sig["provenance"]}
        assert "coherence_engine" in sources, f"Missing coherence provenance in {sig['signal_type']}"
        assert "brt" in sources, f"Missing BRT provenance in {sig['signal_type']}"
        assert "genomic_signature" in sources, f"Missing genomic provenance in {sig['signal_type']}"
        assert sig["biological_time"].get("brt_source") == "CLOCK_FALLBACK", \
            "no observations supplied → BRT must be honestly labeled CLOCK_FALLBACK"

    # Caller-supplied provenance (behavioral hash ids) is carried first
    sig_prov = build_signal(
        entity, SignalType.VALUATION, coherence,
        signal_value=0.72, ci_95_lower=0.67, ci_95_upper=0.77,
        provenance=["bh_abc123", {"source": "rpc", "chain_id": 1, "block": 18000000}],
    )
    assert sig_prov["provenance"][0]["bh_id"] == "bh_abc123"
    assert sig_prov["provenance"][1]["source"] == "rpc"
    assert len(sig_prov["provenance"]) == 5  # 2 caller + 3 auto records

    # Observed-timestamp BRT path now actually resolves (broken import fixed)
    import random as _random
    _rng = _random.Random(99)
    _midnight = 1700000000 - (1700000000 % 86400)
    _obs = [_midnight + d * 86400 + _rng.uniform(32400, 61200)
            for d in range(30) for _ in range(3)]
    sig_obs = build_signal(
        entity, SignalType.VALUATION, coherence,
        signal_value=0.72, ci_95_lower=0.67, ci_95_upper=0.77,
        observed_timestamps=_obs,
    )
    assert sig_obs["biological_time"]["brt_source"] == "OBSERVED", \
        "observed-timestamp BRT derivation must resolve (import fixed)"
    assert sig_obs["biological_time"]["circadian_strength"] > 0.20
    brt_prov = [p for p in sig_obs["provenance"] if p["source"] == "brt"][0]
    assert brt_prov["data_source"] == "OBSERVED"
    assert brt_prov["observations"] == len(_obs)

    print("All 24 signal types:")
    for s in sigs:
        star = " *" if s["signal_type_id"] >= 19 else ""
        print(f"  [{s['signal_type_id']:2d}] {s['signal_type']:28s} C={s['coherence']:.2f}  CI=[{s['ci_95'][0]:.2f},{s['ci_95'][1]:.2f}]"
              f"  prov={len(s['provenance'])} records{star}")

    print(f"\n  * = extended signals (whitepaper Section 11 original — L6–L9 planes)")
    # BTCP §14.2 domain signals (typed sub-payloads on canonical carriers)
    btcp_domain = [
        build_btcp_domain_signal(sub, entity, coherence, 0.7)
        for sub in BTCP_DOMAIN_SIGNALS
    ]
    assert len(btcp_domain) == 7
    for sig, sub in zip(btcp_domain, BTCP_DOMAIN_SIGNALS):
        assert sig["signal_subtype"] == sub
        assert sig["signal_type_id"] < 24, "must ride a canonical-24 carrier"
        assert classify_signal(sub)["domain"] == "btcp_14_2"
    try:
        build_btcp_domain_signal("NOT_A_TYPE", entity, coherence, 0.7)
        raise AssertionError("unknown subtype must fail closed")
    except KeyError:
        pass

    print(f"\nPHASE 15 PASS — all {len(sigs)}/24 signal types built with full provenance")
    print(f"                + {len(btcp_domain)}/7 BTCP §14.2 domain subtypes classifiable")
