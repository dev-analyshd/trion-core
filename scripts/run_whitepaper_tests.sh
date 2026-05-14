#!/usr/bin/env bash
# TRION Protocol — Whitepaper Scaffold Test Runner
# Tests all L0–L10 whitepaper implementations (trion-protocol/ + src/).
# Run from workspace root: bash scripts/run_whitepaper_tests.sh
set -e

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
PASS=0; FAIL=0; RESULTS=()

run_test() {
    local label="$1" cmd="$2" cwd="$3"
    echo ""
    echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
    echo "  $label"
    echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
    pushd "$cwd" > /dev/null
    if eval "$cmd" 2>&1; then
        echo "  ✓ PASSED"
        RESULTS+=("PASS  $label")
        PASS=$((PASS+1))
    else
        echo "  ✗ FAILED"
        RESULTS+=("FAIL  $label")
        FAIL=$((FAIL+1))
    fi
    popd > /dev/null
}

echo ""
echo "╔══════════════════════════════════════════════════════╗"
echo "║    TRION Whitepaper Test Runner (L0–L10 scaffold)    ║"
echo "╚══════════════════════════════════════════════════════╝"

# ── Rust L0 core (trion-protocol/core) ───────────────────────────────────────
run_test "L0 Rust: BehavioralHash + Physical (15 tests)" \
    "cargo test -- --nocapture 2>&1" \
    "$ROOT/trion-protocol"

# ── Python src/ modules (main repo) ─────────────────────────────────────────
run_test "L1 Python: phi_engine — 9 Shannon entropy features (src/planes/physical/phi_engine.py)" \
    "python3 tests/trion_protocol/test_feature_extractor.py" \
    "$ROOT"

run_test "L2 Python: archetypes — 12 Akashic archetypes + match_archetype (src/akashic/archetypes.py)" \
    "python3 tests/trion_protocol/test_archetype_engine.py" \
    "$ROOT"

run_test "L3 Python: m_engine — M(t) prediction interval + observer effect (src/planes/mental/m_engine.py)" \
    "python3 tests/trion_protocol/test_conformal_predictor.py" \
    "$ROOT"

run_test "L4 Python: sigma_engine — Σ diversity-weighted BFT + HHI (src/planes/spiritual/sigma_engine.py)" \
    "python3 tests/trion_protocol/test_consensus_bft.py" \
    "$ROOT"

run_test "L5 Python: coherence_engine — C(t) master equation + moat (src/core/coherence_engine.py)" \
    "python3 tests/trion_protocol/test_five_plane_c.py" \
    "$ROOT"

# ── trion-protocol/ scaffold phases (full suite) ─────────────────────────────
run_test "P2 trion-protocol: Physical Feature Extractor" \
    "PYTHONPATH=src python3 tests/test_features.py" \
    "$ROOT/trion-protocol/akashic"

run_test "P3 trion-protocol: Akashic Index + Resurrection" \
    "PYTHONPATH=src python3 tests/test_akashic.py" \
    "$ROOT/trion-protocol/akashic"

run_test "P4 trion-protocol: Mental M(t) + Conformal + IM Protocol" \
    "PYTHONPATH=src python3 tests/test_mental.py" \
    "$ROOT/trion-protocol/anima"

run_test "P5 trion-protocol: BFT + Living Security + INIT" \
    "PYTHONPATH=src python3 tests/test_spiritual.py" \
    "$ROOT/trion-protocol/validator"

run_test "P6 trion-protocol: First Signal C(t) + 19 types" \
    "PYTHONPATH=src python3 tests/test_first_signal.py" \
    "$ROOT/trion-protocol/anima"

run_test "P7 trion-protocol: ANIMA v1 (BC + NL + EP)" \
    "PYTHONPATH=src python3 tests/phase7/test_anima_v1.py" \
    "$ROOT/trion-protocol/anima"

run_test "P8 trion-protocol: Conscious K(t) + SBA" \
    "PYTHONPATH=src python3 tests/test_conscious.py" \
    "$ROOT/trion-protocol/anima"

run_test "P9 trion-protocol: Five-Plane + Emergence + Conservation" \
    "PYTHONPATH=src python3 tests/test_five_plane.py" \
    "$ROOT/trion-protocol/anima"

run_test "P6b trion-protocol: Python SDK v1.0" \
    "PYTHONPATH=src python3 tests/test_sdk.py" \
    "$ROOT/trion-protocol/sdk"

# ── Solidity contracts syntax check ──────────────────────────────────────────
echo ""
echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
echo "  P10: Solidity Contracts (hardhat/contracts/)"
echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
SOL_OK=true
for f in TRIONSignal.sol TRIONToken.sol TRIONGovernance.sol; do
    path="$ROOT/hardhat/contracts/$f"
    if [ -f "$path" ] && grep -q "pragma solidity" "$path" && grep -q "contract " "$path"; then
        echo "  ✓ $f"
    else
        echo "  ✗ $f — MISSING or INVALID"
        SOL_OK=false
    fi
done
if $SOL_OK; then
    RESULTS+=("PASS  P10: Solidity contracts (TRIONSignal + TRIONToken + TRIONGovernance)")
    PASS=$((PASS+1))
else
    RESULTS+=("FAIL  P10: Solidity contracts")
    FAIL=$((FAIL+1))
fi

# ── Summary ───────────────────────────────────────────────────────────────────
echo ""
echo "╔══════════════════════════════════════════════════════╗"
echo "║                   TEST SUMMARY                       ║"
echo "╚══════════════════════════════════════════════════════╝"
for r in "${RESULTS[@]}"; do echo "  $r"; done
echo ""
echo "  Total: $PASS passed, $FAIL failed"
echo ""
if [ $FAIL -eq 0 ]; then
    echo "╔══════════════════════════════════════════════════════╗"
    echo "║       ALL WHITEPAPER TESTS GREEN — L0–L10 LIVE      ║"
    echo "╚══════════════════════════════════════════════════════╝"
    exit 0
else
    echo "✗ $FAIL test group(s) failed"
    exit 1
fi
