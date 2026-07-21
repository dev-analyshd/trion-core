#!/usr/bin/env python3
"""
TRION Protocol — Historical Exploit Backtest Engine
====================================================
Scores every known attacker address + control addresses through the live
Oracle API, computes precision/recall/F1, builds a Merkle tree of all results,
and saves the proof package for on-chain publication.

Usage:
    uv run python3 backtest/run_backtest.py

Output:
    backtest/results/backtest_report.json
    backtest/results/merkle_proof.json
    backtest/results/summary.txt
"""

import json
import time
import hashlib
import requests
import statistics
import os
import sys
from datetime import datetime, timezone

ORACLE_URL = os.environ.get("ORACLE_API_URL", "http://127.0.0.1:5000")
DATASET_PATH = os.path.join(os.path.dirname(__file__), "exploit_dataset.json")
RESULTS_DIR  = os.path.join(os.path.dirname(__file__), "results")
os.makedirs(RESULTS_DIR, exist_ok=True)

# ── Colour helpers ─────────────────────────────────────────────────────────────
RED   = "\033[91m"
GRN   = "\033[92m"
YEL   = "\033[93m"
BLU   = "\033[94m"
MAG   = "\033[95m"
CYN   = "\033[96m"
BOLD  = "\033[1m"
RST   = "\033[0m"

def query_signal(entity_id: str, retries: int = 3) -> dict:
    for attempt in range(retries):
        try:
            r = requests.get(f"{ORACLE_URL}/api/v1/signal/{entity_id}", timeout=15)
            if r.status_code == 200:
                return r.json()
        except Exception as e:
            if attempt == retries - 1:
                return {"error": str(e), "coherence": 0.0, "threshold": 0.55,
                        "coherent": False, "archetype": "UNKNOWN"}
        time.sleep(1.5)
    return {"error": "max_retries", "coherence": 0.0, "threshold": 0.55,
            "coherent": False, "archetype": "UNKNOWN"}

def sha256(data: str) -> str:
    return hashlib.sha256(data.encode()).hexdigest()

def build_merkle_tree(leaves: list[str]) -> tuple[str, list]:
    if not leaves:
        return sha256("empty"), []
    layer = [sha256(leaf) for leaf in leaves]
    proof_layers = [layer[:]]
    while len(layer) > 1:
        if len(layer) % 2 == 1:
            layer.append(layer[-1])
        layer = [sha256(layer[i] + layer[i+1]) for i in range(0, len(layer), 2)]
        proof_layers.append(layer[:])
    return layer[0], proof_layers

def classify_result(signal: dict, is_attacker: bool) -> dict:
    coherence  = signal.get("coherence", signal.get("coherence_score", 0.0)) or 0.0
    threshold  = signal.get("threshold", signal.get("dynamic_threshold", 0.55)) or 0.55
    coherent   = signal.get("coherent", False)
    archetype  = signal.get("archetype", "UNKNOWN")
    silence    = signal.get("silence", not coherent)
    planes     = signal.get("plane_breakdown", {})
    silence_gap = signal.get("silence_gap", max(0, threshold - coherence))

    trion_flagged = not coherent or silence  # TRION says: anomalous / silent

    tp = trion_flagged and is_attacker       # True Positive:  attacker caught
    fp = trion_flagged and not is_attacker   # False Positive: clean flagged
    tn = (not trion_flagged) and not is_attacker  # True Negative: clean cleared
    fn = (not trion_flagged) and is_attacker      # False Negative: attacker missed

    return {
        "coherence":       round(coherence, 6),
        "threshold":       round(threshold, 6),
        "coherent":        coherent,
        "trion_flagged":   trion_flagged,
        "silence_gap":     round(silence_gap, 6),
        "archetype":       archetype,
        "planes":          planes,
        "TP": tp, "FP": fp, "TN": tn, "FN": fn,
        "outcome": ("TP" if tp else "FP" if fp else "TN" if tn else "FN"),
        "signal_id":       signal.get("signal_id", ""),
        "genomic_sig":     signal.get("genomic_signature", "")[:32] + "...",
        "market_vol":      signal.get("market_volatility", 0.0),
    }

def main():
    print(f"\n{BOLD}{BLU}{'='*70}{RST}")
    print(f"{BOLD}{BLU}  TRION PROTOCOL — HISTORICAL EXPLOIT BACKTEST ENGINE{RST}")
    print(f"{BOLD}{BLU}{'='*70}{RST}\n")

    # ── Load dataset ───────────────────────────────────────────────────────────
    with open(DATASET_PATH) as f:
        dataset = json.load(f)

    exploits = dataset["exploits"]
    controls = dataset["controls"]

    print(f"{BOLD}Dataset:{RST} {len(exploits)} exploits | {len(controls)} controls")
    print(f"{BOLD}Total stolen:{RST} ${dataset['metadata']['total_stolen_usd']:,}\n")

    # Check Oracle API
    try:
        health = requests.get(f"{ORACLE_URL}/api/v1/health", timeout=5).json()
        print(f"{GRN}✓ Oracle API connected — {health.get('oracle','?')} on {health.get('network','?')}{RST}\n")
    except Exception as e:
        print(f"{RED}✗ Oracle API not reachable: {e}{RST}")
        sys.exit(1)

    results = []
    TP = FP = TN = FN = 0
    attacker_scores  = []
    control_scores   = []
    merkle_leaves    = []

    # ── Score all exploit addresses ────────────────────────────────────────────
    print(f"{BOLD}{'─'*70}{RST}")
    print(f"{BOLD}SCORING ATTACKER ADDRESSES ({len(exploits)}){RST}")
    print(f"{BOLD}{'─'*70}{RST}")

    for ex in exploits:
        addr  = ex["attacker_address"]
        print(f"\n  [{ex['id']}] {ex['name']} — ${ex['amount_usd']:,}")
        print(f"       Attacker: {addr}")
        print(f"       Type: {ex['exploit_type']} | Date: {ex['date']}")

        signal = query_signal(addr)
        r = classify_result(signal, is_attacker=True)

        # Status indicator
        outcome_color = GRN if r["outcome"] == "TP" else RED
        outcome_icon  = "🎯" if r["outcome"] == "TP" else "❌"
        print(f"       {outcome_color}{BOLD}→ C(t)={r['coherence']:.4f} | Θ(t)={r['threshold']:.4f} | "
              f"Flagged={r['trion_flagged']} | Archetype={r['archetype']} | {outcome_icon} {r['outcome']}{RST}")
        if r["planes"]:
            print(f"         Planes: Φ={r['planes'].get('physical',0):.3f} "
                  f"M={r['planes'].get('mental',0):.3f} "
                  f"Σ={r['planes'].get('spiritual',0):.3f} "
                  f"K={r['planes'].get('conscious',0):.3f} "
                  f"A={r['planes'].get('anima',0):.3f}")

        if r["TP"]: TP += 1
        elif r["FP"]: FP += 1
        elif r["TN"]: TN += 1
        elif r["FN"]: FN += 1

        attacker_scores.append(r["coherence"])

        row = {**ex, "signal": r, "entity_type": "ATTACKER"}
        results.append(row)

        # Merkle leaf: hash of (id + address + coherence + outcome)
        leaf = f"{ex['id']}:{addr}:{r['coherence']}:{r['outcome']}"
        merkle_leaves.append(leaf)

        time.sleep(0.3)

    # ── Score all control addresses ────────────────────────────────────────────
    print(f"\n{BOLD}{'─'*70}{RST}")
    print(f"{BOLD}SCORING CONTROL ADDRESSES ({len(controls)}){RST}")
    print(f"{BOLD}{'─'*70}{RST}")

    for ctrl in controls:
        addr = ctrl["address"]
        print(f"\n  [{ctrl['id']}] {ctrl['name']}")
        print(f"       Address: {addr}")

        signal = query_signal(addr)
        r = classify_result(signal, is_attacker=False)

        outcome_color = GRN if r["outcome"] == "TN" else RED
        outcome_icon  = "✓" if r["outcome"] == "TN" else "⚠"
        print(f"       {outcome_color}{BOLD}→ C(t)={r['coherence']:.4f} | Θ(t)={r['threshold']:.4f} | "
              f"Flagged={r['trion_flagged']} | Archetype={r['archetype']} | {outcome_icon} {r['outcome']}{RST}")

        if r["TP"]: TP += 1
        elif r["FP"]: FP += 1
        elif r["TN"]: TN += 1
        elif r["FN"]: FN += 1

        control_scores.append(r["coherence"])

        row = {**ctrl, "signal": r, "entity_type": "CONTROL"}
        results.append(row)

        leaf = f"{ctrl['id']}:{addr}:{r['coherence']}:{r['outcome']}"
        merkle_leaves.append(leaf)

        time.sleep(0.3)

    # ── Compute metrics ────────────────────────────────────────────────────────
    precision = TP / (TP + FP) if (TP + FP) > 0 else 0.0
    recall    = TP / (TP + FN) if (TP + FN) > 0 else 0.0
    f1        = 2 * precision * recall / (precision + recall) if (precision + recall) > 0 else 0.0
    accuracy  = (TP + TN) / (TP + FP + TN + FN) if (TP + FP + TN + FN) > 0 else 0.0
    fpr       = FP / (FP + TN) if (FP + TN) > 0 else 0.0
    fnr       = FN / (FN + TP) if (FN + TP) > 0 else 0.0

    avg_attacker = statistics.mean(attacker_scores) if attacker_scores else 0.0
    avg_control  = statistics.mean(control_scores)  if control_scores  else 0.0
    separation   = avg_control - avg_attacker  # positive = TRION separates classes

    # ── Build Merkle tree ──────────────────────────────────────────────────────
    merkle_root, proof_layers = build_merkle_tree(merkle_leaves)

    # ── Print summary ──────────────────────────────────────────────────────────
    print(f"\n{BOLD}{BLU}{'═'*70}{RST}")
    print(f"{BOLD}{BLU}  BACKTEST RESULTS SUMMARY{RST}")
    print(f"{BOLD}{BLU}{'═'*70}{RST}")

    print(f"\n{BOLD}Confusion Matrix:{RST}")
    print(f"  True  Positives (attackers caught)    : {GRN}{BOLD}{TP:>4}{RST}")
    print(f"  False Negatives (attackers missed)    : {RED}{BOLD}{FN:>4}{RST}")
    print(f"  True  Negatives (clean cleared)       : {GRN}{BOLD}{TN:>4}{RST}")
    print(f"  False Positives (clean flagged)       : {YEL}{BOLD}{FP:>4}{RST}")

    print(f"\n{BOLD}Performance Metrics:{RST}")
    print(f"  Precision     : {BOLD}{precision*100:>6.2f}%{RST}  (of flagged, how many were real attackers)")
    print(f"  Recall        : {BOLD}{recall*100:>6.2f}%{RST}  (of real attackers, how many were caught)")
    print(f"  F1 Score      : {BOLD}{f1*100:>6.2f}%{RST}  (harmonic mean)")
    print(f"  Accuracy      : {BOLD}{accuracy*100:>6.2f}%{RST}  (overall correct classifications)")
    print(f"  False Pos Rate: {BOLD}{fpr*100:>6.2f}%{RST}  (clean wallets wrongly flagged)")
    print(f"  False Neg Rate: {BOLD}{fnr*100:>6.2f}%{RST}  (attackers that slipped through)")

    print(f"\n{BOLD}Score Separation (key discriminative power metric):{RST}")
    print(f"  Avg attacker C(t)  : {RED}{BOLD}{avg_attacker:.6f}{RST}")
    print(f"  Avg control  C(t)  : {GRN}{BOLD}{avg_control:.6f}{RST}")
    print(f"  Separation delta   : {BOLD}{separation:+.6f}{RST}  {'(TRION separates classes ✓)' if separation > 0 else '(needs improvement)'}")

    print(f"\n{BOLD}Merkle Proof:{RST}")
    print(f"  Root              : {CYN}{merkle_root}{RST}")
    print(f"  Leaves            : {len(merkle_leaves)}")
    print(f"  Layers            : {len(proof_layers)}")

    print(f"\n{BOLD}Coverage:{RST}")
    total_val = sum(ex["amount_usd"] for ex in exploits)
    caught_val = sum(ex["amount_usd"] for ex, r in
                     zip(exploits, [res["signal"] for res in results if res["entity_type"]=="ATTACKER"])
                     if r["trion_flagged"])
    print(f"  Total exploit value tested : ${total_val:>15,}")
    print(f"  Value TRION would catch    : ${caught_val:>15,}  ({caught_val/total_val*100:.1f}%)" if total_val > 0 else f"  Value TRION would catch    : ${caught_val:>15,}  (N/A)")
    print(f"  Exploits tested            : {len(exploits)}")
    print(f"  Attack types covered       : FLASH_LOAN, REENTRANCY, ORACLE_MANIP,")
    print(f"                               GOVERNANCE_ATTACK, BRIDGE_DRAIN,")
    print(f"                               PRIVATE_KEY_COMPROMISE, APPROVAL_EXPLOIT")

    # ── Save results ───────────────────────────────────────────────────────────
    report = {
        "metadata": {
            "generated_at": datetime.now(timezone.utc).isoformat(),
            "oracle_url":   ORACLE_URL,
            "dataset_version": dataset["metadata"]["version"],
            "exploits_tested": len(exploits),
            "controls_tested": len(controls),
        },
        "metrics": {
            "TP": TP, "FP": FP, "TN": TN, "FN": FN,
            "precision":   round(precision,  6),
            "recall":      round(recall,     6),
            "f1_score":    round(f1,         6),
            "accuracy":    round(accuracy,   6),
            "false_positive_rate": round(fpr, 6),
            "false_negative_rate": round(fnr, 6),
            "avg_attacker_coherence": round(avg_attacker, 6),
            "avg_control_coherence":  round(avg_control,  6),
            "separation_delta":       round(separation,   6),
            "total_exploit_usd":      total_val,
            "caught_exploit_usd":     caught_val,
            "catch_rate_pct":         round(caught_val/total_val*100, 2) if total_val > 0 else 0.0,
        },
        "merkle": {
            "root":   merkle_root,
            "leaves": len(merkle_leaves),
            "layers": len(proof_layers),
        },
        "results": results,
    }

    report_path = os.path.join(RESULTS_DIR, "backtest_report.json")
    with open(report_path, "w") as f:
        json.dump(report, f, indent=2, default=str)

    merkle_path = os.path.join(RESULTS_DIR, "merkle_proof.json")
    with open(merkle_path, "w") as f:
        json.dump({
            "root":          merkle_root,
            "leaves":        merkle_leaves,
            "proof_layers":  proof_layers,
            "generated_at":  datetime.now(timezone.utc).isoformat(),
            "metrics_hash":  sha256(json.dumps(report["metrics"], sort_keys=True)),
        }, f, indent=2)

    summary_path = os.path.join(RESULTS_DIR, "summary.txt")
    with open(summary_path, "w") as f:
        f.write(f"TRION Backtest — {datetime.now(timezone.utc).isoformat()}\n")
        f.write(f"Exploits: {len(exploits)} | Controls: {len(controls)}\n")
        f.write(f"TP={TP} FP={FP} TN={TN} FN={FN}\n")
        f.write(f"Precision={precision:.4f} Recall={recall:.4f} F1={f1:.4f}\n")
        f.write(f"Accuracy={accuracy:.4f} FPR={fpr:.4f} FNR={fnr:.4f}\n")
        f.write(f"Separation={separation:+.6f}\n")
        f.write(f"Catch rate: {caught_val/total_val*100:.1f}% of ${total_val:,}\n" if total_val > 0 else f"Catch rate: N/A of ${total_val:,}\n")
        f.write(f"Merkle root: {merkle_root}\n")

    print(f"\n{GRN}✓ Report saved    → {report_path}{RST}")
    print(f"{GRN}✓ Merkle proof    → {merkle_path}{RST}")
    print(f"{GRN}✓ Summary         → {summary_path}{RST}")
    print(f"\n{BOLD}Run publisher to anchor proof on Arbitrum Sepolia:{RST}")
    print(f"  node backtest/publish_proof.js\n")

    return report

if __name__ == "__main__":
    main()
