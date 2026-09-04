# TRION Protocol -- Signal Types Specification

> **Reference:** TRION Whitepaper, Section 12 (Signal Catalog).
> This document enumerates all 24 canonical signal types emitted by a TRION chain.

## Scope
> **SUPERSEDED IN PART (S23 acronym); COUNT CONFIRMED CANONICAL (K4):** see WHITEPAPER_MD.txt §11 / BTCP_SPEC title — canonical resolution recorded in `docs/audit/CANONICAL_SPEC_MATRIX.md` (K4/K5). K5: **BTCP = Behavioral Transaction Continuity Protocol** (BTCP_SPEC governs; the S23 expansion “Behavioral Trusted Channel Protocol” is an error). K4: the canonical signal set is 24 = MD §11's 19 canonical + 5 V2 extended types — exactly what this registry and `core/master/signal_factory.py` implement (ids 0–23 dense, new types require a protocol fork); BTCP §14.2's 10 names are classifiable as typed sub-payloads on canonical carriers.


Every signal carries a mandatory envelope and trigger conditions. Signals are
selected per L0.5 (Signal Selection Principle) and emitted over the channels
defined in `communication_channels.md`.

---

## Mandatory Envelope

Every signal MUST include the following fields:

```
{
    signal_id      : string,            -- canonical name from this registry
    timestamp      : uint64,            -- epoch-precision
    chain_id       : bytes32,
    emitter_layer  : L0 | L1 | L2 | L3 | L4 | L5 | L6 | L7 | L8 | L9,
    beo_ids        : bytes9[],          -- affected behavioral entities
    confidence     : float in [0, 1],
    evidence_hash  : bytes32,           -- SHA3-256 of supporting observations
    severity       : info | advisory | warning | critical,
    expires_at     : uint64
}
```

---

## Signal Catalog (24 Types)

### S1 VALUATION

```
Trigger      : PR_scalar deviation > 0.20 from archetype centroid (L2.7)
Mandatory    : fair_value_estimate, confidence_interval, archetype_id
Severity     : info | advisory
Emitter      : L1
```

### S2 SILENCE

```
Trigger      : no candidate signal reduces entropy (L0.5 Delta_S < tau_select)
Mandatory    : window_id, entropy_before, entropy_after
Severity     : info
Emitter      : L0
```

### S3 MANIPULATION_ALERT

```
Trigger      : L1.2 fingerprint score r_Mk exceeds type-specific threshold
Mandatory    : manipulation_type (M1-M7), score, residue_vector, affected_BEOs
Severity     : warning | critical
Emitter      : L1
```

### S4 GENESIS

```
Trigger      : new archetype declared (L2.2) AND GC(t) > 0.95 (L2.3)
Mandatory    : archetype_id, beo_id, genesis_confidence, witness_count
Severity     : info
Emitter      : L2
```

### S5 RESURRECTION

```
Trigger      : L2.4 RR(Rk) > tau_revive
Mandatory    : dormancy_type (R1-R5), score, dormancy_duration, lineage_proof
Severity     : advisory | warning
Emitter      : L2
```

### S6 FORK_DIVERGENCE

```
Trigger      : L2.6 fork resolution completes with score delta > tau_tie
Mandatory    : fork_id, winner_score, loser_score, contested_BEOs
Severity     : warning | critical
Emitter      : L2
```

### S7 TRAJECTORY

```
Trigger      : L2.7 anomaly score TA > 1.5
Mandatory    : beo_id, anomaly_score, archetype_id, deviation_vector
Severity     : advisory | warning | critical
Emitter      : L2
```

### S8 NEGATIVE_SPACE

```
Trigger      : expected observation absent for > 3 * mean_inter_arrival (L1.3)
Mandatory    : expected_event_hash, last_seen_epoch, archetype_id
Severity     : advisory
Emitter      : L2
```

### S9 PHASE_TRANSITION

```
Trigger      : L1.4 TI drops below 0.90 OR L5.3 tier transition T1->T2
Mandatory    : from_state, to_state, trigger_metric, trigger_value
Severity     : warning | critical
Emitter      : L1 | L5
```

### S10 SYSTEMIC_RISK

```
Trigger      : L3.1 M(t) drop > 0.30 OR L4.8 HHI non-compliant OR L9 audit fail
Mandatory    : risk_category, contributing_layers, mitigation_required
Severity     : critical
Emitter      : L3 | L4 | L9
```

### S11 LIQUIDITY_HEALTH

```
Trigger      : L7.1 NL crosses tier boundary
Mandatory    : nl_score, sub_scores {LD, LO, LC, LS}, tier
Severity     : info | advisory | critical
Emitter      : L7
```

### S12 GOVERNANCE_SIGNAL

```
Trigger      : L4.9 slashing event OR L4.8 HHI warning OR L6.2 lunar proposal
Mandatory    : proposal_id (if applicable), slash_id (if applicable), affected_validators
Severity     : info | warning | critical
Emitter      : L4 | L6
```

### S13 CROSS_CHAIN_COHERENCE

```
Trigger      : L9.1 XSL crosses tier boundary OR bridge finality degrades
Mandatory    : xsl_score, bridge_ids, fs_min, tp_value
Severity     : info | advisory | critical
Emitter      : L9
```

### S14 STABLECOIN_HEALTH

```
Trigger      : P1 profile asset with peg deviation > 0.5% OR NL < 0.40
Mandatory    : asset_id, peg_ratio, nl_score, reserve_coverage
Severity     : advisory | warning | critical
Emitter      : L7 | L9
```

### S15 MEV_EXPOSURE

```
Trigger      : L1.2 M6 (MEV_EXTRACTION) score > 0.60
Mandatory    : mev_volume, extractors, victim_count, f4_f5_signature
Severity     : warning | critical
Emitter      : L1
```

### S16 INSTITUTIONAL_BHV

```
Trigger      : institutional actor (LP/validator) with C_source change > 0.20
Mandatory    : actor_id, old_credibility, new_credibility, behavioral_delta
Severity     : info | advisory
Emitter      : L3
```

### S17 REGULATORY_BHV

```
Trigger      : L8 compliance posture C < 0.55 OR regulatory framework change declared
Mandatory    : jurisdiction, framework_id, compliance_score, declared_change
Severity     : advisory | warning
Emitter      : L8
```

### S18 ECOSYSTEM_HEALTH

```
Trigger      : L0.6 F crosses tier boundary OR L6.1 BC crosses tier boundary
Mandatory    : fitness_score, bc_score, contributing_actors, trend
Severity     : info | advisory | critical
Emitter      : L0 | L6
```

### S19 BOOTSTRAP

```
Trigger      : L4.7 validator bootstrap OR L4.3 CRISPR action OR L3.7 maintenance entry/exit
Mandatory    : bootstrap_type, validator_id, genome_components_affected
Severity     : info | warning
Emitter      : L4 | L3
```

### S20 SOVEREIGN_BEHAVIORAL

```
Trigger      : L8 SBA crosses tier boundary
Mandatory    : sovereign_id (anonymized), sba_score, axis_scores, severity
Severity     : advisory | warning | critical
Emitter      : L8
```

### S21 ENERGY_PARTICIPATION

```
Trigger      : L7.2 EP crosses tier boundary
Mandatory    : ep_score, sub_scores {VC, PA, DC}, tier
Severity     : info | advisory
Emitter      : L7
```

### S22 BIOLOGICAL_CAPITAL

```
Trigger      : L6.1 BC crosses tier boundary
Mandatory    : bc_score, sub_scores {Flow, Resilience, Uniqueness, Interdependence}, tier
Severity     : info | advisory | critical
Emitter      : L6
```

### S23 BTCP_ROUTE

```
Trigger      : BTCP (Behavioral Trusted Channel Protocol) route established or broken
Mandatory    : route_id, peer_chain, latency, trust_score, route_state
Severity     : info | warning
Emitter      : L9
```

### S24 CONSENSUS_ADAPTATION

```
Trigger      : L5.1 Theta swing > 0.10 OR L3.5 reflexivity dampening activates
Mandatory    : old_threshold, new_threshold, trigger_metric, dampening_applied (bool)
Severity     : advisory
Emitter      : L5 | L3
```

---

## Emission Rules

```
1. Every signal MUST conform to the mandatory envelope.
2. Signal selection follows L0.5 (entropy-reducing signals only).
3. Signals cannot be retracted; supersession requires a new signal referencing
   the prior signal_id in the `evidence_hash`.
4. Critical signals MUST be broadcast on all 10 communication channels.
5. Info signals MAY be restricted to Direct Chain Reading and Off-Chain
   Intelligence channels.
```

## Invariants

- Exactly 24 signal types are defined; new types require a protocol fork.
- A signal without a valid `emitter_layer` MUST be rejected by the consensus boundary.
- `expires_at` MUST be `<= timestamp + 30 epochs` for non-critical signals,
  `<= timestamp + 90 epochs` for critical signals.

---

## Cross-References

- L0.5 -- Signal Selection Principle.
- `communication_channels.md` -- transport for emitted signals.
- `novel_primitives.md` -- P4 (Behavioral ZK Proofs) for confidential signal payloads.
- `falsifiability_registry.md` -- F7 tests signal selection entropy.
