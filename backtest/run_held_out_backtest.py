#!/usr/bin/env python3
"""
TRION Protocol — Held-Out (Non-Circular) Backtest
===================================================

Audit finding #26: "The '100% Recall' Backtest Is Methodologically Circular"

The original `backtest/run_backtest.py` tested 30 KNOWN exploit addresses
against HARDCODED manipulation signatures. This is equivalent to testing
a virus scanner against the exact virus samples it was trained on.

This held-out backtest splits the dataset into:
  - TRAIN set (20 exploits, 67%): used to calibrate the flag threshold
  - TEST set  (10 exploits, 33%): held out — the threshold is FROZEN before
    any TEST entity is evaluated

The backtest reports precision/recall/F1 separately for TRAIN and TEST.
Only the TEST metrics are a valid measure of generalization. The TRAIN
metrics are reported for transparency but should not be cited as
evidence of detection capability.

Remediation v2 (Task 13-b): the original script required a live Oracle
API and had never been executed (its HTTP calls returned unreachable
defaults). It now scores entities through the offline behavioral replay
engine (backtest/replay_engine.py → core/ coherence pipeline), and the
flag rule is `C(t) < θ_calibrated` (Youden's J on TRAIN ONLY), with
silence reported separately.

Statistical methodology:
  - Wilson score 95% confidence intervals on TEST metrics
  - Bootstrap resampling (n=1000) for separation delta CI
  - Cohen's d effect size for attacker vs control separation

Usage:
    python3 backtest/run_held_out_backtest.py

Output:
    backtest/results/held_out_report.json
    backtest/results/held_out_summary.txt
"""
from __future__ import annotations

import hashlib
import json
import math
import os
import random
import statistics
import sys
from datetime import datetime, timezone
from typing import List, Tuple

HERE = os.path.dirname(os.path.abspath(__file__))
DATASET_PATH = os.path.join(HERE, "exploit_dataset.json")
RESULTS_DIR = os.path.join(HERE, "results")
os.makedirs(RESULTS_DIR, exist_ok=True)

# ── Dual-mode import: package (pytest / -m) or direct script execution ────────
try:
    from backtest.replay_engine import score_record
except ImportError:
    sys.path.append(HERE) if HERE not in sys.path else None
    from replay_engine import score_record

# ── Configuration ──────────────────────────────────────────────────────────────

# Fixed seed for reproducibility — the split MUST be deterministic so
# reviewers can verify that no TEST address leaked into TRAIN.
RANDOM_SEED = 42

# 67/33 train/test split
TRAIN_FRACTION = 0.67

# Youden's J calibration grid (same grid as run_backtest.py v2).
THETA_GRID = [round(0.30 + 0.01 * i, 2) for i in range(56)]   # 0.30 .. 0.85


# ── Statistical helpers ────────────────────────────────────────────────────────

def wilson_ci(successes: int, total: int, z: float = 1.96) -> Tuple[float, float]:
    """95% Wilson score confidence interval for a binomial proportion."""
    if total == 0:
        return (0.0, 1.0)
    p = successes / total
    denom = 1 + z * z / total
    center = (p + z * z / (2 * total)) / denom
    margin = (z / denom) * math.sqrt(p * (1 - p) / total + z * z / (4 * total * total))
    return (max(0.0, center - margin), min(1.0, center + margin))


def cohen_d(group_a: List[float], group_b: List[float]) -> float:
    """Cohen's d effect size between two groups."""
    if len(group_a) < 2 or len(group_b) < 2:
        return 0.0
    mean_diff = statistics.mean(group_a) - statistics.mean(group_b)
    pooled_std = math.sqrt(
        ((len(group_a) - 1) * statistics.variance(group_a) +
         (len(group_b) - 1) * statistics.variance(group_b)) /
        (len(group_a) + len(group_b) - 2)
    )
    if pooled_std == 0:
        return 0.0
    return mean_diff / pooled_std


def bootstrap_ci(
    samples_a: List[float],
    samples_b: List[float],
    n_resamples: int = 1000,
    seed: int = RANDOM_SEED,
) -> Tuple[float, float]:
    """Bootstrap 95% CI for the difference of means (a - b)."""
    rng = random.Random(seed)
    if not samples_a or not samples_b:
        return (0.0, 0.0)
    diffs = []
    for _ in range(n_resamples):
        a_sample = [rng.choice(samples_a) for _ in range(len(samples_a))]
        b_sample = [rng.choice(samples_b) for _ in range(len(samples_b))]
        diffs.append(statistics.mean(a_sample) - statistics.mean(b_sample))
    diffs.sort()
    return (diffs[25], diffs[975])  # 2.5th and 97.5th percentiles


# ── Dataset loading and splitting ──────────────────────────────────────────────

def load_dataset() -> dict:
    with open(DATASET_PATH) as f:
        return json.load(f)


def split_dataset(exploits: List[dict]) -> Tuple[List[dict], List[dict]]:
    """Deterministically split the exploit dataset into TRAIN and TEST."""
    rng = random.Random(RANDOM_SEED)
    shuffled = list(exploits)
    rng.shuffle(shuffled)
    split_idx = int(len(shuffled) * TRAIN_FRACTION)
    return shuffled[:split_idx], shuffled[split_idx:]


# ── Threshold calibration (TRAIN ONLY) ─────────────────────────────────────────

def calibrate_threshold_on_train(train_attackers: List[float],
                                 controls: List[float]) -> dict:
    """
    Youden's J (TPR − FPR) maximization over the fixed grid, using ONLY the
    TRAIN attacker coherences and the control cohort. The chosen θ is frozen
    before any TEST entity is scored. Ties resolve to the lowest maximizing
    grid value (deterministic).
    """
    best_theta, best_j = THETA_GRID[0], -1.0
    curve = []
    for theta in THETA_GRID:
        tp = sum(1 for c in train_attackers if c < theta)
        fn = len(train_attackers) - tp
        fp = sum(1 for c in controls if c < theta)
        tn = len(controls) - fp
        tpr = tp / (tp + fn) if (tp + fn) else 0.0
        fpr = fp / (fp + tn) if (fp + tn) else 0.0
        j = tpr - fpr
        curve.append({"theta": theta, "tpr": round(tpr, 4),
                      "fpr": round(fpr, 4), "youdens_j": round(j, 4)})
        if j > best_j:
            best_j, best_theta = j, theta
    return {"theta": best_theta, "youdens_j": round(best_j, 4), "curve": curve}


# ── Backtest runner ────────────────────────────────────────────────────────────

def run_held_out_backtest() -> dict:
    """Run the held-out backtest. Returns a structured report."""
    data = load_dataset()
    exploits = data["exploits"]
    controls = data["controls"]
    train, test = split_dataset(exploits)

    # ── Score TRAIN attackers and the control cohort (replay engine) ──────────
    train_results = []
    for ex in train:
        sig = score_record(ex, "ATTACKER")
        train_results.append({
            "exploit_id":     ex["id"],
            "name":           ex["name"],
            "amount_usd":     ex["amount_usd"],
            "coherence":      round(float(sig["coherence"]), 6),
            "mf_score":       round(float(sig.get("mf_score", 0.0)), 6),
            "mf_primary":     sig.get("mf_primary"),
            "threshold_dyn":  round(float(sig.get("threshold", 0.55)), 6),
            "silence":        bool(sig.get("silence", False)),
            "is_attacker":    True,
        })

    control_results = []
    for ctrl in controls:
        sig = score_record(ctrl, "CONTROL")
        control_results.append({
            "control_id":     ctrl["id"],
            "name":           ctrl["name"],
            "coherence":      round(float(sig["coherence"]), 6),
            "mf_score":       round(float(sig.get("mf_score", 0.0)), 6),
            "threshold_dyn":  round(float(sig.get("threshold", 0.55)), 6),
            "silence":        bool(sig.get("silence", False)),
            "is_attacker":    False,
        })

    train_coherences = [r["coherence"] for r in train_results]
    control_coherences = [r["coherence"] for r in control_results]

    # ── Calibrate θ on TRAIN ONLY, then freeze ────────────────────────────────
    cal = calibrate_threshold_on_train(train_coherences, control_coherences)
    theta_frozen = cal["theta"]

    # ── Score TEST attackers with the FROZEN threshold ────────────────────────
    test_results = []
    for ex in test:
        sig = score_record(ex, "ATTACKER")
        c = float(sig["coherence"])
        test_results.append({
            "exploit_id":     ex["id"],
            "name":           ex["name"],
            "amount_usd":     ex["amount_usd"],
            "coherence":      round(c, 6),
            "mf_score":       round(float(sig.get("mf_score", 0.0)), 6),
            "mf_primary":     sig.get("mf_primary"),
            "threshold_dyn":  round(float(sig.get("threshold", 0.55)), 6),
            "silence":        bool(sig.get("silence", False)),
            "flagged":        c < theta_frozen,
            "is_attacker":    True,
        })
    test_coherences = [r["coherence"] for r in test_results]

    # Confusion under the frozen threshold.
    def _confusion(att: List[float]):
        tp = sum(1 for c in att if c < theta_frozen)
        fn = len(att) - tp
        fp = sum(1 for c in control_coherences if c < theta_frozen)
        tn = len(control_coherences) - fp
        prec = tp / (tp + fp) if (tp + fp) else 0.0
        rec = tp / (tp + fn) if (tp + fn) else 0.0
        f1 = 2 * prec * rec / (prec + rec) if (prec + rec) else 0.0
        fpr = fp / (fp + tn) if (fp + tn) else 0.0
        return {"TP": tp, "FP": fp, "TN": tn, "FN": fn,
                "precision": round(prec, 4), "recall": round(rec, 4),
                "f1": round(f1, 4), "false_positive_rate": round(fpr, 4)}

    train_conf = _confusion(train_coherences)
    test_conf = _confusion(test_coherences)

    train_tp, train_fn = train_conf["TP"], train_conf["FN"]
    test_tp, test_fn = test_conf["TP"], test_conf["FN"]
    train_recall = train_conf["recall"]
    test_recall = test_conf["recall"]

    # Wilson CIs
    train_ci = wilson_ci(train_tp, len(train_results))
    test_ci = wilson_ci(test_tp, len(test_results))

    train_mean = statistics.mean(train_coherences) if train_coherences else 0.0
    test_mean = statistics.mean(test_coherences) if test_coherences else 0.0

    # Cohen's d — control cohort vs attackers (real control scores; the v0
    # script compared against a synthetic gauss(0.5) baseline). Positive d =
    # controls score higher than attackers (separation in the expected
    # direction), matching the sign convention of separation_delta.
    train_d = cohen_d(control_coherences, train_coherences)
    test_d = cohen_d(control_coherences, test_coherences)

    # Bootstrap CI for separation delta (control mean − attacker mean).
    train_sep_ci = bootstrap_ci(control_coherences, train_coherences)
    test_sep_ci = bootstrap_ci(control_coherences, test_coherences)
    separation_train = statistics.mean(control_coherences) - train_mean
    separation_test = statistics.mean(control_coherences) - test_mean

    return {
        "metadata": {
            "generated_at":       datetime.now(timezone.utc).isoformat(),
            "methodology":        "held_out_split",
            "train_fraction":     TRAIN_FRACTION,
            "random_seed":        RANDOM_SEED,
            "signal_path": (
                "Offline behavioral replay (backtest/replay_engine.py) "
                "scored through the core/ coherence pipeline. The v0 script "
                "required a live Oracle API and had never been executed."),
            "total_exploits":     len(exploits),
            "train_count":        len(train),
            "test_count":         len(test),
            "controls_count":     len(controls),
            "audit_finding":      "#26 — original backtest methodologically circular",
            "threshold_calibration": {
                "method": "youdens_j",
                "description": (
                    "θ selected by maximizing Youden's J on TRAIN attacker "
                    "coherences + control cohort ONLY, then frozen before "
                    "TEST evaluation. Ties resolve to the lowest maximizing "
                    "grid value."),
                "grid": [THETA_GRID[0], THETA_GRID[-1], 0.01],
                "theta_frozen": theta_frozen,
                "youdens_j": cal["youdens_j"],
                "calibration_curve": cal["curve"],
            },
        },
        "train_metrics": {
            "exploits_evaluated": len(train_results),
            "true_positives":     train_tp,
            "false_negatives":    train_fn,
            "recall":             round(train_recall, 4),
            "recall_ci_95":       [round(train_ci[0], 4), round(train_ci[1], 4)],
            "mean_coherence":     round(train_mean, 4),
            "confusion":          train_conf,
            "cohen_d_vs_control": round(train_d, 4),
            "cohen_d_sign":        "positive = control cohort higher than attackers",
            "separation_delta":   round(separation_train, 4),
            "separation_ci_95":   [round(train_sep_ci[0], 4), round(train_sep_ci[1], 4)],
            "disclosure":         "TRAIN metrics are NOT a valid measure of generalization. "
                                  "These exploits informed threshold calibration.",
        },
        "test_metrics": {
            "exploits_evaluated": len(test_results),
            "true_positives":     test_tp,
            "false_negatives":    test_fn,
            "recall":             round(test_recall, 4),
            "recall_ci_95":       [round(test_ci[0], 4), round(test_ci[1], 4)],
            "mean_coherence":     round(test_mean, 4),
            "confusion":          test_conf,
            "cohen_d_vs_control": round(test_d, 4),
            "cohen_d_sign":        "positive = control cohort higher than attackers",
            "separation_delta":   round(separation_test, 4),
            "separation_ci_95":   [round(test_sep_ci[0], 4), round(test_sep_ci[1], 4)],
            "theta_used":         theta_frozen,
            "disclosure":         "TEST metrics are the only valid measure of generalization. "
                                  "These exploits were HELD OUT: θ was frozen before they "
                                  "were scored. Silence (dynamic-Θ gate) is reported "
                                  "separately and does not feed the flag.",
        },
        "control_metrics": {
            "count":              len(control_results),
            "mean_coherence":     round(statistics.mean(control_coherences), 4),
            "min_coherence":      round(min(control_coherences), 4),
            "max_coherence":      round(max(control_coherences), 4),
            "in_silence":         sum(1 for c in control_results if c["silence"]),
            "note":               "Controls are a fixed reference cohort (scored identically "
                                  "in TRAIN and TEST phases; no control informed attacker "
                                  "labels).",
        },
        "train_exploits":  [r["exploit_id"] for r in train_results],
        "test_exploits":   [r["exploit_id"] for r in test_results],
        "test_results":    test_results,
        "interpretation": (
            f"Held-out recall: {test_recall:.1%} (95% CI: {test_ci[0]:.1%}–{test_ci[1]:.1%}) "
            f"at frozen θ={theta_frozen:.2f} (Youden's J on TRAIN only). "
            f"Cohen's d vs control cohort: {test_d:.2f}. "
            f"Separation delta (control − attacker): {separation_test:+.3f} "
            f"(bootstrap 95% CI: [{test_sep_ci[0]:.3f}, {test_sep_ci[1]:.3f}]). "
            f"Note: small TEST sample size ({len(test_results)}) produces wide CIs. "
            f"Expand the held-out set in future runs for tighter bounds. "
            f"Flag rule is C(t) < θ (calibrated); silence is reported separately."
        ),
    }


# ── Main ───────────────────────────────────────────────────────────────────────

def main():
    report = run_held_out_backtest()

    # Save JSON report
    report_path = os.path.join(RESULTS_DIR, "held_out_report.json")
    with open(report_path, "w") as f:
        json.dump(report, f, indent=2)
    print(f"Report saved to: {report_path}")

    # Print summary
    print("\n" + "=" * 70)
    print("HELD-OUT (NON-CIRCULAR) BACKTEST RESULTS")
    print("=" * 70)
    print(f"\nMethodology: {report['metadata']['methodology']}")
    print(f"Split: {report['metadata']['train_fraction']:.0%}/{1 - report['metadata']['train_fraction']:.0%} "
          f"train/test (seed={report['metadata']['random_seed']})")
    theta = report['metadata']['threshold_calibration']['theta_frozen']
    print(f"Threshold: θ={theta:.2f} frozen from TRAIN (Youden's J, "
          f"J={report['metadata']['threshold_calibration']['youdens_j']:.4f})")
    print(f"\nTRAIN ({report['train_metrics']['exploits_evaluated']} exploits) — NOT valid for generalization:")
    print(f"  Recall:     {report['train_metrics']['recall']:.1%} "
          f"(95% CI: {report['train_metrics']['recall_ci_95'][0]:.1%}–{report['train_metrics']['recall_ci_95'][1]:.1%})")
    print(f"  Cohen's d:  {report['train_metrics']['cohen_d_vs_control']:.2f}")
    print(f"  Separation: {report['train_metrics']['separation_delta']:+.4f}")
    print(f"\nTEST ({report['test_metrics']['exploits_evaluated']} exploits) — VALID for generalization:")
    print(f"  Recall:     {report['test_metrics']['recall']:.1%} "
          f"(95% CI: {report['test_metrics']['recall_ci_95'][0]:.1%}–{report['test_metrics']['recall_ci_95'][1]:.1%})")
    print(f"  Cohen's d:  {report['test_metrics']['cohen_d_vs_control']:.2f}")
    print(f"  Separation: {report['test_metrics']['separation_delta']:+.4f}")
    print(f"  Confusion:  {report['test_metrics']['confusion']}")
    print(f"\nControls: mean C={report['control_metrics']['mean_coherence']:.4f} "
          f"({report['control_metrics']['in_silence']}/{report['control_metrics']['count']} in SILENCE)")
    print(f"\nInterpretation:")
    print(f"  {report['interpretation']}")
    print("\n" + "=" * 70)

    # Save summary text
    summary_path = os.path.join(RESULTS_DIR, "held_out_summary.txt")
    with open(summary_path, "w") as f:
        f.write("TRION Protocol — Held-Out (Non-Circular) Backtest Summary\n")
        f.write("=" * 70 + "\n\n")
        f.write(f"Methodology: {report['metadata']['methodology']}\n")
        f.write(f"Split: {report['metadata']['train_fraction']:.0%}/{1 - report['metadata']['train_fraction']:.0%} "
                f"train/test (seed={report['metadata']['random_seed']})\n")
        f.write(f"Threshold: theta={theta:.2f} frozen from TRAIN (Youden's J)\n\n")
        f.write(f"TRAIN ({report['train_metrics']['exploits_evaluated']} exploits):\n")
        f.write(f"  Recall:     {report['train_metrics']['recall']:.1%}\n")
        f.write(f"  Cohen's d:  {report['train_metrics']['cohen_d_vs_control']:.2f}\n\n")
        f.write(f"TEST ({report['test_metrics']['exploits_evaluated']} exploits):\n")
        f.write(f"  Recall:     {report['test_metrics']['recall']:.1%}\n")
        f.write(f"  Cohen's d:  {report['test_metrics']['cohen_d_vs_control']:.2f}\n\n")
        f.write(f"Controls: mean C={report['control_metrics']['mean_coherence']:.4f}\n\n")
        f.write(f"Interpretation:\n  {report['interpretation']}\n")
    print(f"Summary saved to: {summary_path}")


if __name__ == "__main__":
    main()
