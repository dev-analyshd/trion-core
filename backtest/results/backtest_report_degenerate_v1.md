# Degenerate Backtest v1 — Historical Record (Superseded)

**Status:** SUPERSEDED by `backtest_report.json` (Task 13-b remediation of DD findings C4 / 6.1).
**Do not delete this artifact.** It is preserved verbatim as the evidence base for the
due-diligence finding and for the remediation diff.

## What this artifact is

`backtest_report_degenerate_v1.json` (and its siblings `merkle_proof_degenerate_v1.json`,
`summary_degenerate_v1.txt`) are byte-for-byte copies of the artifacts committed at
`backtest/results/*` prior to remediation, generated on **2026-08-02T02:26:37Z**.

## Why it was degenerate (DD report §6.1, finding C4)

The committed run recorded:

| Metric                | Value | Meaning                                              |
|-----------------------|-------|------------------------------------------------------|
| `false_positive_rate` | 1.0   | every one of 10 clean controls was flagged           |
| `TN`                  | 0     | no clean entity was ever cleared                     |
| `avg_attacker_coherence` | 0.0 | the signal path returned empty/default signals       |
| `avg_control_coherence`  | 0.0 | same                                                  |
| `separation_delta`    | 0.0   | zero discriminative power between cohorts           |
| per-event `planes`    | `{}`  | five-plane payloads never populated                  |

Root cause (two compounding defects):

1. **Empty signal path.** `run_backtest.py` queried the live Oracle API
   (`/api/v1/signal/<id>`). For all 40 dataset entities FAISS held no behavioral
   sediment, so `_compute_signal` returned the typed `COLD_START / SILENCE`
   fallback (`coherence_score: 0.0`). Every entity therefore scored 0.0.
2. **Tautological detector.** `classify_result` computed
   `silence = not coherent` and then `trion_flagged = not coherent or silence`
   — logically equivalent to `trion_flagged = not coherent`. Combined with (1)
   this is an unconditional flag: TP=30, FP=10, TN=0, FN=0, "100% recall +
   100% false alarms", F1 85.71%, $3.315B "caught" by flagging everything.

The README quoted only the flattering half ("30/30 — 100% recall, F1 85.71%,
$3.315B") of this file. That is the integrity finding, not a prototype bug.

## Remediation (see `backtest_report.json` + `PROVENANCE.md`)

- The backtest now **replays synthetic event histories** (deterministic,
  record-parameterized) for each entity and scores them through the real
  `core/` coherence pipeline (`core.thermodynamics.entropy_engine`,
  `core.physical.manipulation_detector`, `core.master.coherence`).
  No cohort membership, address, or score is hardcoded into the scoring path;
  separation must emerge from behavioral features (burst timing, magnitude
  concentration, entropy collapse) via the MF detector and BH entropy engine.
- The detector flag is `C(t) < θ_calibrated` (Youden's-J-calibrated on labeled
  replay data — disclosed in report metadata). `silence` (engine dynamic
  threshold Θ(t)) is reported separately and no longer feeds the flag.
- The historical `onchain_proof.json` (which anchored these inflated metrics
  on-chain) is marked `"superseded": true` with an unaltered tx record.
