# TRION Protocol-Contract Intelligence — Implementation Report

**Date**: 2026-06-07  
**Author**: TRION Protocol Engine  
**Status**: COMPLETE — 75/75 tests passing, 7 routes live

---

## Problem Statement: The Many-to-One Identity Aggregation Problem

Standard TRION signal computation treats every `entity_id` as an independent behavioral identity. This breaks for DeFi protocol contracts — `uniswap`, `aave`, `compound` — because:

1. **Millions of callers** share a single `to_addr` in `bh_ledger`. All their transactions collapse into one entity.
2. **The Mental plane (M)** measures intent consistency over time for one actor. A contract that processes lending, borrowing, and flash-loan repayments in the same block has inherently incoherent intent signals.
3. **The result**: protocol contracts always produce `SILENCE` or near-zero C(t) — not because they are suspicious, but because the measurement model was built for wallets, not contracts.

**This module solves it** by decomposing protocol activity into (contract, caller) sub-entities, each with its own behavioral identity, and replacing the Mental plane with a distribution-coherence score.

---

## Architecture

```
bh_ledger.db  (SQLite — 93-byte BH per tx, written by Rust/Node indexers)
      │
      ▼
ProtocolSegmenter           segmentation.py
  GROUP BY to_addr, from_addr  →  SubEntity[](contract, caller, tx_count, event_type_counts, ...)
      │
      ▼
RoleClassifier              role_classifier.py
  event_type_counts  →  DeFiRole (7 canonical roles), confidence, archetype, risk_level
      │
      ▼
DistributionCoherenceEngine  distribution_coherence.py
  P_current vs P_baseline  →  DC(t) = 1 - JSD(P_current ‖ P_baseline)
      │
      ▼
ProtocolHealthEngine         protocol_health.py
  H(t) = 0.35·DC + 0.20·RoleCoh + 0.30·UserQual + 0.15·AttackSurf
      │
      ▼
Flask Blueprint              oracle_api/protocol_routes.py
  7 REST endpoints  →  Dashboard (Next.js /protocol page)
```

---

## Core Modules

### 1. `src/protocol/segmentation.py` — Sub-entity Extraction

Queries `bh_ledger` with `GROUP BY LOWER(to_addr), LOWER(from_addr)` to yield one `SubEntity` per (contract, caller) pair.

Each `SubEntity` carries:
- `tx_count` — transaction volume
- `event_type_counts` — {SWAP: N, FLASH_LOAN: N, …}
- `magnitude_stats` — {mean, max, std, p95} of `magnitude_norm`
- `chains` — list of distinct `chain_label` values
- `first_seen` / `last_seen` — temporal range

Additionally provides `get_protocol_activity()` (bucketed event distribution for current window) and `get_global_activity()` (baseline across all entities).

**Cache**: 60-second thread-safe in-memory cache prevents redundant DB queries under high dashboard polling frequency.

### 2. `src/protocol/role_classifier.py` — DeFi Role Detection

Maps `event_type_counts` distribution to one of 7 canonical DeFi roles using weighted scoring against each role's characteristic fingerprint:

| Role | Fingerprint | Risk |
|------|------------|------|
| `LIQUIDITY_PROVIDER` | LIQUIDITY dominant, stable magnitude, low SWAP ratio | LOW |
| `BORROWER` | BORROW + STAKE cycles, low LIQUIDATE exposure | MEDIUM |
| `LIQUIDATOR` | LIQUIDATE spikes, FLASH_LOAN bursts, high magnitude | MEDIUM |
| `MEV_BOT` | MEV_CAPTURE dominant, ultra-high density, timing | HIGH |
| `ARBITRAGEUR` | SWAP + BRIDGE, consistent magnitude, moderate frequency | MEDIUM |
| `GOVERNANCE_ACTOR` | GOVERNANCE + PROPOSAL dominant, low tx count | LOW |
| `TRADER` | SWAP dominant, moderate frequency, varied magnitude | LOW |

Key design decisions:
- TRADER penalised when BRIDGE ratio is high (pure SWAP+BRIDGE → ARBITRAGEUR)
- ARBITRAGEUR score multiplied by `(1 - mev_ratio)` to prevent MEV bots from masquerading
- Confidence bounded [0, 1]; below 0.15 → UNKNOWN
- Each role maps to a TRION ANIMA archetype (Innocent, Outlaw, Jester, Hero, etc.)

### 3. `src/protocol/distribution_coherence.py` — Mental Plane Substitute

Replaces the standard Mental plane M(t) (intent consistency) with distribution stability:

```
DC(t) = 1 - JSD(P_current ‖ P_baseline)
```

Where:
- **P_current** = event-type distribution in the current 1-hour observation window
- **P_baseline** = rolling 30-day event-type distribution (expected normal behaviour)
- **JSD** = Jensen-Shannon divergence — symmetric, bounded [0, 1], always defined

| DC(t) | Interpretation |
|-------|---------------|
| ≥ 0.85 | STABLE — normal activity |
| 0.65–0.85 | DRIFTING — elevated monitoring |
| 0.40–0.65 | ANOMALOUS — significant divergence |
| < 0.40 | CRITICAL — possible exploit or governance attack |

**Attack detection formula**:
```
attack_signal = flash_ratio × 0.45 + liquidate_ratio × 0.30 + mev_ratio × 0.25
attack_probability = attack_signal + jsd × 0.40
```

A flash-loan exploit typically drives `flash_ratio > 0.6` and `jsd > 0.8`, yielding `attack_probability > 0.6`.

### 4. `src/protocol/protocol_health.py` — Aggregate Health Score

```
H(t) = 0.35·DC(t) + 0.20·RoleCoherence(t) + 0.30·UserQuality(t) + 0.15·AttackSurface(t)
```

| Component | Weight | Definition |
|-----------|--------|-----------|
| `DC(t)` | 35% | Distribution coherence from JSD engine |
| `RoleCoherence` | 20% | Shannon entropy of role mix (diverse-but-stable protocols score highest) |
| `UserQuality` | 30% | Mean confidence of top-N caller role classifications |
| `AttackSurface` | 15% | `1 - attack_probability` |

**Grade mapping**: A (≥0.80) · B (≥0.65) · C (≥0.50) · D (≥0.35) · F (<0.35)

The H(t) score lives on the same [0, 1] scale as C(t) and can be compared directly against Θ(t).

---

## API Blueprint — 7 Endpoints

All routes registered under `protocol_bp` in `oracle_api/app.py` via the existing blueprint pattern.

| Method | Route | Description |
|--------|-------|-------------|
| `GET` | `/api/v1/protocol/<address>/health` | Aggregate H(t), grade, 4-component breakdown |
| `GET` | `/api/v1/protocol/<address>/users` | Ranked (contract, caller) list with roles |
| `GET` | `/api/v1/protocol/<address>/roles` | Role distribution + risk concentration |
| `GET` | `/api/v1/protocol/<address>/attack-surface` | Threat level, anomaly events, high-risk callers |
| `GET` | `/api/v1/protocol/<address>/distribution` | JSD, DC(t), current vs baseline event distribution |
| `GET` | `/api/v1/protocol/<address>/sub-entities` | Raw (contract, caller) pairs with statistics |
| `GET` | `/api/v1/protocol/supported-roles` | Role taxonomy reference (7 roles, archetypes, risk levels) |

**Query parameters**: `top_n`, `limit`, `window_seconds`, `role` (filter), `risk` (filter)

### Live API Verification

```
GET /api/v1/protocol/uniswap/health
{
  "health_score": 0.456325,
  "grade": "D",
  "sub_entity_count": 0,          ← uniswap not yet indexed by Rust L0 pipeline
  "components": {
    "distribution_coherence": 0.5,
    "role_coherence": 0.0,
    "user_quality": 0.5,
    "attack_surface": 0.8755
  },
  "recommendations": [
    "Monitor: Event distribution drifting from baseline...",
    "Insufficient user data in bh_ledger — try monitoring at individual wallet level"
  ]
}

GET /api/v1/protocol/supported-roles → 7 roles, status: ok
GET /api/v1/protocol/uniswap/attack-surface → threat: MEDIUM, attack_prob: 0.1245
GET /api/v1/protocol/uniswap/distribution → dc: 0.5, jsd: 0.435
```

Grade D with 0 sub-entities is expected: Uniswap's indexed transactions use the LP/pool address as `entity_id`, not the router address. Once the Rust indexers write (router → caller) pairs into `bh_ledger`, H(t) will reflect real user distribution.

---

## Dashboard — `/protocol` Page

Added to `dashboard/src/app/protocol/page.tsx`:

- **Search bar** — accepts any contract address or ENS/protocol name; 4 preset protocols (Uniswap, Aave, Compound, 0G ExecutionGate)
- **H(t) score card** — large score + letter grade, refreshes every 30s
- **Threat level + Distribution Coherence** — inline summary with attack probability
- **H(t) component breakdown** — 4-bar score chart with weights (35/30/20/15)
- **Role distribution** — horizontal bar chart per DeFi role with colour coding
- **Anomalous event spikes** — spike-factor display vs baseline with red alerts
- **Event distribution vs baseline** — comparison bars; spikes highlighted in red
- **High-risk callers** — MEV bots and liquidators with confidence scores
- **Recommendations** — URGENT/ALERT/nominal guidance from health engine
- **Sub-entity table** — expandable rows; per-caller event breakdown, magnitude, chains, last_seen

Sidebar updated: `Protocol Intel` link (Building2 icon) added to the Intelligence section.

---

## Test Coverage — 75/75 Passed

```
tests/test_protocol_segmentation.py         14 tests
  - Helper pure functions (count_events, parse_floats, magnitude_stats)
  - SubEntity dataclass construction
  - Graceful DB-absent handling
  - Live smoke tests (get_sub_entities, get_protocol_activity, get_global_activity)
  - Cache hit verification

tests/test_protocol_role_classifier.py      20 tests
  - All 7 DeFi roles correctly identified from canonical event patterns
  - UNKNOWN for insufficient tx / empty counts / ambiguous signal
  - Confidence bounded [0, 1]
  - Archetype + risk_level mapping completeness
  - RoleResult evidence fields
  - Batch classification
  - DeFiRole enum integrity

tests/test_protocol_distribution_coherence.py  17 tests
  - JSD = 0 for identical distributions
  - JSD bounded [0, 1] across randomised inputs
  - JSD symmetric
  - DC(t) = 1 for identical, < 0.3 for maximally different
  - Engine: stable activity, attack detection, anomalous spike detection
  - Baseline rolling update
  - Interpretation string labels
  - Attack probability > 0.4 for FLASH_LOAN = 0.9

tests/test_protocol_health.py               24 tests
  - Grade A–F mapping (10 parametrised cases)
  - RoleCoherence entropy bounded, single-role, uniform distribution
  - UserQuality bounded for empty + multi-entity input
  - Recommendations: critical DC, high attack prob, high MEV, low data, nominal
  - Component weights sum to 1.0
  - Full compute() smoke test: bounded score, correct grade, all 4 component keys
```

---

## Key Design Principles

1. **Non-destructive**: zero changes to `oracle_api/app.py` routing logic, `akashic/faiss_service.py`, or existing tests. Blueprint registration is a 6-line try/except block.

2. **Graceful degradation**: all functions return sensible defaults (`[]`, `{}`, `0.5`) when `bh_ledger.db` is absent or the contract has no indexed transactions.

3. **Scale-aware**: 60-second cache prevents DB saturation under dashboard polling. Sub-entity limit defaults to 50, maximum 500.

4. **Aligned with whitepaper**: H(t) occupies the same [0, 1] scale as C(t). DC(t) substitutes M(t) using the same Jensen-Shannon divergence that the ANIMA engine already uses for archetype distance.

5. **Forward-compatible**: once Rust indexers write per-caller transaction pairs (using `from_addr` = caller, `to_addr` = protocol contract), the full H(t) pipeline activates automatically — no code changes required.

---

## Files Delivered

| File | Purpose |
|------|---------|
| `src/protocol/__init__.py` | Package exports |
| `src/protocol/segmentation.py` | (contract, caller) extraction from bh_ledger |
| `src/protocol/role_classifier.py` | 7-role DeFi fingerprint classifier |
| `src/protocol/distribution_coherence.py` | JSD-based Mental plane substitute |
| `src/protocol/protocol_health.py` | H(t) aggregate health engine |
| `oracle_api/protocol_routes.py` | Flask Blueprint, 7 routes |
| `oracle_api/app.py` | +6 lines: blueprint registration |
| `dashboard/src/app/protocol/page.tsx` | Full protocol dashboard page |
| `dashboard/src/components/Sidebar.tsx` | +1 nav item: Protocol Intel |
| `dashboard/src/lib/api.ts` | +7 protocol endpoint helpers |
| `tests/test_protocol_segmentation.py` | 14 tests |
| `tests/test_protocol_role_classifier.py` | 20 tests |
| `tests/test_protocol_distribution_coherence.py` | 17 tests |
| `tests/test_protocol_health.py` | 24 tests |

**Total: 75/75 tests passing — 0 regressions against existing 328-test suite**
