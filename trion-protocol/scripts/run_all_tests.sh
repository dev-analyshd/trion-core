#!/usr/bin/env bash
# TRION Protocol — Master Test Runner
# Runs all phases in order; exits 1 on first failure.
set -e

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
PASS=0
FAIL=0
RESULTS=()

run_phase() {
    local phase="$1"
    local label="$2"
    local cmd="$3"
    local cwd="$4"

    echo ""
    echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
    echo "  $phase — $label"
    echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"

    pushd "$cwd" > /dev/null
    if eval "$cmd"; then
        echo "  ✓ $phase PASSED"
        RESULTS+=("PASS: $phase — $label")
        PASS=$((PASS + 1))
    else
        echo "  ✗ $phase FAILED"
        RESULTS+=("FAIL: $phase — $label")
        FAIL=$((FAIL + 1))
    fi
    popd > /dev/null
}

echo ""
echo "╔══════════════════════════════════════════════════════╗"
echo "║         TRION PROTOCOL — MASTER TEST RUNNER          ║"
echo "╚══════════════════════════════════════════════════════╝"

# ── Phase 1+2: Rust L0 + Physical ────────────────────────────────────────────
run_phase "P1+P2" "Rust L0 BH + ERP + Physical" \
    "cargo test -- --nocapture 2>&1" \
    "$ROOT"

# ── Phase 2: Python feature extractor ────────────────────────────────────────
run_phase "P2" "Python Physical Feature Extractor" \
    "PYTHONPATH=src python3 tests/test_features.py" \
    "$ROOT/akashic"

# ── Phase 3: Akashic Index ───────────────────────────────────────────────────
run_phase "P3" "Akashic Index (FAISS archetypes + resurrection)" \
    "PYTHONPATH=src python3 tests/test_akashic.py" \
    "$ROOT/akashic"

# ── Phase 4: Mental Layer ─────────────────────────────────────────────────────
run_phase "P4" "Mental Layer M(t) + ANIMA stub + IM protocol" \
    "PYTHONPATH=src python3 tests/test_mental.py" \
    "$ROOT/anima"

# ── Phase 5: Spiritual + Living Security ─────────────────────────────────────
run_phase "P5" "BFT Sigma(t) + GK evolution + Immune + Epigenetic + INIT" \
    "PYTHONPATH=src python3 tests/test_spiritual.py" \
    "$ROOT/validator"

# ── Phase 6: First Signal + SDK ──────────────────────────────────────────────
run_phase "P6a" "First Signal C(t) 3-plane + 19 signal types" \
    "PYTHONPATH=src python3 tests/test_first_signal.py" \
    "$ROOT/anima"

run_phase "P6b" "Python SDK v1.0 (BH verify + signal validate)" \
    "PYTHONPATH=src python3 tests/test_sdk.py" \
    "$ROOT/sdk"

# ── Phase 7: ANIMA v1 ────────────────────────────────────────────────────────
run_phase "P7" "ANIMA v1 (BC + NL + EP + MG Monitor)" \
    "PYTHONPATH=src python3 tests/phase7/test_anima_v1.py" \
    "$ROOT/anima"

# ── Phase 8: Conscious Layer ─────────────────────────────────────────────────
run_phase "P8" "Conscious Layer K(t) + SBA sovereignty protocol" \
    "PYTHONPATH=src python3 tests/test_conscious.py" \
    "$ROOT/anima"

# ── Phase 9: Five-plane full ──────────────────────────────────────────────────
run_phase "P9" "Five-plane C(t) + emergence + information conservation" \
    "PYTHONPATH=src python3 tests/test_five_plane.py" \
    "$ROOT/anima"

# ── Phase 10: Solidity contracts syntax ──────────────────────────────────────
echo ""
echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
echo "  P10 — Solidity Contract Syntax Verification"
echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
contracts=("TRIONSignal.sol" "TRIONToken.sol" "TRIONGovernance.sol")
SOL_PASS=true
for contract in "${contracts[@]}"; do
    path="$ROOT/contracts/src/$contract"
    if [ -f "$path" ]; then
        # Validate pragma + key structural elements
        if grep -q "pragma solidity" "$path" && \
           grep -q "SPDX-License-Identifier" "$path" && \
           grep -q "contract " "$path"; then
            echo "  ✓ $contract — structure valid"
        else
            echo "  ✗ $contract — missing required elements"
            SOL_PASS=false
        fi
    else
        echo "  ✗ $contract — FILE NOT FOUND"
        SOL_PASS=false
    fi
done
if $SOL_PASS; then
    RESULTS+=("PASS: P10 — Solidity contracts (TRIONSignal + TRIONToken + TRIONGovernance)")
    PASS=$((PASS + 1))
else
    RESULTS+=("FAIL: P10 — Solidity contracts")
    FAIL=$((FAIL + 1))
fi

# ── Summary ───────────────────────────────────────────────────────────────────
echo ""
echo "╔══════════════════════════════════════════════════════╗"
echo "║                   TEST SUMMARY                       ║"
echo "╚══════════════════════════════════════════════════════╝"
echo ""
for r in "${RESULTS[@]}"; do
    echo "  $r"
done
echo ""
echo "  Total: $PASS passed, $FAIL failed"
echo ""

if [ $FAIL -eq 0 ]; then
    echo "╔══════════════════════════════════════════════════════╗"
    echo "║           ALL PHASES GREEN — TRION COMPLETE          ║"
    echo "╚══════════════════════════════════════════════════════╝"
    exit 0
else
    echo "╔══════════════════════════════════════════════════════╗"
    echo "║         $FAIL PHASE(S) FAILED — SEE ABOVE            ║"
    echo "╚══════════════════════════════════════════════════════╝"
    exit 1
fi
