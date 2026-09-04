# TRION Protocol — API Reference

> **Scope note:** this file documents the primary endpoints, not the full
> surface — the live route set is **282 rules** (26 BTCP + 7 Continuum in the
> `btcp_continuum` blueprint plus app, cex, dashboard, price-feed, protocol,
> self-verification and zg blueprints). The route source of truth is the Flask
> `url_map` in `api/app.py`.

## Base URL
```
http://127.0.0.1:5000   # local dev (see DEPLOYMENT.md for deployment profiles)
```

## Authentication
Reads are public. When `TRION_API_KEY` is set, every write
(POST/PUT/PATCH/DELETE) requires a valid `X-API-Key` header — 401 when absent,
403 on mismatch (pinned by `tests/unit/test_api_truth_boundaries.py`). The
`/api/v1/btcp/sanctions` route additionally fails closed (503) when neither
`TRION_ADMIN_TOKEN` nor `TRION_API_KEY` is configured. Responses label
caller-supplied data (`witness_source`, `data_provenance`) — the API submits
evidence, never manufactures truth.

---

## Core Signal

### GET /api/v1/signal/{entity_id}
Returns the current coherence signal for an entity.

**Response:**
```json
{
  "signal_id": "uuid",
  "signal_type": "VALUATION | SILENCE | MANIPULATION_ALERT | ...",
  "entity_id": "0xabc...",
  "signal_value": 0.72,
  "ci_95": [0.67, 0.77],
  "coherence": 0.72,
  "threshold": 0.62,
  "margin": 0.10,
  "mf_score": 0.0,
  "silence": false,
  "silence_gap": 0,
  "coherence_trend": "STABLE",
  "eta_blocks": 0,
  "plane_breakdown": {
    "phi_adj": 0.72,
    "m_adj": 0.68,
    "sigma": 0.25,
    "k_plane": 0.10,
    "anima": 0.10
  },
  "limiting_plane": "anima",
  "bootstrap_phase": true,
  "biological_time": {
    "circadian_phase": 0.62,
    "ultradian_phase": 0.44,
    "lunar_phase": 0.18,
    "seasonal_phase": 0.34
  },
  "timestamp": 1746000000,
  "ttl_seconds": 3600
}
```

### GET /api/v1/signal/{entity_id}/history
Historical signal stream for an entity.

### POST /api/v1/signal/batch
Batch signal lookup.
```json
{ "entity_ids": ["uniswap", "aave", "0xabc..."] }
```

---

## Plane Endpoints

### GET /api/v1/planes/{entity_id}/all
All five plane scores in one response.

### GET /api/v1/planes/{entity_id}/physical
Physical plane Φ(t) with all 9 features (f1–f9).

### GET /api/v1/planes/{entity_id}/mental
Mental plane M(t) with prediction intervals and observer effect.

### GET /api/v1/planes/{entity_id}/spiritual
Spiritual plane Σ(t) with validator breakdown and HHI.

### GET /api/v1/planes/{entity_id}/conscious
Conscious plane K(t) with annotation summary.

### GET /api/v1/planes/{entity_id}/anima
ANIMA plane A(t) with PCR/HA/CA breakdown.

---

## Security

### POST /api/v1/security/check
Pre-execution security check. Checks CRISPR library.
```json
{ "tx_data": "0x..." }
```

### GET /api/v1/security/{entity_id}/mf
Manipulation fingerprint score for entity.

### GET /api/v1/security/crispr/library
All known attack signatures in the CRISPR library.

### GET /api/v1/security/{entity_id}/genomic
Current genomic key for entity (public portion only).

---

## Liquidity

### GET /api/v1/liquidity/{asset_address}
NL score for a liquidity pool.

**Response:**
```json
{
  "nl_score": 0.09,
  "ld_score": 0.22,
  "lo_score": 0.18,
  "lc_score": 0.65,
  "ls_score": 0.09,
  "alert": true,
  "limiting_factor": "LS",
  "recommendation": "DO_NOT_ROUTE",
  "coherence": 0.42,
  "timestamp": 1746000000
}
```

---

## BTCP Score

### POST /api/v1/btcp/score
Compute BTCP routing score.
```json
{
  "nl_score": 0.75,
  "gas_total": 5.0,
  "gas_99th": 50.0,
  "finality_conf": 0.95,
  "cc_coherence": 0.80,
  "beo_continuity": 0.90,
  "mf_score": 0.0
}
```

---

## Genesis

### GET /api/v1/genesis/{asset_id}
Genesis inference for new assets with no history.

---

## System

### GET /health
Health check.

### GET /api/v1/system/status
Full system status including all plane states.

### GET /api/v1/system/bootstrap
Bootstrap phase status with honest disclosure.

**Response:**
```json
{
  "bootstrap_active": true,
  "sigma_bootstrap_value": 0.25,
  "k_bootstrap_value": 0.10,
  "anima_bootstrap_value": 0.10,
  "anima_d_minimum": 10000,
  "current_depth": 1262330,
  "honest_disclosure": {
    "sigma": "Σ operating at bootstrap (0.25). Full validator network at mainnet.",
    "k":     "K operating at bootstrap (0.10). Annotation onboarding at mainnet.",
    "anima": "ANIMA activates per-entity when D >= 10,000."
  }
}
```

### GET /api/v1/system/falsifiability
All falsifiable predictions with current status.

---

## Signal Types

| Type | Trigger | MF Required |
|------|---------|-------------|
| VALUATION | C(t) ≥ Θ(t) | No |
| SILENCE | C(t) < Θ(t) | No |
| MANIPULATION_ALERT | MF ≥ 0.70 | Yes |
| GENESIS | New asset, no history | No |
| RESURRECTION | Re-activates after dormancy | No |
| FORK_DIVERGENCE | Post-fork behavioral split | No |
| TRAJECTORY | Trending signal | No |
| NEGATIVE_SPACE | Absence detection | No |
| PHASE_TRANSITION | Regime change | No |
| SYSTEMIC_RISK | HHI > DANGER | No |
| LIQUIDITY_HEALTH | NL < 0.30 | No |
| GOVERNANCE_SIGNAL | Governance activity | No |
| CROSS_CHAIN_COHERENCE | Multi-chain divergence | No |
| STABLECOIN_HEALTH | Depeg risk | No |
| MEV_EXPOSURE | MEV rate > threshold | No |
| INSTITUTIONAL_BHV | Institutional pattern | No |
| REGULATORY_BHV | Regulatory signal | No |
| ECOSYSTEM_HEALTH | Protocol ecosystem | No |
| BOOTSTRAP | Bootstrap state signal | No |
