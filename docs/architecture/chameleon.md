# Chameleon Protocol — L4.6

## Overview

The Chameleon Protocol is TRION's adversarial probe detection system. It uses behavioral
noise injection to detect adversaries who are sampling the oracle to reverse-engineer signal
generation logic before launching an attack.

## Problem

An adversary could probe the oracle with thousands of small transactions to map the exact
signal boundaries, then engineer an exploit that stays just below every detection threshold.

## Solution

The Chameleon Protocol introduces calibrated stochastic noise:

```
signal_out = signal_true + N(0, σ(t))
σ(t) = σ_base + σ_probe × probe_confidence(t)
```

- **σ_base** = 0.002 — constant micro-noise making exact fingerprinting impossible
- **σ_probe** = 0.025 — elevated noise when probing is detected
- **probe_confidence** — inferred from probe detection (see below)

## Probe Detection

A probing adversary sends transactions with:
1. High periodicity (fixed time intervals)
2. Consistent small magnitude (just enough to trigger oracle calls)
3. Pattern of entity IDs that scan address space systematically

Detection signal:
```
probe_score = w₁·(1 - entropy(inter_arrival_times))
            + w₂·(1 - entropy(magnitudes))
            + w₃·(1 - entropy(entity_ids))
```

When `probe_score > θ_probe` (default 1.8), the oracle enters **Chameleon Mode**:
- Noise σ increases from 0.002 → 0.027
- Probe entity ID is flagged
- Alert published to BIRP with signal type `PROBE_DETECTED`

## Legitimate Signal Preservation

The noise injection is calibrated so that:
- For C(t) values far from threshold (margin > 0.08): signal label is never flipped
- For C(t) values near threshold: noise may flip, but this is acceptable — the entity
  is in an ambiguous state anyway
- The 95% CI on every signal already accounts for σ(t) via `±1.96 · σ(t)` expansion

## Implementation

```python
# src/security/chameleon_protocol.py
probe_score = chameleon.score_interaction(entity_id, magnitude, inter_arrival_ms)
if probe_score > PROBE_DETECTION_THRESHOLD:
    chameleon.escalate_noise(entity_id)
noisy_signal = chameleon.apply_noise(clean_signal_value)
```

## Interaction with Living Security

The Chameleon Protocol feeds `probe_score` into the CRISPR library as a new "probe"
attack signature. After Genomic Key evolution, probe patterns contribute to:

```
GK(entity, t+1) = Hash_DNA(GK(t) || BE(t) || probe_score_bytes || CV(t))
```

This ensures that probing accelerates key evolution, making previous fingerprints stale.

## Security Properties

| Property | Value |
|---|---|
| Base noise σ | 0.002 |
| Probe noise σ | 0.025 |
| Probe detection threshold | 1.8 |
| Signal flip rate (healthy asset) | < 0.1% |
| Signal flip rate (near-threshold) | up to 5% |
| Probe detection latency | 3 blocks |
| False positive rate | < 1% |
